"""Footballers: a sculpted, skinned body (see body.py) in a kit painted for
each player, animated procedurally for every action state, with smooth
blends between states. Also the ball."""

import math
import zlib

from panda3d.core import Quat, Vec3

from shootout import characters as CH

from . import body as BD
from . import geom as G
from . import kits as K
from . import shading as S
from . import textures as T

IRIS = [(0.25, 0.15, 0.08), (0.18, 0.11, 0.06), (0.3, 0.42, 0.55), (0.32, 0.4, 0.22), (0.12, 0.08, 0.05)]
SOLES = {'black': (0.92, 0.92, 0.9), 'white': (0.85, 0.2, 0.2), 'gold': (0.1, 0.1, 0.1), 'pink': (0.95, 0.95, 0.95),
         'orange': (0.1, 0.1, 0.12), 'cyan': (0.1, 0.12, 0.2)}
ACCENTS = {'black': (0.9, 0.9, 0.92), 'white': (0.1, 0.1, 0.12), 'gold': (0.98, 0.98, 0.95), 'pink': (0.1, 0.1, 0.12),
           'orange': (0.1, 0.1, 0.12), 'cyan': (0.95, 0.95, 0.95)}

# Joint channels driven by the animator (all angles in degrees)
CHANNELS = ('hip0', 'hip1', 'abd0', 'abd1', 'rot0', 'rot1', 'knee0', 'knee1', 'ank0', 'ank1', 'toe0', 'toe1',
            'sh0', 'sh1', 'sha0', 'sha1', 'el0', 'el1', 'wr0', 'wr1', 'lean', 'side', 'twist', 'pel_h', 'pel_r',
            'head_p', 'head_h', 'body_p', 'body_r', 'body_z', 'shrug')
_IDX = {c: i for i, c in enumerate(CHANNELS)}

# How long the blend into each state takes
BLEND_IN = {'kick': 0.07, 'dive': 0.06, 'tackle': 0.08, 'slide': 0.08, 'down': 0.1, 'run': 0.22, 'getup': 0.15,
            'celebrate': 0.3, 'hold': 0.2, 'throw': 0.12, 'jump': 0.08, 'skill': 0.1}


def _lerp(a, b, t):
    return a + (b - a) * t


def _smooth(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def _pos(x):
    return x if x > 0 else 0.0


def _seed(*key):
    return zlib.crc32(repr(key).encode())


class Footballer:
    """One player: builds the rig and mesh, then poses it each frame."""

    def __init__(self, parent, fb, kit, keeper=False, quality='high'):
        self.fb = fb
        lk = fb.look or {}
        cols = CH.look_colours(lk)
        # The shootout's skin tones are a touch pale under the stadium shader
        cols['skin'] = tuple(c * k for c, k in zip(cols['skin'], (0.96, 0.89, 0.84)))
        h = float(lk.get('h', 1.0))
        w = float(lk.get('w', 1.0))
        seed = _seed(fb.name, fb.number)
        boots_name = lk.get('boots', 'black')
        trim = tuple(kit.get('trim', (1, 1, 1)))
        shirt_c = tuple(kit['keeper'] if keeper else kit['shirt'])
        if keeper:
            trim = K.contrast(shirt_c, (0.08, 0.08, 0.1), (0.95, 0.95, 0.95))
        gloves = CH.GLOVE_COLOURS.get(lk.get('gloves', 'white'), (0.95, 0.95, 0.95))
        spec = dict(
            w=w * (0.93 if fb.women else 1.0), women=bool(fb.women), keeper=keeper, sleeves=lk.get('sleeves'),
            socks_down=lk.get('socks') == 'down', hair=lk.get('hair', 'short'), beard=lk.get('beard'),
            headband=bool(lk.get('headband')), skin=tuple(cols['skin']), hair_col=tuple(cols['hair']),
            boots=tuple(cols['boots']), boot_accent=ACCENTS.get(boots_name, (0.9, 0.9, 0.9)),
            sole=SOLES.get(boots_name, (0.9, 0.9, 0.9)), gloves=tuple(gloves),
            glove_accent=K.contrast(gloves, (0.1, 0.1, 0.12), (0.95, 0.95, 0.95)), trim=trim,
            iris=IRIS[seed % len(IRIS)] if int(lk.get('skin', 1)) < 2 else IRIS[(0, 1, 4)[seed % 3]],
        )
        detail = 1.0 if quality == 'high' else 0.6
        self.root = parent.attach_new_node('player')
        skel = BD.skeleton(spec['w'], spec['women'])
        self.rig = BD.Rig(self.root, skel)
        self.body = self.rig.np
        self.body.set_scale(h)
        builder = BD.BodyBuilder(spec, self.rig.blends, BD.rest_positions(skel), detail)
        parts = builder.build()
        textures = {
            'skin': K.skin_detail(),
            'head': K.face(spec['skin'], spec['hair_col'], spec['beard'], spec['women'], spec['iris']),
            'hair': K.hair_strands(), 'shirt': K.shirt(kit, fb.number, fb.name, keeper),
            'lower': K.lower_kit(kit, keeper), 'boots': K.boot_detail(),
        }
        mats = {'skin': 'skin', 'head': 'skin', 'eyes': 'eye', 'hair': 'hair', 'shirt': 'shirt', 'trim': 'shirt',
                'lower': 'shirt', 'boots': 'boots'}
        for name, part in parts.items():
            if part.empty():
                continue
            np_ = BD.geom_node(name, part, self.rig.blends)
            np_.reparent_to(self.body)
            S.material(np_, mats[name])
            if name in textures:
                np_.set_texture(textures[name])
        S.use_skinning(self.body)
        c = self.rig.ctl
        self.ctl = c
        self.hipj = [c['hip_L'], c['hip_R']]
        self.knees = [c['knee_L'], c['knee_R']]
        self.ankles = [c['ankle_L'], c['ankle_R']]
        self.toes = [c['toe_L'], c['toe_R']]
        self.clavs = [c['clav_L'], c['clav_R']]
        self.shoulders = [c['shoulder_L'], c['shoulder_R']]
        self.elbows = [c['elbow_L'], c['elbow_R']]
        self.wrists = [c['wrist_L'], c['wrist_R']]
        self.pelvis, self.spine, self.chest = c['pelvis'], c['spine'], c['chest']
        self.neck, self.head = c['neck'], c['head']
        self.pelvis_z = self.rig.rest['pelvis'][2]
        self.keeper = keeper
        self.kick_side = 0 if fb.foot == 'L' else 1
        self.height = h
        self._last_state = None
        self._cur = [0.0] * len(CHANNELS)
        self._from = None
        self._blend_t = 1.0
        self._blend_len = 0.2
        self._last_t = None
        self._run = 0.0
        self._face = None
        self._turn = 0.0
        self._quirk = (seed % 1000) / 1000.0
        self._phase = self._quirk

    # ------------------------------------------------------------ helpers
    def foot_positions(self, other):
        """World positions of both feet (for contact shadows)."""
        return [a.get_pos(other) for a in self.ankles]

    # ------------------------------------------------------------ animation
    def pose(self, x, y, z, facing, state, anim, state_t, phase, speed, dive_dir, state_len=0.5, holding=False,
             t=0.0):
        dt = 1.0 / 30 if self._last_t is None else max(0.0, min(0.1, t - self._last_t))
        self._last_t = t
        # Facing: follow the sim, but turn smoothly, and lean into the turn
        if self._face is None or dt == 0.0 or state in ('dive', 'slide', 'down'):
            turn = 0.0
            self._face = facing
        else:
            d = (facing - self._face + math.pi) % (2 * math.pi) - math.pi
            step = d * min(1.0, dt * 16.0)
            self._face += step
            turn = step / max(1e-3, dt)
        self._turn += (turn - self._turn) * min(1.0, dt * 8.0)
        self._run += (min(1.0, speed / 7.5) - self._run) * min(1.0, dt * 7.0)
        # Stride from the ground covered, so the planted foot doesn't skate: a
        # full cycle (two steps) is about 1.7 m walking and 4 m flat out
        self._phase = (self._phase + speed * dt / (1.2 + 0.36 * speed)) % 1.0
        phase = self._phase
        r = self.root
        r.set_pos(x, y, z)
        r.set_h(math.degrees(self._face) - 90.0)
        tgt = self._target(state, anim, state_t, phase, speed, dive_dir, state_len, holding, t)
        key = (state, anim)
        if key != self._last_state:
            if self._last_state is not None:
                self._from = list(self._cur)
                self._blend_t = 0.0
                self._blend_len = BLEND_IN.get(state, 0.15)
            self._last_state = key
        if self._from is not None and self._blend_t < self._blend_len:
            self._blend_t += dt
            b = _smooth(self._blend_t / self._blend_len)
            out = [_lerp(a, c, b) for a, c in zip(self._from, tgt)]
        else:
            out = tgt
        self._cur = out
        self._apply(out)

    def _target(self, state, anim, state_t, phase, speed, dive_dir, state_len, holding, t):
        v = [0.0] * len(CHANNELS)
        I = _IDX
        k = self.kick_side
        o = 1 - k
        q = self._quirk
        # Arms rest a little away from the body, elbows soft
        v[I['sha0']] = v[I['sha1']] = 6.0
        v[I['el0']] = v[I['el1']] = 12.0
        if state in ('run', 'skill') or (state == 'celebrate' and anim != 'win'):
            self._run_cycle(v, phase, speed, t)
            if state == 'celebrate':
                # Arms out like a plane, or both fists up
                if q < 0.5:
                    v[I['sh0']] = v[I['sh1']] = 10.0
                    v[I['sha0']] = v[I['sha1']] = 85.0
                    v[I['el0']] = v[I['el1']] = 8.0
                    v[I['side']] = -12.0 * math.sin(t * 2.0)
                else:
                    v[I['sh0']] = v[I['sh1']] = 150.0 + 10 * math.sin(t * 9)
                    v[I['sha0']] = v[I['sha1']] = 25.0
                    v[I['el0']] = v[I['el1']] = 40.0
                    v[I['head_p']] = -18.0
            if state == 'skill':
                f = state_t / max(0.05, state_len)
                v[I['twist']] += math.sin(f * math.pi * 2) * 22
                v[I['hip%d' % k]] += 28 * math.sin(f * math.pi)
                v[I['rot%d' % k]] += 25 * math.sin(f * math.pi * 2)
                v[I['knee%d' % k]] += 20 * math.sin(f * math.pi)
                v[I['body_z']] -= 0.04
                v[I['sha0']] += 25
                v[I['sha1']] += 25
        elif state == 'kick':
            self._kick(v, anim, state_t / max(0.05, state_len))
        elif state == 'jump':
            up = min(1.0, state_t / 0.15)
            v[I['knee0']] = v[I['knee1']] = 35.0 * up + 10
            v[I['hip0']] = v[I['hip1']] = 18.0 * up
            v[I['ank0']] = v[I['ank1']] = -30.0 * up
            v[I['sh0']] = v[I['sh1']] = 40.0
            v[I['sha0']] = v[I['sha1']] = 55.0
            v[I['el0']] = v[I['el1']] = 50.0
            v[I['lean']] = 6.0
            v[I['head_p']] = -10.0
        elif state == 'tackle':
            f = state_t / max(0.05, state_len)
            reach = math.sin(min(1.0, f * 1.6) * math.pi * 0.5) * (1 - _smooth((f - 0.7) / 0.3))
            v[I['hip%d' % k]] = 55 * reach
            v[I['abd%d' % k]] = 18 * reach
            v[I['rot%d' % k]] = 30 * reach
            v[I['knee%d' % k]] = 8
            v[I['ank%d' % k]] = 15 * reach
            v[I['hip%d' % o]] = 25 * reach
            v[I['knee%d' % o]] = 15 + 55 * reach
            v[I['ank%d' % o]] = -10 * reach
            v[I['lean']] = 10 + 14 * reach
            v[I['body_z']] = -0.16 * reach
            v[I['sh0']] = v[I['sh1']] = 15.0
            v[I['sha0']] = v[I['sha1']] = 40 * reach + 10
            v[I['el0']] = v[I['el1']] = 30.0
            v[I['twist']] = (12 if k == 1 else -12) * reach
        elif state == 'slide':
            f = state_t / max(0.05, state_len)
            g = _smooth(min(1.0, state_t / 0.22))
            # Down on the hip with the leading leg straight along the grass to the
            # ball (the body pivots round the feet), the other leg tucked under
            v[I['body_p']] = 78 * g
            v[I['body_z']] = 0.02 * g
            v[I['lean']] = 38 * g
            v[I['hip%d' % k]] = 4 * g
            v[I['knee%d' % k]] = 4
            v[I['ank%d' % k]] = 20 * g
            v[I['hip%d' % o]] = 35 * g
            v[I['knee%d' % o]] = 100 * g
            v[I['abd%d' % o]] = 25 * g
            v[I['rot%d' % o]] = 30 * g
            v[I['body_r']] = (14 if k == 1 else -14) * g
            # Hand trailing on the grass, the other arm up for balance
            v[I['sh%d' % o]] = -40 * g
            v[I['sha%d' % o]] = 40 * g
            v[I['el%d' % o]] = 10.0
            v[I['sh%d' % k]] = 40 * g
            v[I['sha%d' % k]] = 50 * g
            v[I['el%d' % k]] = 40.0
            v[I['head_p']] = -30 * g
            if f > 0.75:
                v[I['body_p']] *= 1 - _smooth((f - 0.75) / 0.25) * 0.3
        elif state in ('down', 'getup'):
            self._down(v, state, anim, state_t, state_len)
        elif state == 'dive':
            self._dive(v, anim, state_t, state_len, dive_dir)
        elif state == 'hold':
            # Ball tucked into the chest
            v[I['sh0']] = v[I['sh1']] = 48.0
            v[I['sha0']] = v[I['sha1']] = 8.0
            v[I['el0']] = v[I['el1']] = 105.0
            v[I['wr0']] = v[I['wr1']] = 20.0
            if speed > 0.4:
                self._legs_only(v, phase, speed)
            else:
                v[I['knee0']] = v[I['knee1']] = 8.0
        elif state == 'throw':
            f = state_t / max(0.05, state_len)
            a = _smooth(f / 0.45)
            b = _smooth((f - 0.45) / 0.35)
            arm = _lerp(_lerp(120, 185, a), 60, b)
            v[I['sh0']] = v[I['sh1']] = arm
            v[I['sha0']] = v[I['sha1']] = 12.0
            v[I['el0']] = v[I['el1']] = _lerp(_lerp(30, 85, a), 15, b)
            v[I['lean']] = _lerp(_lerp(0, -16, a), 22, b)
            v[I['hip%d' % k]] = 18 * (1 - b)
            v[I['knee%d' % o]] = 22.0
            v[I['knee%d' % k]] = 12.0
            v[I['head_p']] = _lerp(-12, 8, b)
        elif state == 'celebrate':
            # Final whistle: jumping, both arms up
            j = abs(math.sin(t * 5.5 + self.fb.number))
            v[I['body_z']] = j * 0.22
            v[I['sh0']] = v[I['sh1']] = 160.0
            v[I['sha0']] = v[I['sha1']] = 22.0
            v[I['el0']] = v[I['el1']] = 15 + 20 * j
            v[I['knee0']] = v[I['knee1']] = 35 * (1 - j) + 8
            v[I['hip0']] = v[I['hip1']] = 18 * (1 - j)
            v[I['ank0']] = v[I['ank1']] = -25 * j
            v[I['head_p']] = -15.0
        # Lean into turns when running
        if state in ('run', 'hold', 'skill'):
            v[I['body_r']] += max(-14.0, min(14.0, -math.degrees(self._turn) * speed * 0.035))
        return v

    def _legs_only(self, v, phase, speed):
        I = _IDX
        run = min(1.0, speed / 7.5)
        a = phase * 2 * math.pi
        for i in (0, 1):
            ai = a + i * math.pi
            v[I['hip%d' % i]] = 6 * run + (12 + 26 * run) * math.sin(ai)
            v[I['knee%d' % i]] = 10 + (20 + 60 * run) * _pos(math.cos(ai - 0.35)) ** 1.3
            v[I['ank%d' % i]] = -(v[I['hip%d' % i]] - v[I['knee%d' % i]]) * 0.6

    def _run_cycle(self, v, phase, speed, t):
        I = _IDX
        run = self._run
        if speed < 0.4 and run < 0.12:
            self._stand(v, t)
            return
        a = phase * 2 * math.pi
        walk = 1.0 - min(1.0, run * 2.5)
        for i in (0, 1):
            ai = a + i * math.pi
            s, c = math.sin(ai), math.cos(ai)
            hip = 8 * run + (14 + 32 * run) * s
            # Knee folds high in the swing, gives a little in the stance
            knee = (6 + 10 * run) + (16 + 88 * run) * _pos(math.cos(ai - 0.45)) ** 1.4 + 14 * run * _pos(-c) * _pos(s)
            # Foot flat in the stance, toes pointed at toe-off, pulled up in the swing
            stance = _pos(-c)
            ank = -(hip - knee) * (0.85 * stance + 0.35 * (1 - stance)) - 26 * run * _pos(-s) ** 1.5 + 8 * _pos(c) * run
            v[I['hip%d' % i]] = hip
            v[I['knee%d' % i]] = knee
            v[I['ank%d' % i]] = ank
            v[I['toe%d' % i]] = 22 * run * _pos(-s) * stance
            v[I['abd%d' % i]] = 2.0 + 2.0 * walk
            # Arms swing against the legs, elbows bent more when running
            v[I['sh%d' % i]] = 6 * run - (10 + 38 * run) * s
            v[I['el%d' % i]] = 20 + 70 * run + 14 * _pos(-s) * run
            v[I['sha%d' % i]] = 8 + 6 * run
            v[I['wr%d' % i]] = 10 * run
        # Pelvis turns with the legs, the chest turns against it
        v[I['pel_h']] = -6 * (0.4 + run) * math.sin(a)
        v[I['twist']] = 8 * (0.4 + run) * math.sin(a)
        v[I['pel_r']] = 3.5 * math.cos(2 * a) * (0.5 + run * 0.5)
        v[I['lean']] = 3 + 13 * run
        # Lowest at mid-stance, highest in flight
        v[I['body_z']] = (0.012 + 0.03 * run) * (1 - math.cos(2 * a)) * 0.5 - 0.025 * run
        v[I['head_p']] = -0.45 * v[I['lean']]

    def _stand(self, v, t):
        I = _IDX
        q = self._quirk
        br = math.sin(t * 1.9 + q * 6)
        sway = math.sin(t * 0.6 + q * 9)
        if self.keeper:
            # Set position: crouched, weight forward, gloves ready, a little bounce
            bounce = math.sin(t * 5.0 + q * 4) * 0.01
            v[I['hip0']] = v[I['hip1']] = 32.0
            v[I['abd0']] = v[I['abd1']] = 12.0
            v[I['rot0']] = v[I['rot1']] = 8.0
            v[I['knee0']] = v[I['knee1']] = 58.0
            v[I['ank0']] = v[I['ank1']] = -(32.0 - 58.0) * 0.9
            v[I['lean']] = 24.0
            v[I['sh0']] = v[I['sh1']] = 42.0
            v[I['sha0']] = v[I['sha1']] = 32.0
            v[I['el0']] = v[I['el1']] = 55.0
            v[I['wr0']] = v[I['wr1']] = -20.0
            v[I['body_z']] = -0.13 + bounce
            v[I['head_p']] = -18.0
            return
        # Weight on the balls of the feet, shifting a little from foot to foot, breathing
        v[I['hip0']] = 4.0 + 2 * sway
        v[I['hip1']] = -2.0 - 2 * sway
        v[I['knee0']] = 12.0 + 3 * sway
        v[I['knee1']] = 10.0 - 3 * sway
        for i in (0, 1):
            v[I['ank%d' % i]] = -(v[I['hip%d' % i]] - v[I['knee%d' % i]])
            v[I['abd%d' % i]] = 4.0
            v[I['rot%d' % i]] = 8.0
        v[I['pel_r']] = 2.5 * sway
        v[I['side']] = -1.5 * sway
        v[I['sh0']] = 4 + br * 1.5
        v[I['sh1']] = 4 - br * 1.5
        v[I['sha0']] = v[I['sha1']] = 9.0
        v[I['el0']] = v[I['el1']] = 22.0
        v[I['lean']] = 5.0 + br * 0.8
        v[I['shrug']] = br * 1.2
        v[I['head_h']] = 10 * math.sin(t * 0.37 + q * 7)

    def _kick(self, v, anim, f):
        I = _IDX
        k = self.kick_side
        o = 1 - k
        sk = 1 if k == 1 else -1
        if anim == 'header':
            up = math.sin(min(1.0, f * 1.4) * math.pi)
            v[I['head_p']] = 38 * up - 18
            v[I['lean']] = -14 + 34 * _smooth(f * 1.3)
            v[I['sh0']] = v[I['sh1']] = 35.0
            v[I['sha0']] = v[I['sha1']] = 55.0
            v[I['el0']] = v[I['el1']] = 60.0
            v[I['knee0']] = 40.0
            v[I['knee1']] = 25.0
            v[I['hip0']] = 15.0
            v[I['ank0']] = v[I['ank1']] = -20.0
            return
        if anim == 'throw':
            v[I['sh0']] = v[I['sh1']] = 180 - 120 * f
            v[I['el0']] = v[I['el1']] = 50 * (1 - f)
            v[I['lean']] = -12 + 32 * f
            return
        big = anim in ('shoot', 'lob', 'chip', 'punt', 'finesse', 'volley')
        side_foot = anim in ('pass', 'finesse')
        back = -38 if big else -26
        fwd = {'shoot': 78, 'punt': 100, 'lob': 70, 'chip': 52, 'finesse': 66}.get(anim, 50)
        knee_back = 105 if big else 80
        # Wind up, strike (the knee snaps straight just after the hip), follow through
        if f < 0.36:
            g = _smooth(f / 0.36)
            hip = back * g
            knee = 20 + (knee_back - 20) * g
            plant = 18 * g
        elif f < 0.56:
            g = (f - 0.36) / 0.2
            hip = _lerp(back, fwd, _smooth(g))
            knee = _lerp(knee_back, 4, _smooth(g * 1.25 - 0.2))
            plant = 18
        else:
            g = (f - 0.56) / 0.44
            hip = _lerp(fwd, fwd + 8, _smooth(g * 2.5)) if g < 0.4 else _lerp(fwd + 8, 8, _smooth((g - 0.4) / 0.6))
            knee = _lerp(4, 25, _smooth(g))
            plant = _lerp(18, 4, _smooth(g))
        strike = math.sin(min(1.0, f / 0.56) * math.pi * 0.5)
        v[I['hip%d' % k]] = hip
        v[I['knee%d' % k]] = knee
        v[I['ank%d' % k]] = -35 if not side_foot else 8
        v[I['rot%d' % k]] = 35 * strike if side_foot else 4
        v[I['abd%d' % k]] = 8
        # Plant foot beside the ball, knee bent, body over it
        v[I['hip%d' % o]] = plant
        v[I['knee%d' % o]] = 22 + plant
        v[I['ank%d' % o]] = -(plant - (22 + plant)) * 0.9
        # Arms out for balance: the opposite arm forward and wide
        v[I['sh%d' % o]] = 35.0 * strike
        v[I['sha%d' % o]] = 25 + 45 * strike
        v[I['el%d' % o]] = 35.0
        v[I['sh%d' % k]] = -30.0 * strike
        v[I['sha%d' % k]] = 20 + 25 * strike
        v[I['el%d' % k]] = 25.0
        # Hips open on the back swing and drive through; lean back for lofted balls
        v[I['pel_h']] = sk * (-18 * _smooth(f / 0.36) * (f < 0.42) + 22 * _smooth((f - 0.42) / 0.2) * (f >= 0.42))
        v[I['twist']] = -0.6 * v[I['pel_h']]
        lean_back = {'lob': -14, 'chip': -12, 'punt': -16}.get(anim, 6)
        v[I['lean']] = _lerp(0, lean_back, _smooth(f / 0.5))
        v[I['side']] = sk * 8 * strike
        v[I['body_r']] = -sk * 4 * strike
        v[I['body_z']] = -0.04 * strike + (0.03 * math.sin((f - 0.56) / 0.44 * math.pi) if f > 0.56 and big else 0)
        v[I['head_p']] = 22 * (1 - _smooth((f - 0.6) / 0.4)) - 0.4 * v[I['lean']]

    def _down(self, v, state, anim, state_t, state_len):
        I = _IDX
        if state == 'down':
            f = _smooth(state_t / 0.4)
        else:
            f = 1.0 - _smooth(state_t / max(0.1, state_len))
        if anim == 'slip':
            # On his back
            v[I['body_p']] = 84 * f
            v[I['body_z']] = 0.1 * f
            v[I['hip0']] = 30 * f
            v[I['hip1']] = 55 * f
            v[I['knee0']] = 40 * f
            v[I['knee1']] = 75 * f
            v[I['sh0']] = v[I['sh1']] = -30 * f
            v[I['sha0']] = v[I['sha1']] = 35 * f
            v[I['el0']] = v[I['el1']] = 30 * f
            v[I['head_p']] = 25 * f
        else:
            # Tripped: face down, arms out to break the fall
            v[I['body_p']] = -82 * f
            v[I['body_z']] = 0.12 * f
            v[I['hip0']] = -8 * f
            v[I['hip1']] = 6 * f
            v[I['knee0']] = 25 * f
            v[I['knee1']] = 50 * f
            v[I['sh0']] = v[I['sh1']] = 120 * f
            v[I['sha0']] = v[I['sha1']] = 35 * f
            v[I['el0']] = v[I['el1']] = 70 * f
            v[I['head_p']] = -40 * f
            v[I['ank0']] = v[I['ank1']] = -40 * f
        if state == 'getup':
            # Knees under him on the way up
            mid = math.sin(f * math.pi)
            v[I['knee0']] += 60 * mid
            v[I['knee1']] += 30 * mid
            v[I['hip0']] += 40 * mid

    def _dive(self, v, anim, state_t, state_len, dive_dir):
        I = _IDX
        f = state_t / max(0.05, state_len)
        g = _smooth(min(1.0, state_t / 0.24))
        dx, dy, dz = dive_dir if dive_dir else (0.0, 0.0, 1.0)
        fx, fy = math.cos(self._face), math.sin(self._face)
        side = -(dx * -fy + dy * fx)          # +1: to his right
        sd = 1 if side >= 0 else -1
        if anim == 'block':
            # Spread wide and low: arms and legs out to fill the gap
            v[I['abd0']] = v[I['abd1']] = 32 * g
            v[I['knee0']] = v[I['knee1']] = 40.0
            v[I['hip0']] = v[I['hip1']] = 28 * g
            v[I['ank0']] = v[I['ank1']] = -10.0
            v[I['sh0']] = v[I['sh1']] = 30.0
            v[I['sha0']] = v[I['sha1']] = 70 * g
            v[I['el0']] = v[I['el1']] = 15.0
            v[I['lean']] = 18.0
            v[I['body_z']] = -0.3 * g
            v[I['head_p']] = -15.0
            return
        height = dz if dz else 0.8
        high = anim == 'high' or height > 1.4
        low = anim == 'low' or height < 0.6
        roll = (68 if high else (86 if low else 80)) * g
        v[I['body_r']] = sd * roll
        # Push off: up and out, then down onto the grass
        v[I['body_z']] = (0.22 if high else 0.12) * math.sin(min(1.0, f * 1.6) * math.pi) - 0.04 * g
        # Arms stretch overhead towards the ball, the top arm crossing over
        near = 1 if sd > 0 else 0              # index of the arm on the diving side
        far = 1 - near
        reach = 165 if not low else 140
        v[I['sha%d' % near]] = reach * g
        v[I['sha%d' % far]] = (reach - 20) * g
        v[I['sh%d' % near]] = 15 * g
        v[I['sh%d' % far]] = 30 * g
        v[I['el0']] = v[I['el1']] = 8.0
        v[I['wr0']] = v[I['wr1']] = -15.0
        # Legs: the take-off leg drives, the other trails
        v[I['hip%d' % near]] = 25 * g
        v[I['knee%d' % near]] = 30 * (1 - g) + 20
        v[I['hip%d' % far]] = -10 * g
        v[I['knee%d' % far]] = 15.0
        v[I['abd%d' % far]] = 15 * g
        v[I['ank0']] = v[I['ank1']] = -30 * g
        v[I['side']] = -sd * 10 * g
        v[I['head_p']] = -8.0
        if f > 0.7:
            # Landed: curl round the ball
            c = _smooth((f - 0.7) / 0.3)
            v[I['knee0']] += 40 * c
            v[I['knee1']] += 40 * c
            v[I['hip0']] += 35 * c
            v[I['hip1']] += 35 * c
            v[I['sh0']] += 30 * c
            v[I['sh1']] += 30 * c
            v[I['el0']] += 70 * c
            v[I['el1']] += 70 * c
            v[I['sha0']] *= 1 - 0.75 * c
            v[I['sha1']] *= 1 - 0.75 * c

    def _apply(self, v):
        I = _IDX
        self.body.set_hpr(0.0, v[I['body_p']], v[I['body_r']])
        self.body.set_z(v[I['body_z']])
        self.pelvis.set_hpr(v[I['pel_h']], 0.0, v[I['pel_r']])
        lean, side, tw = v[I['lean']], v[I['side']], v[I['twist']]
        self.spine.set_hpr(tw * 0.45 - v[I['pel_h']] * 0.5, -lean * 0.55, side * 0.5)
        self.chest.set_hpr(tw * 0.55, -lean * 0.45, side * 0.5)
        hp = v[I['head_p']]
        self.neck.set_hpr(v[I['head_h']] * 0.4, -hp * 0.5 + lean * 0.35, -side * 0.4)
        self.head.set_hpr(v[I['head_h']] * 0.6, -hp * 0.5 + lean * 0.3, -side * 0.3)
        for i, s in ((0, -1), (1, 1)):
            sh, sha = v[I['sh%d' % i]], v[I['sha%d' % i]]
            # The collarbone lifts as the arm goes up
            up = max(0.0, min(1.0, (max(sh, sha) - 60) / 100))
            self.clavs[i].set_hpr(0.0, 0.0, s * (12 * up + v[I['shrug']]))
            self.shoulders[i].set_hpr(0.0, sh, -s * sha)
            self.elbows[i].set_hpr(-s * 8.0, v[I['el%d' % i]], 0.0)
            self.wrists[i].set_hpr(0.0, v[I['wr%d' % i]], 0.0)
            self.hipj[i].set_hpr(-s * v[I['rot%d' % i]], v[I['hip%d' % i]], -s * v[I['abd%d' % i]])
            self.knees[i].set_p(-v[I['knee%d' % i]])
            self.ankles[i].set_p(v[I['ank%d' % i]])
            self.toes[i].set_p(v[I['toe%d' % i]])


class Ball:
    """The ball. Its spin is integrated frame to frame (rolling along the ground,
    spinning on its own axis in the air), so it never snaps round when its
    direction changes."""

    def __init__(self, parent, quality='high'):
        m = G.sphere(0.11, 28 if quality == 'high' else 14, 16 if quality == 'high' else 10)
        self.node = m.node()
        self.node.reparent_to(parent)
        S.material(self.node, 'ball')
        self.node.set_texture(T.ball())
        self.q = Quat()
        self._last = None
        self._step = (Vec3(1, 0, 0), 0.0)

    def pose(self, pos, axis, angle, spin=None, dt=1 / 30.0):
        self.node.set_pos(*pos)
        last = self._last
        self._last = tuple(pos)
        if last is None or math.dist(last, pos) > 3.0:
            self.q.set_from_axis_angle(angle, Vec3(*axis))
            self.node.set_quat(self.q)
            return
        dx, dy = pos[0] - last[0], pos[1] - last[1]
        d = math.hypot(dx, dy)
        if pos[2] < 0.15 and d > 1e-5:
            # Rolling: turn about the horizontal axis across the direction of travel
            self._step = (Vec3(-dy / d, dx / d, 0.0), math.degrees(d / 0.11))
        elif spin is not None and any(abs(w) > 0.5 for w in spin):
            w = Vec3(*spin)
            self._step = (w.normalized(), math.degrees(w.length() * dt))
        else:
            self._step = (self._step[0], self._step[1] * 0.995)
        ax, ang = self._step
        if ang > 1e-4:
            dq = Quat()
            dq.set_from_axis_angle(ang, ax)
            self.q = self.q * dq
            self.q.normalize()
        self.node.set_quat(self.q)
