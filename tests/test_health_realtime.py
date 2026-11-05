"""Tests for live infrared temperature normalization."""

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "dashboard"))

import health_realtime as realtime  # noqa: E402

NOW = datetime(2026, 11, 4, 10, 0, 10, tzinfo=timezone(timedelta(hours=8)))


class HealthRealtimeTests(unittest.TestCase):
    def test_fresh_student_reading_is_ready(self):
        reading = realtime.normalize_infrared_payload(
            {
                "connected": True,
                "student_id": "S-0201",
                "device_id": "ir-01",
                "timestamp": "2026-11-04T10:00:05+08:00",
                "properties": {"mlx_obj": 36.54, "mlx_amb": 25.4},
            },
            now=NOW,
        )
        self.assertEqual(reading["status"], "ready")
        self.assertTrue(reading["fresh"])
        self.assertEqual(reading["temperature_c"], 36.5)
        self.assertEqual(reading["ambient_c"], 25.4)
        self.assertEqual(reading["age_seconds"], 5)
        self.assertTrue(reading["reading_id"].startswith("IRT-"))

    def test_missing_identity_is_visible_but_not_ready(self):
        reading = realtime.normalize_infrared_payload(
            {
                "connected": True,
                "collected_at": "2026-11-04T10:00:08+08:00",
                "mlx_obj": 36.7,
            },
            now=NOW,
        )
        self.assertEqual(reading["status"], "unassigned")
        self.assertTrue(reading["fresh"])
        self.assertEqual(reading["student_id"], "")

    def test_stale_and_unknown_timestamps_are_distinct(self):
        stale = realtime.normalize_infrared_payload(
            {
                "connected": True,
                "student_id": "S-0201",
                "timestamp": "2026-11-04T09:59:50+08:00",
                "mlx_obj": 36.5,
            },
            now=NOW,
        )
        self.assertEqual(stale["status"], "stale")
        self.assertFalse(stale["fresh"])

        unknown = realtime.normalize_infrared_payload(
            {"connected": True, "student_id": "S-0201", "mlx_obj": 36.5},
            now=NOW,
        )
        self.assertEqual(unknown["status"], "timestamp_unknown")
        self.assertFalse(unknown["fresh"])

    def test_offline_invalid_and_unstable_readings_are_not_recordable(self):
        offline = realtime.normalize_infrared_payload(
            {
                "connected": False,
                "timestamp": "2026-11-04T10:00:08+08:00",
                "mlx_obj": 36.5,
            },
            now=NOW,
        )
        self.assertEqual(offline["status"], "offline")

        invalid = realtime.normalize_infrared_payload(
            {
                "connected": True,
                "timestamp": "2026-11-04T10:00:08+08:00",
                "mlx_obj": 25.8,
            },
            now=NOW,
        )
        self.assertEqual(invalid["status"], "invalid_temperature")

        unstable = realtime.normalize_infrared_payload(
            {
                "connected": True,
                "stable": False,
                "student_id": "S-0201",
                "timestamp": "2026-11-04T10:00:08+08:00",
                "mlx_obj": 36.5,
            },
            now=NOW,
        )
        self.assertEqual(unstable["status"], "unstable")

    def test_epoch_timestamp_and_aging(self):
        measured_at = NOW - timedelta(seconds=2)
        reading = realtime.normalize_infrared_payload(
            {
                "connected": True,
                "student_id": "S-0201",
                "timestamp": int(measured_at.timestamp() * 1000),
                "mlx_obj": 36.5,
            },
            now=NOW,
        )
        self.assertEqual(reading["status"], "ready")
        aged = realtime.refresh_infrared_status(
            reading,
            now=NOW + timedelta(seconds=20),
            stale_after_seconds=10,
        )
        self.assertEqual(aged["status"], "stale")
        self.assertFalse(aged["fresh"])


if __name__ == "__main__":
    unittest.main()
