"""异常事件的统一数据契约。

事件页、日报和后续接口都以本模块的字段和枚举为准。C 的日报仍可使用
high/medium/low 和 handled 作为展示层别名，但写入统一事件库前必须映射到
urgent/watch/info 和 resolved。
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit


EVENT_LEVELS = ("urgent", "watch", "info")
EVENT_STATUSES = ("pending", "resolved", "false_alarm")
EVENT_TYPES = (
    "fall",
    "fight",
    "device_offline",
    "sensor_expired",
    "environment",
    "dialogue_attention",
    "sensor_recovered",
)
EVENT_SOURCES = ("rdk", "sensor", "dialogue", "device", "manual")

LEVEL_ALIASES = {
    "urgent": "urgent",
    "high": "urgent",
    "watch": "watch",
    "medium": "watch",
    "info": "info",
    "low": "info",
}
STATUS_ALIASES = {
    "pending": "pending",
    "resolved": "resolved",
    "handled": "resolved",
    "false_alarm": "false_alarm",
}
REPORT_LEVEL = {"urgent": "high", "watch": "medium", "info": "low"}
REPORT_STATUS = {"pending": "pending", "resolved": "handled", "false_alarm": "false_alarm"}

LOCAL_TZ = timezone(timedelta(hours=8))
ALLOWED_STATUS_TRANSITIONS = {
    "pending": {"resolved", "false_alarm"},
    "resolved": {"pending"},
    "false_alarm": {"pending"},
}
MAX_HISTORY = 100
MAX_EVIDENCE_URL = 500_000
RASTER_DATA_IMAGE = re.compile(
    r"^data:image/(?:png|jpeg|webp|gif);base64,[A-Za-z0-9+/]+={0,2}$",
    re.IGNORECASE,
)


class EventValidationError(ValueError):
    """请求字段不合法。"""


class EventNotFound(LookupError):
    """事件编号不存在。"""


class EventConflict(ValueError):
    """状态转换不允许。"""


def now_iso() -> str:
    return datetime.now(LOCAL_TZ).isoformat(timespec="seconds")


def parse_datetime(value) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise EventValidationError("occurred_at must be an ISO 8601 string")
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise EventValidationError("occurred_at must be an ISO 8601 string") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=LOCAL_TZ)
    return parsed.astimezone(LOCAL_TZ)


def normalize_iso(value, field: str = "time") -> str:
    try:
        return parse_datetime(value).isoformat(timespec="seconds")
    except EventValidationError as exc:
        raise EventValidationError(f"{field} must be an ISO 8601 string") from exc


def date_key(value) -> str:
    return parse_datetime(value).date().isoformat()


def text_value(value, field: str, maximum: int, *, required: bool = False, default: str = "") -> str:
    if value is None:
        value = default
    if not isinstance(value, str):
        raise EventValidationError(f"{field} must be a string")
    value = value.strip()
    if required and not value:
        raise EventValidationError(f"{field} is required")
    if len(value) > maximum:
        raise EventValidationError(f"{field} is too long")
    return value


def enum_value(value, aliases: dict, field: str, default: str) -> str:
    if value is None or value == "":
        return default
    if not isinstance(value, str):
        raise EventValidationError(f"{field} must be a string")
    normalized = aliases.get(value.strip().lower())
    if normalized is None:
        raise EventValidationError(f"invalid {field}")
    return normalized


def normalize_evidence_url(value) -> str:
    """Accept only same-origin paths or non-SVG raster data URLs."""
    if value in (None, ""):
        return ""
    if not isinstance(value, str):
        raise EventValidationError("evidence_url must be a string")
    value = value.strip()
    if not value:
        return ""
    if len(value) > MAX_EVIDENCE_URL:
        raise EventValidationError("evidence_url is too long")
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise EventValidationError("evidence_url contains control characters")
    if value.lower().startswith("data:image/"):
        if not RASTER_DATA_IMAGE.fullmatch(value):
            raise EventValidationError("evidence_url must be a raster image data URL")
        return value
    if not value.startswith("/") or value.startswith("//"):
        raise EventValidationError("evidence_url must be a same-origin path")
    parsed = urlsplit(value)
    if parsed.scheme or parsed.netloc or "\\" in value:
        raise EventValidationError("evidence_url must be a same-origin path")
    return value


def normalize_event(payload: dict, event_id: str | None = None) -> dict:
    """把接口、日报或历史文件中的事件规范化为统一结构。"""
    if not isinstance(payload, dict):
        raise EventValidationError("event must be an object")

    event_type = text_value(
        payload.get("event_type") or payload.get("type"),
        "event_type",
        64,
        required=True,
    )
    if event_type not in EVENT_TYPES:
        raise EventValidationError("invalid event_type")

    level = enum_value(payload.get("level"), LEVEL_ALIASES, "level", "watch")
    status = enum_value(payload.get("status"), STATUS_ALIASES, "status", "pending")
    source = enum_value(payload.get("source"), {item: item for item in EVENT_SOURCES}, "source", "manual")

    occurred_at = normalize_iso(
        payload.get("occurred_at") or payload.get("created_at") or now_iso(),
        "occurred_at",
    )
    summary = text_value(
        payload.get("summary") or payload.get("title"),
        "summary",
        200,
        required=True,
    )
    detail = text_value(
        payload.get("detail") or payload.get("description"),
        "detail",
        4000,
        default="",
    )
    location = text_value(payload.get("location"), "location", 100, default="未记录")
    device_id = text_value(payload.get("device_id"), "device_id", 160, default="")
    class_id = text_value(payload.get("class_id"), "class_id", 64, default="")
    class_name = text_value(payload.get("class_name"), "class_name", 80, default="")
    dedupe_key = text_value(payload.get("dedupe_key"), "dedupe_key", 160, default="")
    evidence_url = normalize_evidence_url(payload.get("evidence_url"))
    evidence_captured_at = payload.get("evidence_captured_at")
    evidence_captured_at = (
        normalize_iso(evidence_captured_at, "evidence_captured_at")
        if evidence_captured_at
        else None
    )

    confidence = payload.get("confidence")
    if confidence in (None, ""):
        confidence = None
    else:
        try:
            confidence = float(confidence)
        except (TypeError, ValueError) as exc:
            raise EventValidationError("confidence must be a number") from exc
        if not 0 <= confidence <= 1:
            raise EventValidationError("confidence must be between 0 and 1")

    handled_at = payload.get("handled_at")
    handled_at = normalize_iso(handled_at, "handled_at") if handled_at else None
    handled_by = text_value(
        payload.get("handled_by") or payload.get("handler"),
        "handled_by",
        80,
        default="",
    )
    note = text_value(payload.get("note"), "note", 200, default="")
    normalized_id = event_id or text_value(payload.get("id"), "id", 80, default="")
    if normalized_id and not normalized_id.startswith("EVT-"):
        # 允许测试或迁移数据使用其它编号，但拒绝带路径分隔符的值。
        if "/" in normalized_id or "\\" in normalized_id:
            raise EventValidationError("invalid event id")

    history = []
    raw_history = payload.get("history")
    if isinstance(raw_history, list):
        for raw_item in raw_history[-MAX_HISTORY:]:
            if not isinstance(raw_item, dict):
                continue
            history.append({
                "at": normalize_iso(raw_item.get("at") or occurred_at, "history.at"),
                "action": text_value(raw_item.get("action"), "history.action", 80, default="记录"),
                "by": text_value(raw_item.get("by"), "history.by", 80, default="系统"),
                "note": text_value(raw_item.get("note"), "history.note", 500, default=""),
            })
    if not history:
        history.append({
            "at": occurred_at,
            "action": "系统检测",
            "by": source,
            "note": summary,
        })

    return {
        "id": normalized_id,
        "event_type": event_type,
        "level": level,
        "source": source,
        "status": status,
        "occurred_at": occurred_at,
        "summary": summary,
        "detail": detail,
        "device_id": device_id,
        "class_id": class_id,
        "class_name": class_name,
        "location": location,
        "confidence": confidence,
        "handled_at": handled_at,
        "handled_by": handled_by,
        "note": note,
        "dedupe_key": dedupe_key,
        "evidence_url": evidence_url,
        "evidence_captured_at": evidence_captured_at,
        "history": history,
        "updated_at": normalize_iso(payload.get("updated_at") or now_iso(), "updated_at"),
    }


def make_event_id(occurred_at: str) -> str:
    day = date_key(occurred_at).replace("-", "")
    return f"EVT-{day}-{uuid.uuid4().hex[:6].upper()}"


def validate_status_transition(current: str, target: str) -> None:
    if target not in EVENT_STATUSES:
        raise EventValidationError("invalid status")
    if target == current:
        return
    if target not in ALLOWED_STATUS_TRANSITIONS.get(current, set()):
        raise EventConflict(f"cannot change status from {current} to {target}")


def event_for_report(event: dict) -> dict:
    """转换为 C 日报的事件展示结构；API 汇总时使用。"""
    return {
        "id": event["id"],
        "type": event["event_type"],
        "title": event["summary"],
        "level": REPORT_LEVEL[event["level"]],
        "class_id": event.get("class_id") or "",
        "class_name": event.get("class_name") or "",
        "location": event.get("location") or "",
        "occurred_at": event["occurred_at"],
        "status": REPORT_STATUS[event["status"]],
        "handler": event.get("handled_by") or "",
        "handled_at": event.get("handled_at") or "",
        "note": event.get("note") or "",
    }
