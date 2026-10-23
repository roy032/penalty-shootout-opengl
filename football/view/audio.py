"""Sound: every effect (kicks, whistles, post clangs, crowd, goal horn...) is
synthesised once into small 16-bit mono WAVs in a cache folder, then played
through Panda3D's default sfx manager. Uses numpy when it is installed and
plain Python (array + wave) otherwise. Any failure, such as no audio device or
an unwritable cache, leaves the game silent instead of raising."""

import math
import os
import random
import sys
import time
import wave
from array import array

try:
    import numpy as np
except ImportError:
    np = None

SR = 22050
VERSION = 'v1'          # bump when any recipe changes so cached files are rebuilt
TAU = 2.0 * math.pi


# ======================================================================= DSP
def _biquad(kind, f, q=0.7071):
    """RBJ cookbook coefficients ([b0, b1, b2], [1, a1, a2])."""
    w = TAU * min(f, SR * 0.45) / SR
    c, al = math.cos(w), math.sin(w) / (2.0 * q)
    if kind == 'lp':
        b = [(1 - c) / 2, 1 - c, (1 - c) / 2]
    elif kind == 'hp':
        b = [(1 + c) / 2, -(1 + c), (1 + c) / 2]
    else:                               # band-pass, 0 dB at the centre
        b = [al, 0.0, -al]
    a0 = 1.0 + al
    return [v / a0 for v in b], [1.0, -2.0 * c / a0, (1.0 - al) / a0]


class _L(list):
    """A list of samples with numpy-style elementwise arithmetic, so the same
    recipes run on either backend."""
    __slots__ = ()

    def __add__(s, o):
        if isinstance(o, list):
            return _L([a + b for a, b in zip(s, o)])
        return _L([a + o for a in s])

    def __sub__(s, o):
        if isinstance(o, list):
            return _L([a - b for a, b in zip(s, o)])
        return _L([a - o for a in s])

    def __rsub__(s, o):
        return _L([o - a for a in s])

    def __mul__(s, o):
        if isinstance(o, list):
            return _L([a * b for a, b in zip(s, o)])
        return _L([a * o for a in s])

    def __truediv__(s, o):
        return _L([a / o for a in s])

    def __neg__(s):
        return _L([-a for a in s])

    __radd__ = __iadd__ = __add__
    __rmul__ = __imul__ = __mul__
    __isub__ = __sub__


class _Base:
    """Shared building blocks; subclasses supply the per-sample primitives."""

    def __init__(self, seed):
        self.r = random.Random(seed)

    @staticmethod
    def n(secs):
        return int(round(secs * SR))

    def lp(self, x, f, q=0.7071):
        return self._iir(x, [_biquad('lp', f, q)])

    def hp(self, x, f, q=0.7071):
        return self._iir(x, [_biquad('hp', f, q)])

    def bp(self, x, f, q=1.0):
        return self._iir(x, [_biquad('bp', f, q)])

    def band(self, n, f, q=1.0):
        """Band of noise around f, scaled to roughly unit RMS."""
        bw = min(1.0, 1.57 * f / q / (SR / 2))
        return self.bp(self.noise(n), f, q) * (1.0 / (0.577 * math.sqrt(bw)))

    def lpn(self, n, f):
        """Low-passed noise, roughly unit RMS."""
        return self.lp(self.noise(n), f) * (1.0 / (0.577 * math.sqrt(min(1.0, 1.1 * f / (SR / 2)))))

    def reverb(self, x, wet, rt=1.2, size=1.0):
        """Small Schroeder reverb (four combs, two all-passes) for a sense of stadium."""
        acc = None
        for ms in (29.7, 37.1, 41.1, 43.7):
            d = max(1, int(ms * size * SR / 1000.0))
            c = self._comb(x, d, 10.0 ** (-3.0 * d / (rt * SR)))
            acc = c if acc is None else acc + c
        for ms in (5.0, 1.7):
            acc = self._allpass(acc, int(ms * SR / 1000.0), 0.7)
        return x + self.lp(acc, 3800) * (wet * 0.25)

    def voices(self, n, count, lo, hi, glide=None, vib=0.012):
        """A crowd of sawtooth 'singers' with their own pitch, vibrato and drift."""
        out = self.zeros(n)
        for _ in range(count):
            f0 = self.r.uniform(lo, hi)
            amp = self.slow(n, 0.7) * 0.6 + 0.4
            out = out + self.voice(n, f0, self.r.uniform(4.0, 6.5), vib, glide, self.r.random()) * amp
        return out

    def pcm(self, x, peak=0.89, rms=None, fade=0.004):
        """Scale (never above `peak`), fade the tail out and return 16-bit bytes."""
        p = self.peak(x) or 1.0
        g = peak / p
        if rms:
            g = min(g, rms / (self.rms(x) or 1.0))
        return self._bytes(x, g * 32767.0, self.n(fade) if fade else 0)


class _Py(_Base):
    """Plain Python backend: _L lists and per-sample loops."""

    def t(self, n):
        return _L([i / SR for i in range(n)])

    def zeros(self, n):
        return _L([0.0] * n)

    def noise(self, n):
        u = self.r.uniform
        return _L([u(-1.0, 1.0) for _ in range(n)])

    def sin(self, x):
        s = math.sin
        return _L([s(v) for v in x])

    def exp(self, x):
        e = math.exp
        return _L([e(v) for v in x])

    def osc(self, f, n, shape='sin', ph=0.0):
        out = [0.0] * n
        p = ph % 1.0
        fixed = not isinstance(f, list)
        inc = f / SR if fixed else 0.0
        s = math.sin
        for i in range(n):
            out[i] = s(TAU * p) if shape == 'sin' else 2.0 * p - 1.0
            p += inc if fixed else f[i] / SR
            if p >= 1.0:
                p -= int(p)
        return _L(out)

    def voice(self, n, f0, vr, vib, glide, ph):
        out = [0.0] * n
        p, s = ph, math.sin
        vp, vi = self.r.random() * TAU, TAU * vr / SR
        for i in range(n):
            f = f0 * (1.0 + vib * s(vp + vi * i))
            if glide is not None:
                f *= glide[i]
            out[i] = 2.0 * p - 1.0
            p += f / SR
            if p >= 1.0:
                p -= 1.0
        return _L(out)

    def env(self, n, a, tau, hold=0.0):
        na, nh = max(1, int(a * SR)), int(hold * SR)
        k = math.exp(-1.0 / (tau * SR))
        out = [math.sin(0.5 * math.pi * i / na) ** 2 for i in range(min(n, na))]
        out += [1.0] * max(0, min(nh, n - len(out)))
        v = 1.0
        for _ in range(n - len(out)):
            out.append(v)
            v *= k
        return _L(out)

    def curve(self, n, pts):
        out = []
        for i in range(n):
            t = i / SR
            while len(pts) > 2 and t > pts[1][0]:
                pts = pts[1:]
            (t0, v0), (t1, v1) = pts[0], pts[1]
            u = min(1.0, max(0.0, (t - t0) / (t1 - t0))) if t1 > t0 else 1.0
            out.append(v0 + (v1 - v0) * u)
        return _L(out)

    def slow(self, n, rate):
        """Smooth random wander in 0..1, about `rate` changes per second."""
        step = SR / rate
        pts = [self.r.random() for _ in range(int(n / step) + 3)]
        out = [0.0] * n
        for i in range(n):
            x = i / step
            j = int(x)
            u = x - j
            u = u * u * (3 - 2 * u)
            out[i] = pts[j] + (pts[j + 1] - pts[j]) * u
        return _L(out)

    def _iir(self, x, secs):
        for (b0, b1, b2), (_, a1, a2) in secs:
            y = [0.0] * len(x)
            z1 = z2 = 0.0
            for i, v in enumerate(x):
                o = b0 * v + z1
                z1 = b1 * v - a1 * o + z2
                z2 = b2 * v - a2 * o
                y[i] = o
            x = y
        return _L(x)

    def _comb(self, x, d, g):
        y = list(x)
        for i in range(d, len(y)):
            y[i] += g * y[i - d]
        return _L(y)

    def _allpass(self, x, d, g):
        y = [0.0] * len(x)
        for i, v in enumerate(x):
            if i >= d:
                y[i] = -g * v + x[i - d] + g * y[i - d]
            else:
                y[i] = -g * v
        return _L(y)

    def place(self, dst, src, at, g=1.0):
        for i in range(max(0, -at), min(len(src), len(dst) - at)):
            dst[at + i] += g * src[i]
        return dst

    def loop(self, x, n, fade):
        """Crossfade the overhang onto the start so the first n samples loop seamlessly."""
        out = list(x[:n])
        for i in range(fade):
            u = i / fade
            out[i] = x[i] * math.sqrt(u) + x[n + i] * math.sqrt(1.0 - u)
        return _L(out)

    def rms(self, x):
        return math.sqrt(sum(v * v for v in x) / max(1, len(x)))

    def peak(self, x):
        return max(abs(v) for v in x) if x else 0.0

    def _bytes(self, x, g, fade):
        n = len(x)
        a = array('h', [max(-32767, min(32767, int(round(v * g)))) for v in x])
        for i in range(min(fade, n)):
            a[n - 1 - i] = int(a[n - 1 - i] * i / fade)
        if sys.byteorder == 'big':
            a.byteswap()
        return a.tobytes()


class _Np(_Base):
    """numpy backend: filters run in the frequency domain with enough padding
    for the IIR tail, so results match the per-sample loops."""

    def __init__(self, seed):
        super().__init__(seed)
        self.g = np.random.default_rng(seed)

    def t(self, n):
        return np.arange(n) / SR

    def zeros(self, n):
        return np.zeros(n)

    def noise(self, n):
        return self.g.uniform(-1.0, 1.0, n)

    def sin(self, x):
        return np.sin(x)

    def exp(self, x):
        return np.exp(x)

    def osc(self, f, n, shape='sin', ph=0.0):
        if np.isscalar(f):
            p = np.arange(n) * (f / SR) + ph
        else:
            p = np.concatenate(([0.0], np.cumsum(f[:-1]) / SR)) + ph
        return np.sin(TAU * p) if shape == 'sin' else 2.0 * (p % 1.0) - 1.0

    def voice(self, n, f0, vr, vib, glide, ph):
        f = f0 * (1.0 + vib * np.sin(self.r.random() * TAU + TAU * vr / SR * np.arange(n)))
        if glide is not None:
            f = f * glide
        return self.osc(f, n, 'saw', ph)

    def env(self, n, a, tau, hold=0.0):
        t = np.arange(n) / SR
        return np.where(t < a, np.sin(0.5 * np.pi * t / max(a, 1e-9)) ** 2,
                        np.where(t < a + hold, 1.0, np.exp(-(t - a - hold) / tau)))

    def curve(self, n, pts):
        return np.interp(np.arange(n) / SR, [p[0] for p in pts], [p[1] for p in pts])

    def slow(self, n, rate):
        step = SR / rate
        pts = np.array([self.r.random() for _ in range(int(n / step) + 3)])
        x = np.arange(n) / step
        j = x.astype(int)
        u = x - j
        u = u * u * (3 - 2 * u)
        return pts[j] + (pts[j + 1] - pts[j]) * u

    def _iir(self, x, secs):
        n = len(x)
        pad = 0
        for _, (_, a1, a2) in secs:
            r = max(abs(np.roots([1.0, a1, a2]))) if a2 else abs(a1)
            pad += int(math.log(1e-5) / math.log(min(r, 0.99999))) + 1 if r > 0 else 1
        m = 1 << (n + min(pad, 4 * SR)).bit_length()
        X = np.fft.rfft(x, m)
        zi = np.exp(-2j * np.pi * np.arange(len(X)) / m)
        for (b0, b1, b2), (_, a1, a2) in secs:
            X = X * (b0 + zi * (b1 + zi * b2)) / (1.0 + zi * (a1 + zi * a2))
        return np.fft.irfft(X, m)[:n]

    def _comb(self, x, d, g):
        y = np.array(x, dtype=float)
        n = len(y)
        for s in range(d, n, d):
            e = min(s + d, n)
            y[s:e] += g * y[s - d:e - d]
        return y

    def _allpass(self, x, d, g):
        y = -g * x
        y[d:] += x[:-d]
        n = len(y)
        for s in range(d, n, d):
            e = min(s + d, n)
            y[s:e] += g * y[s - d:e - d]
        return y

    def place(self, dst, src, at, g=1.0):
        i0, i1 = max(0, -at), min(len(src), len(dst) - at)
        if i1 > i0:
            dst[at + i0:at + i1] += g * np.asarray(src[i0:i1])
        return dst

    def loop(self, x, n, fade):
        out = np.array(x[:n], dtype=float)
        u = np.arange(fade) / fade
        out[:fade] = x[:fade] * np.sqrt(u) + x[n:n + fade] * np.sqrt(1.0 - u)
        return out

    def rms(self, x):
        return float(np.sqrt(np.mean(np.square(x))))

    def peak(self, x):
        return float(np.max(np.abs(x))) if len(x) else 0.0

    def _bytes(self, x, g, fade):
        y = np.clip(np.round(np.asarray(x) * g), -32767, 32767)
        if fade:
            f = min(fade, len(y))
            y[len(y) - f:] *= np.arange(f, 0, -1) / f - 1.0 / f
        return y.astype('<i2').tobytes()


# =================================================================== recipes
def _thud(d, n, f_lo, f_hi, drop, tau):
    """Pitched-down sine thump: the body of a kick, header or bump."""
    t = d.t(n)
    f = f_lo + (f_hi - f_lo) * d.exp(t * (-1.0 / drop))
    return d.osc(f, n) * d.env(n, 0.0015, tau)


def _kick(d, pitch):
    n = d.n(0.36)
    body = _thud(d, n, 58 * pitch, 170 * pitch, 0.022, 0.075)
    slap = d.band(n, 1100 * pitch, 1.3) * d.env(n, 0.0004, 0.011)
    click = d.hp(d.noise(n), 3500) * d.env(n, 0.0001, 0.0025)
    return d.reverb(body + slap * 0.35 + click * 0.5, 0.08, 0.7)


def _touch(d):
    n = d.n(0.2)
    body = _thud(d, n, 68, 130, 0.018, 0.04)
    slap = d.band(n, 700, 1.0) * d.env(n, 0.0005, 0.008)
    return body + slap * 0.25


def _pass(d):
    n = d.n(0.3)
    body = _thud(d, n, 55, 150, 0.02, 0.055)
    slap = d.band(n, 1250, 1.3) * d.env(n, 0.0004, 0.009)
    scuff = d.band(n, 2600, 0.8) * d.env(n, 0.002, 0.03)
    return d.reverb(body + slap * 0.3 + scuff * 0.12, 0.06, 0.6)


def _header(d):
    n = d.n(0.32)
    body = _thud(d, n, 60, 150, 0.03, 0.06)
    pop = d.band(n, 420, 4.0) * d.env(n, 0.0008, 0.025)
    ring = d.osc(260.0, n) * d.env(n, 0.001, 0.03)
    return d.reverb(body * 0.8 + pop * 0.35 + ring * 0.25, 0.08, 0.7)


def _clang(d, f0):
    """Struck metal tube: inharmonic free-bar partials, each a slightly detuned
    pair so it beats, high ones dying first."""
    n = d.n(1.9)
    x = d.zeros(n)
    for ratio, amp, tau in ((1.0, 1.0, 1.3), (2.756, 0.75, 0.85), (5.404, 0.45, 0.45),
                            (8.933, 0.3, 0.25), (13.34, 0.18, 0.14)):
        f = f0 * ratio
        dt = 1.0 + d.r.uniform(0.0008, 0.002)
        tone = d.osc(f, n, ph=d.r.random()) + d.osc(f * dt, n, ph=d.r.random()) * 0.7
        x = x + tone * d.env(n, 0.0005, tau) * amp
    strike = d.hp(d.noise(n), 2500) * d.env(n, 0.0002, 0.004)
    ball = _thud(d, n, 55, 160, 0.02, 0.06)
    return d.reverb(x * 0.35 + strike * 0.5 + ball * 0.6, 0.18, 1.6)


def _net(d):
    n = d.n(0.85)
    t = d.t(n)
    swish = d.band(n, 3600, 0.7) * d.env(n, 0.015, 0.16)
    ripple = 1.0 - (0.5 + 0.5 * d.sin(t * (TAU * 22.0))) * d.exp(t * (-1 / 0.3)) * 0.6
    rustle = d.band(n, 1200, 0.9) * d.env(n, 0.03, 0.22)
    whump = d.lpn(n, 220) * d.env(n, 0.01, 0.1)
    return d.reverb(swish * ripple * 0.35 + rustle * 0.2 + whump * 0.5, 0.1, 0.8)


def _whistle(d, segs, f0=3050.0):
    """Pea whistle: a bright tone with the pea's rattle as fast FM/AM, plus breath."""
    total = segs[-1][0] + segs[-1][1] + 0.4
    n = d.n(total)
    t = d.t(n)
    gate, scoop = d.zeros(n), d.zeros(n)
    for start, dur in segs:
        m = d.n(dur)
        gate = d.place(gate, d.curve(m, [(0, 0), (0.012, 1), (dur - 0.05, 1), (dur, 0)]), d.n(start))
        scoop = d.place(scoop, d.curve(m, [(0, -0.07), (0.045, 0), (dur, 0)]), d.n(start))
    pea = 31.0
    f = (1.0 + scoop + d.sin(t * (TAU * pea)) * 0.02) * f0
    tone = d.osc(f, n) + d.osc(f * 2.0, n) * 0.18 + d.osc(f * 3.0, n) * 0.05
    am = 1.0 - (0.5 + 0.5 * d.sin(t * (TAU * pea) + 1.0)) * 0.35
    breath = d.band(n, f0, 5.0) * 0.12 + d.hp(d.noise(n), 5000) * 0.04
    return d.reverb((tone * am + breath) * gate, 0.25, 1.4)


def _shout(d, dur, f0):
    """One distant fan's 'hey!'."""
    n = d.n(dur)
    f = d.curve(n, [(0, f0 * 0.9), (dur * 0.3, f0 * 1.08), (dur, f0 * 0.85)])
    v = d.osc(f, n, 'saw')
    v = d.bp(v, 700, 2.0) + d.bp(v, 1700, 3.0) * 0.5
    return v * d.curve(n, [(0, 0), (0.04, 1), (dur * 0.6, 0.7), (dur, 0)])


def _crowd(d, secs, hot):
    """Ambience loop: a filtered noise wash plus bands of murmur, each with its
    own syllable-rate swell. The hot layer adds singing, claps and shouts."""
    fade = d.n(0.5)
    n = d.n(secs) + fade
    x = d.lpn(n, 650) * 0.5 + d.band(n, 1500, 0.7) * (0.25 if hot else 0.15)
    bands = (330, 480, 700, 980, 1350, 1900, 2600) if hot else (330, 480, 700, 980, 1350, 1900)
    for f in bands:
        am = d.slow(n, d.r.uniform(2.5, 5.5))
        x = x + d.band(n, f, 2.5) * (am * am + 0.12) * (0.32 * (700.0 / f) ** 0.4)
    x = x * (d.slow(n, 0.3) * 0.25 + 0.75)
    for _ in range(4 if hot else 3):
        dur = d.r.uniform(0.25, 0.5)
        d.place(x, _shout(d, dur, d.r.uniform(220, 380)), d.r.randrange(0, n - d.n(dur)),
                d.r.uniform(0.04, 0.09) * (2.0 if hot else 1.0))
    if hot:
        # Singing that pulses with a chant; 1.6 Hz fits the loop length exactly
        t = d.t(n)
        v = d.voices(n, 8, 200, 290)
        v = d.bp(v, 720, 2.0) + d.bp(v, 1150, 3.0) * 0.5
        v = v * (0.35 / (d.rms(v) or 1.0))
        x = x + v * (0.6 + 0.4 * d.sin(t * (TAU * 1.6)))
        _claps(d, x, int(secs * 25), lambda u: 1.0, 0.25)
    return d.loop(d.reverb(x, 0.3, 1.8), n - fade, fade)


def _claps(d, x, count, density, gain):
    """Scatter hand claps (short band-passed noise bursts) into x."""
    k = d.n(0.04)
    kern = [d.bp(d.noise(k), d.r.uniform(900, 2300), 1.4) * d.env(k, 0.0003, d.r.uniform(0.005, 0.011))
            for _ in range(8)]
    kern = [c * (1.0 / (d.peak(c) or 1.0)) for c in kern]
    n = len(x)
    placed = 0
    while placed < count:
        at = d.r.randrange(0, n - k)
        if d.r.random() < density(at / SR):
            d.place(x, kern[d.r.randrange(8)], at, gain * d.r.uniform(0.4, 1.0))
            placed += 1
    return x


def _roar(d):
    n = d.n(4.8)
    t = d.t(n)
    lev = d.curve(n, [(0, 0.1), (0.25, 0.55), (0.7, 1.0), (1.6, 0.9), (3.0, 0.55), (4.8, 0.0)])
    bright = d.curve(n, [(0, 0.3), (0.6, 1.0), (2.5, 0.6), (4.8, 0.3)])
    wash = d.band(n, 850, 0.7) * 0.5 + d.band(n, 2300, 1.2) * bright * 0.3 + d.lpn(n, 350) * 0.35
    glide = d.curve(n, [(0, 0.92), (0.6, 1.05), (4.8, 1.0)])
    v = d.voices(n, 10, 190, 330, glide)
    v = d.bp(v, 760, 2.0) + d.bp(v, 1250, 3.0) * 0.6
    v = v * (0.55 / (d.rms(v) or 1.0))
    # The yell slowly settles into a chant
    chant = 1.0 - d.curve(n, [(0, 0), (1.6, 0), (3.0, 0.55), (4.8, 0.6)]) * (0.5 + 0.5 * d.sin(t * (TAU * 1.9)))
    return d.reverb((wash + v * chant) * lev, 0.3, 1.8)


def _ooh(d):
    n = d.n(2.3)
    lev = d.curve(n, [(0, 0), (0.28, 1.0), (0.6, 0.85), (1.4, 0.45), (2.3, 0)])
    glide = d.curve(n, [(0, 1.0), (0.25, 1.04), (1.6, 0.72), (2.3, 0.68)])
    v = d.voices(n, 12, 210, 330, glide)
    v = d.bp(v, 320, 1.8) + d.bp(v, 860, 3.0) * 0.35
    v = v * (0.6 / (d.rms(v) or 1.0))
    breath = d.band(n, 450, 1.0) * 0.25
    return d.reverb((v + breath) * lev, 0.3, 1.8)


def _applause(d):
    n = d.n(3.3)
    x = d.zeros(n)
    dens = lambda s: min(1.0, s / 0.15) * max(0.0, 1.0 - max(0.0, s - 0.6) / 2.6)
    _claps(d, x, 300, dens, 1.0)
    lev = d.curve(n, [(0, 0), (0.15, 1), (0.8, 0.7), (3.3, 0)])
    cheer = d.band(n, 1000, 0.6) * lev * 0.12
    return d.reverb(x + cheer, 0.3, 1.5)


def _horn(d):
    """Stadium air horn chord over a big bass drum."""
    n = d.n(2.8)
    scoop = d.curve(n, [(0, 0.95), (0.08, 1.0), (2.8, 1.0)])
    h = d.zeros(n)
    for f in (138.6, 174.6, 207.7):
        for det in (0.997, 1.003):
            h = h + d.osc(scoop * (f * det), n, 'saw', d.r.random())
    h = d.lp(h, 1500, 1.2) + d.lp(h, 500) * 0.6
    h = h * d.curve(n, [(0, 0), (0.07, 1), (1.45, 0.9), (1.7, 0), (2.8, 0)])
    h = h * (0.5 / (d.rms(h) or 1.0))
    boom = _thud(d, n, 36, 70, 0.08, 0.5) + d.lpn(n, 140) * d.env(n, 0.003, 0.15) * 0.4
    return d.reverb(h + boom * 0.9, 0.35, 2.0)


def _slide(d):
    n = d.n(0.65)
    grass = d.band(n, 2600, 0.9) * 0.6 + d.band(n, 900, 1.0) * 0.4
    rough = d.slow(n, 45) * 0.5 + 0.5
    thump = d.lpn(n, 200) * d.env(n, 0.004, 0.05)
    return grass * rough * d.env(n, 0.03, 0.14, 0.18) * 0.5 + thump * 0.6


def _bump(d):
    n = d.n(0.3)
    body = _thud(d, n, 55, 100, 0.03, 0.05)
    soft = d.lpn(n, 300) * d.env(n, 0.002, 0.035)
    cloth = d.band(n, 1800, 1.0) * d.env(n, 0.001, 0.015)
    return body * 0.8 + soft * 0.5 + cloth * 0.15


def _notes(d, notes, dur):
    """Soft UI tones: sine plus a little third harmonic, one per (start, freq)."""
    n = d.n(dur)
    x = d.zeros(n)
    for start, f in notes:
        m = n - d.n(start)
        e = d.env(m, 0.003, 0.045)
        d.place(x, (d.osc(f, m) + d.osc(f * 3, m) * 0.12) * e, d.n(start))
    return x


def _card(d):
    n = d.n(1.2)
    s = d.zeros(n)
    for f in (110.0, 155.56, 233.08):
        s = s + d.osc(f, n, 'saw', d.r.random()) + d.osc(f * 1.004, n, 'saw', d.r.random())
    s = d.lp(s, 1200, 2.0) * d.env(n, 0.012, 0.32)
    s = s * (0.5 / (d.rms(s) or 1.0))
    timp = _thud(d, n, 70, 95, 0.1, 0.45) + d.band(n, 140, 1.5) * d.env(n, 0.002, 0.08) * 0.3
    return d.reverb(s + timp * 0.9, 0.3, 1.6)


# name: (recipe, voices, playback gain, options for pcm)
SOUNDS = {
    'kick0': (lambda d: _kick(d, 0.9), 2, 0.9, {}),
    'kick1': (lambda d: _kick(d, 1.0), 2, 0.9, {}),
    'kick2': (lambda d: _kick(d, 1.12), 2, 0.9, {}),
    'touch': (_touch, 3, 0.55, {}),
    'pass': (_pass, 2, 0.7, {}),
    'header': (_header, 2, 0.8, {}),
    'post': (lambda d: _clang(d, 560.0), 1, 0.8, {}),
    'bar': (lambda d: _clang(d, 470.0), 1, 0.8, {}),
    'net': (_net, 1, 0.7, {}),
    'whistle_short': (lambda d: _whistle(d, [(0.0, 0.2)]), 2, 0.6, {}),
    'whistle_long': (lambda d: _whistle(d, [(0.0, 0.95)]), 1, 0.6, {}),
    'whistle_full': (lambda d: _whistle(d, [(0.0, 0.33), (0.48, 0.33), (0.96, 1.25)]), 1, 0.6, {}),
    'crowd_calm': (lambda d: _crowd(d, 6.0, False), 1, 0.55, {'fade': 0}),
    'crowd_hot': (lambda d: _crowd(d, 5.0, True), 1, 0.6, {'fade': 0}),
    'roar': (_roar, 1, 1.0, {}),
    'ooh': (_ooh, 1, 0.8, {}),
    'applause': (_applause, 2, 0.6, {}),
    'horn': (_horn, 1, 0.75, {}),
    'slide': (_slide, 2, 0.55, {}),
    'bump': (_bump, 2, 0.7, {}),
    'ui_move': (lambda d: _notes(d, [(0.0, 1320.0)], 0.12), 2, 0.35, {}),
    'ui_confirm': (lambda d: _notes(d, [(0.0, 880.0), (0.07, 1320.0)], 0.3), 1, 0.4, {}),
    'ui_back': (lambda d: _notes(d, [(0.0, 990.0), (0.07, 660.0)], 0.3), 1, 0.4, {}),
    'card': (_card, 1, 0.7, {}),
}


def build_sounds(cache_dir, names=None):
    """Write any missing WAVs for this VERSION into cache_dir; returns {name: path}."""
    os.makedirs(cache_dir, exist_ok=True)
    backend = _Np if np is not None else _Py
    paths = {}
    order = list(SOUNDS)
    for name in names or order:
        path = os.path.join(cache_dir, 'sfx_%s_%s.wav' % (name, VERSION))
        if not (os.path.exists(path) and os.path.getsize(path) > 44):
            fn, _, _, opts = SOUNDS[name]
            d = backend(1000 + order.index(name) * 17)
            data = d.pcm(fn(d), **opts)
            tmp = path + '.tmp'
            w = wave.open(tmp, 'wb')
            try:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(SR)
                w.writeframes(data)
            finally:
                w.close()
            os.replace(tmp, path)
        paths[name] = path
    # Drop files left by older versions
    try:
        for f in os.listdir(cache_dir):
            if f.startswith('sfx_') and f.endswith('.wav') and not f.endswith('_%s.wav' % VERSION):
                os.remove(os.path.join(cache_dir, f))
    except OSError:
        pass
    return paths


# ================================================================== playback
def _clamp(v, lo=0.0, hi=1.0):
    return lo if v < lo else hi if v > hi else v


class Audio:
    """Match and menu sounds. Every public method is safe to call even when
    audio could not be set up; it then does nothing."""

    def __init__(self, base, cache_dir, volume=1.0, crowd_volume=1.0):
        self.base = base
        self.master = volume
        self.crowd = crowd_volume
        self.snd = {}           # name -> [AudioSound, ...] voices
        self.rr = {}            # name -> next voice
        self.last = {}          # dedupe key -> time last played
        self.rng = random.Random()
        self.exc = 0.0
        self.paused = False
        self.pz = 1.0           # crowd level factor while paused
        self.looping = False
        self.shot_t = -1e9
        self.shot_p = 0.0
        self.gen_time = 0.0
        self.error = None
        self.ok = False
        try:
            from panda3d.core import Filename
            t0 = time.perf_counter()
            paths = build_sounds(cache_dir)
            self.gen_time = time.perf_counter() - t0
            for name, path in paths.items():
                voices = []
                for _ in range(SOUNDS[name][1]):
                    s = base.loader.loadSfx(Filename.from_os_specific(path))
                    if s is not None:
                        voices.append(s)
                if voices:
                    self.snd[name] = voices
                    self.rr[name] = 0
            for name in ('crowd_calm', 'crowd_hot'):
                for s in self.snd.get(name, ()):
                    s.set_loop(True)
                    s.set_volume(0.0)
            self.ok = bool(self.snd)
        except Exception as e:     # no device, read-only disk, broken loader...
            self.error = e
            self.snd = {}
            self.ok = False

    # ---------------------------------------------------------- helpers
    def _play(self, name, vol=1.0, rate=1.0):
        voices = self.snd.get(name)
        if not voices:
            return
        i = self.rr[name]
        self.rr[name] = (i + 1) % len(voices)
        s = voices[i]
        s.set_volume(_clamp(vol * SOUNDS[name][2] * self.master))
        s.set_play_rate(rate)
        s.play()

    def _gap(self, key, secs):
        """True (and remember now) if `key` has not fired in the last `secs`."""
        now = time.monotonic()
        if now - self.last.get(key, -1e9) < secs:
            return False
        self.last[key] = now
        return True

    def _kick(self, vol, rate):
        self._play('kick%d' % self.rng.randrange(3), vol, rate * self.rng.uniform(0.97, 1.03))

    def _ooh(self, vol):
        if self._gap('ooh', 1.5):
            self._play('ooh', vol, self.rng.uniform(0.96, 1.04))

    # ---------------------------------------------------------- events
    def on_events(self, events, match):
        if not self.ok or not events:
            return
        for ev in events:
            try:
                self._event(ev, match)
            except Exception:
                pass

    def _event(self, ev, match):
        k = ev.get('type')
        r = self.rng.uniform
        if k == 'shot':
            p = _clamp(ev.get('power', 0.7))
            self.shot_t, self.shot_p = time.monotonic(), p
            if ev.get('header'):
                self._play('header', 0.6 + 0.4 * p, 1.05 - 0.15 * p)
            else:
                self._kick(0.55 + 0.45 * p, 1.1 - 0.25 * p)
        elif k == 'pass':
            kind = ev.get('kind')
            if kind == 'lob':
                self._kick(0.55, 1.12)
            else:
                self._play('pass', 0.75 if kind == 'through' else 0.6, r(0.94, 1.06))
        elif k == 'clear':
            self._kick(0.8, 1.0)
        elif k == 'distribute':
            if ev.get('kind') == 'throw':
                self._play('touch', 0.35, 1.2)
            else:
                self._kick(0.75, 1.0)
        elif k == 'header':
            self._play('header', 0.7, r(0.95, 1.05))
        elif k in ('control', 'intercept', 'skill'):
            if self._gap('touch', 0.06):
                self._play('touch', 0.3 if k == 'skill' else 0.45, r(0.9, 1.1))
        elif k == 'touch':
            if ev.get('chest'):
                self._play('bump', 0.3, 1.3)
            elif self._gap('touch', 0.06):
                self._play('touch', 0.6 if ev.get('heavy') else 0.3 if ev.get('soft') else 0.45, r(0.9, 1.1))
        elif k == 'bounce':
            if self._gap('bounce', 0.1):
                self._play('touch', _clamp((ev.get('speed', 8) - 5) / 20.0, 0.08, 0.5), r(0.8, 0.9))
        elif k == 'wall':
            if self._gap('wall', 0.1):
                self._play('bump', _clamp(ev.get('speed', 10) / 25.0, 0.1, 0.8), r(1.1, 1.3))
        elif k == 'tackle':
            self._play('bump', 0.75 if ev.get('kind') == 'slide' else 0.55, r(0.9, 1.1))
        elif k == 'slide':
            self._play('slide', 0.8, r(0.92, 1.08))
        elif k == 'dive':
            self._play('slide', 0.35, r(1.15, 1.3))
        elif k == 'foul':
            if self._gap('foul', 0.2):
                self._play('bump', 0.9, r(0.85, 0.95))
        elif k == 'card':
            self._play('card', 0.8)
        elif k == 'catch':
            self._play('bump', 0.5, 1.35)
        elif k == 'parry':
            self._play('touch', 0.7, 0.85)
        elif k == 'save':
            if self._gap('applause', 1.0):
                self._play('applause', 0.6 + 0.4 * _clamp(ev.get('speed', 15) / 30.0), r(0.95, 1.05))
            self._ooh(0.6 + 0.4 * self.shot_p)
        elif k == 'woodwork':
            sp = _clamp(match.ball.speed() / 25.0, 0.3, 1.0) if hasattr(match, 'ball') else 0.8
            self._play('bar' if ev.get('kind') == 'bar' else 'post', sp, r(0.97, 1.03))
            self._ooh(0.9)
        elif k == 'out':
            if ev.get('kind') == 'goalkick' and time.monotonic() - self.shot_t < 2.5:
                self._ooh(0.5 + 0.4 * self.shot_p)
        elif k == 'goal':
            self.shot_t = -1e9
            # The crowd leans towards the home side
            loud = 1.0 if ev.get('team') == 0 else 0.8
            self._play('net', 0.9)
            if self._gap('roar', 2.0):
                self._play('roar', loud)
                self._play('horn', loud * 0.9)
        elif k == 'pen_result':
            if ev.get('scored'):
                self._play('net', 0.8)
                if self._gap('roar', 1.5):
                    self._play('roar', 0.8, r(1.0, 1.06))
            else:
                self._ooh(0.9)
        elif k == 'penalty_awarded':
            if self._gap('roar', 2.0):
                self._play('roar', 0.45, 1.05)
        elif k == 'whistle':
            why = ev.get('why')
            if why == 'full':
                self.last['long'] = time.monotonic()
                self._play('whistle_full', 1.0)
            elif why == 'half':
                self.last['long'] = time.monotonic()
                self._play('whistle_long', 1.0)
            elif self._gap('whistle', 0.3):
                self._play('whistle_short', 0.9, 1.0 if why == 'foul' else 1.03)
        elif k in ('halftime', 'extratime'):
            if self._gap('long', 1.0):
                self._play('whistle_long', 1.0)
        elif k == 'fulltime':
            if self._gap('long', 1.5):
                self._play('whistle_full', 1.0)
        elif k == 'restart_taken':
            if ev.get('kind') in ('kickoff', 'penalty') and self._gap('whistle', 0.3):
                self._play('whistle_short', 0.8)

    # ---------------------------------------------------------- crowd
    def update(self, dt, excitement):
        """Keep the crowd loops running (restarting them after stop()) and let their
        level and pitch follow excitement smoothly."""
        if not self.ok:
            return
        try:
            dt = _clamp(dt, 0.0, 0.25)
            self.exc += (_clamp(excitement) - self.exc) * (1.0 - math.exp(-dt / 1.2))
            self.pz += ((0.3 if self.paused else 1.0) - self.pz) * (1.0 - math.exp(-dt / 0.3))
            if not self.looping:
                for name in ('crowd_calm', 'crowd_hot'):
                    for s in self.snd.get(name, ()):
                        s.set_loop(True)
                        s.play()
                self.looping = True
            self._apply_crowd()
        except Exception:
            pass

    def _apply_crowd(self):
        e = self.exc
        cv = self.crowd * self.master * self.pz
        for name, vol, rate in (('crowd_calm', 0.6 + 0.3 * e, 0.96 + 0.08 * e),
                                ('crowd_hot', e ** 1.5, 0.97 + 0.08 * e)):
            for s in self.snd.get(name, ()):
                s.set_volume(_clamp(cv * vol * SOUNDS[name][2]))
                s.set_play_rate(rate)

    def set_paused(self, paused):
        self.paused = bool(paused)

    # ---------------------------------------------------------- misc
    def ui(self, kind):
        if not self.ok:
            return
        try:
            self._play({'move': 'ui_move', 'confirm': 'ui_confirm', 'back': 'ui_back'}.get(kind, 'ui_move'))
        except Exception:
            pass

    def set_volume(self, master, crowd):
        self.master = _clamp(master)
        self.crowd = _clamp(crowd)
        if self.ok and self.looping:
            try:
                self._apply_crowd()
            except Exception:
                pass

    def stop(self):
        """Silence everything, loops included; the next update() starts the crowd again."""
        self.looping = False
        for voices in self.snd.values():
            for s in voices:
                try:
                    s.stop()
                except Exception:
                    pass
