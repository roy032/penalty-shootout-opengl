"""Gamepad support through pygame's joystick module (optional).

Pad 1 drives Player 1's keys and pad 2 Player 2's, so everything that works
on the keyboard works on a pad. With hidden aim on a shared screen, the pad
rumbles to tell the kicker where the aim is: stronger towards the posts
(left motor) and towards the bar (right motor).
"""

import os

from .controls import CONTROLS

DEADZONE = 0.5
BUTTONS = {0: 'shoot', 1: 'special', 2: 'extra1', 3: 'extra2', 5: 'extra3'}   # 5: right bumper
START, BACK = 7, 6
RUMBLE_EVERY = 0.3


class Gamepads:
    def __init__(self):
        self.pads = []
        self.held = {}             # (pad index, name) -> key currently held down
        self.rumble_t = 0.0
        try:
            os.environ.setdefault('PYGAME_HIDE_SUPPORT_PROMPT', '1')
            os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')   # GLUT owns the real window
            import pygame
            pygame.display.init()
            pygame.joystick.init()
            self.pygame = pygame
            self.pads = [pygame.joystick.Joystick(i) for i in range(min(2, pygame.joystick.get_count()))]
            for p in self.pads:
                p.init()
        except Exception:
            self.pads = []

    @property
    def connected(self):
        return len(self.pads)

    def _set(self, game, i, name, key, down):
        held = self.held.get((i, name))
        if down and held is None:
            self.held[(i, name)] = key
            return game.key_down(key)
        if not down and held is not None:
            del self.held[(i, name)]
            game.key_up(held)
        return None

    def poll(self, game, dt):
        """Turn stick and button state into key presses. Returns 'quit' if asked."""
        if not self.pads:
            return None
        try:
            self.pygame.event.pump()
        except Exception:
            return None
        for i, pad in enumerate(self.pads):
            keys = CONTROLS['p1' if i == 0 else 'p2']
            x = pad.get_axis(0) if pad.get_numaxes() > 0 else 0.0
            y = pad.get_axis(1) if pad.get_numaxes() > 1 else 0.0
            hx, hy = pad.get_hat(0) if pad.get_numhats() > 0 else (0, 0)
            self._set(game, i, 'left', keys['left'], x < -DEADZONE or hx < 0)
            self._set(game, i, 'right', keys['right'], x > DEADZONE or hx > 0)
            self._set(game, i, 'up', keys['up'], y < -DEADZONE or hy > 0)
            self._set(game, i, 'down', keys['down'], y > DEADZONE or hy < 0)
            for b, action in BUTTONS.items():
                if b < pad.get_numbuttons():
                    self._set(game, i, action, keys[action], pad.get_button(b))
            if START < pad.get_numbuttons():
                self._set(game, i, 'start', 'p', pad.get_button(START))
            if BACK < pad.get_numbuttons():
                self._set(game, i, 'back', 'c', pad.get_button(BACK))
        self._rumble(game, dt)
        return None

    def _rumble(self, game, dt):
        """Private aim: buzz the kicker's pad when the reticle is hidden."""
        self.rumble_t += dt
        if self.rumble_t < RUMBLE_EVERY:
            return
        self.rumble_t = 0.0
        if game.ui != 'playing' or game.phase != 'aim' or not game.is_human(game.kicker):
            return
        shared = game.is_human(game.keeper_side())
        if not (shared and game.hidden_aim):
            return
        i = 0 if game.kicker == 'p1' else 1
        if i >= len(self.pads):
            return
        low = min(1.0, abs(game.aim[0]) / 4.0)
        high = min(1.0, max(0.0, game.aim[1] - 0.2) / 2.6)
        try:
            self.pads[i].rumble(low * 0.8, high * 0.8, 120)
        except Exception:
            pass
