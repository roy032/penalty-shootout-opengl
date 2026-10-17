"""Lifetime stats for Player 1, kept in a small JSON file in the home folder."""

import json
import os

PATH = os.path.join(os.path.expanduser('~'), '.penalty_shootout_stats.json')
FIELDS = ('matches', 'wins', 'kicks', 'goals', 'faced', 'saves')
# Goal mouth split into 3 columns x 2 rows for the training heatmap
ZONES = ['left high', 'centre high', 'right high', 'left low', 'centre low', 'right low']


def zone_of(x, y):
    col = 'left' if x < -1.2 else ('right' if x > 1.2 else 'centre')
    return f"{col} {'high' if y > 1.2 else 'low'}"


def load(path=PATH):
    data = dict.fromkeys(FIELDS, 0)
    data['zones'] = {z: [0, 0] for z in ZONES}    # attempts, goals
    try:
        with open(path) as f:
            saved = json.load(f)
        for k in FIELDS:
            if isinstance(saved.get(k), int):
                data[k] = saved[k]
        for z, v in (saved.get('zones') or {}).items():
            if z in data['zones'] and isinstance(v, list) and len(v) == 2:
                data['zones'][z] = [int(v[0]), int(v[1])]
    except (OSError, ValueError, TypeError):
        pass
    return data


def add_zone(data, aim, scored):
    z = data['zones'][zone_of(*aim)]
    z[0] += 1
    z[1] += int(scored)


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
