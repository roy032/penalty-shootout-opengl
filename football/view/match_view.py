"""Draws a sim.Match: the stadium, every player, the ball, markers and the camera.
Can draw from the live match or from a replay snapshot."""

import math

from panda3d.core import TransparencyAttrib, TextNode, NodePath, ColorBlendAttrib

from . import geom as G
from . import textures as T
from .camera import Camera
from .models import Ball, Footballer
from .world import World

MARKER_COLORS = [(0.25, 0.75, 1.0), (1.0, 0.35, 0.3), (0.4, 1.0, 0.45), (1.0, 0.85, 0.2)]


class MatchView:
    def __init__(self, base, match, quality='high', night=True, cam_mode='broadcast', guides=True):
        self.base = base
        self.match = match
        self.guides = guides
        a, b = match.teams
        self.world = World(base, match.pitch, a.info['shirt'], b.info['shirt'], night=night, quality=quality)
        self.root = base.render.attach_new_node('actors')
        self.models = {}
        for t in match.teams:
            for p in t.players:
                self.models[(t.idx, p.idx)] = Footballer(self.root, p.fb, t.info, keeper=p.keeper, quality=quality)
        self.ball = Ball(self.root, quality)
        self.cam = Camera(base, match.pitch, cam_mode)
        self.t = 0.0
        self.excite = 0.0
        self._markers()
        self._guides()
        self.cam.snap(match.ball.pos, None)

    def _markers(self):
        ring = T.ring(128, (1, 1, 1))
        glow = T.radial(64, (1, 1, 1), 1.4)
        self.markers = []
        for i, col in enumerate(MARKER_COLORS):
            n = G.plane(1.5, 1.5).node()
            n.reparent_to(self.root)
            n.set_texture(ring)
            n.set_color(col[0], col[1], col[2], 0.95)
            n.set_transparency(TransparencyAttrib.M_alpha)
            n.set_light_off()
            n.set_shader_off()
            n.set_depth_offset(3)
            n.set_bin('transparent', 20)
            n.hide()
            # Name above the head
            tn = TextNode('name%d' % i)
            tn.set_align(TextNode.A_center)
            tn.set_text_color(col[0], col[1], col[2], 1)
            tn.set_shadow(0.06, 0.06)
            tn.set_shadow_color(0, 0, 0, 0.8)
            lab = self.root.attach_new_node(tn)
            lab.set_scale(0.42)
            lab.set_billboard_point_eye()
            lab.set_light_off()
            lab.set_shader_off()
            lab.set_depth_test(False)
            lab.set_depth_write(False)
            lab.set_bin('fixed', 30)
            lab.hide()
            self.markers.append((n, lab, tn))
        # A soft halo under the ball when it's in the air, to read its height
        self.ball_spot = G.plane(0.5, 0.5).node()
        self.ball_spot.reparent_to(self.root)
        self.ball_spot.set_texture(glow)
        self.ball_spot.set_color(1, 1, 0.7, 0.5)
        self.ball_spot.set_transparency(TransparencyAttrib.M_alpha)
        self.ball_spot.set_light_off()
        self.ball_spot.set_shader_off()
        self.ball_spot.set_depth_offset(3)
        self.ball_spot.set_bin('transparent', 21)

    def _flat(self, sx, sy, tex, col, alpha, bin_order):
        n = G.plane(sx, sy).node()
        n.reparent_to(self.root)
        if tex is not None:
            n.set_texture(tex)
        n.set_color(col[0], col[1], col[2], alpha)
        n.set_transparency(TransparencyAttrib.M_alpha)
        n.set_light_off()
        n.set_shader_off()
        n.set_depth_offset(3)
        n.set_depth_write(False)
        n.set_bin('transparent', bin_order)
        n.hide()
        return n

    def _guides(self):
        """Pass target, through-ball lane, next switch and the offside line (Match.guide)."""
        ring = T.ring(128, (1, 1, 1), 0.24)
        glow = T.radial(64, (1, 1, 1), 1.2)
        self.guide_nodes = []
        k = 1.5 if self.match.pitch.length > 80 else 1.0     # bigger on a full pitch, seen from further away
        for i in range(len(self.match.controllers)):
            col = MARKER_COLORS[i % len(MARKER_COLORS)]
            self.guide_nodes.append(dict(
                pass_to=self._flat(1.2 * k, 1.2 * k, ring, col, 0.9, 18),
                lane=self._flat(0.3 * k, 1.0, None, col, 0.35, 17),
                lead=self._flat(1.0 * k, 1.0 * k, glow, col, 0.75, 17),
                switch=self._flat(1.3 * k, 1.3 * k, ring, (1, 1, 1), 0.45, 18)))
        pt = self.match.pitch
        self.offside_line = self._flat(0.1, pt.width, None, (1.0, 0.95, 0.35), 0.55, 16)
        self.guide_cache = [None] * len(self.match.controllers)
        self.guide_t = 0.0

    def _sync_guides(self, dt, live):
        m = self.match
        nodes = self.guide_nodes
        show = self.guides and live and m.state in ('play', 'kickoff', 'restart')
        self.guide_t -= dt
        if show and self.guide_t <= 0:
            # Ten times a second is plenty, and the switch target costs a few ball predictions
            self.guide_t = 0.1
            self.guide_cache = [m.guide(c) for c in m.controllers]
        line = None
        pulse = 0.85 + 0.15 * math.sin(self.t * 7.0)
        for i, n in enumerate(nodes):
            g = self.guide_cache[i] if show and i < len(self.guide_cache) else None
            q = g and g['pass_to']
            if q is not None and not q.sent_off:
                n['pass_to'].show()
                n['pass_to'].set_pos(q.pos[0], q.pos[1], 0.025)
                n['pass_to'].set_scale(pulse)
            else:
                n['pass_to'].hide()
            th = g and g['through']
            if th is not None:
                mate, (lx, ly) = th
                mx, my = mate.pos
                d = math.hypot(lx - mx, ly - my)
                n['lead'].show()
                n['lead'].set_pos(lx, ly, 0.022)
                if d > 1.0:
                    n['lane'].show()
                    n['lane'].set_pos((lx + mx) / 2.0, (ly + my) / 2.0, 0.021)
                    n['lane'].set_h(math.degrees(math.atan2(ly - my, lx - mx)) - 90.0)
                    n['lane'].set_sy(d)
                else:
                    n['lane'].hide()
            else:
                n['lead'].hide()
                n['lane'].hide()
            sw = g and g['switch']
            if sw is not None and not sw.sent_off:
                n['switch'].show()
                n['switch'].set_pos(sw.pos[0], sw.pos[1], 0.024)
                n['switch'].set_h(-math.degrees(self.t * 1.5))
            else:
                n['switch'].hide()
            if g and g['offside'] is not None:
                line = g['offside']
        if line is not None:
            self.offside_line.show()
            self.offside_line.set_pos(line, 0.0, 0.02)
        else:
            self.offside_line.hide()

    # ------------------------------------------------------------- per frame
    def sync(self, dt, snapshot=None, replay_angle=None, replay_t=0.0):
        m = self.match
        self.t += dt
        players = [p for t in m.teams for p in t.players]
        if snapshot is None:
            b = m.ball
            ball = tuple(b.pos)
            self.ball.pose(ball, b.roll_axis, b.roll_angle)
            for p in players:
                mdl = self.models[(p.team.idx, p.idx)]
                if p.sent_off:
                    mdl.root.hide()
                    continue
                mdl.root.show()
                mdl.pose(p.pos[0], p.pos[1], p.z, p.facing, p.state, p.anim, p.state_t, p.run_phase, p.speed(),
                         p.dive_dir, p.state_len, holding=m.ball.holder is p, t=self.t)
        else:
            ball, axis, angle, rows = snapshot
            self.ball.pose(ball, axis, angle)
            for p, row in zip(players, rows):
                x, y, z, facing, state, anim, st, phase, speed, dive = row
                mdl = self.models[(p.team.idx, p.idx)]
                mdl.pose(x, y, z, facing, state, anim, st, phase, speed, dive, 0.5, t=self.t)
        # Ball height marker
        self.ball_spot.set_pos(ball[0], ball[1], 0.02)
        hgt = max(0.0, ball[2] - 0.11)
        self.ball_spot.set_alpha_scale(min(1.0, hgt * 0.6) if snapshot is None else 0.0)
        self.ball_spot.set_scale(1.0 + hgt * 0.3)
        # Markers for the humans' players
        for i, (ring, lab, tn) in enumerate(self.markers):
            c = m.controllers[i] if i < len(m.controllers) else None
            p = c.player if c else None
            if p is None or snapshot is not None or p.sent_off or m.state in ('goal', 'fulltime'):
                ring.hide()
                lab.hide()
                continue
            ring.show()
            lab.show()
            ring.set_pos(p.pos[0], p.pos[1], 0.02)
            ring.set_h(math.degrees(self.t * 1.5))
            lab.set_pos(p.pos[0], p.pos[1], 2.35 * p.fb.look.get('h', 1.0) + p.z)
            # Constant size on screen, whatever the camera distance
            d = (self.base.camera.get_pos(self.base.render) - lab.get_pos(self.base.render)).length()
            lab.set_scale(max(0.12, min(0.9, d * 0.022)))
            text = p.fb.name
            if c.charge is not None:
                text = p.fb.name
            if tn.get_text() != text:
                tn.set_text(text)
        self._sync_guides(dt, snapshot is None)
        # Crowd
        self.world.update(dt, self.t, self.excite)
        self.excite = max(0.0, self.excite - dt * 0.15)
        # Camera
        if snapshot is not None:
            self.cam.replay(dt, ball, replay_angle or 'side', replay_t)
        else:
            focus = None
            for c in m.controllers:
                if c.player is not None:
                    focus = (c.player.pos[0], c.player.pos[1])
                    attack = c.team.attack
                    break
            else:
                attack = m.teams[0].attack
            zoom = 1.0
            # Zoom in a touch when the ball is near either goal
            if abs(ball[0]) > m.pitch.half_length * 0.6:
                zoom = 1.08
            self.cam.update(dt, ball, focus, attack, zoom)

    def destroy(self):
        self.root.remove_node()
        self.world.root.remove_node()
        self.world.sky.remove_node()
