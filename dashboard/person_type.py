"""成人/儿童画面估算的轻量启发式规则。

这不是年龄识别，也不是身份识别。它只使用 YOLOv8 pose 的关键点比例，
输出“疑似成人/疑似儿童/未知”，用于课堂演示和人工复核。
"""

from __future__ import annotations

import math
from collections import Counter

HEAD_POINTS = (0, 1, 2, 3, 4)
SHOULDER_POINTS = (5, 6)
HIP_POINTS = (11, 12)
ANKLE_POINTS = (15, 16)


def _valid_point(points, scores, index: int, min_confidence: float):
    if index >= len(points) or index >= len(scores):
        return None
    point = points[index]
    score = scores[index]
    if len(point) < 2 or score is None or not math.isfinite(float(score)) or float(score) < min_confidence:
        return None
    x, y = float(point[0]), float(point[1])
    if not math.isfinite(x) or not math.isfinite(y):
        return None
    if x == 0 and y == 0:
        return None
    return x, y, float(score)


def estimate_person_type(
    keypoints,
    scores=None,
    bbox=None,
    child_threshold: float = 0.155,
    adult_threshold: float = 0.135,
    min_confidence: float = 0.25,
) -> dict:
    """根据姿态关键点估算人物类型。

    head_ratio = (肩部高度 - 头顶高度) / (脚踝高度 - 头顶高度)。
    儿童通常头身比例更大；阈值必须按实际摄像头位置重新校准。
    """
    if scores is None:
        scores = [1.0] * len(keypoints)
    if len(keypoints) < 17:
        return {
            "person_type": "unknown",
            "confidence": 0.0,
            "head_ratio": None,
            "reason": "关键点不足",
        }

    head = [
        point for index in HEAD_POINTS
        if (point := _valid_point(keypoints, scores, index, min_confidence)) is not None
    ]
    shoulders = [
        point for index in SHOULDER_POINTS
        if (point := _valid_point(keypoints, scores, index, min_confidence)) is not None
    ]
    hips = [
        point for index in HIP_POINTS
        if (point := _valid_point(keypoints, scores, index, min_confidence)) is not None
    ]
    ankles = [
        point for index in ANKLE_POINTS
        if (point := _valid_point(keypoints, scores, index, min_confidence)) is not None
    ]
    if not head or not shoulders or not hips:
        return {
            "person_type": "unknown",
            "confidence": 0.0,
            "head_ratio": None,
            "reason": "头肩髋关键点不足",
        }

    head_y = min(point[1] for point in head)
    shoulder_y = sum(point[1] for point in shoulders) / len(shoulders)
    hip_y = sum(point[1] for point in hips) / len(hips)
    if ankles:
        ankle_y = max(point[1] for point in ankles)
    elif bbox is not None and len(bbox) >= 4:
        ankle_y = float(bbox[3])
    else:
        return {
            "person_type": "unknown",
            "confidence": 0.0,
            "head_ratio": None,
            "reason": "脚踝关键点不足",
        }

    body_height = ankle_y - head_y
    if body_height <= 1 or shoulder_y <= head_y or hip_y <= shoulder_y:
        return {
            "person_type": "unknown",
            "confidence": 0.0,
            "head_ratio": None,
            "reason": "身体比例无效",
        }

    head_ratio = (shoulder_y - head_y) / body_height
    if head_ratio >= child_threshold:
        person_type = "child"
    elif head_ratio <= adult_threshold:
        person_type = "adult"
    else:
        person_type = "unknown"

    all_scores = [
        point[2] for point in head + shoulders + hips + ankles
    ]
    average_score = sum(all_scores) / len(all_scores)
    confidence = round(min(0.99, max(0.0, average_score)), 2) if person_type != "unknown" else 0.0
    return {
        "person_type": person_type,
        "confidence": confidence,
        "head_ratio": round(head_ratio, 4),
        "shoulder_width": round(abs(shoulders[0][0] - shoulders[-1][0]), 2),
        "body_height": round(body_height, 2),
        "reason": "头身比例估算" if person_type != "unknown" else "比例处于不确定区间",
    }


def majority_vote(history, min_samples: int = 3, threshold: float = 0.6) -> dict:
    """对同一轨迹的多帧结果做多数投票，避免单帧抖动。"""
    values = [
        item.get("person_type") if isinstance(item, dict) else item
        for item in (history or [])
    ]
    valid = [value for value in values if value in ("adult", "child")]
    if len(valid) < min_samples or not values or values[-1] not in ("adult", "child"):
        return {"person_type": "unknown", "confidence": 0.0, "samples": len(valid)}
    counts = Counter(valid)
    person_type, count = counts.most_common(1)[0]
    ratio = count / len(values)
    if ratio < threshold:
        return {"person_type": "unknown", "confidence": 0.0, "samples": len(valid)}
    return {
        "person_type": person_type,
        "confidence": round(ratio, 2),
        "samples": len(valid),
    }


def summarize_person_types(persons) -> dict:
    counts = {"adult": 0, "child": 0, "unknown": 0}
    for person in persons or []:
        person_type = person.get("person_type", "unknown")
        if person_type not in counts:
            person_type = "unknown"
        counts[person_type] += 1
    counts["total"] = sum(counts.values())
    return counts
