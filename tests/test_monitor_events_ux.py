"""Static regression checks for the monitoring and event page UX."""

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EVENTS_PAGE = ROOT / "dashboard" / "events.html"
MONITOR_PAGE = ROOT / "dashboard" / "index.html"


class MonitorEventsUxTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.events = EVENTS_PAGE.read_text(encoding="utf-8")
        cls.monitor = MONITOR_PAGE.read_text(encoding="utf-8")

    def test_event_page_supports_silent_refresh_and_new_event_notice(self):
        self.assertIn("const POLL_EVENTS_MS = 5000", self.events)
        self.assertIn('id="newEventsNotice"', self.events)
        self.assertIn('id="viewNewEvents"', self.events)
        self.assertIn("if (!document.hidden) loadEvents({ background: true })", self.events)
        self.assertIn("previousSelectedId", self.events)
        self.assertIn("state.newEventIds.add(item.id)", self.events)

    def test_event_page_hides_mutation_controls_for_read_only_users(self):
        self.assertIn('id="eventActions"', self.events)
        self.assertIn('id="readOnlyNote"', self.events)
        self.assertIn('const isAdmin = user?.role === "admin"', self.events)
        self.assertIn("els.eventActions.hidden = !isAdmin", self.events)
        self.assertIn("if (!isAdmin) {", self.events)

    def test_monitor_alert_links_to_pending_urgent_events(self):
        self.assertIn(
            'href="/events.html?status=pending&amp;level=urgent&amp;date=all&amp;open=1"',
            self.monitor,
        )
        self.assertIn('id="bannerAction"', self.monitor)
        self.assertIn(
            'els.bannerAction.hidden = kind !== "fall" && kind !== "fight"',
            self.monitor,
        )

    def test_event_detail_has_evidence_and_overdue_regions(self):
        for element_id in (
            "evidenceBox",
            "evidenceImage",
            "evidenceCaption",
            "evidenceEmpty",
            "detailAge",
            "overduePending",
        ):
            self.assertIn(f'id="{element_id}"', self.events)
        self.assertIn("const OVERDUE_MS = 5 * 60 * 1000", self.events)
        self.assertIn("function safeEvidenceUrl(value)", self.events)
        self.assertIn("function isOverdue(event, now = Date.now())", self.events)

    def test_event_detail_has_student_assignment_region(self):
        for element_id in (
            "studentChips",
            "studentCount",
            "studentNamesInput",
            "assignStudentsBtn",
            "studentNote",
        ):
            self.assertIn(f'id="{element_id}"', self.events)
        self.assertIn("function renderStudentChips(event)", self.events)
        self.assertIn("function assignStudents()", self.events)
        self.assertIn(
            '`/api/events/${encodeURIComponent(event.id)}/students`',
            self.events,
        )
        self.assertIn("多个姓名用空格分开", self.events)

    def test_quick_filters_keyboard_and_mobile_detail_are_wired(self):
        for quick_filter in ("today", "pending", "urgent", "overdue"):
            self.assertIn(f'data-quick="{quick_filter}"', self.events)
        self.assertIn('id="detailBack"', self.events)
        self.assertIn('event.key === "/"', self.events)
        self.assertIn('event.key.toLowerCase() === "j"', self.events)
        self.assertIn('event.key.toLowerCase() === "k"', self.events)
        self.assertIn('event.key === "Escape"', self.events)
        self.assertIn(".workspace-grid.detail-open .list-card", self.events)

    def test_query_parameters_restore_event_filters(self):
        self.assertIn("new URLSearchParams(location.search)", self.events)
        self.assertIn('params.get("open") === "1"', self.events)
        for name in ("status", "level", "source", "date", "sort"):
            self.assertIn(f'{name}: new Set(', self.events)

    def test_every_cached_element_id_exists(self):
        referenced = set(re.findall(r'\$\("#([A-Za-z0-9_-]+)"\)', self.events))
        declared = set(re.findall(r'\bid="([A-Za-z0-9_-]+)"', self.events))
        self.assertEqual(referenced - declared, set())


if __name__ == "__main__":
    unittest.main()
