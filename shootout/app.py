"""GLUT window, cameras, clip export and the optional gamepad and phone inputs."""

import argparse
import atexit
import json
import math
import os
import subprocess
import sys
import threading
import time

from OpenGL.GL import *  # noqa: F401,F403
from OpenGL.GLU import *  # noqa: F401,F403
from OpenGL.GLUT import *  # noqa: F401,F403

from . import config as C, controls, gfx, hud, render, scenarios
from .audio import Audio
from .game import REPLAY_FPS, Game, auto_camera
from .gamepad import Gamepads

CLIP_DIR = os.path.join(os.path.expanduser('~'), 'penalty_shootout_clips')
CLIP_WIDTH = 480
CLIP_EVERY = 3            # keep every third frame of the slow-motion replay

FRAME_TIME = 1.0 / 60.0  # frames are scheduled against this, not slept after the work
MAX_DT = 0.25             # longest step the game takes in one go: no slow motion down to 4 fps
SCREEN_EVERY = 0.1        # the big screen's live picture updates at 10 fps

game = None
pads = None
phone = None
_last_t = None
_next_t = None
_screen_t = -1.0
_clip = None              # frames being captured for a GIF
_clip_done = []           # messages from the thread that encodes the GIF
net = None                # LAN session, when hosting or joining
lobby = None              # waiting for the other LAN player
joining = None            # (session, deadline) until the host's settings arrive
_window = dict(full=False, size=(1200, 800))
_cleaned = False


def camera_eye(g, view):
    """Eye and look-at point for the current camera."""
    bx, by, bz = view['ball']
    if g.photo:
        # Photo mode: orbit the frozen moment, centred between ball and keeper
        ang, height, dist = g.photo_cam
        (kx, ky, kz), _, _ = view['keeper']
        cx, cz = (bx + kx) / 2.0, (bz + kz) / 2.0 if abs(bz - kz) < 8.0 else bz
        a = math.radians(ang)
        return (cx + dist * math.sin(a), height, cz + dist * math.cos(a)), (cx, max(0.4, by * 0.6 + 0.4), cz)
    if g.phase == 'replay':
        cam = replay_camera(g)
        if cam == 'strike':
            # Low by the spot, side on, for the super slow-motion strike
            sx, sz = view['shooter']['pos']
            return (sx + 2.6, 0.55, sz - 0.6), (sx * 0.5 + bx * 0.5, 0.45, (sz + bz) * 0.5 - 0.3)
        if cam == 'goalline':
            # The goal-line camera, level with the line, looking across it
            glt = g.replay.get('glt') or {}
            gx = (glt.get('ball') or (0.0, 0.0, 0.0))[0]
            return (C.GOAL_HALF_WIDTH + 2.6, 1.5, C.GOAL_LINE_Z + 1.6), (gx, 0.9, C.GOAL_LINE_Z - 0.2)
        if cam == 'spider':
            # The spider cam on its wires, floating over the run-up
            return (bx * 0.4 + 1.5, 9.5, bz + 7.5), (bx, by * 0.5, bz - 2.0)
        if cam == 'ball':
            # Riding just behind the ball all the way to the net
            return (bx + 1.4, by + 0.6, bz + 2.4), (bx * 0.5, 1.0, C.GOAL_LINE_Z)
        if cam == 'side':
            return (9.0, 1.6, C.GOAL_LINE_Z + 2.5), (0.0, 1.0, C.GOAL_LINE_Z + 0.5)
        # Reverse angle from behind the net, the classic replay shot
        return (4.5, 2.3, C.GOAL_LINE_Z - 6.5), (0.0, 1.0, C.GOAL_LINE_Z + 4.0)
    if g.phase == 'ritual' and g.camera == 'broadcast' and g.phase_t > 0.62 * g.ritual_len:
        # Close-up on the taker's face as he backs off to start the run-up
        sx, sz = view['shooter']['pos']
        yaw = math.radians(view['shooter']['yaw'])
        fx, fz = -math.sin(yaw), -math.cos(yaw)          # the way he is facing
        return (sx + 1.35 * fx + 0.35, 1.75, sz + 1.35 * fz), (sx, 1.62, sz)
    win = g.scene_env().get('win')
    if win and g.camera == 'broadcast' and g.phase in ('result', 'ended'):
        # The winning moment: the camera circles the celebrations
        tx, tz = render._win_target(view, win)
        a = math.radians(-55.0 + 110.0 * min(1.0, win['t'] / 7.0))      # sweeps round in front
        dist = 6.5 - 1.5 * min(1.0, win['t'] / 4.0)
        return (tx + dist * math.sin(a), 2.0 + 0.6 * math.sin(win['t'] * 0.5), tz + dist * math.cos(a)), (tx, 1.1, tz)
    if g.phase in ('walk', 'ritual') and g.camera == 'broadcast':
        # A steadicam walking behind the taker from halfway, bobbing with the
        # operator's steps and drifting round to the side as they near the spot
        sx, sz = view['shooter']['pos']
        r = min(1.0, g.phase_t / g.walk_len) if g.phase == 'walk' else 1.0
        bob = 0.035 * math.sin(g.clock * 9.0)
        drift = 0.12 * math.sin(g.clock * 0.7)
        return ((sx - 0.6 - 0.9 * r + drift, 1.85 - 0.25 * r + bob, sz + 3.6 - 0.6 * r),
                (sx * 0.4, 1.35 - 0.2 * r, sz - 6.0))
    cam = g.camera
    if cam == 'keeper' and not g.is_human(g.keeper_side()):
        cam = 'broadcast'          # the keeper's eye view is for a human keeper
    if cam == 'keeper':
        (kx, ky, kz), lean, arms = view['keeper']
        eye = (kx, ky + 0.7, kz + 0.05)
        if g.phase in ('flight', 'result', 'var', 'rebound') and bz < kz - 0.5:
            return eye, (bx, by, bz)
        target = (bx, by, bz) if g.phase in ('flight', 'rebound') else (0.0, 0.8, C.SPOT_Z)
        return eye, target
    if cam == 'goal':
        return (2.2, 2.0, C.GOAL_LINE_Z - 7.5), (0.0, 1.0, C.SPOT_Z)
    if cam == 'side':
        return (13.0, 3.5, C.GOAL_LINE_Z + 6.0), (0.0, 1.0, C.GOAL_LINE_Z + 3.0)
    if cam == 'orbit':
        ang, height, dist = g.orbit
        a = math.radians(ang)
        return ((dist * math.sin(a), height, C.SPOT_Z + dist * math.cos(a)),
                (0.0, 1.0, C.GOAL_LINE_Z + 4.0))
    # Broadcast: behind the kicker, easing in a touch as the ball flies
    push = 0.0
    if g.phase in ('flight', 'result') and g.contact_t is not None:
        push = min(1.0, g.contact_t / 0.8) * 1.2
    return (0.0, 2.9 - 0.3 * push, C.SPOT_Z + 8.6 - push), (0.0, 0.9, C.GOAL_LINE_Z)


def replay_camera(g):
    """The replay camera in use: the director's cut, or the one picked with C."""
    if g.replay_cam != 'auto' or not g.replay:
        return g.replay_cam
    return auto_camera(int(g.replay['t'] * REPLAY_FPS), g.replay)


def load_camera(eye, look, fov, aspect, near=0.05, far=250.0):
    glMatrixMode(GL_PROJECTION)
    glLoadIdentity()
    gluPerspective(fov, aspect, near, far)
    glMatrixMode(GL_MODELVIEW)
    glLoadIdentity()
    gluLookAt(eye[0], eye[1], eye[2], look[0], look[1], look[2], 0, 1, 0)
    gfx.set_view(eye, look, near, far)


def setup_camera(g, view):
    """Load the current camera. Returns the eye, the look-at point and the field of view."""
    w = max(1, glutGet(GLUT_WINDOW_WIDTH))
    h = max(1, glutGet(GLUT_WINDOW_HEIGHT))
    glViewport(0, 0, w, h)
    fov = 70.0 if g.scene_env()['first_person'] else 50.0
    if g.phase == 'replay' and replay_camera(g) in ('strike', 'goalline'):
        fov = 34.0                               # long lens
    eye, look = camera_eye(g, view)
    if g.shake > 0:
        amp = 0.12 * g.shake
        eye = (eye[0] + amp * math.sin(g.clock * 53.0), eye[1] + amp * math.cos(g.clock * 47.0), eye[2])
    load_camera(eye, look, fov, w / float(h))
    return eye, look, fov


def _dist(a, b):
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def post_settings(g, view, env, eye, look, fov):
    """Grading, bloom, depth of field, motion blur and filters for this frame."""
    weather, daytime = env['weather'], env['daytime']
    grade = weather if weather in ('rain', 'snow', 'fog') else (
        'dusk' if daytime in ('dusk', 'sunset') else daytime)
    lit = daytime == 'night' or (daytime == 'dusk' and env.get('dusk', 0.0) > 0.4)
    post = dict(grade=grade, bloom=0.85 if lit else 0.4, vignette=0.32, time=g.clock, sat=1.0)
    if g.phase == 'ritual' and g.camera == 'broadcast' and g.phase_t > 0.62 * g.ritual_len:
        sx, sz = view['shooter']['pos']
        post.update(focus=_dist(eye, (sx, 1.62, sz)), range=0.7)        # shallow focus on the face
    elif g.phase == 'walk' and g.camera == 'broadcast':
        sx, sz = view['shooter']['pos']
        post.update(focus=_dist(eye, (sx, 1.4, sz)), range=3.5)
    elif g.phase == 'replay' and replay_camera(g) == 'strike':
        post.update(focus=_dist(eye, view['ball']), range=1.5)
    if view.get('rocket') and g.phase == 'flight':
        post['blur'] = 0.55
    if g.phase == 'replay':
        post['vignette'] = 0.5
    if env.get('win') and g.phase in ('result', 'ended'):
        post.update(sat=1.15, vignette=0.45)
    if g.photo:
        post['filter'] = g.photo_filter
        if g.photo_dof:
            post.update(focus=_dist(eye, look), range=4.0)
        post['vignette'] = 0.4
    w = max(1, glutGet(GLUT_WINDOW_WIDTH))
    h = max(1, glutGet(GLUT_WINDOW_HEIGHT))
    proj = gfx.perspective(fov, w / float(h), 0.05, 250.0)
    view_m = gfx.look_at(eye, look)
    haze = []
    for p, strength in render.effects['haze'][:2]:
        sp = gfx.project(p, proj, view_m)
        if sp is not None and -0.2 < sp[0] < 1.2 and -0.2 < sp[1] < 1.2:
            r = max(0.03, min(0.25, 1.4 / max(1.0, _dist(eye, p)) * 0.5))
            haze.append((sp[0], sp[1], r, min(1.0, strength)))
    post['haze'] = haze
    return post


def draw_big_screen_picture(g, env):
    """High quality: draw the scene again from a TV camera into the big screen's picture."""
    if C.VARIANT != 'stadium' or env.get('theme') not in ('classic', 'derby', 'arena') or not gfx.begin_screen():
        return
    sview, eye, look = g.screen_view()
    glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
    load_camera(eye, look, 40.0, 16.0 / 9.0)
    render.draw_scene(sview, None, g.clock, env, screen=True)
    gfx.end_screen()
    gfx.resume_frame()


def _check_graphics(g):
    """Rebuild the pipeline when the quality setting changes; say so if it fails."""
    if g.gfx_request:
        g.gfx_request = False
        if not gfx.init(g.graphics):
            g.toast = (f"Shaders unavailable, using low quality: {gfx.state['error']}", g.clock)
        g.graphics = gfx.quality()


def display_showcase(g):
    """The select and create screens: a character on a turntable, then the HUD."""
    w = max(1, glutGet(GLUT_WINDOW_WIDTH))
    h = max(1, glutGet(GLUT_WINDOW_HEIGHT))
    daytime = g.daytime if g.daytime in ('night', 'day') else 'night'
    render.prepare(dict(daytime=daytime, weather='clear'))
    gfx.begin_frame(w, h)
    glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
    glViewport(0, 0, w, h)
    eye_x = 1.9                             # the figure sits left of centre, the stats panel right
    eye, look = (eye_x, 1.35, C.SPOT_Z + 6.4), (eye_x, 1.05, C.SPOT_Z)
    load_camera(eye, look, 40.0, w / float(h))
    fig, keeper, cel = hud.showcase_subject(g)
    kit = dict(C.KITS['p1'])
    render.draw_showcase(fig, keeper if fig is not None else False, kit, g.clock, daytime, cel if fig else None)
    gfx.end_frame(dict(grade=daytime, bloom=0.6, vignette=0.4, time=g.clock, focus=_dist(eye, look), range=2.5))
    hud.draw(g)
    glutSwapBuffers()


def display():
    g = game
    if g.ui in ('select', 'create'):
        display_showcase(g)
        return
    _check_graphics(g)
    draw_world(g)
    if g.photo:
        hud.photo_decor(g)
    if g.photo_request:
        g.photo_request = False
        g.toast = (save_photo(), g.clock)
    hud.draw(g)
    _capture_frame(g)
    glutSwapBuffers()
    if g.clipboard_request:
        if not copy_to_clipboard(g.clipboard_request):
            g.toast = ('No clipboard tool found: the grid is in ' + os.path.basename(_daily_file()), g.clock)
        g.clipboard_request = None


def draw_world(g, live_screen=True):
    """The 3D scene and its post-processing, without the HUD."""
    global _screen_t
    view = g.current_view()
    w = max(1, glutGet(GLUT_WINDOW_WIDTH))
    h = max(1, glutGet(GLUT_WINDOW_HEIGHT))
    eye, look = camera_eye(g, view)
    env = render.prepare(dict(g.scene_env(), eye=eye))
    gfx.begin_frame(w, h)
    if gfx.fancy():
        gfx.render_shadows(render.light_dir(), lambda: render.draw_casters(view, env))
        gfx.resume_frame()
        now = time.perf_counter()
        if gfx.high() and live_screen and now - _screen_t >= SCREEN_EVERY:
            _screen_t = now
            draw_big_screen_picture(g, env)
        render.set_environment(env['daytime'], env['weather'], env['dusk'])
    glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
    eye, look, fov = setup_camera(g, view)
    aim = tuple(g.aim) if g.aim_visible() else None
    render.draw_scene(view, aim, g.clock, env)
    gfx.end_frame(post_settings(g, view, env, eye, look, fov))


def _daily_file():
    from .game import DAILY_FILE
    return DAILY_FILE


def copy_to_clipboard(s):
    """Put text on the system clipboard with whatever tool the OS has."""
    if sys.platform.startswith('win'):
        cmds = [['clip']]
    elif sys.platform == 'darwin':
        cmds = [['pbcopy']]
    else:
        cmds = [['wl-copy'], ['xclip', '-selection', 'clipboard'], ['xsel', '--clipboard', '--input']]
    for cmd in cmds:
        try:
            subprocess.run(cmd, input=s.encode('utf-16' if cmd == ['clip'] else 'utf-8'), check=True, timeout=3)
            return True
        except (OSError, subprocess.SubprocessError):
            continue
    return False


def _grab():
    w = max(1, glutGet(GLUT_WINDOW_WIDTH))
    h = max(1, glutGet(GLUT_WINDOW_HEIGHT))
    glPixelStorei(GL_PACK_ALIGNMENT, 1)
    return w, h, bytes(glReadPixels(0, 0, w, h, GL_RGB, GL_UNSIGNED_BYTE))


def save_photo(directory=None):
    """Photo mode: save the frame as drawn, without the HUD."""
    directory = directory or CLIP_DIR
    w, h, data = _grab()
    stamp = time.strftime('%Y%m%d-%H%M%S')
    try:
        os.makedirs(directory, exist_ok=True)
        try:
            from PIL import Image
        except ImportError:
            path = os.path.join(directory, f'photo-{stamp}.ppm')
            rows = [data[y * w * 3:(y + 1) * w * 3] for y in range(h - 1, -1, -1)]
            with open(path, 'wb') as f:
                f.write(f'P6 {w} {h} 255\n'.encode() + b''.join(rows))
            return f'Photo saved: {path}'
        path = os.path.join(directory, f'photo-{stamp}.png')
        Image.frombytes('RGB', (w, h), data).transpose(Image.FLIP_TOP_BOTTOM).save(path)
        return f'Photo saved: {path}'
    except OSError as e:
        return f'Could not save photo: {e}'


# ---------------------------------------------------------------- GIF export
def shrink(w, h, data, width=CLIP_WIDTH):
    """Cut a grabbed frame down to about width pixels across while capturing,
    so a long clip stays small: (w, h, rows bottom-up) like the input."""
    f = max(1, w // width)
    if f == 1:
        return w, h, data
    nw, nh = w // f, h // f
    out = bytearray(nw * nh * 3)
    stride = w * 3
    for y in range(nh):
        row = data[y * f * stride:y * f * stride + nw * f * 3]
        o = y * nw * 3
        for c in range(3):
            out[o + c:o + nw * 3:3] = row[c::3 * f]
    return nw, nh, bytes(out)


def _capture_frame(g):
    """While a requested clip is replaying, grab every few frames, small."""
    global _clip
    if g.export_request and g.phase == 'replay':
        if _clip is None:
            _clip = dict(frames=[], n=0)
        _clip['n'] += 1
        if _clip['n'] % CLIP_EVERY:
            return
        _clip['frames'].append(shrink(*_grab()))
        if len(_clip['frames']) > 400:
            g.phase = 'ended'
    if _clip is not None and g.phase != 'replay':
        frames = _clip['frames']
        _clip = None
        g.export_request = False
        g.toast = ('Saving the clip...', g.clock)
        # Encoding takes a few seconds: do it off the main thread so the game keeps running
        threading.Thread(target=lambda: _clip_done.append(save_clip(frames)), daemon=True).start()


def save_clip(frames, directory=CLIP_DIR):
    """Write the frames as an animated GIF with Pillow, or as PPM images without it."""
    if not frames:
        return 'Nothing to save'
    stamp = time.strftime('%Y%m%d-%H%M%S')
    try:
        os.makedirs(directory, exist_ok=True)
        try:
            from PIL import Image
        except ImportError:
            folder = os.path.join(directory, f'shootout-{stamp}')
            os.makedirs(folder, exist_ok=True)
            for i, (w, h, data) in enumerate(frames):
                rows = [data[y * w * 3:(y + 1) * w * 3] for y in range(h - 1, -1, -1)]
                with open(os.path.join(folder, f'frame{i:04d}.ppm'), 'wb') as f:
                    f.write(f'P6 {w} {h} 255\n'.encode() + b''.join(rows))
            return f'Saved frames to {folder} (pip install Pillow for a GIF)'
        images = []
        for w, h, data in frames:
            img = Image.frombytes('RGB', (w, h), data).transpose(Image.FLIP_TOP_BOTTOM)
            if w > CLIP_WIDTH:
                img = img.resize((CLIP_WIDTH, max(1, int(h * CLIP_WIDTH / w))))
            images.append(img.convert('P', palette=Image.ADAPTIVE))
        path = os.path.join(directory, f'shootout-{stamp}.gif')
        images[0].save(path, save_all=True, append_images=images[1:], duration=int(1000 * CLIP_EVERY / 60),
                       loop=0)
        return f'Clip saved: {path}'
    except (OSError, ValueError) as e:
        return f'Could not save clip: {e}'


# --------------------------------------------------------------- main loop
def _phone_service(g):
    """Start or stop the phone controller to match the menu setting."""
    global phone
    if g.phone and phone is None:
        try:
            from .phone import PhoneServer
            phone = PhoneServer()
            g.phone_info = f'Phone controller: {phone.url()}  PIN {phone.pin}'
        except OSError as e:
            g.phone = False
            g.toast = (f'Phone controller unavailable: {e}', g.clock)
    elif not g.phone and phone is not None:
        phone.stop()
        phone = None
        g.phone_info = None
    if phone is not None:
        phone.apply(g)


def _lan_service(g):
    """Wait for the other LAN player without freezing the window, and drop
    the session when the player goes back to the menu."""
    global lobby, joining, net
    from . import net as lan
    if lobby is not None:
        if g.ui != 'lan':                       # ESC on the waiting screen
            lobby.close()
            lobby = None
            return
        try:
            sock = lobby.poll()
        except OSError as e:
            lobby.close()
            lobby = None
            g.ui = 'menu'
            g.toast = (f'LAN game failed: {e}', g.clock)
            return
        if sock is not None:
            session, slot = lan.NetSession(sock, lobby.slot), lobby.slot
            lobby = None
            if slot == 'p1':
                session.start_host(g)
                net = session
            else:
                joining = (session, time.monotonic() + 15.0)
                g.lan_lines = ['Connected: waiting for the host to start...', '', 'ESC back to the menu']
    if joining is not None:
        session, deadline = joining
        if g.ui != 'lan':
            session.close()
            joining = None
        elif session.poll_join(g):
            net, joining = session, None
        elif session.closed or time.monotonic() > deadline:
            session.close()
            joining = None
            g.ui = 'menu'
            g.toast = ('The host did not answer', g.clock)
    if net is not None and g.ui == 'menu':
        net.close()
        net = None
        g.local_slot = g.lan_state = g.lan_notice = None


def tick(_value=0):
    """One step of the game. Frames are scheduled against a target time, so
    the work and the wait add up to 1/60 s instead of the work plus 16 ms."""
    global _last_t, _next_t
    now = time.perf_counter()
    dt = 0.0 if _last_t is None else min(MAX_DT, now - _last_t)
    _last_t = now
    if pads is not None and pads.poll(game, dt) == 'quit':
        _quit()
    _phone_service(game)
    _lan_service(game)
    if net is not None:
        net.pump(game, dt)
    else:
        game.update(dt)
    while _clip_done:
        game.toast = (_clip_done.pop(0), game.clock)
    glutPostRedisplay()
    after = time.perf_counter()
    _next_t = (_next_t or now) + FRAME_TIME
    if _next_t < after - FRAME_TIME:
        _next_t = after                        # running behind: don't try to catch up
    glutTimerFunc(max(0, int((_next_t - after) * 1000.0)), tick, 0)


def cleanup():
    """Stop the phone server and close LAN sockets (also when the window is closed)."""
    global phone, net, lobby, joining, _cleaned
    if _cleaned:
        return
    _cleaned = True
    for thing in (phone, net, lobby, joining[0] if joining else None):
        if thing is None:
            continue
        try:
            thing.stop() if thing is phone else thing.close()
        except Exception:      # noqa: BLE001 - shutting down regardless
            pass
    phone = net = lobby = joining = None


def _quit():
    cleanup()
    if bool(glutLeaveMainLoop):
        glutLeaveMainLoop()
    else:  # glutLeaveMainLoop is freeglut-only
        sys.exit(0)


def _key_down(k):
    if net is not None:
        return net.key(game, k, True)
    return game.key_down(k)


def _key_up(k):
    if net is not None:
        net.key(game, k, False)
    else:
        game.key_up(k)


def keyboard(key, x, y):
    if _key_down(key.decode('latin-1').lower()) == 'quit':
        _quit()


def keyboard_up(key, x, y):
    _key_up(key.decode('latin-1').lower())


def toggle_fullscreen():
    """F11: fullscreen and back to the window size it had."""
    if _window['full']:
        _window['full'] = False
        glutReshapeWindow(*_window['size'])
        glutPositionWindow(40, 40)
    else:
        _window['size'] = (max(320, glutGet(GLUT_WINDOW_WIDTH)), max(240, glutGet(GLUT_WINDOW_HEIGHT)))
        _window['full'] = True
        glutFullScreen()


ARROW_NAMES = {GLUT_KEY_UP: 'UP', GLUT_KEY_DOWN: 'DOWN', GLUT_KEY_LEFT: 'LEFT', GLUT_KEY_RIGHT: 'RIGHT'}
FUNCTION_KEYS = {GLUT_KEY_F2: 'F2', GLUT_KEY_F3: 'F3'}


def _arrow_is_a_key(name):
    """Arrows go to the game as keys in the menu, while rebinding, and when bound to an action."""
    if name is None or game.photo:
        return False
    return game.rebind is not None or game.ui in ('menu', 'lan') or controls.owner(name) is not None


def special(key, x, y):
    if key == GLUT_KEY_F11:
        toggle_fullscreen()
        return
    if key in FUNCTION_KEYS:
        if _key_down(FUNCTION_KEYS[key]) == 'quit':
            _quit()
        return
    name = ARROW_NAMES.get(key)
    if game.ui in ('playing', 'menu', 'lan') and _arrow_is_a_key(name):
        if _key_down(name) == 'quit':
            _quit()
        return
    if game.ui in ('select', 'create'):
        k = {GLUT_KEY_LEFT: 'a', GLUT_KEY_RIGHT: 'd', GLUT_KEY_UP: 'w', GLUT_KEY_DOWN: 's'}.get(key)
        if k and not (game.create and game.create['typing']):
            game.key_down(k)
            game.key_up(k)
        return
    if game.photo:
        cam = game.photo_cam
        if key in (GLUT_KEY_LEFT, GLUT_KEY_RIGHT):
            cam[0] += 4 if key == GLUT_KEY_RIGHT else -4
        elif key in (GLUT_KEY_UP, GLUT_KEY_DOWN):
            cam[1] = max(0.2, min(12.0, cam[1] + (0.2 if key == GLUT_KEY_UP else -0.2)))
        return
    if game.camera != 'orbit':
        return
    if key == GLUT_KEY_LEFT:
        game.orbit[0] -= 4
    elif key == GLUT_KEY_RIGHT:
        game.orbit[0] += 4
    elif key == GLUT_KEY_UP:
        game.orbit[1] = min(20.0, game.orbit[1] + 0.4)
    elif key == GLUT_KEY_DOWN:
        game.orbit[1] = max(0.5, game.orbit[1] - 0.4)
    elif key == GLUT_KEY_PAGE_UP:
        game.orbit[2] = max(3.0, game.orbit[2] - 1)
    elif key == GLUT_KEY_PAGE_DOWN:
        game.orbit[2] = min(40.0, game.orbit[2] + 1)


def special_up(key, x, y):
    name = ARROW_NAMES.get(key)
    if name is not None:
        _key_up(name)


def mouse(button, state, x, y):
    if button != GLUT_LEFT_BUTTON or state != GLUT_DOWN or game.ui != 'menu' or game.rebind is not None:
        return
    w = max(1, glutGet(GLUT_WINDOW_WIDTH))
    h = max(1, glutGet(GLUT_WINDOW_HEIGHT))
    hud.menu_click(game, *hud.to_canvas(x, y, w, h))


def reshape(w, h):
    glViewport(0, 0, w, max(1, h))


def focus_lost(*_args):
    """Keys held when the window loses the pointer or is hidden would stick:
    let go of them (on LAN, as key-up events both screens see)."""
    if net is not None:
        net.release(game)
    else:
        game.release_keys()
    if pads is not None:
        pads.held.clear()


def entry(state):
    if state == GLUT_LEFT:
        focus_lost()


def window_status(state):
    if state != GLUT_FULLY_RETAINED:
        focus_lost()


def enable_vsync():
    """Ask the driver to sync buffer swaps to the screen. GLUT has no call
    for it; try the platform extension and carry on quietly without it."""
    try:
        if sys.platform.startswith('win'):
            from OpenGL.WGL.EXT.swap_control import wglSwapIntervalEXT
            return bool(wglSwapIntervalEXT) and bool(wglSwapIntervalEXT(1))
        if sys.platform.startswith('linux'):
            from OpenGL.GLX.MESA.swap_control import glXSwapIntervalMESA
            if bool(glXSwapIntervalMESA):
                return glXSwapIntervalMESA(1) == 0
            from OpenGL.GLX.SGI.swap_control import glXSwapIntervalSGI
            return bool(glXSwapIntervalSGI) and glXSwapIntervalSGI(1) == 0
    except Exception:          # noqa: BLE001 - no vsync is fine
        return False
    return False


def benchmark(g, budget=1.8):
    """First launch: time a few frames at medium quality and pick the setting
    that leaves headroom for 60 fps (high costs about twice medium: the big
    screen's picture, bloom and depth of field). The first frame builds the
    display lists, which the game would do on its first frame anyway; the
    timed frames after it take under two seconds. Low if anything goes wrong."""
    try:
        if not gfx.init('medium'):
            return 'low'
        draw_world(g, live_screen=False)
        glFinish()
        start = time.perf_counter()
        times = [0.0]
        while len(times) < 6 and time.perf_counter() - start < budget:
            t0 = time.perf_counter()
            draw_world(g, live_screen=False)
            glFinish()
            times.append(time.perf_counter() - t0)
            if len(times) > 1 and times[-1] > 0.03:
                break                                      # clearly too slow: no need to see more
        if len(times) < 2:
            return 'low'
        frame = sorted(times[1:])[len(times[1:]) // 2]     # the first frame builds the display lists
        return 'high' if frame <= 0.007 else 'medium' if frame <= 0.014 else 'low'
    except Exception:          # noqa: BLE001 - a failed test run just means: play it safe
        return 'low'


def start_lan(args, g):
    """Start hosting or joining; the window shows a waiting screen (with the
    address to join) until the other player is there. Returns an error or None."""
    global lobby
    from . import net as lan
    from .phone import local_ip
    try:
        if args.join:
            lobby = lan.Lobby(address=args.join)
            g.lan_lines = [f'Joining the game at {args.join}...', '', 'ESC back to the menu']
        else:
            lobby = lan.Lobby(port=args.host or lan.PORT)
            exe = 'PenaltyShootout.exe' if getattr(sys, 'frozen', False) else 'python penalty_shootout.py'
            g.lan_lines = [f'Hosting a LAN game on port {lobby.port}.', 'Ask your friend to run:',
                           f'{exe} --join {local_ip()}:{lobby.port}', '',
                           'Waiting for them to join...', 'ESC back to the menu']
    except OSError as e:
        lobby = None
        return f'LAN game failed: {e}'
    g.ui = 'lan'
    return None


def main():
    global game, pads
    args, rest = parse_args(sys.argv[1:])
    glutInit([sys.argv[0]] + rest)
    glutInitDisplayMode(GLUT_DOUBLE | GLUT_RGBA | GLUT_DEPTH | GLUT_MULTISAMPLE)
    glutInitWindowSize(*_window['size'])
    glutInitWindowPosition(40, 40)
    try:
        # Closing the window returns from the main loop, so cleanup() runs
        glutSetOption(GLUT_ACTION_ON_WINDOW_CLOSE, GLUT_ACTION_GLUTMAINLOOP_RETURNS)
    except Exception:          # noqa: BLE001 - not freeglut: atexit still cleans up on sys.exit
        pass
    atexit.register(cleanup)
    glutCreateWindow(b'Penalty Shootout')
    enable_vsync()
    render.init_gl()
    controls.load()
    added = scenarios.load_mods(teams=C.TEAMS)
    game = Game(audio=Audio())
    saved = gfx.saved_quality()
    if saved is None:
        saved = benchmark(game)
        gfx.save_quality(saved)
        game.toast = (f"Graphics set to {gfx.QUALITY_LABELS[saved]} for this computer (change it in the menu)", 0.0)
    if not gfx.init(saved):
        print(f"Graphics: shaders unavailable, using low quality ({gfx.state['error']})")
    game.graphics = gfx.quality()
    if added:
        game.toast = (f'Loaded {added} mod item(s) from {scenarios.MOD_DIR}', 0.0)
    if not game.stats['tutorial_done'] and not (args.replay or args.duel or args.host is not None or args.join):
        game.mode = 'tutorial'                 # first run: start with the coach
    pads = Gamepads()
    if pads.connected:
        game.toast = (f'{pads.connected} gamepad(s) connected', 0.0)
    if args.replay:
        try:
            with open(args.replay) as f:
                game.load_replay(json.load(f))
        except (OSError, ValueError, KeyError) as e:
            game.toast = (f'Could not load replay: {e}', 0.0)
    if args.duel:
        data = Game.read_duel(args.duel)
        try:
            ok = bool(data) and game.load_duel(data)
        except Exception:      # noqa: BLE001 - a bad file must not stop the game starting
            ok = False
            game.to_menu()
        if not ok:
            game.toast = (f'Could not read the duel file {args.duel}', 0.0)
    if args.host is not None or args.join:
        err = start_lan(args, game)
        if err:
            game.toast = (err, 0.0)
    glutDisplayFunc(display)
    glutReshapeFunc(reshape)
    glutKeyboardFunc(keyboard)
    glutKeyboardUpFunc(keyboard_up)
    glutIgnoreKeyRepeat(1)
    glutSpecialFunc(special)
    glutSpecialUpFunc(special_up)
    glutMouseFunc(mouse)
    glutEntryFunc(entry)
    try:
        glutWindowStatusFunc(window_status)    # freeglut: hidden or minimised
    except Exception:          # noqa: BLE001
        pass
    glutTimerFunc(0, tick, 0)
    glutMainLoop()
    cleanup()
