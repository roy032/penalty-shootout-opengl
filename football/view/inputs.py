"""Keyboard and gamepad input mapped to named actions (pass, shoot, sprint...).
Both players can share a keyboard; any number of gamepads work."""

import json
import os

from panda3d.core import InputDevice, KeyboardButton, ButtonHandle

from ..sim.match import Input

ACTIONS = ['up', 'down', 'left', 'right', 'pass', 'shoot', 'through', 'lob', 'sprint', 'switch', 'finesse', 'skill']
LABELS = {'up': 'Up', 'down': 'Down', 'left': 'Left', 'right': 'Right', 'pass': 'Pass / tackle',
          'shoot': 'Shoot / slide', 'through': 'Through ball / 2nd man press', 'lob': 'Lob / cross',
          'sprint': 'Sprint', 'switch': 'Switch player', 'finesse': 'Finesse (hold)', 'skill': 'Skill move'}

DEFAULT_KEYS = [
    dict(up='w', down='s', left='a', right='d', **{'pass': 'j'}, shoot='k', through='l', lob='i', sprint='lshift',
         switch='q', finesse='e', skill='space'),
    dict(up='arrow_up', down='arrow_down', left='arrow_left', right='arrow_right', **{'pass': '/'},
         shoot='.', through=',', lob=';', sprint='rshift', switch='rcontrol', finesse="'", skill='enter'),
]

# Xbox-style layout (Panda3D names the face buttons by position)
PAD = {'pass': 'face_a', 'shoot': 'face_b', 'through': 'face_y', 'lob': 'face_x', 'switch': 'lshoulder',
       'finesse': 'rshoulder', 'skill': 'rstick'}
PAD_NAV = {'confirm': 'face_a', 'back': 'face_b', 'start': 'start', 'select': 'back'}


def _handle(name):
    """Turn a key name into a ButtonHandle."""
    special = {
        'lshift': KeyboardButton.lshift(), 'rshift': KeyboardButton.rshift(), 'lcontrol': KeyboardButton.lcontrol(),
        'rcontrol': KeyboardButton.rcontrol(), 'space': KeyboardButton.space(), 'enter': KeyboardButton.enter(),
        'tab': KeyboardButton.tab(), 'escape': KeyboardButton.escape(), 'arrow_up': KeyboardButton.up(),
        'arrow_down': KeyboardButton.down(), 'arrow_left': KeyboardButton.left(), 'arrow_right': KeyboardButton.right(),
        'lalt': KeyboardButton.lalt(), 'ralt': KeyboardButton.ralt(), 'backspace': KeyboardButton.backspace(),
    }
    if name in special:
        return special[name]
    if len(name) == 1:
        return KeyboardButton.ascii_key(name)
    return ButtonHandle(name)


def key_label(name):
    return {'lshift': 'L-Shift', 'rshift': 'R-Shift', 'lcontrol': 'L-Ctrl', 'rcontrol': 'R-Ctrl', 'space': 'Space',
            'arrow_up': 'Up', 'arrow_down': 'Down', 'arrow_left': 'Left', 'arrow_right': 'Right',
            'enter': 'Enter'}.get(name, name.upper())


class Inputs:
    def __init__(self, base, path=None):
        self.base = base
        self.path = path
        self.keys = [dict(k) for k in DEFAULT_KEYS]
        self.load()
        self._compile()
        self.pads = []
        self.prev = {}
        self.pad_prev = {}
        mgr = base.devices
        for d in mgr.get_devices(InputDevice.DeviceClass.gamepad):
            self._add_pad(d)
        base.accept('connect-device', self._connect)
        base.accept('disconnect-device', self._disconnect)

    # ------------------------------------------------------------ devices
    def _add_pad(self, d):
        if d in self.pads:
            return
        self.pads.append(d)
        self.base.attach_input_device(d, prefix='pad%d' % (len(self.pads) - 1))

    def _connect(self, d):
        if d.device_class == InputDevice.DeviceClass.gamepad:
            self._add_pad(d)

    def _disconnect(self, d):
        if d in self.pads:
            self.base.detach_input_device(d)
            self.pads.remove(d)

    def pad_count(self):
        return len(self.pads)

    # ------------------------------------------------------------ bindings
    def load(self):
        if not self.path:
            return
        try:
            with open(self.path) as f:
                data = json.load(f)
            for i, k in enumerate(data.get('keys', [])[:2]):
                for a in ACTIONS:
                    if isinstance(k.get(a), str):
                        self.keys[i][a] = k[a]
        except (OSError, ValueError, AttributeError):
            pass

    def save(self):
        if not self.path:
            return
        tmp = self.path + '.tmp'
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            with open(tmp, 'w') as f:
                json.dump(dict(keys=self.keys), f, indent=1)
            os.replace(tmp, self.path)
        except OSError:
            pass

    def rebind(self, player, action, key):
        """Bind key to action; if another action already had it, they swap."""
        km = self.keys[player]
        old = km[action]
        for a, k in km.items():
            if k == key and a != action:
                km[a] = old
        km[action] = key
        self._compile()
        self.save()

    def reset(self):
        self.keys = [dict(k) for k in DEFAULT_KEYS]
        self._compile()
        self.save()

    def _compile(self):
        self.handles = [{a: _handle(k) for a, k in km.items()} for km in self.keys]

    # ------------------------------------------------------------ polling
    def _down(self, h):
        mw = self.base.mouseWatcherNode
        try:
            return mw.has_mouse() is not None and mw.is_button_down(h)
        except Exception:
            return False

    def read(self, slot, axes=None):
        """Input for controller `slot`: keyboard layout `slot` and gamepad `slot` together.
        axes maps the stick to the camera."""
        inp = Input()
        held = set()
        mx = my = 0.0
        if slot < len(self.handles):
            hs = self.handles[slot]
            if self._down(hs['left']):
                mx -= 1
            if self._down(hs['right']):
                mx += 1
            if self._down(hs['up']):
                my += 1
            if self._down(hs['down']):
                my -= 1
            for a in ('pass', 'shoot', 'through', 'lob', 'sprint', 'switch', 'finesse', 'skill'):
                if self._down(hs[a]):
                    held.add(a)
        if True:
            i = slot
            if i < len(self.pads):
                d = self.pads[i]
                lx = d.find_axis(InputDevice.Axis.left_x)
                ly = d.find_axis(InputDevice.Axis.left_y)
                if lx and abs(lx.value) > 0.18:
                    mx += lx.value
                if ly and abs(ly.value) > 0.18:
                    my += ly.value
                for a, b in PAD.items():
                    btn = d.find_button(b)
                    if btn and btn.pressed:
                        held.add(a)
                rt = d.find_axis(InputDevice.Axis.right_trigger)
                if rt and rt.value > 0.4:
                    held.add('sprint')
                lt = d.find_axis(InputDevice.Axis.left_trigger)
                if lt and lt.value > 0.4:
                    held.add('skill')
                # D-pad works as a stick too
                for b, (dx, dy) in (('dpad_left', (-1, 0)), ('dpad_right', (1, 0)), ('dpad_up', (0, 1)),
                                    ('dpad_down', (0, -1))):
                    btn = d.find_button(b)
                    if btn and btn.pressed:
                        mx += dx
                        my += dy
        mx, my = max(-1.0, min(1.0, mx)), max(-1.0, min(1.0, my))
        if axes and (mx or my):
            (rx, ry), (fx, fy) = axes
            mx, my = rx * mx + fx * my, ry * mx + fy * my
        inp.move = (mx, my)
        prev = self.prev.get(slot, set())
        inp.held = held
        inp.pressed = held - prev
        inp.released = prev - held
        self.prev[slot] = held
        return inp

    def menu_keys(self):
        """Navigation for menus from any pad: returns a set of 'up', 'down', 'left', 'right', 'confirm', 'back', 'start'."""
        out = set()
        for i, d in enumerate(self.pads):
            now = set()
            for name, b in PAD_NAV.items():
                btn = d.find_button(b)
                if btn and btn.pressed:
                    now.add(name)
            for b, nm in (('dpad_up', 'up'), ('dpad_down', 'down'), ('dpad_left', 'left'), ('dpad_right', 'right')):
                btn = d.find_button(b)
                if btn and btn.pressed:
                    now.add(nm)
            ly = d.find_axis(InputDevice.Axis.left_y)
            lx = d.find_axis(InputDevice.Axis.left_x)
            if ly and ly.value > 0.6:
                now.add('up')
            if ly and ly.value < -0.6:
                now.add('down')
            if lx and lx.value > 0.6:
                now.add('right')
            if lx and lx.value < -0.6:
                now.add('left')
            prev = self.pad_prev.get(i, set())
            out |= now - prev
            self.pad_prev[i] = now
        return out
