"""Rain and snow falling around the camera, plus the light and pitch to match.

The sim decides what the weather does to the ball (sim/weather.py); this only
draws it. Each effect is one static GeomNode of streaks or flakes in a box,
drawn twice stacked and slid down every frame so it never runs out."""

import math
import random

from panda3d.core import (Fog, Geom, GeomLines, GeomNode, GeomPoints, GeomVertexData, GeomVertexFormat,
                          GeomVertexWriter, TransparencyAttrib)

from . import geom as G

BOX = 46.0      # metres across, centred on the camera
HEIGHT = 22.0   # metres tall


def _cloud(kind, n, wind, seed=7):
    rng = random.Random(seed)
    vd = GeomVertexData(kind, GeomVertexFormat.get_v3(), Geom.UH_static)
    w = GeomVertexWriter(vd, 'vertex')
    wx, wy = wind
    if kind == 'rain':
        prim = GeomLines(Geom.UH_static)
        # Streaks lean with the wind; length is how far a drop falls in a frame or two
        lx, ly = wx * 0.05, wy * 0.05
        for i in range(n):
            x, y, z = rng.uniform(-BOX / 2, BOX / 2), rng.uniform(-BOX / 2, BOX / 2), rng.uniform(0, HEIGHT)
            w.add_data3(x, y, z)
            w.add_data3(x + lx, y + ly, z + 0.55)
            prim.add_vertices(2 * i, 2 * i + 1)
    else:
        prim = GeomPoints(Geom.UH_static)
        for i in range(n):
            w.add_data3(rng.uniform(-BOX / 2, BOX / 2), rng.uniform(-BOX / 2, BOX / 2), rng.uniform(0, HEIGHT))
            prim.add_vertex(i)
    g = Geom(vd)
    g.add_primitive(prim)
    node = GeomNode(kind)
    node.add_geom(g)
    return node


class WeatherFx:
    def __init__(self, base, world, weather, quality='high'):
        self.base = base
        self.weather = weather
        self.key = weather['key']
        self.root = base.render.attach_new_node('weather')
        self.t = 0.0
        self.layers = []
        self.speed = 0.0
        many = {'low': 0.4, 'medium': 0.7}.get(quality, 1.0)
        wind = weather['wind_vec']
        if self.key == 'rain':
            self.speed = 14.0
            node = _cloud('rain', int(5000 * many), wind)
            col = (0.82, 0.87, 0.97, 0.55)
        elif self.key == 'snow':
            self.speed = 1.6
            node = _cloud('snow', int(3200 * many), wind)
            col = (1.0, 1.0, 1.0, 0.9)
        else:
            node = None
        if node is not None:
            for i in range(2):
                np = self.root.attach_new_node(node if i == 0 else node.make_copy())
                np.set_color(*col)
                np.set_transparency(TransparencyAttrib.M_alpha)
                np.set_light_off()
                np.set_shader_off()
                np.set_fog_off()
                np.set_depth_write(False)
                np.set_bin('transparent', 40)
                if self.key == 'snow':
                    np.set_render_mode_thickness(3.0 if quality != 'low' else 2.0)
                self.layers.append(np)
        # The light and the grass
        if self.key in ('rain', 'snow'):
            f = Fog('weather')
            if self.key == 'rain':
                f.set_color(0.32, 0.35, 0.4) if not world.night else f.set_color(0.08, 0.09, 0.12)
                f.set_exp_density(0.009)
                world.amb.node().set_color(world.amb.node().get_color() * 0.85)
                world.sun.node().set_color(world.sun.node().get_color() * 0.75)
                # A wet pitch is darker and a touch shinier
                world.pitch_node.set_color_scale(0.8, 0.86, 0.85, 1)
                world.wet = 1.0
            else:
                f.set_color(0.82, 0.85, 0.9) if not world.night else f.set_color(0.3, 0.32, 0.38)
                f.set_exp_density(0.008)
                # A dusting of snow over the grass; the lines still show through
                pt = world.pitch
                cover = G.plane(pt.length + 8.0, pt.width + 8.0).node()
                cover.reparent_to(self.root)
                cover.set_pos(0, 0, 0.012)
                cover.set_color(0.95, 0.97, 1.0, 0.5)
                cover.set_transparency(TransparencyAttrib.M_alpha)
                cover.set_light_off()
                cover.set_shader_off()
                cover.set_depth_write(False)
                cover.set_bin('transparent', 1)
            world.root.set_fog(f)
        self.world = world

    def update(self, dt, cam_pos):
        if not self.layers:
            return
        self.t += dt
        fall = (self.t * self.speed) % HEIGHT
        # Snow sways a little; rain streaks already lean with the wind
        sway = 0.6 if self.key == 'snow' else 0.0
        cx = cam_pos[0] + math.sin(self.t * 0.7) * sway
        cy = cam_pos[1] + math.cos(self.t * 0.5) * sway
        base_z = cam_pos[2] - HEIGHT * 0.75
        for i, np in enumerate(self.layers):
            np.set_pos(cx, cy, base_z - fall + i * HEIGHT)

    def destroy(self):
        self.root.remove_node()


def wind_text(weather, attack=1):
    """HUD line for the weather, e.g. 'Rain' or 'Windy, 6 m/s behind you' (for the side attacking +x if attack=1)."""
    label = weather['label']
    sp = weather['wind_speed']
    if sp < (1.0 if weather['key'] in ('clear', 'wind') else 3.0):
        return '' if weather['key'] == 'clear' else label
    wx, wy = weather['wind_vec']
    along = wx * attack / sp
    where = 'behind you' if along > 0.5 else ('in your face' if along < -0.5 else 'across the pitch')
    return '%s, %d m/s %s' % (label, round(sp), where)
