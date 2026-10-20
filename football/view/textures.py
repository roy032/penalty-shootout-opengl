"""Textures painted in code: grass, the ball's panels, crowds, ad boards and
the sky. Nothing is loaded from disk."""

import math
import random

from panda3d.core import PNMImage, SamplerState, Texture


def _tex(img, name, mip=True, wrap=True):
    t = Texture(name)
    t.load(img)
    if mip:
        t.set_minfilter(SamplerState.FT_linear_mipmap_linear)
        t.set_anisotropic_degree(8)
    t.set_magfilter(SamplerState.FT_linear)
    if not wrap:
        t.set_wrap_u(SamplerState.WM_clamp)
        t.set_wrap_v(SamplerState.WM_clamp)
    return t


def grass(size=256, seed=3):
    """Tileable grass blades: fine noise around a mid green, used as a detail texture."""
    r = random.Random(seed)
    img = PNMImage(size, size, 3)
    # Value noise on a small lattice, tiled
    g = 16
    lat = [[r.random() for _ in range(g)] for _ in range(g)]

    def noise(x, y):
        fx, fy = x / size * g, y / size * g
        x0, y0 = int(fx) % g, int(fy) % g
        x1, y1 = (x0 + 1) % g, (y0 + 1) % g
        tx, ty = fx - int(fx), fy - int(fy)
        tx, ty = tx * tx * (3 - 2 * tx), ty * ty * (3 - 2 * ty)
        a = lat[y0][x0] * (1 - tx) + lat[y0][x1] * tx
        b = lat[y1][x0] * (1 - tx) + lat[y1][x1] * tx
        return a * (1 - ty) + b * ty

    for y in range(size):
        for x in range(size):
            n = 0.6 * noise(x, y) + 0.4 * r.random()
            v = 0.82 + 0.3 * n
            img.set_xel(x, y, min(1.0, v * 0.98), min(1.0, v), min(1.0, v * 0.95))
    return _tex(img, 'grass')


def ball(size=256):
    """Modern ball: white with dark curved panels and a coloured trim."""
    img = PNMImage(size * 2, size, 3)
    img.fill(0.97, 0.97, 0.97)
    for y in range(size):
        lat = (y / size - 0.5) * math.pi
        for x in range(size * 2):
            lon = x / (size * 2) * 2 * math.pi
            # Six swooshes wrapping round the ball
            s = math.sin(lon * 3 + math.sin(lat * 2.0) * 1.6) * math.cos(lat)
            t = math.sin(lat * 4 + lon) * 0.5
            if abs(s - t * 0.3) < 0.14:
                img.set_xel(x, y, 0.08, 0.1, 0.16)
            elif abs(s - t * 0.3) < 0.2:
                img.set_xel(x, y, 0.95, 0.3, 0.15)
    return _tex(img, 'ball')


def crowd(w=512, h=128, seed=7, colors=None):
    """Rows of supporters: heads, shirts and scarves in the clubs' colours."""
    r = random.Random(seed)
    img = PNMImage(w, h, 4)
    img.fill(0.08, 0.08, 0.1)
    img.alpha_fill(1.0)
    colors = colors or [(0.85, 0.12, 0.15), (0.15, 0.35, 0.9)]
    skins = [(0.96, 0.8, 0.66), (0.78, 0.58, 0.42), (0.44, 0.3, 0.2), (0.6, 0.42, 0.28)]
    rows = 4
    rh = h // rows
    for row in range(rows):
        x = r.randint(0, 6)
        while x < w:
            cx = x + r.randint(4, 6)
            base = row * rh + rh
            body = r.choice(colors) if r.random() < 0.75 else (r.random() * 0.6, r.random() * 0.6, r.random() * 0.6)
            sk = r.choice(skins)
            bw = r.randint(4, 6)
            for yy in range(base - rh // 2, base):
                for xx in range(cx - bw, cx + bw):
                    if 0 <= xx < w and 0 <= yy < h:
                        img.set_xel(xx % w, yy, *body)
            hr = 3
            hy = base - rh // 2 - hr
            for yy in range(hy - hr, hy + hr):
                for xx in range(cx - hr, cx + hr):
                    if (xx - cx) ** 2 + (yy - hy) ** 2 <= hr * hr and 0 <= yy < h:
                        img.set_xel(xx % w, yy, *sk)
            x += r.randint(10, 14)
    return _tex(img, 'crowd')


def ad_board(texts, w=1024, h=64, seed=1):
    """LED perimeter boards: blocks of colour with simple chunky lettering."""
    r = random.Random(seed)
    img = PNMImage(w, h, 3)
    block = w // max(1, len(texts))
    for i, (text, bg, fg) in enumerate(texts):
        for y in range(h):
            for x in range(i * block, min(w, (i + 1) * block)):
                img.set_xel(x, y, *bg)
        _draw_text(img, text, i * block + 12, h // 2, max(2, h // 12), fg)
    return _tex(img, 'ads')


# 3x5 bitmap font for boards and shirt numbers
_FONT = {
    'A': '010101111101101', 'B': '110101110101110', 'C': '011100100100011', 'D': '110101101101110',
    'E': '111100110100111', 'F': '111100110100100', 'G': '011100101101011', 'H': '101101111101101',
    'I': '111010010010111', 'J': '001001001101010', 'K': '101101110101101', 'L': '100100100100111',
    'M': '101111111101101', 'N': '110101101101101', 'O': '010101101101010', 'P': '110101110100100',
    'Q': '010101101110011', 'R': '110101110101101', 'S': '011100010001110', 'T': '111010010010010',
    'U': '101101101101111', 'V': '101101101101010', 'W': '101101111111101', 'X': '101101010101101',
    'Y': '101101010010010', 'Z': '111001010100111', '0': '111101101101111', '1': '010110010010111',
    '2': '110001010100111', '3': '110001010001110', '4': '101101111001001', '5': '111100110001110',
    '6': '011100111101111', '7': '111001010010010', '8': '111101111101111', '9': '111101111001110',
    ' ': '000000000000000', '-': '000000111000000', '!': '010010010000010', '.': '000000000000010',
}


def _draw_text(img, text, x0, ymid, scale, color):
    x = x0
    y0 = ymid - (5 * scale) // 2
    for ch in text.upper():
        bits = _FONT.get(ch, _FONT[' '])
        for j in range(5):
            for i in range(3):
                if bits[j * 3 + i] == '1':
                    for yy in range(scale):
                        for xx in range(scale):
                            px, py = x + i * scale + xx, y0 + j * scale + yy
                            if 0 <= px < img.get_x_size() and 0 <= py < img.get_y_size():
                                img.set_xel(px, py, *color)
        x += 4 * scale


def number(n, color=(1, 1, 1), size=64):
    """A shirt number on a transparent background."""
    img = PNMImage(size, size, 4)
    img.fill(0, 0, 0)
    img.alpha_fill(0.0)
    text = str(n)
    scale = size // (4 * len(text) + 1) if len(text) > 1 else size // 6
    scale = max(2, min(scale, size // 6))
    w = (4 * len(text) - 1) * scale
    x = (size - w) // 2
    y0 = (size - 5 * scale) // 2
    for ch in text:
        bits = _FONT.get(ch, _FONT['0'])
        for j in range(5):
            for i in range(3):
                if bits[j * 3 + i] == '1':
                    for yy in range(scale):
                        for xx in range(scale):
                            img.set_xel_a(x + i * scale + xx, y0 + j * scale + yy, color[0], color[1], color[2], 1.0)
        x += 4 * scale
    return _tex(img, 'num%s' % n, wrap=False)


def sky(night=False, w=8, h=256):
    """Vertical gradient for the sky dome."""
    img = PNMImage(w, h, 3)
    for y in range(h):
        t = y / (h - 1)          # 0 top .. 1 horizon
        if night:
            top, hor = (0.01, 0.015, 0.04), (0.08, 0.1, 0.18)
        else:
            top, hor = (0.22, 0.45, 0.85), (0.72, 0.84, 0.95)
        c = [top[i] + (hor[i] - top[i]) * t ** 1.6 for i in range(3)]
        for x in range(w):
            img.set_xel(x, y, *c)
    return _tex(img, 'sky', mip=False, wrap=False)


def radial(size=64, color=(1, 1, 1), soft=2.0):
    """Soft round glow (floodlight flares, shadows under players, the player marker)."""
    img = PNMImage(size, size, 4)
    img.fill(*color)
    c = (size - 1) / 2.0
    for y in range(size):
        for x in range(size):
            d = math.hypot(x - c, y - c) / c
            img.set_alpha(x, y, max(0.0, 1.0 - d) ** soft)
    return _tex(img, 'glow', wrap=False)


def ring(size=128, color=(1, 1, 1), width=0.18):
    """Marker ring drawn under the controlled player."""
    img = PNMImage(size, size, 4)
    img.fill(*color)
    c = (size - 1) / 2.0
    for y in range(size):
        for x in range(size):
            d = math.hypot(x - c, y - c) / c
            a = max(0.0, 1.0 - abs(d - (1.0 - width)) / width) if d <= 1.0 else 0.0
            img.set_alpha(x, y, min(1.0, a * 1.4))
    return _tex(img, 'ring', wrap=False)


def net(size=64, cells=8):
    """See-through net mesh: white strings on transparent."""
    img = PNMImage(size, size, 4)
    img.fill(1, 1, 1)
    img.alpha_fill(0.0)
    step = size // cells
    for y in range(size):
        for x in range(size):
            if x % step == 0 or y % step == 0:
                img.set_alpha(x, y, 0.9)
    return _tex(img, 'net')
