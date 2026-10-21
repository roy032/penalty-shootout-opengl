"""Caption commentary: picks a line for the moments that matter."""

import random

LINES = {
    'goal': ["GOAL! {name} finds the net!", "{name} scores! What a finish!", "It's in! {name} wheels away!",
             "{name}! Top bins!", "Back of the net! {name} with the strike!", "That's a beauty from {name}!"],
    'goal_long': ["From distance! {name} has caught it perfectly!", "An absolute screamer from {name}!"],
    'goal_header': ["{name} rises highest and heads it home!", "A bullet header from {name}!"],
    'own': ["Oh no! {name} turns it into their own net!", "An own goal! {name} won't want to see that again."],
    'save': ["Great save by {name}!", "{name} gets down well to keep it out!", "Denied by {name}!",
             "What a stop from {name}!"],
    'catch': ["{name} gathers it comfortably.", "Safe hands from {name}."],
    'woodwork': ["Off the woodwork!", "It smacks the post!", "Rattled the frame!", "Agonisingly close! Off the bar!"],
    'miss': ["Just wide!", "{name} drags it wide.", "Over the bar from {name}.", "That one's gone into the crowd."],
    'tackle': ["Superb tackle by {name}.", "{name} wins it back.", "Clean as a whistle from {name}."],
    'slide': ["{name} goes to ground!"],
    'foul': ["Free kick. {name} was late with that one.", "The referee blows for a foul by {name}."],
    'yellow': ["Yellow card for {name}.", "{name} goes into the book."],
    'red': ["RED CARD! {name} is off!", "{name} sees red! Down to fewer men!"],
    'offside': ["The flag is up. {name} was offside."],
    'skill': ["Lovely skill from {name}!", "{name} with the trick!", "Showboating from {name}!"],
    'through': ["{name} slides it through!", "Defence-splitting pass from {name}!"],
    'penalty': ["PENALTY!", "The referee points to the spot!"],
    'corner': ["Corner kick."],
    'halftime': ["That's half-time.", "The referee blows for the break."],
    'fulltime': ["It's all over!", "Full time!"],
    'kickoff': ["We're under way!", "And we're off!"],
    'shootout': ["It's going to penalties!", "Nothing to separate them. Penalties it is."],
    'pen_scored': ["Scores!", "Cool as you like.", "No mistake."],
    'pen_missed': ["MISSED!", "Saved! Huge moment!", "It's been missed!"],
    'chip': ["The cheeky chip from {name}!"],
    'kickoff_rain': ["We're under way, and it's teeming down!", "Kick-off in the rain. Expect it to skid."],
    'kickoff_snow': ["Snow on the pitch and the orange ball is out!", "A winter wonderland, and we're off!"],
    'kickoff_wind': ["A swirling wind here. Lofted balls will be a lottery!", "We're off, and the wind is up."],
    'slip': ["{name} loses his footing!", "Down goes {name} on the wet grass!"],
    'tip': ["Fingertips from {name}! Corner.", "What a save from {name}, tipped behind!"],
    'one_two': ["Give and go from {name}!", "Lovely one-two, {name} is in!", "{name} plays it and gets it straight back!"],
    'time_waste': ["They're in no hurry over this one.", "Taking their time here. The fans aren't happy."],
    'keeper_up': ["The keeper's coming up for this!", "Everyone forward, even the goalkeeper!"],
    'bank': ["{name} plays it off the boards!", "Clever from {name}, using the wall!",
             "One-two with the wall from {name}!"],
}


class Commentary:
    def __init__(self, seed=None):
        self.rng = random.Random(seed)
        self.last_shot = None
        self.cool = 0.0
        self.recent = []

    def _pick(self, key, **kw):
        options = [l for l in LINES.get(key, []) if l not in self.recent] or LINES.get(key, [''])
        line = self.rng.choice(options).format(**kw)
        self.recent = (self.recent + [line])[-6:]
        return line

    def update(self, dt):
        self.cool = max(0.0, self.cool - dt)

    def events(self, evs, match):
        """Returns (caption or None, priority 0..3)."""
        best = None

        def name(who):
            if who is None:
                return 'someone'
            t, i = who
            p = match.teams[t].players[i]
            return p.fb.name.title() if p.fb.name.isupper() else p.fb.name

        def offer(text, pri):
            nonlocal best
            if text and (best is None or pri > best[1]):
                best = (text, pri)

        for e in evs:
            t = e['type']
            if t == 'goal':
                if e.get('own'):
                    offer(self._pick('own', name=name(e.get('scorer'))), 3)
                else:
                    shot = self.last_shot
                    if shot and shot.get('header'):
                        key = 'goal_header'
                    elif shot and shot.get('dist', 0) > 18:
                        key = 'goal_long'
                    else:
                        key = 'goal'
                    offer(self._pick(key, name=name(e.get('scorer'))), 3)
            elif t == 'shot':
                p = match.teams[e['who'][0]].players[e['who'][1]]
                gx = p.team.opp_goal_x(match.pitch)
                self.last_shot = dict(header=e.get('header'), dist=abs(gx - p.pos[0]), who=e['who'])
                if e.get('style') == 'chip':
                    offer(self._pick('chip', name=name(e['who'])), 1)
            elif t == 'save':
                offer(self._pick('save' if not e.get('caught') or e.get('speed', 0) > 18 else 'catch',
                                 name=name(e['who'])), 2)
            elif t == 'woodwork':
                offer(self._pick('woodwork'), 2)
            elif t == 'card':
                offer(self._pick('red' if e['card'] == 'red' else 'yellow', name=name(e['who'])), 3)
            elif t == 'foul':
                offer(self._pick('foul', name=name(e['who'])), 1)
            elif t == 'offside':
                offer(self._pick('offside', name=name(e['who'])), 2)
            elif t == 'penalty_awarded':
                offer(self._pick('penalty'), 3)
            elif t == 'tackle' and e.get('kind') in ('slide', 'stand') and self.cool <= 0:
                offer(self._pick('tackle', name=name(e['who'])), 0)
            elif t == 'skill' and self.cool <= 0 and self.rng.random() < 0.5:
                offer(self._pick('skill', name=name(e['who'])), 0)
            elif t == 'bank' and self.rng.random() < 0.7:
                offer(self._pick('bank', name=name(e['who'])), 1)
            elif t == 'pass' and e.get('kind') == 'through' and self.cool <= 0 and self.rng.random() < 0.4:
                offer(self._pick('through', name=name(e['who'])), 0)
            elif t == 'kickoff' and match.weather['key'] != 'clear' and match.half == 1 and match.time < 1.0:
                offer(self._pick('kickoff_' + match.weather['key']), 2)
            elif t in ('halftime', 'fulltime', 'kickoff', 'shootout'):
                offer(self._pick(t), 2)
            elif t == 'one_two':
                offer(self._pick('one_two', name=name(e['to'])), 2)
            elif t == 'time_waste' and self.rng.random() < 0.6:
                offer(self._pick('time_waste'), 1)
            elif t == 'keeper_up':
                offer(self._pick('keeper_up'), 3)
            elif t == 'slip':
                offer(self._pick('slip', name=name(e['who'])), 1)
            elif t == 'parry' and e.get('tip'):
                offer(self._pick('tip', name=name(e['who'])), 2)
            elif t == 'pen_result':
                offer(self._pick('pen_scored' if e['scored'] else 'pen_missed'), 2)
            elif t == 'out' and e.get('kind') == 'corner':
                offer(self._pick('corner'), 0)
        if best is not None:
            self.cool = 2.5 if best[1] == 0 else 1.5
        return best
