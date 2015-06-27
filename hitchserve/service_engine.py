from hitchserve.service_handle import ServiceHandle
from hitchserve.hitch_exception import ServiceSuddenStopException
from colorama import Fore
import time


class ServiceEngine(object):
    def __init__(self, bundle_engine, services):
        self.bundle_engine = bundle_engine
        self.service_handles = [ServiceHandle(bundle_engine, x) for x in services]

    def start_services_without_prerequisites(self):
        for service_handle in self.service_handles:
            if service_handle.no_prerequisites():
                service_handle.start_setup()

    def _setup_finished(self):
        return [x for x in self.service_handles if x.setup_finished]

    def pipes(self):
        stdout_pipes = [x.stdout_pipe for x in self._setup_finished()]
        stderr_pipes = [x.stderr_pipe for x in self._setup_finished()]
        return stdout_pipes + stderr_pipes


    def _not_started(self):
        return [x for x in self.service_handles if not x.started]

    def _ready_services(self):
        return [x.service for x in self.service_handles if x.ready]

    def not_ready_services(self):
        return [x.service for x in self.service_handles if not x.ready]


    def all_services_ready(self):
        for service_handle in self.service_handles:
            if not service_handle.ready:
                return False
        return True

    def longest_service_name(self):
        """Length of the longest service name."""
        return max([len(service_handle.service.name) for service_handle in self.service_handles] + [0])

    def tail_setup_and_poststart(self):
        for service_handle in self.service_handles:
            name = service_handle.service.name
            self.bundle_engine.initiate_tail(name.lower() + "_setup.out", "Setup {}".format(name), None)
            self.bundle_engine.initiate_tail(name.lower() + "_setup.err", "Err Setup {}".format(name), Fore.YELLOW)

            self.bundle_engine.initiate_tail(name.lower() + "_poststart.out", "Post {}".format(name), None)
            self.bundle_engine.initiate_tail(name.lower() + "_poststart.err", "Err Post {}".format(name), Fore.YELLOW)

    def _get_service_from_pipe(self, pipe):
        for service_handle in self.service_handles:
            if pipe == service_handle.stdout_pipe:
                return (service_handle, False)
            if pipe == service_handle.stderr_pipe:
                return (service_handle, True)

    def handle_input(self, pipe_handle, data):
        service_handle, is_error = self._get_service_from_pipe(pipe_handle)
        lines = [line for line in data.decode("utf8", "ignore").split('\n') if line != ""]

        for line in lines:
            decoded_line = line

            if is_error:
                self.bundle_engine.writeline("Err {0}".format(service_handle.service.name), decoded_line, color=Fore.YELLOW)
            else:
                self.bundle_engine.writeline("    {0}".format(service_handle.service.name), decoded_line)

            if not service_handle.loaded:
                if service_handle.log_line_readiness_checker(line):
                    service_handle.loaded = True
                    self.bundle_engine.logline("{0} Loaded.".format(service_handle.service.name))
                    service_handle.poststart_run()
                    service_handle.poststart_started = True

    def poll(self):
        for service_handle in self.service_handles:
            # Start the process if its setup thread is done
            if not service_handle.setup_finished and hasattr(service_handle, 'setup_runner') and not service_handle.setup_runner.is_alive():
                service_handle.setup_finished = True
                service_handle.start_process()
                if service_handle.stdout_pipe is not None:
                    service_handle.stdout_pipe.start_read(self.bundle_engine.on_pipe_read)
                if service_handle.stderr_pipe is not None:
                    service_handle.stderr_pipe.start_read(self.bundle_engine.on_pipe_read)

            # If a poststart thread is done...
            if service_handle.poststart_started and not service_handle.ready and not service_handle.poststart_runner.is_alive():
                service_handle.ready = True

                # Start any services which rely upon this one as a prerequisite
                for notstartedservice in self._not_started():
                    if set(notstartedservice.service.needs).issubset(set(self._ready_services())):
                        notstartedservice.start_setup()

            # Throw exception if a service suddenly stops.
            if service_handle.process_started and service_handle.is_dead():
                self.bundle_engine.messages_to_driver.put(
                    ServiceSuddenStopException(
                        "Service '{}' stopped suddenly.".format(
                            service_handle.service.name
                        )
                    )
                )

    def stop(self):
        for service_handle in self.service_handles:
            service_handle.stop()

        still_service_engines = list(self.service_handles)

        for i in range(0, int(self.bundle_engine.service_bundle.shutdown_timeout * 100)):
            for service_handle in still_service_engines:
                if service_handle.is_dead():
                    still_service_engines.remove(service_handle)
                    self.bundle_engine.logline("{0} Stopped".format(service_handle.service.name))

            if len(still_service_engines) == 0:
                break

            time.sleep(0.01)

        # If after timeout seconds there are services remaining, commit service genocide.
        for service_handle in still_service_engines:
            self.bundle_engine.warnline("Killing {0}".format(service_handle.service.name))
            if not service_handle.is_dead():
                service_handle.kill()
