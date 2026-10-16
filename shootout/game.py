"""Match flow and input handling. No OpenGL here, so it can run headless."""

import math
import random

from . import ai, config as C, physics, stats
from .keeper import Keeper
from .kick import Kick
from .rules import Shootout, other

# Keys per player: (left, right, up, down, shoot, special)
CONTROLS = {
    'p1': dict(left='a', right='d', up='w', down='s', shoot=' ', special='e'),
    'p2': dict(left='j', right='l', up='i', down='k', shoot='\r', special='o'),
}

KICKER_START = (-1.4, C.SPOT_Z + 2.5)        # right-footer approaching from the left
KICKER_PLANT = (-0.32, C.SPOT_Z + 0.42)
CAMERAS = ['broadcast', 'goal', 'side', 'orbit']
READ_WINDOW = 0.22   # seconds after contact a keeper who has not guessed can still react


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
        self.menu_focus = 0
        # Overlays and camera
        self.paused = False
        self.show_help = False
        self.camera = 'broadcast'
        self.orbit = [0.0, 3.0, 9.0]          # angle (deg), height, distance
        self.shake = 0.0
        self.held = set()
        self.clock = 0.0
        self._accum = 0.0
        self.new_match()

    # ------------------------------------------------------------------ setup
    def name(self, side):
        if side == 'p2' and self.mode == 'pvc':
            return 'CPU'
        return 'PLAYER 1' if side == 'p1' else 'PLAYER 2'

    def is_human(self, side):
        return side == 'p1' or self.mode == 'pvp'

    def new_match(self):
        first = self.rng.choice(('p1', 'p2'))
        self.shootout = Shootout(first=first, kicks_per_side=self.kicks_per_side)
        self.memory = ai.ShotMemory()
        self.log = []                       # one entry per kick for the summary
        self.profile = self.rng.choice(ai.PROFILES)
        self.phase = 'toss'
        self.phase_t = 0.0
        self.message = f'{self.name(first)} won the toss and will kick first'
        self.recording = []
        self.replay = None
        self.ball = physics.Ball()
        self.keeper = Keeper()
        self.kick = None
        self.kicker = first
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
        self._loops(False)

    def keeper_params(self, side):
        if self.is_human(side):
            return dict(C.HUMAN_KEEPER)
        return C.DIFFICULTY[self.difficulty]['keeper']

    def start_kick(self):
        self.kicker = self.shootout.next_kicker()
        keeper_side = other(self.kicker)
        kp = self.keeper_params(keeper_side)
        self.ball = physics.Ball()
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
        self.stakes = self.shootout.stakes(self.kicker)
        self.phase = 'aim'
        self.phase_t = 0.0
        self.ai_plan = None
        if not self.is_human(self.kicker):
            sp = C.DIFFICULTY[self.difficulty]['shooter']
            kind, aim, power = ai.kicker_plan(self.rng, sp, self.profile, self.memory.dives[keeper_side])
            self.ai_plan = dict(kind=kind, aim=aim, power=power)
            self.shot_kind = kind
        self._play('whistle')
        self._loops(True)

    def _loops(self, on):
        if not self.audio:
            return
        self.audio.loop('ambient', on and self.ui == 'playing')
        self.audio.loop('heartbeat', on and self.ui == 'playing' and self.stakes == 'must_score'
                        and self.phase in ('aim', 'runup'))

    def _play(self, name):
        if self.audio:
            self.audio.play(name)

    def keeper_side(self):
        return other(self.kicker)

    def pressure(self):
        p = {'must_score': 0.6, 'to_win': 0.35}.get(self.stakes, 0.0)
        if self.shootout.in_sudden_death():
            p += 0.2
        return min(1.0, p + 0.12 * self.taunts)

    def power_value(self):
        """Power bar position, sweeping 0 -> 1 -> 0."""
        if self.power is not None:
            return self.power
        x = (self.power_clock / C.POWER_PERIOD) % 1.0
        return 1.0 - abs(1.0 - 2.0 * x)

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
        if self.phase in ('runup', 'flight') or (self.phase == 'result' and self.phase_t < 0.9):
            self.recording.append(self.view())

    def _tick(self, dt):
        self.phase_t += dt
        ph = self.phase
        if ph == 'toss':
            if self.phase_t > 2.4:
                self.start_kick()
        elif ph in ('aim', 'runup'):
            self.keeper.update(dt)
            if self.is_human(self.kicker):
                self._move_aim(dt)
            elif ph == 'aim' and self.phase_t > C.DIFFICULTY[self.difficulty]['shooter']['think']:
                self.begin_runup()
            if ph == 'runup':
                self.power_clock += dt
                if self.ai_plan and self.power is None and self.phase_t > 0.55:
                    self.power = self.ai_plan['power']
                if self.phase_t >= C.RUNUP_TIME:
                    self.contact()
        elif ph in ('flight', 'result'):
            self._step_kick(dt)
            if ph == 'result' and self.phase_t > 2.4:
                self.after_result()
        elif ph == 'replay':
            self.replay['t'] += dt * 0.35
            if self.replay['t'] * 60.0 >= len(self.replay['frames']) + 30:
                self.phase = 'ended'
                self.phase_t = 0.0

    def _move_aim(self, dt):
        keys = CONTROLS[self.kicker]
        dx = (keys['right'] in self.held) - (keys['left'] in self.held)
        dy = (keys['up'] in self.held) - (keys['down'] in self.held)
        self.aim[0] = physics.clamp(self.aim[0] + dx * 3.2 * dt, -4.4, 4.4)
        self.aim[1] = physics.clamp(self.aim[1] + dy * 2.2 * dt, 0.12, 3.3)

    def begin_runup(self):
        if self.phase != 'aim':
            return
        self.phase = 'runup'
        self.phase_t = 0.0
        self.power_clock = 0.0

    def contact(self):
        kp = self.keeper_params(self.keeper_side())
        if self.ai_plan:
            aim = self.ai_plan['aim']
            sigma_scale = C.DIFFICULTY[self.difficulty]['shooter']['sigma_scale']
        else:
            aim = tuple(self.aim)
            sigma_scale = 1.0
        power = self.power_value()
        shot = physics.plan_shot(aim, power, self.shot_kind, self.pressure(), self.rng, sigma_scale)
        self.ball.pos = [0.0, C.BALL_RADIUS, C.SPOT_Z]
        physics.launch(self.ball, shot['target'], shot['speed'], shot['curl'])
        self.shot = shot
        if not self.is_human(self.keeper_side()):
            direction, high, delay = ai.keeper_decision(
                self.rng, kp, shot['target'], self.memory.shots[self.kicker])
            self.keeper.commit(direction, high, delay)
        elif self.keeper_dir is not None:
            self.keeper.commit(self.keeper_dir, self.keeper_high, 0.03)
        self.memory.add_shot(self.kicker, shot['target'][0])
        self.kick = Kick(self.ball, self.keeper)
        self.phase = 'flight'
        self.phase_t = 0.0
        self.contact_t = 0.0
        self._play('kick')
        if self.audio:
            self.audio.loop('heartbeat', False)

    def _step_kick(self, dt):
        self.contact_t += dt
        events = self.kick.step(dt)
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
        if self.phase == 'flight' and self.kick.outcome is not None:
            self.on_outcome(*self.kick.outcome)

    def on_outcome(self, scored, label):
        self.result = (scored, label)
        self.phase = 'result'
        self.phase_t = 0.0
        ks = self.keeper_side()
        self.memory.add_dive(ks, self.keeper.dir or 0)
        self.log.append(dict(side=self.kicker, scored=scored, label=label,
                             at=self.kick.crossing, kind=self.shot_kind))
        self.shootout.record(self.kicker, scored)
        if self.kicker == 'p1':
            self.stats['kicks'] += 1
            self.stats['goals'] += int(scored)
        elif ks == 'p1':
            self.stats['faced'] += 1
            self.stats['saves'] += int(not scored and self.kick.keeper_touch is not None)

    def after_result(self):
        if self.shootout.winner:
            self.start_replay()
            if not self.stats_saved:
                self.stats['matches'] += 1
                self.stats['wins'] += int(self.shootout.winner == 'p1')
                stats.save(self.stats, self.stats_path)
                self.stats_saved = True
        else:
            self.start_kick()

    def start_replay(self):
        if not self.recording:
            self.phase = 'ended'
            return
        self.replay = dict(frames=list(self.recording), t=0.0)
        self.phase = 'replay'
        self.phase_t = 0.0
        self._loops(False)

    # --------------------------------------------------------------- the view
    def shooter_view(self):
        """Position, facing and limb swing of the kicker for drawing."""
        sx, sz = KICKER_START
        px, pz = KICKER_PLANT
        yaw = math.degrees(math.atan2(-(px - sx), -(pz - sz)))
        state = dict(pos=(sx, sz), yaw=yaw, run=0.0, kick=0.0, mood=None)
        if self.phase == 'runup':
            r = min(1.0, self.phase_t / C.RUNUP_TIME)
            e = r * r * (3 - 2 * r)
            state['pos'] = (_lerp(sx, px, e), _lerp(sz, pz, e))
            state['run'] = self.phase_t * 9.0
            state['kick'] = -max(0.0, (r - 0.7) / 0.3)          # wind the leg back
        elif self.phase in ('flight', 'result', 'replay', 'ended'):
            state['pos'] = (px, pz)
            t = self.contact_t or 0.0
            state['kick'] = min(1.0, t / 0.18) if t < 0.5 else max(0.0, 1.0 - (t - 0.5) * 3)
            if self.result is not None:
                state['mood'] = 'celebrate' if self.result[0] else 'despair'
        return state

    def view(self):
        """Everything the renderer needs to draw the moving parts."""
        com, lean, arms = self.keeper.pose()
        return dict(
            ball=tuple(self.ball.pos), spin=(tuple(self.ball.spin_axis), self.ball.spin_angle),
            keeper=(com, lean, arms), shooter=self.shooter_view(),
            kicker=self.kicker, keeper_side=self.keeper_side(),
            net=self.net_hit, clock=self.clock,
        )

    def current_view(self):
        if self.phase == 'replay' and self.replay:
            frames = self.replay['frames']
            i = min(len(frames) - 1, int(self.replay['t'] * 60.0))
            return frames[i]
        return self.view()

    def aim_visible(self):
        """Show the reticle only to a human kicker, and not in hidden-aim PvP."""
        if self.phase not in ('aim', 'runup') or not self.is_human(self.kicker):
            return False
        return not (self.mode == 'pvp' and self.hidden_aim)

    def keeper_choice_visible(self):
        return self.is_human(self.keeper_side()) and self.mode == 'pvc'

    # ------------------------------------------------------------------ input
    def key_down(self, key):
        """Returns 'quit' when the game should close."""
        if key == '\x1b':
            return 'quit'
        self.held.add(key)
        if key == 'n' and self.audio:
            self.audio.toggle_mute()
            self._loops(True)
            return None
        if key == 'h':
            self.show_help = not self.show_help
            return None
        if key == 'c':
            self.camera = CAMERAS[(CAMERAS.index(self.camera) + 1) % len(CAMERAS)]
            return None
        if self.ui == 'menu':
            self._menu_key(key)
            return None
        if key == 'p' and self.phase not in ('ended', 'replay'):
            self.paused = not self.paused
            return None
        if key == 'r' and (self.paused or self.phase in ('ended', 'replay')):
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
            return None
        if self.paused:
            return None
        self._match_key(key)
        return None

    def key_up(self, key):
        self.held.discard(key)

    def _match_key(self, key):
        kicker, keeper_side = self.kicker, self.keeper_side()
        if self.phase not in ('aim', 'runup', 'flight'):
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
        if self.is_human(keeper_side):
            k = CONTROLS[keeper_side]
            if key == k['special'] and self.phase == 'aim' and self.taunts < 3:
                self.taunts += 1
                self.keeper.taunt()
                return
            direction = {k['left']: -1, k['right']: 1, k['down']: 0}.get(key)
            if key == k['up']:
                self.keeper_high = not self.keeper_high
            if self.phase in ('aim', 'runup'):
                if direction is not None:
                    self.keeper_dir = direction
            elif self.phase == 'flight' and not self.keeper.committed() and self.contact_t <= READ_WINDOW:
                if direction is not None:
                    self.keeper.commit(direction, self.keeper_high, 0.0)
                elif key == k['up']:
                    self.keeper.commit(0, True, 0.0)

    # ------------------------------------------------------------------- menu
    MENU_ROWS = ('mode', 'difficulty', 'kicks', 'hidden', 'start')

    def _menu_key(self, key):
        rows = self.MENU_ROWS
        if key in ('w', 's'):
            self.menu_focus = (self.menu_focus + (1 if key == 's' else -1)) % len(rows)
        elif key in ('a', 'd'):
            self.menu_change(rows[self.menu_focus], 1 if key == 'd' else -1)
        elif key in ('\r', ' '):
            self.start_match()

    def menu_change(self, row, step):
        if row == 'mode':
            self.mode = 'pvp' if self.mode == 'pvc' else 'pvc'
        elif row == 'difficulty':
            order = ['easy', 'medium', 'hard']
            self.difficulty = order[(order.index(self.difficulty) + step) % 3]
        elif row == 'kicks':
            order = [3, 5, 10]
            self.kicks_per_side = order[(order.index(self.kicks_per_side) + step) % 3]
        elif row == 'hidden':
            self.hidden_aim = not self.hidden_aim

    def start_match(self):
        self.ui = 'playing'
        self.new_match()
        self._loops(True)

    def to_menu(self):
        self.ui = 'menu'
        self.paused = False
        self._loops(False)
