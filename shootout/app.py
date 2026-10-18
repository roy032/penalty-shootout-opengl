"""GLUT window, cameras, clip export and the optional gamepad and phone inputs."""

import argparse
import json
import math
import os
import subprocess
import sys
import time

from OpenGL.GL import *  # noqa: F401,F403
from OpenGL.GLU import *  # noqa: F401,F403
from OpenGL.GLUT import *  # noqa: F401,F403

from . import config as C, controls, gfx, hud, render, scenarios
from .audio import Audio
from .game import WALK_TIME, Game, auto_camera
from .gamepad import Gamepads

CLIP_DIR = os.path.join(os.path.expanduser('~'), 'penalty_shootout_clips')
CLIP_WIDTH = 480
CLIP_EVERY = 3            # keep every third frame of the slow-motion replay

game = None
pads = None
phone = None
_last_ms = None
_clip = None              # frames being captured for a GIF
net = None                # LAN session, when hosting or joining


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
        r = min(1.0, g.phase_t / WALK_TIME) if g.phase == 'walk' else 1.0
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
    return auto_camera(int(g.replay['t'] * 60.0), g.replay)


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
    view = g.current_view()
    w = max(1, glutGet(GLUT_WINDOW_WIDTH))
    h = max(1, glutGet(GLUT_WINDOW_HEIGHT))
    eye, look = camera_eye(g, view)
    env = render.prepare(dict(g.scene_env(), eye=eye))
    gfx.begin_frame(w, h)
    if gfx.fancy():
        gfx.render_shadows(render.light_dir(), lambda: render.draw_casters(view, env))
        gfx.resume_frame()
        if gfx.high() and gfx.state['frame'] % 2 == 0:
            draw_big_screen_picture(g, env)
        render.set_environment(env['daytime'], env['weather'], env['dusk'])
    glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
    eye, look, fov = setup_camera(g, view)
    aim = tuple(g.aim) if g.aim_visible() else None
    render.draw_scene(view, aim, g.clock, env)
    gfx.end_frame(post_settings(g, view, env, eye, look, fov))
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
def _capture_frame(g):
    """While a requested clip is replaying, grab every few frames."""
    global _clip
    if g.export_request and g.phase == 'replay':
        if _clip is None:
            _clip = dict(frames=[], n=0)
        _clip['n'] += 1
        if _clip['n'] % CLIP_EVERY:
            return
        _clip['frames'].append(_grab())
        if len(_clip['frames']) > 400:
            g.phase = 'ended'
    if _clip is not None and g.phase != 'replay':
        frames = _clip['frames']
        _clip = None
        g.export_request = False
        g.toast = (save_clip(frames), g.clock)


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
            img = img.resize((CLIP_WIDTH, max(1, int(h * CLIP_WIDTH / w))))
            images.append(img.convert('P', palette=Image.ADAPTIVE))
        path = os.path.join(directory, f'shootout-{stamp}.gif')
        images[0].save(path, save_all=True, append_images=images[1:], duration=int(1000 * CLIP_EVERY / 60),
                       loop=0)
        return f'Clip saved: {path}'
    except OSError as e:
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


def tick(_value=0):
    global _last_ms
    now = glutGet(GLUT_ELAPSED_TIME)
    dt = 0.0 if _last_ms is None else min(0.1, (now - _last_ms) / 1000.0)
    _last_ms = now
    if pads is not None and pads.poll(game, dt) == 'quit':
        _quit()
    _phone_service(game)
    if net is not None:
        net.pump(game, dt)
    else:
        game.update(dt)
    glutPostRedisplay()
    glutTimerFunc(C.FRAME_MS, tick, 0)


def _quit():
    if phone is not None:
        phone.stop()
    if net is not None:
        net.close()
    if bool(glutLeaveMainLoop):
        glutLeaveMainLoop()
    else:  # glutLeaveMainLoop is freeglut-only
        sys.exit(0)


def keyboard(key, x, y):
    k = key.decode('latin-1').lower()
    if net is not None:
        if net.key(game, k, True) == 'quit':
            _quit()
        return
    if game.key_down(k) == 'quit':
        _quit()


def keyboard_up(key, x, y):
    k = key.decode('latin-1').lower()
    if net is not None:
        net.key(game, k, False)
        return
    game.key_up(k)


def special(key, x, y):
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


def mouse(button, state, x, y):
    if button != GLUT_LEFT_BUTTON or state != GLUT_DOWN or game.ui != 'menu':
        return
    w = max(1, glutGet(GLUT_WINDOW_WIDTH))
    h = max(1, glutGet(GLUT_WINDOW_HEIGHT))
    hud.menu_click(game, x * hud.W / w, (h - y) * hud.H / h)


def reshape(w, h):
    glViewport(0, 0, w, max(1, h))


def parse_args(argv):
    parser = argparse.ArgumentParser(description='Penalty Shootout')
    parser.add_argument('--replay', metavar='FILE', help='watch a saved shootout replay file')
    parser.add_argument('--duel', metavar='FILE', help="face a friend's ghost duel file")
    parser.add_argument('--host', nargs='?', const=0, type=int, metavar='PORT',
                        help=f'host a LAN game (default port {50505}) and wait for a friend to join')
    parser.add_argument('--join', metavar='IP[:PORT]', help='join a LAN game hosted by a friend')
    return parser.parse_known_args(argv)


def start_lan(args, g):
    """Host or join before the window opens. Returns an error message or None."""
    global net
    from . import net as lan
    try:
        if args.join:
            print(f'Joining {args.join}...')
            net = lan.NetSession(lan.connect(args.join), 'p2')
            if not net.start_join(g):
                net = None
                return 'The host did not answer'
        else:
            port = args.host or lan.PORT
            server = lan.listen(port)
            print(f'Hosting on port {port}: ask your friend to run with --join <this computer\'s IP>:{port}')
            print('Waiting for them to join (Ctrl+C to give up)...')
            net = lan.NetSession(lan.accept(server), 'p1')
            server.close()
            net.start_host(g)
    except OSError as e:
        net = None
        return f'LAN game failed: {e}'
    return None


def main():
    global game, pads
    args, rest = parse_args(sys.argv[1:])
    glutInit([sys.argv[0]] + rest)
    glutInitDisplayMode(GLUT_DOUBLE | GLUT_RGBA | GLUT_DEPTH | GLUT_MULTISAMPLE)
    glutInitWindowSize(1200, 800)
    glutInitWindowPosition(40, 40)
    glutCreateWindow(b'Penalty Shootout')
    render.init_gl()
    controls.load()
    if not gfx.init(gfx.load_quality()):
        print(f"Graphics: shaders unavailable, using low quality ({gfx.state['error']})")
    added = scenarios.load_mods(teams=C.TEAMS)
    game = Game(audio=Audio())
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
        if data:
            game.load_duel(data)
        else:
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
    glutMouseFunc(mouse)
    glutTimerFunc(C.FRAME_MS, tick, 0)
    glutMainLoop()
