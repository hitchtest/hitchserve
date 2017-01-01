from colorama import Fore, Back, Style
from tblib import pickling_support
import multiprocessing
import subprocess
import traceback
import functools
import inspect
import signal
import psutil
import time
import pyuv
import sys
import os


class ServiceHandle(object):
    """This is the handle that starts, stops the services and hooks it up to the service and bundle engines."""
    def __init__(self, bundle_engine, service):
        self.bundle_engine = bundle_engine
        self.service = service
        self.started = False
        self.setup_finished = False
        self.process_started = False
        self.poststart_started = False
        self.poststart_finished = False
        self.ready = False
        self.loaded = False
        self.process = None
        self.stdout_pipe = None
        self.stderr_pipe = None

        if self.service.log_line_ready_checker:
            self.log_line_readiness_checker = self.service.log_line_ready_checker
        else:
            self.log_line_readiness_checker = lambda line: False

    def start_setup(self):
        def run_setup():
            signal.signal(signal.SIGINT, signal.SIG_IGN)
            signal.signal(signal.SIGTERM, signal.SIG_IGN)
            try:
                sys.stdout = open(self.bundle_engine.service_bundle.hitch_dir.setup_out(self.service.name), "ab", 0)
                sys.stderr = open(self.bundle_engine.service_bundle.hitch_dir.setup_err(self.service.name), "ab", 0)
                self.service.setup()
            except Exception as e:
                pickling_support.install()
                self.bundle_engine.messages_to_driver.put(sys.exc_info())

        self.started = True
        self.setup_runner = multiprocessing.Process(target=run_setup)
        self.setup_runner.start()

    def start_process(self):
        self.bundle_engine.logline("Starting {}".format(self.service.name))
        self.bundle_engine.logline("Directory: {}".format(self.service.directory))
        self.bundle_engine.logline("Command: {}".format(' '.join(self.service.command)))
        os.chdir(self.service.directory)

        try:
            self.process = subprocess.Popen(
                self.service.command,
                bufsize=0,                  # Ensures that all stdout/err is pushed to us immediately.
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.PIPE,
                env=self.service.env_vars,
                preexec_fn=os.setpgrp       # Ctrl-C signal is not passed on to the process.
            )
            self.service.pid = self.process.pid
            self.process_started = True
        except Exception as e:
            pickling_support.install()
            self.bundle_engine.messages_to_driver.put(sys.exc_info())
            return

        self.bundle_engine.service_bundle.hitch_dir.save_pgid(self.service.name.lower(), os.getpgid(self.process.pid))

        self.stdout_pipe = pyuv.Pipe(self.bundle_engine.loop)
        self.stdout_pipe.open(self.process.stdout.fileno())

        self.stderr_pipe = pyuv.Pipe(self.bundle_engine.loop)
        self.stderr_pipe.open(self.process.stderr.fileno())


    def poststart_run(self):
        def run_poststart():
            signal.signal(signal.SIGINT, signal.SIG_IGN)
            signal.signal(signal.SIGTERM, signal.SIG_IGN)
            try:
                sys.stdout = open(self.bundle_engine.service_bundle.hitch_dir.poststart(self.service.name), "ab", 0)
                sys.stderr = open(self.bundle_engine.service_bundle.hitch_dir.poststart_err(self.service.name), "ab", 0)
                self.service.poststart()
            except Exception as e:
                pickling_support.install()
                self.bundle_engine.messages_to_driver.put(sys.exc_info())
                return

        self.poststart_runner = multiprocessing.Process(target=run_poststart)
        self.poststart_runner.start()

    def stop(self):
        """Ask politely, first, with SIGINT and SIGQUIT."""
        if hasattr(self, 'process'):
            if self.process is not None:
                try:
                    is_running = self.process.poll() is None
                except AttributeError:
                    is_running = False

                if is_running:
                    self.bundle_engine.logline("Stopping {0}".format(self.service.name))
                    self.term_signal_sent = True

                    # Politely ask all child processes to die first
                    try:
                        for childproc in psutil.Process(self.process.pid).children(recursive=True):
                            childproc.send_signal(signal.SIGINT)
                    except psutil.NoSuchProcess:
                        pass
                    except AttributeError:
                        pass

                    try:
                        self.process.send_signal(self.service.stop_signal)
                    except OSError as e:
                        if e.errno == 3:        # No such process
                            pass
                else:
                    self.bundle_engine.warnline("{0} stopped prematurely.".format(self.service.name))
            else:
                self.bundle_engine.warnline("{0} stopped prematurely.".format(self.service.name))
        else:
            self.bundle_engine.warnline("{0} was never successfully started.".format(self.service.name))

    def is_dead(self):
        if not hasattr(self, 'process'):
            return True
        else:
            if self.process is None:
                return True
            else:
                return self.process.poll() is not None or psutil.Process(self.process.pid).status() == 'zombie'

    def kill(self):
        """Murder the children of this service in front of it, and then murder the service itself."""
        if not self.is_dead():
            self.bundle_engine.warnline("{0} did not shut down cleanly, killing.".format(self.service.name))
            try:
                if hasattr(self.process, 'pid'):
                    for child in psutil.Process(self.process.pid).children(recursive=True):
                        os.kill(child.pid, signal.SIGKILL)
                    self.process.kill()
            except psutil.NoSuchProcess:
                pass

    def no_prerequisites(self):
        return self.service.needs is None or self.service.needs == []
