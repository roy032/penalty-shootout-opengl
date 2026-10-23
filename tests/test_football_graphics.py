"""Headless checks for the football renderer's painted textures and shader set-up
(no window needed: textures are built in memory and shaders only parsed by Panda)."""

import pytest

np = pytest.importorskip('numpy')
pytest.importorskip('panda3d')

from football.view import shading as S  # noqa: E402
from football.view import textures as T  # noqa: E402


def _pixels(tex):
    w, h = tex.get_x_size(), tex.get_y_size()
    a = np.frombuffer(bytes(tex.get_ram_image()), dtype=np.uint8)
    return a.reshape(h, w, -1)


def test_line_mask_covers_markings_only():
    # One 2 m line along y = 0 from x = 1 to x = 3, 0.2 m wide, on a 4 x 2 m patch at 20 px/m
    tex = T.line_mask([(1.0, 0.0, 3.0, 0.0)], 0.2, (0.0, -1.0), (4.0, 2.0), 20)
    px = _pixels(tex)[:, :, 0]
    assert px.shape == (40, 80)
    assert px[20, 40] == 255           # on the line
    assert px[5, 40] == 0              # 0.75 m off it
    assert px[20, 5] == 0              # before it starts
    # Anti-aliased edges: some in-between values
    assert ((px > 0) & (px < 255)).any()


def test_crowd_has_people_and_gaps():
    px = _pixels(T.crowd2(seed=3, colors=[(1, 0, 0), (0, 0, 1)]))
    alpha = px[:, :, 3]
    filled = (alpha > 128).mean()
    assert 0.2 < filled < 0.9          # fans, with see-through gaps between heads


def test_led_board_and_noise_sizes():
    led = T.led_board([('PANDA LEAGUE', (0.05, 0.1, 0.35), (1, 1, 1)), ('TOP BINS', (0.1, 0.5, 0.3), (1, 1, 1))])
    assert (led.get_x_size(), led.get_y_size()) == (1024, 64)
    n = T.noise()
    assert n is T.noise()              # cached
    assert _pixels(n).shape == (256, 256, 4)


def test_shader_programs_build():
    for shadows in (False, True):
        assert S.lit_shader(shadows) is not None
        assert S.grass_shader(shadows) is not None
    assert S.sky_shader() is not None
    assert all(len(v) == 2 for v in S.MATERIALS.values())
