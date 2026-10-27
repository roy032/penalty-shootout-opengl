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

# --- Pitch variants: goal size, spot distance and how the ball behaves ---
# Changed in place by apply_variant(); everything reads them at run time.
HAS_BAR = True                  # park goals have no crossbar: the keeper decides
HAS_NET = True
POST_HEIGHT = None              # jumpers for posts only stop a ball along the ground
BOUNCE = 1.0                    # how lively the ball is off the ground
VARIANT = 'stadium'
_STADIUM = dict(GOAL_HALF_WIDTH=GOAL_HALF_WIDTH, GOAL_HEIGHT=GOAL_HEIGHT, SPOT_DISTANCE=SPOT_DISTANCE,
                SPOT_Z=SPOT_Z, GOAL_DEPTH=GOAL_DEPTH, HAS_BAR=True, HAS_NET=True, POST_HEIGHT=None,
                BOUNCE=1.0)
VARIANTS = {
    'stadium': dict(label='Stadium', friction=None),
    # Jumpers for goalposts: no bar, no net, about the size of a small goal
    'park': dict(label='Jumpers for goalposts', GOAL_HALF_WIDTH=2.5, GOAL_HEIGHT=2.0, SPOT_DISTANCE=10.0,
                 HAS_BAR=False, HAS_NET=False, POST_HEIGHT=0.25, friction=1.6),
    # Futsal: 3 x 2 m goal, the spot at 6 m, a heavier ball that hardly bounces
    'futsal': dict(label='Futsal', GOAL_HALF_WIDTH=1.5, GOAL_HEIGHT=2.0, SPOT_DISTANCE=6.0, GOAL_DEPTH=1.0,
                   BOUNCE=0.45, friction=0.9),
    # Beach: sand kills a rolling ball, so skidders are pointless
    'beach': dict(label='Beach', GOAL_HALF_WIDTH=2.75, GOAL_HEIGHT=2.2, SPOT_DISTANCE=9.0, friction=4.5),
}
VARIANT_ORDER = ['stadium', 'park', 'futsal', 'beach']


def apply_variant(name):
    """Switch the goal and ball to a pitch variant (module-level values)."""
    global VARIANT
    g = globals()
    for k, v in _STADIUM.items():
        g[k] = v
    for k, v in VARIANTS[name].items():
        if k.isupper():
            g[k] = v
    g['SPOT_Z'] = GOAL_LINE_Z + g['SPOT_DISTANCE']
    VARIANT = name


def shot_order():
    """Shot types on offer: on sand a skidder just dies."""
    return [k for k in SHOT_ORDER if not (VARIANT == 'beach' and k == 'skidder')]


# --- Squads: ratings are 0..1 ---
COLD_SUB_SIGMA = 1.25           # a sub who has just come on is cold for his first kick
TIRED_SPEED = 0.97              # 120 minutes in the legs
FRESH_SPEED = 1.03

# --- Run-up styles: (cue multiplier, speed multiplier, spread multiplier) ---
RUNUPS = {
    'angled': dict(label='Angled run-up', cue=1.15, speed=1.04, sigma=1.0),
    'straight': dict(label='Straight run-up', cue=0.7, speed=0.95, sigma=1.0),
    'disguised': dict(label='Disguised run-up', cue=0.3, speed=1.0, sigma=DISGUISE_SIGMA),
}
RUNUP_ORDER = ['angled', 'straight', 'disguised']

# --- Keeper styles chosen at the toss ---
KEEPER_STYLES = {
    'standard': dict(label='Standard', reach=0.0, dive_time=0.0, scale=1.0),
    'tall': dict(label='Tall, slower', reach=0.12, dive_time=0.03, scale=1.08),
    'small': dict(label='Small, explosive', reach=-0.1, dive_time=-0.045, scale=0.93),
}
KEEPER_STYLE_ORDER = ['standard', 'tall', 'small']
FINGERTIP_WINDOW = 0.18         # a stretch pressed this close to the ball's arrival adds reach
FINGERTIP_BONUS = 0.14
AI_FINGERTIP = {'easy': 0.08, 'medium': 0.2, 'hard': 0.35}

# --- Adaptive difficulty: nudges so the human scores about 73% ---
AUTO_UP = 0.03
AUTO_DOWN = 0.08

# --- Teams for PvC and PvP (mods can add more) ---
TEAMS = [
    dict(name='REDS', shirt=(0.85, 0.12, 0.15), shorts=(1.0, 1.0, 1.0), keeper=(0.15, 0.75, 0.25)),
    dict(name='BLUES', shirt=(0.15, 0.35, 0.9), shorts=(0.1, 0.1, 0.15), keeper=(0.95, 0.8, 0.1)),
    dict(name='WHITES', shirt=(0.95, 0.95, 0.95), shorts=(0.1, 0.1, 0.12), keeper=(0.2, 0.2, 0.25)),
    dict(name='GREENS', shirt=(0.1, 0.55, 0.25), shorts=(1.0, 1.0, 1.0), keeper=(0.6, 0.2, 0.7)),
    dict(name='ORANGES', shirt=(0.95, 0.5, 0.1), shorts=(1.0, 1.0, 1.0), keeper=(0.1, 0.1, 0.12)),
    dict(name='STRIPES', shirt=(0.1, 0.1, 0.12), shorts=(0.1, 0.1, 0.12), keeper=(0.95, 0.8, 0.1)),
    dict(name='SKY BLUES', shirt=(0.45, 0.7, 0.95), shorts=(1.0, 1.0, 1.0), keeper=(0.9, 0.3, 0.1)),
    dict(name='PURPLES', shirt=(0.45, 0.15, 0.6), shorts=(1.0, 1.0, 1.0), keeper=(0.2, 0.75, 0.3)),
]
CAREER_GOLD_KIT = (0.95, 0.78, 0.2)
