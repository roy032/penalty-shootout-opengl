"""Full-time highlights, cut from a saved replay.

find() re-simulates a recorded match with no window (a few hundred ticks a
millisecond is plenty) and returns the windows worth watching: every goal with
its build-up, plus the best saves, shots off the woodwork and penalty kicks.
The app then plays the replay and skips straight between the windows."""

from . import inputlog

BEFORE = {'goal': 300, 'woodwork': 150, 'save': 150, 'pen_result': 120}   # ticks of build-up
AFTER = {'goal': 120, 'woodwork': 60, 'save': 60, 'pen_result': 60}
MAX_EXTRAS = 4          # saves and woodwork beyond the goals


def find(log):
    """[(start_tick, end_tick, kind)] in order, merged where they overlap."""
    m = inputlog.make_match(log)
    r = inputlog.Reader(log)
    goals, extras = [], []
    while not r.done:
        for e in m.step(r.next()):
            k = e['type']
            t = m.ticks
            if k == 'goal' or k == 'pen_result':
                goals.append((t, k))
            elif k == 'woodwork':
                extras.append((2.0, t, k))
            elif k == 'save' and e.get('speed', 0) > 15.0:
                extras.append((e['speed'] / 10.0, t, k))
    extras.sort(reverse=True)
    picked = goals + [(t, k) for _, t, k in extras[:MAX_EXTRAS]]
    picked.sort()
    out = []
    for t, k in picked:
        start, end = max(1, t - BEFORE[k]), min(log['ticks'], t + AFTER[k])
        if out and start <= out[-1][1]:
            # Overlapping: one longer clip, named after the bigger moment
            prev = out[-1]
            kind = 'goal' if 'goal' in (prev[2], k) else prev[2]
            out[-1] = (prev[0], max(prev[1], end), kind)
        else:
            out.append((start, end, k))
    return out
