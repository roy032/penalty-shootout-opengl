"""GLUT window, camera and callbacks."""

import math
import sys

from OpenGL.GL import *  # noqa: F401,F403
from OpenGL.GLU import *  # noqa: F401,F403
from OpenGL.GLUT import *  # noqa: F401,F403

from . import config as C, hud, render
from .audio import Audio
from .game import Game

game = None
_last_ms = None


def camera_eye(g):
    """Eye and look-at point for the current camera."""
    if g.phase == 'replay':
        # Reverse angle from behind the net, the classic replay shot
        return (4.5, 2.3, C.GOAL_LINE_Z - 6.5), (0.0, 1.0, C.GOAL_LINE_Z + 4.0)
    cam = g.camera
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


def setup_camera(g):
    w = max(1, glutGet(GLUT_WINDOW_WIDTH))
    h = max(1, glutGet(GLUT_WINDOW_HEIGHT))
    glViewport(0, 0, w, h)
    glMatrixMode(GL_PROJECTION)
    glLoadIdentity()
    gluPerspective(50.0, w / float(h), 0.1, 250.0)
    glMatrixMode(GL_MODELVIEW)
    glLoadIdentity()
    eye, look = camera_eye(g)
    if g.shake > 0:
        amp = 0.12 * g.shake
        eye = (eye[0] + amp * math.sin(g.clock * 53.0), eye[1] + amp * math.cos(g.clock * 47.0), eye[2])
    gluLookAt(eye[0], eye[1], eye[2], look[0], look[1], look[2], 0, 1, 0)


def display():
    g = game
    glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
    setup_camera(g)
    view = g.current_view()
    aim = tuple(g.aim) if g.aim_visible() else None
    render.draw_scene(view, C.KITS, aim, g.clock)
    hud.draw(g)
    glutSwapBuffers()


def tick(_value=0):
    global _last_ms
    now = glutGet(GLUT_ELAPSED_TIME)
    dt = 0.0 if _last_ms is None else min(0.1, (now - _last_ms) / 1000.0)
    _last_ms = now
    game.update(dt)
    glutPostRedisplay()
    glutTimerFunc(C.FRAME_MS, tick, 0)


def _quit():
    if bool(glutLeaveMainLoop):
        glutLeaveMainLoop()
    else:  # glutLeaveMainLoop is freeglut-only
        sys.exit(0)


def keyboard(key, x, y):
    k = key.decode('latin-1').lower()
    if game.key_down(k) == 'quit':
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


def main():
    global game
    glutInit(sys.argv)
    glutInitDisplayMode(GLUT_DOUBLE | GLUT_RGBA | GLUT_DEPTH | GLUT_MULTISAMPLE)
    glutInitWindowSize(1200, 800)
    glutInitWindowPosition(40, 40)
    glutCreateWindow(b'Penalty Shootout')
    render.init_gl()
    game = Game(audio=Audio())
    glutDisplayFunc(display)
    glutReshapeFunc(reshape)
    glutKeyboardFunc(keyboard)
    glutKeyboardUpFunc(keyboard_up)
    glutIgnoreKeyRepeat(1)
    glutSpecialFunc(special)
    glutMouseFunc(mouse)
    glutTimerFunc(C.FRAME_MS, tick, 0)
    glutMainLoop()
