"""Blocking client for one SCharger wallbox in a FusionSolar plant."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
import threading
import time
from typing import Any, Callable, TypeVar

from . import endpoints as ep
from .errors import BadCredentials, CaptchaRequired, ChargerNotFound, PortalError, SessionInvalid
from .login import PortalSession
from .readings import (
    ChargerReading,
    PendingWrite,
    PlantFigures,
    Setting,
    TreeNode,
    apply_pending,
    compose_reading,
    device_signal_value,
    live_signals,
    nodes_of_class,
    parse_plant_figures,
    parse_settings,
    write_accepted,
)

_LOGGER = logging.getLogger(__name__)

T = TypeVar("T")

SETTINGS_TTL = 300            # seconds the settings are cached when nothing is pending
CONFIRM_TIMEOUT = 180         # seconds a written value is shown until the portal confirms it
CONNECTOR_RETRY = 600         # seconds between connector lookups if none was found
PLANT_TTL = 1800              # seconds the plant figures are cached

# settings the integration may change
WRITABLE_SETTINGS = frozenset({
    ep.SETTING_DYNAMIC_POWER,
    ep.SETTING_MODE,
    ep.SETTING_MAX_CURRENT,
    ep.SETTING_PHASE_SWITCHING,
    ep.SETTING_LOCK_MODE,
    ep.SETTING_GRID_SHARE_PV,
    ep.SETTING_SURPLUS_START,
    ep.SETTING_DYNAMIC_ENABLED,
})


class SChargerClient:
    """Finds the first wallbox of a plant and reads/controls it via the web portal.

    All methods block and must run in an executor thread.
    """

    def __init__(self, session: PortalSession, station_dn: str, *, plant_figures: bool = True) -> None:
        self.session = session
        self.station_dn = station_dn
        self.wallbox: TreeNode | None = None
        self.connector: TreeNode | None = None
        self._connector_next_try = 0.0
        self._settings: dict[int, Setting] = {}
        self._settings_owner: dict[int, str] = {}     # signal id -> dn of the owning device
        self._settings_at = 0.0
        self._pending: dict[int, PendingWrite] = {}
        self._plant_enabled = plant_figures
        self._plant: PlantFigures | None = None
        self._plant_at = 0.0
        self._lock = threading.Lock()

    # ---------------------------------------------------------------- helpers
    def _with_relogin(self, action: Callable[[], T]) -> T:
        """Run ``action``; on an expired session log in again and retry once."""
        self.session.ensure_login()
        try:
            return action()
        except (BadCredentials, CaptchaRequired):
            raise
        except SessionInvalid:
            _LOGGER.debug("Session expired, logging in again")
            self.session.login()
            return action()

    def _get(self, path: str, params: dict[str, Any], label: str) -> Any:
        return self.session.request(
            "GET", path, label=label, params=params, headers={"Referer": self.session.app_referer}
        )

    def _post_json(self, path: str, body: Any, label: str) -> Any:
        return self.session.request(
            "POST", path, label=label, data=json.dumps(body),
            headers={
                "Referer": self.session.app_referer,
                "Content-Type": "application/json",
                "Roarand": self.session.csrf_token(),
            },
        )

    def _children(self, parent_dn: str, moc_id: int) -> list[TreeNode]:
        tree = self._post_json(
            ep.PATH_DEVICE_TREE,
            {
                "parentDn": parent_dn,
                "treeDepth": "device",
                "pageParam": {"pageId": 1, "pageSize": 100, "needPage": True},
                "filterCond": {"nameType": "device", "mocIdInclude": [moc_id]},
                "displayCond": {"self": False, "status": True},
            },
            "device tree",
        )
        return nodes_of_class(tree, moc_id)

    # -------------------------------------------------------------- discovery
    def _locate(self) -> None:
        if self.wallbox is None:
            boxes = self._children(self.station_dn, ep.MOC_WALLBOX)
            if not boxes:
                raise ChargerNotFound("no SCharger in this plant")
            self.wallbox = boxes[0]
        if self.connector is None and time.monotonic() >= self._connector_next_try:
            plugs = self._children(self.wallbox.dn, ep.MOC_CONNECTOR)
            if plugs:
                self.connector = plugs[0]
            else:
                self._connector_next_try = time.monotonic() + CONNECTOR_RETRY

    def locate(self) -> TreeNode:
        """Find the wallbox (and its connector); raises ChargerNotFound."""
        with self._lock:
            self._with_relogin(self._locate)
            assert self.wallbox is not None
            return self.wallbox

    # ---------------------------------------------------------------- reading
    def _load_settings(self) -> None:
        fresh_needed = bool(self._pending) or time.monotonic() - self._settings_at >= SETTINGS_TTL
        if self._settings and not fresh_needed:
            return
        merged: dict[int, Setting] = {}
        owner: dict[int, str] = {}
        for node in (self.wallbox, self.connector):
            if node is None:
                continue
            answer = self._get(
                ep.PATH_READ_SETTINGS, {"dn": node.dn, "_": int(time.time() * 1000)}, "read settings"
            )
            for sid, item in parse_settings(answer).items():
                merged[sid] = item
                owner[sid] = node.dn
        self._settings, self._settings_owner = merged, owner
        self._settings_at = time.monotonic()

    def _load_plant(self) -> PlantFigures | None:
        if not self._plant_enabled:
            return None
        if self._plant is not None and time.monotonic() - self._plant_at < PLANT_TTL:
            return self._plant
        now_ms = int(time.time() * 1000)
        offset = datetime.now().astimezone().utcoffset()
        answer = self.session.request(
            "GET", ep.PATH_SOCIAL_CONTRIBUTION, label="plant figures",
            params={
                "dn": self.station_dn,
                "clientTime": now_ms,
                "timeZone": str(int(offset.total_seconds() // 3600) if offset else 0),
                "_": now_ms,
            },
            headers={
                "Referer": self.session.app_referer,
                "X-Requested-With": "XMLHttpRequest",
                "Roarand": self.session.csrf_token(),
            },
        )
        self._plant, self._plant_at = parse_plant_figures(answer), time.monotonic()
        return self._plant

    def _poll(self) -> ChargerReading:
        self._locate()
        assert self.wallbox is not None
        ids = [n.element_id for n in (self.connector, self.wallbox) if n is not None]
        answer = self._post_json(
            ep.PATH_LIVE_VALUES,
            {"conditions": [{"dnId": i, "queryAll": True} for i in ids]},
            "live values",
        )
        fetched_at = datetime.now(timezone.utc)
        plug = live_signals(answer, self.connector.element_id if self.connector else None)
        box = live_signals(answer, self.wallbox.element_id)

        fallback = None
        if ep.SIGNAL_ENERGY_TOTAL_KWH not in box:
            try:
                fallback = device_signal_value(
                    self._get(ep.PATH_DEVICE_SIGNALS,
                              {"deviceDn": self.wallbox.dn, "displayAccessModel": "true"},
                              "device signals"),
                    ep.SIGNAL_ENERGY_TOTAL_KWH,
                )
            except SessionInvalid:
                raise
            except PortalError as err:
                _LOGGER.debug("Energy fallback not available: %s", err)

        try:
            self._load_settings()
        except SessionInvalid:
            raise
        except PortalError as err:
            _LOGGER.debug("Settings not readable, keeping previous values: %s", err)
        settings = apply_pending(
            self._settings, self._pending, self._settings_at, time.monotonic(), CONFIRM_TIMEOUT
        )

        reading = compose_reading(
            plug, box, settings, fallback,
            has_connector=self.connector is not None, fetched_at=fetched_at,
        )
        try:
            reading.plant = self._load_plant()
        except SessionInvalid:
            raise
        except PortalError as err:
            _LOGGER.debug("Plant figures not readable: %s", err)
            reading.plant = self._plant
        return reading

    def read(self) -> ChargerReading:
        """Fetch a fresh reading (re-logs in once if the session expired)."""
        with self._lock:
            return self._with_relogin(self._poll)

    # ---------------------------------------------------------------- writing
    def _send_setting(self, dn: str, signal_id: int, value: str) -> bool:
        answer = self.session.request(
            "POST", ep.PATH_WRITE_SETTINGS, label=f"write setting {signal_id}",
            data={
                "dn": dn,
                "changeValues": json.dumps([{"id": str(signal_id), "value": value}], separators=(",", ":")),
            },
            headers={"Referer": self.session.app_referer, "Roarand": self.session.csrf_token()},
        )
        return write_accepted(answer)

    def write_setting(self, signal_id: int, value: str) -> bool:
        """Change one wallbox/connector setting.

        Returns True when the portal accepted the request. Until a later read
        shows the new value (or ``CONFIRM_TIMEOUT`` passes) the written value
        is reported; while a write is pending, every poll reads the settings
        fresh instead of using the cache.
        """
        if signal_id not in WRITABLE_SETTINGS:
            raise ValueError(f"setting {signal_id} is not writable")
        with self._lock:
            dn = self._settings_owner.get(signal_id)
            if dn is None:
                raise ChargerNotFound(f"setting {signal_id} is not offered by this wallbox")
            accepted = self._with_relogin(lambda: self._send_setting(dn, signal_id, value))
            if accepted:
                self._pending[signal_id] = PendingWrite(value, time.monotonic())
            else:
                _LOGGER.warning("FusionSolar did not accept setting %s", signal_id)
            return accepted

    def set_mode(self, mode: str) -> bool:
        """Set the working mode: "normal" or "pv_preferred"."""
        if mode not in ep.MODE_CODES:
            raise ValueError(f"unknown working mode {mode!r}")
        return self.write_setting(ep.SETTING_MODE, ep.MODE_CODES[mode])

    def set_lock_mode(self, mode: str) -> bool:
        """Set the connector locking mode: "always", "while_charging" or "after_plug_in"."""
        if mode not in ep.LOCK_MODE_CODES:
            raise ValueError(f"unknown lock mode {mode!r}")
        return self.write_setting(ep.SETTING_LOCK_MODE, ep.LOCK_MODE_CODES[mode])
