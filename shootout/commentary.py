"""Commentary lines picked from the situation, shown as captions and, if
pyttsx3 is installed and speech is on, read out loud."""

import queue
import threading

WALK = {
    'must_score': ['{taker} has to score to keep {team} alive.', 'Everything rides on this for {team}.',
                   'Miss, and it is over for {team}.'],
    'to_win': ['{taker} can win it for {team}!', 'This is for the trophy...', 'One kick from glory for {team}.'],
    'sudden': ['Sudden death. {taker} steps forward.', 'Nobody wants to be the one to miss now.'],
    'keeper': ['The goalkeeper is taking one! Everyone else has had a go.'],
    'cold': ['{taker} came on for this moment. Has he warmed up?'],
    'none': ['{taker} walks up for {team}.', 'Here is {taker}.', '{taker} places the ball.'],
}
RESULT = {
    'GOAL': ['He sends the keeper the wrong way!', 'Buried it.', 'Cool as you like.', 'No mistake from {taker}.'],
    'GOAL_TOUCH': ['The keeper got a hand to it, but not enough!', 'Through the gloves and in!'],
    'POST_IN': ['In off the post! Lucky, but they all count.'],
    'CHIP': ['A Panenka! The audacity!', 'He chipped it down the middle!'],
    'SAVED': ['Saved! What a stop!', 'The keeper guessed right!', 'Great save!'],
    'CAUGHT': ['Held! Straight into the gloves.', 'Too close to the keeper.'],
    'FRAME': ['Off the woodwork!', 'He hits the frame!'],
    'OVER': ['Over the bar! He leaned back.', 'Into the stand behind the goal.'],
    'WIDE': ['Wide! He pulled it.', 'It drifts past the post.'],
    'SLIP': ['He slipped! The spot gave way.'],
    'DISALLOWED': ['VAR says no: he touched it twice.'],
    'PARK': ['And the arguing starts...'],
}
STREAK_SAVES = ['That is {n} saves for the keeper now!', '{n} saves. He is in their heads.']
STREAK_GOALS = ['{n} in a row for {team}.']


def _kind(label, shot_kind):
    if 'SLIPPED' in label:
        return 'SLIP'
    if 'DISALLOWED' in label:
        return 'DISALLOWED'
    if 'SAYS' in label:
        return 'PARK'
    if label.startswith('GOAL') or label.startswith('IN OFF'):
        if shot_kind == 'chip' and label == 'GOAL!':
            return 'CHIP'
        if label.startswith('IN OFF'):
            return 'POST_IN'
        return 'GOAL_TOUCH' if 'HAND' in label else 'GOAL'
    if label.startswith('SAVED'):
        return 'SAVED'
    if label.startswith('CAUGHT'):
        return 'CAUGHT'
    if 'POST' in label or 'OFF THE BAR' in label:
        return 'FRAME'
    if 'OVER' in label:
        return 'OVER'
    return 'WIDE'


def walk_line(rng, taker, team, stakes, sudden, keeper_kick, cold):
    if keeper_kick:
        pool = WALK['keeper']
    elif cold:
        pool = WALK['cold']
    elif stakes in WALK:
        pool = WALK[stakes]
    elif sudden:
        pool = WALK['sudden']
    else:
        pool = WALK['none']
    return rng.choice(pool).format(taker=taker, team=team)


def result_line(rng, label, shot_kind, taker, team, saves, goals_in_row):
    kind = _kind(label, shot_kind)
    line = rng.choice(RESULT[kind]).format(taker=taker, team=team)
    if kind in ('SAVED', 'CAUGHT') and saves >= 2:
        line += ' ' + rng.choice(STREAK_SAVES).format(n=saves)
    elif kind.startswith('GOAL') and goals_in_row >= 3:
        line += ' ' + rng.choice(STREAK_GOALS).format(n=goals_in_row, team=team)
    return line


class Speaker:
    """Reads lines out on a background thread with pyttsx3, if it is installed."""

    def __init__(self):
        self.available = False
        self.lines = queue.Queue()
        import importlib.util
        if importlib.util.find_spec('pyttsx3') is None:
            return
        self.available = True
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        import pyttsx3
        try:
            engine = pyttsx3.init()
        except Exception:
            self.available = False
            return
        while True:
            line = self.lines.get()
            try:
                engine.say(line)
                engine.runAndWait()
            except Exception:
                pass

    def say(self, line):
        if self.available:
            # Drop stale lines so speech never lags behind the action
            while not self.lines.empty():
                try:
                    self.lines.get_nowait()
                except queue.Empty:
                    break
            self.lines.put(line)
