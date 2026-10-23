"""Whole-match replays as a seed plus every input.

The sim is deterministic (fixed 60 Hz step, its own seeded rng), so a match is
fully described by how it was set up and what each controller pressed on each
tick. A Recorder packs that into a few kilobytes of run-length encoded JSON;
a Reader feeds it back into a fresh Match, which then plays out identically.

Stick values are rounded to 1/1000 before they reach the live match too
(quantize), so what is recorded is exactly what was played."""

import gzip
import json
import os
import time

from .match import Input, Match

VERSION = 1
BITS = {a: 1 << i for i, a in enumerate(Input.ACTIONS)}
KEEP = 20       # newest replays kept on disk


def quantize(inp):
    """The same input with the stick rounded, as recorded."""
    q = Input()
    q.move = (round(inp.move[0] * 1000) / 1000.0, round(inp.move[1] * 1000) / 1000.0)
    q.held = set(inp.held)
    q.pressed = set(inp.pressed)
    q.released = set(inp.released)
    return q


def _mask(held):
    m = 0
    for a in held:
        m |= BITS.get(a, 0)
    return m


class Recorder:
    def __init__(self, home, away, settings, humans, seed, shootout_only=False):
        self.meta = dict(version=VERSION, home=home, away=away, settings=dict(settings),
                         humans=[list(h) for h in humans], seed=seed, shootout_only=shootout_only,
                         date=time.strftime('%Y-%m-%d %H:%M'))
        self.ticks = 0
        self.tracks = {}

    def add(self, inputs):
        """One tick of {controller index: Input} (after quantize)."""
        self.ticks += 1
        for idx, inp in inputs.items():
            key = [int(round(inp.move[0] * 1000)), int(round(inp.move[1] * 1000)), _mask(inp.held)]
            tr = self.tracks.setdefault(str(idx), [])
            if tr and tr[-1][1:] == key and tr[-1][4] == self.ticks - tr[-1][0]:
                tr[-1][0] += 1
            else:
                # [count, mx, my, mask, first tick]
                tr.append([1] + key + [self.ticks])

    def to_dict(self, match=None):
        d = dict(self.meta, ticks=self.ticks, tracks=self.tracks)
        if match is not None:
            a, b = match.teams
            d['result'] = dict(score=[a.score, b.score], pens=[sum(a.pens), sum(b.pens)] if match.shootout else None,
                               names=[a.short, b.short], pitch=match.settings['pitch'])
        return d


class Reader:
    def __init__(self, log):
        self.log = log
        self.tick = 0
        self.pos = {k: 0 for k in log['tracks']}
        self.prev = {k: set() for k in log['tracks']}

    @property
    def done(self):
        return self.tick >= self.log['ticks']

    def next(self):
        """The inputs for the next tick, exactly as they were played."""
        self.tick += 1
        out = {}
        for k, tr in self.log['tracks'].items():
            i = self.pos[k]
            while i < len(tr) and tr[i][4] + tr[i][0] <= self.tick:
                i += 1
            self.pos[k] = i
            if i >= len(tr) or tr[i][4] > self.tick:
                continue
            _, mx, my, mask, _ = tr[i]
            inp = Input()
            inp.move = (mx / 1000.0, my / 1000.0)
            inp.held = {a for a, bit in BITS.items() if mask & bit}
            inp.pressed = inp.held - self.prev[k]
            inp.released = self.prev[k] - inp.held
            self.prev[k] = inp.held
            out[int(k)] = inp
        return out


def make_match(log):
    """A fresh Match set up exactly as the recorded one was."""
    m = Match(log['home'], log['away'], settings=log['settings'], humans=tuple(tuple(h) for h in log['humans']),
              seed=log['seed'])
    if log.get('shootout_only'):
        m.start_shootout()
    return m


def save(log, folder):
    """Write a replay and prune old ones. Returns the path, or None if it couldn't be saved."""
    try:
        os.makedirs(folder, exist_ok=True)
        name = time.strftime('%Y%m%d-%H%M%S') + '-%s-%s.json.gz' % (log['home'], log['away'])
        path = os.path.join(folder, name)
        with gzip.open(path, 'wt') as f:
            json.dump(log, f, separators=(',', ':'))
        for old in listing(folder)[KEEP:]:
            os.remove(old)
        return path
    except OSError:
        return None


def load(path):
    with gzip.open(path, 'rt') as f:
        log = json.load(f)
    if log.get('version') != VERSION:
        raise ValueError('replay from another version')
    return log


def listing(folder):
    """Saved replays, newest first."""
    try:
        names = [n for n in os.listdir(folder) if n.endswith('.json.gz')]
    except OSError:
        return []
    return [os.path.join(folder, n) for n in sorted(names, reverse=True)]
