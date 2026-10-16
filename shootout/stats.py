"""Lifetime stats for Player 1, kept in a small JSON file in the home folder."""

import json
import os

PATH = os.path.join(os.path.expanduser('~'), '.penalty_shootout_stats.json')
FIELDS = ('matches', 'wins', 'kicks', 'goals', 'faced', 'saves')


def load(path=PATH):
    data = dict.fromkeys(FIELDS, 0)
    try:
        with open(path) as f:
            saved = json.load(f)
        for k in FIELDS:
            if isinstance(saved.get(k), int):
                data[k] = saved[k]
    except (OSError, ValueError):
        pass
    return data


def save(data, path=PATH):
    try:
        with open(path, 'w') as f:
            json.dump(data, f)
    except OSError:
        pass


def summary(data):
    if not data['kicks'] and not data['faced']:
        return 'No career stats yet: take your first shootout!'
    pct = 100.0 * data['goals'] / data['kicks'] if data['kicks'] else 0.0
    return (f"Career  P1: {data['wins']}/{data['matches']} shootouts won  |  "
            f"{data['goals']}/{data['kicks']} pens scored ({pct:.0f}%)  |  "
            f"{data['saves']} saves from {data['faced']}")
