"""One place that masks secrets before anything is logged or shown in an error.

Everything that ends up in a log line or an exception message (``UpdateFailed``,
``ConfigEntryNotReady``, ``HomeAssistantError``) goes through :func:`redact`.
It masks

* values the session knows to be secret (username, password, the anti-CSRF
  ``Roarand`` token, station and device DNs) – registered with :func:`remember`,
* ``key=value`` / ``"key": "value"`` pairs whose key looks like a password,
  user name, cookie, token, session id, CSRF/roarand value or DN,
* FusionSolar DNs such as ``NE=12345678``.
"""

from __future__ import annotations

import re
import threading

MASK = "***"

_known: set[str] = set()
_known_lock = threading.Lock()

_KEYS = (
    r"password|passwd|pwd|username|user_?name|login_?name|account|"
    r"cookie|set-cookie|dp-session|jsessionid|session(?:_?id)?|ticket|"
    r"token|access_?token|refresh_?token|csrf\w*|roarand|"
    r"dn|station_?dn|stationdn|device_?dn|devicedn|parent_?dn|parentdn"
)
_PAIR = re.compile(
    rf"(?i)(?P<key>[\"']?\b(?:{_KEYS})\b[\"']?\s*[:=]\s*[\"']?)(?P<val>[^\"'\s,;&}}\]]+)"
)
_DN = re.compile(r"(?i)\bNE=\d+")


def remember(*values: object) -> None:
    """Register values that must never appear in logs (short or empty values are ignored)."""
    with _known_lock:
        for value in values:
            if isinstance(value, str) and len(value.strip()) >= 4:
                _known.add(value.strip())


def redact(value: object) -> str:
    """Return ``str(value)`` with all known and recognisable secrets masked."""
    text = value if isinstance(value, str) else str(value)
    with _known_lock:
        known = sorted(_known, key=len, reverse=True)
    for secret in known:
        if secret in text:
            text = text.replace(secret, MASK)
    text = _PAIR.sub(lambda m: m.group("key") + MASK, text)
    return _DN.sub("NE=" + MASK, text)


def describe(err: BaseException) -> str:
    """Error type plus redacted message, for log lines and user-facing errors."""
    message = redact(err)
    return f"{type(err).__name__}: {message}" if message else type(err).__name__
