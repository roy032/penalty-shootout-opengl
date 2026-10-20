"""Key bindings for both players, saved to a small JSON file so they can be
rebound from the menu.

Keys are the lower-case character typed, or the name of an arrow key
('UP', 'DOWN', 'LEFT', 'RIGHT') for the arrows, which can be bound too.
"""

import json
import os

from . import storage

PATH = os.path.join(os.path.expanduser('~'), '.penalty_shootout_keys.json')

ACTIONS = ['left', 'right', 'up', 'down', 'shoot', 'special', 'extra1', 'extra2', 'extra3']
ACTION_LABELS = {
    'left': 'Aim / dive left', 'right': 'Aim / dive right', 'up': 'Aim up / high-low',
    'down': 'Aim down / stay', 'shoot': 'Shoot / set power', 'special': 'Shot type / wave arms',
    'extra1': 'Run-up style / shuffle', 'extra2': 'Gaze, celebrate / fake lean, take the ball',
    'extra3': 'Keeper: point to a corner',
}
DEFAULTS = {
    'p1': dict(left='a', right='d', up='w', down='s', shoot=' ', special='e', extra1='q', extra2='x', extra3='z'),
    'p2': dict(left='j', right='l', up='i', down='k', shoot='\r', special='o', extra1='u', extra2='m', extra3=','),
}
# Arrow keys arrive from GLUT as special keys; they are bound by name
ARROWS = ('UP', 'DOWN', 'LEFT', 'RIGHT')
# Keys the game itself uses: Esc pause, pause, help, camera, sound, restart,
# replay, clip export, keep replay, trajectory preview, photo mode, coach report
RESERVED = {'\x1b', 'p', 'h', 'c', 'n', 'r', 'v', 'g', 'f', 't', 'y', '\t'}
# Menu shortcuts are function keys, so they never clash with a player's keys
MENU_KEYS = {'rebind': 'F2', 'achievements': 'F3'}

CONTROLS = {slot: dict(keys) for slot, keys in DEFAULTS.items()}


def valid_key(k):
    return isinstance(k, str) and (len(k) == 1 or k in ARROWS) and k not in RESERVED


def load(path=None):
    try:
        with open(path or PATH) as f:
            saved = json.load(f)
    except (OSError, ValueError):
        return
    if not isinstance(saved, dict):
        return
    loaded = snapshot()
    for slot in loaded:
        keys = saved.get(slot)
        for action in ACTIONS:
            k = keys.get(action) if isinstance(keys, dict) else None
            if valid_key(k):
                loaded[slot][action] = k
    used = [k for keys in loaded.values() for k in keys.values()]
    if len(used) == len(set(used)):            # a file with one key on two actions is ignored
        restore(loaded)


def save(path=None):
    return storage.write_json(path or PATH, CONTROLS)


def reset():
    for slot, keys in DEFAULTS.items():
        CONTROLS[slot] = dict(keys)


def snapshot():
    return {slot: dict(keys) for slot, keys in CONTROLS.items()}


def restore(saved):
    for slot, keys in saved.items():
        CONTROLS[slot] = dict(keys)


def owner(key):
    """(slot, action) that key is bound to, or None."""
    for s, keys in CONTROLS.items():
        for a, k in keys.items():
            if k == key:
                return s, a
    return None


def bind(slot, action, key):
    """Bind key to slot's action. Returns False if the key is reserved. A key
    already used by another action swaps: that action gets this one's old key."""
    if not valid_key(key):
        return False
    taken = owner(key)
    if taken is not None and taken != (slot, action):
        s, a = taken
        CONTROLS[s][a] = CONTROLS[slot][action]
    CONTROLS[slot][action] = key
    return True


def key_name(k):
    return {' ': 'SPACE', '\r': 'ENTER', '\t': 'TAB', '\x1b': 'ESC'}.get(k, k.upper())
