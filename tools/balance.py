"""Monte Carlo check of kick outcomes: computer kicker vs computer keeper.

Run from the repo root: python tools/balance.py
Real-world shootouts convert roughly 70-80% of kicks.
"""

import os
import random
import sys
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from shootout import ai, config as C, physics  # noqa: E402
from shootout.keeper import Keeper  # noqa: E402
from shootout.kick import Kick  # noqa: E402


def one_kick(rng, kicker_level, keeper_level):
    sp = C.DIFFICULTY[kicker_level]['shooter']
    kp = C.DIFFICULTY[keeper_level]['keeper']
    profile = rng.choice(ai.PROFILES)
    kind, aim, power = ai.kicker_plan(rng, sp, profile, [])
    shot = physics.plan_shot(aim, power, kind, 0.0, rng, sp['sigma_scale'])
    ball = physics.Ball()
    physics.launch(ball, shot['target'], shot['speed'], shot['curl'])
    keeper = Keeper(kp['reach'], kp['dive_time'], kp['catch_speed'])
    keeper.commit(*ai.keeper_decision(rng, kp, shot['target'], []))
    kick = Kick(ball, keeper)
    while kick.outcome is None:
        kick.step(C.SIM_DT)
    return kick.outcome


def main(n=400):
    rng = random.Random(7)
    for level in ('easy', 'medium', 'hard'):
        labels = Counter()
        goals = 0
        for _ in range(n):
            scored, label = one_kick(rng, level, level)
            goals += scored
            labels[label] += 1
        print(f'{level:6s} conversion {100.0 * goals / n:5.1f}%  ', dict(labels.most_common()))


if __name__ == '__main__':
    main()
