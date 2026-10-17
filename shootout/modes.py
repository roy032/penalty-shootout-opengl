"""Competition formats. Each one decides who kicks next and when it is over.

Every kick has two slots: the kicking side and the keeping side, 'p1' and
'p2'. Slot 'p1' always uses Player 1's keys and 'p2' Player 2's, unless a
slot is computer-controlled.
"""

from . import config as C
from .rules import Shootout

SHIRT_NUMBERS = [9, 10, 7, 8, 11, 4, 5, 6, 2, 3]


def _kit(colour, keeper=(0.2, 0.2, 0.25)):
    return dict(shirt=colour, shorts=(0.95, 0.95, 0.95), keeper=keeper)


class Competition:
    """Shared defaults; subclasses fill in the format."""
    finished = False
    winner = None
    sudden_death_label = True

    def __init__(self, names, kits, control):
        self.names = dict(names)
        self.kits = dict(kits)
        self.control = dict(control)       # slot -> 'human' | 'ai'
        self.specialist = {'p1': False, 'p2': False}
        self.yellows = {'p1': 0, 'p2': 0}
        self.emergency = {'p1': False, 'p2': False}

    def name(self, slot):
        return self.names[slot]

    def kit(self, slot):
        return self.kits[slot]

    def keeper_colour(self, slot):
        if self.emergency[slot]:
            return C.EMERGENCY_KIT
        if self.specialist[slot]:
            return C.SPECIALIST_KIT
        return self.kits[slot]['keeper']

    def is_human(self, slot):
        return self.control[slot] == 'human'

    def taker(self, slot):
        return None

    def taker_is_keeper(self, slot):
        return False

    def stakes(self, slot):
        return None

    def in_sudden_death(self):
        return False

    def summary_line(self):
        return ''

    def winner_name(self):
        w = self.winner
        if w in ('p1', 'p2'):
            return self.names[w]
        return w


class ShootoutComp(Competition):
    """A normal shootout (also used for famous scenarios and PvP)."""

    def __init__(self, names, kits, control, first='p1', kicks=5, results=None):
        super().__init__(names, kits, control)
        self.rules = Shootout(first=first, kicks_per_side=kicks)
        if results:
            self.rules.results = {s: list(r) for s, r in results.items()}

    @property
    def finished(self):
        return self.rules.winner is not None

    @property
    def winner(self):
        return self.rules.winner

    def next_kicker(self):
        return self.rules.next_kicker()

    def record(self, slot, scored):
        self.rules.record(slot, scored)

    def stakes(self, slot):
        return self.rules.stakes(slot)

    def in_sudden_death(self):
        return self.rules.in_sudden_death()

    def goals(self, slot):
        return self.rules.goals(slot)

    def rows(self):
        return [dict(slot=s, name=self.names[s], colour=self.kits[s]['shirt'],
                     results=self.rules.results[s], goals=self.rules.goals(s),
                     regulation=self.rules.kicks_per_side) for s in ('p1', 'p2')]

    def taker(self, slot):
        i = self.rules.kicks(slot) % C.SQUAD_SIZE
        if i == C.SQUAD_SIZE - 1:
            return 'Goalkeeper'
        return f'No. {SHIRT_NUMBERS[i]}'

    def taker_is_keeper(self, slot):
        return self.rules.kicks(slot) % C.SQUAD_SIZE == C.SQUAD_SIZE - 1

    def summary_line(self):
        r = self.rules
        sd = max(r.kicks('p1'), r.kicks('p2')) > r.kicks_per_side
        return f"{r.goals('p1')} - {r.goals('p2')} on penalties" + ('  (after sudden death)' if sd else '')


class TrainingComp(Competition):
    """Endless practice. role 'kick': Player 1 kicks every time. 'keep': the
    drill machine kicks at Player 1."""
    sudden_death_label = False

    def __init__(self, role):
        names = {'p1': 'YOU', 'p2': 'DRILL'}
        kits = {'p1': C.KITS['p1'], 'p2': C.KITS['p2']}
        if role == 'kick':
            control = {'p1': 'human', 'p2': 'ai'}
        else:
            control = {'p1': 'ai', 'p2': 'human'}
            names = {'p1': 'DRILL', 'p2': 'YOU'}
        super().__init__(names, kits, control)
        self.role = role
        self.results = []

    def next_kicker(self):
        return 'p1'

    def record(self, slot, scored):
        self.results.append(scored)

    def rows(self):
        made = sum(self.results)
        label = 'scored' if self.role == 'kick' else 'conceded'
        return [dict(slot='p1', name=f'{made}/{len(self.results)} {label}', colour=self.kits['p1']['shirt'],
                     results=self.results[-10:], goals=made, regulation=10)]


class MatchPenaltyComp(Competition):
    """A single penalty in the 90th minute at 1-1. Rebounds are live."""
    sudden_death_label = False

    def __init__(self, role):
        names = {'p1': 'YOU', 'p2': 'CPU'}
        control = {'p1': 'human', 'p2': 'ai'} if role == 'kick' else {'p1': 'ai', 'p2': 'human'}
        if role == 'keep':
            names = {'p1': 'CPU', 'p2': 'YOU'}
        super().__init__(names, {'p1': C.KITS['p1'], 'p2': C.KITS['p2']}, control)
        self.role = role
        self.result = None

    @property
    def finished(self):
        return self.result is not None

    @property
    def winner(self):
        if self.result is None:
            return None
        return 'p1' if self.result else 'p2'

    def next_kicker(self):
        return 'p1'

    def record(self, slot, scored):
        self.result = scored

    def rows(self):
        res = [] if self.result is None else [self.result]
        return [dict(slot='p1', name="90'  1 - 1", colour=self.kits['p1']['shirt'],
                     results=res, goals=int(bool(self.result)), regulation=1)]

    def summary_line(self):
        if self.result:
            return '2 - 1: a last-minute winner from the spot!'
        return 'Still 1 - 1 at the final whistle.'


class KingOfTheGoal(Competition):
    """Party mode: each round one friend keeps goal and everyone else takes a
    kick. Goals score for kickers, saves and misses for the keeper. Everyone
    keeps once."""
    sudden_death_label = False

    def __init__(self, players):
        self.players = [f'PLAYER {i + 1}' for i in range(players)]
        self.colours = C.PARTY_COLOURS[:players]
        self.points = [0] * players
        self.round = 0                 # index of the player in goal
        self.order = []
        self.turn = 0
        super().__init__({'p1': '', 'p2': ''}, {'p1': C.KITS['p1'], 'p2': C.KITS['p2']},
                         {'p1': 'human', 'p2': 'human'})
        self._set_round()

    def _set_round(self):
        n = len(self.players)
        self.order = [(self.round + k) % n for k in range(1, n)]
        self.turn = 0
        self._set_slots()

    def _set_slots(self):
        kicker = self.order[self.turn]
        keeper = self.round
        self.names = {'p1': self.players[kicker], 'p2': self.players[keeper]}
        self.kits = {'p1': _kit(self.colours[kicker]), 'p2': _kit(self.colours[keeper], self.colours[keeper])}

    @property
    def finished(self):
        return self.round >= len(self.players)

    @property
    def winner(self):
        if not self.finished:
            return None
        best = max(self.points)
        top = [p for p, pts in zip(self.players, self.points) if pts == best]
        return top[0] if len(top) == 1 else ' & '.join(top) + ' (shared)'

    def next_kicker(self):
        return 'p1'

    def record(self, slot, scored):
        kicker = self.order[self.turn]
        if scored:
            self.points[kicker] += 1
        else:
            self.points[self.round] += 1
        self.turn += 1
        if self.turn >= len(self.order):
            self.round += 1
            if not self.finished:
                self._set_round()
        else:
            self._set_slots()

    def table(self):
        return sorted(zip(self.players, self.points, self.colours), key=lambda r: -r[1])

    def rows(self):
        return []

    def summary_line(self):
        return '   '.join(f'{p}: {pts}' for p, pts, _ in self.table())


class Knockout(Competition):
    """Party mode: a bracket of quick shootouts between friends."""

    def __init__(self, players, kicks=3):
        self.players = [f'PLAYER {i + 1}' for i in range(players)]
        self.colours = C.PARTY_COLOURS[:players]
        self.kicks = kicks
        self.queue = list(range(players))   # still to play this round
        self.winners = []                   # through to the next round
        self.champion = None
        self.history = []                   # (winner name, loser name)
        self.tie = None
        super().__init__({'p1': '', 'p2': ''}, {'p1': C.KITS['p1'], 'p2': C.KITS['p2']},
                         {'p1': 'human', 'p2': 'human'})
        self._next_tie()

    def _next_tie(self):
        if len(self.queue) < 2:
            # Round over: a player left without an opponent gets a bye
            self.queue = self.winners + self.queue
            self.winners = []
            if len(self.queue) == 1:
                self.champion = self.queue[0]
                self.tie = None
                return
        a, b = self.queue.pop(0), self.queue.pop(0)
        self.pair = (a, b)
        self.tie = Shootout(first='p1', kicks_per_side=self.kicks)
        self.names = {'p1': self.players[a], 'p2': self.players[b]}
        self.kits = {'p1': _kit(self.colours[a], self.colours[a]), 'p2': _kit(self.colours[b], self.colours[b])}

    @property
    def finished(self):
        return self.champion is not None

    @property
    def winner(self):
        return None if self.champion is None else self.players[self.champion]

    def next_kicker(self):
        return self.tie.next_kicker()

    def record(self, slot, scored):
        won = self.tie.record(slot, scored)
        if won:
            a, b = self.pair
            w, lost = (a, b) if won == 'p1' else (b, a)
            self.history.append((self.players[w], self.players[lost]))
            self.winners.append(w)
            self._next_tie()
        return won

    def stakes(self, slot):
        return self.tie.stakes(slot) if self.tie else None

    def in_sudden_death(self):
        return bool(self.tie) and self.tie.in_sudden_death()

    def rows(self):
        if not self.tie:
            return []
        return [dict(slot=s, name=self.names[s], colour=self.kits[s]['shirt'],
                     results=self.tie.results[s], goals=self.tie.goals(s),
                     regulation=self.kicks) for s in ('p1', 'p2')]

    def summary_line(self):
        return '   '.join(f'{w} beat {lost}' for w, lost in self.history)


