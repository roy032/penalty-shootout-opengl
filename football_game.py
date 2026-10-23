#!/usr/bin/env python3
"""Ultimate Football: run this to play."""

import sys

if __name__ == '__main__':
    if '--classic' in sys.argv:
        # The bundled Windows build starts the original penalty game this way
        import runpy
        runpy.run_path('penalty_shootout.py', run_name='__main__')
    else:
        from football.app import main
        main()
