"""Cup Run: four knockout ties against harder and harder sides, and a perk to
pick after every win.

Pure logic with no window, so it can be tested and soaked. The app asks a
CupRun for the next tie, plays it as a normal Match with tie_settings(), and
reports the score back with record(). After a win it offers three perks and
take() adds one; perks stack and are applied to the player's (home) team by
apply_perks() when the Match is built."""

import random

from . import roster

ROUNDS = [
    # name, difficulty, opponent pool ('club' = generated clubs, 'stars' = character teams)
    ('Round of 16', 'amateur', 'club'),
    ('Quarter-final', 'pro', 'club'),
    ('Semi-final', 'worldclass', 'stars'),
    ('Final', 'worldclass', 'stars'),
]

# Each perk nudges one team-wide number in match.Team; taking it twice stacks.
PERKS = {
    'boots': dict(label='Rocket boots', blurb='Shots fly 8% faster', field='shot_power', mul=1.08),
    'engine': dict(label='Big engine', blurb='Sprinting tires the team 30% less', field='stamina_drain', mul=0.7),
    'composure': dict(label='Composure', blurb='Passes and shots 12% more accurate', field='error_scale', mul=0.88),
    'pace': dict(label='Quick feet', blurb='Everyone runs 4% faster', field='speed_scale', mul=1.04),
    'gloves': dict(label='Safe hands', blurb='Your keeper reaches 12% further', field='reach', mul=1.12),
}


def apply_perks(team, keys):
    """Stack the chosen perks onto a match.Team."""
    for key in keys:
        p = PERKS[key]
        setattr(team, p['field'], getattr(team, p['field']) * p['mul'])
    team.perks = tuple(keys)


class CupRun:
    def __init__(self, team, seed=None):
        self.team = team
        self.rng = random.Random(seed)
        ids = [t for t in roster.team_ids() if t != team]
        stars = [t for t in ids if t in roster.TEAMS]
        clubs = [t for t in ids if t not in roster.TEAMS] or stars
        picked = []
        self.ties = []
        for name, diff, pool in ROUNDS:
            options = [t for t in (stars if pool == 'stars' else clubs) if t not in picked] or ids
            opp = self.rng.choice(options)
            picked.append(opp)
            self.ties.append(dict(name=name, opp=opp, difficulty=diff, score=None, pens=None, won=None))
        self.round = 0
        self.perks = []
        self.offer = []

    # ------------------------------------------------------------ state
    @property
    def over(self):
        return self.lost or self.champion

    @property
    def lost(self):
        return any(t['won'] is False for t in self.ties)

    @property
    def champion(self):
        return all(t['won'] for t in self.ties)

    def tie(self):
        """The next tie to play, or None when the run is over."""
        return None if self.over else self.ties[self.round]

    def tie_settings(self, base=None):
        """Match settings for the next tie: its difficulty, the perks so far, and always a winner."""
        s = dict(base or {})
        t = self.tie()
        s.update(difficulty=t['difficulty'], perks=tuple(self.perks), decider='penalties')
        return s

    # ------------------------------------------------------------ results
    def record(self, score, pens=None):
        """The result of the current tie from the player's side: score (us, them), pens (us, them) if any."""
        t = self.ties[self.round]
        t['score'] = tuple(score)
        t['pens'] = tuple(pens) if pens else None
        decided = t['pens'] if score[0] == score[1] and pens else score
        t['won'] = decided[0] > decided[1]
        self.offer = []
        if t['won']:
            self.round += 1
            if not self.champion:
                self.offer = self.rng.sample(sorted(PERKS), 3)
        return t['won']

    def take(self, key):
        """Pick one of the perks on offer after a win."""
        if key not in self.offer:
            raise ValueError('%s is not on offer' % key)
        self.perks.append(key)
        self.offer = []

    # ------------------------------------------------------------ text
    def perk_text(self):
        if not self.perks:
            return 'No perks yet'
        counts = {}
        for k in self.perks:
            counts[k] = counts.get(k, 0) + 1
        return ', '.join(PERKS[k]['label'] + (' x%d' % n if n > 1 else '') for k, n in counts.items())

    def bracket_lines(self):
        lines = []
        for i, t in enumerate(self.ties):
            name = roster.team_info(t['opp'])['name']
            if t['won'] is None:
                res = 'next' if i == self.round and not self.over else ''
            else:
                res = '%s %d-%d' % ('W' if t['won'] else 'L', t['score'][0], t['score'][1])
                if t['pens']:
                    res += ' (%d-%d pens)' % t['pens']
            lines.append(('%s:  %s   %s' % (t['name'], name, res)).rstrip())
        return lines
