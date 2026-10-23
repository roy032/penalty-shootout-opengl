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


# ---------------------------------------------------------------- numpy-painted textures
def _from_array(arr, name, mip=True, wrap=True):
    """Texture from a float array (h, w, 3 or 4) in 0..1, row 0 at the top."""
    import numpy as np
    a = np.clip(arr, 0.0, 1.0)
    h, w, c = a.shape
    data = (a[::-1] * 255.0 + 0.5).astype(np.uint8)
    # Panda keeps texels as BGR(A)
    if c == 3:
        data = data[:, :, [2, 1, 0]]
        fmt = Texture.F_rgb
    else:
        data = data[:, :, [2, 1, 0, 3]]
        fmt = Texture.F_rgba
    t = Texture(name)
    t.setup_2d_texture(w, h, Texture.T_unsigned_byte, fmt)
    t.set_ram_image(data.tobytes())
    if mip:
        t.set_minfilter(SamplerState.FT_linear_mipmap_linear)
        t.set_anisotropic_degree(8)
    else:
        t.set_minfilter(SamplerState.FT_linear)
    t.set_magfilter(SamplerState.FT_linear)
    if not wrap:
        t.set_wrap_u(SamplerState.WM_clamp)
        t.set_wrap_v(SamplerState.WM_clamp)
    return t


def _value_noise(size, cells, rng):
    """Tileable smooth value noise in 0..1."""
    import numpy as np
    lat = rng.random((cells, cells))
    x = np.arange(size) / size * cells
    i0 = np.floor(x).astype(int) % cells
    i1 = (i0 + 1) % cells
    f = x - np.floor(x)
    f = f * f * (3 - 2 * f)
    a = lat[i0][:, i0] * (1 - f)[None, :] + lat[i0][:, i1] * f[None, :]
    b = lat[i1][:, i0] * (1 - f)[None, :] + lat[i1][:, i1] * f[None, :]
    return a * (1 - f)[:, None] + b * f[:, None]


def _fbm(size, base_cells, octaves, rng):
    out = 0.0
    amp, tot = 1.0, 0.0
    for o in range(octaves):
        out = out + _value_noise(size, base_cells * (2 ** o), rng) * amp
        tot += amp
        amp *= 0.5
    return out / tot


_noise_cache = {}


def noise(size=256, seed=11):
    """Four channels of tileable noise for the shaders: broad, medium, fine and patchy."""
    if (size, seed) in _noise_cache:
        return _noise_cache[(size, seed)]
    import numpy as np
    rng = np.random.default_rng(seed)
    r = _fbm(size, 4, 4, rng)
    g = _fbm(size, 8, 3, rng)
    b = _fbm(size, 32, 2, rng)
    a = _fbm(size, 6, 4, rng)

    def norm(c):
        return (c - c.min()) / max(1e-6, c.max() - c.min())

    t = _from_array(np.dstack([norm(r), norm(g), norm(b), norm(a)]), 'noise')
    _noise_cache[(size, seed)] = t
    return t


def grass_detail(size=256, seed=3):
    """Tileable close-up grass: thin blade streaks over fine noise, mid grey around 0.92."""
    import numpy as np
    rng = np.random.default_rng(seed)
    img = 0.86 + 0.14 * _fbm(size, 16, 3, rng)
    # Blades: short bright and dark dashes, wrapped round the edges
    for _ in range(2600):
        x, y = rng.integers(0, size, 2)
        ln = rng.integers(3, 9)
        v = rng.uniform(-0.16, 0.14)
        lean = rng.uniform(-0.4, 0.4)
        for k in range(ln):
            img[(y + k) % size, int(x + k * lean) % size] += v * (1 - k / ln)
    img = np.clip(img, 0, 1.2) / 1.05
    rgb = np.dstack([img * 0.97, img, img * 0.93])
    return _from_array(rgb, 'grass_detail')


def crowd2(w=1024, h=128, seed=7, colors=None, seat=(0.35, 0.36, 0.4), fill=0.88, night=True):
    """One row of fans standing and sitting, with shoulders, arms, scarves and flags,
    shaded top to bottom; empty seats are see-through (alpha 0)."""
    import numpy as np
    rng = np.random.default_rng(seed)
    colors = colors or [(0.85, 0.12, 0.15), (0.15, 0.35, 0.9)]
    skins = [(0.96, 0.8, 0.66), (0.86, 0.66, 0.5), (0.66, 0.46, 0.32), (0.44, 0.3, 0.2), (0.3, 0.2, 0.14)]
    hairs = [(0.08, 0.06, 0.05), (0.25, 0.16, 0.08), (0.55, 0.38, 0.18), (0.8, 0.7, 0.45), (0.5, 0.5, 0.5)]
    neutral = [(0.15, 0.15, 0.17), (0.85, 0.85, 0.85), (0.3, 0.32, 0.4), (0.45, 0.3, 0.2), (0.2, 0.35, 0.25)]
    img = np.zeros((h, w, 4))
    yy, xx = np.mgrid[0:h, 0:w]

    def ellipse(cx, cy, rx, ry, col, alpha=1.0):
        x0, x1 = int(max(0, cx - rx - 1)), int(min(w, cx + rx + 2))
        y0, y1 = int(max(0, cy - ry - 1)), int(min(h, cy + ry + 2))
        if x0 >= x1 or y0 >= y1:
            return
        sx, sy = xx[y0:y1, x0:x1], yy[y0:y1, x0:x1]
        d = ((sx - cx) / rx) ** 2 + ((sy - cy) / ry) ** 2
        m = np.clip((1.0 - d) * max(rx, ry) * 0.9, 0, 1) * alpha
        reg = img[y0:y1, x0:x1]
        for c in range(3):
            reg[:, :, c] = reg[:, :, c] * (1 - m) + col[c] * m
        reg[:, :, 3] = np.maximum(reg[:, :, 3], m)

    def rect(x0, y0, x1, y1, col):
        x0, x1 = int(max(0, x0)), int(min(w, x1))
        y0, y1 = int(max(0, y0)), int(min(h, y1))
        if x0 < x1 and y0 < y1:
            img[y0:y1, x0:x1, :3] = col
            img[y0:y1, x0:x1, 3] = 1.0

    # The row is 1.25 m tall: 1 m is h / 1.25 pixels, and fans stand about 0.6 m apart
    pm = h / 1.25
    spacing = 0.6 * pm
    x = rng.uniform(0, spacing)
    while x < w - spacing * 0.5:
        cx = x + rng.uniform(-0.05, 0.05) * pm
        if rng.random() < fill:
            standing = rng.random() < 0.55
            body = colors[rng.integers(len(colors))] if rng.random() < 0.72 else neutral[rng.integers(len(neutral))]
            body = tuple(min(1.0, c * rng.uniform(0.8, 1.1)) for c in body)
            sk = skins[rng.integers(len(skins))]
            hr = hairs[rng.integers(len(hairs))]
            top = (0.2 if standing else 0.5) * pm + rng.uniform(-0.04, 0.04) * pm
            sw = rng.uniform(0.19, 0.24) * pm
            hd = 0.105 * pm
            neck = top + hd * 2.0
            # Torso: rounded shoulders down to the bottom of the row
            ellipse(cx, neck + 0.1 * pm, sw, 0.12 * pm, body)
            rect(cx - sw, neck + 0.1 * pm, cx + sw, h, body)
            up = rng.random() < 0.12
            for s in (-1, 1):
                if up:
                    ellipse(cx + s * (sw * 0.95), neck - 0.12 * pm, 0.06 * pm, 0.24 * pm, body)
                    ellipse(cx + s * (sw * 1.0), neck - 0.37 * pm, 0.05 * pm, 0.055 * pm, sk)
                else:
                    ellipse(cx + s * (sw - 0.02 * pm), neck + 0.34 * pm, 0.055 * pm, 0.26 * pm,
                            tuple(c * 0.82 for c in body))
            if rng.random() < 0.35:
                sc = colors[rng.integers(len(colors))]
                ellipse(cx, neck + 0.04 * pm, sw * 0.62, 0.045 * pm, sc)
                rect(cx + 0.03 * pm, neck + 0.04 * pm, cx + 0.09 * pm, neck + 0.32 * pm, sc)
            # Neck, head and hair
            rect(cx - 0.045 * pm, top + hd * 1.6, cx + 0.045 * pm, neck + 0.04 * pm, tuple(c * 0.85 for c in sk))
            ellipse(cx, top + hd, hd * 0.85, hd, sk)
            if rng.random() < 0.85:
                ellipse(cx, top + hd * 0.45, hd * 0.92, hd * 0.6, hr)
            if rng.random() < 0.1:
                ellipse(cx, top + hd * 0.3, hd * 1.0, hd * 0.55, colors[rng.integers(len(colors))])
        x += spacing * rng.uniform(0.9, 1.1)
    # Light from above, darker towards the feet and the seat row
    shade = np.linspace(1.08, 0.55, h)[:, None]
    img[:, :, :3] *= shade[:, :, None] if img.ndim == 3 else shade
    return _from_array(img, 'crowd2')


def led_board(texts, w=1024, h=64, seed=1):
    """LED perimeter boards: chunky letters made of glowing dots, on a dark panel."""
    import numpy as np
    img = np.zeros((h, w, 3))
    block = w // max(1, len(texts))
    pitch_px = 4
    for i, (text, bg, fg) in enumerate(texts):
        x0, x1 = i * block, (i + 1) * block
        tile = PNMImage(block, h, 3)
        tile.fill(*bg)
        sc = max(2, min(h // 12, (block - 20) // max(1, 4 * len(text))))
        _draw_text(tile, text, (block - (4 * len(text) - 1) * sc) // 2, h // 2, sc, fg)
        arr = np.zeros((h, block, 3))
        for yy in range(h):
            for xx in range(block):
                arr[yy, xx] = tile.get_xel(xx, yy)
        # Gradient behind the letters, like a real advert
        g = np.linspace(1.15, 0.75, block)[None, :, None]
        is_bg = (np.abs(arr - np.array(bg)[None, None, :]).sum(axis=2) < 0.02)[:, :, None]
        arr = np.where(is_bg, arr * g, arr)
        img[:, x0:x1] = arr
    # LED dot grid: bright cores, dim gaps
    yy, xx = np.mgrid[0:h, 0:w]
    dx = (xx % pitch_px) - (pitch_px - 1) / 2.0
    dy = (yy % pitch_px) - (pitch_px - 1) / 2.0
    dot = np.clip(1.25 - (dx * dx + dy * dy) / 3.0, 0.35, 1.0)
    img = img * dot[:, :, None]
    # A dark frame top and bottom
    img[:3] *= 0.15
    img[-3:] *= 0.15
    return _from_array(img, 'led')


def net2(size=128, cells=8):
    """Net: soft-edged white strings in a square mesh (anti-aliased, so it doesn't sparkle)."""
    import numpy as np
    step = size / cells
    yy, xx = np.mgrid[0:size, 0:size].astype(float)
    dx = np.abs(((xx + 0.5) % step) - step / 2) - step / 2
    dy = np.abs(((yy + 0.5) % step) - step / 2) - step / 2
    d = np.minimum(-dx, -dy)
    a = np.clip(1.6 - d, 0, 1) * 0.95
    img = np.dstack([np.ones_like(a), np.ones_like(a), np.ones_like(a), a])
    return _from_array(img, 'net2')


def sky_noise():
    return noise(256, 21)


def line_mask(segs, width, origin, size, ppm):
    """Anti-aliased mask of the pitch markings (white on black), for the grass shader.
    segs are (x0, y0, x1, y1) in metres; origin and size give the area the texture covers."""
    import numpy as np
    W = int(size[0] * ppm)
    H = int(size[1] * ppm)
    img = np.zeros((H, W), dtype=np.float32)
    half = width / 2.0 * ppm
    for x0, y0, x1, y1 in segs:
        ax, ay = (x0 - origin[0]) * ppm, (y0 - origin[1]) * ppm
        bx, by = (x1 - origin[0]) * ppm, (y1 - origin[1]) * ppm
        lo_x = max(0, int(min(ax, bx) - half - 2))
        hi_x = min(W, int(max(ax, bx) + half + 3))
        lo_y = max(0, int(min(ay, by) - half - 2))
        hi_y = min(H, int(max(ay, by) + half + 3))
        if lo_x >= hi_x or lo_y >= hi_y:
            continue
        yy, xx = np.mgrid[lo_y:hi_y, lo_x:hi_x].astype(np.float32) + 0.5
        dx, dy = bx - ax, by - ay
        L2 = dx * dx + dy * dy or 1.0
        t = np.clip(((xx - ax) * dx + (yy - ay) * dy) / L2, 0.0, 1.0)
        d = np.hypot(xx - (ax + t * dx), yy - (ay + t * dy))
        cov = np.clip(half - d + 0.5, 0.0, 1.0)
        reg = img[lo_y:hi_y, lo_x:hi_x]
        np.maximum(reg, cov, out=reg)
    # Row 0 of the array is y = origin (texture v = 0), so no flip: build the texture directly
    data = (img * 255.0 + 0.5).astype(np.uint8)
    t = Texture('lines')
    t.setup_2d_texture(W, H, Texture.T_unsigned_byte, Texture.F_luminance)
    t.set_ram_image(data.tobytes())
    t.set_minfilter(SamplerState.FT_linear_mipmap_linear)
    t.set_magfilter(SamplerState.FT_linear)
    t.set_anisotropic_degree(16)
    t.set_wrap_u(SamplerState.WM_border_color)
    t.set_wrap_v(SamplerState.WM_border_color)
    t.set_border_color((0, 0, 0, 0))
    return t
