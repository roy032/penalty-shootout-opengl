"""Tournament night: a knockout bracket for 2 to 8 players on one machine.

Each player gets their own team. Matches are head to head (two humans), and a
draw goes to penalties, so every match has a winner. Byes fill the bracket up
to the next power of two."""

import random

from . import roster


class Tournament:
    def __init__(self, names, seed=None):
        if not 2 <= len(names) <= 8:
            raise ValueError('2 to 8 players')
        rng = random.Random(seed)
        teams = [t for t in roster.TEAMS if t not in roster.HIDDEN]
        rng.shuffle(teams)
        clubs = [c[0] for c in roster.CLUBS]
        rng.shuffle(clubs)
        pool = teams + clubs
        self.players = [dict(name=n, team=pool[i]) for i, n in enumerate(names)]
        order = list(range(len(names)))
        rng.shuffle(order)
        size = 1
        while size < len(names):
            size *= 2
        slots = order + [None] * (size - len(order))
        # Spread the byes so nobody gets two
        first = []
        for i in range(size // 2):
            first.append([slots[i], slots[size - 1 - i]])
        self.rounds = [[dict(a=a, b=b, winner=None, score=None) for a, b in first]]
        self._settle_byes()

    def _settle_byes(self):
        while True:
            rnd = self.rounds[-1]
            for g in rnd:
                if g['winner'] is None and (g['a'] is None or g['b'] is None):
                    g['winner'] = g['a'] if g['b'] is None else g['b']
                    g['score'] = 'bye'
            if any(g['winner'] is None for g in rnd) or len(rnd) == 1:
                return
            nxt = [dict(a=rnd[i]['winner'], b=rnd[i + 1]['winner'], winner=None, score=None)
                   for i in range(0, len(rnd), 2)]
            self.rounds.append(nxt)

    @property
    def champion(self):
        last = self.rounds[-1]
        return last[0]['winner'] if len(last) == 1 and last[0]['winner'] is not None else None

    def next_match(self):
        """(round index, game) still to play, or None when there's a champion."""
        for ri, rnd in enumerate(self.rounds):
            for g in rnd:
                if g['winner'] is None and g['a'] is not None and g['b'] is not None:
                    return ri, g
        return None

    def record(self, game, home_goals, away_goals, pens=None):
        """Result of a game from 'a' (home) against 'b' (away); pens (a, b) if it went to penalties."""
        hg, ag = (home_goals, away_goals) if home_goals != away_goals or not pens else pens
        if hg == ag:
            raise ValueError('a knockout game needs a winner')
        game['winner'] = game['a'] if hg > ag else game['b']
        game['score'] = '%d-%d' % (home_goals, away_goals) + (' (%d-%d pens)' % tuple(pens) if pens and
                                                              home_goals == away_goals else '')
        self._settle_byes()

    def round_name(self, ri):
        left = len(self.rounds[0]) * 2 >> ri
        return {2: 'Final', 4: 'Semi-finals', 8: 'Quarter-finals'}.get(left, 'Round %d' % (ri + 1))

    def lines(self):
        out = []
        for ri, rnd in enumerate(self.rounds):
            out.append(self.round_name(ri))
            for g in rnd:
                if g['score'] == 'bye':
                    continue
                a = self.players[g['a']]['name'] if g['a'] is not None else '?'
                b = self.players[g['b']]['name'] if g['b'] is not None else '?'
                res = g['score'] or ''
                out.append('   %s v %s   %s' % (a, b, res))
        return out
