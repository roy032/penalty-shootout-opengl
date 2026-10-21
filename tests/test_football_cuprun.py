"""Cup Run: the bracket, results, perk offers and perks reaching the match."""

import pytest

from football.sim import roster, soak
from football.sim.cuprun import PERKS, ROUNDS, CupRun
from football.sim.match import Match


def test_four_ties_get_harder_with_no_repeats():
    c = CupRun('stars', seed=1)
    assert [t['name'] for t in c.ties] == [r[0] for r in ROUNDS]
    opps = [t['opp'] for t in c.ties]
    assert len(set(opps)) == 4 and 'stars' not in opps
    assert all(o in roster.TEAMS for o in opps[2:]), 'the last two ties are against character teams'
    assert c.tie() is c.ties[0] and c.tie_settings()['difficulty'] == 'amateur'
    assert CupRun('stars', seed=1).ties == c.ties, 'same seed, same draw'


def test_a_win_offers_three_perks_and_moves_on():
    c = CupRun('legends', seed=2)
    assert c.record((2, 1))
    assert len(c.offer) == 3 and len(set(c.offer)) == 3 and set(c.offer) <= set(PERKS)
    with pytest.raises(ValueError):
        c.take(next(k for k in PERKS if k not in c.offer))
    k = c.offer[0]
    c.take(k)
    assert c.perks == [k] and c.offer == []
    s = c.tie_settings(dict(size=5))
    assert s['size'] == 5 and s['perks'] == (k,) and s['difficulty'] == 'pro' and s['decider'] == 'penalties'


def test_penalties_decide_a_draw_and_a_loss_ends_the_run():
    c = CupRun('stars', seed=3)
    assert c.record((1, 1), pens=(4, 3))
    c.take(c.offer[0])
    assert not c.record((0, 0), pens=(2, 4))
    assert c.lost and c.over and c.tie() is None and c.offer == []
    assert 'L 0-0 (2-4 pens)' in c.bracket_lines()[1]


def test_four_wins_make_you_champion_with_no_perk_after_the_final():
    c = CupRun('stars', seed=4)
    for _ in range(3):
        c.record((3, 0))
        c.take(c.offer[-1])
    c.record((1, 0))
    assert c.champion and c.over and c.offer == [] and len(c.perks) == 3


def test_perks_stack_on_the_home_team_only():
    m = Match('stars', 'legends', settings=dict(perks=('boots', 'boots', 'gloves', 'engine')), humans=((0, 0),),
              seed=1)
    a, b = m.teams
    assert a.shot_power == pytest.approx(1.08 ** 2) and a.reach == pytest.approx(1.12)
    assert a.stamina_drain == pytest.approx(0.7) and a.perks == ('boots', 'boots', 'gloves', 'engine')
    assert b.shot_power == 1.0 and b.reach == 1.0 and b.perks == ()


def test_perked_shots_are_faster():
    speeds = []
    for perks in ((), ('boots',)):
        m = Match('stars', 'legends', settings=dict(perks=perks), humans=(), seed=5)
        m.state = 'play'
        m.restart = None
        p = m.teams[0].players[3]
        p.pos = [0.0, 0.0]
        m.ball.place(0.4, 0.0)
        m.ball.owner = p
        m.do_shoot(p, (1.0, 0.0), 0.6)
        speeds.append(abs(m.ball.vel[0]))
    assert speeds[1] > speeds[0] * 1.03


def test_a_cup_tie_plays_through_cleanly():
    c = CupRun('stars', seed=6)
    r = soak.play('stars', c.tie()['opp'], c.tie_settings(dict(half_seconds=30.0)), seed=6)
    assert r['problems'] == [] and r['winner'] is not None
