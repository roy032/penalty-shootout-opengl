"""Computer kicker and keeper for PvC."""

from . import config as C


class ShotMemory:
    """What each side has done so far, so the AI can play the percentages."""

    def __init__(self):
        self.shots = {'p1': [], 'p2': []}   # target x of each kick
        self.dives = {'p1': [], 'p2': []}   # dive direction of each kick faced

    def add_shot(self, side, x):
        self.shots[side].append(x)

    def add_dive(self, side, direction):
        self.dives[side].append(direction)

    @staticmethod
    def _lean(values, recent=6):
        """-1..1: how strongly the recent values favour +x (right)."""
        vals = [v for v in values[-recent:] if v]
        if not vals:
            return 0.0
        right = sum(1 for v in vals if v > 0)
        return (2.0 * right - len(vals)) / len(vals)


def keeper_decision(rng, params, shot_target, kicker_history, cue=1.0, shuffle=0.0, pointed=0, notes=0):
    """Choose a dive for the computer keeper at the moment of contact.

    cue: how clearly the kicker's run-up gave the side away (hips, plant
    foot, body angle). 1 is an open, readable run-up; a disguised run-up is
    much lower. With probability read * cue the keeper reads it and goes the
    right way. Otherwise it guesses: towards the bigger side if it shuffled
    off-centre to bait the kicker, else towards this kicker's favourite side.
    notes: the taker's usual side (-1 or 1) when the keeper has notes on him.
    params['memory'] scales how much the kicker's history counts.
    Returns (direction, high, delay).
    """
    tx, ty = shot_target
    high = ty > 0.95
    delay = params['reaction'] + rng.uniform(0.0, 0.05)
    if rng.random() < params['stay']:
        return 0, ty > 1.3, delay
    if rng.random() < params['read'] * cue:
        direction = 0 if abs(tx) < 0.7 else (1 if tx > 0 else -1)
        return direction, high, delay
    if shuffle and rng.random() < 0.7:
        return (1 if shuffle < 0 else -1), rng.random() < 0.35, delay
    if pointed and rng.random() < 0.6:
        # Pointed one way to scare the kicker off it, then goes the other
        return -pointed, rng.random() < 0.35, delay
    if notes and rng.random() < 0.6:
        return notes, rng.random() < 0.35, delay
    lean = ShotMemory._lean(kicker_history)
    p_right = 0.5 + max(-0.45, min(0.45, 0.3 * lean * params.get('memory', 1.0)))
    direction = 1 if rng.random() < p_right else -1
    return direction, rng.random() < 0.35, delay


def keeper_prekick(rng, params, persona=None):
    """Gamesmanship before the kick: shuffle off-centre, sell a fake, wave arms.
    A Showman always points and loves taking the ball; a Dancer waves more.
    Returns dict(shuffle=offset, fake=bool, taunts=int)."""
    shuffle = 0.0
    if rng.random() < params['bait']:
        shuffle = rng.choice((-0.35, 0.35))
    point = 0
    if rng.random() < (0.8 if persona == 'showman' else params['bait'] * 0.5):
        point = rng.choice((-1, 1))
    taunt = rng.random() < params['bait'] + (0.3 if persona == 'dancer' else 0.0)
    return dict(shuffle=shuffle, fake=rng.random() < params['bait'] * 0.6,
                taunts=1 if taunt else 0, point=point,
                take_ball=rng.random() < (0.5 if persona == 'showman' else params['bait'] * 0.4))


def kicker_adjust(rng, plan, keeper_x0, fake_dir, wind, exploit, point_dir=0, rattled=1.0):
    """Last look before the run-up: the bigger side tempts, a fake can fool,
    a pointing keeper plants doubt, and a good kicker allows for the wind.
    rattled: how much the keeper's antics get to this kicker."""
    kind, (x, y) = plan['kind'], plan['aim']
    if kind != 'chip':
        side = 1 if x > 0 else -1
        if keeper_x0 and rng.random() < 0.55:
            side = 1 if keeper_x0 < 0 else -1          # the gap the keeper left
        if fake_dir and rng.random() < 0.4:
            side = -fake_dir                             # sold the dummy
        if point_dir and rng.random() < 0.45 * rattled:
            side = -point_dir                            # stays away from the pointed corner
        x = side * abs(x)
    flight = 11.0 / max(8.0, C.SHOT_TYPES[kind]['speed'][0])
    x -= 0.5 * wind * flight * flight * (0.4 + 0.5 * exploit)
    return dict(plan, aim=(x, y))


# Kicker personalities: chance of each shot type, how often low, and the
# share of kicks to the natural side (a right-footer's natural side is the
# keeper's right, which is -x from behind the kicker).
PROFILES = [
    dict(name='The Placer', types={'placed': 0.7, 'curl': 0.12, 'skidder': 0.1, 'stutter': 0.05, 'chip': 0.03},
         low=0.65, natural=0.6, disguise=0.5),
    dict(name='The Blaster', types={'driven': 0.6, 'knuckle': 0.2, 'placed': 0.15, 'chip': 0.05},
         low=0.35, natural=0.55, disguise=0.1),
    dict(name='The Artist', types={'curl': 0.35, 'placed': 0.2, 'chip': 0.2, 'stutter': 0.15, 'knuckle': 0.1},
         low=0.45, natural=0.5, disguise=0.7),
]


# Personalities of squad players and characters (see characters.py). Steady
# takers keep the match's random profile.
PERSONA_PROFILES = {
    'ice': dict(name='Ice Cold', types={'placed': 0.75, 'curl': 0.1, 'skidder': 0.1, 'driven': 0.05},
                low=0.65, natural=0.6, disguise=0.5),
    'showboat': dict(name='Showboat', types={'chip': 0.2, 'stutter': 0.2, 'curl': 0.25, 'placed': 0.25,
                                             'knuckle': 0.1}, low=0.45, natural=0.5, disguise=0.4),
    'hothead': PROFILES[1],
    'thinker': dict(name='Thinker', types={'placed': 0.5, 'curl': 0.2, 'skidder': 0.15, 'stutter': 0.15},
                    low=0.55, natural=0.5, disguise=0.85),
    'kid': dict(name='Nervous Kid', types={'placed': 0.6, 'driven': 0.25, 'curl': 0.15}, low=0.5, natural=0.6,
                disguise=0.2),
    'clutch': dict(name='Big Game', types={'placed': 0.45, 'driven': 0.35, 'curl': 0.2}, low=0.5, natural=0.55,
                   disguise=0.4),
}


def persona_profile(profile, player):
    """The kicking profile for this taker: his personality, then his
    signature move weighted in."""
    if player is None:
        return profile
    prof = PERSONA_PROFILES.get(player.persona, profile)
    sig = player.signature
    if sig:
        from .characters import SIG_SHOT
        types = dict(prof['types'])
        if sig in SIG_SHOT:
            types[SIG_SHOT[sig]] = types.get(SIG_SHOT[sig], 0.0) + 0.6
            if sig == 'rocket':
                types['knuckle'] = types.get('knuckle', 0.0) + 0.1
        prof = dict(prof, types=types)
        if sig == 'disguise':
            prof['disguise'] = 1.0
        if sig == 'low':
            prof['low'] = 0.9
        if sig == 'rocket':
            prof['low'] = 0.25
    return prof


def _pick(rng, weights):
    r = rng.random() * sum(weights.values())
    for k, w in weights.items():
        r -= w
        if r <= 0:
            return k
    return k


def kicker_plan(rng, params, profile, keeper_dives, player=None, shot_types=None):
    """Choose shot type, aim point and where to stop the power bar. A squad
    player's own habits (natural side, low or high) override the profile's."""
    if player is not None:
        natural = player.natural if player.foot == 'R' else 1.0 - player.natural   # left-footers mirror
        low = player.low
        if player.signature == 'low':
            low = max(low, 0.85)
        elif player.signature == 'rocket':
            low = min(low, 0.3)
        profile = dict(profile, natural=natural, low=low)
    if shot_types is not None:
        profile = dict(profile, types={k: w for k, w in profile['types'].items() if k in shot_types} or
                       {'placed': 1.0})
    kind = _pick(rng, profile['types'])
    power_mean, power_spread = params['power']
    power = min(1.0, max(0.25, rng.gauss(power_mean, power_spread)))
    # Aim points are for a full-size goal; scale them to the pitch variant
    sx, sy = C.GOAL_HALF_WIDTH / 3.66, C.GOAL_HEIGHT / 2.44
    if kind == 'chip':
        return kind, (rng.uniform(-0.4, 0.4) * sx, rng.uniform(1.2, 1.7) * sy), min(power, 0.7)
    if kind == 'stutter':
        power = min(power, 0.75)
    # Natural side, then shade away from the keeper's favourite dive
    p_left = profile['natural']
    p_left = p_left + params['exploit'] * 0.35 * ShotMemory._lean(keeper_dives)
    side = -1 if rng.random() < min(0.9, max(0.1, p_left)) else 1
    x = side * rng.uniform(2.3, 3.25) * sx
    if rng.random() < profile['low']:
        y = rng.uniform(0.2, 0.6)
    else:
        y = rng.uniform(1.5, 2.15) * sy
    return kind, (x, y), power

