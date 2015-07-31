from hitchserve.hitch_dir import HitchDir
from hitchserve.hitch_exception import BundleMisconfiguration
from hitchserve.hitch_exception import HitchServeException
from hitchserve.hitch_service import Service
from hitchserve.test_engine import TestEngine
from hitchserve.utils import log, warn
from datetime import datetime as python_datetime
from datetime import timedelta as python_timedelta
import faketime
import multiprocessing
import colorama
import subprocess
import humanize
import inspect
import termios
import psutil
import signal
import six
import sys
import os


# TODO : Allow stopping, starting, restarting and waiting until stop/start is finished.

class ServiceBundle(object):
    def __init__(self, project_directory, startup_timeout=15.0, shutdown_timeout=5.0, quiet=False):
        self._shutdown_initiated = False
        self.aborted = False
        self._services = {}
        self.quiet = quiet
        self.timedelta = python_timedelta(0)
        self.project_directory = os.path.abspath(project_directory)
        self.hitch_dir = HitchDir(self.project_directory)
        self.startup_timeout = startup_timeout
        self.shutdown_timeout = shutdown_timeout

    def __len__(self):
        return len(self._services.items())

    def __getitem__(self, key):
        if key not in self._services:
            raise IndexError
        return self._services[key]

    def __setitem__(self, key, value):
        if not isinstance(value, Service):
            raise BundleMisconfiguration("'{}' must be of type 'Service'".format(key))

        if "[" in key or "]" in key:
            raise BundleMisconfiguration("[ and ] characters not allowed in service name")

        if " " in key:
            raise BundleMisconfiguration("Spaces are not allowed in service names.")

        if key in ["Test", "Hitch", "Harness", ]:
            raise BundleMisconfiguration("{0} is not an allowed service name.".format(key))
        self._services[key] = value
        self._services[key].name = key
        self._services[key].service_group = self

        if self._services[key].command is None:
            raise BundleMisconfiguration("'{}' command must be a list, not {}".format(key, self._services[key].command))

        if subprocess.call(["which", self._services[key].command[0]], stdout=subprocess.PIPE) != 0:
            raise BundleMisconfiguration("'{}' command must call an existing file, not '{}'".format(key, self._services[key].command[0]))

        if not os.path.exists(self._services[key].directory):
            raise BundleMisconfiguration("'{}' directory '{}' must exist.".format(key, self._services[key].directory))

    def __repr__(self):
        return str(self._services)

    def items(self):
        return self._services.items()

    def values(self):
        return self._services.values()

    def keys(self):
        return self._services.keys()

    def __iter__(self):
        return self._services.__iter__()


    def log(self, message):
        """Print a normal priority message."""
        log(message)

    def warn(self, message):
        """Print a higher priority message."""
        warn(message)

    def check_pid(self, pid):
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        else:
            return True

    def _shutdown_old_processes(self):
        old_pid = self.hitch_dir.old_pid()
        if old_pid is not None:
            if self.check_pid(old_pid):
                log("Shutting down existing test...\n")
                old_process = psutil.Process(old_pid)

                for child in old_process.children(recursive=True):
                    try:
                        child.send_signal(signal.SIGTERM)
                        child.send_signal(signal.SIGQUIT)
                        log("Stopping {} (PID {}) : '{}'\n".format(child.name(), child.pid, ' '.join(child.cmdline())))
                    except psutil.NoSuchProcess:
                        pass

                try:
                    old_process.wait(self.shutdown_timeout)
                    return
                except psutil.TimeoutExpired:
                    pass

            old_pgids = self.hitch_dir.old_pgids()
            if len(old_pgids) > 0:
                log("Killing off left-over processes from previous test...\n")
                processes = [p for p in psutil.process_iter() if os.getpgid(p.pid) in old_pgids]

                for process in processes:
                    try:
                        process.send_signal(signal.SIGKILL)
                        warn("Killing {} (PID {}) : '{}'\n".format(process.name(), process.pid, ' '.join(process.cmdline())))
                    except psutil.NoSuchProcess:
                        pass


    def startup(self, interactive=True):
        #self.setup_signal_handlers()


        self._shutdown_old_processes()

        self._orig_stdin_termios = termios.tcgetattr(sys.stdin.fileno())
        self._orig_stdin_fileno = sys.stdin.fileno()

        for service in self.values():
            service.logs.set_logfilename(self.hitch_dir.testlog())


        self.hitch_dir.clean()

        self.hitch_dir.save_pgid("driver_process", os.getpgid(os.getpid()))
        self.hitch_dir.save_pid(os.getpid())

        self.messages_to_driver = multiprocessing.Queue()
        self.messages_to_bundle_engine = multiprocessing.Queue()

        service_process_args = (self.messages_to_driver, self.messages_to_bundle_engine)

        self.bundle_engine = TestEngine(self)
        self._service_process = multiprocessing.Process(target=self.bundle_engine.start, args=service_process_args)
        self._service_process.start()

        self.redirect_stdout()

        what_happened = self.messages_to_driver.get()

        if what_happened == "READY":
            if interactive:
                self.start_interactive_mode()
            return
        elif type(what_happened) == tuple and len(what_happened) == 3:
            if interactive:
                self.start_interactive_mode()
            six.reraise(*what_happened)
        elif isinstance(what_happened, Exception):
            if interactive:
                self.start_interactive_mode()
            raise what_happened
        else:
            if interactive:
                self.start_interactive_mode()
            raise HitchServeException("Unknown exception occurred")

    def redirect_stdout(self):
        """Redirect stdout to file so that it can be tailed and aggregated with the other logs."""
        self.hijacked_stdout = sys.stdout
        self.hijacked_stderr = sys.stderr
        # 0 must be set as the buffer, otherwise lines won't get logged in time.
        sys.stdout = open(self.hitch_dir.driverout(), "ab", 0)
        sys.stderr = open(self.hitch_dir.drivererr(), "ab", 0)

    def unredirect_stdout(self):
        """Redirect stdout back to stdout."""
        if hasattr(self, 'hijacked_stdout') and hasattr(self, 'hijacked_stderr'):
            sys.stdout = self.hijacked_stdout
            sys.stderr = self.hijacked_stderr

    def start_interactive_mode(self):
        self.messages_to_bundle_engine.put("IPYTHONON")
        log("{}{}{}".format(colorama.Fore.RESET, colorama.Back.RESET, colorama.Style.RESET_ALL))
        warn("{}{}{}".format(colorama.Fore.RESET, colorama.Back.RESET, colorama.Style.RESET_ALL))
        self.unredirect_stdout()

        # Ensure that termios attributes are left in a sensible state
        termios.tcsetattr(self._orig_stdin_fileno, termios.TCSANOW, self._orig_stdin_termios)

        import fcntl
        # Make stdin blocking - so that redis-cli (among others) can work.
        flags = fcntl.fcntl(sys.stdin.fileno(), fcntl.F_GETFL)
        if flags & os.O_NONBLOCK:
            fcntl.fcntl(sys.stdin.fileno(), fcntl.F_SETFL, flags & ~os.O_NONBLOCK)

    def stop_interactive_mode(self):
        # Make stdin non-blocking again
        import fcntl
        flags = fcntl.fcntl(sys.stdin.fileno(), fcntl.F_GETFL)
        if flags & ~os.O_NONBLOCK:
            fcntl.fcntl(sys.stdin.fileno(), fcntl.F_SETFL, flags | os.O_NONBLOCK)

        self.redirect_stdout()
        self.messages_to_bundle_engine.put("IPYTHONOFF")

    def time_travel(self, datetime=None, timedelta=None, seconds=0, minutes=0, hours=0, days=0):
        """Mock moving forward or backward in time by shifting the system clock fed to the services tested.

        Note that all of these arguments can be used together, individually or not at all. The time
        traveled to will be the sum of all specified time deltas from datetime. If no datetime is specified,
        the deltas will be added to the current time.

        Args:
            datetime (Optional[datetime]): Time travel to specific datetime.
            timedelta (Optional[timedelta]): Time travel to 'timedelta' from now.
            seconds (Optional[number]): Time travel 'seconds' seconds from now.
            minutes (Optional[number]): Time travel 'minutes' minutes from now.
            hours (Optional[number]): Time travel 'hours' hours from now.
            days (Optional[number]): Time travel 'days' days from now.
        """
        if datetime is not None:
            self.timedelta = datetime - python_datetime.now()
        if timedelta is not None:
            self.timedelta = self.timedelta + timedelta
        self.timedelta = self.timedelta + python_timedelta(seconds=seconds)
        self.timedelta = self.timedelta + python_timedelta(minutes=minutes)
        self.timedelta = self.timedelta + python_timedelta(hours=hours)
        self.timedelta = self.timedelta + python_timedelta(days=days)
        log("Time traveling to {}\n".format(humanize.naturaltime(self.now())))
        faketime.change_time(self.hitch_dir.faketime(), self.now())

    def now(self):
        """Get a current (mocked) datetime. This will be the current datetime unless you have time traveled."""
        return python_datetime.now() + self.timedelta

    def pstree(self):
        os.system("pstree -panl {}".format(os.getppid()))

    def shutdown(self):
        if not self._shutdown_initiated:
            self._shutdown_initiated = True
            if hasattr(self, '_service_process'):
                if self._service_process.is_alive():
                    self.messages_to_bundle_engine.put("SHUTDOWN")
                    try:
                        psutil.Process(self._service_process.pid).wait()
                    except psutil.NoSuchProcess:
                        pass

            self.unredirect_stdout()
            self.hitch_dir.remove_run_dir()
            log("{}{}{}".format(colorama.Fore.RESET, colorama.Back.RESET, colorama.Style.RESET_ALL))
            warn("{}{}{}".format(colorama.Fore.RESET, colorama.Back.RESET, colorama.Style.RESET_ALL))
            if self.aborted:
                warn("ABORT\n")
