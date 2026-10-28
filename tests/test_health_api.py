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
        temp = Path(self.temp.name)
        self.web.DIALOGUE_DATA_FILE = temp / "dialogue_messages.json"
        self.web.DIALOGUE_CONFIG_FILE = temp / "dialogue_config.json"
        self.web.ANALYSIS_CONFIG_FILE = temp / "analysis_config.json"
        self.web.CONVERSATION_SUMMARIES_FILE = temp / "conversation_summaries.json"
        self.web.PROJECT_ROOT = temp
        self.web.EVENTS_FILE = temp / "events.json"
        self.web.HEALTH_STUDENTS_FILE = temp / "health_students.json"
        self.web.HEALTH_RECORDS_FILE = temp / "health_records.json"
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

    def request(self, path, payload=None, method="GET"):
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        headers = {"Content-Type": "application/json"} if data else {}
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


if __name__ == "__main__":
    unittest.main()
