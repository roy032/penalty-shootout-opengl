"""GLUT window, cameras, clip export and the optional gamepad and phone inputs."""

import argparse
import json
import math
import os
import sys
import time

from OpenGL.GL import *  # noqa: F401,F403
from OpenGL.GLU import *  # noqa: F401,F403
from OpenGL.GLUT import *  # noqa: F401,F403

from . import config as C, controls, hud, render
from .audio import Audio
from .game import WALK_TIME, Game
from .gamepad import Gamepads

CLIP_DIR = os.path.join(os.path.expanduser('~'), 'penalty_shootout_clips')
CLIP_WIDTH = 480
CLIP_EVERY = 3            # keep every third frame of the slow-motion replay

game = None
pads = None
phone = None
_last_ms = None
_clip = None              # frames being captured for a GIF


def camera_eye(g, view):
    """Eye and look-at point for the current camera."""
    bx, by, bz = view['ball']
    if g.phase == 'replay':
        cam = g.replay_cam
        if cam == 'ball':
            # Riding just behind the ball all the way to the net
            return (bx + 1.4, by + 0.6, bz + 2.4), (bx * 0.5, 1.0, C.GOAL_LINE_Z)
        if cam == 'side':
            return (9.0, 1.6, C.GOAL_LINE_Z + 2.5), (0.0, 1.0, C.GOAL_LINE_Z + 0.5)
        # Reverse angle from behind the net, the classic replay shot
        return (4.5, 2.3, C.GOAL_LINE_Z - 6.5), (0.0, 1.0, C.GOAL_LINE_Z + 4.0)
    if g.phase == 'walk' and g.camera == 'broadcast':
        # Tracking shot behind the kicker on the long walk
        sx, sz = view['shooter']['pos']
        r = min(1.0, g.phase_t / WALK_TIME)
        return (sx - 1.0, 2.2 - 0.3 * r, sz + 4.5), (sx * 0.3, 1.2, C.GOAL_LINE_Z)
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


def setup_camera(g, view):
    w = max(1, glutGet(GLUT_WINDOW_WIDTH))
    h = max(1, glutGet(GLUT_WINDOW_HEIGHT))
    glViewport(0, 0, w, h)
    glMatrixMode(GL_PROJECTION)
    glLoadIdentity()
    fov = 70.0 if g.scene_env()['first_person'] else 50.0
    gluPerspective(fov, w / float(h), 0.05, 250.0)
    glMatrixMode(GL_MODELVIEW)
    glLoadIdentity()
    eye, look = camera_eye(g, view)
    if g.shake > 0:
        amp = 0.12 * g.shake
        eye = (eye[0] + amp * math.sin(g.clock * 53.0), eye[1] + amp * math.cos(g.clock * 47.0), eye[2])
    gluLookAt(eye[0], eye[1], eye[2], look[0], look[1], look[2], 0, 1, 0)


def display():
    g = game
    view = g.current_view()
    env = g.scene_env()
    render.set_environment(env['daytime'], env['weather'])
    glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
    setup_camera(g, view)
    aim = tuple(g.aim) if g.aim_visible() else None
    render.draw_scene(view, aim, g.clock, env)
    hud.draw(g)
    _capture_frame(g)
    glutSwapBuffers()


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
        w = max(1, glutGet(GLUT_WINDOW_WIDTH))
        h = max(1, glutGet(GLUT_WINDOW_HEIGHT))
        glPixelStorei(GL_PACK_ALIGNMENT, 1)
        data = glReadPixels(0, 0, w, h, GL_RGB, GL_UNSIGNED_BYTE)
        _clip['frames'].append((w, h, bytes(data)))
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
    game.update(dt)
    glutPostRedisplay()
    glutTimerFunc(C.FRAME_MS, tick, 0)


def _quit():
    if phone is not None:
        phone.stop()
    if bool(glutLeaveMainLoop):
        glutLeaveMainLoop()
    else:  # glutLeaveMainLoop is freeglut-only
        sys.exit(0)


def keyboard(key, x, y):
    if game.key_down(key.decode('latin-1').lower()) == 'quit':
        _quit()


def keyboard_up(key, x, y):
    game.key_up(key.decode('latin-1').lower())


def special(key, x, y):
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
    return parser.parse_known_args(argv)


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
    game = Game(audio=Audio())
    pads = Gamepads()
    if pads.connected:
        game.toast = (f'{pads.connected} gamepad(s) connected', 0.0)
    if args.replay:
        try:
            with open(args.replay) as f:
                game.load_replay(json.load(f))
        except (OSError, ValueError, KeyError) as e:
            game.toast = (f'Could not load replay: {e}', 0.0)
    glutDisplayFunc(display)
    glutReshapeFunc(reshape)
    glutKeyboardFunc(keyboard)
    glutKeyboardUpFunc(keyboard_up)
    glutIgnoreKeyRepeat(1)
    glutSpecialFunc(special)
    glutMouseFunc(mouse)
    glutTimerFunc(C.FRAME_MS, tick, 0)
    glutMainLoop()
