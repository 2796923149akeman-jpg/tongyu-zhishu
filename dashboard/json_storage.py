"""Read JSON snapshots and replace them atomically."""

import json
import os
import tempfile
import time
from pathlib import Path


def read_json_file(path: Path, fallback):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return fallback


def atomic_write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        # Windows readers can briefly prevent replacement of an open file.
        for delay in (0.01, 0.025, 0.05, 0.1, None):
            try:
                os.replace(temporary_name, path)
                break
            except PermissionError as exc:
                if delay is None or getattr(exc, "winerror", None) not in (5, 32, 33):
                    raise
                time.sleep(delay)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)
