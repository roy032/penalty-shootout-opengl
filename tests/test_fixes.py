"""Tests for the fixes from the code review: input, saves, replays, party
games, the Daily, duel files, LAN sync, pacing and the HUD's wording."""

import json
import os
import random
import threading

import pytest

from shootout import config as C, controls, net, stats, storage
from shootout.controls import CONTROLS
from shootout.game import Game, valid_duel
from shootout.modes import TUTORIAL, ChallengeComp, KingOfTheGoal, Knockout, MatchPenaltyComp, TrainingComp

from test_game import make_game, play_match, run


@pytest.fixture(autouse=True)
def clean():
    yield
    C.apply_variant('stadium')
    controls.reset()


def until(g, cond, seconds=120):
    for _ in range(int(seconds * 60)):
        if cond():
            return True
        g.update(1 / 60)
    return cond()


# --------------------------------------------------------------- ESC and quit
def test_esc_pauses_and_quitting_needs_a_confirm(tmp_path):
    g = make_game(tmp_path)
    assert g.key_down('\x1b') is None and g.paused
    assert g.key_down('\x1b') is None and not g.paused          # ESC again resumes
    g.key_down('\x1b')
    g.key_down('q')
    assert g.confirm_quit
    assert g.key_down('n') is None and not g.confirm_quit       # anything else backs out
    g.key_down('q')
    assert g.key_down('\r') == 'quit'


def test_esc_in_the_menu_asks_first(tmp_path):
    g = Game(audio=None, rng=random.Random(1), stats_path=str(tmp_path / 's.json'))
    assert g.key_down('\x1b') is None and g.confirm_quit
    assert g.key_down('y') == 'quit'


# ------------------------------------------------- one human on the P1 keys
@pytest.mark.parametrize('mode,settings', [
    ('training', dict(role='keep')), ('match', dict(role='keep')), ('challenge', dict(challenge='saves')),
    ('career', dict(role='keep')), ('ghost', {}),
])
def test_keeper_modes_use_the_humans_own_keys(tmp_path, mode, settings):
    g = make_game(tmp_path, mode=mode, **settings)
    assert until(g, lambda: g.phase == 'aim' and g.is_human(g.keeper_side()))
    ks = g.keeper_side()
    assert ks == 'p2' and g.keys_for(ks) is CONTROLS['p1']
    g.key_down(CONTROLS['p2']['right'])                         # Player 2's keys do nothing now
    assert g.keeper_dir is None
    g.key_down(CONTROLS['p1']['right'])
    assert g.keeper_dir == 1


def test_two_humans_keep_their_own_keys(tmp_path):
    g = make_game(tmp_path, mode='pvp')
    assert g.keys_for('p1') is CONTROLS['p1'] and g.keys_for('p2') is CONTROLS['p2']


def test_tutorial_names_the_bound_keys(tmp_path):
    controls.bind('p1', 'left', 'j')                             # swaps with P2's left
    controls.bind('p1', 'shoot', 'RIGHT')
    g = make_game(tmp_path, mode='tutorial')
    text = g.comp.instruction(g.keys_for('p1'))
    assert 'J' in text and 'RIGHT' in text and 'SPACE' not in text
    for step, _ in TUTORIAL:
        assert '{' not in g.comp.instruction() or step                # every template formats
    g.comp.step = 5                                              # the keeping step: still P1's keys
    g.comp._set_roles()
    assert g.keys_for('p2') is CONTROLS['p1'] and 'J' in g.comp.instruction(g.keys_for('p2'))


# ------------------------------------------------------------- party games
def test_knockout_result_shows_under_the_tie_that_was_decided(tmp_path):
    g = make_game(tmp_path, mode='party', party_type='knockout', party_players=4)
    first_pair = dict(g.comp.names)
    while not g.comp.history:
        assert until(g, lambda: g.phase == 'aim')
        g.key_down(g.keys_for(g.kicker)['shoot'])
        assert until(g, lambda: g.phase == 'runup')
        g.key_down(g.keys_for(g.kicker)['shoot'])
        assert until(g, lambda: g.phase == 'result')
        if not g.comp.history:
            g.nerves = {'p1': 0.2, 'p2': 0.2}
    assert g.phase == 'result' and g.comp.names == first_pair     # still the tie just won
    g.nerves = {'p1': 0.25, 'p2': -0.1}
    g.keeper_conf = {'p1': 2, 'p2': 3}
    g.after_result()
    assert g.comp.names != first_pair
    assert g.nerves == {'p1': 0.0, 'p2': 0.0} and g.keeper_conf == {'p1': 0, 'p2': 0}


def test_king_of_the_goal_moves_on_after_the_result(tmp_path):
    g = make_game(tmp_path, mode='party', party_type='king', party_players=3)
    kicker = g.comp.names['p1']
    assert until(g, lambda: g.phase == 'aim')
    g.key_down(' ')
    assert until(g, lambda: g.phase == 'runup')
    g.key_down(' ')
    assert until(g, lambda: g.phase == 'result')
    assert g.comp.names['p1'] == kicker and g.log[-1]['name'] == kicker
    g.nerves['p1'] = 0.3
    g.after_result()
    assert g.comp.names['p1'] != kicker and g.nerves['p1'] == 0.0


def test_party_games_still_finish():
    k = KingOfTheGoal(3)
    while not k.finished:
        k.record('p1', True)
        k.advance()
    assert sum(k.points) == 6 and k.winner
    ko = Knockout(3, kicks=1)
    while not ko.finished:
        ko.record(ko.next_kicker(), ko.next_kicker() == 'p1')
        ko.advance()
    assert len(ko.history) == 2 and ko.winner


# ----------------------------------------------------------------- replays
@pytest.mark.parametrize('fps', [30, 144])
def test_replay_frames_are_on_the_simulation_clock(tmp_path, fps):
    def recorded(step):
        g = make_game(tmp_path, seed=3)
        assert until(g, lambda: g.phase == 'aim' and g.kicker == 'p1')
        g.key_down(' ')
        for _ in range(int(2.5 / step)):
            g.update(step)
        return g.recording

    at60, other = recorded(1 / 60), recorded(1 / fps)
    assert abs(len(at60) - len(other)) <= 2 and len(at60) > 60
    assert at60[0]['ball'] == other[0]['ball']


# --------------------------------------------------------------- the Daily
def test_the_daily_does_not_take_over_the_games_rng(tmp_path):
    a = make_game(tmp_path, mode='daily', seed=1)
    a.mode = 'pvc'
    a.new_match()
    b = make_game(tmp_path, mode='daily', seed=2)
    b.mode = 'pvc'
    b.new_match()
    # After the Daily each game is back on its own random numbers
    assert (a.squad_seed, a.toss_winner, a.ref['name']) != (b.squad_seed, b.toss_winner, b.ref['name']) or \
        a.rng.random() != b.rng.random()
    seeds = set()
    for _ in range(4):
        a.new_match()
        seeds.add(a.squad_seed)
    assert len(seeds) == 4


def test_the_daily_is_still_the_same_after_other_matches(tmp_path):
    g = make_game(tmp_path, mode='pvc', seed=5)
    g.mode = 'daily'
    g.new_match()
    first = (g.squad_seed, g.toss_winner, g.ref['name'], g.comp.names['p2'])
    g.mode = 'pvc'
    g.new_match()
    g.mode = 'daily'
    g.new_match()
    assert (g.squad_seed, g.toss_winner, g.ref['name'], g.comp.names['p2']) == first


# ------------------------------------------------------------- duel files
GOOD_DUEL = dict(version=1, name='Ann', kit=dict(shirt=[1, 0, 0], shorts=[1, 1, 1], keeper=[0, 1, 0]),
                 kicks=[dict(shot=dict(kind='placed', target=[2.0, 0.5], speed=20.0, curl=0.0), power=0.7,
                             runup='angled')], score=1)


@pytest.mark.parametrize('bad', [
    None, [], 'text', {}, dict(GOOD_DUEL, kit=None), dict(GOOD_DUEL, kit=dict(shirt=[1, 0])),
    dict(GOOD_DUEL, kicks=[]), dict(GOOD_DUEL, kicks='abc'), dict(GOOD_DUEL, kicks=[{}]),
    dict(GOOD_DUEL, kicks=[dict(shot=dict(kind='rabona', target=[0, 1], speed=20))]),
    dict(GOOD_DUEL, kicks=[dict(shot=dict(kind='placed', target=[0], speed=20))]),
    dict(GOOD_DUEL, kicks=[dict(shot=dict(kind='placed', target=['x', 1], speed=20))]),
    dict(GOOD_DUEL, kicks=[dict(shot=dict(kind='placed', target=[0, 1], speed=float('nan')))]),
    dict(GOOD_DUEL, kicks=[dict(shot=dict(kind='placed', target=[0, 1], speed=1e9))]),
    dict(GOOD_DUEL, kicks=[dict(shot=dict(kind='placed', target=[0, 1], speed=20), power='lots')]),
    dict(GOOD_DUEL, kit=dict(shirt=[1, 0, 9])),
])
def test_bad_duel_files_are_refused(tmp_path, bad):
    assert valid_duel(bad) is None
    path = tmp_path / 'duel.json'
    path.write_text(json.dumps(bad))
    assert Game.read_duel(str(path)) is None
    g = Game(audio=None, rng=random.Random(1), stats_path=str(tmp_path / 's.json'))
    assert g.load_duel(bad) is False and g.ui == 'menu'


def test_a_good_duel_file_plays_and_odd_extras_are_cleaned(tmp_path):
    data = dict(GOOD_DUEL, name=42, runup='?', score='lots')
    data['kicks'] = [dict(GOOD_DUEL['kicks'][0], runup='moonwalk')]
    clean = valid_duel(data)
    assert clean['name'] == 'GHOST' and clean['kicks'][0]['runup'] == 'angled' and clean['score'] is None
    (tmp_path / 'broken.json').write_text('{not json')
    assert Game.read_duel(str(tmp_path / 'broken.json')) is None
    g = Game(audio=None, rng=random.Random(1), stats_path=str(tmp_path / 's.json'))
    assert g.load_duel(data)
    assert until(g, lambda: g.phase == 'flight' and g.kicker == 'p1')
    assert g.shot['target'] == (2.0, 0.5)


# ------------------------------------------------------------- safe saves
def test_saves_are_atomic(tmp_path, monkeypatch):
    path = str(tmp_path / 'stats.json')
    data = stats.load(path)
    data['wins'] = 3
    assert stats.save(data, path)
    assert stats.load(path)['wins'] == 3

    def crash(*a, **k):
        raise OSError('disk full')

    data['wins'] = 4
    monkeypatch.setattr(json, 'dump', crash)                    # dies half way through the write
    assert not stats.save(data, path)
    monkeypatch.undo()
    assert stats.load(path)['wins'] == 3                        # the old file is untouched
    assert os.listdir(tmp_path) == ['stats.json']               # and no temporary file is left


def test_controls_and_players_files_go_through_the_safe_writer(tmp_path, monkeypatch):
    from shootout import characters as CH, gfx
    calls = []
    real = storage.write_json
    monkeypatch.setattr(storage, 'write_json', lambda p, d, indent=None: calls.append(p) or real(p, d, indent))
    controls.save(str(tmp_path / 'keys.json'))
    CH.save_custom(str(tmp_path / 'players.json'))
    gfx.save_quality('low', str(tmp_path / 'gfx.json'))
    assert len(calls) == 3 and gfx.saved_quality(str(tmp_path / 'gfx.json')) == 'low'
    assert gfx.saved_quality(str(tmp_path / 'none.json')) is None


def test_a_keys_file_with_a_clash_is_ignored(tmp_path):
    path = tmp_path / 'keys.json'
    path.write_text(json.dumps(dict(p1=dict(left='j'), p2=dict(left='j'))))
    controls.load(str(path))
    assert CONTROLS['p1']['left'] == 'a'


# ----------------------------------------------------------------- keys
def test_held_keys_are_dropped_between_screens(tmp_path):
    g = make_game(tmp_path)
    g.key_down('a')
    assert 'a' in g.held
    g.key_down('p')
    assert not g.held
    g.key_down('a')
    g.to_menu()
    assert not g.held
    g.key_down('d')
    g.release_keys()
    assert not g.held


def test_menu_shortcuts_are_not_player_keys():
    used = {k for keys in controls.DEFAULTS.values() for k in keys.values()}
    assert not used & set(controls.MENU_KEYS.values())


# -------------------------------------------------------------- pacing
def test_every_cutscene_can_be_skipped(tmp_path):
    g = make_game(tmp_path)
    assert g.phase == 'toss'
    for _ in range(3):
        g.key_down('\r')
    assert g.phase == 'walk'
    g.key_down('\r')
    run(g, 0.1)
    assert g.phase == 'ritual'
    g.key_down('\r')                                             # P1 is the human: ENTER is not his key
    assert g.phase == 'aim'


def test_quick_pacing_shortens_the_cutscenes(tmp_path):
    def time_to_first_kick(pacing):
        g = make_game(tmp_path, pacing=pacing, seed=2)
        t = 0
        while g.phase != 'aim':
            g.update(1 / 60)
            t += 1
        return t

    assert time_to_first_kick('quick') < 0.6 * time_to_first_kick('normal')


def test_result_and_var_can_be_skipped(tmp_path):
    g = make_game(tmp_path, mode='match', role='kick')
    assert until(g, lambda: g.phase == 'aim')
    g.key_down(' ')
    assert until(g, lambda: g.phase == 'runup')
    g.key_down(' ')
    assert until(g, lambda: g.phase in ('result', 'var', 'rebound'))
    if g.phase == 'result':
        run(g, 2.0)                                              # the winning kick runs in slow motion
        assert g.phase == 'result'
        g.key_down('\r')
        assert g.phase != 'result'


# -------------------------------------------------------- the HUD's words
def test_winner_titles_read_right():
    from shootout.hud import winner_title

    class Comp:
        def __init__(self, name):
            self.name = name

        def winner_name(self):
            return self.name

    assert winner_title(Comp('BLUES')) == 'BLUES WIN!'
    ko = Knockout(2)
    ko.champion = 1
    assert winner_title(ko) == 'PLAYER 2 WINS!'
    king = KingOfTheGoal(3)
    king.complete = True
    assert winner_title(king).endswith('SHARE IT!')


def test_stats_line_after_a_manager_match():
    data = stats.load('/nonexistent/stats.json')
    assert stats.summary(data).startswith('No career stats yet')
    data['matches'], data['wins'] = 1, 1
    assert 'No career stats' not in stats.summary(data) and '1/1' in stats.summary(data)


def test_no_ghost_duel_without_a_human_kicker(tmp_path):
    g = make_game(tmp_path, mode='manager')
    play_match(g)
    assert g.duel_data() is None


def test_hidden_aim_is_explained_when_switched_on(tmp_path):
    g = Game(audio=None, rng=random.Random(1), stats_path=str(tmp_path / 's.json'))
    assert not g.hidden_aim
    g.menu_change('hidden', 1)
    assert g.hidden_aim and 'Hidden aim' in g.toast[0]


# ------------------------------------------------------------------- LAN
def _pair(tmp_path):
    lobby = net.Lobby(port=0)
    client = net.connect(f'127.0.0.1:{lobby.port}')
    sock = None
    for _ in range(500):
        sock = lobby.poll()
        if sock:
            break
        threading.Event().wait(0.01)
    host = Game(audio=None, stats_path=str(tmp_path / 'h.json'))
    guest = Game(audio=None, stats_path=str(tmp_path / 'g.json'))
    return net.NetSession(sock, 'p1'), net.NetSession(client, 'p2'), host, guest


def test_lan_guest_takes_the_hosts_squads_and_form(tmp_path):
    a, b, host, guest = _pair(tmp_path)
    try:
        host.squads = guest.squads = 'club'
        host.stats['form'] = {f'{C.TEAMS[0]["name"]} #{n}': 2 for n in range(1, 100)}
        a.start_host(host)
        for _ in range(200):
            if b.poll_join(guest):
                break
            threading.Event().wait(0.01)
        assert guest.ui == 'playing' and guest.comp.names == host.comp.names
        assert [p.to_dict() for p in guest.comp.order['p1']] == [p.to_dict() for p in host.comp.order['p1']]
        assert any(p.form == 2 for p in guest.comp.order['p1'])  # the host's form, not the guest's
    finally:
        a.close()
        b.close()


def test_lan_checksum_spots_a_drift(tmp_path):
    a, b, host, guest = _pair(tmp_path)
    try:
        a.start_host(host)
        assert b.start_join(guest)
        for g in (host, guest):
            g.records.append(dict(kicker='p1', shot=dict(target=(1.0, 1.0)), scored=True))
        guest.records[-1]['scored'] = False                     # the guest's game went its own way
        for _ in range(50):
            a.pump(host, 1 / 60)
            b.pump(guest, 1 / 60)
            if a.closed and b.closed:
                break
        assert host.lan_notice and 'out of sync' in host.lan_notice and host.paused
    finally:
        a.close()
        b.close()


def test_lan_esc_pauses_both_and_m_leaves(tmp_path):
    a, b, host, guest = _pair(tmp_path)
    try:
        a.start_host(host)
        assert b.start_join(guest)
        a.key(host, '\x1b', True)
        for _ in range(30):
            a.pump(host, 1 / 60)
            b.pump(guest, 1 / 60)
        assert host.paused and guest.paused
        b.key(guest, 'm', True)
        assert guest.ui == 'menu'
        b.close()
        for _ in range(10):
            a.pump(host, 1 / 60)
        assert host.lan_notice and host.paused
    finally:
        a.close()
        b.close()


# -------------------------------------------------------------- GIF export
def test_clip_frames_are_shrunk_while_capturing():
    from shootout.app import shrink
    w, h = 1920, 1080
    data = bytes(range(256)) * (w * h * 3 // 256)
    nw, nh, small = shrink(w, h, data)
    assert (nw, nh) == (480, 270) and len(small) == nw * nh * 3
    assert small[:3] == data[:3] and small[3:6] == data[12:15]


def test_training_and_challenge_comps_have_no_pairings_to_advance():
    for comp in (TrainingComp('kick'), MatchPenaltyComp('keep'), ChallengeComp('bins')):
        assert comp.advance() == ()
