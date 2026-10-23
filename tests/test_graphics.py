import random

from shootout import config as C, gfx, stadium
from shootout.controls import CONTROLS
from shootout.game import (DAYTIMES, Game, REPLAY_CAMERAS, auto_camera, goal_line_call, replay_speed, shot_xg)


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


def close(a, b, eps=1e-6):
    return all(abs(x - y) < eps for x, y in zip(a, b))


# ------------------------------------------------------------- matrix maths
def test_look_at_and_rigid_inverse_round_trip():
    view = gfx.look_at((3.0, 2.0, 9.0), (0.0, 1.0, -15.0))
    inv = gfx.invert_rigid(view)
    p = (1.5, -0.4, 7.25)
    assert close(gfx.transform(inv, gfx.transform(view, p)[:3])[:3], p)
    # The eye sits at the origin of eye space
    assert close(gfx.transform(view, (3.0, 2.0, 9.0))[:3], (0.0, 0.0, 0.0))


def test_project_puts_the_look_point_in_the_middle():
    eye, look = (2.0, 3.0, 10.0), (0.0, 1.0, -15.0)
    sp = gfx.project(look, gfx.perspective(50.0, 1.5, 0.05, 250.0), gfx.look_at(eye, look))
    assert close(sp, (0.5, 0.5))
    behind = gfx.project((2.0, 3.0, 20.0), gfx.perspective(50.0, 1.5, 0.05, 250.0), gfx.look_at(eye, look))
    assert behind is None


def test_quality_setting_round_trips_and_defaults(tmp_path):
    path = str(tmp_path / 'g' / 'graphics.json')
    assert gfx.load_quality(path) == 'high'
    gfx.save_quality('medium', path)
    assert gfx.load_quality(path) == 'medium'
    with open(path, 'w') as f:
        f.write('{"quality": "ultra"}')
    assert gfx.load_quality(path) == 'high'


# --------------------------------------------------------------- the menu
def test_menu_has_graphics_stadium_and_dusk(tmp_path, monkeypatch):
    monkeypatch.setattr(gfx, 'SETTINGS_FILE', str(tmp_path / 'graphics.json'))
    g = make_game(tmp_path, variant='stadium')
    rows = g.menu_rows()
    assert 'graphics' in rows and 'stadium' in rows
    g.variant = 'park'
    assert 'stadium' not in g.menu_rows()
    seen = set()
    for _ in DAYTIMES:
        g.menu_change('daytime', 1)
        seen.add(g.daytime)
    assert seen == {'night', 'day', 'dusk', 'sunset'}
    g.menu_change('stadium', 1)
    assert g.stadium in stadium.THEMES and g.stadium != 'classic'
    before = g.graphics
    g.menu_change('graphics', 1)
    assert g.graphics != before and g.gfx_request
    assert gfx.load_quality() == g.graphics


# --------------------------------------------------------- broadcast maths
def test_xg_rewards_corners_and_punishes_misses():
    corner = shot_xg((C.GOAL_HALF_WIDTH - 0.4, C.GOAL_HEIGHT - 0.4), 0.0, 28.0)
    middle = shot_xg((0.0, 1.0), 0.0, 18.0)
    wide = shot_xg((C.GOAL_HALF_WIDTH + 1.0, 1.0))
    assert corner > middle > wide
    assert 0.0 < wide < 0.1 and corner <= 0.97


def _frames(zs, x=0.5, y=0.4):
    return [dict(ball=(x, y, z)) for z in zs]


def test_goal_line_call_measures_the_deepest_point():
    line = C.GOAL_LINE_Z
    over = goal_line_call(_frames([line + 3.0, line + 1.0, line - 0.2, line - 0.6]))
    assert over['goal'] and over['frame'] == 3 and not over['tight']
    shy = goal_line_call(_frames([line + 3.0, line + 0.5, line - 0.05, line + 0.4]))
    assert not shy['goal'] and shy['tight'] and shy['frame'] == 2
    assert goal_line_call(_frames([line + 3.0], x=C.GOAL_HALF_WIDTH + 2.0)) is None


def test_replay_goes_super_slow_round_the_strike_and_cuts_cameras():
    replay = dict(contact=40, events=[70], glt=None)
    assert replay_speed(42, replay) < replay_speed(20, replay)
    assert replay_speed(70, replay) < replay_speed(20, replay)
    assert auto_camera(10, replay) == 'spider'
    assert auto_camera(42, replay) == 'strike'
    assert auto_camera(80, replay) == 'net'
    replay['glt'] = dict(frame=60, tight=True)
    assert auto_camera(70, replay) == 'goalline'
    assert REPLAY_CAMERAS[0] == 'auto'


# ------------------------------------------------------- what the renderer sees
def test_graphics_env_and_the_dusk_sky(tmp_path):
    g = make_game(tmp_path, daytime='dusk', weather='snow', stadium='arena')
    env = g.scene_env()
    for key in ('theme', 'dusk', 'match', 'wear', 'snow', 'screen', 'leaving', 'win', 'roof'):
        assert key in env
    assert env['theme'] == 'arena' and env['dusk'] == 0.0
    run(g, 30.0)
    later = g.scene_env()
    assert 0.0 < later['dusk'] < 1.0
    assert later['snow'] > env['snow'] and later['roof'] > 0.5
    assert stadium.lit_banks('dusk', 1.0) == [True] * 4 and not any(stadium.lit_banks('dusk', 0.0))


def test_new_match_gets_a_new_id(tmp_path):
    g = make_game(tmp_path)
    first = g.scene_env()['match']
    g.new_match()
    assert g.scene_env()['match'] != first


def test_winning_kick_runs_in_slow_motion_with_a_cinematic(tmp_path):
    g = make_game(tmp_path, mode='pvp', kicks_per_side=1)
    for _ in range(20):
        while g.phase != 'aim' and g.phase not in ('replay', 'ended'):
            run(g, 1 / 60)
        if g.phase != 'aim':
            break
        g.aim = [2.6, 0.6] if g.kicker == 'p1' else [0.0, 2.6]
        g.key_down(CONTROLS[g.kicker]['shoot'])
        for _ in range(240):
            run(g, 1 / 60)
            if g.power is not None or g.phase == 'flight':
                break
        while g.phase not in ('result', 'replay', 'ended'):
            run(g, 1 / 60)
        if g.comp.finished:
            break
        while g.phase == 'result':
            run(g, 1 / 60)
    assert g.comp.finished and g.phase == 'result'
    assert g.time_scale() < 1.0
    env = g.scene_env()
    assert env['win'] is not None and env['win']['side'] == g.comp.winner
    assert g.hero_name()
    run(g, 6.0)
    assert g.time_scale() == 1.0
