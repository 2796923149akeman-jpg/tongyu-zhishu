"""Check local prerequisites; no network requests or credential output."""
import importlib.util
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def check(root=ROOT):
    root = Path(root)
    problems = []
    if sys.version_info < (3, 10):
        problems.append("Python 3.10 or newer is required; validated environment is 3.10")
    for name in ["yaml", "torch", "torchaudio", "funasr", "onnxruntime", "websockets", "aiohttp", "openai", "edge_tts", "aioconsole", "opuslib_next"]:
        if importlib.util.find_spec(name) is None:
            problems.append("Missing Python module: " + name)
    if not shutil.which("ffmpeg"):
        problems.append("ffmpeg not found on PATH")
    for name in ["xiaozhi-server/data/.config.yaml"]:
        if not (root / name).is_file():
            problems.append("Initialize local configuration: " + name)
    manifest = json.loads((root / "docs/model-files.json").read_text(encoding="utf-8"))
    for item in manifest:
        p = root / "xiaozhi-server/models" / item["path"]
        if not p.is_file():
            problems.append("Missing model file: " + item["path"])
        elif p.stat().st_size != item["bytes"]:
            problems.append("Model differs from baseline (check compatibility): " + item["path"])
    for message in problems:
        print("NEEDS SETUP:", message)
    if not problems:
        print("Local runtime prerequisites OK (API key validity / hardware not tested).")
    return not problems


if __name__ == "__main__":
    raise SystemExit(0 if check() else 1)
