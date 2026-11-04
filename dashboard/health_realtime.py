"""Normalize live infrared temperature payloads for the health page."""

from __future__ import annotations

import hashlib
import math
from datetime import datetime, timedelta, timezone


LOCAL_TZ = timezone(timedelta(hours=8))
MIN_TEMPERATURE = 35.0
MAX_TEMPERATURE = 42.0
DEFAULT_STALE_SECONDS = 10

OBJECT_TEMPERATURE_KEYS = (
    "mlx_obj",
    "object_temperature",
    "body_temperature",
    "body_temperature_c",
    "temperature_c",
    "temperature",
)
AMBIENT_TEMPERATURE_KEYS = (
    "mlx_amb",
    "ambient_temperature",
    "ambient_temperature_c",
    "ambient_c",
)
STUDENT_KEYS = ("student_id", "person_id", "target_student_id")
DEVICE_KEYS = ("device_id", "sensor_id", "source_id")
READING_KEYS = ("reading_id", "measurement_id", "sample_id", "event_id", "id")
TIME_KEYS = ("timestamp", "collected_at", "measured_at", "created_at", "ts", "updated_at")


def _candidate_containers(payload: dict) -> list[dict]:
    containers = [payload]
    for key in ("properties", "sensor", "data"):
        value = payload.get(key)
        if isinstance(value, dict):
            containers.append(value)
            nested = value.get("properties")
            if isinstance(nested, dict):
                containers.append(nested)
    return containers


def _first(payload: dict, keys: tuple[str, ...]):
    for container in _candidate_containers(payload):
        for key in keys:
            if key in container and container[key] not in (None, ""):
                return container[key]
    return None


def _number(value):
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _boolean(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in ("1", "true", "yes", "on", "connected"):
            return True
        if normalized in ("0", "false", "no", "off", "disconnected"):
            return False
    return None


def parse_sensor_time(value) -> datetime | None:
    if isinstance(value, bool) or value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        try:
            seconds = float(value)
            if seconds > 10_000_000_000:
                seconds /= 1000
            return datetime.fromtimestamp(seconds, LOCAL_TZ)
        except (OSError, OverflowError, ValueError):
            return None
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    try:
        numeric = float(text)
        return parse_sensor_time(numeric)
    except ValueError:
        pass
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=LOCAL_TZ)
    return parsed.astimezone(LOCAL_TZ)


def _iso(value: datetime | None) -> str | None:
    return value.astimezone(LOCAL_TZ).isoformat() if value else None


def _text(value, maximum: int = 160) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        value = str(value)
    return value.strip()[:maximum]


def _reading_id(
    student_id: str,
    device_id: str,
    measured_at: str | None,
    temperature: float | None,
) -> str:
    basis = "|".join((
        student_id,
        device_id,
        measured_at or "",
        "" if temperature is None else f"{temperature:.1f}",
    ))
    return "IRT-" + hashlib.sha256(basis.encode("utf-8")).hexdigest()[:24].upper()


def normalize_infrared_payload(
    payload: dict,
    *,
    now: datetime | None = None,
    stale_after_seconds: float = DEFAULT_STALE_SECONDS,
) -> dict:
    """Return a display-safe reading; this function never assigns a student."""
    if not isinstance(payload, dict):
        raise ValueError("infrared payload must be an object")
    current = (now or datetime.now(LOCAL_TZ)).astimezone(LOCAL_TZ)
    measured_dt = parse_sensor_time(_first(payload, TIME_KEYS))
    measured_at = _iso(measured_dt)
    age = (current - measured_dt).total_seconds() if measured_dt is not None else None
    age_seconds = max(0, int(age)) if age is not None else None
    connected_value = _first(payload, ("connected", "sensor_connected"))
    connected = _boolean(connected_value)
    temperature = _number(_first(payload, OBJECT_TEMPERATURE_KEYS))
    ambient = _number(_first(payload, AMBIENT_TEMPERATURE_KEYS))
    student_id = _text(_first(payload, STUDENT_KEYS), 20)
    device_id = _text(_first(payload, DEVICE_KEYS), 160) or "rdk-x5"
    source_reading_id = _text(_first(payload, READING_KEYS), 160)
    reading_id = source_reading_id or _reading_id(
        student_id,
        device_id,
        measured_at,
        temperature,
    )
    stable_value = _first(payload, ("stable", "is_stable"))
    stable = _boolean(stable_value)

    valid_temperature = (
        temperature is not None
        and MIN_TEMPERATURE <= temperature <= MAX_TEMPERATURE
    )
    if connected is False:
        status = "offline"
    elif temperature is None:
        status = "unavailable"
    elif not valid_temperature:
        status = "invalid_temperature"
    elif measured_dt is None:
        status = "timestamp_unknown"
    elif age < -5:
        status = "timestamp_future"
    elif age > stale_after_seconds:
        status = "stale"
    elif stable is False:
        status = "unstable"
    elif not student_id:
        status = "unassigned"
    else:
        status = "ready"

    return {
        "reading_id": reading_id,
        "student_id": student_id,
        "device_id": device_id,
        "temperature_c": round(temperature, 1) if temperature is not None else None,
        "ambient_c": round(ambient, 1) if ambient is not None else None,
        "measured_at": measured_at,
        "age_seconds": age_seconds,
        "connected": connected,
        "stable": stable,
        "valid_temperature": valid_temperature,
        "fresh": status in ("unassigned", "ready"),
        "status": status,
        "stale_after_seconds": stale_after_seconds,
    }


def refresh_infrared_status(
    reading: dict,
    *,
    now: datetime | None = None,
    stale_after_seconds: float = DEFAULT_STALE_SECONDS,
) -> dict:
    if not isinstance(reading, dict):
        raise ValueError("reading must be an object")
    current = (now or datetime.now(LOCAL_TZ)).astimezone(LOCAL_TZ)
    measured_dt = parse_sensor_time(reading.get("measured_at"))
    refreshed = dict(reading)
    refreshed["stale_after_seconds"] = stale_after_seconds
    age = (current - measured_dt).total_seconds() if measured_dt is not None else None
    refreshed["age_seconds"] = max(0, int(age)) if age is not None else None
    if refreshed.get("connected") is False:
        refreshed["status"] = "offline"
    elif refreshed.get("temperature_c") is None:
        refreshed["status"] = "unavailable"
    elif not refreshed.get("valid_temperature"):
        refreshed["status"] = "invalid_temperature"
    elif measured_dt is None:
        refreshed["status"] = "timestamp_unknown"
    elif age < -5:
        refreshed["status"] = "timestamp_future"
    elif age > stale_after_seconds:
        refreshed["status"] = "stale"
    elif refreshed.get("stable") is False:
        refreshed["status"] = "unstable"
    elif not refreshed.get("student_id"):
        refreshed["status"] = "unassigned"
    else:
        refreshed["status"] = "ready"
    refreshed["fresh"] = refreshed["status"] in ("unassigned", "ready")
    return refreshed
