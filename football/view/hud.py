"""In-match overlay: scoreboard, banners, captions, power bar, radar, prompts.
Everything hangs off aspect2d's corners, so it scales with the window."""

import math

from direct.gui.DirectGui import DirectFrame
from direct.gui.OnscreenText import OnscreenText
from panda3d.core import TextNode, TransparencyAttrib

from .inputs import key_label
from ..sim.match import PEN_SWEET
from .weather_fx import wind_text

PANEL = (0.03, 0.04, 0.07, 0.78)
GOLD = (1.0, 0.82, 0.3, 1)


def _txt(parent, text='', pos=(0, 0), scale=0.05, fg=(1, 1, 1, 1), align=TextNode.A_left, shadow=True, font=None):
    t = OnscreenText(text=text, pos=pos, scale=scale, fg=fg, align=align, parent=parent, mayChange=True,
                     shadow=(0, 0, 0, 0.75) if shadow else None, font=font)
    return t


class Hud:
    def __init__(self, base, match, inputs, font=None, show_hints=True):
        self.base = base
        self.m = match
        self.inputs = inputs
        self.font = font
        self.show_hints = show_hints
        a, b = match.teams
        tl = base.a2dTopLeft
        # Scoreboard
        self.board = DirectFrame(parent=tl, frameColor=PANEL, frameSize=(0, 0.78, -0.13, 0), pos=(0.04, 0, -0.04))
        self.chip_a = DirectFrame(parent=self.board, frameColor=a.info['shirt'] + (1,), frameSize=(0, 0.018, -0.1, -0.03),
                                  pos=(0.02, 0, 0))
        self.chip_b = DirectFrame(parent=self.board, frameColor=b.info['shirt'] + (1,), frameSize=(0, 0.018, -0.1, -0.03),
                                  pos=(0.49, 0, 0))
        self.name_a = _txt(self.board, a.short, (0.05, -0.088), 0.055, font=font)
        self.name_b = _txt(self.board, b.short, (0.52, -0.088), 0.055, font=font)
        self.score = _txt(self.board, '0 - 0', (0.335, -0.09), 0.065, GOLD, TextNode.A_center, font=font)
        self.clock = DirectFrame(parent=self.board, frameColor=(0.85, 0.12, 0.15, 0.95), frameSize=(0, 0.2, -0.065, 0),
                                 pos=(0.0, 0, -0.135))
        self.clock_t = _txt(self.clock, "0'", (0.1, -0.048), 0.045, align=TextNode.A_center, font=font)
        self.pens = _txt(self.board, '', (0.335, -0.2), 0.042, (1, 1, 1, 1), TextNode.A_center, font=font)
        # Weather, and which way the wind blows for the first human's side
        att = match.controllers[0].team.attack if match.controllers else a.attack
        self.wx = _txt(self.board, wind_text(match.weather, att), (0.22, -0.183), 0.036, (0.85, 0.9, 1.0, 1),
                       font=font)
        self.wx_att = att
        # Banner
        self.banner = _txt(base.aspect2d, '', (0, 0.28), 0.16, GOLD, TextNode.A_center, font=font)
        self.sub = _txt(base.aspect2d, '', (0, 0.18), 0.06, (1, 1, 1, 1), TextNode.A_center, font=font)
        self.banner_t = 0.0
        # Caption
        self.cap_bg = DirectFrame(parent=base.a2dBottomCenter, frameColor=(0, 0, 0, 0.55),
                                  frameSize=(-0.9, 0.9, -0.05, 0.05), pos=(0, 0, 0.26))
        self.cap = _txt(self.cap_bg, '', (0, -0.018), 0.05, align=TextNode.A_center, font=font)
        self.cap_t = 0.0
        self.cap_bg.hide()
        # Power bar
        self.pbar = DirectFrame(parent=base.a2dBottomCenter, frameColor=PANEL, frameSize=(-0.32, 0.32, -0.03, 0.03),
                                pos=(0, 0, 0.16))
        self.pfill = DirectFrame(parent=self.pbar, frameColor=(0.3, 0.9, 0.4, 1), frameSize=(0, 0.6, -0.022, 0.022),
                                 pos=(-0.3, 0, 0))
        self.ptxt = _txt(self.pbar, 'POWER', (0, 0.045), 0.04, align=TextNode.A_center, font=font)
        # The sweet spot for a spot kick: hit it there and it stays down
        lo, hi = PEN_SWEET
        self.psweet = DirectFrame(parent=self.pbar, frameColor=(1, 1, 1, 0.22),
                                  frameSize=(0, 0.6 * (hi - lo), -0.03, 0.03), pos=(-0.3 + 0.6 * lo, 0, 0))
        self.psweet.hide()
        self.pbar.hide()
        # Shootout win chances
        self.odds = _txt(self.board, '', (0.335, -0.25), 0.034, (0.85, 0.9, 1.0, 1), TextNode.A_center, font=font)
        # Stamina of the player you control
        self.stam = DirectFrame(parent=base.a2dBottomCenter, frameColor=(0, 0, 0, 0.5), frameSize=(-0.2, 0.2, -0.008, 0.008),
                                pos=(0, 0, 0.1))
        self.stam_fill = DirectFrame(parent=self.stam, frameColor=(0.95, 0.85, 0.3, 0.9),
                                     frameSize=(0, 0.4, -0.007, 0.007), pos=(-0.2, 0, 0))
        # Radar
        pt = match.pitch
        self.rw = 0.42
        self.rh = self.rw * pt.width / pt.length
        self.radar = DirectFrame(parent=base.a2dBottomRight, frameColor=(0.05, 0.25, 0.08, 0.6),
                                 frameSize=(-self.rw / 2, self.rw / 2, -self.rh / 2, self.rh / 2),
                                 pos=(-self.rw / 2 - 0.05, 0, self.rh / 2 + 0.05))
        DirectFrame(parent=self.radar, frameColor=(1, 1, 1, 0.35), frameSize=(-0.002, 0.002, -self.rh / 2, self.rh / 2))
        self.dots = []
        for t in match.teams:
            for p in t.players:
                d = DirectFrame(parent=self.radar, frameColor=t.info['shirt'] + (1,),
                                frameSize=(-0.011, 0.011, -0.011, 0.011))
                self.dots.append((p, d))
        self.ball_dot = DirectFrame(parent=self.radar, frameColor=(1, 1, 1, 1), frameSize=(-0.008, 0.008, -0.008, 0.008))
        self.me_dots = [DirectFrame(parent=self.radar, frameColor=(0.25, 0.75, 1.0, 1), frameSize=(-0.017, 0.017, -0.017, 0.017)),
                        DirectFrame(parent=self.radar, frameColor=(1.0, 0.35, 0.3, 1), frameSize=(-0.017, 0.017, -0.017, 0.017))]
        for d in self.me_dots:
            d.set_bin('fixed', 1)
            d.hide()
        # Context prompt
        self.hint = _txt(base.a2dBottomLeft, '', (0.05, 0.06), 0.042, (0.9, 0.95, 1.0, 0.95), font=font)
        self.replay_tag = DirectFrame(parent=base.a2dTopRight, frameColor=(0.85, 0.12, 0.15, 0.9),
                                      frameSize=(-0.36, 0, -0.08, 0), pos=(-0.05, 0, -0.05))
        _txt(self.replay_tag, 'REPLAY', (-0.18, -0.058), 0.05, align=TextNode.A_center, font=font)
        _txt(self.replay_tag, 'press any button to skip', (-0.18, -0.12), 0.032, align=TextNode.A_center, font=font)
        self.replay_tag.hide()
        self.nodes = [self.board, self.banner, self.sub, self.cap_bg, self.pbar, self.stam, self.radar, self.hint,
                      self.replay_tag]

    def destroy(self):
        for n in self.nodes:
            n.destroy()

    def set_visible(self, on):
        for n in (self.board, self.radar, self.stam, self.hint):
            n.show() if on else n.hide()

    # --------------------------------------------------------- messages
    def flash(self, text, sub='', t=2.2, color=GOLD):
        self.banner.setText(text)
        self.banner.setFg(color)
        self.sub.setText(sub)
        self.banner_t = t

    def caption(self, text, t=3.0):
        self.cap.setText(text)
        self.cap_bg.show()
        self.cap_t = t
        w = max(0.4, len(text) * 0.026)
        self.cap_bg['frameSize'] = (-w, w, -0.05, 0.05)

    # --------------------------------------------------------- per frame
    def update(self, dt, replaying=False):
        m = self.m
        a, b = m.teams
        self.score.setText('%d - %d' % (a.score, b.score))
        att = m.controllers[0].team.attack if m.controllers else a.attack
        if att != self.wx_att:
            # Ends changed at half-time, so the wind did too
            self.wx_att = att
            self.wx.setText(wind_text(m.weather, att))
        minute = int(m.clock())
        self.clock_t.setText("%d'" % min(minute + 1, 90 if m.half <= 2 else 120) if not m.shootout else 'PENS')
        if m.shootout:
            def dots(t):
                return ' '.join('O' if x else 'X' for x in t.pens) or '-'
            self.pens.setText('%s  |  %s' % (dots(a), dots(b)))
            odds = m.penalty_odds()
            self.odds.setText('WIN %d%%  |  %d%%' % (round(odds * 100), round((1 - odds) * 100)))
        else:
            self.pens.setText('')
            self.odds.setText('')
        # Banner fade
        if self.banner_t > 0:
            self.banner_t -= dt
            al = min(1.0, self.banner_t * 2.0)
            self.banner.setAlphaScale(al)
            self.sub.setAlphaScale(al)
            s = 1.0 + max(0.0, self.banner_t - 1.8) * 0.6
            self.banner.setScale(0.16 * s)
        else:
            self.banner.setText('')
            self.sub.setText('')
        if self.cap_t > 0:
            self.cap_t -= dt
            if self.cap_t <= 0:
                self.cap_bg.hide()
        self.replay_tag.show() if replaying else self.replay_tag.hide()
        # Power and stamina for player 1
        c = m.controllers[0] if m.controllers else None
        if c and c.charge is not None and not replaying:
            self.pbar.show()
            f = max(0.0, min(1.0, c.charge))
            self.pfill['frameSize'] = (0, 0.6 * f, -0.022, 0.022)
            pen = m.restart is not None and m.restart['kind'] == 'penalty' and not m.restart.get('taken')
            self.psweet.show() if pen else self.psweet.hide()
            hot = f > (PEN_SWEET[1] if pen else 0.85)
            self.pfill['frameColor'] = (0.95, 0.3, 0.2, 1) if hot else ((0.95, 0.8, 0.2, 1) if f > 0.6 else (0.3, 0.9, 0.4, 1))
        else:
            self.pbar.hide()
        if c and c.player is not None and not replaying:
            self.stam.show()
            self.stam_fill['frameSize'] = (0, 0.4 * c.player.stamina, -0.007, 0.007)
        else:
            self.stam.hide()
        # Radar
        pt = m.pitch
        sx, sy = self.rw / pt.length, self.rh / pt.width
        for p, d in self.dots:
            if p.sent_off:
                d.hide()
                continue
            d.set_pos(p.pos[0] * sx, 0, p.pos[1] * sy)
        self.ball_dot.set_pos(m.ball.pos[0] * sx, 0, m.ball.pos[1] * sy)
        for i, dd in enumerate(self.me_dots):
            cc = m.controllers[i] if i < len(m.controllers) else None
            if cc and cc.player is not None:
                dd.show()
                dd.set_pos(cc.player.pos[0] * sx, 0, cc.player.pos[1] * sy)
            else:
                dd.hide()
        # Contextual prompt: one line, for what you can do right now
        self.hint.setText(self._hint(c) if self.show_hints and not replaying else '')

    def _hint(self, c):
        if c is None or c.player is None:
            return ''
        m = self.m
        k = self.inputs.keys[0]
        pad = self.inputs.pad_count() > 0
        L = (lambda a, p: p) if pad else (lambda a, p: key_label(k[a]))
        b = m.ball
        r = m.restart
        if m.state in ('kickoff', 'restart') and r and r['kind'] == 'penalty' and r['team'] is not c.team \
                and not r.get('taken'):
            gk = c.team.keeper()
            pick = getattr(gk, 'pen_commit', None) if gk else None
            if pick is not None:
                where = 'centre' if abs(pick[0]) < 0.1 else ('to your left' if pick[0] * c.team.attack > 0
                                                             else 'to your right')
                return 'Diving %s%s | change it any time before the kick' % (where, ', high' if pick[1] > 1 else '')
            return 'Pick a dive: stick to a side + %s (hold %s for high) | or leave it and he guesses' % (
                L('pass', 'A'), L('lob', 'X'))
        if m.state in ('kickoff', 'restart') and r and r['team'] is c.team and not r.get('taken'):
            if r['kind'] == 'penalty':
                return 'Aim with the stick | %s hold for power, release in the white zone | %s curl | %s Panenka' % (
                    L('shoot', 'B'), L('finesse', 'RB'), L('lob', 'X'))
            return '%s pass | %s through | %s lob' % (L('pass', 'A'), L('through', 'Y'), L('lob', 'X'))
        if b.owner is c.player:
            return '%s pass | %s shoot (hold) | %s through | %s lob | %s sprint | %s skill' % (
                L('pass', 'A'), L('shoot', 'B'), L('through', 'Y'), L('lob', 'X'), L('sprint', 'RT'), L('skill', 'LT'))
        own = b.owner is not None and b.owner.team is c.team
        if b.owner is not None and not own:
            return '%s hold to press, tap to tackle | %s slide | %s switch | %s call a team-mate | %s keeper out' % (
                L('pass', 'A'), L('shoot', 'B'), L('switch', 'LB'), L('through', 'Y'), L('lob', 'X'))
        return '%s switch | %s or %s first-time pass or shot' % (L('switch', 'LB'), L('pass', 'A'), L('shoot', 'B'))
