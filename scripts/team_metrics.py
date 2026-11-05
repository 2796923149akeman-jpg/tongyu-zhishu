"""Generate team contribution metrics from git history.

Usage:
    python scripts/team_metrics.py            # Markdown table
    python scripts/team_metrics.py --json     # JSON for further processing

The script only reads git metadata; it never changes the repository.
"""

from __future__ import annotations

import argparse
import collections
import json
import subprocess


def git(*args: str) -> str:
    return subprocess.check_output(
        ["git", *args], text=True, encoding="utf-8", errors="replace"
    )


def collect() -> dict:
    log = git("log", "--numstat", "--date=short", "--format=__AUTHOR__%an|%ad")
    authors: dict[str, dict] = collections.defaultdict(
        lambda: {
            "commits": 0,
            "added": 0,
            "deleted": 0,
            "files": 0,
            "areas": collections.Counter(),
            "first": None,
            "last": None,
        }
    )
    current = None
    for line in log.splitlines():
        if line.startswith("__AUTHOR__"):
            payload = line[len("__AUTHOR__"):]
            name, _, date = payload.partition("|")
            current = name.strip()
            entry = authors[current]
            entry["commits"] += 1
            entry["first"] = entry["first"] or date
            entry["last"] = date
            continue
        if not current or not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        added, deleted, path = parts
        if not added.isdigit() or not deleted.isdigit():
            continue
        entry = authors[current]
        entry["added"] += int(added)
        entry["deleted"] += int(deleted)
        entry["files"] += 1
        area = path.split("/")[0] if "/" in path else "(root)"
        entry["areas"][area] += 1

    order = sorted(authors.items(), key=lambda item: item[1]["commits"], reverse=True)
    return {
        "commits": int(git("rev-list", "--count", "HEAD").strip()),
        "branch": git("rev-parse", "--abbrev-ref", "HEAD").strip(),
        "authors": [
            {
                "author": name,
                "commits": data["commits"],
                "added": data["added"],
                "deleted": data["deleted"],
                "net": data["added"] - data["deleted"],
                "files": data["files"],
                "areas": dict(data["areas"].most_common(6)),
                "first": data["first"],
                "last": data["last"],
            }
            for name, data in order
        ],
    }


def to_markdown(data: dict) -> str:
    lines = [
        f"Branch `{data['branch']}`, {data['commits']} commits.",
        "",
        "| Author | Commits | Added | Deleted | Net | Files | Main areas |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for item in data["authors"]:
        areas = ", ".join(f"{name} ({count})" for name, count in item["areas"].items())
        lines.append(
            f"| {item['author']} | {item['commits']} | {item['added']} | "
            f"{item['deleted']} | {item['net']} | {item['files']} | {areas} |"
        )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Team contribution metrics")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    data = collect()
    print(json.dumps(data, ensure_ascii=False, indent=2) if args.json else to_markdown(data))


if __name__ == "__main__":
    main()
