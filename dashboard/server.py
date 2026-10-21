"""课程项目 V1：电脑端基础监控页面。

RDK 运行 web_fall.py，本服务在电脑端把 RDK 的实时画面、行为状态和
STM32 传感器数据转发到同一个简易网页，并提供只读的 ESP32 对话测试页。
本页不调用大模型，不包含情绪分析、事件处置、名单或历史日志功能。
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from collections import deque
from datetime import datetime, timezone
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parent
HOST = os.environ.get("DASHBOARD_HOST", "0.0.0.0")
PORT = int(os.environ.get("DASHBOARD_PORT", "8088"))
RDK_BASE = os.environ.get("RDK_BASE", "http://192.168.43.54:5000").rstrip("/")
DIALOGUE_LIMIT = 200
DIALOGUE_DATA_FILE = Path(
    os.environ.get("DIALOGUE_DATA_FILE", str(ROOT / "dialogue_messages.json"))
)
DIALOGUE_CONFIG_FILE = Path(
    os.environ.get("DIALOGUE_CONFIG_FILE", str(ROOT / "dialogue_config.json"))
)
DEFAULT_DIALOGUE_CONFIG = {
    "title": "陪伴对话记录",
    "refresh_seconds": 2,
    "page_size": 50,
    "show_session_id": False,
    "show_created_at": True,
    "auto_scroll": True,
}
MESSAGES_LOCK = threading.Lock()
DIALOGUE_CONFIG_LOCK = threading.Lock()


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


MESSAGES = load_messages()
DIALOGUE_CONFIG = load_dialogue_config()


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

    def local_dialogue_request(self) -> bool:
        # The conversation test page is for the server PC; the monitoring page
        # remains available to other devices on the LAN.
        host = urlparse('http://' + self.headers.get('Host', '')).hostname
        origin = self.headers.get('Origin')
        if (self.client_address[0] not in ('127.0.0.1', '::1')
                or host not in ('localhost', '127.0.0.1', '::1')
                or (origin and origin != 'http://' + self.headers.get('Host', ''))
                or self.headers.get('Sec-Fetch-Site') == 'cross-site'):
            self.send_json(403, {'ok': False, 'error': 'Open the conversation page on localhost'})
            return False
        return True

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path not in ('/api/dialogue/messages', '/api/dialogue/config'):
            self.send_json(404, {'ok': False, 'error': 'not found'})
            return
        try:
            length = int(self.headers.get('Content-Length', '0'))
            limit = 4096 if path == '/api/dialogue/config' else 65536
            if not 0 < length <= limit:
                raise ValueError('Invalid body size')
            if self.headers.get_content_type() != 'application/json':
                raise ValueError('JSON required')
            # Consume the bounded body before rejecting a local-origin check;
            # otherwise Windows can reset the socket before the 403 is read.
            self.connection.settimeout(5)
            body = self.rfile.read(length)
            if not self.local_dialogue_request():
                return
            item = json.loads(body)

            if path == '/api/dialogue/config':
                config = validate_dialogue_config(item)
                with DIALOGUE_CONFIG_LOCK:
                    atomic_write_json(DIALOGUE_CONFIG_FILE, config)
                    DIALOGUE_CONFIG.clear()
                    DIALOGUE_CONFIG.update(config)
                self.send_json(200, {'ok': True, 'config': DIALOGUE_CONFIG.copy()})
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
            with MESSAGES_LOCK:
                if not any(m['id'] == record['id'] for m in MESSAGES):
                    MESSAGES.append(record)
                    save_messages()
            self.send_json(200, {'ok': True})
        except (ValueError, UnicodeError, TimeoutError):
            error = 'Invalid dialogue config' if path == '/api/dialogue/config' else 'Invalid dialogue message'
            self.send_json(400, {'ok': False, 'error': error})
        except OSError:
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
        if path in ('/chat', '/chat.html', '/api/dialogue/messages', '/api/dialogue/config'):
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
            else:
                self.send_bytes(200, 'text/html; charset=utf-8', (ROOT / 'chat.html').read_bytes())
            return
        if path in ("/", "/index.html"):
            self.serve_index()
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
        self.send_json(404, {"ok": False, "error": "not found"})


def main() -> None:
    print(f"Tongyu dashboard: http://127.0.0.1:{PORT}")
    print(f"RDK input: {RDK_BASE}")
    print("This version only displays real RDK and STM32 input; it has no demo sensor values.")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
