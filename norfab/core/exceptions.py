class UnsupportedPluginError(Exception):
    """Exception to raise when specified plugin not supported"""

    pass


class UnsupportedServiceError(Exception):
    """Exception to raise when specified service not supported"""

    pass


class NorfabJobFailedError(Exception):
    """Exception to raise when job failed"""

    pass


class ServicePluginAlreadyRegistered(Exception):
    """
    Raised when trying to register an already registered plugin
    """


class ServicePluginNotRegistered(Exception):
    """
    Raised when trying to access a plugin that is not registered
    """
