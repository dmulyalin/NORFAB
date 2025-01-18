class UnsupportedPluginError(Exception):
    """Exception to raise when specified plugin not supported"""

    pass


class UnsupportedServiceError(Exception):
    """Exception to raise when specified service not supported"""

    pass


class NorfabJobFailedError(Exception):
    """Exception to raise when job failed"""

    pass
