from hitchserve.hitch_exception import WaitingForLogMessageTimeout
from hitchserve.utils import log, warn
import multiprocessing
import functools
import signal
import inspect
import pyuv
import json
import time
import os
import re

# TODO: All of this could do with some refactoring.


class Tail(object):
    def __init__(self, sublog):
        self._sublog = sublog
        self._logfilename = sublog._logfilename
        self.titles = sublog.titles
        self._end_of_file = os.stat(self._logfilename).st_size
        self.max_length_of_titles = max([len(title) for title in self.titles])
        self._closing = False
        self.trigger_exception = False

    def _timer_callback(self, t_handle):
        if time.time() - self._start_time > float(self.timeout):
            if self.raise_exception:
                self.trigger_exception = True
                self._close_handles()

    def _signal_callback(self, handle, signum):
        """Shutdown tail if ctrl-C is received."""
        if signum == signal.SIGINT:
            self._close_handles()

    def _close_handles(self):
        self._closing = True
        if self._timer_handle is not None and not self._timer_handle.closed:
            self._timer_handle.close()
            self._timer_handle = None
        if not self._event_handle.closed:
            self._event_handle.close()
            self._event_handle = None
        if not self._signal_handle.closed:
            self._signal_handle.close()
            self._signal_handle = None

    def _read_callback(self, match_function, do_function, handle, filename, events, error):
        with open(self._logfilename, "r") as filehandle:
            filehandle.seek(self._end_of_file)
            tailportion = filehandle.read()
        self._end_of_file = self._end_of_file + len(tailportion)

        for line in tailportion.split('\n'):
            matching_line = self._sublog._match_service(line)
            if matching_line is not None:
                if match_function(matching_line):
                    do_function(matching_line)

    def _printtuple(self, line):
        if type(line) is tuple:
            log("[{}] {}\n".format(line[0].rjust(self.max_length_of_titles), line[1]))
        else:
            log("{}\n".format(line))

    def wait_and_do(self, match_function, do_function, lines_back=0, timeout=None, raise_exception=True):
        self.loop = pyuv.Loop.default_loop()
        self.timeout = timeout
        self._start_time = time.time()
        self._started = False
        self._returnval = None
        self.raise_exception = raise_exception

        self._signal_handle = pyuv.Signal(self.loop)
        self._signal_handle.start(self._signal_callback, signal.SIGINT)

        if timeout is None:
            self._timer_handle = None
        else:
            self._timer_handle = pyuv.Timer(self.loop)
            self._timer_handle.start(self._timer_callback, 0.1, 0.1)

        self._event_handle = pyuv.fs.FSEvent(self.loop)

        self._event_handle.start(self._logfilename, 0,
            functools.partial(
                self._read_callback,
                match_function,
                do_function,
            )
        )

        lines = self._sublog.lines()

        for line in lines[len(lines) - lines_back:]:
            if match_function(line):
                do_function(line)

        if not self._started:
            self._started = True
            self.loop.run()
            self.loop = None
        else:
            self.loop = None

        if self.trigger_exception:
            raise WaitingForLogMessageTimeout("Timeout waiting for log line.")
        return self._returnval

    def follow(self, lines_back=0):
        return self.wait_and_do(
            lambda line: True,
            lambda line: self._printtuple(line),
            lines_back=lines_back,
            timeout=None,
            raise_exception=False
        )

    def grep(self, function, lines_back, timeout=None, raise_exception=False):
        return self.wait_and_do(
            lambda line: function,
            lambda line: self._printtuple(line),
            lines_back=lines_back,
            timeout=timeout,
            raise_exception=raise_exception
        )


    def until(self, function, lines_back=0, timeout=None, raise_exception=True):
        def on_match(line):
            self._returnval = line[1]
            self._close_handles()

        return self.wait_and_do(function, on_match, lines_back=lines_back, timeout=timeout, raise_exception=raise_exception)


    def until_json(self, function, lines_back=0, timeout=None, raise_exception=True):
        def json_match(line):
            try:
                return function(json.loads(line[1]))
            except ValueError:
                return False
            except IndexError:
                return False

        def on_match(line):
            self._returnval = json.loads(line[1])
            self._close_handles()

        return self.wait_and_do(json_match, on_match, lines_back=lines_back, timeout=timeout, raise_exception=raise_exception)

    def lines(self):
        lines = []
        with open(self._logfilename, "r") as log_handle:
            for line in log_handle:
                matching_line = self._sublog._match_service(line)
                if matching_line is not None:
                    lines.append(matching_line)
        return lines

    def cat(self, numlines=None):
        """Return a list of lines output by this service."""
        if len(self.titles) == 1:
            lines = self.lines()
            if numlines is not None:
                lines = lines[len(lines)-numlines:]
            log("\n".join(lines))
        else:
            lines = [self._printtuple(line[0], line[1]) for line in self.lines()]
            if numlines is not None:
                lines = lines[len(lines)-numlines:]
            log("".join(lines))


class SubLog(object):
    def __init__(self, name, titles):
        self.titles = titles
        self.name = name
        self._end_of_file = 0
        self.max_length_of_titles = max([len(title) for title in titles])

    def _match_service(self, line_with_color):
        """Return line if line matches this service's name, return None otherwise."""
        line = re.compile("(\x1b\[\d+m)+").sub("", line_with_color)        # Strip color codes

        regexp = re.compile(r"^\[(.*?)\]\s(.*?)$")
        if regexp.match(line):
            title = regexp.match(line).group(1).strip()
            if title in self.titles:
                return (title, regexp.match(line).group(2))
        return None

    @property
    def tail(self):
        """Get a Tail object for these logs."""
        return Tail(self)

    def lines(self):
        """Return a list of lines output by this service."""
        lines = []
        with open(self._logfilename, "r") as log_handle:
            for line in log_handle:
                matching_line = self._match_service(line)
                if matching_line is not None:
                    lines.append(matching_line)
        return lines

    def __repr__(self):
        """Generate a string representation."""
        return "\n".join(["[{}] {}".format(title.rjust(self.max_length_of_titles), line) for title, line in self.lines()])

    def __str__(self):
        return self.__repr__()

    def json(self):
        """Return a list of JSON objects output by this service."""
        lines = []
        for line in self.lines():
            try:
                if len(line) == 1:
                    lines.append(json.loads(line, strict=False))
                else:
                    lines.append(json.loads(line[1], strict=False))
            except ValueError:
                pass
        return lines

class ServiceLogs(SubLog):
    """Service log handling - tailing, matching lines, extracting JSON."""

    def __init__(self, name):
        self._name = name
        sout = name
        serr = "Err " + name
        setupout = "Setup " + name
        setuperr = "Err Setup " + name
        postout = "Post " + name
        posterr = "Post Err " + name

        self.out = SubLog(name, [sout ])
        self.err = SubLog(name, [serr ])
        self.setup = SubLog(name, [setupout, setuperr, ])
        self.setup.out = SubLog(name, [setupout, ])
        self.setup.err = SubLog(name, [setuperr, ])
        self.poststart = SubLog(name, [postout, posterr,])
        self.poststart.out = SubLog(name, [postout, ])
        self.poststart.err = SubLog(name, [posterr, ])
        super(ServiceLogs, self).__init__(name, titles=[sout, serr, setupout, setuperr, postout, posterr, ])

    def set_logfilename(self, logfilename):
        self._logfilename = logfilename
        self.out._logfilename = logfilename
        self.err._logfilename = logfilename
        self.setup._logfilename = logfilename
        self.setup.out._logfilename = logfilename
        self.setup.err._logfilename = logfilename
        self.poststart._logfilename = logfilename
        self.poststart.out._logfilename = logfilename
        self.poststart.err._logfilename = logfilename
