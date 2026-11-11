"""First-run initialization and real launcher restarts retain accounts and policy."""
import http.client
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'dashboard'))
import manage_access
from access_control import AccessStore


class StartupTests(unittest.TestCase):
    def test_admin_setup_only_prompts_once_and_keeps_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'auth_config.json'
            with patch.dict(os.environ, {'DASHBOARD_AUTH_FILE': str(path)}):
                with patch('builtins.input', return_value='owner'), patch.object(manage_access.getpass, 'getpass', return_value='setup-fixture'):
                    manage_access.ensure_admin()
                store = AccessStore(path)
                store.create_user('teacher', 'teacher-fixture')
                policy = store.get_policy(); policy['modules']['events'] = False; policy['video'] = True
                store.set_policy(policy)
                before = path.read_bytes()
                with patch('builtins.input', side_effect=AssertionError('Unexpected repeated setup')), patch.object(manage_access.getpass, 'getpass', side_effect=AssertionError('Unexpected password prompt')):
                    manage_access.ensure_admin()
                self.assertEqual(path.read_bytes(), before)
                reloaded = AccessStore(path)
                self.assertEqual(reloaded.get_policy(), policy)
                self.assertEqual(reloaded.authenticate('owner', 'setup-fixture', 'local')[0], 'ok')
                self.assertEqual(reloaded.authenticate('teacher', 'teacher-fixture', 'local')[0], 'ok')

    def test_f5_entry_restarts_without_resetting_accounts_or_policy(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = Path(directory)
            path = runtime / 'auth_config.json'
            store = AccessStore(path)
            store.create_user('owner', 'owner-fixture', role='admin')
            store.create_user('teacher', 'teacher-fixture')
            policy = store.get_policy(); policy['modules']['events'] = False
            store.set_policy(policy)
            before = path.read_bytes()
            environment = os.environ.copy()
            environment.update(DASHBOARD_AUTH_FILE=str(path), PROJECT_ROOT=str(runtime),
                               PYTHONIOENCODING='utf-8', ENV_MONITOR_ENABLED='0')
            for name in ('DIALOGUE_DATA_FILE', 'DIALOGUE_CONFIG_FILE', 'ANALYSIS_CONFIG_FILE', 'CONVERSATION_SUMMARIES_FILE'):
                environment[name] = str(runtime / (name.lower() + '.json'))
            old_cookie = ''
            for restart in range(2):
                with socket.socket() as free:
                    free.bind(('127.0.0.1', 0))
                    port = free.getsockname()[1]
                process = subprocess.Popen([sys.executable, str(ROOT / 'scripts/run_dashboard.py'), '--no-browser', '--port', str(port)],
                                           cwd=ROOT, env=environment, stdin=subprocess.DEVNULL,
                                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
                def request(route, data=None, cookie='', csrf=''):
                    connection = http.client.HTTPConnection('127.0.0.1', port, timeout=2)
                    connection.request('GET' if data is None else 'POST', route,
                                       body=None if data is None else json.dumps(data).encode(),
                                       headers={'Content-Type': 'application/json', 'Cookie': cookie, 'X-CSRF-Token': csrf})
                    response = connection.getresponse()
                    status, raw, headers = response.status, response.read(), dict(response.getheaders())
                    connection.close()
                    return status, json.loads(raw), headers
                try:
                    deadline = time.monotonic() + 10
                    while True:
                        if process.poll() is not None:
                            self.fail(process.stdout.read().decode('utf-8', errors='replace'))
                        try:
                            if request('/health')[0] == 200:
                                break
                        except OSError:
                            pass
                        if time.monotonic() > deadline:
                            self.fail('Launcher did not become ready')
                        time.sleep(.05)
                    if restart:
                        self.assertEqual(request('/api/dialogue/messages', cookie=old_cookie)[0], 401)
                    for username, password, role in (('owner', 'owner-fixture', 'admin'), ('teacher', 'teacher-fixture', 'viewer')):
                        status, session, headers = request('/api/auth/session')
                        cookie = headers['Set-Cookie'].split(';', 1)[0]
                        status, result, headers = request('/api/auth/login', {'username': username, 'password': password}, cookie, session['csrf'])
                        self.assertEqual(status, 200)
                        self.assertEqual(result['user']['role'], role)
                        old_cookie = headers['Set-Cookie'].split(';', 1)[0]
                    self.assertEqual(path.read_bytes(), before)
                finally:
                    process.terminate()
                    process.communicate(timeout=5)

    def test_launcher_records_environment_alert_without_browser_polling(self):
        class MockRdk(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path != '/api/iot_payload':
                    self.send_error(404)
                    return
                payload = json.dumps({
                    'connected': True, 'collected_at': time.time(), 'eco2': 1800,
                }).encode()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *_args):
                pass

        with tempfile.TemporaryDirectory() as directory, ThreadingHTTPServer(('127.0.0.1', 0), MockRdk) as rdk:
            runtime = Path(directory)
            accounts = runtime / 'auth.json'
            AccessStore(accounts).create_user('owner', 'owner-fixture', role='admin')
            events = runtime / 'events.json'
            # File existence is not readiness: startup may persist an empty
            # collection before the background monitor has polled the device.
            events.write_text('[]', encoding='utf-8')
            environment = {
                **os.environ, 'DASHBOARD_AUTH_FILE': str(accounts), 'PROJECT_ROOT': str(runtime),
                'EVENTS_FILE': str(events), 'RDK_BASE': f'http://127.0.0.1:{rdk.server_port}',
                'ENV_MONITOR_ENABLED': '1', 'ENV_ECO2_LIMIT': '1000', 'PYTHONIOENCODING': 'utf-8',
            }
            for key in ('DIALOGUE_DATA_FILE', 'DIALOGUE_CONFIG_FILE', 'ANALYSIS_CONFIG_FILE',
                        'CONVERSATION_SUMMARIES_FILE', 'HEALTH_STUDENTS_FILE', 'HEALTH_RECORDS_FILE'):
                environment[key] = str(runtime / f'{key.lower()}.json')
            thread = threading.Thread(target=rdk.serve_forever, daemon=True)
            thread.start()
            try:
                with socket.socket() as free:
                    free.bind(('127.0.0.1', 0))
                    port = free.getsockname()[1]
                with subprocess.Popen(
                    [sys.executable, str(ROOT / 'scripts/run_dashboard.py'), '--no-browser', '--port', str(port)],
                    cwd=ROOT, env=environment, stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                ) as process:
                    try:
                        deadline = time.monotonic() + 10
                        recorded = []
                        while process.poll() is None and time.monotonic() < deadline:
                            try:
                                recorded = json.loads(events.read_text(encoding='utf-8'))
                            except (OSError, json.JSONDecodeError):
                                # Windows replacement can briefly contend with a reader.
                                recorded = []
                            if any(event['event_type'] == 'environment' for event in recorded):
                                break
                            time.sleep(.05)
                        self.assertTrue(
                            any(event['event_type'] == 'environment' for event in recorded),
                            f'Background environment event not persisted; exit={process.poll()}, events={recorded}',
                        )
                    finally:
                        process.terminate()
                        process.communicate(timeout=5)
            finally:
                rdk.shutdown()
                thread.join(timeout=2)


if __name__ == '__main__':
    unittest.main()
