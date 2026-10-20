"""Headless tests for the football match engine (no Panda3D needed)."""

import math

import pytest

from football.sim import ball as B
from football.sim import roster
from football.sim.match import Input, Match
from football.sim.pitch import PITCHES


def run(m, seconds, inputs=None):
    evs = []
    for _ in range(int(seconds * 60)):
        evs += m.step(inputs or {})
        if m.state == 'fulltime':
            break
    return evs


def test_roll_speed_reaches_target():
    for d in (5.0, 12.0, 25.0):
        v = B.roll_speed_for(d, 3.0)
        assert abs(B.roll_distance(v, 3.0) - d) < 0.05


def test_ball_rolls_to_a_stop_and_bounces():
    b = B.Ball(PITCHES['full']())
    b.kick(8.0, 0.0, 0.0)
    for _ in range(600):
        b.step(1 / 60)
    assert b.ground_speed() < 0.05
    b.place(0, 0, 3.0)
    evs = []
    for _ in range(120):
        evs += b.step(1 / 60)
    assert 'bounce' in evs and b.pos[2] < 1.0


def test_shot_into_the_net_is_a_goal_and_over_the_bar_is_not():
    pt = PITCHES['fives']()
    b = B.Ball(pt)
    b.place(pt.half_length - 6, 0.0)
    b.kick(20.0, 0.0, 2.0)
    side = 0
    for _ in range(120):
        b.step(1 / 60)
        side = side or b.goal_side()
    assert side == 1
    b.place(pt.half_length - 6, 0.0)
    b.kick(20.0, 0.0, 9.0)
    side = 0
    for _ in range(120):
        b.step(1 / 60)
        side = side or b.goal_side()
    assert side == 0


def test_cage_walls_keep_the_ball_in():
    pt = PITCHES['cage']()
    b = B.Ball(pt)
    b.kick(0.0, 15.0, 0.0)
    for _ in range(240):
        b.step(1 / 60)
        assert abs(b.pos[1]) <= pt.half_width
    assert b.out_of_play() is None


def test_squads_have_a_keeper_and_unique_numbers():
    for tid in roster.team_ids():
        for size in (5, 7, 11):
            sq = roster.squad(tid, size)
            assert len(sq) == size and sq[0].keeper
            assert len({p.number for p in sq}) == size


@pytest.mark.parametrize('fmt', ['cage', 'fives', 'sevens', 'full'])
def test_cpu_match_plays_to_full_time(fmt):
    size = {'cage': 5, 'fives': 5, 'sevens': 7, 'full': 11}[fmt]
    m = Match('stars', 'legends', settings=dict(size=size, pitch=fmt, half_seconds=20, decider='none'), humans=(),
              seed=4)
    evs = run(m, 80)
    assert m.state == 'fulltime'
    kinds = {e['type'] for e in evs}
    assert {'pass', 'control', 'halftime', 'fulltime'} <= kinds
    assert m.teams[0].stats['passes'] + m.teams[1].stats['passes'] > 5


def test_same_seed_same_match():
    a = Match('stars', 'legends', settings=dict(half_seconds=15), humans=(), seed=11)
    b = Match('stars', 'legends', settings=dict(half_seconds=15), humans=(), seed=11)
    run(a, 20)
    run(b, 20)
    assert a.ball.pos == b.ball.pos
    assert (a.teams[0].score, a.teams[1].score) == (b.teams[0].score, b.teams[1].score)


def test_shootout_finishes_with_a_winner():
    for seed in range(4):
        m = Match('stars', 'legends', humans=(), seed=seed)
        m.start_shootout()
        run(m, 150)
        assert m.state == 'fulltime' and m.winner is not None
        a, b = m.teams[0].pens, m.teams[1].pens
        assert sum(a) != sum(b)
        assert abs(len(a) - len(b)) <= 1


def test_human_can_pass_and_shoot():
    m = Match('stars', 'reds', settings=dict(difficulty='beginner'), humans=((0, 0),), seed=1)
    c = m.controllers[0]
    inp = Input()
    inp.held = {'pass'}
    inp.pressed = {'pass'}
    evs = m.step({0: inp})
    assert any(e['type'] == 'pass' for e in evs), 'kick-off pass'
    # Give the ball to the controlled player in front of goal and shoot
    run(m, 0.5)
    p = c.player
    gx = c.team.attack * m.pitch.half_length
    p.pos = [gx - c.team.attack * 8.0, 0.0]
    p.face_towards(gx, 0)
    m.ball.place(p.pos[0] + c.team.attack * 0.5, 0.0)
    m.ball.owner = p
    m.state = 'play'
    hold = Input()
    hold.held = {'shoot'}
    hold.pressed = {'shoot'}
    m.step({0: hold})
    hold.pressed = set()
    for _ in range(30):
        m.step({0: hold})
    rel = Input()
    rel.released = {'shoot'}
    evs = m.step({0: rel})
    assert any(e['type'] == 'shot' for e in evs)


def test_offside_is_flagged_on_authentic_full_pitch():
    m = Match('stars', 'legends', settings=dict(size=11, pitch='full', preset='authentic'), humans=(), seed=2)
    assert m.settings['offside']
    run(m, 0.2)
    att = m.teams[0]
    passer = att.players[6]
    runner = att.players[9]
    a = att.attack
    m.state = 'play'
    m.restart = None
    passer.pos = [0.0, 0.0]
    m.ball.place(a * 0.5, 0.0)
    m.ball.owner = passer
    for o in att.opp.active():
        o.pos = [a * 10.0 if not o.keeper else a * 50.0, o.pos[1]]
    runner.pos = [a * 25.0, 3.0]
    m.do_pass(passer, None, 'ground', receiver=runner)
    assert runner in m.offside_set


def test_rebind_swaps_keys(tmp_path):
    from football.view import inputs as I

    class FakeInputs(I.Inputs):
        def __init__(self, path):
            self.path = path
            self.keys = [dict(k) for k in I.DEFAULT_KEYS]
            self.handles = [{}, {}]

        def _compile(self):
            pass
    fi = FakeInputs(str(tmp_path / 'c.json'))
    fi.rebind(0, 'pass', 'k')
    assert fi.keys[0]['pass'] == 'k' and fi.keys[0]['shoot'] == 'j'
    fi2 = FakeInputs(str(tmp_path / 'c.json'))
    I.Inputs.load(fi2)
    assert fi2.keys[0]['pass'] == 'k'


def test_xg_is_higher_close_to_goal():
    m = Match('stars', 'legends', humans=(), seed=1)
    t = m.teams[0]
    gx = t.opp_goal_x(m.pitch)
    near = m.xg(gx - t.attack * 4, 0, t)
    far = m.xg(gx - t.attack * 18, 0, t)
    wide = m.xg(gx - t.attack * 4, 9, t)
    assert near > far and near > wide
