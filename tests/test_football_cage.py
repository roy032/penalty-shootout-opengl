"""Cage football: passes played off the boards."""

import math

import pytest

from football.sim import ball as B
from football.sim.match import Input, Match


@pytest.mark.parametrize('sx,sy,tx,ty', [(-10, 0, 5, 2), (0, -5, 12, -6), (5, 0, -8, 0), (-18, -3, 10, -1)])
def test_bank_shot_reaches_its_target(sx, sy, tx, ty):
    m = Match('stars', 'legends', humans=(), seed=1)
    bk = m.bank_shot(sx, sy, tx, ty)
    assert bk is not None and abs(abs(bk['wall'][1]) - (m.pitch.half_width - B.RADIUS)) < 1e-6
    b = B.Ball(m.pitch)
    b.place(sx, sy)
    b.kick(math.cos(bk['angle']) * bk['speed'], math.sin(bk['angle']) * bk['speed'], 0.0)
    walls, closest = 0, 1e9
    for _ in range(300):
        walls += 'wall' in b.step(1 / 60)
        closest = min(closest, math.hypot(b.pos[0] - tx, b.pos[1] - ty))
    assert walls >= 1 and closest < 0.4


def test_no_bank_passes_without_walls():
    m = Match('stars', 'legends', settings=dict(pitch='fives'), humans=(), seed=1)
    assert m.bank_shot(-10, 0, 5, 2) is None


def blocked_setup():
    m = Match('stars', 'reds', settings=dict(difficulty='beginner'), humans=((0, 0),), seed=3)
    m.state = 'play'
    m.restart = None
    c = m.controllers[0]
    a = c.team.attack
    p, mate = c.team.players[2], c.team.players[3]
    c.player = p
    # Everyone else well out of the way, at the ends
    for i, q in enumerate(m.all_players()):
        q.pos = [(-a if q.team is c.team else a) * 19.0, (i % 3 - 1) * 6.0]
        q.vel = [0.0, 0.0]
    c.team.players[0].pos = [-a * 21.0, 0.0]
    c.team.opp.players[0].pos = [a * 21.0, 0.0]
    p.pos, mate.pos = [-a * 8.0, -4.0], [a * 8.0, -4.0]
    p.face_towards(*mate.pos)
    # A defender standing right in the passing lane
    o = c.team.opp.players[2]
    o.pos = [-a * 4.5, -4.0]
    m.ball.place(p.pos[0] + a * 0.5, -4.0)
    m.ball.owner = p
    return m, c, p, mate, a


def test_blocked_lane_in_the_cage_goes_off_the_boards():
    m, c, p, mate, a = blocked_setup()
    safe, bank = m.pass_lane(p, *mate.pos)
    assert bank is not None
    g = m.guide(c)
    assert g['pass_to'] is mate and g['bank'] is not None
    inp = Input()
    inp.move = (float(a), 0.0)
    inp.pressed = inp.held = {'pass'}
    evs = m.step({0: inp})
    assert any(e['type'] == 'bank' for e in evs)
    walls = 0
    got = None
    for _ in range(240):
        evs = m.step({0: Input()})
        walls += any(e['type'] == 'wall' for e in evs)
        if any(e['type'] in ('control', 'touch') for e in evs):
            got = m.ball.last_touch
            break
    assert walls >= 1 and got is not None and got.team is c.team


def test_open_lane_stays_a_straight_pass():
    m, c, p, mate, a = blocked_setup()
    c.team.opp.players[2].pos = [0.0, -12.0]
    assert m.pass_lane(p, *mate.pos)[1] is None
    assert m.guide(c)['bank'] is None
