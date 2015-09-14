from os import sep, path, makedirs, system, remove, listdir
import shutil
import sys


class HitchDir(object):
    def __init__(self, project_directory, hitch_dir=None):
        self.project_directory = project_directory

        # 3 directories above virtualenv python binary is the hitchdir
        if hitch_dir is None:
            self.hitch_dir = path.abspath(
                path.join(path.dirname(sys.executable), "..", "..")
            )
        else:
            self.hitch_dir = hitch_dir

    def clean(self):
        if not path.exists(self.hitch_dir):
            makedirs(self.hitch_dir)
            makedirs(self.hitch_dir)
        if path.exists(self.faketime()):
            remove(self.faketime())
        shutil.rmtree(self.stdlogdir(), ignore_errors=True)
        makedirs(self.stdlogdir())
        if path.exists(self.testlog()):
            remove(self.testlog())
        self.remove_run_dir()
        makedirs(self.rundir())

    def save_pgid(self, name, pgid):
        with open(self.rundir() + sep + name + '.pgid', "w") as pgid_file_handle:
            pgid_file_handle.write(str(pgid))

    def save_pid(self, pid):
        with open(self.rundir() + sep + 'driver_process.pid', "w") as pid_file_handle:
            pid_file_handle.write(str(pid))

    def remove_run_dir(self):
        if path.exists(self.rundir()):
            shutil.rmtree(self.rundir())

    def old_pid(self):
        if path.exists(path.join(self.rundir(), 'driver_process.pid')):
            with open(path.join(self.rundir(), 'driver_process.pid')) as pid_file_handle:
                return int(pid_file_handle.read())
        else:
            return None

    def old_pgids(self):
        pgids = []
        if path.exists(self.rundir()):
            for filename in listdir(self.rundir()):
                with open(path.join(self.rundir(), filename)) as pgid_file_handle:
                    pgids.append(int(pgid_file_handle.read()))
        return pgids

    def rundir(self):
        return self.hitch_dir + sep + "run"

    def testlog(self):
        return self.hitch_dir + sep + "test.log"

    def stdlogdir(self):
        return self.hitch_dir + sep + "stdlog"

    def faketime(self):
        return self.hitch_dir + sep + "faketime.txt"

    def pgid(self):
        return self.hitch_dir + sep + "hitch.pgid"

    def driverout(self):
        return self.stdlogdir() + sep + "driver.out"

    def drivererr(self):
        return self.stdlogdir() + sep + "driver.err"

    def setup_out(self, name):
        return self.stdlogdir() + sep + name.lower() + "_setup.out"

    def setup_err(self, name):
        return self.stdlogdir() + sep + name.lower() + "_setup.err"

    def poststart(self, name):
        return self.stdlogdir() + sep + name.lower() + "_poststart.out"

    def poststart_err(self, name):
        return self.stdlogdir() + sep + name.lower() + "_poststart.err"
