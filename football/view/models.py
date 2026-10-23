"""Footballers built from primitives on a simple skeleton, and procedural
animation for every action state. Also the ball."""

import math

from panda3d.core import NodePath, Quat, Vec3, TransparencyAttrib, TextNode

from shootout import characters as CH

from . import geom as G
from . import shading as S
from . import textures as T

_num_cache = {}


def _number_tex(n, color):
    key = (n, color)
    if key not in _num_cache:
        _num_cache[key] = T.number(n, color)
    return _num_cache[key]


def _lerp(a, b, t):
    return a + (b - a) * t


def _smooth(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


class Footballer:
    """A rigged figure. Joints are NodePaths rotated each frame by animate()."""

    def __init__(self, parent, fb, kit, keeper=False, quality='high'):
        self.fb = fb
        lk = fb.look or {}
        cols = CH.look_colours(lk)
        skin = cols['skin'] + (1,)
        hair = cols['hair'] + (1,)
        boots = cols['boots'] + (1,)
        shirt = (kit['keeper'] if keeper else kit['shirt']) + (1,)
        shorts = ((0.12, 0.12, 0.14) if keeper else kit['shorts']) + (1,)
        socks = (kit['keeper'] if keeper else kit.get('socks', kit['shirt'])) + (1,)
        trim = kit.get('trim', (1, 1, 1)) + (1,)
        h = float(lk.get('h', 1.0))
        w = float(lk.get('w', 1.0))
        if fb.women:
            w *= 0.93
        seg = 16 if quality == 'high' else 10
        self.root = parent.attach_new_node('player')
        self.body = self.root.attach_new_node('body')
        self.body.set_scale(h, h, h)
        self.hips = self.body.attach_new_node('hips')
        self.hips.set_z(0.93)
        # Shorts and pelvis
        m = G.Mesh('pelvis')
        G.sphere(0.17, seg, 6, mesh=m, scale=(1.0 * w, 0.75, 0.75), center=(0, 0, 0.02), color=shorts)
        self._attach(self.hips, m)
        self.spine = self.hips.attach_new_node('spine')
        self.spine.set_z(0.06)
        m = G.Mesh('torso')
        G.cylinder(0.15 * w, 0.2 * w, 0.46, seg, mesh=m, base=(0, 0, 0), color=shirt)
        G.sphere(0.2 * w, seg, 6, mesh=m, center=(0, 0, 0.44), scale=(1, 0.66, 0.42), color=shirt)
        # Collar trim
        G.cylinder(0.075, 0.07, 0.04, seg, mesh=m, base=(0, 0, 0.5), color=trim, caps=False)
        tn = self._attach(self.spine, m)
        tn.set_sy(0.7)
        # Shirt number on the back
        num = G.plane(0.22, 0.22, normal_up=True).node()
        num.reparent_to(self.spine)
        num.set_pos(0, -0.115 * w * 1.0, 0.3)
        num.set_p(90)
        num.set_h(180)
        num.set_texture(_number_tex(fb.number, tuple(trim[:3]) if sum(trim[:3]) > 0.5 or sum(shirt[:3]) > 1.5 else (1, 1, 1)))
        num.set_transparency(TransparencyAttrib.M_alpha)
        num.set_depth_offset(1)
        # Head
        self.neck = self.spine.attach_new_node('neck')
        self.neck.set_z(0.52)
        m = G.Mesh('head')
        G.cylinder(0.055, 0.05, 0.1, seg, mesh=m, color=skin)
        G.sphere(0.105, seg, 8, mesh=m, center=(0, 0.01, 0.18), scale=(0.92, 1.0, 1.12), color=skin)
        # Nose and ears
        G.sphere(0.02, 6, 4, mesh=m, center=(0, 0.11, 0.17), color=skin)
        for s in (-1, 1):
            G.sphere(0.025, 6, 4, mesh=m, center=(s * 0.098, 0.0, 0.18), scale=(0.5, 1, 1.2), color=skin)
        # Eyes
        for s in (-1, 1):
            G.sphere(0.012, 6, 4, mesh=m, center=(s * 0.035, 0.095, 0.2), color=(0.05, 0.05, 0.06, 1))
        self._beard(m, lk.get('beard'), hair, seg)
        self._hair(m, lk.get('hair', 'short'), hair, seg)
        if lk.get('headband'):
            G.cylinder(0.104, 0.104, 0.03, seg, mesh=m, base=(0, 0.005, 0.22), color=trim, caps=False)
        self._attach(self.neck, m, 'skin')
        # Arms
        long_sleeves = keeper or lk.get('sleeves') == 'long'
        gloves = CH.GLOVE_COLOURS.get(lk.get('gloves', 'white'), (0.95, 0.95, 0.95)) + (1,) if keeper else skin
        self.shoulders, self.elbows = [], []
        for s in (-1, 1):
            sh = self.spine.attach_new_node('shoulder')
            sh.set_pos(s * 0.22 * w, 0, 0.44)
            m = G.Mesh('upper')
            G.capsule(0.052, 0.26, seg, mesh=m, color=shirt, r_top=0.06)
            if not long_sleeves:
                G.cylinder(0.05, 0.05, 0.12, seg, mesh=m, base=(0, 0, -0.27), color=skin, caps=False)
                # Sleeve cuff in the trim colour
                G.cylinder(0.058, 0.056, 0.03, seg, mesh=m, base=(0, 0, -0.17), color=trim, caps=False)
            self._attach(sh, m)
            el = sh.attach_new_node('elbow')
            el.set_z(-0.27)
            m = G.Mesh('fore')
            G.capsule(0.043, 0.23, seg, mesh=m, color=shirt if long_sleeves else skin, r_top=0.048)
            G.sphere(0.05 if keeper else 0.042, seg, 5, mesh=m, center=(0, 0.0, -0.28), scale=(0.8, 1.0, 1.3), color=gloves)
            self._attach(el, m)
            self.shoulders.append(sh)
            self.elbows.append(el)
        # Legs
        sock_down = lk.get('socks') == 'down'
        self.hipj, self.knees, self.ankles = [], [], []
        for s in (-1, 1):
            hp = self.hips.attach_new_node('hip')
            hp.set_pos(s * 0.1 * w, 0, 0.0)
            m = G.Mesh('thigh')
            G.capsule(0.085 * w, 0.42, seg, mesh=m, color=skin, r_top=0.09 * w)
            G.cylinder(0.098 * w, 0.094 * w, 0.2, seg, mesh=m, base=(0, 0, -0.18), color=shorts, caps=False)
            # Hem of the shorts
            G.cylinder(0.1 * w, 0.1 * w, 0.025, seg, mesh=m, base=(0, 0, -0.185), color=trim, caps=False)
            self._attach(hp, m)
            kn = hp.attach_new_node('knee')
            kn.set_z(-0.44)
            m = G.Mesh('shin')
            G.capsule(0.06 * w, 0.4, seg, mesh=m, color=socks, r_top=0.068 * w)
            if sock_down:
                G.cylinder(0.066 * w, 0.066 * w, 0.18, seg, mesh=m, base=(0, 0, -0.2), color=skin, caps=False)
            else:
                G.cylinder(0.07 * w, 0.07 * w, 0.03, seg, mesh=m, base=(0, 0, -0.06), color=trim, caps=False)
            self._attach(kn, m)
            an = kn.attach_new_node('ankle')
            an.set_z(-0.42)
            m = G.Mesh('boot')
            G.box(0.09, 0.25, 0.085, mesh=m, center=(0, 0.05, -0.035), color=boots)
            G.box(0.085, 0.08, 0.02, mesh=m, center=(0, 0.12, -0.075), color=(0.1, 0.1, 0.1, 1))
            self._attach(an, m, 'boots')
            self.hipj.append(hp)
            self.knees.append(kn)
            self.ankles.append(an)
        self.keeper = keeper
        self.kick_side = 0 if fb.foot == 'L' else 1
        self.height = h
        self._last_state = None

    def _attach(self, parent, mesh, mat='shirt'):
        n = mesh.node()
        n.reparent_to(parent)
        S.material(n, mat)
        return n

    # ------------------------------------------------------- hair and beards
    def _hair(self, m, style, col, seg):
        hc = (0, 0.01, 0.18)
        if style == 'bald':
            return
        if style in ('buzz',):
            G.sphere(0.109, seg, 6, mesh=m, center=hc, scale=(0.94, 1.02, 1.14), zmin=0.05, color=col)
            G.sphere(0.1, seg, 6, mesh=m, center=(0, -0.035, 0.16), scale=(0.96, 0.72, 1.0), color=col)
            return
        if style == 'afro':
            G.sphere(0.17, seg, 8, mesh=m, center=(0, -0.01, 0.24), scale=(1.0, 1.0, 0.85), zmin=-0.25, color=col)
            return
        # A cap of hair over the top, and the back of the head
        G.sphere(0.114, seg, 6, mesh=m, center=(0, -0.003, 0.185), scale=(0.95, 1.03, 1.13), zmin=0.12, color=col)
        G.sphere(0.1, seg, 6, mesh=m, center=(0, -0.042, 0.16), scale=(0.97, 0.72, 1.05), color=col)
        if style in ('long', 'braids'):
            G.box(0.2, 0.06, 0.24, mesh=m, center=(0, -0.08, 0.1), color=col)
        if style == 'ponytail':
            G.capsule(0.035, 0.16, 6, mesh=m, base=(0, -0.13, 0.22), color=col)
        if style in ('bun', 'manbun'):
            G.sphere(0.05, 8, 5, mesh=m, center=(0, -0.08, 0.3), color=col)
        if style == 'quiff':
            G.sphere(0.07, 8, 5, mesh=m, center=(0, 0.06, 0.29), scale=(1.2, 1, 0.7), color=col)
        if style == 'mohawk':
            G.box(0.04, 0.22, 0.08, mesh=m, center=(0, -0.01, 0.31), color=col)
        if style == 'curly':
            for a in range(8):
                ang = a / 8 * 2 * math.pi
                G.sphere(0.04, 6, 4, mesh=m, center=(math.cos(ang) * 0.08, math.sin(ang) * 0.08 - 0.01, 0.27), color=col)
        if style == 'r9':
            G.box(0.06, 0.05, 0.03, mesh=m, center=(0, 0.07, 0.29), color=col)

    def _beard(self, m, beard, col, seg):
        if not beard:
            return
        if beard == 'goatee':
            G.sphere(0.035, 8, 5, mesh=m, center=(0, 0.09, 0.08), color=col)
            return
        r = 0.098 if beard == 'full' else 0.1
        G.sphere(r, seg, 6, mesh=m, center=(0, 0.012, 0.15), scale=(0.93, 1.0, 1.0), zmin=-1.0, zmax=-0.25,
                 color=col if beard == 'full' else (col[0] * 0.8 + 0.1, col[1] * 0.8 + 0.08, col[2] * 0.8 + 0.06, 1))

    # ------------------------------------------------------------ animation
    def pose(self, x, y, z, facing, state, anim, state_t, phase, speed, dive_dir, state_len=0.5, holding=False,
             t=0.0):
        r = self.root
        r.set_pos(x, y, z)
        r.set_h(math.degrees(facing) - 90.0)
        L, R = 0, 1
        hip = [0.0, 0.0]
        hip_r = [0.0, 0.0]
        knee = [0.0, 0.0]
        sh = [0.0, 0.0]
        sh_r = [-8.0, 8.0]
        el = [-15.0, -15.0]
        lean = 0.0
        roll = 0.0
        twist = 0.0
        bob = 0.0
        body_p, body_r, body_z = 0.0, 0.0, 0.0
        head_p = 0.0
        k = self.kick_side
        o = 1 - k
        run = min(1.0, speed / 7.5)
        if state in ('run', 'skill') or (state == 'celebrate' and anim != 'win'):
            s = math.sin(phase * 2 * math.pi)
            c = math.cos(phase * 2 * math.pi)
            amp = 12 + 38 * run
            hip = [s * amp, -s * amp]
            knee = [-(18 + 60 * run) * max(0.0, -c) - 6, -(18 + 60 * run) * max(0.0, c) - 6]
            sh = [-s * (10 + 35 * run), s * (10 + 35 * run)]
            el = [-30 - 50 * run, -30 - 50 * run]
            lean = 4 + 12 * run
            bob = abs(s) * 0.05 * run
            if speed < 0.4:
                # Standing: weight on the balls of the feet, a little breathing
                br = math.sin(t * 2.0 + self.fb.number) * 2.0
                hip = [3.0, -2.0]
                knee = [-10.0, -12.0]
                sh = [br, -br]
                sh_r = [-12.0, 12.0]
                lean = 6.0
                if self.keeper:
                    # Set position: crouched, gloves ready
                    hip = [25.0, 25.0]
                    hip_r = [-12.0, 12.0]
                    knee = [-45.0, -45.0]
                    lean = 20.0
                    sh = [40.0, 40.0]
                    sh_r = [-35.0, 35.0]
                    el = [-40.0, -40.0]
                    bob = -0.12
            if state == 'celebrate':
                sh = [160.0 + s * 10, 160.0 - s * 10]
                sh_r = [-30.0, 30.0]
                el = [-10.0, -10.0]
            if state == 'skill':
                twist = math.sin(state_t * 18) * 20
                hip[k] += 25
        elif state == 'kick':
            f = state_t / max(0.05, state_len)
            if anim == 'header':
                head_p = 35 * math.sin(min(1.0, f * 1.6) * math.pi)
                lean = -15 + 35 * f
                sh = [40.0, 40.0]
                sh_r = [-50.0, 50.0]
                knee = [-50.0, -30.0]
            elif anim in ('throw',):
                sh = [180 - 120 * f, 180 - 120 * f]
                el = [-40.0, -40.0]
                lean = -10 + 30 * f
            else:
                # Wind up, strike, follow through
                back = -45 if anim not in ('pass',) else -30
                fwd = 80 if anim in ('shoot', 'lob', 'chip', 'punt', 'finesse') else 55
                if f < 0.35:
                    a = back * _smooth(f / 0.35)
                    kk = -70 * _smooth(f / 0.35)
                elif f < 0.6:
                    g = (f - 0.35) / 0.25
                    a = _lerp(back, fwd, _smooth(g))
                    kk = _lerp(-70, -5, _smooth(g))
                else:
                    g = (f - 0.6) / 0.4
                    a = _lerp(fwd, 10, _smooth(g))
                    kk = _lerp(-5, -15, g)
                hip[k] = a
                knee[k] = kk
                hip[o] = -6
                knee[o] = -15
                sh = [-30.0, -30.0]
                sh[k] = 25.0
                sh_r = [-55.0, 55.0]
                el = [-25.0, -25.0]
                lean = -8 + 12 * f
                twist = (20 if k == 1 else -20) * math.sin(f * math.pi)
                if anim == 'finesse':
                    hip_r[k] = (-20 if k == 1 else 20) * math.sin(f * math.pi)
        elif state == 'tackle':
            f = state_t / max(0.05, state_len)
            hip[k] = 60 * math.sin(min(1.0, f * 1.5) * math.pi)
            hip_r[k] = -20
            knee[k] = -10
            knee[o] = -40
            lean = 15
            sh_r = [-45.0, 45.0]
            bob = -0.1
        elif state == 'slide':
            f = min(1.0, state_t / 0.25)
            body_p = 0.0
            body_r = 0.0
            lean = -60 * f
            body_z = -0.55 * f
            hip[k] = 85 * f
            knee[k] = -5
            hip[o] = 50 * f
            knee[o] = -100 * f
            sh = [-30.0, -30.0]
            sh_r = [-60.0, 60.0]
        elif state in ('down', 'getup'):
            if state == 'down':
                f = min(1.0, state_t / 0.35)
            else:
                f = 1.0 - min(1.0, state_t / max(0.1, state_len))
            lean = -80 * f
            body_z = -0.78 * f
            hip = [40 * f, 20 * f]
            knee = [-60 * f, -20 * f]
            sh = [60 * f, 100 * f]
            sh_r = [-70 * f, 70 * f]
        elif state == 'dive':
            f = min(1.0, state_t / 0.22)
            dx, dy, dz = dive_dir if dive_dir else (0.0, 0.0, 1.0)
            # Lateral component in the keeper's own frame
            fx = math.cos(facing)
            fy = math.sin(facing)
            side = -(dx * -fy + dy * fx)          # +1: to his right
            if anim == 'block':
                hip_r = [-35.0 * f, 35.0 * f]
                knee = [-30.0, -30.0]
                sh = [20.0, 20.0]
                sh_r = [-80.0 * f, 80.0 * f]
                body_z = -0.3 * f
            else:
                body_r = 78 * f * (1 if side >= 0 else -1)
                height = dz if dz else 0.8
                body_z = -0.55 * f + (0.15 if height > 1.3 else 0.0)
                reach_up = 175.0 if height > 0.7 else 150.0
                sh = [0.0, 0.0]
                sh_r = [-reach_up * f, reach_up * f]
                el = [-5.0, -5.0]
                hip_r = [-15.0 * f, 15.0 * f]
                knee = [-20.0, -35.0]
        elif state == 'hold':
            sh = [55.0, 55.0]
            sh_r = [-20.0, 20.0]
            el = [-70.0, -70.0]
            if speed > 0.4:
                s = math.sin(phase * 2 * math.pi)
                hip = [s * 30, -s * 30]
                knee = [-30 * max(0, -s), -30 * max(0, s)]
        elif state == 'throw':
            f = state_t / max(0.05, state_len)
            sh = [170 - 110 * f, 170 - 110 * f]
            el = [-30.0, -30.0]
            lean = -10 + 30 * f
        elif state == 'celebrate':
            # Final whistle: jumping with arms up
            j = abs(math.sin(t * 6.0 + self.fb.number))
            body_z = j * 0.25
            sh = [165.0, 165.0]
            sh_r = [-25.0, 25.0]
            el = [-5.0, -5.0]
            knee = [-30 * (1 - j), -30 * (1 - j)]
            hip = [15 * (1 - j), 15 * (1 - j)]
        self.body.set_hpr(twist * 0.3, body_p, body_r)
        self.body.set_z(body_z + bob)
        # Positive pitch tilts a joint's +z backwards, so a forward lean is negative
        self.spine.set_hpr(twist, -lean, roll)
        self.neck.set_p(-head_p + lean * 0.5)
        for i in (L, R):
            self.hipj[i].set_hpr(0, hip[i], hip_r[i])
            self.knees[i].set_p(knee[i])
            self.ankles[i].set_p(-knee[i] * 0.3 - hip[i] * 0.15)
            self.shoulders[i].set_hpr(0, sh[i], sh_r[i])
            self.elbows[i].set_p(-el[i])


class Ball:
    def __init__(self, parent, quality='high'):
        m = G.sphere(0.11, 28 if quality == 'high' else 14, 16 if quality == 'high' else 10)
        self.node = m.node()
        self.node.reparent_to(parent)
        S.material(self.node, 'ball')
        self.node.set_texture(T.ball())
        self.q = Quat()

    def pose(self, pos, axis, angle):
        self.node.set_pos(*pos)
        q = Quat()
        q.set_from_axis_angle(angle, Vec3(*axis))
        self.node.set_quat(q)
