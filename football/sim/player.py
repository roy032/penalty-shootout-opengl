"""A player on the pitch: movement, stamina and the action states the
renderer animates (run, kick, tackle, slide, dive, fall, celebrate)."""

import math

RADIUS = 0.38           # body radius for collisions
CONTROL = 0.85          # how far from the feet the ball can be brought under control
REACH_HEAD = 2.25       # highest ball a jumping player can head


def norm(x, y):
    d = math.hypot(x, y)
    return (x / d, y / d) if d > 1e-9 else (0.0, 0.0)


def ang_diff(a, b):
    d = (a - b + math.pi) % (2 * math.pi) - math.pi
    return d


class Player:
    def __init__(self, fb, team, idx, role, slot):
        self.fb = fb                # roster.Footballer
        self.team = team
        self.idx = idx
        self.role = role            # 'GK', 'DEF', 'MID', 'FWD'
        self.slot = slot            # formation slot (fx, fy): fx -1 own goal .. +1 opponent goal
        self.pos = [0.0, 0.0]
        self.vel = [0.0, 0.0]
        self.z = 0.0                # jump height
        self.vz = 0.0
        self.facing = 0.0
        self.target = None          # where the AI or the stick wants to go
        self.want_speed = 0.0
        self.sprint = False
        self.stamina = 1.0
        self.state = 'run'          # run, kick, tackle, slide, down, getup, dive, hold, throw, jump, celebrate, skill
        self.state_t = 0.0
        self.state_len = 0.0
        self.anim = ''              # sub-type of the state, for the animator
        self.dive_dir = (0.0, 0.0, 0.0)
        self.run_phase = 0.0
        self.touch_cd = 0.0         # can't take a touch for this long after kicking
        self.tackle_cd = 0.0
        self.human = None           # index of the controller steering this player
        self.brain_t = 0.0
        self.plan = None            # AI's current plan
        self.marked = None
        self.sent_off = False
        self.yellow = 0
        self.goals = 0
        self.shots = 0
        self.passes = 0
        self.passes_done = 0
        self.tackles = 0
        self.saves = 0
        self.rating = 6.0
        self.dribble_t = 0.0
        self.knock_t = 0.0
        self.immune = 0.0           # brief protection after a skill move
        self.run_t = 0.0            # bursting forward on a give-and-go
        self.receiving = False

    # --------------------------------------------------------------- helpers
    @property
    def keeper(self):
        return self.role == 'GK'

    @property
    def side(self):
        return self.team.side

    def dir(self):
        return math.cos(self.facing), math.sin(self.facing)

    def dist_to(self, x, y):
        return math.hypot(self.pos[0] - x, self.pos[1] - y)

    def speed(self):
        return math.hypot(self.vel[0], self.vel[1])

    def top_speed(self, with_ball=False):
        base = 5.1 + 2.1 * self.fb.pace
        if self.keeper:
            base = 4.6 + 1.8 * self.fb.pace
        if self.sprint and self.stamina > 0.05:
            base *= 1.3
        if with_ball:
            base *= 0.86 + 0.08 * self.fb.dribbling
        # A tired player loses a yard
        base *= 0.86 + 0.14 * min(1.0, self.stamina * 1.6)
        return base * self.team.speed_scale

    def busy(self):
        """True while an action is playing out and the player can't steer."""
        return self.state in ('kick', 'tackle', 'slide', 'down', 'getup', 'dive', 'throw', 'celebrate') \
            and self.state_t < self.state_len

    def can_touch(self):
        return self.touch_cd <= 0.0 and self.state not in ('down', 'getup', 'celebrate') and not self.sent_off

    def set_state(self, state, length, anim=''):
        self.state = state
        self.state_t = 0.0
        self.state_len = length
        self.anim = anim

    def face_towards(self, x, y):
        self.facing = math.atan2(y - self.pos[1], x - self.pos[0])

    def foot_point(self, ahead=0.45):
        dx, dy = self.dir()
        return self.pos[0] + dx * ahead, self.pos[1] + dy * ahead

    # -------------------------------------------------------------- movement
    def update(self, dt, with_ball, pitch):
        if self.sent_off:
            return
        self.touch_cd = max(0.0, self.touch_cd - dt)
        self.tackle_cd = max(0.0, self.tackle_cd - dt)
        self.immune = max(0.0, self.immune - dt)
        self.state_t += dt
        if self.state != 'run' and self.state_t >= self.state_len:
            if self.state == 'slide':
                self.set_state('getup', 0.45)
            elif self.state == 'down':
                self.set_state('getup', 0.6)
            elif self.state == 'dive':
                self.set_state('getup', 0.55)
            elif self.state != 'hold':
                self.set_state('run', 0.0)

        if self.state == 'slide':
            # Sliding along the grass, slowing down
            f = max(0.0, 1.0 - 2.2 * dt)
            self.vel[0] *= f
            self.vel[1] *= f
        elif self.state == 'dive':
            f = max(0.0, 1.0 - 3.0 * dt)
            self.vel[0] *= f
            self.vel[1] *= f
        elif self.state in ('down', 'getup', 'celebrate', 'throw') or (self.state == 'hold' and self.target is None):
            f = max(0.0, 1.0 - 8.0 * dt)
            self.vel[0] *= f
            self.vel[1] *= f
            if self.state == 'celebrate' and self.target is not None:
                self._steer(dt, with_ball)
        else:
            self._steer(dt, with_ball)

        self.pos[0] += self.vel[0] * dt
        self.pos[1] += self.vel[1] * dt
        # Jumps for headers and keeper leaps
        if self.z > 0 or self.vz > 0:
            self.vz -= 9.81 * dt
            self.z += self.vz * dt
            if self.z <= 0:
                self.z = 0.0
                self.vz = 0.0
        # Players can run a little beyond the lines, but not into the crowd
        m = -2.5 if not pitch.walls else 0.4
        self.pos[0], self.pos[1] = pitch.clamp_inside(self.pos[0], self.pos[1], m)
        if self.keeper:
            # Keepers stay on the field side of their line
            lim = pitch.half_length - 0.25
            self.pos[0] = max(-lim, min(lim, self.pos[0]))
        sp = self.speed()
        self.run_phase = (self.run_phase + dt * (1.6 + sp * 0.62)) % 1.0
        # Stamina: sprinting drains it, jogging and walking win it back
        if self.sprint and sp > 3.0:
            self.stamina = max(0.0, self.stamina - dt * (0.05 - 0.02 * self.fb.physical) * self.team.stamina_drain)
        else:
            self.stamina = min(1.0, self.stamina + dt * (0.012 if sp > 3.0 else 0.03))

    def _steer(self, dt, with_ball):
        if self.target is None:
            tx, ty, want = self.pos[0], self.pos[1], 0.0
        else:
            tx, ty = self.target
            want = self.want_speed
        dx, dy = tx - self.pos[0], ty - self.pos[1]
        d = math.hypot(dx, dy)
        top = self.top_speed(with_ball)
        want = min(want if want > 0 else top, top)
        # Arrive gently instead of overshooting
        if d < 2.5:
            want = min(want, d * 2.2)
        if d < 0.08:
            want = 0.0
        ux, uy = (dx / d, dy / d) if d > 1e-6 else (0.0, 0.0)
        dvx = ux * want - self.vel[0]
        dvy = uy * want - self.vel[1]
        acc = (10.0 + 6.0 * self.fb.pace) * (0.82 if with_ball else 1.0)
        dv = math.hypot(dvx, dvy)
        if dv > acc * dt:
            dvx, dvy = dvx / dv * acc * dt, dvy / dv * acc * dt
        self.vel[0] += dvx
        self.vel[1] += dvy
        sp = self.speed()
        if sp > 0.4:
            want_face = math.atan2(self.vel[1], self.vel[0])
            # Faster players turn wider; on the ball even more so
            rate = (13.0 - sp * 0.7) * (0.8 if with_ball else 1.0)
            da = ang_diff(want_face, self.facing)
            step = max(-rate * dt, min(rate * dt, da))
            self.facing += step
        elif self.plan and self.plan.get('face') is not None:
            fx, fy = self.plan['face']
            want_face = math.atan2(fy - self.pos[1], fx - self.pos[0])
            da = ang_diff(want_face, self.facing)
            self.facing += max(-8 * dt, min(8 * dt, da))
