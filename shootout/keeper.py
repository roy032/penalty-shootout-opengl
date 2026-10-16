"""Goalkeeper: dive kinematics and the body shape used for saves.

The keeper commits to a dive (left, centre or right; low or high). Once the
dive starts the body follows a fixed path, so a wrong guess cannot be undone,
which is what makes penalties a guessing game in real football.
"""

import math

from . import config as C
from .physics import sphere_capsule


def _ease_out(p):
    return 1.0 - (1.0 - p) * (1.0 - p)


class Keeper:
    def __init__(self, reach=1.75, dive_time=0.52, catch_speed=21.0):
        self.reach = reach
        self.dive_time = dive_time
        self.catch_speed = catch_speed
        self.x0 = 0.0
        self.dir = None          # -1 left, 0 centre, 1 right; None until a dive starts
        self.high = False
        self.delay = 0.0         # time left before the committed dive starts
        self.t = None            # time since dive start
        self.clock = 0.0         # for idle animation
        self.wave = 0.0          # time left on a pre-kick wave of the arms
        self.touch_cooldown = 0.0
        self.holding = False
        self.adjusted = False
        self.y_end = None        # where the dive finishes: height of the body ...
        self.lean_end = None     # ... and how flat it is

    # --- control ---
    def commit(self, direction, high, delay=0.0):
        if self.dir is not None:
            return False
        self.dir = direction
        self.high = high
        self.delay = max(0.0, delay)
        self.y_end, self.lean_end = (1.2, 50.0) if high else (0.32, 80.0)
        return True

    def committed(self):
        return self.dir is not None

    def taunt(self):
        self.wave = 0.9

    def update(self, dt):
        self.clock += dt
        self.wave = max(0.0, self.wave - dt)
        self.touch_cooldown = max(0.0, self.touch_cooldown - dt)
        if self.dir is None:
            return
        if self.delay > 0:
            self.delay -= dt
            return
        self.t = (self.t or 0.0) + dt

    def adjust(self, ball_x, ball_y):
        """Mid-dive correction: a keeper who guessed the right side can shorten
        the dive and shape it to the ball's height, within limits. A wrong
        guess stays wrong."""
        if self.adjusted or not self.dir:
            return
        self.adjusted = True
        offset = (ball_x - self.x0) * self.dir
        if offset <= 0:
            return
        # Aim to meet the ball with the chest and arms, not the fingertips
        wanted = offset - 0.55
        self.reach = max(0.45 * self.reach, min(self.reach, wanted))
        if self.high:
            self.y_end = max(0.85, min(1.25, ball_y - 0.6))
            self.lean_end = 50.0 + (1.25 - self.y_end) / 0.4 * 15.0
        else:
            self.y_end = max(0.32, min(0.8, ball_y - 0.2))
            self.lean_end = 80.0 - (self.y_end - 0.32) / 0.48 * 20.0

    # --- body shape ---
    def pose(self):
        """com (x, y, z), lean in degrees (positive leans to +x), arms style."""
        z = C.KEEPER_LINE_Z
        if self.t is None:
            sway = 0.06 * math.sin(self.clock * 3.2)
            bounce = 0.03 * abs(math.sin(self.clock * 6.4))
            arms = 'wave' if self.wave > 0 else 'ready'
            return (self.x0 + sway, 0.95 + bounce, z), 0.0, arms
        p = min(1.0, self.t / self.dive_time)
        e = _ease_out(p)
        fall = max(0.0, self.t - self.dive_time) / 0.45
        fall = min(1.0, fall)
        if self.dir == 0:
            if self.high:
                jump = math.sin(math.pi * min(1.0, self.t / 0.62))
                return (self.x0, 0.95 + 0.5 * jump, z), 0.0, 'up'
            return (self.x0, 0.95 - 0.12 * e, z), 0.0, 'block'
        x = self.x0 + self.dir * self.reach * e
        y = 0.95 + (self.y_end - 0.95) * e
        lean = self.lean_end * e
        y = y + (0.3 - y) * fall
        lean = lean + (90.0 - lean) * fall
        return (x, y, z), self.dir * lean, 'dive'

    def capsules(self):
        """List of (a, b, radius) capsules covering the body and arms."""
        (x, y, z), lean, arms = self.pose()
        rad = math.radians(lean)
        u = (math.sin(rad), math.cos(rad), 0.0)

        def along(k):
            return [x + u[0] * k, y + u[1] * k, z]

        caps = []
        if arms == 'dive':
            caps.append((along(-0.95), along(1.4), 0.2))      # feet to fingertips
            caps.append((along(-0.3), along(0.6), 0.26))      # torso
            # The lower arm sweeps below the body line: along the grass on a
            # low dive, across the middle of the goal on a high one
            extra = math.radians((30.0 if not self.high else 40.0) * (1 if lean >= 0 else -1))
            a = along(0.45)
            u2 = (math.sin(rad + extra), math.cos(rad + extra))
            caps.append((a, [a[0] + u2[0] * 0.95, a[1] + u2[1] * 0.95, z], 0.12))
            return caps
        caps.append(([x, max(0.05, y - 0.95), z], [x, y + 0.8, z], 0.23))
        if arms == 'up':
            for s in (-1, 1):
                caps.append(([x + 0.18 * s, y + 0.55, z], [x + 0.3 * s, y + 1.35, z], 0.12))
        elif arms == 'block':
            for s in (-1, 1):
                caps.append(([x + 0.2 * s, y + 0.45, z], [x + 0.95 * s, y - 0.1, z], 0.12))
                caps.append(([x + 0.15 * s, y - 0.4, z], [x + 0.55 * s, 0.08, z], 0.12))
        else:
            for s in (-1, 1):
                caps.append(([x + 0.2 * s, y + 0.5, z], [x + 0.8 * s, y + 0.15, z], 0.12))
        return caps

    def hands(self):
        (x, y, z), lean, arms = self.pose()
        rad = math.radians(lean)
        if arms == 'dive':
            k = 1.15
        elif arms == 'up':
            k = 1.2
        else:
            k = 0.45
        return [x + math.sin(rad) * k, y + math.cos(rad) * k, z + 0.25]

    def try_save(self, ball):
        """Check contact with the ball. Returns 'catch', 'parry' or None."""
        if self.touch_cooldown > 0 or ball.held:
            return None
        for i, (a, b, r) in enumerate(self.capsules()):
            hit = sphere_capsule(ball.pos, C.BALL_RADIUS, a, b, r)
            if not hit:
                continue
            n, depth, t = hit
            for k in range(3):
                ball.pos[k] += n[k] * depth
            speed = ball.speed()
            core = (i == 1) or (i == 0 and 0.2 < t < 0.85)
            if core and speed < self.catch_speed:
                ball.held = True
                ball.vel = [0.0, 0.0, 0.0]
                self.holding = True
                return 'catch'
            vn = ball.vel[0] * n[0] + ball.vel[1] * n[1] + ball.vel[2] * n[2]
            if vn < 0:
                for k in range(3):
                    ball.vel[k] -= 1.3 * vn * n[k]
                    ball.vel[k] *= 0.7
            ball.side_accel = 0.0
            self.touch_cooldown = 0.12
            return 'parry'
        return None
