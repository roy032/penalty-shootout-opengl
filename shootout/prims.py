"""Drawing primitives shared by the renderer, the stadium and the effects."""

import math

from OpenGL.GL import *  # noqa: F401,F403
from OpenGL.GLU import *  # noqa: F401,F403

_quadric = None


def init():
    global _quadric
    _quadric = gluNewQuadric()
    gluQuadricNormals(_quadric, GLU_SMOOTH)
    gluQuadricTexture(_quadric, GL_TRUE)


def box(sx, sy, sz):
    """Unit cube scaled to sx, sy, sz around the current origin, with normals."""
    x, y, z = sx / 2.0, sy / 2.0, sz / 2.0
    glBegin(GL_QUADS)
    for n, verts in (
        ((0, 0, 1), ((-x, -y, z), (x, -y, z), (x, y, z), (-x, y, z))),
        ((0, 0, -1), ((-x, -y, -z), (-x, y, -z), (x, y, -z), (x, -y, -z))),
        ((-1, 0, 0), ((-x, -y, -z), (-x, -y, z), (-x, y, z), (-x, y, -z))),
        ((1, 0, 0), ((x, -y, -z), (x, y, -z), (x, y, z), (x, -y, z))),
        ((0, 1, 0), ((-x, y, -z), (-x, y, z), (x, y, z), (x, y, -z))),
        ((0, -1, 0), ((-x, -y, -z), (x, -y, -z), (x, -y, z), (-x, -y, z))),
    ):
        glNormal3f(*n)
        for v in verts:
            glVertex3f(*v)
    glEnd()


def sphere(r, slices=16):
    gluSphere(_quadric, r, slices, max(6, slices * 3 // 4))


def cylinder_between(a, b, r, slices=14, r2=None):
    """Cylinder (or cone, with r2) from point a to point b."""
    dx, dy, dz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
    length = math.sqrt(dx * dx + dy * dy + dz * dz)
    if length < 1e-6:
        return
    glPushMatrix()
    glTranslatef(*a)
    # gluCylinder runs along +z; rotate +z onto the segment
    ax, ay, az = -dy, dx, 0.0
    angle = math.degrees(math.acos(max(-1.0, min(1.0, dz / length))))
    if abs(ax) + abs(ay) < 1e-6:
        if dz < 0:
            glRotatef(180, 1, 0, 0)
    else:
        glRotatef(angle, ax, ay, az)
    gluCylinder(_quadric, r, r if r2 is None else r2, length, slices, 1)
    glPopMatrix()


def limb(length, r_top, r_bottom, slices=10, cap_top=True, cap_bottom=True):
    """A tapered, rounded limb hanging down (-y) from the current origin."""
    glPushMatrix()
    glRotatef(90.0, 1, 0, 0)                 # +z of the cylinder becomes -y
    gluCylinder(_quadric, r_top, r_bottom, length, slices, 1)
    glPopMatrix()
    if cap_top:
        sphere(r_top, slices)
    if cap_bottom:
        glPushMatrix()
        glTranslatef(0.0, -length, 0.0)
        sphere(r_bottom, slices)
        glPopMatrix()


def rounded_trunk(height, w_bottom, w_top, depth, slices=16):
    """A torso: an elliptical tube widening to the shoulders, with closed
    rounded ends. Centred on the current origin, height along y."""
    glPushMatrix()
    glTranslatef(0.0, -height / 2.0, 0.0)
    glScalef(1.0, 1.0, depth / max(w_bottom, w_top))
    glRotatef(-90.0, 1, 0, 0)
    gluCylinder(_quadric, w_bottom, w_top, height, slices, 2)
    gluDisk(_quadric, 0.0, w_bottom, slices, 1)
    glTranslatef(0.0, 0.0, height)
    glScalef(1.0, 1.0, 0.45)
    gluSphere(_quadric, w_top, slices, 6)
    glPopMatrix()


def flat_quad(x1, z1, x2, z2, y=0.0):
    glNormal3f(0, 1, 0)
    glVertex3f(x1, y, z1)
    glVertex3f(x1, y, z2)
    glVertex3f(x2, y, z2)
    glVertex3f(x2, y, z1)


def disc(x, z, r, y=0.01, segments=24):
    glBegin(GL_TRIANGLE_FAN)
    glNormal3f(0, 1, 0)
    glVertex3f(x, y, z)
    for i in range(segments + 1):
        a = 2 * math.pi * i / segments
        glVertex3f(x + r * math.cos(a), y, z - r * math.sin(a))
    glEnd()


def soft_disc(x, z, r, colour, alpha, y=0.02, segments=20, sx=1.0):
    """A disc that fades out towards its rim (shadows, glows, splashes)."""
    glBegin(GL_TRIANGLE_FAN)
    glNormal3f(0, 1, 0)
    glColor4f(colour[0], colour[1], colour[2], alpha)
    glVertex3f(x, y, z)
    glColor4f(colour[0], colour[1], colour[2], 0.0)
    for i in range(segments + 1):
        a = 2 * math.pi * i / segments
        glVertex3f(x + r * sx * math.cos(a), y, z - r * math.sin(a))
    glEnd()


def quad(p1, p2, p3, p4, normal=None):
    if normal:
        glNormal3f(*normal)
    for p in (p1, p2, p3, p4):
        glVertex3f(*p)


def billboard(x, y, z, size, yaw):
    """A square facing the camera's yaw (degrees), centred on x, y, z."""
    a = math.radians(yaw)
    cx, cz = math.cos(a) * size / 2.0, -math.sin(a) * size / 2.0
    glVertex3f(x - cx, y - size / 2.0, z - cz)
    glVertex3f(x + cx, y - size / 2.0, z + cz)
    glVertex3f(x + cx, y + size / 2.0, z + cz)
    glVertex3f(x - cx, y + size / 2.0, z - cz)
