"""统一事件契约和 B/C 展示映射测试。"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "dashboard"))

import event_contract as contract  # noqa: E402


class EventContractTests(unittest.TestCase):
    def test_aliases_map_to_one_canonical_model(self):
        event = contract.normalize_event({
            "id": "E-1",
            "type": "fight",
            "title": "户外活动区推搡",
            "level": "high",
            "status": "handled",
            "source": "rdk",
            "occurred_at": "2026-10-28T09:15:22+08:00",
            "handler": "王老师",
            "class_id": "C-11",
            "class_name": "中一班",
        })
        self.assertEqual(event["event_type"], "fight")
        self.assertEqual(event["summary"], "户外活动区推搡")
        self.assertEqual(event["level"], "urgent")
        self.assertEqual(event["status"], "resolved")
        self.assertEqual(event["handled_by"], "王老师")
        self.assertEqual(event["class_id"], "C-11")

    def test_report_mapping_does_not_turn_resolved_into_pending(self):
        event = contract.normalize_event({
            "event_type": "fall",
            "level": "watch",
            "status": "resolved",
            "source": "rdk",
            "occurred_at": "2026-10-28T09:15:22+08:00",
            "summary": "现场确认",
        })
        report = contract.event_for_report(event)
        self.assertEqual(report["level"], "medium")
        self.assertEqual(report["status"], "handled")

    def test_status_transition_rules(self):
        contract.validate_status_transition("pending", "resolved")
        contract.validate_status_transition("pending", "false_alarm")
        contract.validate_status_transition("resolved", "pending")
        with self.assertRaises(contract.EventConflict):
            contract.validate_status_transition("resolved", "false_alarm")

    def test_invalid_values_are_rejected(self):
        with self.assertRaises(contract.EventValidationError):
            contract.normalize_event({
                "event_type": "unknown",
                "level": "urgent",
                "source": "rdk",
                "occurred_at": "2026-10-28T09:15:22+08:00",
                "summary": "bad",
            })
        with self.assertRaises(contract.EventValidationError):
            contract.normalize_event({
                "event_type": "fall",
                "level": "high",
                "source": "rdk",
                "occurred_at": "not-a-time",
                "summary": "bad",
            })

    def test_generated_id_and_timezone(self):
        event_id = contract.make_event_id("2026-10-28T09:15:22+08:00")
        self.assertTrue(event_id.startswith("EVT-20261028-"))
        self.assertEqual(contract.date_key("2026-10-28T00:30:00+00:00"), "2026-10-28")


if __name__ == "__main__":
    unittest.main()
