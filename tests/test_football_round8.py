"""Weather, fingertip saves, give-and-go, AI game management and determinism."""

import hashlib
import math

import pytest

from football.sim import soak
from football.sim.ball import Ball
from football.sim.match import ONE_TWO_HOLD, Input, Match
from football.sim.pitch import PITCHES
from football.sim.weather import WEATHER, pick


def roll_distance(friction):
    b = Ball(PITCHES['full']())
    b.friction = friction
    b.kick(10.0, 0.0, 0.0)
    for _ in range(600):
        b.step(1 / 60)
    return b.pos[0]


def test_rain_skids_and_snow_holds_the_ball_up():
    dry = roll_distance(WEATHER['clear']['friction'])
    assert roll_distance(WEATHER['rain']['friction']) > dry * 1.1
    assert roll_distance(WEATHER['snow']['friction']) < dry * 0.8


def test_wind_carries_a_lofted_ball():
    def landing(wind):
        b = Ball(PITCHES['full']())
        b.wind = wind
        b.kick(14.0, 0.0, 12.0)
        for _ in range(240):
            b.step(1 / 60)
            if b.pos[2] <= 0.12 and b.vel[2] == 0.0:
                break
        return b.pos
    calm, side = landing((0.0, 0.0)), landing((0.0, 7.0))
    assert abs(calm[1]) < 0.01 and side[1] > 1.0


def test_weather_is_picked_once_per_match_and_reaches_the_ball():
    m = Match('stars', 'legends', settings=dict(weather='rain'), humans=(), seed=4)
    assert m.weather['key'] == 'rain' and m.ball.friction == WEATHER['rain']['friction']
    assert m.ball.skid == WEATHER['rain']['skid']
    import random
    keys = {pick('random', random.Random(i))['key'] for i in range(40)}
    assert keys == set(WEATHER)
    w = pick('wind', random.Random(1))
    assert 5.0 <= w['wind_speed'] <= 8.0 and abs(math.hypot(*w['wind_vec']) - w['wind_speed']) < 1e-9


def test_same_seed_same_weather_and_it_does_not_change_the_squads():
    a = Match('stars', 'legends', settings=dict(weather='random'), humans=(), seed=9)
    b = Match('stars', 'legends', settings=dict(weather='random'), humans=(), seed=9)
    c = Match('stars', 'legends', settings=dict(weather='clear'), humans=(), seed=9)
    assert a.weather == b.weather
    assert [p.fb.name for p in a.all_players()] == [p.fb.name for p in c.all_players()]


@pytest.mark.parametrize('w', ['rain', 'snow', 'wind'])
def test_matches_in_every_weather_play_cleanly(w):
    r = soak.play('stars', 'legends', dict(half_seconds=30.0, weather=w), seed=3)
    assert r['problems'] == []


def test_a_diving_keeper_can_tip_it_behind_for_a_corner():
    tips, corners, own_goals = 0, 0, 0
    for seed in range(30):
        m = Match('stars', 'legends', settings=dict(size=11, pitch='full'), humans=(), seed=seed)
        m.state = 'play'
        m.restart = None
        gx = m.teams[0].opp_goal_x(m.pitch)
        m.teams[1].keeper().pos = [gx - 0.8, 0.0]
        m.ball.place(gx - 11.0, 0.0, 0.3)
        m.ball.kick(27.0, 3.0, 3.5)
        m.ball.last_touch = m.teams[0].players[9]
        tipped = False
        for _ in range(240):
            evs = m.step({})
            tipped = tipped or any(e['type'] == 'parry' and e.get('tip') for e in evs)
            if tipped and any(e['type'] == 'out' and e['kind'] == 'corner' for e in evs):
                corners += 1
            if tipped and any(e['type'] == 'goal' for e in evs):
                own_goals += 1
            if m.state != 'play':
                break
        tips += tipped
    assert tips >= 5 and corners >= tips * 0.7 and own_goals == 0


def give_and_go():
    m = Match('stars', 'reds', settings=dict(difficulty='beginner'), humans=((0, 0),), seed=3)
    m.state = 'play'
    m.restart = None
    c = m.controllers[0]
    a = c.team.attack
    p, mate = c.team.players[2], c.team.players[3]
    for i, q in enumerate(m.all_players()):
        q.pos = [(-a if q.team is c.team else a) * 19.0, (i % 3 - 1) * 6.0]
    c.team.players[0].pos = [-a * 21.0, 0.0]
    c.team.opp.players[0].pos = [a * 21.0, 0.0]
    p.pos, mate.pos = [0.0, 0.0], [a * 7.0, 0.0]
    p.face_towards(*mate.pos)
    m.ball.place(a * 0.5, 0.0)
    m.ball.owner = p
    c.player = p
    return m, c, p, mate, a


def hold(*keys, pressed=()):
    inp = Input()
    inp.held = set(keys) | set(pressed)
    inp.pressed = set(pressed)
    return inp


def test_hold_pass_after_passing_sends_the_passer_and_release_returns_it():
    m, c, p, mate, a = give_and_go()
    m.step({0: hold(pressed=('pass',))})
    assert c.player is mate and c.one_two is not None
    start = p.pos[0] * a
    for _ in range(int(ONE_TWO_HOLD * 60) + 30):
        m.step({0: hold('pass')})
    assert p.pos[0] * a > start + 2.0, 'the passer bursts forward'
    evs = []
    inp = Input()
    inp.released = {'pass'}
    evs += m.step({0: inp})
    for _ in range(90):
        evs += m.step({0: Input()})
        if any(e['type'] == 'one_two' for e in evs):
            break
    ret = [e for e in evs if e['type'] == 'one_two']
    assert ret and ret[0]['to'] == m._idx(p)


def test_a_quick_tap_is_just_a_pass():
    m, c, p, mate, a = give_and_go()
    m.step({0: hold(pressed=('pass',))})
    evs = []
    for _ in range(60):
        evs += m.step({0: Input()})
    assert c.one_two is None and p.run_t <= 0
    assert not any(e['type'] == 'one_two' for e in evs)


def late(m, home, away, half=2):
    m.half = half
    m.time = m.half_length() * 0.95
    m.teams[0].score, m.teams[1].score = home, away


def test_leading_late_the_ai_runs_the_clock_down():
    m = Match('stars', 'legends', humans=(), seed=2)
    late(m, 1, 0)
    assert m.ai[0].game_state() == 'protect' and m.ai[1].game_state() == 'chase'
    late(m, 1, 1)
    assert m.ai[0].game_state() is None
    late(m, 1, 0, half=1)
    assert m.ai[0].game_state() is None
    # Its free kicks take noticeably longer
    m = Match('stars', 'legends', humans=(), seed=2)
    m.state = 'play'
    m.restart = None
    late(m, 2, 0)
    m.set_piece('freekick', m.teams[0], -5.0, 3.0)
    evs, t = [], 0
    while not m.restart.get('taken') and t < 600:
        evs += m.step({})
        t += 1
    assert any(e['type'] == 'time_waste' for e in evs) and t > 3.0 * 60


def test_keeper_goes_up_for_a_last_minute_corner_when_behind():
    m = Match('stars', 'legends', humans=(), seed=2)
    m.state = 'play'
    m.restart = None
    late(m, 0, 1)
    m.time = m.half_length() * 0.97
    t = m.teams[0]
    k = t.keeper()
    m.set_piece('corner', t, t.attack * m.pitch.half_length, m.pitch.half_width)
    evs = []
    for _ in range(90):
        evs += m.step({})
    assert any(e['type'] == 'keeper_up' for e in evs)
    assert k.pos[0] * t.attack > -m.pitch.half_length + 5.0, 'he has left his goal'


def state_hash(m):
    h = hashlib.sha1()
    for p in m.all_players():
        h.update(('%.6f %.6f %s' % (p.pos[0], p.pos[1], p.state)).encode())
    h.update(('%.6f %.6f %.6f %d %d' % (*m.ball.pos, m.teams[0].score, m.teams[1].score)).encode())
    return h.hexdigest()


def scripted(seed, ticks=60 * 40):
    """A match with a human whose inputs come from a fixed script; a hash every second."""
    m = Match('stars', 'legends', settings=dict(weather='random'), humans=((0, 0),), seed=seed)
    out = []
    for i in range(ticks):
        inp = Input()
        ph = i // 30
        inp.move = (math.cos(ph * 1.3), math.sin(ph * 0.7))
        if i % 47 == 0:
            inp.pressed = {'pass'}
            inp.held = {'pass'}
        elif i % 113 == 0:
            inp.pressed = {'shoot'}
            inp.held = {'shoot'}
        m.step({0: inp})
        if i % 60 == 0:
            out.append(state_hash(m))
    return out


def test_same_seed_and_inputs_give_the_same_match():
    """The groundwork for lockstep online and input-log replays: no hidden randomness or ordering."""
    a, b = scripted(11), scripted(11)
    assert a == b
    assert scripted(12) != a
