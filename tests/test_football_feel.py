"""Forgiving inputs, directional first touches, team styles and the soak harness."""

import math

from football.sim import soak
from football.sim import match as M
from football.sim.match import Input, Match
from football.sim.styles import STYLES, TEAM_STYLES, style_for
from football.sim import roster


def human_match(**settings):
    m = Match('stars', 'reds', settings=dict(difficulty='beginner', **settings), humans=((0, 0),), seed=3)
    m.state = 'play'
    m.restart = None
    c = m.controllers[0]
    p = c.team.players[2]
    c.player = p
    a = c.team.attack
    # Clear everyone else out of the way
    for q in m.all_players():
        if q is not p:
            q.pos = [q.pos[0], 12.0 if q.team is c.team else -12.0]
    p.pos = [0.0, 0.0]
    p.facing = 0.0 if a > 0 else math.pi
    return m, c, p, a


def press(*actions, move=(0.0, 0.0), held=()):
    inp = Input()
    inp.move = move
    inp.pressed = set(actions)
    inp.held = set(actions) | set(held)
    return inp


def test_pass_pressed_just_after_a_knock_on_still_plays_the_ball():
    m, c, p, a = human_match()
    m.ball.place(a * 0.5, 0.0)
    m.ball.owner = p
    m.step({0: Input()})
    assert c.owned_tick == m.ticks
    # The sprint knock-on: the ball runs a yard ahead of him
    m.ball.owner = None
    m.ball.kick(a * 6.0, 0.0, 0.0)
    m.ball.last_touch = p
    p.touch_cd = 0.2
    m.step({0: Input()})
    evs = m.step({0: press('pass')})
    assert any(e['type'] == 'pass' for e in evs)


def test_a_late_press_after_the_grace_window_does_not():
    m, c, p, a = human_match()
    m.ball.place(a * 0.5, 0.0)
    m.ball.owner = p
    m.step({0: Input()})
    m.ball.owner = None
    m.ball.kick(a * 6.0, 0.0, 0.0)
    m.ball.last_touch = p
    p.touch_cd = 1.0
    for _ in range(int(M.LATE_GRACE * 60) + 3):
        m.step({0: Input()})
    evs = m.step({0: press('pass')})
    assert not any(e['type'] == 'pass' for e in evs)
    assert c.queued is not None, 'it waits as a first-time pass instead'


def incoming(m, p, a, speed=8.0):
    """A pass rolling straight at p's feet from in front of him."""
    m.ball.place(p.pos[0] + a * 2.0, p.pos[1])
    m.ball.kick(-a * speed, 0.0, 0.0)
    m.ball.last_touch = None


def receive(m, inp, ticks=40):
    evs = []
    for _ in range(ticks):
        evs += m.step({0: inp})
        if any(e['type'] in ('control', 'touch') for e in evs):
            break
    return evs


def test_stick_across_the_body_turns_with_the_first_touch():
    m, c, p, a = human_match()
    incoming(m, p, a)
    hold = Input()
    hold.move = (0.0, 1.0)
    evs = receive(m, hold)
    touch = [e for e in evs if e['type'] == 'touch']
    assert touch and touch[0].get('push')
    vx, vy = m.ball.vel[0], m.ball.vel[1]
    assert vy > 3.0 and abs(vx) < vy, 'the ball goes the way the stick points'
    # He doesn't keep pushing it away every time he catches up with it
    for _ in range(90):
        m.step({0: hold})
        if m.ball.owner is p:
            break
    assert m.ball.owner is p


def test_stick_left_alone_kills_it_dead():
    m, c, p, a = human_match()
    incoming(m, p, a)
    evs = receive(m, Input())
    assert any(e['type'] == 'control' for e in evs)
    assert m.ball.owner is p


def test_sprinting_onto_it_knocks_it_into_space():
    m, c, p, a = human_match()
    incoming(m, p, a, speed=6.0)
    run = Input()
    run.move = (float(a), 0.0)
    run.held = {'sprint'}
    evs = receive(m, run)
    touch = [e for e in evs if e['type'] == 'touch']
    assert touch and touch[0].get('push')
    assert m.ball.vel[0] * a > 4.0


def test_tackle_pressed_a_moment_early_still_goes_in():
    m, c, p, a = human_match()
    o = c.team.opp.players[2]
    o.pos = [a * 1.0, 0.0]
    o.face_towards(*p.pos)
    m.ball.place(a * 0.6, 0.0)
    m.ball.last_touch = None
    # Pressed while the ball is still loose...
    m.step({0: press('pass')})
    assert c.tackle_t > 0
    # ...then the opponent takes his touch
    m.ball.owner = o
    c.queued = None
    seen = False
    for _ in range(int(M.EARLY_TACKLE * 60) - 2):
        m.step({0: Input()})
        seen = seen or p.state == 'tackle'
    assert seen


def test_every_team_has_a_style():
    for tid in roster.team_ids():
        st = style_for(tid)
        assert st['key'] in STYLES and 'label' in st
    assert set(TEAM_STYLES.values()) == set(STYLES), 'each character team plays a different way'
    m = Match('legends', 'cult', humans=(), seed=1)
    assert m.teams[0].style['key'] == 'possession' and m.teams[1].style['key'] == 'lowblock'
    assert m.ai[0].style is m.teams[0].style


def test_styles_change_how_a_team_plays():
    """Same squad on both sides: the possession side passes far more than the low block."""
    passes = {'possession': 0, 'lowblock': 0}
    for seed in (1, 2):
        r = soak.play('blues', 'blues', dict(size=11, pitch='full', half_seconds=60.0, decider='none',
                                             styles=('possession', 'lowblock')), seed=seed)
        assert not r['problems']
        passes['possession'] += r['teams'][0]['passes']
        passes['lowblock'] += r['teams'][1]['passes']
    assert passes['possession'] > passes['lowblock'] * 1.3


def test_soak_runs_a_clean_match_and_reports_numbers():
    r = soak.play('stars', 'legends', dict(half_seconds=30.0), seed=5)
    assert r['problems'] == []
    assert r['minutes'] > 0.9
    assert all(k in r['teams'][0] for k in ('goals', 'shots', 'passes', 'possession', 'tackles'))
    s = soak.summarise([r])
    assert s['matches'] == 1 and s['goals_per_match'] == r['teams'][0]['goals'] + r['teams'][1]['goals']


def test_soak_reports_a_crash_with_its_seed(monkeypatch):
    real = Match.step

    def broken(self, inputs=None, dt=M.FIXED_DT):
        if self.ticks > 100:
            raise IndexError('boom')
        return real(self, inputs, dt)
    monkeypatch.setattr(Match, 'step', broken)
    r = soak.play('stars', 'legends', dict(half_seconds=30.0), seed=77)
    assert [p['kind'] for p in r['problems']] == ['crash'] and r['problems'][0]['seed'] == 77


def test_soak_spots_a_dead_ball(monkeypatch):
    monkeypatch.setattr(soak, 'STILL_LIMIT', 1.0)
    real = Match.step

    def frozen(self, inputs=None, dt=M.FIXED_DT):
        evs = real(self, inputs, dt)
        if self.state == 'play' and self.ticks > 300:
            # A ball that nobody will ever go and get
            self.ball.owner = self.ball.holder = None
            self.ball.place(0.0, self.pitch.half_width - 0.2)
        return evs
    monkeypatch.setattr(Match, 'step', frozen)
    r = soak.play('stars', 'legends', dict(half_seconds=20.0), seed=1)
    assert 'ball_still' in [p['kind'] for p in r['problems']]


def test_a_side_is_never_sent_down_below_the_minimum():
    m = Match('stars', 'legends', humans=(), seed=1)
    t = m.teams[0]
    victim = m.teams[1].players[2]
    for p in t.players[1:]:
        p.yellow = 1
        m._foul(p, victim, severity=0.9)
    assert len(t.active()) == m.min_players() == 3
    assert m._kickoff_taker(t) is not None


def test_guides_show_the_pass_target_and_the_next_switch():
    m, c, p, a = human_match()
    mate = c.team.players[3]
    mate.pos = [a * 8.0, 0.5]
    m.ball.place(a * 0.5, 0.0)
    m.ball.owner = p
    c.move = (float(a), 0.0)
    g = m.guide(c)
    assert g['pass_to'] is mate
    assert g['through'] is not None and g['through'][0] is mate
    assert g['switch'] is None
    # Defending: the guide names the team-mate a switch would pick
    o = c.team.opp.players[2]
    m.ball.owner = o
    o.pos = [a * 9.0, 0.5]
    m.ball.place(o.pos[0], o.pos[1])
    g = m.guide(c)
    assert g['pass_to'] is None and g['switch'] is m.switch_target(c, (0.0, 0.0))


def test_offside_guide_only_on_authentic_full_pitches():
    m, c, p, a = human_match()
    m.ball.place(a * 0.5, 0.0)
    m.ball.owner = p
    assert m.guide(c)['offside'] is None
    m = Match('stars', 'legends', settings=dict(size=11, pitch='full', preset='authentic'), humans=((0, 0),),
              seed=2)
    m.state = 'play'
    m.restart = None
    c = m.controllers[0]
    p = c.team.players[6]
    c.player = p
    a = c.team.attack
    p.pos = [a * 5.0, 0.0]
    m.ball.place(p.pos[0] + a * 0.5, 0.0)
    m.ball.owner = p
    for i, o in enumerate(c.team.opp.active()):
        o.pos = [a * (50.0 if o.keeper else 20.0 + i * 0.1), o.pos[1]]
    c.team.players[9].pos = [a * 18.0, 2.0]
    line = m.guide(c)['offside']
    assert line is not None and abs(line * a - sorted((o.pos[0] * a for o in c.team.opp.active()))[-2]) < 1e-6
