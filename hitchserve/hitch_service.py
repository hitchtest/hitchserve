from hitchserve.hitch_exception import ServiceMisconfiguration
from hitchserve.hitch_dir import HitchDir
from hitchserve import service_logs
from hitchserve.utils import log, warn
import multiprocessing
import commandlib
import subprocess
import faketime
import inspect
import signal
import psutil
import time
import pyuv
import sys
import os
import re


class HitchServiceException(Exception):
    """Exception associated with a HitchServe service."""
    pass


# TODO: Allow stopping and starting and *waiting* of services from other thread using queue.

class Subcommand(object):
    """Command associated with a service.

       Examples include Postgres's psql or pg_dump, 'redis-cli' or Django's manage."""

    def __init__(self, *args, **kwargs):
        """Define a subcommand.

        Args:
            *args (str): Sequence of program arguments needed to run the command.
            directory (Optional[str]): Directory the command is run in.
            env_vars (Optional[dict]): Environment variable to feed to the subcommand.
        """
        self.command = list(args)
        self.directory = kwargs['directory'] if 'directory' in kwargs else None
        self.env_vars = kwargs['env_vars'] if 'env_vars' in kwargs else None

    @property
    def directory(self):
        """str: Directory subcommand runs in."""
        return self._directory

    @directory.setter
    def directory(self, value):
        self._directory = value

    def run(self, shell=False, ignore_errors=False, stdin=False, check_output=False):
        """Run subcommand.

        Args:
            shell (Optional[bool]): Run command using shell (default False)
            ignore_errors (Optional[bool]): If the command has a non-zero return code, don't raise an exception (default False)
            stdin (Optional[bool]): Plug input from stdin when running command (default False)
            check_output (Optional[bool]): Return command output as string (default False)

        Returns:
            String if check_output is True, else None.

        Raises:
            subprocess.CalledProcessError when the command has an error, unless ignore_errors is True.
        """
        previous_directory = os.getcwd()
        os.chdir(self.directory)
        try:
            kwargs = {
                'stderr': sys.stderr,
                'stdin': sys.stdin if stdin else None,
                'env': self.env_vars,
                'shell': shell,
            }
            if check_output:
                return subprocess.check_output(self.command, **kwargs).decode("utf8")
            else:
                kwargs['stdout'] = sys.stdout
                return subprocess.check_call(self.command, **kwargs)
        except subprocess.CalledProcessError:
            if ignore_errors:
                pass
            else:
                raise

        # Return to previous directory
        os.chdir(previous_directory)

class Service(object):
    """A process to run, monitored and interacted with for the duration of a test."""
    def __init__(self, command=None, log_line_ready_checker=None, directory=None, no_libfaketime=False, env_vars=None, stop_signal=signal.SIGINT, needs=None):
        """Define and configure a service.

        Each service has a command, directory and function which checks
        each line of the logs to ascertain readiness.

        Args:
            command (List(str) or commandlib.Command): Sequence of program arguments needed to run the service.
            log_line_ready_checker (Function[str]): Function which returns True when passed a line which indicates service readiness.
            directory (Optional[str]): Directory the service command is run in. Defaults to project directory specified in service bundle.
            no_libfaketime (Optional[bool]): If True, don't run service with libfaketime. Useful if libfaketime breaks the service.
            env_vars (Optional[dict]): Dictionary of environment variables to feed to the service when running it.
            needs (Optional[List[Service]]): List of services which must be started before this service will run.
            stop_signal (Optional[int]): First signal to send to service when shutting it down (default: signal.SIGINT).

        Raises:
            ServiceMisconfiguration when the wrong parameters are passed.
        """
        
        if type(command) is str:
            raise ServiceMisconfiguration((
                "Command cannot be string. It must either be "
                "a list of arguments (strings) or a commandlib.Command object."
            ))
        
        if isinstance(command, commandlib.Command):
            self.command = command.arguments
            
            if env_vars is None:
                self.env_vars = command.env
            else:
                self.env_vars = command.env
                self.env_vars.update(env_vars)
            
            self.directory = str(command.directory) if command.directory is not None else str(directory)
        else:
            self.command = [str(arg) for arg in command] if command is not None else command
            self.env_vars = {} if env_vars is None else env_vars
            self.directory = directory

        self.no_libfaketime = no_libfaketime
        self.needs = needs
        self.log_line_ready_checker = log_line_ready_checker
        self.stop_signal = stop_signal
        self._pid = multiprocessing.Value('i', 0)

        if not inspect.isfunction(log_line_ready_checker):
            raise ServiceMisconfiguration(
                "log_line_ready_checker must be a function that takes one argument: a string"
            )

        if len(inspect.getargspec(log_line_ready_checker).args) != 1:
            raise ServiceMisconfiguration(
                "log_line_ready_checker must take only one argument."
            )

        if needs is not None:
            if type(needs) != list:
                raise ServiceMisconfiguration(
                    "needs must be of type List[Service] or None. You did not pass a list!"
                )

            for need in needs:
                if not isinstance(need, Service):
                    raise ServiceMisconfiguration(
                        "needs must be of type List[Service] or None."
                    )

    def setup(self):
        """Method that is run before starting the service."""
        pass

    def poststart(self):
        """Method that is run immediately after detecting that the service has started."""
        pass

    @property
    def pid(self):
        """int: UNIX process id of the service process."""
        return self._pid.value

    @pid.setter
    def pid(self, value):
        self._pid.value = value

    @property
    def process(self):
        """psutil.Process: psutil Process object of the service."""
        return psutil.Process(self.pid)

    @property
    def name(self):
        """str: Service name."""
        return self._name

    @name.setter
    def name(self, value):
        self._name = value
        self.logs = service_logs.ServiceLogs(value)

    @property
    def env_vars(self):
        """dict: All environment variables fed to the service."""
        if not self.no_libfaketime:
            faketime_filename = self.service_group.hitch_dir.faketime()

            env_vars = dict(os.environ)
            env_vars.update(self._env_vars)
            env_vars.update(faketime.get_environment_vars(faketime_filename))
        else:
            env_vars = dict(os.environ)
            env_vars.update(self._env_vars)
        return env_vars

    @env_vars.setter
    def env_vars(self, value):
        self._env_vars = value

    @property
    def directory(self):
        """str: Directory that the service is run in."""
        if self._directory is None:
            return self.service_group.hitch_dir.hitch_dir
        else:
            return self._directory

    @directory.setter
    def directory(self, value):
        self._directory = value

    @property
    def command(self):
        """List[str]: Command used to run the service."""
        return self._command

    @command.setter
    def command(self, value):
        self._command = value

    def log(self, line):
        log("{}\n".format(line))

    def warn(self, line):
        warn("{}\n".format(line))

    def subcommand(self, *args):
        """Get subcommand acting on a service. Subcommand will run in service directory
           and with the environment variables used to run the service itself.

        Args:
            *args: Arguments to run command (e.g. "redis-cli", "-n", "1")

        Returns:
            Subcommand object.
        """
        return Subcommand(*args, directory=self.directory, env_vars=self.env_vars)
