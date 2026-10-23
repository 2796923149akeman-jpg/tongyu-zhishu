"""Local HTTP and production message-hook tests, without devices or model APIs."""
import ast
import asyncio
import importlib.util
import json
from pathlib import Path
import threading
import time
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DialogueTests(unittest.TestCase):
    def setUp(self):
        self.web = load('test_dashboard', 'dashboard/server.py')
        self.temp = tempfile.TemporaryDirectory()
        self.web.DIALOGUE_DATA_FILE = Path(self.temp.name) / 'dialogue_messages.json'
        self.web.DIALOGUE_CONFIG_FILE = Path(self.temp.name) / 'dialogue_config.json'
        self.web.ANALYSIS_CONFIG_FILE = Path(self.temp.name) / 'analysis_config.json'
        self.web.CONVERSATION_SUMMARIES_FILE = Path(self.temp.name) / 'conversation_summaries.json'
        self.web.MESSAGES.clear()
        self.web.CONVERSATION_SUMMARIES.clear()
        self.web.DIALOGUE_CONFIG.clear()
        self.web.DIALOGUE_CONFIG.update(self.web.DEFAULT_DIALOGUE_CONFIG)
        self.web.ANALYSIS_CONFIG.clear()
        self.web.ANALYSIS_CONFIG.update(self.web.DEFAULT_ANALYSIS_CONFIG)
        self.web.Handler.log_message = lambda *args: None
        self.http = self.web.ThreadingHTTPServer(('127.0.0.1', 0), self.web.Handler)
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()
        self.base = f'http://127.0.0.1:{self.http.server_port}'
        self.sender = load('test_sender', 'xiaozhi-server/core/utils/dialogue_monitor.py')
        self.sender.URL = self.base + '/api/dialogue/messages'

    def tearDown(self):
        self.http.shutdown()
        self.http.server_close()
        self.thread.join()
        self.temp.cleanup()

    def request(self, path='/api/dialogue/messages', data=None, headers=None):
        hdr = {'Content-Type': 'application/json'}
        hdr.update(headers or {})
        req = urllib.request.Request(self.base + path, data=json.dumps(data).encode() if data is not None else None, headers=hdr)
        try:
            with urllib.request.urlopen(req, timeout=3) as r:
                body = r.read()
                return r.status, json.loads(body) if r.headers.get_content_type() == 'application/json' else body.decode()
        except urllib.error.HTTPError as e:
            return e.code, json.load(e)

    def message(self, ident='first', **overrides):
        return dict(id=ident, role='user', text='你好', device_id='test-esp32', session_id='test-session', created_at='2026-10-17T00:00:00+00:00', **overrides)

    def test_monitor_and_chat_routes(self):
        for path, marker in [('/', 'RDK X5'), ('/chat', '陪伴对话记录')]:
            status, body = self.request(path)
            self.assertEqual(status, 200)
            self.assertIn(marker, body)
        self.assertEqual(self.request()[1]['messages'], [])
        with patch.object(self.web, 'read_rdk_json', return_value={'temperature': 24.5}) as upstream:
            self.assertEqual(self.request('/api/rdk/sensors')[1], {'temperature': 24.5})
            upstream.assert_called_once_with('/api/iot_payload')

    def test_dialogue_interface_config(self):
        status, body = self.request('/api/dialogue/config')
        self.assertEqual(status, 200)
        self.assertEqual(body['config']['page_size'], 50)
        configured = {
            'title': '一班对话记录',
            'refresh_seconds': 5,
            'page_size': 20,
            'show_session_id': True,
            'show_created_at': False,
            'auto_scroll': False,
        }
        status, body = self.request('/api/dialogue/config', configured)
        self.assertEqual(status, 200)
        self.assertEqual(body['config'], configured)
        self.assertEqual(json.loads(self.web.DIALOGUE_CONFIG_FILE.read_text(encoding='utf-8')), configured)

        invalid = configured | {'page_size': 21}
        self.assertEqual(self.request('/api/dialogue/config', invalid)[0], 400)
        self.assertEqual(self.request('/api/dialogue/config')[1]['config'], configured)

    def test_emotion_and_conversation_routes(self):
        self.assertEqual(self.request(data=self.message() | {'text': '我每天都哭，不想上学'})[0], 200)
        message = self.request()[1]['messages'][0]
        self.assertEqual(message['emotion']['label'], 'sad')
        self.assertEqual(message['emotion']['attention'], 'watch')
        status, body = self.request('/api/dialogue/conversations')
        self.assertEqual(status, 200)
        self.assertEqual(body['conversations'][0]['session_id'], 'test-session')
        self.assertEqual(body['conversations'][0]['attention'], 'watch')

    def test_analysis_config_redacts_keys(self):
        configured = {
            'summary_enabled': True, 'summary_model_source': 'custom',
            'summary_base_url': 'https://api.example.com', 'summary_model_name': 'summary-model',
            'summary_api_key': 'private-summary-key', 'emotion_mode': 'model_fallback',
            'emotion_model_source': 'custom', 'emotion_base_url': 'https://api.example.com',
            'emotion_model_name': 'emotion-model', 'emotion_api_key': 'private-emotion-key',
        }
        status, body = self.request('/api/analysis/config', configured)
        self.assertEqual(status, 200)
        self.assertNotIn('summary_api_key', body['config'])
        self.assertNotIn('emotion_api_key', body['config'])
        self.assertTrue(body['config']['summary_api_key_set'])
        saved = json.loads(self.web.ANALYSIS_CONFIG_FILE.read_text(encoding='utf-8'))
        self.assertEqual(saved['summary_api_key'], 'private-summary-key')
        self.assertNotIn('private-summary-key', json.dumps(self.request('/api/analysis/config')[1]))

    def test_validation_and_unknown_routes(self):
        for payload in [{}, [], {'role': 'system'}, self.message() | {'text': ''}, self.message() | {'text': 'x'*8193}]:
            self.assertEqual(self.request(data=payload)[0], 400)
        self.assertEqual(self.request('/missing', data={})[0], 404)
        self.assertEqual(self.request()[1]['messages'], [])

    def test_local_access_restrictions(self):
        for headers in [{'Host': 'attacker.example'}, {'Origin': 'https://attacker.example'}, {'Sec-Fetch-Site': 'cross-site'}]:
            self.assertEqual(self.request(headers=headers)[0], 403)
            self.assertEqual(self.request(data=self.message(), headers=headers)[0], 403)
            self.assertEqual(self.request('/api/analysis/config', headers=headers)[0], 403)

    def test_capacity_and_duplicate_ids(self):
        self.request(data=self.message())
        self.request(data=self.message())
        self.assertEqual(len(self.request()[1]['messages']), 1)
        for i in range(205):
            self.assertEqual(self.request(data=self.message(str(i)))[0], 200)
        messages = self.request()[1]['messages']
        self.assertEqual(len(messages), 200)
        self.assertEqual(messages[0]['id'], '5')
        self.assertEqual(messages[-1]['id'], '204')
        loaded = self.web.load_messages()
        self.assertEqual(len(loaded), 200)
        self.assertEqual(loaded[0]['id'], '5')

    def test_production_hooks_reach_http_in_order(self):
        # Compile the actual changed hooks without importing GPU/audio providers.
        source = ast.parse((ROOT / 'xiaozhi-server/core/handle/sendAudioHandle.py').read_text(encoding='utf-8'))
        nodes = [n for n in source.body if isinstance(n, ast.AsyncFunctionDef) and n.name in ('send_stt_message', 'send_tts_message')]
        self.assertEqual(len(nodes), 2)
        scope = {'json': json, 'publish_dialogue': self.sender.publish,
                 'textUtils': SimpleNamespace(check_emoji=lambda s: s, get_string_no_punctuation_or_emoji=lambda s: s)}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), '<production-message-hooks>', 'exec'), scope)
        conn = SimpleNamespace(device_id='esp32-test', session_id='session-1', config={}, websocket=SimpleNamespace(send=AsyncMock()))
        async def scenario():
            await scope['send_stt_message'](conn, json.dumps({'content': '今天很开心', 'speaker': '小朋友'}))
            await scope['send_tts_message'](conn, 'sentence_start', '真好呀！')
            await scope['send_tts_message'](conn, 'sentence_start', '可以和我分享吗？')
        asyncio.run(scenario())
        self.sender._pending.join()
        records = self.request()[1]['messages']
        self.assertEqual([r['text'] for r in records], ['今天很开心', '真好呀！', '可以和我分享吗？'])
        self.assertEqual([r['role'] for r in records], ['user', 'assistant', 'assistant'])
        self.assertTrue(all(r['device_id'] == 'esp32-test' for r in records))

    def test_slow_or_missing_dashboard_does_not_block_producer(self):
        started, release = threading.Event(), threading.Event()
        def stalled(payload):
            started.set()
            release.wait(3)
            raise OSError('dashboard unavailable')
        with patch.object(self.sender, '_deliver', side_effect=stalled):
            begin = time.monotonic()
            self.sender.publish(SimpleNamespace(), 'user', 'still speaking')
            self.assertLess(time.monotonic()-begin, 0.5)
            self.assertTrue(started.wait(1))
            release.set()
            self.sender._pending.join()
        self.assertEqual(self.request()[1]['messages'], [])
        self.sender.publish(SimpleNamespace(), 'assistant', 'recovered')
        self.sender._pending.join()
        self.assertEqual(self.request()[1]['messages'][0]['text'], 'recovered')


if __name__ == '__main__':
    unittest.main()
