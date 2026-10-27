import random

from shootout import config as C, physics
from shootout.keeper import Keeper
from shootout.kick import Kick


def fire(target, speed=20.0, curl=0.0, keeper=None):
    ball = physics.Ball()
    physics.launch(ball, target, speed, curl)
    kick = Kick(ball, keeper or Keeper())
    while kick.outcome is None:
        kick.step(C.SIM_DT)
    return kick


def test_launch_passes_through_target():
    for target in ((2.5, 0.4), (-3.0, 2.0), (0.0, 1.2)):
        ball = physics.Ball()
        physics.launch(ball, target, 20.0)
        while ball.pos[2] > C.GOAL_LINE_Z:
            physics.step(ball, C.SIM_DT)
        assert abs(ball.pos[0] - target[0]) < 0.05
        assert abs(ball.pos[1] - target[1]) < 0.05


def test_curl_still_reaches_target():
    ball = physics.Ball()
    physics.launch(ball, (2.8, 1.0), 20.0, curl=-7.0)
    assert ball.vel[0] > 0.0
    while ball.pos[2] > C.GOAL_LINE_Z:
        physics.step(ball, C.SIM_DT)
    assert abs(ball.pos[0] - 2.8) < 0.08


def test_empty_net_goal_and_misses():
    keeper = Keeper()
    keeper.x0 = 30.0      # keeper out of the way
    assert fire((2.0, 1.0), keeper=keeper).outcome == (True, 'GOAL!')
    keeper = Keeper()
    keeper.x0 = 30.0
    assert fire((0.0, 3.2), keeper=keeper).outcome[1] == 'OVER THE BAR!'
    keeper = Keeper()
    keeper.x0 = 30.0
    assert fire((-4.6, 0.5), keeper=keeper).outcome[1] == 'WIDE!'


def test_post_hit_is_detected():
    keeper = Keeper()
    keeper.x0 = 30.0
    kick = fire((C.GOAL_HALF_WIDTH + 0.08, 1.0), keeper=keeper)
    assert kick.frame_hit == 'post'


def test_keeper_standing_saves_central_shot():
    assert fire((0.0, 1.0)).outcome[0] is False


def test_every_part_of_the_goal_is_saveable_except_the_corners():
    """The old game let top-corner shots in every time. Now a correct guess
    covers the goal except tight to the posts and under the bar."""
    for x in (1.5, 2.2, 2.8):
        for y in (0.3, 1.6):
            keeper = Keeper(**C.HUMAN_KEEPER)
            keeper.commit(1, y > 1.1, 0.03)
            assert fire((x, y), keeper=keeper).outcome[0] is False, (x, y)


def test_corner_beats_a_correct_guess():
    keeper = Keeper(**C.HUMAN_KEEPER)
    keeper.commit(1, True, 0.03)
    assert fire((3.35, 2.2), speed=24.0, keeper=keeper).outcome[0] is True


def test_panenka_beats_a_diving_keeper_but_not_one_who_stays():
    diving = Keeper(**C.HUMAN_KEEPER)
    diving.commit(-1, False, 0.03)
    assert fire((0.0, 1.5), speed=10.0, keeper=diving).outcome[0] is True
    staying = Keeper(**C.HUMAN_KEEPER)
    staying.commit(0, True, 0.03)
    assert fire((0.0, 1.5), speed=10.0, keeper=staying).outcome[0] is False


def test_overhit_shots_fly_higher():
    rng = random.Random(1)
    sweet = [physics.plan_shot((2.0, 1.5), 0.7, 'driven', 0.0, rng)['target'][1] for _ in range(300)]
    over = [physics.plan_shot((2.0, 1.5), 1.0, 'driven', 0.0, rng)['target'][1] for _ in range(300)]
    assert sum(over) / len(over) > sum(sweet) / len(sweet) + 0.5


def test_pressure_widens_spread():
    rng = random.Random(2)

    def spread(pressure):
        xs = [physics.plan_shot((2.0, 1.0), 0.7, 'placed', pressure, rng)['target'][0] for _ in range(500)]
        mean = sum(xs) / len(xs)
        return sum((x - mean) ** 2 for x in xs) / len(xs)

    assert spread(1.0) > spread(0.0) * 1.5
