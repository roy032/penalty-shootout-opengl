import pytest

from shootout.rules import Shootout


def play(so, kicks):
    """kicks: string of G/M in kicking order."""
    for k in kicks:
        so.record(so.next_kicker(), k == 'G')
    return so.winner


def test_alternates_from_first_kicker():
    so = Shootout(first='p2')
    assert so.next_kicker() == 'p2'
    so.record('p2', True)
    assert so.next_kicker() == 'p1'


def test_wrong_kicker_rejected():
    so = Shootout(first='p1')
    with pytest.raises(ValueError):
        so.record('p2', True)


def test_early_finish_when_cannot_be_caught():
    so = Shootout(first='p1')
    # p1 scores 3, p2 misses 3: 3-0 with p2 having 2 left
    assert play(so, 'GMGMGM') == 'p1'
    assert so.kicks('p1') == 3


def test_regulation_win_after_five_each():
    so = Shootout(first='p1')
    assert play(so, 'GGGGGGGGGM') == 'p1'


def test_level_goes_to_sudden_death():
    so = Shootout(first='p1')
    assert play(so, 'GG' * 5) is None
    assert so.in_sudden_death()
    # p1 scores, p2 must reply: no winner until p2 has kicked
    so.record('p1', True)
    assert so.winner is None
    so.record('p2', False)
    assert so.winner == 'p1'


def test_sudden_death_needs_equal_kicks():
    so = Shootout(first='p1')
    play(so, 'GG' * 5)
    so.record('p1', False)
    assert so.winner is None
    so.record('p2', True)
    assert so.winner == 'p2'


def test_stakes():
    so = Shootout(first='p1')
    play(so, 'GGGGGGGG')          # 4-4, p1 to take kick 5
    assert so.stakes('p1') is None
    so.record('p1', False)        # 4-4, p2 can win it
    assert so.stakes('p2') == 'to_win'
    so = Shootout(first='p1')
    play(so, 'GGGGGGGGG')         # 5-4, p2 must score to survive
    assert so.stakes('p2') == 'must_score'


def test_short_shootout():
    so = Shootout(first='p1', kicks_per_side=3)
    assert play(so, 'GMGM') == 'p1'   # 2-0 with one p2 kick left
