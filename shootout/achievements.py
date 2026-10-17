"""Achievements, unlocked by events in the game and saved with the stats."""

ACHIEVEMENTS = [
    ('first_goal', 'Off the mark', 'Score your first penalty'),
    ('panenka', 'Panenka', 'Score with a chip down the middle'),
    ('knuckle', 'Knuckleball', 'Score with a knuckleball'),
    ('top_bins', 'Top bins', 'Score in a top corner'),
    ('three_saves', 'Wall', 'Make 3 saves in one shootout'),
    ('sudden_win', 'Nerves of steel', 'Win a shootout in sudden death'),
    ('keeper_goal', 'Chilavert', 'Score with your goalkeeper taking a kick'),
    ('rewrite', 'Rewrite history', 'Win a famous shootout that your side really lost'),
    ('slip_goal', 'Terry who?', 'Slip on the spot and still score'),
    ('outfield_save', 'Emergency hero', 'Save a kick with an outfield player in goal'),
    ('tournament', 'Champions', 'Win the tournament'),
    ('career_gold', 'Golden boot', 'Unlock the gold kit in a career'),
    ('daily_perfect', 'Perfect day', 'Score all five in the daily shootout'),
    ('bins_5', 'Sharpshooter', 'Hit all 5 bins in the Top Bins challenge'),
    ('ghost_win', 'Ghostbuster', 'Beat a ghost duel'),
    ('fingertip', 'Fingertips', 'Save one with a timed fingertip stretch'),
]
NAMES = {key: name for key, name, _ in ACHIEVEMENTS}


def unlock(stats, key):
    """Mark an achievement; returns its name if it is new, else None."""
    got = stats.setdefault('achievements', [])
    if key in got or key not in NAMES:
        return None
    got.append(key)
    return NAMES[key]
