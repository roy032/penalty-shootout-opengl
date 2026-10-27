"""Headless checks for the skinned footballers: the mesh builds, every action
state poses cleanly and blends, and the kit textures carry the name and number.
Also the ball's spin on a bounce and the camera's springs."""

import math

import pytest

np = pytest.importorskip('numpy')
pytest.importorskip('panda3d')

from panda3d.core import GeomVertexReader, NodePath, loadPrcFileData  # noqa: E402

loadPrcFileData('', 'window-type none')

from football.sim import ball as BL  # noqa: E402
from football.sim import roster as R  # noqa: E402
from football.view import camera as CAM  # noqa: E402
from football.view import kits as K  # noqa: E402
from football.view import models as M  # noqa: E402

STATES = [('run', '', 0.0), ('run', '', 7.5), ('skill', '', 4.0), ('kick', 'shoot', 0.0), ('kick', 'pass', 0.0),
          ('kick', 'lob', 0.0), ('kick', 'header', 0.0), ('kick', 'punt', 0.0), ('tackle', 'stand', 0.0),
          ('slide', 'slide', 0.0), ('down', 'trip', 0.0), ('down', 'slip', 0.0), ('getup', '', 0.0),
          ('dive', 'mid', 0.0), ('dive', 'high', 0.0), ('dive', 'block', 0.0), ('hold', '', 2.0),
          ('throw', 'throw', 0.0), ('jump', '', 0.0), ('celebrate', 'run', 5.0), ('celebrate', 'win', 0.0)]


def _player(key='henry', keeper=False, team='legends'):
    fb = R.from_character(key)
    return M.Footballer(NodePath('root'), fb, R.team_info(team), keeper=keeper)


def _verts(p):
    return sum(g.get_vertex_data().get_num_rows() for gn in p.body.find_all_matches('**/+GeomNode')
               for g in gn.node().get_geoms())


def test_player_builds_every_part():
    p = _player('ronaldinho')
    names = {gn.get_name() for gn in p.body.find_all_matches('**/+GeomNode')}
    assert {'skin', 'head', 'hair', 'shirt', 'trim', 'lower', 'boots'} <= names
    assert 4000 < _verts(p) < 14000
    assert len(p.rig.joints) == 21


def test_keeper_has_gloves_and_long_sleeves():
    p = _player('pele', keeper=True)
    q = _player('pele', keeper=False)

    def forearm(pl):
        # Shirt out at the arms below the elbow (rest pose, arms down)
        r = GeomVertexReader(pl.body.find('**/shirt').node().get_geom(0).get_vertex_data(), 'vertex')
        n = 0
        while not r.is_at_end():
            v = r.get_data3()
            n += abs(v[0]) > 0.19 and 1.0 < v[2] < 1.1
        return n
    # Long sleeves cover the forearm; gloves make the boots part bigger
    assert forearm(p) > forearm(q) + 50
    assert _rows(p, 'boots') > _rows(q, 'boots')


def _rows(pl, name):
    return pl.body.find('**/' + name).node().get_geom(0).get_vertex_data().get_num_rows()


def test_every_state_poses_without_nans():
    p = _player('pele')
    t = 0.0
    for state, anim, speed in STATES:
        for k in range(12):
            t += 1 / 30
            p.pose(0.0, 0.0, 0.0, 0.3, state, anim, k / 30, 0.0, speed, (1.0, 0.5, 0.9), 0.5, t=t)
            assert all(math.isfinite(v) for v in p._cur), (state, anim)
    assert p.ankles[0].get_pos(p.root) is not None


def test_state_change_blends_instead_of_snapping():
    p = _player('zidane')
    for k in range(10):
        p.pose(0, 0, 0, 0, 'run', '', 0, 0, 0.0, None, 0.5, t=k / 30)
    still = list(p._cur)
    p.pose(0, 0, 0, 0, 'slide', 'slide', 0.5, 0, 0.0, None, 0.75, t=11 / 30)
    first = list(p._cur)
    target = p._target('slide', 'slide', 0.5, 0, 0.0, None, 0.75, False, 11 / 30)
    i = M._IDX['body_p']
    assert still[i] < first[i] < target[i]


def test_stride_follows_ground_speed():
    p = _player('kane', team='stars')
    p.pose(0, 0, 0, 0, 'run', '', 0, 0, 6.0, None, t=0.0)
    start = p._phase
    for k in range(1, 31):
        p.pose(0, 0, 0, 0, 'run', '', 0, 0, 6.0, None, t=k / 30)
    # One second at 6 m/s is about 1.8 strides (3.4 m each), not six
    cycles = (p._phase - start) % 1.0 + 1
    assert 1.5 < cycles < 2.2


def test_shirt_has_name_and_number_on_the_back():
    kit = R.team_info('stars')
    tex = K.shirt(kit, 10, 'MESSI')
    w, h = tex.get_x_size(), tex.get_y_size()
    px = np.frombuffer(bytes(tex.get_ram_image()), dtype=np.uint8).reshape(h, w, -1)[::-1, :, 2::-1]
    back = px[int(h * 0.3):int(h * 0.55), int(w * 0.7):int(w * 0.8)].astype(float)
    side = px[int(h * 0.3):int(h * 0.55), int(w * 0.12):int(w * 0.18)].astype(float)
    # The number is drawn in a contrasting colour, so the back varies far more
    assert back.std(axis=(0, 1)).mean() > side.std(axis=(0, 1)).mean() * 3
    assert K.shirt(kit, 10, 'MESSI') is tex


def test_stroke_font_draws_text():
    img = np.zeros((40, 200, 3), dtype=np.float32)
    w = K.draw_text(img, 'GOAL 9', 4, 4, 30, (1, 1, 1))
    assert abs(w - K.text_width('GOAL 9') * 5) < 1e-6
    assert img[:, :int(w) + 8].max() == pytest.approx(1.0)
    assert img[:, int(w) + 12:].max() == 0.0


def test_topspin_kicks_on_and_backspin_checks_a_bounce():
    def after_bounce(spin_y):
        b = BL.Ball(None)
        b.pos = [0.0, 0.0, 1.0]
        b.vel = [10.0, 0.0, -4.0]
        b.spin = [0.0, spin_y, 0.0]
        for _ in range(200):
            if b._integrate(1 / 120) == 'bounce':
                return b.vel[0]
        raise AssertionError('no bounce')
    plain = after_bounce(0.0)
    assert after_bounce(40.0) > plain > after_bounce(-40.0)


def test_camera_spring_settles_without_overshoot():
    x, v = [0.0], [0.0]
    peak = 0.0
    for _ in range(300):
        CAM._spring(x, v, [10.0], 3.0, 1 / 60)
        peak = max(peak, x[0])
    assert abs(x[0] - 10.0) < 0.05
    assert peak <= 10.0 + 1e-6
