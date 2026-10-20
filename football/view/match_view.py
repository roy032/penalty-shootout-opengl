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
    def __init__(self, base, match, quality='high', night=True, cam_mode='broadcast'):
        self.base = base
        self.match = match
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
