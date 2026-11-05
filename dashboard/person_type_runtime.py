"""Own one optional pose worker. Disabled by default; never touches legacy caches."""
from __future__ import annotations

import atexit
import json
import os
import subprocess
import sys
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path


class PersonTypeRuntime:
    def __init__(self, root, rdk_base):
        self.root = Path(root)
        self.source = rdk_base.rstrip('/') + '/snapshot'
        self.lock = threading.RLock()
        self.process = None
        self.log = None
        self.result_file = None
        self.run_id = None
        self.error = ''
        atexit.register(self.stop)

    def _status(self):
        if self.process is None:
            return {'ok': True, 'enabled': False, 'state': 'error' if self.error else 'disabled', 'error': self.error}
        if self.process.poll() is not None:
            self.error = '人物估算进程已退出，请查看电脑端 output/person-type-runtime 日志后重试。'
            if self.process.stdin:
                self.process.stdin.close()
            self.process = None
            if self.log:
                self.log.close()
                self.log = None
            return {'ok': True, 'enabled': False, 'state': 'error', 'error': self.error}
        result = {'ok': True, 'enabled': True, 'state': 'starting', 'estimate': True}
        try:
            data = json.loads(self.result_file.read_text(encoding='utf-8'))
            if not isinstance(data, dict):
                raise ValueError('object required')
            if data.get('run_id') != self.run_id:
                return result
            stamp = datetime.fromisoformat(data['generated_at'].replace('Z', '+00:00'))
            if stamp.tzinfo is None:
                raise ValueError('timezone required')
            age = (datetime.now(timezone.utc) - stamp).total_seconds()
            result.update(generated_at=data['generated_at'], stale=age > 15 or age < -5)
            if result['stale']:
                result['state'] = 'stale'
            elif data.get('error'):
                result.update(state='error', error='暂时无法分析 RDK 画面，正在重试。')
            else:
                persons = data.get('persons')
                if not isinstance(persons, list) or len(persons) > 100:
                    raise ValueError('invalid persons')
                counts = dict(adult=0, child=0, unknown=0, total=len(persons))
                for person in persons:
                    kind = person.get('person_type') if isinstance(person, dict) else None
                    counts[kind if kind in ('adult', 'child') else 'unknown'] += 1
                result.update(state='running', counts=counts)
        except FileNotFoundError:
            pass
        except (ValueError, KeyError, TypeError, OSError):
            result.update(state='stale', stale=True)
        return result

    def status(self):
        with self.lock:
            return self._status()

    def set_enabled(self, enabled):
        if type(enabled) is not bool:
            raise ValueError('enabled 必须是布尔值')
        with self.lock:
            if not enabled:
                self.stop()
                return self._status()
            if self._status()['enabled']:
                return self._status()
            runtime = self.root / 'output' / 'person-type-runtime'
            python = os.environ.get('PERSON_TYPE_PYTHON')
            local_python = self.root / 'output' / 'person-type-env' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
            python = python or (str(local_python) if local_python.is_file() else sys.executable)
            model = Path(os.environ.get('PERSON_TYPE_MODEL', str(self.root / 'output/models/yolov8n-pose.pt')))
            if not model.is_file():
                self.error = '人物估算模型未准备好，请按 docs/PERSON_TYPE_DEMO.md 安装环境和模型。'
                raise ValueError(self.error)
            try:
                probe = subprocess.run([python, '-c', 'import importlib.util; raise SystemExit(0 if all(importlib.util.find_spec(m) for m in ("ultralytics", "cv2", "numpy")) else 1)'],
                                       capture_output=True, timeout=10)
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise ValueError('人物估算 Python 环境不可用，请检查电脑端配置。') from exc
            if probe.returncode:
                self.error = '人物估算缺少依赖，请按 docs/PERSON_TYPE_DEMO.md 安装独立环境。'
                raise ValueError(self.error)
            self.run_id = uuid.uuid4().hex
            folder = runtime / self.run_id
            folder.mkdir(parents=True)
            self.result_file = folder / 'result.json'
            self.log = (folder / 'worker.log').open('wb')
            command = [python, '-u', str(self.root / 'scripts/person_type_demo.py'),
                       '--source', self.source, '--snapshot', '--no-show', '--watch-parent', '--model', str(model.resolve()),
                       '--output', str(self.result_file), '--run-id', self.run_id, '--fps', '3']
            try:
                environment = os.environ.copy()
                environment['YOLO_CONFIG_DIR'] = str(runtime / 'config')
                environment['YOLO_AUTOINSTALL'] = 'false'
                environment['YOLO_OFFLINE'] = 'true'
                environment['MPLCONFIGDIR'] = str(runtime / 'matplotlib')
                self.process = subprocess.Popen(command, cwd=self.root, stdin=subprocess.PIPE,
                                                stdout=self.log, stderr=subprocess.STDOUT,
                                                env=environment,
                                                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            except OSError as exc:
                self.log.close()
                self.log = None
                raise ValueError('人物估算启动失败，请检查电脑端运行环境。') from exc
            self.error = ''
            return self._status()

    def stop(self):
        with self.lock:
            if self.process is not None:
                if self.process.poll() is None:
                    self.process.terminate()
                    try:
                        self.process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        self.process.kill()
                        self.process.wait(timeout=2)
                if self.process.stdin:
                    self.process.stdin.close()
                self.process = None
            if self.log:
                self.log.close()
                self.log = None
            self.error = ''
