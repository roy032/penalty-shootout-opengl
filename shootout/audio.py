"""Procedural sound effects through pygame.mixer.

Every sound is synthesised at start-up, so the game ships with no audio
files. If pygame is missing or there is no audio device the game runs
silently.
"""

import math
import os
import random
from array import array

RATE = 22050


def _clip(v):
    return max(-32767, min(32767, int(v)))


def _noise(n, rng, smooth=0.0):
    out = []
    prev = 0.0
    for _ in range(n):
        prev = prev * smooth + rng.uniform(-1.0, 1.0) * (1.0 - smooth)
        out.append(prev)
    return out


def _to_sound(mixer, samples, volume):
    data = array('h', (_clip(s * 32767 * volume) for s in samples))
    return mixer.Sound(buffer=data.tobytes())


def _whistle(rng):
    n = int(RATE * 0.75)
    out = []
    for i in range(n):
        t = i / RATE
        env = min(1.0, t / 0.02) * min(1.0, (0.75 - t) / 0.08)
        trill = 0.6 + 0.4 * math.sin(2 * math.pi * 32 * t)   # the pea in the whistle
        out.append(env * trill * (math.sin(2 * math.pi * 2900 * t) + 0.3 * math.sin(2 * math.pi * 5800 * t)))
    return out


def _kick(rng):
    n = int(RATE * 0.18)
    out = []
    for i in range(n):
        t = i / RATE
        thump = math.sin(2 * math.pi * (140 - 300 * t) * t) * math.exp(-t * 28)
        click = rng.uniform(-1, 1) * math.exp(-t * 180) * 0.6
        out.append(thump + click)
    return out


def _clang(rng):
    n = int(RATE * 1.2)
    partials = ((523, 1.0, 4.0), (1347, 0.6, 6.0), (2211, 0.4, 7.5), (3460, 0.25, 9.0))
    out = []
    for i in range(n):
        t = i / RATE
        v = sum(a * math.sin(2 * math.pi * f * t) * math.exp(-t * d) for f, a, d in partials)
        out.append(v * 0.45 + rng.uniform(-1, 1) * math.exp(-t * 90) * 0.3)
    return out


def _crowd(rng, seconds, swell, smooth=0.86):
    n = int(RATE * seconds)
    base = _noise(n, rng, smooth)
    out = []
    for i, v in enumerate(base):
        t = i / RATE
        out.append(v * swell(t, seconds) * 3.0)
    return out


def _heartbeat(rng):
    n = int(RATE * 0.9)
    out = []
    for i in range(n):
        t = i / RATE
        v = 0.0
        for start, amp in ((0.0, 1.0), (0.22, 0.7)):
            dt = t - start
            if dt >= 0:
                v += amp * math.sin(2 * math.pi * 55 * dt) * math.exp(-dt * 22)
        out.append(v)
    return out


class Audio:
    def __init__(self):
        self.enabled = False
        self.sounds = {}
        self.channels = {}
        self.muted = False
        try:
            os.environ.setdefault('PYGAME_HIDE_SUPPORT_PROMPT', '1')
            import pygame
            pygame.mixer.pre_init(RATE, -16, 1, 512)
            pygame.mixer.init()
            mixer = pygame.mixer
        except Exception:
            return
        rng = random.Random(3)

        def loop_swell(t, total):
            # Fade the ends so the loop has no click
            edge = min(1.0, t / 0.3, (total - t) / 0.3)
            return (0.55 + 0.15 * math.sin(t * 1.7) + 0.1 * math.sin(t * 4.3)) * edge

        def roar_swell(t, total):
            return min(1.0, t / 0.15) * math.exp(-max(0.0, t - 0.6) * 1.1)

        def gasp_swell(t, total):
            return math.sin(math.pi * min(1.0, t / total)) ** 2

        try:
            self.sounds = {
                'whistle': _to_sound(mixer, _whistle(rng), 0.35),
                'kick': _to_sound(mixer, _kick(rng), 0.9),
                'post': _to_sound(mixer, _clang(rng), 0.6),
                'ambient': _to_sound(mixer, _crowd(rng, 4.0, loop_swell), 0.22),
                'roar': _to_sound(mixer, _crowd(rng, 3.2, roar_swell, 0.8), 0.6),
                'gasp': _to_sound(mixer, _crowd(rng, 1.4, gasp_swell, 0.93), 0.55),
                'heartbeat': _to_sound(mixer, _heartbeat(rng), 0.8),
            }
        except Exception:
            return
        self.enabled = True

    def play(self, name):
        if not self.enabled or self.muted:
            return
        snd = self.sounds.get(name)
        if snd:
            snd.play()

    def loop(self, name, on):
        if not self.enabled:
            return
        playing = self.channels.get(name)
        if on and not self.muted and playing is None:
            self.channels[name] = self.sounds[name].play(loops=-1)
        elif (not on or self.muted) and playing is not None:
            self.sounds[name].stop()
            self.channels.pop(name, None)

    def toggle_mute(self):
        self.muted = not self.muted
        if self.muted:
            for name in list(self.channels):
                self.loop(name, False)
        return self.muted
