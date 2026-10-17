"""3D scene: stadium, pitch, goal, players, ball and the weather."""

import math
import random

from OpenGL.GL import *  # noqa: F401,F403
from OpenGL.GLU import *  # noqa: F401,F403
from OpenGL.GLUT import *  # noqa: F401,F403

from . import characters as CH, config as C

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
_static = {}          # (daytime, variant) -> display list
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
    if C.VARIANT == 'park':
        _park_ground()
        return
    if C.VARIANT in ('futsal', 'beach'):
        _court(C.VARIANT)
        return
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


def _park_ground():
    """Jumpers for goalposts: no lines, a worn patch in the goalmouth and on the spot."""
    glColor3f(0.42, 0.36, 0.22)
    disc(0.0, C.GOAL_LINE_Z + 0.6, 1.6, 0.012, 28)
    disc(0.0, C.SPOT_Z, 0.5, 0.013, 20)
    glColor3f(0.3, 0.25, 0.16)
    disc(0.0, C.SPOT_Z, 0.14, 0.014)


def _court(kind):
    """Futsal: a painted indoor court. Beach: raked sand with rope lines."""
    if kind == 'futsal':
        glColor3f(0.12, 0.32, 0.6)
        glBegin(GL_QUADS)
        flat_quad(-20.0, C.GOAL_LINE_Z - 8.0, 20.0, 30.0, 0.008)
        glEnd()
        glColor3f(0.85, 0.45, 0.15)
        glBegin(GL_QUADS)
        flat_quad(-10.0, C.GOAL_LINE_Z, 10.0, C.GOAL_LINE_Z + 6.0, 0.009)
        glEnd()
        line_col = (0.95, 0.95, 0.95)
    else:
        rng = random.Random(3)
        glBegin(GL_QUADS)
        for k in range(40):
            z = C.GOAL_LINE_Z - 8.0 + k * 1.0
            shade = 0.03 * rng.random()
            glColor3f(0.87 - shade, 0.77 - shade, 0.55 - shade)
            flat_quad(-24.0, z, 24.0, z + 1.0, 0.008)
        glEnd()
        line_col = (0.1, 0.25, 0.7)
    glColor3f(*line_col)
    line = C.GOAL_LINE_Z
    _line_strip_quads([(-18.0, line), (18.0, line)], 0.1, 0.013)
    # The area is a quarter-circle each side of the goal in futsal
    pts = []
    for k in range(33):
        a = math.pi * k / 32
        pts.append((-math.cos(a) * 6.0, line + math.sin(a) * 6.0))
    _line_strip_quads(pts, 0.1, 0.013)
    disc(0.0, C.SPOT_Z, 0.12, 0.015)


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
    key = (daytime, C.VARIANT)
    if key not in _static:
        _static[key] = _compile(_build_static, daytime)
    glCallList(_static[key])


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
def draw_jumpers():
    """Two piles of clothes for posts, and a bag for good measure."""
    for s, col in ((-1, (0.75, 0.1, 0.12)), (1, (0.15, 0.3, 0.75))):
        x = s * (C.GOAL_HALF_WIDTH + 0.15)
        glColor3f(*col)
        glPushMatrix()
        glTranslatef(x, 0.08, C.GOAL_LINE_Z)
        glRotatef(25 * s, 0, 1, 0)
        box(0.5, 0.16, 0.4)
        glColor3f(0.2, 0.2, 0.22)
        glTranslatef(0.05, 0.12, 0.02)
        box(0.38, 0.1, 0.3)
        glPopMatrix()
    glColor3f(0.1, 0.1, 0.1)
    glPushMatrix()
    glTranslatef(C.GOAL_HALF_WIDTH + 1.4, 0.15, C.GOAL_LINE_Z - 0.8)
    box(0.55, 0.3, 0.3)
    glPopMatrix()


def draw_goal(net_hit, clock):
    if not C.HAS_BAR:
        draw_jumpers()
        return
    hw = C.GOAL_HALF_WIDTH + C.POST_RADIUS
    h = C.GOAL_HEIGHT + C.POST_RADIUS
    z = C.GOAL_LINE_Z - C.POST_RADIUS
    back = C.GOAL_LINE_Z - C.GOAL_DEPTH
    glColor3f(0.97, 0.97, 0.97)
    pr = C.POST_RADIUS
    cylinder_between((-hw, 0, z), (-hw, h + pr, z), pr)
    cylinder_between((hw, 0, z), (hw, h + pr, z), pr)
    cylinder_between((-hw - pr, h, z), (hw + pr, h, z), pr)
    if not C.HAS_NET:
        return
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


FACE_DARK = (0.12, 0.07, 0.06)
BASE_LAYER = (0.1, 0.1, 0.12)
DEFAULT_LOOK = dict(skin=0, hair='short', hc='black', beard=None, h=1.0, w=1.0)


def _cols(lk):
    if not lk:
        return dict(skin=SKIN, hair=(0.12, 0.08, 0.05), boots=BOOT)
    return CH.look_colours(lk)


def _luma(c):
    return 0.3 * c[0] + 0.59 * c[1] + 0.11 * c[2]


def _stroke(s, height, y, cx=0.0, max_width=None, width=2.5):
    """Stroke text in the local x-y plane, centred on cx, reading along +x."""
    units = sum(glutStrokeWidth(GLUT_STROKE_ROMAN, ord(ch)) for ch in s) or 1
    scale = height / 119.05
    if max_width and units * scale > max_width:
        scale = max_width / units
    glPushMatrix()
    glTranslatef(cx - units * scale / 2.0, y, 0.0)
    glScalef(scale, scale, scale)
    glLineWidth(width)
    for ch in s:
        glutStrokeCharacter(GLUT_STROKE_ROMAN, ord(ch))
    glPopMatrix()
    glLineWidth(1.0)


def _shirt_text(name, number, shirt, z, flip=False, number_y=1.18, name_y=1.48, small=False):
    """Name and number on a shirt face at depth z (flip for the other face)."""
    col = (0.06, 0.06, 0.08) if _luma(shirt) > 0.55 else (0.97, 0.97, 0.97)
    glDisable(GL_LIGHTING)
    glColor3f(*col)
    glPushMatrix()
    if flip:
        glRotatef(180.0, 0, 1, 0)
    glTranslatef(0.0, 0.0, z)
    if small:
        _stroke(str(number), 0.09, number_y, cx=0.1, width=2.0)
    else:
        _stroke(str(number), 0.21, number_y, width=3.0)
        if name:
            _stroke(name, 0.06, name_y, max_width=0.4, width=2.0)
    glPopMatrix()
    glEnable(GL_LIGHTING)


def _face(mood):
    """Eyes, brows and mouth on the front (-z) of a head of radius 0.13."""
    glColor3f(*FACE_DARK)
    eye_h = {'nervous': 0.03, 'grin': 0.012, 'gutted': 0.016, 'calm': 0.006, 'shout': 0.026}.get(mood, 0.022)
    for sx in (-1, 1):
        glPushMatrix()
        glTranslatef(0.045 * sx, 0.02, -0.124)
        box(0.028, eye_h, 0.012)
        glPopMatrix()
        # Brows: angled for the mood
        tilt = {'focused': 14, 'nervous': -16, 'gutted': -22, 'grin': 0, 'calm': 0, 'shout': 18}.get(mood, 10)
        glPushMatrix()
        glTranslatef(0.045 * sx, 0.062 + (0.01 if mood in ('nervous', 'grin') else 0.0), -0.113)
        glRotatef(tilt * sx, 0, 0, 1)
        box(0.045, 0.011, 0.014)
        glPopMatrix()
    glPushMatrix()
    glTranslatef(0.0, -0.055, -0.122)
    if mood == 'grin':
        box(0.075, 0.026, 0.012)
        glColor3f(0.97, 0.97, 0.95)
        glTranslatef(0.0, 0.006, -0.004)
        box(0.062, 0.01, 0.008)
    elif mood == 'shout':
        box(0.05, 0.045, 0.014)
    elif mood == 'nervous':
        box(0.026, 0.02, 0.012)
    elif mood == 'gutted':
        for sx in (-1, 1):
            glPushMatrix()
            glTranslatef(0.018 * sx, 0.0, 0.0)
            glRotatef(-24 * sx, 0, 0, 1)
            box(0.04, 0.01, 0.012)
            glPopMatrix()
    else:
        box(0.05, 0.01, 0.012)
    glPopMatrix()


def _hair(style, colour):
    glColor3f(*colour)

    def at(x, y, z, sx, sy, sz, rx=0.0):
        glPushMatrix()
        glTranslatef(x, y, z)
        if rx:
            glRotatef(rx, 1, 0, 0)
        box(sx, sy, sz)
        glPopMatrix()

    def ball(x, y, z, r):
        glPushMatrix()
        glTranslatef(x, y, z)
        sphere(r, 10)
        glPopMatrix()

    if style in ('bald', 'r9'):
        if style == 'r9':
            at(0.0, 0.125, -0.06, 0.07, 0.03, 0.06)          # the 2002 tuft
        return
    if style == 'afro':
        ball(0.0, 0.06, 0.05, 0.17)
        return
    if style == 'mohawk':
        at(0.0, 0.15, 0.01, 0.05, 0.11, 0.25)
        return
    top_h = 0.04 if style == 'buzz' else 0.07
    at(0.0, 0.1 + (0.01 if style == 'buzz' else 0.0), 0.01, 0.25, top_h, 0.25)
    at(0.0, 0.03, 0.095, 0.24, 0.14 if style != 'buzz' else 0.1, 0.07)
    if style == 'quiff':
        at(0.0, 0.16, -0.07, 0.17, 0.08, 0.1, rx=-20.0)
    elif style == 'long':
        at(0.0, -0.08, 0.1, 0.26, 0.32, 0.08)
        for sx in (-1, 1):
            at(0.13 * sx, -0.03, 0.03, 0.035, 0.22, 0.16)
    elif style == 'ponytail':
        at(0.0, -0.02, 0.17, 0.06, 0.24, 0.06, rx=22.0)
    elif style == 'bun':
        ball(0.0, 0.12, 0.1, 0.06)
    elif style == 'manbun':
        ball(0.0, 0.1, 0.14, 0.05)
    elif style == 'curly':
        for x, y, z in ((-0.08, 0.13, -0.04), (0.0, 0.15, -0.05), (0.08, 0.13, -0.04), (-0.08, 0.13, 0.06),
                        (0.08, 0.13, 0.06), (0.0, 0.15, 0.05)):
            ball(x, y, z, 0.05)
    elif style == 'braids':
        for i in range(5):
            at(-0.1 + 0.05 * i, -0.1, 0.11, 0.03, 0.3, 0.03)


def _head(lk, cols, mood='focused', cap=False):
    """A head at the current origin, facing -z: face, hair, beard, extras."""
    glColor3f(*cols['skin'])
    sphere(0.13)
    _face(mood or 'focused')
    lk = lk or {}
    if cap:
        glColor3f(0.12, 0.12, 0.16)
        glPushMatrix()
        glTranslatef(0.0, 0.1, 0.0)
        box(0.27, 0.08, 0.27)
        glTranslatef(0.0, -0.02, -0.17)
        box(0.2, 0.015, 0.12)
        glPopMatrix()
    else:
        _hair(lk.get('hair', 'short'), cols['hair'])
    beard = lk.get('beard')
    if beard:
        if beard == 'stubble':
            glColor3f(*[0.5 * a + 0.5 * b for a, b in zip(cols['skin'], cols['hair'])])
        else:
            glColor3f(*cols['hair'])
        glPushMatrix()
        if beard == 'goatee':
            glTranslatef(0.0, -0.1, -0.1)
            box(0.06, 0.06, 0.05)
        else:
            glTranslatef(0.0, -0.075, -0.075)
            box(0.21, 0.09 if beard == 'full' else 0.06, 0.1)
        glPopMatrix()
    if lk.get('headband') and not cap:
        glColor3f(0.95, 0.95, 0.95)
        glPushMatrix()
        glTranslatef(0.0, 0.075, 0.0)
        box(0.275, 0.03, 0.275)
        glPopMatrix()
    if lk.get('glasses'):
        glColor3f(0.05, 0.05, 0.05)
        glPushMatrix()
        glTranslatef(0.0, 0.02, -0.13)
        box(0.14, 0.012, 0.01)
        for sx in (-1, 1):
            glPushMatrix()
            glTranslatef(0.045 * sx, 0.0, 0.0)
            box(0.045, 0.035, 0.008)
            glPopMatrix()
        glPopMatrix()


def _prop(kind, clock, kit):
    """Something in the hand at the current origin (the end of the arm)."""
    if kind == 'cup':
        glColor3f(0.97, 0.97, 0.97)
        box(0.07, 0.08, 0.07)
    elif kind == 'phone':
        glColor3f(0.05, 0.05, 0.06)
        box(0.08, 0.14, 0.015)
    elif kind == 'orb':
        glDisable(GL_LIGHTING)
        glColor4f(0.5, 1.0, 0.7, 0.85)
        sphere(0.09, 10)
        glEnable(GL_LIGHTING)
    elif kind == 'shirt':
        glRotatef(clock * 700.0 % 360.0, 0, 1, 0)
        glColor3f(*kit['shirt'])
        glTranslatef(0.16, 0.0, 0.0)
        box(0.3, 0.26, 0.02)
    elif kind == 'fingers':
        glColor3f(0.9, 0.9, 0.9)
        glTranslatef(0.0, -0.08, 0.0)
        box(0.05, 0.12, 0.03)


def _arm(joint, swing, spread, length, width, colour, hand, prop=None, clock=0.0, kit=None):
    glPushMatrix()
    glTranslatef(*joint)
    glRotatef(spread, 0, 0, 1)
    glRotatef(swing, 1, 0, 0)
    glColor3f(*colour)
    glTranslatef(0, -length / 2, 0)
    box(width, length, width)
    glColor3f(*hand)
    glTranslatef(0, -length / 2 - 0.05, 0)
    box(width * 1.15, 0.12, width * 1.6)
    if prop:
        _prop(prop, clock, kit)
    glPopMatrix()


def _leg(joint, swing, spread, cols, sock, socks_down, trousers=None):
    glPushMatrix()
    glTranslatef(*joint)
    glRotatef(spread, 0, 0, 1)
    glRotatef(swing, 1, 0, 0)
    if trousers:
        glColor3f(*trousers)
        glTranslatef(0, -0.44, 0)
        box(0.18, 0.88, 0.18)
        glTranslatef(0, 0.44, 0)
    else:
        glColor3f(*cols['skin'])
        glTranslatef(0, -0.22, 0)
        box(0.17, 0.44, 0.17)
        glColor3f(*sock)
        sock_len = 0.14 if socks_down else 0.4
        glTranslatef(0, -0.22 - sock_len / 2, 0)
        box(0.18, sock_len, 0.18)
        if socks_down:
            glColor3f(*cols['skin'])
            glTranslatef(0, sock_len / 2 + 0.13, 0)
            box(0.17, 0.26, 0.17)
            glTranslatef(0, -0.13 - sock_len / 2, 0)
        glTranslatef(0, 0.22 + sock_len / 2, 0)
    glColor3f(*cols['boots'])
    glTranslatef(0, -0.88 - 0.05, 0)
    box(0.17 * 1.15, 0.12, 0.17 * 1.6)
    glPopMatrix()


def _figure(x, z, yaw, kit, arms=(12.0, 12.0, 0.0, 0.0), legs=(0.0, 0.0), jump=0.0, hips=0.0,
            pitch=0.0, height=0.0, face=None, head=0.0, bend=0.0, fig=None, mood='focused', spread=0.0,
            roll=0.0, head_pitch=0.0, torso=None, props=None, clock=0.0, pivot=0.0, collar=False):
    """A standing outfield figure. arms: right and left spread about z, right
    and left swing about x. fig: a character's look, name and number."""
    fig = fig or {}
    lk = fig.get('look') or {}
    cols = _cols(lk)
    if face is not None and not lk:
        cols['skin'] = face
    props = props or {}
    glPushMatrix()
    glTranslatef(x, jump + height, z)
    glRotatef(yaw, 0, 1, 0)
    if pivot:
        glTranslatef(0, pivot, 0)
    glRotatef(pitch, 1, 0, 0)
    glRotatef(roll, 0, 0, 1)
    if pivot:
        glTranslatef(0, -pivot, 0)
    h, w = lk.get('h', 1.0), lk.get('w', 1.0)
    if h != 1.0 or w != 1.0:
        glScalef(w, h, w)
    sock = kit.get('socks', kit['shorts'])
    trousers = lk.get('trousers')
    _leg((0.12, 0.92, 0), legs[0], spread, cols, sock, lk.get('socks') == 'down', trousers)
    _leg((-0.12, 0.92, 0), legs[1], -spread, cols, sock, lk.get('socks') == 'down', trousers)
    glColor3f(*kit['shorts'])
    glPushMatrix()
    glTranslatef(0, 0.88, 0)
    box(0.42, 0.3, 0.24)
    glPopMatrix()
    glRotatef(hips, 0, 1, 0)            # the upper body opens up towards the target
    if bend:
        glTranslatef(0, 1.03, 0)        # bend at the waist (placing the ball)
        glRotatef(-bend, 1, 0, 0)
        glTranslatef(0, -1.03, 0)
    shirt = torso or kit['shirt']
    glColor3f(*shirt)
    glPushMatrix()
    glTranslatef(0, 1.3, 0)
    box(0.46, 0.6, 0.26)
    glPopMatrix()
    if collar or lk.get('collar'):
        glColor3f(*kit['shirt'])
        for sx in (-1, 1):
            glPushMatrix()
            glTranslatef(0.08 * sx, 1.63, 0.0)
            box(0.1, 0.09, 0.2)
            glPopMatrix()
    if fig.get('number') is not None and torso is None:
        _shirt_text(fig.get('name'), fig['number'], kit['shirt'], 0.135)
        _shirt_text(None, fig['number'], kit['shirt'], 0.135, flip=True, number_y=1.42, small=True)
    glPushMatrix()
    glTranslatef(0, 1.75, 0)
    glRotatef(head, 0, 1, 0)            # where he is looking
    glRotatef(head_pitch, 1, 0, 0)
    _head(lk if lk else dict(DEFAULT_LOOK), cols, mood)
    glPopMatrix()
    spread_r, spread_l, swing_r, swing_l = arms
    sleeve = cols['skin'] if torso else kit['shirt']
    _arm((0.29, 1.55, 0), swing_r, spread_r, 0.62, 0.12, sleeve, cols['skin'], props.get('r'), clock, kit)
    _arm((-0.29, 1.55, 0), swing_l, -spread_l, 0.62, 0.12, sleeve, cols['skin'], props.get('l'), clock, kit)
    if lk.get('armband'):
        glColor3f(0.95, 0.75, 0.15)
        glPushMatrix()
        glTranslatef(-0.29, 1.55, 0)
        glRotatef(-spread_l, 0, 0, 1)
        glRotatef(swing_l, 1, 0, 0)
        glTranslatef(0, -0.18, 0)
        box(0.14, 0.07, 0.14)
        glPopMatrix()
    glPopMatrix()


def draw_aura(x, z, aura, glow, clock, height=1.9):
    """Aura: a glowing ring on the grass and sparks rising round the player."""
    if not aura or aura < 0.3:
        return
    r, g, b = glow or (1.0, 0.82, 0.3)
    glDisable(GL_LIGHTING)
    glDepthMask(GL_FALSE)
    glBlendFunc(GL_SRC_ALPHA, GL_ONE)
    pulse = 0.5 + 0.5 * math.sin(clock * 3.0)
    for k, rad in enumerate((0.55, 0.75)):
        glColor4f(r, g, b, (0.18 + 0.12 * pulse) * aura / (k + 1))
        glBegin(GL_TRIANGLE_STRIP)
        for i in range(33):
            a = 2 * math.pi * i / 32
            for rr in (rad - 0.08, rad + 0.08 * (1 + pulse)):
                glVertex3f(x + rr * math.cos(a), 0.03, z + rr * math.sin(a))
        glEnd()
    n = int(6 + 18 * aura)
    glPointSize(5.0)
    glBegin(GL_POINTS)
    for i in range(n):
        ph = (clock * (0.35 + 0.1 * (i % 3)) + i * 0.618) % 1.0
        ang = i * 2.4 + clock * 0.8
        rad = 0.3 + 0.18 * math.sin(i * 1.7)
        glColor4f(r, g, b, (1.0 - ph) * 0.8 * aura)
        glVertex3f(x + rad * math.cos(ang), 0.1 + ph * height * 1.15, z + rad * math.sin(ang))
    glEnd()
    glPointSize(1.0)
    glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
    glDepthMask(GL_TRUE)
    glEnable(GL_LIGHTING)


CALM = {'meditate', 'cold', 'flex', 'stroll', 'crossed arms', 'collar', 'levitate'}
SHOUT = {'scream', 'roar', 'punch'}
RUNNING = {'scream': 2.6, 'shirt swing': 2.0, 'stroll': 0.8, 'samba': 1.2}


def _celebration(style, t, clock):
    """Body shape for a goal celebration, t seconds into it."""
    p = dict(arms=(20.0, 20.0, 0.0, 0.0), legs=(0.0, 0.0), jump=0.0, pitch=0.0, height=0.0, yaw=180.0,
             spread=0.0, roll=0.0, head_pitch=0.0, torso=False, props={}, pivot=0.0, collar=False)
    run = math.sin(clock * 12.0)
    if style == 'knee slide':
        p.update(pitch=-20.0, height=-0.45, legs=(-95.0, -95.0), arms=(100.0, 100.0, 0.0, 0.0))
    elif style == 'aeroplane':
        p.update(yaw=180.0 + 25.0 * math.sin(clock * 3.0), arms=(90.0, 90.0, 0.0, 0.0),
                 legs=(30.0 * math.sin(clock * 10.0), -30.0 * math.sin(clock * 10.0)), pitch=8.0 * math.sin(clock * 3.0))
    elif style == 'shush':
        p.update(arms=(20.0, 12.0, 150.0, 0.0))
    elif style == 'badge kiss':
        p.update(arms=(20.0, 30.0, 120.0, 40.0), jump=0.15 * abs(math.sin(clock * 5.0)))
    elif style == 'siuu':
        if t < 0.6:
            p.update(jump=0.7 * math.sin(math.pi * t / 0.6), yaw=180.0 + 360.0 * t / 0.6,
                     arms=(60.0, 60.0, 0.0, 0.0), legs=(-30.0, -30.0))
        else:
            p.update(spread=24.0, arms=(32.0, 32.0, -40.0, -40.0), pitch=-6.0, height=-0.06, head_pitch=-12.0)
    elif style in ('meditate', 'levitate'):
        p.update(height=-0.62 + (0.6 + 0.08 * math.sin(clock * 2.0) if style == 'levitate' else 0.0),
                 legs=(90.0, 90.0), spread=38.0, arms=(30.0, 30.0, 50.0, 50.0), head_pitch=6.0)
    elif style in ('cold', 'crossed arms'):
        p.update(arms=(-38.0, -38.0, 80.0, 80.0), pitch=-6.0 if style == 'crossed arms' else 0.0,
                 head_pitch=-8.0 if style == 'crossed arms' else 4.0)
        if style == 'cold':
            p['yaw'] += 3.0 * math.sin(clock * 60.0)
    elif style == 'samba':
        p.update(yaw=180.0 + 22.0 * math.sin(clock * 8.0), legs=(28.0 * run, -28.0 * run),
                 arms=(50.0, 50.0, 40.0 * run, -40.0 * run), jump=0.06 * abs(run))
    elif style == 'arms wide':
        p.update(arms=(85.0, 85.0, 0.0, 0.0), spread=12.0, pitch=-5.0, head_pitch=-8.0)
    elif style == 'pose':
        p.update(arms=(115.0, 115.0, -10.0, -10.0), spread=14.0, head_pitch=-18.0)
    elif style == 'tea':
        p.update(arms=(-12.0, 70.0, 155.0, 20.0), props={'r': 'cup'}, head_pitch=-6.0)
    elif style == 'shirt swing':
        p.update(torso=True, arms=(170.0, 30.0, 0.0, 40.0 * run), legs=(35.0 * run, -35.0 * run),
                 props={'r': 'shirt'}, jump=0.05 * abs(run))
    elif style == 'backflip':
        if t < 0.8:
            p.update(pitch=360.0 * t / 0.8, jump=1.0 * math.sin(math.pi * t / 0.8), legs=(-70.0, -70.0),
                     arms=(40.0, 40.0, 60.0, 60.0), pivot=0.95)
        else:
            p.update(arms=(160.0, 160.0, 0.0, 0.0))
    elif style == 'think':
        p.update(arms=(40.0, 14.0, 140.0, 0.0), head=12.0, head_pitch=4.0)
    elif style == 'shaka':
        p.update(arms=(35.0, 35.0, 75.0, 75.0), jump=0.1 * abs(math.sin(clock * 6.0)))
    elif style == 'shirt show':
        p.update(torso=True, arms=(-14.0, -14.0, 95.0, 95.0))
    elif style == 'lean':
        p.update(roll=14.0, legs=(10.0, -10.0), spread=-8.0, arms=(65.0, 30.0, 0.0, -20.0))
    elif style == 'collar':
        p.update(collar=True, arms=(22.0, 22.0, -10.0, -10.0), head_pitch=-14.0,
                 yaw=180.0 + 30.0 * math.sin(clock * 0.8))
    elif style == 'scream':
        p.update(legs=(40.0 * run, -40.0 * run), arms=(50.0, 50.0, 45.0 * run, -45.0 * run), head_pitch=-22.0)
    elif style == 'punch':
        p.update(jump=0.35 * abs(math.sin(clock * 4.0)), arms=(175.0, 20.0, 0.0, 60.0), head_pitch=-14.0)
    elif style == 'heart':
        p.update(arms=(-28.0, -28.0, 130.0, 130.0))
    elif style == 'number':
        p.update(arms=(10.0, 10.0, 100.0, 100.0), props={'r': 'fingers', 'l': 'fingers'})
    elif style == 'point sky':
        p.update(arms=(160.0, 160.0, 20.0, 20.0), head_pitch=-26.0)
    elif style == 'wag':
        p.update(arms=(5.0 + 12.0 * math.sin(clock * 14.0), 14.0, 95.0, 0.0))
    elif style == 'selfie':
        p.update(arms=(30.0, 60.0, 140.0, 0.0), props={'r': 'phone'}, yaw=200.0)
    elif style == 'roar':
        p.update(arms=(70.0, 70.0, 40.0, 40.0), pitch=12.0, spread=15.0)
    elif style == 'flex':
        p.update(torso=True, arms=(80.0, 80.0, 0.0, 0.0), head_pitch=-5.0)
    elif style == 'boot kiss':
        p.update(height=-0.35, pitch=35.0, legs=(-90.0, 0.0), arms=(0.0, 20.0, 30.0, 0.0))
    elif style == 'wings':
        flap = 25.0 * math.sin(clock * 6.0)
        p.update(arms=(85.0 + flap, 85.0 + flap, 0.0, 0.0), jump=0.25 + 0.1 * math.sin(clock * 3.0), pitch=10.0)
    elif style == 'spell':
        p.update(arms=(10.0, 30.0, 90.0, 0.0), props={'r': 'orb'})
    elif style == 'bolt':
        p.update(arms=(140.0, -40.0, 0.0, 60.0), spread=10.0, roll=-8.0)
    elif style == 'stroll':
        sw = 18.0 * math.sin(clock * 4.0)
        p.update(legs=(sw, -sw), arms=(12.0, 12.0, -sw, sw))
    return p


def draw_kicker(state, kit, clock):
    x, z = state['pos']
    swing = math.sin(state['run']) * 35.0 if state['run'] else 0.0
    kick = state['kick']
    mood = state['mood'] or ''
    fig = state.get('fig')
    if fig and fig.get('kit'):
        kit = dict(kit, shirt=fig['kit'])
    right = -swing
    if kick:
        right = (70.0 if kick < 0 else 85.0) * kick
    legs = (right, swing)
    if state.get('left_foot'):
        legs = (swing, right)               # strikes with the left
    arms = (12.0, 12.0, swing * 0.8, -swing * 0.8)
    yaw, jump, pitch, height = state['yaw'], state.get('jump', 0.0), 0.0, 0.0
    extra = dict(spread=0.0, roll=0.0, head_pitch=0.0, torso=None, props=None, pivot=0.0, collar=False)
    face = state.get('face', 'focused')
    style = None
    if mood == 'slip':
        # Plant foot goes from under him: falls back on his backside
        pitch, height = -55.0, -0.55
        legs = (-80.0, -60.0)
        arms = (60.0, 60.0, -30.0, -30.0)
        face = 'gutted'
    elif mood.startswith('celebrate'):
        style = mood.split(':', 1)[1] if ':' in mood else 'knee slide'
        p = _celebration(style, state.get('cel_t', 1.0), clock)
        arms, legs, jump, pitch, height, yaw = p['arms'], p['legs'], p['jump'], p['pitch'], p['height'], p['yaw']
        extra.update(spread=p['spread'], roll=p['roll'], head_pitch=p['head_pitch'], props=p['props'],
                     pivot=p['pivot'], collar=p['collar'], torso=BASE_LAYER if p['torso'] else None)
        face = 'calm' if style in CALM else 'shout' if style in SHOUT else 'grin'
        dist = RUNNING.get(style)
        if dist:
            z += dist * min(1.0, state.get('cel_t', 1.0) / 1.6)          # runs towards the camera
    elif mood == 'despair':
        arms = (200.0, 200.0, 0.0, 0.0)             # hands on head
        pitch = 12.0
    elif state.get('mannerism'):
        name, r = state['mannerism']
        if name == 'kiss' and 0.05 < r < 0.3:
            arms = (-15.0, -15.0, 120.0, 120.0)
        elif name == 'wipe' and 0.65 < r < 0.85:
            arms = (-25.0, 12.0, 150.0, 0.0)
            extra['head_pitch'] = 10.0
        elif name == 'sky' and 0.6 < r < 0.95:
            extra['head_pitch'] = -35.0
        elif name == 'breath' and r > 0.6:
            lift = math.sin(math.pi * min(1.0, (r - 0.6) / 0.4))
            arms = (14.0 + 14.0 * lift, 14.0 + 14.0 * lift, 0.0, 0.0)
            extra['head_pitch'] = -10.0 * lift
    if state.get('stance') and not mood:
        extra['spread'] = 22.0                      # the power stance
        arms = (18.0, 18.0, -8.0, -8.0)
        height = -0.05
    # Gaze: staring the keeper down, or eyes on the ball and away from him
    head = {'away': 75.0, 'stare': 0.0}.get(state.get('gaze'), 0.0)
    if fig:
        draw_aura(x, z, fig.get('aura', 0.0), fig.get('glow'), clock)
    draw_shadow(x, z, 0.45)
    _figure(x, z, yaw, kit, arms, legs, jump, state.get('hips', 0.0), pitch, height, head=head,
            bend=55.0 * state.get('bend', 0.0), fig=fig, mood=face, clock=clock, **extra)
    if style == 'shirt show' and fig:
        # The shirt held up to the fans, name and number showing
        glPushMatrix()
        glTranslatef(x, jump + height, z)
        glRotatef(yaw, 0, 1, 0)
        glTranslatef(0.0, 0.0, -0.5)
        glColor3f(*kit['shirt'])
        glPushMatrix()
        glTranslatef(0.0, 1.38, 0.0)
        box(0.52, 0.6, 0.02)
        glPopMatrix()
        _shirt_text(fig.get('name'), fig.get('number'), kit['shirt'], 0.015, flip=True, number_y=1.16, name_y=1.48)
        glPopMatrix()


SAVE_MOODS = {'dance', 'scorpion', 'roar', 'star', 'shimmy', 'shush', 'wag', 'float', 'arms wide', 'point sky'}


def draw_keeper(pose, colour, clock, mood=None, first_person=False, scale=1.0, point=0, fig=None, face='focused',
                idle=None, sunny=False):
    (x, y, z), lean, arms = pose
    fig = fig or {}
    lk = fig.get('look') or {}
    cols = _cols(lk)
    if fig.get('kit'):
        colour = fig['kit']
    gloves = CH.GLOVE_COLOURS.get(lk.get('gloves'), GLOVE)
    legs_rx = (0.0, 0.0)
    body_rx = 0.0
    leg_spread = None
    if mood in SAVE_MOODS:
        face = 'grin' if mood not in ('roar',) else 'shout'
        y, lean = 0.95, 0.0
        if mood == 'dance':
            # Back on his feet, swaying and wagging the arms at the crowd
            y = 0.95 + 0.08 * abs(math.sin(clock * 7.0))
            lean = 14.0 * math.sin(clock * 5.0)
            arms = 'wave'
        elif mood == 'scorpion':
            y, body_rx, legs_rx, arms = 0.62, 62.0, (125.0, 125.0), 'ready'
        elif mood == 'roar':
            lean, arms = 4.0 * math.sin(clock * 30.0), 'roar'
        elif mood == 'star':
            y = 0.95 + 0.35 * abs(math.sin(clock * 6.0))
            arms, leg_spread = 'star', 30.0
        elif mood == 'shimmy':
            lean, arms = 10.0 * math.sin(clock * 18.0), 'wave'
        elif mood == 'float':
            y, arms = 1.25 + 0.1 * math.sin(clock * 2.0), 'roar'
        else:
            arms = mood                               # shush, wag, arms wide, point sky
    elif idle and (arms in ('ready', 'point', 'wave')):
        if idle == 'bar':
            arms = 'up'
            y += 0.18 * abs(math.sin(clock * 5.0))
        elif idle == 'scuff':
            legs_rx = (25.0 * math.sin(clock * 9.0), 0.0)
        elif idle == 'clap':
            arms = 'clap'
        elif idle == 'legs':
            leg_spread = 10.0 + 22.0 * math.sin(clock * 11.0)       # spaghetti legs
            lean = 9.0 * math.sin(clock * 5.5)
    if first_person:
        _first_person_gloves(x, y, z, arms, clock)
        return
    draw_aura(x, z, fig.get('aura', 0.0), fig.get('glow'), clock, 1.7)
    draw_shadow(x, z, 0.5 if y < 1.2 else 0.35, 0.3)
    glPushMatrix()
    glTranslatef(x, y, z)
    glRotatef(-lean, 0, 0, 1)
    glRotatef(body_rx, 1, 0, 0)
    h, w = lk.get('h', 1.0), lk.get('w', 1.0)
    sx, sy = scale * w, scale * h
    if sx != 1.0 or sy != 1.0:
        glScalef(sx, sy, sx)
    shorts = (0.1, 0.1, 0.12)
    glColor3f(*colour)
    glPushMatrix()
    glTranslatef(0, 0.25, 0)
    box(0.48, 0.62, 0.27)
    glPopMatrix()
    if fig.get('number') is not None:
        # Number on the front for the taker to see, name and number on the back
        _shirt_text(None, fig['number'], colour, 0.14, number_y=0.12)
        _shirt_text(fig.get('name'), fig['number'], colour, 0.14, flip=True, number_y=0.05, name_y=0.38)
    glColor3f(*shorts)
    glPushMatrix()
    glTranslatef(0, -0.12, 0)
    box(0.44, 0.26, 0.25)
    glPopMatrix()
    glPushMatrix()
    glTranslatef(0, 0.7, 0)
    glRotatef(180.0, 0, 1, 0)                    # he faces the taker (+z)
    _head(lk if lk else dict(DEFAULT_LOOK, hair='short'), cols, face, cap=sunny)
    glPopMatrix()
    if leg_spread is not None:
        leg = leg_spread
    elif arms == 'block':
        leg = 18.0
    elif arms == 'dive':
        leg = 8.0
    else:
        leg = 10.0 + 4.0 * math.sin(clock * 6.4)
    _limb((0.12, -0.2, 0), legs_rx[0], leg, 0.78, 0.17, colour, cols['boots'])
    _limb((-0.12, -0.2, 0), legs_rx[1], -leg, 0.78, 0.17, colour, cols['boots'])
    # Arms (rotation about z: 180 = straight up)
    r_x = l_x = 0.0
    if arms in ('dive', 'up'):
        r_arm, l_arm = 172.0, -172.0
    elif arms == 'block':
        r_arm, l_arm = 115.0, -115.0
    elif arms == 'wave':
        wv = 25.0 * math.sin(clock * 14.0)
        r_arm, l_arm = 150.0 + wv, -150.0 - wv
    elif arms == 'point':
        # One arm out straight at a corner: 'I know where you are going'
        r_arm, l_arm = (120.0, -40.0) if point > 0 else (40.0, -120.0)
    elif arms == 'roar':
        r_arm, l_arm = 75.0, -75.0
    elif arms == 'star':
        r_arm, l_arm = 140.0, -140.0
    elif arms == 'arms wide':
        r_arm, l_arm = 100.0, -100.0
    elif arms == 'point sky':
        r_arm, l_arm = 172.0, -172.0
    elif arms == 'shush':
        r_arm, l_arm, r_x = 20.0, -55.0, -150.0
    elif arms == 'wag':
        r_arm, l_arm, r_x = 10.0 + 12.0 * math.sin(clock * 14.0), -55.0, -95.0
    elif arms == 'clap':
        r_arm, l_arm, r_x, l_x = -10.0, 10.0, -80.0, -80.0
    else:
        r_arm, l_arm = 55.0, -55.0
    _limb((0.28, 0.5, 0), r_x, r_arm, 0.62, 0.12, colour, gloves)
    _limb((-0.28, 0.5, 0), l_x, l_arm, 0.62, 0.12, colour, gloves)
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


def teammate_z():
    return C.GOAL_LINE_Z + 37.0      # the group arm in arm in the centre circle


def draw_teammates(colours, team_mood, kicker, clock, kits, bench=None):
    """Both squads on the halfway line, reacting to every kick. bench: the
    named team-mates' looks, numbers and names, when there is a squad."""
    bench = bench or {}
    for side, x0 in (('p1', -2.0), ('p2', 2.0)):
        figs = list(bench.get(side) or [])
        kit = kits.get(side) or dict(shirt=colours[side], shorts=(0.95, 0.95, 0.95))
        happy = None
        if team_mood is not None:
            k, scored = team_mood
            happy = scored if side == k else not scored
        for i in range(5):
            if side == kicker and i == 0:
                continue                         # the kicker has left the group
            fig = figs.pop(0) if figs else None
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
            _figure(x, teammate_z(), 180.0, kit, arms, jump=jump, pitch=pitch, fig=fig,
                    mood='grin' if happy else 'gutted' if happy is False else 'nervous')


SUIT = dict(shirt=(0.13, 0.13, 0.16), shorts=(0.13, 0.13, 0.16))
MANAGER_LOOKS = {'p1': dict(skin=1, hair='short', hc='grey', beard=None, h=1.0, w=1.05, trousers=(0.13, 0.13, 0.16)),
                 'p2': dict(skin=3, hair='bald', hc='black', beard='full', h=0.98, w=1.08,
                            trousers=(0.13, 0.13, 0.16))}


def draw_managers(team_mood, clock):
    """Each manager in a suit by the halfway line: arms folded, then
    celebrating or head in hands."""
    for side, x in (('p1', -6.4), ('p2', 6.4)):
        happy = None
        if team_mood is not None:
            k, scored = team_mood
            happy = scored if side == k else not scored
        arms, jump, pitch, mood = (-35.0, -35.0, 80.0, 80.0), 0.0, 0.0, 'focused'
        if happy:
            arms, jump, mood = (160.0, 160.0, 0.0, 0.0), 0.25 * abs(math.sin(clock * 6.0)), 'grin'
        elif happy is False:
            arms, pitch, mood = (200.0, 200.0, 0.0, 0.0), 14.0, 'gutted'
        z = teammate_z() + 1.2
        draw_shadow(x, z, 0.42)
        _figure(x, z, 180.0 + (12.0 if side == 'p1' else -12.0), SUIT, arms, jump=jump, pitch=pitch,
                fig=dict(look=MANAGER_LOOKS[side]), mood=mood)


def draw_captain(cap, kit, clock):
    """The captain walking up with a nervous taker."""
    x, z = cap['pos']
    swing = math.sin(cap['run']) * 30.0 if cap['run'] else 0.0
    draw_shadow(x, z, 0.42)
    _figure(x, z, cap['yaw'], kit, (30.0, 12.0, swing * 0.6, -swing * 0.6), (-swing, swing), fig=cap.get('fig'))


def draw_showcase(fig, keeper, kit, clock, daytime='night', celebrate=None):
    """A character on a turntable for the select screen, on the spot."""
    set_environment(daytime, 'clear')
    set_lights(daytime)
    draw_static(daytime)
    x, z = 0.0, C.SPOT_Z
    yaw = (clock * 40.0) % 360.0
    if keeper:
        glPushMatrix()
        glTranslatef(x, 0, z)
        glRotatef(yaw, 0, 1, 0)
        glTranslatef(-x, 0, -z)
        draw_keeper(((x, 0.95, z), 0.0, 'ready'), kit['keeper'], clock, mood=celebrate, fig=fig,
                    sunny=daytime == 'day')
        glPopMatrix()
        return
    state = dict(pos=(x, z), yaw=yaw, run=0.0, kick=0.0, mood=('celebrate:' + celebrate) if celebrate else None,
                 hips=0.0, fig=fig, face='grin' if celebrate else 'focused', cel_t=(clock % 3.0))
    if celebrate:
        glPushMatrix()
        glTranslatef(x, 0, z)
        glRotatef(yaw - 180.0, 0, 1, 0)
        glTranslatef(-x, 0, -z)
        draw_kicker(state, kit, clock)
        glPopMatrix()
    else:
        draw_kicker(state, kit, clock)


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


def draw_bins(bins, clock):
    """Top Bins challenge: hoops hung in the top corners."""
    glDisable(GL_LIGHTING)
    glLineWidth(4.0)
    from .modes import BIN_RADIUS
    for i, (bx, by) in enumerate(bins):
        glColor3f(1.0, 0.55 + 0.2 * math.sin(clock * 4.0 + i), 0.1)
        glBegin(GL_LINE_LOOP)
        for k in range(32):
            a = 2 * math.pi * k / 32
            glVertex3f(bx + BIN_RADIUS * math.cos(a), by + BIN_RADIUS * math.sin(a), C.GOAL_LINE_Z - 0.05)
        glEnd()
    glLineWidth(1.0)
    glEnable(GL_LIGHTING)


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
                    first_person=False, kits=None, officials=True, variant='stadium', bins=None, managers=False)


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
    draw_teammates(view['team_colours'], view.get('team_mood'), view['kicker'], view['clock'], kits,
                   view.get('bench'))
    if env.get('managers'):
        draw_managers(view.get('team_mood'), view['clock'])
    if view.get('captain') and kits.get(view['kicker']):
        draw_captain(view['captain'], kits[view['kicker']], view['clock'])
    if kits.get(view['kicker']):
        draw_waiting_keeper(kits[view['kicker']].get('keeper', (0.2, 0.2, 0.25)))
    if env['officials']:
        card = view.get('card')
        draw_officials(card[0] if card else None, view['clock'])
    if not view.get('no_keeper'):
        draw_keeper(view['keeper'], view['keeper_colour'], view['clock'], view.get('keeper_mood'),
                    env['first_person'], view.get('keeper_scale', 1.0), view.get('keeper_point', 0),
                    fig=view.get('keeper_fig'), face=view.get('keeper_face', 'focused'),
                    idle=view.get('keeper_idle'), sunny=daytime == 'day' and weather == 'clear')
    if env['bins']:
        draw_bins(env['bins'], view['clock'])
    draw_kicker(view['shooter'], view['kicker_kit'], view['clock'])
    draw_ball(view['ball'], view['spin'], orange=weather == 'snow')
    if env['preview']:
        draw_preview(env['preview'])
    if aim is not None:
        draw_reticle(aim, clock)
    draw_weather(weather, view['clock'], env['wind'])
