"""Shootout scoring rules (Law 10), kept free of OpenGL so they can be tested."""

SIDES = ('p1', 'p2')


def other(side):
    return 'p2' if side == 'p1' else 'p1'


class Shootout:
    """Tracks kicks for both sides and decides the winner.

    Regulation: each side takes `kicks_per_side` kicks, alternating. The
    shootout ends early once one side cannot be caught. If level after
    regulation, sudden death: pairs of kicks until one side leads after an
    equal number of kicks.
    """

    def __init__(self, first='p1', kicks_per_side=5):
        self.first = first
        self.kicks_per_side = kicks_per_side
        self.results = {'p1': [], 'p2': []}
        self.winner = None

    def goals(self, side):
        return sum(1 for r in self.results[side] if r)

    def kicks(self, side):
        return len(self.results[side])

    def next_kicker(self):
        a, b = self.kicks(self.first), self.kicks(other(self.first))
        return self.first if a == b else other(self.first)

    def in_sudden_death(self):
        n = self.kicks_per_side
        return self.kicks('p1') >= n and self.kicks('p2') >= n and self.winner is None

    def record(self, side, scored):
        if self.winner is not None:
            raise ValueError('shootout already decided')
        if side != self.next_kicker():
            raise ValueError(f'{side} is not due to kick')
        self.results[side].append(bool(scored))
        self.winner = self._decide()
        return self.winner

    def _decide(self):
        n = self.kicks_per_side
        na, nb = self.kicks('p1'), self.kicks('p2')
        ga, gb = self.goals('p1'), self.goals('p2')
        if na <= n and nb <= n:
            if ga > gb + (n - nb):
                return 'p1'
            if gb > ga + (n - na):
                return 'p2'
            return None
        if na == nb and ga != gb:
            return 'p1' if ga > gb else 'p2'
        return None

    def stakes(self, side):
        """What rides on `side`'s next kick: 'to_win', 'must_score' or None."""
        if self.winner is not None:
            return None
        for scored, label in ((True, 'to_win'), (False, 'must_score')):
            trial = Shootout(self.first, self.kicks_per_side)
            trial.results = {s: list(r) for s, r in self.results.items()}
            result = trial.record(side, scored)
            if scored and result == side:
                return label
            if not scored and result == other(side):
                return label
        return None
