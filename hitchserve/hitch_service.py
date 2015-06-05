from hitch_dir import HitchDir
import service_logs
import multiprocessing
import subprocess
import faketime
import signal
import psutil
import time
import pyuv
import sys
import os
import re


class HitchServiceException(Exception):
    pass


# TODO: Allow stopping and starting and *waiting* of services from other thread using queue.

class Subcommand(object):
    def __init__(self, *args, **kwargs):
        self.command = list(args)
        self.directory = kwargs['directory'] if 'directory' in kwargs else None
        self.env_vars = kwargs['env_vars'] if 'env_vars' in kwargs else None

    @property
    def directory(self):
        return self._directory

    @directory.setter
    def directory(self, value):
        self._directory = value

    def run(self, shell=False, ignore_errors=False, stdin=False, check_output=False):
        os.chdir(self.directory)
        try:
            kwargs = {
                'stderr': sys.stderr,
                'stdin': sys.stdin if stdin else None,
                'env': self.env_vars,
                'shell': shell,
            }
            if check_output:
                return subprocess.check_output(self.command, **kwargs)
            else:
                kwargs['stdout'] = sys.stdout
                return subprocess.check_call(self.command, **kwargs)
        except subprocess.CalledProcessError:
            if ignore_errors:
                pass
            else:
                raise

class Service(object):
    stop_signal = signal.SIGINT

    def __init__(self, command=None, log_line_ready_checker=None, directory=None, no_libfaketime=False, env_vars=None, needs=None):
        self.no_libfaketime = no_libfaketime
        self.directory = directory
        self.command = command
        self.env_vars = {} if env_vars is None else env_vars
        self.needs = needs
        self.log_line_ready_checker = log_line_ready_checker
        self._pid = multiprocessing.Value('i', 0)

    def setup(self):
        pass

    def poststart(self):
        pass

    @property
    def pid(self):
        return self._pid.value

    @pid.setter
    def pid(self, value):
        self._pid.value = value

    @property
    def process(self):
        return psutil.Process(self.pid)

    @property
    def name(self):
        return self._name

    @name.setter
    def name(self, value):
        self._name = value
        self.logs = service_logs.ServiceLogs(value)

    @property
    def env_vars(self):
        if not self.no_libfaketime:
            faketime_filename = self.service_group.hitch_dir.faketime()

            env_vars = dict(
                os.environ.items() +
                self._env_vars.items() +
                faketime.get_environment_vars(faketime_filename).items()
            )
        else:
            env_vars = dict(
                os.environ.items() +
                self._env_vars.items()
            )

        return env_vars

    @env_vars.setter
    def env_vars(self, value):
        self._env_vars = value

    @property
    def directory(self):
        if self._directory is None:
            return self.service_group.hitch_dir.hitch_dir
        else:
            return self._directory

    @directory.setter
    def directory(self, value):
        self._directory = value

    @property
    def command(self):
        return self._command

    @command.setter
    def command(self, value):
        self._command = value

    def log(self, line):
        sys.stdout.write("{}\n".format(line))

    def warn(self, line):
        sys.stderr.write("{}\n".format(line))

    def subcommand(self, *args):
        return Subcommand(*args, directory=self.directory, env_vars=self.env_vars)

    def run(self, command, shell=False, ignore_errors=False, stdin=False, check_output=False, return_command=False):
        """Run a command for this service."""
        # TODO : Change directory to "directory" before running cmd.
        self.log(' '.join(command))
        try:
            kwargs = {
                'stderr': sys.stderr,
                'stdin': sys.stdin if stdin else None,
                'env': self.env_vars,
                'shell': shell,
            }
            if check_output:
                return subprocess.check_output(command, **kwargs)
            else:
                kwargs['stdout'] = sys.stdout
                return subprocess.check_call(command, **kwargs)
        except subprocess.CalledProcessError:
            if ignore_errors:
                pass
            else:
                raise
