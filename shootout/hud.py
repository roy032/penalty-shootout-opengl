"""2D overlay: scoreboard, prompts, power bar, banners, menu, summary and captions.

Drawn on a virtual 1000 x 800 canvas that stretches with the window.
"""

import math

from OpenGL.GL import *  # noqa: F401,F403
from OpenGL.GLU import *  # noqa: F401,F403
from OpenGL.GLUT import *  # noqa: F401,F403

from . import achievements, characters as CH, config as C, controls, gfx, stadium, stats
from .controls import CONTROLS
from .game import DRILL_ZONES, MODE_LABELS
from .modes import (CAREER_TRAITS, CAREER_XP, CHALLENGES, ROUND_NAMES, ChallengeComp, KingOfTheGoal,
                    Knockout, MatchPenaltyComp, ShootoutComp, TournamentComp, TrainingComp, TutorialComp)
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
    if g.local_slot is not None:
        label = MODE_LABELS['lan']
    else:
        label = MODE_LABELS[g.mode]
    if isinstance(comp, TournamentComp):
        label += ': ' + ROUND_NAMES[min(comp.round, 2)]
    elif isinstance(comp, ChallengeComp):
        label += ': ' + comp.spec['label']
    if g.mode in ('pvc', 'match', 'training', 'manager', 'tournament', 'career'):
        lvl = g.level()
        label += ' ' + (f"Auto ({100 * g.stats['auto_level']:.0f}%)" if lvl == 'auto' else lvl.capitalize())
    if C.VARIANT != 'stadium':
        label += '  |  ' + C.VARIANTS[C.VARIANT]['label']
    if getattr(getattr(comp, 'rules', None), 'order', 'abab') == 'abba':
        label += '  |  ABBA'
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
    y = 792 - h + slide_offset(g, h + 30)
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
        flash = getattr(g, 'goal_flash', None)
        if flash and g.kicker == slot and g.clock - flash[1] < 1.5:
            pulse = 1.0 + 0.6 * math.sin(min(1.0, (g.clock - flash[1]) / 1.5) * math.pi)
            big_text(x + w - 24, ry - 2, str(r['goals']), 16 * pulse, GOLD, 2.5, False)
        else:
            text(x + w - 18, ry - 2, str(r['goals']), MEDIUM, GOLD, 'right')
        if g.phase in ('walk', 'aim', 'runup', 'flight') and g.kicker == slot:
            circle(x + w - 40, ry + 5, 4, GOLD)
    text(x + w / 2, y + 6, _match_label(g), SMALL, (0.8, 0.8, 0.85), 'center')
    winprob_bar(g, x, y - 18, w)


def winprob_bar(g, x, y, w):
    """Live chance of winning, worked out exactly from the score."""
    p = g.win_prob()
    if p is None or g.phase in ('toss', 'intro'):
        return
    rect(x, y - 19, w, 31, (0.05, 0.05, 0.08), 0.75)
    rect(x + 2, y + 2, (w - 4) * p, 8, g.comp.kit('p1')['shirt'])
    rect(x + 2 + (w - 4) * p, y + 2, (w - 4) * (1 - p), 8, g.comp.kit('p2')['shirt'])
    text(x + 6, y - 14, f"Win chance  {g.name('p1')[:10]} {100 * p:.0f}%", SMALL, (0.85, 0.85, 0.9))
    text(x + w - 6, y - 14, f"{100 * (1 - p):.0f}% {g.name('p2')[:10]}", SMALL, (0.85, 0.85, 0.9), 'right')


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
                             f"{key_name(k['extra1'])} run-up style  |  {key_name(k['extra2'])} gaze  |  "
                             f"{key_name(k['shoot'])} run-up")
            else:
                lines.append(f"{g.name(kicker)}: press {key_name(k['shoot'])} to set power (green = sweet spot)")
            if g.mode == 'training':
                lines.append(f"T trajectory preview {'ON' if g.preview else 'OFF'}")
        else:
            style = g.profile['name']
            if g.player is not None and g.player.persona in CH.TAKER_PERSONAS and g.player.persona != 'steady':
                style = CH.TAKER_PERSONAS[g.player.persona][0]
            who = 'Drill machine' if isinstance(g.comp, TrainingComp) else f"{g.taker_label()} ({style})"
            lines.append(f'{who} is stepping up...')
        if g.is_human(keeper):
            k = CONTROLS[keeper]
            if isinstance(g.comp, TrainingComp):
                lines.append(f"Drill zone: {DRILL_ZONES[g.drill_zone]} ({key_name(k['extra2'])} to change)")
            lines.append(f"{g.name(keeper)} in goal: dive {key_name(k['left'])}/{key_name(k['right'])}, "
                         f"stay {key_name(k['down'])}, high/low {key_name(k['up'])}  |  "
                         f"{key_name(k['special'])} wave ({3 - g.taunts})  |  {key_name(k['extra1'])} shuffle  |  "
                         f"{key_name(k['extra2'])} fake  |  {key_name(k['extra3'])} point")
            lines.append(f"In the dive: {key_name(k['shoot'])} as the ball arrives to stretch  |  hold a direction "
                         f"to push a parry wide, {key_name(k['down'])} to palm it down")
    elif g.phase == 'ritual':
        if g.is_human(kicker) and not g.ritual_kicker:
            lines.append(f"{key_name(CONTROLS[kicker]['shoot'])}: take your time placing the ball (calms the nerves)")
        if g.is_human(keeper) and not g.took_ball:
            lines.append(f"{key_name(CONTROLS[keeper]['extra2'])}: pick the ball up and make him wait "
                         "(gets under his skin, risks a booking)")
    elif g.phase == 'flight' and g.is_human(keeper) and g.keeper.committed() and g.keeper.stretch is None:
        lines.append(f"{key_name(CONTROLS[keeper]['shoot'])}: STRETCH!")
    elif g.phase == 'result' and g.result and g.result[0] and g.is_human(kicker) and g.celebration:
        k = CONTROLS[kicker]
        lines.append(f"Celebration: {CH.CELEBRATIONS.get(g.celebration, g.celebration)}  "
                     f"({key_name(k['special'])}/{key_name(k['extra2'])} to change)")
    y = 24
    for s in reversed(lines):
        tw = text_width(s, SMALL)
        rect(500 - tw / 2 - 10, y - 6, tw + 20, 20, (0, 0, 0), 0.55)
        text(500, y, s, SMALL, WHITE, 'center')
        y += 22
    if g.phase in ('aim', 'runup') and g.is_human(kicker) and g.forced is None:
        rect(20, 92, 190, 88, (0.05, 0.05, 0.08), 0.75)
        text(30, 160, 'SHOT', SMALL, (0.7, 0.7, 0.75))
        text(30, 138, C.SHOT_TYPES[g.shot_kind]['label'], MEDIUM, GOLD)
        text(30, 118, C.RUNUPS[g.runup]['label'], SMALL, GOLD if g.disguise else (0.85, 0.85, 0.9))
        gaze = {'stare': 'Staring him down', 'away': 'Eyes on the ball', None: 'Gaze: natural'}[g.gaze]
        text(30, 100, gaze, SMALL, (0.85, 0.85, 0.9))
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
        if g.keeper.point_dir:
            text(800, 106, 'Pointing ' + ('right' if g.keeper.point_dir > 0 else 'left'), SMALL, WHITE)


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
        if not any(g.controller(s) for s in ('p1', 'p2')):
            hint = 'The managers are picking their takers...'
    if hint:
        text(500, 370, hint, SMALL, (0.85, 0.85, 0.9), 'center')
    ref = g.ref
    text(500, 345, f"Referee: {ref['name']}  ({ref['label']})", SMALL, (0.75, 0.85, 1.0), 'center')
    if g.toss_stage == 'sub':
        for i, slot in enumerate(('p1', 'p2')):
            if g.controller(slot):
                lineup_panel(g, slot, 30 if slot == 'p1' else 520, i)


def lineup_panel(g, slot, x, i):
    """Before the shootout: keeper sub and style, fresh legs, and who kicks when."""
    k = CONTROLS[slot]
    order = g.lineup_for(slot)
    lu = g.lineup[slot]
    w, top = 450, 320
    h = 40 + 17 * min(11, len(order)) + 86
    y = top - h
    rect(x, y, w, h, (0.04, 0.05, 0.09), 0.93)
    outline(x, y, w, h, GOLD if not lu['ready'] else GREEN)
    text(x + 12, top - 22, f"{g.name(slot)}: TAKERS", MEDIUM, GOLD)
    if lu['ready']:
        text(x + w - 12, top - 22, 'READY', MEDIUM, GREEN, 'right')
    ry = top - 44
    for n, p in enumerate(order[:11]):
        focus = n == lu['cursor']
        if focus:
            rect(x + 6, ry - 4, w - 12, 17, (0.16, 0.4, 0.22), 0.9)
        tag = ' (sub, cold)' if p.sub else (' GK' if p.keeper else '')
        col = GOLD if n == 4 else WHITE
        text(x + 12, ry, f"{n + 1}. {p.label}{tag}", SMALL, col)
        text(x + w - 12, ry, f"Comp {100 * p.composure:.0f}  Pow {100 * p.power:.0f}  Pl {100 * p.placement:.0f}  "
             f"{p.foot}", SMALL, (0.8, 0.8, 0.85), 'right')
        ry -= 17
    style = C.KEEPER_STYLES[g.comp.keeper_style[slot]]['label']
    on = 'ON' if g.comp.specialist[slot] else 'OFF'
    lines = [f"{key_name(k['up'])}/{key_name(k['down'])} pick  {key_name(k['left'])}/{key_name(k['right'])} move up/down"
             f"  {key_name(k['shoot'])} ready  (No. 5 kicks fifth: pick a cool head)",
             f"{key_name(k['extra1'])} specialist keeper: {on}   {key_name(k['special'])} keeper: {style}",
             f"{key_name(k['extra2'])} fresh subs for the kicks: {g.comp.subs[slot]} (fresh legs, cold first kick)"]
    for ln in lines:
        ry -= 4
        text(x + 12, ry, ln, SMALL, (0.85, 0.85, 0.9))
        ry -= 18


def story_card(g):
    title, body = g.story_beat
    rect(170, 330, 660, 170, (0.04, 0.05, 0.09), 0.9)
    outline(170, 330, 660, 170, GOLD)
    big_text(500, 455, title, 30, GOLD, 3)
    panel_text(500, 420, wrap(body, 600), SMALL, WHITE, 20)


def bubble(x, y, s, colour=(0.97, 0.97, 0.95), tail_down=True):
    """A speech bubble with its tail pointing at whoever is talking."""
    lines = wrap(s, 240)
    w = max(text_width(ln, SMALL) for ln in lines) + 24
    h = 18 * len(lines) + 14
    rect(x - w / 2, y, w, h, colour, 0.95)
    glColor4f(colour[0], colour[1], colour[2], 0.95)
    glBegin(GL_TRIANGLES)
    if tail_down:
        glVertex2f(x - 10, y)
        glVertex2f(x + 4, y)
        glVertex2f(x - 16, y - 16)
    else:
        glVertex2f(x - 8, y + h)
        glVertex2f(x + 8, y + h)
        glVertex2f(x, y + h + 14)
    glEnd()
    yy = y + h - 22
    for ln in lines:
        text(x, yy, ln, SMALL, (0.05, 0.05, 0.1), 'center')
        yy -= 18


def banter(g):
    """Pre-kick banter between the taker and the keeper, during the ritual."""
    if not g.banter or g.phase not in ('ritual', 'aim') or (g.phase == 'aim' and g.phase_t > 1.6):
        return
    kick_line, keep_line = g.banter
    bubble(250, 330, kick_line)
    if g.phase_t > 0.7 or g.phase == 'aim':
        bubble(560, 520, keep_line, (1.0, 0.95, 0.75))


def banners(g):
    if g.phase == 'intro' and g.story:
        intro_card(g)
        return
    if g.phase == 'pre' and g.story_beat:
        story_card(g)
        return
    if g.phase == 'toss':
        toss_panel(g)
        return
    if g.phase == 'interlude':
        bracket_panel(g)
        return
    if g.phase in ('walk', 'ritual'):
        label = _stakes_label(g)
        if label:
            big_text(500, 600, label[0], 38, label[1])
        if g.phase == 'walk':
            big_text(500, 560, g.taker_label(), 22, WHITE, 2.5)
            end = 'towards his own fans' if g.end_fans == g.kicker else 'towards the away end'
            text(500, 530, f'The long walk, {end}...   (SPACE to skip)', SMALL, (0.85, 0.85, 0.9), 'center')
        elif g.ritual_kicker or g.took_ball:
            text(500, 540, g.message, MEDIUM, WHITE, 'center')
        lower_third(g)
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
        shot_panel(g)
    if g.card:
        colour, msg, _ = g.card
        rect(470, 470, 26, 36, GOLD if colour == 'yellow' else RED)
        text(506, 482, msg, MEDIUM, WHITE)
    if g.phase == 'replay':
        circle(40, 760, 8, RED)
        cam = REPLAY_CAM_NAMES.get(g.replay_cam, g.replay_cam)
        text(56, 754, f'REPLAY  (SPACE skip, C camera: {cam})', MEDIUM, WHITE)
        glt_panel(g)
        if g.comp.finished:
            big_text(500, 640, 'THE DECISIVE KICK', 26, GOLD, 3)
        if g.export_request:
            text(56, 730, 'Recording clip...', SMALL, RED)


REPLAY_CAM_NAMES = {'auto': "director's cut", 'net': 'net cam', 'ball': 'ball cam', 'side': 'side',
                    'goalline': 'goal-line cam', 'spider': 'spider cam'}


def slide_offset(g, distance):
    """The score bug drops in at the start of each kick."""
    if g.phase == 'walk' and g.phase_t < 0.5:
        r = g.phase_t / 0.5
        return (1.0 - r * r * (3 - 2 * r)) * distance
    return 0.0


def shot_panel(g):
    """Broadcast readout after a kick: shot speed, xG and where this match's kicks went."""
    t = g.phase_t
    if t < 0.4 or not getattr(g, 'shot_speed', 0.0):
        return
    r = min(1.0, (t - 0.4) / 0.3)
    x = W - 230 + (1.0 - r) * 260
    rect(x, 120, 210, 66, (0.04, 0.05, 0.1), 0.88)
    rect(x, 182, 210, 4, g.comp.kit(g.kicker)['shirt'])
    text(x + 12, 160, 'SHOT SPEED', SMALL, (0.8, 0.8, 0.85))
    text(x + 198, 158, f'{g.shot_speed * 3.6:.0f} km/h', MEDIUM, WHITE, 'right')
    if g.shot_xg is not None:
        text(x + 12, 132, 'xG', SMALL, (0.8, 0.8, 0.85))
        text(x + 198, 130, f'{g.shot_xg:.2f}', MEDIUM, GOLD, 'right')
    if g.log:
        _heatmap(x + 30, 196, 150, None, g.log[-12:])


def glt_panel(g):
    """Goal-line technology verdict on a tight call."""
    glt = g.replay.get('glt') if g.replay else None
    if not glt or not glt['tight'] or g.replay['t'] * 60.0 < glt['frame']:
        return
    goal = glt['goal']
    cm = abs(glt['gap']) * 100.0
    rect(320, 470, 360, 76, (0.02, 0.04, 0.1), 0.9)
    rect(320, 542, 360, 4, GREEN if goal else RED)
    text(500, 524, 'GOAL-LINE TECHNOLOGY', SMALL, (0.7, 0.85, 1.0), 'center')
    big_text(500, 494, 'GOAL' if goal else 'NO GOAL', 26, GREEN if goal else RED, 3)
    what = f'wholly over by {cm:.0f} cm' if goal else f'{cm:.0f} cm short of being over'
    text(500, 476, what, SMALL, WHITE, 'center')


def photo_decor(g):
    """Photo mode: a poster frame and the scorer's name, saved with the picture."""
    if not (g.photo_frame or g.photo_stamp):
        return
    begin()
    if g.photo_frame:
        for (x, y, w, h) in ((0, 0, W, 26), (0, H - 26, W, 26), (0, 0, 26, H), (W - 26, 0, 26, H)):
            rect(x, y, w, h, (0.97, 0.96, 0.92), 1.0)
        outline(34, 34, W - 68, H - 68, GOLD, 2.0)
    if g.photo_stamp:
        name = g.hero_name()
        big_text(W - 230, 74, name.upper()[:18], 30, WHITE, 3.5)
        text(W - 230, 50, g.screen_info()['score'], SMALL, GOLD, 'center')
    end()


def lower_third(g):
    """TV caption for the taker: ratings and his record from the spot."""
    info = g.lower_third()
    if not info:
        return
    x, y, w, h = 40, 200, 430, 92
    if g.phase == 'walk':
        r = min(1.0, g.phase_t / 0.45)
        x -= (1.0 - r * r * (3 - 2 * r)) * (w + 60)          # slides in from the side
    extra = [s for s in (info.get('full'), info.get('tag')) if s]
    traits = [s for s in (info.get('persona'), info.get('signature')) if s]
    if extra or traits:
        h += 22
    rect(x, y, w, h, (0.04, 0.05, 0.1), 0.9)
    rect(x, y, 8, h, g.comp.kit(g.kicker)['shirt'])
    text(x + 20, y + h - 26, info['label'].upper(), MEDIUM, WHITE)
    sub = '  |  FRESH SUB' if info['sub'] else ''
    text(x + w - 12, y + h - 26, info['team'][:14] + sub, SMALL, GOLD, 'right')
    if extra or traits:
        text(x + 20, y + h - 46, '  |  '.join(extra)[:44], SMALL, (0.85, 0.85, 0.9))
        text(x + w - 12, y + h - 46, ' / '.join(traits), SMALL, GOLD, 'right')
    if info.get('aura', 0) >= 0.3:
        glow = info.get('glow') or GOLD
        text(x + w - 12, y + 8, f"AURA {100 * info['aura']:.0f}", SMALL, glow, 'right')
    for n, (name, val) in enumerate((('Composure', info['composure']), ('Power', info['power']),
                                     ('Placement', info['placement']))):
        bx = x + 20 + n * 135
        text(bx, y + 40, name, SMALL, (0.8, 0.8, 0.85))
        rect(bx, y + 26, 120, 8, GREY, 0.6)
        rect(bx, y + 26, 120 * val, 8, GREEN if val > 0.6 else GOLD if val > 0.4 else RED)
    form = info.get('form', 0)
    form_txt = {2: '  |  Form: red hot', 1: '  |  Form: good', -1: '  |  Form: shaky', -2: '  |  Form: cold'}.get(form, '')
    text(x + 20, y + 8, info['foot'] + ('  |  ' + info['record'] if info['record'] else '') + form_txt, SMALL, WHITE)


def notes_panel(g):
    """The keeper's water-bottle notes on this taker."""
    if not g.bottle_note or g.phase not in ('walk', 'ritual', 'aim', 'runup'):
        return
    x, y, w = 700, 300, 280
    lines = wrap(g.bottle_note, w - 20)
    h = 34 + 18 * len(lines)
    rect(x, y, w, h, (0.85, 0.9, 0.95), 0.92)
    text(x + 10, y + h - 20, 'WATER BOTTLE NOTES', SMALL, (0.1, 0.2, 0.5))
    yy = y + h - 40
    for ln in lines:
        text(x + 10, yy, ln, SMALL, (0.05, 0.05, 0.1))
        yy -= 18


def commentary_line(g):
    if g.commentary == 'off' or not g.comment or g.clock - g.comment[1] > 4.5:
        return
    s = '"' + g.comment[0] + '"'
    tw = text_width(s, MEDIUM)
    rect(500 - tw / 2 - 14, 638, tw + 28, 28, (0.02, 0.02, 0.05), 0.7)
    text(500, 646, s, MEDIUM, (0.95, 0.95, 0.75), 'center')


def coach_panel(g):
    """Tutorial instructions or the challenge brief, top left."""
    comp = g.comp
    if isinstance(comp, TutorialComp) and not comp.finished:
        title, body = f'COACH  (step {comp.step + 1} of 7)', comp.instruction()
    elif isinstance(comp, ChallengeComp) and g.phase not in ('ended', 'replay'):
        title, body = comp.spec['label'].upper(), comp.spec['desc'] + f"  Best: {g.stats['challenges'].get(comp.kind, 0)}"
    else:
        return
    lines = wrap(body, 300)
    h = 34 + 18 * len(lines)
    x, y = 20, 690 - h
    rect(x, y, 330, h, (0.05, 0.1, 0.06), 0.9)
    outline(x, y, 330, h, GREEN)
    text(x + 12, y + h - 22, title, SMALL, GOLD)
    yy = y + h - 42
    for ln in lines:
        text(x + 12, yy, ln, SMALL, WHITE)
        yy -= 18


def bracket_panel(g):
    comp = g.comp
    rect(200, 200, 600, 420, (0.04, 0.05, 0.09), 0.94)
    outline(200, 200, 600, 420, GOLD)
    big_text(500, 570, comp.interlude() or 'TOURNAMENT', 26, GOLD, 3)
    y = 525
    for line in comp.bracket()[-12:]:
        mine = comp.teams[0]['name'] in line
        text(500, y, line, SMALL, GOLD if mine else WHITE, 'center')
        y -= 24
    text(500, 225, 'SPACE or ENTER for the next round', MEDIUM, WHITE, 'center')


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
    elif isinstance(comp, (ChallengeComp, TutorialComp)):
        title = comp.winner_name()
    elif isinstance(comp, TournamentComp):
        title = 'CHAMPIONS!' if comp.champion else 'KNOCKED OUT'
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
    elif isinstance(comp, TournamentComp):
        y = 480
        for line in comp.bracket()[-8:]:
            text(500, y, line, SMALL, GOLD if comp.teams[0]['name'] in line else WHITE, 'center')
            y -= 20
    elif isinstance(comp, (MatchPenaltyComp, ChallengeComp, TutorialComp)):
        text(500, 480, 'Where the kicks went', SMALL, WHITE, 'center')
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
    if g.unlocked:
        text(500, 300, 'Unlocked: ' + ', '.join(g.unlocked)[:90], SMALL, GOLD, 'center')
    if g.daily_grid:
        y = 284
        for ln in g.daily_grid.replace('\U0001F7E9', 'O ').replace('\U0001F7E5', 'X ').split('\n'):
            text(500, y, ln, SMALL, WHITE, 'center')
            y -= 18
    sc = SCENARIOS[g.scenario] if g.mode == 'famous' and g.playback is None else None
    if sc:
        rect(170, 215, 660, 70, (0.12, 0.1, 0.05), 0.9)
        text(185, 265, 'WHAT REALLY HAPPENED', SMALL, GOLD)
        y = 245
        for ln in wrap(sc['history'], 630):
            text(185, y, ln, SMALL, WHITE)
            y -= 18
    text(500, 195, stats.summary(g.stats), SMALL, (0.75, 0.8, 0.9), 'center')
    keys = 'R play again  |  V replay  |  G GIF clip  |  TAB coach report  |  Y photo  |  M menu'
    if isinstance(comp, ShootoutComp):
        keys = 'R again  |  V replay  |  F replay file  |  G GIF  |  B share  |  TAB report  |  M menu'
        share = 'B copies your result grid and saves your kicks as a ghost duel' if g.daily_grid else \
            'B saves your kicks as a ghost duel for a friend to face'
        text(500, 172, share, SMALL, GOLD, 'center')
    text(500, 150, keys, MEDIUM, WHITE, 'center')
    if g.show_report:
        report_overlay(g)


def report_overlay(g):
    rect(170, 220, 660, 300, (0.03, 0.06, 0.04), 0.96)
    outline(170, 220, 660, 300, GREEN)
    big_text(500, 470, "COACH'S REPORT", 26, GOLD, 3)
    y = 430
    for line in g.coach_report():
        for ln in wrap(line, 600, MEDIUM):
            text(200, y, ln, MEDIUM, WHITE)
            y -= 24
        y -= 8
    text(500, 235, 'TAB to close', SMALL, (0.8, 0.8, 0.85), 'center')


def pause_overlay():
    rect(0, 0, W, H, (0, 0, 0), 0.55)
    big_text(500, 470, 'PAUSED', 48, WHITE)
    text(500, 420, 'P resume   |   R restart   |   M menu   |   H help   |   ESC quit', MEDIUM, WHITE, 'center')


def help_lines():
    p1, p2 = CONTROLS['p1'], CONTROLS['p2']

    def keys(c):
        return (f"{key_name(c['up'])} {key_name(c['left'])} {key_name(c['down'])} {key_name(c['right'])} aim/dive, "
                f"{key_name(c['shoot'])} shoot, {key_name(c['special'])} shot type / wave arms, "
                f"{key_name(c['extra1'])} run-up / shuffle, {key_name(c['extra2'])} gaze / fake, "
                f"{key_name(c['extra3'])} point")
    return [
        'Kicking: aim, pick a shot type and a run-up (angled: more pace but readable; straight; disguised),',
        'then start the run-up and press shoot again to stop the power bar in the green. Wait a breath',
        'after the whistle. Gaze: stare the keeper down (calmer, but his antics bite harder) or look away.',
        'After the walk, press shoot to take your time placing the ball. Each taker has his own ratings.',
        'Keeping: pick a dive before the kick or react late. Shuffle, fake, wave, point to a corner, or',
        'pick up the ball to make him wait (risks a booking). In the dive, press shoot as the ball',
        'arrives to stretch; hold a direction to push a parry wide, or down to palm it in front.',
        'P1: ' + keys(p1),
        'P2: ' + keys(p2),
        'C camera  |  Y photo mode (WASD QE move, ENTER saves)  |  N sound  |  P pause  |  H help',
        'After a match: V replay  |  F replay file  |  G GIF  |  B share (ghost duel, daily grid)  |  TAB report',
        'Menu: K rebind keys, L achievements, C create a player. Characters row: club squads, a random draft',
        'of icons, or pick your own on the select screen. --replay FILE, --duel FILE, --host / --join IP for LAN.',
    ]


def help_overlay():
    rect(60, 120, 880, 580, (0.04, 0.05, 0.09), 0.94)
    outline(60, 120, 880, 580, GOLD)
    big_text(500, 650, 'HOW TO PLAY', 30, GOLD, 3)
    y = 610
    for line in help_lines():
        text(85, y, line, SMALL, WHITE)
        y -= 38


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
        y -= 40
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
    'phone': 'Phone controller', 'start': '', 'order': 'Kick order', 'team1': 'Your team', 'team2': 'Opponents',
    'challenge': 'Challenge', 'ghost': 'Ghost', 'variant': 'Pitch', 'commentary': 'Commentary',
    'squads': 'Characters', 'stadium': 'Stadium', 'graphics': 'Graphics',
}
MODE_NAMES = {'pvc': 'Player v CPU', 'pvp': 'Player v Player', 'famous': 'Famous shootouts',
              'match': "90th-minute penalty", 'party': 'Party (3-8 friends)', 'training': 'Training ground',
              'manager': 'Manager (pick the takers)', 'tournament': 'Tournament (8 teams)', 'career': 'Career',
              'challenge': 'Challenges', 'daily': 'Daily shootout', 'ghost': 'Ghost duel', 'tutorial': 'Tutorial'}


def menu_value(g, row):
    if row == 'mode':
        return MODE_NAMES[g.mode]
    if row == 'difficulty':
        if g.difficulty == 'auto':
            return f"Auto (now {100 * g.stats['auto_level']:.0f}% of hard)"
        return g.difficulty.capitalize()
    if row == 'order':
        return 'ABBA (2017 trial)' if g.order == 'abba' else 'ABAB (standard)'
    if row in ('team1', 'team2'):
        return g.team('p1' if row == 'team1' else 'p2')['name']
    if row == 'challenge':
        return CHALLENGES[g.challenge]['label']
    if row == 'ghost':
        return g.duels[g.ghost_i % len(g.duels)][0] if g.duels else 'House ghost (built in)'
    if row == 'variant':
        return C.VARIANTS[g.variant]['label']
    if row == 'commentary':
        return {'off': 'Off', 'text': 'Captions', 'speech': 'Spoken (pyttsx3)'}[g.commentary]
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
        if g.mode == 'career':
            c = g.stats['career'].get(g.role) or {}
            return ('Striker' if g.role == 'kick' else 'Goalkeeper') + f" ({c.get('xp', 0)} XP)"
        return 'Take the kick' if g.role == 'kick' else 'Keep goal'
    if row == 'weather':
        return C.WEATHER[g.weather]['label']
    if row == 'daytime':
        return {'night': 'Night, floodlights', 'day': 'Afternoon sun', 'dusk': 'Dusk into night',
                'sunset': 'Golden sunset'}[g.daytime]
    if row == 'stadium':
        return stadium.THEME_LABELS[g.stadium]
    if row == 'graphics':
        label = gfx.QUALITY_LABELS[g.graphics]
        return label + ('  (shaders unavailable)' if gfx.state.get('error') and g.graphics == 'low' else '')
    if row == 'assist':
        return 'Relaxed timing' if g.assist == 'relaxed' else 'Off'
    if row == 'captions':
        return 'On' if g.captions_on else 'Off'
    if row == 'phone':
        return 'On' if g.phone else 'Off'
    if row == 'squads':
        if g.mode == 'career':
            saved = CH.get((g.stats['career'].get(g.role) or {}).get('char') or '')
            return {'club': 'Plain (no avatar)', 'legends': f"Avatar: {saved['name']}" if saved else 'Random icon',
                    'pick': 'Pick your avatar'}[g.squads]
        if g.mode == 'party':
            return {'club': 'Plain colours', 'legends': 'Random characters', 'pick': 'Everyone picks one'}[g.squads]
        return {'club': 'Club squads', 'legends': 'Icons draft (random)', 'pick': 'Pick your takers'}[g.squads]
    return ''


def menu(g):
    rect(0, 0, W, H, (0, 0, 0), 0.45)
    big_text(500, 715, 'PENALTY SHOOTOUT', 52, GOLD, 5)
    rows = g.menu_rows()
    focus = min(g.menu_focus, len(rows) - 1)
    top = 650
    step = min(40.0, 470.0 / len(rows))
    bh = min(30.0, step - 4)
    bottom = top - step * len(rows) - 46
    hint = mode_hint(g)
    if hint:
        text(500, 664, hint, SMALL, (0.85, 0.85, 0.9), 'center')
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
        text(210, y + bh / 2 - 6, MENU_LABELS[row], MEDIUM, GOLD if focused else WHITE)
        bx = 480
        _button(bx, y, 34, bh, '<', False, focused)
        _button(bx + 270, y, 34, bh, '>', False, focused)
        rect(bx + 38, y, 228, bh, (0.12, 0.14, 0.2) if not focused else (0.16, 0.4, 0.22), 0.95)
        text(bx + 152, y + bh / 2 - 5, menu_value(g, row), SMALL, WHITE, 'center')
        MENU_LAYOUT[(row, -1)] = (bx, y, 34, bh)
        MENU_LAYOUT[(row, 1)] = (bx + 270, y, 34, bh)
        MENU_LAYOUT[(row, 0)] = (bx + 38, y, 228, bh)
        y -= step
    text(500, 95, 'W/S move  |  A/D change  |  ENTER start  |  K keys  |  L achievements  |  C create a player  |  '
         'H help',
         SMALL, (0.8, 0.8, 0.85), 'center')
    text(500, 70, stats.summary(g.stats), SMALL, (0.7, 0.75, 0.85), 'center')
    text(500, 30, 'N toggles sound' + ('' if g.audio and g.audio.enabled else ' (sound unavailable: pip install pygame)'),
         SMALL, (0.6, 0.6, 0.65), 'center')


MODE_HINTS = {
    'pvc': 'A shootout against the computer. Your takers have their own ratings.',
    'pvp': 'Two players, one keyboard (or LAN: --host / --join).',
    'manager': 'You pick the order of takers, the subs and the keeper; the players do the rest.',
    'match': 'One penalty in the 90th minute at 1-1. Rebounds are live.',
    'party': 'King of the Goal or a knockout bracket for 3 to 8 friends.',
    'training': 'Practise against the drill machine. T shows the trajectory.',
    'tournament': 'Eight teams, every tie on penalties. The keepers get sharper each round.',
    'daily': 'The same shootout for everyone today. Share your result grid.',
    'ghost': "Face a friend's kicks exactly as struck. Press B after any shootout to save your own.",
    'tutorial': 'A coach walks you through the controls, step by step.',
}


def mode_hint(g):
    if g.mode == 'famous':
        return SCENARIOS[g.scenario]['intro'][:110] + ('...' if len(SCENARIOS[g.scenario]['intro']) > 110 else '')
    if g.mode == 'challenge':
        best = g.stats['challenges'].get(g.challenge, 0)
        return CHALLENGES[g.challenge]['desc'] + f'  Best: {best}'
    if g.mode == 'career':
        c = g.stats['career'].get(g.role) or {}
        xp = c.get('xp', 0)
        nxt = next((n for n in CAREER_XP if n > xp), None)
        traits = ', '.join(c.get('traits', [])) or 'none yet'
        left = f'next unlock at {nxt} XP' if nxt else 'all traits unlocked'
        gold = '  |  GOLD KIT' if c.get('gold') else ''
        names = ', '.join(n for n, _ in CAREER_TRAITS[g.role])
        return f"{xp} XP, {c.get('wins', 0)}/{c.get('games', 0)} won, {left}. Traits: {traits}{gold}" if c else \
            f'Climb from easy fixtures to hard ones. Unlock: {names}'
    return MODE_HINTS.get(g.mode, '')


def achievements_overlay(g):
    got = set(g.stats.get('achievements', []))
    rect(150, 110, 700, 600, (0.04, 0.05, 0.09), 0.97)
    outline(150, 110, 700, 600, GOLD)
    big_text(500, 660, f'ACHIEVEMENTS  {len(got)}/{len(achievements.ACHIEVEMENTS)}', 26, GOLD, 3)
    y = 620
    for key, name, desc in achievements.ACHIEVEMENTS:
        have = key in got
        circle(185, y + 5, 7, GOLD if have else GREY)
        text(200, y, name, MEDIUM, GOLD if have else (0.75, 0.75, 0.8))
        text(400, y, desc, SMALL, WHITE if have else (0.6, 0.6, 0.65))
        y -= 31
    text(500, 125, 'L or ENTER to close', SMALL, (0.8, 0.8, 0.85), 'center')


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
    if g.ui == 'select':
        select_screen(g)
    elif g.ui == 'create':
        create_screen(g)
    elif g.ui == 'menu':
        menu(g)
        if g.rebind is not None:
            rebind_overlay(g)
        if g.show_achievements:
            achievements_overlay(g)
    elif g.photo:
        text(500, 34, 'PHOTO MODE: A/D orbit, W/S height, Q/E zoom, ENTER save, Y exit', SMALL, WHITE, 'center')
        on = {True: 'on', False: 'off'}
        text(500, 16, f'F filter: {g.photo_filter}   G focus: {on[g.photo_dof]}   B frame: {on[g.photo_frame]}'
                      f'   T name: {on[g.photo_stamp]}', SMALL, GOLD, 'center')
    else:
        scoreboard(g)
        wind_gauge(g)
        if g.phase == 'runup' and (g.is_human(g.kicker) or g.power is not None):
            power_bar(g)
        prompts(g)
        banners(g)
        banter(g)
        notes_panel(g)
        coach_panel(g)
        commentary_line(g)
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


# ------------------------------------------------------- character screens
def _fig(p):
    return dict(look=p.look, name=p.name, number=p.number, aura=p.aura, glow=p.glow, kit=p.kit_override)


def showcase_subject(g):
    """Who stands on the turntable: (fig, is a keeper, celebration or None)."""
    if g.ui == 'create' and g.create:
        p = g.create_player()
    elif g.ui == 'select' and g.select:
        ch = g.select_current()
        if ch is None:
            return None, False, None
        p = CH.make_player(ch)
    else:
        return None, False, None
    cel = p.celebration if (g.clock % 8.0) > 4.5 else None
    if p.keeper and cel not in CH.SAVE_CELEBRATIONS:
        cel = 'dance' if cel else None
    return _fig(p), p.keeper, cel


def _bar(x, y, label, val, w=200):
    text(x, y + 12, label, SMALL, (0.8, 0.8, 0.85))
    rect(x, y, w, 8, GREY, 0.6)
    rect(x, y, w * max(0.0, min(1.0, val)), 8, GREEN if val > 0.75 else GOLD if val > 0.5 else RED)
    text(x + w + 8, y - 2, f'{100 * val:.0f}', SMALL, WHITE)


def character_card(g, p, x, y, w, h, locked=False, unlock=None):
    """Stats, personality, signature and celebration for one character."""
    rect(x, y, w, h, (0.04, 0.05, 0.09), 0.92)
    outline(x, y, w, h, p.glow or GOLD)
    top = y + h
    big_text(x + w / 2, top - 52, p.name, 30, p.glow or GOLD, 3)
    text(x + w / 2, top - 78, f"{p.full}  |  No. {p.number}  |  {'Left' if p.foot == 'L' else 'Right'} foot",
         SMALL, WHITE, 'center')
    text(x + w / 2, top - 98, f"{CH.ERAS.get(p.era, '')}  |  {p.tag}"[:70], SMALL, (0.85, 0.85, 0.9), 'center')
    yy = top - 135
    if p.keeper:
        _bar(x + 24, yy, 'Reach bonus', 0.5 + 4.0 * p.reach)
        _bar(x + 24, yy - 34, 'Speed bonus', 0.5 + 8.0 * p.speed)
        _bar(x + 24, yy - 68, 'Kicking (if it goes round)', (p.composure + p.power + p.placement) / 3)
        personas = CH.KEEPER_PERSONAS
        cels = CH.SAVE_CELEBRATIONS
    else:
        _bar(x + 24, yy, 'Composure', p.composure)
        _bar(x + 24, yy - 34, 'Power', p.power)
        _bar(x + 24, yy - 68, 'Placement', p.placement)
        personas = CH.TAKER_PERSONAS
        cels = CH.CELEBRATIONS
    _bar(x + 24, yy - 102, 'Aura', p.aura)
    yy -= 140
    pname, pdesc = personas.get(p.persona, ('', ''))
    text(x + 24, yy, pname.upper(), MEDIUM, GOLD)
    for ln in wrap(pdesc, w - 48)[:2]:
        yy -= 18
        text(x + 24, yy, ln, SMALL, WHITE)
    if p.signature in CH.SIGNATURES:
        sname, sdesc = CH.SIGNATURES[p.signature]
        yy -= 28
        text(x + 24, yy, 'SIGNATURE: ' + sname.upper(), SMALL, GOLD)
        for ln in wrap(sdesc, w - 48)[:2]:
            yy -= 18
            text(x + 24, yy, ln, SMALL, WHITE)
    if p.celebration:
        yy -= 28
        text(x + 24, yy, 'CELEBRATION: ' + cels.get(p.celebration, CH.CELEBRATIONS.get(p.celebration, p.celebration)),
             SMALL, GOLD)
    form = g.stats.get('form', {}).get(p.char or '', 0)
    if form:
        yy -= 22
        text(x + 24, yy, {2: 'Form: red hot', 1: 'Form: good', -1: 'Form: shaky', -2: 'Form: cold'}[form], SMALL,
             GREEN if form > 0 else RED)
    if locked:
        rect(x, y, w, 44, (0.25, 0.05, 0.05), 0.9)
        text(x + w / 2, y + 16, f"LOCKED: unlock '{achievements.NAMES.get(unlock, unlock)}'", MEDIUM, WHITE, 'center')


def select_screen(g):
    sel = g.select
    step = sel['plan'][sel['step']]
    big_text(500, 740, step['who'], 26, GOLD, 3)
    text(500, 712, f"Step {sel['step'] + 1} of {len(sel['plan'])}", SMALL, (0.8, 0.8, 0.85), 'center')
    # Filter tabs
    tabs = [f for f in CH.FILTERS if CH.filtered(f, step['role'])]
    x = 500 - 116 * len(tabs) / 2
    for f in tabs:
        on = f == sel['filter']
        rect(x + 2, 670, 112, 26, (0.16, 0.45, 0.25) if on else (0.08, 0.09, 0.14), 0.92)
        text(x + 58, 678, CH.FILTER_LABELS[f], SMALL, WHITE, 'center')
        x += 116
    lst = g.select_list()
    ch = g.select_current()
    if ch is None:
        text(500, 400, 'Nobody here yet', MEDIUM, WHITE, 'center')
        return
    p = CH.make_player(ch)
    character_card(g, p, 590, 120, 390, 530, CH.locked(ch, g.stats), ch.get('unlock'))
    # Carousel of names under the figure
    i = sel['cursor'] % len(lst)
    picked_all = g._all_picked()
    for k in range(-3, 4):
        c = lst[(i + k) % len(lst)]
        cx = 290 + k * 82
        col = GOLD if k == 0 else (0.55, 0.55, 0.6) if CH.locked(c, g.stats) or c['key'] in picked_all else WHITE
        if k == 0:
            rect(cx - 41, 128, 82, 24, (0.16, 0.45, 0.25), 0.9)
        text(cx, 135, c['name'][:9], SMALL, col, 'center')
    text(290, 106, f'{i + 1} / {len(lst)}', SMALL, (0.8, 0.8, 0.85), 'center')
    # Picks so far
    y = 640
    for st in sel['plan']:
        keys = sel['picked'].get(st['key'], [])
        if not keys:
            continue
        names = ', '.join(CH.get(k)['name'] for k in keys if CH.get(k))
        text(20, y, f"{st['key'].replace('_keeper', ' keeper').upper()}: {names}"[:60], SMALL, GREEN)
        y -= 18
    rect(0, 38, W, 48, (0.02, 0.03, 0.06), 0.8)
    text(500, 70, 'A/D browse  |  W/S filter  |  ENTER pick  |  X undo  |  R random  |  C create a player  |  '
         'ESC back', SMALL, WHITE, 'center')
    text(500, 48, 'Real names are game caricatures: famous moments and celebrations, not real ratings.', SMALL,
         (0.6, 0.6, 0.65), 'center')


CREATE_LABELS = {'name': 'Name', 'role': 'Position', 'number': 'Number', 'foot': 'Foot', 'women': 'Plays in',
                 'skin': 'Skin tone', 'hair': 'Hair', 'hc': 'Hair colour', 'beard': 'Beard', 'h': 'Height',
                 'w': 'Build', 'boots': 'Boots', 'persona': 'Personality', 'signature': 'Signature move',
                 'celebration': 'Celebration', 'composure': 'Composure', 'power': 'Power', 'placement': 'Placement',
                 'save': ''}


def _create_value(g, f):
    ch = g.create['ch']
    lk = ch['look']
    if f == 'name':
        return ch['name'] + ('_' if g.create['typing'] and int(g.clock * 2) % 2 == 0 else '')
    if f == 'role':
        return 'Goalkeeper' if ch['role'] == 'keep' else 'Outfield (takes kicks)'
    if f == 'women':
        return "Women's game" if ch['women'] else "Men's game"
    if f == 'foot':
        return 'Left' if ch['foot'] == 'L' else 'Right'
    if f in ('hair', 'hc', 'boots'):
        return str(lk.get(f)).capitalize()
    if f == 'beard':
        return (lk.get('beard') or 'None').capitalize()
    if f == 'skin':
        return f"Tone {lk['skin'] + 1}"
    if f in ('h', 'w'):
        return f'{100 * lk[f]:.0f}%'
    if f == 'persona':
        return (CH.KEEPER_PERSONAS if ch['role'] == 'keep' else CH.TAKER_PERSONAS)[ch['persona']][0]
    if f == 'signature':
        return CH.SIGNATURES[ch['signature']][0] if ch['signature'] else 'None'
    if f == 'celebration':
        return (CH.SAVE_CELEBRATIONS if ch['role'] == 'keep' else CH.CELEBRATIONS).get(ch['celebration'], 'None')
    if f in ('composure', 'power', 'placement'):
        return f'{100 * ch[f]:.0f}'
    if f == 'number':
        return str(ch['number'])
    return ''


def create_screen(g):
    cr = g.create
    big_text(500, 745, 'CREATE A PLAYER', 30, GOLD, 3)
    x, top, w = 560, 700, 420
    rect(x, 40, w, top - 40, (0.04, 0.05, 0.09), 0.92)
    outline(x, 40, w, top - 40, GOLD)
    y = top - 34
    for i, f in enumerate(CH.CREATE_FIELDS):
        focused = i == cr['field']
        if f == 'save':
            _button(x + 110, y - 8, 200, 30, 'SAVE PLAYER', True, focused)
            break
        if focused:
            rect(x + 8, y - 6, w - 16, 22, (0.16, 0.4, 0.22), 0.9)
        text(x + 20, y, CREATE_LABELS[f], SMALL, GOLD if focused else WHITE)
        text(x + w - 20, y, _create_value(g, f), SMALL, WHITE, 'right')
        y -= 33
    left = CH.budget_left(cr['ch'])
    text(x + w / 2, 50, f'Rating points left: {100 * left:.0f}', SMALL, GREEN if left > 0 else GOLD, 'center')
    rect(10, 40, 540, 46, (0.02, 0.03, 0.06), 0.8)
    hint = ('Type the name, ENTER to finish' if cr['typing'] else
            'W/S field  |  A/D change  |  ENTER edit name or save  |  ESC back')
    text(280, 70, hint, SMALL, WHITE, 'center')
    text(280, 50, 'Saved to players.json in the .penalty_shootout folder', SMALL, (0.6, 0.6, 0.65), 'center')
