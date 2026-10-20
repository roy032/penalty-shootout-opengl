"""Ball flight: gravity, air drag, spin (curl and dip), bounces, rolling,
the goal frame, nets and cage walls."""

import math

RADIUS = 0.11
GRAVITY = 9.81
DRAG = 0.012            # quadratic air drag per metre
MAGNUS = 0.0026         # side force per (rad/s * m/s)
SPIN_DECAY = 0.45       # per second
ROLL_DECEL = 1.3        # rolling resistance on dry grass, m/s^2
ROLL_DAMP = 0.22        # extra speed-proportional loss when rolling
BOUNCE = 0.56           # vertical restitution off the turf
POST_BOUNCE = 0.65
WALL_BOUNCE = 0.62


def roll_distance(v0, v1=0.0):
    """Approximate distance a rolling ball covers while slowing from v0 to v1."""
    if v0 <= v1:
        return 0.0
    # Integrate dv/ds = -(ROLL_DECEL + ROLL_DAMP v) / v numerically in closed form
    a, b = ROLL_DECEL, ROLL_DAMP
    def s(v):
        return v / b - a / (b * b) * math.log(a + b * v)
    return s(v0) - s(v1)


def roll_speed_for(dist, arrive=2.0):
    """Initial ground speed so a pass covers dist and still arrives at `arrive` m/s."""
    lo, hi = arrive, 45.0
    for _ in range(30):
        mid = 0.5 * (lo + hi)
        if roll_distance(mid, arrive) < dist:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def roll_time(v0, dist):
    """Time for a ball rolling at v0 to cover dist (None if it stops short)."""
    if dist <= 0:
        return 0.0
    v, s, t, dt = v0, 0.0, 0.0, 1 / 60.0
    while s < dist:
        if v <= 0.05:
            return None
        v = max(0.0, v - (ROLL_DECEL + ROLL_DAMP * v) * dt)
        s += v * dt
        t += dt
        if t > 20:
            return None
    return t


class Ball:
    def __init__(self, pitch):
        self.pitch = pitch
        self.pos = [0.0, 0.0, RADIUS]
        self.vel = [0.0, 0.0, 0.0]
        self.spin = [0.0, 0.0, 0.0]     # angular velocity, rad/s (z = curl, horizontal = top/back spin)
        self.roll_axis = (1.0, 0.0, 0.0)
        self.roll_angle = 0.0           # degrees, for drawing
        self.owner = None               # player dribbling it
        self.holder = None              # keeper holding it in his hands
        self.last_touch = None
        self.in_net = 0                 # side of the goal it is in, 0 if not
        self.friction = 1.0             # >1 on heavy or wet pitches
        self.knuckle = 0.0
        self.flight_t = 0.0

    # ----------------------------------------------------------------- state
    def place(self, x, y, z=RADIUS):
        self.pos = [x, y, z]
        self.vel = [0.0, 0.0, 0.0]
        self.spin = [0.0, 0.0, 0.0]
        self.owner = None
        self.holder = None
        self.in_net = 0
        self.knuckle = 0.0

    def speed(self):
        v = self.vel
        return math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])

    def ground_speed(self):
        return math.hypot(self.vel[0], self.vel[1])

    def airborne(self):
        return self.pos[2] > RADIUS + 0.05 or self.vel[2] > 0.5

    def kick(self, vx, vy, vz, spin=(0.0, 0.0, 0.0), knuckle=0.0):
        self.owner = None
        self.holder = None
        self.vel = [vx, vy, vz]
        self.spin = list(spin)
        self.knuckle = knuckle
        self.flight_t = 0.0

    # ------------------------------------------------------------- prediction
    def predict(self, t, dt=1 / 30.0):
        """Where the ball will be after t seconds, ignoring players and the frame."""
        g = Ball(self.pitch)
        g.pos = list(self.pos)
        g.vel = list(self.vel)
        g.spin = list(self.spin)
        g.friction = self.friction
        n = max(1, int(t / dt))
        for _ in range(n):
            g._integrate(t / n)
        return g.pos

    def path(self, t, dt=1 / 20.0):
        """Positions every dt for t seconds (cheap trajectory for the AI and keepers)."""
        g = Ball(self.pitch)
        g.pos = list(self.pos)
        g.vel = list(self.vel)
        g.spin = list(self.spin)
        g.friction = self.friction
        out = []
        n = max(1, int(t / dt))
        for _ in range(n):
            g._integrate(dt)
            out.append(tuple(g.pos))
        return out

    # ---------------------------------------------------------------- physics
    def _integrate(self, dt):
        p, v, w = self.pos, self.vel, self.spin
        sp = math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])
        air = p[2] > RADIUS + 0.01 or v[2] > 0.01
        if air:
            # Drag and Magnus (spin x velocity)
            ax = -DRAG * sp * v[0] + MAGNUS * (w[1] * v[2] - w[2] * v[1])
            ay = -DRAG * sp * v[1] + MAGNUS * (w[2] * v[0] - w[0] * v[2])
            az = -DRAG * sp * v[2] + MAGNUS * (w[0] * v[1] - w[1] * v[0]) - GRAVITY
            if self.knuckle and self.flight_t > 0.15:
                ph = self.flight_t
                ax += self.knuckle * math.sin(ph * 21.0) * 0.5
                ay += self.knuckle * math.cos(ph * 17.0)
                az += self.knuckle * 0.4 * math.sin(ph * 13.0)
            v[0] += ax * dt
            v[1] += ay * dt
            v[2] += az * dt
            decay = math.exp(-SPIN_DECAY * dt)
            for i in range(3):
                w[i] *= decay
        else:
            gs = math.hypot(v[0], v[1])
            if gs > 1e-4:
                dec = (ROLL_DECEL * self.friction + ROLL_DAMP * gs) * dt
                k = max(0.0, gs - dec) / gs
                v[0] *= k
                v[1] *= k
            # Spin bleeds into the grass quickly
            for i in range(3):
                w[i] *= math.exp(-4.0 * dt)
            v[2] = 0.0
        for i in range(3):
            p[i] += v[i] * dt
        if p[2] < RADIUS:
            p[2] = RADIUS
            if v[2] < -0.9:
                v[2] = -v[2] * BOUNCE
                # The grass takes some pace off each bounce
                keep = 0.78
                v[0] *= keep
                v[1] *= keep
                w[0] *= 0.5
                w[1] *= 0.5
                w[2] *= 0.6
                return 'bounce'
            v[2] = 0.0
        return None

    def step(self, dt):
        """Advance by dt; returns a list of event names."""
        events = []
        if self.holder is not None or self.owner is not None:
            return events
        self.flight_t += dt
        ev = self._integrate(dt)
        if ev:
            events.append(ev)
        gs = math.hypot(self.vel[0], self.vel[1])
        if gs > 0.05:
            self.roll_axis = (-self.vel[1] / gs, self.vel[0] / gs, 0.0)
            self.roll_angle = (self.roll_angle + math.degrees(gs * dt / RADIUS)) % 360.0
        hit = self._frame()
        if hit:
            events.append(hit)
        if self.pitch.walls:
            if self._walls():
                events.append('wall')
        return events

    def spin_visual(self, dt):
        """Keep the panels turning while a player dribbles it."""
        gs = math.hypot(self.vel[0], self.vel[1])
        if gs > 0.05:
            self.roll_axis = (-self.vel[1] / gs, self.vel[0] / gs, 0.0)
            self.roll_angle = (self.roll_angle + math.degrees(gs * dt / RADIUS)) % 360.0

    def _bounce(self, n, restitution):
        v = self.vel
        vn = v[0] * n[0] + v[1] * n[1] + v[2] * n[2]
        if vn < 0:
            for i in range(3):
                v[i] -= (1.0 + restitution) * vn * n[i]
            for i in range(3):
                self.spin[i] *= 0.3
            return True
        return False

    def _frame(self):
        """Posts, crossbar and nets at both ends. Returns 'post', 'bar', 'net' or None."""
        pt = self.pitch
        p = self.pos
        side = 1 if p[0] > 0 else -1
        gx = side * pt.half_length
        if abs(p[0] - gx) > pt.goal_depth + 1.0:
            return None
        pr = pt.post_radius
        r = RADIUS + pr
        hw = pt.goal_width / 2.0
        result = None
        # Posts: vertical cylinders on the line
        if p[2] < pt.goal_height + pr:
            for s in (-1, 1):
                cy = s * (hw + pr)
                dx, dy = p[0] - gx, p[1] - cy
                d = math.hypot(dx, dy)
                if 1e-6 < d < r:
                    n = (dx / d, dy / d, 0.0)
                    p[0] = gx + n[0] * r
                    p[1] = cy + n[1] * r
                    if self._bounce(n, POST_BOUNCE):
                        result = 'post'
        # Crossbar: a horizontal cylinder across the top
        if abs(p[1]) <= hw + pr:
            cz = pt.goal_height + pr
            dx, dz = p[0] - gx, p[2] - cz
            d = math.hypot(dx, dz)
            if 1e-6 < d < r:
                n = (dx / d, 0.0, dz / d)
                p[0] = gx + n[0] * r
                p[2] = cz + n[2] * r
                if self._bounce(n, POST_BOUNCE):
                    result = 'bar'
        # Inside the goal: the net soaks up the pace
        inside = side * p[0] > pt.half_length and abs(p[1]) < hw and p[2] < pt.goal_height
        if inside or self.in_net == side:
            hit = False
            back = pt.half_length + pt.goal_depth - RADIUS
            if side * p[0] > back:
                p[0] = side * back
                self.vel[0] = -self.vel[0] * 0.08
                self.vel[1] *= 0.4
                self.vel[2] *= 0.4
                hit = True
            lim = hw - RADIUS
            if abs(p[1]) > lim and side * p[0] > pt.half_length:
                p[1] = math.copysign(lim, p[1])
                self.vel[1] = -self.vel[1] * 0.1
                self.vel[0] *= 0.6
                hit = True
            roof = pt.goal_height - RADIUS
            if p[2] > roof and side * p[0] > pt.half_length:
                p[2] = roof
                self.vel[2] = -abs(self.vel[2]) * 0.1
                hit = True
            if inside and side * p[0] > pt.half_length + RADIUS:
                self.in_net = side
            if hit:
                for i in range(3):
                    self.spin[i] = 0.0
                result = result or 'net'
        elif side * p[0] > pt.half_length and abs(p[1]) >= hw + pr and side * p[0] < pt.half_length + pt.goal_depth:
            # Side netting from the outside
            if abs(p[1]) < hw + 0.3 and p[2] < pt.goal_height:
                p[1] = math.copysign(hw + 0.3, p[1])
                self.vel[1] = -self.vel[1] * 0.1
                self.vel[0] *= 0.5
                result = result or 'sidenet'
        return result

    def _walls(self):
        """Cage boards along the touchlines and beside the goals."""
        pt = self.pitch
        p, v = self.pos, self.vel
        hit = False
        lim_y = pt.half_width - RADIUS
        if abs(p[1]) > lim_y:
            p[1] = math.copysign(lim_y, p[1])
            if v[1] * p[1] > 0:
                v[1] = -v[1] * WALL_BOUNCE
                v[0] *= 0.9
                hit = True
        lim_x = pt.half_length - RADIUS
        if abs(p[0]) > lim_x and (abs(p[1]) > pt.goal_width / 2.0 + pt.post_radius or p[2] > pt.goal_height + 0.2) \
                and self.in_net == 0:
            p[0] = math.copysign(lim_x, p[0])
            if v[0] * p[0] > 0:
                v[0] = -v[0] * WALL_BOUNCE
                v[1] *= 0.9
                hit = True
        # A roof net over the cage keeps lofted balls in
        if p[2] > 7.0 and v[2] > 0:
            v[2] = -v[2] * 0.3
            hit = True
        return hit

    # ------------------------------------------------------------- the rules
    def goal_side(self):
        """+1 or -1 when the whole ball is over that goal line between the posts and under the bar."""
        pt = self.pitch
        p = self.pos
        for side in (-1, 1):
            if side * p[0] > pt.half_length + RADIUS and abs(p[1]) < pt.goal_width / 2.0 \
                    and p[2] < pt.goal_height and side * p[0] < pt.half_length + pt.goal_depth + 0.5:
                return side
        return 0

    def out_of_play(self):
        """'touch', ('goalline', side) or None. Never out in a cage."""
        pt = self.pitch
        if pt.walls:
            return None
        p = self.pos
        if abs(p[1]) > pt.half_width + RADIUS:
            return ('touch', 1 if p[1] > 0 else -1)
        if abs(p[0]) > pt.half_length + RADIUS and not self.goal_side():
            return ('goalline', 1 if p[0] > 0 else -1)
        return None
