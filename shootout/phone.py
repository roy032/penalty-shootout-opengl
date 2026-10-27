"""Phone as a private controller for PvP.

When switched on in the menu, the game serves one small web page on the
local network. The kicker opens it on their phone, enters the PIN shown on
screen and aims by touch, so the other player cannot see where the shot is
going. The server only runs while the setting is on, and every command needs
the PIN; a phone that gets the PIN wrong too often is locked out.

The page sends where it was touched as a share of the goal (0..1 across,
0..1 up), and the game turns that into metres for the goal in use, so it
works on park, futsal and beach goals too.
"""

import hmac
import json
import math
import queue
import random
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

PORT = 8765
ACTIONS = ('shoot', 'special', 'extra1', 'extra2')
MAX_TRIES = 5            # wrong PINs from one address before it is locked out
MARGIN = 0.1             # the page lets you aim a little wide and over, as the keys do

PAGE = """<!doctype html>
<html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,user-scalable=no">
<title>Penalty Shootout controller</title>
<style>
body{margin:0;font-family:sans-serif;background:#0b1220;color:#fff;text-align:center;touch-action:none}
#goal{position:relative;margin:16px auto;width:92vw;height:46vw;border:6px solid #fff;border-bottom:none;
background:repeating-linear-gradient(90deg,#1d6b2a 0 10%,#22802f 10% 20%)}
#dot{position:absolute;width:28px;height:28px;margin:-14px;border-radius:50%;border:4px solid #ffd21a}
button{font-size:20px;margin:6px;padding:14px 18px;border-radius:10px;border:0;background:#2a3550;color:#fff}
#shoot{background:#1f8a3a;width:60vw}
input,select{font-size:20px;padding:8px;margin:6px;width:8em}
</style></head><body>
<h3>Penalty Shootout</h3>
<div><select id="slot"><option value="p1">Player 1</option><option value="p2">Player 2</option></select>
<input id="pin" placeholder="PIN" inputmode="numeric"></div>
<div id="goal"><div id="dot"></div></div>
<div><button id="shoot">SHOOT</button></div>
<div><button data-a="special">Shot type</button><button data-a="extra1">Disguise</button>
<button data-a="extra2">Celebrate</button></div>
<script>
var goal=document.getElementById('goal'),dot=document.getElementById('dot');
function send(body){body.pin=document.getElementById('pin').value;body.slot=document.getElementById('slot').value;
fetch('/cmd',{method:'POST',body:JSON.stringify(body)});}
function aim(e){var r=goal.getBoundingClientRect(),t=e.touches?e.touches[0]:e;
var fx=(t.clientX-r.left)/r.width,fy=(t.clientY-r.top)/r.height;
fx=Math.max(-0.1,Math.min(1.1,fx));fy=Math.max(-0.2,Math.min(1,fy));
dot.style.left=(fx*100)+'%';dot.style.top=(fy*100)+'%';
send({aim:[fx,1-fy]});e.preventDefault();}
goal.addEventListener('touchstart',aim);goal.addEventListener('touchmove',aim);goal.addEventListener('mousedown',aim);
document.getElementById('shoot').onclick=function(){send({action:'shoot'});};
document.querySelectorAll('[data-a]').forEach(function(b){b.onclick=function(){send({action:b.dataset.a});};});
</script></body></html>
"""


def local_ip():
    """The address other devices on the network can reach (no packets are sent)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('10.255.255.255', 1))
        return s.getsockname()[0]
    except OSError:
        return '127.0.0.1'
    finally:
        s.close()


class PhoneServer:
    def __init__(self, port=PORT, pin=None, host='0.0.0.0'):
        self.pin = pin or f'{random.SystemRandom().randrange(1000000):06d}'
        self.commands = queue.Queue()
        self.failures = {}            # address -> wrong PINs
        self.lock = threading.Lock()
        server = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                if urlparse(self.path).path != '/':
                    self.send_error(404)
                    return
                body = PAGE.encode()
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self):
                if urlparse(self.path).path != '/cmd':
                    self.send_error(404)
                    return
                n = min(int(self.headers.get('Content-Length') or 0), 2048)
                try:
                    cmd = json.loads(self.rfile.read(n) or b'{}')
                except ValueError:
                    cmd = {}
                if not isinstance(cmd, dict) or not server.accept(cmd, self.client_address[0]):
                    self.send_error(403)
                    return
                self.send_response(204)
                self.end_headers()

        self.httpd = ThreadingHTTPServer((host, port), Handler)
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def accept(self, cmd, address='local'):
        """Validate a command from the page and queue it for the game thread."""
        with self.lock:
            if self.failures.get(address, 0) >= MAX_TRIES:
                return False                     # locked out: too many wrong PINs
            if not hmac.compare_digest(str(cmd.get('pin')).encode(), self.pin.encode()):
                self.failures[address] = self.failures.get(address, 0) + 1
                return False
        if cmd.get('slot') not in ('p1', 'p2'):
            return False
        if 'aim' in cmd:
            try:
                fx, fy = (float(v) for v in cmd['aim'])
            except (TypeError, ValueError):
                return False
            if not (math.isfinite(fx) and math.isfinite(fy)):
                return False
            fx = min(1.0 + MARGIN, max(-MARGIN, fx))
            fy = min(1.0 + MARGIN, max(-MARGIN, fy))
            self.commands.put((cmd['slot'], 'aim', (fx, fy)))
            return True
        if cmd.get('action') in ACTIONS:
            self.commands.put((cmd['slot'], 'action', cmd['action']))
            return True
        return False

    def url(self):
        return f'http://{local_ip()}:{self.port}'

    def apply(self, game):
        """Run queued commands on the game (call from the main loop)."""
        from . import config as C
        while True:
            try:
                slot, kind, value = self.commands.get_nowait()
            except queue.Empty:
                return
            if kind == 'aim':
                fx, fy = value                    # share of the goal in use, not of a full-size one
                game.set_aim(slot, (fx - 0.5) * 2.0 * C.GOAL_HALF_WIDTH, fy * C.GOAL_HEIGHT)
            else:
                key = game.keys_for(slot)[value]
                game.key_down(key)
                game.key_up(key)

    def stop(self):
        self.httpd.shutdown()
        self.httpd.server_close()
