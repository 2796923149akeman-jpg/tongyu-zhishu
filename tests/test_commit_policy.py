import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_commit_policy():
    path = ROOT / "scripts" / "check_commit_messages.py"
    spec = importlib.util.spec_from_file_location("test_commit_policy_module", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CommitPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy = load_commit_policy()

    def test_accepts_conventional_subjects_and_merge_commits(self):
        self.assertTrue(
            self.policy.is_valid_subject(
                "feat(events): add participant assignment by student name"
            )
        )
        self.assertTrue(self.policy.is_valid_subject("docs: explain demo startup"))
        self.assertTrue(
            self.policy.is_valid_subject(
                "Merge pull request #18 from example/fix/final-rubric"
            )
        )

    def test_rejects_non_conventional_or_non_imperative_subjects(self):
        invalid = [
            "feat:add participant assignment",
            "Assign registered accounts and link records",
            "docs: Add a title case summary",
            "docs: add a trailing period.",
            "unknown: change behavior",
        ]
        for subject in invalid:
            with self.subTest(subject=subject):
                self.assertFalse(self.policy.is_valid_subject(subject))

    def test_rejects_long_subject(self):
        subject = "feat(events): " + ("a" * 60)
        self.assertGreater(len(subject), 72)
        self.assertFalse(self.policy.is_valid_subject(subject))

    def test_commit_message_hook_reads_first_content_line(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "COMMIT_EDITMSG"
            path.write_text(
                "\n# comment\nfix(reports): preserve event source\n\nbody\n",
                encoding="utf-8",
            )
            status = self.policy.main([str(path)])
        self.assertEqual(status, 0)


if __name__ == "__main__":
    unittest.main()
