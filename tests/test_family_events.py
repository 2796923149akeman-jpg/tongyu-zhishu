"""Parent-scoped event API and evidence authorization tests."""

import importlib.util
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load_server():
    spec = importlib.util.spec_from_file_location(
        "test_family_events_server",
        ROOT / "dashboard" / "server.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FamilyEventApiTests(unittest.TestCase):
    def setUp(self):
        self.web = load_server()
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.web.AUTH = self.web.AccessStore(root / "auth_config.json", secure=False)
        self.web.DATA.events.path = root / "events.json"
        self.web.DATA.students.path = root / "health_students.json"
        self.web.DATA.health_records.path = root / "health_records.json"
        self.web.DATA.messages.path = root / "dialogue_messages.json"
        self.web.DIALOGUE_CONFIG_FILE = root / "dialogue_config.json"
        self.web.ANALYSIS_CONFIG_FILE = root / "analysis_config.json"
        self.web.DATA.summaries.path = root / "conversation_summaries.json"
        self.web.PROJECT_ROOT = root
        (root / "xiaozhi-server" / "data").mkdir(parents=True)
        self.web.HEALTH_STUDENTS[:] = [
            {"id": "S-0201", "name": "张小明", "class_id": "C-02", "class_name": "小二班", "active": True},
            {"id": "S-0202", "name": "李小红", "class_id": "C-02", "class_name": "小二班", "active": True},
            {"id": "S-0301", "name": "王小明", "class_id": "C-11", "class_name": "中一班", "active": True},
        ]
        self.web.HEALTH_RECORDS[:] = []
        self.web.MESSAGES.clear()
        self.web.reload_events()
        self.web.AUTH.create_user(
            "parent-one",
            "parent-one-password",
            role="parent",
            bound_student_ids=["S-0201", "S-0202"],
        )
        self.web.AUTH.create_user(
            "parent-two",
            "parent-two-password",
            role="parent",
            bound_student_ids=["S-0301"],
        )
        self.parent_one = self.auth_headers("parent-one", "parent-one-password")
        self.parent_two = self.auth_headers("parent-two", "parent-two-password")
        self.web.Handler.log_message = lambda *args: None
        self.http = self.web.ThreadingHTTPServer(("127.0.0.1", 0), self.web.Handler)
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.http.server_port}"

        self.fall = self.create_visible_event(
            "fall",
            "S-0201",
            "张小明",
            "fall-parent-one",
        )
        self.fight = self.create_visible_event(
            "fight",
            "S-0201",
            "张小明",
            "fight-parent-one",
            extra=("S-0301", "王小明"),
        )
        self.unrelated = self.create_visible_event(
            "fall",
            "S-0301",
            "王小明",
            "fall-parent-two",
        )
        unassigned_result, _ = self.web.create_event({
            "event_type": "fall",
            "level": "urgent",
            "source": "rdk",
            "status": "pending",
            "occurred_at": "2026-11-04T10:00:00+08:00",
            "summary": "未关联事件",
        })
        self.unassigned = unassigned_result["event"]

    def auth_headers(self, username, password):
        token, session = self.web.AUTH.new_session(username)
        return {
            "Cookie": "tongyu_session=" + token,
            "X-CSRF-Token": session["csrf"],
        }

    def create_visible_event(self, event_type, student_id, student_name, dedupe, extra=None):
        participants = [{
            "student_id": student_id,
            "student_name": student_name,
            "input_name": student_name,
        }]
        if extra:
            participants.append({
                "student_id": extra[0],
                "student_name": extra[1],
                "input_name": extra[1],
            })
        result, _ = self.web.create_event({
            "event_type": event_type,
            "level": "urgent",
            "source": "rdk",
            "status": "pending",
            "occurred_at": "2026-11-04T10:00:00+08:00",
            "summary": f"{event_type}-{student_name}",
            "detail": "内部记录：张小明 王小明，家长不应看到自由文本姓名",
            "note": "内部老师备注，家长不应看到",
            "dedupe_key": dedupe,
            "participants": participants,
            "parent_visible_at": "2026-11-04T10:01:00+08:00",
        })
        return result["event"]

    def tearDown(self):
        self.http.shutdown()
        self.http.server_close()
        self.thread.join()
        self.temp.cleanup()

    def request(self, path, headers=None, payload=None):
        headers = dict(headers or {})
        if payload is not None:
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(self.base + path, headers=headers,
                                         data=None if payload is None else json.dumps(payload).encode())
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status, response.headers, response.read()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.headers, exc.read()

    def test_parent_sees_only_their_children_and_own_participant_names(self):
        status, _, body = self.request("/api/family/events", self.parent_one)
        self.assertEqual(status, 200)
        payload = json.loads(body)
        self.assertEqual(
            {event["id"] for event in payload["events"]},
            {self.fall["id"], self.fight["id"]},
        )
        fight = next(event for event in payload["events"] if event["id"] == self.fight["id"])
        self.assertEqual(
            [person["student_id"] for person in fight["participants"]],
            ["S-0201"],
        )
        self.assertNotIn("王小明", json.dumps(fight, ensure_ascii=False))

        status, _, body = self.request("/api/family/events", self.parent_two)
        self.assertEqual(status, 200)
        payload = json.loads(body)
        self.assertEqual(
            {event["id"] for event in payload["events"]},
            {self.fight["id"], self.unrelated["id"]},
        )
        fight = next(event for event in payload["events"] if event["id"] == self.fight["id"])
        self.assertEqual(
            [person["student_id"] for person in fight["participants"]],
            ["S-0301"],
        )
        self.assertEqual(
            [person["student_name"] for person in fight["participants"]],
            ["王小明"],
        )
        self.assertNotIn("内部记录", json.dumps(fight, ensure_ascii=False))
        self.assertNotIn("内部老师备注", json.dumps(fight, ensure_ascii=False))

    def test_parent_cannot_read_another_family_or_general_events(self):
        self.assertEqual(
            self.request(f"/api/family/events/{self.unrelated['id']}", self.parent_one)[0],
            404,
        )
        self.assertEqual(self.request("/api/events", self.parent_one)[0], 403)
        self.assertEqual(self.request("/events.html", self.parent_one)[0], 403)
        self.assertEqual(self.request("/api/family/events")[0], 401)

    def test_snapshot_is_scoped_and_requires_parent_visibility(self):
        path = self.web.event_snapshot_path(self.fall["id"])
        path.parent.mkdir(parents=True, exist_ok=True)
        image = b"\xff\xd8\xffparent-scoped\xff\xd9"
        path.write_bytes(image)
        status, headers, body = self.request(
            f"/api/family/events/{self.fall['id']}/snapshot",
            self.parent_one,
        )
        self.assertEqual(status, 200)
        self.assertEqual(headers.get_content_type(), "image/jpeg")
        self.assertEqual(body, image)
        self.assertEqual(
            self.request(
                f"/api/family/events/{self.fall['id']}/snapshot",
                self.parent_two,
            )[0],
            404,
        )

    def test_unassigned_events_are_never_exposed_to_parent(self):
        status, _, body = self.request("/api/family/events", self.parent_one)
        self.assertEqual(status, 200)
        ids = {event["id"] for event in json.loads(body)["events"]}
        self.assertNotIn(self.unassigned["id"], ids)

    def test_parent_event_page_is_served_and_uses_scoped_endpoints(self):
        status, headers, body = self.request("/family-events.html", self.parent_one)
        self.assertEqual(status, 200)
        self.assertEqual(headers.get_content_type(), "text/html")
        text = body.decode("utf-8")
        self.assertIn("孩子异常事件", text)
        self.assertIn('id="eventList"', text)
        self.assertIn("/api/family/events", text)
        self.assertIn("/snapshot", text)


    def test_family_report_only_contains_the_requested_bound_child(self):
        self.web.HEALTH_RECORDS[:] = [
            {"student_id": student_id, "measured_at": "2026-11-04T09:00:00+08:00", "temperature_c": temperature}
            for student_id, temperature in [("S-0201", 36.4), ("S-0202", 36.8), ("S-0301", 37.0)]
        ]
        self.web.MESSAGES.extend([
            {"id": "first", "role": "user", "text": "本人已关联",
             "created_at": "2026-11-04T09:30:00+08:00"},
            {"role": "user", "text": "未明确开放", "student_id": "S-0201",
             "created_at": "2026-11-04T09:30:00+08:00"},
            {"role": "user", "text": "另一个孩子", "family_student_id": "S-0202",
             "created_at": "2026-11-04T09:30:00+08:00"},
        ])
        path = "/api/family/daily?date=2026-11-04&student_id="
        tag = {"id": "first", "student_id": "S-0201"}
        self.assertEqual(self.request("/api/dialogue/student", self.parent_one, tag)[0], 403)
        self.web.AUTH.create_user("teacher", "teacher-password", role="admin")
        admin = self.auth_headers("teacher", "teacher-password")
        self.assertEqual(self.request("/api/dialogue/student", admin, tag)[0], 200)
        self.assertEqual(self.request(path + "S-0301", self.parent_one)[0], 403)
        self.assertEqual(self.request("/api/reports/daily", self.parent_one)[0], 403)
        _, _, body = self.request(path + "S-0201", self.parent_one)
        self.assertEqual(json.loads(body)["report"]["dialogues"], [])
        access = {"events": True, "snapshots": False, "reports": True, "dialogues": True}
        self.web.AUTH.update_parent_bindings("parent-one", ["S-0201", "S-0202"], access)
        _, _, body = self.request(path + "S-0201", self.parent_one)
        report = json.loads(body)["report"]
        self.assertEqual([item["temperature_c"] for item in report["readings"]], [36.4])
        self.assertEqual([item["text"] for item in report["dialogues"]], ["本人已关联"])
        self.assertEqual({event["id"] for event in report["events"]}, {self.fall["id"], self.fight["id"]})
        access["reports"] = False
        self.web.AUTH.update_parent_bindings("parent-one", ["S-0201"], access)
        self.assertEqual(self.request(path + "S-0201", self.parent_one)[0], 403)

    def test_dialogue_batch_assignment_is_atomic_and_admin_only(self):
        self.web.MESSAGES.extend([
            {"id": "first", "role": "user", "text": "用户消息"},
            {"id": "second", "role": "assistant", "text": "设备回复"},
            {"id": "untouched", "role": "user", "text": "其他消息", "family_student_id": "S-0301"},
        ])
        self.web.AUTH.create_user("teacher", "teacher-password", role="admin")
        admin = self.auth_headers("teacher", "teacher-password")
        path = "/api/dialogue/student"
        payload = {"ids": ["first", "second", "first"], "student_id": "S-0201"}
        self.assertEqual(self.request(path, self.parent_one, payload)[0], 403)
        self.assertEqual(self.request(path, admin, {**payload, "ids": []})[0], 400)
        self.assertEqual(self.request(path, admin, {**payload, "ids": ["first", "missing"]})[0], 404)
        self.assertNotIn("family_student_id", self.web.MESSAGES[0])
        self.assertFalse(self.web.DATA.messages.path.exists())

        self.assertEqual(self.request(path, admin, payload)[0], 200)
        saved = json.loads(self.web.DATA.messages.path.read_text(encoding="utf-8"))
        self.assertEqual([message.get("family_student_id") for message in saved], ["S-0201", "S-0201", "S-0301"])
        for message in saved[:2]:
            self.assertEqual(message["student_id"], "S-0201")
            self.assertEqual(message["class_id"], "C-02")

        self.assertEqual(self.request(path, admin, {**payload, "student_id": ""})[0], 200)
        self.assertEqual([message.get("family_student_id") for message in self.web.MESSAGES], ["", "", "S-0301"])

    def prepare_dialogue_assignment(self):
        self.web.MESSAGES.extend([{"id": "first", "role": "user", "text": "测试消息"}])
        self.web.DATA.messages.save(list(self.web.MESSAGES))
        self.web.AUTH.create_user("teacher", "teacher-password", role="admin")
        return self.auth_headers("teacher", "teacher-password")

    def test_batch_assignment_rejects_invalid_inputs_without_writing(self):
        admin = self.prepare_dialogue_assignment()
        before = self.web.DATA.messages.path.read_bytes()
        self.web.HEALTH_STUDENTS[1]["active"] = False
        invalid = [
            {"ids": "first", "student_id": "S-0201"},
            {"ids": [None], "student_id": "S-0201"},
            {"ids": [""], "student_id": "S-0201"},
            {"ids": ["first"] * (self.web.DIALOGUE_LIMIT + 1), "student_id": "S-0201"},
            {"id": "first", "ids": ["first"], "student_id": "S-0201"},
            {"ids": ["first"], "student_id": "unknown"},
            {"ids": ["first"], "student_id": "S-0202"},
            {"ids": ["first"], "student_id": None},
        ]
        for payload in invalid:
            with self.subTest(payload=payload):
                self.assertEqual(self.request("/api/dialogue/student", admin, payload)[0], 400)
                self.assertEqual(self.web.DATA.messages.path.read_bytes(), before)
                self.assertNotIn("student_id", self.web.MESSAGES[0])

    def test_batch_assignment_requires_csrf_and_same_origin(self):
        admin = self.prepare_dialogue_assignment()
        before = self.web.DATA.messages.path.read_bytes()
        payload = {"ids": ["first"], "student_id": "S-0201"}
        for headers in (
            {"Cookie": admin["Cookie"]},
            {**admin, "X-CSRF-Token": "invalid"},
            {**admin, "Origin": "https://untrusted.example"},
        ):
            with self.subTest(headers=headers):
                self.assertEqual(self.request("/api/dialogue/student", headers, payload)[0], 403)
                self.assertEqual(self.web.DATA.messages.path.read_bytes(), before)
                self.assertNotIn("student_id", self.web.MESSAGES[0])

    def test_single_assignment_and_batch_reassignment_persist(self):
        admin = self.prepare_dialogue_assignment()
        path = "/api/dialogue/student"
        self.assertEqual(self.request(path, admin, {"id": "first", "student_id": "S-0201"})[0], 200)
        self.assertEqual(self.request(path, admin, {"ids": ["first"], "student_id": "S-0301"})[0], 200)
        saved = self.web.DATA.messages.load()
        self.assertEqual(saved, list(self.web.MESSAGES))
        self.assertEqual(saved[0]["student_id"], "S-0301")
        self.assertEqual(saved[0]["family_student_id"], "S-0301")
        self.assertEqual(saved[0]["class_id"], "C-11")

    def test_disabling_snapshots_revokes_direct_image_access(self):
        path = self.web.event_snapshot_path(self.fall["id"])
        path.parent.mkdir(parents=True)
        path.write_bytes(b"\xff\xd8\xff\xd9")
        self.web.AUTH.update_parent_bindings("parent-one", ["S-0201"],
                                             {"events": True, "snapshots": False, "reports": True, "dialogues": False})
        route = "/api/family/events/" + self.fall["id"]
        self.assertFalse(json.loads(self.request(route, self.parent_one)[2])["event"]["has_snapshot"])
        self.assertEqual(self.request(route + "/snapshot", self.parent_one)[0], 404)

    def test_merchant_receives_only_allowlisted_sensor_fields(self):
        self.web.AUTH.create_user("merchant", "merchant-password", role="merchant")
        merchant = self.auth_headers("merchant", "merchant-password")
        data = {"properties": {"sht_t": "24.5", "mlx_obj": 36.5, "student_id": "S-0201",
                               "sht_h": "NaN"}, "video_url": "private"}
        with patch.object(self.web, "read_rdk_json", return_value=data):
            status, _, body = self.request("/api/merchant/sensors", merchant)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["readings"], {"sht_t": 24.5})
        self.assertEqual(self.request("/sensors.html", merchant)[0], 200)
        for route in ("/api/rdk/sensors", "/api/rdk/video_feed", "/api/dialogue/messages",
                      "/api/health/records", "/api/family/events", "/api/reports/daily"):
            self.assertEqual(self.request(route, merchant)[0], 403, route)

    def test_temperature_trend_uses_latest_per_child_and_keeps_gaps(self):
        records = [
            {"student_id": "S-0201", "measured_at": "2026-11-02T08:00:00+08:00", "temperature_c": 35.5},
            {"student_id": "S-0201", "measured_at": "2026-11-02T10:00:00+08:00", "temperature_c": 36.5},
            {"student_id": "S-0301", "measured_at": "2026-11-02T10:00:00+08:00", "temperature_c": 39.0},
            {"student_id": "S-0201", "measured_at": "2026-11-04T10:00:00+08:00", "temperature_c": 37.5},
        ]
        result = self.web.temperature_trend("2026-11-04", records, {"S-0201"})
        self.assertEqual([point["mean_c"] for point in result[-3:]], [36.5, None, 37.5])
        self.assertEqual([point["count"] for point in result[-3:]], [1, 0, 1])

    def test_legacy_student_links_are_kept_for_teacher_review(self):
        event = dict(self.unassigned)
        del event["participants"]
        event["students"] = [{"id": "S-0201", "name": "张小明"}]
        self.web.EVIDENCE_DIR = self.web.DATA.events.path.parent / "evidence"
        self.web.EVIDENCE_DIR.mkdir()
        filename = event["id"] + ".jpg"
        image = b"\xff\xd8legacy\xff\xd9"
        (self.web.EVIDENCE_DIR / filename).write_bytes(image)
        event["evidence_url"] = "/evidence/" + filename
        self.web.atomic_write_json(self.web.DATA.events.path, [event])
        self.web.reload_events()
        self.assertEqual(self.web.get_event(event["id"])["participants"][0]["student_id"], "S-0201")
        route = "/api/family/events/" + event["id"]
        self.assertEqual(self.request(route, self.parent_one)[0], 404)
        with patch.object(self.web.DATA.events, "save", side_effect=OSError("write failed")):
            with self.assertRaises(OSError):
                self.web.assign_event_participants(event["id"], {"names": "张小明"})
        self.assertEqual(self.request(route, self.parent_one)[0], 404)
        self.web.assign_event_participants(event["id"], {"student_ids": ["S-0201"], "share_snapshot": True})
        self.assertEqual(self.request(route, self.parent_one)[0], 200)
        self.assertEqual(self.request(route + "/snapshot", self.parent_one)[2], image)
        self.web.change_event_status(event["id"], {"status": "false_alarm"})
        self.web.change_event_status(event["id"], {"status": "pending"})
        self.assertEqual(self.request(route, self.parent_one)[0], 404)

    def test_snapshot_requires_event_permission_and_uses_stable_student_ids(self):
        self.web.update_student_nickname("S-0201", "小满")
        self.web.update_student_nickname("S-0301", "小满")
        path = self.web.event_snapshot_path(self.fall["id"])
        path.parent.mkdir(parents=True)
        image = b"\xff\xd8new-snapshot\xff\xd9"
        path.write_bytes(image)
        route = "/api/family/events/" + self.fall["id"]
        self.web.assign_event_participants(self.fall["id"], {"student_ids": ["S-0201"]})
        payload = json.loads(self.request(route, self.parent_one)[2])
        self.assertEqual(payload["event"]["participants"], [{"student_id": "S-0201", "student_name": "小满"}])
        self.assertEqual(self.request(route + "/snapshot", self.parent_one)[0], 404)
        self.assertEqual(self.request(route, self.parent_two)[0], 404)
        self.web.assign_event_participants(self.fall["id"], {"student_ids": ["S-0201"], "share_snapshot": True})
        self.assertEqual(self.request(route + "/snapshot", self.parent_one)[2], image)
        self.assertEqual(self.request(route + "/snapshot", self.parent_two)[0], 404)


if __name__ == "__main__":
    unittest.main()
