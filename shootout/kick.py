"""One penalty kick in flight: ball, keeper and the referee's decision."""

from . import config as C
from . import physics


class Kick:
    def __init__(self, ball, keeper):
        self.ball = ball
        self.keeper = keeper
        self.time = 0.0
        self.away_time = 0.0
        self.keeper_touch = None     # 'catch' | 'parry'
        self.frame_hit = None        # 'post' | 'bar'
        self.outcome = None          # (scored, label)
        self.crossing = None         # (x, y) where the ball reached the goal-line plane
        self.events = []             # sounds/effects to play this step

    def step(self, dt):
        self.time += dt
        self.events = []
        ball = self.ball
        self.keeper.update(dt)
        if self.time >= 0.1 and not self.keeper.adjusted and ball.vel[2] < -1.0:
            # Predict where the ball will reach the keeper
            t_left = (ball.pos[2] - C.KEEPER_LINE_Z) / -ball.vel[2]
            self.keeper.adjust(ball.pos[0] + ball.vel[0] * t_left + 0.5 * ball.side_accel * t_left ** 2,
                               ball.pos[1] + ball.vel[1] * t_left - 0.5 * C.GRAVITY * t_left ** 2)
        if ball.held:
            ball.pos = self.keeper.hands()
        else:
            for ev in physics.step(ball, dt):
                self.events.append(ev)
                if ev in ('post', 'bar') and self.frame_hit is None:
                    self.frame_hit = ev
            touch = self.keeper.try_save(ball)
            if touch:
                self.events.append(touch)
                if self.keeper_touch != 'catch':
                    self.keeper_touch = touch
        if self.crossing is None and ball.pos[2] <= C.GOAL_LINE_Z:
            self.crossing = (ball.pos[0], ball.pos[1])
        if self.outcome is None:
            self.outcome = self._decide(dt)
            if self.outcome is not None:
                self.events.append('goal' if self.outcome[0] else 'miss')
                if self.crossing is None:
                    self.crossing = (ball.pos[0], ball.pos[1])
        return self.events

    def _decide(self, dt):
        ball = self.ball
        if physics.is_goal_position(ball):
            if self.frame_hit == 'post':
                return True, 'IN OFF THE POST!'
            if self.frame_hit == 'bar':
                return True, 'IN OFF THE BAR!'
            if self.keeper_touch:
                return True, 'GOAL! KEEPER GOT A HAND TO IT'
            return True, 'GOAL!'
        if ball.held:
            return False, 'CAUGHT!'
        if physics.crossed_line(ball):
            if self.keeper_touch:
                return False, 'SAVED! TIPPED AROUND'
            if self.frame_hit == 'bar' or ball.pos[1] >= C.GOAL_HEIGHT:
                return False, 'OVER THE BAR!'
            if self.frame_hit == 'post':
                return False, 'OFF THE POST!'
            return False, 'WIDE!'
        if ball.vel[2] > 0.0:
            self.away_time += dt
        else:
            self.away_time = 0.0
        sideways = abs(ball.pos[0]) > C.GOAL_HALF_WIDTH + 0.6
        dead = (self.away_time > 0.3 or ball.speed() < 0.8 or self.time > 3.5
                or (sideways and (self.keeper_touch or self.frame_hit)))
        if not dead:
            return None
        if self.keeper_touch:
            return False, 'SAVED!'
        if self.frame_hit == 'post':
            return False, 'OFF THE POST!'
        if self.frame_hit == 'bar':
            return False, 'OFF THE BAR!'
        return False, 'MISSED!'
