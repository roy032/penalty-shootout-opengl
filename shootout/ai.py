"""Computer kicker and keeper for PvC."""


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


def keeper_decision(rng, params, shot_target, kicker_history):
    """Choose a dive for the computer keeper at the moment of contact.

    With probability `read` it reads the kicker's body shape and goes the
    right way (as real keepers do from hips and plant foot). Otherwise it
    guesses, leaning towards the side this kicker has favoured.
    Returns (direction, high, delay).
    """
    tx, ty = shot_target
    high = ty > 0.95
    delay = params['reaction'] + rng.uniform(0.0, 0.05)
    if rng.random() < params['stay']:
        return 0, ty > 1.3, delay
    if rng.random() < params['read']:
        direction = 0 if abs(tx) < 0.7 else (1 if tx > 0 else -1)
        return direction, high, delay
    lean = ShotMemory._lean(kicker_history)
    p_right = 0.5 + 0.3 * lean
    direction = 1 if rng.random() < p_right else -1
    return direction, rng.random() < 0.35, delay


# Kicker personalities: chance of each shot type, how often low, and the
# share of kicks to the natural side (a right-footer's natural side is the
# keeper's right, which is -x from behind the kicker).
PROFILES = [
    dict(name='The Placer', types={'placed': 0.8, 'curl': 0.15, 'chip': 0.05}, low=0.65, natural=0.6),
    dict(name='The Blaster', types={'driven': 0.75, 'placed': 0.2, 'chip': 0.05}, low=0.35, natural=0.55),
    dict(name='The Artist', types={'curl': 0.45, 'placed': 0.3, 'chip': 0.25}, low=0.45, natural=0.5),
]


def _pick(rng, weights):
    r = rng.random() * sum(weights.values())
    for k, w in weights.items():
        r -= w
        if r <= 0:
            return k
    return k


def kicker_plan(rng, params, profile, keeper_dives):
    """Choose shot type, aim point and where to stop the power bar."""
    kind = _pick(rng, profile['types'])
    power_mean, power_spread = params['power']
    power = min(1.0, max(0.25, rng.gauss(power_mean, power_spread)))
    if kind == 'chip':
        return kind, (rng.uniform(-0.4, 0.4), rng.uniform(1.2, 1.7)), min(power, 0.7)
    # Natural side, then shade away from the keeper's favourite dive
    p_left = profile['natural']
    p_left = p_left + params['exploit'] * 0.35 * ShotMemory._lean(keeper_dives)
    side = -1 if rng.random() < min(0.9, max(0.1, p_left)) else 1
    x = side * rng.uniform(2.3, 3.25)
    if rng.random() < profile['low']:
        y = rng.uniform(0.2, 0.6)
    else:
        y = rng.uniform(1.5, 2.15)
    return kind, (x, y), power

