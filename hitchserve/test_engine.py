from hitchserve.service_handle import ServiceHandle
from hitchserve.service_engine import ServiceEngine
from hitchserve.hitch_exception import ServiceStartupTimeoutException
from colorama import Fore, Back, Style
import functools
import termios
import signal
import psutil
import time
import pyuv
import sys
import os

# TODO: Report actual directory being used at the beginning of the logs.
# TODO: Move all from-previous-test-run-process killing code here.
# TODO: Rename TestEngine -> OrchestrationEngine

class TestEngine(object):
    """Engine (and thread) that brings together all I/O and events driving hitchserve."""
    _timedout = False
    _ready = False
    _driver_sent_shutdown_signal = False
    _shutdown_triggered = False
    ipython_on = False

    def __init__(self, service_bundle):
        self.service_bundle = service_bundle

    def signal_cb(self, handle, signum):
        """Handle ctrl-C if not in ipython shell. Always shutdown on SIGTERM."""
        SIGNALS_TO_NAMES_DICT = dict((getattr(signal, n), n) \
            for n in dir(signal) if n.startswith('SIG') and '_' not in n )
        self.logline("Signal {} received...".format(SIGNALS_TO_NAMES_DICT.get(signum)))
        if signum in (signal.SIGTERM, signal.SIGHUP, signal.SIGQUIT, signal.SIGINT):
            self.stop()

    def handle_tail(self, fullfilename, title, color, handle, filename, events, error):
        with open(fullfilename, 'r') as filehandle:
            filehandle.seek(self.tail_positions[fullfilename])
            tailportion = filehandle.read()
        self.tail_positions[fullfilename] = self.tail_positions[fullfilename] + len(tailportion) #os.stat(fullfilename).st_size

        for line in tailportion.split('\n'):
            if line != "":
                if color is None:
                    self.logline(line, title=title)
                else:
                    self.logline(line, title=title, color=color)


    # TODO: Close tail handles after set up / poststart is finished.
    def initiate_tail(self, stdlog, title, color):
        filename = self.service_bundle.hitch_dir.stdlogdir() + os.sep + stdlog
        with open(filename, "a"):
            os.utime(filename, None)
        self.tail_positions[filename] = 0
        tail = pyuv.fs.FSEvent(self.loop)
        tail.start(filename, 0, functools.partial(self.handle_tail, filename, title, color))
        self.tail_handles.append(tail)
        with open(filename, "a"):
            os.utime(filename, None)

    def start(self, messages_to_driver, messages_to_bundle_engine):
        """Orchestrate processes and I/O pipes."""

        os.setpgrp()
        self.service_bundle.hitch_dir.save_pgid("bundleengine", os.getpgid(os.getpid()))
        self.service_engine = ServiceEngine(self, self.service_bundle.values())

        self.start_time = time.time()
        self.messages_to_driver = messages_to_driver
        self.messages_to_bundle_engine = messages_to_bundle_engine

        os.chdir(self.service_bundle.hitch_dir.project_directory)
        self.logfile = open(self.service_bundle.hitch_dir.testlog(), "a")

        self.loop = pyuv.Loop.default_loop()

        self.pipe_logfile = pyuv.Pipe(self.loop)
        self.pipe_logfile.open(self.logfile.fileno())

        if not self.service_bundle.quiet:
            self.pipe_stdout = pyuv.Pipe(self.loop)
            self.pipe_stdout.open(sys.stdout.fileno())

        self.service_engine.start_services_without_prerequisites()


        self.timer_handler = pyuv.Timer(self.loop)
        self.timer_handler.start(self.poll_handler, 0.01, 0.01)

        self.tail_handles = []
        self.tail_positions = {}

        self.initiate_tail("driver.out", "Test", None)
        self.initiate_tail("driver.err", "Err Test", Fore.YELLOW)

        self.service_engine.tail_setup_and_poststart()

        self.signal_h = pyuv.Signal(self.loop)
        self.signal_h.start(self.signal_cb, signal.SIGINT)
        self.signal_h.start(self.signal_cb, signal.SIGTERM)

        self.loop.run()
        self.loop = None
        os.kill(os.getpid(), signal.SIGKILL)

    def _close_pipes(self):
        """Close all the pipes in order to shut the engine down."""
        if not self.service_bundle.quiet:
            if not self.pipe_stdout.closed:
                self.pipe_stdout.close()
        for pipe in self.service_engine.pipes():
            if pipe is not None and not pipe.closed:
                pipe.close()
        if not self.signal_h.closed:
            self.signal_h.close()
        if not self.timer_handler.closed:
            self.timer_handler.close()
        for handle in self.tail_handles:
            handle.close()
        self.logfile.close()

    def writeline(self, identifier, line, color=''):
        """Log a line to the log file and/or stdout."""
        reset_all = Fore.RESET + Back.RESET + Style.RESET_ALL
        full_line = "{0}{1}[{2}] {3}{4}\n".format(
            reset_all,
            color,
            identifier.rjust(self.service_engine.longest_service_name() + 10),
            line,
            reset_all
        )
        if not self.ipython_on and not self.service_bundle.quiet:
            self.pipe_stdout.write(full_line.encode('utf-8'))
        self.pipe_logfile.write(full_line.encode('utf-8'))

    def logline(self, line, title="Hitch", color=''):
        self.writeline(title, line, color)

    def warnline(self, line):
        self.writeline("WARNING", line, color=Fore.YELLOW)

    def on_pipe_read(self, pipe_handle, data, error):
        if data is None:
            pass
        else:
            self.service_engine.handle_input(pipe_handle, data)

    def poll_handler(self, timer_handle):
        """Handle messages from the test thread and timeout."""
        self.service_engine.poll()

        if not self._ready and self.service_engine.all_services_ready():
            startup_duration = time.time() - self.start_time
            self.logline("READY in {0:.1f} seconds.".format(startup_duration), color=Style.BRIGHT)
            self.messages_to_driver.put("READY")
            self._ready = True

        if not self.messages_to_bundle_engine.empty():
            msg = self.messages_to_bundle_engine.get()
            if not self._driver_sent_shutdown_signal and msg == "SHUTDOWN":
                self._driver_sent_shutdown_signal = True
                self.stop()
            if msg == "IPYTHONON":
                self.ipython_on = True
            elif msg == "IPYTHONOFF":
                self.ipython_on = False

        if not self._ready and not self._timedout:
            if time.time() - self.start_time > self.service_bundle.startup_timeout:
                self.warnline("TIMEOUT")
                self._timedout = True
                self.messages_to_driver.put(
                    ServiceStartupTimeoutException(
                        "Services not ready after {} second timeout: {}".format(
                            self.service_bundle.startup_timeout,
                            ", ".join([x.name for x in self.service_engine.not_ready_services()]),
                        )
                    )
                )


    def stop(self):
        """Shut down all hitchserve services and processes started from driver process, kill if necessary."""
        if not self._shutdown_triggered:
            self._shutdown_triggered = True
            self.ipython_on = False

            start_shutdown_time = time.time()

            for child in psutil.Process(os.getppid()).children():
                if child is not None and child.is_running() and child.pid != os.getpid():
                    for grandchild in psutil.Process(child.pid).children(recursive=True):
                        try:
                            grandchild.send_signal(signal.SIGINT)
                            self.logline("Stopping PID {} : {}".format(grandchild.pid, " ".join(grandchild.cmdline())))
                        except psutil.NoSuchProcess:
                            pass
                    try:
                        child.send_signal(signal.SIGINT)
                        self.logline("Stopping PID {} : {}".format(child.pid, " ".join(child.cmdline())))
                    except psutil.NoSuchProcess:
                        pass

            self.service_engine.stop()
            still_alive = False

            if time.time() < start_shutdown_time + self.service_bundle.shutdown_timeout:
                sleep_time = self.service_bundle.shutdown_timeout - (time.time() - start_shutdown_time)
                for i in range(0, int(sleep_time * 100)):
                    still_alive = False
                    for child in psutil.Process(os.getppid()).children():
                        if child is not None and child.is_running() and child.pid != os.getpid():
                            for grandchild in psutil.Process(child.pid).children(recursive=True):
                                try:
                                    if grandchild.status != "zombie":
                                        still_alive = True
                                except psutil.NoSuchProcess:
                                    pass
                    if not still_alive:
                        break
                    time.sleep(0.01)

            if still_alive:
                for child in psutil.Process(os.getppid()).children():
                    if child is not None and child.is_running() and child.pid != os.getpid():
                        for grandchild in psutil.Process(child.pid).children(recursive=True):
                            try:
                                fullname = " ".join(grandchild.cmdline())
                                grandchild.send_signal(signal.SIGKILL)
                                self.logline("Killing PID {} : {}".format(grandchild.pid, grandchild.name))
                            except psutil.NoSuchProcess:
                                pass
                        try:
                            child.send_signal(signal.SIGKILL)
                            self.logline("Killing PID {} : {}".format(child.pid, child.name()))
                        except psutil.NoSuchProcess:
                            pass

            self.logline("Shutdown successful in {0:.1f} seconds".format(time.time() - start_shutdown_time))
            self._close_pipes()



