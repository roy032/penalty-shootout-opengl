"""Match flow and input handling. No OpenGL here, so it can run headless."""

import datetime
import json
import math
import os
import random
import time

from . import achievements, ai, commentary, config as C, physics, report, squad as S, stats, winprob
from .controls import CONTROLS
from .keeper import Keeper
from .kick import Kick
from .modes import (CHALLENGE_ORDER, BINS, TUTORIAL as TUTORIAL_STEPS, CareerComp, ChallengeComp, GhostComp, KingOfTheGoal, Knockout,
                    MatchPenaltyComp, ShootoutComp, TournamentComp, TrainingComp, TutorialComp,
                    career_defaults)
from .rules import other
from .scenarios import SCENARIOS, really_lost

WALK_TIME = 3.6
RITUAL_TIME = 1.2          # placing the ball after the walk, before the whistle
CAMERAS = ['broadcast', 'goal', 'side', 'keeper', 'orbit']
REPLAY_CAMERAS = ['net', 'ball', 'side']
READ_WINDOW = 0.22   # seconds after contact a keeper who has not guessed can still react
SHUFFLE_STEPS = [0.0, -0.35, 0.35]
CELEBRATIONS = ['knee slide', 'aeroplane', 'shush', 'badge kiss']
GAZES = [None, 'stare', 'away']
DRILL_ZONES = ['random', 'left low', 'left high', 'right low', 'right high', 'centre']
LEVELS = ['easy', 'medium', 'hard']
HOME = os.path.join(os.path.expanduser('~'), '.penalty_shootout')
REPLAY_DIR = os.path.join(HOME, 'replays')
DUEL_DIR = os.path.join(HOME, 'duels')
DAILY_FILE = os.path.join(HOME, 'daily.txt')
CAPTIONS = {
    'whistle': '[Referee blows the whistle]', 'kick': '[Thump of the kick]',
    'post': '[Clang off the woodwork]', 'roar': '[The crowd roars]',
    'gasp': '[The crowd gasps]', 'heartbeat': '[Heartbeat]',
    'jeer': '[Whistles from the away end]',
}

MODES = ['pvc', 'pvp', 'manager', 'famous', 'match', 'party', 'training', 'tournament', 'career', 'challenge',
         'daily', 'ghost', 'tutorial']
MODE_LABELS = {'pvc': 'PvC', 'pvp': 'PvP', 'manager': 'Manager', 'famous': 'Famous', 'match': "90' pen",
               'party': 'Party', 'training': 'Training', 'tournament': 'Tournament', 'career': 'Career',
               'challenge': 'Challenge', 'daily': 'Daily', 'ghost': 'Ghost duel', 'tutorial': 'Tutorial',
               'lan': 'LAN'}
SHOOTOUT_STATS = ('pvc', 'pvp', 'famous', 'daily', 'tournament', 'ghost')


def _lerp(a, b, t):
    return a + (b - a) * t


def _blend(a, b, t):
    """Mix two difficulty tables (numbers and tuples of numbers)."""
    if isinstance(a, dict):
        return {k: _blend(a[k], b[k], t) for k in a}
    if isinstance(a, tuple):
        return tuple(_lerp(x, y, t) for x, y in zip(a, b))
    return _lerp(a, b, t)


def kicker_start(runup='angled', left_foot=False):
    """Where the run-up starts: wide for an angled approach, almost straight
    behind the ball for a straight one. Left-footers come from the right."""
    x, back = {'angled': (-1.8, 2.2), 'straight': (-0.45, 3.0)}.get(runup, (-1.4, 2.5))
    return (-x if left_foot else x, C.SPOT_Z + back)


def kicker_plant(left_foot=False):
    return (0.32 if left_foot else -0.32, C.SPOT_Z + 0.42)


def walk_from():
    return (-2.5, C.SPOT_Z + 24.0)          # the walk starts out by the halfway-line group


def demo_ghost():
    """A built-in ghost for when no duel files have been saved yet."""
    rng = random.Random(2026)
    kicks = []
    for aim, kind in (((-2.9, 0.5), 'placed'), ((2.8, 1.9), 'curl'), ((0.1, 1.4), 'chip'),
                      ((3.0, 0.4), 'driven'), ((-2.7, 2.0), 'placed')):
        kicks.append(dict(shot=physics.plan_shot(aim, 0.7, kind, 0.0, rng), power=0.7, runup='angled'))
    return dict(version=1, name='HOUSE GHOST', kit=dict(shirt=(0.8, 0.8, 0.85), shorts=(0.3, 0.3, 0.35),
                                                         keeper=(0.2, 0.2, 0.25)), kicks=kicks, score=None)


class Game:
    def __init__(self, audio=None, rng=None, stats_path=stats.PATH):
        self.rng = rng or random.Random()
        self.crng = random.Random()          # commentary only, so it never changes the match
        self.audio = audio
        self.stats_path = stats_path
        self.stats = stats.load(stats_path)
        # Menu choices
        self.ui = 'menu'
        self.mode = 'pvc'
        self.difficulty = 'medium'
        self.kicks_per_side = 5
        self.order = 'abab'
        self.teams = {'p1': 0, 'p2': 1}
        self.hidden_aim = True
        self.scenario = 0
        self.party_type = 'king'
        self.party_players = 4
        self.role = 'kick'
        self.challenge = 'bins'
        self.ghost_i = 0
        self.duels = []                    # (label, data) for ghost duels
        self.variant = 'stadium'
        self.weather = 'clear'
        self.daytime = 'night'
        self.assist = 'off'
        self.commentary = 'text'
        self.speaker = None
        self.phone = False
        self.phone_info = None             # address and PIN, set by the app when serving
        self.captions_on = False
        self.menu_focus = 0
        self.rebind = None                 # (slot, action index) while rebinding keys
        self.local_slot = None             # set for LAN play: the slot this screen controls
        # Overlays and camera
        self.paused = False
        self.show_help = False
        self.show_achievements = False
        self.show_report = False
        self.photo = False
        self.photo_cam = [30.0, 1.4, 4.5]  # angle (deg), height, distance around the ball
        self.photo_request = False         # the app saves a PNG without the HUD
        self.daily_file = DAILY_FILE
        self.duel_dir = DUEL_DIR
        self.clipboard_request = None      # text the app puts on the clipboard
        self.camera = 'broadcast'
        self.replay_cam = 'net'
        self.orbit = [0.0, 3.0, 9.0]          # angle (deg), height, distance
        self.shake = 0.0
        self.held = set()
        self.clock = 0.0
        self.captions = []                 # (text, time shown)
        self.toast = None                  # (text, time shown) for saved files etc.
        self.comment = None                # (commentary line, time shown)
        self.export_request = False        # the app records the replay to a GIF
        self.playback = None               # kick records when watching a saved replay
        self._accum = 0.0
        self._wp_cache = {}
        self.new_match()

    # ------------------------------------------------------------- settings
    def menu_rows(self):
        m = self.mode
        rows = ['mode']
        if m in ('pvc', 'famous', 'match', 'training', 'manager'):
            rows.append('difficulty')
        if m in ('pvc', 'pvp', 'manager', 'tournament'):
            rows += ['kicks', 'order']
        if m in ('pvc', 'pvp', 'manager'):
            rows += ['team1', 'team2']
        if m in ('pvp', 'party'):
            rows.append('hidden')
        if m == 'famous':
            rows.append('scenario')
        if m == 'party':
            rows += ['party_type', 'players']
        if m in ('match', 'training', 'career'):
            rows.append('role')
        if m == 'challenge':
            rows.append('challenge')
        if m == 'ghost':
            rows.append('ghost')
        if m not in ('famous', 'tutorial'):
            rows.append('variant')
        rows += ['weather', 'daytime', 'assist', 'commentary', 'captions', 'phone', 'start']
        return rows

    def sweet(self):
        return C.RELAXED['sweet'] if self.assist == 'relaxed' else (C.POWER_SWEET_LOW, C.POWER_SWEET_HIGH)

    def power_period(self):
        return C.RELAXED['power_period'] if self.assist == 'relaxed' else C.POWER_PERIOD

    def level(self):
        """The difficulty in force: some modes set their own."""
        lvl = getattr(self.comp, 'level', None)
        if lvl:
            return lvl
        if self.mode == 'daily':
            return 'medium'
        if self.mode == 'challenge':
            return {'panenka': 'hard', 'saves': 'hard'}.get(self.challenge, 'medium')
        if self.mode in ('pvp', 'party', 'ghost', 'tutorial'):
            return 'medium'
        return self.difficulty

    def level_index(self):
        lvl = self.level()
        return 2.0 * self.stats['auto_level'] if lvl == 'auto' else float(LEVELS.index(lvl))

    def diff(self):
        lvl = self.level()
        if lvl != 'auto':
            return C.DIFFICULTY[lvl]
        t = self.stats['auto_level']
        return _blend(C.DIFFICULTY['easy'], C.DIFFICULTY['hard'], t)

    def ai_fingertip(self):
        lvl = self.level()
        if lvl == 'auto':
            return _lerp(C.AI_FINGERTIP['easy'], C.AI_FINGERTIP['hard'], self.stats['auto_level'])
        return C.AI_FINGERTIP[lvl]

    def team(self, slot):
        return C.TEAMS[self.teams[slot] % len(C.TEAMS)]

    # ----------------------------------------------------------------- setup
    def name(self, slot):
        return self.comp.name(slot)

    def is_human(self, slot):
        return self.comp.is_human(slot)

    def controller(self, slot):
        """Whose keys pick the line-up for a side: a human player or a manager."""
        return self.is_human(slot) or self.comp.manager == slot

    def _team_kits(self):
        a, b = self.team('p1'), self.team('p2')
        kits = {s: dict(shirt=t['shirt'], shorts=t['shorts'], keeper=t['keeper']) for s, t in (('p1', a), ('p2', b))}
        if kits['p1']['shirt'] == kits['p2']['shirt']:
            kits['p2'] = dict(kits['p2'], shirt=(0.95, 0.95, 0.95))
        return {'p1': a['name'], 'p2': b['name']}, kits

    def _teams8(self, rng):
        mine = self.team('p1')
        rest = [t for t in C.TEAMS if t is not mine]
        rng.shuffle(rest)
        return [mine] + rest[:7]

    def daily_date(self):
        return datetime.date.today().isoformat()

    def _make_comp(self):
        self.squad_seed = self.rng.randrange(1 << 30)
        srng = random.Random(self.squad_seed)
        if self.playback is not None:
            data = self.playback_data
            return ShootoutComp(data['names'], {s: {k: tuple(v) for k, v in kit.items()}
                                                for s, kit in data['kits'].items()},
                                {'p1': 'ai', 'p2': 'ai'}, first=data['first'], kicks=data['kicks'],
                                results=data.get('preloaded'), order=data.get('order', 'abab'),
                                rng=random.Random(data.get('squad_seed', 0)))
        m = self.mode
        if m == 'famous':
            sc = SCENARIOS[self.scenario]
            control = {'p1': 'human', 'p2': 'ai'}
            return ShootoutComp({'p1': sc['teams'][0].upper(), 'p2': sc['teams'][1].upper()},
                                {'p1': sc['kits'][0], 'p2': sc['kits'][1]}, control,
                                first=sc['first'], kicks=5, results=sc['results'], rng=srng)
        if m == 'match':
            return MatchPenaltyComp(self.role)
        if m == 'career':
            saved = self.stats['career'].get(self.role)
            return CareerComp(dict(saved) if isinstance(saved, dict) else career_defaults(self.role))
        if m == 'training':
            return TrainingComp(self.role)
        if m == 'challenge':
            return ChallengeComp(self.challenge)
        if m == 'tutorial':
            return TutorialComp()
        if m == 'party':
            if self.party_type == 'king':
                return KingOfTheGoal(self.party_players)
            return Knockout(self.party_players, kicks=3)
        if m == 'tournament':
            return TournamentComp(self._teams8(srng), srng, kicks=self.kicks_per_side or 5, order=self.order)
        if m == 'ghost':
            data = self.duels[self.ghost_i % len(self.duels)][1] if self.duels else demo_ghost()
            return GhostComp(data, srng)
        if m == 'daily':
            seed = int(self.daily_date().replace('-', ''))
            drng = random.Random(seed)
            self.rng = random.Random(seed + 1)       # same kicks and dives for everyone today
            opp = drng.choice(C.TEAMS[1:])
            kits = {'p1': dict(C.KITS['p1']), 'p2': dict(shirt=opp['shirt'], shorts=opp['shorts'],
                                                         keeper=opp['keeper'])}
            return ShootoutComp({'p1': 'YOU', 'p2': opp['name']}, kits, {'p1': 'human', 'p2': 'ai'},
                                first='p1', kicks=5, rng=drng)
        names, kits = self._team_kits()
        if m == 'pvc':
            control = {'p1': 'human', 'p2': 'ai'}
        elif m == 'pvp':
            control = {'p1': 'human', 'p2': 'human'}
        else:                                           # manager: you pick, they play
            control = {'p1': 'ai', 'p2': 'ai'}
        comp = ShootoutComp(names, kits, control, first=self.rng.choice(('p1', 'p2')), kicks=self.kicks_per_side,
                            order=self.order, rng=srng)
        if m == 'manager':
            comp.manager = 'p1'
        return comp

    def new_match(self):
        variant = 'stadium' if self.mode in ('famous', 'tutorial') else self.variant
        if self.playback is not None:
            variant = self.playback_data.get('variant', 'stadium')
        C.apply_variant(variant)
        self.comp = self._make_comp()
        self.memory = ai.ShotMemory()
        self.profile = self.rng.choice(ai.PROFILES)
        self.preloaded = {s: len(r['results']) for s, r in zip(('p1', 'p2'), self.comp.rows())} \
            if self.mode == 'famous' else {}
        self.wind = 0.0
        if self.weather == 'wind':
            self.wind = self.rng.uniform(1.0, 2.6) * self.rng.choice((-1, 1))
        if self.playback is not None:
            self.wind = self.playback_data.get('wind', 0.0)
            self.weather = self.playback_data.get('weather', 'clear')
        self.stats_saved = False
        self.unlocked = []                  # things unlocked this match, for the summary
        self.daily_grid = None
        self._reset_tie()

    def _reset_tie(self):
        """Everything that starts afresh for each shootout (tournament ties too)."""
        self.log = []                       # one entry per kick for the summary
        self.records = []                   # exact kick data for replay files
        self.end_fans = 'p1'
        self.toss_winner = self.rng.choice(('p1', 'p2'))
        self.toss_stage = 'end'
        self.lineup = {s: dict(cursor=0, touched=False, ready=False) for s in ('p1', 'p2')}
        orders = self.comp.order if isinstance(self.comp.order, dict) else {}
        self._squad_base = {s: list(o) for s, o in orders.items() if o}
        self.spot_wear = 0
        self.nerves = {'p1': 0.0, 'p2': 0.0}
        self.keeper_conf = {'p1': 0, 'p2': 0}
        self.saves_made = {'p1': 0, 'p2': 0}
        self.goals_in_row = {'p1': 0, 'p2': 0}
        self.recording = []
        self.replay = None
        self.ball = physics.Ball()
        self.keeper = Keeper()
        self.keeper_scale = 1.0
        self.kick = None
        self.kicker = self.comp.next_kicker() if not self.comp.finished else 'p1'
        self.player = None
        self.stakes = None
        self.result = None
        self.aim = [0.0, 1.0]
        self.shot_kind = 'placed'
        self.power = None
        self.power_clock = 0.0
        self.contact_t = None
        self.keeper_dir = None
        self.keeper_high = False
        self.taunts = 0
        self.ai_plan = None
        self.ghost = None
        self.paused = False
        self.photo = False
        self.show_report = False
        self.net_hit = None
        self.runup = 'angled'
        self.gaze = None
        self.shuffle_i = 0
        self.aim_time = 0.0
        self.composure = None
        self.slipped = False
        self.double_touch = False
        self.celebration = None
        self.card = None
        self.var = None
        self.preview = self.mode == 'training'
        self.drill_zone = 0
        self.rebound = None
        self.walk_skip = False
        self.forced = None
        self.retake = False
        self.took_ball = False
        self.ritual_kicker = False
        self.bottle_note = None
        self.ai_stretch = None
        self.stretch_at = None
        self._parry = None
        self._kp = None
        self.message = ''
        self.story = None
        if self.mode == 'famous' and self.playback is None:
            self.story = SCENARIOS[self.scenario]
            self.end_fans = 'p1'
            self.phase = 'intro'
        elif isinstance(self.comp, ShootoutComp) and self.playback is None:
            self.phase = 'toss'
            self.message = f'{self.name(self.toss_winner)} won the toss and chooses the end'
        else:
            self.phase = 'pre'
        self.phase_t = 0.0
        self._loops(False)

    @property
    def disguise(self):
        return self.runup == 'disguised'

    def keeper_params(self, slot):
        if self.is_human(slot):
            kp = dict(C.HUMAN_KEEPER)
        else:
            kp = dict(self.diff()['keeper'])
        style = C.KEEPER_STYLES[self.comp.keeper_style[slot]]
        kp['reach'] += style['reach']
        kp['dive_time'] += style['dive_time']
        if self.comp.specialist[slot]:
            kp['reach'] += C.SPECIALIST['reach']
            kp['dive_time'] += C.SPECIALIST['dive_time']
        if self.comp.emergency[slot]:
            kp['reach'] *= C.EMERGENCY_KEEPER['reach']
            kp['dive_time'] += C.EMERGENCY_KEEPER['dive_time']
            kp['catch_speed'] *= C.EMERGENCY_KEEPER['catch']
        if isinstance(self.comp, CareerComp) and self.comp.role == 'keep' and self.is_human(slot):
            kp['reach'] += 0.06 * self.comp.traits('reach')
            kp['dive_time'] -= 0.015 * self.comp.traits('speed')
            kp['catch_speed'] *= 1.0 + 0.1 * self.comp.traits('catch')
        conf = self.keeper_conf[slot]
        kp['reach'] *= 1.0 + 0.03 * conf
        kp['dive_time'] -= 0.005 * conf
        kp['catch_speed'] *= C.WEATHER[self.weather]['catch']
        return kp

    def ball_friction(self):
        vf = C.VARIANTS[C.VARIANT].get('friction')
        wf = C.WEATHER[self.weather]['friction']
        return wf if vf is None else vf * wf / 1.2

    def start_kick(self, retake=False):
        self.kicker = self.comp.next_kicker()
        keeper_side = other(self.kicker)
        self.player = self.comp.player(self.kicker)
        self.forced = self.playback.pop(0) if self.playback else None
        kp = self.keeper_params(keeper_side)
        if self.forced and self.forced['keeper'].get('params'):
            kp = dict(self.forced['keeper']['params'])
        self._kp = kp
        self.ball = physics.Ball()
        self.ball.friction = self.ball_friction()
        self.ball.skid = C.WEATHER[self.weather]['skid']
        self.keeper = Keeper(kp['reach'], kp['dive_time'], kp['catch_speed'])
        style = self.comp.keeper_style[keeper_side]
        self.keeper_scale = 1.0 if self.comp.emergency[keeper_side] else C.KEEPER_STYLES[style]['scale']
        if getattr(self.comp, 'no_keeper', False):
            self.keeper.x0 = 40.0                  # an empty goal: the keeper is off having a drink
        self.kick = None
        self.aim = [0.0, 1.0]
        self.shot_kind = 'placed'
        if isinstance(self.comp, ChallengeComp) and self.comp.kind == 'panenka':
            self.shot_kind = 'chip'
        self.power = None
        self.power_clock = 0.0
        self.contact_t = None
        self.keeper_dir = None
        self.keeper_high = False
        self.taunts = 0
        self.result = None
        self.recording = []
        self.net_hit = None
        self.runup = 'angled'
        self.gaze = None
        self.shuffle_i = 0
        self.aim_time = 0.0
        self.composure = None
        self.slipped = False
        self.double_touch = False
        self.celebration = None
        self.var = None
        self.rebound = None
        self.stutter_done = False
        self.retake = retake
        self.took_ball = False
        self.ritual_kicker = False
        self.ai_stretch = None
        self.stretch_at = None
        self._parry = None
        self.ghost = None
        self.stakes = self.comp.stakes(self.kicker)
        self.ai_plan = None
        self.bottle_note = None
        if self.forced is not None:
            self.shot_kind = self.forced['shot']['kind']
            self.runup = self.forced.get('runup', 'angled')
        elif self.comp.ghost_shot(self.kicker) is not None:
            g = self.comp.ghost_shot(self.kicker)
            shot = dict(g['shot'], target=tuple(g['shot']['target']))
            self.ghost = shot
            self.shot_kind = shot['kind']
            self.runup = g.get('runup', 'angled')
            self.ai_plan = dict(kind=shot['kind'], aim=shot['target'], power=g.get('power', 0.7))
        elif not self.is_human(self.kicker):
            self._plan_ai_kick(keeper_side)
        if self.player is not None and self.is_human(keeper_side) and not self.is_human(self.kicker):
            self.bottle_note = S.bottle_note(self.player, random.Random(self.player.number * 7919
                                                                         + len(self.player.name)))
        self.ai_take_ball = False
        if not self.is_human(keeper_side) and self.playback is None and not getattr(self.comp, 'no_keeper', False):
            pre = ai.keeper_prekick(self.rng, self.diff()['keeper'])
            self.keeper.shuffle(pre['shuffle'])
            self.keeper.point(pre['point'])
            self.ai_keeper_fake = pre['fake']
            self.ai_take_ball = pre['take_ball'] and not retake
            for _ in range(pre['taunts']):
                self._taunt(keeper_side)
        else:
            self.ai_keeper_fake = False
        walk = isinstance(self.comp, (ShootoutComp, MatchPenaltyComp, Knockout)) and not retake
        self.phase = 'walk' if walk else 'aim'
        self.phase_t = 0.0
        if not walk:
            self._play('whistle')
        else:
            if self.playback is None and isinstance(self.comp, (ShootoutComp, Knockout)):
                # The walk towards your own fans gets a roar, towards theirs a wall of whistles
                self._play('roar' if self.end_fans == self.kicker else 'jeer')
            if self.playback is None:
                cold = bool(self.player and self.player.sub and self.player.kicks == 0)
                self._say(commentary.walk_line(self.crng, self.taker_name(), self.name(self.kicker), self.stakes,
                                               self.comp.in_sudden_death(), self.comp.taker_is_keeper(self.kicker),
                                               cold))
        self._loops(True)

    def _plan_ai_kick(self, keeper_side):
        sp = self.diff()['shooter']
        if isinstance(self.comp, TrainingComp):
            zone = DRILL_ZONES[self.drill_zone]
            if zone != 'random':
                col = {'left': -1, 'right': 1, 'centre': 0}[zone.split()[0]] * (C.GOAL_HALF_WIDTH - 1.06)
                y = min(1.8, C.GOAL_HEIGHT - 0.64) if zone.endswith('high') else 0.4
                self.ai_plan = dict(kind='placed', aim=(col, y), power=0.7)
                self.shot_kind = 'placed'
                return
        kind, aim, power = ai.kicker_plan(self.rng, sp, self.profile, self.memory.dives[keeper_side],
                                          player=self.player, shot_types=C.shot_order())
        self.ai_plan = dict(kind=kind, aim=aim, power=power)
        self.shot_kind = kind
        self.runup = 'disguised' if self.rng.random() < self.profile.get('disguise', 0.3) else \
            self.rng.choice(('angled', 'straight'))
        self.gaze = self.rng.choice(GAZES)

    def _loops(self, on):
        if not self.audio:
            return
        self.audio.loop('ambient', on and self.ui == 'playing')
        self.audio.loop('heartbeat', on and self.ui == 'playing' and self.stakes == 'must_score'
                        and self.phase in ('aim', 'runup'))

    def _play(self, name):
        if self.audio:
            self.audio.play(name)
        if name in CAPTIONS:
            self.captions.append((CAPTIONS[name], self.clock))
            self.captions = self.captions[-3:]

    def _say(self, line):
        if self.commentary == 'off' or not line:
            return
        self.comment = (line, self.clock)
        if self.commentary == 'speech':
            if self.speaker is None:
                self.speaker = commentary.Speaker()
            self.speaker.say(line)

    def _achieve(self, key):
        if self.playback is not None:
            return
        name = achievements.unlock(self.stats, key)
        if name:
            self.unlocked.append(name)
            self.toast = (f'Achievement unlocked: {name}', self.clock)
            stats.save(self.stats, self.stats_path)

    def keeper_side(self):
        return other(self.kicker)

    def taker_name(self):
        t = self.comp.taker(self.kicker)
        return t or self.name(self.kicker)

    def taker_label(self):
        t = self.comp.taker(self.kicker)
        return f'{self.name(self.kicker)} {t}' if t else self.name(self.kicker)

    def antics(self):
        """How hard the keeper's antics land: staring him down invites them."""
        return {'stare': 1.5, 'away': 0.5}.get(self.gaze, 1.0)

    def pressure(self):
        p = {'must_score': 0.6, 'to_win': 0.35}.get(self.stakes, 0.0)
        if self.comp.in_sudden_death():
            p += 0.2
        mult = self.antics()
        p += 0.12 * self.taunts * mult
        if self.keeper.point_dir:
            p += 0.05 * mult
        if self.took_ball:
            p += 0.12 * mult
        p += {'stare': -0.06, 'away': 0.05}.get(self.gaze, 0.0)
        if self.ritual_kicker:
            p -= 0.06
        if isinstance(self.comp, ShootoutComp) and self.end_fans != self.kicker:
            p += 0.1                                   # whistled by the away end
        p += self.nerves[self.kicker]
        p += {'rushed': 0.25, 'settled': -0.12, 'dragged': 0.15}.get(self.composure, 0.0)
        if self.player is not None and hasattr(self.comp, 'slot_index'):
            p += self.player.pressure(self.comp.slot_index(self.kicker))
        if isinstance(self.comp, CareerComp) and self.comp.role == 'kick' and self.is_human(self.kicker):
            p -= 0.08 * self.comp.traits('pressure')
        return max(-0.2, min(1.2, p))

    def power_value(self):
        """Power bar position, sweeping 0 -> 1 -> 0."""
        if self.power is not None:
            return self.power
        x = (self.power_clock / self.power_period()) % 1.0
        return 1.0 - abs(1.0 - 2.0 * x)

    def runup_time(self):
        return C.RUNUP_TIME + (C.STUTTER_PAUSE if self.shot_kind == 'stutter' else 0.0)

    def left_foot(self):
        return bool(self.player and self.player.foot == 'L')

    # ----------------------------------------------------------------- update
    def update(self, dt):
        """Advance the game by dt seconds of real time."""
        self.clock += dt
        self.shake = max(0.0, self.shake - dt)
        if self.ui != 'playing' or self.paused or self.photo:
            self._accum = 0.0
            return
        self._accum += dt
        while self._accum >= C.SIM_DT:
            self._accum -= C.SIM_DT
            self._tick(C.SIM_DT)
        # Record for the replay: the run-up, the flight and a moment after
        if self.phase in ('runup', 'flight', 'rebound') or (self.phase == 'result' and self.phase_t < 0.9):
            self.recording.append(self.view())

    def _tick(self, dt):
        self.phase_t += dt
        ph = self.phase
        if self.card and self.clock - self.card[2] > 2.6:
            self.card = None
        if ph == 'intro':
            if self.phase_t > 9.0:
                self.start_kick()
        elif ph == 'pre':
            if self.phase_t > 0.8:
                self.start_kick()
        elif ph == 'toss':
            self._tick_toss()
        elif ph == 'interlude':
            if self.phase_t > 10.0:
                self._next_tie()
        elif ph == 'walk':
            self.keeper.update(dt)
            if self.phase_t > WALK_TIME or self.walk_skip:
                self.walk_skip = False
                if self.playback is None:
                    self._start_ritual()
                else:
                    self._whistle()
        elif ph == 'ritual':
            self.keeper.update(dt)
            self._tick_ritual()
        elif ph in ('aim', 'runup'):
            self.keeper.update(dt)
            if ph == 'aim':
                self.aim_time += dt
            if self.is_human(self.kicker) and self.forced is None:
                self._move_aim(dt)
            elif ph == 'aim':
                think = 0.9 if (self.forced or self.ghost) else self.diff()['shooter']['think']
                if isinstance(self.comp, TrainingComp):
                    think = 0.8
                if self.phase_t > think:
                    self.begin_runup()
            if ph == 'runup':
                self._tick_runup(dt)
        elif ph in ('flight', 'result'):
            self._step_kick(dt)
            if ph == 'result' and self.phase_t > 2.4:
                self.after_result()
        elif ph == 'rebound':
            self._tick_rebound(dt)
        elif ph == 'var':
            self._step_kick(dt)
            if self.phase_t > 2.6:
                self._resolve_var()
        elif ph == 'replay':
            frames = self.replay['frames']
            i = int(self.replay['t'] * 60.0)
            slow = any(abs(i - e) < 10 for e in self.replay['events'])
            self.replay['t'] += dt * (0.1 if slow else 0.35)
            if self.replay['t'] * 60.0 >= len(frames) + 30:
                self.phase = 'ended'
                self.phase_t = 0.0

    def _whistle(self):
        self.phase = 'aim'
        self.phase_t = 0.0
        self._play('whistle')

    # ------------------------------------------------------------ the ritual
    def _start_ritual(self):
        self.phase = 'ritual'
        self.phase_t = 0.0
        self.ritual_len = RITUAL_TIME
        if not self.is_human(self.kicker) and self.rng.random() < 0.35:
            self._take_time()

    def _tick_ritual(self):
        if self.ai_take_ball and self.phase_t > 0.4:
            self.ai_take_ball = False
            self._take_ball(self.keeper_side())
        if self.phase_t >= self.ritual_len:
            self._whistle()

    def _take_time(self):
        """The kicker places the ball himself and takes a long breath."""
        if not self.ritual_kicker:
            self.ritual_kicker = True
            self.ritual_len = max(self.ritual_len, 2.4)
            self.message = f'{self.taker_name()} takes his time placing the ball...'

    def _take_ball(self, slot):
        """The keeper picks the ball up and hands it over slowly: gamesmanship
        that gets under the kicker's skin, and sometimes a yellow card."""
        if self.took_ball:
            return
        self.took_ball = True
        self.ritual_len += 1.0
        self.message = f'{self.name(slot)} keeper picks the ball up and takes his time giving it back'
        if self.rng.random() < 0.3:
            self._book(slot, 'Delaying the kick')

    # -------------------------------------------------------------- the toss
    def _tick_toss(self):
        t = self.phase_t
        w = self.toss_winner
        if self.toss_stage == 'end':
            if not self.is_human(w) and t > 1.4:
                self._choose_end(w)
            elif t > 5.0:
                self._choose_end(w)
        elif self.toss_stage == 'sub':
            busy = any(self.lineup[s]['touched'] and not self.lineup[s]['ready'] for s in ('p1', 'p2'))
            if (t > 3.2 and not busy) or t > 60.0:
                self._finish_prep()
                first = self.rng.choice(('p1', 'p2'))
                self.comp.rules.first = first
                self.message = f'{self.name(first)} will kick first'
                self.toss_stage = 'first'
                self.phase_t = 0.0
        elif self.toss_stage == 'first' and t > 1.8:
            self.start_kick()

    def _finish_prep(self):
        """The computer managers make their choices."""
        for slot in ('p1', 'p2'):
            if self.controller(slot):
                continue
            kp = self.diff()['keeper']
            if self.rng.random() < kp['specialist']:
                self.comp.specialist[slot] = True
            r = self.rng.random()
            self.comp.keeper_style[slot] = 'tall' if r < 0.25 else 'small' if r < 0.5 else 'standard'
            if self.comp.order.get(slot) and self.rng.random() < 0.25:
                self._set_subs(slot, 1)

    def _choose_end(self, slot_fans):
        self.end_fans = slot_fans
        self.message = f"Kicking towards the {self.name(slot_fans)} fans"
        self.toss_stage = 'sub'
        self.phase_t = 0.0

    def _set_subs(self, slot, count):
        """Bring on fresh legs for the shootout: count of the weakest five
        come off. Cold for their first kick, but not tired."""
        base = self._squad_base.get(slot)
        if not base:
            return
        for p in base:
            p.sub = False
        order = S.cold_subs(random.Random(self.squad_seed + (1 if slot == 'p1' else 2)), list(base), count)
        self.comp.order[slot] = order
        self.comp.subs[slot] = count

    def lineup_for(self, slot):
        return self.comp.order.get(slot) or []

    # ---------------------------------------------------------- the run-up
    def _tick_runup(self, dt):
        self.power_clock += dt
        plan = self.forced or self.ai_plan
        if plan and self.power is None and self.phase_t > 0.55:
            self.power = plan['power'] if 'power' in plan else 0.7
        stutter_at = C.RUNUP_TIME * 0.72
        if self.shot_kind == 'stutter' and not self.stutter_done and self.phase_t >= stutter_at:
            self.stutter_done = True
            self._stutter()
        if (self.ai_keeper_fake and self.keeper.fake_t is None and not self.keeper.committed()
                and self.phase_t > 0.25 and self.phase_t < 0.4):
            self.keeper.fake(self.rng.choice((-1, 1)))
            self.ai_keeper_fake = False
        if self.phase_t >= self.runup_time():
            self.contact()

    def _stutter(self):
        """The hop: a keeper who has already decided gives it away."""
        ks = self.keeper_side()
        if self.forced or self.ghost:
            return
        if self.is_human(ks):
            if self.keeper_dir is not None:
                self.keeper.commit(self.keeper_dir, self.keeper_high, 0.0)
                self.keeper.dove_early = True
        elif self.rng.random() < 0.45:
            d = self.rng.choice((-1, 1))
            self.keeper.commit(d, self.rng.random() < 0.3, 0.0)
            self.keeper.dove_early = True
        if self.ai_plan and self.keeper.committed():
            # Seen him go: roll it the other way
            d = self.keeper.dir or self.rng.choice((-1, 1))
            self.ai_plan = dict(self.ai_plan, aim=(-d * 2.4 * C.GOAL_HALF_WIDTH / 3.66, 0.3))

    def aim_limits(self):
        return C.GOAL_HALF_WIDTH + 0.74, C.GOAL_HEIGHT + 0.86

    def _move_aim(self, dt):
        keys = CONTROLS[self.kicker]
        dx = (keys['right'] in self.held) - (keys['left'] in self.held)
        dy = (keys['up'] in self.held) - (keys['down'] in self.held)
        mx, my = self.aim_limits()
        self.aim[0] = physics.clamp(self.aim[0] + dx * 3.2 * dt, -mx, mx)
        self.aim[1] = physics.clamp(self.aim[1] + dy * 2.2 * dt, 0.12, my)

    def begin_runup(self):
        if self.phase != 'aim':
            return
        if self.is_human(self.kicker) and self.forced is None:
            t = self.aim_time
            if t < C.RUSHED_BEFORE:
                self.composure = 'rushed'
            elif C.SETTLED[0] <= t <= C.SETTLED[1]:
                self.composure = 'settled'
            elif t > C.DRAGGED_AFTER:
                self.composure = 'dragged'
        if self.ai_plan and not self.is_human(self.kicker) and self.ghost is None:
            self.ai_plan = ai.kicker_adjust(
                self.rng, self.ai_plan, self.keeper.x0,
                self.keeper.fake_dir if self.keeper.fake_t is not None else 0,
                self.wind, self.diff()['shooter']['exploit'], point_dir=self.keeper.point_dir,
                rattled=self.antics())
        self.phase = 'runup'
        self.phase_t = 0.0
        self.power_clock = 0.0
        if self.audio:
            self.audio.loop('heartbeat', False)

    def cue(self):
        """How clearly the run-up gives the side away (1 = open book)."""
        c = C.RUNUPS[self.runup]['cue']
        if self.shot_kind == 'stutter':
            c *= 0.6
        return c

    def _slip(self, shot, power):
        w = C.WEATHER[self.weather]
        chance = C.SLIP_BASE + C.SLIP_PER_KICK * self.spot_wear + w['slip'] + 0.01 * self.taunts
        if shot['kind'] in ('driven', 'knuckle') and power > self.sweet()[1]:
            chance += 0.03
        if self.rng.random() >= chance:
            return shot
        self.slipped = True
        self.double_touch = self.rng.random() < C.DOUBLE_TOUCH_SHARE
        tx, ty = shot['target']
        return dict(shot, target=(tx + self.rng.gauss(0.0, 0.9), ty + self.rng.uniform(0.9, 1.9)),
                    speed=shot['speed'] * 0.85, curl=0.0)

    def contact(self):
        ks = self.keeper_side()
        kp = self.keeper_params(ks)
        self.spot_wear += 1
        no_keeper = getattr(self.comp, 'no_keeper', False)
        kk = self.keeper
        if self.forced and self.forced['keeper'].get('idle'):
            # The standing keeper's sway and dummies at the moment of the kick
            kk.clock, kk.wave, kk.fake_t, kk.fake_dir, kk.point_dir = self.forced['keeper']['idle']
        self._idle = (kk.clock, kk.wave, kk.fake_t, kk.fake_dir, kk.point_dir)
        if self.forced:
            shot = dict(self.forced['shot'])
            shot['target'] = tuple(shot['target'])
            self.slipped = self.forced.get('slipped', False)
            self.double_touch = self.forced.get('double_touch', False)
            self.keeper.x0 = self.forced['keeper']['x0']
            self.keeper.parry_mode, self.keeper.parry_side = self.forced['keeper'].get('parry') or (None, 0)
            self.aimed = shot['target']
        elif self.ghost:
            shot = dict(self.ghost)
            self.aimed = shot['target']
        else:
            if self.ai_plan:
                aim = self.ai_plan['aim']
                sigma_scale = self.diff()['shooter']['sigma_scale']
            else:
                aim = tuple(self.aim)
                sigma_scale = C.RELAXED['sigma'] if self.assist == 'relaxed' else 1.0
            sigma_scale *= C.RUNUPS[self.runup]['sigma']
            speed_scale = C.RUNUPS[self.runup]['speed']
            if self.player is not None:
                sigma_scale *= self.player.sigma_scale()
                speed_scale *= self.player.speed_scale()
            if isinstance(self.comp, CareerComp) and self.comp.role == 'kick' and self.is_human(self.kicker):
                sigma_scale *= 0.9 ** self.comp.traits('accuracy')
                speed_scale *= 1.03 ** self.comp.traits('power')
            if self.comp.taker_is_keeper(self.kicker):
                sigma_scale *= 2.0 if self.comp.specialist[self.kicker] else 1.6
            power = self.power_value()
            shot = physics.plan_shot(aim, power, self.shot_kind, self.pressure(), self.rng, sigma_scale,
                                     self.sweet())
            if shot['kind'] != 'chip':
                shot['speed'] *= speed_scale
            shot = self._slip(shot, power)
            self.aimed = aim
        self.ball.pos = [0.0, C.BALL_RADIUS, C.SPOT_Z]
        physics.apply_shot(self.ball, shot, self.wind)
        self.shot = shot
        if shot['kind'] == 'knuckle':
            self.keeper.catch_speed *= 0.7
        if self.forced:
            k = self.forced['keeper']
            if k['commit'] and not self.keeper.committed():
                d, high, start = k['commit']
                self.keeper.commit(d, high, max(0.0, start))
                if start < 0:
                    self.keeper.update(-start)
            self.keeper.dove_early = k.get('early', False)
        elif no_keeper:
            pass
        elif not self.is_human(ks) and not self.keeper.committed():
            direction, high, delay = ai.keeper_decision(
                self.rng, kp, shot['target'], self.memory.shots[self.kicker],
                cue=self.cue(), shuffle=self.keeper.x0, pointed=self.keeper.point_dir)
            early = self.rng.random() < kp.get('early', 0.0)
            if early:
                # Off the line a fraction early: a gamble the VAR may catch
                delay = 0.0
                self.keeper.dove_early = True
            self.keeper.commit(direction, high, delay)
            if direction and self.rng.random() < self.ai_fingertip():
                self.ai_stretch = 'good' if self.rng.random() < 0.75 else 'early'
        elif self.is_human(ks) and self.keeper_dir is not None and not self.keeper.committed():
            self.keeper.commit(self.keeper_dir, self.keeper_high, 0.03)
        self.memory.add_shot(self.kicker, shot['target'][0])
        self.kick = Kick(self.ball, self.keeper)
        self.phase = 'flight'
        self.phase_t = 0.0
        self.contact_t = 0.0
        self._commit_at_contact = (self.keeper.dir, self.keeper.high,
                                   (self.keeper.delay if self.keeper.t is None else -self.keeper.t)) \
            if self.keeper.committed() else None
        self._play('kick')

    def time_to_line(self):
        """Seconds until the ball reaches the keeper's line."""
        vz = self.ball.vel[2]
        if vz >= -0.1:
            return 9.0
        return (self.ball.pos[2] - C.KEEPER_LINE_Z) / -vz

    def _record_kick(self, scored, label):
        commit = self._commit_at_contact
        if commit is None and self.keeper.committed():
            commit = (self.keeper.dir, self.keeper.high, self.keeper_commit_t)
        self.records.append(dict(
            kicker=self.kicker, shot={k: v for k, v in self.shot.items()},
            keeper=dict(x0=self.keeper.x0, commit=commit, early=self.keeper.dove_early, params=self._kp,
                        stretch=self.stretch_at, parry=self._parry, idle=self._idle),
            slipped=self.slipped, double_touch=self.double_touch, power=self.power_value(),
            scored=scored, label=label, retake=self.var == 'encroach', runup=self.runup))

    def _stretch(self, result=None):
        """The fingertip stretch, pressed during the dive."""
        if result is not None:
            if self.keeper.t is not None and self.keeper.stretch is None:
                self.keeper.stretch = result
        else:
            result = self.keeper.press_stretch(self.time_to_line())
        if self.keeper.stretch is not None and self.stretch_at is None:
            self.stretch_at = (self.contact_t, self.keeper.stretch)

    def _step_kick(self, dt):
        ks = self.keeper_side()
        if self.phase == 'flight' and self.keeper.stretch is None:
            if self.forced:
                at = self.forced['keeper'].get('stretch')
                if at and self.contact_t >= at[0] - 1e-9:
                    self._stretch(at[1])
            elif self.ai_stretch and self.keeper.t is not None:
                ttb = self.time_to_line()
                if ttb <= (0.1 if self.ai_stretch == 'good' else 0.35):
                    self._stretch()
        if self.phase == 'flight' and self.forced is None and self.is_human(ks):
            k = CONTROLS[ks]
            side = (k['right'] in self.held) - (k['left'] in self.held)
            if side:
                self.keeper.parry_mode, self.keeper.parry_side = 'wide', side
            elif k['down'] in self.held:
                self.keeper.parry_mode, self.keeper.parry_side = 'front', 0
            else:
                self.keeper.parry_mode, self.keeper.parry_side = None, 0
        self.contact_t += dt
        was_committed = self.keeper.committed()
        events = self.kick.step(dt)
        if not was_committed and self.keeper.committed():
            self.keeper_commit_t = self.contact_t
        for ev in events:
            if ev in ('post', 'bar'):
                self._play('post')
                self.shake = 0.45
            elif ev == 'goal':
                self._play('roar')
                self.shake = max(self.shake, 0.25)
            elif ev == 'miss':
                self._play('gasp')
            elif ev == 'net' and self.net_hit is None:
                self.net_hit = (self.ball.pos[0], self.ball.pos[1], self.clock)
            elif ev == 'parry' and self._parry is None:
                self._parry = (self.keeper.parry_mode, self.keeper.parry_side)
        self._frame_events = events
        if self.phase == 'flight' and self.kick.outcome is not None:
            self.on_outcome(*self.kick.outcome)

    # -------------------------------------------------------------- outcomes
    def on_outcome(self, scored, label):
        # VAR checks: a double touch kills a goal; a keeper off his line
        # early gets a retake if the kick was not scored
        if self.double_touch and self.var is None:
            self.var = 'double_touch'
            self.phase = 'var'
            self.phase_t = 0.0
            self.pending = (False, 'DISALLOWED: DOUBLE TOUCH')
            return
        if self.keeper.dove_early and not scored and self.var is None:
            self.var = 'encroach'
            self.phase = 'var'
            self.phase_t = 0.0
            self.pending = (scored, label)
            return
        if self.slipped and not self.double_touch:
            label = 'SLIPPED! ' + label
        if (isinstance(self.comp, MatchPenaltyComp) and not scored and self.kick.keeper_touch == 'parry'
                and self.rebound is None and self.ball.pos[2] > C.GOAL_LINE_Z
                and abs(self.ball.pos[0]) < 7.0 and self.ball.pos[2] < C.GOAL_LINE_Z + 9.0):
            self._start_rebound()
            return
        self._finish_kick(scored, label)

    def _finish_kick(self, scored, label):
        ks = self.keeper_side()
        self.result = (scored, label)
        self.phase = 'result'
        self.phase_t = 0.0
        self.memory.add_dive(ks, self.keeper.dir or 0)
        aimed = getattr(self, 'aimed', self.shot['target'])
        touch = self.kick.keeper_touch
        hit = self.comp.judge(self.kicker, scored, dict(at=self.kick.crossing, touch=touch))
        human_keeper_dir = self.keeper_dir if self.is_human(ks) else self.keeper.dir
        self.log.append(dict(side=self.kicker, scored=scored, hit=hit, label=label,
                             at=self.kick.crossing, kind=self.shot_kind, name=self.name(self.kicker),
                             taker=self.comp.taker(self.kicker), aim=tuple(aimed), composure=self.composure,
                             runup=self.runup, keeper_dir=human_keeper_dir, keeper_side=ks,
                             stretch=self.keeper.stretch))
        self._record_kick(scored, label)
        self.comp.record(self.kicker, hit)
        if self.player is not None:
            self.player.kicks += 1
        if scored:
            self.nerves[self.kicker] = max(-0.1, self.nerves[self.kicker] - 0.06)
            self.keeper_conf[ks] = 0
            self.celebration = self.rng.choice(CELEBRATIONS)
            self.goals_in_row[self.kicker] += 1
        else:
            self.nerves[self.kicker] = min(0.3, self.nerves[self.kicker] + 0.12)
            self.keeper_conf[ks] = min(3, self.keeper_conf[ks] + 1)
            self.goals_in_row[self.kicker] = 0
            if touch is not None:
                self.saves_made[ks] += 1
        if self.playback is not None:
            return
        self._say(commentary.result_line(self.crng, label, self.shot_kind, self.taker_name(),
                                         self.name(self.kicker), self.saves_made[ks],
                                         self.goals_in_row[self.kicker]))
        self._kick_bookkeeping(scored, label, aimed, ks, touch)

    def _kick_bookkeeping(self, scored, label, aimed, ks, touch):
        """Stats, achievements, adaptive difficulty and the tutorial."""
        kicker = self.kicker
        human_kick = self.is_human(kicker)
        if isinstance(self.comp, TutorialComp):
            lo, hi = self.sweet()
            step = self.comp.step
            ok = self.comp.check(dict(aim=aimed, sweet=lo <= self.power_value() <= hi, kind=self.shot_kind,
                                      runup=self.runup, scored=scored, composure=self.composure,
                                      keeper_dir=self.keeper_dir))
            self.toast = ('Well done!' if ok else 'Not quite: try that again', self.clock)
            if self.comp.finished and step < len(TUTORIAL_STEPS):
                self.stats['tutorial_done'] = True
                stats.save(self.stats, self.stats_path)
            return
        tracked = self.mode in ('pvc', 'pvp', 'famous', 'match', 'daily', 'tournament', 'career')
        if self.mode == 'training' and human_kick:
            stats.add_zone(self.stats, aimed, scored)
        if tracked and kicker == 'p1' and self.is_human('p1'):
            self.stats['kicks'] += 1
            self.stats['goals'] += int(scored)
        elif tracked and ks == 'p1' and self.is_human('p1') or (tracked and self.mode in ('match', 'career')
                                                                 and self.role == 'keep'):
            self.stats['faced'] += 1
            self.stats['saves'] += int(not scored and touch is not None)
        # Each shirt number's record from the spot, for sides you pick
        if self.player is not None and self.controller(kicker):
            key = f'{self.name(kicker)} #{self.player.number}'
            rec = self.stats['takers'].setdefault(key, [0, 0])
            rec[0] += 1
            rec[1] += int(scored)
        if self.level() == 'auto' and human_kick and self.mode in ('pvc', 'match', 'training'):
            lvl = self.stats['auto_level'] + (C.AUTO_UP if scored else -C.AUTO_DOWN)
            self.stats['auto_level'] = round(max(0.0, min(1.0, lvl)), 3)
        if human_kick and scored:
            self._achieve('first_goal')
            if self.shot_kind == 'chip' and abs(aimed[0]) < 1.0:
                self._achieve('panenka')
            if self.shot_kind == 'knuckle':
                self._achieve('knuckle')
            at = self.kick.crossing
            if at and at[1] > C.GOAL_HEIGHT - 0.6 and abs(at[0]) > C.GOAL_HALF_WIDTH - 0.8:
                self._achieve('top_bins')
            if self.comp.taker_is_keeper(kicker):
                self._achieve('keeper_goal')
            if self.slipped:
                self._achieve('slip_goal')
        if self.is_human(ks) and not scored and touch is not None:
            if self.saves_made[ks] >= 3:
                self._achieve('three_saves')
            if self.comp.emergency[ks]:
                self._achieve('outfield_save')
            if self.keeper.stretch == 'good':
                self._achieve('fingertip')

    def _resolve_var(self):
        if self.var == 'double_touch':
            scored, label = self.pending
            self._finish_kick(scored, label)
            return
        # Encroachment: book the keeper and retake
        ks = self.keeper_side()
        self._record_retake()
        self._book(ks, 'Off his line early')
        self.start_kick(retake=True)

    def _record_retake(self):
        self.records.append(dict(
            kicker=self.kicker, shot={k: v for k, v in self.shot.items()},
            keeper=dict(x0=self.keeper.x0, commit=self._commit_at_contact, early=True, params=self._kp,
                        stretch=self.stretch_at, parry=self._parry, idle=self._idle),
            slipped=self.slipped, double_touch=False, power=self.power_value(),
            scored=False, label='RETAKE', retake=True, runup=self.runup))

    def _book(self, slot, reason):
        self.comp.yellows[slot] += 1
        if self.comp.yellows[slot] >= 2 and not self.comp.emergency[slot]:
            self.comp.emergency[slot] = True
            self.card = ('red', f'{self.name(slot)} keeper sent off! An outfield player goes in goal', self.clock)
        else:
            self.card = ('yellow', f'{self.name(slot)} keeper booked: {reason}', self.clock)

    def _taunt(self, slot):
        """Arm-waving and time-wasting: rattles the kicker, but the referee is watching."""
        self.taunts += 1
        self.keeper.taunt()
        risk = {1: 0.0, 2: 0.15, 3: 0.35}.get(self.taunts, 0.5)
        if self.rng.random() < risk:
            self._book(slot, 'Time-wasting')

    def _start_rebound(self):
        # A parry palmed down in front is easier to fall on
        self.rebound = dict(t=0.0, done=False, smother=self.keeper.parry_mode == 'front')
        self.phase = 'rebound'
        self.phase_t = 0.0
        self.message = 'REBOUND!'

    def _tick_rebound(self, dt):
        self._step_kick(dt)
        rb = self.rebound
        rb['t'] += dt
        kicker_ai = not self.is_human(self.kicker)
        if not rb['done'] and kicker_ai and rb['t'] > 0.35 and self.rng.random() < 0.6 * dt * 60 / 20:
            self._follow_up()
        if not rb['done'] and rb['t'] > 1.0:
            self.message = 'CLEARED!'
            self._finish_kick(False, 'SAVED! REBOUND CLEARED')

    def _follow_up(self):
        """Second bite at it: smash the loose ball at goal before the keeper recovers."""
        rb = self.rebound
        rb['done'] = True
        (kx, ky, kz), lean, arms = self.keeper.pose()
        start = list(self.ball.pos)
        start[1] = C.BALL_RADIUS
        ball = physics.Ball(start)
        ball.friction = self.ball.friction
        far = -2.6 if kx > 0 else 2.6
        physics.launch(ball, (far * C.GOAL_HALF_WIDTH / 3.66 + self.rng.gauss(0, 0.4), 0.45), 17.0)
        keeper = Keeper(1.3, 0.62, 18.0)
        keeper.x0 = kx
        recover = 0.12 if rb['smother'] else 0.4 - min(0.25, rb['t'] * 0.2)
        keeper.commit(-1 if far < kx else 1, False, recover)
        self.ball = ball
        self.keeper = keeper
        self.kick = Kick(ball, keeper)
        self.phase = 'flight'
        self.phase_t = 0.0
        self.message = 'FOLLOW-UP!'
        self._play('kick')

    def _celebrate_effect(self):
        """Celebrations spread: a big one lifts your side and needles theirs."""
        if not (self.result and self.result[0] and self.celebration):
            return
        if not isinstance(self.comp, (ShootoutComp, Knockout)) or self.playback is not None:
            return
        me, them = self.kicker, other(self.kicker)
        c = self.celebration
        if c in ('knee slide', 'aeroplane'):
            self.nerves[me] -= 0.08
            self.nerves[them] += 0.06
            note = f'{self.name(me)} are buzzing; {self.name(them)} feel it'
        elif c == 'shush':
            if self.end_fans != me:
                self.nerves[them] -= 0.05          # the away end roars its side on
                self.nerves[me] += 0.05
                note = f'Shushing the {self.name(them)} fans: that has fired them up'
            else:
                note = None
        else:
            self.nerves[me] -= 0.04
            note = 'Kissing the badge: the team-mates love it'
        for s in (me, them):
            self.nerves[s] = max(-0.15, min(0.3, self.nerves[s]))
        if note:
            self.captions.append((note, self.clock))
            self.captions = self.captions[-3:]

    def after_result(self):
        self._celebrate_effect()
        if self.comp.finished:
            self.start_replay()
            if not self.stats_saved and self.playback is None:
                self._match_over()
                stats.save(self.stats, self.stats_path)
                self.stats_saved = True
        elif self.comp.interlude() and self.playback is None:
            self.phase = 'interlude'
            self.phase_t = 0.0
            self._loops(False)
        else:
            if self.mode == 'training':
                stats.save(self.stats, self.stats_path)
            self.start_kick()

    def _next_tie(self):
        self.comp.next_tie()
        self._reset_tie()

    def _match_over(self):
        comp = self.comp
        human_side = 'p2' if self.mode == 'ghost' else 'p1'
        won = comp.winner == human_side
        if self.mode in ('pvc', 'pvp', 'famous', 'daily', 'manager'):
            self.stats['matches'] += 1
            self.stats['wins'] += int(comp.winner == 'p1')
        if isinstance(comp, ShootoutComp) and won and self.is_human(human_side):
            r = comp.rules
            if max(r.kicks('p1'), r.kicks('p2')) > r.kicks_per_side:
                self._achieve('sudden_win')
        if self.mode == 'famous' and won and really_lost(SCENARIOS[self.scenario]):
            self._achieve('rewrite')
        if isinstance(comp, TournamentComp) and comp.champion:
            self._achieve('tournament')
        if isinstance(comp, CareerComp):
            gained = comp.finish()
            self.stats['career'][comp.career['role']] = comp.career
            self.unlocked += gained
            if gained:
                self.toast = ('Unlocked: ' + ', '.join(gained), self.clock)
            if comp.career['gold']:
                self._achieve('career_gold')
        if isinstance(comp, ChallengeComp):
            best = self.stats['challenges'].get(comp.kind, 0)
            if comp.score > best:
                self.stats['challenges'][comp.kind] = comp.score
                self.unlocked.append(f'New best: {comp.score}')
            if comp.kind == 'bins' and comp.score >= 5:
                self._achieve('bins_5')
        if self.mode == 'ghost' and won:
            self._achieve('ghost_win')
        if self.mode == 'daily':
            self.daily_grid = self.make_daily_grid()
            self.stats['daily'][self.daily_date()] = self.daily_grid
            mine = comp.rules.results['p1'][:5]
            if len(mine) == 5 and all(mine):
                self._achieve('daily_perfect')
            try:
                os.makedirs(os.path.dirname(self.daily_file), exist_ok=True)
                with open(self.daily_file, 'a', encoding='utf-8') as f:
                    f.write(self.daily_grid + '\n\n')
            except OSError:
                pass

    def make_daily_grid(self):
        r = self.comp.rules
        row = {True: '\U0001F7E9', False: '\U0001F7E5'}
        return (f'Penalty Shootout daily {self.daily_date()}: {r.goals("p1")}-{r.goals("p2")}\n'
                f'YOU  {"".join(row[x] for x in r.results["p1"])}\n'
                f'CPU  {"".join(row[x] for x in r.results["p2"])}')

    def start_replay(self):
        if not self.recording:
            self.phase = 'ended'
            return
        frames = list(self.recording)
        events = [i for i, f in enumerate(frames) if f.get('ev')]
        self.replay = dict(frames=frames, t=0.0, events=events[:3])
        self.phase = 'replay'
        self.phase_t = 0.0
        self._loops(False)

    # ------------------------------------------------------- analysis helpers
    def human_slots(self):
        return [s for s in ('p1', 'p2') if self.is_human(s)]

    def coach_report(self):
        return report.coach_report(self.log, self.human_slots())

    def _conv(self, slot):
        """Rough chance a kick by slot goes in, for the win-probability bar."""
        idx = self.level_index()
        kicker_ai, keeper_ai = not self.is_human(slot), not self.is_human(other(slot))
        c = 0.75
        if kicker_ai and not keeper_ai:
            c = 0.68 + 0.07 * idx
        elif keeper_ai and not kicker_ai:
            c = 0.82 - 0.07 * idx
        return max(0.4, min(0.95, c - 0.25 * self.nerves[slot]))

    def win_prob(self):
        """Live chance that p1 wins the shootout, or None outside shootouts."""
        rules = getattr(self.comp, 'rules', None) if isinstance(self.comp, ShootoutComp) else \
            (self.comp.tie if isinstance(self.comp, Knockout) else None)
        if rules is None:
            return None
        conv = {s: round(self._conv(s), 3) for s in ('p1', 'p2')}
        key = (rules.first, rules.order, rules.kicks_per_side, tuple(rules.results['p1']),
               tuple(rules.results['p2']), rules.winner, conv['p1'], conv['p2'])
        if key not in self._wp_cache:
            if len(self._wp_cache) > 200:
                self._wp_cache.clear()
            self._wp_cache[key] = winprob.p1_wins(rules, conv)
        return self._wp_cache[key]

    def lower_third(self):
        """The TV caption for the taker on his walk."""
        p = self.player
        if p is None or self.phase not in ('walk', 'ritual'):
            return None
        rec = self.stats['takers'].get(f'{self.name(self.kicker)} #{p.number}')
        return dict(label=p.label, team=self.name(self.kicker), foot='Left foot' if p.foot == 'L' else 'Right foot',
                    composure=p.composure, power=p.power, placement=p.placement, sub=p.sub,
                    record=f'{rec[1]}/{rec[0]} from the spot' if rec else None,
                    keeper=p.keeper)

    # ------------------------------------------------------------ replay files
    def replay_data(self):
        rows = self.comp.rows()
        return dict(
            version=2, names=dict(self.comp.names), kits={s: dict(k) for s, k in self.comp.kits.items()},
            first=getattr(getattr(self.comp, 'rules', None), 'first', 'p1'),
            kicks=getattr(getattr(self.comp, 'rules', None), 'kicks_per_side', 5),
            order=getattr(getattr(self.comp, 'rules', None), 'order', 'abab'),
            squad_seed=self.squad_seed, variant=C.VARIANT,
            preloaded={s: r['results'][:self.preloaded.get(s, 0)] for s, r in zip(('p1', 'p2'), rows)}
            if self.preloaded else None,
            weather=self.weather, wind=self.wind, kick_records=self.records)

    def save_replay(self, directory=REPLAY_DIR):
        if not isinstance(self.comp, ShootoutComp):
            self.toast = ('Replay files are for shootouts', self.clock)
            return None
        try:
            os.makedirs(directory, exist_ok=True)
            path = os.path.join(directory, time.strftime('shootout-%Y%m%d-%H%M%S.json'))
            with open(path, 'w') as f:
                json.dump(self.replay_data(), f)
        except OSError as e:
            self.toast = (f'Could not save replay: {e}', self.clock)
            return None
        self.toast = (f'Replay saved: {path}', self.clock)
        return path

    def load_replay(self, data):
        """Watch a saved shootout: every kick is re-simulated from its record."""
        self.playback_data = data
        self.playback = list(data['kick_records'])
        self.mode = 'pvc'
        self.ui = 'playing'
        self.new_match()

    # ------------------------------------------------------------ ghost duels
    def duel_data(self):
        """Your five kicks, exactly as struck, for a friend to face."""
        if not isinstance(self.comp, ShootoutComp):
            return None
        side = 'p2' if self.mode == 'ghost' else 'p1'
        if not self.is_human(side):
            return None
        kicks = [dict(shot=r['shot'], power=r['power'], runup=r.get('runup', 'angled'))
                 for r in self.records if r['kicker'] == side and not r.get('retake')][:5]
        if not kicks:
            return None
        return dict(version=1, name=self.name(side) if self.mode != 'ghost' else 'CHALLENGER',
                    kit=dict(self.comp.kit(side)), kicks=kicks,
                    score=sum(1 for r in self.records if r['kicker'] == side and r['scored']))

    def save_duel(self, directory=None):
        directory = directory or self.duel_dir
        data = self.duel_data()
        if data is None:
            self.toast = ('Nothing to send: take some kicks in a shootout first', self.clock)
            return None
        try:
            os.makedirs(directory, exist_ok=True)
            path = os.path.join(directory, time.strftime('duel-%Y%m%d-%H%M%S.json'))
            with open(path, 'w') as f:
                json.dump(data, f)
        except OSError as e:
            self.toast = (f'Could not save duel: {e}', self.clock)
            return None
        self.toast = (f'Ghost duel saved: {path}  (send it to a friend)', self.clock)
        return path

    def refresh_duels(self, directory=None):
        directory = directory or self.duel_dir
        self.duels = []
        try:
            names = sorted(f for f in os.listdir(directory) if f.endswith('.json'))
        except OSError:
            names = []
        for n in names[-20:]:
            data = self.read_duel(os.path.join(directory, n))
            if data:
                self.duels.append((n[:-5], data))
        self.ghost_i = min(self.ghost_i, max(0, len(self.duels) - 1))

    @staticmethod
    def read_duel(path):
        try:
            with open(path) as f:
                data = json.load(f)
            kicks = data['kicks']
            ok = isinstance(kicks, list) and kicks and all(
                k['shot']['kind'] in C.SHOT_TYPES and len(k['shot']['target']) == 2 for k in kicks)
            return data if ok and len(data['kit']['shirt']) == 3 else None
        except (OSError, ValueError, KeyError, TypeError):
            return None

    def load_duel(self, data):
        self.duels = [('challenge', data)]
        self.ghost_i = 0
        self.mode = 'ghost'
        self.start_match()

    # ------------------------------------------------------- training helpers
    def preview_path(self):
        """Trajectory of the current aim with no error, for the training preview."""
        if not (self.preview and self.phase in ('aim', 'runup') and self.is_human(self.kicker)):
            return None
        power = self.power_value() if self.phase == 'runup' else 0.7
        shot = physics.plan_shot(tuple(self.aim), power, self.shot_kind, 0.0, random.Random(0), 1.0, self.sweet())
        ball = physics.Ball()
        physics.apply_shot(ball, dict(shot, target=tuple(self.aim) if shot['kind'] != 'skidder'
                                      else shot['target'], knuckle=0.0), self.wind)
        pts = []
        for i in range(300):
            physics.step(ball, 1 / 120)
            if i % 4 == 0:
                pts.append(tuple(ball.pos))
            if ball.pos[2] < C.GOAL_LINE_Z - 0.3:
                break
        spec = C.SHOT_TYPES[self.shot_kind]
        sigma = spec['sigma'] + 0.14 * max(0.0, self.pressure())
        return dict(points=pts, sigma=sigma)

    # --------------------------------------------------------------- the view
    def shooter_view(self):
        """Position, facing and limb swing of the kicker for drawing."""
        lf = self.left_foot()
        sx, sz = kicker_start(self.runup, lf)
        px, pz = kicker_plant(lf)
        yaw = math.degrees(math.atan2(-(px - sx), -(pz - sz)))
        state = dict(pos=(sx, sz), yaw=yaw, run=0.0, kick=0.0, mood=None, hips=0.0, left_foot=lf,
                     gaze=self.gaze if self.phase in ('ritual', 'aim') else None)
        if self.phase == 'walk':
            r = min(1.0, self.phase_t / WALK_TIME)
            wx, wz = walk_from()
            state['pos'] = (_lerp(wx, sx, r), _lerp(wz, sz, r))
            state['yaw'] = math.degrees(math.atan2(-(sx - wx), -(sz - wz)))
            state['run'] = self.phase_t * 5.0
        elif self.phase == 'ritual':
            # Bends to place the ball, then backs off to the start of the run-up
            r = min(1.0, self.phase_t / max(0.1, self.ritual_len))
            bend = math.sin(math.pi * min(1.0, r * 1.6))
            state['pos'] = (_lerp(px, sx, max(0.0, r * 1.6 - 0.6)), _lerp(pz, sz, max(0.0, r * 1.6 - 0.6)))
            state['bend'] = bend
        elif self.phase == 'runup':
            rt = self.runup_time()
            t = self.phase_t
            if self.shot_kind == 'stutter':
                stop = C.RUNUP_TIME * 0.72
                t = t if t < stop else (stop if t < stop + C.STUTTER_PAUSE else t - C.STUTTER_PAUSE)
                rt = C.RUNUP_TIME
            r = min(1.0, t / rt)
            e = r * r * (3 - 2 * r)
            state['pos'] = (_lerp(sx, px, e), _lerp(sz, pz, e))
            state['run'] = t * 9.0
            state['kick'] = -max(0.0, (r - 0.7) / 0.3)          # wind the leg back
            # Body shape: the hips open towards where it is going, unless disguised
            plan = self.forced['shot']['target'] if self.forced else (
                self.ai_plan['aim'] if self.ai_plan else self.aim)
            side = 0 if abs(plan[0]) < 0.8 else (1 if plan[0] > 0 else -1)
            state['hips'] = -side * 22.0 * self.cue() * max(0.0, (r - 0.45) / 0.55)
        elif self.phase in ('flight', 'result', 'replay', 'ended', 'var', 'rebound', 'interlude'):
            state['pos'] = (px, pz)
            t = self.contact_t or 0.0
            state['kick'] = min(1.0, t / 0.18) if t < 0.5 else max(0.0, 1.0 - (t - 0.5) * 3)
            if self.slipped and t < 1.5:
                state['mood'] = 'slip'
            elif self.result is not None:
                state['mood'] = ('celebrate:' + (self.celebration or 'knee slide')) if self.result[0] else 'despair'
                if self.result[0] and self.celebration == 'knee slide':
                    slide = min(1.0, self.phase_t / 0.8)
                    state['pos'] = (px + 1.5 * slide, pz - 2.2 * slide)
        return state

    def view(self):
        """Everything the renderer needs to draw the moving parts."""
        com, lean, arms = self.keeper.pose()
        ks = self.keeper_side()
        keeper_mood = None
        if (self.phase == 'result' and self.phase_t > 0.9 and not self.result[0]
                and self.kick and self.kick.keeper_touch):
            keeper_mood = 'dance'
        kicker_kit = dict(self.comp.kit(self.kicker))
        if self.comp.taker_is_keeper(self.kicker):
            kicker_kit['shirt'] = self.comp.keeper_colour(self.kicker)
        ball = tuple(self.ball.pos)
        if self.phase in ('walk', 'ritual') and not (self.phase == 'ritual' and self.took_ball
                                                     and self.phase_t < self.ritual_len - 0.6):
            ball = (0.0, C.BALL_RADIUS, C.SPOT_Z)
        elif self.phase == 'ritual':
            ball = (com[0] + 0.25, com[1] + 0.2, com[2] + 0.2)     # tucked under the keeper's arm
        return dict(
            ball=ball, spin=(tuple(self.ball.spin_axis), self.ball.spin_angle),
            keeper=(com, lean, arms), keeper_mood=keeper_mood, shooter=self.shooter_view(),
            keeper_point=self.keeper.point_dir, keeper_scale=self.keeper_scale,
            no_keeper=getattr(self.comp, 'no_keeper', False),
            kicker=self.kicker, keeper_side=ks,
            kicker_kit=kicker_kit, keeper_colour=self.comp.keeper_colour(ks),
            team_colours={s: self.comp.kit(s)['shirt'] for s in ('p1', 'p2')},
            team_mood=(None if self.result is None else (self.kicker, self.result[0])),
            net=self.net_hit, clock=self.clock, card=self.card,
            ev=bool(getattr(self, '_frame_events', None)) and self.phase in ('flight', 'result', 'rebound')
            and any(e in ('post', 'bar', 'catch', 'parry', 'goal') for e in self._frame_events),
        )

    def crowd_state(self):
        """What the fans behind the goal are doing."""
        if self.phase in ('toss', 'intro', 'interlude'):
            return 'wave'
        if self.phase in ('walk', 'ritual', 'aim', 'runup') and self.end_fans != self.kicker:
            return 'jeer'
        if self.phase == 'result' and self.result:
            fans_happy = self.result[0] == (self.kicker == self.end_fans)
            return 'roar' if fans_happy else 'calm'
        return 'calm'

    def scene_env(self):
        """Settings for the renderer that are not part of a replay frame."""
        ks = self.keeper_side()
        return dict(
            weather=self.weather, daytime=self.daytime, wind=self.wind, variant=C.VARIANT,
            end_colour=self.comp.kit(self.end_fans)['shirt'], crowd=self.crowd_state(),
            tension=self.stakes is not None or self.comp.in_sudden_death(),
            flares=self.stakes == 'to_win' or self.comp.finished,
            tifo=self.phase in ('toss', 'intro'),
            preview=self.preview_path(),
            bins=BINS if isinstance(self.comp, ChallengeComp) and self.comp.kind == 'bins' else None,
            first_person=(self.camera == 'keeper' and self.phase != 'replay' and self.is_human(ks)
                          and not self.photo),
            kits=self.comp.kits)

    def current_view(self):
        if self.phase == 'replay' and self.replay:
            frames = self.replay['frames']
            i = min(len(frames) - 1, int(self.replay['t'] * 60.0))
            return frames[i]
        return self.view()

    def aim_visible(self):
        """Show the reticle only to a human kicker, and not with hidden aim on
        a shared screen (PvP and party)."""
        if self.phase not in ('aim', 'runup') or not self.is_human(self.kicker) or self.forced:
            return False
        if self.local_slot is not None:
            return self.kicker == self.local_slot
        shared = self.is_human(self.keeper_side())
        return not (shared and self.hidden_aim)

    def keeper_choice_visible(self):
        if self.local_slot is not None:
            return self.keeper_side() == self.local_slot
        return self.is_human(self.keeper_side()) and not self.is_human(self.kicker)

    # ------------------------------------------------------------------ input
    def key_down(self, key):
        """Returns 'quit' when the game should close."""
        if key == '\x1b':
            if self.rebind is not None:
                self.rebind = None
                return None
            if self.photo:
                self.photo = False
                return None
            return 'quit'
        if self.rebind is not None:
            self._rebind_key(key)
            return None
        self.held.add(key)
        if key == 'n' and self.audio:
            self.audio.toggle_mute()
            self._loops(True)
            return None
        if key == 'h':
            self.show_help = not self.show_help
            return None
        if self.ui == 'menu':
            if key == 'c':
                return None
            self._menu_key(key)
            return None
        if key == 'y':
            self.photo = not self.photo
            return None
        if self.photo:
            self._photo_key(key)
            return None
        if key == 'c':
            if self.phase == 'replay':
                i = REPLAY_CAMERAS.index(self.replay_cam)
                self.replay_cam = REPLAY_CAMERAS[(i + 1) % len(REPLAY_CAMERAS)]
            else:
                self.camera = CAMERAS[(CAMERAS.index(self.camera) + 1) % len(CAMERAS)]
            return None
        if key == 'p' and self.phase not in ('ended', 'replay'):
            self.paused = not self.paused
            return None
        if key == 'r' and (self.paused or self.phase in ('ended', 'replay')):
            if self.playback is not None:
                self.load_replay(self.playback_data)
            else:
                self.start_match()
            return None
        if key == 'm' and (self.paused or self.phase in ('ended', 'replay')):
            self.to_menu()
            return None
        if self.phase == 'replay' and key in (' ', '\r'):
            self.phase = 'ended'
            return None
        if self.phase == 'ended':
            self._ended_key(key)
            return None
        if self.paused:
            return None
        if key == 't' and self.mode == 'training':
            self.preview = not self.preview
            return None
        self._match_key(key)
        return None

    def _ended_key(self, key):
        if key == 'v' and self.recording:
            self.start_replay()
        elif key == 'g' and self.recording:
            self.export_request = True
            self.start_replay()
        elif key == 'f':
            self.save_replay()
        elif key == '\t':
            self.show_report = not self.show_report
        elif key == 'b':
            # Share: the daily grid to the clipboard, your kicks as a ghost duel
            if self.daily_grid:
                self.clipboard_request = self.daily_grid
            if isinstance(self.comp, ShootoutComp) and self.save_duel() and self.daily_grid:
                self.toast = ('Result grid copied, and your kicks saved as a ghost duel', self.clock)

    def _photo_key(self, key):
        cam = self.photo_cam
        if key in ('a', 'd'):
            cam[0] += 8.0 if key == 'd' else -8.0
        elif key in ('w', 's'):
            cam[1] = max(0.2, min(12.0, cam[1] + (0.3 if key == 'w' else -0.3)))
        elif key in ('q', 'e'):
            cam[2] = max(1.2, min(30.0, cam[2] + (0.5 if key == 'e' else -0.5)))
        elif key in ('\r', ' '):
            self.photo_request = True

    def key_up(self, key):
        self.held.discard(key)

    def set_aim(self, slot, x, y):
        """Absolute aim from the phone controller."""
        if self.phase in ('aim', 'runup') and self.kicker == slot and self.is_human(slot):
            mx, my = self.aim_limits()
            self.aim = [physics.clamp(x, -mx, mx), physics.clamp(y, 0.12, my)]

    def _match_key(self, key):
        if self.phase == 'intro':
            if key in (' ', '\r'):
                self.start_kick()
            return
        if self.phase == 'toss':
            self._toss_key(key)
            return
        if self.phase == 'interlude':
            if key in (' ', '\r'):
                self._next_tie()
            return
        if self.phase == 'walk':
            if key in (' ', '\r'):
                self.walk_skip = True
            return
        if self.phase == 'ritual':
            self._ritual_key(key)
            return
        if self.phase == 'rebound':
            self._rebound_key(key)
            return
        if self.phase == 'result' and self.result and self.result[0] and self.is_human(self.kicker):
            if key in (CONTROLS[self.kicker]['special'], CONTROLS[self.kicker]['extra2']):
                i = CELEBRATIONS.index(self.celebration) if self.celebration in CELEBRATIONS else 0
                self.celebration = CELEBRATIONS[(i + 1) % len(CELEBRATIONS)]
            return
        kicker, keeper_side = self.kicker, self.keeper_side()
        if self.phase not in ('aim', 'runup', 'flight') or self.forced:
            return
        if self.is_human(kicker) and self.phase != 'flight':
            k = CONTROLS[kicker]
            if key == k['shoot']:
                if self.phase == 'aim':
                    self.begin_runup()
                elif self.phase == 'runup' and self.power is None:
                    self.power = self.power_value()
                return
            if key == k['special'] and self.phase == 'aim':
                if isinstance(self.comp, ChallengeComp) and self.comp.kind == 'panenka':
                    return
                order = C.shot_order()
                i = order.index(self.shot_kind) if self.shot_kind in order else -1
                self.shot_kind = order[(i + 1) % len(order)]
                if self.shot_kind == 'chip':
                    self.aim[0] = 0.0
                return
            if key == k['extra1'] and self.phase == 'aim':
                i = C.RUNUP_ORDER.index(self.runup)
                self.runup = C.RUNUP_ORDER[(i + 1) % len(C.RUNUP_ORDER)]
                return
            if key == k['extra2'] and self.phase == 'aim':
                if self.mode == 'training' and not self.is_human(keeper_side):
                    return
                self.gaze = GAZES[(GAZES.index(self.gaze) + 1) % len(GAZES)]
                return
        if self.is_human(keeper_side) and not getattr(self.comp, 'no_keeper', False):
            k = CONTROLS[keeper_side]
            if key == k['shoot'] and self.phase == 'flight' and self.keeper.committed():
                self._stretch()
                return
            if key == k['special'] and self.phase == 'aim' and self.taunts < 3:
                self._taunt(keeper_side)
                return
            if key == k.get('extra3') and self.phase in ('aim', 'runup') and not self.keeper.committed():
                nxt = {0: -1, -1: 1, 1: 0}[self.keeper.point_dir]
                self.keeper.point(nxt)
                return
            if key == k['extra1'] and self.phase in ('aim', 'runup') and not self.keeper.committed():
                self.shuffle_i = (self.shuffle_i + 1) % len(SHUFFLE_STEPS)
                self.keeper.shuffle(SHUFFLE_STEPS[self.shuffle_i])
                return
            if key == k['extra2'] and self.phase in ('aim', 'runup'):
                if self.mode == 'training' and not self.is_human(kicker):
                    self.drill_zone = (self.drill_zone + 1) % len(DRILL_ZONES)
                    return
                self.keeper.fake(self.keeper_dir or self.rng.choice((-1, 1)))
                if self.phase == 'runup' and self.phase_t > self.runup_time() - 0.25:
                    self.keeper.dove_early = True          # moved off the line
                return
            direction = {k['left']: -1, k['right']: 1, k['down']: 0}.get(key)
            if key == k['up']:
                self.keeper_high = not self.keeper_high
            if self.phase in ('aim', 'runup'):
                if direction is not None:
                    self.keeper_dir = direction
            elif self.phase == 'flight' and not self.keeper.committed():
                window = READ_WINDOW + (0.15 if self.shot_kind in ('stutter', 'chip') else 0.0)
                if isinstance(self.comp, CareerComp) and self.comp.role == 'keep':
                    window += 0.05 * self.comp.traits('read')
                if self.contact_t <= window:
                    if direction is not None:
                        self.keeper.commit(direction, self.keeper_high, 0.0)
                    elif key == k['up']:
                        self.keeper.commit(0, True, 0.0)

    def _ritual_key(self, key):
        if self.is_human(self.kicker) and key == CONTROLS[self.kicker]['shoot']:
            self._take_time()
        ks = self.keeper_side()
        if self.is_human(ks) and key == CONTROLS[ks]['extra2']:
            self._take_ball(ks)

    def _toss_key(self, key):
        w = self.toss_winner
        if self.toss_stage == 'end' and self.is_human(w):
            k = CONTROLS[w]
            if key in (k['left'], k['right']):
                self._choose_end(w if key == k['left'] else other(w))
        elif self.toss_stage == 'sub':
            for slot in ('p1', 'p2'):
                if self.controller(slot):
                    self._prep_key(slot, key)

    def _prep_key(self, slot, key):
        """Before the shootout: keeper sub and style, fresh legs, and the order of takers."""
        k = CONTROLS[slot]
        lu = self.lineup[slot]
        order = self.comp.order.get(slot)
        if key == k['extra1']:
            self.comp.specialist[slot] = not self.comp.specialist[slot]
        elif key == k['special']:
            i = C.KEEPER_STYLE_ORDER.index(self.comp.keeper_style[slot])
            self.comp.keeper_style[slot] = C.KEEPER_STYLE_ORDER[(i + 1) % len(C.KEEPER_STYLE_ORDER)]
        elif key == k['extra2'] and order:
            self._set_subs(slot, (self.comp.subs[slot] + 1) % 3)
        elif order and key in (k['up'], k['down']):
            lu['cursor'] = (lu['cursor'] + (1 if key == k['down'] else -1)) % len(order)
            lu['touched'], lu['ready'] = True, False
        elif order and key in (k['left'], k['right']):
            i = lu['cursor']
            j = i - 1 if key == k['left'] else i + 1
            if 0 <= j < len(order):
                order[i], order[j] = order[j], order[i]
                lu['cursor'] = j
            lu['touched'], lu['ready'] = True, False
        elif key == k['shoot'] and lu['touched']:
            lu['ready'] = True

    def _rebound_key(self, key):
        rb = self.rebound
        if rb['done']:
            return
        if self.is_human(self.kicker) and key == CONTROLS[self.kicker]['shoot']:
            self._follow_up()
        elif self.is_human(self.keeper_side()):
            k = CONTROLS[self.keeper_side()]
            if key in (k['left'], k['right'], k['down'], k['up']):
                rb['smother'] = True

    # ------------------------------------------------------------------- menu
    def _menu_key(self, key):
        if self.show_achievements:
            if key in ('l', '\r', ' '):
                self.show_achievements = False
            return
        rows = self.menu_rows()
        self.menu_focus = min(self.menu_focus, len(rows) - 1)
        if key in ('w', 's'):
            self.menu_focus = (self.menu_focus + (1 if key == 's' else -1)) % len(rows)
        elif key in ('a', 'd'):
            self.menu_change(rows[self.menu_focus], 1 if key == 'd' else -1)
        elif key in ('\r', ' '):
            self.start_match()
        elif key == 'k':
            self.rebind = ('p1', 0)
        elif key == 'l':
            self.show_achievements = True

    def _rebind_key(self, key):
        from . import controls
        slot, i = self.rebind
        action = controls.ACTIONS[i]
        if not controls.bind(slot, action, key):
            self.toast = (f"'{controls.key_name(key)}' is taken or reserved", self.clock)
            return
        i += 1
        if i >= len(controls.ACTIONS):
            if slot == 'p1':
                self.rebind = ('p2', 0)
            else:
                self.rebind = None
                controls.save()
                self.toast = ('Controls saved', self.clock)
        else:
            self.rebind = (slot, i)

    def menu_change(self, row, step):
        def cycle(options, current):
            return options[(options.index(current) + step) % len(options)]

        if row == 'mode':
            self.mode = cycle(MODES, self.mode)
            if self.mode == 'ghost':
                self.refresh_duels()
        elif row == 'difficulty':
            self.difficulty = cycle(LEVELS + ['auto'], self.difficulty)
        elif row == 'kicks':
            self.kicks_per_side = cycle([3, 5, 10, 0], self.kicks_per_side)
        elif row == 'order':
            self.order = cycle(['abab', 'abba'], self.order)
        elif row in ('team1', 'team2'):
            slot = 'p1' if row == 'team1' else 'p2'
            n = len(C.TEAMS)
            i = (self.teams[slot] + step) % n
            if i == self.teams[other(slot)] % n:
                i = (i + step) % n
            self.teams[slot] = i
        elif row == 'hidden':
            self.hidden_aim = not self.hidden_aim
        elif row == 'scenario':
            self.scenario = (self.scenario + step) % len(SCENARIOS)
        elif row == 'party_type':
            self.party_type = cycle(['king', 'knockout'], self.party_type)
        elif row == 'players':
            self.party_players = cycle([3, 4, 5, 6, 7, 8], self.party_players)
        elif row == 'role':
            self.role = cycle(['kick', 'keep'], self.role)
        elif row == 'challenge':
            self.challenge = cycle(CHALLENGE_ORDER, self.challenge)
        elif row == 'ghost':
            self.ghost_i = (self.ghost_i + step) % max(1, len(self.duels))
        elif row == 'variant':
            self.variant = cycle(C.VARIANT_ORDER, self.variant)
        elif row == 'weather':
            self.weather = cycle(C.WEATHER_ORDER, self.weather)
        elif row == 'daytime':
            self.daytime = cycle(['night', 'day'], self.daytime)
        elif row == 'assist':
            self.assist = cycle(['off', 'relaxed'], self.assist)
        elif row == 'commentary':
            self.commentary = cycle(['off', 'text', 'speech'], self.commentary)
        elif row == 'captions':
            self.captions_on = not self.captions_on
        elif row == 'phone':
            self.phone = not self.phone

    def start_match(self):
        self.ui = 'playing'
        self.playback = None
        if self.mode == 'famous':
            sc = SCENARIOS[self.scenario]
            if sc['role'] == 'keep' and self.camera == 'broadcast':
                self.camera = 'keeper'
        self.new_match()
        self._loops(True)

    def to_menu(self):
        self.ui = 'menu'
        self.paused = False
        self.photo = False
        self.playback = None
        self._loops(False)
