"""Pitch dimensions, physics constants and difficulty tables.

All distances are in metres (1 world unit = 1 m) so the pitch matches the
Laws of the Game. The goal line runs along z = GOAL_LINE_Z and the kicker
faces -z.
"""

# --- Pitch and goal (Laws of the Game, Law 1) ---
GOAL_LINE_Z = -15.0
GOAL_HALF_WIDTH = 3.66          # inner edge of each post: 7.32 m between posts
GOAL_HEIGHT = 2.44              # underside of the crossbar
GOAL_DEPTH = 2.0                # how far the net sits behind the line
POST_RADIUS = 0.06              # 12 cm posts
SPOT_DISTANCE = 11.0
SPOT_Z = GOAL_LINE_Z + SPOT_DISTANCE
PENALTY_AREA_DEPTH = 16.5
PENALTY_AREA_HALF_WIDTH = 20.16
GOAL_AREA_DEPTH = 5.5
GOAL_AREA_HALF_WIDTH = 9.16
ARC_RADIUS = 9.15

# --- Ball ---
BALL_RADIUS = 0.11
GRAVITY = 9.81

# --- Simulation ---
SIM_DT = 1.0 / 240.0            # small step so a 30 m/s ball cannot tunnel through a post
FRAME_MS = 16                   # display refresh (about 60 fps)

# --- Keeper ---
KEEPER_LINE_Z = GOAL_LINE_Z + 0.25   # keeper stands on the line, as Law 14 requires
HUMAN_KEEPER = dict(reach=1.85, dive_time=0.5, catch_speed=21.0)

# --- Shot types ---
# speed: (min, max) launch speed in m/s across the power bar
# sigma: base spread of the error around the aim point, in metres
SHOT_TYPES = {
    'placed': dict(label='Placed', speed=(16.0, 23.0), sigma=0.16, curl=0.0),
    'driven': dict(label='Driven', speed=(23.0, 31.0), sigma=0.27, curl=0.0),
    'curl':   dict(label='Curler', speed=(18.0, 25.0), sigma=0.21, curl=7.0),
    'chip':   dict(label='Chip / Panenka', speed=(8.5, 12.0), sigma=0.12, curl=0.0),
    # Almost no spin: wobbles late and is hard to hold
    'knuckle': dict(label='Knuckleball', speed=(23.0, 29.0), sigma=0.3, curl=0.0),
    # Drilled low so it skids off the turf just before the line
    'skidder': dict(label='Skidder', speed=(20.0, 26.0), sigma=0.2, curl=0.0),
    # Hop in the run-up to make the keeper move first, then roll it in
    'stutter': dict(label='Stutter (hop)', speed=(12.0, 16.0), sigma=0.14, curl=0.0),
}
SHOT_ORDER = ['placed', 'driven', 'curl', 'chip', 'knuckle', 'skidder', 'stutter']
STUTTER_PAUSE = 0.45            # how long the hop holds the run-up
DISGUISE_SIGMA = 1.15           # hiding your body shape costs a little accuracy

POWER_SWEET_LOW = 0.55
POWER_SWEET_HIGH = 0.85
POWER_PERIOD = 1.3              # seconds for the bar to go 0 -> 1 -> 0
RUNUP_TIME = 0.9                # seconds from pressing shoot to contact
# Relaxed assist: slower bar, wider sweet spot, steadier aim
RELAXED = dict(power_period=1.95, sweet=(0.45, 0.9), sigma=0.8)

# --- Composure: time between the whistle and starting the run-up ---
RUSHED_BEFORE = 0.6             # starting sooner than this rattles the kicker
SETTLED = (1.0, 3.0)            # a calm breath in this window steadies the aim
DRAGGED_AFTER = 5.0             # waiting longer lets the crowd get to you

# --- Slips and the spot ---
SLIP_BASE = 0.008
SLIP_PER_KICK = 0.004           # the spot cuts up as the shootout goes on
DOUBLE_TOUCH_SHARE = 0.2        # share of slips where the ball is touched twice

# --- Weather: (ground friction, keeper catch multiplier, slip bonus) ---
WEATHER = {
    'clear': dict(label='Clear', friction=1.2, catch=1.0, slip=0.0, skid=1.0),
    'rain':  dict(label='Rain', friction=0.45, catch=0.8, slip=0.03, skid=1.35),
    'wind':  dict(label='Windy', friction=1.2, catch=0.95, slip=0.0, skid=1.0),
    'snow':  dict(label='Snow', friction=2.2, catch=0.85, slip=0.02, skid=0.8),
    'fog':   dict(label='Fog', friction=1.2, catch=1.0, slip=0.0, skid=1.0),
}
WEATHER_ORDER = ['clear', 'rain', 'wind', 'snow', 'fog']

# --- Squads: outfield takers then the keeper (Law 10: everyone kicks once
# before anyone kicks twice) ---
SQUAD_SIZE = 11

# --- Difficulty (PvC) ---
# keeper: how the computer keeps goal
#   read: chance it reads the kicker's body shape and picks the right side
#   reaction: delay after contact before it moves (s)
# shooter: how the computer takes kicks
#   sigma_scale: multiplies the shot spread
#   power: (mean, spread) of where it stops the power bar
#   exploit: how strongly it shoots away from the human keeper's favourite side
# Keeper specialists brought on just for the shootout
SPECIALIST = dict(reach=0.15, dive_time=-0.02)
# An outfield player forced into goal after a red card
EMERGENCY_KEEPER = dict(reach=0.72, dive_time=0.08, catch=0.75)

DIFFICULTY = {
    'easy': dict(
        keeper=dict(read=0.15, reaction=0.1, reach=1.6, dive_time=0.56, catch_speed=17.0, stay=0.08,
                    bait=0.0, early=0.02, specialist=0.0),
        shooter=dict(sigma_scale=1.45, power=(0.66, 0.16), exploit=0.0, think=1.4),
    ),
    'medium': dict(
        keeper=dict(read=0.30, reaction=0.05, reach=1.7, dive_time=0.53, catch_speed=20.0, stay=0.06,
                    bait=0.2, early=0.04, specialist=0.15),
        shooter=dict(sigma_scale=1.1, power=(0.70, 0.11), exploit=0.35, think=1.1),
    ),
    'hard': dict(
        keeper=dict(read=0.35, reaction=0.03, reach=1.9, dive_time=0.5, catch_speed=21.0, stay=0.05,
                    bait=0.35, early=0.05, specialist=0.4),
        shooter=dict(sigma_scale=0.8, power=(0.72, 0.07), exploit=0.6, think=0.9),
    ),
}

# --- Kits: shirt and shorts for outfield players, plus the keeper's shirt ---
KITS = {
    'p1': dict(shirt=(0.85, 0.12, 0.15), shorts=(1.0, 1.0, 1.0), keeper=(0.15, 0.75, 0.25)),
    'p2': dict(shirt=(0.15, 0.35, 0.9), shorts=(0.1, 0.1, 0.15), keeper=(0.95, 0.8, 0.1)),
}
SPECIALIST_KIT = (0.95, 0.45, 0.75)
EMERGENCY_KIT = (0.55, 0.55, 0.58)

# Party mode players: shirt colours for up to 8 friends
PARTY_COLOURS = [
    (0.85, 0.12, 0.15), (0.15, 0.35, 0.9), (0.95, 0.8, 0.1), (0.15, 0.7, 0.3),
    (0.6, 0.2, 0.75), (0.95, 0.5, 0.1), (0.1, 0.75, 0.8), (0.9, 0.9, 0.9),
]
