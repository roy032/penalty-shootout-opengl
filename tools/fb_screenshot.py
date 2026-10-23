"""Render Ultimate Football scenes to PNGs, for checking the graphics
(works headless: xvfb-run -a python tools/fb_screenshot.py out_dir).

    python tools/fb_screenshot.py shots/ --scenes full-day,cage-night --quality high

Each scene starts a CPU match with a fixed seed, plays a few seconds and saves
one frame. Settings are kept in a throwaway home folder, so nothing of yours
is touched.
"""

import argparse
import os
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
}


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
        s.update(night=night, camera=cam, weather=weather, mode='cpu', home='stars', away='legends')
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
