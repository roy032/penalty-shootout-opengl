"""Ball flight, the goal frame and shot generation. No OpenGL here."""

import math

from . import config as C


def clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


def dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def sub(a, b):
    return [a[0] - b[0], a[1] - b[1], a[2] - b[2]]


def length(a):
    return math.sqrt(dot(a, a))


class Ball:
    def __init__(self, pos=None):
        self.pos = list(pos) if pos else [0.0, C.BALL_RADIUS, C.SPOT_Z]
        self.vel = [0.0, 0.0, 0.0]
        self.side_accel = 0.0       # sideways (Magnus) acceleration from spin
        self.spin_axis = [1.0, 0.0, 0.0]
        self.spin_angle = 0.0       # degrees, for drawing the panels rolling
        self.in_net = False
        self.held = False           # caught by the keeper

    def speed(self):
        return length(self.vel)


def plan_shot(aim, power, kind, pressure, rng, sigma_scale=1.0):
    """Turn the kicker's intent into an actual target and launch parameters.

    aim: (x, y) on the goal-line plane the kicker is going for
    power: 0..1 where the power bar was stopped
    pressure: 0..1 extra nerves (must-score kicks, keeper antics)
    Returns dict with target (x, y), speed and curl.
    """
    spec = C.SHOT_TYPES[kind]
    over = max(0.0, power - C.POWER_SWEET_HIGH) / (1.0 - C.POWER_SWEET_HIGH)
    under = max(0.0, C.POWER_SWEET_LOW - power) / C.POWER_SWEET_LOW
    lo, hi = spec['speed']
    speed = lo + (hi - lo) * clamp(power, 0.0, 1.0)
    sigma = (spec['sigma'] * (1.0 + 1.6 * over + 0.4 * under) + 0.14 * pressure) * sigma_scale
    tx = aim[0] + rng.gauss(0.0, sigma)
    # An over-hit ball climbs: the classic penalty blazed over the bar
    ty = aim[1] + rng.gauss(0.0, sigma * 0.8) + 0.9 * over * over + 0.25 * over
    ty = max(C.BALL_RADIUS, ty)
    curl = 0.0
    if spec['curl']:
        # Start it wide and bend it back towards the target
        curl = -math.copysign(spec['curl'], tx if tx else 1.0)
    return dict(target=(tx, ty), speed=speed, curl=curl, kind=kind)


def launch(ball, target, speed, curl=0.0):
    """Set ball velocity so that, under gravity and curl, it passes through
    target (x, y) on the goal-line plane."""
    start = ball.pos
    dx = target[0] - start[0]
    dz = C.GOAL_LINE_Z - start[2]
    dy = target[1] - start[1]
    horiz = math.hypot(dx, dz)
    # speed is the horizontal speed; gravity supplies the dip, so a slow
    # chip naturally loops up and drops under the bar
    t = horiz / speed
    vx = (dx - 0.5 * curl * t * t) / t
    vz = dz / t
    vy = (dy + 0.5 * C.GRAVITY * t * t) / t
    ball.vel = [vx, vy, vz]
    ball.side_accel = curl
    return t


def _bounce(ball, normal, restitution):
    vn = dot(ball.vel, normal)
    if vn < 0:
        for i in range(3):
            ball.vel[i] -= (1.0 + restitution) * vn * normal[i]
        # Some sideways speed is lost to friction
        for i in range(3):
            ball.vel[i] = ball.vel[i] * 0.9
        ball.side_accel *= 0.3


def _collide_posts(ball):
    """Posts and crossbar are cylinders. Returns 'post', 'bar' or None."""
    r = C.BALL_RADIUS + C.POST_RADIUS
    px, py, pz = ball.pos
    cz = C.GOAL_LINE_Z - C.POST_RADIUS
    for side in (-1, 1):
        cx = side * (C.GOAL_HALF_WIDTH + C.POST_RADIUS)
        if py <= C.GOAL_HEIGHT + C.POST_RADIUS:
            d = math.hypot(px - cx, pz - cz)
            if d < r and d > 1e-6:
                n = [(px - cx) / d, 0.0, (pz - cz) / d]
                ball.pos[0] = cx + n[0] * r
                ball.pos[2] = cz + n[2] * r
                _bounce(ball, n, 0.6)
                return 'post'
    cy = C.GOAL_HEIGHT + C.POST_RADIUS
    if abs(px) <= C.GOAL_HALF_WIDTH + C.POST_RADIUS:
        d = math.hypot(py - cy, pz - cz)
        if d < r and d > 1e-6:
            n = [0.0, (py - cy) / d, (pz - cz) / d]
            ball.pos[1] = cy + n[1] * r
            ball.pos[2] = cz + n[2] * r
            _bounce(ball, n, 0.6)
            return 'bar'
    return None


def _collide_net(ball):
    """Once inside the goal the net soaks up the ball's speed."""
    x, y, z = ball.pos
    r = C.BALL_RADIUS
    inside = abs(x) < C.GOAL_HALF_WIDTH and y < C.GOAL_HEIGHT and z < C.GOAL_LINE_Z - r
    if not inside and not ball.in_net:
        return False
    hit = False
    back = C.GOAL_LINE_Z - C.GOAL_DEPTH + r
    if z < back:
        ball.pos[2] = back
        ball.vel[2] = abs(ball.vel[2]) * 0.08
        ball.vel[0] *= 0.35
        ball.vel[1] *= 0.35
        hit = True
    lim = C.GOAL_HALF_WIDTH - r
    if abs(x) > lim and z < C.GOAL_LINE_Z:
        ball.pos[0] = math.copysign(lim, x)
        ball.vel[0] = -ball.vel[0] * 0.1
        ball.vel[2] *= 0.6
        hit = True
    roof = C.GOAL_HEIGHT - r
    if y > roof and z < C.GOAL_LINE_Z:
        ball.pos[1] = roof
        ball.vel[1] = -abs(ball.vel[1]) * 0.1
        hit = True
    if hit:
        ball.side_accel = 0.0
    ball.in_net = ball.in_net or inside
    return hit


def closest_on_segment(p, a, b):
    ab = sub(b, a)
    denom = dot(ab, ab)
    t = 0.0 if denom == 0 else clamp(dot(sub(p, a), ab) / denom, 0.0, 1.0)
    return [a[0] + ab[0] * t, a[1] + ab[1] * t, a[2] + ab[2] * t], t


def sphere_capsule(p, radius, a, b, cap_radius):
    """Returns (normal, depth, t) if the sphere overlaps the capsule a-b."""
    q, t = closest_on_segment(p, a, b)
    d = sub(p, q)
    dist = length(d)
    reach = radius + cap_radius
    if dist >= reach:
        return None
    n = [d[0] / dist, d[1] / dist, d[2] / dist] if dist > 1e-6 else [0.0, 0.0, 1.0]
    return n, reach - dist, t


def step(ball, dt):
    """Advance the ball by dt. Returns a list of event names."""
    events = []
    if ball.held:
        return events
    ball.vel[0] += ball.side_accel * dt
    ball.vel[1] -= C.GRAVITY * dt
    for i in range(3):
        ball.pos[i] += ball.vel[i] * dt
    # Spin for drawing: roll axis perpendicular to travel
    sp = math.hypot(ball.vel[0], ball.vel[2])
    if sp > 0.05:
        ball.spin_axis = [-ball.vel[2] / sp, 0.0, ball.vel[0] / sp]
        ball.spin_angle = (ball.spin_angle + math.degrees(sp * dt / C.BALL_RADIUS)) % 360.0

    if ball.pos[1] < C.BALL_RADIUS:
        ball.pos[1] = C.BALL_RADIUS
        if ball.vel[1] < -0.6:
            events.append('bounce')
            ball.vel[1] = -ball.vel[1] * 0.5
            ball.vel[0] *= 0.85
            ball.vel[2] *= 0.85
        else:
            ball.vel[1] = 0.0
            f = max(0.0, 1.0 - 1.2 * dt)
            ball.vel[0] *= f
            ball.vel[2] *= f
        ball.side_accel = 0.0

    hit = _collide_posts(ball)
    if hit:
        events.append(hit)
    if _collide_net(ball):
        events.append('net')
    return events


def crossed_line(ball):
    """Whole ball over the goal-line plane."""
    return ball.pos[2] < C.GOAL_LINE_Z - C.BALL_RADIUS


def is_goal_position(ball):
    return crossed_line(ball) and abs(ball.pos[0]) < C.GOAL_HALF_WIDTH and ball.pos[1] < C.GOAL_HEIGHT
