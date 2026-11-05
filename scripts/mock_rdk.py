"""无硬件演示用的模拟 RDK 服务。

提供与真实 RDK 相同的接口形状，便于在答辩、录屏或界面检查时复现
视频流、行为告警、传感器读数和抓拍，不需要连接 STM32/摄像头。

用法：
    python scripts/mock_rdk.py --port 5000
    set RDK_BASE=http://127.0.0.1:5000
    python scripts/run_dashboard.py

控制接口：
    POST /mock/alert    {"alert_type": "fall" | "fight" | "normal"}
    POST /mock/sensors  {"connected": false, "eco2": 1200, "tvoc": 620,
                         "sht_t": 25.1, "sht_h": 55, "stale_seconds": 120}
    GET  /mock/state    查看当前模拟状态

所有模拟数据只用于本地演示，不代表真实设备读数。
"""

from __future__ import annotations

import argparse
import base64
import json
import threading
import time
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_FILE = ROOT / "docs" / "assets" / "mock-snapshot.jpg"
# 备用 1x1 JPEG，避免资源缺失时抓拍接口不可用。
FALLBACK_JPEG = base64.b64decode(
    "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAoHBwgHBgoICAgLCgoLDhgQDg0NDh0VFhEYIx8lJCIfIiEmKzcvJik0KSEiMEExNDk7Pj4+JS5ESUM8SDc9Pjv/2wBDAQoLCw4NDhwQEBw7KCIoOzs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozs7Ozv/wAARCAAIAAgDASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwD1eiiigzP/2Q=="
)
STATE = {
    "alert_type": "normal",
    "confidence": 0.86,
    "connected": True,
    "eco2": 520.0,
    "tvoc": 60.0,
    "sht_t": 25.0,
    "sht_h": 55.0,
    "mlx_amb": 24.8,
    "stale_seconds": 0,
}
LOCK = threading.Lock()


def snapshot_bytes() -> bytes:
    try:
        return SNAPSHOT_FILE.read_bytes()
    except OSError:
        return FALLBACK_JPEG


def iso_now(minus_seconds: int = 0) -> str:
    moment = datetime.now(timezone.utc) - timedelta(seconds=max(0, minus_seconds))
    return moment.isoformat(timespec="seconds")


class Handler(BaseHTTPRequestHandler):
    server_version = "MockRDK/1.0"

    def log_message(self, fmt, *args):
        print(f"[MOCK] {self.command} {self.path.split('?')[0]}")

    def send_json(self, payload, status=200):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_jpeg(self):
        image = snapshot_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "image/jpeg")
        self.send_header("Content-Length", str(len(image)))
        self.end_headers()
        self.wfile.write(image)

    def read_json(self):
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def do_GET(self):
        path = self.path.split("?")[0]
        with LOCK:
            state = dict(STATE)
        if path == "/":
            self.send_json({"service": "mock-rdk", "endpoints": ["/alert_status", "/snapshot", "/api/iot_payload", "/video_feed", "/mock/state"]})
        elif path == "/alert_status":
            self.send_json({"alert_type": state["alert_type"], "confidence": state["confidence"]})
        elif path == "/snapshot":
            self.send_jpeg()
        elif path == "/api/iot_payload":
            self.send_json({
                "timestamp": iso_now(state["stale_seconds"]),
                "connected": state["connected"],
                "properties": {
                    "mlx_obj": 36.5,
                    "mlx_amb": state["mlx_amb"],
                    "sht_t": state["sht_t"],
                    "sht_h": state["sht_h"],
                    "eco2": state["eco2"],
                    "tvoc": state["tvoc"],
                },
            })
        elif path == "/video_feed":
            self.stream_video()
        elif path == "/mock/state":
            self.send_json(state)
        else:
            self.send_json({"error": "not found"}, 404)

    def stream_video(self):
        image = snapshot_bytes()
        boundary = b"mockframe"
        self.send_response(200)
        self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=mockframe")
        self.end_headers()
        try:
            while True:
                self.wfile.write(b"--" + boundary + b"\r\n")
                self.wfile.write(b"Content-Type: image/jpeg\r\n")
                self.wfile.write(b"Content-Length: " + str(len(image)).encode() + b"\r\n\r\n")
                self.wfile.write(image)
                self.wfile.write(b"\r\n")
                self.wfile.flush()
                time.sleep(1)
        except (BrokenPipeError, ConnectionResetError):
            return

    def do_POST(self):
        path = self.path.split("?")[0]
        try:
            payload = self.read_json()
        except (ValueError, UnicodeDecodeError):
            self.send_json({"error": "invalid json"}, 400)
            return
        with LOCK:
            if path == "/mock/alert":
                alert = str(payload.get("alert_type", "")).strip().lower()
                if alert not in ("normal", "fall", "fight"):
                    self.send_json({"error": "alert_type must be normal/fall/fight"}, 400)
                    return
                STATE["alert_type"] = alert
                self.send_json({"alert_type": alert})
                return
            if path == "/mock/sensors":
                for key in ("connected", "eco2", "tvoc", "sht_t", "sht_h", "mlx_amb", "stale_seconds"):
                    if key in payload:
                        STATE[key] = payload[key]
                self.send_json(dict(STATE))
                return
        self.send_json({"error": "not found"}, 404)


def main():
    parser = argparse.ArgumentParser(description="模拟 RDK 接口，供无硬件演示使用")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5000)
    args = parser.parse_args()
    http = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Mock RDK: http://{args.host}:{args.port}")
    print("控制告警: curl -X POST http://127.0.0.1:%d/mock/alert -H \"Content-Type: application/json\" -d \"{\\\"alert_type\\\":\\\"fall\\\"}\"" % args.port)
    try:
        http.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        http.server_close()


if __name__ == "__main__":
    main()
