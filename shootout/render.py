"""3D scene: stadium, pitch, goal, players, ball and the weather."""

import math
import random

from OpenGL.GL import *  # noqa: F401,F403
from OpenGL.GLU import *  # noqa: F401,F403
from OpenGL.GLUT import *  # noqa: F401,F403

from . import config as C

SKIN = (0.93, 0.76, 0.6)
GLOVE = (0.95, 0.95, 0.95)
BOOT = (0.08, 0.08, 0.08)
REF_KIT = dict(shirt=(0.08, 0.08, 0.1), shorts=(0.08, 0.08, 0.1))
AR_KIT = dict(shirt=(0.95, 0.85, 0.1), shorts=(0.08, 0.08, 0.1))
CROWD_SHIRTS = [(0.85, 0.12, 0.15), (0.15, 0.35, 0.9), (0.9, 0.9, 0.9),
                (0.95, 0.8, 0.1), (0.1, 0.1, 0.12), (0.8, 0.3, 0.1)]
FACES = [SKIN, (0.55, 0.38, 0.26), (0.36, 0.24, 0.16)]

# Sky, ambient and key light for day and night, then tints for the weather
SKIES = {'night': (0.03, 0.05, 0.11), 'day': (0.52, 0.72, 0.93)}
AMBIENT = {'night': 0.32, 'day': 0.48}
KEY_LIGHT = {'night': (0.85, 0.85, 0.8), 'day': (1.0, 0.96, 0.86)}
WEATHER_SKY = {'rain': 0.55, 'snow': 0.75, 'fog': 0.85, 'wind': 0.95, 'clear': 1.0}
FOG_RANGE = {'clear': (45.0, 140.0), 'wind': (45.0, 140.0), 'rain': (25.0, 100.0),
             'snow': (20.0, 90.0), 'fog': (6.0, 42.0)}

# The end behind the goal is split into column segments, each compiled twice
# (fans sitting and fans up), so the crowd can wave and jump cheaply
END_X = (-36.0, 36.0)
END_FRONT = C.GOAL_LINE_Z - 9.0
END_DEPTH = 14.0
END_ROWS = 12
SEGMENTS = 24

_quadric = None
_static = {}          # daytime -> display list
_end = {}             # end colour -> [(down list, up list), ...]
_particles = None
_torches = None
_shadow = (0.0, 0.0, 1.0)     # sun offset x, z and stretch for day shadows


def init_gl():
    global _quadric
    glEnable(GL_DEPTH_TEST)
    glEnable(GL_BLEND)
    glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
    glEnable(GL_LINE_SMOOTH)
    glEnable(GL_POINT_SMOOTH)
    glEnable(GL_NORMALIZE)
    glEnable(GL_LIGHTING)
    glEnable(GL_LIGHT0)
    glEnable(GL_LIGHT1)
    glEnable(GL_COLOR_MATERIAL)
    glColorMaterial(GL_FRONT_AND_BACK, GL_AMBIENT_AND_DIFFUSE)
    glShadeModel(GL_SMOOTH)
    glEnable(GL_FOG)
    glFogi(GL_FOG_MODE, GL_LINEAR)
    _quadric = gluNewQuadric()
    gluQuadricNormals(_quadric, GLU_SMOOTH)
    set_environment('night', 'clear')


def sky_colour(daytime, weather):
    base = SKIES[daytime]
    k = WEATHER_SKY.get(weather, 1.0)
    grey = 0.45 if daytime == 'day' else 0.08
    return tuple(c * k + grey * (1 - k) for c in base)


def set_environment(daytime, weather):
    """Clear colour, fog and lights for the time of day and the weather."""
    global _shadow
    sky = sky_colour(daytime, weather)
    glClearColor(sky[0], sky[1], sky[2], 1.0)
    glFogfv(GL_FOG_COLOR, (sky[0], sky[1], sky[2], 1.0))
    start, end = FOG_RANGE.get(weather, FOG_RANGE['clear'])
    glFogf(GL_FOG_START, start)
    glFogf(GL_FOG_END, end)
    dim = 0.75 if weather in ('rain', 'fog') and daytime == 'day' else 1.0
    a = AMBIENT[daytime] * dim
    glLightModelfv(GL_LIGHT_MODEL_AMBIENT, (a, a, a + 0.04, 1.0))
    key = KEY_LIGHT[daytime]
    glLightfv(GL_LIGHT0, GL_DIFFUSE, (key[0] * dim, key[1] * dim, key[2] * dim, 1.0))
    glLightfv(GL_LIGHT1, GL_DIFFUSE, (0.35, 0.37, 0.45, 1.0))
    # A low afternoon sun throws long shadows; floodlights keep them short
    _shadow = (0.9, 0.6, 2.2) if daytime == 'day' and weather in ('clear', 'wind') else (0.0, 0.0, 1.0)


def set_lights(daytime='night'):
    if daytime == 'day':
        glLightfv(GL_LIGHT0, GL_POSITION, (-0.6, 0.5, -0.4, 0.0))
    else:
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


def _fan(x, h, zc, facing, shirt, face, up):
    lift = 0.18 if up else 0.0
    glColor3f(*shirt)
    glPushMatrix()
    glTranslatef(x, h + 0.3 + lift, zc + facing * 0.1)
    box(0.38, 0.6, 0.3)
    if up:
        for s in (-1, 1):
            glPushMatrix()
            glTranslatef(s * 0.22, 0.5, 0)
            box(0.09, 0.45, 0.09)
            glPopMatrix()
    glTranslatef(0, 0.42, 0)
    glColor3f(*face)
    box(0.2, 0.2, 0.2)
    glPopMatrix()


def _steps(x1, x2, z_front, depth, rows, facing):
    step_d = depth / rows
    glColor3f(0.22, 0.24, 0.3)
    for r in range(rows):
        h = 1.0 + r * 0.65
        glPushMatrix()
        glTranslatef((x1 + x2) / 2, h / 2, z_front - facing * (r + 0.5) * step_d)
        box(x2 - x1, h, step_d)
        glPopMatrix()


def _crowd(x1, x2, z_front, depth, rows, facing, rng, colours, up=False):
    step_d = depth / rows
    for r in range(rows):
        h = 1.0 + r * 0.65
        zc = z_front - facing * (r + 0.5) * step_d
        x = x1 + 0.3
        while x < x2 - 0.3:
            if rng.random() < 0.85:
                _fan(x, h, zc, facing, colours(rng), rng.choice(FACES), up)
            x += 0.55 + rng.random() * 0.15


def _stand(x1, x2, z_front, depth, rows, facing, rng):
    """A tiered stand with a seated crowd."""
    _steps(x1, x2, z_front, depth, rows, facing)
    _crowd(x1, x2, z_front, depth, rows, facing, rng, lambda r: r.choice(CROWD_SHIRTS))


def _floodlight(x, z, lit):
    glColor3f(0.4, 0.42, 0.45)
    cylinder_between((x, 0, z), (x, 26, z), 0.35)
    glDisable(GL_LIGHTING)
    glColor3f(*((1.0, 0.98, 0.85) if lit else (0.55, 0.57, 0.6)))
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


def _build_static(daytime):
    rng = random.Random(11)
    _pitch()
    _ad_boards()
    # Steps behind the goal (its fans are drawn separately) and the side stands
    _steps(END_X[0], END_X[1], END_FRONT, END_DEPTH, END_ROWS, 1)
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
        _floodlight(x, z, daytime == 'night')


def _compile(build, *args):
    lst = glGenLists(1)
    glNewList(lst, GL_COMPILE)
    build(*args)
    glEndList()
    return lst


def draw_static(daytime='night'):
    if daytime not in _static:
        _static[daytime] = _compile(_build_static, daytime)
    glCallList(_static[daytime])


def _end_lists(colour):
    """The fans behind the goal, mostly in the colours of the team whose end it is."""
    key = tuple(round(c, 3) for c in colour)
    if key not in _end:
        def shirts(r):
            return colour if r.random() < 0.75 else r.choice(CROWD_SHIRTS)
        width = (END_X[1] - END_X[0]) / SEGMENTS
        segs = []
        for i in range(SEGMENTS):
            x1 = END_X[0] + i * width
            pair = []
            for up in (False, True):
                rng = random.Random(100 + i)      # same fans sitting and standing
                pair.append(_compile(_crowd, x1, x1 + width, END_FRONT, END_DEPTH, END_ROWS, 1, rng, shirts, up))
            segs.append(pair)
        _end[key] = segs
    return _end[key]


def segment_up(i, crowd, clock):
    """Whether segment i of the end crowd is on its feet."""
    if crowd == 'wave':                       # a Mexican wave rolling along the end
        return (clock * 9.0 - i) % SEGMENTS < 2.5
    if crowd == 'jeer':                       # bouncing to put the kicker off
        return math.sin(clock * 9.0 + i * 0.8) > 0.2
    if crowd == 'roar':
        return math.sin(clock * 12.0 + i * 1.3) > -0.3
    return math.sin(clock * 0.7 + i * 2.1) > 0.97


def draw_end_crowd(colour, crowd, clock):
    for i, (down, up) in enumerate(_end_lists(colour)):
        glCallList(up if segment_up(i, crowd, clock) else down)


def draw_flags(colour, clock, wind):
    """Flags waving along the front of the end behind the goal."""
    glDisable(GL_LIGHTING)
    strength = 1.0 + 0.6 * abs(wind)
    for k, x in enumerate((-26.0, -15.0, -5.0, 6.0, 17.0, 28.0)):
        base = (x, 3.2, END_FRONT - 1.5)
        glColor3f(0.85, 0.85, 0.85)
        glBegin(GL_LINES)
        glVertex3f(base[0], base[1] - 1.0, base[2])
        glVertex3f(base[0], base[1] + 2.4, base[2])
        glEnd()
        glBegin(GL_QUAD_STRIP)
        for j in range(9):
            u = j / 8.0
            sway = 0.25 * strength * u * math.sin(clock * 5.0 * strength - u * 4.0 + k)
            stripe = colour if (j // 3) % 2 == 0 else (0.95, 0.95, 0.95)
            glColor3f(*stripe)
            glVertex3f(base[0] + 1.6 * u, base[1] + 1.3, base[2] + sway)
            glVertex3f(base[0] + 1.6 * u, base[1] + 2.4, base[2] + sway)
        glEnd()
    glEnable(GL_LIGHTING)


def draw_tifo(colour):
    """A giant banner held up across the end before the shootout."""
    glDisable(GL_LIGHTING)
    step_d = END_DEPTH / END_ROWS
    bands = 8
    for b in range(bands):
        glColor3f(*(colour if b % 2 == 0 else (0.95, 0.95, 0.95)))
        r0, r1 = b * END_ROWS / bands, (b + 1) * END_ROWS / bands
        glBegin(GL_QUADS)
        for (r, x) in ((r0, END_X[0] + 6), (r0, END_X[1] - 6), (r1, END_X[1] - 6), (r1, END_X[0] + 6)):
            glVertex3f(x, 1.9 + r * 0.65, END_FRONT - r * step_d + 0.2)
        glEnd()
    glEnable(GL_LIGHTING)


def _torch_points():
    global _torches
    if _torches is None:
        rng = random.Random(7)
        pts = []
        for _ in range(260):
            r = rng.randrange(END_ROWS)
            pts.append((rng.uniform(*END_X), 2.0 + r * 0.65, END_FRONT - (r + 0.5) * END_DEPTH / END_ROWS,
                        rng.uniform(0, 6.28)))
        for _ in range(240):
            r = rng.randrange(10)
            pts.append((rng.uniform(-36, 36), 2.0 + r * 0.65, 30.0 + (r + 0.5) * 1.2, rng.uniform(0, 6.28)))
        _torches = pts
    return _torches


def draw_torches(clock, flares):
    """Phone torches twinkling in the dark, and a few flares in the home end."""
    glDisable(GL_LIGHTING)
    glDepthMask(GL_FALSE)
    glPointSize(3.0)
    glBegin(GL_POINTS)
    for x, y, z, ph in _torch_points():
        a = 0.5 + 0.5 * math.sin(clock * 3.0 + ph * 5.0)
        glColor4f(1.0, 1.0, 0.95, 0.35 + 0.65 * a)
        glVertex3f(x, y, z)
    glEnd()
    if flares:
        glPointSize(11.0)
        glBegin(GL_POINTS)
        for k, x in enumerate((-22.0, -9.0, 4.0, 19.0)):
            f = 0.75 + 0.25 * math.sin(clock * 23.0 + k * 1.7)
            glColor4f(1.0, 0.3 * f + 0.1, 0.05, 0.9)
            glVertex3f(x, 4.5 + k % 2 * 1.3, END_FRONT - 4.0 - k)
        glEnd()
    glPointSize(1.0)
    glDepthMask(GL_TRUE)
    glEnable(GL_LIGHTING)


def _particle_field():
    global _particles
    if _particles is None:
        rng = random.Random(5)
        _particles = [(rng.uniform(-22, 22), rng.uniform(-28, 12), rng.uniform(0, 14), rng.uniform(0, 6.28))
                      for _ in range(900)]
    return _particles


def draw_weather(weather, clock, wind):
    """Rain streaks or falling snow around the penalty area."""
    if weather not in ('rain', 'snow'):
        return
    glDisable(GL_LIGHTING)
    glDepthMask(GL_FALSE)
    if weather == 'rain':
        glColor4f(0.75, 0.8, 0.9, 0.45)
        glBegin(GL_LINES)
        for x, z, h, ph in _particle_field():
            y = (h - clock * 16.0) % 14.0
            glVertex3f(x, y, z)
            glVertex3f(x - 0.04, y + 0.45, z + 0.06)
        glEnd()
    else:
        glPointSize(3.0)
        glColor4f(1.0, 1.0, 1.0, 0.9)
        glBegin(GL_POINTS)
        for x, z, h, ph in _particle_field()[:600]:
            y = (h - clock * 1.3) % 14.0
            glVertex3f(x + 0.4 * math.sin(clock * 0.9 + ph) + wind * 0.05 * y, y, z + 0.3 * math.cos(clock * 0.7 + ph))
        glEnd()
        glPointSize(1.0)
    glDepthMask(GL_TRUE)
    glEnable(GL_LIGHTING)


def draw_ground_cover(weather):
    """A dusting of snow, or the sheen of a soaked pitch."""
    if weather not in ('rain', 'snow'):
        return
    glDisable(GL_LIGHTING)
    glDepthMask(GL_FALSE)
    glColor4f(*((0.95, 0.96, 1.0, 0.45) if weather == 'snow' else (0.15, 0.2, 0.3, 0.22)))
    glBegin(GL_QUADS)
    flat_quad(-48.0, -40.0, 48.0, 40.0, 0.015)
    glEnd()
    glDepthMask(GL_TRUE)
    glEnable(GL_LIGHTING)


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


def draw_shadow(x, z, r, strength=0.35, height=1.8):
    """A soft disc under a player or the ball; stretched away from a low sun."""
    ox, oz, stretch = _shadow
    glDisable(GL_LIGHTING)
    glDepthMask(GL_FALSE)
    glColor4f(0.0, 0.0, 0.0, strength)
    glPushMatrix()
    if stretch > 1.0:
        glTranslatef(x + ox * height * 0.5, 0, z + oz * height * 0.5)
        glRotatef(math.degrees(math.atan2(-oz, ox)), 0, 1, 0)
        glScalef(1.0 + (stretch - 1.0) * height / 1.8, 1, 1)
        disc(0.0, 0.0, r, 0.02, 20)
    else:
        disc(x, z, r, 0.02, 20)
    glPopMatrix()
    glDepthMask(GL_TRUE)
    glEnable(GL_LIGHTING)


def _figure(x, z, yaw, kit, arms=(12.0, 12.0, 0.0, 0.0), legs=(0.0, 0.0), jump=0.0, hips=0.0,
            pitch=0.0, height=0.0, face=SKIN):
    """A standing outfield figure. arms: right and left spread about z, right
    and left swing about x."""
    glPushMatrix()
    glTranslatef(x, jump + height, z)
    glRotatef(yaw, 0, 1, 0)
    glRotatef(pitch, 1, 0, 0)
    _limb((0.12, 0.92, 0), legs[0], 0, 0.88, 0.17, SKIN, BOOT)
    _limb((-0.12, 0.92, 0), legs[1], 0, 0.88, 0.17, SKIN, BOOT)
    glColor3f(*kit['shorts'])
    glPushMatrix()
    glTranslatef(0, 0.88, 0)
    box(0.42, 0.3, 0.24)
    glPopMatrix()
    glRotatef(hips, 0, 1, 0)            # the upper body opens up towards the target
    glColor3f(*kit['shirt'])
    glPushMatrix()
    glTranslatef(0, 1.3, 0)
    box(0.46, 0.6, 0.26)
    glPopMatrix()
    glColor3f(*face)
    glPushMatrix()
    glTranslatef(0, 1.75, 0)
    sphere(0.13)
    glPopMatrix()
    spread_r, spread_l, swing_r, swing_l = arms
    _limb((0.29, 1.55, 0), swing_r, spread_r, 0.62, 0.12, kit['shirt'], SKIN)
    _limb((-0.29, 1.55, 0), swing_l, -spread_l, 0.62, 0.12, kit['shirt'], SKIN)
    glPopMatrix()


def draw_kicker(state, kit, clock):
    x, z = state['pos']
    swing = math.sin(state['run']) * 35.0 if state['run'] else 0.0
    kick = state['kick']
    mood = state['mood'] or ''
    right = -swing
    if kick:
        right = (70.0 if kick < 0 else 85.0) * kick
    legs = (right, swing)
    arms = (12.0, 12.0, swing * 0.8, -swing * 0.8)
    yaw, jump, pitch, height = state['yaw'], 0.0, 0.0, 0.0
    if mood == 'slip':
        # Plant foot goes from under him: falls back on his backside
        pitch, height = -55.0, -0.55
        legs = (-80.0, -60.0)
        arms = (60.0, 60.0, -30.0, -30.0)
    elif mood.startswith('celebrate'):
        style = mood.split(':', 1)[1] if ':' in mood else 'knee slide'
        yaw = 180.0                                 # turns to face the fans
        if style == 'knee slide':
            pitch, height = -20.0, -0.45
            legs = (-95.0, -95.0)
            arms = (100.0, 100.0, 0.0, 0.0)
        elif style == 'aeroplane':
            yaw += 25.0 * math.sin(clock * 3.0)
            arms = (90.0, 90.0, 0.0, 0.0)
            legs = (30.0 * math.sin(clock * 10.0), -30.0 * math.sin(clock * 10.0))
            pitch = 8.0 * math.sin(clock * 3.0)
        elif style == 'shush':
            arms = (20.0, 12.0, 150.0, 0.0)         # finger to the lips
        else:                                       # badge kiss
            arms = (20.0, 30.0, 120.0, 40.0)
            jump = 0.15 * abs(math.sin(clock * 5.0))
    elif mood == 'despair':
        arms = (200.0, 200.0, 0.0, 0.0)             # hands on head
        pitch = 12.0
    draw_shadow(x, z, 0.45)
    _figure(x, z, yaw, kit, arms, legs, jump, state.get('hips', 0.0), pitch, height)


def draw_keeper(pose, colour, clock, mood=None, first_person=False):
    (x, y, z), lean, arms = pose
    if mood == 'dance':
        # Back on his feet, swaying and wagging the arms at the crowd
        y = 0.95 + 0.08 * abs(math.sin(clock * 7.0))
        lean = 14.0 * math.sin(clock * 5.0)
        arms = 'wave'
    if first_person:
        _first_person_gloves(x, y, z, arms, clock)
        return
    draw_shadow(x, z, 0.5 if y < 1.2 else 0.35, 0.3)
    glPushMatrix()
    glTranslatef(x, y, z)
    glRotatef(-lean, 0, 0, 1)
    shorts = (0.1, 0.1, 0.12)
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


def _first_person_gloves(x, y, z, arms, clock):
    """Keeper's-eye view: just the gloves, held up in front of the face."""
    spread = 0.3 if arms == 'ready' else 0.45
    lift = 0.5 + (0.1 * math.sin(clock * 14.0) if arms == 'wave' else 0.0)
    glColor3f(*GLOVE)
    for s in (-1, 1):
        glPushMatrix()
        glTranslatef(x + s * spread, y + lift, z + 0.75)
        box(0.11, 0.14, 0.04)
        glColor3f(0.2, 0.2, 0.25)
        glTranslatef(0, -0.09, 0)
        box(0.1, 0.04, 0.05)
        glColor3f(*GLOVE)
        glPopMatrix()


def draw_officials(card, clock):
    """Referee by the area with the whistle and any card, and an assistant on the goal line."""
    rx, rz = 3.2, C.SPOT_Z - 3.0
    yaw = math.degrees(math.atan2(-rx, C.SPOT_Z + 2.0 - rz))
    arms = (12.0, 12.0, 0.0, 0.0)
    if card:
        arms = (175.0, 12.0, 0.0, 0.0)
    draw_shadow(rx, rz, 0.42)
    _figure(rx, rz, yaw, REF_KIT, arms)
    if card:
        glDisable(GL_LIGHTING)
        glColor3f(*((0.95, 0.85, 0.1) if card == 'yellow' else (0.9, 0.1, 0.1)))
        glPushMatrix()
        glTranslatef(rx + 0.3, 2.45, rz)
        glRotatef(yaw, 0, 1, 0)
        box(0.12, 0.17, 0.01)
        glPopMatrix()
        glEnable(GL_LIGHTING)
    ax, az = C.GOAL_AREA_HALF_WIDTH, C.GOAL_LINE_Z + 0.3
    draw_shadow(ax, az, 0.42)
    _figure(ax, az, -90.0, AR_KIT, (12.0, 12.0, 20.0 * math.sin(clock * 0.8), 0.0))


TEAMMATE_Z = C.SPOT_Z + 26.0     # the group arm in arm in the centre circle


def draw_teammates(colours, team_mood, kicker, clock, kits):
    """Both squads on the halfway line, reacting to every kick."""
    for side, x0 in (('p1', -2.0), ('p2', 2.0)):
        kit = kits.get(side) or dict(shirt=colours[side], shorts=(0.95, 0.95, 0.95))
        happy = None
        if team_mood is not None:
            k, scored = team_mood
            happy = scored if side == k else not scored
        for i in range(5):
            if side == kicker and i == 0:
                continue                         # the kicker has left the group
            x = x0 + (i if side == 'p2' else -i) * 0.62
            jump = 0.0
            arms = (35.0, 35.0, 0.0, 0.0)        # arms round each other
            pitch = 0.0
            if happy:
                jump = 0.35 * abs(math.sin(clock * 7.0 + i))
                arms = (165.0, 165.0, 0.0, 0.0)
            elif happy is False:
                pitch = 25.0                     # heads down
                arms = (200.0, 200.0, 0.0, 0.0) if i % 2 else (12.0, 12.0, 0.0, 0.0)
            _figure(x, TEAMMATE_Z, 180.0, kit, arms, jump=jump, pitch=pitch)


def draw_waiting_keeper(colour):
    """The kicking side's keeper waits where the goal line meets the penalty area line."""
    x, z = -C.PENALTY_AREA_HALF_WIDTH, C.GOAL_LINE_Z + 0.4
    kit = dict(shirt=colour, shorts=(0.1, 0.1, 0.12))
    draw_shadow(x, z, 0.42)
    _figure(x, z, 90.0, kit, (40.0, 40.0, 0.0, 0.0))


# Panel centres of a football (icosahedron vertices)
_PHI = (1 + 5 ** 0.5) / 2
_PANELS = []
for _a, _b in ((1, _PHI), (-1, _PHI), (1, -_PHI), (-1, -_PHI)):
    for _v in ((0, _a, _b), (_a, _b, 0), (_b, 0, _a)):
        _n = math.sqrt(sum(c * c for c in _v))
        _PANELS.append(tuple(c / _n for c in _v))


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


def draw_ball(pos, spin, orange=False):
    axis, angle = spin
    x, y, z = pos
    draw_shadow(x, z, 0.13 + 0.05 * min(1.0, y), max(0.08, 0.4 - 0.1 * y), 0.2 + y)
    glPushMatrix()
    glTranslatef(x, y, z)
    glRotatef(angle, *axis)
    glColor3f(*((1.0, 0.45, 0.05) if orange else (0.97, 0.97, 0.97)))   # orange ball in the snow
    sphere(C.BALL_RADIUS, 18)
    glColor3f(0.08, 0.08, 0.1)
    r = C.BALL_RADIUS
    for p in _PANELS:
        glPushMatrix()
        glTranslatef(p[0] * r * 0.72, p[1] * r * 0.72, p[2] * r * 0.72)
        sphere(r * 0.33, 8)
        glPopMatrix()
    glPopMatrix()


def draw_preview(preview):
    """Training: dotted path of the shot as aimed, and a ring for how far it may stray."""
    pts = preview['points']
    if not pts:
        return
    glDisable(GL_LIGHTING)
    glDepthMask(GL_FALSE)
    glPointSize(5.0)
    glColor4f(0.3, 0.9, 1.0, 0.85)
    glBegin(GL_POINTS)
    for p in pts:
        glVertex3f(*p)
    glEnd()
    glPointSize(1.0)
    end = pts[-1]
    for p in pts:
        if p[2] <= C.GOAL_LINE_Z:
            end = p
            break
    r = preview['sigma']
    glLineWidth(2.0)
    glColor4f(0.3, 0.9, 1.0, 0.6)
    glBegin(GL_LINE_LOOP)
    for i in range(32):
        a = 2 * math.pi * i / 32
        glVertex3f(end[0] + r * math.cos(a), max(0.02, end[1] + r * 0.7 * math.sin(a)), C.GOAL_LINE_Z + 0.06)
    glEnd()
    glLineWidth(1.0)
    glDepthMask(GL_TRUE)
    glEnable(GL_LIGHTING)


ENV_DEFAULTS = dict(weather='clear', daytime='night', end_colour=(0.85, 0.12, 0.15), crowd='calm',
                    tension=False, flares=False, tifo=False, wind=0.0, preview=None,
                    first_person=False, kits=None, officials=True)


def draw_scene(view, aim=None, clock=0.0, env=None):
    env = dict(ENV_DEFAULTS, **(env or {}))
    weather, daytime = env['weather'], env['daytime']
    set_environment(daytime, weather)
    set_lights(daytime)
    draw_static(daytime)
    draw_end_crowd(env['end_colour'], env['crowd'], view['clock'])
    draw_flags(env['end_colour'], view['clock'], env['wind'])
    if env['tifo']:
        draw_tifo(env['end_colour'])
    if daytime == 'night' and (env['tension'] or env['flares']):
        draw_torches(view['clock'], env['flares'])
    draw_ground_cover(weather)
    draw_goal(view['net'], view['clock'])
    kits = env['kits'] or {}
    draw_teammates(view['team_colours'], view.get('team_mood'), view['kicker'], view['clock'], kits)
    if kits.get(view['kicker']):
        draw_waiting_keeper(kits[view['kicker']].get('keeper', (0.2, 0.2, 0.25)))
    if env['officials']:
        card = view.get('card')
        draw_officials(card[0] if card else None, view['clock'])
    draw_keeper(view['keeper'], view['keeper_colour'], view['clock'], view.get('keeper_mood'),
                env['first_person'])
    draw_kicker(view['shooter'], view['kicker_kit'], view['clock'])
    draw_ball(view['ball'], view['spin'], orange=weather == 'snow')
    if env['preview']:
        draw_preview(env['preview'])
    if aim is not None:
        draw_reticle(aim, clock)
    draw_weather(weather, view['clock'], env['wind'])
