import random

from shootout.game import Game


def make_game(tmp_path, mode='pvc', seed=4):
    g = Game(audio=None, rng=random.Random(seed), stats_path=str(tmp_path / 'stats.json'))
    g.mode = mode
    g.start_match()
    return g


def run(g, seconds):
    for _ in range(int(seconds * 60)):
        g.update(1 / 60)


def play_match(g, max_kicks=60):
    """Human players hold the aim, start the run-up and set power; keepers guess."""
    rng = random.Random(9)
    kicks = 0
    while g.phase not in ('replay', 'ended') and kicks < max_kicks:
        run(g, 1 / 60)
        if g.phase == 'aim' and g.phase_t > 0.3:
            for side in ('p1', 'p2'):
                if g.is_human(side) and side == g.keeper_side():
                    g.key_down({'p1': 'a', 'p2': 'j'}[side] if rng.random() < 0.5 else {'p1': 'd', 'p2': 'l'}[side])
            if g.is_human(g.kicker):
                g.aim = [rng.choice([-2.7, 2.7]), rng.choice([0.4, 1.8])]
                g.key_down(' ' if g.kicker == 'p1' else '\r')
                kicks += 1
            else:
                run(g, 2.0)
                kicks += 1
    return kicks


def test_full_pvc_match_finishes_with_replay(tmp_path):
    g = make_game(tmp_path)
    play_match(g)
    assert g.shootout.winner in ('p1', 'p2')
    assert g.phase in ('replay', 'ended')
    assert g.log and all(k['at'] is not None for k in g.log)
    while g.phase == 'replay':
        run(g, 1.0)
    assert g.phase == 'ended'
    assert g.stats['matches'] == 1


def test_pvp_hidden_aim(tmp_path):
    g = make_game(tmp_path, mode='pvp')
    run(g, 3.0)
    assert g.phase == 'aim'
    assert not g.aim_visible()
    g.hidden_aim = False
    assert g.aim_visible()
    play_match(g)
    assert g.shootout.winner in ('p1', 'p2')


def test_keeper_choice_is_hidden_until_contact(tmp_path):
    g = make_game(tmp_path, mode='pvp')
    run(g, 3.0)
    keeper = g.keeper_side()
    g.key_down({'p1': 'd', 'p2': 'l'}[keeper])
    assert g.keeper_dir == 1
    assert not g.keeper.committed()          # nothing moves before the kick
    g.key_down(' ' if g.kicker == 'p1' else '\r')
    run(g, 1.2)
    assert g.keeper.dir == 1


def test_pause_freezes_play(tmp_path):
    g = make_game(tmp_path)
    run(g, 1.0)
    g.key_down('p')
    t = g.phase_t
    run(g, 2.0)
    assert g.phase_t == t
    g.key_down('p')
    run(g, 0.5)
    assert g.phase_t != t or g.phase != 'toss'


def test_menu_changes(tmp_path):
    g = Game(audio=None, rng=random.Random(1), stats_path=str(tmp_path / 's.json'))
    g.menu_focus = 2
    g.key_down('d')
    assert g.kicks_per_side == 10
    g.key_down('\r')
    assert g.ui == 'playing' and g.shootout.kicks_per_side == 10
