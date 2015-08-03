import os
import io

def _write(handle, message):
    if isinstance(handle, io.TextIOWrapper):
        handle.write(message)
    else:
        handle.write(message.encode('utf8'))
    handle.flush()

def log(message):
    """Output to stdout."""
    import sys
    _write(sys.stdout, message)

def warn(message):
    """Output to stderr."""
    import sys
    _write(sys.stderr, message)
