"""Pitch geometry. World axes: x along the pitch (goals at x = +-length/2),
y across it, z up. Metres throughout."""

import math


class Pitch:
    def __init__(self, length=105.0, width=68.0, goal_width=7.32, goal_height=2.44, goal_depth=2.0,
                 box_depth=16.5, box_width=40.32, six_depth=5.5, six_width=18.32, spot=11.0,
                 circle=9.15, walls=False, offside=True, name='Full pitch'):
        self.length = length
        self.width = width
        self.goal_width = goal_width
        self.goal_height = goal_height
        self.goal_depth = goal_depth
        self.box_depth = box_depth
        self.box_width = box_width
        self.six_depth = six_depth
        self.six_width = six_width
        self.spot = spot
        self.circle = circle
        self.walls = walls          # cage football: the ball rebounds off boards instead of going out
        self.offside = offside
        self.name = name
        self.post_radius = 0.06
        self.wall_height = 1.2

    @property
    def half_length(self):
        return self.length / 2.0

    @property
    def half_width(self):
        return self.width / 2.0

    def goal_x(self, side):
        """x of the goal line a team defends; side is -1 or +1."""
        return side * self.half_length

    def in_box(self, x, y, side):
        """Inside the penalty area at the end side (-1/+1)."""
        return side * x >= self.half_length - self.box_depth and abs(y) <= self.box_width / 2.0 \
            and side * x <= self.half_length

    def spot_pos(self, side):
        return (side * (self.half_length - self.spot), 0.0)

    def clamp_inside(self, x, y, margin=0.0):
        hl = self.half_length - margin
        hw = self.half_width - margin
        return max(-hl, min(hl, x)), max(-hw, min(hw, y))

    def goal_angle(self, x, y, side):
        """Angle (radians) the goal mouth subtends from (x, y) for the goal at end side."""
        gx = side * self.half_length
        a = math.atan2(self.goal_width / 2.0 - y, abs(gx - x) + 1e-6)
        b = math.atan2(-self.goal_width / 2.0 - y, abs(gx - x) + 1e-6)
        return abs(a - b)


def five_a_side(walls=True):
    return Pitch(length=46.0, width=28.0, goal_width=4.4, goal_height=2.1, goal_depth=1.4, box_depth=7.5,
                 box_width=16.0, six_depth=0.0, six_width=0.0, spot=7.0, circle=4.5, walls=walls, offside=False,
                 name='Cage 5-a-side' if walls else '5-a-side')


def seven_a_side():
    return Pitch(length=64.0, width=42.0, goal_width=5.5, goal_height=2.2, goal_depth=1.6, box_depth=11.0,
                 box_width=26.0, six_depth=4.0, six_width=12.0, spot=9.0, circle=6.0, walls=False,
                 offside=False, name='7-a-side')


def full_size():
    return Pitch()


PITCHES = {'cage': lambda: five_a_side(True), 'fives': lambda: five_a_side(False), 'sevens': seven_a_side,
           'full': full_size}
