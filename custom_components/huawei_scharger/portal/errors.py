"""Exceptions raised by the FusionSolar portal layer."""


class PortalError(Exception):
    """Base class for all portal errors."""


class PortalUnreachable(PortalError):
    """Network problem, timeout or unexpected HTTP status."""


class RateLimited(PortalUnreachable):
    """The portal answered HTTP 429 (too many requests); polling should slow down."""


class SessionInvalid(PortalError):
    """The portal rejected the session (expired cookie, login page returned)."""


class BadCredentials(SessionInvalid):
    """Username or password was rejected."""


class CaptchaRequired(SessionInvalid):
    """The portal demands a captcha before it accepts another login."""


class UnexpectedPayload(PortalError):
    """The portal answered with JSON of an unknown shape."""


class ChargerNotFound(PortalError):
    """The selected plant contains no SCharger wallbox."""
