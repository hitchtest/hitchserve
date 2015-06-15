HitchServe
==========

HitchServe is a UNIX service orchestration library for the Hitch testing
framework.

Use
===

Install like so::

    $ hitch install hitchserve

.. code-block:: python

        import hitchtest

        # Gets the directory above the file that this code is written in
        PROJECT_DIRECTORY = path.join(path.dirname(__file__), '..')

        # Specify an environment using HitchEnvironment_.
        import hitchenvironment
        environment = hitchenvironment.Environment("linux2", 64, False)

        # Create a service bundle
        self.services = hitchserve.ServiceBundle(
            project_directory=PROJECT_DIRECTORY,
            environment=environment,
            startup_timeout=15.0,                       # How long to wait for all of the services to startup
            shutdown_timeout=5.0,                       # How long to wait for all of the services to shutdown before killing
        )

        # [ DO SERVICE DEFINITIONS HERE ]
        # See below for an example.

        # Start services (use interactive=True if you run this command from IPython).
        self.services.startup(interactive=True)

        # Use interactive=False if you run this command in a test (this aggregate and output service logs):
        self.services.startup(interactive=False)

        # You can log a message to the logs
        self.services.log("Message")

        # You can stop the logging and switch to a more interactive mode for debugging
        self.services.stop_interactive_mode()

        # Launch into ipython...
        hitchtest.ipython_embed()

        # ...and start it back up again.
        self.services.start_interactive_mode()

        # You can log a warning message to the logs
        self.serviecs.warn("Warning!")

        # You can also make the services think that the system time has changed
        self.services.time_travel(minutes=30)
        self.services.time_travel(hours=30)
        self.services.time_travel(days=30)

        # Stop services when you are done
        self.services.shutdown()


Available prewritten services
=============================

* HitchCron_
* HitchSelenium_
* HitchRedis_
* HitchDjango_
* HitchPostgres_
* HitchCelery_


Features
========

* Starts services in parallel and abstracts away the difficulties of writing multiprocess code.
* Creates an easy way to 'listen' to the logs and trigger events.
* Lets you interact with services and inspect their processes.
* Handles all of the thorny UNIX process handling.
* Aggregates the output of services and logs it all together for easy reading.


Caveats and Known issues
========================

* Faketime does not currently work with Firefox, node.js and Java services.

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


.. _HitchEnvironment: https://github.com/hitchtest/hitchenvironment
.. _HitchSMTP: https://github.com/hitchtest/hitchsmtp
.. _HitchCron: https://github.com/hitchtest/hitchcron
.. _HitchSelenium: https://github.com/hitchtest/hitchselenium
.. _HitchRedis: https://github.com/hitchtest/hitchredis
.. _HitchDjango: https://github.com/hitchtest/hitchdjango
.. _HitchCelery: https://github.com/hitchtest/hitchcelery
