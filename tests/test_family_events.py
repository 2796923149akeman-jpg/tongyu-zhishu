"""Parent-scoped event API and evidence authorization tests."""

import importlib.util
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path


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
        self.web.EVENTS_FILE = root / "events.json"
        self.web.HEALTH_STUDENTS_FILE = root / "health_students.json"
        self.web.HEALTH_RECORDS_FILE = root / "health_records.json"
        self.web.DIALOGUE_DATA_FILE = root / "dialogue_messages.json"
        self.web.DIALOGUE_CONFIG_FILE = root / "dialogue_config.json"
        self.web.ANALYSIS_CONFIG_FILE = root / "analysis_config.json"
        self.web.CONVERSATION_SUMMARIES_FILE = root / "conversation_summaries.json"
        self.web.PROJECT_ROOT = root
        (root / "xiaozhi-server" / "data").mkdir(parents=True)
        self.web.HEALTH_STUDENTS[:] = [
            {"id": "S-0201", "name": "张小明", "class_id": "C-02", "class_name": "小二班", "active": True},
            {"id": "S-0202", "name": "李小红", "class_id": "C-02", "class_name": "小二班", "active": True},
            {"id": "S-0301", "name": "王小明", "class_id": "C-11", "class_name": "中一班", "active": True},
        ]
        self.web.HEALTH_RECORDS[:] = []
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

    def request(self, path, headers=None):
        request = urllib.request.Request(self.base + path, headers=headers or {})
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


if __name__ == "__main__":
    unittest.main()
