"""FusionSolar web portal access for the SCharger wallbox (no Home Assistant imports)."""

from .errors import (
    BadCredentials,
    CaptchaRequired,
    ChargerNotFound,
    PortalError,
    PortalUnreachable,
    SessionInvalid,
    UnexpectedPayload,
)
from .login import PortalSession, normalize_host
from .readings import ChargerReading, PlantFigures, Setting, compose_reading
from .wallbox import SChargerClient

__all__ = [
    "BadCredentials",
    "CaptchaRequired",
    "ChargerNotFound",
    "ChargerReading",
    "PlantFigures",
    "Setting",
    "PortalError",
    "PortalSession",
    "PortalUnreachable",
    "SChargerClient",
    "SessionInvalid",
    "UnexpectedPayload",
    "compose_reading",
    "normalize_host",
]
