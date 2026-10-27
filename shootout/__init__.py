"""Penalty shootout game. The OpenGL front end lives in app.py; the rest is pure Python."""

import os

# PyOpenGL checks glGetError after every call by default, which costs 12-20%
# of the CPU time. It has to be switched off before OpenGL.GL is first
# imported; set SHOOTOUT_GL_DEBUG=1 to keep the checks while debugging.
try:
    import OpenGL
    OpenGL.ERROR_CHECKING = os.environ.get('SHOOTOUT_GL_DEBUG') == '1'
except ImportError:          # the pure-Python parts still work without PyOpenGL
    pass
