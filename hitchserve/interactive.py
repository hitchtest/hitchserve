from IPython.terminal.embed import InteractiveShellEmbed
from IPython.terminal.ipapp import load_default_config
import IPython
import multiprocessing
import inspect
import sys
import os
import signal
import psutil
import fcntl


class Interactive(object):
    def __init__(self):
        pass

    #def ipython_process(self, frame, message, fdin, child_queue):
        #from IPython.terminal.embed import InteractiveShellEmbed
        #orig_pgid = os.getpgrp()
        #os.setpgrp()
        #child_queue.put(os.getpgrp())
        #sys.stdin = os.fdopen(fdin)

        #InteractiveShellEmbed()(message, local_ns=frame.f_locals, global_ns=frame.f_globals)

        #os.tcsetpgrp(fdin, orig_pgid)

    #def embed(self, frame, message=""):
        #fdin = sys.stdin.fileno()
        #child_queue = multiprocessing.Queue()
        #proc = multiprocessing.Process(target=self.ipython_process, args=(frame, message, fdin, child_queue))
        #proc.start()
        #pgid = child_queue.get()
        #pgid = os.getpgid(proc.pid)
        #os.tcsetpgrp(fdin, pgid)
        #proc.join()

    def embed(self, frame, message=""):

        config = IPython.Config({
            'InteractiveShell': {'confirm_exit': False, },
            'IPCompleter': {'greedy': True, }
        })
        InteractiveShellEmbed.instance(config=config)(message, local_ns=frame.f_locals, global_ns=frame.f_globals)

    #def kernel(self):
        #"""Launch IPython console and connect to an existing kernel. You must use IPython.embed_kernel() in your code to use this."""
        #os.system("{0} -m IPython console --existing".format(sys.executable))

