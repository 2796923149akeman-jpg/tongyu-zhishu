"""First-run initialization and real launcher restarts retain accounts and policy."""
import http.client
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'dashboard'))
from access_control import AccessStore
import manage_access


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
            environment.update(DASHBOARD_AUTH_FILE=str(path), PROJECT_ROOT=str(runtime), PYTHONIOENCODING='utf-8')
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


if __name__ == '__main__':
    unittest.main()
