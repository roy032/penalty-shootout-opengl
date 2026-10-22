"""Hall of fame: what every character has done across all your matches.

update() folds one finished Match into a records dict (plain JSON), keyed by
the character's key, so club players and the generated sides are left out."""

from .roster import TEAMS


def _characters():
    keys = set()
    for t in TEAMS.values():
        keys.update(t['players'])
        keys.update(t['keepers'])
    return keys


def update(records, match):
    """Add a finished match to records (modified in place and returned)."""
    chars = _characters()
    players = records.setdefault('players', {})
    motm = max((p for t in match.teams for p in t.players), key=lambda p: p.rating + p.goals * 0.5 + p.saves * 0.3)
    for t in match.teams:
        won = match.winner is t
        for p in t.players:
            k = p.fb.key
            if k not in chars:
                continue
            r = players.setdefault(k, dict(name=p.fb.name, apps=0, goals=0, wins=0, motm=0, saves=0))
            r['apps'] += 1
            r['goals'] += p.goals
            r['saves'] += p.saves
            r['wins'] += 1 if won else 0
            r['motm'] += 1 if p is motm else 0
    records['matches'] = records.get('matches', 0) + 1
    return records


def table(records, key='goals', n=8):
    """The top n characters by key (ties broken by fewer appearances)."""
    rows = [r for r in records.get('players', {}).values() if r.get(key)]
    rows.sort(key=lambda r: (-r[key], r['apps'], r['name']))
    return rows[:n]
