import json
import random

from shootout import characters as CH, commentary, config as C, scenarios
from shootout import squad as S
from shootout.game import Game
from shootout.modes import CareerComp, ShootoutComp, career_defaults

from test_game import make_game, play_match


def fresh(tmp_path, mode='pvc', seed=4, **settings):
    """A game that keeps its files in tmp_path; start_match is left to the test."""
    g = Game(audio=None, rng=random.Random(seed), stats_path=str(tmp_path / 'stats.json'))
    g.players_file = str(tmp_path / 'players.json')
    g.mode = mode
    for k, v in settings.items():
        setattr(g, k, v)
    return g


# ------------------------------------------------------------------ roster
def test_roster_is_valid():
    keys = [c['key'] for c in CH.ROSTER]
    assert len(keys) == len(set(keys))
    for c in CH.ROSTER:
        keep = c['role'] == 'keep'
        assert c['persona'] in (CH.KEEPER_PERSONAS if keep else CH.TAKER_PERSONAS), c['key']
        assert c['signature'] is None or c['signature'] in CH.SIGNATURES, c['key']
        assert c['celebration'] is None or c['celebration'] in (
            CH.SAVE_CELEBRATIONS if keep else CH.CELEBRATIONS), c['key']
        assert c['look']['hair'] in CH.HAIRS and c['look']['hc'] in CH.HAIR_COLOURS, c['key']
        assert all(0 <= c[k] <= 1 for k in ('composure', 'power', 'placement', 'aura')), c['key']
        assert len(c['name']) <= 12, c['key']
    women = [c for c in CH.ROSTER if c['women']]
    assert women and any(c['role'] == 'keep' for c in women)
    for era in ('legend', 'icon', 'current', 'fantasy'):
        assert CH.filtered(era), era


def test_player_round_trips_character_fields():
    p = CH.make_player(CH.get(CH.ROSTER[0]['key']))
    q = S.Player.from_dict(json.loads(json.dumps(p.to_dict())))
    for f in S.Player.CHAR_FIELDS:
        a, b = getattr(p, f), getattr(q, f)
        assert (list(a) if isinstance(a, tuple) else a) == (list(b) if isinstance(b, tuple) else b), f


def test_gender_swaps_pronouns():
    assert commentary._gender('He steps up. His run-up.', True) == 'She steps up. Her run-up.'
    assert commentary._gender('He steps up.', False) == 'He steps up.'


# ------------------------------------------------------------------ squads
def test_legends_squads_are_characters(tmp_path):
    g = fresh(tmp_path, squads='legends')
    g.start_match()
    assert isinstance(g.comp, ShootoutComp)
    for s in ('p1', 'p2'):
        sq = g.comp.squads[s]
        assert all(p.char for p in sq)
        assert sq[-1].keeper
    keys = [p.char for s in ('p1', 'p2') for p in g.comp.squads[s]]
    assert len(keys) == len(set(keys))


def test_pick_flow_keeps_the_order(tmp_path):
    g = fresh(tmp_path, squads='pick')
    g.start_match()
    assert g.ui == 'select'
    takers = [c['key'] for c in CH.filtered('current', 'kick')[:5]]
    g.select['filter'] = 'current'
    for k in takers:
        g.select['cursor'] = [c['key'] for c in g.select_list()].index(k)
        g._select_key('\r')
    assert g.select['step'] == 1
    g._select_key('r')                                 # random keeper
    assert g.ui != 'select' and g.select is None
    order = [p.char for p in g.comp.order['p1'][:5]]
    assert order == takers
    assert g.comp.squads['p1'][-1].keeper


def test_cannot_pick_twice_or_locked(tmp_path):
    g = fresh(tmp_path, squads='pick')
    g.start_match()
    first = g.select_current()
    g._select_key('\r')
    g.select['cursor'] = [c['key'] for c in g.select_list()].index(first['key'])
    g._select_key('\r')
    assert g.select['picked']['p1'] == [first['key']]
    locked = next(c for c in CH.ROSTER if c.get('unlock') and c['role'] == 'kick')
    assert CH.locked(locked, g.stats)
    assert not CH.locked(locked, {'achievements': [locked['unlock']]})
    g.select['cursor'] = [c['key'] for c in g.select_list()].index(locked['key'])
    g._select_key('\r')
    assert locked['key'] not in g.select['picked']['p1']
    g._select_key('x')
    assert g.select['picked']['p1'] == []


def test_party_pick(tmp_path):
    g = fresh(tmp_path, mode='party', squads='pick', party_players=3, party_type='king')
    g.start_match()
    assert g.ui == 'select' and len(g.select['plan']) == 3
    for _ in range(3):
        g._select_key('r')
    assert len(g.picks['party']) == 3
    assert [p.char for p in g.comp.chars] == g.picks['party']
    assert g.taker_label().count(g.comp.chars[0].name) <= 1


def test_draft_skips_locked_and_custom():
    rng = random.Random(1)
    for _ in range(20):
        takers, keepers = CH.draft(rng, 10, 1, stats={})
        assert all(not c.get('unlock') and c['era'] != 'custom' for c in takers + keepers)


# ------------------------------------------------------------------ create
def test_create_save_and_reload(tmp_path):
    g = fresh(tmp_path)
    g.open_create('menu')
    ch = g.create['ch']
    ch['name'] = 'TESTER'
    before = CH.budget_left(ch)
    g.create_change('composure', 1)
    assert CH.budget_left(ch) <= before
    for _ in range(40):
        g.create_change('power', 1)
    assert CH.budget_left(ch) >= -1e-9                 # the rating budget holds
    saved = g.save_created()
    assert saved and saved['era'] == 'custom' and g.ui == 'menu'
    assert CH.get(saved['key'])
    CH.EXTRA[:] = []
    assert CH.load_custom(g.players_file) == 1
    assert CH.get(saved['key'])['name'] == 'TESTER'
    CH.EXTRA[:] = []


def test_mods_add_players(tmp_path):
    (tmp_path / 'mine.json').write_text(json.dumps({'players': [
        dict(name='Mod Hero', composure=0.8, power=0.7, placement=0.6, persona='ice'),
        dict(name='Broken', composure=4),
    ]}))
    try:
        assert scenarios.load_mods(str(tmp_path)) == 1
        ch = next(c for c in CH.EXTRA if c['era'] == 'mod')
        assert ch['name'] == 'MOD HERO' and ch['persona'] == 'ice'
        assert ch in CH.filtered('custom')
    finally:
        CH.EXTRA[:] = []


# ------------------------------------------------------------- personalities
def test_persona_pressure():
    kid = S.Player(9, 'KID', 0.5, 0.5, 0.5)
    kid.persona = 'kid'
    calm = S.Player(9, 'CALM', 0.5, 0.5, 0.5)
    clutch = S.Player(9, 'BIG', 0.5, 0.5, 0.5)
    clutch.persona = 'clutch'
    assert kid.pressure(4) > calm.pressure(4)
    assert clutch.pressure(2, 'must_score') < calm.pressure(2, 'must_score')
    calm.form = 2
    assert calm.pressure(2) < S.Player(9, 'X', 0.5, 0.5, 0.5).pressure(2)


def test_perfect_bottle_notes_are_never_wrong():
    p = S.Player(9, 'LEFTY', 0.5, 0.5, 0.5, natural=0.8)
    rng = random.Random(3)
    notes = {S.bottle_note(p, rng, perfect=True) for _ in range(50)}
    assert len(notes) == 1


def test_form_rises_and_fades(tmp_path):
    g = make_game(tmp_path)
    g.log = [dict(pkey='x', scored=True, n=4), dict(pkey='y', scored=False, n=1)]
    g._update_form()
    assert g.stats['form'] == {'x': 1, 'y': -1}
    g.log = [dict(pkey='x', scored=True, n=0)]
    g._update_form()
    assert g.stats['form']['x'] == 0


def test_figure_celebrates_its_own_way(tmp_path):
    g = make_game(tmp_path, seed=6, squads='legends')
    for s in ('p1', 'p2'):
        for p in g.comp.squads[s]:
            p.celebration = 'siuu'
    seen = []
    n = 0

    def watch(_g, seconds):
        nonlocal n
        for _ in range(int(round(seconds * 60))):
            g.update(1 / 60)
            if len(g.log) > n:
                n = len(g.log)
                if g.log[-1]['scored']:
                    seen.append(g.celebration)

    import test_game
    real = test_game.run
    test_game.run = watch
    try:
        play_match(g)
    finally:
        test_game.run = real
    assert seen and set(seen) == {'siuu'}


# ------------------------------------------------------------------ career
def test_career_rival_and_story():
    career = career_defaults('kick')
    rival = Game._career_rival(career)
    assert rival.keeper and career['rival'] == rival.char
    assert Game._career_rival(dict(career_defaults('kick'))).char == rival.char   # same rival every career
    career['games'] = 2
    comp = CareerComp(career, None, rival)
    assert comp.rival_game and comp.keeper_player('p2') is rival
    assert comp.story()
    career['games'] = 4
    assert not CareerComp(career, None, rival).rival_game


# ------------------------------------------------------------------ replays
def test_legends_replay_round_trip(tmp_path):
    g = make_game(tmp_path, seed=8, squads='legends')
    play_match(g)
    data = json.loads(json.dumps(g.replay_data()))
    assert data['squads']
    C.apply_variant('stadium')
    watch = Game(audio=None, rng=random.Random(5), stats_path=str(tmp_path / 'w.json'))
    watch.load_replay(data)
    for s in ('p1', 'p2'):
        assert [p.char for p in watch.comp.order[s]] == [p.char for p in g.comp.order[s]]
    t = 0
    while watch.phase not in ('replay', 'ended') and t < 60 * 900:
        watch.update(1 / 60)
        t += 1
    assert watch.comp.rules.results == g.comp.rules.results
