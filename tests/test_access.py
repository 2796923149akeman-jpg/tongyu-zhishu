"""End-to-end permission, account and session checks over a real local HTTP socket."""
import hashlib
import http.client
import importlib.util
import io
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class AccessTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location('access_test_server', ROOT / 'dashboard/server.py')
        self.web = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.web)
        self.temp = tempfile.TemporaryDirectory()
        self.web.DATA.events.path = Path(self.temp.name) / "events.json"
        self.web.DATA.students.path = Path(self.temp.name) / "health_students.json"
        self.web.DATA.health_records.path = Path(self.temp.name) / "health_records.json"
        self.web.reload_events()
        self.web.reload_health()
        self.now = [1000.0]
        self.web.AUTH = self.web.AccessStore(Path(self.temp.name) / 'auth_config.json', secure=False, clock=lambda: self.now[0])
        self.web.AUTH.create_user('owner', 'owner-fixture', role='admin')
        self.web.DATA.messages.path = Path(self.temp.name) / 'dialogue_messages.json'
        self.web.MESSAGES.clear()
        self.web.CONVERSATION_SUMMARIES.clear()
        self.web.Handler.log_message = lambda *args: None
        self.http = self.web.ThreadingHTTPServer(('127.0.0.1', 0), self.web.Handler)
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()
        self.cookie = ''
        self.csrf = ''

    def tearDown(self):
        self.http.shutdown()
        self.http.server_close()
        self.thread.join()
        self.temp.cleanup()

    def request(self, path, data=None, headers=None, *, remember=True):
        connection = http.client.HTTPConnection('127.0.0.1', self.http.server_port, timeout=5)
        hdr = {'Cookie': self.cookie, 'X-CSRF-Token': self.csrf, 'Content-Type': 'application/json'}
        hdr.update(headers or {})
        connection.request('GET' if data is None else 'POST', path,
                           body=None if data is None else json.dumps(data).encode(), headers=hdr)
        response = connection.getresponse()
        body = response.read()
        response_headers = dict(response.getheaders())
        status = response.status
        connection.close()
        if remember and 'Set-Cookie' in response_headers:
            self.cookie = response_headers['Set-Cookie'].split(';', 1)[0]
        value = json.loads(body) if 'application/json' in response_headers.get('Content-Type', '') else body.decode()
        if remember and path == '/api/auth/session' and status == 200:
            self.csrf = value['csrf']
        return status, value, response_headers

    def login(self, username='owner', password='owner-fixture'):
        self.request('/api/auth/session')
        result = self.request('/api/auth/login', {'username': username, 'password': password})
        self.assertEqual(result[0], 200)
        self.request('/api/auth/session')
        return result

    def register_viewer(self):
        self.request('/api/auth/session')
        self.assertEqual(self.request('/api/auth/register', {'username': 'teacher', 'password': 'teacher-fixture', 'role': 'admin'})[0], 201)
        self.login()
        self.assertEqual(self.request('/api/admin/accounts', {'username': 'teacher', 'role': 'viewer'})[0], 200)
        self.login('teacher', 'teacher-fixture')

    def test_team_apis_obey_roles_csrf_and_module_switches(self):
        self.register_viewer()
        for route in ('/api/events', '/api/health/students', '/api/health/records', '/api/reports/daily', '/api/config'):
            self.assertEqual(self.request(route)[0], 200, route)
        for route in ('/api/events', '/api/events/example/status', '/api/events/example/notes', '/api/health/import', '/api/health/records'):
            self.assertEqual(self.request(route, {})[0], 403, route)
        self.login()
        self.assertEqual(self.request('/api/health/import', {'students': []}, {'X-CSRF-Token': ''})[0], 403)
        policy = self.web.AUTH.get_policy()
        for module in ('events', 'health', 'chat'):
            policy['modules'][module] = False
        self.web.AUTH.set_policy(policy)
        self.login('teacher', 'teacher-fixture')
        for route in ('/api/events', '/api/health/students', '/api/health/records'):
            self.assertEqual(self.request(route)[0], 403, route)
        status, body, _ = self.request('/api/reports/daily')
        self.assertEqual(status, 200)
        self.assertEqual(body['report']['health'], {})
        self.assertEqual(body['report']['events'], [])
        self.assertEqual(body['report']['dialogues'], [])

    def test_report_raw_text_is_filtered_server_side(self):
        self.register_viewer()
        payload = {'report': {'dialogues': [{'session_id': 'test', 'excerpt': 'private speech', 'reason': 'private reason', 'attention': 'watch'}], 'health': {}, 'events': []}}
        with patch.object(self.web, 'build_daily_report', return_value=payload):
            status, body, _ = self.request('/api/reports/daily')
        self.assertEqual(status, 200)
        self.assertNotIn('private', json.dumps(body))
        self.assertEqual(body['report']['dialogues'][0]['attention'], 'watch')

    def test_all_business_routes_require_login(self):
        for path in self.web.PAGE_ROUTES:
            status, _, headers = self.request(path)
            self.assertEqual(status, 303, path)
            self.assertTrue(headers['Location'].startswith('/login?next='))
        for path in ('/api/rdk/sensors', '/api/rdk/video_feed', '/api/dialogue/messages', '/api/admin/policy',
                     '/api/dialogue/model', '/api/analysis/config', '/api/events', '/api/health/records', '/api/reports/daily', '/health-report.js'):
            status, body, _ = self.request(path)
            self.assertEqual(status, 401, path)
            self.assertFalse(body['ok'])
        self.assertEqual(self.request('/health')[1], {'ok': True})

    def test_registration_login_role_and_private_storage(self):
        self.register_viewer()
        self.assertEqual(self.request('/api/auth/session')[1]['user']['role'], 'viewer')
        saved = self.web.AUTH.path.read_text(encoding='utf-8')
        self.assertNotIn('teacher-fixture', saved)
        self.assertNotIn('owner-fixture', saved)
        self.assertNotIn(self.cookie.split('=', 1)[1], saved)
        reloaded = self.web.AccessStore(self.web.AUTH.path)
        self.assertEqual(reloaded.users['teacher']['role'], 'viewer')
        self.assertEqual(self.request('/api/auth/register', {'username': 'TEACHER', 'password': 'other-fixture'})[0], 400)
        for path in ('/admin', '/admin.html', '/family-events.html', '/api/admin/policy', '/api/dialogue/model', '/api/analysis/config'):
            self.assertEqual(self.request(path)[0], 403)
        for path in ('/api/admin/policy', '/api/dialogue/model', '/api/dialogue/config', '/api/analysis/config', '/api/analysis/rebuild', '/api/health/records'):
            self.assertEqual(self.request(path, {})[0], 403)

    def test_admin_provisions_parent_account_with_student_bindings(self):
        self.login()
        status, _, _ = self.request(
            '/api/health/import',
            {
                'students': [
                    {'id': 'S-0201', 'name': '张小明', 'class_id': 'C-02'},
                    {'id': 'S-0202', 'name': '李小红', 'class_id': 'C-02'},
                ]
            },
        )
        self.assertEqual(status, 200)
        status, created, _ = self.request(
            '/api/admin/parents',
            {
                'username': 'parent-one',
                'password': 'parent-fixture',
                'student_ids': ['S-0201', 'S-0202'],
            },
        )
        self.assertEqual(status, 200)
        self.assertEqual(created['parent']['student_ids'], ['S-0201', 'S-0202'])
        status, listing, _ = self.request('/api/admin/parents')
        self.assertEqual(status, 200)
        self.assertEqual(listing['parents'][0]['username'], 'parent-one')

        self.login('parent-one', 'parent-fixture')
        status, session, _ = self.request('/api/auth/session')
        self.assertEqual(status, 200)
        self.assertEqual(session['user']['role'], 'parent')
        self.assertEqual(session['user']['student_ids'], ['S-0201', 'S-0202'])
        self.assertEqual(self.request('/welcome')[0], 200)
        self.assertEqual(self.request('/api/events')[0], 403)
        self.assertEqual(self.request('/health.html')[0], 403)
        self.assertEqual(self.request('/api/admin/parents')[0], 403)

        saved = self.web.AUTH.path.read_text(encoding='utf-8')
        self.assertNotIn('parent-fixture', saved)
        reloaded = self.web.AccessStore(self.web.AUTH.path)
        self.assertEqual(reloaded.users['parent-one']['student_ids'], ['S-0201', 'S-0202'])

    def test_admin_can_assign_and_change_registered_account_roles(self):
        self.request('/api/auth/session')
        self.assertEqual(self.request('/api/auth/register', {
            'username': 'family-user', 'password': 'family-fixture', 'role': 'merchant',
        })[0], 201)
        self.login('family-user', 'family-fixture')
        registered = {'Cookie': self.cookie, 'X-CSRF-Token': self.csrf}
        self.assertEqual(self.request('/api/auth/session')[1]['user']['role'], 'pending')
        for route in ('/api/admin/accounts', '/api/health/students', '/api/rdk/sensors', '/api/family/students'):
            self.assertEqual(self.request(route)[0], 403, route)
        self.assertEqual(self.request('/api/admin/accounts', {'username': 'family-user', 'role': 'merchant'})[0], 403)

        self.cookie = self.csrf = ''
        self.login()
        listing = self.request('/api/admin/accounts')[1]['accounts']
        self.assertIn({'username': 'family-user', 'role': 'pending'}, listing)
        self.assertNotIn('password_hash', json.dumps(listing))
        self.assertEqual(self.request('/api/admin/accounts', {'username': 'owner', 'role': 'merchant'})[0], 400)
        self.assertEqual(self.request('/api/health/import', {
            'students': [{'id': 'S-0201', 'name': '张小明', 'class_id': 'C-02'}],
        })[0], 200)
        self.assertEqual(self.request('/api/admin/student-nickname', {'student_id': 'S-0201', 'nickname': '小满'})[0], 200)
        assignment = {'username': 'family-user', 'role': 'parent', 'student_ids': ['S-0201']}
        self.assertEqual(self.request('/api/admin/accounts', {**assignment, 'student_ids': ['UNKNOWN']})[0], 400)
        self.assertEqual(self.request('/api/admin/accounts', assignment)[0], 200)
        status, data, _ = self.request('/api/family/students', headers=registered, remember=False)
        self.assertEqual((status, data['students']), (200, [{'id': 'S-0201', 'name': '小满'}]))
        self.assertEqual(self.web.load_health_students()[0]['nickname'], '小满')

        self.assertEqual(self.request('/api/admin/accounts', {'username': 'family-user', 'role': 'merchant'})[0], 200)
        self.assertEqual(self.request('/api/family/students', headers=registered, remember=False)[0], 403)
        self.assertEqual(self.request('/sensors.html', headers=registered, remember=False)[0], 200)
        self.assertEqual(self.web.AUTH.users['family-user']['student_ids'], [])

    def test_admin_page_contains_account_assignment_controls(self):
        page = (ROOT / "dashboard" / "admin.html").read_text(encoding="utf-8")
        for element_id in (
            "accountList",
            "accountRole",
            "roleForm",
            "parentStudents",
            "nicknameForm",
        ):
            self.assertIn(f'id="{element_id}"', page)
        self.assertIn("已注册账号", page)

    def test_admin_initialization_is_never_available_to_browser(self):
        self.web.AUTH = self.web.AccessStore(Path(self.temp.name) / 'empty.json', secure=False)
        self.request('/api/auth/session')
        self.assertFalse(self.request('/api/auth/session')[1]['initialized'])
        self.assertEqual(self.request('/api/auth/register', {'username': 'takeover', 'password': 'fixture-pass', 'role': 'admin'})[0], 503)

    def test_csrf_and_origin_checks_include_authentication(self):
        self.request('/api/auth/session')
        payload = {'username': 'owner', 'password': 'owner-fixture'}
        for headers in ({'X-CSRF-Token': ''}, {'X-CSRF-Token': 'wrong'}, {'Origin': 'https://evil.example'}, {'Sec-Fetch-Site': 'cross-site'}):
            self.assertEqual(self.request('/api/auth/login', payload, headers)[0], 403)
        self.login()
        for path in ('/api/admin/policy', '/api/auth/logout', '/api/dialogue/config'):
            self.assertEqual(self.request(path, {}, {'X-CSRF-Token': ''})[0], 403)
        # A public HTTPS Host/Origin is valid; no assumption that browser users are local.
        self.assertEqual(self.request('/api/admin/policy', headers={'Host': 'demo.example', 'Origin': 'https://demo.example'})[0], 200)

    def test_cookies_rotate_expire_and_logout_revokes(self):
        self.web.AUTH.secure = True
        self.request('/api/auth/session')
        old_cookie = self.cookie
        status, _, headers = self.request('/api/auth/login', {'username': 'owner', 'password': 'owner-fixture'})
        self.assertEqual(status, 200)
        self.assertNotEqual(old_cookie, self.cookie)
        for value in ('Secure', 'HttpOnly', 'SameSite=Lax', 'Path=/', 'Max-Age=28800'):
            self.assertIn(value, headers['Set-Cookie'])
        token = self.cookie.split('=', 1)[1]
        self.assertNotIn(token, self.web.AUTH.sessions)
        self.assertIn(hashlib.sha256(token.encode()).hexdigest(), self.web.AUTH.sessions)
        self.request('/api/auth/session')
        authenticated = self.cookie
        self.assertEqual(self.request('/api/auth/logout', {})[0], 200)
        self.assertEqual(self.request('/api/dialogue/messages', headers={'Cookie': authenticated})[0], 401)
        self.login()
        self.now[0] += self.web.AUTH.idle_seconds
        self.assertEqual(self.request('/api/dialogue/messages')[0], 401)
        self.login()
        for _ in range(17):
            self.now[0] += 1700
            self.request('/api/dialogue/config')
        self.assertEqual(self.request('/api/dialogue/messages')[0], 401)

    def test_failure_message_and_temporary_rate_limit(self):
        self.request('/api/auth/session')
        wrong = {'username': 'owner', 'password': 'wrong-fixture'}
        missing = self.request('/api/auth/login', wrong | {'username': 'missing'})
        failed = self.request('/api/auth/login', wrong)
        self.assertEqual(failed[1], missing[1])
        self.assertNotIn('Set-Cookie', failed[2])
        for _ in range(4):
            self.assertEqual(self.request('/api/auth/login', wrong)[0], 401)
        self.assertEqual(self.request('/api/auth/login', wrong)[0], 429)
        self.now[0] += 601
        self.login()

    def test_module_policy_persists_and_blocks_pages_and_apis(self):
        self.login()
        policy = self.web.AUTH.get_policy()
        policy['modules'] = dict.fromkeys(policy['modules'], False)
        self.assertEqual(self.request('/api/admin/policy', policy)[0], 200)
        self.assertEqual(self.web.AccessStore(self.web.AUTH.path).get_policy(), policy)
        self.assertEqual(self.request('/api/admin/policy', policy | {'video': 'false'})[0], 400)
        self.register_viewer()
        for path in ('/', '/index.html', '/events', '/chat', '/health.html', '/reports.html',
                     '/api/rdk/status', '/api/rdk/sensors', '/api/rdk/video_feed', '/api/config',
                     '/api/dialogue/messages', '/api/dialogue/conversations', '/api/dialogue/config',
                     '/api/events', '/api/health/records', '/api/reports/daily'):
            self.assertEqual(self.request(path)[0], 403, path)
        self.assertEqual(self.request('/welcome')[0], 200)
        self.login()
        self.assertEqual(self.request('/chat')[0], 200)

    def test_raw_speech_is_removed_from_every_dialogue_field(self):
        secret = 'private-original-speech'
        self.web.MESSAGES.append({'id': 'm', 'role': 'user', 'text': secret, 'session_id': 's',
                                 'emotion': {'label': 'sad', 'reason': secret, 'attention_reason': secret, 'attention': 'watch'}})
        self.web.CONVERSATION_SUMMARIES['s'] = {'session_id': 's', 'message_count': 1, 'title': secret,
                                               'summary': secret, 'attention_reason': secret, 'attention': 'watch'}
        self.register_viewer()
        for path in ('/api/dialogue/messages', '/api/dialogue/conversations'):
            self.assertNotIn(secret, json.dumps(self.request(path)[1]))
        self.assertEqual(self.request('/api/dialogue/messages')[1]['messages'][0]['emotion']['label'], 'sad')
        # Policy changes apply to an already established session.
        policy = self.web.AUTH.get_policy(); policy['dialogue_raw'] = True
        self.web.AUTH.set_policy(policy)
        self.assertIn(secret, json.dumps(self.request('/api/dialogue/messages')[1]))
        policy['dialogue_raw'] = False; self.web.AUTH.set_policy(policy)
        self.assertNotIn(secret, json.dumps(self.request('/api/dialogue/messages')[1]))

    def test_video_permission_is_independent_of_sensor_permission(self):
        self.register_viewer()
        with patch.object(self.web, 'read_rdk_json', return_value={'temperature': 24}), patch.object(self.web.Handler, 'proxy_video') as video:
            self.assertEqual(self.request('/api/rdk/sensors')[0], 200)
            self.assertEqual(self.request('/api/rdk/video_feed')[0], 403)
            video.assert_not_called()
        status, html, _ = self.request('/')
        self.assertEqual(status, 200)
        self.assertNotIn('src="/api/rdk/video_feed"', html)

    def test_open_video_stream_stops_when_permission_changes(self):
        self.register_viewer()
        policy = self.web.AUTH.get_policy(); policy['video'] = True
        self.web.AUTH.set_policy(policy)
        class Upstream(io.BytesIO):
            status = 200
            headers = {}

            def read1(upstream, size):
                policy['video'] = False
                self.web.AUTH.set_policy(policy)
                return b'frame-that-must-not-be-sent'

        with patch.object(self.web.urllib.request, 'urlopen', return_value=Upstream()):
            status, body, _ = self.request('/api/rdk/video_feed')
        self.assertEqual(status, 200)
        self.assertEqual(body, '')

    def test_local_message_hook_survives_and_proxy_cannot_impersonate_it(self):
        payload = dict(id='ingest', role='user', text='fixture', device_id='d', session_id='s', created_at='2026-10-28')
        self.assertEqual(self.request('/api/dialogue/messages', payload)[0], 200)
        for headers in ({'Host': 'demo.example'}, {'X-Forwarded-For': '127.0.0.1'}, {'CF-Connecting-IP': '127.0.0.1'},
                        {'X-Forwarded-Proto': 'https'}, {'Forwarded': 'for=127.0.0.1'}, {'Sec-Fetch-Site': 'cross-site'}):
            self.assertEqual(self.request('/api/dialogue/messages', payload, headers)[0], 403)
        with patch.object(self.web.Handler, 'client_address', ('192.0.2.1', 123), create=True):
            # Verify the guard with a constructed handler; live sockets above stay loopback.
            handler = object.__new__(self.web.Handler)
            handler.client_address = ('192.0.2.1', 123)
            handler.headers = {'Host': 'localhost'}
            handler.send_json = lambda *args: None
            self.assertFalse(handler.require_local_ingest())


if __name__ == '__main__':
    unittest.main()
