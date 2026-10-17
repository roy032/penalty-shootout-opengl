"""LAN play: two copies of the game kept in lockstep over TCP.

The host plays as Player 1 and the joiner as Player 2; each uses their own
Player 1 keys. The host sends the settings and a random seed, then both
sides run the same simulation one 1/60 s frame at a time. Every frame each
side sends the actions pressed on its keyboard, scheduled a few frames
ahead, and a frame only runs once both sides' actions for it have arrived.
Nothing else crosses the network, so the two games stay identical as long
as the simulation is deterministic (it is: fixed steps and a seeded rng).
"""

import json
import random
import select
import socket

from . import controls
from .controls import CONTROLS

PORT = 50505
STEP = 1.0 / 60.0
DELAY = 4                # frames of input delay: hides the round trip on a LAN
SETTINGS = ('kicks_per_side', 'order', 'variant', 'weather', 'daytime', 'assist', 'squads')
GLOBAL_KEYS = ('p', 'r', 'v')          # pause, restart, watch the replay: both screens
LOCAL_KEYS = ('c', 'h', 'n', 'f', 'b', '\t')   # camera, help, sound, files, share, report: this screen only


def listen(port=PORT, bind=''):
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((bind, port))
    server.listen(1)
    return server


def accept(server, timeout=None):
    server.settimeout(timeout)
    conn, _ = server.accept()
    return conn


def connect(address, timeout=10.0):
    host, _, port = address.partition(':')
    return socket.create_connection((host, int(port or PORT)), timeout)


class NetSession:
    def __init__(self, sock, slot):
        self.sock = sock
        self.sock.settimeout(None)
        self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.slot = slot
        self.keys = dict(CONTROLS['p1'])        # this player's own keys, whichever side they play
        self.buf = b''
        self.inbox = []
        self.frame = 0                          # next frame to simulate
        self.sent = 0                           # next frame to send our input for
        self.pending = []
        self.remote = {}
        self.local = {}
        self.accum = 0.0
        self.closed = False

    # --------------------------------------------------------------- wire
    def _send(self, msg):
        try:
            self.sock.sendall((json.dumps(msg) + '\n').encode())
        except OSError:
            self.closed = True

    def _read(self, wait=0.0):
        while not self.closed:
            try:
                ready, _, _ = select.select([self.sock], [], [], wait)
            except (OSError, ValueError):
                self.closed = True
                return
            if not ready:
                return
            try:
                data = self.sock.recv(65536)
            except OSError:
                data = b''
            if not data:
                self.closed = True
                return
            self.buf += data
            while b'\n' in self.buf:
                line, self.buf = self.buf.split(b'\n', 1)
                try:
                    self.inbox.append(json.loads(line))
                except ValueError:
                    continue
            wait = 0.0
        return

    def _take_frames(self):
        rest = []
        for msg in self.inbox:
            if msg.get('t') == 'f':
                self.remote[int(msg['n'])] = [tuple(e) for e in msg['e']]
            else:
                rest.append(msg)
        self.inbox = rest

    # ----------------------------------------------------------- handshake
    def start_host(self, game):
        """Pick the seed, send the settings, and start the match here."""
        seed = random.randrange(1 << 30)
        settings = {k: getattr(game, k) for k in SETTINGS}
        settings['teams'] = dict(game.teams)
        self._send(dict(t='hello', seed=seed, settings=settings))
        self._begin(game, seed, settings)

    def start_join(self, game, timeout=15.0):
        """Wait for the host's settings, then start the same match."""
        waited = 0.0
        while not self.closed and waited < timeout:
            self._read(0.1)
            waited += 0.1
            for msg in self.inbox:
                if msg.get('t') == 'hello':
                    self.inbox.remove(msg)
                    self._begin(game, msg['seed'], msg['settings'])
                    return True
        return False

    def _begin(self, game, seed, settings):
        for k in SETTINGS:
            if k in settings:
                setattr(game, k, settings[k])
        game.teams = {s: int(v) for s, v in settings.get('teams', game.teams).items()}
        controls.reset()                    # both games read the same bindings for each side
        game.mode = 'pvp'
        game.local_slot = self.slot
        if game.squads == 'pick':
            game.squads = 'legends'          # no select screen over the network: a random draft
        game.rng = random.Random(seed)
        game._begin_match()

    # --------------------------------------------------------------- input
    def key(self, game, key, down):
        """A key pressed on this computer. Returns 'quit' for Esc."""
        if key == '\x1b' and down:
            if game.photo:
                game.photo = False
                return None
            self.close()
            return 'quit'
        for action, k in self.keys.items():
            if k == key:
                self.pending.append(('a', self.slot, action, bool(down)))
                return None
        if key in GLOBAL_KEYS and down:
            self.pending.append(('g', self.slot, key, True))
        elif key in LOCAL_KEYS and down:
            game.key_down(key)
            game.key_up(key)
        return None

    def _apply(self, game, events):
        for kind, slot, what, down in events:
            if kind == 'a':
                k = CONTROLS[slot][what]
                if down:
                    game.key_down(k)
                else:
                    game.key_up(k)
            elif kind == 'g':
                game.key_down(what)
                game.key_up(what)

    # ---------------------------------------------------------------- loop
    def pump(self, game, dt):
        """Advance the game by as many whole frames as both sides allow."""
        self._read()
        self._take_frames()
        if self.closed:
            if not getattr(self, '_told', False):
                game.toast = ('The other player has left: LAN game over', game.clock)
                self._told = True
            game.paused = True
            return 0
        self.accum = min(self.accum + dt, 0.25)
        ran = 0
        while self.accum >= STEP:
            while self.sent <= self.frame + DELAY:
                self.local[self.sent] = self.pending
                self._send(dict(t='f', n=self.sent, e=self.pending))
                self.pending = []
                self.sent += 1
            if self.frame not in self.remote:
                break                                   # waiting on the other side
            mine, theirs = self.local.pop(self.frame), self.remote.pop(self.frame)
            self._apply(game, mine + theirs if self.slot == 'p1' else theirs + mine)
            game.update(STEP)
            self.frame += 1
            self.accum -= STEP
            ran += 1
        return ran

    def close(self):
        self.closed = True
        try:
            self.sock.close()
        except OSError:
            pass
