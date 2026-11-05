"""环境与设备异常自动事件测试。"""

import importlib.util
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_server():
    spec = importlib.util.spec_from_file_location(
        "test_dashboard_environment", ROOT / "dashboard" / "server.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class EnvironmentEventTests(unittest.TestCase):
    def setUp(self):
        self.web = load_server()
        self.temp = tempfile.TemporaryDirectory()
        self.web.DATA.events.path = Path(self.temp.name) / "events.json"
        self.web.EVIDENCE_DIR = Path(self.temp.name) / "evidence"
        self.web.reload_events()
        self.web.ENV_ACTIVE_CONDITIONS = set()
        self.now = datetime.now(timezone.utc)

    def tearDown(self):
        self.temp.cleanup()

    def reading(self, **overrides):
        payload = {
            "connected": True,
            "timestamp": self.now.isoformat(),
            "properties": {"eco2": 520, "tvoc": 80, "sht_t": 24.5, "sht_h": 55},
        }
        payload.update(overrides)
        return self.web.environment_reading(payload)

    def test_normal_reading_creates_nothing_and_resets_state(self):
        self.assertEqual(self.web.evaluate_environment(self.reading()), [])
        self.assertEqual(self.web.ENV_ACTIVE_CONDITIONS, set())

    def test_offline_transition_creates_one_event_and_dedupes(self):
        offline = self.reading(connected=False)
        created = self.web.evaluate_environment(offline)
        self.assertEqual(len(created), 1)
        self.assertEqual(created[0]["event_type"], "device_offline")
        self.assertEqual(created[0]["source"], "device")

        # 同一异常持续期间不重复建事件
        self.assertEqual(self.web.evaluate_environment(offline), [])

        # 恢复后同一去重窗口内再次断开：不重复建事件
        self.assertEqual(self.web.evaluate_environment(self.reading()), [])
        self.assertEqual(self.web.evaluate_environment(offline), [])

    def test_stale_and_gas_thresholds_create_separate_events(self):
        stale_at = datetime.fromtimestamp(
            self.now.timestamp() - (self.web.ENV_STALE_SECONDS + 30),
            timezone.utc,
        ).isoformat()
        reading = self.reading(
            timestamp=stale_at,
            properties={"eco2": 1200, "tvoc": 620, "sht_t": 25, "sht_h": 50},
        )
        created = self.web.evaluate_environment(reading)
        self.assertEqual(
            sorted(item["event_type"] for item in created),
            ["environment", "environment", "sensor_expired"],
        )
        summaries = {item["summary"] for item in created}
        self.assertIn("室内 eCO₂ 偏高", summaries)
        self.assertIn("室内 TVOC 偏高", summaries)
        self.assertIn("环境数据超过刷新时间", summaries)

    def test_missing_timestamp_reports_stale_unknown(self):
        reading = self.reading(timestamp="")
        created = self.web.evaluate_environment(reading)
        self.assertEqual([item["event_type"] for item in created], ["sensor_expired"])
        self.assertIn("缺少采集时间", created[0]["summary"])


if __name__ == "__main__":
    unittest.main()
