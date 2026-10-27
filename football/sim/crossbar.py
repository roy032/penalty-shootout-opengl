"""Crossbar challenge: a minute to hit the woodwork from the edge of the box.

Just you, a ball and an empty goal. Each kick is placed somewhere new; the bar
scores 3, a post 1, and in off the woodwork 1 more. A clean goal or a miss
scores nothing. Uses the normal Match and shooting, so it teaches power and
height for the real thing."""

import random

from .match import FIXED_DT, Match

DURATION = 60.0
POINTS = {'bar': 3, 'post': 1}
IN_OFF = 1


class Crossbar:
    def __init__(self, team='stars', seed=None):
        self.rng = random.Random(seed)
        m = Match(team, 'reds', settings=dict(size=11, pitch='full', fouls=False, cards=False, weather='clear',
                                              half_seconds=1.0e6, decider='none', rules=False),
                  humans=((0, 0),), seed=seed)
        self.m = m
        t = m.teams[0]
        outs = [p for p in t.players if not p.keeper]
        self.striker = max(outs, key=lambda p: p.fb.shooting)
        for p in m.all_players():
            if p is not self.striker:
                m._send_off(p)
        self.score = 0
        self.time = 0.0
        self.kicks = []          # (kind, points) per kick: 'bar', 'post', 'in_off', 'goal' or 'miss'
        self.flight = None
        self.done = False
        self._spot()

    def _spot(self):
        m = self.m
        pt = m.pitch
        a = m.teams[0].attack
        gx = a * pt.half_length
        d = self.rng.uniform(15.0, 20.0)
        y = self.rng.uniform(-9.0, 9.0)
        x = gx - a * d
        m.state = 'play'
        m.restart = None
        for t in m.teams:
            t.score = 0
        m.ball.place(x, y)
        s = self.striker
        s.pos = [x - a * 0.5, y]
        s.vel = [0.0, 0.0]
        s.state = 'run'
        s.target = None
        s.face_towards(gx, 0.0)
        m.ball.owner = s
        m.ball.last_touch = s
        c = m.controllers[0]
        c.player = s
        c.charge = None
        self.flight = None

    def step(self, inputs):
        """One tick. Returns the match events plus 'cb_hit' / 'cb_kick' / 'cb_over' of its own."""
        if self.done:
            return []
        m = self.m
        evs = list(m.step(inputs))
        self.time += FIXED_DT
        out = []
        for e in evs:
            if e['type'] == 'shot' and self.flight is None:
                self.flight = dict(t=0.0, hit=None, goal=False)
            elif e['type'] == 'woodwork' and self.flight is not None and self.flight['hit'] is None:
                self.flight['hit'] = e['kind']
                out.append(dict(type='cb_hit', kind=e['kind'], points=POINTS[e['kind']]))
            elif e['type'] == 'goal' and self.flight is not None:
                self.flight['goal'] = True
        f = self.flight
        if f is not None and m.ball.goal_side():
            f['goal'] = True
        if f is not None:
            f['t'] += FIXED_DT
            b = m.ball
            settled = f['t'] > 0.8 and b.speed() < 1.0
            if f['t'] > 2.6 or settled or (m.state != 'play' and f['t'] > 1.2):
                hit = f['hit']
                pts = POINTS.get(hit, 0) + (IN_OFF if hit and f['goal'] else 0)
                kind = ('in_off' if f['goal'] else hit) if hit else ('goal' if f['goal'] else 'miss')
                self.kicks.append((kind, pts))
                self.score += pts
                out.append(dict(type='cb_kick', kind=kind, points=pts, total=self.score))
                if self.time >= DURATION:
                    self.done = True
                    out.append(dict(type='cb_over', score=self.score))
                else:
                    self._spot()
        elif self.time >= DURATION:
            self.done = True
            out.append(dict(type='cb_over', score=self.score))
        elif m.ball.owner is not self.striker and m.ball.speed() < 0.5 and m.state == 'play':
            # Dribbled off and lost it: put it back
            self._spot()
        elif m.state != 'play':
            self._spot()
        return evs + out

    def time_left(self):
        return max(0.0, DURATION - self.time)
