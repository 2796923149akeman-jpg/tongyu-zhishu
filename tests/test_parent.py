"""家长账号、家长端异常事件页与后台管理的隔离测试。"""

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
        "test_dashboard_parent", ROOT / "dashboard" / "server.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class ParentAccountTests(unittest.TestCase):
    def setUp(self):
        self.web = load_server()
        self.temp = tempfile.TemporaryDirectory()
        self.web.AUTH = self.web.AccessStore(Path(self.temp.name) / "auth_config.json", secure=False)
        self.web.AUTH.create_user("owner", "owner-fixture", role="admin")
        self.web.EVENTS_FILE = Path(self.temp.name) / "events.json"
        self.web.EVIDENCE_DIR = Path(self.temp.name) / "evidence"
        self.web.EVIDENCE_DIR.mkdir()
        self.web.HEALTH_STUDENTS_FILE = Path(self.temp.name) / "health_students.json"
        self.web.HEALTH_STUDENTS_FILE.write_text(
            json.dumps([
                {"id": "S-0201", "name": "陈小满", "class_id": "C-02", "class_name": "小二班", "active": True},
                {"id": "S-0202", "name": "王一诺", "class_id": "C-02", "class_name": "小二班", "active": True},
            ], ensure_ascii=False),
            encoding="utf-8",
        )
        self.web.reload_events()
        self.web.reload_health()
        self.web.Handler.log_message = lambda *args: None
        self.http = self.web.ThreadingHTTPServer(("127.0.0.1", 0), self.web.Handler)
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.http.server_port}"
        self.opener = urllib.request.build_opener(NoRedirect)

    def tearDown(self):
        self.http.shutdown()
        self.http.server_close()
        self.thread.join()
        self.temp.cleanup()

    def login_headers(self, username="owner", password="owner-fixture"):
        token, session = self.web.AUTH.new_session(username.casefold())
        return {
            "Cookie": "tongyu_session=" + token,
            "X-CSRF-Token": session["csrf"],
            "Content-Type": "application/json",
        }

    def request(self, path, payload=None, method="GET", headers=None):
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = urllib.request.Request(
            self.base + path,
            data=data,
            headers=headers or self.login_headers(),
            method=method,
        )

        def parse(body, content_type):
            if body and content_type == "application/json":
                return json.loads(body)
            if content_type.startswith("text/"):
                return body.decode("utf-8", "replace")
            return body

        try:
            with self.opener.open(request, timeout=5) as response:
                body = response.read()
                return response.status, parse(body, response.headers.get_content_type()), dict(response.headers)
        except urllib.error.HTTPError as exc:
            body = exc.read()
            return exc.code, parse(body, exc.headers.get_content_type()), dict(exc.headers)

    def create_event(self, event_type="fall", students=(), dedupe_key="parent-1"):
        payload = {
            "event_type": event_type,
            "level": "urgent",
            "source": "rdk",
            "status": "pending",
            "occurred_at": self.web.now_iso(),
            "summary": "检测到疑似摔倒" if event_type == "fall" else "检测到疑似斗殴",
            "detail": "测试事件",
            "location": "活动室 A",
            "dedupe_key": dedupe_key,
            "students": [{"id": sid, "name": name} for sid, name in students],
        }
        return self.request("/api/events", payload, "POST")

    def test_parent_scope_limits_pages_and_apis(self):
        self.web.AUTH.create_user("parent1", "parent-fixture", role="parent", students=["S-0201"])
        headers = self.login_headers("parent1", "parent-fixture")

        status, body, _ = self.request("/parent", headers=headers)
        self.assertEqual(status, 200)
        self.assertIn("孩子的异常事件", body)

        status, _, response = self.request("/", headers=headers)
        self.assertEqual(status, 303)
        self.assertEqual(response["Location"], "/parent")

        for path in ("/api/events", "/api/health/students", "/api/admin/parents", "/api/reports/daily"):
            status, body, _ = self.request(path, headers=headers)
            self.assertEqual(status, 403, path)

        status, body, _ = self.request(
            "/api/events", {"event_type": "fall"}, "POST", headers
        )
        self.assertEqual(status, 403)

    def test_parent_sees_only_own_children_events(self):
        self.web.AUTH.create_user("parent1", "parent-fixture", role="parent", students=["S-0201"])
        self.web.AUTH.create_user("parent2", "parent-fixture", role="parent", students=["S-0202"])
        self.create_event("fall", [("S-0201", "陈小满")], "pf-1")
        self.create_event("fight", [("S-0201", "陈小满"), ("S-0202", "王一诺")], "pf-2")

        status, body, _ = self.request("/api/parent/events", headers=self.login_headers("parent1", "parent-fixture"))
        self.assertEqual(status, 200)
        self.assertEqual(body["children"], [{"id": "S-0201", "name": "陈小满"}])
        self.assertEqual(len(body["events"]), 2)
        fight = next(item for item in body["events"] if item["event_type"] == "fight")
        self.assertEqual(fight["students"], [{"id": "S-0201", "name": "陈小满"}])

        status, body, _ = self.request("/api/parent/events", headers=self.login_headers("parent2", "parent-fixture"))
        self.assertEqual(len(body["events"]), 1)
        self.assertEqual(body["events"][0]["event_type"], "fight")
        self.assertEqual(body["events"][0]["students"], [{"id": "S-0202", "name": "王一诺"}])

    def test_parent_event_history_redacts_other_children_names(self):
        self.web.AUTH.create_user("parent1", "parent-fixture", role="parent", students=["S-0201"])
        self.create_event("fight", [("S-0201", "陈小满"), ("S-0202", "王一诺")], "pf-3")
        with self.web.EVENTS_LOCK:
            event = self.web.EVENTS[0]
            event["history"].append({
                "at": self.web.now_iso(),
                "action": "关联学生",
                "by": "李老师",
                "note": "陈小满、王一诺",
            })
            self.web.save_events()

        status, body, _ = self.request("/api/parent/events", headers=self.login_headers("parent1", "parent-fixture"))
        assign = next(item for item in body["events"][0]["history"] if item["action"] == "关联学生")
        self.assertNotIn("王一诺", assign["note"])
        self.assertEqual(assign["note"], "老师已登记 2 名涉及学生")

    def test_parent_evidence_access_is_limited_to_own_children(self):
        self.web.AUTH.create_user("parent1", "parent-fixture", role="parent", students=["S-0201"])
        self.web.AUTH.create_user("parent2", "parent-fixture", role="parent", students=["S-0202"])
        self.create_event("fall", [("S-0201", "陈小满")], "pf-4")
        image = b"\x89PNG\r\n\x1a\nfixture"
        (self.web.EVIDENCE_DIR / "pf-4.png").write_bytes(image)
        with self.web.EVENTS_LOCK:
            self.web.EVENTS[0]["evidence_url"] = "/evidence/pf-4.png"
            self.web.save_events()

        status, _, _ = self.request("/evidence/pf-4.png", headers=self.login_headers("parent1", "parent-fixture"))
        self.assertEqual(status, 200)
        status, body, _ = self.request("/evidence/pf-4.png", headers=self.login_headers("parent2", "parent-fixture"))
        self.assertEqual(status, 403)
        self.assertFalse(body["ok"])

    def test_admin_parent_management_api(self):
        self.web.AUTH.create_user("parent1", "parent-fixture", role="parent", students=["S-0201"])
        status, body, _ = self.request("/api/admin/parents")
        self.assertEqual(status, 200)
        self.assertEqual(
            body["parents"],
            [{"username": "parent1", "students": [{"id": "S-0201", "name": "陈小满"}]}],
        )

        status, body, _ = self.request(
            "/api/admin/parents",
            {"username": "parent2", "password": "parent-fixture", "student_ids": ["S-0202", "S-0202"]},
            "POST",
        )
        self.assertEqual(status, 201)

        status, body, _ = self.request(
            "/api/admin/parents",
            {"username": "parent3", "password": "parent-fixture", "student_ids": ["S-9999"]},
            "POST",
        )
        self.assertEqual(status, 400)

        status, body, _ = self.request(
            "/api/admin/parents",
            {"username": "parent1", "password": "parent-fixture", "student_ids": ["S-0201"]},
            "POST",
        )
        self.assertEqual(status, 400)

        status, body, _ = self.request("/parent", headers=self.login_headers("parent2", "parent-fixture"))
        self.assertEqual(status, 200)

    def test_parent_role_validation_in_access_store(self):
        with self.assertRaises(ValueError):
            self.web.AUTH.create_user("bad1", "fixture-pass", role="nurse")
        with self.assertRaises(ValueError):
            self.web.AUTH.create_user("bad2", "fixture-pass", role="parent", students=[])
        with self.assertRaises(ValueError):
            self.web.AUTH.create_user("bad3", "fixture-pass", role="parent", students=["x"])
        self.web.AUTH.create_user("ok1", "fixture-pass", role="parent", students=["S-0202", "S-0201"])
        self.assertEqual(self.web.AUTH.users["ok1"]["students"], ["S-0201", "S-0202"])
        user = self.web.AUTH.public_user({"username": "ok1"})
        self.assertEqual(user["role"], "parent")
        self.assertEqual(user["students"], ["S-0201", "S-0202"])


if __name__ == "__main__":
    unittest.main()
