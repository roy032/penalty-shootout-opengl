"""3D scene: stadium, pitch, goal, players, ball and the weather."""

import math
import random

from OpenGL.GL import *  # noqa: F401,F403
from OpenGL.GLU import *  # noqa: F401,F403
from OpenGL.GLUT import *  # noqa: F401,F403

from . import characters as CH, config as C, gfx, prims as P, stadium

SKIN = (0.93, 0.76, 0.6)
GLOVE = (0.95, 0.95, 0.95)
BOOT = (0.08, 0.08, 0.08)
REF_KIT = dict(shirt=(0.08, 0.08, 0.1), shorts=(0.08, 0.08, 0.1))
AR_KIT = dict(shirt=(0.95, 0.85, 0.1), shorts=(0.08, 0.08, 0.1))
CROWD_SHIRTS = [(0.85, 0.12, 0.15), (0.15, 0.35, 0.9), (0.9, 0.9, 0.9),
                (0.95, 0.8, 0.1), (0.1, 0.1, 0.12), (0.8, 0.3, 0.1)]
FACES = [SKIN, (0.55, 0.38, 0.26), (0.36, 0.24, 0.16)]

# Sky, ambient and key light for day and night, then tints for the weather.
# Dusk runs from a low golden sun to full night over the shootout.
SKIES = {'night': (0.03, 0.05, 0.11), 'day': (0.52, 0.72, 0.93), 'sunset': (0.82, 0.5, 0.36)}
AMBIENT = {'night': 0.32, 'day': 0.48, 'sunset': 0.42}
KEY_LIGHT = {'night': (0.85, 0.85, 0.8), 'day': (1.0, 0.96, 0.86), 'sunset': (1.0, 0.7, 0.45)}
LIGHT_DIR = {'night': (0.35, 1.0, 0.6), 'day': (-0.6, 0.5, -0.4), 'sunset': (-0.85, 0.24, -0.35)}
WEATHER_SKY = {'rain': 0.55, 'snow': 0.75, 'fog': 0.85, 'wind': 0.95, 'clear': 1.0}
FOG_RANGE = {'clear': (45.0, 140.0), 'wind': (45.0, 140.0), 'rain': (25.0, 100.0),
             'snow': (20.0, 90.0), 'fog': (6.0, 42.0)}

# The end behind the goal is split into column segments, each compiled three
# times (fans sitting, fans up with scarves, and half-empty as they leave),
# so the crowd can wave, jump and drift away cheaply
END_X = (-36.0, 36.0)
END_FRONT = C.GOAL_LINE_Z - 9.0
END_DEPTH = 14.0
END_ROWS = 12
SEGMENTS = 24

_static = {}          # (daytime, variant, theme, quality) -> display lists by material
_end = {}             # end colour -> [(down, up, leaving), ...]
_particles = None
_torches = None
_shadow = (0.0, 0.0, 1.0)     # sun offset x, z and stretch for day shadows
_env = dict(daytime='night', weather='clear', dusk=0.0, sky=SKIES['night'], light=LIGHT_DIR['night'])


def _mix(a, b, t):
    return tuple(x + (y - x) * t for x, y in zip(a, b))


def init_gl():
    glEnable(GL_DEPTH_TEST)
    glEnable(GL_BLEND)
    glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
    glEnable(GL_LINE_SMOOTH)
    glEnable(GL_POINT_SMOOTH)
    glEnable(GL_NORMALIZE)
    gfx.lighting(True)
    glEnable(GL_LIGHT0)
    glEnable(GL_LIGHT1)
    glEnable(GL_COLOR_MATERIAL)
    glColorMaterial(GL_FRONT_AND_BACK, GL_AMBIENT_AND_DIFFUSE)
    glShadeModel(GL_SMOOTH)
    glEnable(GL_FOG)
    glFogi(GL_FOG_MODE, GL_LINEAR)
    P.init()
    set_environment('night', 'clear')


def _phase(daytime, dusk=0.0):
    """Sky, ambient, key light and its direction for the time of day."""
    if daytime == 'dusk':
        t = max(0.0, min(1.0, dusk))
        e = t * t * (3 - 2 * t)
        return (_mix(SKIES['sunset'], SKIES['night'], e), AMBIENT['sunset'] + (AMBIENT['night'] - AMBIENT['sunset']) * e,
                _mix(KEY_LIGHT['sunset'], KEY_LIGHT['night'], e), _mix(LIGHT_DIR['sunset'], LIGHT_DIR['night'], e))
    key = daytime if daytime in SKIES else 'night'
    return SKIES[key], AMBIENT[key], KEY_LIGHT[key], LIGHT_DIR[key]


def sky_colour(daytime, weather, dusk=0.0):
    base = _phase(daytime, dusk)[0]
    k = WEATHER_SKY.get(weather, 1.0)
    grey = 0.45 if daytime == 'day' else (0.3 * (1 - dusk) + 0.08 * dusk if daytime == 'dusk' else 0.08)
    return tuple(c * k + grey * (1 - k) for c in base)


def set_environment(daytime, weather, dusk=0.0):
    """Clear colour, fog and lights for the time of day and the weather."""
    global _shadow
    sky = sky_colour(daytime, weather, dusk)
    _, amb, key, light = _phase(daytime, dusk)
    _env.update(daytime=daytime, weather=weather, dusk=dusk, sky=sky, light=light)
    glClearColor(sky[0], sky[1], sky[2], 1.0)
    glFogfv(GL_FOG_COLOR, (sky[0], sky[1], sky[2], 1.0))
    start, end = FOG_RANGE.get(weather, FOG_RANGE['clear'])
    glFogf(GL_FOG_START, start)
    glFogf(GL_FOG_END, end)
    dim = 0.75 if weather in ('rain', 'fog') and daytime != 'night' else 1.0
    a = amb * dim
    glLightModelfv(GL_LIGHT_MODEL_AMBIENT, (a, a, a + 0.04, 1.0))
    glLightfv(GL_LIGHT0, GL_DIFFUSE, (key[0] * dim, key[1] * dim, key[2] * dim, 1.0))
    glLightfv(GL_LIGHT1, GL_DIFFUSE, (0.35, 0.37, 0.45, 1.0))
    # A low sun throws long shadows; floodlights keep them short
    if daytime == 'day' and weather in ('clear', 'wind'):
        _shadow = (0.9, 0.6, 2.2)
    elif daytime == 'dusk' and dusk < 0.6 and weather in ('clear', 'wind'):
        _shadow = (1.4, 0.6, 3.0 - 2.0 * dusk)
    else:
        _shadow = (0.0, 0.0, 1.0)


def light_dir():
    """The key light's direction (towards the light), in the world."""
    return _env['light']


def set_lights(daytime='night'):
    lx, ly, lz = _env['light']
    glLightfv(GL_LIGHT0, GL_POSITION, (lx, ly, lz, 0.0))
    glLightfv(GL_LIGHT1, GL_POSITION, (-0.5, 0.6, -1.0, 0.0))


# ------------------------------------------------------------------ primitives
box, sphere, cylinder_between, flat_quad, disc = P.box, P.sphere, P.cylinder_between, P.flat_quad, P.disc


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


def _stripes():
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


def _pitch():
    """The grass and its markings (the courts are drawn by _court)."""
    _stripes()
    if C.VARIANT == 'park':
        _park_ground()
        return
    if C.VARIANT in ('futsal', 'beach'):
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


def _blades():
    """Grass blades where the camera gets close: round the spot and in the goalmouth."""
    rng = random.Random(4)
    glBegin(GL_LINES)
    glNormal3f(0, 1, 0)
    for x0, x1, z0, z1, n in ((-5.0, 5.0, C.SPOT_Z - 3.0, C.SPOT_Z + 9.0, 5200),
                              (-5.5, 5.5, C.GOAL_LINE_Z - 0.5, C.GOAL_LINE_Z + 4.0, 2600)):
        for _ in range(n):
            x, z = rng.uniform(x0, x1), rng.uniform(z0, z1)
            g = rng.uniform(0.38, 0.62)
            glColor3f(0.16 * g / 0.5, g, 0.17 * g / 0.5)
            glVertex3f(x, 0.0, z)
            h = rng.uniform(0.025, 0.06)
            glVertex3f(x + rng.uniform(-0.012, 0.012), h, z + rng.uniform(-0.012, 0.012))
    glEnd()


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


def _fan(x, h, zc, facing, shirt, face, up, scarf=None):
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
        if scarf:
            # A scarf held high between both hands
            for k in range(4):
                glColor3f(*(scarf if k % 2 == 0 else (0.95, 0.95, 0.95)))
                glPushMatrix()
                glTranslatef(-0.27 + k * 0.18, 0.74, 0.02)
                box(0.18, 0.1, 0.02)
                glPopMatrix()
    glTranslatef(0, 0.42, 0)
    glColor3f(*face)
    box(0.2, 0.2, 0.2)
    glPopMatrix()


def _steps(x1, x2, z_front, depth, rows, facing, colour=(0.22, 0.24, 0.3)):
    step_d = depth / rows
    glColor3f(*colour)
    for r in range(rows):
        h = 1.0 + r * 0.65
        glPushMatrix()
        glTranslatef((x1 + x2) / 2, h / 2, z_front - facing * (r + 0.5) * step_d)
        box(x2 - x1, h, step_d)
        glPopMatrix()


def _crowd(x1, x2, z_front, depth, rows, facing, rng, colours, up=False, fill=0.85, scarves=None):
    step_d = depth / rows
    for r in range(rows):
        h = 1.0 + r * 0.65
        zc = z_front - facing * (r + 0.5) * step_d
        x = x1 + 0.3
        while x < x2 - 0.3:
            seat = rng.random()
            shirt, face, scarf = colours(rng), rng.choice(FACES), rng.random()
            if seat < fill:
                _fan(x, h, zc, facing, shirt, face, up, scarves if (scarves and scarf < 0.3) else None)
            x += 0.55 + rng.random() * 0.15


def _stand(x1, x2, z_front, depth, rows, facing, rng, colour=(0.22, 0.24, 0.3)):
    """A tiered stand with a seated crowd."""
    _steps(x1, x2, z_front, depth, rows, facing, colour)
    _crowd(x1, x2, z_front, depth, rows, facing, rng, lambda r: r.choice(CROWD_SHIRTS))


def _lower_steps(theme):
    colour = stadium.style(theme)['steps']
    _steps(END_X[0], END_X[1], END_FRONT, END_DEPTH, END_ROWS, 1, colour)
    _steps(-36.0, 36.0, 30.0, 12.0, 10, -1, colour)
    glPushMatrix()
    glTranslatef(-41.0, 0.0, -2.0)
    glRotatef(90, 0, 1, 0)
    _steps(-24.0, 30.0, 0.0, 12.0, 10, 1, colour)
    glPopMatrix()
    glPushMatrix()
    glTranslatef(41.0, 0.0, -2.0)
    glRotatef(-90, 0, 1, 0)
    _steps(-30.0, 24.0, 0.0, 12.0, 10, 1, colour)
    glPopMatrix()


def _lower_crowd():
    rng = random.Random(11)

    def shirts(r):
        return r.choice(CROWD_SHIRTS)
    _crowd(-36.0, 36.0, 30.0, 12.0, 10, -1, rng, shirts)
    glPushMatrix()
    glTranslatef(-41.0, 0.0, -2.0)
    glRotatef(90, 0, 1, 0)
    _crowd(-24.0, 30.0, 0.0, 12.0, 10, 1, rng, shirts)
    glPopMatrix()
    glPushMatrix()
    glTranslatef(41.0, 0.0, -2.0)
    glRotatef(-90, 0, 1, 0)
    _crowd(-30.0, 24.0, 0.0, 12.0, 10, 1, rng, shirts)
    glPopMatrix()


def _compile(build, *args):
    lst = glGenLists(1)
    glNewList(lst, GL_COMPILE)
    build(*args)
    glEndList()
    return lst


def _static_lists(daytime, theme):
    key = (daytime, C.VARIANT, theme, gfx.quality())
    if key not in _static:
        structure, upper = stadium.build_structure(theme, daytime, CROWD_SHIRTS, FACES)
        lists = dict(grass=_compile(_pitch),
                     court=_compile(_court, C.VARIANT) if C.VARIANT in ('futsal', 'beach') else None,
                     steps=_compile(_lower_steps, theme), structure=_compile(structure),
                     crowd=_compile(_lower_crowd), upper=_compile(upper),
                     blades=_compile(_blades) if gfx.fancy() and C.VARIANT in ('stadium', 'park') else None)
        _static[key] = lists
    return _static[key]


def draw_static(daytime='night', theme='classic'):
    lists = _static_lists(daytime, theme)
    gfx.material('grass')
    glCallList(lists['grass'])
    if lists['blades'] and not gfx.screen_pass():
        glCallList(lists['blades'])
    if lists['court']:
        gfx.material('ground')
        glCallList(lists['court'])
    gfx.material('default')
    glCallList(lists['steps'])
    glCallList(lists['structure'])
    gfx.material('crowd')
    glCallList(lists['crowd'])
    glCallList(lists['upper'])
    gfx.material('default')


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
            trio = []
            for up, fill in ((False, 0.85), (True, 0.85), (False, 0.3)):
                rng = random.Random(100 + i)      # same fans sitting and standing
                trio.append(_compile(_crowd, x1, x1 + width, END_FRONT, END_DEPTH, END_ROWS, 1, rng, shirts, up,
                                     fill, colour))
            segs.append(trio)
        _end[key] = segs
    return _end[key]


def segment_up(i, crowd, clock):
    """Whether segment i of the end crowd is on its feet."""
    if crowd == 'stand':                      # the whole end up for the big kick
        return True
    if crowd == 'wave':                       # a Mexican wave rolling along the end
        return (clock * 9.0 - i) % SEGMENTS < 2.5
    if crowd == 'jeer':                       # bouncing to put the kicker off
        return math.sin(clock * 9.0 + i * 0.8) > 0.2
    if crowd == 'roar':
        return math.sin(clock * 12.0 + i * 1.3) > -0.3
    return math.sin(clock * 0.7 + i * 2.1) > 0.97


def draw_end_crowd(colour, crowd, clock, leaving=0.0):
    """leaving: 0..1, how far the losing fans have drifted towards the exits."""
    gfx.material('crowd')
    for i, (down, up, sparse) in enumerate(_end_lists(colour)):
        if leaving and ((i * 7919) % SEGMENTS) / float(SEGMENTS) < leaving:
            glCallList(sparse)
        else:
            glCallList(up if segment_up(i, crowd, clock) else down)
    gfx.material('default')


def draw_flags(colour, clock, wind):
    """Flags waving along the front of the end behind the goal."""
    gfx.lighting(False)
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
    gfx.lighting(True)


def draw_tifo(colour):
    """A giant banner held up across the end before the shootout."""
    gfx.lighting(False)
    step_d = END_DEPTH / END_ROWS
    bands = 8
    for b in range(bands):
        glColor3f(*(colour if b % 2 == 0 else (0.95, 0.95, 0.95)))
        r0, r1 = b * END_ROWS / bands, (b + 1) * END_ROWS / bands
        glBegin(GL_QUADS)
        for (r, x) in ((r0, END_X[0] + 6), (r0, END_X[1] - 6), (r1, END_X[1] - 6), (r1, END_X[0] + 6)):
            glVertex3f(x, 1.9 + r * 0.65, END_FRONT - r * step_d + 0.2)
        glEnd()
    gfx.lighting(True)


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
    gfx.lighting(False)
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
    gfx.lighting(True)


def _particle_field():
    global _particles
    if _particles is None:
        rng = random.Random(5)
        _particles = [(rng.uniform(-22, 22), rng.uniform(-28, 12), rng.uniform(0, 14), rng.uniform(0, 6.28))
                      for _ in range(900)]
    return _particles


_ball_prev = dict(pos=None, clock=None)


def draw_weather(weather, clock, wind, ball=None, figures=()):
    """Rain streaks with splashes off the pitch, the players and a skidding
    ball, or falling snow round the penalty area."""
    if weather not in ('rain', 'snow') or gfx.shadow_pass():
        return
    gfx.lighting(False)
    glDepthMask(GL_FALSE)
    fancy = gfx.fancy()
    if weather == 'rain':
        glColor4f(0.75, 0.8, 0.9, 0.45)
        glBegin(GL_LINES)
        for x, z, h, ph in _particle_field():
            y = (h - clock * 16.0) % 14.0
            glVertex3f(x, y, z)
            glVertex3f(x - 0.04 + wind * 0.02, y + 0.45, z + 0.06)
        glEnd()
        if fancy:
            # Splash rings where drops land, densest near the goal
            glBegin(GL_LINES)
            for k in range(140):
                ph = (clock * 1.7 + k * 0.618) % 1.0
                cyc = int(clock * 1.7 + k * 0.618)
                x = ((k * 7.31 + cyc * 3.17) % 24.0) - 12.0
                z = C.GOAL_LINE_Z + ((k * 3.77 + cyc * 5.31) % 20.0)
                r = 0.03 + 0.12 * ph
                glColor4f(0.8, 0.85, 0.95, 0.5 * (1.0 - ph))
                for a in range(6):
                    a1, a2 = a * 1.047, (a + 1) * 1.047
                    glVertex3f(x + r * math.cos(a1), 0.03, z + r * math.sin(a1))
                    glVertex3f(x + r * math.cos(a2), 0.03, z + r * math.sin(a2))
            glEnd()
            # Spray bouncing off heads and shoulders
            glPointSize(2.0)
            glBegin(GL_POINTS)
            for fx, fy, fz in figures:
                for k in range(10):
                    ph = (clock * 2.3 + k * 0.37) % 1.0
                    a = k * 2.4
                    glColor4f(0.85, 0.9, 1.0, 0.6 * (1.0 - ph))
                    glVertex3f(fx + 0.25 * ph * math.cos(a), fy + 0.3 * ph - 1.2 * ph * ph, fz + 0.25 * ph * math.sin(a))
            glEnd()
            glPointSize(1.0)
        _ball_spray(ball, clock)
    else:
        gfx.round_points(True)
        glPointSize(4.0 if fancy else 3.0)
        glColor4f(1.0, 1.0, 1.0, 0.9)
        glBegin(GL_POINTS)
        for x, z, h, ph in _particle_field()[:800 if fancy else 600]:
            y = (h - clock * 1.3) % 14.0
            glVertex3f(x + 0.4 * math.sin(clock * 0.9 + ph) + wind * 0.05 * y, y, z + 0.3 * math.cos(clock * 0.7 + ph))
        glEnd()
        glPointSize(1.0)
        gfx.round_points(False)
    glDepthMask(GL_TRUE)
    gfx.lighting(True)


def _ball_spray(ball, clock):
    """A rooster tail of water behind a ball skidding across a wet pitch."""
    prev, t0 = _ball_prev['pos'], _ball_prev['clock']
    _ball_prev.update(pos=ball, clock=clock)
    if ball is None or prev is None or t0 is None or not 0.0 < clock - t0 < 0.2:
        return
    dt = clock - t0
    vx, vz = (ball[0] - prev[0]) / dt, (ball[2] - prev[2]) / dt
    speed = math.hypot(vx, vz)
    if ball[1] > 0.3 or speed < 3.0:
        return
    glPointSize(2.5)
    glBegin(GL_POINTS)
    for k in range(24):
        ph = (k / 24.0 + clock * 3.0) % 1.0
        side = ((k * 0.618) % 1.0 - 0.5) * 0.6
        back = ph * 0.08
        glColor4f(0.85, 0.9, 1.0, 0.7 * (1.0 - ph))
        glVertex3f(ball[0] - vx * back + side * vz / speed * ph, 0.05 + 0.5 * ph - 1.4 * ph * ph,
                   ball[2] - vz * back - side * vx / speed * ph)
    glEnd()
    glPointSize(1.0)


def draw_ground_cover(weather, snow=0.0):
    """Without the shader: a dusting of snow (thicker as it settles) or the sheen of a soaked pitch."""
    if weather not in ('rain', 'snow') or gfx.shaders() or gfx.shadow_pass():
        return
    gfx.lighting(False)
    glDepthMask(GL_FALSE)
    glColor4f(*((0.95, 0.96, 1.0, 0.3 + 0.4 * snow) if weather == 'snow' else (0.15, 0.2, 0.3, 0.22)))
    glBegin(GL_QUADS)
    flat_quad(-48.0, -40.0, 48.0, 40.0, 0.015)
    glEnd()
    glDepthMask(GL_TRUE)
    gfx.lighting(True)


def _billboard_yaw():
    eye = _env.get('eye') or (0.0, 2.0, C.SPOT_Z + 8.0)
    return eye


def draw_smoke(clock, colour, wind, flares):
    """Flare smoke drifting out of the end and across the floodlight beams."""
    if gfx.shadow_pass():
        return
    ex, ey, ez = _billboard_yaw()
    gfx.lighting(False)
    glDepthMask(GL_FALSE)
    n = 26 if flares else 14
    tint = _mix(colour, (0.75, 0.75, 0.78), 0.6)
    for k in range(n):
        life = 9.0 + (k % 4)
        ph = ((clock + k * 1.37) % life) / life
        x0 = -26.0 + (k * 7.3) % 52.0
        x = x0 + (1.5 + wind) * ph * 8.0
        y = 3.0 + ph * 14.0
        z = END_FRONT - 3.0 - (k % 5) * 2.0 + ph * 6.0
        r = 2.0 + 6.0 * ph
        a = 0.16 * math.sin(math.pi * ph) * (1.0 if flares else 0.6)
        yaw = math.degrees(math.atan2(ex - x, ez - z))
        glPushMatrix()
        glTranslatef(x, y, z)
        glRotatef(yaw, 0, 1, 0)
        glRotatef(90.0, 1, 0, 0)
        P.soft_disc(0.0, 0.0, r, tint, a, 0.0, 18)
        glPopMatrix()
    glDepthMask(GL_TRUE)
    gfx.lighting(True)


def draw_phone_flashes(clock):
    """Camera flashes popping round the ground for a big kick."""
    if gfx.shadow_pass():
        return
    gfx.lighting(False)
    gfx.material('emissive', emit=2.0)
    glDepthMask(GL_FALSE)
    gfx.round_points(True)
    glPointSize(5.0)
    glBegin(GL_POINTS)
    tick = int(clock * 14.0)
    for i, (x, y, z, ph) in enumerate(_torch_points()):
        if (i * 31 + tick * 17) % 97 < 3:
            glColor4f(1.0, 1.0, 1.0, 1.0)
            glVertex3f(x, y + 0.2, z)
    glEnd()
    glPointSize(1.0)
    gfx.round_points(False)
    glDepthMask(GL_TRUE)
    gfx.material('default')
    gfx.lighting(True)


def draw_confetti(win, clock):
    """Confetti raining down over the winners, in their colours, gold and white."""
    if gfx.shadow_pass():
        return
    t = win['t']
    cols = (win['colour'], (1.0, 0.85, 0.2), (0.97, 0.97, 0.97))
    gfx.lighting(False)
    glBegin(GL_QUADS)
    for k in range(520):
        fall = (t * (0.9 + 0.3 * ((k * 0.37) % 1.0)) + k * 0.031) % 12.0
        y = 16.0 - fall * 1.4
        if y < 0.02:
            continue
        x = -14.0 + (k * 7.919) % 28.0 + 0.6 * math.sin(clock * 1.3 + k)
        z = C.GOAL_LINE_Z - 2.0 + (k * 3.141) % 30.0 + 0.5 * math.cos(clock * 1.1 + k)
        a = clock * (3.0 + k % 5) + k
        c = cols[k % 3]
        glColor4f(c[0], c[1], c[2], min(1.0, t * 2.0))
        s = 0.11
        ca, sa = math.cos(a) * s, math.sin(a) * s
        glVertex3f(x - ca, y - sa * 0.4, z - sa)
        glVertex3f(x + sa, y + ca * 0.4, z - ca)
        glVertex3f(x + ca, y + sa * 0.4, z + sa)
        glVertex3f(x - sa, y - ca * 0.4, z + ca)
    glEnd()
    gfx.lighting(True)


def draw_fireworks(win, clock):
    """Fireworks bursting over the stands."""
    if gfx.shadow_pass() or win['t'] < 0.8:
        return
    gfx.lighting(False)
    gfx.material('emissive', emit=2.2)
    glDepthMask(GL_FALSE)
    glBlendFunc(GL_SRC_ALPHA, GL_ONE)
    gfx.round_points(True)
    palette = (win['colour'], (1.0, 0.85, 0.3), (0.9, 0.95, 1.0), (1.0, 0.4, 0.3))
    glPointSize(4.0)
    glBegin(GL_POINTS)
    for b in range(6):
        period = 2.2
        age = (win['t'] + b * 0.37) % period
        n = int((win['t'] + b * 0.37) / period)
        seed = n * 6 + b
        cx = -30.0 + (seed * 13.7) % 60.0
        cz = (-34.0 if seed % 2 else 36.0) + (seed * 3.3) % 8.0
        cy = 24.0 + (seed * 5.1) % 10.0
        col = palette[seed % len(palette)]
        if age < 0.5:                                    # the rocket going up
            glColor4f(1.0, 0.9, 0.6, 0.9)
            glVertex3f(cx, cy * age / 0.5, cz)
            continue
        e = age - 0.5
        fade = max(0.0, 1.0 - e / 1.6)
        for k in range(40):
            u = (k * 0.618) % 1.0 * 2.0 - 1.0
            a = k * 2.39996
            r = math.sqrt(1.0 - u * u)
            sp = 9.0 * e
            glColor4f(col[0], col[1], col[2], fade)
            glVertex3f(cx + sp * r * math.cos(a), cy + sp * u - 2.5 * e * e, cz + sp * r * math.sin(a))
    glEnd()
    glPointSize(1.0)
    gfx.round_points(False)
    glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
    glDepthMask(GL_TRUE)
    gfx.material('default')
    gfx.lighting(True)


def draw_glt(glt, clock):
    """The goal-line technology graphic: the line lit up, a plane across the
    goal, and the ball frozen where it was deepest."""
    if gfx.shadow_pass():
        return
    hw, h = C.GOAL_HALF_WIDTH, C.GOAL_HEIGHT
    colour = (0.2, 0.95, 0.4) if glt['goal'] else (0.95, 0.3, 0.25)
    gfx.lighting(False)
    glDepthMask(GL_FALSE)
    glColor4f(colour[0], colour[1], colour[2], 0.16)
    glBegin(GL_QUADS)
    glVertex3f(-hw, 0.0, C.GOAL_LINE_Z)
    glVertex3f(hw, 0.0, C.GOAL_LINE_Z)
    glVertex3f(hw, h, C.GOAL_LINE_Z)
    glVertex3f(-hw, h, C.GOAL_LINE_Z)
    glEnd()
    glLineWidth(4.0)
    glColor4f(colour[0], colour[1], colour[2], 0.95)
    glBegin(GL_LINES)
    glVertex3f(-hw, 0.03, C.GOAL_LINE_Z)
    glVertex3f(hw, 0.03, C.GOAL_LINE_Z)
    glEnd()
    x, y, z = glt['ball']
    glLineWidth(2.0)
    for axis in range(3):                          # a wireframe ball, frozen
        glBegin(GL_LINE_LOOP)
        for i in range(24):
            a = 2 * math.pi * i / 24
            c, s = C.BALL_RADIUS * math.cos(a), C.BALL_RADIUS * math.sin(a)
            p = ((0.0, c, s), (c, 0.0, s), (c, s, 0.0))[axis]
            glVertex3f(x + p[0], y + p[1], z + p[2])
        glEnd()
    glBegin(GL_LINES)                              # the ball's back edge down to the line
    glVertex3f(x, y, z + C.BALL_RADIUS)
    glVertex3f(x, 0.03, z + C.BALL_RADIUS)
    glVertex3f(x, 0.03, z + C.BALL_RADIUS)
    glVertex3f(x, 0.03, C.GOAL_LINE_Z)
    glEnd()
    glLineWidth(1.0)
    glDepthMask(GL_TRUE)
    gfx.lighting(True)


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


# The back of the net as a sheet of cloth: each knot's outward give and
# speed, pushed by the ball and pulled back by its neighbours
NET_STEP = 0.22
_cloths = {}


def _net_grid(hw, h):
    nx = int(2 * hw / NET_STEP) + 1
    ny = int(h / NET_STEP) + 1
    xs = [-hw + i * (2 * hw) / (nx - 1) for i in range(nx)]
    ys = [j * h / (ny - 1) for j in range(ny)]
    return xs, ys


def step_net(net_hit, ball, clock, hw, h, back):
    """Advance the cloth to this clock: a ripple from the ball's impact, the
    net held out round a ball lying in it, and the knots pulled back taut."""
    xs, ys = _net_grid(hw, h)
    nx, ny = len(xs), len(ys)
    _cloth = _cloths.setdefault('screen' if gfx.screen_pass() else 'main', dict(clock=None, size=None))
    if _cloth['size'] != (nx, ny) or _cloth['clock'] is None or clock < _cloth['clock'] \
            or clock - _cloth['clock'] > 1.0:
        _cloth.update(d=[[0.0] * nx for _ in range(ny)], v=[[0.0] * nx for _ in range(ny)], size=(nx, ny),
                      clock=clock, hit=None)
    d, v = _cloth['d'], _cloth['v']
    if net_hit is not None and _cloth['hit'] != net_hit[2] and 0.0 <= clock - net_hit[2] < 0.5:
        _cloth['hit'] = net_hit[2]
        for j, y in enumerate(ys):
            for i, x in enumerate(xs):
                r2 = (x - net_hit[0]) ** 2 + (y - net_hit[1]) ** 2
                v[j][i] += 7.0 * math.exp(-r2 / 0.18)
    elapsed = min(0.06, clock - _cloth['clock'])
    _cloth['clock'] = clock
    steps = int(elapsed / (1 / 120.0) + 0.5)
    k, damp = 850.0, 3.2
    for _ in range(steps):
        dt = 1 / 120.0
        for j in range(1, ny - 1):          # the edges are tied to the frame and the ground
            row, up, dn = d[j], d[j + 1], d[j - 1]
            vr = v[j]
            for i in range(1, nx - 1):
                lap = row[i - 1] + row[i + 1] + dn[i] + up[i] - 4.0 * row[i]
                vr[i] += (k * lap - damp * vr[i] - 40.0 * row[i]) * dt
        for j in range(1, ny - 1):
            row, vr = d[j], v[j]
            for i in range(1, nx - 1):
                row[i] = max(-0.05, min(0.9, row[i] + vr[i] * dt))
    # A ball resting in the net holds it out
    if ball is not None:
        bx, by, bz = ball
        depth = back - (bz - C.BALL_RADIUS)
        if depth > 0.0 and abs(bx) < hw and by < h + 0.3:
            for j, y in enumerate(ys):
                for i, x in enumerate(xs):
                    r2 = (x - bx) ** 2 + (y - by) ** 2
                    if r2 < 0.5:
                        d[j][i] = max(d[j][i], depth * math.exp(-r2 / 0.12))
    return xs, ys, d


def draw_goal(net_hit, clock, ball=None, wet=0.0, wood=None):
    if not C.HAS_BAR:
        draw_jumpers()
        return
    hw = C.GOAL_HALF_WIDTH + C.POST_RADIUS
    h = C.GOAL_HEIGHT + C.POST_RADIUS
    z = C.GOAL_LINE_Z - C.POST_RADIUS
    back = C.GOAL_LINE_Z - C.GOAL_DEPTH
    gfx.material('paint')
    glColor3f(0.97, 0.97, 0.97)
    pr = C.POST_RADIUS
    cylinder_between((-hw, 0, z), (-hw, h + pr, z), pr, 16)
    cylinder_between((hw, 0, z), (hw, h + pr, z), pr, 16)
    cylinder_between((-hw - pr, h, z), (hw + pr, h, z), pr, 16)
    gfx.material('default')
    if wet and wood is not None:
        _drips(wood, clock, hw, h, z)
    if not C.HAS_NET:
        return
    # Net supports
    glColor3f(0.6, 0.6, 0.62)
    for s in (-1, 1):
        cylinder_between((s * hw, h, z), (s * hw, h, back), 0.025, 6)
        cylinder_between((s * hw, h, back), (s * hw, 0, back), 0.025, 6)
    if gfx.shadow_pass():
        return
    xs, ys, d = step_net(net_hit, ball, clock, hw, h, back)
    sag = 0.16 * wet                                   # a soaked net hangs heavier

    def back_z(i, j):
        u = ys[j] / h
        return back - d[j][i] - sag * math.sin(math.pi * u) * 0.6

    def roof_y(zz, x):
        t = (z - zz) / (z - back)
        return h - sag * math.sin(math.pi * t) * (1.0 - (x / hw) ** 2 * 0.6)

    gfx.lighting(False)
    glColor4f(0.92, 0.92, 0.95, 0.6 if gfx.fancy() else 0.55)
    glLineWidth(1.0)
    nx, ny = len(xs), len(ys)
    for i in range(nx):                            # back: verticals
        glBegin(GL_LINE_STRIP)
        for j in range(ny):
            glVertex3f(xs[i], ys[j], back_z(i, j))
        glEnd()
    for j in range(ny):                            # back: horizontals
        glBegin(GL_LINE_STRIP)
        for i in range(nx):
            glVertex3f(xs[i], ys[j], back_z(i, j))
        glEnd()
    nz = int(C.GOAL_DEPTH / NET_STEP) + 1
    zs = [z - k * (z - back) / (nz - 1) for k in range(nz)]
    for zz in zs:                                  # roof (sagging in the rain) and sides
        glBegin(GL_LINE_STRIP)
        for i in range(0, nx, 2):
            glVertex3f(xs[i], roof_y(zz, xs[i]), zz)
        glVertex3f(hw, roof_y(zz, hw), zz)
        glEnd()
    glBegin(GL_LINES)
    for zz in zs:
        for s in (-1, 1):
            glVertex3f(s * hw, 0, zz)
            glVertex3f(s * hw, roof_y(zz, s * hw), zz)
    glEnd()
    for i in range(nx):                            # roof: front to back
        glBegin(GL_LINE_STRIP)
        for zz in zs:
            glVertex3f(xs[i], roof_y(zz, xs[i]), zz)
        glVertex3f(xs[i], ys[-1], back_z(i, ny - 1))
        glEnd()
    glBegin(GL_LINES)
    for j in range(ny):
        for s, i in ((-1, 0), (1, nx - 1)):
            glVertex3f(s * hw, ys[j], z)
            glVertex3f(s * hw, ys[j], back_z(i, j))
    glEnd()
    gfx.lighting(True)


def _drips(wood, clock, hw, h, z):
    """Water shaken off the bar or post by the ball, dripping for a while."""
    age = clock - wood[2]
    if age < 0.0:
        return
    gfx.lighting(False)
    glDepthMask(GL_FALSE)
    glPointSize(2.5)
    glBegin(GL_POINTS)
    for k in range(26):
        x = wood[0] + ((k * 0.37) % 1.0 - 0.5) * (1.6 if age < 0.3 else 1.0)
        x = max(-hw, min(hw, x))
        t = (age * (0.8 + 0.4 * ((k * 0.61) % 1.0)) + k * 0.13) % 0.9
        fade = max(0.0, 1.0 - age / 8.0)
        glColor4f(0.8, 0.86, 0.95, 0.75 * fade)
        glVertex3f(x, h - 0.06 - 4.9 * t * t, z + 0.02)
    if age < 0.5:                                  # the spray off the frame
        for k in range(30):
            a = k * 2.39996
            r = age * (2.0 + (k % 5) * 0.5)
            glColor4f(0.85, 0.9, 1.0, 0.8 * (1.0 - age / 0.5))
            glVertex3f(wood[0] + r * math.cos(a), wood[1] + r * math.sin(a) * 0.7 - 2.0 * age * age, z + 0.1 + 0.3 * r)
    glEnd()
    glPointSize(1.0)
    glDepthMask(GL_TRUE)
    gfx.lighting(True)


# --------------------------------------------------------------------- players
# Mud on kits builds up through a match: slips, dives and the rain
_dirt = {}
# Smoothed poses (animation blending) and when each keeper hit the ground
_poses = {}
_landed = {}
_match = [None]


def new_match(match_id):
    """Fresh kits, fresh poses: called when a different match is drawn."""
    if _match[0] != match_id:
        _match[0] = match_id
        _dirt.clear()
        _poses.clear()
        _landed.clear()
        _marks['divots'].clear()
        _marks['prints'].clear()


def dirt(key, at_least=None):
    if at_least is not None and key is not None:
        _dirt[key] = min(1.0, max(_dirt.get(key, 0.0), at_least))
    return _dirt.get(key, 0.0)


def _ease(key, target, clock, rate=18.0):
    """Blend from the last drawn pose towards this one, so poses flow into
    each other instead of snapping. Angles in degrees."""
    if gfx.screen_pass():
        return tuple(target)                     # the big screen shows other moments: no blending
    prev = _poses.get(key)
    if prev is None or not (0.0 <= clock - prev[0] < 0.3) or len(prev[1]) != len(target):
        _poses[key] = (clock, tuple(target))
        return tuple(target)
    k = 1.0 - math.exp(-rate * (clock - prev[0]))
    out = []
    for p, t in zip(prev[1], target):
        d = t - p
        if abs(d) > 180.0:                       # take the short way round
            d -= math.copysign(360.0, d)
        out.append(p + d * k)
    _poses[key] = (clock, tuple(out))
    return tuple(out)


def _limb(joint, rot_x, rot_z, length, width, colour, end_colour=None, end='boot'):
    """A straight, rounded limb (the keeper's) with a glove or boot at the end."""
    glPushMatrix()
    glTranslatef(*joint)
    glRotatef(rot_z, 0, 0, 1)
    glRotatef(rot_x, 1, 0, 0)
    glColor3f(*colour)
    P.limb(length, width * 0.58, width * 0.42, 10)
    if end_colour:
        glColor3f(*end_colour)
        glTranslatef(0, -length - 0.04, 0)
        if end == 'glove':
            glPushMatrix()
            glScalef(1.0, 1.25, 0.6)
            sphere(width * 0.62, 10)
            glPopMatrix()
        else:
            _boot(width)
    glPopMatrix()


def _boot(width=0.17):
    gfx.material('paint')
    glPushMatrix()
    glTranslatef(0.0, -0.02, -0.06)
    glScalef(0.62, 0.42, 1.25)
    sphere(width * 0.6, 10)
    glPopMatrix()
    gfx.material('fabric')


def draw_shadow(x, z, r, strength=0.35, height=1.8):
    """A soft shadow under a player or the ball: stretched away from a low sun,
    or (with real shadows on) four faint floodlight shadows and a contact shadow."""
    if gfx.shadow_pass():
        return
    ox, oz, stretch = _shadow
    gfx.lighting(False)
    glDepthMask(GL_FALSE)
    if gfx.shaders():
        gfx.material('default')
        P.soft_disc(x, z, r * 0.75, (0, 0, 0), strength * 0.9, 0.021, 18)
        if _env['daytime'] != 'day' and stadium.lit_banks(_env['daytime'], _env['dusk'])[0]:
            for fx, fz in stadium.FLOODLIGHTS:
                dx, dz = x - fx, z - fz
                d = math.hypot(dx, dz) or 1.0
                glPushMatrix()
                glTranslatef(x + dx / d * height * 0.35, 0, z + dz / d * height * 0.35)
                glRotatef(math.degrees(math.atan2(-dz, dx)), 0, 1, 0)
                P.soft_disc(0.0, 0.0, r * 1.05, (0, 0, 0), strength * 0.32, 0.02, 16, 1.0 + height * 0.45)
                glPopMatrix()
    else:
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
    gfx.lighting(True)


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
    if gfx.shadow_pass():
        return
    col = (0.06, 0.06, 0.08) if _luma(shirt) > 0.55 else (0.97, 0.97, 0.97)
    gfx.lighting(False)
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
    gfx.lighting(True)


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


def _hair(style, colour, sway=0.0):
    """sway: degrees that long hair, ponytails and braids swing back and forth."""
    glColor3f(*colour)

    def at(x, y, z, sx, sy, sz, rx=0.0, swing=0.0):
        glPushMatrix()
        glTranslatef(x, y + sy / 2.0, z)
        if swing:
            glRotatef(swing, 1, 0, 0)
        glTranslatef(0.0, -sy / 2.0, 0.0)
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
    # A cap of hair over the crown, and the back of the head
    glPushMatrix()
    glTranslatef(0.0, 0.035 if style == 'buzz' else 0.045, 0.012)
    glScalef(1.0, 0.82 if style == 'buzz' else 0.92, 1.0)
    sphere(0.133 if style == 'buzz' else 0.142, 12)
    glPopMatrix()
    if style == 'quiff':
        at(0.0, 0.14, -0.07, 0.17, 0.08, 0.1, rx=-20.0)
    elif style == 'long':
        at(0.0, -0.2, 0.1, 0.26, 0.3, 0.08, swing=sway)
        for sx in (-1, 1):
            at(0.13 * sx, -0.15, 0.03, 0.035, 0.22, 0.16, swing=sway * 0.5)
    elif style == 'ponytail':
        glPushMatrix()
        glTranslatef(0.0, 0.06, 0.15)
        glRotatef(22.0 + sway * 1.5, 1, 0, 0)
        glRotatef(sway * 0.6, 0, 0, 1)
        P.limb(0.24, 0.035, 0.02, 8)
        glPopMatrix()
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
            at(-0.1 + 0.05 * i, -0.25, 0.11, 0.03, 0.3, 0.03, swing=sway * (0.8 + 0.1 * i))


def _head(lk, cols, mood='focused', cap=False, sway=0.0):
    """A head at the current origin, facing -z: face, hair, beard, extras."""
    gfx.material('skin')
    glColor3f(*cols['skin'])
    sphere(0.13)
    glPushMatrix()                              # nose and ears
    glTranslatef(0.0, -0.01, -0.128)
    glScalef(0.6, 1.0, 0.8)
    sphere(0.028, 8)
    glPopMatrix()
    for sx in (-1, 1):
        glPushMatrix()
        glTranslatef(0.128 * sx, 0.0, 0.0)
        glScalef(0.45, 1.0, 0.8)
        sphere(0.035, 8)
        glPopMatrix()
    _face(mood or 'focused')
    gfx.material('default')
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
        _hair(lk.get('hair', 'short'), cols['hair'], sway)
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
            glTranslatef(0.0, -0.06, -0.035)
            glScalef(1.0, 0.85 if beard == 'full' else 0.6, 0.95)
            sphere(0.122, 10)
        glPopMatrix()
    if lk.get('headband') and not cap:
        glColor3f(0.95, 0.95, 0.95)
        glPushMatrix()
        glTranslatef(0.0, 0.075, 0.0)
        glScalef(1.0, 0.18, 1.0)
        sphere(0.142, 12)
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
        gfx.lighting(False)
        glColor4f(0.5, 1.0, 0.7, 0.85)
        sphere(0.09, 10)
        gfx.lighting(True)
    elif kind == 'shirt':
        glRotatef(clock * 700.0 % 360.0, 0, 1, 0)
        glColor3f(*kit['shirt'])
        glTranslatef(0.16, 0.0, 0.0)
        box(0.3, 0.26, 0.02)
    elif kind == 'fingers':
        glColor3f(0.9, 0.9, 0.9)
        glTranslatef(0.0, -0.08, 0.0)
        box(0.05, 0.12, 0.03)


def _arm(joint, swing, spread, length, width, colour, hand, prop=None, clock=0.0, kit=None, sleeve=None,
         elbow=None):
    """Upper arm, elbow, forearm and hand. colour: the sleeve (or skin), hand:
    the skin or glove. sleeve: 'long' for a long-sleeved shirt."""
    glPushMatrix()
    glTranslatef(*joint)
    glRotatef(spread, 0, 0, 1)
    glRotatef(swing, 1, 0, 0)
    upper, fore = length * 0.48, length * 0.47
    skin = hand
    gfx.material('fabric')
    glColor3f(*colour)
    P.limb(upper * 0.55, width * 0.68, width * 0.6, 10, True, False)       # the sleeve
    gfx.material('skin' if sleeve != 'long' else 'fabric')
    glColor3f(*(skin if sleeve != 'long' else colour))
    P.limb(upper, width * 0.5, width * 0.42, 10, False, True)
    glTranslatef(0, -upper, 0)
    bend = elbow if elbow is not None else 12.0 + 0.35 * abs(swing) * (1.0 if abs(spread) < 100 else 0.2)
    glRotatef(min(120.0, bend), 1, 0, 0)
    P.limb(fore, width * 0.42, width * 0.34, 10, False, False)
    gfx.material('skin')
    glColor3f(*hand)
    glTranslatef(0, -fore - 0.04, 0)
    glPushMatrix()
    glScalef(0.8, 1.15, 0.55)
    sphere(width * 0.45, 8)
    glPopMatrix()
    if prop:
        _prop(prop, clock, kit)
    gfx.material('fabric')
    glPopMatrix()


def _leg(joint, swing, spread, cols, sock, socks_down, trousers=None, shorts=None, knee=None):
    """Thigh, knee, shin and boot, with the shorts' leg moving with the thigh."""
    glPushMatrix()
    glTranslatef(*joint)
    glRotatef(spread, 0, 0, 1)
    glRotatef(swing, 1, 0, 0)
    thigh, shin = 0.44, 0.42
    if knee is None:
        knee = 6.0 + max(0.0, -swing) * 0.85
    gfx.material('fabric')
    if trousers:
        glColor3f(*trousers)
        P.limb(thigh, 0.1, 0.085, 10)
    else:
        if shorts:
            glColor3f(*shorts)
            P.limb(0.2, 0.112, 0.104, 10, False, False)
        gfx.material('skin')
        glColor3f(*cols['skin'])
        P.limb(thigh, 0.088, 0.068, 10, False, True)
    glTranslatef(0, -thigh, 0)
    glRotatef(-min(130.0, knee), 1, 0, 0)
    gfx.material('fabric')
    if trousers:
        glColor3f(*trousers)
        P.limb(shin, 0.085, 0.07, 10, False, False)
    elif socks_down:
        gfx.material('skin')
        glColor3f(*cols['skin'])
        P.limb(shin * 0.7, 0.066, 0.055, 10, False, False)
        gfx.material('fabric')
        glColor3f(*sock)
        glPushMatrix()
        glTranslatef(0, -shin * 0.68, 0)
        P.limb(shin * 0.32, 0.07, 0.062, 10, False, False)
        glPopMatrix()
    else:
        glColor3f(*sock)
        P.limb(shin, 0.072, 0.058, 10, False, False)
    glColor3f(*cols['boots'])
    glTranslatef(0, -shin - 0.03, 0)
    _boot()
    glPopMatrix()


def _figure(x, z, yaw, kit, arms=(12.0, 12.0, 0.0, 0.0), legs=(0.0, 0.0), jump=0.0, hips=0.0,
            pitch=0.0, height=0.0, face=None, head=0.0, bend=0.0, fig=None, mood='focused', spread=0.0,
            roll=0.0, head_pitch=0.0, torso=None, props=None, clock=0.0, pivot=0.0, collar=False,
            knees=(None, None), elbows=(None, None), dirt_key=None, sway=0.0, speed=0.0):
    """A standing outfield figure. arms: right and left spread about z, right
    and left swing about x. fig: a character's look, name and number."""
    fig = fig or {}
    lk = fig.get('look') or {}
    cols = _cols(lk)
    if face is not None and not lk:
        cols['skin'] = face
    props = props or {}
    gfx.set_dirt(dirt(dirt_key))
    gfx.material('fabric')
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
    _leg((0.11, 0.92, 0), legs[0], spread, cols, sock, lk.get('socks') == 'down', trousers, kit['shorts'], knees[0])
    _leg((-0.11, 0.92, 0), legs[1], -spread, cols, sock, lk.get('socks') == 'down', trousers, kit['shorts'],
         knees[1])
    gfx.material('fabric')
    glColor3f(*(trousers or kit['shorts']))
    glPushMatrix()
    glTranslatef(0, 0.97, 0)
    P.rounded_trunk(0.16, 0.2, 0.215, 0.13, 14)
    glPopMatrix()
    glRotatef(hips, 0, 1, 0)            # the upper body opens up towards the target
    if bend:
        glTranslatef(0, 1.03, 0)        # bend at the waist (placing the ball)
        glRotatef(-bend, 1, 0, 0)
        glTranslatef(0, -1.03, 0)
    shirt = torso or kit['shirt']
    gfx.material('skin' if torso else 'fabric')
    glColor3f(*shirt)
    glPushMatrix()
    glTranslatef(0, 1.3, 0)
    P.rounded_trunk(0.6, 0.2, 0.245, 0.14, 16)
    # The shirt's hem flaps when running
    if not torso and speed > 0.2:
        flap = 3.0 * speed * math.sin(clock * 14.0)
        glPushMatrix()
        glTranslatef(0.0, -0.3, 0.0)
        glRotatef(flap, 1, 0, 0)
        glScalef(1.0, 1.0, 0.6)
        P.limb(0.05, 0.205, 0.21, 14, False, False)
        glPopMatrix()
    glPopMatrix()
    gfx.material('skin')
    glColor3f(*cols['skin'])
    glPushMatrix()
    glTranslatef(0, 1.68, 0)
    P.limb(0.08, 0.055, 0.06, 8, False, False)                     # neck
    glPopMatrix()
    gfx.material('fabric')
    if collar or lk.get('collar'):
        glColor3f(*kit['shirt'])
        for sx in (-1, 1):
            glPushMatrix()
            glTranslatef(0.08 * sx, 1.63, 0.0)
            box(0.1, 0.09, 0.2)
            glPopMatrix()
    elif not torso:
        glColor3f(*[c * 0.8 for c in kit['shirt']])                   # crew neck
        glPushMatrix()
        glTranslatef(0, 1.645, 0)
        glScalef(1.0, 0.35, 0.8)
        sphere(0.075, 10)
        glPopMatrix()
    if fig.get('number') is not None and torso is None:
        _shirt_text(fig.get('name'), fig['number'], kit['shirt'], 0.14)
        _shirt_text(None, fig['number'], kit['shirt'], 0.135, flip=True, number_y=1.42, small=True)
    glPushMatrix()
    glTranslatef(0, 1.78, 0)
    glRotatef(head, 0, 1, 0)            # where he is looking
    glRotatef(head_pitch, 1, 0, 0)
    _head(lk if lk else dict(DEFAULT_LOOK), cols, mood, sway=sway)
    glPopMatrix()
    spread_r, spread_l, swing_r, swing_l = arms
    sleeve = cols['skin'] if torso else kit['shirt']
    sl = None if torso else lk.get('sleeves')
    _arm((0.27, 1.55, 0), swing_r, spread_r, 0.62, 0.12, sleeve, cols['skin'], props.get('r'), clock, kit, sl,
         elbows[0])
    _arm((-0.27, 1.55, 0), swing_l, -spread_l, 0.62, 0.12, sleeve, cols['skin'], props.get('l'), clock, kit, sl,
         elbows[1])
    if lk.get('armband'):
        gfx.material('fabric')
        glColor3f(0.95, 0.75, 0.15)
        glPushMatrix()
        glTranslatef(-0.27, 1.55, 0)
        glRotatef(-spread_l, 0, 0, 1)
        glRotatef(swing_l, 1, 0, 0)
        glTranslatef(0, -0.2, 0)
        glScalef(1.0, 0.45, 1.0)
        sphere(0.07, 10)
        glPopMatrix()
    gfx.material('default')
    gfx.set_dirt(0.0)
    glPopMatrix()


# Heat-haze sources gathered while drawing (world position, strength); the
# app projects them to the screen for the post-processing pass
effects = dict(haze=[])
# Marks left on the pitch this match: divots kicked up by slips and footprints in the snow
_marks = dict(divots=[], prints=[], foot=[0])


def draw_aura(x, z, aura, glow, clock, height=1.9, era=None, moving=False):
    """Aura: light pooling on the grass, rings, sparks trailing upwards and,
    for the strongest, a heat haze. Legends shimmer gold, most of all on the walk."""
    if gfx.shadow_pass() or not aura or aura < 0.3:
        return
    r, g, b = glow or (1.0, 0.82, 0.3)
    gfx.lighting(False)
    gfx.material('emissive', emit=1.0)
    glDepthMask(GL_FALSE)
    glBlendFunc(GL_SRC_ALPHA, GL_ONE)
    pulse = 0.5 + 0.5 * math.sin(clock * 3.0)
    fancy = gfx.fancy()
    if fancy:
        # The glow lights the grass round the player's feet
        P.soft_disc(x, z, 1.25 + 0.2 * pulse, (r, g, b), (0.2 + 0.1 * pulse) * aura, 0.025, 28)
    for k, rad in enumerate((0.55, 0.75)):
        glColor4f(r, g, b, (0.18 + 0.12 * pulse) * aura / (k + 1))
        glBegin(GL_TRIANGLE_STRIP)
        for i in range(33):
            a = 2 * math.pi * i / 32
            for rr in (rad - 0.08, rad + 0.08 * (1 + pulse)):
                glVertex3f(x + rr * math.cos(a), 0.03, z + rr * math.sin(a))
        glEnd()
    n = int(6 + (34 if fancy else 18) * aura)

    def spark(i, ph):
        ang = i * 2.4 + clock * 0.8 + ph * 1.5
        rad = (0.3 + 0.18 * math.sin(i * 1.7)) * (1.0 - 0.35 * ph)
        return x + rad * math.cos(ang), 0.1 + ph * height * 1.15, z + rad * math.sin(ang)

    if fancy:
        # Each spark leaves a fading trail behind it
        glLineWidth(2.0)
        glBegin(GL_LINES)
        for i in range(n):
            ph = (clock * (0.35 + 0.1 * (i % 3)) + i * 0.618) % 1.0
            a = (1.0 - ph) * 0.55 * aura
            glColor4f(r, g, b, a)
            glVertex3f(*spark(i, ph))
            glColor4f(r, g, b, 0.0)
            glVertex3f(*spark(i, max(0.0, ph - 0.09)))
        glEnd()
        glLineWidth(1.0)
    gfx.round_points(True)
    glPointSize(6.0 if fancy else 5.0)
    glBegin(GL_POINTS)
    for i in range(n):
        ph = (clock * (0.35 + 0.1 * (i % 3)) + i * 0.618) % 1.0
        glColor4f(min(1.0, r + 0.2), min(1.0, g + 0.2), min(1.0, b + 0.2), (1.0 - ph) * 0.8 * aura)
        glVertex3f(*spark(i, ph))
    glEnd()
    if era == 'legend':
        # Gold glints spiralling up the body
        shimmer = 1.0 if moving else 0.55
        glPointSize(4.0)
        glBegin(GL_POINTS)
        for i in range(14):
            ph = (clock * 0.5 + i / 14.0) % 1.0
            ang = ph * 9.0 + i
            tw = max(0.0, math.sin(clock * 9.0 + i * 2.3))
            glColor4f(1.0, 0.86, 0.4, tw * shimmer * (1.0 - abs(ph - 0.5) * 1.6))
            glVertex3f(x + 0.34 * math.cos(ang), 0.2 + ph * height, z + 0.34 * math.sin(ang))
        glEnd()
    glPointSize(1.0)
    gfx.round_points(False)
    glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
    glDepthMask(GL_TRUE)
    gfx.material('default')
    gfx.lighting(True)
    if aura > 0.7 and fancy:
        effects['haze'].append(((x, height * 0.6, z), (aura - 0.6) * 1.5))


def _divot(x, z, clock):
    """A slip tears up the turf at the plant foot."""
    for d in _marks['divots']:
        if abs(d[0] - x) < 0.4 and abs(d[1] - z) < 0.4:
            return
    _marks['divots'].append((x, z, clock))


def draw_marks(clock, weather):
    """Divots (and clods flying for a moment) and footprints in the snow."""
    if gfx.shadow_pass():
        return
    gfx.lighting(False)
    glDepthMask(GL_FALSE)
    for x, z, t0 in _marks['divots']:
        P.soft_disc(x, z, 0.32, (0.24, 0.16, 0.08), 0.85, 0.022, 14, 1.4)
    if weather == 'snow':
        for x, z, yaw in _marks['prints']:
            glPushMatrix()
            glTranslatef(x, 0, z)
            glRotatef(yaw, 0, 1, 0)
            glScalef(0.55, 1.0, 1.0)
            P.soft_disc(0.0, 0.0, 0.13, (0.55, 0.6, 0.72), 0.6, 0.026, 10)
            glPopMatrix()
    glDepthMask(GL_TRUE)
    gfx.lighting(True)
    gfx.material('default')
    for x, z, t0 in _marks['divots']:
        age = clock - t0
        if not 0.0 <= age < 1.1:
            continue
        for k in range(6):
            a = k * 1.05 + x
            v = 1.6 + 0.4 * (k % 3)
            px = x + math.cos(a) * 0.5 * age
            pz = z + math.sin(a) * 0.5 * age - 0.8 * age
            py = max(0.03, v * age - 4.9 * age * age)
            glColor3f(0.28, 0.2, 0.1) if k % 2 else glColor3f(0.2, 0.42, 0.14)
            glPushMatrix()
            glTranslatef(px, py, pz)
            glRotatef(age * 500.0 + k * 40, 1, 0.3, 0)
            box(0.09, 0.04, 0.07)
            glPopMatrix()
    gfx.material('default')


def _footprint(x, z, yaw):
    prints = _marks['prints']
    if prints:
        lx, lz, _ = prints[-1]
        if (lx - x) ** 2 + (lz - z) ** 2 < 0.3:
            return
        for px, pz, _ in prints[-60:]:
            if (px - x) ** 2 + (pz - z) ** 2 < 0.05:
                return              # the same path again (a replay)
    _marks['foot'][0] ^= 1
    side = 0.12 if _marks['foot'][0] else -0.12
    a = math.radians(yaw)
    prints.append((x + side * math.cos(a), z - side * math.sin(a), yaw))
    del prints[:-400]


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
    running = bool(state['run'])
    swing = math.sin(state['run']) * 35.0 if running else 0.0
    kick = state['kick']
    mood = state['mood'] or ''
    fig = state.get('fig')
    if fig and fig.get('kit'):
        kit = dict(kit, shirt=fig['kit'])
    key = 'k:' + str((fig or {}).get('name') or 'kicker')
    right, plant = -swing, swing
    knee_r = knee_l = None
    if kick < 0:
        # Winding the leg back: the heel comes up behind, the plant leg straightens
        right = 70.0 * kick
        knee_r = 25.0 + 85.0 * -kick
        plant = swing * (1.0 + kick)
        knee_l = 10.0 + 14.0 * -kick
    elif kick:
        right = 85.0 * kick
        knee_r = 30.0 * (1.0 - kick) + 4.0
        plant, knee_l = 0.0, 16.0                     # the planted foot sticks
    arms = (12.0, 12.0, swing * 0.8, -swing * 0.8)
    yaw, jump, pitch, height = state['yaw'], state.get('jump', 0.0), 0.0, 0.0
    extra = dict(spread=0.0, roll=0.0, head_pitch=0.0, torso=None, props=None, pivot=0.0, collar=False)
    follow = state.get('follow')
    if kick and follow is not None and 0.12 < follow < 0.9 and not mood:
        # Follow-through: the leg carries on up across the body, the arms
        # fling out for balance and the body leans back
        carry = math.sin(math.pi * min(1.0, (follow - 0.12) / 0.78))
        right = 85.0 + 35.0 * carry
        knee_r = 6.0 + 20.0 * carry
        arms = (40.0 + 35.0 * carry, 55.0 + 25.0 * carry, -10.0 * carry, 25.0 * carry)
        pitch = -7.0 * carry
        extra['roll'] = 5.0 * carry * (-1 if state.get('left_foot') else 1)
    if kick < -0.2 and not mood:
        # The arm opposite the kicking leg swings out wide
        arms = (12.0 + 40.0 * -kick, 12.0 + 18.0 * -kick, -25.0 * -kick, 35.0 * -kick)
    legs, knees = (right, plant), (knee_r, knee_l)
    if state.get('left_foot'):
        legs, knees = (plant, right), (knee_l, knee_r)
        arms = (arms[1], arms[0], arms[3], arms[2])
    face = state.get('face', 'focused')
    style = None
    if mood == 'slip':
        # Plant foot goes from under him: falls back on his backside
        pitch, height = -55.0, -0.55
        legs = (-80.0, -60.0)
        knees = (20.0, 35.0)
        arms = (60.0, 60.0, -30.0, -30.0)
        face = 'gutted'
        dirt(key, dirt(key) + 0.5 if not _divot_known(x, z) else None)
        _divot(x, z - 0.2, clock)
    elif mood.startswith('celebrate'):
        style = mood.split(':', 1)[1] if ':' in mood else 'knee slide'
        p = _celebration(style, state.get('cel_t', 1.0), clock)
        arms, legs, jump, pitch, height, yaw = p['arms'], p['legs'], p['jump'], p['pitch'], p['height'], p['yaw']
        knees = (None, None)
        extra.update(spread=p['spread'], roll=p['roll'], head_pitch=p['head_pitch'], props=p['props'],
                     pivot=p['pivot'], collar=p['collar'], torso=BASE_LAYER if p['torso'] else None)
        face = 'calm' if style in CALM else 'shout' if style in SHOUT else 'grin'
        dist = RUNNING.get(style)
        if dist:
            z += dist * min(1.0, state.get('cel_t', 1.0) / 1.6)          # runs towards the camera
        if style == 'knee slide' and _env['weather'] in ('rain', 'snow'):
            dirt(key, 0.45)                                              # grass stains up the shorts
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
    if _env['weather'] == 'rain' and (running or kick):
        dirt(key, 0.12)
    # Blend into the new pose rather than snapping (spins and flips stay exact)
    if style not in ('siuu', 'backflip'):
        blended = _ease(key, legs + arms + (pitch,), clock, 30.0 if kick else 16.0)
        legs, arms, pitch = blended[0:2], blended[2:6], blended[6]
    # Gaze: staring the keeper down, or eyes on the ball and away from him
    head = {'away': 75.0, 'stare': 0.0}.get(state.get('gaze'), 0.0)
    if _env['weather'] == 'snow' and running:
        _footprint(x, z, yaw)
    sway = swing * 0.25 + 6.0 * _env.get('wind', 0.0) * math.sin(clock * 2.3)
    if fig:
        draw_aura(x, z, fig.get('aura', 0.0), fig.get('glow'), clock, era=fig.get('era'), moving=running)
    draw_shadow(x, z, 0.45)
    _figure(x, z, yaw, kit, arms, legs, jump, state.get('hips', 0.0), pitch, height, head=head,
            bend=55.0 * state.get('bend', 0.0), fig=fig, mood=face, clock=clock, knees=knees, dirt_key=key,
            sway=sway, speed=1.0 if running else 0.0, **extra)
    if style == 'shirt show' and fig:
        # The shirt held up to the fans, name and number showing
        glPushMatrix()
        glTranslatef(x, jump + height, z)
        glRotatef(yaw, 0, 1, 0)
        glTranslatef(0.0, 0.0, -0.5)
        gfx.material('fabric')
        glColor3f(*kit['shirt'])
        glPushMatrix()
        glTranslatef(0.0, 1.38, 0.0)
        box(0.52, 0.6, 0.02)
        glPopMatrix()
        gfx.material('default')
        _shirt_text(fig.get('name'), fig.get('number'), kit['shirt'], 0.015, flip=True, number_y=1.16, name_y=1.48)
        glPopMatrix()


def _divot_known(x, z):
    return any(abs(d[0] - x) < 0.4 and abs(d[1] - (z - 0.2)) < 0.4 for d in _marks['divots'])


SAVE_MOODS = {'dance', 'scorpion', 'roar', 'star', 'shimmy', 'shush', 'wag', 'float', 'arms wide', 'point sky'}


def draw_keeper(pose, colour, clock, mood=None, first_person=False, scale=1.0, point=0, fig=None, face='focused',
                idle=None, sunny=False, key='keeper'):
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
    roll = 0.0
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
    # A full-stretch dive lands and rolls on through, and muddies the kit
    if gfx.screen_pass():
        key += ':screen'
    if arms == 'dive' and y < 0.33 and abs(lean) > 84.0 and not mood:
        t0 = _landed.get(key)
        if t0 is None or clock < t0:
            _landed[key] = t0 = clock
            wet = _env['weather'] in ('rain', 'snow')
            dirt(key, dirt(key) + (0.35 if wet else 0.15))
        age = clock - t0
        e = min(1.0, age / 0.75)
        e = e * e * (3 - 2 * e)
        side = 1.0 if lean > 0 else -1.0
        roll = 360.0 * e * side
        x += side * 0.55 * e
        y += 0.1 * math.sin(math.pi * e)
    elif arms != 'dive':
        _landed.pop(key, None)
    gfx.set_dirt(dirt(key))
    draw_aura(x, z, fig.get('aura', 0.0), fig.get('glow'), clock, 1.7, era=fig.get('era'))
    draw_shadow(x, z, 0.5 if y < 1.2 else 0.35, 0.3)
    glPushMatrix()
    glTranslatef(x, y, z)
    glRotatef(-lean, 0, 0, 1)
    glRotatef(body_rx, 1, 0, 0)
    if roll:
        glRotatef(roll, 0, 1, 0)                 # roll about the body's own length
    h, w = lk.get('h', 1.0), lk.get('w', 1.0)
    sx, sy = scale * w, scale * h
    if sx != 1.0 or sy != 1.0:
        glScalef(sx, sy, sx)
    shorts = (0.1, 0.1, 0.12)
    gfx.material('fabric')
    glColor3f(*colour)
    glPushMatrix()
    glTranslatef(0, 0.25, 0)
    P.rounded_trunk(0.62, 0.21, 0.255, 0.145, 16)
    glPopMatrix()
    # Padded elbows and a collar: a keeper's jersey
    glColor3f(*[c * 0.82 for c in colour])
    glPushMatrix()
    glTranslatef(0, 0.565, 0)
    glScalef(1.0, 0.35, 0.85)
    sphere(0.085, 10)
    glPopMatrix()
    if fig.get('number') is not None:
        # Number on the front for the taker to see, name and number on the back
        _shirt_text(None, fig['number'], colour, 0.15, number_y=0.12)
        _shirt_text(fig.get('name'), fig['number'], colour, 0.15, flip=True, number_y=0.05, name_y=0.38)
    gfx.material('fabric')
    glColor3f(*shorts)
    glPushMatrix()
    glTranslatef(0, -0.1, 0)
    P.rounded_trunk(0.2, 0.21, 0.215, 0.14, 14)
    glPopMatrix()
    gfx.material('skin')
    glColor3f(*cols['skin'])
    glPushMatrix()
    glTranslatef(0, 0.6, 0)
    P.limb(0.06, 0.055, 0.06, 8, False, False)
    glPopMatrix()
    glPushMatrix()
    glTranslatef(0, 0.7, 0)
    glRotatef(180.0, 0, 1, 0)                    # he faces the taker (+z)
    sway = lean * 0.15 + 5.0 * _env.get('wind', 0.0) * math.sin(clock * 2.1)
    _head(lk if lk else dict(DEFAULT_LOOK, hair='short'), cols, face, cap=sunny, sway=sway)
    glPopMatrix()
    if leg_spread is not None:
        leg = leg_spread
    elif arms == 'block':
        leg = 18.0
    elif arms == 'dive':
        leg = 8.0
    else:
        leg = 10.0 + 4.0 * math.sin(clock * 6.4)
    gfx.material('fabric')
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
    r_arm, l_arm, r_x, l_x = _ease(key + ':arms', (r_arm, l_arm, r_x, l_x), clock, 22.0)
    _limb((0.28, 0.5, 0), r_x, r_arm, 0.62, 0.12, colour, gloves, end='glove')
    _limb((-0.28, 0.5, 0), l_x, l_arm, 0.62, 0.12, colour, gloves, end='glove')
    gfx.material('default')
    gfx.set_dirt(0.0)
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
        gfx.lighting(False)
        glColor3f(*((0.95, 0.85, 0.1) if card == 'yellow' else (0.9, 0.1, 0.1)))
        glPushMatrix()
        glTranslatef(rx + 0.3, 2.45, rz)
        glRotatef(yaw, 0, 1, 0)
        box(0.12, 0.17, 0.01)
        glPopMatrix()
        gfx.lighting(True)
    ax, az = C.GOAL_AREA_HALF_WIDTH, C.GOAL_LINE_Z + 0.3
    draw_shadow(ax, az, 0.42)
    _figure(ax, az, -90.0, AR_KIT, (12.0, 12.0, 20.0 * math.sin(clock * 0.8), 0.0))


def teammate_z():
    return C.GOAL_LINE_Z + 37.0      # the group arm in arm in the centre circle


def draw_teammates(colours, team_mood, kicker, clock, kits, bench=None, win=None, target=None):
    """Both squads on the halfway line, reacting to every kick. bench: the
    named team-mates' looks, numbers and names, when there is a squad. win:
    after the deciding kick the winners sprint on and pile on the hero at target."""
    bench = bench or {}
    for side, x0 in (('p1', -2.0), ('p2', 2.0)):
        figs = list(bench.get(side) or [])
        kit = kits.get(side) or dict(shirt=colours[side], shorts=(0.95, 0.95, 0.95))
        happy = None
        if team_mood is not None:
            k, scored = team_mood
            happy = scored if side == k else not scored
        if win is not None:
            happy = side == win['side']
        for i in range(5):
            if side == kicker and i == 0:
                continue                         # the kicker has left the group
            fig = figs.pop(0) if figs else None
            x = x0 + (i if side == 'p2' else -i) * 0.62
            z = teammate_z()
            yaw = 180.0
            jump = 0.0
            arms = (35.0, 35.0, 0.0, 0.0)        # arms round each other
            legs = (0.0, 0.0)
            pitch = 0.0
            run = 0.0
            if win is not None and happy and target is not None:
                # The sprint to the hero, then jumping on him
                spot = (target[0] + 0.75 * math.cos(i * 1.3 + (0.6 if side == 'p2' else 0.0)),
                        target[1] + 0.75 * math.sin(i * 1.3 + (0.6 if side == 'p2' else 0.0)))
                dur = 4.2 + 0.3 * i
                r = min(1.0, win['t'] / dur)
                e = r * r * (3 - 2 * r)
                yaw = math.degrees(math.atan2(-(spot[0] - x), -(spot[1] - z)))
                x, z = x + (spot[0] - x) * e, z + (spot[1] - z) * e
                if r < 1.0:
                    sw = 40.0 * math.sin(clock * 13.0 + i)
                    legs, arms, run = (sw, -sw), (25.0, 25.0, -sw, sw), 1.0
                    pitch = 8.0
                else:
                    jump = 0.3 * abs(math.sin(clock * 7.0 + i))
                    arms = (160.0, 160.0, 0.0, 0.0) if i % 2 else (60.0, 60.0, 90.0, 90.0)
                    pitch = 18.0 if i % 2 == 0 else 0.0
            elif happy:
                jump = 0.35 * abs(math.sin(clock * 7.0 + i))
                arms = (165.0, 165.0, 0.0, 0.0)
            elif happy is False:
                pitch = 25.0                     # heads down
                arms = (200.0, 200.0, 0.0, 0.0) if i % 2 else (12.0, 12.0, 0.0, 0.0)
            if run:
                draw_shadow(x, z, 0.42)
            _figure(x, z, yaw, kit, arms, legs, jump=jump, pitch=pitch, fig=fig, clock=clock, speed=run,
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
    set_lights(daytime)
    gfx.use_scene(dict(sky=_env['sky'], clock=clock, shadows=True))
    draw_static(daytime)
    x, z = 0.0, C.SPOT_Z
    yaw = (clock * 40.0) % 360.0
    if keeper:
        glPushMatrix()
        glTranslatef(x, 0, z)
        glRotatef(yaw, 0, 1, 0)
        glTranslatef(-x, 0, -z)
        draw_keeper(((x, 0.95, z), 0.0, 'ready'), kit['keeper'], clock, mood=celebrate, fig=fig,
                    sunny=daytime == 'day', key='showcase')
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
    gfx.lighting(False)
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
    gfx.lighting(True)


_trail = dict(points=[], clock=None)


def draw_ball(pos, spin, orange=False, wobble=0.0, rocket=False, scuff=0.0, accent=(0.85, 0.12, 0.15), clock=0.0):
    """The ball: panels and the tournament design (painted by the shader),
    a knuckleball wobble, scuffs after the woodwork and a light trail on a rocket."""
    axis, angle = spin
    x, y, z = pos
    draw_shadow(x, z, 0.13 + 0.05 * min(1.0, y), max(0.08, 0.4 - 0.1 * y), 0.2 + y)
    _ball_trail(pos, rocket, clock)
    glPushMatrix()
    glTranslatef(x, y, z)
    if wobble:
        glRotatef(wobble * 40.0, 0, 0, 1)            # the knuckleball shudder
    glRotatef(angle, *axis)
    white = (1.0, 0.45, 0.05) if orange else (0.97, 0.97, 0.97)    # orange ball in the snow
    r = C.BALL_RADIUS
    if gfx.shaders() and not gfx.shadow_pass():
        gfx.material('ball', scuff=scuff, accent=accent)
        glColor3f(*white)
        sphere(r, 24)
        gfx.material('default')
    else:
        glColor3f(*white)
        sphere(r, 18)
        glColor3f(0.08, 0.08, 0.1)
        for p in _PANELS:
            glPushMatrix()
            glTranslatef(p[0] * r * 0.72, p[1] * r * 0.72, p[2] * r * 0.72)
            sphere(r * 0.33, 8)
            glPopMatrix()
    glPopMatrix()


def _ball_trail(pos, rocket, clock):
    """A streak of light behind a rocket of a shot."""
    pts = _trail['points']
    if _trail['clock'] is None or clock < _trail['clock'] or clock - _trail['clock'] > 0.2 or not rocket:
        pts[:] = []
    _trail['clock'] = clock
    if not rocket or gfx.shadow_pass():
        return
    if not pts or sum((a - b) ** 2 for a, b in zip(pts[-1], pos)) > 0.01:
        pts.append(tuple(pos))
    del pts[:-14]
    if len(pts) < 2:
        return
    gfx.lighting(False)
    gfx.material('emissive', emit=1.8)
    glDepthMask(GL_FALSE)
    glBlendFunc(GL_SRC_ALPHA, GL_ONE)
    for width, a0 in ((7.0, 0.25), (2.5, 0.8)):
        glLineWidth(width)
        glBegin(GL_LINE_STRIP)
        for i, p in enumerate(pts):
            glColor4f(1.0, 0.85, 0.45, a0 * i / (len(pts) - 1))
            glVertex3f(*p)
        glEnd()
    glLineWidth(1.0)
    glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
    glDepthMask(GL_TRUE)
    gfx.material('default')
    gfx.lighting(True)


def draw_bins(bins, clock):
    """Top Bins challenge: hoops hung in the top corners."""
    gfx.lighting(False)
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
    gfx.lighting(True)


def draw_preview(preview):
    """Training: dotted path of the shot as aimed, and a ring for how far it may stray."""
    pts = preview['points']
    if not pts:
        return
    gfx.lighting(False)
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
    gfx.lighting(True)


ENV_DEFAULTS = dict(weather='clear', daytime='night', end_colour=(0.85, 0.12, 0.15), crowd='calm',
                    tension=False, flares=False, tifo=False, wind=0.0, preview=None,
                    first_person=False, kits=None, officials=True, variant='stadium', bins=None, managers=False,
                    theme='classic', dusk=0.0, match=None, wear=0.4, snow=0.0, wet=0.0, flash=None, screen=None,
                    leaving=0.0, stand=False, phones=False, win=None, glt=None, wood=None, roof=0.0,
                    team_colours=None, eye=None)


def scene_uniforms(env, clock):
    """Per-frame settings for the scene shader."""
    return dict(sky=_env['sky'], wet=env['wet'], snow=env['snow'], wear=env['wear'],
                mow=0.16 if env['daytime'] == 'day' else 0.1, clock=clock, shadows=True)


def prepare(env):
    """Set up the time of day and weather for a frame, before any pass."""
    env = dict(ENV_DEFAULTS, **(env or {}))
    new_match(env['match'])
    set_environment(env['daytime'], env['weather'], env['dusk'])
    _env['wind'] = env['wind']
    _env['eye'] = env['eye']
    effects['haze'] = []
    return env


def _win_target(view, win):
    if win is None:
        return None
    if win['on'] == 'kicker':
        return view['shooter']['pos']
    (kx, ky, kz), _, _ = view['keeper']
    return (kx, kz + 0.4)


def draw_casters(view, env):
    """What throws a shadow from the key light: the players, the goal frame and the ball."""
    env = dict(ENV_DEFAULTS, **(env or {}))
    clock = view['clock']
    draw_goal(view['net'], clock)
    if not view.get('no_keeper') and not env['first_person']:
        draw_keeper(view['keeper'], view['keeper_colour'], clock, view.get('keeper_mood'), False,
                    view.get('keeper_scale', 1.0), view.get('keeper_point', 0), fig=view.get('keeper_fig'),
                    face=view.get('keeper_face', 'focused'), idle=view.get('keeper_idle'))
    draw_kicker(view['shooter'], view['kicker_kit'], clock)
    if env['officials']:
        card = view.get('card')
        draw_officials(card[0] if card else None, clock)
    if env['win'] is not None:
        draw_teammates(view['team_colours'], view.get('team_mood'), view['kicker'], clock, env['kits'] or {},
                       view.get('bench'), env['win'], _win_target(view, env['win']))
    draw_ball(view['ball'], view['spin'], clock=clock)


def draw_scene(view, aim=None, clock=0.0, env=None, screen=False):
    """Everything in the world for the current camera. screen: this is the
    big screen's own picture (no big screen in it, fewer extras)."""
    env = dict(ENV_DEFAULTS, **(env or {}))
    weather, daytime, dusk, theme = env['weather'], env['daytime'], env['dusk'], env['theme']
    vclock = view['clock']
    set_lights(daytime)
    gfx.use_scene(scene_uniforms(env, vclock))
    draw_static(daytime, theme)
    team_colours = env['team_colours'] or view['team_colours']
    if C.VARIANT == 'stadium':
        flash = env['flash']
        stadium.draw_boards(vclock, flash, team_colours)
        if not screen:
            stadium.draw_big_screen(theme, env['screen'], vclock)
        if theme == 'arena':
            stadium.draw_arena_ribbon(vclock, env['end_colour'])
            stadium.draw_arena_roof(env['roof'])
        stadium.draw_corner_flags(vclock, env['wind'])
    stadium.draw_floodlights(daytime, dusk, weather, vclock, env['eye'])
    crowd = 'stand' if env['stand'] and env['crowd'] in ('calm', 'wave') else env['crowd']
    draw_end_crowd(env['end_colour'], crowd, vclock, env['leaving'])
    draw_flags(env['end_colour'], vclock, env['wind'])
    if env['tifo']:
        draw_tifo(env['end_colour'])
    lit = daytime != 'day' and (daytime == 'night' or dusk > 0.4)
    if lit and (env['tension'] or env['flares']):
        draw_torches(vclock, env['flares'])
    if env['phones']:
        draw_phone_flashes(vclock)
    draw_ground_cover(weather, env['snow'])
    draw_marks(vclock, weather)
    ball = view['ball']
    draw_goal(view['net'], vclock, ball, env['wet'], env['wood'])
    if env['glt'] is not None:
        draw_glt(env['glt'], vclock)
    kits = env['kits'] or {}
    win = env['win']
    draw_teammates(view['team_colours'], view.get('team_mood'), view['kicker'], vclock, kits,
                   view.get('bench'), win, _win_target(view, win))
    if env.get('managers'):
        draw_managers(view.get('team_mood') if win is None else (win['side'], True), vclock)
    if view.get('captain') and kits.get(view['kicker']):
        draw_captain(view['captain'], kits[view['kicker']], vclock)
    if kits.get(view['kicker']):
        draw_waiting_keeper(kits[view['kicker']].get('keeper', (0.2, 0.2, 0.25)))
    if env['officials']:
        card = view.get('card')
        draw_officials(card[0] if card else None, vclock)
    if not view.get('no_keeper'):
        draw_keeper(view['keeper'], view['keeper_colour'], vclock, view.get('keeper_mood'),
                    env['first_person'], view.get('keeper_scale', 1.0), view.get('keeper_point', 0),
                    fig=view.get('keeper_fig'), face=view.get('keeper_face', 'focused'),
                    idle=view.get('keeper_idle'), sunny=daytime == 'day' and weather == 'clear')
    if env['bins']:
        draw_bins(env['bins'], vclock)
    draw_kicker(view['shooter'], view['kicker_kit'], vclock)
    accent = team_colours.get(view['kicker'], (0.85, 0.12, 0.15)) if team_colours else (0.85, 0.12, 0.15)
    draw_ball(ball, view['spin'], orange=weather == 'snow', wobble=view.get('wobble', 0.0),
              rocket=view.get('rocket', False) and not screen, scuff=view.get('scuff', 0.0), accent=accent,
              clock=vclock)
    if env['preview']:
        draw_preview(env['preview'])
    if aim is not None:
        draw_reticle(aim, clock)
    if theme == 'derby' or env['flares']:
        draw_smoke(vclock, env['end_colour'], env['wind'], env['flares'])
    if win is not None:
        draw_confetti(win, vclock)
        draw_fireworks(win, vclock)
    if not screen:
        (kx, ky, kz), _, _ = view['keeper']
        sx, sz = view['shooter']['pos']
        draw_weather(weather, vclock, env['wind'], ball, ((kx, ky + 0.8, kz), (sx, 1.9, sz)))
