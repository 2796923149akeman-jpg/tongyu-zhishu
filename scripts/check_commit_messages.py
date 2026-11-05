"""Validate commit subjects against the repository's Conventional Commits policy."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

CONVENTIONAL_SUBJECT = re.compile(
    r"^(?P<type>build|chore|ci|docs|feat|fix|perf|refactor|revert|style|test)"
    r"(?:\((?P<scope>[a-z0-9][a-z0-9._/-]*)\))?: "
    r"(?P<summary>[a-z0-9][^\r\n]*)$",
    re.ASCII,
)


def is_valid_subject(subject: str) -> bool:
    """Return whether a subject follows the repository's commit policy."""
    if subject.startswith("Merge "):
        return True
    if not subject or len(subject) > 72:
        return False
    match = CONVENTIONAL_SUBJECT.fullmatch(subject)
    if not match:
        return False
    return not match.group("summary").endswith(".")


def first_message_line(message: str) -> str:
    """Return the first non-empty, non-comment line from a commit message."""
    for line in message.splitlines():
        candidate = line.strip()
        if candidate and not candidate.startswith("#"):
            return candidate
    return ""


def git_subject(commit: str) -> str:
    """Read one commit subject from Git."""
    return subprocess.check_output(
        ["git", "show", "-s", "--format=%s", commit],
        text=True,
        encoding="utf-8",
    ).strip()


def commits_in_range(revision_range: str) -> list[str]:
    """List non-merge commits in a revision range in chronological order."""
    output = subprocess.check_output(
        ["git", "rev-list", "--reverse", "--no-merges", revision_range],
        text=True,
        encoding="utf-8",
    )
    return [line for line in output.splitlines() if line]


def validate_range(revision_range: str) -> list[tuple[str, str]]:
    """Return invalid commit subjects in a revision range."""
    invalid: list[tuple[str, str]] = []
    for commit in commits_in_range(revision_range):
        subject = git_subject(commit)
        if not is_valid_subject(subject):
            invalid.append((commit[:12], subject))
    return invalid


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "message_file",
        nargs="?",
        help="Commit message file passed by the commit-msg hook.",
    )
    parser.add_argument(
        "--range",
        dest="revision_range",
        help="Git revision range to validate, for example origin/main..HEAD.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.message_file and args.revision_range:
        print("Specify either message_file or --range, not both.", file=sys.stderr)
        return 2

    if args.revision_range:
        try:
            invalid = validate_range(args.revision_range)
        except subprocess.CalledProcessError as exc:
            print(f"Unable to read commit range: {exc}", file=sys.stderr)
            return 2
        for commit, subject in invalid:
            print(f"{commit}  {subject}", file=sys.stderr)
        if invalid:
            print(
                "Commit subjects must use 'type(scope): imperative summary' "
                "and stay within 72 characters.",
                file=sys.stderr,
            )
            return 1
        print(f"Commit policy passed for {args.revision_range}.")
        return 0

    if args.message_file:
        path = Path(args.message_file)
        subject = first_message_line(path.read_text(encoding="utf-8"))
    else:
        subject = git_subject("HEAD")

    if not is_valid_subject(subject):
        print(f"Invalid commit subject: {subject}", file=sys.stderr)
        print(
            "Expected format: type(scope): imperative summary",
            file=sys.stderr,
        )
        print(
            "Allowed types: build, chore, ci, docs, feat, fix, perf, "
            "refactor, revert, style, test.",
            file=sys.stderr,
        )
        return 1
    print(f"Commit subject passed: {subject}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
