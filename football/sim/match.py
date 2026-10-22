"""The match: teams, the ball, touches, kicks, tackles, the referee's rules
and the flow from kick-off to the final whistle (and penalties)."""

import collections
import math
import random

from . import ball as B
from . import roster, weather
from .styles import style_for
from .ball import Ball
from .pitch import PITCHES
from .player import Player, CONTROL, REACH_HEAD, norm, ang_diff

FIXED_DT = 1.0 / 60.0
PEN_SWEET = (0.55, 0.82)    # spot-kick power that is struck cleanly: above it the ball climbs
LATE_GRACE = 0.13           # a press this soon after the ball slips off your foot still plays it
ONE_TWO_HOLD = 0.22        # seconds pass must stay held after a pass to send the passer on a run
EARLY_TACKLE = 0.25         # a tackle pressed this early still goes in when the man takes his touch

# Formations as (role, fx, fy): fx runs -1 (own goal line) .. +1 (opponent's), fy -1 .. +1 across
FORMATIONS = {
    5: [('GK', -0.93, 0.0), ('DEF', -0.52, 0.0), ('MID', -0.12, -0.5), ('MID', -0.12, 0.5), ('FWD', 0.32, 0.0)],
    7: [('GK', -0.94, 0.0), ('DEF', -0.58, -0.35), ('DEF', -0.58, 0.35), ('MID', -0.2, -0.55), ('MID', -0.25, 0.0),
        ('MID', -0.2, 0.55), ('FWD', 0.3, 0.0)],
    11: [('GK', -0.95, 0.0), ('DEF', -0.62, -0.68), ('DEF', -0.66, -0.24), ('DEF', -0.66, 0.24),
         ('DEF', -0.62, 0.68), ('MID', -0.3, -0.42), ('MID', -0.36, 0.0), ('MID', -0.3, 0.42),
         ('FWD', 0.12, -0.62), ('FWD', 0.2, 0.0), ('FWD', 0.12, 0.62)],
}

DIFFICULTY = {
    # reaction (s), decision noise, AI accuracy multiplier on errors, AI speed
    'beginner': dict(react=0.42, noise=0.35, error=1.7, speed=0.9, press=0.6, label='Beginner'),
    'amateur': dict(react=0.3, noise=0.22, error=1.3, speed=0.95, press=0.8, label='Amateur'),
    'pro': dict(react=0.2, noise=0.12, error=1.0, speed=1.0, press=1.0, label='Pro'),
    'worldclass': dict(react=0.13, noise=0.06, error=0.8, speed=1.03, press=1.15, label='World Class'),
    'legendary': dict(react=0.08, noise=0.02, error=0.65, speed=1.06, press=1.3, label='Legendary'),
}

DEFAULTS = dict(size=5, pitch='cage', half_seconds=150.0, difficulty='pro', preset='arcade', fouls=True,
                cards=True, offside=None, decider='penalties', assist=True, auto_switch=True, weather='clear',
                stamina=True, extra_time=False, styles=None, perks=())


class Team:
    def __init__(self, idx, info, players, attack):
        self.idx = idx
        self.info = info
        self.name = info['name']
        self.short = info['short']
        self.players = players
        self.attack = attack        # +1: attacks the goal at +x
        self.score = 0
        self.speed_scale = 1.0
        self.error_scale = 1.0
        self.shot_power = 1.0       # perks (Cup Run): harder shots, ...
        self.stamina_drain = 1.0    # ... a bigger engine, ...
        self.reach = 1.0            # ... and a keeper who gets further
        self.perks = ()
        self.ai_react = 0.2
        self.ai_noise = 0.1
        self.press = 1.0
        self.style = style_for(info['id'])     # how the AI likes to play (styles.py)
        self.human = False
        self.stats = collections.Counter()
        self.possession_t = 0.0
        self.xg = 0.0
        self.pens = []
        self.opp = None

    @property
    def side(self):
        return self.attack

    def keeper(self):
        for p in self.players:
            if p.keeper and not p.sent_off:
                return p
        return None

    def active(self):
        return [p for p in self.players if not p.sent_off]

    def own_goal_x(self, pitch):
        return -self.attack * pitch.half_length

    def opp_goal_x(self, pitch):
        return self.attack * pitch.half_length


class Controller:
    """One human: which team they play for and who they control."""

    def __init__(self, index, team):
        self.index = index
        self.team = team
        self.player = None
        self.charge = None          # shot power while the button is held
        self.charge_kind = None
        self.lock_t = 0.0           # no auto-switch right after a manual one
        self.queued = None          # first-time action waiting for the ball
        self.one_two = None         # give-and-go: the passer bursting forward while pass is held
        self.one_two_pending = False
        self.queue_t = 0.0
        self.move = (0.0, 0.0)      # this tick's stick, for the first touch
        self.held = frozenset()
        self.owned_tick = -10 ** 6  # last tick the controlled player had the ball at his feet
        self.tackle_t = 0.0         # tackle pressed a moment before the opponent got the ball
        self.pen_aim = None         # [y, z] on the goal mouth while lining up a penalty


class Input:
    """A frame of input for one controller: analog move plus named actions."""
    ACTIONS = ('pass', 'shoot', 'through', 'lob', 'sprint', 'switch', 'finesse', 'skill')

    def __init__(self):
        self.move = (0.0, 0.0)
        self.held = set()
        self.pressed = set()
        self.released = set()


class Match:
    def __init__(self, home='stars', away='legends', settings=None, humans=((0, 0),), seed=None):
        s = dict(DEFAULTS)
        s.update(settings or {})
        self.settings = s
        self.rng = random.Random(seed)
        self.pitch = PITCHES[s['pitch']]()
        if s['offside'] is None:
            s['offside'] = self.pitch.offside and s['preset'] == 'authentic'
        self.ball = Ball(self.pitch)
        self.weather = weather.pick(s['weather'], random.Random('weather%s' % seed))
        self.ball.friction = self.weather['friction']
        self.ball.skid = self.weather['skid']
        self.ball.wind = self.weather['wind_vec']
        # Small goals are close: shots arrive sooner, so keepers get a little more reach
        self.small_goal = 1.0 + max(0.0, (5.5 - self.pitch.goal_width)) * 0.3
        size = s['size']
        form = FORMATIONS[size]
        self.teams = []
        for ti, tid in enumerate((home, away)):
            info = roster.team_info(tid)
            squad = roster.squad(tid, size, self.rng)
            players = []
            team = Team(ti, info, players, 1 if ti == 0 else -1)
            for i, fb in enumerate(squad):
                role, fx, fy = form[i]
                players.append(Player(fb, team, i, role, (fx, fy)))
            self.teams.append(team)
        a, b = self.teams
        a.opp, b.opp = b, a
        if s['styles']:
            # Force a style per side (the soak tool compares styles with identical squads)
            for t, key in zip(self.teams, s['styles']):
                if key:
                    t.style = style_for(t.info['id'], key)
        # Away side changes into a neutral kit if the shirts clash
        if roster.kits_clash(a.info['shirt'], b.info['shirt']):
            b.info = dict(b.info, shirt=(0.95, 0.95, 0.95), shorts=(0.12, 0.12, 0.14), socks=(0.95, 0.95, 0.95))
        diff = DIFFICULTY[s['difficulty']]
        self.controllers = []
        for ci, ti in humans:
            c = Controller(ci, self.teams[ti])
            self.teams[ti].human = True
            self.controllers.append(c)
        for t in self.teams:
            if not t.human:
                t.speed_scale = diff['speed']
                t.error_scale = diff['error']
                t.ai_react = diff['react']
                t.ai_noise = diff['noise']
                t.press = diff['press']
            else:
                t.ai_react = 0.16
                t.ai_noise = 0.08
            t.press *= t.style['press']
            if s['preset'] == 'authentic':
                t.error_scale *= 1.35
                t.speed_scale *= 0.94
        for t in self.teams:
            t.speed_scale *= self.weather['pace']
        if s['perks']:
            # Cup Run perks belong to the home side (the player's team)
            from .cuprun import apply_perks
            apply_perks(a, s['perks'])
        self.time = 0.0             # seconds played in this half
        self.half = 1
        self.state = 'kickoff'
        self.state_t = 0.0
        self.restart = None
        self.events = []
        self.log = []               # every goal, card and shot, for the report
        self.replay = collections.deque(maxlen=int(9.0 / FIXED_DT))
        self.last_goal = None
        self.offside_set = set()
        self.offside_team = None
        self.pass_target = None     # (player, until_time) of the last pass
        self.ticks = 0
        self.shootout = None
        self.winner = None
        self.slowmo = 0.0
        self.paused = False
        from . import ai
        self.ai = [ai.TeamAI(self, t) for t in self.teams]
        self.kickoff(self.teams[0])

    # ======================================================= public helpers
    def all_players(self):
        return [p for t in self.teams for p in t.players if not p.sent_off]

    def emit(self, _type, **kw):
        kw['type'] = _type
        kw['t'] = self.clock()
        self.events.append(kw)

    def clock(self):
        """Match minute shown on the scoreboard."""
        hs = self.settings['half_seconds']
        if self.half <= 2:
            return (self.half - 1) * 45.0 + min(1.0, self.time / hs) * 45.0 + max(0.0, self.time - hs) / hs * 45.0
        return 90.0 + (self.half - 3) * 15.0 + self.time / (hs / 3.0) * 15.0

    def half_length(self):
        hs = self.settings['half_seconds']
        return hs if self.half <= 2 else hs / 3.0

    def possessor(self):
        b = self.ball
        if b.owner is not None:
            return b.owner
        if b.holder is not None:
            return b.holder
        return None

    def team_in_possession(self):
        p = self.possessor()
        if p is not None:
            return p.team
        if self.restart:
            return self.restart['team']
        return None

    # ============================================================== set-ups
    def _formation_spot(self, p, attacking=None, kickoff=False):
        pt = self.pitch
        fx, fy = p.slot
        if kickoff:
            fx = min(fx * 1.0, -0.06) if not p.keeper else fx
            fx = fx * 0.9 if not p.keeper else fx
        x = p.team.attack * fx * pt.half_length
        y = fy * pt.half_width * 0.8 * p.team.attack
        return x, y

    def kickoff(self, team):
        """Line both teams up; `team` kicks off."""
        self.state = 'kickoff'
        self.state_t = 0.0
        self.restart = dict(kind='kickoff', team=team, pos=(0.0, 0.0), t=0.0)
        self.ball.place(0.0, 0.0)
        self.offside_set = set()
        for t in self.teams:
            for p in t.players:
                if p.sent_off:
                    continue
                x, y = self._formation_spot(p, kickoff=True)
                if t is not team or not p.slot[0] > 0:
                    # Everyone in their own half, out of the centre circle
                    if abs(x) < 1.0 and abs(y) < self.pitch.circle:
                        x = -t.attack * (self.pitch.circle + 0.5)
                p.pos = [x, y]
                p.vel = [0.0, 0.0]
                p.z = 0.0
                p.set_state('run', 0.0)
                p.target = None
                p.face_towards(0.0, 0.0)
        # The taker stands over the ball, a team-mate just beside him
        taker = self._kickoff_taker(team)
        taker.pos = [-team.attack * 0.35, 0.0]
        taker.face_towards(0.0, 0.0)
        self.restart['taker'] = taker
        self._give_control(team, taker)

    def _kickoff_taker(self, team):
        outs = [p for p in team.active() if not p.keeper]
        outs.sort(key=lambda p: -p.slot[0])
        return outs[0] if outs else team.keeper()

    def _give_control(self, team, player):
        for c in self.controllers:
            if c.team is team:
                c.player = player
                c.lock_t = 0.5

    def set_piece(self, kind, team, x, y):
        """Throw-in / kick-in, corner, goal kick, free kick or penalty for team at (x, y)."""
        pt = self.pitch
        if kind == 'penalty':
            x, y = pt.spot_pos(team.attack)
        x, y = max(-pt.half_length, min(pt.half_length, x)), max(-pt.half_width, min(pt.half_width, y))
        self.state = 'restart'
        self.state_t = 0.0
        self.ball.place(x, y)
        self.offside_set = set()
        self.restart = dict(kind=kind, team=team, pos=(x, y), t=0.0)
        if kind == 'goalkick':
            taker = team.keeper() or self._nearest(team, x, y)
        elif kind == 'penalty':
            outs = [p for p in team.active() if not p.keeper]
            taker = max(outs, key=lambda p: p.fb.shooting + 0.3 * p.fb.aura)
        else:
            taker = self._nearest(team, x, y, outfield=True)
        self.restart['taker'] = taker
        # Taker steps up behind the ball, facing the play
        gx = team.opp_goal_x(pt)
        if kind == 'penalty':
            fx, fy = gx, 0.0
        elif kind == 'goalkick':
            fx, fy = 0.0, y
        else:
            fx, fy = (x + team.attack * 8.0, y * 0.5)
        dx, dy = norm(fx - x, fy - y)
        taker.pos = [x - dx * 0.55, y - dy * 0.55]
        taker.vel = [0.0, 0.0]
        taker.face_towards(x, y)
        taker.set_state('run', 0.0)
        self._give_control(team, taker)
        if kind == 'penalty':
            self._penalty_lineup(team, taker)
        self.emit('restart', kind=kind, team=team.idx)

    def _penalty_lineup(self, team, taker):
        pt = self.pitch
        gx = team.opp_goal_x(pt)
        gk = team.opp.keeper()
        if gk:
            gk.pos = [gx - team.attack * 0.15, 0.0]
            gk.vel = [0.0, 0.0]
            gk.face_towards(0.0, 0.0)
            gk.set_state('run', 0.0)
        # Everyone else waits outside the box
        line = gx - team.attack * (pt.box_depth + 1.5)
        k = 0
        for p in self.all_players():
            if p is taker or p is gk:
                continue
            if p.keeper:
                continue
            k += 1
            p.pos = [line - team.attack * (k % 2) * 1.2, (k - 4) * 1.6]
            p.target = None

    def _nearest(self, team, x, y, outfield=False):
        best, bd = None, 1e9
        for p in team.active():
            if outfield and p.keeper:
                continue
            d = p.dist_to(x, y)
            if d < bd:
                best, bd = p, d
        return best

    # ================================================================ step
    def step(self, inputs=None, dt=FIXED_DT):
        """Advance one fixed tick. inputs: {controller index: Input}."""
        self.events = []
        if self.paused:
            return self.events
        self.ticks += 1
        self.state_t += dt
        inputs = inputs or {}
        b = self.ball
        st = self.state
        if st in ('fulltime',):
            for p in self.all_players():
                p.update(dt, False, self.pitch)
            return self.events
        if st == 'halftime':
            if self.state_t > 2.5:
                self._start_half(self.half + 1)
            return self.events
        if st == 'goal':
            self._celebrate(dt)
            return self.events
        if st == 'pen_wait':
            for p in self.all_players():
                p.update(dt, False, self.pitch)
            b.step(dt)
            if b.out_of_play():
                # Over the line between kicks: the ball boy has it, it doesn't roll on into the stands
                b.vel = [0.0, 0.0, min(0.0, b.vel[2])]
            self.shootout_step(dt)
            self._record()
            return self.events

        # Clock runs in open play and during quick restarts
        if st in ('play', 'restart') and not self.shootout:
            self.time += dt
            if self.time >= self.half_length() and st == 'play' and not self._attack_on():
                self._end_half()
                return self.events

        for ai in self.ai:
            ai.update(dt)
        for c in self.controllers:
            self._human(c, inputs.get(c.index) or Input(), dt)

        if st in ('kickoff', 'restart'):
            self._restart_hold(dt)
        # Dribbling: the ball sits at the owner's feet
        if b.owner is not None:
            self._dribble(b.owner, dt)
        if b.holder is not None:
            h = b.holder
            hx, hy = h.foot_point(0.3)
            b.pos = [hx, hy, 1.1 + h.z]
            b.vel = [h.vel[0], h.vel[1], 0.0]
        for p in self.all_players():
            p.update(dt, b.owner is p, self.pitch)
        self._collide_players()
        for ev in b.step(dt):
            if ev in ('post', 'bar'):
                self.emit('woodwork', kind=ev, by=self._idx(b.last_touch))
            elif ev == 'net':
                pass
            elif ev == 'wall':
                self.emit('wall', speed=b.speed())
            elif ev == 'bounce' and b.speed() > 6:
                self.emit('bounce', speed=b.speed())
        if self.state == 'play' or (self.state in ('kickoff', 'restart') and self.restart.get('taken')):
            self._touches()
            self._slides()
            self._check_ball_rules()
        if self.state == 'restart' and self.restart.get('taken'):
            self.state = 'play'
        if self.state == 'kickoff' and self.restart.get('taken'):
            self.state = 'play'
        if self.shootout and self.state == 'play':
            self.shootout_step(dt)
        # Possession clock
        tp = self.team_in_possession() if self.state == 'play' else None
        if tp is None and b.last_touch is not None and self.state == 'play':
            tp = b.last_touch.team
        if tp is not None:
            tp.possession_t += dt
        self._record()
        return self.events

    def _attack_on(self):
        """Let a promising attack finish before the whistle (up to a few seconds)."""
        over = self.time - self.half_length()
        if over > 4.0:
            return False
        b = self.ball
        for t in self.teams:
            gx = t.opp_goal_x(self.pitch)
            if abs(b.pos[0] - gx) < self.pitch.length * 0.22 and (b.last_touch and b.last_touch.team is t):
                return True
        return False

    def _idx(self, p):
        return None if p is None else (p.team.idx, p.idx)

    # ---------------------------------------------------------- restarts
    def _restart_hold(self, dt):
        r = self.restart
        r['t'] += dt
        b = self.ball
        if r.get('taken'):
            return
        x, y = r['pos']
        b.place(x, y)
        taker = r['taker']
        # Keep the defending side back the required distance
        need = 9.15 if self.pitch.length > 80 else 4.0
        if r['kind'] == 'kickoff':
            need = self.pitch.circle
        if r['kind'] == 'penalty':
            # Everyone but the taker and the keeper stays outside the box until it's struck
            a = r['team'].attack
            line = a * (self.pitch.half_length - self.pitch.box_depth - 1.0)
            gk = r['team'].opp.keeper()
            for p in self.all_players():
                if p is not taker and p is not gk and not p.keeper and p.pos[0] * a > line * a:
                    p.pos[0] = line
        for p in r['team'].opp.active():
            if r['kind'] == 'penalty':
                continue
            d = p.dist_to(x, y)
            if d < need and not (p.keeper and r['kind'] in ('corner',)):
                dx, dy = norm(p.pos[0] - x, p.pos[1] - y)
                if dx == 0 and dy == 0:
                    dx = -r['team'].attack
                p.pos = [x + dx * need, y + dy * need]
                p.pos[0], p.pos[1] = self.pitch.clamp_inside(p.pos[0], p.pos[1], 0.3)
        if r['kind'] == 'kickoff':
            for p in self.all_players():
                if p is taker:
                    continue
                own = -p.team.attack
                if p.pos[0] * own < 0.3:
                    p.pos[0] = own * 0.3
        # Taker stays on the ball until he plays it
        if taker.dist_to(x, y) > 0.8:
            taker.target = (x - taker.dir()[0] * 0.5, y - taker.dir()[1] * 0.5)
            taker.want_speed = 6.0

    def _taken(self, by):
        r = self.restart
        if r and not r.get('taken') and self.state in ('kickoff', 'restart'):
            r['taken'] = True
            r['taken_tick'] = self.ticks
            r['by'] = by
            self.emit('restart_taken', kind=r['kind'])

    # ---------------------------------------------------------- dribbling
    def _dribble(self, p, dt):
        b = self.ball
        sp = p.speed()
        if p.busy() and p.state not in ('skill',):
            b.owner = None
            return
        dx, dy = p.dir()
        ahead = 0.5 + 0.22 * min(1.0, sp / 7.0)
        tx, ty = p.pos[0] + dx * ahead, p.pos[1] + dy * ahead
        k = min(1.0, dt * (16.0 + 6.0 * p.fb.dribbling))
        b.pos[0] += (tx - b.pos[0]) * k
        b.pos[1] += (ty - b.pos[1]) * k
        # Never dribbled over a line: he stops it with his sole
        lim = self.pitch.half_length - 0.3
        b.pos[0] = max(-lim, min(lim, b.pos[0]))
        if self.pitch.walls:
            wl = self.pitch.half_width - 0.3
            b.pos[1] = max(-wl, min(wl, b.pos[1]))
        b.pos[2] = B.RADIUS
        b.vel = [p.vel[0], p.vel[1], 0.0]
        b.spin_visual(dt)
        p.dribble_t += dt
        # Sprinting knocks the ball ahead: quicker, but it can be nicked
        if p.sprint and sp > 6.2 and p.stamina > 0.05:
            p.knock_t += dt
            if p.knock_t > 0.62 - 0.2 * p.fb.dribbling:
                p.knock_t = 0.0
                push = sp * (1.32 - 0.12 * p.fb.dribbling)
                b.owner = None
                b.kick(dx * push, dy * push, 0.0)
                b.last_touch = p
                p.touch_cd = 0.22
                self.emit('touch', who=self._idx(p), soft=True)
        else:
            p.knock_t = 0.0

    def _collide_players(self):
        ps = self.all_players()
        n = len(ps)
        for i in range(n):
            a = ps[i]
            for j in range(i + 1, n):
                c = ps[j]
                dx = c.pos[0] - a.pos[0]
                dy = c.pos[1] - a.pos[1]
                d2 = dx * dx + dy * dy
                lim = 0.72
                if d2 < lim * lim and d2 > 1e-8:
                    d = math.sqrt(d2)
                    push = (lim - d) * 0.5
                    ux, uy = dx / d, dy / d
                    # Stronger players hold their ground
                    wa = 0.5 + 0.3 * (c.fb.physical - a.fb.physical)
                    a.pos[0] -= ux * push * 2 * wa
                    a.pos[1] -= uy * push * 2 * wa
                    c.pos[0] += ux * push * 2 * (1 - wa)
                    c.pos[1] += uy * push * 2 * (1 - wa)
                    # Shoulder to shoulder: the weaker man on the ball can lose it
                    b = self.ball
                    for owner, other in ((a, c), (c, a)):
                        if b.owner is owner and other.team is not owner.team and owner.immune <= 0 \
                                and other.state == 'run' and other.speed() > 3.0:
                            chance = 0.012 * (1.0 + other.fb.physical - owner.fb.physical) * other.team.press
                            if self.rng.random() < chance:
                                b.owner = None
                                b.kick(other.vel[0] * 0.6, other.vel[1] * 0.6, 0.0)
                                b.last_touch = other
                                owner.touch_cd = 0.4
                                self.emit('tackle', who=self._idx(other), victim=self._idx(owner), kind='shoulder')
                                other.team.stats['tackles'] += 1

    # ---------------------------------------------------------- touches
    def _touches(self):
        b = self.ball
        if b.owner is not None or b.holder is not None or b.in_net:
            return
        bx, by, bz = b.pos
        best, bd, kind = None, 1e9, None
        for p in self.all_players():
            if not p.can_touch():
                continue
            # Keepers use their hands in their own box
            if p.keeper and self.pitch.in_box(bx, by, -p.team.attack) and p.state != 'down':
                reach = self._keeper_reach(p)
                if reach is not None and reach < bd:
                    best, bd, kind = p, reach, 'hands'
                    continue
            if p.state == 'slide':
                continue
            fx, fy = p.foot_point(0.28)
            d = math.hypot(bx - fx, by - fy)
            if bz < 0.75 + p.z and d < CONTROL:
                if d < bd:
                    best, bd, kind = p, d, 'feet'
            elif bz < REACH_HEAD + p.z and d < 0.75 and bz >= 0.75:
                if d < bd:
                    best, bd, kind = p, d, 'head' if bz > 1.45 else 'chest'
        if best is None:
            return
        if kind == 'hands':
            self._keeper_handle(best)
        elif kind == 'feet':
            self._first_touch(best)
        else:
            self._aerial(best, kind)

    def _note_touch(self, p):
        """Bookkeeping when someone touches the ball: offside, possession changes, pass completion."""
        b = self.ball
        prev = b.last_touch
        if self.offside_set and p.team is self.offside_team:
            if p in self.offside_set and self.settings['offside']:
                self.offside_set = set()
                self.emit('offside', who=self._idx(p))
                self.whistle('offside')
                self.set_piece('freekick', p.team.opp, p.pos[0], p.pos[1])
                return False
        if p.team is not self.offside_team:
            self.offside_set = set()
        if self.pass_target is not None:
            tgt, passer = self.pass_target
            if p.team is passer.team and p is not passer:
                passer.passes_done += 1
                passer.team.stats['passes_done'] += 1
            elif p.team is not passer.team:
                self.emit('intercept', who=self._idx(p))
                p.team.stats['interceptions'] += 1
            self.pass_target = None
        if prev is not None and prev.team is not p.team:
            self.emit('turnover', team=p.team.idx)
        b.last_touch = p
        if self.restart and self.state in ('kickoff', 'restart') and not self.restart.get('taken'):
            self._taken(p)
        return True

    def _first_touch(self, p):
        b = self.ball
        if not self._note_touch(p):
            return
        q = p.plan.get('first_time') if p.plan else None
        c = self._controller_of(p)
        if c and c.queued:
            q = c.queued
            c.queued = None
        if q:
            # One-touch pass or a first-time strike
            self._perform(p, q)
            if c is not None and c.one_two_pending and q[0] == 'through' and len(q) > 2 and q[2] is not None:
                self.emit('one_two', who=self._idx(p), to=self._idx(q[2]))
            if c is not None:
                c.one_two_pending = False
            return
        rvx, rvy = b.vel[0] - p.vel[0], b.vel[1] - p.vel[1]
        rel = math.hypot(rvx, rvy)
        limit = 11.0 + 12.0 * p.fb.dribbling
        if c is not None and math.hypot(*c.move) < 0.2:
            limit += 4.0        # stick left alone: he cushions it dead
        if rel > limit and self.rng.random() < min(0.8, (rel - limit) / 10.0 + 0.2):
            # Heavy touch: it bounces away
            b.vel = [b.vel[0] * -0.25 + p.vel[0] * 0.6 + self.rng.uniform(-2, 2),
                     b.vel[1] * -0.25 + p.vel[1] * 0.6 + self.rng.uniform(-2, 2), 0.6]
            p.touch_cd = 0.3
            self.emit('touch', who=self._idx(p), heavy=True)
            return
        if c is not None and self._push_touch(p, c):
            return
        b.owner = p
        b.vel = [p.vel[0], p.vel[1], 0.0]
        p.dribble_t = 0.0
        p.receiving = False
        self.emit('control', who=self._idx(p))
        for c in self.controllers:
            if c.team is p.team and c.player is not p and (self.settings['auto_switch'] or c.player is None):
                c.player = p
                c.charge = None

    def _push_touch(self, p, c):
        """Directional first touch: with the stick held, a sprinting player knocks the ball
        into space ahead of him, and any player can take it across his body or turn with
        it, away from where it came from. Returns True if the ball was pushed."""
        mx, my = c.move
        if math.hypot(mx, my) < 0.5 or getattr(p, 'push_tick', -10 ** 6) > self.ticks - 90:
            return False
        ux, uy = norm(mx, my)
        b = self.ball
        # Where the ball came from: pushing the stick back towards it means "come and meet it"
        fx, fy = norm(-(b.vel[0] - p.vel[0]), -(b.vel[1] - p.vel[1]))
        if fx == 0.0 and fy == 0.0:
            fx, fy = p.dir()
        turn = ux * fx + uy * fy < 0.7          # more than about 45 degrees away from it
        sprint = 'sprint' in c.held and p.stamina > 0.05
        if not (turn or sprint):
            return False
        ahead = max(0.0, p.vel[0] * ux + p.vel[1] * uy)
        speed = min(13.0, max(3.5, ahead) + (3.4 if sprint else 2.0) + 1.0 * p.fb.dribbling)
        # A touch is never perfect: a little spread, less for good dribblers
        ang = math.atan2(uy, ux) + self.rng.gauss(0.0, 0.1 * (1.2 - p.fb.dribbling) * p.team.error_scale)
        b.owner = None
        b.kick(math.cos(ang) * speed, math.sin(ang) * speed, 0.0)
        b.last_touch = p
        p.push_tick = self.ticks
        p.touch_cd = 0.14
        p.receiving = False
        p.facing = math.atan2(uy, ux)
        self.emit('touch', who=self._idx(p), soft=True, push=True)
        return True

    def _aerial(self, p, kind):
        b = self.ball
        if not self._note_touch(p):
            return
        c = self._controller_of(p)
        q = None
        if c and c.queued:
            q = c.queued
            c.queued = None
        elif p.plan and p.plan.get('first_time'):
            q = p.plan['first_time']
        pt = self.pitch
        gx = p.team.opp_goal_x(pt)
        dist_goal = math.hypot(gx - b.pos[0], b.pos[1])
        p.vz = 3.2 if b.pos[2] > 1.7 else 0.0
        if kind == 'head':
            p.set_state('kick', 0.4, 'header')
            if q and q[0] == 'shoot' or (q is None and dist_goal < 16.0 and p.team.attack * (b.pos[0] - 0) > 0):
                ty = self.rng.uniform(-1, 1) * pt.goal_width * 0.35
                if q and q[1] and abs(q[1][1]) > 0.3:
                    ty = math.copysign(pt.goal_width * 0.38, q[1][1])
                self._shot_at(p, ty, 0.4 + self.rng.uniform(-0.1, 0.5), 12.0 + 6.0 * p.fb.shooting, header=True)
            elif q and q[0] in ('pass', 'through', 'lob'):
                self._perform(p, q)
            else:
                # Defensive header: away from your own goal
                away = p.team.attack
                vx = away * (9.0 + 4.0 * p.fb.physical)
                vy = self.rng.uniform(-4, 4) + b.pos[1] * -0.1
                b.kick(vx, vy, 4.0)
                p.touch_cd = 0.3
                self.emit('header', who=self._idx(p), kind='clear')
        else:
            # Chest it down
            if q:
                self._perform(p, q)
                return
            b.kick(p.vel[0] * 0.8 + p.dir()[0] * 1.0, p.vel[1] * 0.8 + p.dir()[1] * 1.0, -1.0)
            p.touch_cd = 0.12
            self.emit('touch', who=self._idx(p), chest=True)

    def _controller_of(self, p):
        for c in self.controllers:
            if c.player is p:
                return c
        return None

    # ---------------------------------------------------------- keepers
    def _keeper_reach(self, k):
        """Distance from the ball to the keeper's reach (smaller is better), None if out of reach."""
        b = self.ball
        bx, by, bz = b.pos
        if k.state == 'dive':
            dx, dy, hz = k.dive_dir
            # Body stretched from the hip to the gloves at the height he went for
            span = 0.85 + 0.4 * k.fb.keeping
            ax, ay, az = k.pos[0], k.pos[1], 0.55 + k.z * 0.5
            hx, hy = ax + dx * span, ay + dy * span
            hz = hz + k.z * 0.5
            reach = (0.3 + 0.14 * k.fb.keeping) * k.team.reach * self.small_goal
        else:
            ax, ay, az = k.pos[0], k.pos[1], 0.15
            hx, hy, hz = k.pos[0], k.pos[1], 2.25 + k.z
            reach = (0.5 + 0.15 * k.fb.keeping) * k.team.reach * self.small_goal
        abx, aby, abz = hx - ax, hy - ay, hz - az
        L = abx * abx + aby * aby + abz * abz
        t = max(0.0, min(1.0, ((bx - ax) * abx + (by - ay) * aby + (bz - az) * abz) / L)) if L > 0 else 0.0
        qx, qy, qz = ax + abx * t, ay + aby * t, az + abz * t
        d = math.sqrt((bx - qx) ** 2 + (by - qy) ** 2 + (bz - qz) ** 2)
        return d if d < reach else None

    def _keeper_handle(self, k):
        b = self.ball
        sp = b.speed()
        shot = b.last_touch is not None and b.last_touch.team is not k.team and sp > 9.0
        if not self._note_touch(k):
            return
        catch = (9.0 + 14.0 * k.fb.handling) * self.weather['catch']
        if k.state == 'dive':
            catch *= 0.72
        if sp < catch or self.rng.random() < 0.25 * k.fb.handling:
            b.holder = k
            b.owner = None
            b.vel = [0.0, 0.0, 0.0]
            k.set_state('hold', 1.0e9)
            k.target = None
            self.emit('catch', who=self._idx(k), shot=shot, speed=sp)
        elif shot and k.state == 'dive' and self.rng.random() < 0.45:
            # Fingertips: round the post or over the bar, for a corner
            pt = self.pitch
            side = 1 if b.vel[1] >= 0 else -1
            line_x = -k.team.attack * pt.half_length
            back = 2.5 + sp * 0.08
            t = max(0.15, abs(line_x - b.pos[0]) / back)
            # Wide enough to clear the post by the time it reaches the line, or high enough to clear the bar
            vy = side * max(3.0, (pt.goal_width / 2.0 + 1.0 - side * b.pos[1]) / t)
            vz = max(2.0, (pt.goal_height + 0.6 - b.pos[2]) / t + 4.9 * t)
            b.kick(-k.team.attack * back, vy, min(vz, 12.0))
            k.touch_cd = 0.6
            self.emit('parry', who=self._idx(k), shot=shot, speed=sp, tip=True)
        else:
            # Parry it away from goal, wide if possible
            away = k.team.attack
            side = 1 if b.pos[1] >= k.pos[1] else -1
            b.kick(away * (2.0 + sp * 0.18) + self.rng.uniform(-1, 1), side * (3.0 + sp * 0.2) + self.rng.uniform(-2, 2),
                   2.5 + self.rng.uniform(0, 3))
            k.touch_cd = 0.5
            self.emit('parry', who=self._idx(k), shot=shot, speed=sp)
        if shot:
            k.saves += 1
            k.team.stats['saves'] += 1
            k.rating += 0.4
            self.emit('save', who=self._idx(k), speed=sp, caught=b.holder is k)

    def keeper_dive(self, k, tx, ty, tz, t_arrive):
        """Launch a dive towards (ty, tz) on the goal line, aiming to get there in t_arrive."""
        if k.busy():
            return
        dx, dy = tx - k.pos[0], ty - k.pos[1]
        lateral = math.hypot(dx, dy)
        ux, uy = norm(dx, dy) if lateral > 0.2 else (0.0, 0.0)
        hz = max(0.15, min(2.5, tz))
        k.dive_dir = (ux, uy, hz)
        span = 0.85 + 0.4 * k.fb.keeping
        speed = min(6.0 + 3.0 * k.fb.keeping, max(1.0, (lateral - span * 0.8) / max(0.12, t_arrive)))
        k.vel = [ux * speed, uy * speed]
        k.vz = 1.2 + 1.6 * max(0.0, tz - 1.2) if tz > 0.9 else 0.4
        k.z = 0.01
        k.set_state('dive', 0.85, 'high' if tz > 1.4 else ('low' if tz < 0.6 else 'mid'))
        if lateral < 0.7:
            k.set_state('dive', 0.5, 'block')
        k.face_towards(k.pos[0] + k.team.attack, k.pos[1])
        self.emit('dive', who=self._idx(k))

    def keeper_release(self, k, kind, target):
        """Throw or punt the ball out of the hands."""
        b = self.ball
        if b.holder is not k:
            return
        b.holder = None
        tx, ty = target
        if kind == 'throw':
            k.set_state('throw', 0.45, 'throw')
            d = math.hypot(tx - b.pos[0], ty - b.pos[1])
            v = B.roll_speed_for(d, 3.0)
            ux, uy = norm(tx - b.pos[0], ty - b.pos[1])
            b.pos[2] = 0.6
            b.kick(ux * v, uy * v, 0.0)
        else:
            k.set_state('kick', 0.5, 'punt')
            self._lofted(k, tx, ty, hang=1.0)
        k.touch_cd = 0.5
        b.last_touch = k
        self.emit('distribute', who=self._idx(k), kind=kind)

    # ---------------------------------------------------------- kicking
    def _perform(self, p, action):
        """Run a queued or AI action: (kind, direction or None, extra)."""
        kind = action[0]
        if kind == 'pass':
            self.do_pass(p, action[1], 'ground', action[2] if len(action) > 2 else None)
        elif kind == 'through':
            self.do_pass(p, action[1], 'through', action[2] if len(action) > 2 else None)
        elif kind == 'lob':
            self.do_pass(p, action[1], 'lob', action[2] if len(action) > 2 else None)
        elif kind == 'shoot':
            self.do_shoot(p, action[1], action[2] if len(action) > 2 else 0.7,
                          action[3] if len(action) > 3 else 'normal')
        elif kind == 'clear':
            self.do_clear(p)

    def pick_receiver(self, p, direction, kind):
        """Best team-mate in the direction the stick points (pass assistance)."""
        dx, dy = direction if direction and (direction[0] or direction[1]) else p.dir()
        dx, dy = norm(dx, dy)
        best, bs = None, -1e9
        for m in p.team.active():
            if m is p:
                continue
            vx, vy = m.pos[0] - p.pos[0], m.pos[1] - p.pos[1]
            d = math.hypot(vx, vy)
            if d < 1.0:
                continue
            cos = (vx * dx + vy * dy) / d
            if cos < 0.35:
                continue
            score = cos * 3.0 - d * 0.035
            if m.keeper:
                score -= 1.5
            if kind == 'through':
                score += 0.03 * p.team.attack * (m.pos[0] - p.pos[0])
            if score > bs:
                best, bs = m, score
        return best

    def lead_point(self, p, m, kind, speed_guess=14.0):
        """Where to put the ball so m runs onto it."""
        d = math.hypot(m.pos[0] - p.pos[0], m.pos[1] - p.pos[1])
        t = d / speed_guess
        if kind == 'through':
            # Into the space ahead of him, towards goal
            gx = m.team.opp_goal_x(self.pitch)
            ux, uy = norm(gx - m.pos[0], -m.pos[1] * 0.4)
            lead = 4.0 + 2.5 * m.fb.pace
            return self.pitch.clamp_inside(m.pos[0] + ux * lead + m.vel[0] * t * 0.5,
                                           m.pos[1] + uy * lead + m.vel[1] * t * 0.5, 1.0)
        return m.pos[0] + m.vel[0] * t * 0.9, m.pos[1] + m.vel[1] * t * 0.9

    def _error(self, p, base):
        """Angle error (radians) for a kick by p."""
        pressure = 0.0
        for o in p.team.opp.active():
            d = o.dist_to(*p.pos)
            if d < 2.5:
                pressure += (2.5 - d) / 2.5
        sigma = base * p.team.error_scale * (1.0 + 0.8 * min(1.5, pressure)) * (1.25 - 0.25 * min(1.0, p.stamina * 2))
        return self.rng.gauss(0.0, sigma)

    def _start_kick(self, p, anim, length=0.32):
        p.set_state('kick', length, anim)
        p.touch_cd = 0.28
        b = self.ball
        b.owner = None
        b.holder = None
        b.last_touch = p
        self._taken(p)

    def _mark_offside(self, p):
        """Freeze who is offside at the moment a team-mate plays the ball."""
        if not self.settings['offside']:
            return
        a = p.team.attack
        opp = sorted((o.pos[0] * a for o in p.team.opp.active()), reverse=True)
        second_last = opp[1] if len(opp) > 1 else 0.0
        bx = self.ball.pos[0] * a
        self.offside_set = {m for m in p.team.active()
                            if m is not p and m.pos[0] * a > 0 and m.pos[0] * a > bx + 0.2
                            and m.pos[0] * a > second_last + 0.2}
        self.offside_team = p.team

    # ---------------------------------------------------------- cage wall passes
    def bank_shot(self, sx, sy, tx, ty, arrive=8.0):
        """A ground pass from (sx, sy) off a side board of the cage to (tx, ty).
        Returns dict(wall=(x, y), speed, angle, t1, t2) for the board that suits it
        best, or None if neither works (or the pitch has no walls)."""
        pt = self.pitch
        if not pt.walls:
            return None
        W = pt.half_width - B.RADIUS
        r = B.WALL_BOUNCE / 0.9         # the board keeps 62% of the speed across it, 90% along it
        D = tx - sx
        best = None
        for side in (-1, 1):
            wy = side * W
            a, bb = abs(wy - sy), abs(wy - ty)
            if a < 1.5 or bb < 1.0:
                continue
            # Angle in and out differ because the board deadens the ball more across it
            dx1 = D / (1.0 + bb / (r * a))
            wx = sx + dx1
            if abs(wx) > pt.half_length - 1.0:
                continue
            l1 = math.hypot(dx1, a)
            l2 = math.hypot(D - dx1, bb)
            if l1 < 2.0 or l2 < 2.0:
                continue
            cosi, sini = abs(dx1) / l1, a / l1
            keep = math.hypot(0.9 * cosi, B.WALL_BOUNCE * sini)
            v_out = B.roll_speed_for(l2, arrive)
            v0 = B.roll_speed_for(l1, v_out / keep)
            if v0 > 30.0:
                continue
            t1 = B.roll_time(v0, l1) or 9.0
            t2 = B.roll_time(v_out, l2) or 9.0
            cand = dict(wall=(wx, wy), speed=v0, angle=math.atan2(wy - sy, dx1), t1=t1, t2=t2, length=l1 + l2)
            if best is None or cand['length'] < best['length']:
                best = cand
        return best

    def lane_safety(self, team, sx, sy, tx, ty, speed=14.0, t0=0.0):
        """Seconds of margin before the nearest opponent of team could cut out a ball
        rolling from (sx, sy) to (tx, ty), starting t0 seconds from now."""
        dx, dy = tx - sx, ty - sy
        L = math.hypot(dx, dy)
        if L < 0.5:
            return 2.0
        ux, uy = dx / L, dy / L
        worst = 3.0
        for o in team.opp.active():
            ox, oy = o.pos[0] - sx, o.pos[1] - sy
            along = ox * ux + oy * uy
            if along < -1.0:
                continue
            along = min(along, L)
            perp = abs(ox * -uy + oy * ux) if along < L else math.hypot(o.pos[0] - tx, o.pos[1] - ty)
            t_ball = t0 + along / speed + 0.1
            reach = 0.9 if not o.keeper else 1.6
            t_opp = max(0.0, perp - reach) / max(4.0, o.top_speed() * 0.8) + 0.18
            worst = min(worst, t_opp - t_ball)
        return worst

    def pass_lane(self, p, tx, ty):
        """(safety, bank) for a ground pass from p to (tx, ty): bank is a bank_shot()
        dict when playing it off the boards is clearly safer than straight, else None."""
        sx, sy = self.ball.pos[0], self.ball.pos[1]
        direct = self.lane_safety(p.team, sx, sy, tx, ty)
        if direct > 0.15 or not self.pitch.walls:
            return direct, None
        bk = self.bank_shot(sx, sy, tx, ty)
        if bk is None:
            return direct, None
        wx, wy = bk['wall']
        l1 = math.hypot(wx - sx, wy - sy)
        safe = min(self.lane_safety(p.team, sx, sy, wx, wy, speed=l1 / max(0.2, bk['t1'])),
                   self.lane_safety(p.team, wx, wy, tx, ty, t0=bk['t1']))
        if safe > direct + 0.1 and safe > -0.25:
            return safe, bk
        return direct, None

    def do_pass(self, p, direction, kind='ground', receiver=None):
        b = self.ball
        if receiver is None:
            receiver = self.pick_receiver(p, direction, kind)
        if kind == 'lob' and receiver is None and direction:
            tx, ty = p.pos[0] + direction[0] * 22.0, p.pos[1] + direction[1] * 22.0
        elif receiver is None:
            dx, dy = norm(*direction) if direction and (direction[0] or direction[1]) else p.dir()
            tx, ty = p.pos[0] + dx * 12.0, p.pos[1] + dy * 12.0
        else:
            tx, ty = self.lead_point(p, receiver, kind)
        self._mark_offside(p)
        p.passes += 1
        p.team.stats['passes'] += 1
        self._start_kick(p, 'pass' if kind != 'lob' else 'lob')
        if kind == 'lob':
            self._lofted(p, tx, ty)
        else:
            bank = self.pass_lane(p, tx, ty)[1] if kind == 'ground' and receiver is not None else None
            if bank is not None:
                # Off the boards: aim at the wall, and the bounce takes it on to him
                v = bank['speed']
                ang = bank['angle'] + self._error(p, 0.03 + 0.05 * (1 - p.fb.passing))
                tx, ty = bank['wall']
                self.emit('bank', who=self._idx(p), wall=bank['wall'])
            else:
                d = math.hypot(tx - b.pos[0], ty - b.pos[1])
                arrive = 4.0 if kind == 'ground' else 5.0
                v = min(30.0, B.roll_speed_for(d, arrive) + (1.2 if d > 10 else 0.4))
                ang = math.atan2(ty - b.pos[1], tx - b.pos[0]) + self._error(p, 0.035 + 0.06 * (1 - p.fb.passing))
            b.kick(math.cos(ang) * v, math.sin(ang) * v, 0.0)
        p.face_towards(tx, ty)
        if receiver is not None:
            self.pass_target = (receiver, p)
            receiver.receiving = True
            # The human follows the ball to the receiver
            for c in self.controllers:
                if c.player is p and self.settings['auto_switch']:
                    c.player = receiver
                    c.lock_t = 0.3
        else:
            self.pass_target = (None, p)
        self.emit('pass', who=self._idx(p), kind=kind, to=self._idx(receiver))
        self.last_pass = dict(team=p.team.idx, kind=kind, tick=self.ticks)

    def _lofted(self, p, tx, ty, hang=None):
        b = self.ball
        d = math.hypot(tx - b.pos[0], ty - b.pos[1])
        T = hang if hang else 0.7 + d * 0.042
        T = max(0.6, T)
        err = self._error(p, 0.03 + 0.05 * (1 - p.fb.passing))
        ang = math.atan2(ty - b.pos[1], tx - b.pos[0]) + err
        vh = d / T * (1.0 + B.DRAG * d * 0.55)
        vz = 0.5 * B.GRAVITY * T
        spin_axis = (-math.sin(ang) * -12.0, math.cos(ang) * -12.0, 0.0)  # backspin holds it up
        b.kick(math.cos(ang) * vh, math.sin(ang) * vh, vz, spin=spin_axis)

    def do_clear(self, p):
        a = p.team.attack
        tx = p.pos[0] + a * self.rng.uniform(22, 32)
        ty = p.pos[1] * 0.5 + self.rng.uniform(-8, 8)
        tx, ty = self.pitch.clamp_inside(tx, ty, 2.0)
        self._mark_offside(p)
        self._start_kick(p, 'lob', 0.4)
        self._lofted(p, tx, ty, hang=1.4)
        self.pass_target = (None, p)
        self.emit('clear', who=self._idx(p))

    def shot_target(self, p, direction):
        """Turn the stick into a spot in the goal: up/down on the stick picks the post."""
        pt = self.pitch
        hw = pt.goal_width / 2.0
        gx = p.team.opp_goal_x(pt)
        if direction and abs(direction[1]) > 0.25:
            ty = math.copysign(hw - 0.45, direction[1]) * min(1.0, abs(direction[1]) * 1.3)
        else:
            # No preference: far post from where he is standing
            ty = -math.copysign(hw - 0.55, p.pos[1]) if abs(p.pos[1]) > 0.5 else (hw - 0.6) * self.rng.choice((-1, 1))
        return gx, ty

    def do_shoot(self, p, direction, power, style='normal'):
        b = self.ball
        pt = self.pitch
        gx, ty = self.shot_target(p, direction)
        power = max(0.0, min(1.0, power))
        if style == 'chip':
            tz = pt.goal_height * 0.75
            self._start_kick(p, 'chip')
            dist = math.hypot(gx - b.pos[0], ty - b.pos[1])
            T = 0.9 + dist * 0.045
            err = self._error(p, 0.03 + 0.05 * (1 - p.fb.shooting))
            ang = math.atan2(ty - b.pos[1], gx - b.pos[0]) + err
            vh = dist / T * (1.0 + B.DRAG * dist * 0.5)
            # Lands under the bar: aim the peak short of the line
            vz = (tz - b.pos[2]) / T + 0.5 * B.GRAVITY * T
            b.kick(math.cos(ang) * vh, math.sin(ang) * vh, vz, spin=(math.sin(ang) * 8, -math.cos(ang) * 8, 0.0))
            self._shot_bookkeeping(p, power, style)
            return
        # Height rises with power; a blasted shot can fly over
        tz = 0.35 + power * 1.25 + max(0.0, power - 0.82) * 4.5 * (1.1 - p.fb.shooting)
        speed = (13.0 + 17.0 * power) * (0.8 + 0.3 * p.fb.shooting) * p.team.shot_power
        if style == 'finesse':
            speed *= 0.82
            tz = min(tz, 1.8)
        self._shot_at(p, ty, tz, speed, style=style, power=power)

    def _shot_at(self, p, ty, tz, speed, style='normal', power=0.7, header=False):
        b = self.ball
        pt = self.pitch
        gx = p.team.opp_goal_x(pt)
        self._start_kick(p, 'header' if header else ('finesse' if style == 'finesse' else 'shoot'), 0.38)
        base = (0.022 + 0.05 * (1 - p.fb.shooting) + (0.03 if header else 0.0)) * self.small_goal ** 0.5
        # Shooting across the body or on the run is harder
        want = math.atan2(ty - b.pos[1], gx - b.pos[0])
        turn = abs(ang_diff(want, p.facing))
        base *= 1.0 + 0.6 * min(1.0, turn / 1.6) + 0.045 * p.speed() + (0.25 if p.sprint else 0.0)
        if power > 0.85:
            base *= 1.0 + (power - 0.85) * 3.0
        err_h = self._error(p, base)
        err_v = self._error(p, base * 0.7)
        dist = math.hypot(gx - b.pos[0], ty - b.pos[1])
        curl = 0.0
        if style == 'finesse':
            # Bend it: aim outside the post and let the spin bring it back
            side = 1.0 if ty > b.pos[1] else -1.0
            curl = -side * p.team.attack * (35.0 + 20.0 * p.fb.shooting)
            t_est = dist / speed
            bend = 0.5 * B.MAGNUS * abs(curl) * speed * t_est * t_est
            want = math.atan2(ty + side * bend * 0.8 - b.pos[1], gx - b.pos[0])
        ang = want + err_h
        t = dist / max(5.0, speed)
        vh = speed * (1.0 + B.DRAG * dist * 0.5)
        vz = (tz - b.pos[2]) / t + 0.5 * B.GRAVITY * t + err_v * 8.0
        knuckle = 2.5 if (style == 'normal' and power > 0.9 and self.rng.random() < 0.25) else 0.0
        b.kick(math.cos(ang) * vh, math.sin(ang) * vh, vz, spin=(0.0, 0.0, curl), knuckle=knuckle)
        p.face_towards(gx, ty)
        self._shot_bookkeeping(p, power, style, header)

    def _shot_bookkeeping(self, p, power, style, header=False):
        self.shot_from = dict(team=p.team.idx, x=p.pos[0], y=p.pos[1], tick=self.ticks, header=header)
        p.shots += 1
        p.team.stats['shots'] += 1
        xg = self.xg(p.pos[0], p.pos[1], p.team)
        if header:
            xg *= 0.6
        p.team.xg += xg
        self.pass_target = None
        self.offside_set = set()
        self.last_shot = dict(by=p, t=self.ticks, xg=xg)
        self.emit('shot', who=self._idx(p), power=power, style=style, xg=xg, header=header)

    def xg(self, x, y, team):
        """Chance quality from distance and angle (0..1), for the AI and the stats."""
        pt = self.pitch
        gx = team.opp_goal_x(pt)
        d = math.hypot(gx - x, y)
        ang = pt.goal_angle(x, y, team.attack)
        scale = pt.goal_width / 7.32
        v = 1.0 / (1.0 + math.exp(-(-1.1 + 1.6 * ang / scale - 0.11 * d / max(0.6, scale) * 0.9)))
        return max(0.005, min(0.95, v))

    def do_tackle(self, p):
        """Standing tackle on whoever has the ball."""
        b = self.ball
        if p.tackle_cd > 0 or p.busy():
            return False
        o = b.owner
        p.tackle_cd = 0.9
        p.set_state('tackle', 0.35, 'stand')
        if o is None or o.team is p.team:
            return False
        d = math.hypot(b.pos[0] - p.pos[0], b.pos[1] - p.pos[1])
        if d > 1.55:
            return False
        behind = False
        if o.immune > 0:
            chance = 0.1
        else:
            # From the front it's easier than from behind
            behind = abs(ang_diff(math.atan2(p.pos[1] - o.pos[1], p.pos[0] - o.pos[0]), o.facing)) > 2.0
            chance = 0.42 + 0.55 * p.fb.defending - 0.38 * o.fb.dribbling + 0.1 * (p.fb.physical - o.fb.physical)
            chance += 0.12 if not behind else -0.15
            if o.sprint:
                chance += 0.08
        if self.rng.random() < max(0.08, min(0.9, chance)):
            b.owner = None
            # Toe-poke: either it's his or it pops loose
            if self.rng.random() < 0.55:
                b.owner = p
                b.last_touch = p
            else:
                dx, dy = p.dir()
                b.kick(dx * 4.0 + self.rng.uniform(-2, 2), dy * 4.0 + self.rng.uniform(-2, 2), 0.0)
                b.last_touch = p
            o.touch_cd = 0.45
            p.tackles += 1
            p.team.stats['tackles'] += 1
            self.emit('tackle', who=self._idx(p), victim=self._idx(o), kind='stand')
            if b.owner is p:
                for c in self.controllers:
                    if c.team is p.team and self.settings['auto_switch']:
                        c.player = p
            return True
        # Missed: a moment to recover; sometimes he clips the man
        p.set_state('tackle', 0.55, 'miss')
        if self.weather['slip'] and self.rng.random() < self.weather['slip']:
            # Wet grass: his standing foot goes
            p.set_state('down', 0.9, 'slip')
            self.emit('slip', who=self._idx(p))
        if behind and o.immune <= 0:
            if self.settings['fouls'] and self.rng.random() < 0.25:
                self._foul(p, o, severity=0.4)
        return False

    def do_slide(self, p, direction=None):
        if p.tackle_cd > 0 or p.busy():
            return
        dx, dy = norm(*direction) if direction and (direction[0] or direction[1]) else p.dir()
        p.facing = math.atan2(dy, dx)
        sp = max(p.speed(), 5.0) + 2.0
        p.vel = [dx * sp, dy * sp]
        p.set_state('slide', 0.75, 'slide')
        p.tackle_cd = 1.4
        p.slide_hit = False
        self.emit('slide', who=self._idx(p))

    def _slides(self):
        b = self.ball
        for p in self.all_players():
            if p.state != 'slide' or p.state_t > 0.6 or getattr(p, 'slide_hit', False):
                continue
            fx, fy = p.foot_point(0.75)
            got_ball = math.hypot(b.pos[0] - fx, b.pos[1] - fy) < 0.85 and b.pos[2] < 0.5 and b.holder is None
            victim = None
            for o in p.team.opp.active():
                if o.state in ('down', 'getup') or o.keeper and b.holder is o:
                    continue
                if math.hypot(o.pos[0] - fx, o.pos[1] - fy) < 0.75:
                    victim = o
                    break
            if got_ball:
                p.slide_hit = True
                owner = b.owner
                b.owner = None
                dx, dy = p.dir()
                b.kick(dx * 7.0 + p.vel[0] * 0.3, dy * 7.0 + p.vel[1] * 0.3, 0.4)
                b.last_touch = p
                if owner is not None and owner.team is not p.team:
                    owner.touch_cd = 0.5
                    p.tackles += 1
                    p.team.stats['tackles'] += 1
                    self.emit('tackle', who=self._idx(p), victim=self._idx(owner), kind='slide')
                    if victim is owner:
                        # Won the ball, then took the man: fair
                        owner.set_state('down', 0.6, 'trip')
                return
            if victim is not None:
                p.slide_hit = True
                behind = abs(ang_diff(p.facing, victim.facing)) < 1.0
                victim.set_state('down', 1.1, 'trip')
                if b.owner is victim:
                    b.owner = None
                    b.kick(victim.vel[0] * 0.5, victim.vel[1] * 0.5, 0.0)
                if self.settings['fouls']:
                    self._foul(p, victim, severity=0.7 if behind else 0.45)
                return

    def _foul(self, p, victim, severity=0.5):
        pt = self.pitch
        self.emit('foul', who=self._idx(p), victim=self._idx(victim))
        p.team.stats['fouls'] += 1
        victim.set_state('down', 1.0, 'trip')
        team = victim.team
        x, y = victim.pos
        card = None
        if self.settings['cards']:
            # Last man denying a clear run on goal sees red
            a = team.attack
            last_man = all(o.pos[0] * a < x * a or o is p or o.keeper for o in p.team.active())
            r = self.rng.random()
            # (only when the run was heading for goal from close enough to score)
            near = abs(team.opp_goal_x(pt) - x) < pt.length * 0.3
            if last_man and near and severity > 0.6 and r < 0.7:
                card = 'red'
            elif r < severity * 0.32:
                card = 'yellow'
        if card == 'yellow':
            p.yellow += 1
            if p.yellow >= 2:
                card = 'red'
        if card == 'red' and len(p.team.active()) <= self.min_players():
            # Too few left to play on: the referee keeps it to a yellow
            card = 'yellow'
        if card:
            self.emit('card', who=self._idx(p), card=card)
            self.log.append(dict(kind=card, team=p.team.idx, name=p.fb.name, minute=int(self.clock()) + 1))
            p.team.stats['yellows' if card == 'yellow' else 'reds'] += 1
            if card == 'red':
                self._send_off(p)
        self.whistle('foul')
        if pt.in_box(x, y, team.attack):
            self.set_piece('penalty', team, x, y)
            self.emit('penalty_awarded', team=team.idx)
        else:
            self.set_piece('freekick', team, x, y)

    def min_players(self):
        """Fewest players a side can be reduced to (7 of 11, as in the laws; scaled for small-sided)."""
        size = self.settings['size']
        return {5: 3, 7: 5}.get(size, max(3, size - 4))

    def _send_off(self, p):
        p.sent_off = True
        p.pos = [0.0, -self.pitch.half_width - 6.0]
        if self.ball.owner is p:
            self.ball.owner = None
        for c in self.controllers:
            if c.player is p:
                c.player = None

    def do_skill(self, p, direction):
        """A quick feint: a burst sideways that a tackler can't read."""
        if p.busy() or self.ball.owner is not p:
            return
        dx, dy = norm(*direction) if direction and (direction[0] or direction[1]) else (-p.dir()[1], p.dir()[0])
        p.vel = [dx * (4.5 + 2.5 * p.fb.dribbling), dy * (4.5 + 2.5 * p.fb.dribbling)]
        p.facing = math.atan2(dy, dx)
        p.immune = 0.35 + 0.35 * p.fb.dribbling
        p.state = 'skill'
        p.state_t = 0.0
        p.state_len = 0.35
        p.anim = self.rng.choice(['stepover', 'roulette', 'dragback'])
        self.emit('skill', who=self._idx(p), kind=p.anim)

    def whistle(self, why):
        self.emit('whistle', why=why)

    # ---------------------------------------------------------- the rules
    def _check_ball_rules(self):
        b = self.ball
        if b.holder is not None:
            return
        side = b.goal_side()
        if side:
            scorer_team = self.teams[0] if self.teams[0].attack == side else self.teams[1]
            self._goal(scorer_team)
            return
        out = b.out_of_play()
        if out is None:
            return
        last = b.last_touch
        if out[0] == 'touch':
            team = last.team.opp if last else self.teams[0]
            x = max(-self.pitch.half_length + 1, min(self.pitch.half_length - 1, b.pos[0]))
            self.set_piece('throwin', team, x, out[1] * self.pitch.half_width)
            self.emit('out', kind='throwin')
        else:
            end = out[1]
            defending = self.teams[0] if -self.teams[0].attack == end else self.teams[1]
            attacking = defending.opp
            if last is not None and last.team is defending:
                y = math.copysign(self.pitch.half_width, b.pos[1])
                self.set_piece('corner', attacking, end * self.pitch.half_length, y)
                attacking.stats['corners'] += 1
                self.emit('out', kind='corner')
            else:
                x = end * (self.pitch.half_length - max(2.0, self.pitch.six_depth))
                self.set_piece('goalkick', defending, x, 0.0)
                self.emit('out', kind='goalkick')

    def _goal(self, team):
        b = self.ball
        scorer = b.last_touch
        own = scorer is not None and scorer.team is not team
        if self.shootout:
            self._shootout_result(True)
            return
        team.score += 1
        if scorer is not None and not own:
            scorer.goals += 1
            scorer.rating += 1.0
        minute = int(self.clock()) + 1
        assist = None
        self.last_goal = dict(team=team.idx, scorer=self._idx(scorer), own=own, minute=minute, tick=self.ticks)
        self.log.append(dict(kind='goal', team=team.idx, name=(scorer.fb.name if scorer else '?'), own=own,
                             minute=minute, how=self._goal_type(team, own)))
        self.emit('goal', team=team.idx, scorer=self._idx(scorer), own=own, assist=assist,
                  speed=b.speed(), score=(self.teams[0].score, self.teams[1].score))
        self.state = 'goal'
        self.state_t = 0.0
        b.owner = None
        self.goal_team = team
        self.goal_scorer = scorer if not own else None
        for p in team.active():
            p.set_state('celebrate', 3.2, 'run')

    def _celebrate(self, dt):
        """Scorer wheels away, team-mates pile on; then back for the kick-off."""
        b = self.ball
        b.step(dt)
        team = self.goal_team
        s = self.goal_scorer
        corner = (team.attack * (self.pitch.half_length - 4.0), math.copysign(self.pitch.half_width - 3.0,
                                                                                (s.pos[1] if s else 1.0) or 1.0))
        for p in self.all_players():
            if p.team is team:
                p.target = corner if p is s else ((s.pos[0], s.pos[1]) if s else corner)
                p.want_speed = 7.5 if p is s else 6.5
                p.state = 'celebrate'
            else:
                p.target = None
            p.update(dt, False, self.pitch)
        self._collide_players()
        self._record()
        if self.state_t > 3.6:
            if self.settings.get('golden_goal') and self.half > 2:
                self._full_time()
                return
            self.kickoff(team.opp)

    # ---------------------------------------------------------- halves
    def _goal_type(self, team, own):
        """How a goal came about, for the AI's half-time talk: through, cross, long, close or own."""
        if own:
            return 'own'
        sh, ps = getattr(self, 'shot_from', None), getattr(self, 'last_pass', None)
        if sh and sh['team'] == team.idx and self.ticks - sh['tick'] < 180:
            gx = team.opp_goal_x(self.pitch)
            if math.hypot(gx - sh['x'], sh['y']) > self.pitch.length * 0.2 and not sh['header']:
                return 'long'
        if ps and ps['team'] == team.idx and self.ticks - ps['tick'] < 300:
            if ps['kind'] == 'through':
                return 'through'
            if ps['kind'] == 'lob':
                return 'cross'
        return 'close'

    def _end_half(self):
        self.whistle('half' if self.half < 2 else 'full')
        level = self.teams[0].score == self.teams[1].score
        if self.half == 1:
            self.state = 'halftime'
            self.state_t = 0.0
            self.emit('halftime')
            for t_ai in self.ai:
                t_ai.half_time_talk()
        elif self.half == 2 and level and self.settings['extra_time']:
            self.state = 'halftime'
            self.state_t = 0.0
            self.emit('extratime')
        elif self.half == 3:
            self.state = 'halftime'
            self.state_t = 0.0
        elif level and self.settings['decider'] == 'penalties' and self.half >= 2:
            self.start_shootout()
        else:
            self._full_time()

    def _start_half(self, half):
        self.half = half
        self.time = 0.0
        for t in self.teams:
            t.attack = -t.attack
            for p in t.players:
                p.stamina = min(1.0, p.stamina + 0.35)
        # Second half: the other side kicks off
        self.kickoff(self.teams[1] if half % 2 == 0 else self.teams[0])
        self.emit('kickoff', half=half)

    def _full_time(self):
        self.state = 'fulltime'
        self.state_t = 0.0
        a, b = self.teams
        if a.score != b.score:
            self.winner = a if a.score > b.score else b
        elif self.shootout:
            pa, pb = sum(a.pens), sum(b.pens)
            self.winner = a if pa > pb else b
        else:
            self.winner = None
        for t in self.teams:
            for p in t.active():
                p.target = None
                if self.winner is t:
                    p.set_state('celebrate', 1e9, 'win')
        self.emit('fulltime', winner=None if self.winner is None else self.winner.idx)

    # ---------------------------------------------------------- penalties
    def start_shootout(self):
        self.shootout = dict(turn=0, kick=0, order=[], t=0.0, done=False, result=None)
        for t in self.teams:
            t.pens = []
            outs = [p for p in t.active() if not p.keeper]
            outs.sort(key=lambda p: -(p.fb.shooting * 0.7 + p.fb.aura * 0.3))
            self.shootout['order'].append(outs + [t.keeper()] if t.keeper() else outs)
        self.emit('shootout')
        self._next_penalty()

    def _next_penalty(self):
        so = self.shootout
        t = self.teams[so['turn']]
        order = so['order'][so['turn']]
        taker = order[len(t.pens) % len(order)]
        self.set_piece('penalty', t, 0.0, 0.0)
        r = self.restart
        # set_piece picked the best taker; the shootout uses the running order
        old = r['taker']
        r['taker'] = taker
        x, y = r['pos']
        taker.pos = [x - t.attack * 0.55, y]
        taker.face_towards(x, y)
        if old is not taker:
            old.pos = [0.0, (old.idx - 3) * 1.5]
        self._give_control(t, taker)
        self._penalty_lineup(t, taker)
        # Everyone else in the centre circle
        for p in self.all_players():
            if p is not taker and p is not t.opp.keeper():
                p.pos = [0.0 + (p.team.idx - 0.5) * 2.0, (p.idx - 3) * 1.4]
                p.target = None
        so['t'] = 0.0
        so['resolved'] = False

    def _shootout_result(self, scored):
        so = self.shootout
        if so.get('resolved'):
            return
        so['resolved'] = True
        t = self.teams[so['turn']]
        t.pens.append(1 if scored else 0)
        self.emit('pen_result', team=t.idx, scored=scored, pens=([*self.teams[0].pens], [*self.teams[1].pens]))
        self.state = 'pen_wait'
        self.state_t = 0.0

    def shootout_over(self):
        a, b = self.teams[0].pens, self.teams[1].pens
        na, nb = len(a), len(b)
        sa, sb = sum(a), sum(b)
        if na <= 5 and nb <= 5:
            # Can't be caught any more
            if sa > sb + (5 - nb) or sb > sa + (5 - na):
                return True
            return na == 5 and nb == 5 and sa != sb
        return na == nb and sa != sb

    def shootout_step(self, dt):
        """Called by step() while a penalty is live or between kicks."""
        so = self.shootout
        b = self.ball
        if self.state == 'pen_wait':
            if self.state_t > 1.8:
                if self.shootout_over():
                    self._full_time()
                else:
                    so['turn'] = 1 - so['turn']
                    self._next_penalty()
            return
        if self.state == 'play':
            so['t'] += dt
            gone = b.speed() < 1.0 and so['t'] > 1.0
            missed = b.out_of_play() is not None or b.holder is not None or so['t'] > 4.0 or gone
            # Ball going away from goal after a save or the woodwork
            t = self.teams[so['turn']]
            if b.last_touch is not None and b.last_touch.team is not t and so['t'] > 0.3 and b.speed() < 4.0:
                missed = True
            if b.vel[0] * t.attack < -1.0 and so['t'] > 0.4:
                missed = True
            if missed:
                self._shootout_result(False)

    # ---------------------------------------------------------- humans
    def time_to_ball(self, p):
        """Rough time for p to reach the ball, following its path."""
        b = self.ball
        if b.owner is not None or b.holder is not None:
            return p.dist_to(b.pos[0], b.pos[1]) / max(3.0, p.top_speed())
        top = max(3.0, p.top_speed())
        for i, q in enumerate(b.path(2.5, 0.1)):
            t = (i + 1) * 0.1
            if q[2] < 2.0 and math.hypot(q[0] - p.pos[0], q[1] - p.pos[1]) - 0.6 <= top * t:
                return t
        q = b.path(2.5, 0.5)[-1]
        return 2.5 + math.hypot(q[0] - p.pos[0], q[1] - p.pos[1]) / top

    def switch_target(self, c, move):
        team = c.team
        cur = c.player
        cands = [p for p in team.active() if not p.keeper and p is not cur]
        if not cands:
            return cur
        mx, my = move
        if math.hypot(mx, my) > 0.4 and cur is not None:
            # Right-stick style: the team-mate in the direction pushed
            ux, uy = norm(mx, my)
            best, bs = None, -1e9
            for p in cands:
                vx, vy = p.pos[0] - cur.pos[0], p.pos[1] - cur.pos[1]
                d = math.hypot(vx, vy) or 1.0
                s = (vx * ux + vy * uy) / d * 2.0 - d * 0.03
                if s > bs:
                    best, bs = p, s
            return best
        return min(cands, key=self.time_to_ball)

    def _auto_switch(self, c):
        if not self.settings['auto_switch'] or c.lock_t > 0 or c.charge is not None:
            return
        b = self.ball
        p = c.player
        if b.owner is not None and b.owner.team is c.team:
            return
        if b.holder is not None and b.holder.team is c.team:
            return
        if self.pass_target and self.pass_target[1].team is c.team and self.pass_target[0] is not None:
            return
        cands = [q for q in c.team.active() if not q.keeper]
        if not cands:
            return
        best = min(cands, key=self.time_to_ball)
        if p is None or p.sent_off or p.keeper or (best is not p and
                                                   self.time_to_ball(p) > self.time_to_ball(best) + 0.45):
            c.player = best
            c.lock_t = 0.6

    def _human(self, c, inp, dt):
        c.lock_t = max(0.0, c.lock_t - dt)
        c.move = inp.move
        c.held = frozenset(inp.held)
        c.tackle_t = max(0.0, c.tackle_t - dt)
        b = self.ball
        if c.queued is not None:
            c.queue_t -= dt
            if c.queue_t <= 0:
                c.queued = None
        r = self.restart
        taking = self.state in ('kickoff', 'restart') and r and r['team'] is c.team and not r.get('taken')
        if taking:
            c.player = r['taker']
        if 'switch' in inp.pressed and not taking:
            c.player = self.switch_target(c, inp.move)
            c.lock_t = 1.2
            c.charge = None
            self.emit('switch', who=self._idx(c.player))
        if not taking:
            self._auto_switch(c)
        p = c.player
        if p is None or p.sent_off:
            return
        if c.one_two is not None and self._one_two(c, p, inp, dt):
            return
        mx, my = inp.move
        mag = min(1.0, math.hypot(mx, my))
        stick = norm(mx, my) if mag > 0.2 else None
        p.sprint = 'sprint' in inp.held
        finesse = 'finesse' in inp.held

        # Penalties, free kicks and the rest: stand over the ball and pick the option
        facing_pen = self.state in ('kickoff', 'restart') and r and r['kind'] == 'penalty' and \
            r['team'] is not c.team and not r.get('taken')
        if facing_pen:
            self._penalty_keeper(c, inp)
            return
        if taking and r['kind'] == 'penalty':
            self._penalty_taker(c, p, inp, dt, finesse)
            return
        if taking:
            if stick:
                p.facing = math.atan2(stick[1], stick[0]) if r['kind'] != 'penalty' else p.facing
            if r['kind'] == 'penalty' or (r['kind'] == 'freekick' and self.xg(r['pos'][0], r['pos'][1], c.team) > 0.04):
                if 'shoot' in inp.pressed:
                    c.charge = 0.0
            if c.charge is not None and 'shoot' in inp.held:
                c.charge = min(1.0, c.charge + dt * 1.05)
            if c.charge is not None and 'shoot' in inp.released:
                self.do_shoot(p, stick, c.charge, 'finesse' if finesse else 'normal')
                c.charge = None
                return
            if r['kind'] == 'penalty':
                return
            kind = None
            for k in ('pass', 'through', 'lob'):
                if k in inp.pressed:
                    kind = k
            if kind:
                if kind == 'lob' or r['kind'] in ('corner',) and kind != 'pass':
                    self.do_pass(p, stick or p.dir(), 'lob')
                else:
                    self.do_pass(p, stick or p.dir(), 'ground' if kind == 'pass' else 'through')
            return

        # Keeper with the ball in his hands (only when you've switched to him)
        if b.holder is p:
            if 'pass' in inp.pressed or 'through' in inp.pressed:
                m = self.pick_receiver(p, stick, 'ground')
                if m:
                    self.keeper_release(p, 'throw', (m.pos[0], m.pos[1]))
            elif 'lob' in inp.pressed or 'shoot' in inp.pressed:
                tx = p.pos[0] + p.team.attack * 30
                self.keeper_release(p, 'punt', self.pitch.clamp_inside(tx, (stick[1] if stick else 0) * 10, 2))
            return

        if not p.busy():
            if stick:
                p.target = (p.pos[0] + stick[0] * 4.0, p.pos[1] + stick[1] * 4.0)
                p.want_speed = p.top_speed(b.owner is p) * mag
            else:
                p.target = None

        # Late press: the ball has only just slipped off his foot (a sprint knock-on or a
        # push touch), so a pass or shot pressed now still plays it
        if b.owner is p:
            c.owned_tick = self.ticks
        elif self._late_grace(c, p) and (inp.pressed & {'pass', 'through', 'lob', 'shoot'}):
            b.owner = p
            b.vel = [p.vel[0], p.vel[1], 0.0]
            c.owned_tick = self.ticks

        if b.owner is p:
            if 'shoot' in inp.pressed:
                c.charge = 0.0
            if c.charge is not None:
                if 'shoot' in inp.held:
                    c.charge = min(1.0, c.charge + dt * 1.05)
                if 'shoot' in inp.released:
                    self.do_shoot(p, stick, c.charge, 'finesse' if finesse else 'normal')
                    c.charge = None
                    return
            if 'pass' in inp.pressed:
                self.do_pass(p, stick, 'ground')
                if self.pass_target and self.pass_target[0] is not None and c.player is not p:
                    c.one_two = dict(runner=p, t=0.0, running=False)
            elif 'through' in inp.pressed:
                self.do_pass(p, stick, 'through')
            elif 'lob' in inp.pressed:
                if finesse:
                    self.do_shoot(p, stick, 0.6, 'chip')
                else:
                    self.do_pass(p, stick, 'lob')
            elif 'skill' in inp.pressed:
                self.do_skill(p, stick)
            return

        if c.charge is not None and 'shoot' in inp.released:
            # Let go after losing the ball: try a first-time strike if it comes back
            c.queued = ('shoot', stick, c.charge, 'finesse' if finesse else 'normal')
            c.queue_t = 0.5
            c.charge = None
        elif c.charge is not None and 'shoot' not in inp.held:
            c.charge = None

        opp_has = (b.owner is not None and b.owner.team is not c.team) or \
            (b.holder is not None and b.holder.team is not c.team)
        if opp_has:
            o = b.owner
            if 'pass' in inp.held and o is not None and not p.busy():
                # Contain: get goal-side of the man and close him down
                gx = c.team.own_goal_x(self.pitch)
                ux, uy = norm(gx - o.pos[0], -o.pos[1])
                stand = 1.1
                p.target = (o.pos[0] + ux * stand + o.vel[0] * 0.15, o.pos[1] + uy * stand + o.vel[1] * 0.15)
                p.want_speed = p.top_speed()
                if p.dist_to(b.pos[0], b.pos[1]) < 1.45 and 'pass' in inp.pressed:
                    self.do_tackle(p)
                elif p.dist_to(b.pos[0], b.pos[1]) < 1.25 and p.tackle_cd <= 0 and self.rng.random() < dt * 2.5:
                    self.do_tackle(p)
            elif o is not None and p.dist_to(b.pos[0], b.pos[1]) < 1.6 and \
                    ('pass' in inp.pressed or c.tackle_t > 0):
                # Pressed now, or a moment before he took his touch
                c.tackle_t = 0.0
                self.do_tackle(p)
            if 'shoot' in inp.pressed:
                self.do_slide(p, stick)
            if 'through' in inp.held:
                self.ai[c.team.idx].call_press = 0.3
            k = c.team.keeper()
            if 'lob' in inp.held and k is not None and k is not p and b.holder is None:
                # Keeper out: he charges the man on the ball while it's held
                if k.rush_t <= 0:
                    self.emit('keeper_rush', who=self._idx(k))
                k.rush_t = 0.15
            return

        # Loose ball: line up a first-time action
        for k in ('pass', 'through', 'lob'):
            if k in inp.pressed:
                c.queued = (k, stick)
                c.queue_t = 0.7
        if 'pass' in inp.pressed:
            # If an opponent gets there first, it becomes a tackle instead
            c.tackle_t = EARLY_TACKLE
        if 'shoot' in inp.pressed:
            c.charge = 0.0

    def _one_two(self, c, p, inp, dt):
        """Give-and-go: keep pass held after a pass and the passer bursts forward; let go and the
        ball goes straight back into his path. A quick tap is just a pass. True if it played the ball."""
        o = c.one_two
        runner = o['runner']
        o['t'] += dt
        b = self.ball
        if o['t'] > 3.0 or runner.sent_off or (b.owner is not None and b.owner.team is not c.team) \
                or self.state != 'play':
            c.one_two = None
            return False
        if 'pass' in inp.held:
            if o['t'] > ONE_TWO_HOLD:
                o['running'] = True
                runner.run_t = 0.4
            return False
        if not o['running']:
            c.one_two = None
            return False
        # Released: return it first time, or as soon as it arrives
        c.one_two = None
        runner.run_t = 1.2
        if b.owner is p:
            self.do_pass(p, None, 'through', runner)
            self.emit('one_two', who=self._idx(p), to=self._idx(runner))
            return True
        c.queued = ('through', None, runner)
        c.queue_t = 0.9
        c.one_two_pending = True
        return False

    # ---------------------------------------------------------- penalties
    def penalty_limits(self):
        """How far the aim can go: a little outside the posts and over the bar."""
        pt = self.pitch
        return pt.goal_width / 2.0 + 0.7, pt.goal_height + 0.6

    def penalty_pressure(self, team):
        """0..1: how much rides on this kick for team (sudden death is the worst)."""
        if self.shootout:
            mine, theirs = len(team.pens), len(team.opp.pens)
            if mine >= 5:
                return 1.0
            # Must score to stay alive: a miss now and they can't be caught
            if theirs > mine and sum(team.pens) + (4 - mine) < sum(team.opp.pens):
                return 0.85
            return 0.3 + 0.1 * mine
        return 0.35 + (0.35 if self.clock() > 80 else 0.0)

    def _penalty_taker(self, c, p, inp, dt, finesse):
        """The classic spot kick: aim anywhere on the goal mouth, then strike with timed power."""
        if c.pen_aim is None:
            c.pen_aim = [0.0, 0.9]
        ly, lz = self.penalty_limits()
        mx, my = inp.move
        a = p.team.attack
        # Across the goal moves the aim sideways; pushing towards the goal lifts it
        c.pen_aim[0] = max(-ly, min(ly, c.pen_aim[0] + my * 2.6 * dt))
        c.pen_aim[1] = max(0.15, min(lz, c.pen_aim[1] + mx * a * 2.0 * dt))
        if 'lob' in inp.pressed and c.charge is None:
            # The Panenka: a soft chip where you're aiming (down the middle, if you dare)
            self.take_penalty(p, c.pen_aim[0], max(0.9, c.pen_aim[1]), 0.35, 'panenka')
            c.pen_aim = None
            return
        if 'shoot' in inp.pressed:
            c.charge = 0.0
        if c.charge is not None and 'shoot' in inp.held:
            c.charge = min(1.0, c.charge + dt * 0.85)
        if c.charge is not None and 'shoot' in inp.released:
            self.take_penalty(p, c.pen_aim[0], c.pen_aim[1], c.charge, 'finesse' if finesse else 'normal')
            c.charge = None
            c.pen_aim = None

    def _penalty_keeper(self, c, inp):
        """Facing a penalty: pick a dive before the kick (stick to a side, I for high), or
        leave it and let the keeper guess."""
        k = c.team.keeper()
        if k is None:
            return
        c.player = k
        if inp.pressed & {'pass', 'shoot', 'through', 'lob'}:
            mx, my = inp.move
            hw = self.pitch.goal_width / 2.0
            side = 0.0 if abs(my) < 0.3 else math.copysign(1.0, my)
            high = 'lob' in inp.pressed or 'lob' in inp.held
            k.pen_commit = (side * hw * 0.75, 1.55 if high else 0.45)
            self.emit('keeper_pick', who=self._idx(k), side=side, high=high)

    def take_penalty(self, p, ty, tz, power, style='normal'):
        """Strike a spot kick at (ty, tz) on the goal mouth. Spread comes from the taker's
        penalty ratings and the pressure; over-hitting it lifts it, a Panenka floats."""
        b = self.ball
        pt = self.pitch
        gx = p.team.opp_goal_x(pt)
        comp, pw, plc = p.fb.pen
        power = max(0.0, min(1.0, power))
        pressure = self.penalty_pressure(p.team)
        sigma = (0.08 + 0.26 * (1.0 - plc)) * (1.0 + pressure * (1.0 - comp)) * math.sqrt(p.team.error_scale)
        lo, hi = PEN_SWEET
        if style == 'panenka':
            speed = 8.0 + 2.0 * power
            sigma *= 0.6
        else:
            speed = (14.0 + 16.0 * power) * (0.85 + 0.25 * pw)
            if power > hi:
                sigma *= 1.0 + (power - hi) * 3.0
                tz += (power - hi) * (7.0 - 4.0 * pw)
            elif power < lo:
                speed *= 0.8 + 0.2 * power / lo
            if style == 'finesse':
                speed *= 0.85
                sigma *= 0.85
        ty += self.rng.gauss(0.0, sigma)
        tz = max(0.12, tz + self.rng.gauss(0.0, sigma * 0.7))
        self._start_kick(p, 'chip' if style == 'panenka' else ('finesse' if style == 'finesse' else 'shoot'), 0.38)
        dist = math.hypot(gx - b.pos[0], ty - b.pos[1])
        t = dist / speed
        vh = speed * (1.0 + B.DRAG * dist * 0.5)
        vz = (tz - b.pos[2]) / t + 0.5 * B.GRAVITY * t
        ang = math.atan2(ty - b.pos[1], gx - b.pos[0])
        spin = (0.0, 0.0, -math.copysign(12.0, ty - b.pos[1]) * p.team.attack) if style == 'finesse' else (0, 0, 0)
        b.kick(math.cos(ang) * vh, math.sin(ang) * vh, vz, spin=spin)
        p.face_towards(gx, ty)
        self._shot_bookkeeping(p, power, 'chip' if style == 'panenka' else style)
        # A keeper who picked his side goes as the ball is struck
        k = p.team.opp.keeper()
        commit = getattr(k, 'pen_commit', None) if k else None
        if commit is not None:
            k.pen_commit = None
            self.keeper_dive(k, k.pos[0], commit[0], commit[1], max(0.15, t * 0.9))
        return (ty, tz)

    def penalty_odds(self, conv=0.75):
        """Chance the home side wins the shootout from here (each kick scores with conv)."""
        if not self.shootout:
            return None
        from functools import lru_cache

        @lru_cache(maxsize=None)
        def win(na, sa, nb, sb):
            if na <= 5 and nb <= 5:
                if sa > sb + (5 - nb):
                    return 1.0
                if sb > sa + (5 - na):
                    return 0.0
                if na == 5 and nb == 5 and sa == sb:
                    return 0.5      # sudden death between equal takers
            elif na == nb:
                if sa != sb:
                    return 1.0 if sa > sb else 0.0
                return 0.5
            if na == nb:
                return conv * win(na + 1, sa + 1, nb, sb) + (1 - conv) * win(na + 1, sa, nb, sb)
            return conv * win(na, sa, nb + 1, sb + 1) + (1 - conv) * win(na, sa, nb + 1, sb)
        a, b = self.teams[0].pens, self.teams[1].pens
        return win(len(a), sum(a), len(b), sum(b))

    def penalty_cam(self):
        """True while a penalty is being lined up, struck or settled: the view goes behind the taker."""
        r = self.restart
        if not r or r['kind'] != 'penalty' or self.state in ('goal', 'fulltime', 'halftime'):
            return False
        if not r.get('taken'):
            return True
        return self.ticks - r.get('taken_tick', 0) < 140 or (self.shootout is not None and self.state == 'pen_wait')

    def guide(self, c):
        """What the on-pitch guides show for controller c: who an assisted pass would go to,
        where a through ball would be played, who a switch would hand you, and the offside
        line. Any of them can be None."""
        g = dict(pass_to=None, through=None, switch=None, offside=None, bank=None)
        p = c.player
        if p is None or p.sent_off or self.state not in ('play', 'kickoff', 'restart'):
            return g
        b = self.ball
        stick = norm(*c.move) if math.hypot(*c.move) > 0.2 else None
        if b.owner is p or (self.restart and self.restart['taker'] is p and not self.restart.get('taken')):
            g['pass_to'] = self.pick_receiver(p, stick, 'ground')
            if g['pass_to'] is not None and self.pitch.walls:
                lx, ly = self.lead_point(p, g['pass_to'], 'ground')
                bk = self.pass_lane(p, lx, ly)[1]
                if bk is not None:
                    g['bank'] = (bk['wall'], (lx, ly))
            m = self.pick_receiver(p, stick, 'through')
            if m is not None and not m.keeper and (m.pos[0] - p.pos[0]) * p.team.attack > 2.0:
                g['through'] = (m, self.lead_point(p, m, 'through'))
            if self.settings['offside']:
                a = p.team.attack
                xs = sorted((o.pos[0] * a for o in p.team.opp.active()), reverse=True)
                line = max(xs[1] if len(xs) > 1 else 0.0, 0.0, b.pos[0] * a)
                # Only when someone is close enough to it to matter
                if line > 0 and any(abs(q.pos[0] * a - line) < 6.0 for q in p.team.active() if q is not p):
                    g['offside'] = line * a
        elif self.team_in_possession() is not c.team:
            nxt = self.switch_target(c, (0.0, 0.0))
            if nxt is not p:
                g['switch'] = nxt
        return g

    def _late_grace(self, c, p):
        b = self.ball
        if b.owner is not None or b.holder is not None or b.last_touch is not p or p.busy():
            return False
        if (self.ticks - c.owned_tick) * FIXED_DT > LATE_GRACE or b.airborne():
            return False
        fx, fy = p.foot_point(0.28)
        return math.hypot(b.pos[0] - fx, b.pos[1] - fy) < CONTROL * 2.2

    # ---------------------------------------------------------- replays
    def _record(self):
        b = self.ball
        snap = (tuple(b.pos), b.roll_axis, b.roll_angle,
                tuple((p.pos[0], p.pos[1], p.z, p.facing, p.state, p.anim, p.state_t, p.run_phase, p.speed(),
                       p.dive_dir) for t in self.teams for p in t.players))
        self.replay.append(snap)
