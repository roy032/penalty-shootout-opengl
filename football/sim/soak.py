"""Headless CPU v CPU matches for balance numbers and bug hunting.

play() runs one match with no window and returns its statistics plus any
"stuck" problems found on the way: a ball that never moves, a restart nobody
takes, a player or the ball outside the ground, a score that doesn't match the
goals, or a match that never ends. Every problem carries the seed, so the
exact match can be replayed. tools/sim_matches.py runs many of these."""

import math
import statistics
import traceback

from .match import FIXED_DT, Match

STILL_LIMIT = 10.0          # seconds of open play with the ball not moving
RESTART_LIMIT = 15.0        # seconds waiting for a set piece to be taken
OUTSIDE = 4.0               # metres beyond the lines that counts as "outside the ground"


def play(home='stars', away='legends', settings=None, seed=0, max_minutes=None):
    """One CPU v CPU match. Returns a dict of numbers and a list of problems."""
    m = Match(home, away, settings=settings, humans=(), seed=seed)
    s = m.settings
    # Two halves, possible extra time and a long shootout, with plenty to spare
    limit = max_minutes * 60.0 if max_minutes else s['half_seconds'] * 2 * 3 + 400.0
    problems = []
    goals = [0, 0]
    shots = [0, 0]
    counts = {}
    still_t = 0.0
    last_ball = tuple(m.ball.pos)
    restart_t = 0.0
    seen = set()
    t = 0.0

    def problem(kind, **kw):
        if kind in seen:
            return
        seen.add(kind)
        problems.append(dict(kind=kind, seed=seed, home=home, away=away, time=round(t, 1),
                             minute=round(m.clock(), 1), state=m.state, **kw))

    while m.state != 'fulltime':
        try:
            evs = m.step({})
        except Exception as exc:  # a crash is the worst stuck state of all
            problem('crash', error=repr(exc), where=traceback.format_exc().strip().splitlines()[-3].strip())
            break
        for e in evs:
            k = e['type']
            counts[k] = counts.get(k, 0) + 1
            if k == 'goal':
                goals[e['team']] += 1
            elif k == 'shot' and e.get('who'):
                shots[e['who'][0]] += 1
            elif k == 'restart' and not m.shootout:
                key = 'restart_' + e['kind']
                counts[key] = counts.get(key, 0) + 1
        t += FIXED_DT
        if t > limit:
            problem('never_ends')
            break
        b = m.ball
        if any(math.isnan(v) or math.isinf(v) for v in b.pos):
            problem('ball_nan')
            break
        pt = m.pitch
        if abs(b.pos[0]) > pt.half_length + pt.goal_depth + OUTSIDE or abs(b.pos[1]) > pt.half_width + OUTSIDE \
                or b.pos[2] > 60.0:
            problem('ball_outside', pos=[round(v, 1) for v in b.pos])
        for p in m.all_players():
            if abs(p.pos[0]) > pt.half_length + OUTSIDE or abs(p.pos[1]) > pt.half_width + OUTSIDE:
                problem('player_outside', who=p.fb.name, pos=[round(v, 1) for v in p.pos])
        # The ball sitting still in open play with nobody on it
        pos = tuple(b.pos)
        moved = math.dist(pos, last_ball) > 0.002
        last_ball = pos
        if m.state == 'play' and not moved and b.owner is None and b.holder is None:
            still_t += FIXED_DT
            if still_t > STILL_LIMIT:
                problem('ball_still', pos=[round(v, 1) for v in pos])
        else:
            still_t = 0.0
        # A keeper who never lets go is the same bug in disguise
        if m.state == 'play' and b.holder is not None:
            hold = getattr(m, '_soak_hold', 0.0) + FIXED_DT
            m._soak_hold = hold
            if hold > STILL_LIMIT:
                problem('keeper_holds', who=b.holder.fb.name)
        else:
            m._soak_hold = 0.0
        if m.state in ('kickoff', 'restart') and m.restart and not m.restart.get('taken'):
            restart_t += FIXED_DT
            if restart_t > RESTART_LIMIT:
                problem('restart_stuck', kind=m.restart['kind'])
        else:
            restart_t = 0.0
    a, bt = m.teams
    if not m.shootout and (a.score, bt.score) != tuple(goals):
        problem('score_mismatch', score=(a.score, bt.score), goals=goals)
    poss = a.possession_t + bt.possession_t
    stats = []
    for team in m.teams:
        passes = sum(pl.passes for pl in team.players)
        done = sum(pl.passes_done for pl in team.players)
        stats.append(dict(goals=team.score, shots=shots[team.idx],
                          possession=team.possession_t / poss if poss else 0.5,
                          passes=passes, pass_pct=done / passes if passes else 0.0,
                          tackles=sum(pl.tackles for pl in team.players),
                          xg=round(team.xg, 2)))
    return dict(seed=seed, home=home, away=away, styles=[team.style['key'] for team in m.teams],
                minutes=round(t / 60.0, 2), events=counts, teams=stats,
                pens=[list(a.pens), list(bt.pens)] if m.shootout else None,
                winner=None if m.winner is None else m.winner.idx, problems=problems)


def summarise(results):
    """Averages over many matches, per team slot and overall."""
    n = len(results)
    if not n:
        return {}
    goals = [r['teams'][0]['goals'] + r['teams'][1]['goals'] for r in results]
    out = dict(matches=n, goals_per_match=statistics.mean(goals),
               draws=sum(1 for r in results if r['teams'][0]['goals'] == r['teams'][1]['goals']) / n,
               shootouts=sum(1 for r in results if r['pens']) / n,
               problems=sum(len(r['problems']) for r in results))
    for key in ('shots', 'passes', 'pass_pct', 'tackles', 'possession', 'xg'):
        out[key] = [statistics.mean(r['teams'][i][key] for r in results) for i in (0, 1)]
    for key in ('foul', 'card', 'restart_corner', 'restart_penalty', 'save', 'woodwork', 'offside', 'wall'):
        out[key] = statistics.mean(r['events'].get(key, 0) for r in results)
    out['home_wins'] = sum(1 for r in results if r['winner'] == 0) / n
    return out
