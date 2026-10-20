"""Render one screen of the game to a PNG, for checking the HUD at different
window sizes (works headless: xvfb-run -a python tools/screenshot.py ...).

    python tools/screenshot.py menu 800x600 out.png
    python tools/screenshot.py aim 1920x1080 out.png --quality medium

Screens: menu, aim (Player 1 aiming in a PvC shootout), keep (keeping goal
in the 90th-minute penalty), walk, pause. Settings and stats are kept in a
throwaway home folder, so nothing of yours is touched.
"""

import argparse
import os
import sys
import tempfile

os.environ['HOME'] = os.environ['USERPROFILE'] = tempfile.mkdtemp(prefix='shootout-shot-')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from OpenGL.GL import *  # noqa: E402,F401,F403
from OpenGL.GLUT import *  # noqa: E402,F401,F403

from shootout import app, controls, gfx, hud, render  # noqa: E402
from shootout.game import Game  # noqa: E402


def setup(g, screen):
    if screen == 'menu':
        return
    if screen == 'keep':
        g.mode, g.role = 'match', 'keep'
    g.start_match()
    want = {'aim': 'aim', 'keep': 'aim', 'walk': 'walk', 'pause': 'aim'}[screen]
    for _ in range(60 * 60):
        g.update(1 / 60)
        if g.phase == want and (screen in ('keep', 'walk') or g.kicker == 'p1'):
            break
        if g.phase == 'aim' and g.kicker != 'p1' and screen != 'keep':
            for _ in range(60 * 4):
                g.update(1 / 60)
    for _ in range(int(60 * (1.2 if screen == 'walk' else 0.8))):
        g.update(1 / 60)
    if screen in ('aim', 'pause'):
        g.aim = [-2.2, 1.6]
    if screen == 'pause':
        g.key_down('\x1b')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('screen', choices=['menu', 'aim', 'keep', 'walk', 'pause'])
    ap.add_argument('size')
    ap.add_argument('out')
    ap.add_argument('--quality', default='medium', choices=gfx.QUALITIES)
    args = ap.parse_args()
    w, h = (int(v) for v in args.size.lower().split('x'))
    glutInit([sys.argv[0]])
    glutInitDisplayMode(GLUT_DOUBLE | GLUT_RGBA | GLUT_DEPTH)
    glutInitWindowSize(w, h)
    glutCreateWindow(b'Penalty Shootout screenshot')
    render.init_gl()
    controls.reset()
    g = Game(audio=None)
    gfx.init(args.quality)
    g.graphics = gfx.quality()
    app.game = g
    setup(g, args.screen)
    state = dict(n=0)

    def display():
        glViewport(0, 0, w, h)
        app.draw_world(g)
        hud.draw(g)
        state['n'] += 1
        if state['n'] == 3:
            glPixelStorei(GL_PACK_ALIGNMENT, 1)
            glReadBuffer(GL_BACK)
            data = bytes(glReadPixels(0, 0, w, h, GL_RGB, GL_UNSIGNED_BYTE))
            from PIL import Image
            Image.frombytes('RGB', (w, h), data).transpose(Image.FLIP_TOP_BOTTOM).save(args.out)
            print(f'{args.out}: {args.screen} at {w}x{h}, graphics {gfx.quality()}')
            glutLeaveMainLoop()
            return
        glutSwapBuffers()

    def tick(_v=0):
        glutPostRedisplay()
        glutTimerFunc(16, tick, 0)

    glutSetOption(GLUT_ACTION_ON_WINDOW_CLOSE, GLUT_ACTION_GLUTMAINLOOP_RETURNS)
    glutDisplayFunc(display)
    glutTimerFunc(16, tick, 0)
    glutMainLoop()


if __name__ == '__main__':
    main()
