"""Commentary lines picked from the situation, shown as captions and, if
pyttsx3 is installed and speech is on, read out loud."""

import queue
import re
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

# Lines that know the characters: their personality, their record, their aura
PERSONA_WALK = {
    'ice': ['{taker}, Ice Cold. Not a flicker of nerves.', 'Nothing gets to {taker}. Nothing.'],
    'showboat': ['{taker} is enjoying this far too much.', 'Is {taker} going to try something outrageous?'],
    'hothead': ['{taker} looks wound up. The keeper will try to wind him up even more.'],
    'thinker': ['{taker} takes a long look at the goal. Planning every step.'],
    'kid': ['{taker} looks young out there. Big moment for a nervous kid.'],
    'clutch': ['Big moments are made for {taker}.', '{taker} lives for this.'],
}
KEEPER_WALK = {
    'dancer': ['The Dancer is at it again on the line.', 'Look at the keeper: wobbling, waving, anything to distract.'],
    'showman': ['The Showman in goal is pointing at a corner already.'],
    'reader': ['This keeper does the homework. He knows where {taker} likes to go.'],
    'wall': ['The keeper makes himself enormous.'],
    'gambler': ['This keeper gambles. He will go early.'],
    'cat': ['Quick hands in goal. One of the sharpest around.'],
}
AURA = ['You can feel the aura from {name}.', 'The aura is ridiculous. {name}.', '{name}. Pure aura.']
RECORD_PERFECT = '{taker} has never missed from the spot in this shirt: {g} from {k}.'
RECORD_MISSED = '{taker} has missed {m} from the spot before. Will it play on the mind?'
BANTER_KICKER = ['Pick a side. Any side.', 'You will be picking this one out of the net.', 'Seen this one before?',
                 'Big goal. Small keeper.', 'Dive early, I dare you.', 'Bottom corner. Try and stop it.']
BANTER_KEEPER = ['I know where you are going.', 'Your hips gave it away last time.', 'Nervous?',
                 'The goal looks small from there, does it not?', 'Go on then.', 'I have your name in my notes.']
SIGNATURE_BANTER = {
    'siuu': 'The whole crowd will be shouting SIU in a minute.', 'cold': 'Is it cold out here, or is it just me?',
    'tea': 'Put the kettle on.', 'crossed arms': 'I will not even celebrate. Too easy.',
    'meditate': 'Inner peace. Then top corner.', 'selfie': 'Smile for the camera.',
    'roar': 'You will hear me after this one.', 'shimmy': 'I have saved better than you.',
    'scorpion': 'Watch this.', 'flex': 'Why always me?',
}


def _gender(line, women):
    """Commentary is written about a he; switch it for a woman taker."""
    if not women:
        return line
    for a, b in (('He', 'She'), ('he', 'she'), ('His', 'Her'), ('his', 'her'), ('him', 'her')):
        line = re.sub(rf'\b{a}\b', b, line)
    return line


def character_line(rng, player, keeper, record, team):
    """A walk-up line about the taker or keeper as characters, or None."""
    options = []
    if player is not None:
        name = player.name.title() if player.char else player.label
        if player.lines:
            options += player.lines
        if player.persona in PERSONA_WALK:
            options.append(_gender(rng.choice(PERSONA_WALK[player.persona]).format(taker=name), player.women))
        if player.aura >= 0.85:
            options.append(rng.choice(AURA).format(name=name))
        if record and record[0] >= 3:
            k, g = record
            if g == k:
                options.append(_gender(RECORD_PERFECT.format(taker=name, g=g, k=k), player.women))
            elif k - g >= 2:
                options.append(_gender(RECORD_MISSED.format(taker=name, m=k - g), player.women))
    if keeper is not None:
        taker = player.name.title() if player is not None else team
        if keeper.persona in KEEPER_WALK:
            options.append(_gender(rng.choice(KEEPER_WALK[keeper.persona]).format(taker=taker), keeper.women))
        if keeper.char and keeper.lines:
            options += keeper.lines
        if keeper.aura >= 0.9:
            options.append(rng.choice(AURA).format(name=keeper.name.title()) + ' And that is just the keeper.')
    return rng.choice(options) if options else None


def banter(rng, kicker, keeper, memory=None):
    """A pre-kick exchange in speech bubbles: (taker's line, keeper's line)."""
    k_line = rng.choice(BANTER_KICKER)
    if kicker is not None and kicker.celebration in SIGNATURE_BANTER and rng.random() < 0.5:
        k_line = SIGNATURE_BANTER[kicker.celebration]
    g_line = rng.choice(BANTER_KEEPER)
    if keeper is not None and keeper.celebration in SIGNATURE_BANTER and rng.random() < 0.5:
        g_line = SIGNATURE_BANTER[keeper.celebration]
    if memory:
        g_line = memory.replace('Last time you', 'Last time, you')
    return k_line, g_line


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


def walk_line(rng, taker, team, stakes, sudden, keeper_kick, cold, women=False):
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
    return _gender(rng.choice(pool).format(taker=taker, team=team), women)


CELEBRATION_LINES = {
    'siuu': 'And the jump, the spin... SIUUU!', 'cold': 'Shivering. So cold.', 'tea': 'And a sip of tea!',
    'meditate': 'Sits down cross-legged. Total calm.', 'pose': 'Arms out, chin up. The pose!',
    'crossed arms': 'Arms folded. Unbothered.', 'shirt swing': 'The shirt comes off and spins round!',
    'backflip': 'Backflip!', 'selfie': 'A selfie with the fans!', 'lean': 'Leaning on the post, like he owns it.',
    'collar': 'Collar up. Stands there. Iconic.', 'shaka': 'All smiles.', 'scream': 'He is screaming at the sky!',
    'flex': 'Stands still, flexes. Why always him?', 'heart': 'A heart for the fans.',
}


def result_line(rng, label, shot_kind, taker, team, saves, goals_in_row, women=False, keeper_women=False,
                celebration=None):
    kind = _kind(label, shot_kind)
    line = _gender(rng.choice(RESULT[kind]).format(taker=taker, team=team), women)
    if kind in ('SAVED', 'CAUGHT') and saves >= 2:
        line += ' ' + _gender(rng.choice(STREAK_SAVES).format(n=saves), keeper_women)
    elif kind.startswith('GOAL') and goals_in_row >= 3:
        line += ' ' + rng.choice(STREAK_GOALS).format(n=goals_in_row, team=team)
    elif kind.startswith('GOAL') and celebration in CELEBRATION_LINES:
        line += ' ' + _gender(CELEBRATION_LINES[celebration], women)
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
