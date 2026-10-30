"""疑似成人/儿童估算规则和缓存接口测试。"""

import importlib.util
import json
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "dashboard"))

import person_type  # noqa: E402


def make_keypoints(shoulder_y, ankle_y):
    points = [[0.0, 0.0] for _ in range(17)]
    scores = [1.0] * 17
    points[0] = [80.0, 10.0]  # nose/head top
    points[5] = [60.0, shoulder_y]
    points[6] = [100.0, shoulder_y]
    points[11] = [70.0, 70.0]
    points[12] = [90.0, 70.0]
    points[15] = [60.0, ankle_y]
    points[16] = [100.0, ankle_y]
    return points, scores


class PersonTypeHeuristicTests(unittest.TestCase):
    def test_child_adult_and_uncertain_ratios(self):
        child_points, child_scores = make_keypoints(36, 170)
        child = person_type.estimate_person_type(child_points, child_scores, [50, 0, 110, 180])
        self.assertEqual(child["person_type"], "child")

        adult_points, adult_scores = make_keypoints(20, 180)
        adult = person_type.estimate_person_type(adult_points, adult_scores, [50, 0, 110, 180])
        self.assertEqual(adult["person_type"], "adult")

        uncertain_points, uncertain_scores = make_keypoints(33, 170)
        uncertain = person_type.estimate_person_type(
            uncertain_points, uncertain_scores, [50, 0, 110, 180]
        )
        self.assertEqual(uncertain["person_type"], "unknown")

    def test_vote_and_summary(self):
        history = [
            {"person_type": "child"},
            {"person_type": "child"},
            {"person_type": "child"},
            {"person_type": "adult"},
        ]
        vote = person_type.majority_vote(history, min_samples=3)
        self.assertEqual(vote["person_type"], "child")
        counts = person_type.summarize_person_types([
            {"person_type": "child"},
            {"person_type": "adult"},
            {"person_type": "child"},
            {"person_type": "unknown"},
        ])
        self.assertEqual(counts, {"adult": 1, "child": 2, "unknown": 1, "total": 4})


class PersonTypeApiTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location(
            "test_dashboard_person_type", ROOT / "dashboard" / "server.py"
        )
        self.web = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.web)
        self.temp = tempfile.TemporaryDirectory()
        self.web.PERSON_TYPES_FILE = Path(self.temp.name) / "person_types.json"
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

    def request(self):
        try:
            with urllib.request.urlopen(self.base + "/api/rdk/person-types", timeout=5) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read())

    def test_person_type_cache_endpoint(self):
        status, body = self.request()
        self.assertEqual(status, 404)
        self.assertFalse(body["ok"])

        self.web.PERSON_TYPES_FILE.write_text(json.dumps({
            "estimate": True,
            "generated_at": "2026-10-30T15:55:00+08:00",
            "counts": {"adult": 1, "child": 2, "unknown": 0, "total": 3},
            "persons": [],
        }, ensure_ascii=False), encoding="utf-8")
        status, body = self.request()
        self.assertEqual(status, 200)
        self.assertTrue(body["ok"])
        self.assertEqual(body["counts"]["child"], 2)
        self.assertIn("age_seconds", body)


if __name__ == "__main__":
    unittest.main()
