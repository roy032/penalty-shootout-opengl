"""Challenges: things to do in matches that unlock extras.

check() looks at a finished Match from the point of view of the human side and
returns the ids of challenges it completes. Progress (a set of ids) is saved by
the app; rewards() turns it into what is unlocked."""

CHALLENGES = [
    ('first_win', 'First win', 'Win any match against the computer'),
    ('giant_killer', 'Giant killer', 'Beat the Legends with a club side'),
    ('fortress', 'Fortress', 'Keep a clean sheet in the cage on World Class or Legendary'),
    ('hat_trick', 'Hat-trick hero', 'Score three goals with one player in a match'),
    ('comeback', 'Comeback kings', 'Win after being two goals down'),
    ('ice_cold', 'Ice cold', 'Win a penalty shootout'),
    ('snow_day', 'Snow day', 'Win a match in the snow'),
    ('champions', 'Champions', 'Win a Cup Run'),
]
IDS = [c[0] for c in CHALLENGES]

# How many challenges unlock each reward
REWARDS = [
    (3, 'golden_ball', 'Golden ball', 'A gold match ball for every game'),
    (5, 'dream', 'Dream XI', 'A hidden team of the very best: Pele, Maradona, Messi, Marta, Yashin...'),
]


def human_team(match):
    """Index of the side the humans play for, or None (CPU v CPU, or one human on each side)."""
    sides = {c.team.idx for c in match.controllers}
    return sides.pop() if len(sides) == 1 else None


def check(match, cup_won=False):
    """Challenge ids completed by this finished match."""
    t = human_team(match)
    if t is None:
        return set()
    us, them = match.teams[t], match.teams[1 - t]
    won = match.winner is us
    done = set()
    goals = [e for e in match.log if e['kind'] == 'goal']
    if won:
        done.add('first_win')
        if us.info['id'] not in _character_teams() and them.info['id'] == 'legends':
            done.add('giant_killer')
        if match.weather['key'] == 'snow':
            done.add('snow_day')
        if match.shootout:
            done.add('ice_cold')
        # Two down at some point, and still won
        diff = 0
        for e in goals:
            diff += 1 if e['team'] == t else -1
            if diff <= -2:
                done.add('comeback')
                break
    if match.half >= 2 and them.score == 0 and match.settings['pitch'] == 'cage' and match.settings['difficulty'] in ('worldclass',
                                                                                                    'legendary'):
        done.add('fortress')
    scorers = {}
    for e in goals:
        if e['team'] == t and not e['own']:
            scorers[e['name']] = scorers.get(e['name'], 0) + 1
    if any(n >= 3 for n in scorers.values()):
        done.add('hat_trick')
    if cup_won:
        done.add('champions')
    return done


def rewards(progress):
    """The reward ids unlocked by a set of completed challenges."""
    n = len(set(progress) & set(IDS))
    return {key for need, key, _, _ in REWARDS if n >= need}


def _character_teams():
    from .roster import TEAMS
    return set(TEAMS)
