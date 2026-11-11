"""Fault injection for atomic JSON writes; no business data is used."""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "dashboard"))
import json_storage


class JsonStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / "records.json"
        json_storage.atomic_write_json(self.path, [{"id": "old"}])
        self.before = self.path.read_bytes()

    def assert_original_preserved(self):
        self.assertEqual(self.path.read_bytes(), self.before)
        self.assertEqual(list(self.root.iterdir()), [self.path])

    def test_failed_replace_preserves_old_file_and_removes_temporary_file(self):
        with patch.object(json_storage.os, "replace", side_effect=OSError("disk failure")):
            with self.assertRaises(OSError):
                json_storage.atomic_write_json(self.path, [{"id": "new"}])
        self.assert_original_preserved()

    def test_serialization_failure_preserves_old_file(self):
        with self.assertRaises(TypeError):
            json_storage.atomic_write_json(self.path, {"invalid": object()})
        self.assert_original_preserved()

    def test_windows_sharing_violation_retries_then_persists(self):
        error = PermissionError("sharing violation")
        error.winerror = 32
        replace = json_storage.os.replace
        attempts = 0

        def transient_failure(source, destination):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise error
            return replace(source, destination)

        with patch.object(json_storage.os, "replace", side_effect=transient_failure):
            with patch.object(json_storage.time, "sleep"):
                json_storage.atomic_write_json(self.path, [{"id": "new"}])
        self.assertEqual(attempts, 2)
        self.assertEqual(json_storage.read_json_file(self.path, []), [{"id": "new"}])
        self.assertEqual(list(self.root.iterdir()), [self.path])

    def test_permanent_sharing_violation_stops_retrying_and_preserves_file(self):
        error = PermissionError("sharing violation")
        error.winerror = 32
        with patch.object(json_storage.os, "replace", side_effect=error) as replace:
            with patch.object(json_storage.time, "sleep"):
                with self.assertRaises(PermissionError):
                    json_storage.atomic_write_json(self.path, [{"id": "new"}])
        self.assertEqual(replace.call_count, 5)
        self.assert_original_preserved()
