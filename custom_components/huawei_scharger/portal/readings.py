"""Pure functions that turn portal JSON into a ``ChargerReading``.

Nothing here performs I/O or imports Home Assistant, so it can be unit tested
with synthetic payloads.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from . import endpoints as ep
from .errors import UnexpectedPayload

Signals = dict[int, dict[str, Any]]


@dataclass(frozen=True)
class TreeNode:
    """A device found in the plant tree."""

    dn: str
    element_id: int
    name: str | None = None


@dataclass(frozen=True)
class Setting:
    """One config signal as reported by the portal."""

    value: str | None
    minimum: float | None = None
    maximum: float | None = None


@dataclass(frozen=True)
class PendingWrite:
    """A write the portal accepted but has not yet confirmed by read-back."""

    value: str
    since: float          # monotonic time of the write


@dataclass
class PlantFigures:
    """Environmental figures of the plant ("social contribution")."""

    co2_avoided_kg: float | None = None
    standard_coal_saved_kg: float | None = None
    equivalent_trees: int | None = None


@dataclass
class ChargerReading:
    """One poll worth of wallbox values (``None`` = not reported)."""

    power_kw: float | None = None
    status: str | None = None                 # "charging" / "idle"
    energy_total_kwh: float | None = None
    working_status: str | None = None         # vehicle / connection state as text
    working_mode: str | None = None           # mode as reported in the live data
    lock_state: str | None = None
    reported_status: str | None = None
    currents_a: dict[str, float | None] = field(default_factory=dict)
    temperature_c: float | None = None
    data_time: datetime | None = None         # when the live values were fetched
    settings: dict[int, Setting] = field(default_factory=dict)
    model: str | None = None
    firmware: str | None = None
    serial: str | None = None
    has_connector: bool = False
    plant: PlantFigures | None = None

    # --- convenience views on the settings -----------------------------------
    def setting(self, signal_id: int) -> str | None:
        item = self.settings.get(signal_id)
        return item.value if item else None

    def setting_number(self, signal_id: int) -> float | None:
        return to_float(self.setting(signal_id))

    @property
    def dynamic_power_kw(self) -> float | None:
        return self.setting_number(ep.SETTING_DYNAMIC_POWER)

    @property
    def max_power_kw(self) -> float | None:
        return self.setting_number(ep.SETTING_MAX_POWER)

    @property
    def mode_setting(self) -> str | None:
        return code_to_name(self.setting(ep.SETTING_MODE), ep.MODE_NAMES)

    @property
    def lock_mode_setting(self) -> str | None:
        return code_to_name(self.setting(ep.SETTING_LOCK_MODE), ep.LOCK_MODE_NAMES)


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def to_float(value: Any) -> float | None:
    """Parse ``12.3``, ``"12.3"`` or ``"12.3 kW"``; placeholders give ``None``."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if text in ("", "-", "--", "null", "N/A"):
        return None
    try:
        return float(text.split()[0].replace(",", "."))
    except (ValueError, IndexError):
        return None


def code_to_name(code: str | None, names: dict[str, str]) -> str | None:
    """Map a raw enum setting ("0", "1", "1.0") to its option name."""
    if code is None:
        return None
    return names.get(str(code).split(".")[0])


def same_value(a: Any, b: Any) -> bool:
    """Compare setting values numerically when possible ("11" == "11.0")."""
    fa, fb = to_float(a), to_float(b)
    if fa is not None and fb is not None:
        return abs(fa - fb) < 1e-6
    return str(a) == str(b)


def nodes_of_class(tree: Any, moc_id: int) -> list[TreeNode]:
    """Collect all devices of the given object class from a device tree answer."""
    if not isinstance(tree, dict) or not isinstance(tree.get("childList"), list):
        raise UnexpectedPayload("device tree without childList")
    found: list[TreeNode] = []
    pending: list[Any] = list(tree["childList"])
    while pending:
        node = pending.pop(0)
        if not isinstance(node, dict):
            continue
        pending.extend(node.get("childList") or [])
        if _as_int(node.get("mocId")) != moc_id:
            continue
        dn, element_id = str(node.get("elementDn", "")), _as_int(node.get("elementId"))
        if dn.startswith("NE=") and element_id is not None:
            found.append(TreeNode(dn, element_id, node.get("nodeName") or node.get("name")))
    return found


def live_signals(answer: Any, element_id: int | None) -> Signals:
    """Signals of one device from a get-realtime-info answer (keyed by dnId)."""
    if element_id is None or not isinstance(answer, dict):
        return {}
    rows = answer.get(str(element_id))
    if not isinstance(rows, list) and isinstance(answer.get("data"), dict):
        rows = answer["data"].get(str(element_id))
    out: Signals = {}
    for row in rows or []:
        if isinstance(row, dict) and (sid := _as_int(row.get("id"))) is not None:
            out[sid] = row
    return out


def parse_settings(answer: Any) -> dict[int, Setting]:
    """Config signals (value plus allowed range) from a get-config-signals answer."""
    out: dict[int, Setting] = {}
    if not isinstance(answer, dict):
        return out
    for group in answer.get("data") or []:
        if not isinstance(group, dict):
            continue
        for row in group.get("configSignalDisplayList") or []:
            if isinstance(row, dict) and (sid := _as_int(row.get("id"))) is not None:
                value = row.get("value")
                out[sid] = Setting(
                    None if value is None else str(value),
                    to_float(row.get("minValue")),
                    to_float(row.get("maxValue")),
                )
    return out


def apply_pending(
    settings: dict[int, Setting],
    pending: dict[int, PendingWrite],
    read_at: float,
    now: float,
    timeout: float,
) -> dict[int, Setting]:
    """Overlay accepted-but-unconfirmed writes on the read settings.

    A pending write is dropped (mutating ``pending``) once a read taken after
    the write shows the new value, or after ``timeout`` seconds; from then on
    the value reported by the portal counts again.
    """
    merged = dict(settings)
    for sid, write in list(pending.items()):
        current = settings.get(sid)
        confirmed = (
            read_at > write.since and current is not None and current.value is not None
            and same_value(current.value, write.value)
        )
        if confirmed or now - write.since > timeout:
            del pending[sid]
            continue
        base = current or Setting(None)
        merged[sid] = Setting(write.value, base.minimum, base.maximum)
    return merged


def device_signal_value(answer: Any, signal_id: int) -> float | None:
    """Numeric value of one signal from a device-realtime-data answer."""
    if not isinstance(answer, dict):
        return None
    for group in answer.get("data") or []:
        if not isinstance(group, dict):
            continue
        for row in group.get("signals") or []:
            if isinstance(row, dict) and _as_int(row.get("id")) == signal_id:
                return to_float(row.get("value"))
    return None


def parse_plant_figures(answer: Any) -> PlantFigures:
    """Values of a social-contribution answer (kg / count)."""
    data = answer.get("data") if isinstance(answer, dict) else None
    if not isinstance(data, dict):
        raise UnexpectedPayload("social contribution without data")
    trees = to_float(data.get("equivalentTreePlanting"))
    return PlantFigures(
        co2_avoided_kg=to_float(data.get("co2Reduction")),
        standard_coal_saved_kg=to_float(data.get("standardCoalSavings")),
        equivalent_trees=None if trees is None else int(round(trees)),
    )


def _text(signals: Signals, sid: int) -> str | None:
    row = signals.get(sid) or {}
    value = row.get("realValue")
    if value in (None, ""):
        value = row.get("value")
    return None if value in (None, "") else str(value)


def _number(signals: Signals, sid: int) -> float | None:
    row = signals.get(sid)
    return to_float(row.get("value")) if row else None


def compose_reading(
    connector: Signals,
    wallbox: Signals,
    settings: dict[int, Setting] | None = None,
    fallback_energy_kwh: float | None = None,
    has_connector: bool = True,
    fetched_at: datetime | None = None,
) -> ChargerReading:
    """Combine the parsed portal answers into one reading."""
    reading = ChargerReading(has_connector=has_connector, settings=dict(settings or {}))

    reading.power_kw = _number(connector, ep.SIGNAL_POWER_KW)
    if reading.power_kw is not None:
        reading.status = "charging" if reading.power_kw >= ep.CHARGING_THRESHOLD_KW else "idle"
    reading.working_status = _text(connector, ep.SIGNAL_WORKING_STATUS)
    reading.working_mode = _text(connector, ep.SIGNAL_WORKING_MODE)
    reading.lock_state = _text(connector, ep.SIGNAL_LOCK_STATE)
    reading.reported_status = _text(connector, ep.SIGNAL_REPORTED_STATUS)
    reading.currents_a = {phase: _number(connector, sid) for phase, sid in ep.SIGNAL_PHASE_CURRENTS.items()}

    reading.energy_total_kwh = _number(wallbox, ep.SIGNAL_ENERGY_TOTAL_KWH)
    if reading.energy_total_kwh is None:
        reading.energy_total_kwh = fallback_energy_kwh
    reading.temperature_c = _number(wallbox, ep.SIGNAL_TEMPERATURE)
    reading.model = _text(wallbox, ep.SIGNAL_MODEL)
    reading.firmware = _text(wallbox, ep.SIGNAL_FIRMWARE)
    reading.serial = _text(wallbox, ep.SIGNAL_SERIAL)
    if connector or wallbox:
        reading.data_time = fetched_at
    return reading


def write_accepted(answer: Any) -> bool:
    """True if a set-config-signals answer reports success for every item."""
    if not isinstance(answer, dict) or answer.get("code") != 0:
        return False
    items = answer.get("data")
    return isinstance(items, list) and bool(items) and all(
        isinstance(i, dict) and i.get("code") == 0 for i in items
    )
