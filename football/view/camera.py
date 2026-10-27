"""Cameras: TV broadcast, wide tactical, behind-the-player, and replay angles."""

import math

MODES = ['broadcast', 'wide', 'player', 'end']
LABELS = {'broadcast': 'Broadcast', 'wide': 'Tactical', 'player': 'Player (third person)', 'end': 'End to end'}


def _spring(x, v, target, omega, dt):
    """Move x towards target with velocity v (both lists, updated in place)."""
    f = 1.0 + 2.0 * dt * omega
    oo = omega * omega
    hoo = dt * oo
    det = 1.0 / (f + dt * hoo)
    for i in range(len(x)):
        nx = (f * x[i] + dt * v[i] + dt * hoo * target[i]) * det
        v[i] = (v[i] + hoo * (target[i] - x[i])) * det
        x[i] = nx


class Camera:
    def __init__(self, base, pitch, mode='broadcast'):
        self.base = base
        self.pitch = pitch
        self.mode = mode
        self.pos = [0.0, -30.0, 12.0]
        self.look = [0.0, 0.0, 0.0]
        self.fov = 40.0
        self.shake = 0.0
        self.t = 0.0
        self.attack = 1
        self.vpos = [0.0, 0.0, 0.0]
        self.vlook = [0.0, 0.0, 0.0]
        base.camLens.set_near_far(0.3, 900)

    def ground_axes(self):
        """(right, forward) unit vectors on the pitch for the current view, so the stick
        always moves the player the way it looks on screen."""
        fx, fy = self.look[0] - self.pos[0], self.look[1] - self.pos[1]
        d = math.hypot(fx, fy) or 1.0
        fx, fy = fx / d, fy / d
        return (fy, -fx), (fx, fy)

    def snap(self, ball, focus):
        self._target(ball, focus, 1.0)
        self.pos = list(self._tp)
        self.look = list(self._tl)
        self.vpos = [0.0, 0.0, 0.0]
        self.vlook = [0.0, 0.0, 0.0]

    def _target(self, ball, focus, vel_lead):
        pt = self.pitch
        big = pt.length > 80
        bx, by, bz = ball
        fx, fy = focus if focus else (bx, by)
        if self.mode in ('broadcast', 'wide'):
            wide = self.mode == 'wide'
            h = (15.0 if big else 11.5) * (1.6 if wide else 1.0)
            back = (19.0 if big else 14.0) * (1.6 if wide else 1.0)
            cx = max(-pt.half_length * 0.82, min(pt.half_length * 0.82, bx * 0.92))
            # Closer to the goal the camera swings round a touch
            tilt = cx / pt.half_length
            self._tp = (cx - tilt * 4.0, -pt.half_width - back, h)
            self._tl = (cx + (bx - cx) * 0.5, by * 0.45, 0.0)
        elif self.mode == 'end':
            a = self.attack
            h = 18.0 if big else 11.0
            self._tp = (bx - a * (26.0 if big else 15.0), by * 0.6, h)
            self._tl = (bx + a * 8.0, by * 0.85, 0.0)
        else:
            # Over the shoulder of whoever you control, looking at the ball and goal
            a = self.attack
            px, py = fx, fy
            self._tp = (px - a * 9.0, py * 0.9, 4.6)
            self._tl = (px + a * 7.0, py * 0.8 + (by - py) * 0.3, 0.6)

    def update(self, dt, ball, focus=None, attack=1, zoom=1.0, ball_vel=None):
        self.t += dt
        self.attack = attack
        self._target(ball, focus, 1.0)
        tl = list(self._tl)
        if ball_vel is not None and self.mode != 'player':
            # A camera operator leads the play: aim a little ahead of a moving ball,
            # and tilt up a touch to follow a high one
            lead = 0.28 if self.mode == 'broadcast' else 0.2
            tl[0] += max(-6.0, min(6.0, ball_vel[0] * lead))
            tl[1] += max(-4.0, min(4.0, ball_vel[1] * lead * 0.6))
            tl[2] += min(2.5, max(0.0, ball[2] - 0.5) * 0.35)
        # Critically damped springs: they ease in and out instead of jerking
        wp = 2.6 if self.mode != 'player' else 4.0
        wl = 3.6 if self.mode != 'player' else 5.0
        _spring(self.pos, self.vpos, self._tp, wp, dt)
        _spring(self.look, self.vlook, tl, wl, dt)
        self._apply(zoom)

    def _apply(self, zoom=1.0):
        c = self.base.camera
        sx = sy = 0.0
        if self.shake > 0:
            self.shake = max(0.0, self.shake - 0.016)
            sx = math.sin(self.t * 53) * self.shake * 0.25
            sy = math.cos(self.t * 47) * self.shake * 0.25
        if self.mode in ('broadcast', 'wide'):
            # The faint drift of a camera on a head, not a computer's dead-still view
            sx += math.sin(self.t * 0.71) * 0.05 + math.sin(self.t * 1.9) * 0.012
            sy += math.sin(self.t * 0.53 + 1.0) * 0.035
        c.set_pos(self.pos[0] + sx, self.pos[1], self.pos[2] + sy)
        c.look_at(self.look[0], self.look[1], self.look[2])
        self.base.camLens.set_fov(self.fov / zoom)

    def penalty(self, dt, spot, attack, ball=None):
        """Low behind the taker, the whole goal in view (the penalty game's camera)."""
        pt = self.pitch
        sx, sy = spot
        gx = attack * pt.half_length
        big = pt.length > 80
        tp = (sx - attack * (7.5 if big else 6.0), sy * 0.5, 2.5 if big else 2.2)
        tl = (gx, 0.0, pt.goal_height * 0.45)
        k = min(1.0, dt * 4.0)
        for i in range(3):
            self.pos[i] += (tp[i] - self.pos[i]) * k
            self.look[i] += (tl[i] - self.look[i]) * k
        self._apply(1.25 if big else 1.0)

    def replay(self, dt, ball, angle, t):
        """Replay cameras: low behind the goal, side-on tracking, or circling the ball."""
        pt = self.pitch
        bx, by, bz = ball
        if angle == 'goal':
            # Low by the post, looking out at the finish
            side = 1 if bx > 0 else -1
            wing = -1 if by > 0 else 1
            tp = (side * (pt.half_length - 1.2), wing * (pt.goal_width / 2 + 2.5), 2.6)
            tl = (bx, by, bz * 0.6 + 0.4)
        elif angle == 'orbit':
            a = t * 0.5
            tp = (bx + math.cos(a) * 9.0, by + math.sin(a) * 9.0, 3.0)
            tl = (bx, by, 0.6)
        else:
            # Pitch-side, low: inside the cage, or just off the touchline
            tp = (bx - 3.0, -pt.half_width + (1.5 if pt.walls else -3.0), 3.2)
            tl = (bx, by, 0.5)
        k = min(1.0, dt * 5.0)
        for i in range(3):
            self.pos[i] += (tp[i] - self.pos[i]) * k
            self.look[i] += (tl[i] - self.look[i]) * min(1.0, dt * 9.0)
        self._apply(1.15)
