"""Competition formats. Each one decides who kicks next and when it is over.

Every kick has two slots: the kicking side and the keeping side, 'p1' and
'p2'. Slot 'p1' always uses Player 1's keys and 'p2' Player 2's, unless a
slot is computer-controlled.
"""

import random

from . import config as C, squad as S
from .rules import Shootout


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
        self.keeper_style = {'p1': 'standard', 'p2': 'standard'}
        self.order = {'p1': None, 'p2': None}      # taker order (squad.Player list), if there are squads
        self.manager = None                         # slot picked by a human manager who does not play

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

    def player(self, slot):
        return None

    def taker(self, slot):
        p = self.player(slot)
        return p.label if p else None

    def taker_is_keeper(self, slot):
        p = self.player(slot)
        return bool(p and p.keeper)

    def stakes(self, slot):
        return None

    def judge(self, slot, scored, info):
        """Lets a format decide what counts (challenges score bins, not goals)."""
        return scored

    def interlude(self):
        """Text to show between rounds (tournament bracket), or None."""
        return None

    def ghost_shot(self, slot):
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

    def __init__(self, names, kits, control, first='p1', kicks=5, results=None, order='abab', rng=None,
                 strength=(0.55, 0.55)):
        super().__init__(names, kits, control)
        self.rules = Shootout(first=first, kicks_per_side=kicks, order=order)
        if results:
            self.rules.results = {s: list(r) for s, r in results.items()}
        rng = rng or random.Random(0)
        self.squads = {s: S.make_squad(rng, st) for s, st in zip(('p1', 'p2'), strength)}
        self.order = {s: S.ai_order(rng, sq) for s, sq in self.squads.items()}
        self.subs = {'p1': 0, 'p2': 0}

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

    def player(self, slot):
        order = self.order[slot]
        return order[self.rules.kicks(slot) % len(order)]

    def slot_index(self, slot):
        return self.rules.kicks(slot) % len(self.order[slot])

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




class GhostComp(ShootoutComp):
    """A ghost duel: the challenger's recorded kicks come at you exactly as
    they were struck, then you take five against the computer keeper. Your
    five are saved as the reply."""

    def __init__(self, challenge, rng=None):
        kits = {'p1': {k: tuple(v) for k, v in challenge['kit'].items()}, 'p2': C.KITS['p1']}
        if kits['p1']['shirt'] == kits['p2']['shirt']:
            kits['p2'] = C.KITS['p2']
        super().__init__({'p1': challenge.get('name', 'GHOST')[:12].upper(), 'p2': 'YOU'}, kits,
                         {'p1': 'ai', 'p2': 'human'}, first='p1', kicks=5, rng=rng)
        self.challenge = challenge
        self.kicks_left = list(challenge['kicks'])

    def ghost_shot(self, slot):
        if slot != 'p1' or not self.kicks_left:
            return None
        i = self.rules.kicks('p1') % len(self.kicks_left)
        return self.kicks_left[i]

    def summary_line(self):
        r = self.rules
        return f"The ghost scored {r.goals('p1')} against you; you scored {r.goals('p2')}."


ROUND_NAMES = ['Quarter-final', 'Semi-final', 'Final']
ROUND_LEVELS = ['easy', 'medium', 'hard']


class TournamentComp(ShootoutComp):
    """A World Cup style knockout of eight teams, every tie decided on
    penalties. You are the first team; the other ties are simulated."""

    def __init__(self, teams, rng, kicks=5, order='abab'):
        self.rng = rng
        self.teams = [dict(t) for t in teams[:8]]
        self.alive = list(range(len(self.teams)))
        self.round = 0
        self.results = []               # (round, winner name, loser name, score)
        self.over = False
        self.champion = False
        self.pending = None
        self.kicks_n = kicks
        self.order_kind = order
        self._start_tie()

    def _opponent(self):
        i = self.alive.index(0)
        return self.alive[i ^ 1]

    def _start_tie(self):
        me, opp = self.teams[0], self.teams[self._opponent()]
        kits = {'p1': dict(shirt=me['shirt'], shorts=me['shorts'], keeper=me['keeper']),
                'p2': dict(shirt=opp['shirt'], shorts=opp['shorts'], keeper=opp['keeper'])}
        if kits['p1']['shirt'] == kits['p2']['shirt']:
            kits['p2'] = dict(kits['p2'], shirt=(0.95, 0.95, 0.95))
        ShootoutComp.__init__(self, {'p1': me['name'], 'p2': opp['name']}, kits, {'p1': 'human', 'p2': 'ai'},
                              first=self.rng.choice(('p1', 'p2')), kicks=self.kicks_n, order=self.order_kind,
                              rng=self.rng, strength=(0.55, 0.5 + 0.05 * self.round))

    @property
    def level(self):
        return ROUND_LEVELS[min(self.round, 2)]

    @property
    def finished(self):
        return self.over

    @property
    def winner(self):
        if not self.over:
            return None
        return 'p1' if self.champion else 'p2'

    def winner_name(self):
        return self.teams[0]['name'] if self.champion else self.names['p2']

    def record(self, slot, scored):
        won = self.rules.record(slot, scored)
        if won is None:
            return None
        g1, g2 = self.rules.goals('p1'), self.rules.goals('p2')
        score = f'{max(g1, g2)}-{min(g1, g2)}'          # the winner's score first
        opp = self._opponent()
        stage = ROUND_NAMES[self.round] if self.round < 3 else ''
        if won == 'p1':
            self.results.append((stage, self.teams[0]['name'], self.teams[opp]['name'], score))
        else:
            self.results.append((stage, self.teams[opp]['name'], self.teams[0]['name'], score))
            self.over = True
            return won
        # Settle the other ties of this round
        survivors = []
        pairs = [self.alive[i:i + 2] for i in range(0, len(self.alive), 2)]
        for pair in pairs:
            if 0 in pair or len(pair) < 2:
                survivors.append(0 if 0 in pair else pair[0])
                continue
            a, b = pair
            w, lost = (a, b) if self.rng.random() < 0.5 else (b, a)
            goals = self.rng.choice(['4-3', '5-4', '3-2', '4-2', '6-5'])
            self.results.append((stage, self.teams[w]['name'], self.teams[lost]['name'], goals))
            survivors.append(w)
        self.alive = sorted(survivors)
        self.round += 1
        if len(self.alive) == 1:
            self.over = True
            self.champion = True
        else:
            self.pending = f'Through to the {ROUND_NAMES[self.round].lower()}!'
        return won

    def interlude(self):
        return self.pending

    def next_tie(self):
        self.pending = None
        self._start_tie()

    def bracket(self):
        return [f'{stage}: {w} beat {lost} {score}' for stage, w, lost, score in self.results]

    def summary_line(self):
        if self.champion:
            return f"{self.teams[0]['name']} are champions!"
        return f"Knocked out in the {ROUND_NAMES[min(self.round, 2)].lower()}."


CAREER_TRAITS = {
    'kick': [('Ice veins', 'pressure'), ('Laser', 'accuracy'), ('Thunder', 'power'), ('Showman', 'pressure'),
             ('Sniper', 'accuracy')],
    'keep': [('Long arms', 'reach'), ('Cat', 'speed'), ('Safe hands', 'catch'), ('Wall', 'reach'),
             ('Reader', 'read')],
}
CAREER_XP = [30, 60, 100, 150, 210]
GOLD_XP = 100


def career_defaults(role):
    return dict(role=role, xp=0, games=0, wins=0, traits=[], gold=False)


class CareerComp(MatchPenaltyComp):
    """One fixture in a career: a single penalty, against stronger opponents
    as you climb. Success earns XP; XP unlocks traits and a gold kit."""

    def __init__(self, career):
        super().__init__(career['role'])
        self.career = career
        if career.get('gold'):
            mine = 'p1' if career['role'] == 'kick' else 'p2'
            self.kits = dict(self.kits)
            self.kits[mine] = dict(self.kits[mine], shirt=C.CAREER_GOLD_KIT)
        self.names = {'p1': 'YOU', 'p2': 'RIVALS'} if career['role'] == 'kick' else {'p1': 'RIVALS', 'p2': 'YOU'}

    @property
    def level(self):
        return 'easy' if self.career['games'] < 4 else 'medium' if self.career['games'] < 10 else 'hard'

    def traits(self, kind):
        return sum(1 for name, k in CAREER_TRAITS[self.career['role']] if name in self.career['traits']
                   and k == kind)

    def finish(self):
        """Add XP after the fixture. Returns the list of things unlocked."""
        c = self.career
        success = self.result if c['role'] == 'kick' else not self.result
        c['games'] += 1
        c['wins'] += int(success)
        before = c['xp']
        c['xp'] += 15 if success else 4
        unlocked = []
        for i, need in enumerate(CAREER_XP):
            if before < need <= c['xp'] and i < len(CAREER_TRAITS[c['role']]):
                name = CAREER_TRAITS[c['role']][i][0]
                c['traits'].append(name)
                unlocked.append(f'Trait: {name}')
        if before < GOLD_XP <= c['xp']:
            c['gold'] = True
            unlocked.append('Gold kit')
        return unlocked

    def summary_line(self):
        c = self.career
        return f"Career: {c['wins']}/{c['games']} won, {c['xp']} XP  |  Traits: {', '.join(c['traits']) or 'none yet'}"


CHALLENGES = {
    'bins': dict(label='Top Bins', desc='Five kicks, no keeper: hit the bins in the top corners.', kicks=5,
                 role='kick'),
    'panenka': dict(label='Panenka', desc='Five chips down the middle against a hard keeper. Score 3.', kicks=5,
                    role='kick'),
    'saves': dict(label='Save 3 in a row', desc='Face up to 12 kicks from a sharp kicker. Save 3 in a row.',
                  kicks=12, role='keep'),
    'survival': dict(label='Sudden death survival', desc='Keep scoring. One miss and it is over.', kicks=999,
                     role='kick'),
}
CHALLENGE_ORDER = ['bins', 'panenka', 'saves', 'survival']
BINS = [(-3.05, 2.0), (3.05, 2.0)]
BIN_RADIUS = 0.42


class ChallengeComp(Competition):
    sudden_death_label = False

    def __init__(self, kind):
        spec = CHALLENGES[kind]
        if spec['role'] == 'kick':
            names, control = {'p1': 'YOU', 'p2': 'KEEPER'}, {'p1': 'human', 'p2': 'ai'}
        else:
            names, control = {'p1': 'SHOOTER', 'p2': 'YOU'}, {'p1': 'ai', 'p2': 'human'}
        super().__init__(names, {'p1': C.KITS['p1'], 'p2': C.KITS['p2']}, control)
        self.kind = kind
        self.spec = spec
        self.results = []
        self.streak = 0
        self.done = False

    @property
    def no_keeper(self):
        return self.kind == 'bins'

    @property
    def finished(self):
        return self.done

    @property
    def score(self):
        if self.kind == 'saves':
            return self.streak
        return sum(self.results)

    @property
    def winner(self):
        if not self.done:
            return None
        target = {'bins': 3, 'panenka': 3, 'saves': 3, 'survival': 5}[self.kind]
        return 'p1' if self.score >= target else 'p2'

    def winner_name(self):
        return 'CHALLENGE COMPLETE' if self.winner == 'p1' else 'CHALLENGE FAILED'

    def next_kicker(self):
        return 'p1'

    def judge(self, slot, scored, info):
        if self.kind == 'bins':
            at = info.get('at')
            return bool(at) and any((at[0] - bx) ** 2 + (at[1] - by) ** 2 < BIN_RADIUS ** 2 for bx, by in BINS)
        if self.kind == 'saves':
            return not scored and info.get('touch') is not None   # a real save, not a miss
        return scored

    def record(self, slot, hit):
        self.results.append(hit)
        if self.kind == 'saves':
            self.streak = self.streak + 1 if hit else 0
            self.done = self.streak >= 3 or len(self.results) >= self.spec['kicks']
        elif self.kind == 'survival':
            self.done = not hit
        else:
            self.done = len(self.results) >= self.spec['kicks']

    def rows(self):
        label = {'bins': 'bins hit', 'panenka': 'scored', 'saves': 'saves', 'survival': 'in a row'}[self.kind]
        return [dict(slot='p1', name=f'{self.score} {label}', colour=self.kits['p1']['shirt'],
                     results=self.results[-10:], goals=self.score, regulation=min(10, self.spec['kicks']))]

    def summary_line(self):
        return f"{self.spec['label']}: {self.score}"


TUTORIAL = [
    ('aim', "Aim at the top-left corner with W and A. Press SPACE to start the run-up, then SPACE again to "
            "stop the power bar."),
    ('power', 'Stop the power bar in the green zone: not too soft, not too hard.'),
    ('type', 'Press E to change the shot type. Pick the Curler and shoot.'),
    ('disguise', 'Press Q until it says Disguised run-up, then score. The keeper cannot read you.'),
    ('settle', 'After the whistle, wait until the ring says Settled before you start the run-up.'),
    ('dive', 'Now you are in goal. Pick a dive with A or D BEFORE the kick (W for a high dive).'),
    ('save', 'Last one: make a save. Watch the kicker\'s hips: they open towards where he is aiming.'),
]


class TutorialComp(Competition):
    """A coach walks you through the controls, one step at a time."""
    sudden_death_label = False

    def __init__(self):
        super().__init__({'p1': 'YOU', 'p2': 'COACH'}, {'p1': C.KITS['p1'], 'p2': C.KITS['p2']},
                         {'p1': 'human', 'p2': 'ai'})
        self.step = 0
        self.results = []

    @property
    def finished(self):
        return self.step >= len(TUTORIAL)

    @property
    def winner(self):
        return 'p1' if self.finished else None

    def winner_name(self):
        return 'TUTORIAL COMPLETE'

    def instruction(self):
        return None if self.finished else TUTORIAL[self.step][1]

    def next_kicker(self):
        return 'p1'

    def _set_roles(self):
        keeping = not self.finished and TUTORIAL[self.step][0] in ('dive', 'save')
        self.control = {'p1': 'ai', 'p2': 'human'} if keeping else {'p1': 'human', 'p2': 'ai'}
        self.names = {'p1': 'COACH', 'p2': 'YOU'} if keeping else {'p1': 'YOU', 'p2': 'COACH'}

    def check(self, info):
        """info: what happened on the kick. Moves on when the step is done."""
        key = TUTORIAL[self.step][0]
        ok = {
            'aim': info['aim'][0] < -1.6 and info['aim'][1] > 1.3,
            'power': info['sweet'],
            'type': info['kind'] == 'curl',
            'disguise': info['runup'] == 'disguised' and info['scored'],
            'settle': info['composure'] == 'settled',
            'dive': info['keeper_dir'] is not None,
            'save': not info['scored'],
        }[key]
        if ok:
            self.step += 1
            self._set_roles()
        return ok

    def record(self, slot, scored):
        self.results.append(scored)

    def rows(self):
        return [dict(slot='p1', name=f'Step {min(self.step + 1, len(TUTORIAL))} of {len(TUTORIAL)}',
                     colour=self.kits['p1']['shirt'], results=self.results[-10:], goals=self.step,
                     regulation=len(TUTORIAL))]

    def summary_line(self):
        return 'You know the basics. Try the Training ground or a shootout next.'
