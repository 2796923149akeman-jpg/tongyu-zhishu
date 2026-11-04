"""异常事件 API 的隔离测试。"""

import importlib.util
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from urllib.parse import urlencode
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


def load_server():
    spec = importlib.util.spec_from_file_location(
        "test_dashboard_events", ROOT / "dashboard" / "server.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class EventApiTests(unittest.TestCase):
    def setUp(self):
        self.web = load_server()
        self.temp = tempfile.TemporaryDirectory()
        self.web.AUTH = self.web.AccessStore(Path(self.temp.name) / "auth_config.json", secure=False)
        self.web.AUTH.create_user("owner", "test-owner-password", role="admin")
        token, session = self.web.AUTH.new_session("owner")
        self.auth_headers = {"Cookie": "tongyu_session=" + token, "X-CSRF-Token": session["csrf"]}
        self.web.DIALOGUE_DATA_FILE = Path(self.temp.name) / "dialogue_messages.json"
        self.web.DIALOGUE_CONFIG_FILE = Path(self.temp.name) / "dialogue_config.json"
        self.web.ANALYSIS_CONFIG_FILE = Path(self.temp.name) / "analysis_config.json"
        self.web.CONVERSATION_SUMMARIES_FILE = Path(self.temp.name) / "conversation_summaries.json"
        self.web.PROJECT_ROOT = Path(self.temp.name)
        self.web.EVENTS_FILE = Path(self.temp.name) / "events.json"
        self.web.EVIDENCE_DIR = Path(self.temp.name) / "evidence"
        self.web.EVIDENCE_DIR.mkdir()
        self.web.CURRENT_RDK_ALERT = "normal"
        (Path(self.temp.name) / "xiaozhi-server" / "data").mkdir(parents=True)
        self.web.reload_events()
        self.web.Handler.log_message = lambda *args: None
        self.http = self.web.ThreadingHTTPServer(("127.0.0.1", 0), self.web.Handler)
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.http.server_port}"

    def tearDown(self):
        self.http.shutdown()
        self.http.server_close()
        self.thread.join()
        self.temp.cleanup()

    def request(self, path, payload=None, method="GET"):
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        headers = {"Content-Type": "application/json"} if data else {}
        headers.update(self.auth_headers)
        request = urllib.request.Request(self.base + path, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                body = response.read()
                return response.status, json.loads(body) if body else {}
        except urllib.error.HTTPError as exc:
            body = exc.read()
            return exc.code, json.loads(body) if body else {}

    def event_payload(self):
        now = datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")
        return {
            "event_type": "fall",
            "level": "urgent",
            "source": "rdk",
            "occurred_at": now,
            "summary": "测试摔倒事件",
            "detail": "行为识别测试",
            "class_id": "C-02",
            "class_name": "小二班",
            "device_id": "rdk-test",
            "dedupe_key": "test-fall-1",
            "evidence_url": "/evidence/test-fall-1.png",
            "evidence_captured_at": now,
        }

    def test_create_dedupe_query_status_notes_and_persistence(self):
        payload = self.event_payload()
        status, created = self.request("/api/events", payload, "POST")
        self.assertEqual(status, 201)
        self.assertFalse(created["duplicate"])
        event_id = created["event"]["id"]
        self.assertTrue(event_id.startswith("EVT-"))
        self.assertEqual(created["event"]["class_name"], "小二班")
        self.assertEqual(created["event"]["evidence_url"], "/evidence/test-fall-1.png")
        self.assertEqual(created["event"]["evidence_captured_at"], payload["evidence_captured_at"])
        self.assertTrue(created["event"]["history"])

        status, duplicate = self.request("/api/events", self.event_payload(), "POST")
        self.assertEqual(status, 200)
        self.assertTrue(duplicate["duplicate"])
        self.assertEqual(duplicate["event"]["id"], event_id)

        status, listing = self.request("/api/events?status=pending&class_id=C-02&limit=20")
        self.assertEqual(status, 200)
        self.assertEqual(listing["total"], 1)
        self.assertEqual(listing["events"][0]["id"], event_id)

        status, one = self.request(f"/api/events/{event_id}")
        self.assertEqual(status, 200)
        self.assertEqual(one["event"]["summary"], "测试摔倒事件")

        status, resolved = self.request(
            f"/api/events/{event_id}/status",
            {"status": "resolved", "note": "现场确认安全", "handled_by": "测试老师"},
            "POST",
        )
        self.assertEqual(status, 200)
        self.assertEqual(resolved["event"]["status"], "resolved")
        self.assertTrue(resolved["event"]["handled_at"])
        self.assertEqual(resolved["event"]["handled_by"], "测试老师")

        status, conflict = self.request(
            f"/api/events/{event_id}/status",
            {"status": "false_alarm"},
            "POST",
        )
        self.assertEqual(status, 409)

        status, note = self.request(
            f"/api/events/{event_id}/notes",
            {"note": "交接班复核", "author": "测试老师"},
            "POST",
        )
        self.assertEqual(status, 200)
        self.assertEqual(note["event"]["note"], "交接班复核")

        saved = json.loads(self.web.EVENTS_FILE.read_text(encoding="utf-8"))
        self.assertEqual(saved[0]["id"], event_id)
        self.web.reload_events()
        self.assertEqual(self.web.get_event(event_id)["status"], "resolved")

    def test_filters_and_invalid_requests(self):
        payload = self.event_payload()
        payload["level"] = "watch"
        payload["class_id"] = "C-11"
        payload["class_name"] = "中一班"
        status, created = self.request("/api/events", payload, "POST")
        self.assertEqual(status, 201)

        status, listing = self.request("/api/events?" + urlencode({
            "level": "watch",
            "class_id": "C-11",
            "q": "测试",
        }))
        self.assertEqual(status, 200)
        self.assertEqual(listing["total"], 1)
        status, empty = self.request("/api/events?level=urgent")
        self.assertEqual(status, 200)
        self.assertEqual(empty["total"], 0)

        bad = self.event_payload()
        bad["event_type"] = "unknown"
        status, body = self.request("/api/events", bad, "POST")
        self.assertEqual(status, 400)
        self.assertFalse(body["ok"])

        status, body = self.request(f"/api/events/{created['event']['id']}/notes", {"note": "x" * 201}, "POST")
        self.assertEqual(status, 400)

        status, body = self.request("/api/events/not-found", method="GET")
        self.assertEqual(status, 404)

    def test_rdk_alert_edge_creates_one_deduplicated_event(self):
        with patch.object(self.web, "read_rdk_json", return_value={"alert_type": "fall", "confidence": 0.8}):
            for _ in range(2):
                status, body = self.request("/api/rdk/status")
                self.assertEqual(status, 200)
                self.assertEqual(body["alert_type"], "fall")

        status, listing = self.request("/api/events")
        self.assertEqual(status, 200)
        self.assertEqual(listing["total"], 1)
        self.assertEqual(listing["events"][0]["event_type"], "fall")
        self.assertEqual(listing["events"][0]["level"], "urgent")

        with patch.object(self.web, "read_rdk_json", return_value={"alert_type": "normal"}):
            status, _ = self.request("/api/rdk/status")
            self.assertEqual(status, 200)
        with patch.object(self.web, "read_rdk_json", return_value={"alert_type": "fight"}):
            status, _ = self.request("/api/rdk/status")
            self.assertEqual(status, 200)

        status, listing = self.request("/api/events")
        self.assertEqual(status, 200)
        self.assertEqual(listing["total"], 2)
        self.assertEqual({item["event_type"] for item in listing["events"]}, {"fall", "fight"})

    def test_evidence_asset_requires_login_and_is_served_safely(self):
        image = b"\x89PNG\r\n\x1a\nfixture"
        (self.web.EVIDENCE_DIR / "event-frame.png").write_bytes(image)

        request = urllib.request.Request(
            self.base + "/evidence/event-frame.png",
            headers=self.auth_headers,
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            self.assertEqual(response.status, 200)
            self.assertEqual(response.headers.get_content_type(), "image/png")
            self.assertEqual(response.read(), image)

        with self.assertRaises(urllib.error.HTTPError) as unauth:
            urllib.request.urlopen(self.base + "/evidence/event-frame.png", timeout=5)
        self.assertEqual(unauth.exception.code, 401)

        status, body = self.request("/evidence/not-an-image.txt")
        self.assertEqual(status, 404)
        self.assertFalse(body["ok"])


if __name__ == "__main__":
    unittest.main()
