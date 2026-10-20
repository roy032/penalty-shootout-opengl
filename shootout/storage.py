"""Saving settings and records safely: write a temporary file, then rename it
over the old one, so a crash mid-save never leaves a half-written file."""

import json
import os
import tempfile


def write_json(path, data, indent=None):
    """Atomically replace path with data as JSON. Returns True on success."""
    folder = os.path.dirname(os.path.abspath(path))
    tmp = None
    try:
        os.makedirs(folder, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix='.' + os.path.basename(path) + '.', suffix='.tmp', dir=folder)
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=indent)
            f.flush()
            os.fsync(f.fileno())
        try:
            mode = os.stat(path).st_mode & 0o777          # keep the old file's permissions
        except OSError:
            umask = os.umask(0)
            os.umask(umask)
            mode = 0o666 & ~umask
        os.chmod(tmp, mode)
        os.replace(tmp, path)
        return True
    except (OSError, TypeError, ValueError):
        if tmp is not None:
            try:
                os.remove(tmp)
            except OSError:
                pass
        return False
