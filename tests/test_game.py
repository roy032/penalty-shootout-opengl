import json
import random

from shootout import config as C, controls
from shootout.controls import CONTROLS
from shootout.game import Game
from shootout.modes import KingOfTheGoal, Knockout


def make_game(tmp_path, mode='pvc', seed=4, **settings):
    g = Game(audio=None, rng=random.Random(seed), stats_path=str(tmp_path / 'stats.json'))
    g.mode = mode
    for k, v in settings.items():
        setattr(g, k, v)
    g.start_match()
    return g


def run(g, seconds):
    for _ in range(int(round(seconds * 60))):
        g.update(1 / 60)


def play_match(g, max_seconds=900):
    """Human players aim, start the run-up and set power; human keepers guess."""
    rng = random.Random(9)
    t = 0.0
    while g.phase not in ('replay', 'ended') and t < max_seconds:
        run(g, 1 / 60)
        t += 1 / 60
        if g.phase == 'aim' and g.phase_t > 1.2:
            ks = g.keeper_side()
            if g.is_human(ks):
                k = CONTROLS[ks]
                g.key_down(k['left'] if rng.random() < 0.5 else k['right'])
            if g.is_human(g.kicker):
                g.aim = [rng.choice([-2.7, 2.7]), rng.choice([0.4, 1.8])]
                g.key_down(CONTROLS[g.kicker]['shoot'])
            else:
                run(g, 2.0)
                t += 2.0
    return t


def test_full_pvc_match_finishes_with_replay(tmp_path):
    g = make_game(tmp_path)
    assert g.phase == 'toss'
    play_match(g)
    assert g.comp.winner in ('p1', 'p2')
    assert g.phase in ('replay', 'ended')
    assert g.log and all(k['at'] is not None for k in g.log)
    while g.phase == 'replay':
        run(g, 1.0)
    assert g.phase == 'ended'
    assert g.stats['matches'] == 1


def test_pvp_hidden_aim(tmp_path):
    g = make_game(tmp_path, mode='pvp')
    while g.phase != 'aim':
        run(g, 0.5)
    assert not g.aim_visible()
    g.hidden_aim = False
    assert g.aim_visible()
    play_match(g)
    assert g.comp.winner in ('p1', 'p2')


def test_keeper_choice_is_hidden_until_contact(tmp_path):
    g = make_game(tmp_path, mode='pvp')
    while g.phase != 'aim':
        run(g, 0.5)
    keeper = g.keeper_side()
    g.key_down(CONTROLS[keeper]['right'])
    assert g.keeper_dir == 1
    assert not g.keeper.committed()          # nothing moves before the kick
    g.key_down(CONTROLS[g.kicker]['shoot'])
    run(g, 2.0)
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
    assert g.menu_rows()[2] == 'kicks'
    g.menu_focus = 2
    g.key_down('d')
    assert g.kicks_per_side == 10
    g.key_down('\r')
    assert g.ui == 'playing' and g.comp.rules.kicks_per_side == 10


def test_menu_rows_follow_the_mode(tmp_path):
    g = Game(audio=None, rng=random.Random(1), stats_path=str(tmp_path / 's.json'))
    g.mode = 'party'
    assert 'players' in g.menu_rows() and 'difficulty' not in g.menu_rows()
    g.mode = 'famous'
    assert 'scenario' in g.menu_rows()


def test_toss_winner_picks_the_end(tmp_path):
    g = make_game(tmp_path, mode='pvp', seed=2)
    w = g.toss_winner
    g.key_down(CONTROLS[w]['right'])             # towards the other team's fans
    assert g.end_fans != w and g.toss_stage == 'sub'
    g.key_down(CONTROLS['p1']['extra1'])
    assert g.comp.specialist['p1']
    run(g, 6.0)
    assert g.phase in ('walk', 'aim')


def test_famous_scenario_is_the_deciding_kick(tmp_path):
    g = make_game(tmp_path, mode='famous', scenario=0)        # Belgrade 1976
    assert g.phase == 'intro'
    g.key_down(' ')
    assert g.kicker == 'p1' and g.stakes == 'to_win'
    assert g.comp.rows()[0]['results'] == [True] * 4


def test_sudden_death_only(tmp_path):
    g = make_game(tmp_path, mode='pvp', kicks_per_side=0)
    while g.phase not in ('aim',):
        run(g, 0.5)
    assert g.comp.in_sudden_death() or g.stakes is not None


def test_king_of_the_goal_runs_to_a_winner(tmp_path):
    g = make_game(tmp_path, mode='party', party_type='king', party_players=3)
    assert isinstance(g.comp, KingOfTheGoal)
    play_match(g)
    assert g.comp.finished
    assert sum(g.comp.points) == 3 * 2               # every kick scores for someone
    assert g.comp.winner


def test_knockout_crowns_a_champion(tmp_path):
    g = make_game(tmp_path, mode='party', party_type='knockout', party_players=3)
    assert isinstance(g.comp, Knockout)
    play_match(g)
    assert g.comp.champion is not None
    assert len(g.comp.history) == 2


def test_training_keeps_going_and_fills_zones(tmp_path):
    g = make_game(tmp_path, mode='training')
    play_match(g, max_seconds=40)
    assert g.phase not in ('replay', 'ended')
    assert sum(a for a, _ in g.stats['zones'].values()) == len(g.comp.results) > 3
    assert g.preview_path() is None or g.preview_path()['points']


def test_match_penalty_is_one_kick(tmp_path):
    g = make_game(tmp_path, mode='match', role='keep')
    play_match(g)
    assert g.comp.finished
    assert len(g.log) == 1


def test_double_touch_is_disallowed(tmp_path):
    g = make_game(tmp_path)
    original = g._slip

    def always_double(shot, power):
        g.double_touch = True
        g.slipped = True
        return original(shot, power)

    g._slip = always_double
    while g.phase != 'aim' or g.kicker != 'p1':
        run(g, 1 / 60)
        if g.phase == 'aim' and g.kicker != 'p1':
            run(g, 3.0)
    g.key_down(CONTROLS['p1']['shoot'])
    for _ in range(60 * 8):
        run(g, 1 / 60)
        if g.phase == 'result':
            break
    assert g.result == (False, 'DISALLOWED: DOUBLE TOUCH')


def test_second_yellow_sends_the_keeper_off(tmp_path):
    g = make_game(tmp_path)
    g._book('p2', 'Time-wasting')
    assert g.card[0] == 'yellow' and not g.comp.emergency['p2']
    g._book('p2', 'Off his line early')
    assert g.card[0] == 'red' and g.comp.emergency['p2']
    assert g.comp.keeper_colour('p2') == C.EMERGENCY_KIT
    assert g.keeper_params('p2')['reach'] < C.DIFFICULTY[g.difficulty]['keeper']['reach']


def test_keeper_takes_the_eleventh_kick(tmp_path):
    g = make_game(tmp_path)
    g.comp.rules.results = {'p1': [True] * 10, 'p2': [True] * 10}
    g.comp.rules.first = 'p1'
    assert g.comp.taker_is_keeper('p1')
    assert g.comp.taker('p1') == 'Goalkeeper'


def test_replay_file_round_trip(tmp_path):
    g = make_game(tmp_path, seed=7)
    play_match(g)
    path = g.save_replay(str(tmp_path / 'replays'))
    with open(path) as f:
        data = json.load(f)
    watch = Game(audio=None, rng=random.Random(99), stats_path=str(tmp_path / 'w.json'))
    watch.load_replay(data)
    t = 0
    while watch.phase not in ('replay', 'ended') and t < 60 * 600:
        watch.update(1 / 60)
        t += 1
    assert watch.comp.rules.results == g.comp.rules.results
    assert watch.comp.winner == g.comp.winner


def test_rebind_keys(tmp_path, monkeypatch):
    monkeypatch.setattr(controls, 'PATH', str(tmp_path / 'keys.json'))
    g = Game(audio=None, rng=random.Random(1), stats_path=str(tmp_path / 's.json'))
    try:
        g.key_down('k')
        assert g.rebind == ('p1', 0)
        g.key_down('p')                         # reserved: refused
        assert g.rebind == ('p1', 0)
        g.key_down('z')
        assert CONTROLS['p1']['left'] == 'z' and g.rebind == ('p1', 1)
        g.key_down('d')                         # still P1's 'right': allowed for that action
        assert g.rebind == ('p1', 2)
        g.key_down('\x1b')
        assert g.rebind is None
    finally:
        controls.reset()


def test_phone_controller_needs_the_pin(tmp_path):
    from shootout.phone import PhoneServer
    server = PhoneServer(port=0, pin='1234', host='127.0.0.1')
    try:
        assert not server.accept({'pin': '0000', 'slot': 'p1', 'aim': [1, 1]})
        assert server.accept({'pin': '1234', 'slot': 'p1', 'aim': [1.5, 2.0]})
        assert server.accept({'pin': '1234', 'slot': 'p1', 'action': 'shoot'})
        assert not server.accept({'pin': '1234', 'slot': 'p1', 'action': 'quit'})
        g = make_game(tmp_path, mode='pvp')
        while g.phase != 'aim':
            run(g, 0.5)
        server.commands.queue.clear()
        server.accept({'pin': '1234', 'slot': g.kicker, 'aim': [1.5, 2.0]})
        server.apply(g)
        assert g.aim == [1.5, 2.0]
    finally:
        server.stop()
