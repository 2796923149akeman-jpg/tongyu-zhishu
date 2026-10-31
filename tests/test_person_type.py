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
from unittest.mock import patch
import test_access as access_tests
from person_type_runtime import PersonTypeRuntime


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

    def test_unknown_frames_do_not_reuse_old_certainty(self):
        for history in (['child'] * 3 + ['unknown'] * 12,
                        ['unknown'] * 12 + ['child'] * 3):
            self.assertEqual(person_type.majority_vote(history)['person_type'], 'unknown')

    def test_missing_keypoint_scores_are_unknown(self):
        points, _ = make_keypoints(36, 170)
        result = person_type.estimate_person_type(points, list([0.0] * 17), [50, 0, 110, 180])
        self.assertEqual(result['person_type'], 'unknown')

    def test_tracks_without_ids_never_share_history_and_old_tracks_expire(self):
        spec = importlib.util.spec_from_file_location('test_pose_worker', ROOT / 'scripts/person_type_demo.py')
        worker = importlib.util.module_from_spec(spec); spec.loader.exec_module(worker)
        histories = {}
        for _ in range(4):
            self.assertEqual(worker.vote_for_track(histories, None, {'person_type': 'child'}, 1)['person_type'], 'unknown')
        self.assertFalse(histories)
        for now in (1, 1.3, 1.6):
            result = worker.vote_for_track(histories, '7', {'person_type': 'child'}, now)
        self.assertEqual(result['person_type'], 'child')
        self.assertEqual(worker.vote_for_track(histories, '7', {'person_type': 'adult'}, 5)['person_type'], 'unknown')


class PersonTypeApiTests(unittest.TestCase):
    def setUp(self):
        self.fixture = access_tests.AccessTests()
        self.fixture.setUp()
        self.web = self.fixture.web
        self.web.PERSON_TYPE_RUNTIME = PersonTypeRuntime(self.fixture.temp.name, 'http://rdk.invalid:5000')

    def tearDown(self):
        self.web.PERSON_TYPE_RUNTIME.stop()
        self.fixture.tearDown()

    def test_switch_requires_admin_csrf_and_read_obeys_video_and_monitor(self):
        request = self.fixture.request
        route = '/api/rdk/person-types'
        settings = route + '/settings'
        self.assertEqual(request(route)[0], 401)
        self.fixture.register_viewer()
        self.assertEqual(request(route)[0], 403)  # video closed by default
        self.assertEqual(request(settings, {'enabled': False})[0], 403)
        policy = self.web.AUTH.get_policy(); policy['video'] = True
        self.web.AUTH.set_policy(policy)
        self.assertEqual(request(route)[0], 200)
        policy['modules']['monitor'] = False; self.web.AUTH.set_policy(policy)
        self.assertEqual(request(route)[0], 403)
        self.fixture.login()
        self.assertEqual(request(settings, {'enabled': False}, {'X-CSRF-Token': ''})[0], 403)
        self.assertEqual(request(settings, {'enabled': 'yes'})[0], 400)
        self.assertEqual(request(settings, {'enabled': True, 'source': 'http://other/'})[0], 400)
        self.assertEqual(request(settings, {'enabled': True})[0], 400)  # absent model
        status, body, _ = request(settings, {'enabled': False})
        self.assertEqual(status, 200)
        self.assertFalse(body['enabled'])
        self.assertEqual(request(route)[1]['state'], 'disabled')
        html = request('/')[1]
        self.assertIn('id="personTypeToggle"', html)


class PersonTypeRuntimeTests(unittest.TestCase):
    def test_watchdog_does_not_block_terminal_checks_during_import(self):
        import subprocess
        code = ('import sys,time,threading,os;sys.path.insert(0,sys.argv[1]);'
                'from person_type_demo import start_parent_watchdog;'
                'start_parent_watchdog();threading.Timer(3,lambda:os._exit(8)).start();'
                'time.sleep(.1);sys.stdin.isatty();os._exit(0)')
        process = subprocess.Popen([sys.executable, '-c', code, str(ROOT / 'scripts')],
                                   stdin=subprocess.PIPE, stdout=subprocess.DEVNULL)
        try:
            self.assertEqual(process.wait(timeout=8), 0)
        finally:
            process.stdin.close()
            if process.poll() is None:
                process.terminate(); process.wait(timeout=5)

    def test_worker_exits_when_dashboard_pipe_closes(self):
        import subprocess
        code = ('import sys,time;sys.path.insert(0,sys.argv[1]);'
                'from person_type_demo import start_parent_watchdog;'
                'start_parent_watchdog();time.sleep(60)')
        process = subprocess.Popen([sys.executable, '-c', code, str(ROOT / 'scripts')],
                                   stdin=subprocess.PIPE, stdout=subprocess.DEVNULL)
        try:
            process.stdin.close()
            self.assertEqual(process.wait(timeout=5), 0)
        finally:
            if process.poll() is None:
                process.terminate(); process.wait(timeout=5)

    def test_process_starts_once_stops_and_rejects_old_results(self):
        import os
        import subprocess
        import time
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=False):
            os.environ.pop('PERSON_TYPE_MODEL', None)
            os.environ['PERSON_TYPE_PYTHON'] = sys.executable
            root = Path(directory)
            (root / 'scripts').mkdir()
            model = root / 'output/models/yolov8n-pose.pt'
            model.parent.mkdir(parents=True); model.write_bytes(b'fixture')
            # Real child process, fake inference only. No camera/model loading.
            (root / 'scripts/person_type_demo.py').write_text(
                'import argparse,time,json\nfrom datetime import datetime,timezone\n'
                'p=argparse.ArgumentParser();p.add_argument("--output");p.add_argument("--run-id");a,_=p.parse_known_args()\n'
                'open(a.output,"w").write(json.dumps({"run_id":a.run_id,"generated_at":datetime.now(timezone.utc).isoformat(),"persons":[{"person_type":"child"}]}))\n'
                'time.sleep(60)\n', encoding='utf-8')
            runtime = PersonTypeRuntime(root, 'http://rdk.invalid:5000')
            try:
                self.assertFalse(runtime.status()['enabled'])
                with patch('person_type_runtime.subprocess.run', return_value=subprocess.CompletedProcess([], 0)):
                    self.assertTrue(runtime.set_enabled(True)['enabled'])
                    process = runtime.process
                    runtime.set_enabled(True)
                    self.assertIs(runtime.process, process)
                for _ in range(100):
                    result = runtime.status()
                    if result['state'] == 'running': break
                    time.sleep(.02)
                self.assertEqual(result['counts']['child'], 1)
                self.assertNotIn('source', result)
                runtime.result_file.write_text(json.dumps({'run_id': runtime.run_id,
                    'generated_at': '2020-01-01T00:00:00+00:00', 'persons': []}))
                self.assertEqual(runtime.status()['state'], 'stale')
                runtime.result_file.write_text(json.dumps({'run_id': 'old-run'}))
                self.assertEqual(runtime.status()['state'], 'starting')
                runtime.set_enabled(False)
                self.assertIsNotNone(process.poll())
                self.assertFalse(runtime.status()['enabled'])
                self.assertNotIn('counts', runtime.status())
            finally:
                runtime.stop()


if __name__ == "__main__":
    unittest.main()
