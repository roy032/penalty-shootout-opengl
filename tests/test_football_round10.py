"""Highlights, hall of fame, crossbar challenge and tournament night."""

import math

import pytest

from football.sim import highlights, inputlog, records
from football.sim.crossbar import POINTS, Crossbar
from football.sim.match import Input, Match
from football.sim.tournament import Tournament


def recorded(seed=4, half=25.0):
    cfg = dict(size=5, pitch='cage', half_seconds=half)
    m = Match('stars', 'legends', settings=cfg, humans=((0, 0),), seed=seed)
    rec = inputlog.Recorder('stars', 'legends', cfg, ((0, 0),), seed)
    i, prev, goals = 0, set(), []
    while m.state != 'fulltime':
        inp = Input()
        inp.move = (math.cos(i // 40 * 1.3), math.sin(i // 40 * 0.8))
        held = {'shoot'} if i % 90 < 30 else ({'pass'} if i % 90 > 85 else set())
        inp.held, inp.pressed, inp.released = held, held - prev, prev - held
        prev = held
        q = inputlog.quantize(inp)
        rec.add({0: q})
        goals += [m.ticks + 1 for e in m.step({0: q}) if e['type'] == 'goal']
        i += 1
    return rec.to_dict(m), goals, m


def test_highlights_cover_every_goal_in_order():
    log, goals, m = recorded()
    assert goals, 'the scripted match should have goals to show'
    clips = highlights.find(log)
    assert clips == sorted(clips)
    for a, b in zip(clips, clips[1:]):
        assert a[1] < b[0], 'clips never overlap'
    for g in goals:
        assert any(s <= g <= e and k == 'goal' for s, e, k in clips)
    assert sum(e - s for s, e, _ in clips) < log['ticks'], 'shorter than the match'


def test_hall_of_fame_counts_characters_only():
    _, _, m = recorded()
    rec = records.update({}, m)
    rec = records.update(rec, m)
    assert rec['matches'] == 2
    ps = rec['players']
    assert all(k in records._characters() for k in ps)
    total = sum(p.goals for t in m.teams for p in t.players if p.fb.key in ps and not p.keeper or p.fb.key in ps)
    assert sum(r['goals'] for r in ps.values()) == 2 * total
    assert sum(r['motm'] for r in ps.values()) == 2
    top = records.table(rec, 'goals')
    assert top == sorted(top, key=lambda r: (-r['goals'], r['apps'], r['name']))
    assert records.update({}, Match('reds', 'blues', humans=(), seed=1))['players'] == {}, 'clubs are not kept'


def test_crossbar_challenge_scores_the_bar_and_respawns():
    c = Crossbar(seed=2)
    m = c.m
    assert [p for p in m.all_players()] == [c.striker]
    pt = m.pitch
    a = m.teams[0].attack
    # Strike it straight at the bar
    b = m.ball
    b.owner = None
    gx = a * pt.half_length
    b.place(gx - a * 6.0, 0.0, 0.3)
    b.last_touch = c.striker
    c.flight = dict(t=0.0, hit=None, goal=False)
    # Find the lift that meets the bar on the line
    from football.sim.ball import Ball

    def height_at_line(vz):
        g = Ball(pt)
        g.place(gx - a * 6.0, 0.0, 0.3)
        g.kick(a * 22.0, 0.0, vz)
        while (gx - g.pos[0]) * a > 0:
            g._integrate(1 / 240)
        return g.pos[2]
    bar = pt.goal_height + pt.post_radius
    vz = min((v / 20.0 for v in range(100, 240)), key=lambda v: abs(height_at_line(v) - bar))
    b.kick(a * 22.0, 0.0, vz)
    evs = []
    for _ in range(240):
        evs += c.step({0: Input()})
        if any(e['type'] == 'cb_kick' for e in evs):
            break
    kick = [e for e in evs if e['type'] == 'cb_kick']
    assert kick and kick[0]['kind'] in ('bar', 'in_off') and c.score >= POINTS['bar']
    assert m.ball.owner is c.striker and m.state == 'play', 'next ball set up'


def test_crossbar_challenge_ends_after_a_minute():
    c = Crossbar(seed=3)
    evs = []
    while not c.done:
        evs += c.step({0: Input()})
    assert any(e['type'] == 'cb_over' for e in evs) and c.time_left() == 0.0


@pytest.mark.parametrize('n', range(2, 9))
def test_tournament_brackets_find_one_champion(n):
    t = Tournament(['P%d' % i for i in range(n)], seed=n)
    assert len({p['team'] for p in t.players}) == n
    games = 0
    while t.next_match():
        _, g = t.next_match()
        if games % 2:
            t.record(g, 1, 1, pens=(5, 4))
        else:
            t.record(g, 0, 2)
        games += 1
    assert games == n - 1 and t.champion is not None
    with pytest.raises(ValueError):
        Tournament(['solo'])


def test_tournament_needs_a_winner_each_game():
    t = Tournament(['A', 'B'], seed=1)
    _, g = t.next_match()
    with pytest.raises(ValueError):
        t.record(g, 1, 1)
    t.record(g, 1, 1, pens=(3, 4))
    assert t.champion == g['b'] and '(3-4 pens)' in t.lines()[-1]
