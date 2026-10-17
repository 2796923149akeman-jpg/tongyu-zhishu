"""Best-effort, ordered message mirroring; never wait on HTTP in the audio loop."""
import json
import os
import queue
import threading
import urllib.request
import uuid
from datetime import datetime, timezone

URL = os.environ.get('DIALOGUE_DASHBOARD_URL', 'http://127.0.0.1:8088/api/dialogue/messages')
_pending = queue.Queue(maxsize=256)
_lock = threading.Lock()
_worker = None


def _deliver(payload):
    request = urllib.request.Request(URL, data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
                                     headers={'Content-Type': 'application/json'}, method='POST')
    with urllib.request.urlopen(request, timeout=1) as response:
        response.read(1024)


def _run():
    while True:
        payload = _pending.get()
        try:
            _deliver(payload)
        except Exception:
            # The monitor is optional; missed messages are not retried or saved to disk.
            pass
        finally:
            _pending.task_done()


def publish(conn, role, text):
    global _worker
    text = str(text or '').strip()
    if not URL or not text:
        return
    payload = {
        'id': uuid.uuid4().hex, 'role': role, 'text': text[:8192],
        'device_id': str(getattr(conn, 'device_id', 'unknown'))[:160],
        'session_id': str(getattr(conn, 'session_id', ''))[:160],
        'created_at': datetime.now(timezone.utc).isoformat(),
    }
    with _lock:
        if _worker is None or not _worker.is_alive():
            _worker = threading.Thread(target=_run, name='dialogue-monitor', daemon=True)
            _worker.start()
    try:
        _pending.put_nowait(payload)
    except queue.Full:
        pass
