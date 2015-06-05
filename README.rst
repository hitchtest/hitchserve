HitchServe
==========

HitchServe is a UNIX service orchestration library for the Hitch testing
framework.


Caveats and Known issues
========================

* Libfaketime, which fakes the time has the following issues:
** Does not work correctly with node.js
** Does not work correctly with Java
** Does not work on Windows

* HitchServe has not been tested on Windows, Mac OS, BSD or Linux distributions
other than Ubuntu 14.04.2 LTS (kernel version : 3.13.0-49.81). Please
report any issues you have on your specific OS.

* The stacktrace printed after an exception in a test (before showing ipython)
does not contain the full error.

* The code is missing a lot of docstrings.

* Won't run with nosetests/py.test yet.

* Only works on python 2.


Thanks
======

Thanks to Wolfgang Hommel for the libfaketime library, which is used by
HitchServe.
