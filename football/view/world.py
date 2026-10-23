"""The stadium: pitch, markings, goals and nets, cage boards, stands and
crowd, floodlights, sky and lighting."""

import math
import random

from panda3d.core import (AmbientLight, DirectionalLight, Fog, TransparencyAttrib, Vec3, Vec4,
                          ColorBlendAttrib, BitMask32, TextureStage)

from . import geom as G
from . import shading as S
from . import textures as T

LINE = (0.93, 0.94, 0.92, 1)
SHADOW_MASK = BitMask32.bit(1)


def _dim(c, k):
    return tuple(max(0.0, min(1.0, v * k)) for v in c[:3])


class World:
    def __init__(self, base, pitch, home_colors, away_colors, night=True, quality='high'):
        self.base = base
        self.pitch = pitch
        self.night = night
        self.quality = quality
        self.home = tuple(home_colors[:3])
        self.away = tuple(away_colors[:3])
        self.root = base.render.attach_new_node('world')
        self.crowd_nodes = []
        self.cheer = 0.0
        self.wet = 0.0
        self.frames = 0
        self.t = 0.0
        self._lights()
        self._sky()
        self._pitch()
        self._goals()
        if pitch.walls:
            self._cage()
        else:
            self._boards()
        self._stands(home_colors, away_colors)
        self._floodlights()
        self.lighting = None
        try:
            self.lighting = S.Lighting(base, self, quality)
            if not night and not pitch.walls:
                # The main stand (camera side) throws its shadow over the near touchline
                self.lighting.set_stand_shadow(-(pitch.half_width + self.gap), self.near_stand_top, 1.4)
        except Exception as exc:        # very old drivers: Panda's own shaders instead
            import traceback
            traceback.print_exc()
            print('Shaders disabled:', exc)
            self._fallback()

    def _fallback(self):
        self.lighting = None
        self.base.render.clear_shader()
        self.grass.clear_shader()
        self.grass.set_color(0.22, 0.48, 0.17, 1)
        self.grass.set_tex_scale(TextureStage.get_default(), 30, 20)
        self.sky.set_shader_off()
        self.line_mesh.show()
        if self.quality != 'low':
            self.base.render.set_shader_auto()

    # ------------------------------------------------------------ lighting
    def _lights(self):
        r = self.root
        pt = self.pitch
        amb = AmbientLight('amb')
        amb.set_color(Vec4(0.34, 0.37, 0.48, 1) if self.night else Vec4(0.5, 0.56, 0.66, 1))
        self.amb = r.attach_new_node(amb)
        self.base.render.set_light(self.amb)
        sun = DirectionalLight('key')
        sun.set_color(Vec4(1.0, 0.98, 0.94, 1) if self.night else Vec4(1.12, 1.03, 0.88, 1))
        if self.quality != 'low':
            size = 2048 if self.quality == 'high' else 1024
            sun.set_shadow_caster(True, size, size)
            lens = sun.get_lens()
            ext = max(pt.length, pt.width) * 0.62 + 6
            lens.set_film_size(ext * 2, ext * 2)
            lens.set_near_far(1, 200)
        self.sun = r.attach_new_node(sun)
        # Bit 1 is the shadow pass: things hidden from it cast no shadow
        sun.set_camera_mask(SHADOW_MASK)
        cam = self.base.cam.node()
        cam.set_camera_mask(cam.get_camera_mask() & ~SHADOW_MASK)
        if self.night:
            self.sun.set_pos(-pt.length * 0.2, -pt.width * 0.75, 70)
        else:
            self.sun.set_pos(-pt.length * 0.35, -pt.width * 1.05, 52)
        self.sun.look_at(0, 0, 0)
        self.base.render.set_light(self.sun)
        fill = DirectionalLight('fill')
        fill.set_color(Vec4(0.3, 0.33, 0.42, 1) if self.night else Vec4(0.22, 0.26, 0.34, 1))
        self.fill = r.attach_new_node(fill)
        self.fill.set_hpr(140, -35, 0)
        self.base.render.set_light(self.fill)
        f = Fog('haze')
        f.set_color(0.05, 0.07, 0.12) if self.night else f.set_color(0.72, 0.8, 0.9)
        f.set_exp_density(0.0028 if self.night else 0.0011)
        self.root.set_fog(f)

    def _sky(self):
        m = G.sphere(400, 32, 16, zmin=-0.25, zmax=1.0)
        sky = m.node()
        sky.reparent_to(self.base.render)
        sky.set_texture(T.sky(self.night))
        sky.set_two_sided(True)
        sky.set_light_off()
        sky.set_fog_off()
        sky.set_bin('background', 0)
        sky.set_depth_write(False)
        sky.set_compass()
        sky.set_shader(S.sky_shader())
        sky.set_shader_input('u_noise', T.sky_noise())
        if self.night:
            sky.set_shader_input('u_zenith', Vec3(0.004, 0.007, 0.025))
            sky.set_shader_input('u_horizon', Vec3(0.09, 0.1, 0.16))
            sky.set_shader_input('u_sky_opts', Vec4(1, 0.45, 0, 0))
        else:
            sky.set_shader_input('u_zenith', Vec3(0.16, 0.38, 0.78))
            sky.set_shader_input('u_horizon', Vec3(0.72, 0.82, 0.93))
            sky.set_shader_input('u_sky_opts', Vec4(0, 0.5, 0, 0))
        sky.set_shader_input('u_sun_dir', Vec3(-0.35, -0.75, 0.55).normalized())
        self.sky = sky
        if self.night:
            r = random.Random(5)
            stars = G.Mesh('stars')
            for _ in range(320):
                a = r.uniform(0, 2 * math.pi)
                e = r.uniform(0.3, 1.2)
                d = 380
                x, y, z = math.cos(a) * math.cos(e) * d, math.sin(a) * math.cos(e) * d, math.sin(e) * d
                s = r.uniform(0.3, 0.9)
                b = r.uniform(0.4, 1.0)
                G.quad3(stars, (x - s, y, z - s), (x + s, y, z - s), (x + s, y, z + s), (x - s, y, z + s),
                        double=True, color=(b, b, b * 0.95, 1))
            sn = stars.node()
            sn.reparent_to(sky)
            sn.set_light_off()
            sn.set_shader_off()
            sn.set_bin('background', 1)

    # ------------------------------------------------------------- the pitch
    def _pitch(self):
        pt = self.pitch
        root = self.root.attach_new_node('pitch')
        n = 14 if pt.length > 80 else 10
        # One big lawn: the shader paints the stripes, wear and colour
        grass = G.plane(pt.length + 70, pt.width + 70, uv=(1, 1), center=(0, 0, 0.0)).node()
        grass.reparent_to(root)
        grass.set_texture(T.grass_detail())
        grass.set_shader(S.grass_shader(self.quality != 'low'))
        grass.set_shader_input('u_noise', T.noise())
        grass.set_shader_input('u_pitch', Vec4(pt.half_length, pt.half_width, pt.length / n, 0.0))
        if self.night:
            grass.set_shader_input('u_grass_a', Vec4(0.14, 0.31, 0.12, 1))
            grass.set_shader_input('u_grass_b', Vec4(0.23, 0.44, 0.17, 1))
        else:
            grass.set_shader_input('u_grass_a', Vec4(0.17, 0.34, 0.12, 1))
            grass.set_shader_input('u_grass_b', Vec4(0.27, 0.48, 0.18, 1))
        S.material(grass, 'grass')
        grass.set_bin('background', 10)
        self.grass = grass
        self._markings(root)
        self.pitch_node = root

    def _markings(self, root):
        pt = self.pitch
        hl, hw = pt.half_length, pt.half_width
        w = 0.12 if pt.length > 80 else 0.09
        m = G.Mesh('lines')
        z = 0.03

        segs = []

        def seg(x0, y0, x1, y1):
            segs.append((x0, y0, x1, y1))
            dx, dy = x1 - x0, y1 - y0
            d = math.hypot(dx, dy) or 1.0
            nx, ny = -dy / d * w / 2, dx / d * w / 2
            G.quad3(m, (x0 - nx, y0 - ny, z), (x1 - nx, y1 - ny, z), (x1 + nx, y1 + ny, z), (x0 + nx, y0 + ny, z))

        def arc(cx, cy, r, a0, a1, steps=48):
            for i in range(steps):
                t0 = a0 + (a1 - a0) * i / steps
                t1 = a0 + (a1 - a0) * (i + 1) / steps
                seg(cx + math.cos(t0) * r, cy + math.sin(t0) * r, cx + math.cos(t1) * r, cy + math.sin(t1) * r)

        seg(-hl, -hw, hl, -hw)
        seg(-hl, hw, hl, hw)
        seg(-hl, -hw, -hl, hw)
        seg(hl, -hw, hl, hw)
        seg(0, -hw, 0, hw)
        arc(0, 0, pt.circle, 0, 2 * math.pi, 96)
        arc(0, 0, 0.15, 0, 2 * math.pi, 12)
        for s in (-1, 1):
            gx = s * hl
            bd, bw = pt.box_depth, pt.box_width / 2
            if pt.length > 60:
                seg(gx, -bw, gx - s * bd, -bw)
                seg(gx, bw, gx - s * bd, bw)
                seg(gx - s * bd, -bw, gx - s * bd, bw)
                if pt.six_depth:
                    sd, sw = pt.six_depth, pt.six_width / 2
                    seg(gx, -sw, gx - s * sd, -sw)
                    seg(gx, sw, gx - s * sd, sw)
                    seg(gx - s * sd, -sw, gx - s * sd, sw)
                d = math.acos(min(1.0, (bd - pt.spot) / pt.circle))
                c = math.pi if s > 0 else 0.0
                arc(gx - s * pt.spot, 0, pt.circle, c - d, c + d, 32)
            else:
                arc(gx, 0, bd, math.pi / 2 if s > 0 else -math.pi / 2, 3 * math.pi / 2 if s > 0 else math.pi / 2, 56)
            sx = gx - s * pt.spot
            arc(sx, 0, 0.12, 0, 2 * math.pi, 10)
            for cy in (-1, 1):
                a0 = math.atan2(-cy, -s)
                arc(gx, cy * hw, 1.0, a0 - math.pi / 4, a0 + math.pi / 4, 10)
        # The markings are painted into a mask the grass shader reads, so they stay crisp and
        # unbroken however far away they are; the mesh is only drawn if the shaders fail
        x0, y0 = -hl - 2.0, -hw - 2.0
        ppm = min(4096 / (pt.length + 4), 40.0)
        tex = T.line_mask(segs, w, (x0, y0), (pt.length + 4, pt.width + 4), ppm)
        self.grass.set_shader_input('u_lines', tex)
        self.grass.set_shader_input('u_lines_rect', Vec4(x0, y0, 1.0 / (pt.length + 4), 1.0 / (pt.width + 4)))
        self.grass.set_shader_input('u_line_col', Vec4(*LINE))
        node = m.node()
        node.reparent_to(root)
        node.set_color(*LINE)
        node.set_depth_offset(2)
        node.hide()
        self.line_mesh = node

    # ---------------------------------------------------------- goals
    def _goals(self):
        pt = self.pitch
        net_tex = T.net2()
        self.nets = []
        for s in (-1, 1):
            g = self.root.attach_new_node('goal%d' % s)
            gx = s * pt.half_length
            hw = pt.goal_width / 2 + pt.post_radius
            h = pt.goal_height + pt.post_radius
            r = pt.post_radius
            frame = G.Mesh('frame')
            for y in (-hw, hw):
                G.cylinder(r, r, h + r, 20, mesh=frame, base=(gx, y, 0))
            G.cylinder(r, r, 2 * hw, 20, mesh=frame, axis='y', base=(gx, -hw, h))
            for y in (-hw, hw):
                G.sphere(r, 20, 8, mesh=frame, center=(gx, y, h))
            d = pt.goal_depth
            stan = G.Mesh('stanchions')
            for y in (-hw, hw):
                G.cylinder(0.025, 0.025, h, 10, mesh=stan, base=(gx + s * d, y, 0))
                G.cylinder(0.025, 0.025, d, 10, mesh=stan, axis='x', base=(gx, y, h) if s > 0 else (gx - d, y, h))
                # Ground bar along the bottom of the side net
                G.cylinder(0.02, 0.02, d, 8, mesh=stan, axis='x', base=(gx, y, 0.02) if s > 0 else (gx - d, y, 0.02))
            G.cylinder(0.025, 0.025, 2 * hw, 10, mesh=stan, axis='y', base=(gx + s * d, -hw, h))
            G.cylinder(0.02, 0.02, 2 * hw, 8, mesh=stan, axis='y', base=(gx + s * d, -hw, 0.02))
            fn = frame.node()
            fn.reparent_to(g)
            fn.set_color(0.97, 0.97, 0.97, 1)
            S.material(fn, 'goal')
            sn = stan.node()
            sn.reparent_to(g)
            sn.set_color(0.55, 0.57, 0.6, 1)
            S.material(sn, 'metal')
            # Net: back, sides and roof, sagging a little
            net = G.Mesh('net')
            bx = gx + s * d
            cell = 0.12
            u = pt.goal_width / cell
            v = pt.goal_height / cell
            G.quad3(net, (bx, -hw, 0), (bx, hw, 0), (bx, hw, h), (bx, -hw, h), uv=((0, 0), (u, 0), (u, v), (0, v)),
                    double=True)
            for y in (-hw, hw):
                G.quad3(net, (gx, y, 0), (bx, y, 0), (bx, y, h), (gx, y, h),
                        uv=((0, 0), (d / cell, 0), (d / cell, v), (0, v)), double=True)
            G.quad3(net, (gx, -hw, h), (bx, -hw, h), (bx, hw, h), (gx, hw, h),
                    uv=((0, 0), (d / cell, 0), (d / cell, u), (0, u)), double=True)
            nn = net.node()
            nn.reparent_to(g)
            nn.set_texture(net_tex)
            nn.set_transparency(TransparencyAttrib.M_alpha)
            nn.set_color(1, 1, 1, 0.9)
            nn.set_bin('transparent', 10)
            nn.set_depth_write(False)
            S.material(nn, 'net')
            self.nets.append((s, nn))

    def ripple_net(self, side, amount):
        """Bulge the back of the net after a goal (scaled with a decaying wobble)."""
        for s, nn in self.nets:
            if s == side:
                nn.set_scale(1.0 + 0.06 * amount, 1.0, 1.0)

    # ------------------------------------------------------- cage and boards
    def _ads(self, texts):
        return T.led_board(texts)

    def _led(self, node):
        """LED screens give off their own light: unlit, unfogged, a touch dimmer by day."""
        node.set_shader_off()
        node.set_light_off()
        node.set_fog_off()
        k = 1.0 if self.night else 0.85
        node.set_color_scale(k, k, k, 1)

    def _cage(self):
        pt = self.pitch
        hl, hw = pt.half_length, pt.half_width
        h = pt.wall_height
        ads = self._ads([('PANDA LEAGUE', (0.05, 0.1, 0.35), (1, 1, 1)), ('GOALS GOALS', (0.85, 0.12, 0.15), (1, 1, 1)),
                         ('SUPER 5S', (0.95, 0.75, 0.1), (0.05, 0.05, 0.1)), ('TOP BINS', (0.1, 0.55, 0.3), (1, 1, 1))])
        boards = G.Mesh('boards')
        frame = G.Mesh('board_frame')
        t = 0.08

        def wall(x0, y0, x1, y1):
            L = math.hypot(x1 - x0, y1 - y0)
            G.quad3(boards, (x0, y0, 0.05), (x1, y1, 0.05), (x1, y1, h), (x0, y0, h),
                    uv=((0, 0), (L / 8, 0), (L / 8, 1), (0, 1)))
            # A padded top rail and a kick plate
            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
            if abs(x1 - x0) > abs(y1 - y0):
                G.box(L, 0.14, 0.1, mesh=frame, center=(cx, cy, h + 0.05))
                G.box(L, 0.12, 0.06, mesh=frame, center=(cx, cy, 0.03))
            else:
                G.box(0.14, L, 0.1, mesh=frame, center=(cx, cy, h + 0.05))
                G.box(0.12, L, 0.06, mesh=frame, center=(cx, cy, 0.03))

        wall(hl, -hw - t, -hl, -hw - t)
        wall(-hl, hw + t, hl, hw + t)
        gy = pt.goal_width / 2 + pt.post_radius * 2
        wall(hl + t, hw, hl + t, gy)
        wall(hl + t, -gy, hl + t, -hw)
        wall(-hl - t, -hw, -hl - t, -gy)
        wall(-hl - t, gy, -hl - t, hw)
        bn = boards.node()
        bn.reparent_to(self.root)
        bn.set_texture(ads)
        self._led(bn)
        fr = frame.node()
        fr.reparent_to(self.root)
        fr.set_color(0.1, 0.1, 0.12, 1)
        S.material(fr, 'roof')
        # Mesh fencing above the boards
        net_tex = T.net2(64, 4)
        fence = G.Mesh('fence')
        top = 7.0
        for y in (hw + t,):
            G.quad3(fence, (-hl, y, h), (hl, y, h), (hl, y, top), (-hl, y, top),
                    uv=((0, 0), (pt.length / 0.5, 0), (pt.length / 0.5, (top - h) / 0.5), (0, (top - h) / 0.5)), double=True)
        for s in (-1, 1):
            x = s * (hl + t)
            G.quad3(fence, (x, -hw, h), (x, hw, h), (x, hw, top), (x, -hw, top),
                    uv=((0, 0), (pt.width / 0.5, 0), (pt.width / 0.5, (top - h) / 0.5), (0, (top - h) / 0.5)), double=True)
        fn = fence.node()
        fn.reparent_to(self.root)
        fn.set_texture(net_tex)
        fn.set_transparency(TransparencyAttrib.M_alpha)
        fn.set_color(0.75, 0.76, 0.8, 0.45)
        fn.set_depth_write(False)
        fn.set_bin('transparent', 5)
        S.material(fn, 'net')
        posts = G.Mesh('fposts')
        for x in range(int(-hl), int(hl) + 1, 6):
            for y in (hw + t,):
                G.cylinder(0.05, 0.05, top, 8, mesh=posts, base=(x, y, 0))
        for s in (-1, 1):
            for y in range(int(-hw), int(hw) + 1, 6):
                G.cylinder(0.05, 0.05, top, 8, mesh=posts, base=(s * (hl + t), y, 0))
        G.cylinder(0.04, 0.04, pt.length, 6, mesh=posts, axis='x', base=(-hl, hw + t, top))
        pn = posts.node()
        pn.reparent_to(self.root)
        pn.set_color(0.22, 0.23, 0.26, 1)
        S.material(pn, 'metal')

    def _boards(self):
        pt = self.pitch
        hl, hw = pt.half_length, pt.half_width
        ads = self._ads([('PANDA LEAGUE', (0.05, 0.1, 0.35), (1, 1, 1)), ('GOAL OF THE SEASON', (0.85, 0.12, 0.15), (1, 1, 1)),
                         ('ULTIMATE XI', (0.95, 0.75, 0.1), (0.05, 0.05, 0.1)), ('TOP BINS', (0.1, 0.55, 0.3), (1, 1, 1))])
        boards = G.Mesh('boards')
        backs = G.Mesh('board_backs')
        h = 0.9
        off = 4.0
        lean = 0.18

        def wall(x0, y0, x1, y1, ox, oy):
            L = math.hypot(x1 - x0, y1 - y0)
            # Leaning back a little, like real LED boards
            G.quad3(boards, (x0, y0, 0), (x1, y1, 0), (x1 + ox * lean, y1 + oy * lean, h),
                    (x0 + ox * lean, y0 + oy * lean, h), uv=((0, 0), (L / 10, 0), (L / 10, 1), (0, 1)))
            G.quad3(backs, (x1 + ox * (lean + 0.3), y1 + oy * (lean + 0.3), 0), (x0 + ox * (lean + 0.3), y0 + oy * (lean + 0.3), 0),
                    (x0 + ox * lean, y0 + oy * lean, h), (x1 + ox * lean, y1 + oy * lean, h))

        wall(hl + off, -hw - off, -hl - off, -hw - off, 0, -1)
        wall(-hl - off, hw + off, hl + off, hw + off, 0, 1)
        wall(hl + off, hw + off, hl + off, -hw - off, 1, 0)
        wall(-hl - off, -hw - off, -hl - off, hw + off, -1, 0)
        bn = boards.node()
        bn.reparent_to(self.root)
        bn.set_texture(ads)
        self._led(bn)
        kn = backs.node()
        kn.reparent_to(self.root)
        kn.set_color(0.08, 0.08, 0.1, 1)
        kn.set_two_sided(True)
        # A strip of darker, trodden grass where the photographers and stewards stand
        apron = G.Mesh('apron')
        for (x0, y0, x1, y1) in ((-hl - off - 3, -hw - off - 0.4, hl + off + 3, -hw - off - 6),
                                 (-hl - off - 3, hw + off + 0.4, hl + off + 3, hw + off + 6)):
            G.quad3(apron, (x0, y0, 0.004), (x1, y0, 0.004), (x1, y1, 0.004), (x0, y1, 0.004), double=True)
        an = apron.node()
        an.reparent_to(self.root)
        an.set_color(0.2, 0.22, 0.2, 0.55)
        an.set_transparency(TransparencyAttrib.M_alpha)
        an.set_depth_offset(1)

    # --------------------------------------------------------- stands
    def _stands(self, home, away):
        """A bowl of stands, one node per side so a side can be hidden when the camera is inside it.
        Lower tier, an LED fascia, upper tier, back wall; roofs over all but the camera side."""
        pt = self.pitch
        hl, hw = pt.half_length, pt.half_width
        gap = 6.0 if not pt.walls else 3.0
        self.gap = gap
        big = pt.length > 80
        tiers = 16 if big else 10
        split = 9 if big else 6         # the upper tier starts here, behind a fascia
        rise, step = 0.5, 0.8
        fascia_h = 2.4
        crowd_tex = [T.crowd2(seed=s, colors=[tuple(home[:3]), tuple(away[:3]), tuple(home[:3])],
                              fill=0.9) for s in (1, 2, 3)]
        fascia_tex = self._ads([('ULTIMATE FOOTBALL', (0.02, 0.02, 0.04), tuple(home[:3])),
                                ('WELCOME', (0.02, 0.02, 0.04), (1, 1, 1)),
                                ('PANDA LEAGUE', (0.02, 0.02, 0.04), tuple(away[:3]))])
        seat_cols = [_dim(home, 0.55), _dim(home, 0.42), _dim(away, 0.5)]
        r = random.Random(2)
        x_in, y_in = hl + gap, hw + gap
        # Each side runs left to right as seen from the pitch: (inner edge start, end, outward normal)
        sides = [((-1, -1), (1, -1), (0, -1)),
                 ((1, 1), (-1, 1), (0, 1)),
                 ((-1, 1), (-1, -1), (-1, 0)),
                 ((1, -1), (1, 1), (1, 0))]
        self.side_nodes = []
        self.crowd_root = self.root.attach_new_node('crowd')
        top_z = 0.0
        d = 0.0
        for si, ((ax, ay), (bx, by), (ox, oy)) in enumerate(sides):
            side = self.root.attach_new_node('stand%d' % si)
            self.side_nodes.append(side)
            concrete = G.Mesh('stands')
            seats = G.Mesh('seats')
            fascia = G.Mesh('fascia')
            crowd_side = self.crowd_root.attach_new_node('crowd%d' % si)
            z = 0.9
            d = 0.0
            for t in range(tiers):
                if t == split:
                    xa, ya = ax * (x_in + d), ay * (y_in + d)
                    xb, yb = bx * (x_in + d), by * (y_in + d)
                    L = math.hypot(xb - xa, yb - ya)
                    G.quad3(fascia, (xa, ya, z), (xb, yb, z), (xb, yb, z + fascia_h), (xa, ya, z + fascia_h),
                            uv=((0, 0), (L / 12.0, 0), (L / 12.0, 1), (0, 1)))
                    z += fascia_h
                    d += 1.2
                    G.quad3(concrete, (xa, ya, z), (xb, yb, z), (bx * (x_in + d), by * (y_in + d), z),
                            (ax * (x_in + d), ay * (y_in + d), z))
                z0 = z
                z += rise
                xa, ya = ax * (x_in + d), ay * (y_in + d)
                xb, yb = bx * (x_in + d), by * (y_in + d)
                d2 = d + step
                xa2, ya2 = ax * (x_in + d2), ay * (y_in + d2)
                xb2, yb2 = bx * (x_in + d2), by * (y_in + d2)
                col = seat_cols[(si + (t >= split)) % len(seat_cols)]
                G.quad3(seats, (xa, ya, z0), (xb, yb, z0), (xb, yb, z), (xa, ya, z), color=col + (1,))
                G.quad3(concrete, (xa, ya, z), (xb, yb, z), (xb2, yb2, z), (xa2, ya2, z))
                L = math.hypot(xb - xa, yb - ya)
                fh = 1.25
                ins = 0.32
                cm = G.Mesh('fans')
                k = (t + r.randint(0, 3)) % 3
                u0 = r.random()
                G.quad3(cm, (xa + ox * ins, ya + oy * ins, z - 0.05), (xb + ox * ins, yb + oy * ins, z - 0.05),
                        (xb + ox * ins, yb + oy * ins, z - 0.05 + fh), (xa + ox * ins, ya + oy * ins, z - 0.05 + fh),
                        uv=((u0, 0), (u0 + L / 10.0, 0), (u0 + L / 10.0, 1), (u0, 1)))
                n = cm.node()
                n.reparent_to(crowd_side)
                n.set_texture(crowd_tex[k])
                n.set_two_sided(True)
                n.set_python_tag('tier', t)
                self.crowd_nodes.append(n)
                d = d2
            # Back wall behind the top row, and the outside of the stand
            xa, ya = ax * (x_in + d), ay * (y_in + d)
            xb, yb = bx * (x_in + d), by * (y_in + d)
            G.quad3(concrete, (xa, ya, z), (xb, yb, z), (xb, yb, z + 3.0), (xa, ya, z + 3.0))
            G.quad3(concrete, (xb, yb, 0), (xa, ya, 0), (xa, ya, z + 3.0), (xb, yb, z + 3.0))
            top_z = z
            if si == 0:
                self.near_stand_top = z + 1.2
            cn = concrete.node()
            cn.reparent_to(side)
            cn.set_color(0.42, 0.43, 0.46, 1)
            cn.set_two_sided(True)
            S.material(cn, 'concrete')
            sn = seats.node()
            sn.reparent_to(side)
            sn.set_two_sided(True)
            S.material(sn, 'seats')
            fz = fascia.node()
            fz.reparent_to(side)
            fz.set_texture(fascia_tex)
            self._led(fz)
            crowd_side.reparent_to(side)
        self.stand_depth = d
        self.crowd_root.set_color_scale(0.8, 0.8, 0.8, 1)
        for side in self.side_nodes:
            c = side.find('crowd*')
            c.set_shader_input('u_alpha_cut', 0.5)
            S.material(c, 'crowd')
            # Crowds don't need to cast shadows on each other: cheaper shadow pass
            c.hide(SHADOW_MASK)
        self._roofs(top_z + 3.0, gap)
        self.stand_top = top_z

    def _roofs(self, top, gap):
        """Cantilevered roofs over the far side and both ends, with a fascia and lights underneath."""
        pt = self.pitch
        hl, hw = pt.half_length, pt.half_width
        d = self.stand_depth
        x_in, y_in = hl + gap, hw + gap
        over = 5.0
        lc = (1.0, 0.97, 0.88, 1) if self.night else (0.6, 0.6, 0.62, 1)
        # (side index, inner start, inner end, outward) - not over the camera side
        for si, (ax, ay), (bx, by), (ox, oy) in ((1, (1, 1), (-1, 1), (0, 1)), (2, (-1, 1), (-1, -1), (-1, 0)),
                                                  (3, (1, -1), (1, 1), (1, 0))):
            roof = G.Mesh('roof')
            under = G.Mesh('roof_under')
            trim = G.Mesh('roof_trim')
            lamps = G.Mesh('roof_lamps')
            if ox:
                xa, xb = ax * x_in - ox * over, bx * x_in - ox * over
                ya, yb = ay * (y_in + d), by * (y_in + d)
            else:
                xa, xb = ax * (x_in + d), bx * (x_in + d)
                ya, yb = ay * y_in - oy * over, by * y_in - oy * over
            xa2, ya2 = xa + ox * (d + over), ya + oy * (d + over)
            xb2, yb2 = xb + ox * (d + over), yb + oy * (d + over)
            G.quad3(roof, (xa, ya, top + 0.6), (xb, yb, top + 0.6), (xb2, yb2, top + 2.2), (xa2, ya2, top + 2.2))
            G.quad3(under, (xa, ya, top), (xa2, ya2, top + 1.6), (xb2, yb2, top + 1.6), (xb, yb, top))
            G.quad3(trim, (xa, ya, top - 0.2), (xb, yb, top - 0.2), (xb, yb, top + 0.6), (xa, ya, top + 0.6))
            L = math.hypot(xb - xa, yb - ya)
            n = int(L / 4)
            for i in range(n):
                f = (i + 0.5) / n
                px, py = xa + (xb - xa) * f + ox * 0.6, ya + (yb - ya) * f + oy * 0.6
                G.box(1.4 if not ox else 0.3, 0.3 if not ox else 1.4, 0.08, mesh=lamps, center=(px, py, top - 0.04))
            for i in range(n // 3 + 1):
                f = i / max(1, n // 3)
                px, py = xa2 + (xb2 - xa2) * f, ya2 + (yb2 - ya2) * f
                G.cylinder(0.3, 0.3, top + 2.2, 8, mesh=roof, base=(px, py, 0))
            side = self.side_nodes[si]
            rn = roof.node()
            rn.reparent_to(side)
            rn.set_color(0.28, 0.29, 0.32, 1)
            rn.set_two_sided(True)
            S.material(rn, 'roof')
            un = under.node()
            un.reparent_to(side)
            un.set_color(0.16, 0.17, 0.2, 1)
            un.set_two_sided(True)
            S.material(un, 'concrete')
            tn = trim.node()
            tn.reparent_to(side)
            tn.set_color(*(_dim(self.home, 0.7) + (1,)))
            S.material(tn, 'roof')
            ln = lamps.node()
            ln.reparent_to(side)
            ln.set_light_off()
            ln.set_shader_off()
            ln.set_color(*lc)
            ln.hide(SHADOW_MASK)

    def _hide_stands_around_camera(self):
        """A stand the camera sits inside (or behind) would fill the screen: hide it."""
        c = self.base.camera.get_pos(self.base.render)
        hl, hw = self.pitch.half_length + self.gap, self.pitch.half_width + self.gap
        inside = (c.y < -hw, c.y > hw, c.x < -hl, c.x > hl)
        for node, hide in zip(self.side_nodes, inside):
            if hide != node.is_hidden():
                node.hide() if hide else node.show()

    def _floodlights(self):
        pt = self.pitch
        hl, hw = pt.half_length, pt.half_width
        glow = T.radial(64, (1.0, 0.96, 0.86), 1.8)
        poles = G.Mesh('poles')
        heads = G.Mesh('heads')
        self.flares = self.root.attach_new_node('flares')
        h = self.stand_top + 12
        back = hw + self.gap + self.stand_depth + 4
        for sx in (-1, 1):
            # Towers behind the far corners only: the TV camera sits on the near side
            for sy in (1,):
                x, y = sx * (hl + self.gap + 4), sy * back
                G.cylinder(0.55, 0.3, h, 10, mesh=poles, base=(x, y, 0))
                # Lattice head: a frame with 4 x 3 lamps, angled at the pitch
                G.box(6.0, 0.5, 3.6, mesh=poles, center=(x, y, h + 1.5))
                for i in range(4):
                    for j in range(3):
                        cx = x - 2.25 + i * 1.5
                        cz = h + 0.4 + j * 1.1
                        G.box(1.2, 0.2, 0.9, mesh=heads, center=(cx, y - sy * 0.3, cz))
                        if self.night:
                            f = G.plane(4.0, 4.0, normal_up=True).node()
                            f.reparent_to(self.flares)
                            f.set_pos(cx, y - sy * 0.6, cz)
                            f.set_p(90)
                            f.set_billboard_point_eye()
                            f.set_texture(glow)
        pn = poles.node()
        pn.reparent_to(self.root)
        pn.set_color(0.3, 0.31, 0.34, 1)
        S.material(pn, 'metal')
        hn = heads.node()
        hn.reparent_to(self.root)
        if self.night:
            hn.set_light_off()
            hn.set_shader_off()
            hn.set_color(1.0, 0.98, 0.92, 1)
        else:
            hn.set_color(0.75, 0.77, 0.8, 1)
            S.material(hn, 'metal')
        self.flares.set_transparency(TransparencyAttrib.M_alpha)
        self.flares.set_attrib(ColorBlendAttrib.make(ColorBlendAttrib.M_add))
        self.flares.set_light_off()
        self.flares.set_shader_off()
        self.flares.set_depth_write(False)
        self.flares.set_bin('fixed', 5)
        self.flares.set_fog_off()
        self.flares.hide(SHADOW_MASK)

    def destroy(self):
        # Drop the shadow buffer first: left behind, it keeps rendering the old stadium
        self.sun.node().set_shadow_caster(False)
        r = self.base.render
        for lt in (self.amb, self.sun, self.fill):
            r.clear_light(lt)
        self.root.remove_node()
        self.sky.remove_node()

    # --------------------------------------------------------- per frame
    def update(self, dt, t, excitement):
        """Crowd bounces with the excitement level (0..1); the lights follow the weather."""
        self.t += dt
        self.cheer += (excitement - self.cheer) * min(1.0, dt * 2.0)
        amp = 0.04 + 0.22 * self.cheer
        for n in self.crowd_nodes:
            tier = n.get_python_tag('tier')
            n.set_z(abs(math.sin(t * (6.0 + tier * 0.37) + tier)) * amp)
        self._hide_stands_around_camera()
        if self.lighting is not None:
            self.frames += 1
            if self.frames == 3 and not S.check(self.base):
                print('Shaders failed to compile: using the basic look')
                self._fallback()
                return
            self.lighting.update()
            self.grass.set_shader_input('u_pitch', Vec4(self.pitch.half_length, self.pitch.half_width,
                                                        self.pitch.length / (14 if self.pitch.length > 80 else 10),
                                                        self.wet))
            self.sky.set_shader_input('u_sky_opts', Vec4(1 if self.night else 0, 0.45 if self.night else 0.5,
                                                         self.t, 0))
