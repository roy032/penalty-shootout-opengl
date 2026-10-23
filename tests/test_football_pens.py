"""Spot kicks in Ultimate Football: the classic aim-and-power penalty."""

import statistics

from football.sim.match import PEN_SWEET, Input, Match


def pen_match(humans=((0, 0),), against=False, seed=2):
    """A match lined up for a penalty: to the human's team, or against it."""
    m = Match('stars', 'legends', settings=dict(difficulty='pro'), humans=humans, seed=seed)
    team = m.teams[1] if against else m.teams[0]
    m.set_piece('penalty', team, *m.pitch.spot_pos(team.attack))
    return m, team


def step(m, move=(0.0, 0.0), pressed=(), held=(), released=()):
    inp = Input()
    inp.move = move
    inp.pressed, inp.held, inp.released = set(pressed), set(held) | set(pressed), set(released)
    return m.step({0: inp})


def test_stick_moves_the_aim_on_the_goal_mouth():
    m, team = pen_match()
    c = m.controllers[0]
    step(m)
    assert c.pen_aim == [0.0, 0.9]
    for _ in range(30):
        step(m, move=(0.0, 1.0))           # across the goal
    for _ in range(20):
        step(m, move=(float(team.attack), 0.0))   # towards the goal lifts it
    ly, lz = m.penalty_limits()
    assert 0.9 < c.pen_aim[0] <= ly and c.pen_aim[1] > 1.3


def strike(m, power_ticks, aim=None, finesse=False):
    c = m.controllers[0]
    step(m)
    if aim:
        c.pen_aim = list(aim)
    held = {'finesse'} if finesse else set()
    step(m, pressed={'shoot'}, held=held)
    for _ in range(power_ticks):
        step(m, held={'shoot'} | held)
    return step(m, released={'shoot'}, held=held)


def test_releasing_shoots_where_you_aimed():
    hits = []
    for seed in range(8):
        m, team = pen_match(seed=seed)
        evs = strike(m, int(0.68 / 0.85 * 60), aim=(-1.6, 0.6))
        assert any(e['type'] == 'shot' for e in evs)
        b = m.ball
        assert b.vel[0] * team.attack > 15.0
        # Where it crosses the goal line, ignoring the keeper
        gx = team.opp_goal_x(m.pitch)
        t = (gx - b.pos[0]) / b.vel[0]
        hits.append(b.pos[1] + b.vel[1] * t)
    assert abs(statistics.mean(hits) + 1.6) < 0.35


def test_overhitting_it_sends_it_high():
    def height(ticks):
        zs = []
        for seed in range(6):
            m, team = pen_match(seed=seed)
            strike(m, ticks, aim=(1.0, 1.0))
            b = m.ball
            zs.append(b.vel[2])
        return statistics.mean(zs)
    sweet = height(int(sum(PEN_SWEET) / 2 / 0.85 * 60))
    blasted = height(int(1.0 / 0.85 * 60) + 5)
    assert blasted > sweet + 0.5


def test_panenka_is_a_soft_chip():
    m, team = pen_match()
    step(m)
    evs = step(m, pressed={'lob'})
    shot = [e for e in evs if e['type'] == 'shot']
    assert shot and shot[0]['style'] == 'chip'
    assert abs(m.ball.vel[0]) < 13.0 and m.ball.vel[2] > 1.0


def test_keeper_picks_a_side_and_dives_there_at_the_kick():
    for side in (-1, 1):
        m, team = pen_match(against=True)
        c = m.controllers[0]
        k = c.team.keeper()
        step(m)
        assert c.player is k
        step(m, move=(0.0, float(side)), pressed={'pass'})
        assert k.pen_commit is not None and k.pen_commit[0] * side > 0
        # The computer taker goes after its pause
        dived = None
        for _ in range(240):
            for e in step(m):
                if e['type'] == 'dive':
                    dived = k.dive_dir
            if dived:
                break
        assert dived is not None and dived[1] * side > 0


def test_ai_penalties_score_about_as_often_as_real_ones():
    goals = kicks = 0
    for seed in range(12):
        m = Match('stars', 'legends', settings=dict(pitch='full', size=11), humans=(), seed=seed)
        m.start_shootout()
        for _ in range(60 * 150):
            for e in m.step({}):
                if e['type'] == 'pen_result':
                    kicks += 1
                    goals += e['scored']
            if m.state == 'fulltime':
                break
    assert 0.6 < goals / kicks < 0.9


def test_win_odds_follow_the_score():
    m = Match('stars', 'legends', humans=(), seed=1)
    m.start_shootout()
    assert abs(m.penalty_odds() - 0.5) < 1e-9
    m.teams[0].pens, m.teams[1].pens = [1, 1, 1], [1, 0]
    assert m.penalty_odds() > 0.75
    m.teams[0].pens, m.teams[1].pens = [1, 1, 1, 1], [1, 1, 1]
    assert 0.0 < m.penalty_odds() < 1.0
    m.teams[0].pens, m.teams[1].pens = [1, 1, 1], [0, 0, 0]
    assert m.penalty_odds() == 1.0


def test_penalty_ratings_come_from_the_classic_game():
    m = Match('stars', 'legends', humans=(), seed=1)
    for p in m.all_players():
        assert len(p.fb.pen) == 3 and all(0.0 <= v <= 1.0 for v in p.fb.pen)
