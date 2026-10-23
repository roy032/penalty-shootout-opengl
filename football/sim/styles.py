"""Team playing styles: how each side likes to play, as nudges to the team AI.

Every number is a small offset or multiplier on what TeamAI already does, so a
style changes the flavour of a team, not its strength:

    line     block height when defending, as a fraction of half the pitch (+ high, - deep)
    width    how wide the team spreads when attacking
    press    multiplier on how hard and how often the team presses
    tempo    how long a player keeps the ball before passing (seconds of patience)
    passing  extra value for passing at all, rather than running with it
    risk     weight on losing the ball with a pass (lower = more daring passes)
    forward  extra value for passes that gain ground
    through  extra value for balls in behind
    long     extra value for lofted passes over the top and crosses (0 = never chosen)
    shoot    extra value for shooting (+ shoots from further out)
    dribble  extra value for running with the ball, and the chance of a trick
    runs     how often midfielders break forward (1 in N players at a time)
    counter  extra urgency to go forward in the seconds after winning the ball
"""

import zlib

NEUTRAL = dict(line=0.0, width=1.0, press=1.0, tempo=0.18, passing=0.0, risk=1.2, forward=0.0, through=0.0, long=0.0,
               shoot=0.0, dribble=0.0, runs=3, counter=0.0)

STYLES = {
    'possession': dict(label='Patient possession', blurb='Short passes, keeps the ball, high line',
                       line=0.06, width=1.08, press=1.0, tempo=0.12, passing=0.2, risk=1.55, forward=0.05,
                       through=-0.05, shoot=0.12, dribble=-0.05, runs=3),
    'counter': dict(label='Quick counters', blurb='Sits off, then breaks fast into space',
                    line=-0.06, press=0.85, tempo=0.1, passing=0.05, risk=1.0, forward=0.3, through=0.25, counter=0.5,
                    dribble=0.05, runs=2),
    'press': dict(label='High press', blurb='Hunts the ball high up the pitch, quick switches',
                  line=0.1, width=1.12, press=1.35, tempo=0.15, passing=0.1, risk=1.1, forward=0.12, through=0.08, runs=3),
    'direct': dict(label='Direct', blurb='Long balls, crosses and headers',
                   line=-0.02, width=1.18, press=1.0, tempo=0.08, risk=0.95, forward=0.25, long=0.6,
                   shoot=0.05, runs=2),
    'chaos': dict(label='Chaos', blurb='Long shots, tricks and risky balls in behind',
                  line=0.04, press=1.1, tempo=0.06, passing=-0.12, risk=0.85, forward=0.1, through=0.2, shoot=0.1,
                  dribble=0.08, runs=2),
    'lowblock': dict(label='Low block', blurb='Deep and compact, physical, long balls out',
                     line=-0.12, width=0.9, press=0.75, tempo=0.12, passing=-0.05, risk=1.3, forward=0.1, long=0.4,
                     shoot=0.05, runs=5),
}

TEAM_STYLES = {'legends': 'possession', 'stars': 'counter', 'queens': 'press', 'pioneers': 'direct',
               'myths': 'chaos', 'cult': 'lowblock'}


def style_key(team_id):
    """Character teams have a fixed style; generated clubs get a stable one from their name."""
    if team_id in TEAM_STYLES:
        return TEAM_STYLES[team_id]
    keys = sorted(STYLES)
    return keys[zlib.crc32(team_id.encode()) % len(keys)]


def style_for(team_id, key=None):
    """The style a team plays; key forces a particular one (tests, the soak tool)."""
    key = key or style_key(team_id)
    st = dict(NEUTRAL)
    st.update(STYLES[key])
    st['key'] = key
    return st
