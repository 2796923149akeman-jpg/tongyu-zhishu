"""学生名单、测温记录与日报 API 的隔离测试。"""

import importlib.util
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load_server():
    spec = importlib.util.spec_from_file_location(
        "test_dashboard_health_api", ROOT / "dashboard" / "server.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def local_date():
    return datetime.now(timezone(timedelta(hours=8))).date().isoformat()


class HealthApiTests(unittest.TestCase):
    def setUp(self):
        self.web = load_server()
        self.temp = tempfile.TemporaryDirectory()
        self.web.AUTH = self.web.AccessStore(Path(self.temp.name) / "auth_config.json", secure=False)
        self.web.AUTH.create_user("owner", "test-owner-password", role="admin")
        token, session = self.web.AUTH.new_session("owner")
        self.auth_headers = {"Cookie": "tongyu_session=" + token, "X-CSRF-Token": session["csrf"]}
        temp = Path(self.temp.name)
        self.web.DIALOGUE_DATA_FILE = temp / "dialogue_messages.json"
        self.web.DIALOGUE_CONFIG_FILE = temp / "dialogue_config.json"
        self.web.ANALYSIS_CONFIG_FILE = temp / "analysis_config.json"
        self.web.CONVERSATION_SUMMARIES_FILE = temp / "conversation_summaries.json"
        self.web.PROJECT_ROOT = temp
        self.web.EVENTS_FILE = temp / "events.json"
        self.web.HEALTH_STUDENTS_FILE = temp / "health_students.json"
        self.web.HEALTH_RECORDS_FILE = temp / "health_records.json"
        self.web.HEALTH_DEVICE_TOKEN = "fixture-device-token-0123456789abcdef"
        self.web.HEALTH_INFRARED_STALE_SECONDS = 10
        self.web.HEALTH_LAST_INFRARED = None
        (temp / "xiaozhi-server" / "data").mkdir(parents=True)
        self.web.reload_events()
        self.web.reload_health()
        self.web.Handler.log_message = lambda *args: None
        self.http = self.web.ThreadingHTTPServer(("127.0.0.1", 0), self.web.Handler)
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.http.server_port}"
        self.today = local_date()

    def tearDown(self):
        self.http.shutdown()
        self.http.server_close()
        self.thread.join()
        self.temp.cleanup()

    def request(
        self,
        path,
        payload=None,
        method="GET",
        extra_headers=None,
        authenticated=True,
    ):
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        headers = {"Content-Type": "application/json"} if data else {}
        if authenticated:
            headers.update(self.auth_headers)
        headers.update(extra_headers or {})
        request = urllib.request.Request(self.base + path, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                body = response.read()
                return response.status, json.loads(body) if body else {}
        except urllib.error.HTTPError as exc:
            body = exc.read()
            return exc.code, json.loads(body) if body else {}

    def import_students(self):
        return self.request(
            "/api/health/import",
            {
                "students": [
                    {"id": "S-0201", "name": "甲同学", "class_id": "C-02"},
                    {"id": "S-0202", "name": "乙同学", "class_id": "C-02"},
                    {"id": "S-1101", "name": "丙同学", "class_id": "C-11"},
                ]
            },
            "POST",
        )

    def add_record(self, student_id, temperature, note="", recheck_of=None):
        return self.request(
            "/api/health/records",
            {
                "student_id": student_id,
                "temperature_c": temperature,
                "source": "forehead",
                "note": note,
                "recheck_of": recheck_of,
            },
            "POST",
        )

    def test_students_import_records_and_persistence(self):
        status, students = self.request("/api/health/students")
        self.assertEqual(status, 200)
        self.assertEqual(students["students"], [])
        self.assertEqual(len(students["classes"]), 3)

        status, imported = self.import_students()
        self.assertEqual(status, 200)
        self.assertEqual(imported["imported"], 3)
        status, duplicate = self.import_students()
        self.assertEqual(status, 200)
        self.assertEqual(duplicate["skipped"], 3)

        status, students = self.request("/api/health/students")
        self.assertEqual(status, 200)
        self.assertEqual(len(students["students"]), 3)
        self.assertEqual(len(students["classes"]), 3)

        status, first = self.add_record("S-0201", 36.6, "正常")
        self.assertEqual(status, 201)
        self.assertEqual(first["record"]["temperature_c"], 36.6)
        status, high = self.add_record("S-0202", 37.6, "首次偏高")
        self.assertEqual(status, 201)
        status, recheck = self.add_record(
            "S-0202", 36.8, "复测正常", first["record"]["id"]
        )
        # recheck_of 必须指向同一学生的记录。
        self.assertEqual(status, 400)
        status, recheck = self.add_record(
            "S-0202", 36.8, "复测正常", high["record"]["id"]
        )
        self.assertEqual(status, 201)
        self.assertEqual(recheck["record"]["recheck_of"], high["record"]["id"])

        status, invalid = self.add_record("S-0201", 45)
        self.assertEqual(status, 400)

        status, records = self.request(
            f"/api/health/records?date={self.today}&class_id=C-02"
        )
        self.assertEqual(status, 200)
        self.assertEqual(len(records["records"]), 3)
        self.assertEqual(len(records["sources"]), 4)

        self.web.reload_health()
        self.assertEqual(len(self.web.health_student_snapshot()), 3)
        self.assertEqual(len(self.web.health_record_snapshot()), 3)

    def test_daily_report_uses_event_contract_and_class_filter(self):
        self.import_students()
        self.add_record("S-0201", 36.6)
        self.add_record("S-0202", 37.6)
        self.add_record("S-1101", 36.5)

        now = datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")
        status, event_a = self.request(
            "/api/events",
            {
                "event_type": "fall",
                "level": "urgent",
                "source": "rdk",
                "occurred_at": now,
                "summary": "小二班事件",
                "class_id": "C-02",
                "class_name": "小二班",
                "dedupe_key": "report-a",
            },
            "POST",
        )
        self.assertEqual(status, 201)
        status, event_b = self.request(
            "/api/events",
            {
                "event_type": "fight",
                "level": "watch",
                "source": "rdk",
                "occurred_at": now,
                "summary": "中一班事件",
                "class_id": "C-11",
                "class_name": "中一班",
                "dedupe_key": "report-b",
            },
            "POST",
        )
        self.assertEqual(status, 201)
        status, resolved = self.request(
            f"/api/events/{event_a['event']['id']}/status",
            {"status": "resolved", "handled_by": "测试老师"},
            "POST",
        )
        self.assertEqual(status, 200)
        self.assertEqual(resolved["event"]["status"], "resolved")

        status, report = self.request(
            f"/api/reports/daily?date={self.today}&class_id=C-02"
        )
        self.assertEqual(status, 200)
        data = report["report"]
        self.assertEqual(len(data["events"]), 1)
        self.assertEqual(data["events"][0]["id"], event_a["event"]["id"])
        self.assertEqual(data["events"][0]["level"], "high")
        self.assertEqual(data["events"][0]["status"], "handled")
        self.assertEqual(data["events"][0]["source"], "rdk")
        self.assertEqual(data["events"][0]["handler"], "测试老师")
        self.assertEqual(data["health"]["total"], 2)
        self.assertEqual(data["health"]["recheck"], 1)
        self.assertEqual(len(data["health"]["classes"]), 1)

        status, full = self.request(f"/api/reports/daily?date={self.today}")
        self.assertEqual(status, 200)
        self.assertEqual(len(full["report"]["events"]), 2)
        self.assertEqual(full["report"]["health"]["total"], 3)
        self.assertEqual(len(full["report"]["health"]["classes"]), 3)

        status, invalid = self.request("/api/reports/daily?date=not-a-date")
        self.assertEqual(status, 400)

    def test_cross_class_incident_appears_once_in_each_relevant_report(self):
        self.import_students()
        status, result = self.request("/api/events", {
            "event_type": "fight", "summary": "跨班斗殴",
        }, "POST")
        self.assertEqual(status, 201)
        event_id = result["event"]["id"]
        status, _ = self.request(f"/api/events/{event_id}/participants", {
            "student_ids": ["S-0201", "S-1101"],
        }, "POST")
        self.assertEqual(status, 200)

        for class_id in ("", "C-02", "C-11", "C-21"):
            with self.subTest(class_id=class_id):
                status, payload = self.request(f"/api/reports/daily?date={self.today}&class_id={class_id}")
                self.assertEqual(status, 200)
                ids = [event["id"] for event in payload["report"]["events"]]
                self.assertEqual(ids, [] if class_id == "C-21" else [event_id])
                for event in payload["report"]["events"]:
                    self.assertEqual(event["source"], "manual")

    def test_infrared_device_reading_is_ingested_deduplicated_and_published(self):
        self.import_students()
        measured_at = datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")
        reading = {
            "connected": True,
            "stable": True,
            "student_id": "S-0201",
            "device_id": "ir-test-01",
            "reading_id": "IR-0001",
            "timestamp": measured_at,
            "properties": {"mlx_obj": 36.7, "mlx_amb": 24.8},
        }
        device_headers = {"X-Device-Token": self.web.HEALTH_DEVICE_TOKEN}
        status, first = self.request(
            "/api/health/device-readings",
            reading,
            "POST",
            device_headers,
            authenticated=False,
        )
        self.assertEqual(status, 201)
        self.assertTrue(first["stored"])
        self.assertEqual(first["record"]["source"], "infrared")
        self.assertEqual(first["record"]["origin"], "device")
        self.assertEqual(first["record"]["device_id"], "ir-test-01")
        self.assertEqual(first["record"]["ambient_c"], 24.8)

        status, duplicate = self.request(
            "/api/health/device-readings",
            reading,
            "POST",
            device_headers,
            authenticated=False,
        )
        self.assertEqual(status, 200)
        self.assertTrue(duplicate["duplicate"])
        self.assertEqual(duplicate["record"]["id"], first["record"]["id"])
        self.assertEqual(len(self.web.health_record_snapshot()), 1)

        with patch.object(self.web, "read_rdk_json", return_value=reading):
            status, realtime = self.request("/api/health/realtime")
        self.assertEqual(status, 200)
        self.assertTrue(realtime["source_available"])
        self.assertEqual(realtime["reading"]["temperature_c"], 36.7)
        self.assertEqual(realtime["reading"]["student_id"], "S-0201")
        self.assertTrue(realtime["ingest"]["duplicate"])

    def test_device_ingestion_requires_token_and_keeps_unassigned_reading_live(self):
        reading = {
            "connected": True,
            "timestamp": datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds"),
            "properties": {"mlx_obj": 36.6},
        }
        status, body = self.request(
            "/api/health/device-readings",
            reading,
            "POST",
            {"X-Device-Token": "wrong-device-token-000000000000"},
            authenticated=False,
        )
        self.assertEqual(status, 403)
        self.assertFalse(body["ok"])

        status, result = self.request(
            "/api/health/device-readings",
            reading,
            "POST",
            {"X-Device-Token": self.web.HEALTH_DEVICE_TOKEN},
            authenticated=False,
        )
        self.assertEqual(status, 200)
        self.assertFalse(result["stored"])
        self.assertEqual(result["reason"], "unassigned")
        self.assertEqual(result["reading"]["status"], "unassigned")
        self.assertEqual(len(self.web.health_record_snapshot()), 0)

        with patch.object(
            self.web,
            "read_rdk_json",
            side_effect=urllib.error.URLError("offline"),
        ):
            status, fallback = self.request("/api/health/realtime")
        self.assertEqual(status, 200)
        self.assertFalse(fallback["source_available"])
        self.assertEqual(fallback["reading"]["temperature_c"], 36.6)
        self.assertEqual(fallback["reading"]["status"], "unassigned")

    def test_out_of_range_infrared_can_be_confirmed_and_reloaded(self):
        self.import_students()
        reading = {
            "connected": True,
            "stable": True,
            "student_id": "S-0201",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "properties": {"mlx_obj": 22.5},
        }
        with patch.object(self.web, "read_rdk_json", return_value=reading):
            status, realtime = self.request("/api/health/realtime")
        self.assertEqual(status, 200)
        self.assertEqual(realtime["reading"]["temperature_c"], 22.5)
        self.assertTrue(realtime["reading"]["fresh"])
        self.assertFalse(realtime["ingest"]["stored"])

        headers = {"X-Device-Token": self.web.HEALTH_DEVICE_TOKEN}
        status, pushed = self.request(
            "/api/health/device-readings", reading, "POST", headers, authenticated=False,
        )
        self.assertEqual(status, 200)
        self.assertEqual(pushed["reason"], "invalid_temperature")
        self.assertFalse(pushed["stored"])
        self.assertEqual(self.add_record("S-0201", 22.5)[0], 400)

        status, saved = self.request(
            "/api/health/records",
            {"student_id": "S-0201", "source": "infrared", "temperature_c": 22.5},
            "POST",
        )
        self.assertEqual(status, 201)
        self.assertEqual(saved["record"]["temperature_c"], 22.5)
        self.assertEqual(self.web.load_health_records(), [saved["record"]])
        for invalid in (True, "NaN", "Infinity"):
            status, _ = self.request(
                "/api/health/records",
                {"student_id": "S-0201", "source": "infrared", "temperature_c": invalid},
                "POST",
            )
            self.assertEqual(status, 400)

    def test_realtime_get_is_read_only_and_push_rejects_unverified_samples(self):
        self.import_students()
        reading = {
            "connected": True,
            "stable": True,
            "student_id": "S-0201",
            "device_id": "ir-test",
            "reading_id": "IR-GUARD",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "properties": {"mlx_obj": 36.6},
        }
        with patch.object(self.web, "read_rdk_json", return_value=reading):
            status, realtime = self.request("/api/health/realtime")
        self.assertEqual(status, 200)
        self.assertEqual(realtime["reading"]["status"], "ready")
        self.assertFalse(realtime["ingest"]["stored"])
        self.assertEqual(self.web.health_record_snapshot(), [])

        headers = {"X-Device-Token": self.web.HEALTH_DEVICE_TOKEN}
        future = (datetime.now(timezone.utc) + timedelta(minutes=1)).isoformat()
        for fields, reason in (({"stable": None}, "stability_unknown"),
                               ({"connected": None}, "connection_unknown"),
                               ({"timestamp": future}, "timestamp_future")):
            status, result = self.request("/api/health/device-readings",
                                          {**reading, **fields}, "POST", headers, authenticated=False)
            self.assertEqual(status, 200)
            self.assertFalse(result["stored"])
            self.assertEqual(result["reason"], reason)
        self.assertEqual(self.web.health_record_snapshot(), [])

        for device_id in ("ir-test", "ir-test-2"):
            status, result = self.request("/api/health/device-readings",
                                          {**reading, "device_id": device_id}, "POST", headers, authenticated=False)
            self.assertEqual(status, 201)
            self.assertTrue(result["stored"])
        self.web.reload_health()
        self.assertEqual(len(self.web.health_record_snapshot()), 2)


if __name__ == "__main__":
    unittest.main()
