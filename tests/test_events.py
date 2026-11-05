"""异常事件 API 的隔离测试。"""

import importlib.util
import io
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from email.message import Message
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlencode

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
        self.web.HEALTH_STUDENTS_FILE = Path(self.temp.name) / "health_students.json"
        self.web.HEALTH_RECORDS_FILE = Path(self.temp.name) / "health_records.json"
        self.web.CURRENT_RDK_ALERT = "normal"
        (Path(self.temp.name) / "xiaozhi-server" / "data").mkdir(parents=True)
        self.web.reload_events()
        self.web.reload_health()
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
                if response.headers.get_content_type() == "image/jpeg":
                    return response.status, body
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
        with patch.object(self.web, "read_rdk_json", return_value={"alert_type": "fall", "confidence": 0.8, "snapshot_available": False}):
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
        with patch.object(self.web, "read_rdk_json", return_value={"alert_type": "fight", "snapshot_available": False}):
            status, _ = self.request("/api/rdk/status")
            self.assertEqual(status, 200)

        status, listing = self.request("/api/events")
        self.assertEqual(status, 200)
        self.assertEqual(listing["total"], 2)
        self.assertEqual({item["event_type"] for item in listing["events"]}, {"fall", "fight"})
        self.assertTrue(all(item["snapshot_status"] == "skipped" for item in listing["events"]))

    def test_admin_can_retry_snapshot_and_status_is_recorded(self):
        status, created = self.request("/api/events", self.event_payload(), "POST")
        event_id = created["event"]["id"]
        with patch.object(self.web, "capture_event_snapshot") as capture:
            status, body = self.request(
                f"/api/events/{event_id}/snapshot/retry", {}, "POST"
            )
        self.assertEqual(status, 200)
        self.assertEqual(body["event"]["snapshot_status"], "ok")
        capture.assert_called_once_with(event_id)
        self.assertEqual(body["event"]["history"][-1]["action"], "重新抓拍成功")

        with patch.object(self.web, "capture_event_snapshot", side_effect=OSError("down")):
            status, body = self.request(
                f"/api/events/{event_id}/snapshot/retry", {}, "POST"
            )
        self.assertEqual(status, 200)
        self.assertEqual(body["event"]["snapshot_status"], "failed")
        self.assertEqual(body["event"]["snapshot_error"], "OSError")
        self.assertEqual(body["event"]["history"][-1]["action"], "重新抓拍失败")

    def test_capture_is_tied_to_event_and_protected_by_video_access(self):
        image = b"\xff\xd8fixture\xff\xd9"
        original = urllib.request.urlopen

        def upstream(request, **kwargs):
            if request.full_url == self.web.RDK_BASE + "/snapshot":
                stream = io.BytesIO(image)
                stream.headers = Message()
                stream.headers["Content-Type"] = "image/jpeg"
                return stream
            return original(request, **kwargs)

        with patch.object(self.web, "read_rdk_json", return_value={"alert_type": "fall"}), \
                patch.object(urllib.request, "urlopen", side_effect=upstream):
            self.assertEqual(self.request("/api/rdk/status")[0], 200)
        self.web.reload_events()
        event = self.request("/api/events")[1]["events"][0]
        self.assertTrue(event["has_snapshot"])
        self.assertEqual(event["snapshot_status"], "ok")
        route = f"/api/events/{event['id']}/snapshot"
        self.assertEqual(self.request(route), (200, image))
        with patch.object(self.web, "read_rdk_json", return_value={"alert_type": "fight"}), \
                patch.object(self.web, "capture_event_snapshot", side_effect=TimeoutError):
            self.assertEqual(self.request("/api/rdk/status")[0], 200)
        events = {item["event_type"]: item for item in self.request("/api/events")[1]["events"]}
        self.assertFalse(events["fight"]["has_snapshot"])
        self.assertEqual(events["fight"]["snapshot_status"], "timeout")
        self.assertEqual(self.request(f"/api/events/{events['fight']['id']}/snapshot")[0], 404)
        self.web.AUTH.create_user("viewer", "test-viewer-password")
        token, _ = self.web.AUTH.new_session("viewer")
        self.auth_headers = {"Cookie": "tongyu_session=" + token}
        self.assertEqual(self.request(route)[0], 403)
        self.assertFalse(self.request(f"/api/events/{event['id']}")[1]["event"]["has_snapshot"])

    def test_dialogue_deletion_is_scoped_and_persisted(self):
        self.web.MESSAGES.clear()
        self.web.CONVERSATION_SUMMARIES.clear()
        for ident in ("first", "second"):
            self.web.MESSAGES.append({"id": ident, "session_id": "shared", "text": ident})
        self.web.CONVERSATION_SUMMARIES["shared"] = {"message_count": 2}
        route = "/api/dialogue/delete"
        self.assertEqual(self.request(route, {"scope": "all", "confirm": False}, "POST")[0], 400)
        status, result = self.request(route, {"ids": ["first"]}, "POST")
        self.assertEqual((status, result["deleted"]), (200, 1))
        self.assertEqual([item["id"] for item in self.web.load_messages()], ["second"])
        self.assertEqual(self.web.load_summaries(), {})
        self.web.AUTH.create_user("viewer", "test-viewer-password")
        token, session = self.web.AUTH.new_session("viewer")
        admin_headers = self.auth_headers
        self.auth_headers = {"Cookie": "tongyu_session=" + token, "X-CSRF-Token": session["csrf"]}
        self.assertEqual(self.request(route, {"scope": "all", "confirm": True}, "POST")[0], 403)
        self.auth_headers = admin_headers
        status, result = self.request(route, {"scope": "all", "confirm": True}, "POST")
        self.assertEqual((status, result["deleted"]), (200, 1))
        self.assertFalse(self.web.load_messages())

    def test_json_persistence_retries_transient_windows_replace_error(self):
        real_replace = self.web.os.replace
        busy = PermissionError("file temporarily busy")
        busy.winerror = 32
        target = Path(self.temp.name) / "retry.json"
        attempts = []

        def replace_once_busy(source, destination):
            attempts.append(destination)
            if len(attempts) == 1:
                raise busy
            real_replace(source, destination)

        with patch.object(self.web.os, "replace", side_effect=replace_once_busy) as replace:
            self.web.atomic_write_json(target, {"saved": True})
            self.assertEqual(replace.call_count, 2)
        self.assertEqual(self.web.read_json_file(target, None), {"saved": True})

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

    def test_teacher_can_assign_single_and_multiple_participants(self):
        status, imported = self.request(
            "/api/health/import",
            {
                "students": [
                    {"id": "S-0201", "name": "张小明", "class_id": "C-02"},
                    {"id": "S-0202", "name": "李小红", "class_id": "C-02"},
                ]
            },
            "POST",
        )
        self.assertEqual(status, 200)
        self.assertEqual(imported["imported"], 2, imported)

        fall_payload = self.event_payload()
        fall_payload["dedupe_key"] = "participant-fall"
        status, created = self.request("/api/events", fall_payload, "POST")
        self.assertEqual(status, 201)
        fall_id = created["event"]["id"]
        status, assigned = self.request(
            f"/api/events/{fall_id}/participants",
            {"names": "张小明", "handled_by": "王老师"},
            "POST",
        )
        self.assertEqual(status, 200)
        self.assertEqual(assigned["event"]["participants"][0]["student_id"], "S-0201")
        self.assertEqual(assigned["event"]["class_name"], "小二班")
        self.assertTrue(assigned["event"]["parent_visible_at"])

        fight_payload = self.event_payload()
        fight_payload["event_type"] = "fight"
        fight_payload["dedupe_key"] = "participant-fight"
        status, created = self.request("/api/events", fight_payload, "POST")
        fight_id = created["event"]["id"]
        status, invalid = self.request(
            f"/api/events/{fight_id}/participants",
            {"names": "张小明"},
            "POST",
        )
        self.assertEqual(status, 400)
        status, assigned = self.request(
            f"/api/events/{fight_id}/participants",
            {"names": "张小明　李小红", "handled_by": "王老师"},
            "POST",
        )
        self.assertEqual(status, 200)
        self.assertEqual(
            [item["student_id"] for item in assigned["event"]["participants"]],
            ["S-0201", "S-0202"],
        )

    def test_duplicate_student_names_require_explicit_id(self):
        self.request(
            "/api/health/import",
            {
                "students": [
                    {"id": "S-0201", "name": "张小明", "class_id": "C-02"},
                    {"id": "S-0202", "name": "张小明", "class_id": "C-02"},
                ]
            },
            "POST",
        )
        payload = self.event_payload()
        payload["dedupe_key"] = "duplicate-name-fall"
        status, created = self.request("/api/events", payload, "POST")
        event_id = created["event"]["id"]
        status, body = self.request(
            f"/api/events/{event_id}/participants",
            {"names": "张小明"},
            "POST",
        )
        self.assertEqual(status, 400)
        self.assertIn("S-0201", body["detail"])
        status, assigned = self.request(
            f"/api/events/{event_id}/participants",
            {"names": "张小明@S-0202"},
            "POST",
        )
        self.assertEqual(status, 200)
        self.assertEqual(assigned["event"]["participants"][0]["student_id"], "S-0202")
        payload = self.event_payload()
        payload["evidence_url"] = "data:image/png;base64,YQ=="
        status, result = self.request("/api/events", payload, "POST")
        self.assertEqual(status, 201)
        self.web.AUTH.create_user("viewer", "test-viewer-password")
        token, _ = self.web.AUTH.new_session("viewer")
        self.auth_headers = {"Cookie": "tongyu_session=" + token}
        self.assertEqual(self.request("/evidence/event-frame.png")[0], 403)
        event = self.request(f"/api/events/{result['event']['id']}")[1]["event"]
        self.assertNotIn("evidence_url", event)
        self.assertNotIn("evidence_captured_at", event)


    def test_fall_event_notifies_configured_channel(self):
        self.web.ALERT_NOTIFY_URL = "http://notify.local/alert"
        with patch.object(self.web, "notify_event_async") as notify:
            status, created = self.request("/api/events", self.event_payload(), "POST")
            self.assertEqual(status, 201)
            notify.assert_called_once()
            self.assertEqual(notify.call_args[0][0]["event_type"], "fall")

    def test_notification_success_and_failure_are_recorded(self):
        status, created = self.request("/api/events", self.event_payload(), "POST")
        event_id = created["event"]["id"]
        self.web.ALERT_NOTIFY_URL = "http://notify.local/alert"

        class Response:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        with patch.object(self.web.urllib.request, "urlopen", return_value=Response()):
            self.assertTrue(self.web.deliver_event_notification(self.web.get_event(event_id)))
        event = self.web.get_event(event_id)
        self.assertEqual(event["history"][-1]["action"], "设备播报")
        self.assertEqual(event["history"][-1]["by"], "通知服务")

        with patch.object(self.web.urllib.request, "urlopen", side_effect=OSError("down")):
            self.assertFalse(self.web.deliver_event_notification(self.web.get_event(event_id)))
        event = self.web.get_event(event_id)
        self.assertEqual(event["history"][-1]["action"], "设备播报失败")

    def test_notification_only_for_behavior_alerts(self):
        self.web.ALERT_NOTIFY_URL = "http://notify.local/alert"
        with patch.object(self.web.threading, "Thread") as thread:
            self.web.notify_event_async({"id": "EVT-1", "event_type": "environment"})
            thread.assert_not_called()
            self.web.notify_event_async({"id": "EVT-2", "event_type": "fall"})
            thread.assert_called_once()


if __name__ == "__main__":
    unittest.main()
