"""Local benchmark for event storage and lexicon emotion analysis.

Usage:
    python scripts/benchmark_events.py [--iterations 200]

Results are written to stdout as JSON; use them in docs/EXPERIMENTS.md.
The script uses a temporary directory and never touches runtime data.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import statistics
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = [
    ("今天和小朋友玩了滑梯，很开心", "none"),
    ("我喜欢画画，老师夸我了", "none"),
    ("我不难过，明天还想来", "none"),
    ("我每天都哭", "watch"),
    ("我不想上学", "watch"),
    ("我被欺负了", "watch"),
    ("我睡不着，有点害怕", "watch"),
    ("我不想活了", "urgent"),
    ("救命，有人打我", "urgent"),
    ("我喘不过气", "urgent"),
]


def load_server():
    spec = importlib.util.spec_from_file_location(
        "dashboard_benchmark", ROOT / "dashboard" / "server.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def percentile(values: list[float], ratio: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    index = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * ratio))))
    return ordered[index]


def summarize(values: list[float]) -> dict:
    return {
        "count": len(values),
        "mean_ms": round(statistics.mean(values) * 1000, 3),
        "p50_ms": round(percentile(values, 0.50) * 1000, 3),
        "p95_ms": round(percentile(values, 0.95) * 1000, 3),
        "max_ms": round(max(values) * 1000, 3),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=200)
    args = parser.parse_args()
    web = load_server()
    temp = tempfile.TemporaryDirectory()
    try:
        web.DATA.events.path = Path(temp.name) / "events.json"
        web.EVIDENCE_DIR = Path(temp.name) / "evidence"
        web.reload_events()

        create_times, query_times = [], []
        for index in range(args.iterations):
            payload = {
                "event_type": "fall" if index % 2 == 0 else "environment",
                "level": "urgent" if index % 2 == 0 else "watch",
                "source": "rdk" if index % 2 == 0 else "sensor",
                "occurred_at": web.now_iso(),
                "summary": f"benchmark event {index}",
                "detail": "local benchmark",
                "dedupe_key": f"bench-{index}",
            }
            started = time.perf_counter()
            web.create_event(payload)
            create_times.append(time.perf_counter() - started)

            started = time.perf_counter()
            web.query_events({"limit": ["50"], "sort": ["newest"]})
            query_times.append(time.perf_counter() - started)

        correct = 0
        expected_positive = actual_positive = true_positive = 0
        for text, expected in SAMPLES:
            result = web.analyze_lexicon(text, web.EMOTION_LEXICON)
            actual = result.get("attention", "none")
            if actual == expected:
                correct += 1
            if expected != "none":
                expected_positive += 1
            if actual != "none":
                actual_positive += 1
            if expected != "none" and actual != "none":
                true_positive += 1

        precision = true_positive / actual_positive if actual_positive else 0.0
        recall = true_positive / expected_positive if expected_positive else 0.0
        result = {
            "iterations": args.iterations,
            "event_create": summarize(create_times),
            "event_query": summarize(query_times),
            "emotion_lexicon": {
                "samples": len(SAMPLES),
                "exact_accuracy": round(correct / len(SAMPLES), 3),
                "attention_precision": round(precision, 3),
                "attention_recall": round(recall, 3),
            },
            "measured_at": web.now_iso(),
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
    finally:
        temp.cleanup()


if __name__ == "__main__":
    main()
