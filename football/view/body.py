"""A footballer's body as one smooth, skinned mesh.

The figure is sculpted from lofted cross-sections (thighs with the quads at
the front, calves bulging at the back, a chest that tapers to the waist, a
head with a jaw, nose, brows and lips) and bound to a skeleton of 21 joints
with blended weights, so knees, elbows, hips and shoulders bend smoothly
instead of being separate parts. Panda3D deforms it each frame from the
joint transforms (see ``Rig``); the animation code only sets joint angles.

Everything is in metres for a 1.83 m player standing at the origin and
facing +y, with +x on his right.
"""

import math

import numpy as np
from panda3d.core import (Character, CharacterJoint, Geom, GeomNode, GeomTriangles, GeomVertexAnimationSpec,
                          GeomVertexArrayFormat, GeomVertexData, GeomVertexFormat, InternalName, JointVertexTransform,
                          Mat4, ModelNode, NodePath, OmniBoundingVolume, PartGroup, TransformTable)

# name, parent, offset from the parent in the rest pose
SKELETON = [
    ('pelvis', None, (0.0, 0.0, 0.96)),
    ('spine', 'pelvis', (0.0, 0.0, 0.10)),
    ('chest', 'spine', (0.0, 0.0, 0.18)),
    ('neck', 'chest', (0.0, 0.0, 0.25)),
    ('head', 'neck', (0.0, 0.0, 0.10)),
]
for _s, _x in (('L', -1), ('R', 1)):
    SKELETON += [
        ('clav_' + _s, 'chest', (_x * 0.02, 0.0, 0.19)),
        ('shoulder_' + _s, 'clav_' + _s, (_x * 0.175, 0.0, 0.0)),
        ('elbow_' + _s, 'shoulder_' + _s, (0.0, 0.0, -0.29)),
        ('wrist_' + _s, 'elbow_' + _s, (0.0, 0.0, -0.25)),
        ('hip_' + _s, 'pelvis', (_x * 0.092, 0.0, -0.05)),
        ('knee_' + _s, 'hip_' + _s, (0.0, 0.0, -0.44)),
        ('ankle_' + _s, 'knee_' + _s, (0.0, 0.0, -0.40)),
        ('toe_' + _s, 'ankle_' + _s, (0.0, 0.13, -0.045)),
    ]

HEAD_C = np.array((0.0, 0.012, 1.688))
HEAD_R = np.array((0.081, 0.104, 0.116))


def skeleton(w=1.0, women=False):
    """Joint offsets for a build: wider shoulders and hips for a broader player."""
    sw = w * (0.93 if women else 1.0)
    hw = w * (1.04 if women else 1.0)
    out = []
    for name, parent, (x, y, z) in SKELETON:
        if name.startswith('clav') or name.startswith('shoulder'):
            x *= sw
        elif name.startswith('hip'):
            x *= hw
        out.append((name, parent, (x, y, z)))
    return out


def rest_positions(skel):
    pos = {}
    for name, parent, off in skel:
        p = pos[parent] if parent else (0.0, 0.0, 0.0)
        pos[name] = (p[0] + off[0], p[1] + off[1], p[2] + off[2])
    return pos


# ---------------------------------------------------------------- mesh parts
class Part:
    """Vertices and triangles for one material, gathered from several grids."""

    def __init__(self):
        self.P, self.N, self.UV, self.C, self.B, self.T = [], [], [], [], [], []
        self.n = 0

    def add(self, P, N, UV, C, B, tris):
        self.P.append(P.reshape(-1, 3))
        self.N.append(N.reshape(-1, 3))
        self.UV.append(UV.reshape(-1, 2))
        self.C.append(C.reshape(-1, 4))
        self.B.append(B.reshape(-1))
        self.T.append(tris + self.n)
        self.n += len(self.P[-1])

    def empty(self):
        return self.n == 0


def _normalize(v):
    d = np.linalg.norm(v, axis=-1, keepdims=True)
    return v / np.maximum(d, 1e-9), d[..., 0]


def grid(part, P, UV, C, B, wrap=True, mask=None, center=None):
    """Add a grid of points (rows x cols); with wrap, the last column repeats the first.
    Normals come from the surface; they and the winding are turned to face away
    from ``center`` (default: the middle of each row)."""
    R, K = P.shape[:2]
    if wrap:
        core = P[:, :-1]
        du = np.roll(core, -1, axis=1) - np.roll(core, 1, axis=1)
        du = np.concatenate([du, du[:, :1]], axis=1)
    else:
        du = np.gradient(P, axis=1)
    dv = np.gradient(P, axis=0)
    N, ln = _normalize(np.cross(du, dv))
    if center is None:
        cen = P.mean(axis=1, keepdims=True)
    else:
        cen = np.asarray(center, dtype=np.float64).reshape(1, 1, 3)
    radial = P - cen
    if (N * radial).sum() < 0:
        N = -N
    # Poles and other degenerate rows: point straight out
    bad = ln < 1e-7
    if bad.any():
        out, _ = _normalize(P - P.reshape(-1, 3).mean(axis=0))
        N[bad] = out[bad]
    if C.ndim == 1:
        C = np.broadcast_to(C, (R, K, 4))
    if np.ndim(B) == 1:
        B = np.broadcast_to(np.asarray(B)[:, None], (R, K))
    idx = np.arange(R * K).reshape(R, K)
    a, b, c, d = idx[:-1, :-1], idx[:-1, 1:], idx[1:, 1:], idx[1:, :-1]
    if mask is not None:
        keep = mask[:-1, :-1] & mask[:-1, 1:] & mask[1:, 1:] & mask[1:, :-1]
        a, b, c, d = a[keep], b[keep], c[keep], d[keep]
    else:
        a, b, c, d = a.ravel(), b.ravel(), c.ravel(), d.ravel()
    tris = np.concatenate([np.stack([a, b, c], 1), np.stack([a, c, d], 1)])
    if len(tris):
        flat = P.reshape(-1, 3)
        fn = np.cross(flat[tris[:, 1]] - flat[tris[:, 0]], flat[tris[:, 2]] - flat[tris[:, 0]])
        if (fn * N.reshape(-1, 3)[tris[:, 0]]).sum() < 0:
            tris = tris[:, [0, 2, 1]]
    part.add(P, N, UV, np.ascontiguousarray(C), np.ascontiguousarray(B), tris)


def _interp(keys, sub):
    """Catmull-Rom through the rows of keys (k x m), sub steps per span, clamped
    between neighbouring keys so sharp steps (a sleeve hem) don't overshoot."""
    keys = np.asarray(keys, dtype=np.float64)
    k = len(keys)
    out = []
    for i in range(k - 1):
        p0 = keys[max(0, i - 1)]
        p1, p2 = keys[i], keys[i + 1]
        p3 = keys[min(k - 1, i + 2)]
        lo, hi = np.minimum(p1, p2), np.maximum(p1, p2)
        for j in range(sub):
            t = j / sub
            t2, t3 = t * t, t * t * t
            v = 0.5 * (2 * p1 + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2 + (-p0 + 3 * p1 - 3 * p2 + p3) * t3)
            out.append(np.clip(v, lo, hi))
    out.append(keys[-1])
    return np.array(out)


def section(rows, seg):
    """Points round superellipse cross-sections.
    rows: (n, 7) of z, cx, cy, rx, ry_front, ry_back, squareness."""
    th = np.linspace(0.0, 2 * math.pi, seg + 1)
    c, s = np.cos(th), np.sin(th)
    z, cx, cy, rx, ryf, ryb, sq = (rows[:, i:i + 1] for i in range(7))
    e = 2.0 / sq
    x = cx + rx * np.sign(c) * np.abs(c) ** e
    ry = np.where(s[None, :] > 0, ryf, ryb)
    y = cy + ry * np.sign(s) * np.abs(s) ** e
    P = np.stack([x, y, np.broadcast_to(z, x.shape)], axis=-1)
    return P, th


class Blends:
    """Joint weights to blend indices, shared by every part of one figure."""

    def __init__(self, joints):
        self.joints = joints
        self.keys = []
        self.ids = {}
        self.xf = {name: JointVertexTransform(j) for name, j in joints.items()}
        self.order = list(joints)
        self.index = {n: i for i, n in enumerate(self.order)}
        self._tt = None

    def get(self, weights):
        items = sorted((n, round(w * 32) / 32) for n, w in weights.items() if w > 0.015)
        tot = sum(w for _, w in items) or 1.0
        key = tuple((n, w / tot) for n, w in items)
        if key not in self.ids:
            self.ids[key] = len(self.keys)
            self.keys.append(key)
        return self.ids[key]

    def transform_table(self):
        if self._tt is None:
            t = TransformTable()
            for name in self.order:
                t.add_transform(self.xf[name])
            self._tt = TransformTable.register_table(t)
        return self._tt

    def weights_indices(self):
        """Per blend id: four weights and four joint indices."""
        W = np.zeros((len(self.keys), 4), dtype=np.float32)
        J = np.zeros((len(self.keys), 4), dtype=np.uint8)
        for i, key in enumerate(self.keys):
            for k, (n, w) in enumerate(key[:4]):
                W[i, k] = w
                J[i, k] = self.index[n]
        return W, J

    def along(self, zs, table):
        """Blend ids for heights zs from a table of (z, {joint: weight}), highest first,
        weights interpolated linearly in between."""
        out = []
        for z in zs:
            if z >= table[0][0]:
                w = table[0][1]
            elif z <= table[-1][0]:
                w = table[-1][1]
            else:
                for (za, wa), (zb, wb) in zip(table, table[1:]):
                    if zb <= z <= za:
                        f = (za - z) / max(1e-9, za - zb)
                        w = {n: wa.get(n, 0.0) * (1 - f) + wb.get(n, 0.0) * f for n in set(wa) | set(wb)}
                        break
            out.append(self.get(w))
        return np.array(out, dtype=np.int32)


def _smoothstep(a, b, x):
    t = np.clip((x - a) / (b - a), 0.0, 1.0)
    return t * t * (3 - 2 * t)


# ---------------------------------------------------------------- the figure
class BodyBuilder:
    """Sculpts one player. ``spec`` holds the look: w, women, keeper, sleeves,
    socks_down, hair, beard, headband and the colours."""

    def __init__(self, spec, blends, skel_pos, detail=1.0):
        self.s = spec
        self.b = blends
        self.j = skel_pos
        self.sub = 3 if detail >= 1.0 else 2
        self.seg = 20 if detail >= 1.0 else 12
        self.parts = {k: Part() for k in ('skin', 'head', 'eyes', 'hair', 'shirt', 'trim', 'lower', 'boots')}

    # ---------------------------------------------------------- helpers
    def loft(self, part, keys, weights, uvf, color, seg=None, sub=None, closed_top=False, closed_bottom=False,
             mask_fn=None):
        rows = _interp(keys, sub or self.sub)
        seg = seg or self.seg
        P, th = section(rows, seg)
        z = rows[:, 0]
        U, V = uvf(th[None, :].repeat(len(rows), 0), z[:, None].repeat(seg + 1, 1))
        UV = np.stack([U, V], axis=-1)
        if isinstance(weights, str):
            weights = [(0.0, {weights: 1.0})]
        B = self.b.along(z, weights)
        col = np.array(color, dtype=np.float64)
        C = np.broadcast_to(col, P.shape[:2] + (4,)) if col.ndim == 1 else col
        grid(self.parts[part], P, UV, C, B)
        return P

    def side_x(self, side):
        return -1.0 if side == 'L' else 1.0

    # ---------------------------------------------------------- whole body
    def build(self):
        self.torso()
        for side in ('L', 'R'):
            self.leg(side)
            self.boot(side)
            self.arm(side)
        self.neck()
        self.head()
        return self.parts

    # ---------------------------------------------------------- torso
    def torso(self):
        s = self.s
        w = s['w']
        wm = s['women']
        hip = 1.06 if wm else 1.0
        sh = 0.92 if wm else 1.0
        chest_f = 1.08 if wm else 1.0
        waist = 0.9 if wm else 1.0
        P = 'pelvis'
        wts = [(1.47, {'chest': 0.75, 'neck': 0.25}), (1.32, {'chest': 1.0}), (1.22, {'spine': 0.6, 'chest': 0.4}),
               (1.12, {'spine': 1.0}), (1.02, {P: 0.6, 'spine': 0.4}), (0.95, {P: 1.0})]
        # Shorts round the hips: z, cx, cy, rx, ryf, ryb, squareness
        k = [(0.80, 0, 0.0, 0.06, 0.04, 0.04, 2.0),
             (0.83, 0, 0.0, 0.135 * hip, 0.075, 0.085, 2.2),
             (0.88, 0, 0.0, 0.178 * hip, 0.098, 0.125, 2.4),
             (0.95, 0, 0.0, 0.18 * hip, 0.1, 0.122, 2.5),
             (1.01, 0, 0.0, 0.17 * hip, 0.096, 0.108, 2.5),
             (1.03, 0, 0.0, 0.165, 0.093, 0.103, 2.5)]
        k = [(z, cx, cy, rx * w, rf * w, rb * w, q) for z, cx, cy, rx, rf, rb, q in k]

        def shorts_uv(th, z):
            return th / (2 * math.pi), 0.5 + 0.5 * np.clip((z - 0.78) / 0.25, 0, 1)

        self.loft('lower', k, wts, shorts_uv, (1, 1, 1, 1))
        # The shirt, worn untucked over the shorts
        k = [(0.925, 0, 0.0, 0.192 * hip, 0.116, 0.132, 2.4),
             (0.935, 0, 0.0, 0.195 * hip, 0.118, 0.134, 2.4),
             (1.02, 0, 0.0, 0.182 * waist, 0.112, 0.118, 2.5),
             (1.10, 0, 0.0, 0.17 * waist, 0.108, 0.108, 2.5),
             (1.18, 0, 0.004, 0.172, 0.112 * chest_f, 0.104, 2.5),
             (1.26, 0, 0.006, 0.18 * sh, 0.124 * chest_f, 0.106, 2.6),
             (1.33, 0, 0.006, 0.188 * sh, 0.13 * chest_f, 0.112, 2.7),
             (1.39, 0, 0.0, 0.198 * sh, 0.118, 0.116, 2.7),
             (1.43, 0, -0.008, 0.19 * sh, 0.1, 0.108, 2.6),
             (1.462, 0, -0.012, 0.165 * sh, 0.082, 0.092, 2.5),
             (1.485, 0, -0.012, 0.095, 0.068, 0.07, 2.1),
             (1.50, 0, -0.012, 0.062, 0.056, 0.056, 2.0)]
        k = [(z, cx, cy, rx * w, rf * w, rb * w, q) for z, cx, cy, rx, rf, rb, q in k]

        def shirt_uv(th, z):
            return th / (2 * math.pi), np.clip((z - 0.93) / 0.57, 0.0, 1.0)

        self.loft('shirt', k, wts, shirt_uv, (1, 1, 1, 1), seg=self.seg + 8)
        # Collar band, standing a touch proud of the shirt
        trim = self.s['trim'] + (1,)
        k = [(1.478, 0, -0.012, 0.075, 0.068, 0.068, 2.0), (1.492, 0, -0.012, 0.07, 0.064, 0.064, 2.0),
             (1.505, 0, -0.012, 0.062, 0.058, 0.058, 2.0), (1.51, 0, -0.012, 0.057, 0.053, 0.053, 2.0)]
        k = [(z, cx, cy, rx * w, rf * w, rb * w, q) for z, cx, cy, rx, rf, rb, q in k]
        self.loft('trim', k, [(1.5, {'chest': 0.7, 'neck': 0.3})], lambda th, z: (th * 0, z * 0), trim, sub=1)

    # ---------------------------------------------------------- legs
    def leg(self, side):
        s = self.s
        w = s['w']
        x = self.j['hip_' + side][0]
        sx = self.side_x(side)
        hip, knee, ank = 'hip_' + side, 'knee_' + side, 'ankle_' + side
        wts = [(0.97, {'pelvis': 0.9, hip: 0.1}), (0.9, {'pelvis': 0.45, hip: 0.55}), (0.82, {hip: 1.0}),
               (0.53, {hip: 1.0}),
               (0.47, {hip: 0.5, knee: 0.5}), (0.41, {knee: 1.0}), (0.12, {knee: 1.0}), (0.085, {knee: 0.4, ank: 0.6}),
               (0.07, {ank: 1.0})]
        thick = 1.08 if s['women'] else 1.0
        # Bare leg: z, cx (outwards), cy, rx, ry front, ry back, squareness
        bare = [(0.74, 0.0, 0.0, 0.078, 0.082, 0.072, 2.1),
                (0.66, -0.003, 0.002, 0.07, 0.074, 0.062, 2.1),
                (0.58, -0.006, 0.004, 0.06, 0.066, 0.054, 2.1),
                (0.52, -0.008, 0.004, 0.053, 0.06, 0.048, 2.1),
                (0.47, -0.008, 0.006, 0.049, 0.056, 0.046, 2.2),
                (0.42, -0.007, 0.0, 0.046, 0.046, 0.054, 2.1),
                (0.35, -0.005, -0.004, 0.049, 0.04, 0.068, 2.0),
                (0.28, -0.002, -0.004, 0.045, 0.037, 0.058, 2.0),
                (0.2, 0.0, 0.0, 0.036, 0.032, 0.04, 2.0),
                (0.13, 0.0, 0.0, 0.03, 0.03, 0.032, 2.0),
                (0.09, 0.0, -0.004, 0.032, 0.032, 0.036, 2.0),
                (0.07, 0.0, -0.004, 0.034, 0.034, 0.036, 2.0)]

        def place(keys, grow=0.0, front=0.0):
            out = []
            for z, cx, cy, rx, rf, rb, q in keys:
                g = grow(z) if callable(grow) else grow
                f = front(z) if callable(front) else front
                out.append((z, x + cx * sx, cy, (rx * thick + g) * w, (rf * thick + g + f) * w, (rb * thick + g) * w, q))
            return out

        def skin_uv(th, z):
            return th / (2 * math.pi), z * 2.0

        skin = s['skin'] + (1,)
        sock_top = 0.2 if s['socks_down'] else 0.435
        # Skin from inside the shorts to inside the sock
        keys = [k for k in bare if k[0] >= sock_top - 0.04]
        self.loft('skin', place(keys), wts, skin_uv, skin)
        # Socks over the shin pads, folded over at the top
        keys = [k for k in bare if k[0] <= sock_top]
        top = bare[0]
        for a, b in zip(bare, bare[1:]):
            if b[0] <= sock_top <= a[0]:
                f = (a[0] - sock_top) / (a[0] - b[0])
                top = tuple(a[i] + (b[i] - a[i]) * f for i in range(7))
                break
        keys = [top] + keys
        pad = (lambda z: 0.008 * float(_smoothstep(0.17, 0.24, z) * (1 - _smoothstep(0.36, 0.41, z)))) \
            if not s['socks_down'] else 0.0
        bunched = (lambda z: 0.006 + 0.006 * math.sin(z * 180.0) ** 2) if s['socks_down'] else 0.004
        socks = place(keys, grow=bunched, front=pad)
        z0, z1 = 0.075, sock_top
        flip = 0.0 if sx > 0 else 0.5

        def sock_uv(th, z):
            return th / (2 * math.pi) + flip, 0.5 * np.clip((z - z0) / (z1 - z0), 0, 1)

        socks[0] = socks[0][:3] + tuple(r + 0.006 * w for r in socks[0][3:6]) + socks[0][6:]
        self.loft('lower', socks, wts, sock_uv, (1, 1, 1, 1))
        # Shorts leg: loose round the thigh, hem at mid-thigh
        hem = 0.665 if not s['keeper'] else 0.64
        sk = [(0.95, 0.002, 0.0, 0.104, 0.1, 0.11, 2.2),
              (0.9, 0.006, 0.0, 0.106, 0.104, 0.11, 2.2),
              (0.78, 0.004, 0.0, 0.1, 0.1, 0.096, 2.2),
              (hem + 0.005, 0.0, 0.0, 0.097, 0.097, 0.09, 2.2),
              (hem, 0.0, 0.0, 0.095, 0.095, 0.088, 2.2),
              (hem + 0.012, 0.0, 0.0, 0.074, 0.078, 0.066, 2.1)]

        def shorts_uv(th, z):
            return th / (2 * math.pi) + flip, 0.5 + 0.5 * np.clip((z - hem) / (0.99 - hem), 0, 1)

        self.loft('lower', place(sk), wts, shorts_uv, (1, 1, 1, 1))

    def boot(self, side):
        """A modern boot: low collar, rounded toe box, a sole that tilts up at the toe."""
        s = self.s
        sx = self.side_x(side)
        ax, _, az = self.j['ankle_' + side]
        ank, toe = 'ankle_' + side, 'toe_' + side
        sc = 1.0 if not s['women'] else 0.93
        # y, half width, top, bottom, x offset (toes point a touch outwards)
        keys = [(-0.075, 0.018, 0.075, 0.012, 0.0),
                (-0.068, 0.034, 0.1, 0.004, 0.0),
                (-0.05, 0.04, 0.118, 0.0, 0.0),
                (-0.02, 0.043, 0.122, 0.0, 0.0),
                (0.02, 0.045, 0.105, 0.0, 0.002),
                (0.06, 0.048, 0.085, 0.0, 0.004),
                (0.1, 0.05, 0.068, 0.0, 0.006),
                (0.14, 0.047, 0.056, 0.002, 0.007),
                (0.175, 0.04, 0.046, 0.005, 0.007),
                (0.2, 0.028, 0.038, 0.01, 0.006),
                (0.212, 0.012, 0.032, 0.016, 0.005),
                (0.215, 0.0, 0.026, 0.02, 0.005)]
        rows = _interp(keys, 3)
        seg = self.seg
        th = np.linspace(0.0, 2 * math.pi, seg + 1)
        c, sn = np.cos(th), np.sin(th)
        e = 2.0 / 3.0
        y = rows[:, 0:1] * sc
        hw = rows[:, 1:2] * sc
        top, bot = rows[:, 2:3], rows[:, 3:4]
        cz, rz = (top + bot) / 2, (top - bot) / 2
        X = ax + rows[:, 4:5] * sx + hw * np.sign(c) * np.abs(c) ** e
        Z = cz + rz * np.sign(sn) * np.abs(sn) ** e
        Y = np.broadcast_to(y, X.shape)
        P = np.stack([X, Y, Z], axis=-1)
        boot = np.array(s['boots'], dtype=np.float64)
        accent = np.array(s['boot_accent'], dtype=np.float64)
        sole = np.array(s['sole'], dtype=np.float64)
        C = np.empty(P.shape[:2] + (4,))
        C[..., 3] = 1.0
        C[..., :3] = boot
        # The sole and the stud plate along the bottom
        Zr = P[..., 2]
        sole_m = (Zr < 0.012)[..., None]
        C[..., :3] = np.where(sole_m, sole, C[..., :3])
        # A swoosh-like flash along the outside and the heel counter
        outer = (np.sign(P[..., 0] - ax) == sx)
        flash = outer & (np.abs((Zr - 0.03) - (P[..., 1] + 0.05) * 0.18) < 0.009) & (P[..., 1] > -0.04) & \
            (P[..., 1] < 0.15)
        C[..., :3] = np.where(flash[..., None], accent, C[..., :3])
        heel = (P[..., 1] < -0.055) & (Zr > 0.02)
        C[..., :3] = np.where(heel[..., None], accent * 0.6 + boot * 0.4, C[..., :3])
        # Laces on top of the foot
        lace = (P[..., 1] > -0.005) & (P[..., 1] < 0.1) & (np.abs(P[..., 0] - ax) < 0.014) & (Zr > 0.05)
        C[..., :3] = np.where(lace[..., None], C[..., :3] * 0.7 + 0.3 * np.array((0.95, 0.95, 0.95)), C[..., :3])
        U = th[None, :].repeat(len(rows), 0) / (2 * math.pi)
        UV = np.stack([U, np.broadcast_to(y * 4, U.shape)], axis=-1)
        B = self.b.along(-rows[:, 0], [(-0.08, {ank: 1.0}), (-0.12, {toe: 0.6, ank: 0.4}), (-0.16, {toe: 1.0})])
        grid(self.parts['boots'], P, UV, C, B, center=(ax, 0.05, 0.05))

    # ---------------------------------------------------------- arms
    def arm(self, side):
        s = self.s
        w = s['w']
        sx = self.side_x(side)
        x, _, zs = self.j['shoulder_' + side]
        cl, sh, el, wr = 'clav_' + side, 'shoulder_' + side, 'elbow_' + side, 'wrist_' + side
        ze = self.j['elbow_' + side][2]
        zw = self.j['wrist_' + side][2]
        wts = [(zs + 0.05, {cl: 0.55, sh: 0.45}), (zs - 0.02, {sh: 1.0}), (ze + 0.035, {sh: 1.0}),
               (ze, {sh: 0.5, el: 0.5}), (ze - 0.035, {el: 1.0}), (zw + 0.03, {el: 1.0}), (zw, {el: 0.5, wr: 0.5}),
               (zw - 0.02, {wr: 1.0})]
        thick = 0.95 if s['women'] else 1.08
        # z offset from the shoulder, cx (outwards), cy, rx, ry front, ry back, squareness
        rel = [(0.046, -0.045, 0.0, 0.02, 0.03, 0.03, 2.0),
               (0.036, -0.02, 0.0, 0.044, 0.05, 0.05, 2.0),
               (0.005, -0.002, 0.0, 0.053, 0.054, 0.054, 2.0),
               (-0.04, 0.0, 0.0, 0.052, 0.05, 0.052, 2.0),
               (-0.11, 0.0, 0.004, 0.048, 0.05, 0.048, 2.0),
               (-0.19, -0.002, 0.004, 0.043, 0.045, 0.042, 2.0),
               (-0.27, 0.0, -0.002, 0.039, 0.038, 0.038, 2.0),
               (-0.29, 0.0, -0.004, 0.04, 0.036, 0.04, 2.0),
               (-0.33, 0.0, 0.0, 0.044, 0.04, 0.042, 2.0),
               (-0.41, 0.0, 0.002, 0.036, 0.034, 0.032, 2.0),
               (-0.5, 0.0, 0.0, 0.026, 0.022, 0.02, 2.0),
               (-0.535, 0.0, 0.0, 0.025, 0.02, 0.02, 2.0)]
        keys = [(zs + dz, x + cx * sx, cy, rx * w * thick, rf * w * thick, rb * w * thick, q)
                for dz, cx, cy, rx, rf, rb, q in rel]
        long_sleeve = s['keeper'] or s['sleeves'] == 'long'
        skin = s['skin'] + (1,)
        trim = s['trim'] + (1,)

        def skin_uv(th, z):
            return th / (2 * math.pi), z * 2.0

        cuff_z = zw + 0.04 if long_sleeve else zs - 0.15
        self.loft('skin', [k for k in keys if k[0] <= cuff_z + 0.05], wts, skin_uv, skin)
        # The sleeve: loose over the arm, ending in a cuff
        sleeve = []
        for k in keys:
            if k[0] < cuff_z:
                continue
            g = 0.012 if k[0] < zs - 0.02 else 0.006
            sleeve.append(k[:3] + (k[3] + g, k[4] + g, k[5] + g) + k[6:])
        last = sleeve[-1]
        sleeve.append((cuff_z,) + last[1:])

        def sleeve_uv(th, z):
            return 0.09 + 0.07 * th / (2 * math.pi), 0.45 + 0.1 * np.clip((z - cuff_z) / 0.4, 0, 1)

        self.loft('shirt', sleeve, wts, sleeve_uv, (1, 1, 1, 1))
        cuff = [(cuff_z + 0.016,) + last[1:3] + tuple(r + 0.002 for r in last[3:6]) + last[6:],
                (cuff_z,) + last[1:3] + tuple(r + 0.002 for r in last[3:6]) + last[6:],
                (cuff_z - 0.002,) + last[1:3] + tuple(r - 0.008 for r in last[3:6]) + last[6:]]
        self.loft('trim', cuff, wts, lambda th, z: (th * 0, z * 0), trim, sub=1)
        self.hand(side, x, zw)

    def hand(self, side, x, zw):
        s = self.s
        sx = self.side_x(side)
        wr = 'wrist_' + side
        gloves = s['keeper']
        g = 1.25 if gloves else 1.0
        # A relaxed hand: palm facing in, fingers curled forward a little
        rel = [(0.02, 0.0, 0.0, 0.02, 0.024, 0.024, 2.0),
               (-0.01, 0.0, 0.002, 0.016, 0.03, 0.026, 2.2),
               (-0.05, -0.002, 0.006, 0.017, 0.042, 0.036, 2.6),
               (-0.09, -0.004, 0.012, 0.016, 0.04, 0.034, 2.6),
               (-0.13, -0.008, 0.024, 0.013, 0.034, 0.026, 2.4),
               (-0.165, -0.012, 0.038, 0.011, 0.026, 0.018, 2.2),
               (-0.185, -0.014, 0.05, 0.004, 0.012, 0.008, 2.0)]
        keys = [(zw + dz * g, x + cx * sx, cy * g, rx * g, rf * g, rb * g, q) for dz, cx, cy, rx, rf, rb, q in rel]
        col = (s['gloves'] if gloves else s['skin']) + (1,)
        part = 'boots' if gloves else 'skin'
        self.loft(part, keys, wr, lambda th, z: (th / (2 * math.pi), z * 2.0), col,
                  seg=max(10, self.seg - 8), sub=2)
        if gloves:
            # Wrist strap
            strap = [(zw + 0.005, x, 0.0, 0.032, 0.036, 0.036, 2.0), (zw - 0.03, x, 0.002, 0.032, 0.04, 0.038, 2.0)]
            accent = s['glove_accent'] + (1,)
            self.loft('boots', strap, wr, lambda th, z: (th * 0, z * 0), accent, seg=max(10, self.seg - 8), sub=1)
        # Thumb, along the front of the palm
        tk = [(-0.01, 0.006, 0.02, 0.011, 0.011, 0.011, 2.0), (-0.05, 0.0, 0.042, 0.01, 0.01, 0.01, 2.0),
              (-0.08, -0.004, 0.05, 0.008, 0.008, 0.008, 2.0), (-0.092, -0.005, 0.052, 0.002, 0.002, 0.002, 2.0)]
        keys = [(zw + dz * g, x + cx * sx * g, cy * g, rx * g, rf * g, rb * g, q) for dz, cx, cy, rx, rf, rb, q in tk]
        self.loft(part, keys, wr, lambda th, z: (th / (2 * math.pi), z * 2.0), col, seg=8, sub=2)

    # ---------------------------------------------------------- neck and head
    def neck(self):
        s = self.s
        w = 0.88 if s['women'] else 1.0
        keys = [(1.44, 0, -0.012, 0.056, 0.052, 0.056, 2.0), (1.52, 0, -0.008, 0.052, 0.05, 0.054, 2.0),
                (1.6, 0, -0.004, 0.05, 0.048, 0.052, 2.0), (1.66, 0, -0.008, 0.05, 0.05, 0.05, 2.0)]
        keys = [(z, cx, cy, rx * w * s['w'] ** 0.5, rf * w * s['w'] ** 0.5, rb * w * s['w'] ** 0.5, q)
                for z, cx, cy, rx, rf, rb, q in keys]
        wts = [(1.62, {'head': 1.0}), (1.56, {'neck': 1.0}), (1.48, {'chest': 0.6, 'neck': 0.4})]
        self.loft('skin', keys, wts, lambda th, z: (th / (2 * math.pi), z * 2.0), s['skin'] + (1,))

    def head_surface(self, U, V, offset=0.0):
        """Points on the head for texture coordinates U (longitude, face at 0.25)
        and V (chin 0 .. crown 1), pushed out by ``offset``."""
        th = U * 2 * math.pi
        ph = (V - 0.5) * math.pi
        d = np.stack([np.cos(th) * np.cos(ph), np.sin(th) * np.cos(ph), np.sin(ph)], axis=-1)
        r = 1.0 / np.sqrt(((d / HEAD_R) ** 2).sum(-1))
        du = (U - 0.25 + 0.5) % 1.0 - 0.5          # -0.5..0.5, 0 at the face
        front = np.clip(np.sin(th), 0, 1)
        women = self.s['women']
        f = 0.0
        # Brow ridge and eye sockets
        f += 0.006 * np.exp(-((du / 0.09) ** 2 + ((V - 0.6) / 0.025) ** 2)) * (0.6 if women else 1.0)
        for e in (-0.068, 0.068):
            f -= 0.006 * np.exp(-(((du - e) / 0.035) ** 2 + ((V - 0.548) / 0.03) ** 2))
        # Cheekbones
        for e in (-0.1, 0.1):
            f += 0.005 * np.exp(-(((du - e) / 0.04) ** 2 + ((V - 0.47) / 0.04) ** 2))
        # Nose: bridge to tip, then back in under the nostrils
        nv = np.clip((0.56 - V) / 0.13, 0, 1)
        nose_h = (0.004 + 0.022 * nv ** 1.3) * _smoothstep(0.395, 0.425, V)
        nose_w = 0.012 + 0.016 * nv
        f += nose_h * np.exp(-(du / nose_w) ** 2) * (V < 0.58) * (0.85 if women else 1.0)
        # Lips and chin
        f += 0.006 * np.exp(-((du / 0.04) ** 2 + ((V - 0.355) / 0.016) ** 2))
        f += 0.005 * np.exp(-((du / 0.035) ** 2 + ((V - 0.335) / 0.012) ** 2))
        f -= 0.003 * np.exp(-((du / 0.04) ** 2 + ((V - 0.346) / 0.005) ** 2))
        f += 0.006 * np.exp(-((du / 0.05) ** 2 + ((V - 0.22) / 0.04) ** 2)) * (0.5 if women else 1.0)
        P = d * (r + f * front ** 0.5 + offset)[..., None]
        # The jaw narrows to the chin; the back of the skull tucks in above the neck
        low = _smoothstep(0.45, 0.12, V)
        P[..., 0] *= 1 - (0.2 if not women else 0.26) * low ** 1.3
        back = np.clip(-np.sin(th), 0, 1)
        P[..., 1] *= 1 - 0.28 * low * back
        P[..., 1] += 0.012 * low * front * (V < 0.3)
        # A flatter face and sides
        P[..., 1] *= 1 - 0.05 * front * _smoothstep(0.35, 0.65, V)
        return P + HEAD_C

    def head(self):
        s = self.s
        rows, seg = (32, 40) if self.sub >= 3 else (20, 24)
        V = np.linspace(0.0, 1.0, rows + 1)[:, None].repeat(seg + 1, 1)
        U = np.linspace(0.0, 1.0, seg + 1)[None, :].repeat(rows + 1, 0)
        P = self.head_surface(U, V)
        Bv = np.where(P[..., 2] > 1.62, self.b.get({'head': 1.0}), self.b.get({'head': 0.85, 'neck': 0.15}))
        grid(self.parts['head'], P, np.stack([U, V], -1), np.array((1.0, 1.0, 1.0, 1.0)), Bv, center=HEAD_C)
        # Ears
        skin = s['skin'] + (1,)
        for sx in (-1, 1):
            u = 0.0 if sx > 0 else 0.5
            c = self.head_surface(np.array(u), np.array(0.54))
            c = c + np.array((sx * 0.002, -0.02, 0.0))
            th = np.linspace(0, 2 * math.pi, 13)
            ph = np.linspace(-math.pi / 2, math.pi / 2, 9)
            T, F = np.meshgrid(th, ph)
            E = np.stack([0.011 * np.cos(T) * np.cos(F), 0.027 * np.sin(T) * np.cos(F), 0.034 * np.sin(F)], -1)
            # Tilt back a little, with the top further out
            E[..., 1] -= E[..., 2] * 0.25
            E[..., 0] += sx * (E[..., 2] + 0.034) * 0.05
            E = E + c
            Bb = np.full(E.shape[:2], self.b.get({'head': 1.0}))
            UV = np.stack([np.full(T.shape, u), np.full(T.shape, 0.5)], -1)
            grid(self.parts['skin'], E, UV, np.array(skin), Bb, center=c)
        self.hair()

    def eyes(self):
        s = self.s
        iris = np.array(s['iris'])
        for e in (-0.068, 0.068):
            c = self.head_surface(np.array(0.25 + e), np.array(0.548), -0.0045)
            r = 0.0122
            th = np.linspace(0, 2 * math.pi, 13)
            ph = np.linspace(-math.pi / 2, math.pi / 2, 9)
            T, F = np.meshgrid(th, ph)
            d = np.stack([np.cos(T) * np.cos(F), np.sin(T) * np.cos(F), np.sin(F)], -1)
            # Look straight ahead: colour by the angle from +y
            fwd = d[..., 1]
            C = np.ones(T.shape + (4,))
            C[..., :3] = (0.92, 0.9, 0.86)
            ir = (fwd > 0.86)[..., None]
            pu = (fwd > 0.96)[..., None]
            C[..., :3] = np.where(ir, iris, C[..., :3])
            C[..., :3] = np.where(pu, (0.03, 0.03, 0.03), C[..., :3])
            P = c + d * r
            Bb = np.full(T.shape, self.b.get({'head': 1.0}))
            grid(self.parts['eyes'], P, np.zeros(T.shape + (2,)), C, Bb, center=c)

    # ---------------------------------------------------------- hair
    def hair(self):
        s = self.s
        style = s['hair']
        hair = np.array(s['hair_col'] + (1,))
        rows, seg = (26, 40) if self.sub >= 3 else (16, 24)
        V = np.linspace(0.2, 1.0, rows + 1)[:, None].repeat(seg + 1, 1)
        U = np.linspace(0.0, 1.0, seg + 1)[None, :].repeat(rows + 1, 0)
        du = np.abs((U - 0.25 + 0.5) % 1.0 - 0.5)         # 0 face .. 0.5 back
        head_w = {'head': 1.0}
        if style != 'bald':
            # Hairline: low over the forehead, up round the temples, down to the nape
            line = np.interp(du, [0.0, 0.08, 0.14, 0.2, 0.24, 0.3, 0.5], [0.705, 0.69, 0.655, 0.6, 0.53, 0.47, 0.34])
            if style in ('long', 'braids'):
                line = np.interp(du, [0.0, 0.08, 0.14, 0.2, 0.3, 0.5], [0.71, 0.69, 0.64, 0.5, 0.3, 0.22])
            if s['women'] and style not in ('buzz',):
                line = np.minimum(line, np.interp(du, [0.0, 0.12, 0.2, 0.3, 0.5], [0.72, 0.66, 0.5, 0.32, 0.24]))
            m = _smoothstep(line - 0.005, line + 0.035, V)
            top = _smoothstep(0.55, 1.0, V)
            t = {'short': 0.009 + 0.008 * top, 'buzz': 0.0025, 'quiff': 0.01 + 0.006 * top, 'long': 0.012 + 0.006 * top,
                 'ponytail': 0.008 + 0.004 * top, 'bun': 0.008 + 0.004 * top, 'manbun': 0.008 + 0.004 * top,
                 'afro': 0.03 + 0.04 * top, 'curly': 0.016 + 0.016 * top, 'mohawk': 0.0025, 'braids': 0.005,
                 'r9': 0.0025}.get(style, 0.012)
            t = np.asarray(t) + np.zeros_like(V)
            rng = np.random.default_rng(len(style) * 7 + int(s['w'] * 100))
            if style == 'quiff':
                t = t + 0.035 * np.exp(-((du / 0.12) ** 2 + ((V - 0.8) / 0.09) ** 2))
            if style in ('curly', 'afro'):
                bumps = np.sin(U * 2 * math.pi * 17 + np.sin(V * 23) * 2) * np.sin(V * 2 * math.pi * 9 + U * 11)
                t = t + (0.006 if style == 'curly' else 0.009) * bumps
            if style == 'braids':
                t = t + 0.004 * np.abs(np.sin(U * 2 * math.pi * 14))
            if style == 'r9':
                t = t + 0.02 * np.exp(-((du / 0.06) ** 2 + ((V - 0.8) / 0.05) ** 2))
            if style == 'mohawk':
                Pc = self.head_surface(U, V)
                t = t + 0.045 * np.exp(-((Pc[..., 0] - HEAD_C[0]) / 0.016) ** 2) * _smoothstep(0.74, 0.9, V)
            t = t + 0.0015 * (rng.random(V.shape) - 0.5) * (style not in ('buzz', 'mohawk', 'r9'))
            # Hair that hangs below the skull drops straight down
            # Where the hair thins out the shell sinks under the scalp, so the hairline
            # is where the two surfaces cross: a smooth edge, not a ragged one
            P = self.head_surface(U, V, (t + 0.0015) * m - 0.004 * (1 - m))
            if style == 'long':
                hang = np.clip((0.42 - V) / 0.22, 0, 1) * np.clip((du - 0.12) / 0.1, 0, 1)
                P[..., 2] -= hang * 0.14
                P[..., 1] -= hang * 0.02
            mask = V > line - 0.1
            col = np.broadcast_to(hair, V.shape + (4,)).copy()
            if style in ('buzz', 'mohawk', 'r9'):
                # Skin shows through a close crop
                skin = np.array(s['skin'] + (1,))
                k = 0.45 if style != 'mohawk' else 0.45 * (t < 0.01)[..., None]
                col = col * (1 - k) + skin * k
            Bv = np.where(P[..., 2] > 1.6, self.b.get(head_w), self.b.get({'head': 0.6, 'neck': 0.4}))
            grid(self.parts['hair'], P, np.stack([U, V * 2], -1), col, Bv, mask=mask, center=HEAD_C)
        # Extras: tails, buns and the headband
        hb = self.b.get(head_w)
        if style == 'ponytail':
            keys = [(1.79, 0, -0.08, 0.03, 0.03, 0.03, 2.0), (1.76, 0, -0.125, 0.034, 0.034, 0.034, 2.0),
                    (1.66, 0, -0.14, 0.026, 0.026, 0.026, 2.0), (1.56, 0, -0.13, 0.016, 0.016, 0.016, 2.0),
                    (1.52, 0, -0.12, 0.004, 0.004, 0.004, 2.0)]
            self.loft('hair', keys, [(1.7, head_w), (1.56, {'head': 0.5, 'neck': 0.5})],
                      lambda th, z: (th / (2 * math.pi), z * 4), tuple(hair), seg=12)
        if style in ('bun', 'manbun'):
            cz, cy = (1.83, -0.06) if style == 'bun' else (1.8, -0.09)
            th = np.linspace(0, 2 * math.pi, 13)
            ph = np.linspace(-math.pi / 2, math.pi / 2, 9)
            T, F = np.meshgrid(th, ph)
            c = np.array((0.0, cy, cz))
            P = c + np.stack([0.042 * np.cos(T) * np.cos(F), 0.038 * np.sin(T) * np.cos(F), 0.036 * np.sin(F)], -1)
            grid(self.parts['hair'], P, np.stack([T / 6.28, F], -1), hair, np.full(T.shape, hb), center=c)
        if style == 'braids':
            for bx in (-0.045, -0.015, 0.015, 0.045):
                keys = [(1.74, bx, -0.1, 0.012, 0.012, 0.012, 2.0), (1.62, bx * 1.3, -0.115, 0.011, 0.011, 0.011, 2.0),
                        (1.5, bx * 1.5, -0.105, 0.008, 0.008, 0.008, 2.0), (1.46, bx * 1.5, -0.1, 0.002, 0.002, 0.002, 2)]
                self.loft('hair', keys, [(1.66, head_w), (1.52, {'head': 0.4, 'neck': 0.3, 'chest': 0.3})],
                          lambda th, z: (th / (2 * math.pi), z * 6), tuple(hair), seg=8)
        if s['headband']:
            rows_v = np.linspace(0.66, 0.72, 4)[:, None].repeat(41, 1)
            Uh = np.linspace(0.0, 1.0, 41)[None, :].repeat(4, 0)
            off = 0.02 if style in ('afro', 'curly') else (0.006 if style in ('buzz', 'bald', 'mohawk', 'r9') else 0.016)
            P = self.head_surface(Uh, rows_v, off)
            grid(self.parts['trim'], P, np.zeros(P.shape[:2] + (2,)), np.array(s['trim'] + (1,)),
                 np.full(Uh.shape, hb), center=HEAD_C)
        self.beard()

    def beard(self):
        s = self.s
        beard = s['beard']
        if beard not in ('full', 'goatee'):
            return
        rows, seg = 18, 48
        V = np.linspace(0.12, 0.47, rows + 1)[:, None].repeat(seg + 1, 1)
        U = np.linspace(0.0, 1.0, seg + 1)[None, :].repeat(rows + 1, 0)
        du = np.abs((U - 0.25 + 0.5) % 1.0 - 0.5)
        if beard == 'full':
            m = _smoothstep(0.24, 0.2, du) * _smoothstep(0.45, 0.41, V) * _smoothstep(0.14, 0.18, V)
            mouth = np.exp(-((du / 0.045) ** 2 + ((V - 0.345) / 0.016) ** 2))
            m = m * (1 - mouth)
            # Keep the cheeks above the jawline bare
            m *= 1 - _smoothstep(0.38, 0.44, V) * _smoothstep(0.05, 0.12, du) * (du < 0.2)
            t = 0.009
        else:
            m = _smoothstep(0.05, 0.03, du) * _smoothstep(0.34, 0.32, V) * _smoothstep(0.17, 0.2, V)
            m = np.maximum(m, _smoothstep(0.05, 0.035, du) * np.exp(-((V - 0.372) / 0.008) ** 2))
            t = 0.006
        P = self.head_surface(U, V, t * m + 0.001)
        Bv = np.full(U.shape, self.b.get({'head': 1.0}))
        grid(self.parts['hair'], P, np.stack([U, V * 2], -1), np.array(s['hair_col'] + (1,)), Bv, mask=m > 0.05,
             center=HEAD_C)


# ---------------------------------------------------------------- Panda glue
_FORMAT = None


def _format():
    global _FORMAT
    if _FORMAT is None:
        a0 = GeomVertexArrayFormat()
        a0.add_column(InternalName.get_vertex(), 3, Geom.NT_float32, Geom.C_point)
        a0.add_column(InternalName.get_normal(), 3, Geom.NT_float32, Geom.C_normal)
        a0.add_column(InternalName.get_texcoord(), 2, Geom.NT_float32, Geom.C_texcoord)
        a1 = GeomVertexArrayFormat()
        a1.add_column(InternalName.get_color(), 4, Geom.NT_float32, Geom.C_color)
        a2 = GeomVertexArrayFormat()
        a2.add_column(InternalName.get_transform_weight(), 4, Geom.NT_float32, Geom.C_other)
        a2.add_column(InternalName.get_transform_index(), 4, Geom.NT_uint8, Geom.C_index)
        f = GeomVertexFormat()
        f.add_array(a0)
        f.add_array(a1)
        f.add_array(a2)
        # Up to four joints per vertex, deformed in the shader where it can
        # (Panda falls back to doing it on the processor otherwise)
        spec = GeomVertexAnimationSpec()
        spec.set_hardware(4, True)
        f.set_animation(spec)
        _FORMAT = GeomVertexFormat.register_format(f)
    return _FORMAT


def _write(vdata, i, data):
    vdata.modify_array_handle(i).set_data(data.tobytes())


def geom_node(name, part, blends):
    P = np.concatenate(part.P).astype(np.float32)
    N = np.concatenate(part.N).astype(np.float32)
    UV = np.concatenate(part.UV).astype(np.float32)
    C = np.concatenate(part.C).astype(np.float32)
    B = np.concatenate(part.B).astype(np.uint16)
    T = np.concatenate(part.T).astype(np.uint32)
    n = len(P)
    vd = GeomVertexData(name, _format(), Geom.UH_static)
    vd.unclean_set_num_rows(n)
    vd.set_transform_table(blends.transform_table())
    _write(vd, 0, np.ascontiguousarray(np.concatenate([P, N, UV], axis=1)))
    _write(vd, 1, np.ascontiguousarray(C))
    W, J = blends.weights_indices()
    rec = np.zeros(n, dtype=[('w', np.float32, 4), ('j', np.uint8, 4)])
    rec['w'] = W[B]
    rec['j'] = J[B]
    _write(vd, 2, rec)
    tris = GeomTriangles(Geom.UH_static)
    tris.set_index_type(Geom.NT_uint32)
    ia = tris.modify_vertices()
    ia.unclean_set_num_rows(len(T) * 3)
    ia.modify_handle().set_data(np.ascontiguousarray(T.reshape(-1)).tobytes())
    g = Geom(vd)
    g.add_primitive(tris)
    gn = GeomNode(name)
    gn.add_geom(g)
    return NodePath(gn)


class Rig:
    """A Character with the body's joints, each driven by a NodePath you rotate.

    ``self.ctl[name]`` mirrors the skeleton in the scene graph (under ``self.np``)
    so you can ask where a foot or hand is in the world."""

    def __init__(self, parent, skel):
        self.char = Character('footballer')
        bundle = self.char.get_bundle(0)
        group = PartGroup(bundle, '<skeleton>')
        self.np = parent.attach_new_node(self.char)
        self.joints = {}
        self.ctl = {}
        for name, par, off in skel:
            mat = Mat4.translate_mat(*off)
            pj = self.joints[par] if par else group
            self.joints[name] = CharacterJoint(self.char, bundle, pj, name, mat)
            node = ModelNode(name)
            node.set_preserve_transform(ModelNode.PT_local)
            cp = (self.ctl[par] if par else self.np).attach_new_node(node)
            cp.set_pos(*off)
            self.ctl[name] = cp
            bundle.control_joint(name, node)
        self.rest = {name: off for name, _, off in skel}
        self.blends = Blends(self.joints)
        self.char.set_bounds(OmniBoundingVolume())
        self.char.set_final(True)
