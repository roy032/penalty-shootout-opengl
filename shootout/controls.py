"""Key bindings for both players, saved to a small JSON file so they can be
rebound from the menu."""

import json
import os

PATH = os.path.join(os.path.expanduser('~'), '.penalty_shootout_keys.json')

ACTIONS = ['left', 'right', 'up', 'down', 'shoot', 'special', 'extra1', 'extra2']
ACTION_LABELS = {
    'left': 'Aim / dive left', 'right': 'Aim / dive right', 'up': 'Aim up / high-low',
    'down': 'Aim down / stay', 'shoot': 'Shoot / set power', 'special': 'Shot type / wave arms',
    'extra1': 'Disguise run-up / shuffle', 'extra2': 'Celebrate / fake lean',
}
DEFAULTS = {
    'p1': dict(left='a', right='d', up='w', down='s', shoot=' ', special='e', extra1='q', extra2='x'),
    'p2': dict(left='j', right='l', up='i', down='k', shoot='\r', special='o', extra1='u', extra2='m'),
}
# Keys the game itself uses: Esc quit, pause, help, camera, sound, restart,
# replay, clip export, keep replay, trajectory preview
RESERVED = {'\x1b', 'p', 'h', 'c', 'n', 'r', 'v', 'g', 'f', 't'}

CONTROLS = {slot: dict(keys) for slot, keys in DEFAULTS.items()}


def load(path=PATH):
    try:
        with open(path) as f:
            saved = json.load(f)
    except (OSError, ValueError):
        return
    for slot in CONTROLS:
        for action in ACTIONS:
            k = saved.get(slot, {}).get(action)
            if isinstance(k, str) and len(k) == 1 and k not in RESERVED:
                CONTROLS[slot][action] = k


def save(path=PATH):
    try:
        with open(path, 'w') as f:
            json.dump(CONTROLS, f)
    except OSError:
        pass


def reset():
    for slot, keys in DEFAULTS.items():
        CONTROLS[slot] = dict(keys)


def bind(slot, action, key):
    """Bind key to slot's action. Returns False if the key is reserved or
    already used by another action."""
    if key in RESERVED:
        return False
    for s, keys in CONTROLS.items():
        for a, k in keys.items():
            if k == key and (s, a) != (slot, action):
                return False
    CONTROLS[slot][action] = key
    return True


def key_name(k):
    return {' ': 'SPACE', '\r': 'ENTER'}.get(k, k.upper())
