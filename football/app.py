"""Ultimate Football: the Panda3D application. Menus over a live CPU match,
matches with replays and commentary, settings and controls."""

import json
import os

from panda3d.core import loadPrcFileData

HOME = os.path.join(os.path.expanduser('~'), '.ultimate_football')
SETTINGS = os.path.join(HOME, 'settings.json')

DEFAULTS = dict(quality='high', camera='broadcast', difficulty='pro', half=150, preset='arcade', format='cage',
                hints=True, volume=0.8, crowd=0.8, fullscreen=False, home='stars', away='legends', mode='1p',
                night=True, auto_switch=True, matches=0)

FORMATS = {'cage': (5, 'cage'), 'fives': (5, 'fives'), 'sevens': (7, 'sevens'), 'full': (11, 'full')}
FORMAT_LABELS = [('cage', 'Cage 5-a-side (walls)'), ('fives', '5-a-side'), ('sevens', '7-a-side'),
                 ('full', '11-a-side')]
MODES = [('1p', '1 player vs CPU'), ('2p', '2 players: head to head'), ('coop', '2 players: same team vs CPU'),
         ('cpu', 'Watch: CPU vs CPU')]


def load_settings():
    s = dict(DEFAULTS)
    try:
        with open(SETTINGS) as f:
            data = json.load(f)
        for k, v in data.items():
            if k in DEFAULTS and isinstance(v, type(DEFAULTS[k])):
                s[k] = v
    except (OSError, ValueError):
        pass
    return s


def save_settings(s):
    tmp = SETTINGS + '.tmp'
    try:
        os.makedirs(HOME, exist_ok=True)
        with open(tmp, 'w') as f:
            json.dump(s, f, indent=1)
        os.replace(tmp, SETTINGS)
    except OSError:
        pass


def configure(s, offscreen=False, size=(1280, 720)):
    lines = ['window-title Ultimate Football', 'win-size %d %d' % size, 'sync-video 1',
             'show-frame-rate-meter 0', 'textures-power-2 none', 'gl-coordinate-system default',
             'default-model-extension .bam']
    if s['quality'] != 'low':
        lines += ['framebuffer-multisample 1', 'multisamples 4']
    if s['fullscreen']:
        lines.append('fullscreen 1')
    if offscreen:
        lines += ['window-type offscreen', 'audio-library-name null']
    loadPrcFileData('', '\n'.join(lines))


def main(argv=None):
    s = load_settings()
    configure(s)
    from .game import FootballApp
    app = FootballApp(s)
    app.run()


if __name__ == '__main__':
    main()
