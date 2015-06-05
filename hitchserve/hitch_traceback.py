from IPython.core import ultratb
from IPython.terminal.embed import InteractiveShellEmbed


class HitchTraceback(object):
    """Representation of a python traceback caused by a failed test case with added tools."""

    def __init__(self, tb_id, traceback):
        self.tb_id = tb_id
        self.traceback = traceback

    def filename(self):
        return self.traceback.tb_frame.f_code.co_filename

    def lineno(self):
        return self.traceback.tb_lineno

    def func(self):
        return self.traceback.tb_frame.f_code.co_name

    def localvars(self):
        return self.traceback.tb_frame.f_locals

    def globalvars(self):
        return self.traceback.tb_frame.f_globals

    def ipython(self):
        InteractiveShellEmbed()("Entering {} at line {}".format(self.filename(), self.lineno()), local_ns=self.localvars(), global_ns=self.globalvars())

    def loc(self):
        with open(self.filename(), 'r') as source_handle:
            contents = source_handle.read().split('\n')
        return contents[self.lineno() - 1].strip()

    def __repr__(self):
        return "\n [{}] File {}, line {} in {}:\n    {}".format(self.tb_id, self.filename(), self.lineno(), self.func(), self.loc())
