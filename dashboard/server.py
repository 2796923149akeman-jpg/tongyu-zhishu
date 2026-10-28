"""课程项目 V1：电脑端基础监控页面。

RDK 运行 web_fall.py，本服务在电脑端把 RDK 的实时画面、行为状态和
STM32 传感器数据转发到同一个简易网页，并提供 ESP32 对话回顾页。
对话页可在后台进行词库/模型情绪分析与会话总结，不影响设备语音链路。
"""

from __future__ import annotations

import json
import os
import queue
import re
import tempfile
import threading
from collections import deque
from datetime import datetime, timezone
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse


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
    EventConflict,
    EventNotFound,
    EventValidationError,
    date_key,
    make_event_id,
    normalize_event,
    now_iso,
    text_value,
    validate_status_transition,
)

HOST = os.environ.get("DASHBOARD_HOST", "0.0.0.0")
PORT = int(os.environ.get("DASHBOARD_PORT", "8088"))
RDK_BASE = os.environ.get("RDK_BASE", "http://192.168.43.54:5000").rstrip("/")
PROJECT_ROOT = Path(os.environ.get("PROJECT_ROOT", str(ROOT.parent)))
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
EVENTS_LIMIT = 2000
# 学生测温与当日日报页面及其专用样式、脚本。页面只包含静态结构和演示数据，
# 名单与测温数据需要后续接口提供；这些路由不读取任何本机业务数据。
STATIC_PAGES = {
    "/health.html": ("health.html", "text/html; charset=utf-8"),
    "/reports.html": ("reports.html", "text/html; charset=utf-8"),
    "/health-report.css": ("health-report.css", "text/css; charset=utf-8"),
    "/health-report.js": ("health-report.js", "text/javascript; charset=utf-8"),
}
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
        os.replace(temporary_name, path)
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
            event = normalize_event(raw)
        except EventValidationError:
            continue
        if not event["id"]:
            event["id"] = make_event_id(event["occurred_at"])
        loaded.append(event)
    return loaded


def save_events() -> None:
    atomic_write_json(EVENTS_FILE, EVENTS)


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
        EVENTS.append(event)
        if len(EVENTS) > EVENTS_LIMIT:
            del EVENTS[:len(EVENTS) - EVENTS_LIMIT]
        save_events()
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
        event = next((item for item in EVENTS if item.get("id") == event_id), None)
        if event is None:
            raise EventNotFound("event not found")
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
        save_events()
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
                    with SUMMARIES_LOCK:
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


class Handler(BaseHTTPRequestHandler):
    server_version = "TongyuDashboard/1.0"

    def log_message(self, fmt: str, *args) -> None:
        print("[HTTP] " + (fmt % args))

    def send_bytes(self, status: int, content_type: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, status: int, data: dict) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_bytes(status, "application/json; charset=utf-8", body)

    def serve_index(self) -> None:
        self.send_bytes(
            200,
            "text/html; charset=utf-8",
            (ROOT / "index.html").read_bytes(),
        )

    def local_request(self, error: str) -> bool:
        host = urlparse('http://' + self.headers.get('Host', '')).hostname
        origin = self.headers.get('Origin')
        if (self.client_address[0] not in ('127.0.0.1', '::1')
                or host not in ('localhost', '127.0.0.1', '::1')
                or (origin and origin != 'http://' + self.headers.get('Host', ''))
                or self.headers.get('Sec-Fetch-Site') == 'cross-site'):
            self.send_json(403, {'ok': False, 'error': error})
            return False
        return True

    def local_dialogue_request(self) -> bool:
        # The conversation test page is for the server PC; the monitoring page
        # remains available to other devices on the LAN.
        return self.local_request('Open the conversation page on localhost')

    def local_event_request(self) -> bool:
        return self.local_request('Open the event API on localhost')

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        event_match = re.fullmatch(r"/api/events/([^/]+)/(status|notes)", path)
        event_request = path == "/api/events" or event_match is not None
        dialogue_request = path in (
            '/api/dialogue/messages',
            '/api/dialogue/config',
            '/api/dialogue/model',
            '/api/analysis/config',
            '/api/analysis/rebuild',
        )
        if not dialogue_request and not event_request:
            self.send_json(404, {'ok': False, 'error': 'not found'})
            return
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
            if event_request:
                if not self.local_event_request():
                    return
            elif not self.local_dialogue_request():
                return
            try:
                item = json.loads(body)
            except (ValueError, UnicodeError):
                if event_request:
                    self.send_json(400, {'ok': False, 'error': 'Invalid event JSON'})
                    return
                raise

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
                    else:
                        result = append_event_note(event_id, item)
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
                    MESSAGES.append(record)
                    save_messages()
                    inserted = True
            if inserted:
                if record['role'] == 'user':
                    enqueue_analysis('emotion', record['id'])
                schedule_summary(record['session_id'])
            self.send_json(200, {'ok': True})
        except (ValueError, UnicodeError, TimeoutError):
            if event_request:
                error = 'Invalid event request'
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
            else:
                self.send_json(500, {'ok': False, 'error': 'Unable to save dialogue data'})

    def proxy_json(self, upstream_path: str) -> None:
        try:
            self.send_json(200, read_rdk_json(upstream_path))
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
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                self.send_response(response.status)
                self.send_header(
                    "Content-Type",
                    response.headers.get("Content-Type", "multipart/x-mixed-replace; boundary=frame"),
                )
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                while True:
                    chunk = response.read(16 * 1024)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            return
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            if not self.wfile.closed:
                try:
                    self.send_json(502, {"ok": False, "error": str(exc)})
                except (BrokenPipeError, ConnectionResetError):
                    pass

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path in ('/chat', '/chat.html', '/api/dialogue/messages', '/api/dialogue/config', '/api/dialogue/model', '/api/dialogue/conversations', '/api/analysis/config'):
            if not self.local_dialogue_request():
                return
            if path == '/api/dialogue/messages':
                with MESSAGES_LOCK:
                    items = list(MESSAGES)
                self.send_json(200, {'messages': items, 'limit': DIALOGUE_LIMIT})
            elif path == '/api/dialogue/config':
                with DIALOGUE_CONFIG_LOCK:
                    config = DIALOGUE_CONFIG.copy()
                self.send_json(200, {'config': config})
            elif path == '/api/dialogue/conversations':
                self.send_json(200, {'conversations': conversation_items()})
            elif path == '/api/dialogue/model':
                self.send_json(200, {'model': public_xiaozhi_model(PROJECT_ROOT)})
            elif path == '/api/analysis/config':
                with ANALYSIS_CONFIG_LOCK:
                    config = public_analysis_config(ANALYSIS_CONFIG.copy(), load_xiaozhi_model(PROJECT_ROOT))
                self.send_json(200, {'config': config})
            else:
                self.send_bytes(200, 'text/html; charset=utf-8', (ROOT / 'chat.html').read_bytes())
            return
        if path in ("/", "/index.html"):
            self.serve_index()
            return
        if path in ("/events", "/events.html"):
            self.send_bytes(200, "text/html; charset=utf-8", (ROOT / "events.html").read_bytes())
            return
        if path == "/api/events":
            if not self.local_event_request():
                return
            try:
                result = query_events(parse_qs(urlparse(self.path).query))
                self.send_json(200, {"ok": True, **result})
            except (EventValidationError, ValueError) as exc:
                self.send_json(400, {"ok": False, "error": "invalid event query", "detail": str(exc)})
            return
        event_get = re.fullmatch(r"/api/events/([^/]+)", path)
        if event_get:
            if not self.local_event_request():
                return
            try:
                event = get_event(unquote(event_get.group(1)))
                self.send_json(200, {"ok": True, "event": event})
            except EventNotFound:
                self.send_json(404, {"ok": False, "error": "event not found"})
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
            self.proxy_video()
            return
        if path == "/health":
            self.send_json(200, {"ok": True, "rdk_base": RDK_BASE})
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
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
