"""2D overlay: scoreboard, prompts, power bar, banners, menu, summary and captions.

Drawn on a virtual 1000 x 800 canvas that stretches with the window.
"""

import math

from OpenGL.GL import *  # noqa: F401,F403
from OpenGL.GLU import *  # noqa: F401,F403
from OpenGL.GLUT import *  # noqa: F401,F403

from . import config as C, controls, stats
from .controls import CONTROLS
from .game import DRILL_ZONES, MODE_LABELS
from .modes import KingOfTheGoal, Knockout, MatchPenaltyComp, ShootoutComp, TrainingComp
from .scenarios import SCENARIOS

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


def wrap(s, width, font=SMALL):
    """Split s into lines no wider than width pixels."""
    lines, cur = [], ''
    for word in s.split():
        trial = (cur + ' ' + word).strip()
        if text_width(trial, font) > width and cur:
            lines.append(cur)
            cur = word
        else:
            cur = trial
    if cur:
        lines.append(cur)
    return lines


def panel_text(cx, y, lines, font=SMALL, colour=WHITE, step=20):
    for line in lines:
        text(cx, y, line, font, colour, 'center')
        y -= step
    return y


def mark(x, y, r, scored):
    """Scoreboard result: a coloured disc with a tick or a cross, so it reads without colour."""
    circle(x, y, r, GREEN if scored else RED)
    glColor3f(1, 1, 1)
    glLineWidth(2.0)
    glBegin(GL_LINES)
    if scored:
        glVertex2f(x - r * 0.5, y)
        glVertex2f(x - r * 0.1, y - r * 0.45)
        glVertex2f(x - r * 0.1, y - r * 0.45)
        glVertex2f(x + r * 0.55, y + r * 0.5)
    else:
        for s in (-1, 1):
            glVertex2f(x - r * 0.45, y - s * r * 0.45)
            glVertex2f(x + r * 0.45, y + s * r * 0.45)
    glEnd()
    glLineWidth(1.0)


# ------------------------------------------------------------------ in match
def _match_label(g):
    comp = g.comp
    if g.playback is not None:
        return 'SAVED REPLAY'
    if g.mode == 'famous':
        return SCENARIOS[g.scenario]['title']
    if isinstance(comp, Knockout):
        done = len(comp.history)
        return f'Knockout: tie {done + 1} of {len(comp.players) - 1}'
    label = MODE_LABELS[g.mode]
    if g.mode in ('pvc', 'match', 'training'):
        label += ' ' + g.difficulty.capitalize()
    if comp.sudden_death_label and comp.in_sudden_death():
        label += '  |  SUDDEN DEATH'
    return label


def scoreboard(g):
    comp = g.comp
    if isinstance(comp, KingOfTheGoal):
        king_table(g, 300, 792, compact=True)
        return
    rows = comp.rows()
    x, w = 300, 400
    h = 30 + 32 * len(rows)
    y = 792 - h
    rect(x, y, w, h, (0.07, 0.08, 0.12), 0.88)
    rect(x, y + h - 5, w, 5, GOLD)
    for i, r in enumerate(rows):
        slot = r['slot']
        ry = y + h - 30 - i * 32
        rect(x + 10, ry - 4, 8, 22, r['colour'])
        text(x + 26, ry, r['name'][:15], SMALL, WHITE)
        # Bookings for the keeper, and the specialist sub
        cx = x + 26 + text_width(r['name'][:15], SMALL) + 6
        for k in range(comp.yellows.get(slot, 0)):
            rect(cx + k * 9, ry - 2, 7, 11, RED if comp.emergency.get(slot) and k == 1 else GOLD)
        n = max(1, r['regulation'])
        step = min(22.0, 190.0 / n)
        results = r['results']
        for k in range(n):
            px = x + 135 + k * step
            if k < len(results):
                mark(px, ry + 5, min(7.0, step * 0.36), results[k])
            else:
                circle(px, ry + 5, min(7.0, step * 0.36), GREY)
        for k, res in enumerate(results[n:][-5:]):
            mark(x + 135 + n * step + 10 + k * 17, ry + 5, 6, res)
        text(x + w - 18, ry - 2, str(r['goals']), MEDIUM, GOLD, 'right')
        if g.phase in ('walk', 'aim', 'runup', 'flight') and g.kicker == slot:
            circle(x + w - 40, ry + 5, 4, GOLD)
    text(x + w / 2, y + 6, _match_label(g), SMALL, (0.8, 0.8, 0.85), 'center')


def king_table(g, x, top, compact=False):
    comp = g.comp
    table = comp.table()
    h = 26 + 20 * len(table)
    w = 400
    y = top - h
    rect(x, y, w, h, (0.07, 0.08, 0.12), 0.88)
    rect(x, y + h - 5, w, 5, GOLD)
    in_goal = comp.players[min(comp.round, len(comp.players) - 1)]
    for i, (name, pts, colour) in enumerate(table):
        ry = y + h - 24 - i * 20
        rect(x + 10, ry - 3, 8, 15, colour)
        tag = '  (in goal)' if name == in_goal and not comp.finished else ''
        text(x + 26, ry, name + tag, SMALL, GOLD if tag else WHITE)
        text(x + w - 18, ry, f'{pts} pts', SMALL, GOLD, 'right')
    if compact:
        text(x + w / 2, y - 16, f'King of the Goal  |  round {min(comp.round + 1, len(comp.players))} of '
             f'{len(comp.players)}', SMALL, (0.8, 0.8, 0.85), 'center')


def wind_gauge(g):
    if not g.wind:
        return
    x, y = 20, 712
    rect(x, y, 150, 48, (0.05, 0.05, 0.08), 0.75)
    text(x + 10, y + 30, f'WIND {abs(g.wind):.1f} m/s', SMALL, (0.8, 0.85, 0.95))
    d = 1 if g.wind > 0 else -1
    length = 25 + 14 * abs(g.wind)
    cx = x + 75
    glColor3f(*GOLD)
    glLineWidth(3)
    glBegin(GL_LINES)
    glVertex2f(cx - d * length / 2, y + 12)
    glVertex2f(cx + d * length / 2, y + 12)
    glVertex2f(cx + d * length / 2, y + 12)
    glVertex2f(cx + d * (length / 2 - 8), y + 18)
    glVertex2f(cx + d * length / 2, y + 12)
    glVertex2f(cx + d * (length / 2 - 8), y + 6)
    glEnd()
    glLineWidth(1)


def power_bar(g):
    x, y, w, h = 350, 60, 300, 22
    lo, hi = g.sweet()
    rect(x - 4, y - 4, w + 8, h + 8, (0.05, 0.05, 0.08), 0.85)
    rect(x, y, w, h, (0.25, 0.25, 0.3))
    rect(x + w * lo, y, w * (hi - lo), h, (0.2, 0.6, 0.25))
    rect(x + w * hi, y, w * (1 - hi), h, (0.65, 0.2, 0.15))
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


def composure(g):
    """A breathing ring while the kicker stands over the ball: settle, don't rush or dither."""
    t = g.aim_time
    if t < C.RUSHED_BEFORE:
        label, col = 'Rushing...', RED
    elif t < C.SETTLED[0]:
        label, col = 'Breathe...', WHITE
    elif t <= C.SETTLED[1]:
        label, col = 'Settled', GREEN
    elif t <= C.DRAGGED_AFTER:
        label, col = 'Ready', WHITE
    else:
        label, col = 'Overthinking', RED
    x, y = 20, 186
    rect(x, y, 190, 40, (0.05, 0.05, 0.08), 0.75)
    r = 9 + 4 * math.sin(g.clock * 2.4)
    circle(x + 22, y + 20, r, col)
    text(x + 44, y + 14, label, MEDIUM, col)


def prompts(g):
    kicker, keeper = g.kicker, g.keeper_side()
    lines = []
    if g.phase in ('aim', 'runup') and g.forced is None:
        if g.is_human(kicker):
            k = CONTROLS[kicker]
            aim = ''.join(key_name(k[a]) for a in ('up', 'left', 'down', 'right'))
            if g.phase == 'aim':
                lines.append(f"{g.taker_label()} shooting: aim {aim}  |  {key_name(k['special'])} shot type  |  "
                             f"{key_name(k['extra1'])} disguise  |  {key_name(k['shoot'])} run-up")
            else:
                lines.append(f"{g.name(kicker)}: press {key_name(k['shoot'])} to set power (green = sweet spot)")
            if g.mode == 'training':
                lines.append(f"T trajectory preview {'ON' if g.preview else 'OFF'}")
        else:
            who = 'Drill machine' if isinstance(g.comp, TrainingComp) else f"{g.taker_label()} ({g.profile['name']})"
            lines.append(f'{who} is stepping up...')
        if g.is_human(keeper):
            k = CONTROLS[keeper]
            if isinstance(g.comp, TrainingComp):
                lines.append(f"Drill zone: {DRILL_ZONES[g.drill_zone]} ({key_name(k['extra2'])} to change)")
            lines.append(f"{g.name(keeper)} in goal: dive {key_name(k['left'])}/{key_name(k['right'])}, "
                         f"stay {key_name(k['down'])}, high/low {key_name(k['up'])}  |  "
                         f"{key_name(k['special'])} wave ({3 - g.taunts})  |  {key_name(k['extra1'])} shuffle  |  "
                         f"{key_name(k['extra2'])} fake")
    elif g.phase == 'result' and g.result and g.result[0] and g.is_human(kicker) and g.celebration:
        k = CONTROLS[kicker]
        lines.append(f"Celebration: {g.celebration}  ({key_name(k['special'])} to change)")
    y = 24
    for s in reversed(lines):
        tw = text_width(s, SMALL)
        rect(500 - tw / 2 - 10, y - 6, tw + 20, 20, (0, 0, 0), 0.55)
        text(500, y, s, SMALL, WHITE, 'center')
        y += 22
    if g.phase in ('aim', 'runup') and g.is_human(kicker) and g.forced is None:
        rect(20, 110, 190, 70, (0.05, 0.05, 0.08), 0.75)
        text(30, 160, 'SHOT', SMALL, (0.7, 0.7, 0.75))
        text(30, 138, C.SHOT_TYPES[g.shot_kind]['label'], MEDIUM, GOLD)
        text(30, 118, 'Disguised run-up' if g.disguise else 'Open body shape', SMALL,
             GOLD if g.disguise else (0.7, 0.7, 0.75))
        if g.phase == 'aim':
            composure(g)
    if g.phase in ('aim', 'runup') and g.is_human(keeper) and g.forced is None:
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


def _stakes_label(g):
    label = {'must_score': ('MUST SCORE', RED), 'to_win': ('TO WIN IT', GOLD)}.get(g.stakes)
    if label is None and g.comp.sudden_death_label and g.comp.in_sudden_death():
        label = ('SUDDEN DEATH', RED)
    return label


def intro_card(g):
    sc = g.story
    rect(150, 230, 700, 380, (0.04, 0.05, 0.09), 0.93)
    outline(150, 230, 700, 380, GOLD)
    big_text(500, 550, sc['title'].upper(), 34, GOLD, 3.5)
    text(500, 505, f"{sc['teams'][0]}  v  {sc['teams'][1]}", MEDIUM, WHITE, 'center')
    panel_text(500, 460, wrap(sc['intro'], 600), SMALL, WHITE, 22)
    role = 'You are in goal.' if sc['role'] == 'keep' else f"You take the kick for {sc['teams'][0]}."
    text(500, 300, role, MEDIUM, GOLD, 'center')
    text(500, 260, 'SPACE or ENTER to step up', SMALL, (0.8, 0.8, 0.85), 'center')


def toss_panel(g):
    rect(0, 330, W, 150, (0, 0, 0), 0.6)
    big_text(500, 440, 'COIN TOSS', 34, GOLD)
    text(500, 405, g.message, MEDIUM, WHITE, 'center')
    w = g.toss_winner
    hint = ''
    if g.toss_stage == 'end' and g.is_human(w):
        k = CONTROLS[w]
        hint = f"{key_name(k['left'])}: kick towards your fans    {key_name(k['right'])}: towards theirs"
    elif g.toss_stage == 'sub':
        parts = []
        for slot in ('p1', 'p2'):
            if g.is_human(slot):
                on = 'ON' if g.comp.specialist[slot] else 'OFF'
                parts.append(f"{g.name(slot)}: {key_name(CONTROLS[slot]['extra1'])} specialist keeper sub ({on})")
        hint = '   |   '.join(parts) or 'Managers are deciding on a keeper sub...'
    if hint:
        text(500, 370, hint, SMALL, (0.85, 0.85, 0.9), 'center')
    if g.toss_stage == 'sub':
        text(500, 345, 'A specialist has a longer reach but is a worse kicker if the keepers have to take one.',
             SMALL, (0.65, 0.65, 0.7), 'center')


def banners(g):
    if g.phase == 'intro' and g.story:
        intro_card(g)
        return
    if g.phase == 'toss':
        toss_panel(g)
        return
    if g.phase == 'walk':
        label = _stakes_label(g)
        if label:
            big_text(500, 600, label[0], 38, label[1])
        big_text(500, 560, g.taker_label(), 22, WHITE, 2.5)
        end = 'towards his own fans' if g.end_fans == g.kicker else 'towards the away end'
        text(500, 530, f'The long walk, {end}...   (SPACE to skip)', SMALL, (0.85, 0.85, 0.9), 'center')
    if g.phase == 'aim' and g.phase_t < 2.2:
        label = _stakes_label(g)
        if g.retake:
            label = ('RETAKE', GOLD)
        if label:
            big_text(500, 600, label[0], 38, label[1])
        big_text(500, 560, f'{g.taker_label()} TO KICK', 20, WHITE, 2.5)
        if g.comp.taker_is_keeper(g.kicker):
            text(500, 530, 'Everyone has kicked: the goalkeeper steps up!', MEDIUM, GOLD, 'center')
    if g.phase == 'var':
        rect(0, 360, W, 100, (0.02, 0.03, 0.12), 0.75)
        big_text(500, 415, 'VAR CHECK', 34, (0.5, 0.75, 1.0))
        if g.phase_t < 1.3:
            what = 'possible double touch' if g.var == 'double_touch' else 'keeper off his line early'
            text(500, 380, f'Checking: {what}...', MEDIUM, WHITE, 'center')
        else:
            decision = ('GOAL DISALLOWED: DOUBLE TOUCH' if g.var == 'double_touch'
                        else 'RETAKE: THE KEEPER LEFT HIS LINE')
            text(500, 380, decision, MEDIUM, GOLD, 'center')
    if g.phase == 'rebound':
        big_text(500, 600, 'REBOUND!', 40, GOLD)
        hints = []
        if g.is_human(g.kicker):
            hints.append(f"{key_name(CONTROLS[g.kicker]['shoot'])} follow it in!")
        if g.is_human(g.keeper_side()):
            hints.append('Keeper: any direction key to smother')
        text(500, 560, '   |   '.join(hints), MEDIUM, WHITE, 'center')
    if g.phase == 'result' and g.result:
        scored, label = g.result
        rect(0, 380, W, 80, (0, 0, 0), 0.5)
        big_text(500, 405, label, 40 if len(label) < 18 else 26, GREEN if scored else RED)
    if g.card:
        colour, msg, _ = g.card
        rect(470, 470, 26, 36, GOLD if colour == 'yellow' else RED)
        text(506, 482, msg, MEDIUM, WHITE)
    if g.phase == 'replay':
        circle(40, 760, 8, RED)
        text(56, 754, f'REPLAY  (SPACE skip, C camera: {g.replay_cam})', MEDIUM, WHITE)
        if g.comp.finished:
            big_text(500, 640, 'THE DECISIVE KICK', 26, GOLD, 3)
        if g.export_request:
            text(56, 730, 'Recording clip...', SMALL, RED)


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
        if (side and k['side'] != side) or not k['at']:
            continue
        px = ox + max(-C.GOAL_HALF_WIDTH - 1.0, min(C.GOAL_HALF_WIDTH + 1.0, k['at'][0])) * sx
        py = y + 10 + min(C.GOAL_HEIGHT + 0.8, max(0.0, k['at'][1])) * sx
        mark(px, py, 6, k['scored'])


def zone_panel(g, x=790, y=520):
    """Training: success rate in each part of the goal, built up over every session."""
    zones = g.stats['zones']
    w, h = 190, 130
    rect(x, y, w, h, (0.05, 0.05, 0.08), 0.8)
    text(x + w / 2, y + h - 18, 'YOUR ZONES (all time)', SMALL, (0.8, 0.8, 0.85), 'center')
    cw, ch = (w - 20) / 3.0, (h - 40) / 2.0
    for i, z in enumerate(stats.ZONES):
        col, row = i % 3, i // 3
        att, goals = zones[z]
        cx, cy = x + 10 + col * cw, y + 10 + (1 - row) * ch
        if att:
            r = goals / att
            rect(cx + 2, cy + 2, cw - 4, ch - 4, (0.9 - 0.7 * r, 0.25 + 0.6 * r, 0.25), 0.9)
            text(cx + cw / 2, cy + ch / 2 + 2, f'{100 * r:.0f}%', SMALL, WHITE, 'center')
            text(cx + cw / 2, cy + 8, f'{goals}/{att}', SMALL, (0.9, 0.9, 0.9), 'center')
        else:
            rect(cx + 2, cy + 2, cw - 4, ch - 4, GREY, 0.5)
            text(cx + cw / 2, cy + ch / 2 - 4, '-', SMALL, WHITE, 'center')


def summary(g):
    comp = g.comp
    rect(150, 130, 700, 500, (0.05, 0.06, 0.1), 0.92)
    outline(150, 130, 700, 500, GOLD)
    if isinstance(comp, MatchPenaltyComp):
        title = 'MATCH WON!' if comp.is_human(comp.winner) else 'MATCH LOST'
    else:
        title = f'{comp.winner_name()} WINS!'
    big_text(500, 570, title, 40 if len(title) < 20 else 26, GOLD)
    line = comp.summary_line()
    panel_text(500, 535, wrap(line, 640, MEDIUM), MEDIUM, WHITE, 22)
    if isinstance(comp, KingOfTheGoal):
        king_table(g, 300, 500)
    elif isinstance(comp, Knockout):
        y = 480
        text(500, y, 'Results', MEDIUM, GOLD, 'center')
        for w, lost in comp.history:
            y -= 24
            text(500, y, f'{w} beat {lost}', SMALL, WHITE, 'center')
    elif isinstance(comp, MatchPenaltyComp):
        text(500, 480, 'Where the kick went', SMALL, WHITE, 'center')
        _heatmap(360, 330, 280, None, g.log)
    else:
        for i, side in enumerate(('p1', 'p2')):
            x = 200 + i * 320
            text(x + 140, 480, f"{g.name(side)}: where the kicks went", SMALL, WHITE, 'center')
            _heatmap(x, 330, 280, side, g.log)
            kicks = [k for k in g.log if k['side'] == side]
            saved = sum(1 for k in kicks if not k['scored'] and k['label'].startswith(('SAVED', 'CAUGHT')))
            off = sum(1 for k in kicks if not k['scored']) - saved
            text(x + 140, 305, f"{sum(k['scored'] for k in kicks)}/{len(kicks)} scored, {saved} saved, "
                 f"{off} off target", SMALL, (0.85, 0.85, 0.9), 'center')
    sc = SCENARIOS[g.scenario] if g.mode == 'famous' and g.playback is None else None
    if sc:
        rect(170, 215, 660, 70, (0.12, 0.1, 0.05), 0.9)
        text(185, 265, 'WHAT REALLY HAPPENED', SMALL, GOLD)
        y = 245
        for ln in wrap(sc['history'], 630):
            text(185, y, ln, SMALL, WHITE)
            y -= 18
    text(500, 195, stats.summary(g.stats), SMALL, (0.75, 0.8, 0.9), 'center')
    keys = 'R play again  |  V replay  |  G save GIF clip  |  M menu'
    if isinstance(comp, ShootoutComp):
        keys = 'R play again  |  V replay  |  F save replay file  |  G save GIF clip  |  M menu'
    text(500, 150, keys, MEDIUM, WHITE, 'center')


def pause_overlay():
    rect(0, 0, W, H, (0, 0, 0), 0.55)
    big_text(500, 470, 'PAUSED', 48, WHITE)
    text(500, 420, 'P resume   |   R restart   |   M menu   |   H help   |   ESC quit', MEDIUM, WHITE, 'center')


def help_lines():
    p1, p2 = CONTROLS['p1'], CONTROLS['p2']

    def keys(c):
        return (f"{key_name(c['up'])} {key_name(c['left'])} {key_name(c['down'])} {key_name(c['right'])} aim/dive, "
                f"{key_name(c['shoot'])} shoot, {key_name(c['special'])} shot type / wave arms, "
                f"{key_name(c['extra1'])} disguise / shuffle, {key_name(c['extra2'])} celebrate / fake")
    return [
        'Kicking: aim with your direction keys, pick a shot type, then start the run-up. Press shoot',
        'again to stop the power bar: green is the sweet spot. Wait a breath after the whistle (rushing',
        'hurts, dithering too). Disguise hides your body shape from the keeper at a small cost in accuracy.',
        'Shots: Placed, Driven, Curler, Chip/Panenka, Knuckleball (wobbles), Skidder (low, fizzes off',
        'the turf), Stutter (hop and wait for the keeper to move, slow if he holds his ground).',
        'Keeping: pick a dive before the kick, or react late after it. Shuffle along the line to make',
        'one side look bigger, fake a lean, or wave your arms. Too much and the referee books you;',
        'leave your line early and VAR orders a retake. Two yellows and an outfielder goes in goal.',
        '',
        'P1: ' + keys(p1),
        'P2: ' + keys(p2),
        'C camera (walk-on, keeper eye view, orbit with arrows)  |  N sound  |  P pause  |  H help',
        'After a match: V replay (C changes replay camera)  |  F save replay file  |  G save GIF clip',
        'Menu: K rebinds keys. Start with --replay FILE to watch a saved shootout.',
    ]


def help_overlay():
    rect(60, 120, 880, 580, (0.04, 0.05, 0.09), 0.94)
    outline(60, 120, 880, 580, GOLD)
    big_text(500, 650, 'HOW TO PLAY', 30, GOLD, 3)
    y = 610
    for line in help_lines():
        text(85, y, line, SMALL, WHITE)
        y -= 32


def rebind_overlay(g):
    slot, idx = g.rebind
    rect(200, 150, 600, 520, (0.04, 0.05, 0.09), 0.96)
    outline(200, 150, 600, 520, GOLD)
    big_text(500, 620, f"KEYS: {'PLAYER 1' if slot == 'p1' else 'PLAYER 2'}", 28, GOLD, 3)
    y = 570
    for i, action in enumerate(controls.ACTIONS):
        current = i == idx
        col = GOLD if current else WHITE
        text(260, y, controls.ACTION_LABELS[action], MEDIUM, col)
        k = '...' if current else key_name(CONTROLS[slot][action])
        text(740, y, k, MEDIUM, col, 'right')
        y -= 44
    text(500, 190, 'Press a key for the highlighted action  |  ESC cancel', SMALL, (0.8, 0.8, 0.85), 'center')


def overlays(g):
    """Captions for sound cues, short notices and the phone controller address."""
    if g.captions_on:
        y = 92
        for s, t in reversed(g.captions):
            if g.clock - t < 2.5:
                tw = text_width(s, SMALL)
                rect(14, y - 5, tw + 12, 19, (0, 0, 0), 0.6)
                text(20, y, s, SMALL, (0.95, 0.95, 0.7))
                y += 22
    if g.toast and g.clock - g.toast[1] < 4.0:
        s = g.toast[0]
        tw = text_width(s, SMALL)
        rect(500 - tw / 2 - 12, 668, tw + 24, 24, (0.1, 0.2, 0.12), 0.9)
        text(500, 675, s, SMALL, WHITE, 'center')
    if g.phone_info:
        text(990, 780, g.phone_info, SMALL, (0.7, 0.85, 1.0), 'right')


# ----------------------------------------------------------------------- menu
MENU_LAYOUT = {}
MENU_LABELS = {
    'mode': 'Game mode', 'difficulty': 'Difficulty', 'kicks': 'Kicks each', 'hidden': 'Hidden aim',
    'scenario': 'Famous shootout', 'party_type': 'Party game', 'players': 'Players', 'role': 'You',
    'weather': 'Weather', 'daytime': 'Kick-off', 'assist': 'Assist', 'captions': 'Sound captions',
    'phone': 'Phone controller', 'start': '',
}
MODE_NAMES = {'pvc': 'Player v CPU', 'pvp': 'Player v Player', 'famous': 'Famous shootouts',
              'match': "90th-minute penalty", 'party': 'Party (3-8 friends)', 'training': 'Training ground'}


def menu_value(g, row):
    if row == 'mode':
        return MODE_NAMES[g.mode]
    if row == 'difficulty':
        return g.difficulty.capitalize()
    if row == 'kicks':
        return 'Sudden death only' if g.kicks_per_side == 0 else str(g.kicks_per_side)
    if row == 'hidden':
        return 'On' if g.hidden_aim else 'Off'
    if row == 'scenario':
        sc = SCENARIOS[g.scenario]
        return f"{sc['title']}: {sc['teams'][0]}"
    if row == 'party_type':
        return 'King of the Goal' if g.party_type == 'king' else 'Knockout bracket'
    if row == 'players':
        return str(g.party_players)
    if row == 'role':
        return 'Take the kick' if g.role == 'kick' else 'Keep goal'
    if row == 'weather':
        return C.WEATHER[g.weather]['label']
    if row == 'daytime':
        return 'Night, floodlights' if g.daytime == 'night' else 'Afternoon sun'
    if row == 'assist':
        return 'Relaxed timing' if g.assist == 'relaxed' else 'Off'
    if row == 'captions':
        return 'On' if g.captions_on else 'Off'
    if row == 'phone':
        return 'On' if g.phone else 'Off'
    return ''


def menu(g):
    rect(0, 0, W, H, (0, 0, 0), 0.45)
    big_text(500, 715, 'PENALTY SHOOTOUT', 52, GOLD, 5)
    rows = g.menu_rows()
    focus = min(g.menu_focus, len(rows) - 1)
    top, step = 650, 40
    bottom = top - step * len(rows) - 50
    rect(180, bottom, 640, top - bottom + 10, (0.06, 0.07, 0.11), 0.92)
    outline(180, bottom, 640, top - bottom + 10, (0.3, 0.45, 0.8))
    MENU_LAYOUT.clear()
    y = top - 36
    for i, row in enumerate(rows):
        focused = i == focus
        if row == 'start':
            _button(380, y - 18, 240, 46, 'KICK OFF', True, focused)
            MENU_LAYOUT[('start', 0)] = (380, y - 18, 240, 46)
            break
        text(210, y + 8, MENU_LABELS[row], MEDIUM, GOLD if focused else WHITE)
        bx = 480
        _button(bx, y, 34, 30, '<', False, focused)
        _button(bx + 270, y, 34, 30, '>', False, focused)
        rect(bx + 38, y, 228, 30, (0.12, 0.14, 0.2) if not focused else (0.16, 0.4, 0.22), 0.95)
        text(bx + 152, y + 9, menu_value(g, row), SMALL, WHITE, 'center')
        MENU_LAYOUT[(row, -1)] = (bx, y, 34, 30)
        MENU_LAYOUT[(row, 1)] = (bx + 270, y, 34, 30)
        MENU_LAYOUT[(row, 0)] = (bx + 38, y, 228, 30)
        y -= step
    if g.mode == 'famous':
        sc = SCENARIOS[g.scenario]
        panel_text(500, bottom - 24, wrap(sc['intro'], 620)[:2], SMALL, (0.8, 0.8, 0.85), 18)
    text(500, 95, 'W/S move  |  A/D change  |  ENTER or SPACE start  |  K rebind keys  |  H how to play',
         SMALL, (0.8, 0.8, 0.85), 'center')
    text(500, 70, stats.summary(g.stats), SMALL, (0.7, 0.75, 0.85), 'center')
    text(500, 30, 'N toggles sound' + ('' if g.audio and g.audio.enabled else ' (sound unavailable: pip install pygame)'),
         SMALL, (0.6, 0.6, 0.65), 'center')


def _button(x, y, w, h, label, active, focused, disabled=False):
    col = (0.25, 0.25, 0.28) if disabled else ((0.16, 0.55, 0.25) if active else (0.15, 0.17, 0.22))
    rect(x, y, w, h, col, 0.95)
    outline(x, y, w, h, GOLD if focused else (0.35, 0.35, 0.42), 3 if focused else 1.5)
    text(x + w / 2, y + h / 2 - 6, label, MEDIUM, (0.7, 0.7, 0.72) if disabled else WHITE, 'center')


def menu_click(g, x, y):
    for (row, step), (bx, by, bw, bh) in MENU_LAYOUT.items():
        if bx <= x <= bx + bw and by <= y <= by + bh:
            if row == 'start':
                g.start_match()
                return
            g.menu_focus = g.menu_rows().index(row)
            g.menu_change(row, step or 1)
            return


def draw(g):
    begin()
    if g.ui == 'menu':
        menu(g)
        if g.rebind is not None:
            rebind_overlay(g)
    else:
        scoreboard(g)
        wind_gauge(g)
        if g.phase == 'runup' and (g.is_human(g.kicker) or g.power is not None):
            power_bar(g)
        prompts(g)
        banners(g)
        if g.mode == 'training' and g.phase not in ('ended', 'replay'):
            zone_panel(g)
        if g.phase == 'ended':
            summary(g)
        cam = g.replay_cam if g.phase == 'replay' else g.camera
        text(990, 8, f'Camera: {cam} (C)', SMALL, (0.7, 0.7, 0.75), 'right')
        if g.paused:
            pause_overlay()
    overlays(g)
    if g.show_help:
        help_overlay()
    end()
