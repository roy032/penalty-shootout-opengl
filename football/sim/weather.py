"""Weather that changes how the ball and the players behave.

    friction  rolling resistance multiplier (rain < 1: a quick, skiddy ball; snow > 1: it dies)
    skid      pace kept through each bounce (0.78 on dry grass)
    wind      wind speed range in m/s; the direction is picked per match
    catch     multiplier on how hard a shot a keeper can hold (wet gloves spill)
    slip      chance a missed tackle ends with the tackler on his backside
    pace      multiplier on everyone's running speed
"""

import math

WEATHER = {
    'clear': dict(label='Clear', friction=1.0, skid=0.78, wind=(0.0, 0.0), catch=1.0, slip=0.0, pace=1.0),
    'rain': dict(label='Rain', friction=0.72, skid=0.9, wind=(0.0, 2.0), catch=0.78, slip=0.3, pace=0.98),
    'snow': dict(label='Snow', friction=1.9, skid=0.6, wind=(0.0, 1.5), catch=0.92, slip=0.15, pace=0.95),
    'wind': dict(label='Windy', friction=1.0, skid=0.78, wind=(5.0, 8.0), catch=0.95, slip=0.0, pace=1.0),
}
CHOICES = ['clear', 'rain', 'snow', 'wind']


def pick(key, rng):
    """The weather for a match: key from WEATHER, or 'random' (clear half the time)."""
    if key == 'random':
        key = 'clear' if rng.random() < 0.5 else rng.choice(CHOICES[1:])
    w = dict(WEATHER[key])
    w['key'] = key
    lo, hi = w['wind']
    speed = rng.uniform(lo, hi) if hi > 0 else 0.0
    ang = rng.uniform(-math.pi, math.pi)
    w['wind_vec'] = (math.cos(ang) * speed, math.sin(ang) * speed)
    w['wind_speed'] = speed
    return w
