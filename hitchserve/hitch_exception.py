class HitchException(Exception):
    pass

class HitchServeException(Exception):
    pass

class ServiceStartupTimeoutException(HitchServeException):
    pass

class ServiceSuddenStopException(HitchServeException):
    pass

class ServiceMisconfiguration(HitchServeException):
    pass

class BundleMisconfiguration(HitchServeException):
    pass

class WaitingForLogMessageTimeout(HitchServeException):
    pass
