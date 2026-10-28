"""Login and session handling for the FusionSolar web portal.

Adapted from Home-Assistant-FusionSolar-App by Henrique Craveiro
(https://github.com/hcraveiro/Home-Assistant-FusionSolar-App),
Copyright (c) 2024 Henrique Craveiro, MIT License. See THIRD_PARTY_NOTICES.md.

Changes compared to the original: standalone class instead of a mixin, no
background session thread (the caller re-logs in on demand), no interactive
captcha handling (a captcha demand raises ``CaptchaRequired``), redacted logging,
at most one login attempt per ``_MIN_LOGIN_GAP`` seconds, HTTP 429 raises ``RateLimited``.
"""

from __future__ import annotations

import base64
import json
import logging
import re
import secrets
import threading
import time
from typing import Any
from urllib.parse import quote, urlparse

import requests

from . import endpoints as ep
from .errors import (
    BadCredentials,
    CaptchaRequired,
    PortalUnreachable,
    RateLimited,
    SessionInvalid,
    UnexpectedPayload,
)

_LOGGER = logging.getLogger(__name__)

_TIMEOUT = 20
_CSRF_MAX_AGE = 300
_MIN_LOGIN_GAP = 300  # seconds between login attempts (no login storms against the portal)
_EU5_SERVICE = "/unisess/v1/auth?service=%2Fnetecowebext%2Fhome%2Findex.html"
_AUTH_PAGE_MARKERS = (
    "login", "sign in", "verifycode", "captcha", "dpcloud/auth",
    "uniportal", "user name", "username", "password",
)


def normalize_host(host: str | None) -> str:
    """Turn user input like ``https://region01eu5.fusionsolar...`` into a login host."""
    if not isinstance(host, str):
        return ep.DEFAULT_HOST
    value = re.sub(r"^https?://", "", host.strip().lower())
    value = value.split("/", 1)[0].split(":", 1)[0]
    if value.endswith(ep.HOST_SUFFIX):
        value = value[: -len(ep.HOST_SUFFIX)]
    match = re.match(r"^(?:region|uni)\d+(?P<short>[a-z]+\d+)$", value)
    if match:
        value = match.group("short")
    return f"{value or 'eu5'}{ep.HOST_SUFFIX}"


def _make_nonce() -> str:
    return secrets.token_hex(16)


def _encrypt(pub_key_pem: str, password: str) -> str:
    """RSA-OAEP(SHA384) encrypt the password with the portal's public key."""
    # imported lazily so the parsing layer stays importable without cryptography
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding

    key = serialization.load_pem_public_key(pub_key_pem.encode())
    cipher = key.encrypt(
        password.encode(),
        padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA384()), algorithm=hashes.SHA384(), label=None),
    )
    return base64.b64encode(cipher).decode()


class PortalSession:
    """A logged-in HTTP session against the FusionSolar portal (blocking, thread-safe)."""

    def __init__(self, username: str, password: str, host: str | None = None) -> None:
        self.username = username
        self._password = password
        self.login_host = normalize_host(host)
        self.data_host: str | None = None
        self.logged_in = False
        self._csrf: str | None = None
        self._csrf_at = 0.0
        self._login_at: float | None = None
        self._lock = threading.RLock()
        self._http = self._new_http()

    # ------------------------------------------------------------------ basics
    @staticmethod
    def _new_http() -> requests.Session:
        http = requests.Session()
        http.cookies.set("locale", "en-us")
        return http

    def close(self) -> None:
        """Drop cookies and the HTTP connection pool."""
        try:
            self._http.close()
        except Exception:  # noqa: BLE001
            pass
        self._http = self._new_http()
        self.logged_in = False
        self._csrf = None

    @property
    def base_url(self) -> str:
        return f"https://{self.data_host or self.login_host}"

    @property
    def app_referer(self) -> str:
        return f"{self.base_url}{ep.PATH_APP_PAGE}"

    # ------------------------------------------------------------------ login
    def login(self) -> None:
        """Log in from scratch. Raises BadCredentials, CaptchaRequired, PortalUnreachable."""
        with self._lock:
            now = time.monotonic()
            if self._login_at is not None and now - self._login_at < _MIN_LOGIN_GAP:
                raise PortalUnreachable("login attempted shortly before; waiting before the next one")
            self._login_at = now
            self.close()
            try:
                if "la5" in self.login_host or "intl" in self.login_host:
                    self._login_la5()
                else:
                    self._login_eu5()
            except requests.RequestException as err:
                raise PortalUnreachable(f"login request failed: {err}") from err
            self.logged_in = True
            self.csrf_token()

    def ensure_login(self) -> None:
        with self._lock:
            if not self.logged_in:
                self.login()

    def _login_eu5(self) -> None:
        host = self.login_host
        service = quote(_EU5_SERVICE, safe="")
        page_with_service = f"https://{host}{ep.PATH_LOGIN_PAGE}?service={service}"
        try:
            self._http.get(page_with_service, timeout=_TIMEOUT)
        except requests.RequestException as err:
            _LOGGER.debug("Pre-loading login page failed: %s", err)

        resp = self._http.get(
            f"https://{host}{ep.PATH_PUBKEY}",
            headers={"Accept": "application/json", "Referer": page_with_service},
            timeout=_TIMEOUT,
        )
        try:
            key_info = resp.json()
            pub_key, stamp, version = key_info["pubKey"], key_info["timeStamp"], key_info["version"]
        except (ValueError, KeyError, TypeError) as err:
            raise PortalUnreachable("public key response not understood") from err

        nonce = _make_nonce()
        body = {
            "organizationName": "",
            "username": self.username,
            "password": _encrypt(pub_key, self._password) + version,
            "multiRegionName": "",
        }
        last_code = ""
        # browser-like flow with nested service parameter first, legacy flow second
        for with_service in (True, False):
            referer = page_with_service if with_service else f"https://{host}{ep.PATH_LOGIN_PAGE}"
            url = f"https://{host}{ep.PATH_VALIDATE_USER}?timeStamp={stamp}&nonce={nonce}"
            if with_service:
                url += f"&service={service}"
            resp = self._http.post(
                url,
                json=body,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "Origin": f"https://{host}",
                    "Referer": referer,
                    "X-Requested-With": "XMLHttpRequest",
                },
                timeout=_TIMEOUT,
            )
            if resp.status_code == 429:
                raise RateLimited("login: HTTP 429")
            if resp.status_code != 200:
                _LOGGER.debug("Login attempt answered HTTP %s", resp.status_code)
                continue
            try:
                answer = resp.json()
            except ValueError:
                continue
            redirect = None
            if answer.get("respMultiRegionName"):
                redirect = answer["respMultiRegionName"][1]
            elif answer.get("redirectURL"):
                redirect = answer["redirectURL"]
            if redirect:
                self._follow_redirect(f"https://{host}{redirect}")
                return
            last_code = str(answer.get("errorCode", ""))
            if last_code == "411" or answer.get("verifyCodeCreate"):
                raise CaptchaRequired(
                    "FusionSolar requires a captcha for this account; log in once in a "
                    "browser, wait a while and try again"
                )
            if not with_service and last_code == "406":
                raise BadCredentials("invalid username or password")
        raise SessionInvalid(f"login did not return a redirect (code {last_code or 'n/a'})")

    def _follow_redirect(self, url: str) -> None:
        resp = self._http.get(
            url,
            headers={"Referer": f"https://{self.login_host}{ep.PATH_LOGIN_CUSTOMIZE}"},
            allow_redirects=False,
            timeout=_TIMEOUT,
        )
        location = resp.headers.get("Location")
        self.data_host = urlparse(location).netloc if location else self.login_host
        if resp.status_code not in (200, 302):
            raise SessionInvalid(f"login redirect failed with HTTP {resp.status_code}")
        if not (resp.cookies.get("dp-session") or self._http.cookies.get("dp-session")
                or "dp-session=" in resp.headers.get("Set-Cookie", "")):
            raise SessionInvalid("no session cookie after login")

    def _login_la5(self) -> None:
        base = f"https://{self.login_host}"
        self._http.get(f"{base}/", timeout=_TIMEOUT)
        resp = self._http.post(
            f"{base}{ep.PATH_VALIDATE_USER_LA5}?service=%2Frest%2Fdp%2Fuidm%2Fauth%2Fv1%2Fon-sso-credential-ready",
            json={"username": self.username, "password": self._password, "organizationName": ""},
            headers={
                "Content-Type": "application/json;charset=UTF-8",
                "Accept": "application/json, text/plain, */*",
                "Origin": base,
                "Referer": base,
                "X-Requested-With": "XMLHttpRequest",
            },
            timeout=_TIMEOUT,
        )
        if resp.status_code == 429:
            raise RateLimited("login: HTTP 429")
        if resp.status_code != 200:
            raise SessionInvalid(f"login failed with HTTP {resp.status_code}")
        redirect = resp.headers.get("redirect_url")
        if not redirect:
            raise BadCredentials("login rejected (no redirect)")
        self._http.get(f"{base}{redirect}", timeout=_TIMEOUT, allow_redirects=False)
        self._http.get(f"{base}{ep.PATH_FINAL_AUTH_LA5}", timeout=_TIMEOUT, allow_redirects=False)
        if not self._http.cookies.get("dp-session"):
            raise SessionInvalid("no session cookie after login")
        self.data_host = self.login_host

    # ---------------------------------------------------------------- requests
    @staticmethod
    def _is_login_page(resp: requests.Response) -> bool:
        location = (resp.headers.get("Location") or "").lower()
        ctype = (resp.headers.get("Content-Type") or "").lower()
        head = (resp.text or "")[:500].lower()
        return (
            resp.status_code in (401, 403)
            or "login" in location
            or ("text/html" in ctype and any(m in head for m in _AUTH_PAGE_MARKERS))
        )

    def request(self, method: str, path: str, *, label: str, **kwargs: Any) -> Any:
        """Send a request to the data host and return decoded JSON.

        Raises SessionInvalid when the portal answers with a login page.
        """
        url = f"{self.base_url}{path}"
        try:
            resp = self._http.request(method, url, timeout=_TIMEOUT, **kwargs)
        except requests.RequestException as err:
            raise PortalUnreachable(f"{label}: {err.__class__.__name__}") from err
        if resp.status_code == 429:
            raise RateLimited(f"{label}: HTTP 429")
        if self._is_login_page(resp):
            self.logged_in = False
            raise SessionInvalid(f"{label}: session expired")
        if resp.status_code != 200:
            raise PortalUnreachable(f"{label}: HTTP {resp.status_code}")
        try:
            return resp.json()
        except json.JSONDecodeError as err:
            if "<html" in resp.text[:300].lower() or "<!doctype" in resp.text[:300].lower():
                self.logged_in = False
                raise SessionInvalid(f"{label}: HTML instead of JSON") from err
            raise UnexpectedPayload(f"{label}: no JSON") from err

    def csrf_token(self) -> str:
        """Return the 'Roarand' anti-CSRF token, refreshing it every few minutes."""
        with self._lock:
            if self._csrf and time.monotonic() - self._csrf_at < _CSRF_MAX_AGE:
                return self._csrf
            answer = self.request(
                "GET", ep.PATH_KEEP_ALIVE, label="keep-alive",
                headers={"Accept": "application/json, text/plain, */*", "Referer": self.app_referer},
            )
            token = answer.get("payload") if isinstance(answer, dict) else None
            if not token:
                self.logged_in = False
                raise SessionInvalid("keep-alive returned no token")
            self._csrf, self._csrf_at = token, time.monotonic()
            return token

    # ---------------------------------------------------------------- stations
    def list_stations(self) -> list[dict[str, Any]]:
        """Return the plants of the account as a list of ``{"dn": ..., "name": ...}``."""
        answer = self.request(
            "POST", ep.PATH_STATION_LIST, label="station list",
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Origin": self.base_url,
                "Referer": self.app_referer,
                "Roarand": self.csrf_token(),
            },
            json={
                "curPage": 1, "pageSize": 10, "gridConnectedTime": "", "queryTime": 1666044000000,
                "timeZone": 2, "sortId": "createTime", "sortDir": "DESC", "locale": "en_US",
            },
        )
        data = answer.get("data") if isinstance(answer, dict) else None
        rows = data.get("list") if isinstance(data, dict) else None
        if not isinstance(rows, list):
            raise UnexpectedPayload("station list without data.list")
        return [
            {"dn": str(row["dn"]), "name": str(row.get("name") or row.get("stationName") or row["dn"])}
            for row in rows if isinstance(row, dict) and row.get("dn")
        ]
