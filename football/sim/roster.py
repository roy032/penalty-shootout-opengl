"""Teams and footballing ratings for the shootout's 89 characters.

The shootout only rated penalty skills (composure, power, placement), so the
outfield numbers here are hand-set for the famous names and derived for the
rest. Ratings run 0..1."""

import random
import zlib

from shootout import characters as CH

# pace, shooting, passing, dribbling, defending, physical
STATS = {
    'messi': (0.85, 0.92, 0.95, 0.98, 0.35, 0.65), 'ronaldo': (0.86, 0.95, 0.80, 0.86, 0.35, 0.80),
    'haaland': (0.89, 0.95, 0.66, 0.80, 0.45, 0.93), 'mbappe': (0.98, 0.91, 0.80, 0.92, 0.36, 0.77),
    'neymar': (0.86, 0.85, 0.87, 0.95, 0.35, 0.60), 'bellingham': (0.80, 0.84, 0.85, 0.88, 0.76, 0.84),
    'palmer': (0.76, 0.88, 0.88, 0.88, 0.50, 0.68), 'vinicius': (0.95, 0.84, 0.81, 0.92, 0.30, 0.68),
    'yamal': (0.88, 0.82, 0.86, 0.92, 0.32, 0.58), 'saka': (0.86, 0.83, 0.84, 0.87, 0.55, 0.70),
    'kane': (0.70, 0.94, 0.88, 0.82, 0.48, 0.84), 'salah': (0.90, 0.88, 0.84, 0.88, 0.45, 0.75),
    'lewandowski': (0.75, 0.92, 0.80, 0.85, 0.42, 0.82), 'jorginho': (0.55, 0.70, 0.88, 0.80, 0.70, 0.62),
    'rashford': (0.92, 0.80, 0.76, 0.84, 0.40, 0.75), 'grealish': (0.78, 0.76, 0.84, 0.88, 0.45, 0.70),
    'bonmati': (0.80, 0.84, 0.93, 0.92, 0.70, 0.70), 'putellas': (0.74, 0.86, 0.91, 0.90, 0.60, 0.72),
    'kerr': (0.88, 0.90, 0.75, 0.84, 0.40, 0.80), 'kelly': (0.88, 0.80, 0.78, 0.84, 0.45, 0.66),
    'russo': (0.84, 0.86, 0.78, 0.83, 0.48, 0.78), 'ljames': (0.90, 0.84, 0.82, 0.88, 0.38, 0.70),
    'hegerberg': (0.80, 0.90, 0.74, 0.80, 0.40, 0.84), 'bronze': (0.85, 0.70, 0.80, 0.80, 0.86, 0.86),
    'pele': (0.92, 0.97, 0.90, 0.95, 0.50, 0.80), 'maradona': (0.88, 0.92, 0.92, 0.99, 0.40, 0.75),
    'zidane': (0.75, 0.88, 0.94, 0.96, 0.62, 0.84), 'ronaldinho': (0.86, 0.88, 0.93, 0.98, 0.38, 0.75),
    'r9': (0.96, 0.96, 0.80, 0.95, 0.35, 0.84), 'henry': (0.95, 0.92, 0.86, 0.92, 0.42, 0.80),
    'beckham': (0.72, 0.85, 0.97, 0.80, 0.62, 0.74), 'cantona': (0.72, 0.89, 0.88, 0.86, 0.48, 0.86),
    'zlatan': (0.76, 0.93, 0.84, 0.90, 0.40, 0.92), 'pirlo': (0.55, 0.82, 0.98, 0.86, 0.62, 0.62),
    'panenka': (0.66, 0.84, 0.86, 0.82, 0.50, 0.70), 'baggio': (0.80, 0.91, 0.88, 0.93, 0.35, 0.65),
    'totti': (0.74, 0.90, 0.92, 0.88, 0.45, 0.80), 'drogba': (0.84, 0.92, 0.76, 0.82, 0.48, 0.94),
    'gerrard': (0.80, 0.90, 0.92, 0.84, 0.78, 0.86), 'klose': (0.78, 0.92, 0.74, 0.76, 0.45, 0.82),
    'grosso': (0.80, 0.74, 0.76, 0.74, 0.82, 0.78), 'pearce': (0.74, 0.76, 0.74, 0.70, 0.88, 0.90),
    'balotelli': (0.82, 0.88, 0.70, 0.80, 0.35, 0.88), 'marta': (0.86, 0.92, 0.88, 0.96, 0.40, 0.70),
    'hamm': (0.90, 0.90, 0.84, 0.90, 0.45, 0.72), 'wambach': (0.76, 0.92, 0.74, 0.76, 0.48, 0.90),
    'rapinoe': (0.82, 0.86, 0.90, 0.88, 0.40, 0.64), 'morgan': (0.90, 0.88, 0.76, 0.84, 0.38, 0.74),
    'chastain': (0.80, 0.80, 0.80, 0.78, 0.84, 0.82), 'sawa': (0.80, 0.84, 0.92, 0.88, 0.72, 0.70),
    'prinz': (0.78, 0.92, 0.80, 0.84, 0.42, 0.86), 'sinclair': (0.82, 0.92, 0.84, 0.86, 0.42, 0.76),
    'ksmith': (0.84, 0.88, 0.84, 0.86, 0.40, 0.70),
    'professor': (0.70, 0.86, 0.99, 0.90, 0.70, 0.70), 'elloco': (0.90, 0.88, 0.70, 0.94, 0.30, 0.80),
    'ice': (0.84, 0.94, 0.86, 0.88, 0.50, 0.74), 'mystic': (0.86, 0.88, 0.95, 0.94, 0.50, 0.66),
    'thunder': (0.94, 0.98, 0.72, 0.80, 0.50, 0.97), 'shadow': (0.97, 0.86, 0.82, 0.96, 0.60, 0.70),
    'phoenix': (0.92, 0.92, 0.86, 0.92, 0.55, 0.80), 'wizard': (0.80, 0.90, 0.94, 0.99, 0.40, 0.65),
    'valkyrie': (0.90, 0.88, 0.80, 0.84, 0.88, 0.94), 'phantom': (0.95, 0.90, 0.84, 0.95, 0.45, 0.70),
    'siren': (0.88, 0.90, 0.90, 0.92, 0.45, 0.68),
}

# keeping, reflexes, handling, distribution, pace
KEEPERS = {
    'emi': (0.88, 0.88, 0.82, 0.78, 0.55), 'pickford': (0.82, 0.86, 0.76, 0.84, 0.58),
    'courtois': (0.92, 0.90, 0.90, 0.76, 0.50), 'bounou': (0.86, 0.88, 0.82, 0.80, 0.55),
    'donnarumma': (0.90, 0.92, 0.84, 0.70, 0.52), 'earps': (0.88, 0.88, 0.82, 0.80, 0.55),
    'hampton': (0.84, 0.86, 0.80, 0.84, 0.55), 'endler': (0.88, 0.88, 0.84, 0.82, 0.55),
    'coll': (0.86, 0.88, 0.82, 0.84, 0.58), 'buffon': (0.95, 0.94, 0.92, 0.78, 0.55),
    'yashin': (0.96, 0.95, 0.94, 0.80, 0.60), 'higuita': (0.80, 0.86, 0.74, 0.92, 0.70),
    'chilavert': (0.84, 0.84, 0.82, 0.90, 0.50), 'ceni': (0.84, 0.84, 0.82, 0.92, 0.50),
    'neuer': (0.94, 0.92, 0.90, 0.92, 0.72), 'dudek': (0.84, 0.90, 0.78, 0.74, 0.55),
    'kahn': (0.94, 0.94, 0.92, 0.72, 0.52), 'lehmann': (0.86, 0.86, 0.82, 0.78, 0.55),
    'schmeichel': (0.94, 0.95, 0.90, 0.86, 0.58), 'casillas': (0.93, 0.97, 0.86, 0.78, 0.60),
    'angerer': (0.90, 0.90, 0.88, 0.78, 0.55), 'solo': (0.92, 0.92, 0.88, 0.80, 0.58),
    'scurry': (0.86, 0.88, 0.80, 0.76, 0.55), 'thecat': (0.96, 0.99, 0.88, 0.80, 0.75),
    'colossus': (0.98, 0.88, 0.95, 0.74, 0.45),
}

# Name, kit (shirt, shorts, socks, keeper shirt), characters (keeper first)
TEAMS = {
    'legends': dict(name='LEGENDS', short='LEG', shirt=(0.95, 0.78, 0.22), shorts=(0.1, 0.1, 0.12),
                    socks=(0.95, 0.78, 0.22), keeper=(0.2, 0.2, 0.25), trim=(0.1, 0.1, 0.12),
                    keepers=['yashin', 'buffon', 'schmeichel', 'kahn', 'casillas'],
                    players=['pele', 'maradona', 'zidane', 'ronaldinho', 'r9', 'henry', 'beckham', 'cantona',
                             'zlatan', 'pirlo', 'baggio', 'totti', 'drogba', 'gerrard', 'klose']),
    'stars': dict(name='ALL STARS', short='AST', shirt=(0.12, 0.3, 0.85), shorts=(1.0, 1.0, 1.0),
                  socks=(0.12, 0.3, 0.85), keeper=(0.95, 0.85, 0.15), trim=(1.0, 1.0, 1.0),
                  keepers=['courtois', 'emi', 'donnarumma', 'bounou', 'pickford'],
                  players=['messi', 'ronaldo', 'haaland', 'mbappe', 'bellingham', 'vinicius', 'yamal', 'kane',
                           'salah', 'palmer', 'saka', 'neymar', 'lewandowski', 'jorginho', 'rashford',
                           'grealish']),
    'queens': dict(name='QUEENS', short='QNS', shirt=(0.9, 0.2, 0.45), shorts=(0.95, 0.95, 0.95),
                   socks=(0.9, 0.2, 0.45), keeper=(0.2, 0.75, 0.6), trim=(1.0, 1.0, 1.0),
                   keepers=['earps', 'endler', 'coll', 'hampton'],
                   players=['bonmati', 'putellas', 'kerr', 'kelly', 'russo', 'ljames', 'hegerberg', 'bronze']),
    'pioneers': dict(name='PIONEERS', short='PIO', shirt=(0.95, 0.95, 0.95), shorts=(0.1, 0.18, 0.45),
                     socks=(0.85, 0.12, 0.15), keeper=(0.95, 0.5, 0.1), trim=(0.85, 0.12, 0.15),
                     keepers=['solo', 'angerer', 'scurry'],
                     players=['marta', 'hamm', 'wambach', 'rapinoe', 'morgan', 'chastain', 'sawa', 'prinz',
                              'sinclair', 'ksmith']),
    'myths': dict(name='MYTHS', short='MYT', shirt=(0.4, 0.12, 0.6), shorts=(0.1, 0.05, 0.15),
                  socks=(0.4, 0.12, 0.6), keeper=(0.1, 0.85, 0.75), trim=(0.75, 0.4, 1.0),
                  keepers=['thecat', 'colossus'],
                  players=['professor', 'elloco', 'ice', 'mystic', 'thunder', 'shadow', 'phoenix', 'wizard',
                           'valkyrie', 'phantom', 'siren']),
    'cult': dict(name='CULT HEROES', short='CLT', shirt=(0.1, 0.55, 0.25), shorts=(1.0, 1.0, 1.0),
                 socks=(0.1, 0.55, 0.25), keeper=(0.95, 0.4, 0.7), trim=(1.0, 1.0, 1.0),
                 keepers=['higuita', 'chilavert', 'ceni', 'dudek', 'lehmann', 'neuer'],
                 players=['grosso', 'pearce', 'balotelli', 'panenka', 'jorginho', 'grealish', 'rashford']),
    # Unlocked by finishing challenges (sim/challenges.py)
    'dream': dict(name='DREAM XI', short='DRM', shirt=(0.08, 0.08, 0.1), shorts=(0.95, 0.78, 0.22),
                  socks=(0.08, 0.08, 0.1), keeper=(0.85, 0.85, 0.9), trim=(0.95, 0.78, 0.22),
                  keepers=['yashin', 'casillas', 'neuer'],
                  players=['pele', 'maradona', 'messi', 'r9', 'zidane', 'marta', 'bonmati', 'ronaldo', 'henry',
                           'beckham', 'gerrard', 'bronze', 'valkyrie', 'mbappe', 'pirlo']),
}
HIDDEN = {'dream'}      # not offered until unlocked

# Club sides made of generated players, using the shootout's team colours
CLUBS = [
    ('reds', 'REDS', 'RED', (0.85, 0.12, 0.15), (1.0, 1.0, 1.0), (0.15, 0.75, 0.25)),
    ('blues', 'BLUES', 'BLU', (0.15, 0.35, 0.9), (0.1, 0.1, 0.15), (0.95, 0.8, 0.1)),
    ('whites', 'WHITES', 'WHI', (0.95, 0.95, 0.95), (0.1, 0.1, 0.12), (0.2, 0.2, 0.25)),
    ('oranges', 'ORANGES', 'ORA', (0.95, 0.5, 0.1), (1.0, 1.0, 1.0), (0.1, 0.1, 0.12)),
    ('skyblues', 'SKY BLUES', 'SKY', (0.45, 0.7, 0.95), (1.0, 1.0, 1.0), (0.9, 0.3, 0.1)),
]
FIRST = ['Alex', 'Sam', 'Jordan', 'Chris', 'Luca', 'Mateo', 'Kai', 'Noah', 'Leo', 'Rafa', 'Tom', 'Ben', 'Dani',
         'Joao', 'Max', 'Ola', 'Tiago', 'Yusuf', 'Arlo', 'Rio']
LAST = ['SILVA', 'MORENO', 'KOVAC', 'OKAFOR', 'HUGHES', 'BAKER', 'ROSSI', 'MULLER', 'NAKAMURA', 'DIALLO',
        'PEREIRA', 'WALSH', 'NOVAK', 'LINDQVIST', 'ADEYEMI', 'COSTA', 'FISCHER', 'GARCIA', 'MENDY', 'BRANDT']


def _hash(*parts):
    return zlib.crc32('|'.join(str(p) for p in parts).encode())


class Footballer:
    """Everything the match needs to know about one player."""

    def __init__(self, key, name, number, look, keeper=False, women=False, stats=None, gk=None, aura=0.5,
                 glow=None, foot='R', celebration=None, era='club', pen=None):
        self.key = key
        self.name = name
        self.number = number
        self.look = look
        self.keeper = keeper
        self.women = women
        self.pace, self.shooting, self.passing, self.dribbling, self.defending, self.physical = \
            stats or (0.7, 0.7, 0.7, 0.7, 0.6, 0.7)
        self.keeping, self.reflexes, self.handling, self.distribution, self.gk_pace = \
            gk or (0.4, 0.4, 0.4, 0.5, 0.5)
        if keeper:
            self.pace = self.gk_pace
        self.aura = aura
        self.glow = glow
        self.foot = foot
        self.celebration = celebration
        self.era = era
        # Spot-kick ratings from the penalty game: composure, power, placement
        self.pen = pen or (0.5 + 0.4 * self.shooting * (0.6 + 0.4 * aura), 0.4 + 0.5 * self.shooting,
                           0.35 + 0.55 * self.shooting)

    def overall(self):
        if self.keeper:
            return (self.keeping + self.reflexes + self.handling) / 3.0
        return (self.pace + self.shooting + self.passing + self.dribbling + self.defending * 0.6
                + self.physical * 0.6) / 5.2


def from_character(key, number=None):
    ch = CH.get(key)
    if ch is None:
        return None
    gk = KEEPERS.get(key)
    st = STATS.get(key)
    if st is None:
        # Derive outfield numbers from the penalty ratings, with a stable spread
        r = random.Random(_hash(key))
        shoot = (ch['power'] + ch['placement']) / 2.0
        st = (r.uniform(0.66, 0.86), shoot, 0.55 + 0.35 * ch['placement'], 0.5 + 0.4 * ch['composure'],
              r.uniform(0.35, 0.6), r.uniform(0.6, 0.85))
    glow = tuple(ch['glow']) if ch.get('glow') else CH.GLOWS.get(ch['era'], CH.GLOWS['mod'])
    return Footballer(key, ch['name'], ch['number'] if number is None else number, dict(ch['look']),
                      keeper=gk is not None, women=ch['women'], stats=st, gk=gk, aura=ch['aura'], glow=glow,
                      foot=ch['foot'], celebration=ch['celebration'], era=ch['era'],
                      pen=(ch['composure'], ch['power'], ch['placement']))


def club_player(club, i, keeper=False):
    r = random.Random(_hash(club, i))
    names = list(LAST)
    random.Random(_hash(club)).shuffle(names)
    name = names[i % len(names)]
    look = CH.club_look(_hash(club, i, 'look'), keeper=keeper)
    base = r.uniform(0.6, 0.78)
    st = tuple(max(0.3, min(0.95, base + r.uniform(-0.12, 0.12))) for _ in range(6))
    gk = tuple(max(0.3, min(0.95, base + r.uniform(-0.08, 0.1))) for _ in range(5)) if keeper else None
    return Footballer('%s%d' % (club, i), name, 1 if keeper else i + 1, look, keeper=keeper, stats=st, gk=gk,
                      aura=0.3, era='club')


def team_ids(unlocked=()):
    """Every team on offer: the character teams, any unlocked hidden ones, then the clubs."""
    return [t for t in TEAMS if t not in HIDDEN or t in unlocked] + [c[0] for c in CLUBS]


def team_info(tid):
    if tid in TEAMS:
        t = TEAMS[tid]
        return dict(id=tid, name=t['name'], short=t['short'], shirt=t['shirt'], shorts=t['shorts'],
                    socks=t['socks'], keeper=t['keeper'], trim=t['trim'])
    for cid, name, short, shirt, shorts, keeper in CLUBS:
        if cid == tid:
            return dict(id=cid, name=name, short=short, shirt=shirt, shorts=shorts, socks=shirt, keeper=keeper,
                        trim=shorts)
    raise KeyError(tid)


def squad(tid, size, rng=None):
    """Keeper first, then the best size-1 outfield players (characters picked
    by overall, with a little rotation if rng is given)."""
    rng = rng or random.Random(0)
    if tid in TEAMS:
        t = TEAMS[tid]
        gk = from_character(t['keepers'][0])
        pool = [from_character(k) for k in t['players']]
        pool = [p for p in pool if p is not None]
        pool.sort(key=lambda p: -(p.overall() + rng.uniform(0.0, 0.05)))
        out = pool[:size - 1]
        while len(out) < size - 1:
            out.append(club_player(tid, len(out) + 20))
        used = {gk.number}
        for p in out:
            if p.number in used:
                p.number = next(n for n in range(2, 99) if n not in used)
            used.add(p.number)
        return [gk] + out
    return [club_player(tid, 0, keeper=True)] + [club_player(tid, i + 1) for i in range(size - 1)]


def kits_clash(a, b):
    """True when two shirts are too alike to tell apart."""
    return sum(abs(x - y) for x, y in zip(a, b)) < 0.6
