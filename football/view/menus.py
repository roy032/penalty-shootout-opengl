"""A small menu toolkit: a titled list of rows you drive with keyboard, mouse
or gamepad. Rows are buttons, or options you change with left/right."""

from direct.gui.DirectGui import DirectButton, DirectFrame, DGG
from direct.gui.OnscreenText import OnscreenText
from panda3d.core import TextNode

BG = (0.02, 0.03, 0.06, 0.82)
ROW = (0.1, 0.12, 0.18, 0.85)
SEL = (0.95, 0.75, 0.2, 1.0)
TXT = (0.95, 0.96, 1.0, 1)


class Row:
    def __init__(self, label, action=None, options=None, get=None, set=None, help=''):
        self.label = label
        self.action = action        # called on confirm
        self.options = options      # list of (value, text) for left/right rows
        self.get = get
        self.set = set
        self.help = help

    def text(self):
        if self.options is None:
            return self.label
        v = self.get()
        shown = next((t for val, t in self.options if val == v), str(v))
        return '%s:   <  %s  >' % (self.label, shown)

    def step(self, d):
        if not self.options:
            return False
        vals = [v for v, _ in self.options]
        cur = self.get()
        i = vals.index(cur) if cur in vals else 0
        self.set(vals[(i + d) % len(vals)])
        return True


class Menu:
    def __init__(self, app, title, rows, back=None, subtitle='', width=1.3, y0=0.45, footer=''):
        self.app = app
        self.rows = rows
        self.back = back
        self.sel = 0
        self.root = DirectFrame(parent=app.aspect2d, frameColor=BG, frameSize=(-width / 2 - 0.08, width / 2 + 0.08,
                                                                            -0.95, 0.85))
        OnscreenText(text=title, parent=self.root, pos=(0, 0.66), scale=0.11, fg=SEL, align=TextNode.A_center,
                     shadow=(0, 0, 0, 1))
        if subtitle:
            OnscreenText(text=subtitle, parent=self.root, pos=(0, 0.57), scale=0.045, fg=(0.8, 0.85, 0.95, 1),
                         align=TextNode.A_center)
        self.buttons = []
        n = len(rows)
        gap = min(0.12, 1.25 / max(1, n))
        for i, r in enumerate(rows):
            b = DirectButton(parent=self.root, text=r.text(), text_scale=0.055 if gap >= 0.1 else 0.046,
                             text_fg=TXT, text_align=TextNode.A_center, frameColor=ROW,
                             frameSize=(-width / 2, width / 2, -gap * 0.38, gap * 0.48), pos=(0, 0, y0 - i * gap),
                             relief=DGG.FLAT, command=self._click, extraArgs=[i], pressEffect=1)
            b.bind(DGG.ENTER, self._hover, [i])
            self.buttons.append(b)
        self.help = OnscreenText(text='', parent=self.root, pos=(0, -0.86), scale=0.04, fg=(0.75, 0.8, 0.9, 1),
                                 align=TextNode.A_center, mayChange=True, wordwrap=34)
        self.footer = footer
        self._refresh()
        app.menu_stack_push(self)

    def _hover(self, i, _evt=None):
        if i != self.sel:
            self.sel = i
            self.app.sound_ui('move')
            self._refresh()

    def _click(self, i):
        self.sel = i
        self.confirm()

    def _refresh(self):
        for i, (b, r) in enumerate(zip(self.buttons, self.rows)):
            b['text'] = r.text()
            b['frameColor'] = SEL if i == self.sel else ROW
            b['text_fg'] = (0.05, 0.05, 0.08, 1) if i == self.sel else TXT
        r = self.rows[self.sel] if self.rows else None
        self.help.setText((r.help if r else '') or self.footer)

    def refresh(self):
        self._refresh()

    # ------------------------------------------------------------- input
    def key(self, k):
        if k == 'up':
            self.sel = (self.sel - 1) % len(self.rows)
            self.app.sound_ui('move')
        elif k == 'down':
            self.sel = (self.sel + 1) % len(self.rows)
            self.app.sound_ui('move')
        elif k in ('left', 'right'):
            if self.rows[self.sel].step(-1 if k == 'left' else 1):
                self.app.sound_ui('move')
        elif k == 'confirm':
            self.confirm()
            return
        elif k == 'back':
            if self.back:
                self.app.sound_ui('back')
                self.back()
            return
        self._refresh()

    def confirm(self):
        r = self.rows[self.sel]
        if r.action:
            self.app.sound_ui('confirm')
            r.action()
        elif r.options:
            r.step(1)
            self.app.sound_ui('move')
            self._refresh()

    def destroy(self):
        self.app.menu_stack_pop(self)
        self.root.destroy()
