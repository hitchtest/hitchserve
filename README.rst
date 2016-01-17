HitchServe
==========

HitchServe is a UNIX service orchestration plugin for the Hitch testing
framework.

Features
--------

* Start a group of services in parallel by using a simple, declarative API.
* Aggregates logs from all the services it runs and prints them together, labeled.
* Provides API to print logs, tail logs as well as to tail service logs and 'listen' for specific lines.
* Provides an API to auto-convert JSON log lines into JSON and to tail and listen for specific properties.
* Asks politely first with a configurable signal (default: SIGTERM) to shut down services.
* If the shutdown timeout is exceeded, sends SIGKILL to any misbehaving processes and all of their children and grandchildren.
* Runs services with libfaketime and provides an API to change the time sent to their APIs.
* Provides an API call to listen for and connect to any process's IPython kernel.

Install
-------

Install into a hitch environment like so::

    $ hitch install hitchserve

Docs
----

* `Full hitch documentation <https://hitchtest.readthedocs.org/en/latest/>`_
* `hitchserve-specific API docs <https://hitchtest.readthedocs.org/en/latest/api/generic_service_api.html>`_
