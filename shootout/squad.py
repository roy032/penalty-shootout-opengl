"""Squads of eleven with ratings, the taker order, and the manager's choices.

Ratings run 0..1. Composure steadies the aim under pressure, power adds pace,
placement tightens the spread. Each outfield player also has a stronger foot
and habits (favourite side, low or high) that the opposing keeper's notes
can show.
"""

SURNAMES = [
    'Moreno', 'Kovac', 'Lindqvist', 'Okafor', 'Duarte', 'Brennan', 'Haddad', 'Novak', 'Rossi', 'Kowalski',
    'Mensah', 'Fischer', 'Silva', 'Murphy', 'Tanaka', 'Leclerc', 'Varga', 'Ibrahim', 'Costa', 'Petrov',
    'Jansen', 'Ortega', 'Dubois', 'Nkemelu', 'Walsh', 'Sato', 'Bergkamp', 'Alvarez', 'Hughes', 'Mbeki',
    'Romano', 'Eriksen', 'Popescu', 'Quinn', 'Yilmaz', 'Laurent', 'Nakamura', 'Doyle', 'Santos', 'Weber',
]
NUMBERS = [9, 10, 7, 8, 11, 4, 5, 6, 2, 3]


class Player:
    def __init__(self, number, name, composure, power, placement, foot='R', natural=0.6, low=0.5,
                 keeper=False):
        self.number = number
        self.name = name
        self.composure = composure
        self.power = power
        self.placement = placement
        self.foot = foot
        self.natural = natural       # share of kicks to his natural side
        self.low = low               # share of kicks kept low
        self.keeper = keeper
        self.sub = False             # came on just for the shootout
        self.kicks = 0               # taken in this shootout
        # Character: look, personality and flair (see characters.py)
        self.char = None             # roster key for a character, None for a club player
        self.full = name
        self.women = False
        self.look = {}
        self.persona = 'steady'
        self.signature = None
        self.celebration = None
        self.aura = 0.0
        self.glow = None
        self.reach = 0.0             # keeper bonuses on top of the difficulty table
        self.speed = 0.0
        self.tag = ''
        self.lines = []
        self.mannerism = None
        self.era = None
        self.kit_override = None
        self.form = 0                # -2..2 from recent shootouts

    CHAR_FIELDS = ('char', 'full', 'women', 'look', 'persona', 'signature', 'celebration', 'aura', 'glow', 'reach',
                   'speed', 'tag', 'lines', 'mannerism', 'era', 'kit_override', 'form')

    @property
    def his(self):
        return 'her' if self.women else 'his'

    def record_key(self, team):
        """Key for the record from the spot and form: the character, or the shirt."""
        return self.char or f'{team} #{self.number}'

    @property
    def label(self):
        return f'No. {self.number} {self.name}'

    def overall(self):
        return (self.composure + self.power + self.placement) / 3.0

    def to_dict(self):
        return dict(number=self.number, name=self.name, composure=self.composure, power=self.power,
                    placement=self.placement, foot=self.foot, natural=self.natural, low=self.low,
                    keeper=self.keeper, sub=self.sub, **{k: getattr(self, k) for k in self.CHAR_FIELDS})

    @classmethod
    def from_dict(cls, d):
        p = cls(d['number'], d['name'], d['composure'], d['power'], d['placement'], d['foot'],
                d['natural'], d['low'], d['keeper'])
        p.sub = d.get('sub', False)
        for k in cls.CHAR_FIELDS:
            if k in d:
                v = d[k]
                setattr(p, k, tuple(v) if k in ('glow', 'kit_override') and v else v)
        return p

    # How the ratings change the kick
    def sigma_scale(self):
        s = 1.25 - 0.5 * self.placement
        if self.sub and self.kicks == 0:
            from .config import COLD_SUB_SIGMA
            s *= COLD_SUB_SIGMA
        return s

    def speed_scale(self):
        from .config import FRESH_SPEED, TIRED_SPEED
        return (FRESH_SPEED if self.sub else TIRED_SPEED) * (0.95 + 0.1 * self.power)

    def pressure(self, slot_index, stakes=None):
        """Nerves from temperament and form; the fifth kick weighs on a nervous
        taker, and big-game players grow when it matters."""
        p = (0.5 - self.composure) * 0.4
        if slot_index == 4:
            p += 0.15 * (1.0 - self.composure)
        if self.persona == 'kid' and (slot_index == 4 or stakes == 'must_score'):
            p += 0.15
        if self.persona == 'clutch' and stakes in ('must_score', 'to_win'):
            p -= 0.15
        return p - 0.03 * self.form


def _rating(rng, base):
    return round(max(0.05, min(0.98, rng.gauss(base, 0.15))), 2)


def make_squad(rng, strength=0.55):
    """Ten outfielders and a keeper with random ratings."""
    names = rng.sample(SURNAMES, 11)
    squad = []
    for i, number in enumerate(NUMBERS):
        # Forwards (first in the list) are a touch better from the spot
        base = strength + (0.1 if i < 4 else -0.05 if i >= 7 else 0.0)
        squad.append(Player(number, names[i], _rating(rng, base), _rating(rng, base), _rating(rng, base),
                            'L' if rng.random() < 0.22 else 'R', round(rng.uniform(0.45, 0.75), 2),
                            round(rng.uniform(0.3, 0.75), 2)))
    squad.append(Player(1, names[10], _rating(rng, 0.4), _rating(rng, 0.45), _rating(rng, 0.3), 'R',
                        0.6, 0.5, keeper=True))
    from .characters import dress_club_player
    return [dress_club_player(p) for p in squad]


def ai_order(rng, squad):
    """A manager's list: best takers first, the coolest head fifth, with a little noise."""
    outfield = [p for p in squad if not p.keeper]
    ranked = sorted(outfield, key=lambda p: -(p.overall() + rng.gauss(0, 0.05)))
    top5 = ranked[:5]
    coolest = max(top5, key=lambda p: p.composure)
    top5.remove(coolest)
    order = top5[:4] + [coolest] + ranked[5:]
    return order + [p for p in squad if p.keeper]


def cold_subs(rng, order, count, strength=0.55):
    """Swap the weakest of the first five for fresh subs."""
    first5 = order[:5]
    weakest = sorted(first5, key=lambda p: p.overall())[:count]
    used = {p.name for p in order}
    pool = [n for n in SURNAMES if n not in used]
    for k, p in enumerate(weakest):
        sub = Player(12 + k + rng.randrange(8), rng.choice(pool), _rating(rng, strength + 0.05),
                     _rating(rng, strength + 0.1), _rating(rng, strength + 0.05),
                     'L' if rng.random() < 0.2 else 'R', round(rng.uniform(0.45, 0.75), 2),
                     round(rng.uniform(0.3, 0.75), 2))
        sub.sub = True
        from .characters import dress_club_player
        dress_club_player(sub)
        pool.remove(sub.name)
        order[order.index(p)] = sub
    return order


def natural_dir(player):
    """-1 or 1: the side (in x) this taker usually goes. A right-footer's
    natural side is his left."""
    return -1 if (player.natural >= 0.5) == (player.foot == 'R') else 1


def bottle_note(player, rng, perfect=False):
    """The keeper's water-bottle note on this taker. Notes are usually right;
    a keeper famous for his notes is never wrong."""
    his = player.his
    side = f'{his} left' if natural_dir(player) < 0 else f'{his} right'
    if rng.random() < 0.2 and not perfect:
        side = f'{his} right' if side == f'{his} left' else f'{his} left'     # bad scouting
    height = 'low' if player.low >= 0.5 else 'high'
    return f"{player.label}: goes to {side} ({round(100 * max(player.natural, 1 - player.natural))}%), usually {height}"
