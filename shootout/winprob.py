"""Live win probability for a shootout, worked out exactly from the score.

Each kick scores with probability conv[side]. Regulation kicks are solved by
recursion; once the shootout reaches sudden death the chance per round has a
closed form.
"""

from functools import lru_cache

from .rules import Shootout


def p1_wins(rules, conv):
    """Chance that p1 wins from the current state of a rules.Shootout."""
    if rules.winner is not None:
        return 1.0 if rules.winner == 'p1' else 0.0
    n, first, order = rules.kicks_per_side, rules.first, rules.order
    a, b = conv['p1'], conv['p2']
    # In sudden death each pair of kicks: p1 wins the round if he scores and
    # p2 misses; the round repeats if both score or both miss
    w = a * (1 - b)
    lose = b * (1 - a)
    sd = w / (w + lose) if w + lose > 0 else 0.5

    @lru_cache(maxsize=None)
    def solve(r1, r2):
        trial = Shootout(first, n, order)
        trial.results = {'p1': list(r1), 'p2': list(r2)}
        win = trial._decide()
        if win is not None:
            return 1.0 if win == 'p1' else 0.0
        k1, k2 = len(r1), len(r2)
        if k1 == k2 and k1 >= n and sum(r1) == sum(r2):
            return sd
        side = trial.next_kicker()
        p = a if side == 'p1' else b
        if side == 'p1':
            return p * solve(r1 + (True,), r2) + (1 - p) * solve(r1 + (False,), r2)
        return p * solve(r1, r2 + (True,)) + (1 - p) * solve(r1, r2 + (False,))

    return solve(tuple(rules.results['p1']), tuple(rules.results['p2']))
