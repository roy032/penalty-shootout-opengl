"""Team AI: shape, pressing, marking, support runs, on-ball decisions,
set pieces and goalkeeping. Runs for both teams; the human's team uses it
for everyone the human isn't steering."""

import math

from .player import ang_diff, norm
from .styles import style_for


class TeamAI:
    def __init__(self, match, team):
        self.match = match
        self.team = team
        self.call_press = 0.0
        self.shot_seen = None       # (time seen, crossing y, z, t) for the keeper
        self.hold_t = 0.0
        self.plan_t = 0.0
        self.chaser = None
        self.presser = None
        self.cover = None
        self.marks = {}
        self.style = getattr(team, 'style', None) or style_for(team.info['id'])
        self.had_ball = False
        self.won_tick = -10 ** 6     # when we last won the ball back, for counter-attacks

    # =========================================================== the loop
    def update(self, dt):
        m = self.match
        self.call_press = max(0.0, self.call_press - dt)
        self.plan_t -= dt
        if self.plan_t <= 0:
            self.plan_t = 0.1
            self._team_plan()
        k = self.team.keeper()
        for p in self.team.active():
            if m._controller_of(p) is not None and not (p is k and m.penalty_cam()):
                # (a human facing a penalty only picks the dive: the keeper still moves himself)
                continue
            if m.shootout and m.restart and p is not m.restart['taker'] \
                    and not (p is k and m.restart['team'] is not self.team):
                # Everyone waiting their turn stays put in the centre circle
                p.target = None
                continue
            if p is k:
                self._keeper(p, dt)
                continue
            if p.run_t > 0 and m.state == 'play':
                # Give-and-go: burst into the space ahead and wait for it back
                p.run_t -= dt
                a = self.team.attack
                p.target = m.pitch.clamp_inside(p.pos[0] + a * 6.0, p.pos[1] * 0.85, 1.0)
                p.want_speed = p.top_speed()
                p.sprint = p.stamina > 0.1
                continue
            p.brain_t -= dt
            if p.brain_t <= 0:
                p.brain_t = self.team.ai_react * (0.6 + 0.8 * m.rng.random()) + 0.04
                self._think(p)

    def game_state(self):
        """'protect' when leading in the last fifth of the second half (or extra time),
        'chase' when behind by one or two then, otherwise None."""
        m = self.match
        if m.half not in (2, 4) or m.time < m.half_length() * 0.8 or m.shootout:
            return None
        diff = self.team.score - self.team.opp.score
        if diff > 0:
            return 'protect'
        if -2 <= diff < 0:
            return 'chase'
        return None

    # ======================================================== team level
    def _team_plan(self):
        m = self.match
        b = m.ball
        t = self.team
        outs = [p for p in t.active() if not p.keeper]
        self.chaser = None
        self.presser = None
        self.cover = None
        self.marks = {}
        if not outs:
            return
        owner = b.owner or b.holder
        ours = owner is not None and owner.team is t
        if ours and not self.had_ball:
            self.won_tick = m.ticks
        if owner is not None:
            self.had_ball = ours
        if owner is None and m.state == 'play':
            pt = m.pass_target
            if pt and pt[0] is not None and pt[0].team is t:
                self.chaser = pt[0]
            elif pt and pt[0] is not None and pt[0].team is not t and pt[1].team is not t:
                # Their pass: whoever can cut it out
                self.chaser = min(outs, key=m.time_to_ball)
            else:
                self.chaser = min(outs, key=m.time_to_ball)
        elif owner is not None and owner.team is not t and b.holder is None:
            ordered = sorted(outs, key=lambda p: p.dist_to(owner.pos[0], owner.pos[1]))
            self.presser = ordered[0]
            # A second man covers when they're in our half, or when asked to press
            in_our_half = owner.pos[0] * t.attack < 0
            if len(ordered) > 1 and (in_our_half or t.press > 1.1 or self.call_press > 0):
                self.cover = ordered[1]
            # Man-marking for the rest, most dangerous attacker first
            gx = t.own_goal_x(m.pitch)
            threats = [o for o in t.opp.active() if not o.keeper and o is not owner]
            threats.sort(key=lambda o: math.hypot(o.pos[0] - gx, o.pos[1]))
            free = [p for p in outs if p is not self.presser and p is not self.cover]
            for o in threats:
                if not free:
                    break
                d = min(free, key=lambda p: p.dist_to(o.pos[0], o.pos[1]))
                self.marks[d] = o
                free.remove(d)

    # ===================================================== player brains
    def _think(self, p):
        m = self.match
        b = m.ball
        st = m.state
        p.sprint = False
        p.plan = p.plan or {}
        p.plan['first_time'] = None
        if st in ('kickoff', 'restart'):
            r = m.restart
            if r and r['taker'] is p and not r.get('taken'):
                self._take_set_piece(p, r)
                return
            self._shape(p, attacking=r is not None and r['team'] is self.team)
            return
        if st != 'play':
            p.target = None
            return
        if b.owner is p:
            self._on_ball(p)
            return
        owner = b.owner or b.holder
        if owner is not None and owner.team is self.team:
            self._support(p, owner)
        elif owner is not None:
            self._defend(p, owner)
        else:
            if p is self.chaser:
                self._chase(p)
            else:
                pt = m.pass_target
                attacking = (pt is not None and pt[1].team is self.team) or \
                    (b.last_touch is not None and b.last_touch.team is self.team)
                self._shape(p, attacking=attacking)

    # ---------------------------------------------------------- positions
    def shape_spot(self, p, attacking):
        m = self.match
        pt = m.pitch
        b = m.ball
        a = self.team.attack
        fx, fy = p.slot
        bx = b.pos[0] * a          # ball position in our attacking frame
        # The block slides with the ball, pushes up when we have it
        st = self.style
        x = fx * pt.half_length * 0.62 + bx * 0.5 + (0.12 if attacking else -0.06) * pt.half_length
        x += st['line'] * pt.half_length * (0.5 if attacking else 1.0)
        if p.role == 'FWD' and attacking:
            x += pt.half_length * 0.1
        y = fy * pt.half_width * (0.82 * st['width'] if attacking else 0.62) + b.pos[1] * 0.28
        if not attacking:
            # Stay goal-side of the ball
            x = min(x, bx - 1.5 if p.role != 'FWD' else bx + 3)
        x = max(-pt.half_length + 2.0, min(pt.half_length - 2.0, x))
        if m.settings['offside'] and attacking:
            line = self._offside_line()
            x = min(x, max(line - 0.4, bx))
        return pt.clamp_inside(a * x, y, 1.0)

    def _offside_line(self):
        """Second-last defender, in our attacking frame."""
        a = self.team.attack
        xs = sorted((o.pos[0] * a for o in self.team.opp.active()), reverse=True)
        return max(xs[1] if len(xs) > 1 else 0.0, 0.0)

    def _shape(self, p, attacking):
        x, y = self.shape_spot(p, attacking)
        p.target = (x, y)
        d = p.dist_to(x, y)
        p.want_speed = p.top_speed() if d > 6 else 4.0 + d * 0.4
        p.sprint = d > 12
        p.plan['face'] = tuple(self.match.ball.pos[:2])

    def _open_space(self, x, y, radius=3.0):
        """Nudge (x, y) towards the spot nearby that is furthest from opponents."""
        m = self.match
        best, bs = (x, y), -1.0
        for dx, dy in ((0, 0), (radius, 0), (-radius, 0), (0, radius), (0, -radius), (radius * 0.7, radius * 0.7),
                       (radius * 0.7, -radius * 0.7)):
            cx, cy = m.pitch.clamp_inside(x + dx, y + dy, 1.0)
            near = min((o.dist_to(cx, cy) for o in self.team.opp.active()), default=10.0)
            s = min(near, 8.0) - 0.15 * math.hypot(dx, dy)
            if s > bs:
                best, bs = (cx, cy), s
        return best

    def _support(self, p, owner):
        m = self.match
        pt = m.pitch
        a = self.team.attack
        x, y = self.shape_spot(p, True)
        # Forwards (and sometimes midfielders) run in behind
        run = p.role == 'FWD' or (p.role == 'MID' and (p.idx + int(m.time / 6)) % self.style['runs'] == 0)
        if run and owner.pos[0] * a > -pt.half_length * 0.3:
            line = self._offside_line() if m.settings['offside'] else self._last_line()
            depth = 0.5 if m.settings['offside'] else 4.0
            rx = min(pt.half_length - 3.0, max(x * a, line + depth))
            x = rx * a
            y = y * 0.6
            p.sprint = True
        # The nearest team-mate shows for the ball at an angle
        if p.dist_to(owner.pos[0], owner.pos[1]) < 10 and not run:
            ox, oy = owner.pos
            side = 1 if p.pos[1] > oy else -1
            x, y = ox + a * 3.0, oy + side * 6.0
        x, y = self._open_space(x, y)
        p.target = m.pitch.clamp_inside(x, y, 0.8)
        p.want_speed = p.top_speed()
        p.plan['face'] = (owner.pos[0], owner.pos[1])

    def _last_line(self):
        a = self.team.attack
        xs = [o.pos[0] * a for o in self.team.opp.active() if not o.keeper]
        return max(xs) if xs else 0.0

    def _defend(self, p, owner):
        m = self.match
        b = m.ball
        gx = self.team.own_goal_x(m.pitch)
        if b.holder is not None:
            self._shape(p, False)
            return
        if p is self.presser or p is self.cover:
            # Close down: goal-side, a yard off, then nick it
            ux, uy = norm(gx - owner.pos[0], -owner.pos[1])
            stand = 0.9 if p is self.presser else 3.5
            tx = owner.pos[0] + ux * stand + owner.vel[0] * 0.25
            ty = owner.pos[1] + uy * stand + owner.vel[1] * 0.25
            p.target = (tx, ty)
            p.want_speed = p.top_speed()
            d = p.dist_to(b.pos[0], b.pos[1])
            p.sprint = d > 4.0
            if p is self.presser and d < 1.35 and p.tackle_cd <= 0:
                rate = 0.55 + 0.6 * p.fb.defending * self.team.press
                # A good defender doesn't dive in from behind: he gets goal-side first
                if abs(ang_diff(math.atan2(p.pos[1] - owner.pos[1], p.pos[0] - owner.pos[0]), owner.facing)) > 2.0:
                    rate *= 0.3
                if m.rng.random() < rate * (p.brain_t + 0.1) * 2.0:
                    m.do_tackle(p)
            elif p is self.presser and 1.2 < d < 2.6 and p.tackle_cd <= 0:
                # He's got past: last-ditch slide from the side
                behind = (owner.pos[0] - p.pos[0]) * -self.team.attack > 0.5
                if behind and m.rng.random() < 0.18 * self.team.press:
                    m.do_slide(p, norm(b.pos[0] + owner.vel[0] * 0.25 - p.pos[0],
                                       b.pos[1] + owner.vel[1] * 0.25 - p.pos[1]))
            return
        o = self.marks.get(p)
        if o is not None:
            ux, uy = norm(gx - o.pos[0], -o.pos[1] * 0.5)
            mx, my = o.pos[0] + ux * 1.6 + o.vel[0] * 0.3, o.pos[1] + uy * 1.6 + o.vel[1] * 0.3
            sx, sy = self.shape_spot(p, False)
            w = 0.85 if p.role == 'DEF' else 0.65
            p.target = (mx * w + sx * (1 - w), my * w + sy * (1 - w))
            p.want_speed = p.top_speed()
            p.sprint = p.dist_to(*p.target) > 6
            p.plan['face'] = tuple(b.pos[:2])
            return
        self._shape(p, False)

    def _chase(self, p):
        m = self.match
        b = m.ball
        # Head for where the ball will be when we get there
        t = min(2.0, m.time_to_ball(p))
        q = b.predict(t * 0.9) if b.speed() > 1.0 else b.pos
        p.target = (q[0], q[1])
        p.want_speed = p.top_speed()
        p.sprint = p.dist_to(q[0], q[1]) > 3.0
        # First-time finish if it's dropping in front of goal
        a = self.team.attack
        if m.xg(q[0], q[1], self.team) > 0.2 and q[0] * a > 0:
            p.plan['first_time'] = ('shoot', self._shot_dir(p), 0.75)

    # ---------------------------------------------------------- on the ball
    def _shot_dir(self, p):
        """Aim for the side the keeper isn't covering."""
        k = self.team.opp.keeper()
        ky = k.pos[1] if k else 0.0
        side = -1 if ky > p.pos[1] * 0.15 else 1
        if self.match.rng.random() < 0.25:
            side = -side
        return (0.0, side)

    def _lane_safety(self, p, tx, ty, speed=14.0):
        """Seconds of margin before the nearest opponent could cut out a pass to (tx, ty)."""
        return self.match.lane_safety(self.team, p.pos[0], p.pos[1], tx, ty, speed)

    def _pressure(self, p, r=3.0):
        return min((o.dist_to(*p.pos) for o in self.team.opp.active()), default=10.0)

    def _on_ball(self, p):
        m = self.match
        pt = m.pitch
        rng = m.rng
        noise = self.team.ai_noise
        a = self.team.attack
        gx = self.team.opp_goal_x(pt)
        st = self.style
        options = []
        near = self._pressure(p)
        # Just won it back: a counter-attacking side looks forward first
        fresh = (m.ticks - self.won_tick) < 4.0 * 60
        forward = st['forward'] + (st['counter'] if fresh else 0.0)
        # Shooting
        xg = m.xg(p.pos[0], p.pos[1], self.team)
        block = 0
        for o in self.team.opp.active():
            if o.keeper:
                continue
            if (o.pos[0] - p.pos[0]) * a > 0 and abs(o.pos[0] - p.pos[0]) < abs(gx - p.pos[0]):
                # Inside the shooting triangle?
                f = (o.pos[0] - p.pos[0]) / (gx - p.pos[0] + 1e-6)
                lim = pt.goal_width / 2.0 * f + 0.6
                if abs(o.pos[1] - p.pos[1] * (1 - f)) < lim:
                    block += 1
        sx = xg * (0.55 ** block)
        dist = math.hypot(gx - p.pos[0], p.pos[1])
        if dist < pt.length * (0.42 + max(0.0, st['shoot']) * 0.3):
            # On small pitches everything is "in range", so work for a better chance
            fussy = 0.5 if pt.length < 50 else 0.0
            options.append((sx * 5.0 - 0.45 - fussy + st['shoot'] + rng.uniform(-noise, noise), 'shoot'))
        # Passing
        best_pass = None
        for mate in self.team.active():
            if mate is p:
                continue
            for kind in ('ground', 'through', 'lob'):
                if kind == 'through' and (mate.role == 'GK' or mate.pos[0] * a < p.pos[0] * a):
                    continue
                if kind == 'lob' and (st['long'] <= 0 or mate.keeper or mate.pos[0] * a < p.pos[0] * a + 6.0):
                    continue
                tx, ty = m.lead_point(p, mate, kind)
                if not (-pt.half_length < tx < pt.half_length):
                    continue
                d = math.hypot(tx - p.pos[0], ty - p.pos[1])
                if d < 3.0 or d > pt.length * 0.6:
                    continue
                if kind == 'lob' and d < 14.0:
                    continue
                if kind == 'ground':
                    # In the cage, a blocked lane might still be on off the boards
                    safe = m.pass_lane(p, tx, ty)[0]
                else:
                    safe = self._lane_safety(p, tx, ty)
                space = min((o.dist_to(tx, ty) for o in self.team.opp.active()), default=8.0)
                if kind == 'lob':
                    # Over the top: the lane doesn't matter, the landing spot does
                    safe = max(safe, min(space, 4.0) * 0.12 - 0.15)
                prog = (tx * a - p.pos[0] * a) / pt.half_length
                val = 0.2 + prog * (1.2 + forward) + m.xg(tx, ty, self.team) * 4.0 + min(space, 6.0) * 0.06
                if mate.keeper:
                    val -= 0.7
                if m.settings['offside'] and kind == 'through' and mate.pos[0] * a > self._offside_line() + 0.2:
                    val -= 2.0
                risk = 1.0 / (1.0 + math.exp(-safe * 7.0))
                score = val * risk - (1.0 - risk) * st['risk'] + rng.uniform(-noise, noise)
                if kind == 'through':
                    score += st['through'] - 0.05
                elif kind == 'lob':
                    score += st['long'] - 0.45
                if best_pass is None or score > best_pass[0]:
                    best_pass = (score, kind, mate)
        if best_pass:
            options.append((best_pass[0] + st['passing'], 'pass'))
        # Dribbling
        best_drib = None
        want = math.atan2(-p.pos[1] * 0.3, a)
        for off in (0.0, 0.6, -0.6, 1.2, -1.2):
            ang = want + off
            dx, dy = math.cos(ang), math.sin(ang)
            cx, cy = p.pos[0] + dx * 4.0, p.pos[1] + dy * 4.0
            if abs(cx) > pt.half_length - 1 or abs(cy) > pt.half_width - 1:
                continue
            free = min((o.dist_to(cx, cy) for o in self.team.opp.active() if not o.keeper), default=8.0)
            val = (dx * a) * 0.3 + min(free, 5.0) * 0.08 - 0.32 + 0.2 * p.fb.dribbling + st['dribble']
            if near < 2.2:
                val -= 0.2
            if best_drib is None or val > best_drib[0]:
                best_drib = (val, (dx, dy), free)
        if best_drib:
            options.append((best_drib[0] + rng.uniform(-noise, noise), 'dribble'))
        # Hoof it when cornered at the back
        own = -a * pt.half_length
        if near < 1.6 and abs(p.pos[0] - own) < pt.length * 0.3:
            options.append((0.25 + rng.uniform(-noise, noise), 'clear'))
        if self.game_state() == 'protect':
            # Seeing it out: only a clear chance is worth a shot; up the pitch, take it to the corner flag
            options = [(v - (0.3 if k == 'shoot' and sx < 0.25 else 0.0), k) for v, k in options]
            if p.pos[0] * a > pt.half_length * 0.45 and near > 1.2:
                cx, cy = a * pt.half_length, math.copysign(pt.half_width, p.pos[1] or 1.0)
                best_drib = (0.6, norm(cx - p.pos[0], cy - p.pos[1]), 3.0)
                options.append((0.6 + rng.uniform(-noise, noise), 'dribble'))
        options.sort(key=lambda o: -o[0])
        choice = options[0][1] if options else 'dribble'
        # Don't pass the instant it arrives unless pressed
        if choice == 'pass' and p.dribble_t < st['tempo'] and near > 2.0:
            choice = 'dribble'
        if choice == 'shoot':
            style = 'normal'
            k = self.team.opp.keeper()
            if k and abs(k.pos[0] - gx) > 4.0 and dist < 22 and rng.random() < 0.5:
                style = 'chip'
            elif dist < 18 and rng.random() < 0.35:
                style = 'finesse'
            power = min(1.0, 0.55 + dist * 0.012 + rng.uniform(-0.05, 0.12))
            m.do_shoot(p, self._shot_dir(p), power, style)
        elif choice == 'pass':
            _, kind, mate = best_pass
            m.do_pass(p, None, kind, receiver=mate)
        elif choice == 'clear':
            m.do_clear(p)
        else:
            dx, dy = best_drib[1] if best_drib else (a, 0.0)
            p.target = (p.pos[0] + dx * 5.0, p.pos[1] + dy * 5.0)
            free = best_drib[2] if best_drib else 3.0
            p.sprint = free > 4.0 and p.stamina > 0.3
            p.want_speed = p.top_speed(True)
            # A trick to beat the man in front
            if near < 1.8 and p.fb.dribbling > 0.78 and \
                    rng.random() < 0.08 * p.fb.dribbling * (1.0 + 4.0 * max(0.0, st['dribble'])):
                m.do_skill(p, (-dy, dx) if rng.random() < 0.5 else (dy, -dx))

    # ---------------------------------------------------------- set pieces
    def _take_set_piece(self, p, r):
        m = self.match
        pt = m.pitch
        wait = 0.6 if r['kind'] == 'kickoff' else 1.0
        if r['kind'] == 'penalty':
            wait = 1.4
        elif r['kind'] != 'kickoff' and self.game_state() == 'protect':
            # Running the clock down
            wait += 2.5
            if not r.get('wasting'):
                r['wasting'] = True
                m.emit('time_waste', team=self.team.idx)
        if r['t'] < wait:
            p.target = None
            return
        kind = r['kind']
        a = self.team.attack
        mates = [q for q in self.team.active() if q is not p]
        if kind == 'kickoff':
            mate = min(mates, key=lambda q: q.dist_to(*p.pos) + (5 if q.keeper else 0))
            m.do_pass(p, None, 'ground', receiver=mate)
        elif kind == 'penalty':
            rng = m.rng
            hw = pt.goal_width / 2.0
            if rng.random() < 0.04 + 0.05 * p.fb.aura:
                m.take_penalty(p, 0.0, 1.1, 0.35, 'panenka')
            else:
                m.take_penalty(p, rng.choice((-1, 1)) * rng.uniform(0.5, 0.85) * hw, rng.uniform(0.3, 1.7),
                               rng.uniform(0.5, 0.8), 'finesse' if rng.random() < 0.25 else 'normal')
        elif kind == 'corner':
            box = [q for q in mates if pt.in_box(q.pos[0], q.pos[1], a) and not q.keeper]
            if box and m.rng.random() < 0.75:
                tgt = max(box, key=lambda q: q.fb.physical + m.rng.uniform(0, 0.3))
                m.do_pass(p, None, 'lob', receiver=tgt)
            else:
                short = min(mates, key=lambda q: q.dist_to(*p.pos))
                m.do_pass(p, None, 'ground', receiver=short)
        elif kind == 'freekick' and m.xg(p.pos[0], p.pos[1], self.team) > 0.07:
            m.do_shoot(p, self._shot_dir(p), 0.75, 'finesse')
        elif kind == 'goalkick' and m.rng.random() < 0.4:
            fwd = max(mates, key=lambda q: q.pos[0] * a)
            m.do_pass(p, None, 'lob', receiver=fwd)
        else:
            best, bs = None, -1e9
            for q in mates:
                if q.keeper:
                    continue
                s = self._lane_safety(p, q.pos[0], q.pos[1]) * 2.0 + (q.pos[0] * a) * 0.02
                if s > bs:
                    best, bs = q, s
            if best is None:
                m.do_clear(p)
            else:
                m.do_pass(p, None, 'ground', receiver=best)

    # ---------------------------------------------------------- keeper
    def _keeper(self, k, dt):
        m = self.match
        b = m.ball
        pt = m.pitch
        t = self.team
        gx = t.own_goal_x(pt)
        a = t.attack
        if m.state in ('kickoff',):
            k.target = (gx + a * 1.0, 0.0)
            k.want_speed = 4.0
            return
        r = m.restart
        if m.state == 'restart' and r and not r.get('taken'):
            if r['taker'] is k:
                self._take_set_piece(k, r)
                return
            if r['kind'] == 'penalty' and r['team'] is not t:
                k.target = None
                k.vel = [0.0, 0.0]
                return
            if r['kind'] == 'corner' and r['team'] is t and self.game_state() == 'chase' and \
                    m.time > m.half_length() * 0.9:
                # Last throw of the dice: the keeper goes up for it
                if not r.get('keeper_up'):
                    r['keeper_up'] = True
                    m.emit('keeper_up', who=m._idx(k))
                k.target = (-gx * 0.82, 0.0)
                k.want_speed = k.top_speed()
                k.sprint = True
                return
        # Holding the ball: look up, then distribute
        if b.holder is k:
            self.hold_t += dt
            k.target = None
            if self.hold_t > 1.2:
                self.hold_t = 0.0
                k.set_state('run', 0.0)
                best, bs = None, -1e9
                for q in t.active():
                    if q is k:
                        continue
                    safe = self._lane_safety(k, q.pos[0], q.pos[1], 16.0)
                    d = q.dist_to(*k.pos)
                    s = safe * 2.0 - d * 0.02 + q.pos[0] * a * 0.01
                    if s > bs:
                        best, bs = q, s
                if best is not None and bs > 0.2 and best.dist_to(*k.pos) < pt.length * 0.45:
                    m.keeper_release(k, 'throw', (best.pos[0] + best.vel[0] * 0.5, best.pos[1] + best.vel[1] * 0.5))
                else:
                    fwd = max((q for q in t.active() if q is not k), key=lambda q: q.pos[0] * a)
                    m.keeper_release(k, 'punt', (fwd.pos[0], fwd.pos[1]))
            return
        self.hold_t = 0.0
        if k.busy():
            return
        # Shot coming? Read where it crosses our line
        threat = self._incoming(k)
        if threat is not None:
            ty, tz, tc = threat
            now = m.ticks
            if self.shot_seen is None:
                self.shot_seen = now
            seen = (now - self.shot_seen) / 60.0
            react = 0.06 + 0.22 * (1.0 - k.fb.reflexes) + 0.25 * t.ai_react
            if m.shootout or (m.restart and m.restart['kind'] == 'penalty' and m.restart.get('taken')
                              and b.last_touch is m.restart['taker']):
                react = 0.02
            if seen >= react:
                lateral = abs(ty - k.pos[1])
                spot_kick = m.shootout or (m.restart and m.restart['kind'] == 'penalty')
                if lateral > 0.55 or tz > 1.85:
                    if tc < 0.5 or spot_kick:
                        # Penalty: he has to go as it's struck, so it's mostly a guess
                        if spot_kick:
                            side = 1 if ty > 0 else -1
                            if m.rng.random() > 0.34 + 0.12 * k.fb.reflexes:
                                side = -side
                            ty = side * m.rng.uniform(0.4, 1.0) * m.pitch.goal_width / 2.0
                            tz = m.rng.uniform(0.3, 1.6)
                        m.keeper_dive(k, k.pos[0], ty, tz, tc)
                        return
                k.target = (gx + a * 0.4, max(-pt.goal_width / 2, min(pt.goal_width / 2, ty)))
                k.want_speed = k.top_speed()
            return
        self.shot_seen = None
        # Rush out on a 1-v-1 or to claim a loose ball in the box
        owner = b.owner
        in_box = pt.in_box(b.pos[0], b.pos[1], -a)
        if owner is None and b.holder is None and in_box:
            mine = m.time_to_ball(k)
            theirs = min((m.time_to_ball(o) for o in t.opp.active()), default=9.0)
            if mine < theirs + 0.15:
                q = b.predict(min(1.5, mine))
                k.target = (q[0], q[1])
                k.want_speed = k.top_speed()
                return
        if owner is not None and owner.team is not t:
            d_goal = math.hypot(owner.pos[0] - gx, owner.pos[1])
            covered = any(abs(q.pos[0] - gx) < abs(owner.pos[0] - gx) - 0.5 and
                          abs(q.pos[1] - owner.pos[1]) < 3.0 for q in t.active() if q is not k)
            if not covered and d_goal < pt.box_depth * 1.6:
                # Narrow the angle, then spread at his feet
                k.target = (owner.pos[0] + (gx - owner.pos[0]) * 0.3, owner.pos[1] * 0.8)
                k.want_speed = k.top_speed()
                # Spread at his feet when the ball is there to be taken
                if k.dist_to(b.pos[0], b.pos[1]) < 1.4 and m.rng.random() < dt * (2.0 + 2.0 * k.fb.keeping):
                    m.keeper_dive(k, b.pos[0], b.pos[1], 0.2, 0.2)
                return
        # Default: on the line between the ball and the middle of the goal
        bx, by = b.pos[0], b.pos[1]
        d = math.hypot(bx - gx, by)
        off = max(0.6, min(pt.box_depth * 0.35, 0.8 + d * 0.09))
        ux, uy = norm(bx - gx, by)
        k.target = (gx + ux * off, uy * off * 0.9)
        k.want_speed = k.top_speed() * 0.8
        k.plan = k.plan or {}
        k.plan['face'] = (bx, by)

    def _incoming(self, k):
        """(y, z, seconds) where a ball heading for our goal crosses the keeper's line, else None."""
        m = self.match
        b = m.ball
        pt = m.pitch
        a = self.team.attack
        if b.owner is not None or b.holder is not None:
            return None
        if b.vel[0] * a > -5.0:
            return None
        if b.last_touch is not None and b.last_touch.team is self.team:
            return None
        plane = k.pos[0]
        prev = tuple(b.pos)
        if (prev[0] - plane) * -a > 0:
            return None
        dt = 1.0 / 60.0
        for i, q in enumerate(b.path(1.2, dt)):
            if (q[0] - plane) * -a >= 0:
                f = (plane - prev[0]) / (q[0] - prev[0]) if q[0] != prev[0] else 0.0
                y = prev[1] + (q[1] - prev[1]) * f
                z = prev[2] + (q[2] - prev[2]) * f
                # Only bother with balls that would trouble the goal
                gl = pt.goal_width / 2.0 + 1.0
                if abs(y) < gl and z < pt.goal_height + 0.6:
                    return y, z, (i + 1) * dt
                return None
            prev = q
        return None
