"""Soak test and balance report for Ultimate Football: CPU v CPU matches with no window.

Run from the repo root:
    python tools/sim_matches.py                       # 20 cage matches, Pro, random team pairs
    python tools/sim_matches.py -n 200 --format full  # overnight-style run on the full pitch
    python tools/sim_matches.py --home legends --away cult --json out.json
    python tools/sim_matches.py --replay 1234 --home stars --away myths   # re-run one seed
    python tools/sim_matches.py --compare-styles -n 60  # every style against every other, identical squads

Prints goals, shots, passing, fouls and set pieces per match, a table of team
styles, and every stuck state found (with the seed to replay it). Exits with
status 1 if any problem was found, so it can run in CI.
"""

import argparse
import json
import os
import random
import sys
import time
from concurrent.futures import ProcessPoolExecutor

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from football.sim import roster, soak  # noqa: E402
from football.sim.styles import STYLES  # noqa: E402

FORMATS = {'cage': 5, 'fives': 5, 'sevens': 7, 'full': 11}


def _one(job):
    home, away, cfg, seed = job
    return soak.play(home, away, cfg, seed)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('-n', '--matches', type=int, default=20)
    ap.add_argument('--format', choices=sorted(FORMATS), default='cage')
    ap.add_argument('--difficulty', default='pro')
    ap.add_argument('--preset', choices=['arcade', 'authentic'], default='arcade')
    ap.add_argument('--half', type=float, default=150.0, help='seconds per half (default 150)')
    ap.add_argument('--home', help='team id (default: random each match)')
    ap.add_argument('--away', help='team id (default: random each match)')
    ap.add_argument('--seed', type=int, default=1, help='first seed')
    ap.add_argument('--replay', type=int, help='run just this seed and print everything')
    ap.add_argument('--jobs', type=int, default=os.cpu_count() or 1)
    ap.add_argument('--json', help='write every match result to this file')
    ap.add_argument('--compare-styles', action='store_true',
                    help='same club squad on both sides, each style against every other')
    a = ap.parse_args(argv)

    cfg = dict(size=FORMATS[a.format], pitch=a.format, half_seconds=a.half, difficulty=a.difficulty,
               preset=a.preset)
    teams = roster.team_ids()
    if a.replay is not None:
        r = soak.play(a.home or 'stars', a.away or 'legends', cfg, a.replay)
        print(json.dumps(r, indent=1))
        return 1 if r['problems'] else 0

    pick = random.Random(a.seed)
    jobs = []
    pairs = [(x, y) for x in sorted(STYLES) for y in sorted(STYLES) if x != y]
    for i in range(a.matches):
        if a.compare_styles:
            club = a.home or 'blues'
            jobs.append((club, club, dict(cfg, styles=pairs[i % len(pairs)]), a.seed + i))
            continue
        home = a.home or pick.choice(teams)
        away = a.away or pick.choice([t for t in teams if t != home] or teams)
        jobs.append((home, away, cfg, a.seed + i))
    t0 = time.time()
    if a.jobs > 1 and len(jobs) > 1:
        with ProcessPoolExecutor(a.jobs) as ex:
            results = list(ex.map(_one, jobs))
    else:
        results = [_one(j) for j in jobs]
    took = time.time() - t0

    s = soak.summarise(results)
    print('%d %s matches (%s, %s, %ds halves) in %.0fs' % (len(results), a.format, a.difficulty, a.preset,
                                                            a.half, took))
    print('  goals per match   %.2f   (draws %.0f%%, shootouts %.0f%%)' % (
        s['goals_per_match'], s['draws'] * 100, s['shootouts'] * 100))
    print('  shots per team    %.1f   xG %.2f' % (sum(s['shots']) / 2, sum(s['xg']) / 2))
    print('  passes per team   %.0f   completed %.0f%%' % (sum(s['passes']) / 2, sum(s['pass_pct']) / 2 * 100))
    print('  tackles per team  %.1f' % (sum(s['tackles']) / 2))
    print('  per match: fouls %.1f, cards %.1f, corners %.1f, penalties %.2f, saves %.1f, woodwork %.1f, '
          'offsides %.1f, off the walls %.1f' % (s['foul'], s['card'], s['restart_corner'], s['restart_penalty'],
                                                 s['save'], s['woodwork'], s['offside'], s['wall']))
    # How each team style actually plays
    rows = {}
    for r in results:
        for i, key in enumerate(r['styles']):
            rows.setdefault(STYLES[key]['label'], []).append(r['teams'][i])
    if rows:
        print('\n  %-22s %7s %7s %7s %7s %7s' % ('style', 'goals', 'shots', 'passes', 'poss', 'tackles'))
        for label, ts in sorted(rows.items()):
            n = len(ts)
            print('  %-22s %7.2f %7.1f %7.0f %6.0f%% %7.1f' % (
                label, sum(t['goals'] for t in ts) / n, sum(t['shots'] for t in ts) / n,
                sum(t['passes'] for t in ts) / n, sum(t['possession'] for t in ts) / n * 100,
                sum(t['tackles'] for t in ts) / n))
    probs = [p for r in results for p in r['problems']]
    print('\n  problems: %d' % len(probs))
    for p in probs:
        print('   ', p['kind'], 'seed', p['seed'], p['home'], 'v', p['away'], 'at %.0f\'' % p['minute'],
              {k: v for k, v in p.items() if k not in ('kind', 'seed', 'home', 'away', 'minute', 'time')})
    if probs:
        print('  replay one with: python tools/sim_matches.py --format %s --replay SEED --home H --away A' % a.format)
    if a.json:
        with open(a.json, 'w') as f:
            json.dump(dict(summary=s, matches=results), f, indent=1)
    return 1 if probs else 0


if __name__ == '__main__':
    sys.exit(main())
