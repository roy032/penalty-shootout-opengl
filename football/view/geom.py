"""Procedural meshes: boxes, cylinders, spheres, capsules and planes with
normals and UVs, built straight into Panda3D GeomNodes."""

import math

from panda3d.core import (Geom, GeomNode, GeomTriangles, GeomVertexData, GeomVertexFormat, GeomVertexWriter,
                          NodePath)

_FMT = GeomVertexFormat.get_v3n3t2()
_FMT_C = GeomVertexFormat.get_v3n3c4t2()


class Mesh:
    """Accumulate triangles, then turn them into a GeomNode."""

    def __init__(self, name='mesh', colors=True):
        self.name = name
        self.colors = colors
        self.vdata = GeomVertexData(name, _FMT_C if colors else _FMT, Geom.UH_static)
        self.v = GeomVertexWriter(self.vdata, 'vertex')
        self.n = GeomVertexWriter(self.vdata, 'normal')
        self.t = GeomVertexWriter(self.vdata, 'texcoord')
        self.c = GeomVertexWriter(self.vdata, 'color') if colors else None
        self.tris = GeomTriangles(Geom.UH_static)
        self.count = 0

    def vert(self, p, n, uv=(0.0, 0.0), c=(1, 1, 1, 1)):
        self.v.add_data3(*p)
        self.n.add_data3(*n)
        self.t.add_data2(*uv)
        if self.c is not None:
            self.c.add_data4(*c)
        self.count += 1
        return self.count - 1

    def tri(self, a, b, c):
        self.tris.add_vertices(a, b, c)

    def quad(self, a, b, c, d):
        self.tris.add_vertices(a, b, c)
        self.tris.add_vertices(a, c, d)

    def node(self):
        g = Geom(self.vdata)
        g.add_primitive(self.tris)
        gn = GeomNode(self.name)
        gn.add_geom(g)
        return NodePath(gn)


def _norm(x, y, z):
    d = math.sqrt(x * x + y * y + z * z) or 1.0
    return x / d, y / d, z / d


def box(sx, sy, sz, name='box', center=(0, 0, 0), mesh=None, color=(1, 1, 1, 1)):
    """Axis-aligned box of size sx, sy, sz around center."""
    m = mesh or Mesh(name)
    cx, cy, cz = center
    hx, hy, hz = sx / 2, sy / 2, sz / 2
    faces = [((1, 0, 0), (0, 1, 0), (0, 0, 1)), ((-1, 0, 0), (0, -1, 0), (0, 0, 1)),
             ((0, 1, 0), (-1, 0, 0), (0, 0, 1)), ((0, -1, 0), (1, 0, 0), (0, 0, 1)),
             ((0, 0, 1), (1, 0, 0), (0, 1, 0)), ((0, 0, -1), (1, 0, 0), (0, -1, 0))]
    for n, u, w in faces:
        c0 = (cx + n[0] * hx, cy + n[1] * hy, cz + n[2] * hz)
        su = abs(u[0]) * hx + abs(u[1]) * hy + abs(u[2]) * hz
        sw = abs(w[0]) * hx + abs(w[1]) * hy + abs(w[2]) * hz
        pts = []
        for a, b, uv in ((-1, -1, (0, 0)), (1, -1, (1, 0)), (1, 1, (1, 1)), (-1, 1, (0, 1))):
            p = (c0[0] + u[0] * su * a + w[0] * sw * b, c0[1] + u[1] * su * a + w[1] * sw * b,
                 c0[2] + u[2] * su * a + w[2] * sw * b)
            pts.append(m.vert(p, n, uv, color))
        m.quad(*pts)
    return m


def cylinder(r0, r1, h, seg=16, name='cyl', mesh=None, caps=True, axis='z', base=(0, 0, 0), color=(1, 1, 1, 1),
             uv_scale=(1.0, 1.0)):
    """Tapered cylinder from base along +axis for length h."""
    m = mesh or Mesh(name)

    def P(x, y, z):
        if axis == 'z':
            return (base[0] + x, base[1] + y, base[2] + z)
        if axis == 'x':
            return (base[0] + z, base[1] + x, base[2] + y)
        return (base[0] + y, base[1] + z, base[2] + x)

    def N(x, y, z):
        return (x, y, z) if axis == 'z' else ((z, x, y) if axis == 'x' else (y, z, x))

    slope = (r0 - r1) / h if h else 0.0
    ring = []
    for i in range(seg + 1):
        a = 2 * math.pi * i / seg
        ca, sa = math.cos(a), math.sin(a)
        n = _norm(ca, sa, slope)
        v0 = m.vert(P(ca * r0, sa * r0, 0), N(*n), (i / seg * uv_scale[0], 0), color)
        v1 = m.vert(P(ca * r1, sa * r1, h), N(*n), (i / seg * uv_scale[0], uv_scale[1]), color)
        ring.append((v0, v1))
    for i in range(seg):
        a0, a1 = ring[i]
        b0, b1 = ring[i + 1]
        m.quad(a0, b0, b1, a1)
    if caps:
        for z, r, s in ((0, r0, -1), (h, r1, 1)):
            if r <= 0:
                continue
            c = m.vert(P(0, 0, z), N(0, 0, s), (0.5, 0.5), color)
            pts = [m.vert(P(math.cos(2 * math.pi * i / seg) * r, math.sin(2 * math.pi * i / seg) * r, z), N(0, 0, s),
                          (0.5 + 0.5 * math.cos(2 * math.pi * i / seg), 0.5 + 0.5 * math.sin(2 * math.pi * i / seg)),
                          color) for i in range(seg + 1)]
            for i in range(seg):
                if s > 0:
                    m.tri(c, pts[i], pts[i + 1])
                else:
                    m.tri(c, pts[i + 1], pts[i])
    return m


def sphere(r, seg=16, rings=10, name='sphere', mesh=None, center=(0, 0, 0), scale=(1, 1, 1), color=(1, 1, 1, 1),
           zmin=-1.0, zmax=1.0):
    """UV sphere (or a band of one, between zmin and zmax as fractions of the radius)."""
    m = mesh or Mesh(name)
    cx, cy, cz = center
    sx, sy, sz = scale
    t0, t1 = math.acos(max(-1, min(1, zmax))), math.acos(max(-1, min(1, zmin)))
    rows = []
    for j in range(rings + 1):
        th = t0 + (t1 - t0) * j / rings
        st, ct = math.sin(th), math.cos(th)
        row = []
        for i in range(seg + 1):
            ph = 2 * math.pi * i / seg
            x, y, z = st * math.cos(ph), st * math.sin(ph), ct
            n = _norm(x / sx, y / sy, z / sz)
            row.append(m.vert((cx + x * r * sx, cy + y * r * sy, cz + z * r * sz), n, (i / seg, 1 - j / rings), color))
        rows.append(row)
    for j in range(rings):
        for i in range(seg):
            a, b = rows[j][i], rows[j][i + 1]
            c, d = rows[j + 1][i + 1], rows[j + 1][i]
            m.quad(a, d, c, b)
    return m


def capsule(r, length, seg=12, name='capsule', mesh=None, base=(0, 0, 0), color=(1, 1, 1, 1), r_top=None):
    """Capsule along -z from base (limbs hang down from their joint)."""
    m = mesh or Mesh(name)
    rt = r if r_top is None else r_top
    bx, by, bz = base
    sphere(rt, seg, 6, mesh=m, center=(bx, by, bz), color=color, zmin=0.0, zmax=1.0)
    cylinder(r, rt, length, seg, mesh=m, caps=False, base=(bx, by, bz - length), color=color)
    sphere(r, seg, 6, mesh=m, center=(bx, by, bz - length), color=color, zmin=-1.0, zmax=0.0)
    return m


def plane(sx, sy, name='plane', uv=(1.0, 1.0), center=(0, 0, 0), mesh=None, color=(1, 1, 1, 1), normal_up=True):
    m = mesh or Mesh(name)
    cx, cy, cz = center
    hx, hy = sx / 2, sy / 2
    n = (0, 0, 1) if normal_up else (0, 0, -1)
    a = m.vert((cx - hx, cy - hy, cz), n, (0, 0), color)
    b = m.vert((cx + hx, cy - hy, cz), n, (uv[0], 0), color)
    c = m.vert((cx + hx, cy + hy, cz), n, (uv[0], uv[1]), color)
    d = m.vert((cx - hx, cy + hy, cz), n, (0, uv[1]), color)
    if normal_up:
        m.quad(a, b, c, d)
    else:
        m.quad(a, d, c, b)
    return m


def quad3(m, p0, p1, p2, p3, uv=((0, 0), (1, 0), (1, 1), (0, 1)), color=(1, 1, 1, 1), double=False):
    """Arbitrary quad (counter-clockwise seen from the front)."""
    ux, uy, uz = p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2]
    vx, vy, vz = p3[0] - p0[0], p3[1] - p0[1], p3[2] - p0[2]
    n = _norm(uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx)
    idx = [m.vert(p, n, t, color) for p, t in zip((p0, p1, p2, p3), uv)]
    m.quad(*idx)
    if double:
        nb = (-n[0], -n[1], -n[2])
        idx = [m.vert(p, nb, t, color) for p, t in zip((p0, p1, p2, p3), uv)]
        m.quad(idx[0], idx[3], idx[2], idx[1])
