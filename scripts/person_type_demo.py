"""课堂演示：YOLOv8 Pose 估算画面中的疑似儿童/疑似成人。

使用头身比例和多帧投票，不做年龄或身份识别。结果写入
dashboard/person_types.json，供实时监控页显示人数。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = ROOT / "dashboard"
if str(DASHBOARD) not in sys.path:
    sys.path.insert(0, str(DASHBOARD))

from person_type import estimate_person_type, majority_vote, summarize_person_types  # noqa: E402


def parse_args():
    parser = argparse.ArgumentParser(description="YOLOv8 Pose adult/child classroom demo")
    parser.add_argument("--source", default="0", help="摄像头编号 0 或 RDK video_feed URL")
    parser.add_argument("--model", default="yolov8n-pose.pt", help="YOLOv8 pose 模型路径")
    parser.add_argument("--output", default=str(DASHBOARD / "person_types.json"), help="结果 JSON 路径")
    parser.add_argument("--no-show", action="store_true", help="不打开本地预览窗口")
    parser.add_argument("--json-interval", type=int, default=5, help="每 N 帧写一次 JSON")
    parser.add_argument("--child-threshold", type=float, default=0.155, help="头身比儿童阈值")
    parser.add_argument("--adult-threshold", type=float, default=0.135, help="头身比成人阈值")
    parser.add_argument("--min-keypoint-conf", type=float, default=0.25, help="关键点最低置信度")
    parser.add_argument("--min-vote-samples", type=int, default=3, help="同一轨迹至少观察帧数")
    parser.add_argument("--device", default=None, help="可选设备，例如 cpu 或 0")
    return parser.parse_args()


def atomic_write_json(path: Path, payload: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def main():
    args = parse_args()
    if args.child_threshold <= args.adult_threshold:
        raise SystemExit("child-threshold must be greater than adult-threshold")
    try:
        import cv2
        import numpy as np
        from ultralytics import YOLO
    except ImportError as exc:
        raise SystemExit(
            "缺少演示依赖，请先安装：pip install -r scripts/requirements-person-type.txt"
        ) from exc

    source = int(args.source) if str(args.source).isdigit() else args.source
    model = YOLO(args.model)
    capture = cv2.VideoCapture(source)
    if not capture.isOpened():
        raise SystemExit(f"无法打开视频源：{args.source}")

    histories = defaultdict(list)
    output_path = Path(args.output)
    frame_index = 0

    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            frame_index += 1
            predict_args = {
                "persist": True,
                "classes": [0],
                "verbose": False,
            }
            if args.device:
                predict_args["device"] = args.device
            results = model.track(frame, **predict_args)
            result = results[0] if results else None
            persons = []

            if result is not None and result.boxes is not None:
                boxes = result.boxes.xyxy.cpu().numpy()
                scores = result.boxes.conf.cpu().numpy()
                ids = result.boxes.id.cpu().numpy() if result.boxes.id is not None else None
                keypoints = result.keypoints.xy.cpu().numpy() if result.keypoints is not None else []
                if result.keypoints is not None and result.keypoints.conf is not None:
                    keypoint_scores = result.keypoints.conf.cpu().numpy()
                else:
                    keypoint_scores = [
                        [1.0] * len(person_points) for person_points in keypoints
                    ]

                for index in range(min(len(boxes), len(keypoints))):
                    track_id = str(int(ids[index])) if ids is not None else f"frame-{index}"
                    estimate = estimate_person_type(
                        keypoints[index].tolist(),
                        keypoint_scores[index].tolist(),
                        boxes[index].tolist(),
                        child_threshold=args.child_threshold,
                        adult_threshold=args.adult_threshold,
                        min_confidence=args.min_keypoint_conf,
                    )
                    histories[track_id].append(estimate)
                    histories[track_id] = histories[track_id][-15:]
                    vote = majority_vote(
                        histories[track_id],
                        min_samples=max(1, args.min_vote_samples),
                    )
                    person_type = vote["person_type"]
                    confidence = vote["confidence"]
                    person = {
                        "person_id": track_id,
                        "person_type": person_type,
                        "confidence": confidence,
                        "head_ratio": estimate.get("head_ratio"),
                        "bbox": [round(float(value), 1) for value in boxes[index].tolist()],
                    }
                    persons.append(person)

                    x1, y1, x2, y2 = [int(value) for value in boxes[index].tolist()]
                    colors = {
                        "child": (80, 190, 120),
                        "adult": (220, 150, 70),
                        "unknown": (160, 160, 160),
                    }
                    color = colors[person_type]
                    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                    labels = {
                        "child": "疑似儿童",
                        "adult": "疑似成人",
                        "unknown": "人物类型未知",
                    }
                    label = f"{labels[person_type]} {confidence:.0%} #{track_id}"
                    cv2.putText(
                        frame,
                        label,
                        (x1, max(22, y1 - 8)),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.62,
                        color,
                        2,
                        cv2.LINE_AA,
                    )

            counts = summarize_person_types(persons)
            if frame_index % max(1, args.json_interval) == 0 or frame_index == 1:
                payload = {
                    "generated_at": datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds"),
                    "estimate": True,
                    "disclaimer": "疑似成人/儿童为课堂演示估算，不是年龄或身份识别，需人工复核。",
                    "source": str(args.source),
                    "model": args.model,
                    "counts": counts,
                    "persons": persons,
                }
                atomic_write_json(output_path, payload)

            if not args.no_show:
                summary = (
                    f"child {counts['child']} | adult {counts['adult']} | "
                    f"unknown {counts['unknown']}"
                )
                cv2.putText(
                    frame,
                    summary,
                    (16, frame.shape[0] - 18),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.56,
                    (235, 235, 235),
                    2,
                    cv2.LINE_AA,
                )
                cv2.imshow("Tongyu person type demo (estimated)", frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
    except KeyboardInterrupt:
        pass
    finally:
        capture.release()
        if not args.no_show:
            cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
