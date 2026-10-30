"""Audit the exact Git-visible candidate files without staging or committing."""
import ast
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def verify(root=ROOT):
    root = Path(root).resolve()
    # Trust only this explicit checkout for these read-only audit commands.
    # This avoids global configuration changes when a sandbox created the copy.
    git = ["git", "-c", "safe.directory=" + root.as_posix(), "-C", str(root)]
    # Git always writes paths as UTF-8; decoding with the console code page (for
    # example cp936 on Chinese Windows) would break the comparison below.
    git_root = Path(
        subprocess.check_output(
            git + ["rev-parse", "--show-toplevel"], encoding="utf-8"
        ).strip()
    ).resolve()
    if git_root != root:
        raise RuntimeError("This directory must have its own Git repository")
    raw = subprocess.check_output(git + ["ls-files", "--cached", "--others", "--exclude-standard", "-z"])
    candidates = sorted(set(filter(None, raw.decode("utf-8").split("\0"))))
    errors = []
    total = 0
    sensitive = {"auth_config.json", "health_students.json", "health_records.json", "dialogue_messages.json", "dialogue_config.json", "analysis_config.json", "model_config.json", "messages.json", "events.json", "conversation_summaries.json", ".config.yaml"}
    for rel in candidates:
        path = root / rel
        if not path.is_file():
            errors.append((rel, "missing/non-file candidate"))
            continue
        total += path.stat().st_size
        if path.name in sensitive or any(part in {"models", "__pycache__", "tmp", "data", ".git"} for part in path.relative_to(root).parts):
            errors.append((rel, "private/runtime path"))
        if path.stat().st_size > 10 * 1024 * 1024:
            errors.append((rel, "unexpected file larger than 10 MiB"))
        if path.suffix in {".py", ".yaml", ".json", ".md", ".txt"}:
            text = path.read_text(encoding="utf-8-sig")
            if path.suffix == ".py":
                try:
                    ast.parse(text)
                except SyntaxError:
                    errors.append((rel, "Python syntax error"))
            if re.search(r"(?<![A-Za-z0-9])sk-[A-Za-z0-9_-]{16,}", text):
                errors.append((rel, "possible API credential; value withheld"))
            if re.search(r"(?i)(?:password|api_key|secret)\s*[:=]\s*[\"']([a-f0-9]{24,})[\"']", text):
                errors.append((rel, "possible hardcoded credential; value withheld"))
    nested = [p for p in root.rglob(".git") if p != root / ".git"]
    if nested:
        errors.append(("repository", "nested .git directory"))
    for rel, reason in errors:
        print("FAIL", rel, reason)
    print(json.dumps({"candidate_files": len(candidates), "total_MiB": round(total / 1048576, 2), "errors": len(errors)}, ensure_ascii=False))
    return not errors


if __name__ == "__main__":
    raise SystemExit(0 if verify() else 1)
