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
from .sim import roster
from .sim.match import FIXED_DT, DIFFICULTY, Match
from .view.camera import LABELS as CAM_LABELS, MODES as CAM_MODES
from .view.commentary import Commentary
from .view.hud import Hud
from .view.inputs import ACTIONS, LABELS as ACTION_LABELS, Inputs, key_label
from .view.match_view import MatchView
from .view.menus import Menu, Row

HALVES = [(60.0, '1 min halves'), (90.0, '1.5 min halves'), (150.0, '2.5 min halves'), (240.0, '4 min halves'),
          (360.0, '6 min halves'), (600.0, '10 min halves')]


class MatchSession:
    def __init__(self, app, home, away, humans, attract=False, shootout_only=False):
        s = app.settings
        size, pitch = A.FORMATS[s['format']]
        cfg = dict(size=size, pitch=pitch, half_seconds=s['half'] if not attract else 120.0,
                   difficulty=s['difficulty'], preset=s['preset'], auto_switch=s['auto_switch'])
        self.app = app
        self.attract = attract
        self.match = Match(home, away, settings=cfg, humans=humans, seed=random.randrange(1 << 30))
        if shootout_only:
            self.match.start_shootout()
        self.view = MatchView(app, self.match, quality=s['quality'], night=s['night'],
                              cam_mode='broadcast' if attract else s['camera'])
        self.hud = None if attract else Hud(app, self.match, app.inputs, show_hints=s['hints'])
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
        self.view.destroy()

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
        self.acc += dt
        steps = 0
        axes = self.view.cam.ground_axes()
        while self.acc >= FIXED_DT and steps < 8:
            inputs = {}
            if not self.attract:
                for c in m.controllers:
                    inputs[c.index] = app.inputs.read(c.index, axes)
            evs = m.step(inputs)
            self._events(evs)
            self.acc -= FIXED_DT
            steps += 1
            if self.replay is not None:
                break
        if steps == 8:
            self.acc = 0.0
        self.view.sync(dt)
        if self.hud:
            self.hud.update(dt)
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
                    if not self.attract:
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
        self.results_menu(session.match)

    # ------------------------------------------------------------ menus
    def main_menu(self):
        self.clear_menus()
        Menu(self, 'ULTIMATE FOOTBALL', [
            Row('Kick off', self.setup_menu, help='Pick the teams, the format and go'),
            Row('Quick match', lambda: self.start_match(), help='Straight into a match with your last settings'),
            Row('Penalty shootout', lambda: self.start_match(shootout_only=True),
                help='Best of five from the spot, then sudden death'),
            Row('Classic penalty game', self.launch_classic, help='The original Penalty Shootout game'),
            Row('Controls', self.controls_menu, help='See and change the keys'),
            Row('Settings', self.settings_menu, help='Graphics, camera, sound and assists'),
            Row("Quit", self.quit_game),
        ], subtitle='Legends, icons and fantasy stars. Arcade football.', back=None,
            footer='Arrows or stick to move, Enter or A to choose. F11 for fullscreen.')

    def _team_rows(self):
        s = self.settings
        teams = [(t, roster.team_info(t)['name']) for t in roster.team_ids()]

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
            Row('Opponent', options=teams, get=g('away'), set=st('away')),
            Row('Players', options=A.MODES, get=g('mode'), set=st('mode'),
                help='Two players: one on the keyboard (or pad 1), the other on arrows (or pad 2)'),
            Row('Format', options=A.FORMAT_LABELS, get=g('format'), set=st('format')),
            Row('Difficulty', options=[(k, v['label']) for k, v in DIFFICULTY.items()], get=g('difficulty'),
                set=st('difficulty')),
            Row('Match length', options=HALVES, get=g('half'), set=st('half')),
            Row('Style', options=[('arcade', 'Arcade'), ('authentic', 'Authentic')], get=g('preset'),
                set=st('preset'), help='Authentic: slower, less accurate, offside on full pitches'),
            Row('Time', options=[(True, 'Night, floodlights'), (False, 'Day')], get=g('night'), set=st('night')),
            Row('PLAY', lambda: self.start_match()),
        ], back=self.main_menu, footer='Left and right change an option.')

    def _team_help(self, k):
        return 'Teams of legends, icons, current stars and fantasy players, plus club sides'

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

        Menu(self, 'PAUSED', [
            Row('Resume', self._resume),
            Row('Camera', options=[(k, CAM_LABELS[k]) for k in CAM_MODES], get=lambda: s['camera'], set=cam),
            Row('Control hints', options=[(True, 'On'), (False, 'Off')], get=lambda: s['hints'], set=hints),
            Row('Restart match', lambda: self.start_match(shootout_only=bool(se.match.shootout and se.match.half == 1))),
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
        menu = Menu(self, 'FULL TIME', [
            Row('Rematch', lambda: self.start_match()),
            Row('Swap teams', self._swap_and_play),
            Row('Main menu', self._quit_to_menu),
        ], subtitle=title, back=self._quit_to_menu, y0=-0.42, width=1.2)
        text = '\n'.join(stats) + '\n\nPlayer of the match: %s' % motm.fb.name
        if lines:
            text += '\n\n' + '\n'.join(lines[:8])
        OnscreenText(text=text, parent=menu.root, pos=(0, 0.47), scale=0.042, fg=(0.92, 0.94, 1, 1),
                     align=TextNode.A_center)

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
