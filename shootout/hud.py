"""2D overlay: scoreboard, prompts, power bar, banners, menu and summary.

Drawn on a virtual 1000 x 800 canvas that stretches with the window.
"""

import math

from OpenGL.GL import *  # noqa: F401,F403
from OpenGL.GLU import *  # noqa: F401,F403
from OpenGL.GLUT import *  # noqa: F401,F403

from . import config as C, stats
from .game import CONTROLS

W, H = 1000.0, 800.0
SMALL = GLUT_BITMAP_HELVETICA_12
MEDIUM = GLUT_BITMAP_HELVETICA_18

GOLD = (1.0, 0.82, 0.2)
RED = (0.95, 0.25, 0.25)
GREEN = (0.25, 0.85, 0.35)
GREY = (0.5, 0.5, 0.55)
WHITE = (1.0, 1.0, 1.0)

KEY_NAMES = {' ': 'SPACE', '\r': 'ENTER'}


def begin():
    glDisable(GL_LIGHTING)
    glDisable(GL_DEPTH_TEST)
    glDisable(GL_FOG)
    glMatrixMode(GL_PROJECTION)
    glPushMatrix()
    glLoadIdentity()
    gluOrtho2D(0, W, 0, H)
    glMatrixMode(GL_MODELVIEW)
    glPushMatrix()
    glLoadIdentity()


def end():
    glPopMatrix()
    glMatrixMode(GL_PROJECTION)
    glPopMatrix()
    glMatrixMode(GL_MODELVIEW)
    glEnable(GL_DEPTH_TEST)
    glEnable(GL_LIGHTING)
    glEnable(GL_FOG)


def rect(x, y, w, h, colour, alpha=1.0):
    glColor4f(colour[0], colour[1], colour[2], alpha)
    glBegin(GL_QUADS)
    glVertex2f(x, y)
    glVertex2f(x + w, y)
    glVertex2f(x + w, y + h)
    glVertex2f(x, y + h)
    glEnd()


def outline(x, y, w, h, colour, width=2.0):
    glColor3f(*colour)
    glLineWidth(width)
    glBegin(GL_LINE_LOOP)
    glVertex2f(x, y)
    glVertex2f(x + w, y)
    glVertex2f(x + w, y + h)
    glVertex2f(x, y + h)
    glEnd()
    glLineWidth(1.0)


def circle(x, y, r, colour):
    glColor3f(*colour)
    glBegin(GL_TRIANGLE_FAN)
    glVertex2f(x, y)
    for i in range(21):
        a = 2 * math.pi * i / 20
        glVertex2f(x + r * math.cos(a), y + r * math.sin(a))
    glEnd()


def text_width(s, font=MEDIUM):
    return sum(glutBitmapWidth(font, ord(ch)) for ch in s)


def text(x, y, s, font=MEDIUM, colour=WHITE, align='left'):
    if align == 'center':
        x -= text_width(s, font) / 2.0
    elif align == 'right':
        x -= text_width(s, font)
    glColor3f(*colour)
    glRasterPos2f(x, y)
    for ch in s:
        glutBitmapCharacter(font, ord(ch))


def big_text(cx, y, s, size=40.0, colour=WHITE, width=4.0, shadow=True):
    """Scalable stroke text, centred on cx."""
    scale = size / 119.0
    total = sum(glutStrokeWidth(GLUT_STROKE_ROMAN, ord(ch)) for ch in s) * scale
    for dx, dy, col in (((3, -3, (0, 0, 0)),) if shadow else ()) + ((0, 0, colour),):
        glPushMatrix()
        glTranslatef(cx - total / 2 + dx, y + dy, 0)
        glScalef(scale, scale, 1)
        glLineWidth(width)
        glColor3f(*col)
        for ch in s:
            glutStrokeCharacter(GLUT_STROKE_ROMAN, ord(ch))
        glPopMatrix()
    glLineWidth(1.0)


def key_name(k):
    return KEY_NAMES.get(k, k.upper())


# ------------------------------------------------------------------ in match
def scoreboard(g):
    so = g.shootout
    x, y, w, h = 300, 700, 400, 92
    rect(x, y, w, h, (0.07, 0.08, 0.12), 0.88)
    rect(x, y + h - 5, w, 5, GOLD)
    for row, side in enumerate(('p1', 'p2')):
        ry = y + h - 30 - row * 32
        kit = C.KITS[side]['shirt']
        rect(x + 10, ry - 4, 8, 22, kit)
        text(x + 26, ry, g.name(side), SMALL, WHITE)
        results = so.results[side]
        n = so.kicks_per_side
        shown = list(results[:n])
        extra = results[n:]
        for i in range(n):
            col = GREY if i >= len(shown) else (GREEN if shown[i] else RED)
            circle(x + 130 + i * 22, ry + 5, 7, col)
        if extra:
            sd = extra[-5:]
            for i, r in enumerate(sd):
                circle(x + 130 + n * 22 + 14 + i * 18, ry + 5, 6, GREEN if r else RED)
        text(x + w - 18, ry - 2, str(so.goals(side)), MEDIUM, GOLD, 'right')
        if g.phase in ('aim', 'runup', 'flight') and g.kicker == side:
            circle(x + w - 40, ry + 5, 4, GOLD)
    label = f"{'PvC ' + g.difficulty.capitalize() if g.mode == 'pvc' else 'PvP'}"
    if so.in_sudden_death():
        label += '  |  SUDDEN DEATH'
    text(x + w / 2, y + 6, label, SMALL, (0.8, 0.8, 0.85), 'center')


def power_bar(g):
    x, y, w, h = 350, 60, 300, 22
    rect(x - 4, y - 4, w + 8, h + 8, (0.05, 0.05, 0.08), 0.85)
    rect(x, y, w, h, (0.25, 0.25, 0.3))
    rect(x + w * C.POWER_SWEET_LOW, y, w * (C.POWER_SWEET_HIGH - C.POWER_SWEET_LOW), h, (0.2, 0.6, 0.25))
    rect(x + w * C.POWER_SWEET_HIGH, y, w * (1 - C.POWER_SWEET_HIGH), h, (0.65, 0.2, 0.15))
    p = g.power_value()
    rect(x, y + 6, w * p, h - 12, GOLD)
    glColor3f(1, 1, 1)
    glLineWidth(3)
    glBegin(GL_LINES)
    glVertex2f(x + w * p, y - 6)
    glVertex2f(x + w * p, y + h + 6)
    glEnd()
    glLineWidth(1)
    text(x + w / 2, y + h + 12, 'POWER', SMALL, WHITE, 'center')


def prompts(g):
    kicker, keeper = g.kicker, g.keeper_side()
    lines = []
    if g.phase in ('aim', 'runup'):
        if g.is_human(kicker):
            k = CONTROLS[kicker]
            aim = f"{k['up'].upper()}{k['left'].upper()}{k['down'].upper()}{k['right'].upper()}"
            if g.phase == 'aim':
                lines.append(f"{g.name(kicker)} shooting: aim {aim}  |  {key_name(k['special'])} shot type"
                             f"  |  {key_name(k['shoot'])} start run-up")
            else:
                lines.append(f"{g.name(kicker)}: press {key_name(k['shoot'])} to set power (green = sweet spot)")
        else:
            lines.append(f"CPU ({g.profile['name']}) is stepping up...")
        if g.is_human(keeper):
            k = CONTROLS[keeper]
            lines.append(f"{g.name(keeper)} in goal: dive {key_name(k['left'])}/{key_name(k['right'])}"
                         f", stay {key_name(k['down'])}, high/low {key_name(k['up'])}"
                         f"  |  {key_name(k['special'])} put them off ({3 - g.taunts} left)")
    y = 24
    for s in reversed(lines):
        rect(500 - text_width(s, SMALL) / 2 - 10, y - 6, text_width(s, SMALL) + 20, 20, (0, 0, 0), 0.55)
        text(500, y, s, SMALL, WHITE, 'center')
        y += 22
    # Shot type and keeper intent
    if g.phase in ('aim', 'runup') and g.is_human(kicker):
        rect(20, 120, 190, 54, (0.05, 0.05, 0.08), 0.75)
        text(30, 154, 'SHOT', SMALL, (0.7, 0.7, 0.75))
        text(30, 130, C.SHOT_TYPES[g.shot_kind]['label'], MEDIUM, GOLD)
    if g.phase in ('aim', 'runup') and g.is_human(keeper):
        rect(790, 120, 190, 54, (0.05, 0.05, 0.08), 0.75)
        text(800, 154, 'KEEPER PLAN', SMALL, (0.7, 0.7, 0.75))
        if g.keeper_choice_visible():
            if g.keeper_dir is None:
                plan = 'Wait and react'
            else:
                plan = {-1: 'Dive left', 0: 'Stay centre', 1: 'Dive right'}[g.keeper_dir]
                plan += ', high' if g.keeper_high else ', low'
        else:
            plan = 'Locked in' if g.keeper_dir is not None else 'Wait and react'
        text(800, 130, plan, MEDIUM, GOLD)


def banners(g):
    if g.phase == 'toss':
        rect(0, 360, W, 90, (0, 0, 0), 0.6)
        big_text(500, 405, 'COIN TOSS', 34, GOLD)
        text(500, 375, g.message, MEDIUM, WHITE, 'center')
        return
    if g.phase == 'aim' and g.phase_t < 2.2:
        label = {'must_score': ('MUST SCORE', RED), 'to_win': ('TO WIN IT', GOLD)}.get(g.stakes)
        if label is None and g.shootout.in_sudden_death():
            label = ('SUDDEN DEATH', RED)
        if label:
            big_text(500, 600, label[0], 38, label[1])
        big_text(500, 560, f'{g.name(g.kicker)} TO KICK', 20, WHITE, 2.5)
    if g.phase == 'result' and g.result:
        scored, label = g.result
        rect(0, 380, W, 80, (0, 0, 0), 0.5)
        big_text(500, 405, label, 40 if len(label) < 18 else 28, GREEN if scored else RED)
    if g.phase == 'replay':
        circle(40, 760, 8, RED)
        text(56, 754, 'REPLAY  (SPACE to skip)', MEDIUM, WHITE)
        if g.shootout.winner:
            big_text(500, 640, 'THE DECISIVE KICK', 26, GOLD, 3)


def _heatmap(x, y, w, side, log):
    """Small goal frame with a dot where each kick ended up."""
    h = w * C.GOAL_HEIGHT / (2 * C.GOAL_HALF_WIDTH)
    sx = w / (2 * C.GOAL_HALF_WIDTH + 2.0)
    ox = x + w / 2
    gw = C.GOAL_HALF_WIDTH * sx
    gh = C.GOAL_HEIGHT * sx
    rect(x, y, w, h + 30, (0.15, 0.4, 0.17), 0.9)
    glColor3f(1, 1, 1)
    glLineWidth(3)
    glBegin(GL_LINE_STRIP)
    glVertex2f(ox - gw, y + 10)
    glVertex2f(ox - gw, y + 10 + gh)
    glVertex2f(ox + gw, y + 10 + gh)
    glVertex2f(ox + gw, y + 10)
    glEnd()
    glLineWidth(1)
    for k in log:
        if k['side'] != side or not k['at']:
            continue
        px = ox + max(-C.GOAL_HALF_WIDTH - 1.0, min(C.GOAL_HALF_WIDTH + 1.0, k['at'][0])) * sx
        py = y + 10 + min(C.GOAL_HEIGHT + 0.8, max(0.0, k['at'][1])) * sx
        circle(px, py, 6, GREEN if k['scored'] else RED)


def summary(g):
    so = g.shootout
    rect(150, 150, 700, 470, (0.05, 0.06, 0.1), 0.92)
    outline(150, 150, 700, 470, GOLD)
    big_text(500, 560, f'{g.name(so.winner)} WINS!', 44, GOLD)
    text(500, 525, f"{so.goals('p1')} - {so.goals('p2')} on penalties"
         + ('  (after sudden death)' if max(so.kicks('p1'), so.kicks('p2')) > so.kicks_per_side else ''),
         MEDIUM, WHITE, 'center')
    for i, side in enumerate(('p1', 'p2')):
        x = 200 + i * 320
        text(x + 140, 480, f"{g.name(side)}: where the kicks went", SMALL, WHITE, 'center')
        _heatmap(x, 330, 280, side, g.log)
        kicks = [k for k in g.log if k['side'] == side]
        saved = sum(1 for k in kicks if not k['scored'] and k['label'].startswith(('SAVED', 'CAUGHT')))
        off = sum(1 for k in kicks if not k['scored']) - saved
        text(x + 140, 305, f"{sum(k['scored'] for k in kicks)}/{len(kicks)} scored, {saved} saved, {off} off target",
             SMALL, (0.85, 0.85, 0.9), 'center')
    text(500, 250, stats.summary(g.stats), SMALL, (0.75, 0.8, 0.9), 'center')
    text(500, 190, 'R play again   |   V watch the decisive kick again   |   M menu', MEDIUM, WHITE, 'center')


def pause_overlay():
    rect(0, 0, W, H, (0, 0, 0), 0.55)
    big_text(500, 470, 'PAUSED', 48, WHITE)
    text(500, 420, 'P resume   |   R restart   |   M menu   |   H help   |   ESC quit', MEDIUM, WHITE, 'center')


HELP = [
    'Kicking: move the aim with your direction keys, change shot type, then start the run-up.',
    'Press shoot again during the run-up to stop the power bar. Green is the sweet spot;',
    'red sends it high, too little power is easy to save. Aiming tight to the post is risky.',
    'Shot types: Placed (accurate), Driven (fast but wild), Curler (bends), Chip/Panenka (slow,',
    'lofted: deadly if the keeper dives, embarrassing if they stand still).',
    'Nerves: must-score kicks, sudden death and keeper antics make your aim shakier.',
    '',
    'Keeping: pick a dive (left/right/stay) and high or low BEFORE the kick. It stays hidden.',
    'If you have not guessed, you get a split second after contact to react, but late.',
    'Wave your arms (special key) up to 3 times to put the kicker off.',
    '',
    'P1: W A S D aim/dive, SPACE shoot, E shot type / taunt',
    'P2: I J K L aim/dive, ENTER shoot, O shot type / taunt',
    'C camera   |   N sound on/off   |   P pause   |   H close help   |   ESC quit',
]


def help_overlay():
    rect(80, 130, 840, 560, (0.04, 0.05, 0.09), 0.94)
    outline(80, 130, 840, 560, GOLD)
    big_text(500, 640, 'HOW TO PLAY', 30, GOLD, 3)
    y = 600
    for line in HELP:
        text(110, y, line, SMALL if line.startswith(('P1', 'P2', 'C ')) else SMALL, WHITE)
        y -= 30


# ----------------------------------------------------------------------- menu
MENU_LAYOUT = {}


def _button(x, y, w, h, label, active, focused, disabled=False):
    col = (0.25, 0.25, 0.28) if disabled else ((0.16, 0.55, 0.25) if active else (0.15, 0.17, 0.22))
    rect(x, y, w, h, col, 0.95)
    outline(x, y, w, h, GOLD if focused else (0.35, 0.35, 0.42), 3 if focused else 1.5)
    text(x + w / 2, y + h / 2 - 6, label, MEDIUM, (0.7, 0.7, 0.72) if disabled else WHITE, 'center')


def menu(g):
    rect(0, 0, W, H, (0, 0, 0), 0.45)
    big_text(500, 690, 'PENALTY SHOOTOUT', 52, GOLD, 5)
    rect(220, 150, 560, 500, (0.06, 0.07, 0.11), 0.92)
    outline(220, 150, 560, 500, (0.3, 0.45, 0.8))
    rows = [
        ('mode', 'Game mode', [('PvC', g.mode == 'pvc'), ('PvP', g.mode == 'pvp')], False),
        ('difficulty', 'Difficulty (PvC)', [(d.capitalize(), g.difficulty == d) for d in ('easy', 'medium', 'hard')],
         g.mode != 'pvc'),
        ('kicks', 'Kicks each', [(str(n), g.kicks_per_side == n) for n in (3, 5, 10)], False),
        ('hidden', 'Hidden aim (PvP)', [('On', g.hidden_aim), ('Off', not g.hidden_aim)], g.mode != 'pvp'),
    ]
    MENU_LAYOUT.clear()
    y = 570
    for i, (key, label, options, disabled) in enumerate(rows):
        focused_row = g.menu_focus == i
        text(250, y + 14, label, MEDIUM, GOLD if focused_row else WHITE)
        bw = 92
        x = 760 - len(options) * (bw + 8)
        for j, (opt, active) in enumerate(options):
            _button(x, y, bw, 40, opt, active and not disabled, focused_row and active, disabled)
            MENU_LAYOUT[(key, j)] = (x, y, bw, 40)
            x += bw + 8
        y -= 70
    _button(380, 250, 240, 56, 'KICK OFF', True, g.menu_focus == 4)
    MENU_LAYOUT[('start', 0)] = (380, 250, 240, 56)
    text(500, 205, 'W/S move  |  A/D change  |  ENTER or SPACE start  |  H how to play', SMALL,
         (0.8, 0.8, 0.85), 'center')
    text(500, 175, stats.summary(g.stats), SMALL, (0.7, 0.75, 0.85), 'center')
    text(500, 30, 'N toggles sound' + ('' if g.audio and g.audio.enabled else ' (sound unavailable: pip install pygame)'),
         SMALL, (0.6, 0.6, 0.65), 'center')


def menu_click(g, x, y):
    for (key, j), (bx, by, bw, bh) in MENU_LAYOUT.items():
        if bx <= x <= bx + bw and by <= y <= by + bh:
            if key == 'start':
                g.start_match()
                return
            g.menu_focus = g.MENU_ROWS.index(key)
            if key == 'mode':
                g.mode = ('pvc', 'pvp')[j]
            elif key == 'difficulty' and g.mode == 'pvc':
                g.difficulty = ('easy', 'medium', 'hard')[j]
            elif key == 'kicks':
                g.kicks_per_side = (3, 5, 10)[j]
            elif key == 'hidden' and g.mode == 'pvp':
                g.hidden_aim = j == 0
            return


def draw(g):
    begin()
    if g.ui == 'menu':
        menu(g)
    else:
        scoreboard(g)
        if g.phase == 'runup' and (g.is_human(g.kicker) or g.power is not None):
            power_bar(g)
        prompts(g)
        banners(g)
        if g.phase == 'ended':
            summary(g)
        text(990, 8, f'Camera: {g.camera} (C)', SMALL, (0.7, 0.7, 0.75), 'right')
        if g.paused:
            pause_overlay()
    if g.show_help:
        help_overlay()
    end()
