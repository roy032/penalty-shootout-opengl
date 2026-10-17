"""Match flow and input handling. No OpenGL here, so it can run headless."""

import json
import math
import os
import random
import time

from . import ai, config as C, physics, stats
from .controls import CONTROLS
from .keeper import Keeper
from .kick import Kick
from .modes import KingOfTheGoal, Knockout, MatchPenaltyComp, ShootoutComp, TrainingComp
from .rules import other
from .scenarios import SCENARIOS

KICKER_START = (-1.4, C.SPOT_Z + 2.5)        # right-footer approaching from the left
KICKER_PLANT = (-0.32, C.SPOT_Z + 0.42)
WALK_FROM = (-2.5, C.SPOT_Z + 24.0)          # the walk starts out by the halfway-line group
WALK_TIME = 3.6
CAMERAS = ['broadcast', 'goal', 'side', 'keeper', 'orbit']
REPLAY_CAMERAS = ['net', 'ball', 'side']
READ_WINDOW = 0.22   # seconds after contact a keeper who has not guessed can still react
SHUFFLE_STEPS = [0.0, -0.35, 0.35]
CELEBRATIONS = ['knee slide', 'aeroplane', 'shush', 'badge kiss']
DRILL_ZONES = ['random', 'left low', 'left high', 'right low', 'right high', 'centre']
REPLAY_DIR = os.path.join(os.path.expanduser('~'), '.penalty_shootout', 'replays')
CAPTIONS = {
    'whistle': '[Referee blows the whistle]', 'kick': '[Thump of the kick]',
    'post': '[Clang off the woodwork]', 'roar': '[The crowd roars]',
    'gasp': '[The crowd gasps]', 'heartbeat': '[Heartbeat]',
    'jeer': '[Whistles from the away end]',
}

MODES = ['pvc', 'pvp', 'famous', 'match', 'party', 'training']
MODE_LABELS = {'pvc': 'PvC', 'pvp': 'PvP', 'famous': 'Famous', 'match': "90' pen",
               'party': 'Party', 'training': 'Training'}


def _lerp(a, b, t):
    return a + (b - a) * t


class Game:
    def __init__(self, audio=None, rng=None, stats_path=stats.PATH):
        self.rng = rng or random.Random()
        self.audio = audio
        self.stats_path = stats_path
        self.stats = stats.load(stats_path)
        # Menu choices
        self.ui = 'menu'
        self.mode = 'pvc'
        self.difficulty = 'medium'
        self.kicks_per_side = 5
        self.hidden_aim = True
        self.scenario = 0
        self.party_type = 'king'
        self.party_players = 4
        self.role = 'kick'
        self.weather = 'clear'
        self.daytime = 'night'
        self.assist = 'off'
        self.phone = False
        self.phone_info = None             # address and PIN, set by the app when serving
        self.captions_on = False
        self.menu_focus = 0
        self.rebind = None                 # (slot, action index) while rebinding keys
        # Overlays and camera
        self.paused = False
        self.show_help = False
        self.camera = 'broadcast'
        self.replay_cam = 'net'
        self.orbit = [0.0, 3.0, 9.0]          # angle (deg), height, distance
        self.shake = 0.0
        self.held = set()
        self.clock = 0.0
        self.captions = []                 # (text, time shown)
        self.toast = None                  # (text, time shown) for saved files etc.
        self.export_request = False        # the app records the replay to a GIF
        self.playback = None               # kick records when watching a saved replay
        self._accum = 0.0
        self.new_match()

    # ------------------------------------------------------------- settings
    def menu_rows(self):
        rows = ['mode']
        if self.mode in ('pvc', 'famous', 'match', 'training'):
            rows.append('difficulty')
        if self.mode in ('pvc', 'pvp'):
            rows.append('kicks')
        if self.mode in ('pvp', 'party'):
            rows.append('hidden')
        if self.mode == 'famous':
            rows.append('scenario')
        if self.mode == 'party':
            rows += ['party_type', 'players']
        if self.mode in ('match', 'training'):
            rows.append('role')
        rows += ['weather', 'daytime', 'assist', 'captions', 'phone', 'start']
        return rows

    def sweet(self):
        return C.RELAXED['sweet'] if self.assist == 'relaxed' else (C.POWER_SWEET_LOW, C.POWER_SWEET_HIGH)

    def power_period(self):
        return C.RELAXED['power_period'] if self.assist == 'relaxed' else C.POWER_PERIOD

    # ----------------------------------------------------------------- setup
    def name(self, slot):
        return self.comp.name(slot)

    def is_human(self, slot):
        return self.comp.is_human(slot)

    def _make_comp(self):
        human2 = 'human' if self.mode == 'pvp' else 'ai'
        if self.playback is not None:
            data = self.playback_data
            return ShootoutComp(data['names'], {s: {k: tuple(v) for k, v in kit.items()}
                                                for s, kit in data['kits'].items()},
                                {'p1': 'ai', 'p2': 'ai'}, first=data['first'], kicks=data['kicks'],
                                results=data.get('preloaded'))
        if self.mode == 'famous':
            sc = SCENARIOS[self.scenario]
            control = {'p1': 'human', 'p2': 'ai'}
            return ShootoutComp({'p1': sc['teams'][0].upper(), 'p2': sc['teams'][1].upper()},
                                {'p1': sc['kits'][0], 'p2': sc['kits'][1]}, control,
                                first=sc['first'], kicks=5, results=sc['results'])
        if self.mode == 'match':
            return MatchPenaltyComp(self.role)
        if self.mode == 'training':
            return TrainingComp(self.role)
        if self.mode == 'party':
            if self.party_type == 'king':
                return KingOfTheGoal(self.party_players)
            return Knockout(self.party_players, kicks=3)
        names = {'p1': 'PLAYER 1', 'p2': 'PLAYER 2' if self.mode == 'pvp' else 'CPU'}
        first = self.rng.choice(('p1', 'p2'))
        return ShootoutComp(names, dict(C.KITS), {'p1': 'human', 'p2': human2},
                            first=first, kicks=self.kicks_per_side)

    def new_match(self):
        self.comp = self._make_comp()
        self.memory = ai.ShotMemory()
        self.log = []                       # one entry per kick for the summary
        self.records = []                   # exact kick data for replay files
        self.profile = self.rng.choice(ai.PROFILES)
        self.preloaded = {s: len(r['results']) for s, r in zip(('p1', 'p2'), self.comp.rows())} \
            if self.mode == 'famous' else {}
        self.end_fans = 'p1'
        self.toss_winner = self.rng.choice(('p1', 'p2'))
        self.toss_stage = 'end'
        self.wind = 0.0
        if self.weather == 'wind':
            self.wind = self.rng.uniform(1.0, 2.6) * self.rng.choice((-1, 1))
        if self.playback is not None:
            self.wind = self.playback_data.get('wind', 0.0)
            self.weather = self.playback_data.get('weather', 'clear')
        self.spot_wear = 0
        self.nerves = {'p1': 0.0, 'p2': 0.0}
        self.keeper_conf = {'p1': 0, 'p2': 0}
        self.recording = []
        self.replay = None
        self.ball = physics.Ball()
        self.keeper = Keeper()
        self.kick = None
        self.kicker = 'p1'
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
        self.stats_saved = False
        self.paused = False
        self.net_hit = None
        self.disguise = False
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

    def keeper_params(self, slot):
        if self.is_human(slot):
            kp = dict(C.HUMAN_KEEPER)
        else:
            kp = dict(C.DIFFICULTY[self.difficulty]['keeper'])
        if self.comp.specialist[slot]:
            kp['reach'] += C.SPECIALIST['reach']
            kp['dive_time'] += C.SPECIALIST['dive_time']
        if self.comp.emergency[slot]:
            kp['reach'] *= C.EMERGENCY_KEEPER['reach']
            kp['dive_time'] += C.EMERGENCY_KEEPER['dive_time']
            kp['catch_speed'] *= C.EMERGENCY_KEEPER['catch']
        conf = self.keeper_conf[slot]
        kp['reach'] *= 1.0 + 0.03 * conf
        kp['dive_time'] -= 0.005 * conf
        kp['catch_speed'] *= C.WEATHER[self.weather]['catch']
        return kp

    def start_kick(self, retake=False):
        self.kicker = self.comp.next_kicker()
        keeper_side = other(self.kicker)
        self.forced = self.playback.pop(0) if self.playback else None
        kp = self.keeper_params(keeper_side)
        if self.forced and self.forced['keeper'].get('params'):
            kp = dict(self.forced['keeper']['params'])
        self._kp = kp
        self.ball = physics.Ball()
        self.ball.friction = C.WEATHER[self.weather]['friction']
        self.ball.skid = C.WEATHER[self.weather]['skid']
        self.keeper = Keeper(kp['reach'], kp['dive_time'], kp['catch_speed'])
        self.kick = None
        self.aim = [0.0, 1.0]
        self.shot_kind = 'placed'
        self.power = None
        self.power_clock = 0.0
        self.contact_t = None
        self.keeper_dir = None
        self.keeper_high = False
        self.taunts = 0
        self.result = None
        self.recording = []
        self.net_hit = None
        self.disguise = False
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
        self.stakes = self.comp.stakes(self.kicker)
        self.ai_plan = None
        if self.forced is not None:
            self.shot_kind = self.forced['shot']['kind']
        elif not self.is_human(self.kicker):
            self._plan_ai_kick(keeper_side)
        if not self.is_human(keeper_side) and self.playback is None:
            pre = ai.keeper_prekick(self.rng, C.DIFFICULTY[self.difficulty]['keeper'])
            self.keeper.shuffle(pre['shuffle'])
            self.ai_keeper_fake = pre['fake']
            for _ in range(pre['taunts']):
                self._taunt(keeper_side)
        else:
            self.ai_keeper_fake = False
        walk = isinstance(self.comp, (ShootoutComp, MatchPenaltyComp, Knockout)) and not retake
        self.phase = 'walk' if walk else 'aim'
        self.phase_t = 0.0
        if not walk:
            self._play('whistle')
        elif self.playback is None and isinstance(self.comp, (ShootoutComp, Knockout)):
            # The walk towards your own fans gets a roar, towards theirs a wall of whistles
            self._play('roar' if self.end_fans == self.kicker else 'jeer')
        self._loops(True)

    def _plan_ai_kick(self, keeper_side):
        sp = C.DIFFICULTY[self.difficulty]['shooter']
        if isinstance(self.comp, TrainingComp):
            zone = DRILL_ZONES[self.drill_zone]
            if zone != 'random':
                col = {'left': -2.6, 'right': 2.6, 'centre': 0.0}[zone.split()[0]]
                y = 1.8 if zone.endswith('high') else 0.4
                self.ai_plan = dict(kind='placed', aim=(col, y), power=0.7)
                self.shot_kind = 'placed'
                return
        kind, aim, power = ai.kicker_plan(self.rng, sp, self.profile, self.memory.dives[keeper_side])
        self.ai_plan = dict(kind=kind, aim=aim, power=power)
        self.shot_kind = kind
        self.disguise = self.rng.random() < self.profile.get('disguise', 0.3)

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

    def keeper_side(self):
        return other(self.kicker)

    def taker_label(self):
        t = self.comp.taker(self.kicker)
        return f'{self.name(self.kicker)} {t}' if t else self.name(self.kicker)

    def pressure(self):
        p = {'must_score': 0.6, 'to_win': 0.35}.get(self.stakes, 0.0)
        if self.comp.in_sudden_death():
            p += 0.2
        p += 0.12 * self.taunts
        if isinstance(self.comp, ShootoutComp) and self.end_fans != self.kicker:
            p += 0.1                                   # whistled by the away end
        p += self.nerves[self.kicker]
        p += {'rushed': 0.25, 'settled': -0.12, 'dragged': 0.15}.get(self.composure, 0.0)
        return max(-0.2, min(1.2, p))

    def power_value(self):
        """Power bar position, sweeping 0 -> 1 -> 0."""
        if self.power is not None:
            return self.power
        x = (self.power_clock / self.power_period()) % 1.0
        return 1.0 - abs(1.0 - 2.0 * x)

    def runup_time(self):
        return C.RUNUP_TIME + (C.STUTTER_PAUSE if self.shot_kind == 'stutter' else 0.0)

    # ----------------------------------------------------------------- update
    def update(self, dt):
        """Advance the game by dt seconds of real time."""
        self.clock += dt
        self.shake = max(0.0, self.shake - dt)
        if self.ui != 'playing' or self.paused:
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
        elif ph == 'walk':
            self.keeper.update(dt)
            if self.phase_t > WALK_TIME or self.walk_skip:
                self.walk_skip = False
                self.phase = 'aim'
                self.phase_t = 0.0
                self._play('whistle')
        elif ph in ('aim', 'runup'):
            self.keeper.update(dt)
            if ph == 'aim':
                self.aim_time += dt
            if self.is_human(self.kicker) and self.forced is None:
                self._move_aim(dt)
            elif ph == 'aim':
                think = 0.9 if self.forced else C.DIFFICULTY[self.difficulty]['shooter']['think']
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

    def _tick_toss(self):
        t = self.phase_t
        w = self.toss_winner
        if self.toss_stage == 'end':
            if not self.is_human(w) and t > 1.4:
                self._choose_end(w)
            elif t > 5.0:
                self._choose_end(w)
        elif self.toss_stage == 'sub':
            if t > 3.2:
                for slot in ('p1', 'p2'):
                    if not self.is_human(slot):
                        kp = C.DIFFICULTY[self.difficulty]['keeper']
                        if self.rng.random() < kp['specialist']:
                            self.comp.specialist[slot] = True
                first = self.rng.choice(('p1', 'p2'))
                self.comp.rules.first = first
                self.message = f'{self.name(first)} will kick first'
                self.toss_stage = 'first'
                self.phase_t = 0.0
        elif self.toss_stage == 'first' and t > 1.8:
            self.start_kick()

    def _choose_end(self, slot_fans):
        self.end_fans = slot_fans
        self.message = f"Kicking towards the {self.name(slot_fans)} fans"
        self.toss_stage = 'sub'
        self.phase_t = 0.0

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
        if self.forced:
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
            self.ai_plan = dict(self.ai_plan, aim=(-d * 2.4, 0.3))

    def _move_aim(self, dt):
        keys = CONTROLS[self.kicker]
        dx = (keys['right'] in self.held) - (keys['left'] in self.held)
        dy = (keys['up'] in self.held) - (keys['down'] in self.held)
        self.aim[0] = physics.clamp(self.aim[0] + dx * 3.2 * dt, -4.4, 4.4)
        self.aim[1] = physics.clamp(self.aim[1] + dy * 2.2 * dt, 0.12, 3.3)

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
        if self.ai_plan and not self.is_human(self.kicker):
            self.ai_plan = ai.kicker_adjust(
                self.rng, self.ai_plan, self.keeper.x0,
                self.keeper.fake_dir if self.keeper.fake_t is not None else 0,
                self.wind, C.DIFFICULTY[self.difficulty]['shooter']['exploit'])
        self.phase = 'runup'
        self.phase_t = 0.0
        self.power_clock = 0.0
        if self.audio:
            self.audio.loop('heartbeat', False)

    def cue(self):
        """How clearly the run-up gives the side away (1 = open book)."""
        c = 0.3 if self.disguise else 1.0
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
        if self.forced:
            shot = dict(self.forced['shot'])
            shot['target'] = tuple(shot['target'])
            self.slipped = self.forced.get('slipped', False)
            self.double_touch = self.forced.get('double_touch', False)
            self.keeper.x0 = self.forced['keeper']['x0']
            self.aimed = shot['target']
        else:
            if self.ai_plan:
                aim = self.ai_plan['aim']
                sigma_scale = C.DIFFICULTY[self.difficulty]['shooter']['sigma_scale']
            else:
                aim = tuple(self.aim)
                sigma_scale = C.RELAXED['sigma'] if self.assist == 'relaxed' else 1.0
            if self.disguise:
                sigma_scale *= C.DISGUISE_SIGMA
            if self.comp.taker_is_keeper(self.kicker):
                sigma_scale *= 2.0 if self.comp.specialist[self.kicker] else 1.6
            power = self.power_value()
            shot = physics.plan_shot(aim, power, self.shot_kind, self.pressure(), self.rng, sigma_scale,
                                     self.sweet())
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
        elif not self.is_human(ks) and not self.keeper.committed():
            direction, high, delay = ai.keeper_decision(
                self.rng, kp, shot['target'], self.memory.shots[self.kicker],
                cue=self.cue(), shuffle=self.keeper.x0)
            early = self.rng.random() < kp.get('early', 0.0)
            if early:
                # Off the line a fraction early: a gamble the VAR may catch
                delay = 0.0
                self.keeper.dove_early = True
            self.keeper.commit(direction, high, delay)
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

    def _record_kick(self, scored, label):
        commit = self._commit_at_contact
        if commit is None and self.keeper.committed():
            commit = (self.keeper.dir, self.keeper.high, self.keeper_commit_t)
        self.records.append(dict(
            kicker=self.kicker, shot={k: v for k, v in self.shot.items()},
            keeper=dict(x0=self.keeper.x0, commit=commit, early=self.keeper.dove_early, params=self._kp),
            slipped=self.slipped, double_touch=self.double_touch, power=self.power_value(),
            scored=scored, label=label, retake=self.var == 'encroach'))

    def _step_kick(self, dt):
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
        self.log.append(dict(side=self.kicker, scored=scored, label=label,
                             at=self.kick.crossing, kind=self.shot_kind,
                             name=self.name(self.kicker)))
        self._record_kick(scored, label)
        self.comp.record(self.kicker, scored)
        if scored:
            self.nerves[self.kicker] = max(0.0, self.nerves[self.kicker] - 0.06)
            self.keeper_conf[ks] = 0
            self.celebration = self.rng.choice(CELEBRATIONS)
        else:
            self.nerves[self.kicker] = min(0.3, self.nerves[self.kicker] + 0.12)
            self.keeper_conf[ks] = min(3, self.keeper_conf[ks] + 1)
        if self.playback is not None:
            return
        tracked = self.mode in ('pvc', 'pvp', 'famous', 'match')
        if self.mode == 'training' and self.is_human(self.kicker):
            stats.add_zone(self.stats, aimed, scored)
        if tracked and self.kicker == 'p1' and self.is_human('p1'):
            self.stats['kicks'] += 1
            self.stats['goals'] += int(scored)
        elif tracked and ks == 'p1' and self.is_human('p1') or (tracked and self.mode == 'match'
                                                                 and self.role == 'keep'):
            self.stats['faced'] += 1
            self.stats['saves'] += int(not scored and self.kick.keeper_touch is not None)

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
            keeper=dict(x0=self.keeper.x0, commit=self._commit_at_contact, early=True, params=self._kp),
            slipped=self.slipped, double_touch=False, power=self.power_value(),
            scored=False, label='RETAKE', retake=True))

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
        self.rebound = dict(t=0.0, done=False, smother=False)
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
        physics.launch(ball, (far + self.rng.gauss(0, 0.4), 0.45), 17.0)
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

    def after_result(self):
        if self.comp.finished:
            self.start_replay()
            if not self.stats_saved and self.playback is None:
                if self.mode in ('pvc', 'pvp', 'famous'):
                    self.stats['matches'] += 1
                    self.stats['wins'] += int(self.comp.winner == 'p1')
                stats.save(self.stats, self.stats_path)
                self.stats_saved = True
        else:
            if self.mode == 'training':
                stats.save(self.stats, self.stats_path)
            self.start_kick()

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

    # ------------------------------------------------------------ replay files
    def replay_data(self):
        rows = self.comp.rows()
        return dict(
            version=1, names=dict(self.comp.names), kits={s: dict(k) for s, k in self.comp.kits.items()},
            first=getattr(getattr(self.comp, 'rules', None), 'first', 'p1'),
            kicks=getattr(getattr(self.comp, 'rules', None), 'kicks_per_side', 5),
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
        sx, sz = KICKER_START
        px, pz = KICKER_PLANT
        yaw = math.degrees(math.atan2(-(px - sx), -(pz - sz)))
        state = dict(pos=(sx, sz), yaw=yaw, run=0.0, kick=0.0, mood=None, hips=0.0)
        if self.phase == 'walk':
            r = min(1.0, self.phase_t / WALK_TIME)
            wx, wz = WALK_FROM
            state['pos'] = (_lerp(wx, sx, r), _lerp(wz, sz, r))
            state['yaw'] = math.degrees(math.atan2(-(sx - wx), -(sz - wz)))
            state['run'] = self.phase_t * 5.0
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
        elif self.phase in ('flight', 'result', 'replay', 'ended', 'var', 'rebound'):
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
        return dict(
            ball=tuple(self.ball.pos), spin=(tuple(self.ball.spin_axis), self.ball.spin_angle),
            keeper=(com, lean, arms), keeper_mood=keeper_mood, shooter=self.shooter_view(),
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
        if self.phase in ('toss', 'intro'):
            return 'wave'
        if self.phase in ('walk', 'aim', 'runup') and self.end_fans != self.kicker:
            return 'jeer'
        if self.phase == 'result' and self.result:
            fans_happy = self.result[0] == (self.kicker == self.end_fans)
            return 'roar' if fans_happy else 'calm'
        return 'calm'

    def scene_env(self):
        """Settings for the renderer that are not part of a replay frame."""
        ks = self.keeper_side()
        return dict(
            weather=self.weather, daytime=self.daytime, wind=self.wind,
            end_colour=self.comp.kit(self.end_fans)['shirt'], crowd=self.crowd_state(),
            tension=self.stakes is not None or self.comp.in_sudden_death(),
            flares=self.stakes == 'to_win' or self.comp.finished,
            tifo=self.phase in ('toss', 'intro'),
            preview=self.preview_path(),
            first_person=(self.camera == 'keeper' and self.phase != 'replay' and self.is_human(ks)),
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
        shared = self.is_human(self.keeper_side())
        return not (shared and self.hidden_aim)

    def keeper_choice_visible(self):
        return self.is_human(self.keeper_side()) and not self.is_human(self.kicker)

    # ------------------------------------------------------------------ input
    def key_down(self, key):
        """Returns 'quit' when the game should close."""
        if key == '\x1b':
            if self.rebind is not None:
                self.rebind = None
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
        if key == 'c':
            if self.phase == 'replay':
                i = REPLAY_CAMERAS.index(self.replay_cam)
                self.replay_cam = REPLAY_CAMERAS[(i + 1) % len(REPLAY_CAMERAS)]
            else:
                self.camera = CAMERAS[(CAMERAS.index(self.camera) + 1) % len(CAMERAS)]
            return None
        if self.ui == 'menu':
            self._menu_key(key)
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
            if key == 'v' and self.recording:
                self.start_replay()
            elif key == 'g' and self.recording:
                self.export_request = True
                self.start_replay()
            elif key == 'f':
                self.save_replay()
            return None
        if self.paused:
            return None
        if key == 't' and self.mode == 'training':
            self.preview = not self.preview
            return None
        self._match_key(key)
        return None

    def key_up(self, key):
        self.held.discard(key)

    def set_aim(self, slot, x, y):
        """Absolute aim from the phone controller."""
        if self.phase in ('aim', 'runup') and self.kicker == slot and self.is_human(slot):
            self.aim = [physics.clamp(x, -4.4, 4.4), physics.clamp(y, 0.12, 3.3)]

    def _match_key(self, key):
        if self.phase == 'intro':
            if key in (' ', '\r'):
                self.start_kick()
            return
        if self.phase == 'toss':
            self._toss_key(key)
            return
        if self.phase == 'walk':
            if key in (' ', '\r'):
                self.walk_skip = True
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
        if self.is_human(kicker):
            k = CONTROLS[kicker]
            if key == k['shoot']:
                if self.phase == 'aim':
                    self.begin_runup()
                elif self.phase == 'runup' and self.power is None:
                    self.power = self.power_value()
                return
            if key == k['special'] and self.phase == 'aim':
                i = C.SHOT_ORDER.index(self.shot_kind)
                self.shot_kind = C.SHOT_ORDER[(i + 1) % len(C.SHOT_ORDER)]
                if self.shot_kind == 'chip':
                    self.aim[0] = 0.0
                return
            if key == k['extra1'] and self.phase == 'aim':
                self.disguise = not self.disguise
                return
            if key == k['extra2'] and self.mode == 'training' and not self.is_human(keeper_side):
                return
        if self.is_human(keeper_side):
            k = CONTROLS[keeper_side]
            if key == k['special'] and self.phase == 'aim' and self.taunts < 3:
                self._taunt(keeper_side)
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
                if self.contact_t <= window:
                    if direction is not None:
                        self.keeper.commit(direction, self.keeper_high, 0.0)
                    elif key == k['up']:
                        self.keeper.commit(0, True, 0.0)

    def _toss_key(self, key):
        w = self.toss_winner
        if self.toss_stage == 'end' and self.is_human(w):
            k = CONTROLS[w]
            if key in (k['left'], k['right']):
                self._choose_end(w if key == k['left'] else other(w))
        elif self.toss_stage == 'sub':
            for slot in ('p1', 'p2'):
                if self.is_human(slot) and key == CONTROLS[slot]['extra1']:
                    self.comp.specialist[slot] = not self.comp.specialist[slot]

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
        elif row == 'difficulty':
            self.difficulty = cycle(['easy', 'medium', 'hard'], self.difficulty)
        elif row == 'kicks':
            self.kicks_per_side = cycle([3, 5, 10, 0], self.kicks_per_side)
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
        elif row == 'weather':
            self.weather = cycle(C.WEATHER_ORDER, self.weather)
        elif row == 'daytime':
            self.daytime = cycle(['night', 'day'], self.daytime)
        elif row == 'assist':
            self.assist = cycle(['off', 'relaxed'], self.assist)
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
        self.playback = None
        self._loops(False)
