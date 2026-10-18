"""The stadium round the pitch: tiers and roofs for each ground, the
dugouts and tunnel, the LED boards, the big screen, floodlights and their
beams, and the corner flags."""

import math
import random

from OpenGL.GL import *  # noqa: F401,F403
from OpenGL.GLUT import *  # noqa: F401,F403

from . import config as C, gfx
from .prims import box, cylinder_between, disc, flat_quad

THEMES = ['classic', 'derby', 'terrace', 'arena', 'nordic']
THEME_LABELS = {'classic': 'Classic bowl', 'derby': 'Derby night', 'terrace': 'Old terraces',
                'arena': 'Future arena', 'nordic': 'Nordic winter'}
# Colours of the concrete, steel and roofs for each ground
STYLE = {
    'classic': dict(steps=(0.22, 0.24, 0.3), steel=(0.42, 0.44, 0.48), roof=(0.55, 0.57, 0.62), tiers=2),
    'derby': dict(steps=(0.16, 0.16, 0.19), steel=(0.25, 0.25, 0.28), roof=(0.2, 0.2, 0.23), tiers=2),
    'terrace': dict(steps=(0.36, 0.34, 0.31), steel=(0.3, 0.32, 0.3), roof=(0.33, 0.36, 0.34), tiers=1),
    'arena': dict(steps=(0.75, 0.77, 0.82), steel=(0.85, 0.87, 0.9), roof=(0.9, 0.92, 0.95), tiers=2),
    'nordic': dict(steps=(0.38, 0.27, 0.18), steel=(0.3, 0.22, 0.15), roof=(0.92, 0.94, 0.98), tiers=1),
}
FLOODLIGHTS = ((-40.0, -30.0), (40.0, -30.0), (-46.0, 34.0), (46.0, 34.0))
SCREEN = dict(x=0.0, y=13.3, z=-31.0, w=12.0, h=4.0)
END_FRONT = C.GOAL_LINE_Z - 9.0
BOARD_Z = C.GOAL_LINE_Z - 6.0
WORDS = ['SHOOTOUT', 'PENALTY CUP', 'TOP BINS', 'PANENKA', 'SUDDEN DEATH', 'ICE COLD', 'BOTTLE NOTES']
LED_COLOURS = [(0.1, 0.25, 0.75), (0.8, 0.1, 0.14), (0.05, 0.55, 0.3), (0.95, 0.62, 0.05), (0.5, 0.15, 0.7)]


def style(theme):
    return STYLE.get(theme, STYLE['classic'])


# ------------------------------------------------------------- structures
def _tier(x1, x2, z_front, depth, rows, y0, rise, colour):
    """Steps of a tier facing +z (the pitch), front edge at z_front, going back to -z."""
    step_d = depth / rows
    glColor3f(*colour)
    for r in range(rows):
        h = y0 + r * rise
        glPushMatrix()
        glTranslatef((x1 + x2) / 2, h / 2, z_front - (r + 0.5) * step_d)
        box(x2 - x1, h, step_d)
        glPopMatrix()


def _fan_quad(x, y, z, shirt, face, rng):
    """A cheap fan for the upper tiers: a body and a head, both flat."""
    w = 0.36 + rng.random() * 0.06
    glColor3f(*shirt)
    glNormal3f(0, 0.3, 1)
    glVertex3f(x - w / 2, y, z)
    glVertex3f(x + w / 2, y, z)
    glVertex3f(x + w / 2, y + 0.55, z)
    glVertex3f(x - w / 2, y + 0.55, z)
    glColor3f(*face)
    glVertex3f(x - 0.1, y + 0.58, z + 0.01)
    glVertex3f(x + 0.1, y + 0.58, z + 0.01)
    glVertex3f(x + 0.1, y + 0.78, z + 0.01)
    glVertex3f(x - 0.1, y + 0.78, z + 0.01)


def upper_crowd(x1, x2, z_front, depth, rows, y0, rise, rng, shirts, faces, fill=0.88):
    """Rows of flat fans on an upper tier (a few thousand of them, cheaply)."""
    step_d = depth / rows
    glBegin(GL_QUADS)
    for r in range(rows):
        y = y0 + r * rise
        z = z_front - (r + 0.5) * step_d + 0.12
        x = x1 + 0.3
        while x < x2 - 0.3:
            if rng.random() < fill:
                _fan_quad(x, y, z, shirts(rng), rng.choice(faces), rng)
            x += 0.5 + rng.random() * 0.12
    glEnd()


def _roof(x1, x2, z_front, z_back, y_front, y_back, colour, supports=True, steel=(0.4, 0.4, 0.45)):
    glColor3f(*colour)
    glBegin(GL_QUADS)
    glNormal3f(0, -1, 0)
    glVertex3f(x1, y_front, z_front)
    glVertex3f(x2, y_front, z_front)
    glVertex3f(x2, y_back, z_back)
    glVertex3f(x1, y_back, z_back)
    glNormal3f(0, 1, 0)
    glVertex3f(x1, y_front + 0.25, z_front)
    glVertex3f(x1, y_back + 0.25, z_back)
    glVertex3f(x2, y_back + 0.25, z_back)
    glVertex3f(x2, y_front + 0.25, z_front)
    glEnd()
    glColor3f(*steel)
    glPushMatrix()
    glTranslatef((x1 + x2) / 2, y_front + 0.1, z_front)
    box(x2 - x1, 0.5, 0.3)                 # the fascia along the front
    glPopMatrix()
    if supports:
        x = x1 + 4.0
        while x < x2 - 2.0:
            cylinder_between((x, y_back - 8.0, z_back + 0.4), (x, y_back, z_back + 0.4), 0.18, 8)
            cylinder_between((x, y_back, z_back + 0.4), (x, y_front, z_front + 0.6), 0.09, 6)
            x += 9.0


def _barriers(x1, x2, z_front, depth, rows, y0, rise, colour):
    """Crush barriers on a standing terrace."""
    step_d = depth / rows
    glColor3f(*colour)
    for r in range(1, rows, 3):
        y = y0 + r * rise + 0.95
        z = z_front - r * step_d + 0.2
        cylinder_between((x1 + 1.0, y, z), (x2 - 1.0, y, z), 0.04, 6)
        x = x1 + 2.0
        while x < x2 - 1.0:
            cylinder_between((x, y - 0.95, z), (x, y, z), 0.035, 5)
            x += 3.5


def _pines(rng, count, x1, x2, z1, z2):
    """Snowy pine trees behind a Nordic ground."""
    for _ in range(count):
        x, z = rng.uniform(x1, x2), rng.uniform(z1, z2)
        h = rng.uniform(9.0, 15.0)
        glColor3f(0.3, 0.2, 0.12)
        cylinder_between((x, 0, z), (x, h * 0.25, z), 0.3, 6)
        for k, (y0, r) in enumerate(((0.2, 2.6), (0.45, 2.0), (0.68, 1.3))):
            glColor3f(*((0.08, 0.22, 0.14) if k % 2 == 0 else (0.86, 0.9, 0.95)))
            cylinder_between((x, h * y0, z), (x, h * (y0 + 0.36), z), r, 8, 0.05)


def _pylon(x, z, colour):
    """A lattice floodlight pylon, as at old grounds."""
    glColor3f(*colour)
    for dx, dz in ((-0.8, -0.8), (0.8, -0.8), (0.8, 0.8), (-0.8, 0.8)):
        cylinder_between((x + dx * 1.6, 0, z + dz * 1.6), (x + dx * 0.4, 25.5, z + dz * 0.4), 0.08, 5)
    for k in range(10):
        y = 1.0 + k * 2.5
        s = 1.6 - 1.2 * y / 25.5
        cylinder_between((x - s, y, z - s), (x + s, y + 2.5, z + s), 0.04, 4)
        cylinder_between((x + s, y, z - s), (x - s, y + 2.5, z + s), 0.04, 4)


def _ring_roof(colour, steel):
    """The future arena's roof: a ring of panels round an open middle."""
    glColor3f(*colour)
    glBegin(GL_QUADS)
    n = 36
    for i in range(n):
        a1, a2 = 2 * math.pi * i / n, 2 * math.pi * (i + 1) / n
        for (r1, r2, y1, y2) in ((62.0, 44.0, 22.0, 25.0),):
            p = [(r1 * math.cos(a1), y1, 5.0 + r1 * 0.8 * math.sin(a1)),
                 (r1 * math.cos(a2), y1, 5.0 + r1 * 0.8 * math.sin(a2)),
                 (r2 * math.cos(a2), y2, 5.0 + r2 * 0.8 * math.sin(a2)),
                 (r2 * math.cos(a1), y2, 5.0 + r2 * 0.8 * math.sin(a1))]
            glNormal3f(0, -1, 0)
            for v in p:
                glVertex3f(*v)
    glEnd()
    glColor3f(*steel)
    for i in range(0, 36, 3):
        a = 2 * math.pi * i / 36
        x, z = 62.0 * math.cos(a), 5.0 + 49.6 * math.sin(a)
        cylinder_between((x, 0.0, z), (x, 22.0, z), 0.5, 8)


def _dugouts(steel):
    """Two dugouts on the left touchline, and the tunnel between them."""
    for z in (8.0, 18.0):
        glColor3f(0.12, 0.13, 0.16)
        glPushMatrix()
        glTranslatef(-37.6, 0.9, z)
        box(1.6, 1.8, 6.0)                       # the back
        glPopMatrix()
        glColor3f(0.75, 0.82, 0.9)
        glBegin(GL_QUADS)                        # perspex canopy
        glNormal3f(0.4, 1, 0)
        glVertex3f(-36.8, 2.1, z - 3.0)
        glVertex3f(-36.8, 2.1, z + 3.0)
        glVertex3f(-35.2, 1.5, z + 3.0)
        glVertex3f(-35.2, 1.5, z - 3.0)
        glEnd()
        glColor3f(*((0.75, 0.12, 0.14) if z < 10 else (0.12, 0.3, 0.75)))
        for k in range(6):                       # the seats
            glPushMatrix()
            glTranslatef(-36.6, 0.45, z - 2.4 + k * 0.95)
            box(0.5, 0.5, 0.6)
            glPopMatrix()
    # The tunnel: a dark mouth with an inflatable concertina sleeve
    glColor3f(0.02, 0.02, 0.03)
    glPushMatrix()
    glTranslatef(-40.4, 1.4, 13.0)
    box(0.4, 2.8, 3.4)
    glPopMatrix()
    for k in range(4):
        glColor3f(*((0.85, 0.85, 0.88) if k % 2 == 0 else (0.15, 0.3, 0.7)))
        glPushMatrix()
        glTranslatef(-39.6 + k * 0.7, 1.6, 13.0)
        box(0.66, 3.2 - k * 0.1, 3.9 - k * 0.1)
        glPopMatrix()
    glColor3f(0.02, 0.02, 0.03)
    glPushMatrix()
    glTranslatef(-36.85, 1.5, 13.0)
    box(0.1, 2.6, 2.9)
    glPopMatrix()


def build_structure(theme, daytime, crowd_shirts, faces):
    """Everything that does not move, beyond the lower tiers built in render:
    upper tiers with their fans, roofs, pylons, trees and the dugouts.
    Returns two builders: structure (default material) and crowd."""
    st = style(theme)
    rng = random.Random(23)

    def shirts(r):
        return r.choice(crowd_shirts)

    def structure():
        steps, steel, roof = st['steps'], st['steel'], st['roof']
        if st['tiers'] == 2:
            _tier(-36.0, 36.0, END_FRONT - 14.0, 10.0, 8, 10.0, 0.8, steps)              # end, upper tier
            glPushMatrix()
            glRotatef(180.0, 0, 1, 0)
            _tier(-36.0, 36.0, -42.0, 10.0, 8, 10.0, 0.8, steps)                       # far stand, upper
            glPopMatrix()
            for s in (-1, 1):
                glPushMatrix()
                glTranslatef(s * 53.0, 0.0, -2.0)
                glRotatef(-90.0 * s, 0, 1, 0)
                _tier(-28.0, 28.0, 0.0, 10.0, 8, 10.0, 0.8, steps)
                glPopMatrix()
        top = 17.0 if st['tiers'] == 2 else 9.8
        if theme == 'arena':
            _ring_roof(roof, steel)
        else:
            # Roofs over the end and the sides (the terrace roofs sit low)
            fy = top + (3.5 if st['tiers'] == 2 else 2.0)
            _roof(-36.0, 36.0, END_FRONT - 3.0, END_FRONT - 25.0, fy, fy - 1.5, roof, True, steel)
            for s in (-1, 1):
                glPushMatrix()
                glTranslatef(s * 41.0, 0.0, -2.0)
                glRotatef(-90.0 * s, 0, 1, 0)
                _roof(-28.0, 28.0, -2.0, -24.0, fy, fy - 1.5, roof, True, steel)
                glPopMatrix()
            glPushMatrix()
            glRotatef(180.0, 0, 1, 0)
            _roof(-36.0, 36.0, -32.0, -54.0, fy, fy - 1.5, roof, True, steel)
            glPopMatrix()
        if theme == 'terrace':
            _barriers(-36.0, 36.0, END_FRONT, 14.0, 12, 1.0, 0.65, (0.55, 0.58, 0.55))
            for x, z in FLOODLIGHTS:
                _pylon(x, z, steel)
        else:
            for x, z in FLOODLIGHTS:
                glColor3f(*steel)
                cylinder_between((x, 0, z), (x, 26, z), 0.35, 10)
        if theme == 'nordic':
            _pines(random.Random(8), 40, -60.0, 60.0, -70.0, -48.0)
            for s in (-1, 1):
                _pines(random.Random(9 + s), 14, s * 58.0, s * 72.0, -40.0, 30.0)
        if theme in ('classic', 'derby', 'arena'):
            # The big screen's frame and the struts it hangs from
            glColor3f(0.08, 0.08, 0.1)
            glPushMatrix()
            glTranslatef(SCREEN['x'], SCREEN['y'], SCREEN['z'] - 0.3)
            box(SCREEN['w'] + 0.6, SCREEN['h'] + 0.6, 0.5)
            glPopMatrix()
            glColor3f(*steel)
            for sx in (-1, 1):
                cylinder_between((sx * SCREEN['w'] * 0.4, SCREEN['y'] + SCREEN['h'] / 2, SCREEN['z'] - 0.4),
                                 (sx * SCREEN['w'] * 0.4, top + 3.0, SCREEN['z'] - 3.0), 0.12, 6)
        elif theme == 'terrace':
            # An old hand-turned scoreboard on the end roof
            glColor3f(0.08, 0.2, 0.12)
            glPushMatrix()
            glTranslatef(0.0, 12.6, END_FRONT - 3.2)
            box(8.0, 2.4, 0.4)
            glPopMatrix()
        _dugouts(steel)

    def crowd():
        if st['tiers'] == 2:
            upper_crowd(-36.0, 36.0, END_FRONT - 14.0, 10.0, 8, 10.0, 0.8, rng, shirts, faces)
            glPushMatrix()
            glRotatef(180.0, 0, 1, 0)
            upper_crowd(-36.0, 36.0, -42.0, 10.0, 8, 10.0, 0.8, rng, shirts, faces)
            glPopMatrix()
            for s in (-1, 1):
                glPushMatrix()
                glTranslatef(s * 53.0, 0.0, -2.0)
                glRotatef(-90.0 * s, 0, 1, 0)
                upper_crowd(-28.0, 28.0, 0.0, 10.0, 8, 10.0, 0.8, rng, shirts, faces)
                glPopMatrix()

    return structure, crowd


# ---------------------------------------------------------------- moving parts
def _stroke_text(s, x, y, z, height, width=2.5, flip=False):
    units = sum(glutStrokeWidth(GLUT_STROKE_ROMAN, ord(ch)) for ch in s) or 1
    scale = height / 119.05
    glPushMatrix()
    glTranslatef(x, y, z)
    if flip:
        glRotatef(180.0, 0, 1, 0)
    glTranslatef(-units * scale / 2.0, 0.0, 0.0)
    glScalef(scale, scale, scale)
    glLineWidth(width)
    for ch in s:
        glutStrokeCharacter(GLUT_STROKE_ROMAN, ord(ch))
    glPopMatrix()
    glLineWidth(1.0)


def draw_boards(clock, flash=None, team_colours=None):
    """The LED boards behind the goal: colour panels with words scrolling
    along them, and a flashing GOAL! in the scorer's colours."""
    gfx.material('emissive', emit=1.25)
    gfx.lighting(False)
    x1, x2 = -30.0, 30.0
    goal = flash is not None and flash[1] < 4.0
    glBegin(GL_QUADS)
    n = 10
    for i in range(n):
        a = x1 + (x2 - x1) * i / n
        b = x1 + (x2 - x1) * (i + 1) / n
        if goal:
            on = int(flash[1] * 6.0 + i) % 2 == 0
            c = flash[0] if on else (0.95, 0.95, 0.95)
        else:
            palette = LED_COLOURS
            if team_colours and int(clock / 6.0) % 2:
                palette = list(team_colours.values())          # every other spell: the teams' colours
            c = palette[(i + int(clock / 6.0)) % len(palette)]
            k = 0.85 + 0.15 * math.sin(clock * 2.0 + i)
            c = (c[0] * k, c[1] * k, c[2] * k)
        glColor3f(*c)
        glVertex3f(a, 0.02, BOARD_Z + 0.08)
        glVertex3f(b, 0.02, BOARD_Z + 0.08)
        glVertex3f(b, 0.98, BOARD_Z + 0.08)
        glVertex3f(a, 0.98, BOARD_Z + 0.08)
    glEnd()
    glColor3f(1.0, 1.0, 1.0)
    if goal:
        col = (0.05, 0.05, 0.06) if sum(flash[0]) > 2.2 else (1.0, 1.0, 1.0)
        glColor3f(*col)
        for k in range(5):
            _stroke_text('GOAL!', x1 + 6.0 + k * 12.0, 0.22, BOARD_Z + 0.1, 0.6, 3.0)
    else:
        span = x2 - x1
        for k, word in enumerate(WORDS):
            pos = (k * span / len(WORDS) - clock * 2.2) % span
            centre = x1 + pos
            half = len(word) * 0.21
            if centre - half < x1 + 0.3 or centre + half > x2 - 0.3:
                continue
            _stroke_text(word, centre, 0.28, BOARD_Z + 0.1, 0.45, 2.5)
    gfx.lighting(True)
    gfx.material('default')
    glColor3f(0.08, 0.08, 0.1)
    glPushMatrix()
    glTranslatef(0.0, 0.5, BOARD_Z - 0.02)
    box(60.4, 1.04, 0.15)                         # the frame
    glPopMatrix()


def draw_big_screen(theme, info, clock):
    """The big screen over the end: the live picture (high quality) or the
    score and what is happening, in stroke text."""
    if theme not in ('classic', 'derby', 'arena'):
        if theme == 'terrace' and info:
            gfx.lighting(False)
            glColor3f(0.95, 0.95, 0.85)
            _stroke_text(info.get('score', ''), 0.0, 12.0, END_FRONT - 2.95, 0.9, 3.0)
            gfx.lighting(True)
        return
    x, y, z, w, h = SCREEN['x'], SCREEN['y'], SCREEN['z'], SCREEN['w'], SCREEN['h']
    if gfx.bind_screen_texture():
        gfx.material('screen')
        glColor3f(1, 1, 1)
        glBegin(GL_QUADS)
        glNormal3f(0, 0, 1)
        for (u, v) in ((0, 0), (1, 0), (1, 1), (0, 1)):
            glTexCoord2f(u, v)
            glVertex3f(x - w / 2 + u * w, y - h / 2 + v * h, z)
        glEnd()
        gfx.material('default')
        if info and info.get('banner'):
            gfx.lighting(False)
            glColor3f(1.0, 0.85, 0.2)
            _stroke_text(info['banner'], x, y - h / 2 + 0.2, z + 0.02, 0.5, 3.0)
            gfx.lighting(True)
        return
    gfx.material('emissive', emit=1.1)
    gfx.lighting(False)
    glColor3f(0.03, 0.06, 0.16)
    glBegin(GL_QUADS)
    glVertex3f(x - w / 2, y - h / 2, z)
    glVertex3f(x + w / 2, y - h / 2, z)
    glVertex3f(x + w / 2, y + h / 2, z)
    glVertex3f(x - w / 2, y + h / 2, z)
    glEnd()
    if info:
        glColor3f(1.0, 1.0, 1.0)
        _stroke_text(info.get('score', ''), x, y + 0.2, z + 0.02, 1.2, 3.5)
        banner = info.get('banner') or 'PENALTIES'
        pulse = 0.75 + 0.25 * math.sin(clock * 6.0) if info.get('banner') else 1.0
        glColor3f(1.0 * pulse, 0.85 * pulse, 0.2 * pulse)
        _stroke_text(banner, x, y - 1.4, z + 0.02, 0.7, 3.0)
    gfx.lighting(True)
    gfx.material('default')


def lit_banks(daytime, dusk):
    """Which floodlights are on: all at night, none by day, in banks at dusk."""
    if daytime == 'night':
        return [True] * 4
    if daytime == 'day':
        return [False] * 4
    return [dusk > 0.15 + 0.17 * k for k in (0, 2, 1, 3)]


def draw_floodlights(daytime, dusk, weather, clock, eye):
    """The lamp banks (glowing when on) and their beams in the damp air."""
    banks = lit_banks(daytime, dusk)
    gfx.material('emissive', emit=1.6)
    gfx.lighting(False)
    for (x, z), on in zip(FLOODLIGHTS, banks):
        glColor3f(*((1.0, 0.98, 0.88) if on else (0.5, 0.52, 0.56)))
        glPushMatrix()
        glTranslatef(x, 27.0, z)
        glRotatef(math.degrees(math.atan2(-x, 5.0 - z)), 0, 1, 0)
        glBegin(GL_QUADS)
        for i in range(4):
            for j in range(3):
                x0, y0 = -3.0 + i * 1.5, -1.5 + j * 1.0
                glVertex3f(x0 + 0.08, y0 + 0.08, 0.45)
                glVertex3f(x0 + 1.42, y0 + 0.08, 0.45)
                glVertex3f(x0 + 1.42, y0 + 0.92, 0.45)
                glVertex3f(x0 + 0.08, y0 + 0.92, 0.45)
        glEnd()
        glPopMatrix()
    gfx.material('default')
    damp = {'fog': 1.0, 'rain': 0.75, 'snow': 0.7}.get(weather, 0.28 if daytime != 'day' else 0.0)
    if damp > 0 and gfx.fancy():
        glDepthMask(GL_FALSE)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE)
        target = (0.0, 0.0, C.GOAL_LINE_Z + 12.0)
        for (x, z), on in zip(FLOODLIGHTS, banks):
            if not on:
                continue
            top = (x, 26.5, z)
            # A cone of light: fans of triangles from the lamp to a wide ellipse on the pitch
            dx, dz = target[0] - x, target[2] - z
            n = 18
            glBegin(GL_TRIANGLES)
            for i in range(n):
                a1, a2 = 2 * math.pi * i / n, 2 * math.pi * (i + 1) / n
                r = 13.0
                p1 = (x + dx * 0.75 + r * math.cos(a1), 0.0, z + dz * 0.75 + r * math.sin(a1))
                p2 = (x + dx * 0.75 + r * math.cos(a2), 0.0, z + dz * 0.75 + r * math.sin(a2))
                glColor4f(1.0, 0.97, 0.85, 0.07 * damp)
                glVertex3f(*top)
                glColor4f(1.0, 0.97, 0.85, 0.0)
                glVertex3f(*p1)
                glVertex3f(*p2)
            glEnd()
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glDepthMask(GL_TRUE)
    gfx.lighting(True)


def draw_corner_flags(clock, wind):
    """Corner flags at either end of the goal line, flapping in the wind."""
    strength = 1.0 + 1.2 * abs(wind)
    for k, x in enumerate((-34.0, 34.0)):
        z = C.GOAL_LINE_Z
        glColor3f(0.95, 0.95, 0.95)
        cylinder_between((x, 0.0, z), (x, 1.55, z), 0.025, 6)
        gfx.material('fabric')
        glColor3f(0.98, 0.85, 0.1)
        glBegin(GL_QUAD_STRIP)
        for j in range(7):
            u = j / 6.0
            sway = 0.12 * strength * u * math.sin(clock * 6.0 * strength - u * 5.0 + k)
            glNormal3f(0, 0, 1)
            glVertex3f(x + (0.45 * u if wind >= 0 else -0.45 * u), 1.2 + 0.03 * u, z + sway)
            glVertex3f(x + (0.45 * u if wind >= 0 else -0.45 * u), 1.52 - 0.03 * u, z + sway)
        glEnd()
        gfx.material('default')
        glColor3f(0.95, 0.95, 0.95)
        pts = []
        for i in range(9):
            a = math.pi / 2 * i / 8
            pts.append((x - math.copysign(1.0, x) * math.sin(a), z + math.cos(a)))
        glBegin(GL_LINE_STRIP)
        for px, pz in pts:
            glVertex3f(px, 0.013, pz)
        glEnd()


def draw_arena_ribbon(clock, colour):
    """The future arena's LED ribbon round the front of the stands."""
    gfx.material('emissive', emit=1.4)
    gfx.lighting(False)
    glBegin(GL_QUAD_STRIP)
    n = 48
    for i in range(n + 1):
        x = -36.0 + 72.0 * i / n
        k = 0.5 + 0.5 * math.sin(clock * 3.0 - i * 0.4)
        glColor3f(colour[0] * k + 0.1, colour[1] * k + 0.1, colour[2] * k + 0.2)
        glVertex3f(x, 9.1, END_FRONT - 13.9)
        glVertex3f(x, 9.6, END_FRONT - 13.9)
    glEnd()
    gfx.lighting(True)
    gfx.material('default')


def draw_arena_roof(closed):
    """The future arena's roof panels sliding shut over the pitch (in rain
    and snow), translucent so the floodlights still glow through."""
    if closed <= 0.01 or gfx.shadow_pass():
        return
    gfx.lighting(False)
    glDepthMask(GL_FALSE)
    glColor4f(0.75, 0.82, 0.9, 0.42)
    reach = 44.0 * min(1.0, closed)
    glBegin(GL_QUADS)
    for s in (-1, 1):
        x_out, x_in = s * 46.0, s * (46.0 - reach)
        for k in range(8):
            z1, z2 = -32.0 + k * 9.25, -32.0 + (k + 1) * 9.25
            glNormal3f(0, -1, 0)
            glVertex3f(x_out, 25.2, z1)
            glVertex3f(x_in, 25.2, z1)
            glVertex3f(x_in, 25.2, z2 - 0.4)
            glVertex3f(x_out, 25.2, z2 - 0.4)
    glEnd()
    glColor4f(0.9, 0.92, 0.95, 0.8)
    glBegin(GL_LINES)                            # the leading edge of each panel
    for s in (-1, 1):
        glVertex3f(s * (46.0 - reach), 25.2, -32.0)
        glVertex3f(s * (46.0 - reach), 25.2, 42.0)
    glEnd()
    glDepthMask(GL_TRUE)
    gfx.lighting(True)


def disc_marks(points, colour, alpha, r=0.12):
    """Small marks on the ground (footprints in the snow, divots)."""
    glDepthMask(GL_FALSE)
    for x, z in points:
        glColor4f(colour[0], colour[1], colour[2], alpha)
        disc(x, z, r, 0.018, 8)
    glDepthMask(GL_TRUE)


__all__ = ['THEMES', 'THEME_LABELS', 'build_structure', 'draw_boards', 'draw_big_screen', 'draw_floodlights',
           'draw_corner_flags', 'draw_arena_ribbon', 'draw_arena_roof', 'lit_banks', 'flat_quad']
