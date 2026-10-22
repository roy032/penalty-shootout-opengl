"""The app and a match session: fixed-step simulation, inputs, replays,
the HUD, commentary, sound and the menus around them."""

import os
import random
import subprocess
import sys

from direct.showbase.ShowBase import ShowBase
from direct.gui.DirectGui import DirectFrame
from direct.gui.OnscreenText import OnscreenText
from panda3d.core import TextNode, WindowProperties

from . import app as A
import json

from .sim import challenges, highlights, inputlog, records, roster
from .sim.crossbar import Crossbar
from .sim.tournament import Tournament
from .sim.cuprun import PERKS, CupRun
from .sim.styles import style_for
from .sim.match import FIXED_DT, DIFFICULTY, Match
from .view.camera import LABELS as CAM_LABELS, MODES as CAM_MODES
from .view.commentary import Commentary
from .view.hud import Hud
from .view.inputs import ACTIONS, LABELS as ACTION_LABELS, Inputs, key_label
from .view.match_view import MatchView
from .view.menus import Menu, Row

WEATHER_OPTIONS = [('clear', 'Clear'), ('rain', 'Rain'), ('snow', 'Snow'), ('wind', 'Windy'), ('random', 'Surprise me')]

REPLAYS = os.path.join(A.HOME, 'replays')
CHALLENGES = os.path.join(A.HOME, 'challenges.json')
RECORDS = os.path.join(A.HOME, 'records.json')

HALVES = [(60.0, '1 min halves'), (90.0, '1.5 min halves'), (150.0, '2.5 min halves'), (240.0, '4 min halves'),
          (360.0, '6 min halves'), (600.0, '10 min halves')]


class MatchSession:
    def __init__(self, app, home, away, humans, attract=False, shootout_only=False, cup=False, log=None,
                 windows=None, crossbar=False, tie=None):
        s = app.settings
        self.app = app
        self.attract = attract
        self.cup = cup
        self.tie = tie                  # tournament night game, if this is one
        self.rec = None
        self.reader = None
        self.log = log
        self.windows = list(windows) if windows else None
        self.clip = 0
        self.cb = None
        self.speed = 1
        self.watch_paused = False
        if log is not None:
            # Watching a saved match: the same setup, fed the recorded inputs
            self.match = inputlog.make_match(log)
            self.reader = inputlog.Reader(log)
        elif crossbar:
            self.cb = Crossbar(s['home'], seed=random.randrange(1 << 30))
            self.match = self.cb.m
        else:
            size, pitch = A.FORMATS[s['format']]
            cfg = dict(size=size, pitch=pitch, half_seconds=s['half'] if not attract else 120.0,
                       difficulty=s['difficulty'], preset=s['preset'], auto_switch=s['auto_switch'],
                       weather=s['weather'] if not attract else 'random')
            if cup:
                cfg = app.cup.tie_settings(cfg)
            seed = random.randrange(1 << 30)
            self.match = Match(home, away, settings=cfg, humans=humans, seed=seed)
            if shootout_only:
                self.match.start_shootout()
            if not attract:
                self.rec = inputlog.Recorder(home, away, cfg, humans, seed, shootout_only)
        self.view = MatchView(app, self.match, quality=s['quality'], night=s['night'],
                              cam_mode='broadcast' if attract else s['camera'], guides=s['guides'] and not log)
        self.hud = None if attract else Hud(app, self.match, app.inputs, show_hints=s['hints'] and not log)
        if 'golden_ball' in app.unlocked() and self.match.weather['key'] != 'snow':
            self.view.ball.node.set_color_scale(1.0, 0.82, 0.3, 1)
        self.watch_text = None
        if log is not None or crossbar:
            self.watch_text = OnscreenText(text='', parent=app.a2dTopRight, pos=(-0.05, -0.1), scale=0.045,
                                           fg=(1, 0.82, 0.3, 1), align=TextNode.A_right, shadow=(0, 0, 0, 0.8),
                                           mayChange=True)
        self.comm = Commentary()
        self.acc = 0.0
        self.replay = None
        self.replay_due = None
        self.paused = False
        self.over_t = None
        self.done = False
        self.time = 0.0
        if app.audio and not attract:
            app.audio.update(0.0, 0.3)

    def destroy(self):
        if self.hud:
            self.hud.destroy()
        if self.watch_text:
            self.watch_text.destroy()
        self.view.destroy()

    def _watch_controls(self):
        """While watching a saved match: J pause, K speed, Q camera."""
        inp = self.app.inputs.read(0)
        if 'pass' in inp.pressed:
            self.watch_paused = not self.watch_paused
        if 'shoot' in inp.pressed:
            self.speed = {1: 2, 2: 4, 4: 1}[self.speed]
        if 'switch' in inp.pressed:
            cam = self.view.cam
            cam.mode = CAM_MODES[(CAM_MODES.index(cam.mode) + 1) % len(CAM_MODES)] if cam.mode in CAM_MODES \
                else CAM_MODES[0]
        state = 'PAUSED' if self.watch_paused else 'x%d' % self.speed
        title = 'HIGHLIGHTS  %d of %d' % (min(self.clip + 1, len(self.windows)), len(self.windows)) \
            if self.windows else 'REPLAY'
        self.watch_text.setText('%s  %s\nJ pause   K speed   Q camera   Esc menu' % (title, state))

    def _skip_to_clip(self):
        """Highlights: jump the replay to the next clip, simulating the gap with nothing drawn.
        Returns False once the last clip is over."""
        r = self.reader
        while self.clip < len(self.windows) and r.tick >= self.windows[self.clip][1]:
            self.clip += 1
        if self.clip >= len(self.windows):
            return False
        start = self.windows[self.clip][0]
        if r.tick < start - 1:
            while r.tick < start - 1 and not r.done:
                self.match.step(r.next())
            self.replay_due = None
            if self.hud:
                self.hud.caption(self.windows[self.clip][2] == 'goal' and 'Goal' or 'Chance')
            self.view.cam.snap(self.match.ball.pos, None)
        return True

    # ------------------------------------------------------------ the loop
    def update(self, dt):
        app = self.app
        self.time += dt
        if self.paused:
            return
        m = self.match
        if self.replay is not None:
            self._replay(dt)
            return
        if self.reader is not None:
            self._watch_controls()
        if not self.watch_paused:
            self.acc += dt * self.speed
        steps = 0
        axes = self.view.cam.ground_axes()
        while self.acc >= FIXED_DT and steps < 8 * self.speed:
            inputs = {}
            if self.reader is not None:
                if self.windows is not None and not self._skip_to_clip():
                    self.acc = 0.0
                    if not self.done:
                        self.done = True
                        app.match_over(self)
                    return
                if self.reader.done:
                    self.acc = 0.0
                    break
                inputs = self.reader.next()
            elif self.cb is not None:
                for c in m.controllers:
                    inputs[c.index] = app.inputs.read(c.index, axes)
                evs = self.cb.step(inputs)
                self._events(evs)
                self.acc -= FIXED_DT
                steps += 1
                if self.cb.done and not self.done:
                    self.done = True
                    app.match_over(self)
                    return
                continue
            elif not self.attract:
                for c in m.controllers:
                    inputs[c.index] = inputlog.quantize(app.inputs.read(c.index, axes))
                self.rec.add(inputs)
            evs = m.step(inputs)
            self._events(evs)
            self.acc -= FIXED_DT
            steps += 1
            if self.replay is not None:
                break
        if steps == 8 * self.speed:
            self.acc = 0.0
        self.view.sync(dt)
        if self.hud:
            self.hud.update(dt)
        if self.cb is not None:
            best = self.app.records.get('crossbar_best', 0)
            self.watch_text.setText('CROSSBAR CHALLENGE   %d points   %d s left\nBest %d.   Bar 3, post 1, in off +1'
                                    % (self.cb.score, self.cb.time_left() + 0.99, best))
        self.comm.update(dt)
        if app.audio and not self.attract:
            app.audio.update(dt, self.view.excite)
        if self.replay_due is not None:
            self.replay_due -= dt
            if self.replay_due <= 0:
                self.replay_due = None
                self._start_replay()
        if m.state == 'fulltime':
            if self.over_t is None:
                self.over_t = 0.0
            self.over_t += dt
            if self.over_t > (3.0 if not self.attract else 4.0) and not self.done:
                self.done = True
                app.match_over(self)

    def _events(self, evs):
        m = self.match
        if not evs:
            return
        if self.app.audio and not self.attract:
            self.app.audio.on_events(evs, m)
        v = self.view
        hud = self.hud
        for e in evs:
            t = e['type']
            if t == 'goal':
                v.excite = 1.0
                v.world.ripple_net(1 if m.ball.pos[0] > 0 else -1, 1.0)
                if hud:
                    team = m.teams[e['team']]
                    sc = e.get('scorer')
                    who = m.teams[sc[0]].players[sc[1]].fb.name if sc else ''
                    sub = ('%s  %d\'' % (who, int(m.clock()) + 1)) if not e.get('own') else 'Own goal: %s' % who
                    hud.flash('GOAL!', sub, 3.0)
                    if not self.attract and self.windows is None:
                        self.replay_due = 1.6
            elif t == 'shot':
                v.excite = max(v.excite, 0.6)
            elif t == 'woodwork':
                v.cam.shake = 0.5
                v.excite = max(v.excite, 0.8)
            elif t == 'save' and e.get('speed', 0) > 16:
                v.excite = max(v.excite, 0.7)
            elif hud and t == 'card':
                p = m.teams[e['who'][0]].players[e['who'][1]]
                hud.flash('RED CARD' if e['card'] == 'red' else 'YELLOW CARD', p.fb.name, 2.0,
                          (1, 0.2, 0.2, 1) if e['card'] == 'red' else (1, 0.9, 0.2, 1))
            elif hud and t == 'offside':
                hud.flash('OFFSIDE', '', 1.6, (1, 1, 1, 1))
            elif hud and t == 'penalty_awarded':
                hud.flash('PENALTY!', '', 2.0)
            elif hud and t == 'halftime':
                hud.flash('HALF TIME', '%s %d - %d %s' % (m.teams[0].short, m.teams[0].score, m.teams[1].score,
                                                          m.teams[1].short), 2.5, (1, 1, 1, 1))
            elif hud and t == 'fulltime':
                w = m.winner
                hud.flash('FULL TIME', ('%s WIN' % w.name) if w else 'A DRAW', 3.0, (1, 1, 1, 1))
            elif hud and t == 'shootout':
                hud.flash('PENALTIES', 'Best of five', 2.5)
            elif hud and t == 'cb_kick':
                labels = dict(bar='CROSSBAR!', post='POST!', in_off='IN OFF THE WOODWORK!', goal='IN THE NET',
                              miss='MISSED')
                hud.flash(labels[e['kind']], '+%d' % e['points'] if e['points'] else '', 1.0,
                          (1, 0.82, 0.3, 1) if e['points'] else (1, 1, 1, 1))
            elif hud and t == 'pen_result':
                hud.flash('SCORED' if e['scored'] else 'MISSED', '', 1.2,
                          (0.5, 1, 0.5, 1) if e['scored'] else (1, 0.4, 0.4, 1))
        if hud:
            line = self.comm.events(evs, m)
            if line:
                hud.caption(line[0])

    # ------------------------------------------------------------ replays
    def _start_replay(self):
        frames = list(self.match.replay)
        if len(frames) < 60:
            return
        # The build-up and the finish, ending a moment after the ball went in
        n = min(len(frames), int(5.0 / FIXED_DT))
        self.replay = dict(frames=frames[-n:], i=0.0, t=0.0)
        self.app.inputs.read(0)      # swallow the press that might be held

    def _replay(self, dt):
        r = self.replay
        frames = r['frames']
        r['t'] += dt
        speed = 0.6 if r['i'] > len(frames) * 0.55 else 1.0
        r['i'] += dt / FIXED_DT * speed
        skip = False
        for c in self.match.controllers:
            inp = self.app.inputs.read(c.index)
            if inp.pressed:
                skip = True
        i = int(r['i'])
        if i >= len(frames) or (skip and r['t'] > 0.3):
            self.replay = None
            self.view.cam.snap(self.match.ball.pos, None)
            return
        angle = 'side' if i < len(frames) * 0.45 else 'goal'
        f = frames[i]
        self.view.sync(dt, snapshot=(f[0], f[1], f[2], f[3]), replay_angle=angle, replay_t=r['t'])
        if self.hud:
            self.hud.update(dt, replaying=True)
        if self.app.audio:
            self.app.audio.update(dt, 0.6)


class FootballApp(ShowBase):
    def __init__(self, settings, offscreen=False):
        ShowBase.__init__(self)
        self.settings = settings
        self.disable_mouse()
        self.set_background_color(0.02, 0.03, 0.06, 1)
        self.menus = []
        self.session = None
        self.cup = None
        self.progress = self._load_progress()
        self.news = []
        self.records = self._load_json(RECORDS, {})
        self.tourney = None
        self.last_log = None
        self.inputs = Inputs(self, os.path.join(A.HOME, 'controls.json'))
        self.audio = None
        try:
            from .view.audio import Audio
            self.audio = Audio(self, os.path.join(A.HOME, 'sounds'), settings['volume'], settings['crowd'])
        except Exception as exc:          # sound is a nice-to-have
            print('Sound disabled:', exc)
            self.audio = None
        self.filters = None
        self._setup_filters()
        for key, name in (('arrow_up', 'up'), ('w', 'up'), ('arrow_down', 'down'), ('s', 'down'),
                          ('arrow_left', 'left'), ('a', 'left'), ('arrow_right', 'right'), ('d', 'right'),
                          ('enter', 'confirm'), ('space', 'confirm'), ('escape', 'back'), ('backspace', 'back')):
            self.accept(key, self._key, [name])
            if name in ('up', 'down', 'left', 'right'):
                self.accept(key + '-repeat', self._key, [name])
        self.accept('f11', self.toggle_fullscreen)
        self.accept('window-event', self._window_event)
        self.rebinding = None
        self.task_mgr.add(self._loop, 'loop')
        self.attract()
        self.main_menu()

    # ------------------------------------------------------------ plumbing
    def _setup_filters(self):
        if self.settings['quality'] != 'high':
            return
        try:
            from direct.filter.CommonFilters import CommonFilters
            self.filters = CommonFilters(self.win, self.cam)
            if not self.filters.set_bloom(blend=(0.3, 0.4, 0.3, 0.0), mintrigger=0.72, maxtrigger=1.0,
                                          desat=0.2, intensity=0.9, size='medium'):
                self.filters = None
        except Exception:
            self.filters = None

    def _window_event(self, win):
        if win is self.win and not win.get_properties().get_open():
            self.quit_game()

    def quit_game(self):
        if self.audio:
            self.audio.stop()
        A.save_settings(self.settings)
        self.user_exit()

    def toggle_fullscreen(self):
        self.settings['fullscreen'] = not self.settings['fullscreen']
        wp = WindowProperties()
        wp.set_fullscreen(self.settings['fullscreen'])
        if not self.settings['fullscreen']:
            wp.set_size(1280, 720)
        self.win.request_properties(wp)
        A.save_settings(self.settings)

    def sound_ui(self, kind):
        if self.audio:
            self.audio.ui(kind)

    def menu_stack_push(self, m):
        self.menus.append(m)

    def menu_stack_pop(self, m):
        if m in self.menus:
            self.menus.remove(m)

    def _key(self, name):
        if self.rebinding:
            return
        if self.menus:
            self.menus[-1].key(name)
        elif name == 'back' and self.session and not self.session.attract:
            self.pause_menu()

    def _loop(self, task):
        dt = min(0.1, self.clock.get_dt())
        if self.menus:
            for k in self.inputs.menu_keys():
                if k == 'start':
                    k = 'back'
                self.menus[-1].key(k)
        elif self.session and not self.session.attract:
            for k in self.inputs.menu_keys():
                if k == 'start':
                    self.pause_menu()
        if self.session:
            self.session.update(dt)
        return task.cont

    def clear_menus(self):
        for m in list(self.menus):
            m.destroy()

    # ------------------------------------------------------------ sessions
    def end_session(self):
        if self.session:
            self.session.destroy()
            self.session = None
        if self.audio:
            self.audio.stop()

    def attract(self):
        """A CPU match playing behind the menus."""
        self.end_session()
        ids = roster.team_ids()
        a, b = random.sample(ids[:6], 2)
        self.session = MatchSession(self, a, b, humans=(), attract=True)

    def start_match(self, shootout_only=False):
        s = self.settings
        mode = s['mode']
        humans = {'1p': ((0, 0),), '2p': ((0, 0), (1, 1)), 'coop': ((0, 0), (1, 0)), 'cpu': ()}[mode]
        self.clear_menus()
        self.end_session()
        self.session = MatchSession(self, s['home'], s['away'], humans, shootout_only=shootout_only)
        s['matches'] += 1
        A.save_settings(s)

    def match_over(self, session):
        if session.attract:
            self.attract()
            return
        if session.reader is not None:
            self._quit_to_menu()
            self.replays_menu()
            return
        if session.cb is not None:
            self.crossbar_result(session.cb)
            return
        if session.rec is not None:
            self.last_log = session.rec.to_dict(session.match)
            inputlog.save(self.last_log, REPLAYS)
        records.update(self.records, session.match)
        self._save_json(RECORDS, self.records)
        if session.tie is not None:
            self.tourney_result(session.match, session.tie)
            return
        self.news = self._record_challenges(session.match) if not session.cup else []
        if session.cup:
            self.cup_result(session.match)
            return
        self.results_menu(session.match)

    # ------------------------------------------------------------ menus
    def main_menu(self):
        self.clear_menus()
        Menu(self, 'ULTIMATE FOOTBALL', [
            Row('Kick off', self.setup_menu, help='Pick the teams, the format and go'),
            Row('Quick match', lambda: self.start_match(), help='Straight into a match with your last settings'),
            Row('Cup Run', self.cup_menu, help='Four knockout ties, harder each round. Pick a perk after every win'),
            Row('Penalty shootout', lambda: self.start_match(shootout_only=True),
                help='Best of five from the spot, then sudden death'),
            Row('Tournament night', self.tourney_setup, help='A knockout for 2 to 8 players, two at a time'),
            Row('Crossbar challenge', lambda: self.start_crossbar(),
                help='A minute to hit the bar from the edge of the box'),
            Row('Hall of fame', self.hall_menu, help='Career goals, wins and awards for every character'),
            Row('Challenges', self.challenges_menu, help='Things to do in matches. They unlock a golden ball and a hidden team'),
            Row('Replays', self.replays_menu, help='Watch your last %d matches again, from any camera' % inputlog.KEEP),
            Row('Classic penalty game', self.launch_classic, help='The original Penalty Shootout game'),
            Row('Controls', self.controls_menu, help='See and change the keys'),
            Row('Settings', self.settings_menu, help='Graphics, camera, sound and assists'),
            Row("Quit", self.quit_game),
        ], subtitle='Legends, icons and fantasy stars. Arcade football.', back=None,
            footer='Arrows or stick to move, Enter or A to choose. F11 for fullscreen.')

    def _team_rows(self):
        s = self.settings
        teams = [(t, roster.team_info(t)['name']) for t in roster.team_ids(self.unlocked())]

        def g(k):
            return lambda: s[k]

        def st(k):
            def f(v):
                s[k] = v
            return f
        return teams, g, st

    def setup_menu(self):
        self.clear_menus()
        s = self.settings
        teams, g, st = self._team_rows()
        Menu(self, 'KICK OFF', [
            Row('Your team', options=teams, get=g('home'), set=st('home'),
                help=self._team_help('home')),
            Row('Opponent', options=teams, get=g('away'), set=st('away'), help=self._team_help('away')),
            Row('Players', options=A.MODES, get=g('mode'), set=st('mode'),
                help='Two players: one on the keyboard (or pad 1), the other on arrows (or pad 2)'),
            Row('Format', options=A.FORMAT_LABELS, get=g('format'), set=st('format')),
            Row('Difficulty', options=[(k, v['label']) for k, v in DIFFICULTY.items()], get=g('difficulty'),
                set=st('difficulty')),
            Row('Match length', options=HALVES, get=g('half'), set=st('half')),
            Row('Style', options=[('arcade', 'Arcade'), ('authentic', 'Authentic')], get=g('preset'),
                set=st('preset'), help='Authentic: slower, less accurate, offside on full pitches'),
            Row('Time', options=[(True, 'Night, floodlights'), (False, 'Day')], get=g('night'), set=st('night')),
            Row('Weather', options=WEATHER_OPTIONS, get=g('weather'), set=st('weather'),
                help='Rain: a quick, skiddy ball and slippery keepers. Snow: it dies on the turf. Wind: watch your lobs'),
            Row('PLAY', lambda: self.start_match()),
        ], back=self.main_menu, footer='Left and right change an option.')

    def _team_help(self, k):
        def text():
            st = style_for(self.settings[k])
            return 'Plays: %s. %s.' % (st['label'], st['blurb'])
        return text

    def settings_menu(self):
        self.clear_menus()
        s = self.settings
        _, g, st = self._team_rows()

        def vol(k):
            def f(v):
                s[k] = v
                if self.audio:
                    self.audio.set_volume(s['volume'], s['crowd'])
            return f
        levels = [(round(i / 10, 1), '%d%%' % (i * 10)) for i in range(11)]
        Menu(self, 'SETTINGS', [
            Row('Graphics', options=[('low', 'Low'), ('medium', 'Medium'), ('high', 'High')], get=g('quality'),
                set=st('quality'), help='Shadows, smoothing and glow. Restart the game to apply all of it.'),
            Row('Camera', options=[(k, CAM_LABELS[k]) for k in CAM_MODES], get=g('camera'), set=st('camera')),
            Row('Control hints', options=[(True, 'On'), (False, 'Off')], get=g('hints'), set=st('hints')),
            Row('Pitch guides', options=[(True, 'On'), (False, 'Off')], get=g('guides'), set=st('guides'),
                help='Rings under your pass target and next switch, the through-ball lane and the offside line'),
            Row('Auto switching', options=[(True, 'On'), (False, 'Off')], get=g('auto_switch'),
                set=st('auto_switch'), help='Hand you the player nearest the ball when defending'),
            Row('Volume', options=levels, get=g('volume'), set=vol('volume')),
            Row('Crowd', options=levels, get=g('crowd'), set=vol('crowd')),
            Row('Fullscreen', options=[(False, 'Off'), (True, 'On')], get=g('fullscreen'),
                set=lambda v: self.toggle_fullscreen() if v != s['fullscreen'] else None),
            Row('Back', self._settings_done),
        ], back=self._settings_done)

    def _settings_done(self):
        A.save_settings(self.settings)
        self.main_menu()

    def controls_menu(self):
        self.clear_menus()
        rows = []
        for a in ACTIONS:
            rows.append(Row('%s:  %s  |  P2 %s' % (ACTION_LABELS[a], key_label(self.inputs.keys[0][a]),
                                                   key_label(self.inputs.keys[1][a])),
                            lambda a=a: self.rebind(a)))
        rows.append(Row('Reset to defaults', self._reset_keys))
        rows.append(Row('Back', self.main_menu))
        Menu(self, 'CONTROLS', rows, back=self.main_menu, width=1.6,
             footer='Choose an action, then press the new key for player 1. Keys swap if already used. '
                    'Gamepads: A pass, B shoot, Y through, X lob, RT sprint, LB switch, RB finesse, LT skill.')

    def _reset_keys(self):
        self.inputs.reset()
        self.controls_menu()

    def rebind(self, action):
        self.rebinding = action
        m = self.menus[-1]
        m.help.setText('Press a key for "%s" (Escape to cancel)' % ACTION_LABELS[action])
        bt = self.buttonThrowers[0].node()
        bt.set_button_down_event('rebind-key')
        self.accept('rebind-key', self._rebind_key)

    def _rebind_key(self, key):
        bt = self.buttonThrowers[0].node()
        bt.set_button_down_event('')
        self.ignore('rebind-key')
        action = self.rebinding
        self.rebinding = None
        if key.startswith('mouse') or key in ('escape', 'f11'):
            self.controls_menu()
            return
        self.inputs.rebind(0, action, key)
        sel = ACTIONS.index(action)
        self.controls_menu()
        self.menus[-1].sel = sel
        self.menus[-1].refresh()

    def pause_menu(self):
        se = self.session
        if not se or se.attract or self.menus:
            return
        se.paused = True
        if self.audio:
            self.audio.set_paused(True)
        s = self.settings

        def cam(v):
            s['camera'] = v
            se.view.cam.mode = v

        def hints(v):
            s['hints'] = v
            se.hud.show_hints = v

        def guides(v):
            s['guides'] = v
            se.view.guides = v

        Menu(self, 'PAUSED', [
            Row('Resume', self._resume),
            Row('Camera', options=[(k, CAM_LABELS[k]) for k in CAM_MODES], get=lambda: s['camera'], set=cam),
            Row('Control hints', options=[(True, 'On'), (False, 'Off')], get=lambda: s['hints'], set=hints),
            Row('Pitch guides', options=[(True, 'On'), (False, 'Off')], get=lambda: s['guides'], set=guides),
        ] + ([] if se.reader or se.cb else [
            Row('Restart match', lambda: self.start_match(shootout_only=bool(se.match.shootout and se.match.half == 1)))]) + [
            Row('Quit to main menu', self._quit_to_menu),
        ], back=self._resume, width=1.1)

    def _resume(self):
        self.clear_menus()
        if self.session:
            self.session.paused = False
        if self.audio:
            self.audio.set_paused(False)
        A.save_settings(self.settings)

    def _quit_to_menu(self):
        self.clear_menus()
        self.attract()
        self.main_menu()

    def results_menu(self, m):
        a, b = m.teams
        lines = []
        for e in m.log:
            if e['kind'] == 'goal':
                lines.append("%s  %s%s %d'" % (m.teams[e['team']].short, e['name'], ' (og)' if e['own'] else '',
                                              e['minute']))
            else:
                lines.append("%s  %s card: %s %d'" % (m.teams[e['team']].short, e['kind'].title(), e['name'],
                                                     e['minute']))
        tot = max(1e-6, a.possession_t + b.possession_t)

        def row(label, va, vb):
            return '%-6s %16s %6s' % (va, label, vb)
        stats = [
            row('Possession', '%d%%' % round(100 * a.possession_t / tot), '%d%%' % round(100 * b.possession_t / tot)),
            row('Shots', a.stats['shots'], b.stats['shots']),
            row('xG', '%.1f' % a.xg, '%.1f' % b.xg),
            row('Saves', a.stats['saves'], b.stats['saves']),
            row('Passes', '%d/%d' % (a.stats['passes_done'], a.stats['passes']),
                '%d/%d' % (b.stats['passes_done'], b.stats['passes'])),
            row('Tackles', a.stats['tackles'], b.stats['tackles']),
            row('Fouls', a.stats['fouls'], b.stats['fouls']),
        ]
        motm = max((p for t in m.teams for p in t.players), key=lambda p: p.rating + p.goals * 0.5 + p.saves * 0.3)
        title = '%s  %d - %d  %s' % (a.name, a.score, b.score, b.name)
        if m.shootout:
            title += '   (%d-%d pens)' % (sum(a.pens), sum(b.pens))
        menu = Menu(self, 'FULL TIME', ([Row('Watch highlights', self.watch_highlights)] if self.last_log else []) + [
            Row('Rematch', lambda: self.start_match()),
            Row('Swap teams', self._swap_and_play),
            Row('Main menu', self._quit_to_menu),
        ], subtitle=title, back=self._quit_to_menu, y0=-0.42, width=1.2)
        text = '\n'.join(stats) + '\n\nPlayer of the match: %s' % motm.fb.name
        if self.news:
            text = '\n'.join(self.news) + '\n\n' + text
            lines = lines[:4]
        if lines:
            text += '\n\n' + '\n'.join(lines[:8])
        OnscreenText(text=text, parent=menu.root, pos=(0, 0.47), scale=0.042, fg=(0.92, 0.94, 1, 1),
                     align=TextNode.A_center)

    # ------------------------------------------------------------ highlights, records, mini-games
    def _load_json(self, path, default):
        try:
            with open(path) as f:
                data = json.load(f)
            return data if isinstance(data, type(default)) else default
        except (OSError, ValueError):
            return default

    def _save_json(self, path, data):
        try:
            os.makedirs(A.HOME, exist_ok=True)
            with open(path + '.tmp', 'w') as f:
                json.dump(data, f)
            os.replace(path + '.tmp', path)
        except OSError:
            pass

    def watch_highlights(self, log=None):
        log = log or self.last_log
        clips = highlights.find(log)
        if not clips:
            return
        self.clear_menus()
        self.end_session()
        self.session = MatchSession(self, None, None, None, log=log, windows=clips)

    def hall_menu(self):
        self.clear_menus()
        rec = self.records

        def block(title, key, unit):
            rows = records.table(rec, key, 6)
            if not rows:
                return '%s\n   nobody yet' % title
            return title + '\n' + '\n'.join('   %s  %d %s  (%d apps)' % (r['name'], r[key], unit, r['apps'])
                                              for r in rows)
        menu = Menu(self, 'HALL OF FAME', [Row('Back', self.main_menu)], back=self.main_menu, y0=-0.78,
                    subtitle='%d matches played.   Crossbar challenge best: %d' % (rec.get('matches', 0),
                                                                                 rec.get('crossbar_best', 0)))
        OnscreenText(text=block('Top scorers', 'goals', 'goals'), parent=menu.root, pos=(-0.32, 0.45), scale=0.04,
                     fg=(0.92, 0.94, 1, 1), align=TextNode.A_center)
        OnscreenText(text=block('Players of the match', 'motm', 'awards') + '\n\n' + block('Most saves', 'saves', 'saves'),
                     parent=menu.root, pos=(0.32, 0.45), scale=0.04, fg=(0.92, 0.94, 1, 1), align=TextNode.A_center)

    def start_crossbar(self):
        self.clear_menus()
        self.end_session()
        self.session = MatchSession(self, None, None, ((0, 0),), crossbar=True)

    def crossbar_result(self, cb):
        best = self.records.get('crossbar_best', 0)
        new_best = cb.score > best
        if new_best:
            self.records['crossbar_best'] = cb.score
            self._save_json(RECORDS, self.records)
        counts = {}
        for k, _ in cb.kicks:
            counts[k] = counts.get(k, 0) + 1
        detail = ', '.join('%s %d' % (dict(bar='bar', post='post', in_off='in off', goal='goals', miss='misses')[k], n)
                           for k, n in sorted(counts.items()))
        Menu(self, 'NEW BEST!' if new_best else 'TIME UP', [
            Row('Try again', self.start_crossbar),
            Row('Main menu', self._quit_to_menu),
        ], subtitle='%d points from %d kicks   (%s)' % (cb.score, len(cb.kicks), detail or 'no kicks'),
            back=self._quit_to_menu)

    # ------------------------------------------------------------ tournament night
    def tourney_setup(self):
        self.clear_menus()
        s = self.settings
        s.setdefault('tourney_n', 4)
        Menu(self, 'TOURNAMENT NIGHT', [
            Row('Players', options=[(n, '%d players' % n) for n in range(2, 9)], get=lambda: s['tourney_n'],
                set=lambda v: s.__setitem__('tourney_n', v)),
            Row('Format', options=A.FORMAT_LABELS, get=lambda: s['format'], set=lambda v: s.__setitem__('format', v)),
            Row('Match length', options=HALVES, get=lambda: s['half'], set=lambda v: s.__setitem__('half', v)),
            Row('Draw the bracket', self._new_tourney),
            Row('Back', self.main_menu),
        ], back=self.main_menu, subtitle='Two at a time: one on the keyboard (or pad 1), one on arrows (or pad 2)')

    def _new_tourney(self):
        n = self.settings.get('tourney_n', 4)
        self.tourney = Tournament(['Player %d' % (i + 1) for i in range(n)], seed=random.randrange(1 << 30))
        self.tourney_menu()

    def tourney_menu(self, news=''):
        t = self.tourney
        self.clear_menus()
        nxt = t.next_match()
        rows = []
        if nxt:
            ri, g = nxt
            pa, pb = t.players[g['a']], t.players[g['b']]
            rows.append(Row('Play: %s v %s' % (pa['name'], pb['name']), lambda: self._play_tie(g),
                            help='%s (%s) on the keyboard or pad 1, %s (%s) on arrows or pad 2' % (
                                pa['name'], roster.team_info(pa['team'])['name'], pb['name'],
                                roster.team_info(pb['team'])['name'])))
            title = 'TOURNAMENT NIGHT'
        else:
            title = '%s WINS!' % t.players[t.champion]['name'].upper()
            rows.append(Row('New tournament', self.tourney_setup))
        rows.append(Row('Main menu', self._quit_to_menu))
        teams = '   '.join('%s: %s' % (p['name'], roster.team_info(p['team'])['short']) for p in t.players)
        menu = Menu(self, title, rows, back=self._quit_to_menu, y0=-0.5, subtitle=teams)
        OnscreenText(text=(news + '\n\n' if news else '') + '\n'.join(t.lines()), parent=menu.root, pos=(0, 0.46),
                     scale=0.042, fg=(0.92, 0.94, 1, 1), align=TextNode.A_center)

    def _play_tie(self, g):
        t = self.tourney
        self.clear_menus()
        self.end_session()
        self.session = MatchSession(self, t.players[g['a']]['team'], t.players[g['b']]['team'], ((0, 0), (1, 1)),
                                    tie=g)

    def tourney_result(self, m, g):
        a, b = m.teams
        t = self.tourney
        t.record(g, a.score, b.score, (sum(a.pens), sum(b.pens)) if m.shootout else None)
        w = t.players[g['winner']]['name']
        self.end_session()
        self.attract()
        self.tourney_menu('%s go through: %s %d - %d %s%s' % (
            w, a.short, a.score, b.score, b.short, ' (%d-%d pens)' % (sum(a.pens), sum(b.pens)) if m.shootout else ''))

    # ------------------------------------------------------------ challenges
    def _load_progress(self):
        try:
            with open(CHALLENGES) as f:
                return set(json.load(f).get('done', [])) & set(challenges.IDS)
        except (OSError, ValueError, AttributeError):
            return set()

    def unlocked(self):
        return challenges.rewards(self.progress)

    def _record_challenges(self, m, cup_won=False):
        """Note what this match completed; returns lines to show for anything new."""
        before = self.unlocked()
        new = challenges.check(m, cup_won) - self.progress
        if not new:
            return []
        self.progress |= new
        try:
            os.makedirs(A.HOME, exist_ok=True)
            with open(CHALLENGES, 'w') as f:
                json.dump(dict(done=sorted(self.progress)), f)
        except OSError:
            pass
        names = dict((c[0], c[1]) for c in challenges.CHALLENGES)
        out = ['Challenge complete: %s' % names[k] for k in challenges.IDS if k in new]
        for need, key, label, _ in challenges.REWARDS:
            if key in self.unlocked() - before:
                out.append('UNLOCKED: %s' % label)
        return out

    def challenges_menu(self):
        self.clear_menus()
        rows = []
        for key, label, desc in challenges.CHALLENGES:
            rows.append(Row(('[x]  ' if key in self.progress else '[  ]  ') + label, None, help=desc))
        rows.append(Row('Back', self.main_menu))
        have = self.unlocked()
        n = len(self.progress)
        reward = '   '.join('%s %s (%d)' % ('Unlocked:' if key in have else 'Locked:', label, need)
                           for need, key, label, _ in challenges.REWARDS)
        Menu(self, 'CHALLENGES', rows, back=self.main_menu, y0=0.4,
             subtitle='%d of %d done.   %s' % (n, len(challenges.IDS), reward))

    # ------------------------------------------------------------ replays
    def replays_menu(self):
        self.clear_menus()
        rows = []
        for path in inputlog.listing(REPLAYS)[:9]:
            try:
                log = inputlog.load(path)
            except (OSError, ValueError):
                continue
            res = log.get('result') or {}
            names = res.get('names') or [log['home'], log['away']]
            score = res.get('score') or ['?', '?']
            label = '%s %s - %s %s' % (names[0], score[0], score[1], names[1])
            if res.get('pens'):
                label += ' (%d-%d pens)' % tuple(res['pens'])
            fmt = dict(A.FORMAT_LABELS).get(res.get('pitch'), '')
            rows.append(Row(label, (lambda log=log: self.watch_replay(log)), help='%s   %s' % (log['date'], fmt)))
        if not rows:
            rows.append(Row('No replays yet: play a match first', self.main_menu))
        rows.append(Row('Back', self.main_menu))
        Menu(self, 'REPLAYS', rows, back=self.main_menu, subtitle='Every match is saved. Watch from any camera.')

    def watch_replay(self, log):
        self.clear_menus()
        self.end_session()
        self.session = MatchSession(self, None, None, None, log=log)

    # ------------------------------------------------------------ cup run
    def cup_menu(self):
        if self.cup is None or self.cup.over:
            self.cup = CupRun(self.settings['home'], seed=random.randrange(1 << 30))
        cup = self.cup
        self.clear_menus()
        rows = []
        t = cup.tie()
        opp = roster.team_info(t['opp'])['name']
        rows.append(Row('Play the %s v %s' % (t['name'].lower(), opp), self._play_cup_tie,
                        help='%s difficulty. Draws go to penalties.' % DIFFICULTY[t['difficulty']]['label']))
        if cup.round == 0:
            teams, _, _ = self._team_rows()

            def pick(v):
                self.settings['home'] = v
                self.cup = None
                self.cup_menu()
            rows.append(Row('Your team', options=teams, get=lambda: cup.team, set=pick,
                            help=self._team_help('home')))
        rows.append(Row('Abandon the run', self._abandon_cup))
        menu = Menu(self, 'CUP RUN', rows, back=self.main_menu, y0=-0.3, width=1.3,
                    subtitle='%s   |   Perks: %s' % (roster.team_info(cup.team)['name'], cup.perk_text()))
        OnscreenText(text='\n'.join(cup.bracket_lines()), parent=menu.root, pos=(0, 0.42), scale=0.05,
                     fg=(0.92, 0.94, 1, 1), align=TextNode.A_center)

    def _play_cup_tie(self):
        cup = self.cup
        self.clear_menus()
        self.end_session()
        self.session = MatchSession(self, cup.team, cup.tie()['opp'], ((0, 0),), cup=True)
        self.settings['matches'] += 1
        A.save_settings(self.settings)

    def _abandon_cup(self):
        self.cup = None
        self.main_menu()

    def cup_result(self, m):
        cup = self.cup
        a, b = m.teams
        tie = cup.tie()
        won = cup.record((a.score, b.score), (sum(a.pens), sum(b.pens)) if m.shootout else None)
        news = self._record_challenges(m, cup_won=cup.champion)
        score = '%s  %d - %d  %s' % (a.name, a.score, b.score, b.name)
        if m.shootout:
            score += '   (%d-%d pens)' % (sum(a.pens), sum(b.pens))
        if cup.champion:
            title, rows = 'CHAMPIONS', [Row('New Cup Run', self.cup_menu), Row('Main menu', self._quit_to_menu)]
        elif not won:
            title = 'KNOCKED OUT'
            rows = [Row('Try again', self.cup_menu), Row('Main menu', self._quit_to_menu)]
        else:
            title = '%s WON' % tie['name'].upper()
            rows = [Row(PERKS[k]['label'], (lambda k=k: self._take_perk(k)), help=PERKS[k]['blurb'])
                    for k in cup.offer]
        self.end_session()
        self.attract()
        menu = Menu(self, title, rows, back=None if won and not cup.champion else self._quit_to_menu,
                    subtitle=score, y0=-0.12, width=1.3)
        text = '\n'.join(cup.bracket_lines())
        if won and not cup.champion:
            text += '\n\nPick a perk for the rest of the run'
        if news:
            text += '\n\n' + '\n'.join(news)
        OnscreenText(text=text, parent=menu.root, pos=(0, 0.42), scale=0.048, fg=(0.92, 0.94, 1, 1),
                     align=TextNode.A_center)

    def _take_perk(self, key):
        self.cup.take(key)
        self.cup_menu()

    def _swap_and_play(self):
        s = self.settings
        s['home'], s['away'] = s['away'], s['home']
        self.start_match()

    def launch_classic(self):
        """Start the original penalty game in its own window."""
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        script = os.path.join(root, 'penalty_shootout.py')
        try:
            if getattr(sys, 'frozen', False):
                subprocess.Popen([sys.executable, '--classic'])
            else:
                subprocess.Popen([sys.executable, script], cwd=root)
        except OSError as exc:
            print('Could not start the classic game:', exc)
