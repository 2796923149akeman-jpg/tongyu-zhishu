"""课程项目 V1：电脑端基础监控页面。

RDK 运行 web_fall.py，本服务在电脑端把 RDK 的实时画面、行为状态和
STM32 传感器数据转发到同一个简易网页，并提供 ESP32 对话回顾页。
对话页可在后台进行词库/模型情绪分析与会话总结，不影响设备语音链路。
"""

from __future__ import annotations

import json
import hashlib
import hmac
import math
import os
import queue
import re
import tempfile
import threading
import time
import unicodedata
import uuid
from collections import deque
from datetime import datetime, timedelta, timezone
import urllib.error
import urllib.request
from http.client import HTTPException
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from http.cookies import SimpleCookie, CookieError
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse, quote


ROOT = Path(__file__).resolve().parent
import sys
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis import (
    ATTENTION_ORDER, DEFAULT_ANALYSIS_CONFIG, analyze_emotion, analyze_lexicon,
    load_lexicon, load_xiaozhi_model, local_conversation_summary,
    public_analysis_config, public_xiaozhi_model, summarize_conversation,
    update_xiaozhi_model, validate_analysis_config,
)
from event_contract import (
    EVENT_LEVELS,
    EVENT_SOURCES,
    EVENT_STATUSES,
    MAX_PARTICIPANTS,
    EventConflict,
    EventNotFound,
    EventValidationError,
    date_key,
    event_for_report,
    make_event_id,
    normalize_iso,
    normalize_event,
    now_iso,
    text_value,
    validate_status_transition,
)
from access_control import AccessStore, COOKIE_NAME, MODULES
from health_realtime import normalize_infrared_payload, refresh_infrared_status
from person_type_runtime import PersonTypeRuntime

HOST = os.environ.get("DASHBOARD_HOST", "127.0.0.1")
PORT = int(os.environ.get("DASHBOARD_PORT", "8088"))
AUTH = AccessStore(
    os.environ.get("DASHBOARD_AUTH_FILE", str(ROOT / "auth_config.json")),
    secure=os.environ.get("DASHBOARD_COOKIE_SECURE", "1") != "0",
)
RDK_BASE = os.environ.get("RDK_BASE", "http://192.168.43.54:5000").rstrip("/")
PROJECT_ROOT = Path(os.environ.get("PROJECT_ROOT", str(ROOT.parent)))
PERSON_TYPE_RUNTIME = PersonTypeRuntime(PROJECT_ROOT, RDK_BASE)
DIALOGUE_LIMIT = 200
DIALOGUE_DATA_FILE = Path(
    os.environ.get("DIALOGUE_DATA_FILE", str(ROOT / "dialogue_messages.json"))
)
DIALOGUE_CONFIG_FILE = Path(
    os.environ.get("DIALOGUE_CONFIG_FILE", str(ROOT / "dialogue_config.json"))
)
ANALYSIS_CONFIG_FILE = Path(
    os.environ.get("ANALYSIS_CONFIG_FILE", str(ROOT / "analysis_config.json"))
)
CONVERSATION_SUMMARIES_FILE = Path(
    os.environ.get("CONVERSATION_SUMMARIES_FILE", str(ROOT / "conversation_summaries.json"))
)
EMOTION_LEXICON_FILE = Path(
    os.environ.get("EMOTION_LEXICON_FILE", str(ROOT / "emotion_lexicon.json"))
)
EVENTS_FILE = Path(os.environ.get("EVENTS_FILE", str(ROOT / "events.json")))
EVIDENCE_DIR = Path(os.environ.get("EVIDENCE_DIR", str(ROOT / "evidence")))
HEALTH_STUDENTS_FILE = Path(os.environ.get("HEALTH_STUDENTS_FILE", str(ROOT / "health_students.json")))
HEALTH_RECORDS_FILE = Path(os.environ.get("HEALTH_RECORDS_FILE", str(ROOT / "health_records.json")))
HEALTH_DEVICE_TOKEN = os.environ.get("HEALTH_DEVICE_TOKEN", "")
HEALTH_INFRARED_STALE_SECONDS = max(
    1,
    int(os.environ.get("HEALTH_INFRARED_STALE_SECONDS", "10")),
)
EVENTS_LIMIT = 2000
HEALTH_SOURCES = ("forehead", "infrared", "ear", "axillary")
HEALTH_SOURCE_LABELS = {
    "forehead": "额温枪",
    "infrared": "红外测温",
    "ear": "耳温枪",
    "axillary": "腋下体温计",
}
DEFAULT_HEALTH_CLASSES = (
    {"id": "C-02", "name": "小二班"},
    {"id": "C-11", "name": "中一班"},
    {"id": "C-21", "name": "大一班"},
)
# 学生测温与当日日报页面及其专用样式、脚本。页面只包含静态结构和演示数据，
# 名单与测温数据需要后续接口提供；这些路由不读取任何本机业务数据。
STATIC_PAGES = {
    "/health.html": ("health.html", "text/html; charset=utf-8"),
    "/reports.html": ("reports.html", "text/html; charset=utf-8"),
    "/health-report.css": ("health-report.css", "text/css; charset=utf-8"),
    "/health-report.js": ("health-report.js", "text/javascript; charset=utf-8"),
}
PAGE_ROUTES = {
    "/": ("index.html", "monitor"), "/index.html": ("index.html", "monitor"),
    "/events": ("events.html", "events"), "/events.html": ("events.html", "events"),
    "/chat": ("chat.html", "chat"), "/chat.html": ("chat.html", "chat"),
    "/health.html": ("health.html", "health"), "/reports.html": ("reports.html", "reports"),
    "/family-events.html": ("family-events.html", None),
    "/sensors.html": ("sensors.html", None),
    "/admin": ("admin.html", "admin"), "/admin.html": ("admin.html", "admin"),
    "/welcome": ("welcome.html", None),
}


def route_module(path):
    if path in PAGE_ROUTES:
        return PAGE_ROUTES[path][1]
    for prefix, module in (("/api/rdk/", "monitor"), ("/api/dialogue/", "chat"),
                           ("/api/analysis/", "chat"), ("/api/events", "events"),
                           ("/evidence/", "events"),
                           ("/api/health/", "health"), ("/api/reports/", "reports")):
        if path.startswith(prefix):
            return module
    if path == "/api/config":
        return "monitor"
    return None


def public_messages(items, raw):
    if raw:
        return items
    result = []
    for item in items:
        clean = {k: item[k] for k in ("id", "role", "device_id", "session_id", "created_at", "received_at") if k in item}
        clean["text"] = "对话原文未开放"
        emotion = item.get("emotion") or {}
        clean["emotion"] = {k: emotion[k] for k in ("label", "label_text", "confidence", "source", "attention") if k in emotion}
        result.append(clean)
    return result


def public_conversations(items, raw):
    # Summary, title and reasons can quote speech just as the message text can.
    keys = ("session_id", "dominant_emotion", "dominant_emotion_text", "attention", "message_count", "last_message_at")
    return [({k: item[k] for k in keys if k in item} | {"title": f"会话 {i + 1}"})
            for i, item in enumerate(items)] if not raw else items
DEFAULT_DIALOGUE_CONFIG = {
    "title": "陪伴对话记录",
    "refresh_seconds": 2,
    "page_size": 50,
    "show_session_id": False,
    "show_created_at": True,
    "auto_scroll": True,
}
MESSAGES_LOCK = threading.Lock()
EVENTS_LOCK = threading.Lock()
HEALTH_LOCK = threading.Lock()
HEALTH_REALTIME_LOCK = threading.Lock()
RDK_ALERT_LOCK = threading.Lock()
CURRENT_RDK_ALERT = "normal"
HEALTH_LAST_INFRARED = None
DIALOGUE_CONFIG_LOCK = threading.Lock()
ANALYSIS_CONFIG_LOCK = threading.Lock()
SUMMARIES_LOCK = threading.Lock()
ANALYSIS_QUEUE = queue.Queue(maxsize=512)
ANALYSIS_WORKER_STARTED = False
SUMMARY_TIMERS = {}
SUMMARY_TIMERS_LOCK = threading.Lock()


def read_json_file(path: Path, fallback):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return fallback


def atomic_write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        # Windows may briefly deny replacement while another process has the file open.
        for delay in (0.01, 0.025, 0.05, 0.1, None):
            try:
                os.replace(temporary_name, path)
                break
            except PermissionError as exc:
                if delay is None or getattr(exc, "winerror", None) not in (5, 32, 33):
                    raise
                time.sleep(delay)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


def load_messages() -> deque:
    data = read_json_file(DIALOGUE_DATA_FILE, [])
    if not isinstance(data, list):
        data = []
    valid = [item for item in data if isinstance(item, dict)]
    return deque(valid[-DIALOGUE_LIMIT:], maxlen=DIALOGUE_LIMIT)


def save_messages() -> None:
    atomic_write_json(DIALOGUE_DATA_FILE, list(MESSAGES))


def copy_event(event: dict) -> dict:
    return json.loads(json.dumps(event, ensure_ascii=False))


def load_events() -> list[dict]:
    data = read_json_file(EVENTS_FILE, [])
    if not isinstance(data, list):
        return []
    loaded = []
    for raw in data[-EVENTS_LIMIT:]:
        try:
            if isinstance(raw, dict) and "participants" not in raw and isinstance(raw.get("students"), list):
                raw = {**raw, "participants": [
                    {"student_id": item.get("id"), "student_name": item.get("name")}
                    for item in raw["students"][-MAX_PARTICIPANTS:]
                    if isinstance(item, dict) and isinstance(item.get("id"), str)
                    and re.fullmatch(r"[A-Za-z0-9-]{3,20}", item["id"])
                    and isinstance(item.get("name"), str) and item["name"].strip()
                ]}
            event = normalize_event(raw)
        except EventValidationError:
            continue
        if not event["id"]:
            event["id"] = make_event_id(event["occurred_at"])
        loaded.append(event)
    return loaded


def save_events() -> None:
    atomic_write_json(EVENTS_FILE, EVENTS)


def replace_event(index: int, event: dict) -> None:
    # Call under EVENTS_LOCK so a failed write cannot change family visibility.
    updated = EVENTS.copy()
    updated[index] = event
    atomic_write_json(EVENTS_FILE, updated)
    EVENTS[index] = event


SNAPSHOT_LIMIT = 2 * 1024 * 1024


def event_snapshot_path(event_id: str) -> Path:
    key = hashlib.sha256(event_id.encode("utf-8")).hexdigest()
    return EVENTS_FILE.parent / "event_snapshots" / f"{key}.jpg"


def stored_snapshot_path(event: dict) -> Path:
    path = event_snapshot_path(event["id"])
    name = event["id"] + ".jpg"
    if (not path.is_file() and event.get("evidence_url") == "/evidence/" + name
            and re.fullmatch(r"[A-Za-z0-9_-]{1,100}\.jpg", name)):
        legacy = EVIDENCE_DIR / name
        if legacy.resolve().parent == EVIDENCE_DIR.resolve():
            return legacy
    return path


def event_with_visible_evidence(event: dict, can_view: bool) -> dict:
    event["has_snapshot"] = False
    if not can_view:
        event.pop("evidence_url", None)
        event.pop("evidence_captured_at", None)
        return event
    try:
        modified = stored_snapshot_path(event).stat().st_mtime
    except OSError:
        return event
    event["has_snapshot"] = True
    event["snapshot_captured_at"] = datetime.fromtimestamp(modified, timezone.utc).isoformat()
    return event


def capture_event_snapshot(event_id: str) -> None:
    request = urllib.request.Request(RDK_BASE + "/snapshot", headers={"Accept": "image/jpeg"})
    try:
        with urllib.request.urlopen(request, timeout=1.5) as response:
            if response.headers.get_content_type() != "image/jpeg":
                return
            image = response.read(SNAPSHOT_LIMIT + 1)
    except urllib.error.HTTPError as exc:
        if exc.code not in (404, 405):
            raise
        image = capture_legacy_snapshot()
    if len(image) > SNAPSHOT_LIMIT or not image.startswith(b"\xff\xd8") or not image.endswith(b"\xff\xd9"):
        return
    path = event_snapshot_path(event_id)
    with EVENTS_LOCK:
        if not any(item["id"] == event_id for item in EVENTS):
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=path.parent, suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
        try:
            temporary.write_bytes(image)
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)


def capture_legacy_snapshot() -> bytes:
    request = urllib.request.Request(RDK_BASE + "/video_feed", headers={"Accept": "multipart/x-mixed-replace"})
    deadline = time.monotonic() + 1.5
    with urllib.request.urlopen(request, timeout=1.5) as response:
        buffer = bytearray()
        while len(buffer) <= SNAPSHOT_LIMIT and time.monotonic() < deadline:
            chunk = response.read1(16 * 1024)
            if not chunk:
                break
            previous_size = len(buffer)
            buffer.extend(chunk)
            start = buffer.find(b"\xff\xd8")
            if start == -1:
                del buffer[:-1]
                continue
            end = buffer.find(b"\xff\xd9", max(start + 2, previous_size - 1))
            if end != -1:
                return bytes(buffer[start:end + 2])
    return b""


def reload_events() -> list[dict]:
    loaded = load_events()
    with EVENTS_LOCK:
        EVENTS[:] = loaded
    return [copy_event(item) for item in loaded]


def events_snapshot() -> list[dict]:
    with EVENTS_LOCK:
        return [copy_event(item) for item in EVENTS]


def get_event(event_id: str) -> dict:
    with EVENTS_LOCK:
        event = next((item for item in EVENTS if item.get("id") == event_id), None)
        if event is None:
            raise EventNotFound("event not found")
        return copy_event(event)


def query_events(params: dict) -> dict:
    def one(name: str, default: str = "") -> str:
        values = params.get(name)
        return values[-1] if values else default

    status = one("status").strip().lower()
    level = one("level").strip().lower()
    source = one("source").strip().lower()
    class_id = one("class_id").strip()
    keyword = one("q").strip().casefold()
    date_from = one("date_from").strip()
    date_to = one("date_to").strip()
    sort = one("sort", "newest").strip().lower()
    if status and status not in EVENT_STATUSES:
        raise EventValidationError("invalid status")
    if level and level not in EVENT_LEVELS:
        raise EventValidationError("invalid level")
    if source and source not in EVENT_SOURCES:
        raise EventValidationError("invalid source")
    if sort not in ("newest", "oldest"):
        raise EventValidationError("invalid sort")
    for label, value in (("date_from", date_from), ("date_to", date_to)):
        if value:
            try:
                datetime.strptime(value, "%Y-%m-%d")
            except ValueError as exc:
                raise EventValidationError(f"invalid {label}") from exc
    try:
        limit = int(one("limit", "50"))
        offset = int(one("offset", "0"))
    except ValueError as exc:
        raise EventValidationError("invalid pagination") from exc
    if not 1 <= limit <= 200 or offset < 0:
        raise EventValidationError("invalid pagination")

    filtered = []
    for event in events_snapshot():
        if status and event["status"] != status:
            continue
        if level and event["level"] != level:
            continue
        if source and event["source"] != source:
            continue
        if class_id and event.get("class_id") != class_id:
            continue
        event_day = date_key(event["occurred_at"])
        if date_from and event_day < date_from:
            continue
        if date_to and event_day > date_to:
            continue
        if keyword:
            haystack = " ".join([
                event.get("id", ""),
                event.get("summary", ""),
                event.get("detail", ""),
                event.get("location", ""),
                event.get("device_id", ""),
                event.get("class_id", ""),
                event.get("class_name", ""),
            ]).casefold()
            if keyword not in haystack:
                continue
        filtered.append(event)

    filtered.sort(key=lambda item: item["occurred_at"], reverse=sort != "oldest")
    page = filtered[offset:offset + limit]
    updated_at = max((item.get("updated_at", "") for item in filtered), default=now_iso())
    return {
        "events": page,
        "total": len(filtered),
        "limit": limit,
        "offset": offset,
        "updated_at": updated_at or now_iso(),
    }


def family_event_view(event: dict, allowed_student_ids: set[str] | None, nicknames: dict, *, snapshots=True) -> dict | None:
    if (event["event_type"] not in ("fall", "fight") or not event.get("parent_visible_at")
            or event.get("status") == "false_alarm"):
        return None
    participants = [
        {"student_id": item["student_id"], "student_name": nicknames.get(item["student_id"]) or item["student_name"]}
        for item in event.get("participants", [])
        if allowed_student_ids is None or item.get("student_id") in allowed_student_ids
    ]
    if allowed_student_ids is not None and not participants:
        return None
    snapshot_time = None
    if snapshots and event.get("share_snapshot"):
        try:
            path = stored_snapshot_path(event)
            if path.is_file():
                snapshot_time = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()
        except OSError:
            pass
    return {
        "id": event["id"],
        "event_type": event["event_type"],
        "level": event["level"],
        "occurred_at": event["occurred_at"],
        "summary": (
            "系统检测到疑似摔倒"
            if event["event_type"] == "fall"
            else "系统检测到疑似斗殴"
        ),
        "detail": (
            "系统检测到疑似摔倒，老师已收到告警并正在核实处置。"
            if event["event_type"] == "fall"
            else "系统检测到疑似肢体冲突，老师已收到告警并正在核实处置。"
        ),
        "location": "",
        "class_name": "",
        "status": event["status"],
        "handled_at": event.get("handled_at"),
        "participants": participants,
        "parent_visible_at": event["parent_visible_at"],
        "has_snapshot": snapshot_time is not None,
        "snapshot_captured_at": snapshot_time,
    }


def student_nicknames() -> dict:
    return {item["id"]: item["nickname"] for item in health_student_snapshot() if item.get("nickname")}


def family_events_payload(user: dict) -> dict:
    allowed = None if user["role"] == "admin" else set(user.get("student_ids", []))
    snapshots = user["role"] == "admin" or user["access"]["snapshots"]
    nicknames = student_nicknames()
    events = []
    for event in events_snapshot():
        visible = family_event_view(event, allowed, nicknames, snapshots=snapshots)
        if visible is not None:
            events.append(visible)
    events.sort(key=lambda item: item["occurred_at"], reverse=True)
    return {
        "student_ids": sorted(allowed) if allowed is not None else [],
        "events": events[:100],
        "generated_at": now_iso(),
    }


def family_event_detail(user: dict, event_id: str) -> tuple[dict, dict]:
    allowed = None if user["role"] == "admin" else set(user.get("student_ids", []))
    event = next((item for item in events_snapshot() if item["id"] == event_id), None)
    if event is None:
        raise EventNotFound("event not found")
    snapshots = user["role"] == "admin" or user["access"]["snapshots"]
    visible = family_event_view(event, allowed, student_nicknames(), snapshots=snapshots)
    if visible is None:
        raise EventNotFound("event not found")
    return event, visible


def create_event(payload: dict) -> tuple[dict, int]:
    if not isinstance(payload, dict):
        raise EventValidationError("event must be an object")
    event = normalize_event(payload)
    if not event["id"]:
        event["id"] = make_event_id(event["occurred_at"])
    event["updated_at"] = now_iso()
    with EVENTS_LOCK:
        dedupe_key = event.get("dedupe_key", "")
        if dedupe_key:
            duplicate = next((item for item in EVENTS if item.get("dedupe_key") == dedupe_key), None)
            if duplicate is not None:
                return {"event": copy_event(duplicate), "duplicate": True}, 200
        if any(item.get("id") == event["id"] for item in EVENTS):
            raise EventConflict("event id already exists")
        updated = [*EVENTS, event]
        retained = updated[-EVENTS_LIMIT:]
        atomic_write_json(EVENTS_FILE, retained)
        EVENTS[:] = retained
        for removed in updated[:-EVENTS_LIMIT]:
            try:
                event_snapshot_path(removed["id"]).unlink(missing_ok=True)
            except OSError as exc:
                print(f"[EVENT] snapshot cleanup failed: {type(exc).__name__}")
    return {"event": copy_event(event), "duplicate": False}, 201


def change_event_status(event_id: str, payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise EventValidationError("request must be an object")
    target = str(payload.get("status", "")).strip().lower()
    if target not in EVENT_STATUSES:
        raise EventValidationError("invalid status")
    note = text_value(payload.get("note"), "note", 200, default="")
    handled_by = text_value(payload.get("handled_by"), "handled_by", 80, default="")
    with EVENTS_LOCK:
        index = next((i for i, item in enumerate(EVENTS) if item.get("id") == event_id), None)
        if index is None:
            raise EventNotFound("event not found")
        event = copy_event(EVENTS[index])
        validate_status_transition(event["status"], target)
        if event["status"] == target:
            return {"event": copy_event(event), "changed": False}
        now = now_iso()
        action = {
            "resolved": "标记已处理",
            "false_alarm": "标记误报",
            "pending": "重新打开",
        }[target]
        if note:
            event["note"] = note
        event["status"] = target
        if target == "false_alarm":
            event["parent_visible_at"] = None
            event["share_snapshot"] = False
        event["handled_at"] = None if target == "pending" else now
        event["handled_by"] = "" if target == "pending" else (handled_by or "值班老师")
        event["history"].append({
            "at": now,
            "action": action,
            "by": handled_by or "值班老师",
            "note": note,
        })
        event["history"] = event["history"][-100:]
        event["updated_at"] = now
        replace_event(index, event)
        return {"event": copy_event(event), "changed": True}


def append_event_note(event_id: str, payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise EventValidationError("request must be an object")
    note = text_value(payload.get("note"), "note", 200, default="")
    author = text_value(payload.get("author"), "author", 80, default="值班老师")
    with EVENTS_LOCK:
        event = next((item for item in EVENTS if item.get("id") == event_id), None)
        if event is None:
            raise EventNotFound("event not found")
        now = now_iso()
        event["note"] = note
        event["updated_at"] = now
        event["history"].append({
            "at": now,
            "action": "保存处理备注" if note else "清空处理备注",
            "by": author,
            "note": note,
        })
        event["history"] = event["history"][-100:]
        save_events()
        return {"event": copy_event(event)}


def resolve_event_participants(names_value: str) -> list[dict]:
    names = re.split(r"\s+", names_value.strip()) if isinstance(names_value, str) else []
    names = [name for name in names if name]
    if not names:
        raise EventValidationError("participant names are required")
    if len(names) > MAX_PARTICIPANTS:
        raise EventValidationError(f"at most {MAX_PARTICIPANTS} participants are allowed")
    students = health_student_snapshot()
    by_id = {student["id"]: student for student in students if student.get("active", True)}
    by_name = {}
    for student in by_id.values():
        by_name.setdefault(student["name"], []).append(student)

    participants = []
    errors = []
    seen = set()
    for value in names:
        token = value.strip()
        if "@" in token:
            name, student_id = (part.strip() for part in token.rsplit("@", 1))
            student = by_id.get(student_id)
            if student is None or (name and student["name"] != name):
                errors.append(f"未找到学生：{token}")
                continue
        else:
            candidates = by_name.get(token, [])
            if len(candidates) != 1:
                if candidates:
                    choices = "、".join(
                        f"{item['name']}@{item['id']}" for item in candidates
                    )
                    errors.append(f"姓名“{token}”对应多名学生，请使用：{choices}")
                else:
                    errors.append(f"未找到学生：{token}")
                continue
            student = candidates[0]
        if student["id"] in seen:
            continue
        seen.add(student["id"])
        participants.append({
            "student_id": student["id"],
            "student_name": student["name"],
            "input_name": token[:20],
        })
    if errors:
        raise EventValidationError("；".join(errors))
    return participants


def assign_event_participants(event_id: str, payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise EventValidationError("request must be an object")
    students = {item["id"]: item for item in health_student_snapshot()}
    if "student_ids" in payload:
        ids = validate_bound_students(payload["student_ids"], students)
        if not 1 <= len(ids) <= MAX_PARTICIPANTS:
            raise EventValidationError(f"请选择 1–{MAX_PARTICIPANTS} 名学生")
        participants = [
            {"student_id": sid, "student_name": students[sid]["name"], "input_name": ""}
            for sid in dict.fromkeys(ids)
        ]
    else:
        names = payload.get("names")
        if not isinstance(names, str):
            raise EventValidationError("names must be a string")
        participants = resolve_event_participants(names)
    share_snapshot = payload.get("share_snapshot", False)
    if type(share_snapshot) is not bool:
        raise EventValidationError("share_snapshot must be a boolean")
    handled_by = text_value(payload.get("handled_by"), "handled_by", 80, default="值班老师")
    with EVENTS_LOCK:
        index = next((i for i, item in enumerate(EVENTS) if item.get("id") == event_id), None)
        if index is None:
            raise EventNotFound("event not found")
        event = copy_event(EVENTS[index])
        if event["status"] == "false_alarm":
            raise EventValidationError("请先重新打开误报事件，再关联学生")
        if event["event_type"] == "fall" and len(participants) != 1:
            raise EventValidationError("fall event requires exactly one student")
        if event["event_type"] == "fight" and len(participants) < 2:
            raise EventValidationError("fight event requires at least two students")
        if event["event_type"] not in ("fall", "fight") and not participants:
            raise EventValidationError("event requires at least one student")
        if share_snapshot and (event["event_type"] not in ("fall", "fight") or not stored_snapshot_path(event).is_file()):
            raise EventValidationError("当前事件没有可开放的截图")
        class_ids = {
            students[item["student_id"]].get("class_id", "")
            for item in participants
            if item["student_id"] in students
        }
        class_ids.discard("")
        if len(class_ids) == 1:
            class_id = next(iter(class_ids))
            event["class_id"] = class_id
            event["class_name"] = (
                students[participants[0]["student_id"]].get("class_name") or class_id
            )
        else:
            event["class_id"] = ""
            event["class_name"] = "跨班事件" if len(class_ids) > 1 else ""
        now = now_iso()
        event["participants"] = participants
        event["parent_visible_at"] = now
        event["share_snapshot"] = share_snapshot
        event["updated_at"] = now
        labels = "、".join(item["student_name"] for item in participants)
        event["history"].append({
            "at": now,
            "action": "关联事件学生",
            "by": handled_by,
            "note": f"已关联：{labels}；家长账号可查看该事件。",
        })
        event["history"] = event["history"][-100:]
        replace_event(index, event)
        return {"event": copy_event(event), "changed": True}


def record_rdk_alert(data: dict) -> None:
    """把 RDK 行为告警从正常→告警的边沿写入事件库。"""
    global CURRENT_RDK_ALERT
    if not isinstance(data, dict):
        return
    alert = str(data.get("alert_type", "")).strip().lower()
    if alert not in ("fall", "fight"):
        with RDK_ALERT_LOCK:
            CURRENT_RDK_ALERT = "normal"
        return
    with RDK_ALERT_LOCK:
        if CURRENT_RDK_ALERT == alert:
            return
        confidence = data.get("confidence")
        try:
            confidence = float(confidence) if confidence not in (None, "") else None
            if confidence is not None and not 0 <= confidence <= 1:
                confidence = None
        except (TypeError, ValueError):
            confidence = None
        title = "检测到疑似摔倒" if alert == "fall" else "检测到疑似斗殴"
        try:
            result, _ = create_event({
                "event_type": alert,
                "level": "urgent",
                "source": "rdk",
                "status": "pending",
                "occurred_at": now_iso(),
                "summary": title,
                "detail": f"RDK /alert_status 返回 alert_type={alert}，请查看监控画面并现场确认。",
                "device_id": "rdk-x5",
                "location": "RDK 监控区域",
                "confidence": confidence,
                "dedupe_key": f"rdk-{alert}-{uuid.uuid4().hex}",
            })
        except Exception as exc:  # 事件写入失败不阻断监控代理
            print(f"[EVENT] unable to record RDK alert: {exc}")
            return
        CURRENT_RDK_ALERT = alert
        if data.get("snapshot_available") is not False:
            try:
                capture_event_snapshot(result["event"]["id"])
            except (OSError, ValueError, HTTPException) as exc:
                print(f"[EVENT] snapshot unavailable: {type(exc).__name__}")


def local_today() -> str:
    return datetime.now(timezone(timedelta(hours=8))).date().isoformat()


def health_classes_from(students: list[dict]) -> list[dict]:
    classes = {item["id"]: {"id": item["id"], "name": item["name"]} for item in DEFAULT_HEALTH_CLASSES}
    for student in students:
        class_id = student.get("class_id", "")
        if not class_id:
            continue
        class_name = student.get("class_name") or class_id
        if class_id not in classes:
            classes[class_id] = {"id": class_id, "name": class_name}
        elif classes[class_id].get("name") in ("", class_id):
            classes[class_id]["name"] = class_name
    return list(classes.values())


def load_health_students() -> list[dict]:
    data = read_json_file(HEALTH_STUDENTS_FILE, [])
    if not isinstance(data, list):
        return []
    result = []
    for raw in data:
        if not isinstance(raw, dict):
            continue
        try:
            student_id = text_value(raw.get("id"), "id", 20, required=True)
            if not re.fullmatch(r"[A-Za-z0-9-]{3,20}", student_id):
                continue
            name = text_value(raw.get("name"), "name", 20, required=True)
            class_id = text_value(raw.get("class_id"), "class_id", 64, required=True)
            class_name = text_value(raw.get("class_name"), "class_name", 80, default="")
            active = raw.get("active", True)
            student = {
                "id": student_id,
                "name": name,
                "class_id": class_id,
                "class_name": class_name or class_id,
                "active": active if isinstance(active, bool) else True,
            }
            nickname = raw.get("nickname")
            if isinstance(nickname, str) and 1 <= len(nickname.strip()) <= 20:
                student["nickname"] = nickname.strip()
            result.append(student)
        except (ValueError, TypeError):
            continue
    return result


def load_health_records() -> list[dict]:
    data = read_json_file(HEALTH_RECORDS_FILE, [])
    if not isinstance(data, list):
        return []
    result = []
    for raw in data:
        if not isinstance(raw, dict):
            continue
        try:
            record_id = text_value(raw.get("id"), "id", 80, required=True)
            student_id = text_value(raw.get("student_id"), "student_id", 20, required=True)
            measured_at = normalize_iso(raw.get("measured_at"), "measured_at")
            raw_temperature = raw.get("temperature_c")
            if isinstance(raw_temperature, bool):
                continue
            temperature = float(raw_temperature)
            source = text_value(raw.get("source"), "source", 20, required=True)
            if source not in HEALTH_SOURCES:
                continue
            if not math.isfinite(temperature) or (source != "infrared" and not 35 <= temperature <= 42):
                continue
            note = text_value(raw.get("note"), "note", 50, default="")
            recheck_of = text_value(raw.get("recheck_of"), "recheck_of", 80, default="") or None
            device_id = text_value(raw.get("device_id"), "device_id", 160, default="")
            reading_id = text_value(raw.get("reading_id"), "reading_id", 160, default="")
            origin = text_value(raw.get("origin"), "origin", 20, default="manual")
            if origin not in ("manual", "device"):
                origin = "manual"
            dedupe_key = text_value(raw.get("dedupe_key"), "dedupe_key", 160, default="")
            ambient = raw.get("ambient_c")
            if ambient not in (None, ""):
                try:
                    ambient = round(float(ambient), 1)
                except (TypeError, ValueError):
                    ambient = None
            else:
                ambient = None
            result.append({
                "id": record_id,
                "student_id": student_id,
                "measured_at": measured_at,
                "temperature_c": round(temperature, 1),
                "source": source,
                "note": note,
                "recheck_of": recheck_of,
                "device_id": device_id,
                "reading_id": reading_id,
                "origin": origin,
                "dedupe_key": dedupe_key,
                "ambient_c": ambient,
            })
        except (ValueError, TypeError, OverflowError):
            continue
    return result


def save_health_students() -> None:
    atomic_write_json(HEALTH_STUDENTS_FILE, HEALTH_STUDENTS)


def save_health_records() -> None:
    atomic_write_json(HEALTH_RECORDS_FILE, HEALTH_RECORDS)


def reload_health() -> None:
    students = load_health_students()
    records = load_health_records()
    with HEALTH_LOCK:
        HEALTH_STUDENTS[:] = students
        HEALTH_RECORDS[:] = records


def health_student_snapshot() -> list[dict]:
    with HEALTH_LOCK:
        return [dict(item) for item in HEALTH_STUDENTS]


def health_record_snapshot() -> list[dict]:
    with HEALTH_LOCK:
        return [dict(item) for item in HEALTH_RECORDS]


def health_classes_payload() -> list[dict]:
    return health_classes_from(health_student_snapshot())


def health_students_payload() -> dict:
    return {
        "students": health_student_snapshot(),
        "classes": health_classes_payload(),
        "generated_at": now_iso(),
    }


def update_student_nickname(student_id, nickname) -> dict:
    nickname = text_value(nickname, "昵称", 20)
    with HEALTH_LOCK:
        index = next((i for i, student in enumerate(HEALTH_STUDENTS) if student["id"] == student_id), None)
        if index is None:
            raise ValueError("学生不在当前名单")
        student = {**HEALTH_STUDENTS[index], "nickname": nickname}
        updated = HEALTH_STUDENTS.copy()
        updated[index] = student
        atomic_write_json(HEALTH_STUDENTS_FILE, updated)
        HEALTH_STUDENTS[index] = student
        return student


def validate_bound_students(bound, students: dict) -> list[str]:
    if not isinstance(bound, list) or any(not isinstance(item, str) for item in bound):
        raise ValueError("请选择名单中的学生")
    bound = [item.strip() for item in bound]
    if any(item not in students or not students[item].get("active", True) for item in bound):
        raise ValueError("学生不在当前有效名单")
    return bound


def create_or_update_parent(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("request must be an object")
    username = payload.get("username")
    password = payload.get("password")
    bound = payload.get("student_ids")
    if not isinstance(username, str):
        raise ValueError("username is required")
    username = unicodedata.normalize("NFKC", username).strip()
    bound = validate_bound_students(bound, {item["id"]: item for item in health_student_snapshot()})
    existing = next(
        (
            item for item in AUTH.list_parents()
            if item["username"].casefold() == username.strip().casefold()
        ),
        None,
    )
    if existing:
        return AUTH.update_parent_bindings(existing["username"], bound, payload.get("access"))
    if not isinstance(password, str):
        raise ValueError("password is required for a new parent account")
    AUTH.create_user(
        username,
        password,
        role="parent",
        bound_student_ids=bound,
        access=payload.get("access"),
    )
    return next(
        item for item in AUTH.list_parents()
        if item["username"].casefold() == username.strip().casefold()
    )


def person_types_payload() -> dict:
    return PERSON_TYPE_RUNTIME.status()


def validate_date(value: str | None) -> str:
    value = (value or "").strip() or local_today()
    try:
        day = datetime.strptime(value, "%Y-%m-%d").date()
        if day.year < 2:
            raise ValueError("date out of range")
    except ValueError as exc:
        raise ValueError("invalid date") from exc
    return day.isoformat()


def query_health_records(params: dict) -> dict:
    date = validate_date((params.get("date") or [None])[-1])
    class_id = ((params.get("class_id") or [""])[-1]).strip()
    student_id = ((params.get("student_id") or [""])[-1]).strip()
    students = {item["id"]: item for item in health_student_snapshot()}
    records = []
    for record in health_record_snapshot():
        if date_key(record["measured_at"]) != date:
            continue
        student = students.get(record["student_id"])
        if class_id and (not student or student.get("class_id") != class_id):
            continue
        if student_id and record["student_id"] != student_id:
            continue
        records.append(record)
    records.sort(key=lambda item: item["measured_at"])
    return {
        "date": date,
        "records": records,
        "sources": [{"value": key, "label": HEALTH_SOURCE_LABELS[key]} for key in HEALTH_SOURCES],
    }


def create_health_record(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("request must be an object")
    student_id = text_value(payload.get("student_id"), "student_id", 20, required=True)
    students = {item["id"]: item for item in health_student_snapshot()}
    student = students.get(student_id)
    if student is None:
        raise LookupError("student not found")
    raw_temperature = payload.get("temperature_c")
    if isinstance(raw_temperature, bool):
        raise ValueError("invalid temperature")
    try:
        temperature = float(raw_temperature)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("invalid temperature") from exc
    if not math.isfinite(temperature):
        raise ValueError("invalid temperature")
    source = text_value(payload.get("source"), "source", 20, required=True)
    if source not in HEALTH_SOURCES:
        raise ValueError("invalid source")
    if source != "infrared" and not 35 <= temperature <= 42:
        raise ValueError("temperature must be between 35.0 and 42.0")
    note = text_value(payload.get("note"), "note", 50, default="")
    recheck_of = text_value(payload.get("recheck_of"), "recheck_of", 80, default="") or None
    with HEALTH_LOCK:
        if recheck_of:
            original = next((item for item in HEALTH_RECORDS if item["id"] == recheck_of), None)
            if original is None or original["student_id"] != student_id:
                raise ValueError("invalid recheck relationship")
        record = {
            "id": f"R-{uuid.uuid4().hex[:10].upper()}",
            "student_id": student_id,
            "measured_at": now_iso(),
            "temperature_c": round(temperature, 1),
            "source": source,
            "note": note,
            "recheck_of": recheck_of,
            "device_id": "",
            "reading_id": "",
            "origin": "manual",
            "dedupe_key": "",
            "ambient_c": None,
        }
        HEALTH_RECORDS.append(record)
        save_health_records()
        return dict(record)


def process_infrared_reading(reading: dict, *, persist: bool = False) -> dict:
    result = {"stored": False, "duplicate": False, "reason": reading["status"], "reading": reading, "record": None}
    if reading["status"] != "ready":
        return result
    with HEALTH_LOCK:
        if not any(item["id"] == reading["student_id"] for item in HEALTH_STUDENTS):
            reading["student_known"] = False
            result["reason"] = "unknown_student"
            return result
        reading["student_known"] = True
        identity = (reading["device_id"], reading["reading_id"])
        digest = hashlib.sha256(json.dumps(identity, ensure_ascii=False).encode("utf-8")).hexdigest()
        dedupe_key = f"infrared:{digest}"
        duplicate = next(
            (item for item in HEALTH_RECORDS
             if (item.get("device_id"), item.get("reading_id")) == identity),
            None,
        )
        if duplicate is not None:
            result.update(duplicate=True, reason="duplicate", record=dict(duplicate))
            return result
        if not persist:
            return result
        if reading["connected"] is not True or reading["stable"] is not True:
            result["reason"] = "stability_unknown" if reading["connected"] is True else "connection_unknown"
            return result
        record = {
            "id": f"R-{uuid.uuid4().hex[:10].upper()}",
            "student_id": reading["student_id"],
            "measured_at": reading["measured_at"],
            "temperature_c": reading["temperature_c"],
            "source": "infrared",
            "note": "红外设备自动采集",
            "recheck_of": None,
            "device_id": reading["device_id"],
            "reading_id": reading["reading_id"],
            "origin": "device",
            "dedupe_key": dedupe_key,
            "ambient_c": reading["ambient_c"],
        }
        updated = [*HEALTH_RECORDS, record]
        atomic_write_json(HEALTH_RECORDS_FILE, updated)
        HEALTH_RECORDS[:] = updated
        result.update(stored=True, reason="stored", record=dict(record))
        return result


def ingest_infrared_reading(payload: dict) -> dict:
    global HEALTH_LAST_INFRARED
    reading = normalize_infrared_payload(payload, stale_after_seconds=HEALTH_INFRARED_STALE_SECONDS)
    reading["received_at"] = now_iso()
    result = process_infrared_reading(reading, persist=True)
    with HEALTH_REALTIME_LOCK:
        HEALTH_LAST_INFRARED = dict(reading)
    return result


def live_infrared_payload() -> dict:
    """Read RDK or a recent device push without writing health records."""
    with HEALTH_REALTIME_LOCK:
        cached = dict(HEALTH_LAST_INFRARED) if HEALTH_LAST_INFRARED else None
    reading = None
    sensor_error = None
    try:
        raw = read_rdk_json("/api/iot_payload")
        reading = normalize_infrared_payload(
            raw, stale_after_seconds=HEALTH_INFRARED_STALE_SECONDS, allow_raw_temperature=True,
        )
    except (OSError, ValueError, HTTPException):
        sensor_error = "RDK 传感器接口暂时不可用"
    if cached:
        cached = refresh_infrared_status(
            cached, stale_after_seconds=HEALTH_INFRARED_STALE_SECONDS, allow_raw_temperature=True,
        )
        if not reading or (cached["fresh"] and (
            not reading["fresh"] or cached["measured_at"] >= reading["measured_at"]
        )):
            reading = cached
    result = process_infrared_reading(reading) if reading else None
    return {
        "ok": True,
        "source_available": sensor_error is None,
        "sensor_error": sensor_error,
        "reading": reading,
        "ingest": {key: result[key] for key in ("stored", "duplicate", "reason", "record")} if result else None,
        "stale_after_seconds": HEALTH_INFRARED_STALE_SECONDS,
    }


def import_health_students(payload: dict) -> dict:
    if not isinstance(payload, dict) or not isinstance(payload.get("students"), list):
        raise ValueError("students must be a list")
    incoming = payload["students"]
    if len(incoming) > 500:
        raise ValueError("too many students")
    classes = health_classes_payload()
    class_by_id = {item["id"]: item["name"] for item in classes}
    class_by_name = {item["name"]: item["id"] for item in classes}
    imported = 0
    skipped = 0
    errors = []
    seen = set()
    with HEALTH_LOCK:
        existing = {item["id"] for item in HEALTH_STUDENTS}
        for index, raw in enumerate(incoming):
            line = raw.get("line") if isinstance(raw, dict) else index + 2
            line = line if isinstance(line, int) and line > 0 else index + 2
            original = raw.get("raw") if isinstance(raw, dict) else ""
            try:
                if not isinstance(raw, dict):
                    raise ValueError("学生记录必须是对象")
                student_id = text_value(raw.get("id"), "id", 20, required=True)
                if not re.fullmatch(r"[A-Za-z0-9-]{3,20}", student_id):
                    raise ValueError("学号格式错误")
                if student_id in existing or student_id in seen:
                    skipped += 1
                    continue
                name = text_value(raw.get("name"), "name", 20, required=True)
                class_id = text_value(raw.get("class_id"), "class_id", 64, default="")
                class_name = text_value(raw.get("class_name"), "class_name", 80, default="")
                if class_id and class_id not in class_by_id and not class_name:
                    raise ValueError("班级不存在")
                if not class_id and class_name:
                    class_id = class_by_name.get(class_name, "")
                if not class_id:
                    raise ValueError("班级不存在")
                if class_id not in class_by_id:
                    class_by_id[class_id] = class_name or class_id
                seen.add(student_id)
                HEALTH_STUDENTS.append({
                    "id": student_id,
                    "name": name,
                    "class_id": class_id,
                    "class_name": class_by_id[class_id],
                    "active": True,
                })
                imported += 1
            except (ValueError, TypeError) as exc:
                errors.append({
                    "line": line,
                    "reason": str(exc),
                    "raw": original if isinstance(original, str) else "",
                })
        if imported:
            save_health_students()
    return {"imported": imported, "skipped": skipped, "errors": errors}


def dialogue_attention_items(date: str, class_id: str, students: dict[str, dict]) -> list[dict]:
    with MESSAGES_LOCK:
        messages = [dict(item) for item in MESSAGES]
    grouped = {}
    for message in messages:
        if message.get("role") != "user":
            continue
        timestamp = message.get("created_at") or message.get("received_at")
        try:
            if date_key(timestamp) != date:
                continue
        except (ValueError, TypeError):
            continue
        attention = ((message.get("emotion") or {}).get("attention") or "none")
        if attention not in ("watch", "urgent"):
            continue
        message_class = message.get("class_id") or ""
        if class_id and message_class != class_id:
            continue
        session_id = message.get("session_id") or message.get("device_id") or message.get("id")
        candidate = {
            "id": message.get("id") or session_id,
            "student_id": message.get("student_id") or "",
            "student_name": "",
            "class_id": message_class,
            "attention": attention,
            "reason": (message.get("emotion") or {}).get("attention_reason") or "文本关注线索",
            "excerpt": str(message.get("text") or "")[:120],
            "last_at": timestamp,
        }
        previous = grouped.get(session_id)
        if previous is None or str(candidate["last_at"]) >= str(previous["last_at"]):
            grouped[session_id] = candidate
    result = []
    for item in grouped.values():
        student = students.get(item["student_id"])
        if student:
            item["student_name"] = student["name"]
        result.append(item)
    result.sort(key=lambda item: item.get("last_at", ""), reverse=True)
    return result


def family_daily_report(params: dict, user: dict) -> dict:
    date = validate_date((params.get("date") or [None])[-1])
    student_id = (params.get("student_id") or [""])[-1]
    if student_id not in user["student_ids"]:
        raise PermissionError("只能查询绑定学生的日报")
    readings = [
        {"measured_at": record["measured_at"], "temperature_c": record["temperature_c"]}
        for record in health_record_snapshot()
        if record["student_id"] == student_id and date_key(record["measured_at"]) == date
    ]
    dialogues = []
    if user["access"]["dialogues"]:
        with MESSAGES_LOCK:
            messages = list(MESSAGES)
        for message in messages:
            if message.get("family_student_id") != student_id:
                continue
            try:
                timestamp = normalize_iso(message.get("created_at") or message.get("received_at"))
            except ValueError:
                continue
            if date_key(timestamp) == date and message.get("role") in ("user", "assistant") and isinstance(message.get("text"), str):
                dialogues.append({"role": message["role"], "text": message["text"], "at": timestamp})
    events = []
    if user["access"]["events"]:
        nicknames = student_nicknames()
        for event in events_snapshot():
            if date_key(event["occurred_at"]) == date:
                visible = family_event_view(event, {student_id}, nicknames, snapshots=user["access"]["snapshots"])
                if visible is not None:
                    events.append(visible)
    return {
        "date": date,
        "readings": sorted(readings, key=lambda item: item["measured_at"]),
        "dialogues": sorted(dialogues, key=lambda item: item["at"]),
        "events": sorted(events, key=lambda item: item["occurred_at"]),
    }


def temperature_trend(date: str, records: list[dict], student_ids: set[str]) -> list[dict]:
    end = datetime.fromisoformat(date).date()
    days = {(end - timedelta(days=offset)).isoformat(): {} for offset in range(6, -1, -1)}
    for record in sorted(records, key=lambda item: item["measured_at"]):
        if record["student_id"] in student_ids:
            day = days.get(date_key(record["measured_at"]))
            if day is not None:
                day[record["student_id"]] = record["temperature_c"]
    return [
        {"date": day, "mean_c": round(sum(values.values()) / len(values), 2) if values else None,
         "count": len(values)}
        for day, values in days.items()
    ]


def build_daily_report(params: dict) -> dict:
    date = validate_date((params.get("date") or [None])[-1])
    class_id = ((params.get("class_id") or [""])[-1]).strip()
    students = health_student_snapshot()
    all_classes = health_classes_payload()
    class_names = {item["id"]: item["name"] for item in all_classes}
    active_students = [item for item in students if item.get("active", True)]
    if class_id:
        active_students = [item for item in active_students if item.get("class_id") == class_id]
    records = health_record_snapshot()
    records_by_student = {}
    for record in records:
        if date_key(record["measured_at"]) == date:
            records_by_student.setdefault(record["student_id"], []).append(record)
    for items in records_by_student.values():
        items.sort(key=lambda item: item["measured_at"])

    classes = []
    total = measured = pending = recheck = 0
    for klass in all_classes:
        if class_id and klass["id"] != class_id:
            continue
        class_students = [item for item in active_students if item["class_id"] == klass["id"]]
        details = []
        class_counts = {"total": len(class_students), "measured": 0, "pending": 0, "recheck": 0}
        for student in sorted(class_students, key=lambda item: (item["name"], item["id"])):
            student_records = records_by_student.get(student["id"], [])
            if not student_records:
                status = "pending"
            elif float(student_records[-1]["temperature_c"]) >= 37.3:
                status = "recheck"
            else:
                status = "measured"
            class_counts[status] += 1
            details.append({"id": student["id"], "name": student["name"], "status": status})
        classes.append({
            "id": klass["id"],
            "name": klass["name"],
            "total": class_counts["total"],
            "measured": class_counts["measured"],
            "pending": class_counts["pending"],
            "recheck": class_counts["recheck"],
            "students": details,
        })
        total += class_counts["total"]
        measured += class_counts["measured"]
        pending += class_counts["pending"]
        recheck += class_counts["recheck"]

    student_map = {item["id"]: item for item in students}
    events = []
    for event in events_snapshot():
        if date_key(event["occurred_at"]) != date:
            continue
        if class_id:
            event_class = event.get("class_id")
            if event_class:
                if event_class != class_id:
                    continue
            elif not any(
                student_map.get(person["student_id"], {}).get("class_id") == class_id
                for person in event.get("participants", [])
            ):
                continue
        events.append(event_for_report(event))
    events.sort(key=lambda item: item["occurred_at"], reverse=True)

    dialogues = dialogue_attention_items(date, class_id, student_map)
    return {
        "report": {
            "date": date,
            "timezone": "Asia/Shanghai",
            "generated_at": now_iso(),
            "events": events,
            "dialogues": dialogues,
            "health": {
                "total": total,
                "measured": measured,
                "pending": pending,
                "recheck": recheck,
                "classes": classes,
                "temperature_trend": temperature_trend(date, records, {item["id"] for item in active_students}),
            },
        }
    }


def validate_dialogue_config(data: dict) -> dict:
    if not isinstance(data, dict):
        raise ValueError("Configuration must be an object")
    allowed = set(DEFAULT_DIALOGUE_CONFIG)
    if set(data) - allowed:
        raise ValueError("Unknown configuration field")

    result = DEFAULT_DIALOGUE_CONFIG.copy()
    result.update(data)
    title = result.get("title")
    if not isinstance(title, str) or not title.strip() or len(title.strip()) > 40:
        raise ValueError("Invalid title")
    result["title"] = title.strip()
    if result.get("refresh_seconds") not in (1, 2, 3, 5, 10):
        raise ValueError("Invalid refresh interval")
    if result.get("page_size") not in (20, 50, 100, 200):
        raise ValueError("Invalid page size")
    for key in ("show_session_id", "show_created_at", "auto_scroll"):
        if not isinstance(result.get(key), bool):
            raise ValueError(f"Invalid {key}")
    return result


def load_dialogue_config() -> dict:
    data = read_json_file(DIALOGUE_CONFIG_FILE, {})
    try:
        return validate_dialogue_config(data)
    except ValueError:
        return DEFAULT_DIALOGUE_CONFIG.copy()


def load_analysis_config() -> dict:
    data = read_json_file(ANALYSIS_CONFIG_FILE, {})
    try:
        config = validate_analysis_config(data)
    except ValueError:
        config = DEFAULT_ANALYSIS_CONFIG.copy()
    # The page exposes one real dialogue model. Background summaries and model
    # emotion analysis always reuse that model; only the emotion mode is user-selectable.
    config["summary_enabled"] = True
    config["summary_model_source"] = "xiaozhi"
    config["emotion_model_source"] = "shared"
    return config


def load_summaries() -> dict:
    data = read_json_file(CONVERSATION_SUMMARIES_FILE, {})
    return data if isinstance(data, dict) else {}


MESSAGES = load_messages()
DIALOGUE_CONFIG = load_dialogue_config()
ANALYSIS_CONFIG = load_analysis_config()
CONVERSATION_SUMMARIES = load_summaries()
EMOTION_LEXICON = load_lexicon(EMOTION_LEXICON_FILE)
EVENTS = load_events()
HEALTH_STUDENTS = load_health_students()
HEALTH_RECORDS = load_health_records()


def messages_for_session(session_id: str) -> list[dict]:
    with MESSAGES_LOCK:
        return [dict(item) for item in MESSAGES if item.get("session_id") == session_id]


def conversation_items() -> list[dict]:
    with MESSAGES_LOCK:
        snapshot = [dict(item) for item in MESSAGES]
    grouped = {}
    for item in snapshot:
        grouped.setdefault(item.get("session_id") or "unknown", []).append(item)
    with SUMMARIES_LOCK:
        saved = {key: dict(value) for key, value in CONVERSATION_SUMMARIES.items() if isinstance(value, dict)}
    result = []
    for session_id, messages in grouped.items():
        local = local_conversation_summary(messages, session_id)
        item = saved.get(session_id) if saved.get(session_id, {}).get("message_count") == len(messages) else local
        item = dict(item)
        item["last_message_at"] = messages[-1].get("received_at", messages[-1].get("created_at", ""))
        result.append(item)
    return sorted(
        result,
        key=lambda item: (ATTENTION_ORDER.get(item.get("attention", "none"), 0), item.get("last_message_at", "")),
        reverse=True,
    )


def save_summaries() -> None:
    atomic_write_json(CONVERSATION_SUMMARIES_FILE, CONVERSATION_SUMMARIES)


def delete_dialogue_records(payload: dict) -> int:
    clear_all = set(payload) == {"scope", "confirm"} and payload["scope"] == "all" and payload["confirm"] is True
    ids = payload.get("ids")
    if not clear_all and (
        set(payload) != {"ids"} or not isinstance(ids, list) or not 1 <= len(ids) <= DIALOGUE_LIMIT
        or any(not isinstance(value, str) or not 1 <= len(value) <= 64 for value in ids)
    ):
        raise ValueError("请选择要删除的会话，或确认清空全部对话。")
    selected = set() if clear_all else set(ids)
    with MESSAGES_LOCK, SUMMARIES_LOCK:
        removed = [item for item in MESSAGES if clear_all or item.get("id") in selected]
        remaining = [item for item in MESSAGES if not clear_all and item.get("id") not in selected]
        sessions = {item.get("session_id") for item in removed}
        summaries = {} if clear_all else {
            key: value for key, value in CONVERSATION_SUMMARIES.items() if key not in sessions
        }
        if summaries != CONVERSATION_SUMMARIES:
            atomic_write_json(CONVERSATION_SUMMARIES_FILE, summaries)
            CONVERSATION_SUMMARIES.clear()
            CONVERSATION_SUMMARIES.update(summaries)
        if removed:
            atomic_write_json(DIALOGUE_DATA_FILE, remaining)
            MESSAGES.clear()
            MESSAGES.extend(remaining)
    return len(removed)


def enqueue_analysis(kind: str, value: str) -> None:
    if not ANALYSIS_WORKER_STARTED:
        return
    try:
        ANALYSIS_QUEUE.put_nowait((kind, value))
    except queue.Full:
        pass


def schedule_summary(session_id: str) -> None:
    if not ANALYSIS_WORKER_STARTED or not session_id:
        return
    with SUMMARY_TIMERS_LOCK:
        previous = SUMMARY_TIMERS.pop(session_id, None)
        if previous:
            previous.cancel()
        timer = threading.Timer(1.5, lambda: enqueue_analysis("summary", session_id))
        timer.daemon = True
        SUMMARY_TIMERS[session_id] = timer
        timer.start()


def analysis_worker() -> None:
    while True:
        kind, value = ANALYSIS_QUEUE.get()
        try:
            with ANALYSIS_CONFIG_LOCK:
                config = ANALYSIS_CONFIG.copy()
            if kind == "emotion":
                with MESSAGES_LOCK:
                    message = next((dict(item) for item in MESSAGES if item.get("id") == value), None)
                if message and message.get("role") == "user":
                    result = analyze_emotion(message.get("text", ""), config, EMOTION_LEXICON, PROJECT_ROOT)
                    with MESSAGES_LOCK:
                        target = next((item for item in MESSAGES if item.get("id") == value), None)
                        if target:
                            target["emotion"] = result
                            save_messages()
            elif kind == "summary":
                messages = messages_for_session(value)
                if messages:
                    result = summarize_conversation(messages, value, config, PROJECT_ROOT)
                    with MESSAGES_LOCK, SUMMARIES_LOCK:
                        current_ids = [item.get("id") for item in MESSAGES if item.get("session_id") == value]
                        if current_ids == [item.get("id") for item in messages]:
                            CONVERSATION_SUMMARIES[value] = result
                            save_summaries()
            elif kind == "rebuild":
                with MESSAGES_LOCK:
                    snapshot = list(MESSAGES)
                for item in snapshot:
                    if item.get("role") == "user":
                        enqueue_analysis("emotion", item.get("id", ""))
                for session_id in {item.get("session_id") for item in snapshot if item.get("session_id")}:
                    enqueue_analysis("summary", session_id)
        except Exception as exc:
            print(f"[ANALYSIS] {kind} failed: {type(exc).__name__}")
        finally:
            ANALYSIS_QUEUE.task_done()


def start_analysis_worker() -> None:
    global ANALYSIS_WORKER_STARTED
    if ANALYSIS_WORKER_STARTED:
        return
    ANALYSIS_WORKER_STARTED = True
    changed = False
    retry_ids = []
    sessions = set()
    with MESSAGES_LOCK:
        for item in MESSAGES:
            if not isinstance(item.get("emotion"), dict):
                item["emotion"] = analyze_lexicon(item.get("text", ""), EMOTION_LEXICON)
                if item.get("role") != "user":
                    item["emotion"]["attention"] = "none"
                    item["emotion"]["attention_reason"] = "助手回复不参与用户留意判断"
                changed = True
            elif item.get("role") == "user" and item["emotion"].get("source") in {"lexicon-fallback", "lexicon-no-model"}:
                retry_ids.append(item.get("id", ""))
            if item.get("session_id"):
                sessions.add(item["session_id"])
        if changed:
            save_messages()
    threading.Thread(target=analysis_worker, name="dialogue-analysis", daemon=True).start()
    for message_id in retry_ids[-20:]:
        enqueue_analysis("emotion", message_id)
    with SUMMARIES_LOCK:
        summarized_sessions = set(CONVERSATION_SUMMARIES)
    for session_id in sessions - summarized_sessions:
        enqueue_analysis("summary", session_id)


def read_rdk_json(path: str) -> dict:
    request = urllib.request.Request(
        RDK_BASE + path,
        headers={"Accept": "application/json", "User-Agent": "TongyuDashboard/1.0"},
    )
    with urllib.request.urlopen(request, timeout=3) as response:
        return json.loads(response.read().decode("utf-8"))


def merchant_sensors() -> dict:
    data = read_rdk_json("/api/iot_payload")
    if not isinstance(data, dict):
        raise ValueError("invalid sensor payload")
    sensor = data.get("sensor")
    sensor = sensor if isinstance(sensor, dict) else data
    properties = data.get("properties", sensor.get("properties", sensor))
    properties = properties if isinstance(properties, dict) else data
    readings = {}
    for key in ("eco2", "tvoc", "sht_t", "sht_h", "mlx_amb"):
        try:
            raw = data.get(key, properties.get(key))
            if type(raw) not in (str, int, float):
                continue
            value = float(raw)
            if math.isfinite(value):
                readings[key] = value
        except (ValueError, OverflowError):
            pass
    timestamp = None
    raw = data.get("timestamp") or properties.get("timestamp")
    if isinstance(raw, str):
        try:
            timestamp = normalize_iso(raw)
        except ValueError:
            pass
    return {"readings": readings, "timestamp": timestamp}


class Handler(BaseHTTPRequestHandler):
    server_version = "TongyuDashboard/1.0"

    def log_message(self, fmt: str, *args) -> None:
        # Do not log query strings, bodies, cookies or authorization headers.
        print(f"[HTTP] {self.command} {urlparse(self.path).path} {args[1] if len(args) > 1 else ''}")

    def security_headers(self):
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "same-origin")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy", "frame-ancestors 'none'; base-uri 'self'; form-action 'self'")
        cookie = getattr(self, "response_cookie", None)
        if cookie:
            self.send_header("Set-Cookie", cookie)
            self.response_cookie = None

    def send_bytes(self, status: int, content_type: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.security_headers()
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, status: int, data: dict) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_bytes(status, "application/json; charset=utf-8", body)

    def serve_index(self) -> None:
        self.serve_html("index.html")

    def token(self):
        try:
            cookie = SimpleCookie()
            cookie.load(self.headers.get("Cookie", ""))
            return cookie[COOKIE_NAME].value if COOKIE_NAME in cookie else ""
        except CookieError:
            return ""

    def current_session(self, *, touch=True):
        return AUTH.session(self.token(), touch=touch)

    def same_origin(self):
        host = self.headers.get("Host", "")
        origin = self.headers.get("Origin")
        if self.headers.get("Sec-Fetch-Site") == "cross-site":
            return False
        if not origin:
            return True
        try:
            parsed = urlparse(origin)
            return (parsed.netloc == host and parsed.path in ("", "/")
                    and (parsed.scheme == "https" or (parsed.scheme == "http"
                         and (not AUTH.secure or parsed.hostname in ("localhost", "127.0.0.1", "::1")))))
        except ValueError:
            return False

    def serve_html(self, filename, status=200):
        session = self.current_session()
        user = AUTH.public_user(session)
        policy = AUTH.get_policy() if user else None
        permissions = ({"modules": dict.fromkeys(MODULES, True), "video": True, "dialogue_raw": True}
                       if user and user["role"] == "admin" else policy)
        if user and user["role"] in ("parent", "merchant", "pending"):
            permissions = {
                "modules": dict.fromkeys(MODULES, False),
                "video": False,
                "dialogue_raw": False,
            }
        bootstrap = json.dumps({"user": user, "policy": policy, "permissions": permissions,
                                "csrf": session["csrf"] if session else None}, ensure_ascii=True).replace("<", "\\u003c")
        source = (ROOT / filename).read_text(encoding="utf-8")
        source = source.replace("</head>", '<link rel="stylesheet" href="/access.css">'
                                '<script>window.TongyuBootstrap=' + bootstrap + ';</script>'
                                '<script src="/access.js"></script></head>', 1)
        if filename == "index.html" and not AUTH.permitted(session, "video"):
            source = source.replace('src="/api/rdk/video_feed"', '')
        self.send_bytes(status, "text/html; charset=utf-8", source.encode("utf-8"))

    def redirect(self, location):
        self.send_response(303)
        self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        self.security_headers()
        self.end_headers()

    def deny(self, path, status, error):
        if path in PAGE_ROUTES:
            if status == 401:
                self.redirect("/login?next=" + quote(path, safe=""))
            else:
                self.serve_html("unavailable.html", status)
        else:
            self.send_json(status, {"ok": False, "error": error})
        return False

    def require_session(self, path, *, admin=False, write=False):
        session = self.current_session()
        user = AUTH.public_user(session)
        if not user:
            return self.deny(path, 401, "请先登录")
        if not self.same_origin():
            return self.deny(path, 403, "请求来源不匹配")
        if user["role"] == "parent":
            allowed = {"/welcome", "/family-events.html", "/api/family/students"}
            if user["access"]["reports"]:
                allowed.add("/api/family/daily")
            if user["access"]["events"] and (path == "/api/family/events" or path.startswith("/api/family/events/")):
                allowed.add(path)
            if path not in allowed:
                return self.deny(path, 403, "此内容未向该家长账号开放")
        if user["role"] == "merchant" and path not in ("/welcome", "/sensors.html", "/api/merchant/sensors"):
            return self.deny(path, 403, "商家账号仅可查看环境传感器数据")
        if user["role"] == "pending" and path != "/welcome":
            return self.deny(path, 403, "请等待管理员分配账号角色")
        if admin and user["role"] != "admin":
            return self.deny(path, 403, "此操作仅限管理员")
        module = route_module(path)
        if module and module != "admin" and not AUTH.permitted(session, module):
            return self.deny(path, 403, "管理员尚未开放此模块")
        if write and not self.valid_csrf(session):
            return self.deny(path, 403, "页面验证已失效，请刷新后重试")
        return True

    def valid_csrf(self, session):
        supplied = self.headers.get("X-CSRF-Token", "")
        return bool(session and hmac.compare_digest(supplied.encode(), session["csrf"].encode()))

    def require_local_ingest(self) -> bool:
        # A tunnel's socket is also loopback: reject forwarded requests and public
        # Host values rather than treating every loopback connection as trusted.
        host = urlparse('http://' + self.headers.get('Host', '')).hostname
        origin = self.headers.get('Origin')
        if (self.client_address[0] not in ('127.0.0.1', '::1')
                or host not in ('localhost', '127.0.0.1', '::1')
                or (origin and origin != 'http://' + self.headers.get('Host', ''))
                or any(self.headers.get(h) is not None for h in ('Forwarded', 'X-Forwarded-For', 'X-Forwarded-Host', 'X-Forwarded-Proto', 'CF-Connecting-IP'))
                or self.headers.get('Sec-Fetch-Site') == 'cross-site'):
            self.send_json(403, {'ok': False, 'error': '仅允许本机设备消息写入'})
            return False
        return True

    def require_health_device(self) -> bool:
        configured = HEALTH_DEVICE_TOKEN
        if len(configured) < 24:
            self.send_json(
                503,
                {
                    "ok": False,
                    "error": "health device token is not configured",
                    "detail": "请设置至少 24 位的 HEALTH_DEVICE_TOKEN 后重启 Dashboard",
                },
            )
            return False
        if AUTH.rate_limited("health-device:" + self.client_address[0], 2000, record=True):
            self.send_json(429, {"ok": False, "error": "device upload rate limited"})
            return False
        supplied = self.headers.get("X-Device-Token", "")
        if not hmac.compare_digest(supplied.encode("utf-8"), configured.encode("utf-8")):
            self.send_json(403, {"ok": False, "error": "invalid device token"})
            return False
        return True

    def auth_post(self, path, item):
        session = self.current_session()
        if not self.same_origin() or not self.valid_csrf(session):
            self.send_json(403, {"ok": False, "error": "页面验证已失效，请刷新后重试"})
            return
        if path == "/api/auth/logout":
            AUTH.revoke(self.token())
            self.response_cookie = AUTH.cookie("", clear=True)
            self.send_json(200, {"ok": True})
            return
        if not AUTH.initialized:
            self.send_json(503, {"ok": False, "error": "请先在电脑上创建管理员账号"})
            return
        username, password = item.get("username"), item.get("password")
        if path == "/api/auth/register":
            if AUTH.rate_limited("register:" + self.client_address[0], 20, record=True):
                self.send_json(429, {"ok": False, "error": "注册过于频繁，请稍后再试"})
                return
            try:
                AUTH.create_user(username, password, role="pending")
            except ValueError as exc:
                self.send_json(400, {"ok": False, "error": str(exc)})
                return
            self.send_json(201, {"ok": True})
            return
        try:
            status, username = AUTH.authenticate(username, password, self.client_address[0])
        except ValueError:
            status, username = "invalid", None
        if status != "ok":
            self.send_json(429 if status == "limited" else 401,
                           {"ok": False, "error": "尝试次数过多，请 10 分钟后再试" if status == "limited" else "用户名或密码不正确"})
            return
        AUTH.revoke(self.token())
        token, session = AUTH.new_session(username)
        self.response_cookie = AUTH.cookie(token)
        self.send_json(200, {"ok": True, "user": AUTH.public_user(session)})

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        event_match = re.fullmatch(r"/api/events/([^/]+)/(status|notes|participants)", path)
        event_request = path == "/api/events" or event_match is not None
        health_post = path in (
            "/api/health/records",
            "/api/health/import",
            "/api/health/device-readings",
        )
        try:
            length = int(self.headers.get('Content-Length', '0'))
            limit = 8192 if path in ('/api/dialogue/config', '/api/dialogue/model', '/api/analysis/config', '/api/analysis/rebuild') else 65536
            if not 0 < length <= limit:
                raise ValueError('Invalid body size')
            if self.headers.get_content_type() != 'application/json':
                raise ValueError('JSON required')
            # Consume the bounded body before rejecting a local-origin check;
            # otherwise Windows can reset the socket before the 403 is read.
            self.connection.settimeout(5)
            body = self.rfile.read(length)
            item = json.loads(body)
            if not isinstance(item, dict):
                raise ValueError('Object required')
            if path in ('/api/auth/register', '/api/auth/login', '/api/auth/logout'):
                self.auth_post(path, item)
                return
            if path == "/api/health/device-readings":
                if not self.require_health_device():
                    return
            elif path == '/api/dialogue/messages':
                if not self.require_local_ingest():
                    return
            elif not self.require_session(path, admin=True, write=True):
                return
            if path == '/api/admin/policy':
                self.send_json(200, {'ok': True, 'policy': AUTH.set_policy(item)})
                return
            if path == '/api/admin/parents':
                try:
                    parent = create_or_update_parent(item)
                    self.send_json(200, {'ok': True, 'parent': parent})
                except (ValueError, TypeError) as exc:
                    self.send_json(400, {'ok': False, 'error': str(exc)})
                return
            if path == "/api/admin/merchants":
                AUTH.create_user(item.get("username"), item.get("password"), role="merchant")
                self.send_json(201, {"ok": True})
                return
            if path in ("/api/admin/accounts", "/api/admin/student-nickname"):
                try:
                    if path == "/api/admin/accounts":
                        role = item.get("role")
                        bound = None
                        if role == "parent":
                            students = {student["id"]: student for student in health_student_snapshot()}
                            bound = validate_bound_students(item.get("student_ids"), students)
                        account = AUTH.assign_role(item.get("username"), role, bound, item.get("access"))
                        self.send_json(200, {"ok": True, "account": account})
                    else:
                        if not isinstance(item.get("nickname"), str):
                            raise ValueError("请输入昵称或留空使用姓名")
                        student = update_student_nickname(item.get("student_id"), item["nickname"])
                        self.send_json(200, {"ok": True, "student": student})
                except ValueError as exc:
                    self.send_json(400, {"ok": False, "error": str(exc)})
                return
            if path == "/api/dialogue/student":
                message_id = item.get("id")
                student_id = item.get("student_id")
                if not isinstance(message_id, str) or not isinstance(student_id, str):
                    self.send_json(400, {"ok": False, "error": "请选择消息与学生"})
                    return
                students = {student["id"]: student for student in health_student_snapshot() if student.get("active", True)}
                if student_id and student_id not in students:
                    self.send_json(400, {"ok": False, "error": "学生不在当前名单"})
                    return
                with MESSAGES_LOCK:
                    if not any(message.get("id") == message_id for message in MESSAGES):
                        self.send_json(404, {"ok": False, "error": "消息不存在"})
                        return
                    updated = [
                        {**message, "family_student_id": student_id, "student_id": student_id,
                         "class_id": students.get(student_id, {}).get("class_id", "")}
                        if message.get("id") == message_id else message for message in MESSAGES
                    ]
                    atomic_write_json(DIALOGUE_DATA_FILE, updated)
                    MESSAGES.clear()
                    MESSAGES.extend(updated)
                self.send_json(200, {"ok": True})
                return
            if path == '/api/dialogue/delete':
                try:
                    deleted = delete_dialogue_records(item)
                except ValueError as exc:
                    self.send_json(400, {'ok': False, 'error': str(exc)})
                else:
                    self.send_json(200, {'ok': True, 'deleted': deleted})
                return
            if path == '/api/rdk/person-types/settings':
                try:
                    if set(item) != {'enabled'}:
                        raise ValueError('只接受 enabled 开关')
                    result = PERSON_TYPE_RUNTIME.set_enabled(item['enabled'])
                    self.send_json(200, result)
                except ValueError as exc:
                    self.send_json(400, {'ok': False, 'error': str(exc)})
                return
            if event_request:
                try:
                    if path == "/api/events":
                        result, status = create_event(item)
                        self.send_json(status, {'ok': True, **result})
                        return
                    event_id = unquote(event_match.group(1))
                    action = event_match.group(2)
                    if action == "status":
                        result = change_event_status(event_id, item)
                    elif action == "notes":
                        result = append_event_note(event_id, item)
                    else:
                        result = assign_event_participants(event_id, item)
                    event_with_visible_evidence(result["event"], True)
                    self.send_json(200, {'ok': True, **result})
                    return
                except EventNotFound as exc:
                    self.send_json(404, {'ok': False, 'error': 'event not found', 'detail': str(exc)})
                except EventConflict as exc:
                    self.send_json(409, {'ok': False, 'error': 'invalid status transition', 'detail': str(exc)})
                except (EventValidationError, ValueError, TypeError) as exc:
                    self.send_json(400, {'ok': False, 'error': 'invalid event request', 'detail': str(exc)})
                except OSError:
                    self.send_json(500, {'ok': False, 'error': 'Unable to save event data'})
                return

            if health_post:
                try:
                    if path == "/api/health/device-readings":
                        result = ingest_infrared_reading(item)
                        self.send_json(
                            201 if result["stored"] else 200,
                            {
                                "ok": True,
                                "accepted": result["reason"]
                                not in ("offline", "unavailable", "invalid_temperature"),
                                **result,
                            },
                        )
                    elif path == "/api/health/records":
                        record = create_health_record(item)
                        self.send_json(201, {'ok': True, 'record': record})
                    else:
                        result = import_health_students(item)
                        self.send_json(200, {'ok': True, **result})
                    return
                except LookupError:
                    self.send_json(404, {'ok': False, 'error': 'student not found'})
                except (ValueError, TypeError) as exc:
                    self.send_json(400, {'ok': False, 'error': 'invalid health request', 'detail': str(exc)})
                except OSError:
                    self.send_json(500, {'ok': False, 'error': 'Unable to save health data'})
                return
            if not event_request and not health_post and path not in ('/api/dialogue/messages', '/api/dialogue/config', '/api/dialogue/model', '/api/analysis/config', '/api/analysis/rebuild'):
                self.send_json(404, {'ok': False, 'error': 'not found'})
                return

            if path == '/api/dialogue/config':
                config = validate_dialogue_config(item)
                with DIALOGUE_CONFIG_LOCK:
                    atomic_write_json(DIALOGUE_CONFIG_FILE, config)
                    DIALOGUE_CONFIG.clear()
                    DIALOGUE_CONFIG.update(config)
                self.send_json(200, {'ok': True, 'config': DIALOGUE_CONFIG.copy()})
                return

            if path == '/api/dialogue/model':
                model = update_xiaozhi_model(PROJECT_ROOT, item)
                self.send_json(200, {'ok': True, 'model': model})
                return

            if path == '/api/analysis/config':
                with ANALYSIS_CONFIG_LOCK:
                    config = validate_analysis_config(item, ANALYSIS_CONFIG)
                    config['summary_enabled'] = True
                    config['summary_model_source'] = 'xiaozhi'
                    config['emotion_model_source'] = 'shared'
                    atomic_write_json(ANALYSIS_CONFIG_FILE, config)
                    ANALYSIS_CONFIG.clear()
                    ANALYSIS_CONFIG.update(config)
                    public = public_analysis_config(config, load_xiaozhi_model(PROJECT_ROOT))
                enqueue_analysis('rebuild', 'all')
                self.send_json(200, {'ok': True, 'config': public})
                return

            if path == '/api/analysis/rebuild':
                if not isinstance(item, dict):
                    raise ValueError('Invalid rebuild request')
                enqueue_analysis('rebuild', 'all')
                self.send_json(202, {'ok': True, 'status': 'queued'})
                return

            if not isinstance(item, dict) or item.get('role') not in ('user', 'assistant'):
                raise ValueError('Invalid role')
            for key, limit in [('id', 64), ('text', 8192), ('device_id', 160), ('session_id', 160), ('created_at', 64)]:
                if not isinstance(item.get(key), str) or len(item[key]) > limit:
                    raise ValueError('Invalid message fields')
            if not item['id'] or not item['text'].strip():
                raise ValueError('Empty message')
            record = {key: item[key] for key in ('id', 'role', 'text', 'device_id', 'session_id', 'created_at')}
            record['received_at'] = datetime.now(timezone.utc).isoformat()
            record['emotion'] = analyze_lexicon(record['text'], EMOTION_LEXICON)
            if record['role'] != 'user':
                record['emotion']['attention'] = 'none'
                record['emotion']['attention_reason'] = '助手回复不参与用户留意判断'
            inserted = False
            with MESSAGES_LOCK:
                if not any(m['id'] == record['id'] for m in MESSAGES):
                    updated = [*MESSAGES, record][-DIALOGUE_LIMIT:]
                    atomic_write_json(DIALOGUE_DATA_FILE, updated)
                    MESSAGES.clear()
                    MESSAGES.extend(updated)
                    inserted = True
            if inserted:
                if record['role'] == 'user':
                    enqueue_analysis('emotion', record['id'])
                schedule_summary(record['session_id'])
            self.send_json(200, {'ok': True})
        except (ValueError, UnicodeError, TimeoutError):
            if event_request:
                error = 'Invalid event request'
            elif health_post:
                error = 'Invalid health request'
            elif path == '/api/dialogue/config':
                error = 'Invalid dialogue config'
            elif path == '/api/dialogue/model':
                error = 'Invalid dialogue model config'
            elif path == '/api/analysis/config':
                error = 'Invalid analysis config'
            elif path == '/api/analysis/rebuild':
                error = 'Invalid rebuild request'
            else:
                error = 'Invalid dialogue message'
            self.send_json(400, {'ok': False, 'error': error})
        except OSError:
            if event_request:
                self.send_json(500, {'ok': False, 'error': 'Unable to save event data'})
            elif health_post:
                self.send_json(500, {'ok': False, 'error': 'Unable to save health data'})
            else:
                self.send_json(500, {'ok': False, 'error': 'Unable to save dialogue data'})

    def proxy_json(self, upstream_path: str) -> None:
        try:
            data = read_rdk_json(upstream_path)
            if upstream_path == "/alert_status":
                record_rdk_alert(data)
            self.send_json(200, data)
        except (urllib.error.URLError, TimeoutError, ValueError, OSError) as exc:
            self.send_json(
                502,
                {
                    "ok": False,
                    "error": "RDK service unavailable",
                    "detail": str(exc),
                    "rdk_base": RDK_BASE,
                },
            )

    def proxy_video(self) -> None:
        request = urllib.request.Request(
            RDK_BASE + "/video_feed",
            headers={"Accept": "multipart/x-mixed-replace", "User-Agent": "TongyuDashboard/1.0"},
        )
        started = False
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                self.send_response(response.status)
                self.send_header(
                    "Content-Type",
                    response.headers.get("Content-Type", "multipart/x-mixed-replace; boundary=frame"),
                )
                self.security_headers()
                self.end_headers()
                started = True
                while True:
                    # Stop an existing stream after logout, expiry or revocation.
                    session = self.current_session(touch=False)
                    if not AUTH.permitted(session, "monitor") or not AUTH.permitted(session, "video"):
                        break
                    chunk = response.read1(16 * 1024)
                    if not chunk:
                        break
                    session = self.current_session(touch=False)
                    if not AUTH.permitted(session, "monitor") or not AUTH.permitted(session, "video"):
                        break
                    self.wfile.write(chunk)
                    self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            return
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            if not started and not self.wfile.closed:
                try:
                    self.send_json(502, {"ok": False, "error": str(exc)})
                except (BrokenPipeError, ConnectionResetError):
                    pass

    def serve_evidence(self, path: str) -> None:
        if not AUTH.permitted(self.current_session(), "video"):
            self.send_json(403, {"ok": False, "error": "管理员尚未开放摄像头画面"})
            return
        name = unquote(path[len("/evidence/"):])
        if not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9._-]{0,159}\.(?:png|jpe?g|webp|gif)",
            name,
            re.IGNORECASE,
        ):
            self.send_json(404, {"ok": False, "error": "evidence not found"})
            return
        base = EVIDENCE_DIR.resolve()
        candidate = (base / name).resolve()
        try:
            candidate.relative_to(base)
        except ValueError:
            self.send_json(403, {"ok": False, "error": "invalid evidence path"})
            return
        if not candidate.is_file():
            self.send_json(404, {"ok": False, "error": "evidence not found"})
            return
        if candidate.stat().st_size > 10 * 1024 * 1024:
            self.send_json(413, {"ok": False, "error": "evidence image is too large"})
            return
        content_type = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
            ".gif": "image/gif",
        }[candidate.suffix.lower()]
        self.send_bytes(200, content_type, candidate.read_bytes())

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == '/health':
            self.send_json(200, {'ok': True})
            return
        if path == '/favicon.ico':
            self.send_bytes(204, 'image/x-icon', b'')
            return
        if path in ('/login', '/login.html'):
            self.serve_html('login.html')
            return
        if path in ('/access.js', '/access.css'):
            kind = 'text/javascript' if path.endswith('.js') else 'text/css'
            self.send_bytes(200, kind + '; charset=utf-8', (ROOT / path[1:]).read_bytes())
            return
        if path == '/api/auth/session':
            if not self.same_origin():
                self.send_json(403, {'ok': False, 'error': '请求来源不匹配'})
                return
            session = self.current_session()
            if not session:
                token, session = AUTH.new_session()
                self.response_cookie = AUTH.cookie(token)
            self.send_json(200, {'user': AUTH.public_user(session), 'csrf': session['csrf'],
                                 'initialized': AUTH.initialized,
                                 'policy': AUTH.get_policy() if AUTH.public_user(session) else None})
            return
        admin = path in (
            '/admin',
            '/admin.html',
            '/api/admin/policy',
            '/api/admin/parents',
            '/api/admin/accounts',
            '/api/dialogue/model',
            '/api/analysis/config',
        )
        if not self.require_session(path, admin=admin):
            return
        if path.startswith("/api/family/"):
            user = AUTH.public_user(self.current_session())
            if not user or user["role"] not in ("parent", "admin"):
                self.send_json(403, {"ok": False, "error": "parent account required"})
                return
            if path in ("/api/family/students", "/api/family/daily"):
                if user["role"] != "parent":
                    self.send_json(403, {"ok": False, "error": "parent account required"})
                elif path == "/api/family/students":
                    students = [{"id": student["id"], "name": student.get("nickname") or student["name"]}
                                for student in health_student_snapshot() if student["id"] in user["student_ids"]]
                    self.send_json(200, {"students": students})
                else:
                    try:
                        report = family_daily_report(parse_qs(urlparse(self.path).query), user)
                        self.send_json(200, {"report": report})
                    except PermissionError as exc:
                        self.send_json(403, {"ok": False, "error": str(exc)})
                    except ValueError as exc:
                        self.send_json(400, {"ok": False, "error": str(exc)})
                return
            if user["role"] == "parent" and not user["access"]["events"]:
                self.send_json(403, {"ok": False, "error": "该账号未开放安全事件"})
                return
            if path == "/api/family/events":
                self.send_json(200, {"ok": True, **family_events_payload(user)})
                return
            snapshot_match = re.fullmatch(r"/api/family/events/([^/]+)/snapshot", path)
            if snapshot_match:
                event_id = unquote(snapshot_match.group(1))
                try:
                    event, visible = family_event_detail(user, event_id)
                    if not visible["has_snapshot"]:
                        raise EventNotFound("snapshot not found")
                    with stored_snapshot_path(event).open("rb") as stream:
                        image = stream.read(SNAPSHOT_LIMIT + 1)
                    if len(image) > SNAPSHOT_LIMIT:
                        raise EventNotFound("snapshot too large")
                    self.send_bytes(200, "image/jpeg", image)
                except EventNotFound:
                    self.send_json(404, {"ok": False, "error": "event not found"})
                except OSError:
                    self.send_json(404, {"ok": False, "error": "snapshot not found"})
                return
            event_match = re.fullmatch(r"/api/family/events/([^/]+)", path)
            if event_match:
                try:
                    _, event = family_event_detail(user, unquote(event_match.group(1)))
                    self.send_json(200, {"ok": True, "event": event})
                except EventNotFound:
                    self.send_json(404, {"ok": False, "error": "event not found"})
                return
            self.send_json(404, {"ok": False, "error": "not found"})
            return
        if path in ("/sensors.html", "/api/merchant/sensors"):
            if AUTH.public_user(self.current_session())["role"] not in ("merchant", "admin"):
                self.deny(path, 403, "此内容仅向商家与管理员开放")
                return
            if path == "/sensors.html":
                self.serve_html("sensors.html")
            else:
                try:
                    self.send_json(200, merchant_sensors())
                except (OSError, ValueError, HTTPException):
                    self.send_json(502, {"ok": False, "error": "传感器暂时无法连接"})
            return
        if path == '/api/admin/policy':
            self.send_json(200, {'policy': AUTH.get_policy()})
            return
        if path == '/api/admin/parents':
            self.send_json(200, {'parents': AUTH.list_parents()})
            return
        if path == "/api/admin/accounts":
            self.send_json(200, {"accounts": AUTH.list_accounts()})
            return
        if path in PAGE_ROUTES:
            if path == "/family-events.html":
                user = AUTH.public_user(self.current_session())
                if not user or user["role"] not in ("parent", "admin"):
                    self.deny(path, 403, "家长账号才能查看")
                    return
            self.serve_html(PAGE_ROUTES[path][0])
            return
        if path.startswith("/evidence/"):
            self.serve_evidence(path)
            return
        if path in ('/chat', '/chat.html', '/api/dialogue/messages', '/api/dialogue/config', '/api/dialogue/model', '/api/dialogue/conversations', '/api/analysis/config'):
            raw = AUTH.permitted(self.current_session(), 'dialogue_raw')
            if path == '/api/dialogue/messages':
                with MESSAGES_LOCK:
                    items = list(MESSAGES)
                self.send_json(200, {'messages': public_messages(items, raw), 'limit': DIALOGUE_LIMIT, 'raw_visible': raw})
            elif path == '/api/dialogue/config':
                with DIALOGUE_CONFIG_LOCK:
                    config = DIALOGUE_CONFIG.copy()
                self.send_json(200, {'config': config})
            elif path == '/api/dialogue/conversations':
                self.send_json(200, {'conversations': public_conversations(conversation_items(), raw)})
            elif path == '/api/dialogue/model':
                self.send_json(200, {'model': public_xiaozhi_model(PROJECT_ROOT)})
            elif path == '/api/analysis/config':
                with ANALYSIS_CONFIG_LOCK:
                    config = public_analysis_config(ANALYSIS_CONFIG.copy(), load_xiaozhi_model(PROJECT_ROOT))
                self.send_json(200, {'config': config})
            else:
                self.send_bytes(200, 'text/html; charset=utf-8', (ROOT / 'chat.html').read_bytes())
            return
        if path == "/api/events":
            try:
                result = query_events(parse_qs(urlparse(self.path).query))
                can_view = AUTH.permitted(self.current_session(), "video")
                for event in result["events"]:
                    event_with_visible_evidence(event, can_view)
                self.send_json(200, {"ok": True, **result})
            except (EventValidationError, ValueError) as exc:
                self.send_json(400, {"ok": False, "error": "invalid event query", "detail": str(exc)})
            return
        snapshot_get = re.fullmatch(r"/api/events/([^/]+)/snapshot", path)
        if snapshot_get:
            if not AUTH.permitted(self.current_session(), "video"):
                self.send_json(403, {"ok": False, "error": "管理员尚未开放摄像头画面"})
                return
            try:
                event = get_event(unquote(snapshot_get.group(1)))
                with stored_snapshot_path(event).open("rb") as stream:
                    image = stream.read(SNAPSHOT_LIMIT + 1)
                if len(image) > SNAPSHOT_LIMIT:
                    raise EventNotFound("snapshot too large")
            except (EventNotFound, OSError):
                self.send_json(404, {"ok": False, "error": "没有可用抓拍"})
                return
            self.send_bytes(200, "image/jpeg", image)
            return
        event_get = re.fullmatch(r"/api/events/([^/]+)", path)
        if event_get:
            try:
                event = get_event(unquote(event_get.group(1)))
                event_with_visible_evidence(event, AUTH.permitted(self.current_session(), "video"))
                self.send_json(200, {"ok": True, "event": event})
            except EventNotFound:
                self.send_json(404, {"ok": False, "error": "event not found"})
            return
        if path == "/api/health/students":
            self.send_json(200, {"ok": True, **health_students_payload()})
            return
        if path == "/api/health/records":
            try:
                self.send_json(200, {"ok": True, **query_health_records(parse_qs(urlparse(self.path).query))})
            except ValueError as exc:
                self.send_json(400, {"ok": False, "error": "invalid health query", "detail": str(exc)})
            return
        if path == "/api/health/realtime":
            try:
                self.send_json(200, live_infrared_payload())
            except OSError:
                self.send_json(500, {"ok": False, "error": "Unable to save health data"})
            return
        if path == "/api/reports/daily":
            try:
                payload = build_daily_report(parse_qs(urlparse(self.path).query))
                report = payload["report"]
                session = self.current_session()
                if not AUTH.permitted(session, "dialogue_raw"):
                    report["dialogues"] = [{k: v for k, v in item.items() if k not in ("excerpt", "reason", "summary", "title", "text", "attention_reason")} for item in report.get("dialogues", [])]
                if not AUTH.permitted(session, "chat"):
                    report["dialogues"] = []
                if not AUTH.permitted(session, "events"):
                    report["events"] = []
                if not AUTH.permitted(session, "health"):
                    report["health"] = {}
                self.send_json(200, {"ok": True, **payload})
            except ValueError as exc:
                self.send_json(400, {"ok": False, "error": "invalid report query", "detail": str(exc)})
            return
        if path == "/api/rdk/person-types":
            if not AUTH.permitted(self.current_session(), 'video'):
                self.send_json(403, {'ok': False, 'error': '管理员尚未开放摄像头画面'})
                return
            self.send_json(200, person_types_payload())
            return
        if path == "/api/config":
            self.send_json(200, {"rdk_base": RDK_BASE})
            return
        if path == "/api/rdk/status":
            self.proxy_json("/alert_status")
            return
        if path == "/api/rdk/sensors":
            self.proxy_json("/api/iot_payload")
            return
        if path == "/api/rdk/video_feed":
            if not AUTH.permitted(self.current_session(), 'video'):
                self.send_json(403, {'ok': False, 'error': '管理员尚未开放摄像头画面'})
                return
            self.proxy_video()
            return
        static_page = STATIC_PAGES.get(path)
        if static_page:
            self.send_bytes(200, static_page[1], (ROOT / static_page[0]).read_bytes())
            return
        self.send_json(404, {"ok": False, "error": "not found"})


def main() -> None:
    start_analysis_worker()
    print(f"Tongyu dashboard: http://127.0.0.1:{PORT}")
    print(f"RDK input: {RDK_BASE}")
    print("Dialogue emotion analysis and summaries run in the dashboard background.")
    http = ThreadingHTTPServer((HOST, PORT), Handler)
    try:
        http.serve_forever()
    finally:
        PERSON_TYPE_RUNTIME.stop()
        http.server_close()


if __name__ == "__main__":
    main()
