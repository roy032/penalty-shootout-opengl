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


def test_a_recorded_match_replays_exactly_through_json():
    import json
    from football.sim import inputlog
    cfg = dict(size=5, pitch='cage', half_seconds=20.0, weather='random', perks=('boots',))
    m = Match('stars', 'legends', settings=cfg, humans=((0, 0), (1, 1)), seed=21)
    rec = inputlog.Recorder('stars', 'legends', cfg, ((0, 0), (1, 1)), 21)
    hashes = []
    i = 0
    prev = {0: set(), 1: set()}
    while m.state != 'fulltime' and i < 60 * 80:
        inputs = {}
        for c in (0, 1):
            inp = Input()
            ph = (i + c * 17) // 25
            inp.move = (math.cos(ph * 1.7 + c) * 0.73219, math.sin(ph * 0.9) * 0.51177)
            held = set()
            if (i + c * 5) % 41 < 3:
                held.add('pass')
            if (i + c * 11) % 97 < 20:
                held.add('shoot')
            if (i // 60) % 3 == c:
                held.add('sprint')
            inp.held, inp.pressed, inp.released = held, held - prev[c], prev[c] - held
            prev[c] = held
            inputs[c] = inputlog.quantize(inp)
        rec.add(inputs)
        m.step(inputs)
        if i % 30 == 0:
            hashes.append(state_hash(m))
        i += 1
    log = json.loads(json.dumps(rec.to_dict(m)))
    assert log['result']['score'] == [m.teams[0].score, m.teams[1].score]
    import gzip
    assert len(gzip.compress(json.dumps(log).encode())) < 40000, 'small enough to keep every match'
    r = inputlog.Reader(log)
    m2 = inputlog.make_match(log)
    again = []
    j = 0
    while not r.done:
        m2.step(r.next())
        if j % 30 == 0:
            again.append(state_hash(m2))
        j += 1
    assert again == hashes and m2.state == m.state


def test_replays_are_saved_listed_and_pruned(tmp_path, monkeypatch):
    from football.sim import inputlog
    monkeypatch.setattr(inputlog, 'KEEP', 3)
    rec = inputlog.Recorder('stars', 'legends', {}, ((0, 0),), 5)
    rec.add({0: Input()})
    paths = []
    import time as T
    for k in range(5):
        monkeypatch.setattr(T, 'strftime', lambda f, k=k: '2026102%d-000000' % k if '%H%M%S' in f else 'x')
        paths.append(inputlog.save(rec.to_dict(), str(tmp_path)))
    left = inputlog.listing(str(tmp_path))
    assert len(left) == 3 and left[0] == paths[-1]
    assert inputlog.load(left[0])['seed'] == 5


def finished(home='reds', away='legends', goals=(), settings=None, pens=None):
    """A Match marked finished with the given goals [(team, name, own)]."""
    m = Match(home, away, settings=settings, humans=((0, 0),), seed=1)
    for t, name, own in goals:
        m.teams[t].score += 1
        m.log.append(dict(kind='goal', team=t, name=name, own=own, minute=10))
    m.half = 2
    if pens:
        m.start_shootout()
        m.teams[0].pens, m.teams[1].pens = list(pens[0]), list(pens[1])
    a, b = m.teams
    m.winner = a if (a.score, sum(a.pens)) > (b.score, sum(b.pens)) else (b if (a.score, sum(a.pens)) <
                                                                                (b.score, sum(b.pens)) else None)
    m.state = 'fulltime'
    return m


def test_challenges_from_a_finished_match():
    from football.sim import challenges as C
    m = finished(goals=[(1, 'PELE', False), (1, 'PELE', False), (0, 'X', False), (0, 'Y', False), (0, 'X', False)])
    done = C.check(m)
    assert {'first_win', 'giant_killer', 'comeback'} <= done and 'hat_trick' not in done
    m = finished('legends', 'reds', goals=[(0, 'HENRY', False)] * 3,
                 settings=dict(pitch='cage', difficulty='legendary', weather='snow'))
    done = C.check(m)
    assert {'first_win', 'hat_trick', 'fortress', 'snow_day'} <= done and 'giant_killer' not in done
    m = finished(pens=([1, 1, 1], [0, 0, 1]))
    assert 'ice_cold' in C.check(m)
    assert C.check(finished(goals=[(1, 'PELE', False)])) == set()
    assert 'champions' in C.check(finished(goals=[(0, 'X', False)]), cup_won=True)
    # Nobody to credit when both sides are human
    m = Match('stars', 'legends', humans=((0, 0), (1, 1)), seed=1)
    assert C.check(m) == set()


def test_dream_team_is_hidden_until_unlocked():
    from football.sim import challenges as C, roster
    assert 'dream' not in roster.team_ids()
    assert 'dream' in roster.team_ids(C.rewards(C.IDS[:5]))
    assert C.rewards(C.IDS[:2]) == set() and C.rewards(C.IDS[:3]) == {'golden_ball'}
    squad = roster.squad('dream', 11)
    assert squad[0].keeper and len({p.number for p in squad}) == 11


def test_goals_are_labelled_by_how_they_came():
    m = Match('stars', 'legends', humans=(), seed=1)
    t = m.teams[0]
    m.last_pass = dict(team=0, kind='through', tick=m.ticks)
    assert m._goal_type(t, False) == 'through'
    m.shot_from = dict(team=0, x=t.opp_goal_x(m.pitch) - t.attack * 15.0, y=0.0, tick=m.ticks, header=False)
    assert m._goal_type(t, False) == 'long'
    assert m._goal_type(t, True) == 'own'


def test_a_side_carved_open_by_through_balls_drops_deeper_at_half_time():
    m = Match('stars', 'legends', humans=((0, 0),), seed=1)
    cpu = m.ai[1]
    line0 = cpu.style['line']
    for _ in range(2):
        m.teams[0].score += 1
        m.log.append(dict(kind='goal', team=0, name='X', own=False, minute=5, how='through'))
    evs = []
    m.events = evs
    assert cpu.half_time_talk() == 'deeper' and cpu.style['line'] < line0
    assert m.teams[1].style is cpu.style
    assert any(e['type'] == 'tactics' for e in m.events)
    assert m.ai[0].half_time_talk() is None, 'the human side picks its own tactics'


def test_behind_with_nothing_obvious_the_ai_goes_for_it():
    m = Match('stars', 'legends', humans=(), seed=1)
    cpu = m.ai[1]
    fwd = cpu.style['forward']
    m.teams[0].score = 1
    m.log.append(dict(kind='goal', team=0, name='X', own=False, minute=5, how='close'))
    assert cpu.half_time_talk() == 'attack' and cpu.style['forward'] > fwd
    assert m.ai[0].half_time_talk() is None, 'winning sides leave it alone'


def test_keeper_out_sends_the_keeper_at_the_ball():
    m = Match('stars', 'reds', settings=dict(difficulty='beginner'), humans=((0, 0),), seed=3)
    m.state = 'play'
    m.restart = None
    c = m.controllers[0]
    a = c.team.attack
    k = c.team.keeper()
    o = c.team.opp.players[3]
    for q in m.all_players():
        if q is not k:
            q.pos = [q.pos[0], 12.0]
    k.pos = [-a * (m.pitch.half_length - 1.0), 0.0]
    o.pos = [-a * (m.pitch.half_length - 9.0), 0.0]
    m.ball.place(o.pos[0], 0.0)
    m.ball.owner = o
    c.player = c.team.players[2]
    start = k.dist_to(*o.pos)
    evs = []
    for _ in range(60):
        o.pos = [-a * (m.pitch.half_length - 9.0), 0.0]
        m.ball.place(o.pos[0] + a * -0.4, 0.0)
        m.ball.owner = o
        evs += m.step({0: hold('lob')})
    assert any(e['type'] == 'keeper_rush' for e in evs)
    assert k.dist_to(*o.pos) < start - 3.0
