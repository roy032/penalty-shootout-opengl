"""Textures for the footballers, painted in code with numpy: shirts with the
fabric knit, side panels, crest and the name and number on the back; shorts,
socks, faces, hair strands and skin. Names and numbers use a small stroke
font drawn with soft edges, so they stay sharp at any size."""

import math
import zlib

import numpy as np

from . import textures as T

# ------------------------------------------------------------ stroke font
# Glyphs in a 4 x 6 box (x right, y up), as polylines
_O = [(1, 0), (3, 0), (4, 1), (4, 5), (3, 6), (1, 6), (0, 5), (0, 1), (1, 0)]
_P = [(0, 0), (0, 6), (3, 6), (4, 5), (4, 4), (3, 3), (0, 3)]
GLYPHS = {
    '0': [_O],
    '1': [[(1.0, 4.8), (2.3, 6), (2.3, 0)]],
    '2': [[(0, 5), (1, 6), (3, 6), (4, 5), (4, 4), (0, 0), (4, 0)]],
    '3': [[(0, 5), (1, 6), (3, 6), (4, 5), (4, 4), (3, 3), (1.5, 3)], [(3, 3), (4, 2), (4, 1), (3, 0), (1, 0), (0, 1)]],
    '4': [[(3, 0), (3, 6), (0, 2), (4, 2)]],
    '5': [[(4, 6), (0.3, 6), (0, 3.3), (3, 3.5), (4, 2.5), (4, 1), (3, 0), (1, 0), (0, 1)]],
    '6': [[(3.6, 6), (1.5, 6), (0, 4.5), (0, 1), (1, 0), (3, 0), (4, 1), (4, 2.5), (3, 3.5), (1, 3.5), (0, 2.5)]],
    '7': [[(0, 6), (4, 6), (1.5, 0)]],
    '8': [[(1, 3), (0, 4), (0, 5), (1, 6), (3, 6), (4, 5), (4, 4), (3, 3), (1, 3), (0, 2), (0, 1), (1, 0), (3, 0),
           (4, 1), (4, 2), (3, 3)]],
    '9': [[(0.4, 0), (2.5, 0), (4, 1.5), (4, 5), (3, 6), (1, 6), (0, 5), (0, 3.5), (1, 2.5), (3, 2.5), (4, 3.5)]],
    'A': [[(0, 0), (0, 4), (2, 6), (4, 4), (4, 0)], [(0, 2.5), (4, 2.5)]],
    'B': [[(0, 0), (0, 6), (3, 6), (4, 5), (4, 4), (3, 3), (0, 3)], [(3, 3), (4, 2), (4, 1), (3, 0), (0, 0)]],
    'C': [[(4, 5), (3, 6), (1, 6), (0, 5), (0, 1), (1, 0), (3, 0), (4, 1)]],
    'D': [[(0, 0), (0, 6), (2.5, 6), (4, 4.5), (4, 1.5), (2.5, 0), (0, 0)]],
    'E': [[(4, 6), (0, 6), (0, 0), (4, 0)], [(0, 3), (3, 3)]],
    'F': [[(4, 6), (0, 6), (0, 0)], [(0, 3), (3, 3)]],
    'G': [[(4, 5), (3, 6), (1, 6), (0, 5), (0, 1), (1, 0), (3, 0), (4, 1), (4, 3), (2.2, 3)]],
    'H': [[(0, 0), (0, 6)], [(4, 0), (4, 6)], [(0, 3), (4, 3)]],
    'I': [[(1, 6), (3, 6)], [(2, 6), (2, 0)], [(1, 0), (3, 0)]],
    'J': [[(4, 6), (4, 1), (3, 0), (1, 0), (0, 1)]],
    'K': [[(0, 0), (0, 6)], [(4, 6), (0, 2.2)], [(1.3, 3.4), (4, 0)]],
    'L': [[(0, 6), (0, 0), (4, 0)]],
    'M': [[(0, 0), (0, 6), (2, 3), (4, 6), (4, 0)]],
    'N': [[(0, 0), (0, 6), (4, 0), (4, 6)]],
    'O': [_O],
    'P': [_P],
    'Q': [_O, [(2.5, 1.5), (4, 0)]],
    'R': [_P, [(2, 3), (4, 0)]],
    'S': [[(4, 5), (3, 6), (1, 6), (0, 5), (0, 4), (1, 3), (3, 3), (4, 2), (4, 1), (3, 0), (1, 0), (0, 1)]],
    'T': [[(0, 6), (4, 6)], [(2, 6), (2, 0)]],
    'U': [[(0, 6), (0, 1), (1, 0), (3, 0), (4, 1), (4, 6)]],
    'V': [[(0, 6), (2, 0), (4, 6)]],
    'W': [[(0, 6), (1, 0), (2, 4), (3, 0), (4, 6)]],
    'X': [[(0, 6), (4, 0)], [(4, 6), (0, 0)]],
    'Y': [[(0, 6), (2, 3), (4, 6)], [(2, 3), (2, 0)]],
    'Z': [[(0, 6), (4, 6), (0, 0), (4, 0)]],
    '-': [[(1, 3), (3, 3)]],
    '.': [[(2, 0), (2, 0.05)]],
    "'": [[(2, 6), (2, 4.8)]],
    ' ': [],
}


def text_width(text, spacing=5.0):
    return max(0.0, len(text) * spacing - (spacing - 4.0))


def draw_text(img, text, x0, y0, height, color, weight=0.85, outline=None, outline_w=0.5, spacing=5.0,
              max_width=None):
    """Draw text into a float image (h, w, 3), top-left of the first glyph at
    (x0, y0) pixels, letters ``height`` pixels tall. Returns the width used."""
    text = ''.join(ch for ch in text.upper() if ch in GLYPHS)
    s = height / 6.0
    w = text_width(text, spacing) * s
    if max_width and w > max_width:
        # Squeeze long names sideways, as kit printers do
        sx = max_width / w
        w = max_width
    else:
        sx = 1.0
    if outline is not None:
        _strokes(img, text, x0, y0, s, sx, spacing, weight + outline_w * 2, outline)
    _strokes(img, text, x0, y0, s, sx, spacing, weight, color)
    return w


def _strokes(img, text, x0, y0, s, sx, spacing, weight, color):
    h, w = img.shape[:2]
    half = weight * s * 0.5
    col = np.asarray(color, dtype=np.float32)
    for k, ch in enumerate(text):
        gx = x0 + k * spacing * s * sx
        for line in GLYPHS[ch]:
            for (ax, ay), (bx, by) in zip(line, line[1:]):
                # Glyph y is up; image rows go down
                px0, py0 = gx + ax * s * sx, y0 + (6 - ay) * s
                px1, py1 = gx + bx * s * sx, y0 + (6 - by) * s
                xa = int(max(0, math.floor(min(px0, px1) - half - 2)))
                xb = int(min(w, math.ceil(max(px0, px1) + half + 2)))
                ya = int(max(0, math.floor(min(py0, py1) - half - 2)))
                yb = int(min(h, math.ceil(max(py0, py1) + half + 2)))
                if xa >= xb or ya >= yb:
                    continue
                yy, xx = np.mgrid[ya:yb, xa:xb].astype(np.float32)
                xx += 0.5
                yy += 0.5
                dx, dy = px1 - px0, py1 - py0
                ll = dx * dx + dy * dy
                if ll < 1e-6:
                    t = np.zeros_like(xx)
                else:
                    t = np.clip(((xx - px0) * dx + (yy - py0) * dy) / ll, 0.0, 1.0)
                d = np.hypot(xx - (px0 + t * dx), yy - (py0 + t * dy))
                a = np.clip(half - d + 0.5, 0.0, 1.0)[..., None]
                img[ya:yb, xa:xb] = img[ya:yb, xa:xb] * (1 - a) + col * a


# ------------------------------------------------------------ helpers
def _rng(*key):
    return np.random.default_rng(zlib.crc32(repr(key).encode()))


def _lum(c):
    return 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]


def contrast(c, a, b):
    """Whichever of a and b stands out more against c."""
    return a if abs(_lum(a) - _lum(c)) >= abs(_lum(b) - _lum(c)) else b


def _knit(h, w, rng, strength=0.06):
    """Fine fabric: a knit of tiny alternating loops plus soft noise."""
    yy, xx = np.mgrid[0:h, 0:w]
    loops = ((xx // 2 + yy // 2) % 2) * 2 - 1
    mesh = (np.sin(xx * 1.9) * np.sin(yy * 1.9 + (xx % 4) * 0.8)) * 0.5
    n = T._value_noise(max(h, w), 24, rng)[:h, :w] - 0.5
    return 1.0 + strength * (0.35 * loops + 0.4 * mesh) + strength * 0.8 * n


def _folds(h, w, rng, strength=0.05):
    """Soft vertical creases and shading where the shirt hangs."""
    xs = np.arange(w) / w
    f = np.zeros(w)
    for _ in range(9):
        c, s, a = rng.random(), 0.01 + 0.025 * rng.random(), (rng.random() - 0.5) * 2
        d = np.minimum(abs(xs - c), 1 - abs(xs - c))
        f += a * np.exp(-(d / s) ** 2)
    ys = np.arange(h) / h
    # Creases fade out over the chest, where the shirt sits tight
    fade = 0.5 + 0.5 * np.clip((ys - 0.35) / 0.4, 0, 1)
    return 1.0 + strength * f[None, :] * fade[:, None]


PATTERNS = ('plain', 'pinstripe', 'tonal', 'chevron', 'gradient')


def pattern_for(kit):
    key = kit.get('id', '') or str(kit.get('shirt'))
    return PATTERNS[sum(ord(c) for c in key) % len(PATTERNS)]


# ------------------------------------------------------------ shirt
SHIRT_W, SHIRT_H = 512, 256
# Where things sit on the shirt texture (u: around the body from the right side,
# front at 0.25, left side at 0.5, back at 0.75; v: hem 0 .. collar 1)
U_FRONT, U_BACK = 0.25, 0.75

_shirt_base = {}


def _shirt_base_img(kit, keeper):
    key = (kit.get('id'), keeper)
    if key in _shirt_base:
        return _shirt_base[key]
    h, w = SHIRT_H, SHIRT_W
    rng = _rng('shirt', key)
    shirt = np.array(kit['keeper'] if keeper else kit['shirt'], dtype=np.float32)
    trim = np.array(kit.get('trim', (1, 1, 1)), dtype=np.float32)
    if keeper:
        trim = np.array(contrast(tuple(shirt), (0.08, 0.08, 0.1), (0.95, 0.95, 0.95)), dtype=np.float32)
    img = np.ones((h, w, 3), dtype=np.float32) * shirt
    u = (np.arange(w) + 0.5) / w
    v = 1.0 - (np.arange(h) + 0.5) / h       # row 0 is the collar
    U, V = np.meshgrid(u, v)
    pat = 'tonal' if keeper else pattern_for(kit)
    tone = np.ones((h, w), dtype=np.float32)
    if pat == 'pinstripe':
        stripe = (np.abs(((U * 64) % 1.0) - 0.5) < 0.06).astype(np.float32)
        img = img * (1 - stripe[..., None] * 0.55) + trim * stripe[..., None] * 0.55
    elif pat == 'tonal':
        tone *= 1.0 + 0.06 * np.sign(np.sin(U * 2 * math.pi * 14))
    elif pat == 'chevron':
        du = np.abs(U - U_FRONT)
        d = np.abs(V - (0.5 + du * 1.6))
        band = np.clip((0.04 - d) / 0.008, 0, 1) * (du < 0.2)
        img = img * (1 - band[..., None] * 0.85) + trim * band[..., None] * 0.85
    elif pat == 'gradient':
        tone *= 0.82 + 0.3 * V
    # Side panels in the trim colour, from the armpit down
    for c in (0.0, 0.5, 1.0):
        d = np.abs(U - c)
        panel = np.clip((0.035 - d) / 0.006, 0, 1) * np.clip((V - 0.05) / 0.05, 0, 1) * np.clip((0.86 - V) / 0.04, 0, 1)
        img = img * (1 - panel[..., None] * 0.8) + trim * panel[..., None] * 0.8
    # Shoulder yoke piping and the hem band
    hem = np.clip((0.035 - V) / 0.01, 0, 1)
    img = img * (1 - hem[..., None] * 0.6) + trim * hem[..., None] * 0.6
    img *= (tone * _knit(h, w, rng) * _folds(h, w, rng))[..., None]
    # Soft shading baked in: under the chest, around the hem and the armholes
    ao = 1.0 - 0.08 * np.exp(-((V - 0.0) / 0.06) ** 2) - 0.05 * np.exp(-((V - 0.5) / 0.12) ** 2) * \
        np.cos((U - U_FRONT) * 2 * math.pi).clip(0, 1)
    img *= ao[..., None]
    out = (img, tuple(shirt), tuple(trim))
    _shirt_base[key] = out
    return out


_shirt_cache = {}


def shirt(kit, number, name, keeper=False):
    """The shirt texture for one player: kit, crest, and his name and number."""
    key = (kit.get('id'), keeper, number, name)
    if key in _shirt_cache:
        return _shirt_cache[key]
    base, shirt_c, trim_c = _shirt_base_img(kit, keeper)
    img = base.copy()
    h, w = img.shape[:2]
    ink = contrast(shirt_c, trim_c, contrast(shirt_c, (1, 1, 1), (0.06, 0.06, 0.08)))
    edge = contrast(ink, shirt_c, (0.05, 0.05, 0.05))
    num = str(int(number) % 100)
    # Back: name across the shoulders, the big number below
    nh = 92
    nw = text_width(num) * nh / 6
    draw_text(img, num, U_BACK * w - nw / 2, h * 0.25, nh, ink, weight=1.05, outline=edge, outline_w=0.22)
    label = ''.join(ch for ch in name.upper() if ch in GLYPHS)[:12]
    th = 17
    tw = min(text_width(label) * th / 6, w * 0.17)
    draw_text(img, label, U_BACK * w - tw / 2, h * 0.13, th, ink, weight=0.95, max_width=w * 0.17)
    # Front: a small number in the middle, the crest over the heart (his left)
    fh = 34
    fw = text_width(num) * fh / 6
    draw_text(img, num, U_FRONT * w - fw / 2, h * 0.36, fh, ink, weight=1.0)
    cx, cy, r = (U_FRONT + 0.075) * w, h * 0.26, 11
    yy, xx = np.mgrid[0:h, 0:w]
    shield = (np.abs(xx - cx) < r * 0.8) & (yy > cy - r) & (yy < cy + r * 0.4 + (r * 0.8 - np.abs(xx - cx)) * 0.9)
    inner = (np.abs(xx - cx) < r * 0.55) & (yy > cy - r * 0.7) & \
        (yy < cy + r * 0.25 + (r * 0.55 - np.abs(xx - cx)) * 0.9)
    img[shield] = np.array(ink, dtype=np.float32)
    img[inner] = np.array(shirt_c, dtype=np.float32) * 0.85
    t = T._from_array(np.clip(img, 0, 1), 'shirt-%s-%s' % (number, name))
    _shirt_cache[key] = t
    return t


# ------------------------------------------------------------ shorts and socks
_kit_cache = {}


def lower_kit(kit, keeper=False):
    """Shorts (top half) and socks (bottom half) for a team, in one texture.
    Shorts: u around the leg with the outer seam at 0; v down the leg.
    Socks: u around, v from the boot (0) to the top of the sock (1)."""
    key = (kit.get('id'), keeper)
    if key in _kit_cache:
        return _kit_cache[key]
    rng = _rng('lower', key)
    w, h = 128, 256
    shorts = np.array((0.12, 0.12, 0.14) if keeper else kit['shorts'], dtype=np.float32)
    socks = np.array(kit['keeper'] if keeper else kit.get('socks', kit['shirt']), dtype=np.float32)
    trim = np.array(kit.get('trim', (1, 1, 1)), dtype=np.float32)
    s_trim = np.array(contrast(tuple(shorts), tuple(trim), (0.95, 0.95, 0.95)), dtype=np.float32)
    k_trim = np.array(contrast(tuple(socks), tuple(trim), (0.95, 0.95, 0.95)), dtype=np.float32)
    img = np.zeros((h, w, 3), dtype=np.float32)
    u = (np.arange(w) + 0.5) / w
    # Shorts: rows 0..127 (row 0 = waistband)
    top = np.ones((128, w, 3), dtype=np.float32) * shorts
    v = (np.arange(128) + 0.5) / 128
    U, Vv = np.meshgrid(u, v)
    seam = np.clip((0.04 - np.minimum(U, 1 - U)) / 0.01, 0, 1)
    top = top * (1 - seam[..., None]) + s_trim * seam[..., None]
    hem = np.clip((Vv - 0.9) / 0.02, 0, 1)
    top = top * (1 - hem[..., None] * 0.7) + s_trim * hem[..., None] * 0.7
    band = np.clip((0.06 - Vv) / 0.01, 0, 1)
    top *= (1 - 0.25 * band)[..., None]
    top *= (_knit(128, w, rng, 0.05) * _folds(128, w, rng, 0.08))[..., None]
    img[:128] = top
    # Socks: rows 128..255, row 128 = top of the sock
    bot = np.ones((128, w, 3), dtype=np.float32) * socks
    v = 1.0 - (np.arange(128) + 0.5) / 128      # 1 at the top
    U, Vv = np.meshgrid(u, v)
    for c, wd in ((0.86, 0.025), (0.92, 0.018)):
        b = np.clip((wd - np.abs(Vv - c)) / 0.006, 0, 1)
        bot = bot * (1 - b[..., None]) + k_trim * b[..., None]
    rib = 1.0 + 0.07 * np.sin(U * 2 * math.pi * 40)
    cuff = np.clip((Vv - 0.96) / 0.02, 0, 1)
    bot *= (rib * (1 - 0.15 * cuff) * _knit(128, w, rng, 0.04))[..., None]
    # Grip tape round the ankle
    tape = np.clip((0.03 - np.abs(Vv - 0.12)) / 0.008, 0, 1)
    bot = bot * (1 - tape[..., None] * 0.35) + np.array((0.9, 0.9, 0.9)) * tape[..., None] * 0.35
    img[128:] = bot
    t = T._from_array(np.clip(img, 0, 1), 'kit-lower')
    _kit_cache[key] = t
    return t


# ------------------------------------------------------------ skin, face and hair
_skin_tex = None


def skin_detail():
    """Grey around 1.0: pores and blotches, multiplied over the skin colour."""
    global _skin_tex
    if _skin_tex is None:
        rng = np.random.default_rng(5)
        n = 0.94 + 0.07 * T._fbm(128, 8, 3, rng) + 0.03 * (rng.random((128, 128)) - 0.5)
        _skin_tex = T._from_array(np.dstack([n * 1.01, n, n * 0.99]), 'skin')
    return _skin_tex


FACE_W, FACE_H = 512, 512
_face_cache = {}
_face_noise = None


def _box(U, V, u0, u1, v0, v1):
    """Index slices of the grid (U along columns, V down the rows) covering a range."""
    cols = np.searchsorted(U[0], [u0, u1])
    rows = np.searchsorted(-V[:, 0], [-v1, -v0])
    return slice(rows[0], rows[1] + 1), slice(cols[0], cols[1] + 1)


def _gauss(U, V, cu, cv, su, sv):
    du = np.minimum(np.abs(U - cu), 1 - np.abs(U - cu))
    return np.exp(-((du / su) ** 2 + ((V - cv) / sv) ** 2))


def face(skin, hair, beard=None, women=False, iris=(0.25, 0.15, 0.08)):
    """Head texture, wrapped round the head mesh: u = longitude with the face
    at 0.25, v = latitude from the chin (0) to the crown (1).

    Brows, lips, the stubble and a little colour in the cheeks; the eyes and
    nose are modelled."""
    key = (skin, hair, beard, women, iris)
    if key in _face_cache:
        return _face_cache[key]
    rng = _rng('face', key)
    h, w = FACE_H, FACE_W
    skin = np.array(skin, dtype=np.float32)
    hair = np.array(hair, dtype=np.float32)
    global _face_noise
    if _face_noise is None:
        _face_noise = (0.95 + 0.08 * T._fbm(512, 16, 3, np.random.default_rng(21))).astype(np.float32)
    full = _face_noise[..., None] * skin
    u = (np.arange(w) + 0.5) / w
    v = 1.0 - (np.arange(h) + 0.5) / h
    UF, VF = np.meshgrid(u, v)
    # The features only cover the front half, from the chin to the hairline
    win = (slice(int(h * 0.2), int(h * 0.92)), slice(0, w // 2))
    U, V = UF[win], VF[win]
    img = full[win].copy()
    dark = _lum(skin) < 0.5
    # Warmth in the cheeks, nose and ears
    blush = np.array((1.06, 0.95, 0.93) if not dark else (1.03, 0.97, 0.96), dtype=np.float32)
    for cu in (0.25 - 0.1, 0.25 + 0.1):
        g = _gauss(U, V, cu, 0.45, 0.045, 0.05)[..., None]
        img *= 1 + (blush - 1) * g
    img *= 1 + (blush - 1) * _gauss(U, V, 0.25, 0.44, 0.02, 0.04)[..., None]
    # Eye sockets a touch darker, and the upper lids
    for cu in (0.25 - 0.068, 0.25 + 0.068):
        img *= 1 - 0.2 * _gauss(U, V, cu, 0.55, 0.04, 0.03)[..., None]
        img *= 1 - 0.3 * _gauss(U, V, cu, 0.565, 0.028, 0.006)[..., None]
    # Eyes: an almond of white, the iris and pupil, a dark lash line above
    iris = np.array(iris, dtype=np.float32)
    white = np.array((0.88, 0.86, 0.82), dtype=np.float32)
    for side in (-1, 1):
        cu = 0.25 + side * 0.068
        box = _box(U, V, cu - 0.034, cu + 0.034, 0.525, 0.575)
        Ue, Ve, e = U[box], V[box], img[box]
        du = (Ue - cu) * side             # + towards the ear
        x = du / 0.029
        top = 0.0115 * np.clip(1 - x * x, 0, 1) ** 0.8 * (1 + 0.15 * x)
        bot = 0.0085 * np.clip(1 - x * x, 0, 1) ** 0.9
        ok = np.abs(x) < 1
        dv = Ve - 0.548
        inside = np.clip(np.minimum(top - dv, dv + bot) / 0.0018, 0, 1) * ok
        e[...] = e * (1 - inside[..., None]) + white * inside[..., None]
        # Iris and pupil (the head is slightly squashed in v, so the circles are too)
        rr = np.sqrt((du * 2 * math.pi * 0.081) ** 2 + (dv * math.pi * 0.116) ** 2)
        ir = np.clip((0.0058 - rr) / 0.0006, 0, 1) * inside
        ring = 0.7 + 0.3 * np.clip(rr / 0.0058, 0, 1)
        e[...] = e * (1 - ir[..., None]) + (iris * ring[..., None]) * ir[..., None]
        pu = np.clip((0.0025 - rr) / 0.0005, 0, 1) * inside
        e[...] = e * (1 - pu[..., None]) + 0.02 * pu[..., None]
        # A glint
        gl = np.clip((0.0012 - np.sqrt(((du + 0.004 * side) * 0.51) ** 2 + ((dv - 0.004) * 0.364) ** 2)) / 0.0004,
                     0, 1) * inside
        e[...] = e * (1 - gl[..., None] * 0.8) + 0.8 * gl[..., None]
        # Lids: shadow under the brow, lash line on top, a softer one below
        lash = np.clip((0.0022 - np.abs(dv - top)) / 0.0009, 0, 1) * ok
        e *= (1 - 0.85 * lash)[..., None]
        low = np.clip((0.0012 - np.abs(dv + bot)) / 0.0008, 0, 1) * ok
        e *= (1 - 0.35 * low)[..., None]
        lid = np.clip((dv - top) / 0.002, 0, 1) * np.clip((top + 0.009 - dv) / 0.004, 0, 1) * ok
        e *= (1 - 0.12 * lid)[..., None]
    # Brows
    brow_c = hair * 0.7 + skin * 0.1
    if _lum(hair) > 0.75:
        brow_c = skin * 0.55
    box = _box(U, V, 0.12, 0.38, 0.56, 0.65)
    Ub, Vb, e = U[box], V[box], img[box]
    for side in (-1, 1):
        du = (Ub - 0.25) * side
        cur = 0.6 + 0.012 * np.sin(np.clip((du - 0.025) / 0.08, 0, 1) * math.pi) - 0.012 * np.clip((du - 0.09) / 0.03, 0, 1)
        thick = 0.008 if women else 0.012
        b = np.clip((thick - np.abs(Vb - cur)) / 0.005, 0, 1) * np.clip((du - 0.022) / 0.01, 0, 1) * \
            np.clip((0.118 - du) / 0.015, 0, 1)
        e[...] = e * (1 - b[..., None] * 0.85) + brow_c * b[..., None] * 0.85
    # Lips
    lip = skin * np.array((0.86, 0.6, 0.58) if not dark else (0.75, 0.55, 0.55), dtype=np.float32)
    if women:
        lip = skin * np.array((0.85, 0.5, 0.52), dtype=np.float32)
    du = np.abs(U - 0.25)
    upper = np.clip((0.006 - np.abs(V - 0.354 - 0.003 * np.cos(du / 0.04 * math.pi))) / 0.004, 0, 1)
    lower = np.clip((0.008 - np.abs(V - 0.337)) / 0.004, 0, 1)
    mouth = np.maximum(upper, lower) * np.clip((0.042 - du) / 0.01, 0, 1)
    img = img * (1 - mouth[..., None]) + lip * mouth[..., None]
    line = np.clip((0.0025 - np.abs(V - 0.346)) / 0.0015, 0, 1) * np.clip((0.04 - du) / 0.008, 0, 1)
    img *= (1 - 0.45 * line)[..., None]
    # Stubble or a beard's shadow on the jaw
    if beard in ('stubble', 'full', 'goatee'):
        amt = {'stubble': 0.45, 'full': 0.75, 'goatee': 0.35}[beard]
        jaw = np.clip((0.43 - V) / 0.06, 0, 1) * np.clip((V - 0.12) / 0.05, 0, 1) * np.clip((0.24 - du) / 0.04, 0, 1)
        jaw = np.maximum(jaw, np.exp(-((du / 0.045) ** 2 + ((V - 0.372) / 0.008) ** 2)))
        if beard == 'goatee':
            jaw *= np.clip((0.04 - du) / 0.015, 0, 1)
        grain = rng.random(V.shape) * 0.5 + 0.5
        a = (jaw * amt * grain)[..., None]
        img = img * (1 - a) + hair * 0.8 * a
    full[win] = img
    img, U, V = full, UF, VF
    # Short hair at the temples and the back fades into the scalp
    scalp = np.clip((V - 0.66) / 0.08, 0, 1) * (1 - np.clip((0.12 - np.abs(U - 0.25)) / 0.05, 0, 1) * 0.6)
    img = img * (1 - scalp[..., None] * 0.35) + hair * scalp[..., None] * 0.35
    t = T._from_array(np.clip(img, 0, 1), 'face')
    _face_cache[key] = t
    return t


_hair_tex = None


def hair_strands():
    """Grey streaks running down the head (along v), multiplied over the hair colour."""
    global _hair_tex
    if _hair_tex is None:
        rng = np.random.default_rng(9)
        w, h = 256, 128
        cols = rng.random(w)
        cols = np.convolve(np.concatenate([cols[-3:], cols, cols[:3]]), np.ones(3) / 3, 'same')[3:-3]
        n = 0.72 + 0.4 * cols[None, :] + 0.12 * (T._fbm(256, 8, 2, rng)[:h, :w] - 0.5)
        n = n + 0.08 * (rng.random((h, w)) - 0.5)
        _hair_tex = T._from_array(np.dstack([n, n, n]), 'hair')
    return _hair_tex


_boot_tex = None


def boot_detail():
    """Faint stitching and the gloss break-up on boots and gloves."""
    global _boot_tex
    if _boot_tex is None:
        rng = np.random.default_rng(13)
        n = 0.93 + 0.1 * T._fbm(64, 8, 2, rng)
        _boot_tex = T._from_array(np.dstack([n, n, n]), 'boot')
    return _boot_tex
