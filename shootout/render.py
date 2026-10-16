"""3D scene: stadium, pitch, goal, players and ball."""

import math
import random

from OpenGL.GL import *  # noqa: F401,F403
from OpenGL.GLU import *  # noqa: F401,F403
from OpenGL.GLUT import *  # noqa: F401,F403

from . import config as C

SKY = (0.03, 0.05, 0.11)
SKIN = (0.93, 0.76, 0.6)
GLOVE = (0.95, 0.95, 0.95)
BOOT = (0.08, 0.08, 0.08)

_quadric = None
_static_list = None


def init_gl():
    global _quadric
    glClearColor(SKY[0], SKY[1], SKY[2], 1.0)
    glEnable(GL_DEPTH_TEST)
    glEnable(GL_BLEND)
    glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
    glEnable(GL_LINE_SMOOTH)
    glEnable(GL_NORMALIZE)
    glEnable(GL_LIGHTING)
    glEnable(GL_LIGHT0)
    glEnable(GL_LIGHT1)
    glEnable(GL_COLOR_MATERIAL)
    glColorMaterial(GL_FRONT_AND_BACK, GL_AMBIENT_AND_DIFFUSE)
    glLightModelfv(GL_LIGHT_MODEL_AMBIENT, (0.32, 0.32, 0.36, 1.0))
    glLightfv(GL_LIGHT0, GL_DIFFUSE, (0.85, 0.85, 0.8, 1.0))
    glLightfv(GL_LIGHT1, GL_DIFFUSE, (0.35, 0.37, 0.45, 1.0))
    glShadeModel(GL_SMOOTH)
    glEnable(GL_FOG)
    glFogi(GL_FOG_MODE, GL_LINEAR)
    glFogfv(GL_FOG_COLOR, (SKY[0], SKY[1], SKY[2], 1.0))
    glFogf(GL_FOG_START, 45.0)
    glFogf(GL_FOG_END, 140.0)
    _quadric = gluNewQuadric()
    gluQuadricNormals(_quadric, GLU_SMOOTH)


def set_lights():
    # Floodlights: high and behind the camera, plus a cool fill from the far side
    glLightfv(GL_LIGHT0, GL_POSITION, (0.35, 1.0, 0.6, 0.0))
    glLightfv(GL_LIGHT1, GL_POSITION, (-0.5, 0.6, -1.0, 0.0))


# ------------------------------------------------------------------ primitives
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
    gluSphere(_quadric, r, slices, slices)


def cylinder_between(a, b, r, slices=14):
    """Cylinder from point a to point b."""
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
    gluCylinder(_quadric, r, r, length, slices, 1)
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


# ---------------------------------------------------------------- static scene
def _line_strip_quads(points, width, y=0.012):
    """Thick white line on the grass through a list of (x, z) points."""
    glBegin(GL_QUADS)
    glNormal3f(0, 1, 0)
    for (x1, z1), (x2, z2) in zip(points, points[1:]):
        dx, dz = x2 - x1, z2 - z1
        length = math.hypot(dx, dz) or 1.0
        nx, nz = -dz / length * width / 2, dx / length * width / 2
        glVertex3f(x1 - nx, y, z1 - nz)
        glVertex3f(x1 + nx, y, z1 + nz)
        glVertex3f(x2 + nx, y, z2 + nz)
        glVertex3f(x2 - nx, y, z2 - nz)
    glEnd()


def _pitch():
    # Mown stripes
    stripe = 5.5
    z = -40.0
    i = 0
    glBegin(GL_QUADS)
    while z < 40.0:
        glColor3f(*((0.17, 0.5, 0.19) if i % 2 else (0.2, 0.57, 0.22)))
        flat_quad(-48.0, z, 48.0, z + stripe)
        z += stripe
        i += 1
    glEnd()
    glColor3f(0.95, 0.95, 0.95)
    w = 0.12
    line = C.GOAL_LINE_Z
    _line_strip_quads([(-34.0, line), (34.0, line)], w)
    pa_front = line + C.PENALTY_AREA_DEPTH
    hw = C.PENALTY_AREA_HALF_WIDTH
    _line_strip_quads([(-hw, line), (-hw, pa_front), (hw, pa_front), (hw, line)], w)
    ga_front = line + C.GOAL_AREA_DEPTH
    gw = C.GOAL_AREA_HALF_WIDTH
    _line_strip_quads([(-gw, line), (-gw, ga_front), (gw, ga_front), (gw, line)], w)
    # Penalty arc: the part of the 9.15 m circle outside the area
    limit = math.acos((pa_front - C.SPOT_Z) / C.ARC_RADIUS)
    pts = []
    for k in range(25):
        a = -limit + 2 * limit * k / 24
        pts.append((C.ARC_RADIUS * math.sin(a), C.SPOT_Z + C.ARC_RADIUS * math.cos(a)))
    _line_strip_quads(pts, w)
    disc(0.0, C.SPOT_Z, 0.12, 0.013)
    # Touchlines at the edge of view
    _line_strip_quads([(-34.0, line), (-34.0, 40.0)], w)
    _line_strip_quads([(34.0, line), (34.0, 40.0)], w)


def _ad_boards():
    colours = [(0.1, 0.2, 0.6), (0.75, 0.1, 0.12), (0.05, 0.45, 0.25), (0.9, 0.6, 0.05)]
    words = ['SHOOTOUT', 'PENALTY CUP', 'TOP BINS', 'PANENKA']
    z = C.GOAL_LINE_Z - 6.0
    x = -30.0
    i = 0
    while x < 30.0:
        glColor3f(*colours[i % len(colours)])
        glPushMatrix()
        glTranslatef(x + 3.0, 0.5, z)
        box(6.0, 1.0, 0.15)
        glPopMatrix()
        glDisable(GL_LIGHTING)
        glColor3f(1, 1, 1)
        glPushMatrix()
        word = words[i % len(words)]
        glTranslatef(x + 3.0 - len(word) * 0.235, 0.28, z + 0.09)
        glScalef(0.0045, 0.0045, 0.0045)
        glLineWidth(2.0)
        for ch in word:
            glutStrokeCharacter(GLUT_STROKE_ROMAN, ord(ch))
        glPopMatrix()
        glEnable(GL_LIGHTING)
        x += 6.0
        i += 1


def _stand(x1, x2, z_front, depth, rows, facing, rng):
    """A tiered stand with a crowd. facing: +1 faces +z, -1 faces -x, 1j faces +x..."""
    step_d = depth / rows
    for r in range(rows):
        h = 1.0 + r * 0.65
        zc = z_front - facing * (r + 0.5) * step_d
        glColor3f(0.22, 0.24, 0.3)
        glPushMatrix()
        glTranslatef((x1 + x2) / 2, h / 2, zc)
        box(x2 - x1, h, step_d)
        glPopMatrix()
        # Fans: little coloured blocks on each step
        x = x1 + 0.3
        while x < x2 - 0.3:
            if rng.random() < 0.85:
                shirt = rng.choice([(0.85, 0.12, 0.15), (0.15, 0.35, 0.9), (0.9, 0.9, 0.9),
                                    (0.95, 0.8, 0.1), (0.1, 0.1, 0.12), (0.8, 0.3, 0.1)])
                glColor3f(*shirt)
                glPushMatrix()
                glTranslatef(x, h + 0.3, zc + facing * 0.1)
                box(0.38, 0.6, 0.3)
                glTranslatef(0, 0.42, 0)
                glColor3f(*rng.choice([SKIN, (0.55, 0.38, 0.26), (0.36, 0.24, 0.16)]))
                box(0.2, 0.2, 0.2)
                glPopMatrix()
            x += 0.55 + rng.random() * 0.15


def _floodlight(x, z):
    glColor3f(0.4, 0.42, 0.45)
    cylinder_between((x, 0, z), (x, 26, z), 0.35)
    glDisable(GL_LIGHTING)
    glColor3f(1.0, 0.98, 0.85)
    glPushMatrix()
    glTranslatef(x, 27.0, z)
    glBegin(GL_QUADS)
    glVertex3f(-3, -1.5, 0.4)
    glVertex3f(3, -1.5, 0.4)
    glVertex3f(3, 1.5, 0.4)
    glVertex3f(-3, 1.5, 0.4)
    glEnd()
    glPopMatrix()
    glEnable(GL_LIGHTING)


def _build_static():
    rng = random.Random(11)
    _pitch()
    _ad_boards()
    # Stand behind the goal, and stands along both touchlines
    _stand(-36.0, 36.0, C.GOAL_LINE_Z - 9.0, 14.0, 12, 1, rng)
    _stand(-36.0, 36.0, 30.0, 12.0, 10, -1, rng)
    glPushMatrix()
    glTranslatef(-41.0, 0.0, -2.0)
    glRotatef(90, 0, 1, 0)
    _stand(-24.0, 30.0, 0.0, 12.0, 10, 1, rng)
    glPopMatrix()
    glPushMatrix()
    glTranslatef(41.0, 0.0, -2.0)
    glRotatef(-90, 0, 1, 0)
    _stand(-30.0, 24.0, 0.0, 12.0, 10, 1, rng)
    glPopMatrix()
    for x, z in ((-40.0, -30.0), (40.0, -30.0), (-46.0, 25.0), (46.0, 25.0)):
        _floodlight(x, z)


def draw_static():
    global _static_list
    if _static_list is None:
        _static_list = glGenLists(1)
        glNewList(_static_list, GL_COMPILE)
        _build_static()
        glEndList()
    glCallList(_static_list)


# ------------------------------------------------------------------------ goal
def draw_goal(net_hit, clock):
    hw = C.GOAL_HALF_WIDTH + C.POST_RADIUS
    h = C.GOAL_HEIGHT + C.POST_RADIUS
    z = C.GOAL_LINE_Z - C.POST_RADIUS
    back = C.GOAL_LINE_Z - C.GOAL_DEPTH
    glColor3f(0.97, 0.97, 0.97)
    pr = C.POST_RADIUS
    cylinder_between((-hw, 0, z), (-hw, h + pr, z), pr)
    cylinder_between((hw, 0, z), (hw, h + pr, z), pr)
    cylinder_between((-hw - pr, h, z), (hw + pr, h, z), pr)
    # Net supports
    glColor3f(0.6, 0.6, 0.62)
    for s in (-1, 1):
        cylinder_between((s * hw, h, z), (s * hw, h, back), 0.025, 6)
        cylinder_between((s * hw, h, back), (s * hw, 0, back), 0.025, 6)
    # Net with a ripple where the ball hit
    bulge = None
    if net_hit is not None:
        age = clock - net_hit[2]
        if age < 2.5:
            bulge = (net_hit[0], net_hit[1], 0.55 * math.exp(-age * 2.2) * math.cos(age * 9.0))

    def back_z(x, y):
        if bulge is None:
            return back
        d2 = (x - bulge[0]) ** 2 + (y - bulge[1]) ** 2
        return back - bulge[2] * math.exp(-d2 / 0.35)

    glDisable(GL_LIGHTING)
    glColor4f(0.92, 0.92, 0.95, 0.55)
    glLineWidth(1.0)
    step = 0.22
    nx = int(2 * hw / step) + 1
    ny = int(h / step) + 1
    xs = [-hw + i * (2 * hw) / (nx - 1) for i in range(nx)]
    ys = [j * h / (ny - 1) for j in range(ny)]
    for x in xs:                                   # back: verticals
        glBegin(GL_LINE_STRIP)
        for y in ys:
            glVertex3f(x, y, back_z(x, y))
        glEnd()
    for y in ys:                                   # back: horizontals
        glBegin(GL_LINE_STRIP)
        for x in xs:
            glVertex3f(x, y, back_z(x, y))
        glEnd()
    nz = int(C.GOAL_DEPTH / step) + 1
    zs = [z - k * (z - back) / (nz - 1) for k in range(nz)]
    glBegin(GL_LINES)
    for zz in zs:                                  # roof and sides
        glVertex3f(-hw, h, zz)
        glVertex3f(hw, h, zz)
        for s in (-1, 1):
            glVertex3f(s * hw, 0, zz)
            glVertex3f(s * hw, h, zz)
    for x in xs:
        glVertex3f(x, h, z)
        glVertex3f(x, h, back_z(x, h))
    for y in ys:
        for s in (-1, 1):
            glVertex3f(s * hw, y, z)
            glVertex3f(s * hw, y, back_z(s * hw, y))
    glEnd()
    glEnable(GL_LIGHTING)


# --------------------------------------------------------------------- players
def _limb(joint, rot_x, rot_z, length, width, colour, end_colour=None):
    glPushMatrix()
    glTranslatef(*joint)
    glRotatef(rot_z, 0, 0, 1)
    glRotatef(rot_x, 1, 0, 0)
    glColor3f(*colour)
    glTranslatef(0, -length / 2, 0)
    box(width, length, width)
    if end_colour:
        glColor3f(*end_colour)
        glTranslatef(0, -length / 2 - 0.05, 0)
        box(width * 1.15, 0.12, width * 1.6)
    glPopMatrix()


def draw_shadow(x, z, r, strength=0.35):
    glDisable(GL_LIGHTING)
    glDepthMask(GL_FALSE)
    glColor4f(0.0, 0.0, 0.0, strength)
    disc(x, z, r, 0.02, 20)
    glDepthMask(GL_TRUE)
    glEnable(GL_LIGHTING)


def draw_kicker(state, kit, clock):
    x, z = state['pos']
    draw_shadow(x, z, 0.45)
    swing = math.sin(state['run']) * 35.0 if state['run'] else 0.0
    kick = state['kick']
    mood = state['mood']
    jump = 0.0
    if mood == 'celebrate':
        jump = 0.25 * abs(math.sin(clock * 6.0))
    glPushMatrix()
    glTranslatef(x, jump, z)
    glRotatef(state['yaw'], 0, 1, 0)
    # Legs: the right leg winds back, then swings through the ball
    right = -swing
    if kick:
        right = (70.0 if kick < 0 else 85.0) * kick
    _limb((0.12, 0.92, 0), right, 0, 0.88, 0.17, SKIN, BOOT)
    _limb((-0.12, 0.92, 0), swing, 0, 0.88, 0.17, SKIN, BOOT)
    glColor3f(*kit['shorts'])
    glPushMatrix()
    glTranslatef(0, 0.88, 0)
    box(0.42, 0.3, 0.24)
    glPopMatrix()
    glColor3f(*kit['shirt'])
    glPushMatrix()
    glTranslatef(0, 1.3, 0)
    box(0.46, 0.6, 0.26)
    glPopMatrix()
    glColor3f(*SKIN)
    glPushMatrix()
    glTranslatef(0, 1.75, 0)
    sphere(0.13)
    glPopMatrix()
    if mood == 'celebrate':
        arm_l, arm_r, spread = 170.0, 170.0, 20.0
    elif mood == 'despair':
        arm_l, arm_r, spread = 150.0, 150.0, -35.0          # hands on head
    else:
        arm_l, arm_r, spread = -swing * 0.8, swing * 0.8, 12.0
    _limb((0.29, 1.55, 0), arm_r, -spread, 0.62, 0.12, kit['shirt'], SKIN)
    _limb((-0.29, 1.55, 0), arm_l, spread, 0.62, 0.12, kit['shirt'], SKIN)
    glPopMatrix()


def draw_keeper(pose, colour, clock):
    (x, y, z), lean, arms = pose
    draw_shadow(x, z, 0.5 if y < 1.2 else 0.35, 0.3)
    glPushMatrix()
    glTranslatef(x, y, z)
    glRotatef(-lean, 0, 0, 1)
    shorts = (0.1, 0.1, 0.12)
    # Torso and head
    glColor3f(*colour)
    glPushMatrix()
    glTranslatef(0, 0.25, 0)
    box(0.48, 0.62, 0.27)
    glPopMatrix()
    glColor3f(*shorts)
    glPushMatrix()
    glTranslatef(0, -0.12, 0)
    box(0.44, 0.26, 0.25)
    glPopMatrix()
    glColor3f(*SKIN)
    glPushMatrix()
    glTranslatef(0, 0.7, 0)
    sphere(0.13)
    glPopMatrix()
    # Legs
    if arms == 'block':
        leg = 18.0
    elif arms == 'dive':
        leg = 8.0
    else:
        leg = 10.0 + 4.0 * math.sin(clock * 6.4)
    _limb((0.12, -0.2, 0), 0, leg, 0.78, 0.17, colour, BOOT)
    _limb((-0.12, -0.2, 0), 0, -leg, 0.78, 0.17, colour, BOOT)
    # Arms (rotation about z: 180 = straight up)
    if arms in ('dive', 'up'):
        r_arm, l_arm = 172.0, -172.0
    elif arms == 'block':
        r_arm, l_arm = 115.0, -115.0
    elif arms == 'wave':
        w = 25.0 * math.sin(clock * 14.0)
        r_arm, l_arm = 150.0 + w, -150.0 - w
    else:
        r_arm, l_arm = 55.0, -55.0
    _limb((0.28, 0.5, 0), 0, r_arm, 0.62, 0.12, colour, GLOVE)
    _limb((-0.28, 0.5, 0), 0, l_arm, 0.62, 0.12, colour, GLOVE)
    glPopMatrix()


# Panel centres of a football (icosahedron vertices)
_PHI = (1 + 5 ** 0.5) / 2
_PANELS = []
for _a, _b in ((1, _PHI), (-1, _PHI), (1, -_PHI), (-1, -_PHI)):
    for _v in ((0, _a, _b), (_a, _b, 0), (_b, 0, _a)):
        _n = math.sqrt(sum(c * c for c in _v))
        _PANELS.append(tuple(c / _n for c in _v))


def draw_ball(pos, spin):
    axis, angle = spin
    x, y, z = pos
    draw_shadow(x, z, 0.13 + 0.05 * min(1.0, y), max(0.08, 0.4 - 0.1 * y))
    glPushMatrix()
    glTranslatef(x, y, z)
    glRotatef(angle, *axis)
    glColor3f(0.97, 0.97, 0.97)
    sphere(C.BALL_RADIUS, 18)
    glColor3f(0.08, 0.08, 0.1)
    r = C.BALL_RADIUS
    for p in _PANELS:
        glPushMatrix()
        glTranslatef(p[0] * r * 0.72, p[1] * r * 0.72, p[2] * r * 0.72)
        sphere(r * 0.33, 8)
        glPopMatrix()
    glPopMatrix()


def draw_reticle(aim, clock):
    glDisable(GL_LIGHTING)
    glDepthMask(GL_FALSE)
    x, y = aim
    z = C.GOAL_LINE_Z + 0.05
    pulse = 0.2 + 0.03 * math.sin(clock * 8.0)
    glLineWidth(3.0)
    glColor4f(1.0, 0.85, 0.1, 0.95)
    glBegin(GL_LINE_LOOP)
    for i in range(32):
        a = 2 * math.pi * i / 32
        glVertex3f(x + pulse * math.cos(a), y + pulse * math.sin(a), z)
    glEnd()
    glBegin(GL_LINES)
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        glVertex3f(x + dx * pulse * 0.4, y + dy * pulse * 0.4, z)
        glVertex3f(x + dx * pulse * 1.5, y + dy * pulse * 1.5, z)
    glEnd()
    glLineWidth(1.0)
    glDepthMask(GL_TRUE)
    glEnable(GL_LIGHTING)


def draw_scene(view, kits, aim=None, clock=0.0):
    set_lights()
    draw_static()
    draw_goal(view['net'], view['clock'])
    keeper_colour = kits[view['keeper_side']]['keeper']
    draw_keeper(view['keeper'], keeper_colour, view['clock'])
    draw_kicker(view['shooter'], kits[view['kicker']], view['clock'])
    draw_ball(view['ball'], view['spin'])
    if aim is not None:
        draw_reticle(aim, clock)
