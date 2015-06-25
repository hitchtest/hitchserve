import os

def _write(handle, message):
    if os.isatty(handle.fileno()):
        handle.write(message)
    else:
        handle.write(bytes(message, 'utf8'))
    handle.flush()

def log(message):
    """Output to stdout."""
    import sys
    _write(sys.stdout, message)

def warn(message):
    """Output to stderr."""
    import sys
    _write(sys.stderr, message)
