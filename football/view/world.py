"""The stadium: pitch, markings, goals and nets, cage boards, stands and
crowd, floodlights, sky and lighting."""

import math
import random

from panda3d.core import (AmbientLight, DirectionalLight, Fog, TransparencyAttrib, Vec3, Vec4, NodePath,
                          TextureStage, BillboardEffect, ColorBlendAttrib, CullFaceAttrib)

from . import geom as G
from . import textures as T

LINE = (0.96, 0.97, 0.95, 1)


class World:
    def __init__(self, base, pitch, home_colors, away_colors, night=True, quality='high'):
        self.base = base
        self.pitch = pitch
        self.night = night
        self.quality = quality
        self.root = base.render.attach_new_node('world')
        self.crowd_nodes = []
        self.cheer = 0.0
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

    # ------------------------------------------------------------ lighting
    def _lights(self):
        r = self.root
        amb = AmbientLight('amb')
        amb.set_color(Vec4(0.36, 0.38, 0.45, 1) if self.night else Vec4(0.45, 0.47, 0.5, 1))
        self.amb = r.attach_new_node(amb)
        r.set_light(self.amb)
        sun = DirectionalLight('key')
        sun.set_color(Vec4(1.05, 1.02, 0.95, 1) if self.night else Vec4(1.1, 1.05, 0.95, 1))
        pt = self.pitch
        if self.quality != 'low':
            size = 2048 if self.quality == 'high' else 1024
            sun.set_shadow_caster(True, size, size)
            lens = sun.get_lens()
            ext = max(pt.length, pt.width) * 0.62 + 6
            lens.set_film_size(ext * 2, ext * 2)
            lens.set_near_far(1, 160)
        self.sun = r.attach_new_node(sun)
        self.sun.set_pos(-pt.length * 0.25, -pt.width * 0.9, 60)
        self.sun.look_at(0, 0, 0)
        r.set_light(self.sun)
        fill = DirectionalLight('fill')
        fill.set_color(Vec4(0.22, 0.24, 0.3, 1))
        self.fill = r.attach_new_node(fill)
        self.fill.set_hpr(140, -35, 0)
        r.set_light(self.fill)
        if self.quality != 'low':
            self.base.render.set_shader_auto()
        f = Fog('haze')
        f.set_color(0.05, 0.06, 0.1) if self.night else f.set_color(0.7, 0.8, 0.9)
        f.set_exp_density(0.0035)
        self.root.set_fog(f)

    def _sky(self):
        m = G.sphere(400, 24, 12, zmin=-0.2, zmax=1.0)
        sky = m.node()
        sky.reparent_to(self.base.render)
        sky.set_texture(T.sky(self.night))
        # The texture runs top to horizon; spheres map v from 1 (top) to 0
        sky.set_two_sided(True)
        sky.set_light_off()
        sky.set_shader_off()
        sky.set_fog_off()
        sky.set_bin('background', 0)
        sky.set_depth_write(False)
        sky.set_compass()
        self.sky = sky
        # Stars at night
        if self.night:
            r = random.Random(5)
            stars = G.Mesh('stars')
            for _ in range(260):
                a = r.uniform(0, 2 * math.pi)
                e = r.uniform(0.25, 1.2)
                d = 380
                x, y, z = math.cos(a) * math.cos(e) * d, math.sin(a) * math.cos(e) * d, math.sin(e) * d
                s = r.uniform(0.4, 1.0)
                G.quad3(stars, (x - s, y, z - s), (x + s, y, z - s), (x + s, y, z + s), (x - s, y, z + s), double=True)
            sn = stars.node()
            sn.reparent_to(sky)
            sn.set_color(1, 1, 0.95, 1)
            sn.set_light_off()
            sn.set_bin('background', 1)

    # ------------------------------------------------------------- the pitch
    def _pitch(self):
        pt = self.pitch
        hl, hw = pt.half_length, pt.half_width
        grass = T.grass()
        root = self.root.attach_new_node('pitch')
        # Surround: plain grass well beyond the lines
        sur = G.plane(pt.length + 40, pt.width + 40, uv=((pt.length + 40) / 4, (pt.width + 40) / 4),
                      center=(0, 0, -0.01)).node()
        sur.reparent_to(root)
        sur.set_color(0.16, 0.38, 0.14, 1)
        sur.set_texture(grass)
        # Mowing stripes across the pitch
        n = 14 if pt.length > 80 else 10
        stripe = pt.length / n
        for i in range(n):
            x0 = -hl + i * stripe
            shade = 1.0 if i % 2 == 0 else 0.86
            s = G.plane(stripe, pt.width + 4, uv=(stripe / 4, (pt.width + 4) / 4),
                        center=(x0 + stripe / 2, 0, 0.0)).node()
            s.reparent_to(root)
            s.set_color(0.2 * shade, 0.5 * shade, 0.18 * shade, 1)
            s.set_texture(grass)
        self._markings(root)
        self.pitch_node = root

    def _markings(self, root):
        pt = self.pitch
        hl, hw = pt.half_length, pt.half_width
        w = 0.12 if pt.length > 80 else 0.09
        m = G.Mesh('lines')
        z = 0.012

        def seg(x0, y0, x1, y1):
            dx, dy = x1 - x0, y1 - y0
            d = math.hypot(dx, dy) or 1.0
            nx, ny = -dy / d * w / 2, dx / d * w / 2
            G.quad3(m, (x0 - nx, y0 - ny, z), (x1 - nx, y1 - ny, z), (x1 + nx, y1 + ny, z), (x0 + nx, y0 + ny, z))

        def arc(cx, cy, r, a0, a1, steps=48):
            for i in range(steps):
                t0 = a0 + (a1 - a0) * i / steps
                t1 = a0 + (a1 - a0) * (i + 1) / steps
                seg(cx + math.cos(t0) * r, cy + math.sin(t0) * r, cx + math.cos(t1) * r, cy + math.sin(t1) * r)

        # Touchlines, goal lines, halfway line, centre circle and spot
        seg(-hl, -hw, hl, -hw)
        seg(-hl, hw, hl, hw)
        seg(-hl, -hw, -hl, hw)
        seg(hl, -hw, hl, hw)
        seg(0, -hw, 0, hw)
        arc(0, 0, pt.circle, 0, 2 * math.pi, 64)
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
                # The D
                d = math.acos(min(1.0, (bd - pt.spot) / pt.circle))
                c = math.pi if s > 0 else 0.0
                arc(gx - s * pt.spot, 0, pt.circle, c - d, c + d, 24)
            else:
                # Small-sided: a semicircular area
                arc(gx, 0, bd, math.pi / 2 if s > 0 else -math.pi / 2, 3 * math.pi / 2 if s > 0 else math.pi / 2, 40)
            sx = gx - s * pt.spot
            arc(sx, 0, 0.12, 0, 2 * math.pi, 10)
            # Corner arcs
            for cy in (-1, 1):
                a0 = math.atan2(-cy, -s)
                arc(gx, cy * hw, 1.0, a0 - math.pi / 4, a0 + math.pi / 4, 8)
        node = m.node()
        node.reparent_to(root)
        node.set_color(*LINE)
        node.set_depth_offset(2)

    # ---------------------------------------------------------- goals
    def _goals(self):
        pt = self.pitch
        net_tex = T.net()
        self.nets = []
        for s in (-1, 1):
            g = self.root.attach_new_node('goal%d' % s)
            gx = s * pt.half_length
            hw = pt.goal_width / 2 + pt.post_radius
            h = pt.goal_height + pt.post_radius
            r = pt.post_radius
            frame = G.Mesh('frame')
            for y in (-hw, hw):
                G.cylinder(r, r, h + r, 16, mesh=frame, base=(gx, y, 0))
            G.cylinder(r, r, 2 * hw, 16, mesh=frame, axis='y', base=(gx, -hw, h))
            # Back stanchions
            d = pt.goal_depth
            for y in (-hw, hw):
                G.cylinder(0.025, 0.025, h, 8, mesh=frame, base=(gx + s * d, y, 0))
                G.cylinder(0.025, 0.025, d, 8, mesh=frame, axis='x', base=(gx, y, h) if s > 0 else (gx - d, y, h))
            G.cylinder(0.025, 0.025, 2 * hw, 8, mesh=frame, axis='y', base=(gx + s * d, -hw, h))
            fn = frame.node()
            fn.reparent_to(g)
            fn.set_color(0.98, 0.98, 0.98, 1)
            # Net: back, sides and roof
            net = G.Mesh('net')
            bx = gx + s * d
            u = pt.goal_width / 0.12
            v = pt.goal_height / 0.12
            G.quad3(net, (bx, -hw, 0), (bx, hw, 0), (bx, hw, h), (bx, -hw, h), uv=((0, 0), (u, 0), (u, v), (0, v)),
                    double=True)
            for y in (-hw, hw):
                G.quad3(net, (gx, y, 0), (bx, y, 0), (bx, y, h), (gx, y, h),
                        uv=((0, 0), (d / 0.12, 0), (d / 0.12, v), (0, v)), double=True)
            G.quad3(net, (gx, -hw, h), (bx, -hw, h), (bx, hw, h), (gx, hw, h),
                    uv=((0, 0), (d / 0.12, 0), (d / 0.12, u), (0, u)), double=True)
            nn = net.node()
            nn.reparent_to(g)
            nn.set_texture(net_tex)
            nn.set_transparency(TransparencyAttrib.M_alpha)
            nn.set_color(1, 1, 1, 1)
            nn.set_bin('transparent', 10)
            nn.set_depth_write(False)
            self.nets.append((s, nn))

    def ripple_net(self, side, amount):
        """Bulge the back of the net after a goal (scaled with a decaying wobble)."""
        for s, nn in self.nets:
            if s == side:
                nn.set_scale(1.0 + 0.06 * amount, 1.0, 1.0)

    # ------------------------------------------------------- cage and boards
    def _cage(self):
        pt = self.pitch
        hl, hw = pt.half_length, pt.half_width
        h = pt.wall_height
        ads = T.ad_board([('PANDA LEAGUE', (0.05, 0.1, 0.35), (1, 1, 1)), ('GOALS GOALS', (0.85, 0.12, 0.15), (1, 1, 1)),
                          ('SUPER 5S', (0.95, 0.75, 0.1), (0.05, 0.05, 0.1)), ('TOP BINS', (0.1, 0.55, 0.3), (1, 1, 1))])
        boards = G.Mesh('boards')
        t = 0.08

        def wall(x0, y0, x1, y1, inward):
            ix, iy = inward
            L = math.hypot(x1 - x0, y1 - y0)
            G.quad3(boards, (x0, y0, 0), (x1, y1, 0), (x1, y1, h), (x0, y0, h), uv=((0, 0), (L / 8, 0), (L / 8, 1), (0, 1)))

        # Each wall runs left to right as seen from the pitch, so the ads read properly
        wall(hl, -hw - t, -hl, -hw - t, (0, 1))
        wall(-hl, hw + t, hl, hw + t, (0, -1))
        gy = pt.goal_width / 2 + pt.post_radius * 2
        wall(hl + t, hw, hl + t, gy, (-1, 0))
        wall(hl + t, -gy, hl + t, -hw, (-1, 0))
        wall(-hl - t, -hw, -hl - t, -gy, (1, 0))
        wall(-hl - t, gy, -hl - t, hw, (1, 0))
        bn = boards.node()
        bn.reparent_to(self.root)
        bn.set_texture(ads)
        bn.set_light_off()
        bn.set_color(1.15, 1.15, 1.15, 1)
        # Mesh fencing above the boards
        net_tex = T.net(64, 4)
        fence = G.Mesh('fence')
        top = 7.0
        # No fencing on the camera side, so nothing gets between you and the game
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
        fn.set_color(0.6, 0.6, 0.65, 0.6)
        fn.set_light_off()
        fn.set_depth_write(False)
        fn.set_bin('transparent', 5)
        # Posts holding the fence
        posts = G.Mesh('fposts')
        for x in range(int(-hl), int(hl) + 1, 6):
            for y in (hw + t,):
                G.cylinder(0.05, 0.05, top, 6, mesh=posts, base=(x, y, 0))
        pn = posts.node()
        pn.reparent_to(self.root)
        pn.set_color(0.2, 0.2, 0.22, 1)

    def _boards(self):
        pt = self.pitch
        hl, hw = pt.half_length, pt.half_width
        ads = T.ad_board([('PANDA LEAGUE', (0.05, 0.1, 0.35), (1, 1, 1)), ('GOAL OF THE SEASON', (0.85, 0.12, 0.15), (1, 1, 1)),
                          ('ULTIMATE XI', (0.95, 0.75, 0.1), (0.05, 0.05, 0.1)), ('TOP BINS', (0.1, 0.55, 0.3), (1, 1, 1))])
        boards = G.Mesh('boards')
        h = 0.9
        off = 4.0

        def wall(x0, y0, x1, y1):
            L = math.hypot(x1 - x0, y1 - y0)
            G.quad3(boards, (x0, y0, 0), (x1, y1, 0), (x1, y1, h), (x0, y0, h), uv=((0, 0), (L / 10, 0), (L / 10, 1), (0, 1)))

        wall(hl + off, -hw - off, -hl - off, -hw - off)
        wall(-hl - off, hw + off, hl + off, hw + off)
        wall(hl + off, hw + off, hl + off, -hw - off)
        wall(-hl - off, -hw - off, -hl - off, hw + off)
        bn = boards.node()
        bn.reparent_to(self.root)
        bn.set_texture(ads)
        bn.set_light_off()
        bn.set_color(1.15, 1.15, 1.15, 1)

    # --------------------------------------------------------- stands
    def _stands(self, home, away):
        pt = self.pitch
        hl, hw = pt.half_length, pt.half_width
        gap = 6.0 if not pt.walls else 3.0
        tiers = 14 if pt.length > 80 else 9
        rise, step = 0.55, 0.85
        crowd_tex = [T.crowd(seed=s, colors=[home, away, home]) for s in (1, 2, 3)]
        concrete = G.Mesh('stands')
        sides = [((-hl - 2, -hw - gap), (hl + 2, -hw - gap), (0, -1)),
                 ((hl + 2, hw + gap), (-hl - 2, hw + gap), (0, 1)),
                 ((-hl - gap, hw + 2), (-hl - gap, -hw - 2), (-1, 0)),
                 ((hl + gap, -hw - 2), (hl + gap, hw + 2), (1, 0))]
        r = random.Random(2)
        crowd = []
        for (x0, y0), (x1, y1), (ox, oy) in sides:
            for t in range(tiers):
                z = 0.8 + t * rise
                d = t * step
                a = (x0 + ox * d, y0 + oy * d)
                b = (x1 + ox * d, y1 + oy * d)
                # Step riser and tread
                G.quad3(concrete, (a[0], a[1], z - rise), (b[0], b[1], z - rise), (b[0], b[1], z), (a[0], a[1], z))
                G.quad3(concrete, (a[0], a[1], z), (b[0], b[1], z), (b[0] + ox * step, b[1] + oy * step, z),
                        (a[0] + ox * step, a[1] + oy * step, z))
                # Fans standing on the step, facing the pitch
                L = math.hypot(b[0] - a[0], b[1] - a[1])
                fz = z
                fh = 1.25
                cm = G.Mesh('fans')
                k = (t + r.randint(0, 3)) % 3
                inset = 0.3
                G.quad3(cm, (a[0] + ox * inset, a[1] + oy * inset, fz), (b[0] + ox * inset, b[1] + oy * inset, fz),
                        (b[0] + ox * inset, b[1] + oy * inset, fz + fh), (a[0] + ox * inset, a[1] + oy * inset, fz + fh),
                        uv=((0, 0), (L / 9.0, 0), (L / 9.0, 1), (0, 1)))
                crowd.append((cm, k, t))
            # Roof
        cn = concrete.node()
        cn.reparent_to(self.root)
        cn.set_color(0.32, 0.33, 0.36, 1)
        cn.set_two_sided(True)
        self.crowd_root = self.root.attach_new_node('crowd')
        for cm, k, t in crowd:
            n = cm.node()
            n.reparent_to(self.crowd_root)
            n.set_texture(crowd_tex[k])
            n.set_two_sided(True)
            n.set_python_tag('tier', t)
            self.crowd_nodes.append(n)
        self.crowd_root.set_color(0.95, 0.95, 0.95, 1)
        # Roof over the long sides
        roof = G.Mesh('roof')
        top = 0.8 + tiers * rise + 4.0
        for s in (1,):
            y0 = s * (hw + gap)
            y1 = s * (hw + gap + tiers * step + 3)
            G.quad3(roof, (-hl - 4, y0 - s * 2, top), (hl + 4, y0 - s * 2, top), (hl + 4, y1, top + 2), (-hl - 4, y1, top + 2),
                    double=True)
            for x in range(int(-hl), int(hl) + 1, 12):
                G.cylinder(0.25, 0.25, top + 2, 8, mesh=roof, base=(x, y1, 0))
        rn = roof.node()
        rn.reparent_to(self.root)
        rn.set_color(0.18, 0.19, 0.22, 1)
        self.stand_top = top

    def _floodlights(self):
        pt = self.pitch
        hl, hw = pt.half_length, pt.half_width
        glow = T.radial(64, (1.0, 0.97, 0.88), 1.6)
        poles = G.Mesh('poles')
        self.flares = self.root.attach_new_node('flares')
        h = self.stand_top + 8 if hasattr(self, 'stand_top') else 24
        back = hw + 10 if not hasattr(self, 'stand_top') else hw + 14
        for sx in (-1, 1):
            # Towers behind the far corners only: the TV camera sits on the near side
            for sy in (1,):
                x, y = sx * (hl + 8), sy * back
                G.cylinder(0.35, 0.25, h, 8, mesh=poles, base=(x, y, 0))
                G.box(4.5, 0.4, 2.5, mesh=poles, center=(x, y, h + 1))
                if self.night:
                    for i in range(3):
                        for j in range(2):
                            f = G.plane(3.0, 3.0, normal_up=True).node()
                            f.reparent_to(self.flares)
                            f.set_pos(x - 1.5 + i * 1.5, y - sy * 0.4, h + 0.4 + j * 1.2)
                            f.set_p(90)
                            f.set_billboard_point_eye()
                            f.set_texture(glow)
        pn = poles.node()
        pn.reparent_to(self.root)
        pn.set_color(0.25, 0.26, 0.28, 1)
        self.flares.set_transparency(TransparencyAttrib.M_alpha)
        self.flares.set_attrib(ColorBlendAttrib.make(ColorBlendAttrib.M_add))
        self.flares.set_light_off()
        self.flares.set_shader_off()
        self.flares.set_depth_write(False)
        self.flares.set_bin('fixed', 5)
        self.flares.set_fog_off()

    # --------------------------------------------------------- per frame
    def update(self, dt, t, excitement):
        """Crowd bounces with the excitement level (0..1)."""
        self.cheer += (excitement - self.cheer) * min(1.0, dt * 2.0)
        amp = 0.04 + 0.22 * self.cheer
        for n in self.crowd_nodes:
            tier = n.get_python_tag('tier')
            n.set_z(abs(math.sin(t * (6.0 + tier * 0.37) + tier)) * amp)
