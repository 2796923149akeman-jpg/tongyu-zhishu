"""学生测温页与当日日报页的静态路由、页面结构与接口约定检查。

这些测试不依赖浏览器：页面脚本的行为由 docs/HEALTH_REPORT_UI.md 中记录的
浏览器检查覆盖，这里只锁定路由、公共导航、演示数据标识和接口可用状态。
"""
import importlib.util
import json
from html.parser import HTMLParser
from pathlib import Path
import re
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class NavParser(HTMLParser):
    """收集主导航中的链接与当前页标记。"""

    def __init__(self):
        super().__init__()
        self.links = []
        self.in_nav = False

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "nav" and values.get("aria-label") == "主导航":
            self.in_nav = True
        elif tag == "a" and self.in_nav:
            self.links.append((values.get("href"), values.get("aria-current")))

    def handle_endtag(self, tag):
        if tag == "nav":
            self.in_nav = False


def nav_links(path):
    parser = NavParser()
    parser.feed(path.read_text(encoding="utf-8"))
    return parser.links


class HealthReportPageTests(unittest.TestCase):
    def setUp(self):
        self.web = load("test_dashboard_health_report", "dashboard/server.py")
        self.temp = tempfile.TemporaryDirectory()
        self.web.DIALOGUE_DATA_FILE = Path(self.temp.name) / "dialogue_messages.json"
        self.web.DIALOGUE_CONFIG_FILE = Path(self.temp.name) / "dialogue_config.json"
        self.web.ANALYSIS_CONFIG_FILE = Path(self.temp.name) / "analysis_config.json"
        self.web.CONVERSATION_SUMMARIES_FILE = Path(self.temp.name) / "conversation_summaries.json"
        self.web.EVENTS_FILE = Path(self.temp.name) / "events.json"
        self.web.HEALTH_STUDENTS_FILE = Path(self.temp.name) / "health_students.json"
        self.web.HEALTH_RECORDS_FILE = Path(self.temp.name) / "health_records.json"
        self.web.PROJECT_ROOT = Path(self.temp.name)
        self.web.AUTH = self.web.AccessStore(Path(self.temp.name) / 'auth_config.json', secure=False)
        self.web.AUTH.create_user('testadmin', 'fixture-password', role='admin')
        self.auth_token, _ = self.web.AUTH.new_session('testadmin')
        (Path(self.temp.name) / "xiaozhi-server" / "data").mkdir(parents=True)
        self.web.reload_events()
        self.web.reload_health()
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

    def request(self, path):
        request = urllib.request.Request(self.base + path, headers={'Cookie': 'tongyu_session=' + self.auth_token})
        with urllib.request.urlopen(request, timeout=5) as response:
            body = response.read()
            content_type = response.headers.get("Content-Type", "")
            if "json" in content_type:
                return response.status, content_type, json.loads(body)
            return response.status, content_type, body.decode("utf-8")

    def test_pages_and_shared_assets_are_served(self):
        pages = {
            "/health.html": ("学生测温", "学生名单", "测温登记", "测温记录"),
            "/reports.html": ("当日日报", "安全事件与处置", "需要关注的对话", "当日结论"),
        }
        for path, markers in pages.items():
            status, content_type, body = self.request(path)
            self.assertEqual(status, 200)
            self.assertIn("text/html", content_type)
            for marker in markers:
                self.assertIn(marker, body)

        status, content_type, css = self.request("/health-report.css")
        self.assertEqual(status, 200)
        self.assertIn("text/css", content_type)
        self.assertIn("--brand: #176b67", css)

        status, content_type, script = self.request("/health-report.js")
        self.assertEqual(status, 200)
        self.assertIn("javascript", content_type)
        self.assertIn("dataset.page", script)

        # 新增静态路由不能遮蔽原有的服务健康检查。
        status, content_type, health = self.request("/health")
        self.assertEqual(status, 200)
        self.assertTrue(health["ok"])
        self.assertNotIn("rdk_base", health)

    def test_navigation_is_shared_with_monitor_page(self):
        expected = ["index.html", "events.html", "chat.html", "health.html", "reports.html"]

        monitor = nav_links(ROOT / "dashboard" / "index.html")
        self.assertEqual([href for href, _ in monitor], expected)
        self.assertEqual([href for href, marker in monitor if marker == "page"], ["index.html"])

        for name in ("health.html", "reports.html"):
            links = nav_links(ROOT / "dashboard" / name)
            self.assertEqual([href for href, _ in links], expected)
            self.assertEqual([href for href, marker in links if marker == "page"], [name])

    def test_demo_data_is_labelled_and_assets_are_local(self):
        for name in ("health.html", "reports.html"):
            text = (ROOT / "dashboard" / name).read_text(encoding="utf-8")
            self.assertIn('href="health-report.css"', text)
            self.assertIn('src="health-report.js"', text)
            self.assertIn("演示数据", text)
            self.assertIn('data-page="', text)
            # 页面不得引入外部脚本、样式或内联事件处理器。
            self.assertIsNone(re.search(r'(?:src|href)="https?://', text), name)
            self.assertIsNone(re.search(r"\son(?:click|change|input|submit)=", text), name)

    def test_pages_cover_required_interactions(self):
        health = (ROOT / "dashboard" / "health.html").read_text(encoding="utf-8")
        for marker in ("导入名单", "导出 CSV", "复测关系", "班级", "搜索学号或姓名", "需复测"):
            self.assertIn(marker, health)
        for column in ("学号", "姓名", "班级", "体温", "来源", "备注", "复测关系"):
            self.assertIn(column, health)

        reports = (ROOT / "dashboard" / "reports.html").read_text(encoding="utf-8")
        for marker in ("日报日期", "班级范围", "打印日报", "未测温与需复测名单", "处置率"):
            self.assertIn(marker, reports)

        script = (ROOT / "dashboard" / "health-report.js").read_text(encoding="utf-8")
        self.assertIn("dashboard-day-change", script)

    def test_health_page_has_live_infrared_panel_and_freshness_states(self):
        health = (ROOT / "dashboard" / "health.html").read_text(encoding="utf-8")
        for element_id in (
            "infraredRealtime",
            "irTemperature",
            "irAmbient",
            "irMeasuredAt",
            "irStudent",
            "entryTempLabel",
            "entryTempHint",
        ):
            self.assertIn(f'id="{element_id}"', health)
        script = (ROOT / "dashboard" / "health-report.js").read_text(encoding="utf-8")
        self.assertIn("const REALTIME_MS = 2000", script)
        self.assertIn("function pollInfraredRealtime()", script)
        self.assertIn("数据已过期", script)
        self.assertIn("待关联学生", script)

    def test_documented_endpoints_match_page_script(self):
        script = (ROOT / "dashboard" / "health-report.js").read_text(encoding="utf-8")
        document = (ROOT / "docs" / "HEALTH_REPORT_UI.md").read_text(encoding="utf-8")
        for endpoint in (
            "/api/health/students",
            "/api/health/records",
            "/api/health/realtime",
            "/api/health/import",
            "/api/reports/daily",
        ):
            self.assertIn(endpoint, script)
            self.assertIn(endpoint, document)

    def test_health_data_endpoints_are_available(self):
        status, content_type, students = self.request("/api/health/students")
        self.assertEqual(status, 200)
        self.assertIn("json", content_type)
        self.assertEqual(students["students"], [])
        self.assertEqual(len(students["classes"]), 3)

        status, _, records = self.request("/api/health/records?date=2026-10-27")
        self.assertEqual(status, 200)
        self.assertEqual(records["records"], [])

        status, _, report = self.request("/api/reports/daily?date=2026-10-27")
        self.assertEqual(status, 200)
        self.assertEqual(report["report"]["health"]["total"], 0)


if __name__ == "__main__":
    unittest.main()
