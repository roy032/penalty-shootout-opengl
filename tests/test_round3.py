import json
import random
import threading

import pytest

from shootout import config as C, net, squad as S, winprob
from shootout.controls import CONTROLS
from shootout.game import Game
from shootout.kick import Kick
from shootout.modes import ChallengeComp, GhostComp, TournamentComp
from shootout.rules import Shootout

from test_game import make_game, play_match, run


@pytest.fixture(autouse=True)
def stadium():
    yield
    C.apply_variant('stadium')


# ------------------------------------------------------------------ squads
def test_squad_order_puts_a_cool_head_fifth():
    rng = random.Random(3)
    squad = S.make_squad(rng)
    assert len(squad) == 11 and sum(p.keeper for p in squad) == 1
    order = S.ai_order(rng, squad)
    assert order[-1].keeper
    assert order[4].composure == max(p.composure for p in order[:5])


def test_cold_subs_are_fresh_but_cold():
    rng = random.Random(4)
    order = S.ai_order(rng, S.make_squad(rng))
    order = S.cold_subs(rng, order, 2)
    subs = [p for p in order if p.sub]
    assert len(subs) == 2 and all(p in order[:5] for p in subs)
    p = subs[0]
    cold = p.sigma_scale()
    p.kicks = 1
    assert p.sigma_scale() < cold
    assert p.speed_scale() > S.Player(9, 'X', 0.5, p.power, 0.5).speed_scale()
    assert 'goes to' in S.bottle_note(p, random.Random(1))


# --------------------------------------------------------- rules and odds
def test_abba_order():
    r = Shootout(first='p1', kicks_per_side=5, order='abba')
    seq = []
    for _ in range(8):
        side = r.next_kicker()
        seq.append(side)
        r.record(side, True)
    assert seq == ['p1', 'p2', 'p2', 'p1', 'p1', 'p2', 'p2', 'p1']


def test_win_probability():
    r = Shootout(first='p1', kicks_per_side=5)
    even = {'p1': 0.75, 'p2': 0.75}
    assert winprob.p1_wins(r, even) == pytest.approx(0.5, abs=0.06)
    assert winprob.p1_wins(r, {'p1': 0.85, 'p2': 0.7}) > 0.6
    r.results = {'p1': [True, True, True], 'p2': [False, False, True]}
    assert winprob.p1_wins(r, even) > 0.9
    r.results = {'p1': [True] * 3, 'p2': [False] * 3}
    r.winner = 'p1'
    assert winprob.p1_wins(r, even) == 1.0


# ---------------------------------------------------------------- variants
def test_variants_change_the_goal():
    C.apply_variant('futsal')
    assert C.GOAL_HALF_WIDTH == 1.5 and C.SPOT_Z == C.GOAL_LINE_Z + 6.0
    C.apply_variant('park')
    assert not C.HAS_BAR and not C.HAS_NET
    C.apply_variant('beach')
    assert 'skidder' not in C.shot_order()
    C.apply_variant('stadium')
    assert C.GOAL_HALF_WIDTH == 3.66 and C.HAS_BAR and C.SPOT_Z == C.GOAL_LINE_Z + 11.0


def test_park_goal_near_the_imaginary_bar_is_argued():
    from shootout import physics
    from shootout.keeper import Keeper
    C.apply_variant('park')
    ball = physics.Ball()
    physics.launch(ball, (0.6, C.GOAL_HEIGHT + 0.1), 22.0)
    keeper = Keeper()
    keeper.x0 = 30.0
    kick = Kick(ball, keeper)
    while kick.outcome is None:
        kick.step(C.SIM_DT)
    assert 'SAYS' in kick.outcome[1]


def test_variant_match_and_abba_replay_round_trip(tmp_path):
    g = make_game(tmp_path, seed=11, variant='futsal', order='abba')
    play_match(g)
    data = json.loads(json.dumps(g.replay_data()))
    assert data['variant'] == 'futsal' and data['order'] == 'abba'
    C.apply_variant('stadium')
    watch = Game(audio=None, rng=random.Random(5), stats_path=str(tmp_path / 'w.json'))
    watch.load_replay(data)
    t = 0
    while watch.phase not in ('replay', 'ended') and t < 60 * 900:
        watch.update(1 / 60)
        t += 1
    assert watch.comp.rules.results == g.comp.rules.results


# ------------------------------------------------------------------- modes
def test_manager_picks_the_order(tmp_path):
    g = make_game(tmp_path, mode='manager', seed=2)
    assert not g.is_human('p1') and g.controller('p1')
    while g.toss_stage != 'sub':
        run(g, 0.2)
    first = g.lineup_for('p1')[0]
    k = CONTROLS['p1']
    g.key_down(k['right'])                     # move the first taker down one
    assert g.lineup_for('p1')[1] is first
    g.key_down(k['extra2'])                    # one fresh sub
    assert sum(p.sub for p in g.lineup_for('p1')) == 1
    run(g, 5.0)
    assert g.toss_stage == 'sub'               # waits for the manager to confirm
    g.key_down(k['shoot'])
    play_match(g)
    assert g.comp.finished


def test_tournament_runs_to_the_end(tmp_path):
    g = make_game(tmp_path, mode='tournament', seed=3)
    assert isinstance(g.comp, TournamentComp)
    play_match(g, max_seconds=3000)
    assert g.comp.finished
    assert g.comp.bracket()


def test_top_bins_has_no_keeper_and_scores_bins(tmp_path):
    g = make_game(tmp_path, mode='challenge', challenge='bins')
    assert isinstance(g.comp, ChallengeComp)
    while g.phase != 'aim':
        run(g, 0.2)
    assert g.keeper.x0 == 40.0 and g.view()['no_keeper']
    assert g.comp.judge('p1', True, dict(at=(3.05, 2.0)))
    assert not g.comp.judge('p1', True, dict(at=(0.0, 1.0)))


def test_panenka_challenge_only_chips(tmp_path):
    g = make_game(tmp_path, mode='challenge', challenge='panenka')
    while g.phase != 'aim':
        run(g, 0.2)
    g.key_down(CONTROLS['p1']['special'])
    assert g.shot_kind == 'chip'


def test_career_earns_xp_and_saves_it(tmp_path):
    g = make_game(tmp_path, mode='career', role='kick')
    play_match(g)
    career = g.stats['career']['kick']
    assert career['games'] == 1 and career['xp'] in (4, 15)
    again = Game(audio=None, stats_path=str(tmp_path / 'stats.json'))
    assert again.stats['career']['kick']['games'] == 1


def test_daily_is_the_same_for_everyone(tmp_path):
    a = make_game(tmp_path, mode='daily', seed=1)
    b = make_game(tmp_path, mode='daily', seed=2)
    assert a.comp.names == b.comp.names
    assert [p.name for p in a.comp.order['p2']] == [p.name for p in b.comp.order['p2']]


def test_daily_grid_and_share(tmp_path):
    g = make_game(tmp_path, mode='daily', seed=1)
    g.daily_file = str(tmp_path / 'daily.txt')
    g.duel_dir = str(tmp_path / 'duels')
    play_match(g)
    while g.phase != 'ended':
        run(g, 1.0)
    assert g.daily_grid and g.daily_grid.count('\n') == 2
    g.key_down('b')
    assert g.clipboard_request == g.daily_grid
    assert (tmp_path / 'daily.txt').exists() and list((tmp_path / 'duels').iterdir())


def test_ghost_duel_round_trip(tmp_path):
    g = make_game(tmp_path, seed=8)
    g.duel_dir = str(tmp_path / 'duels')
    play_match(g)
    path = g.save_duel()
    data = Game.read_duel(path)
    mine = [r['shot']['target'] for r in g.records if r['kicker'] == 'p1' and not r.get('retake')][:5]
    friend = Game(audio=None, rng=random.Random(2), stats_path=str(tmp_path / 'f.json'))
    friend.load_duel(data)
    assert isinstance(friend.comp, GhostComp) and friend.is_human('p2') and not friend.is_human('p1')
    while not (friend.phase == 'flight' and friend.kicker == 'p1'):
        run(friend, 1 / 60)
    assert friend.shot['target'] == tuple(mine[0])


def test_tutorial_moves_on_when_a_step_is_done(tmp_path):
    g = make_game(tmp_path, mode='tutorial')
    while g.phase != 'aim':
        run(g, 0.2)
    run(g, 1.5)
    g.aim = [-2.5, 1.8]
    g.key_down(' ')
    for _ in range(60 * 8):
        run(g, 1 / 60)
        if g.phase == 'runup' and g.power is None:
            g.key_down(' ')
        if g.phase == 'result':
            break
    assert g.comp.step == 1


def test_achievements_and_auto_difficulty(tmp_path):
    g = make_game(tmp_path, difficulty='auto')
    level = g.stats['auto_level']
    play_match(g)
    assert 'first_goal' in g.stats['achievements'] or g.stats['goals'] == 0
    assert g.stats['auto_level'] != level


# ------------------------------------------------------- in-match details
def test_keeper_takes_the_ball_and_points(tmp_path):
    g = make_game(tmp_path, mode='pvp', seed=5)
    while g.phase != 'ritual':
        run(g, 1 / 60)
    ks = g.keeper_side()
    before = g.pressure()
    g.key_down(CONTROLS[ks]['extra2'])
    assert g.took_ball and g.pressure() > before
    while g.phase != 'aim':
        run(g, 1 / 60)
    g.key_down(CONTROLS[ks]['extra3'])
    assert g.keeper.point_dir == -1 and g.view()['keeper'][2] == 'point'


def test_gaze_and_runup_style(tmp_path):
    g = make_game(tmp_path, seed=6)
    while not (g.phase == 'aim' and g.kicker == 'p1'):
        run(g, 1 / 60)
        if g.phase == 'aim' and g.kicker != 'p1':
            run(g, 3.0)
    k = CONTROLS['p1']
    g.taunts = 2
    plain = g.pressure()
    g.key_down(k['extra2'])
    assert g.gaze == 'stare' and g.pressure() > plain - 0.06    # calmer, but the waving bites harder
    g.key_down(k['extra2'])
    assert g.gaze == 'away'
    assert g.runup == 'angled' and g.cue() > 1.0
    g.key_down(k['extra1'])
    g.key_down(k['extra1'])
    assert g.disguise and g.cue() < 0.5


def test_fingertip_stretch_and_report(tmp_path):
    g = make_game(tmp_path, seed=12)
    while not (g.phase == 'aim' and g.kicker == 'p2'):
        run(g, 1 / 60)
        if g.phase == 'aim' and g.kicker == 'p1':
            g.key_down(' ')
            run(g, 0.6)
            g.key_down(' ')
    g.key_down(CONTROLS['p1']['right'])
    while g.phase != 'flight':
        run(g, 1 / 60)
    while g.phase == 'flight' and g.time_to_line() > 0.1:
        g.update(1 / 240)
    g.key_down(CONTROLS['p1']['shoot'])
    assert g.keeper.stretch == 'good'
    run(g, 3.0)
    assert g.log[-1]['stretch'] == 'good'
    assert g.coach_report()


def test_lan_two_players_finish_the_same_match(tmp_path):
    server = net.listen(0, '127.0.0.1')
    port = server.getsockname()[1]
    out = {}
    t = threading.Thread(target=lambda: out.setdefault('conn', net.accept(server, 5)))
    t.start()
    client = net.connect(f'127.0.0.1:{port}')
    t.join()
    server.close()
    host = Game(audio=None, stats_path=str(tmp_path / 'h.json'))
    guest = Game(audio=None, stats_path=str(tmp_path / 'g.json'))
    host.kicks_per_side = 3
    a, b = net.NetSession(out['conn'], 'p1'), net.NetSession(client, 'p2')
    a.start_host(host)
    assert b.start_join(guest)
    assert guest.local_slot == 'p2' and guest.kicks_per_side == 3 and guest.mode == 'pvp'
    bots = [(a, host, random.Random(1)), (b, guest, random.Random(2))]
    for _ in range(60 * 400):
        for session, game, rng in bots:
            if game.phase == 'aim' and game.phase_t > 1.2 and rng.random() < 0.05:
                if game.kicker == session.slot:
                    session.key(game, session.keys['shoot'], True)
                elif rng.random() < 0.3:
                    session.key(game, session.keys[rng.choice(('left', 'right'))], True)
            if game.phase == 'runup' and game.power is None and game.kicker == session.slot and rng.random() < 0.1:
                session.key(game, session.keys['shoot'], True)
            session.pump(game, 1 / 60)
        if host.phase in ('replay', 'ended') and guest.phase in ('replay', 'ended'):
            break
    try:
        assert host.comp.finished and guest.comp.finished
        assert host.comp.rules.results == guest.comp.rules.results
        assert [r['shot'] for r in host.records] == [r['shot'] for r in guest.records]
    finally:
        a.close()
        b.close()


def test_mods_add_scenarios_and_teams(tmp_path):
    from shootout import scenarios
    mod = dict(teams=[dict(name='Rovers', shirt=[0.1, 0.5, 0.3], shorts=[1, 1, 1], keeper=[0.9, 0.8, 0.1]),
                      dict(name='Broken', shirt=[1, 1])],
               scenarios=[dict(key='mod1', title='Mod Cup', teams=['A', 'B'], first='p1', role='kick',
                               kits=[dict(shirt=[1, 0, 0], shorts=[1, 1, 1], keeper=[0, 1, 0])] * 2,
                               results={'p1': [True], 'p2': [False]})])
    (tmp_path / 'm.json').write_text(json.dumps(mod))
    teams = []
    before = len(scenarios.SCENARIOS)
    try:
        assert scenarios.load_mods(str(tmp_path), teams) == 2
        assert teams[0]['name'] == 'ROVERS' and scenarios.SCENARIOS[-1]['key'] == 'mod1'
    finally:
        del scenarios.SCENARIOS[before:]
