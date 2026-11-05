"""Persistence boundary for dashboard business records."""

import hashlib
import os
from collections.abc import Callable
from pathlib import Path
from typing import Generic, TypeVar

from json_storage import atomic_write_json, read_json_file

Snapshot = TypeVar("Snapshot", list[dict], dict[str, dict])


class JsonRepository(Generic[Snapshot]):
    """Load or replace a complete collection in its existing JSON format."""

    def __init__(self, path: Path, empty: Callable[[], Snapshot]):
        self.path = path
        self._empty = empty

    def load(self) -> Snapshot:
        empty = self._empty()
        saved = read_json_file(self.path, empty)
        return saved if isinstance(saved, type(empty)) else empty

    def save(self, records: Snapshot) -> None:
        atomic_write_json(self.path, records)


class EventRepository(JsonRepository[list[dict]]):
    def __init__(self, path: Path):
        super().__init__(path, list)

    def snapshot_path(self, event_id: str) -> Path:
        key = hashlib.sha256(event_id.encode("utf-8")).hexdigest()
        return self.path.parent / "event_snapshots" / f"{key}.jpg"


class DashboardRepositories:
    """Bind each business collection to a configurable store at startup."""

    def __init__(self, root: Path):
        def path(variable: str, name: str) -> Path:
            return Path(os.environ.get(variable, str(root / name)))

        self.events = EventRepository(path("EVENTS_FILE", "events.json"))
        self.messages = JsonRepository[list[dict]](path("DIALOGUE_DATA_FILE", "dialogue_messages.json"), list)
        self.students = JsonRepository[list[dict]](path("HEALTH_STUDENTS_FILE", "health_students.json"), list)
        self.health_records = JsonRepository[list[dict]](path("HEALTH_RECORDS_FILE", "health_records.json"), list)
        self.summaries = JsonRepository[dict[str, dict]](
            path("CONVERSATION_SUMMARIES_FILE", "conversation_summaries.json"), dict
        )
