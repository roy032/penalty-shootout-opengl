"""Render Ultimate Football scenes to PNGs, for checking the graphics
(works headless: xvfb-run -a python tools/fb_screenshot.py out_dir).

    python tools/fb_screenshot.py shots/ --scenes full-day,cage-night --quality high

Each scene starts a CPU match with a fixed seed, plays a few seconds and saves
one frame. Settings are kept in a throwaway home folder, so nothing of yours
is touched.
"""

import argparse
import os
import math
import random
import sys
import tempfile

os.environ['HOME'] = os.environ['USERPROFILE'] = tempfile.mkdtemp(prefix='football-shot-')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from football import app as A  # noqa: E402

# name: (format, night, camera, seconds played, weather)
SCENES = {
    'full-day': ('full', False, 'broadcast', 6.0, 'clear'),
    'full-night': ('full', True, 'broadcast', 9.0, 'clear'),
    'cage-night': ('cage', True, 'broadcast', 5.0, 'clear'),
    'fives-day': ('fives', False, 'broadcast', 7.0, 'clear'),
    'sevens-night': ('sevens', True, 'wide', 8.0, 'clear'),
    'player-cam': ('fives', True, 'player', 4.0, 'clear'),
    'end-cam': ('full', False, 'end', 5.0, 'clear'),
    'rain-night': ('sevens', True, 'broadcast', 6.0, 'rain'),
    'menu': (None, True, 'broadcast', 3.0, 'clear'),
    # Close-ups of the players, to judge the models and animation
    'close-run': ('fives', False, 'close', 4.0, 'clear'),
    'close-night': ('full', True, 'close', 7.0, 'clear'),
    'close-keeper': ('sevens', False, 'keeper', 5.0, 'clear'),
    'lineup': ('fives', False, 'lineup', 0.5, 'clear'),
}


def _close_camera(app, mode):
    """Put the camera a few metres from a player (the one nearest the ball, a keeper,
    or the line-up at kick-off) and look at him."""
    m = app.session.match
    players = [p for t in m.teams for p in t.players if not p.sent_off]
    bx, by = m.ball.pos[0], m.ball.pos[1]
    if mode == 'keeper':
        p = min((q for q in players if q.keeper), key=lambda q: abs(q.pos[0] - bx))
        a = 1 if p.pos[0] < 0 else -1
        pos = (p.pos[0] + a * 4.2, p.pos[1] - 2.4, 1.5)
        look = (p.pos[0], p.pos[1], 1.0)
    elif mode == 'lineup':
        # The kick-off group, from whichever side has no one standing in front of the lens
        t = m.teams[0]
        p = min(t.players, key=lambda q: math.hypot(q.pos[0] - bx, q.pos[1] - by))
        group = sorted(t.players, key=lambda q: math.hypot(q.pos[0] - p.pos[0], q.pos[1] - p.pos[1]))[:3]
        cx = sum(q.pos[0] for q in group) / 3
        cy = sum(q.pos[1] for q in group) / 3

        def clearance(a):
            ex, ey = cx + 9.0 * math.cos(a), cy + 9.0 * math.sin(a)
            return min(math.hypot(q.pos[0] - ex, q.pos[1] - ey) for q in players)
        a = max((math.radians(d) for d in range(-150, -20, 10)), key=clearance)
        pos = (cx + 9.0 * math.cos(a), cy + 9.0 * math.sin(a), 2.0)
        look = (cx, cy, 1.0)
    else:
        p = min(players, key=lambda q: math.hypot(q.pos[0] - bx, q.pos[1] - by))
        pos = (p.pos[0] - 2.8, p.pos[1] - 3.6, 1.6)
        look = (p.pos[0], p.pos[1], 1.0)
    c = app.camera
    c.set_pos(*pos)
    c.look_at(*look)
    app.camLens.set_fov(42)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('out')
    ap.add_argument('--scenes', default=','.join(SCENES))
    ap.add_argument('--quality', default='high')
    ap.add_argument('--size', default='1280x720')
    ap.add_argument('--fast', action='store_true', help='play one second instead of the full warm-up')
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    w, h = (int(v) for v in args.size.split('x'))
    s = A.load_settings()
    s['quality'] = args.quality
    A.configure(s, size=(w, h))
    from football.game import FootballApp
    from football.view.inputs import Input
    app = FootballApp(s)
    app.inputs.read = lambda slot, axes=None: Input()
    app.inputs.menu_keys = lambda: []
    for name in args.scenes.split(','):
        fmt, night, cam, secs, weather = SCENES[name]
        random.seed(name)
        close = cam in ('close', 'keeper', 'lineup')
        s.update(night=night, camera='broadcast' if close else cam, weather=weather, mode='cpu', home='stars', away='legends')
        if fmt is None:
            app.attract()
        else:
            s['format'] = fmt
            app.start_match()
        sess = app.session
        steps = 30 if args.fast else int(secs * 30)
        for _ in range(steps):
            app.clock.set_mode(app.clock.M_forced)
            app.clock.set_frame_rate(30)
            app.task_mgr.step()
        if close:
            _close_camera(app, cam)
        app.graphics_engine.render_frame()
        app.graphics_engine.render_frame()
        path = os.path.join(args.out, name + '.png')
        app.win.save_screenshot(path)
        print('saved', path, sess.match.state if sess else '')
        if fmt is not None:
            app.clear_menus()
            app.main_menu()
    app.destroy()


if __name__ == '__main__':
    main()
