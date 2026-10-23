"""Emotion and conversation analysis for the local dialogue dashboard.

The lexicon path never sends dialogue off the machine. Model analysis uses an
OpenAI-compatible endpoint selected by the local operator. Results are signals
for review rather than medical, psychological, or safety diagnoses.
"""
from __future__ import annotations

import json
import math
import re
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse


EMOTION_NAMES = {
    "happy": "开心", "sad": "难过", "angry": "生气", "scared": "害怕",
    "anxious": "焦虑", "disgusted": "厌恶", "surprised": "惊讶", "neutral": "平静",
}
NEGATIVE = {"sad", "angry", "scared", "anxious", "disgusted"}
ATTENTION_ORDER = {"none": 0, "watch": 1, "urgent": 2}
DEFAULT_ANALYSIS_CONFIG = {
    "summary_enabled": True,
    "summary_model_source": "xiaozhi",
    "summary_base_url": "https://api.deepseek.com",
    "summary_model_name": "deepseek-v4-pro",
    "summary_api_key": "",
    "emotion_mode": "model_fallback",
    "emotion_model_source": "shared",
    "emotion_base_url": "https://api.deepseek.com",
    "emotion_model_name": "deepseek-v4-pro",
    "emotion_api_key": "",
}
SECRET_FIELDS = {"summary_api_key", "emotion_api_key"}


def load_lexicon(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data.get("categories"), dict) or not isinstance(data.get("attention"), dict):
        raise ValueError("Invalid emotion lexicon")
    return data


def _matches(text: str, terms: list[str]) -> list[str]:
    return [term for term in sorted(set(terms), key=len, reverse=True) if term and term in text]


def analyze_lexicon(text: str, lexicon: dict) -> dict:
    text = str(text or "").strip()
    scores = Counter()
    matched = {}
    negations = lexicon.get("negations", [])
    intensifiers = lexicon.get("intensifiers", [])
    for label, terms in lexicon.get("categories", {}).items():
        hits = _matches(text, terms)
        if not hits:
            continue
        matched[label] = hits
        for term in hits:
            position = text.find(term)
            prefix = text[max(0, position - 4):position]
            negated = any(prefix.endswith(word) for word in negations)
            strength = 0.25 if negated else 1.0
            if any(word in prefix for word in intensifiers):
                strength *= 1.5
            scores[label] += strength

    label = scores.most_common(1)[0][0] if scores else "neutral"
    top_score = float(scores.get(label, 0))
    confidence = 0.5 if label == "neutral" else min(0.95, 0.52 + 0.12 * math.log2(top_score + 1))
    urgent = _matches(text, lexicon.get("attention", {}).get("urgent", []))
    watch = _matches(text, lexicon.get("attention", {}).get("watch", []))
    if urgent:
        attention, attention_reason = "urgent", f"出现需优先核实的表达：{urgent[0]}"
    elif watch or (label in NEGATIVE and top_score >= 2.5):
        signal = watch[0] if watch else EMOTION_NAMES[label]
        attention, attention_reason = "watch", f"出现建议持续留意的表达：{signal}"
    else:
        attention, attention_reason = "none", "未发现明确的重点留意信号"
    words = matched.get(label, [])[:3]
    reason = "未命中明显情绪词" if not words else "识别到：" + "、".join(words)
    return {
        "label": label,
        "label_text": EMOTION_NAMES[label],
        "valence": "negative" if label in NEGATIVE else ("positive" if label == "happy" else "neutral"),
        "confidence": round(confidence, 2),
        "attention": attention,
        "attention_reason": attention_reason,
        "reason": reason,
        "source": "lexicon",
        "analyzed_at": datetime.now(timezone.utc).isoformat(),
    }


def _valid_url(value: str) -> bool:
    try:
        parsed = urlparse(value)
        return parsed.scheme == "https" or (parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1", "::1"})
    except ValueError:
        return False


def validate_analysis_config(data: dict, current: dict | None = None) -> dict:
    if not isinstance(data, dict):
        raise ValueError("Configuration must be an object")
    allowed = set(DEFAULT_ANALYSIS_CONFIG) | {"clear_summary_api_key", "clear_emotion_api_key"}
    if set(data) - allowed:
        raise ValueError("Unknown analysis configuration field")
    result = DEFAULT_ANALYSIS_CONFIG.copy()
    result.update(current or {})
    for key, value in data.items():
        if key not in SECRET_FIELDS and not key.startswith("clear_"):
            result[key] = value
    for key in SECRET_FIELDS:
        clear_key = "clear_" + key
        if data.get(clear_key):
            result[key] = ""
        elif isinstance(data.get(key), str) and data[key].strip():
            result[key] = data[key].strip()
    if not isinstance(result["summary_enabled"], bool):
        raise ValueError("Invalid summary switch")
    if result["summary_model_source"] not in {"xiaozhi", "custom"}:
        raise ValueError("Invalid summary model source")
    if result["emotion_mode"] not in {"model_fallback", "lexicon"}:
        raise ValueError("Invalid emotion mode")
    if result["emotion_model_source"] not in {"shared", "xiaozhi", "custom"}:
        raise ValueError("Invalid emotion model source")
    for prefix in ("summary", "emotion"):
        url, model = result[f"{prefix}_base_url"], result[f"{prefix}_model_name"]
        if not isinstance(url, str) or len(url) > 300 or (url and not _valid_url(url.rstrip("/"))):
            raise ValueError("Invalid model URL")
        if not isinstance(model, str) or len(model) > 120:
            raise ValueError("Invalid model name")
        result[f"{prefix}_base_url"] = url.rstrip("/")
        result[f"{prefix}_model_name"] = model.strip()
    for key in SECRET_FIELDS:
        if not isinstance(result[key], str) or len(result[key]) > 500:
            raise ValueError("Invalid API key")
    return result


def public_analysis_config(config: dict, xiaozhi_model: dict | None) -> dict:
    result = {key: value for key, value in config.items() if key not in SECRET_FIELDS}
    result["summary_api_key_set"] = bool(config.get("summary_api_key"))
    result["emotion_api_key_set"] = bool(config.get("emotion_api_key"))
    result["xiaozhi_model_available"] = bool(xiaozhi_model and xiaozhi_model.get("api_key"))
    result["xiaozhi_model_name"] = (xiaozhi_model or {}).get("model_name", "")
    return result


def load_xiaozhi_model(project_root: Path) -> dict | None:
    path = project_root / "xiaozhi-server" / "data" / ".config.yaml"
    try:
        import yaml
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        selected = data.get("selected_module", {}).get("LLM")
        model = data.get("LLM", {}).get(selected, {})
        base_url = model.get("base_url", model.get("url", ""))
        if not selected or not base_url or not model.get("model_name"):
            return None
        return {"base_url": base_url.rstrip("/"), "model_name": model["model_name"], "api_key": model.get("api_key", "")}
    except (OSError, UnicodeError, ValueError, ImportError, AttributeError):
        return None


def resolve_model(config: dict, purpose: str, project_root: Path) -> dict | None:
    if purpose == "summary":
        source = config["summary_model_source"]
    else:
        source = config["emotion_model_source"]
        if source == "shared":
            return resolve_model(config, "summary", project_root)
    if source == "xiaozhi":
        return load_xiaozhi_model(project_root)
    model = {
        "base_url": config[f"{purpose}_base_url"],
        "model_name": config[f"{purpose}_model_name"],
        "api_key": config[f"{purpose}_api_key"],
    }
    return model if all(model.values()) else None


def _extract_json(content: str) -> dict:
    content = content.strip()
    content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content, flags=re.I)
    try:
        value = json.loads(content)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", content, flags=re.S)
        if not match:
            raise ValueError("Model did not return JSON")
        value = json.loads(match.group(0))
    if not isinstance(value, dict):
        raise ValueError("Model response must be an object")
    return value


def call_json_model(model: dict, system_prompt: str, user_prompt: str, max_tokens: int = 500) -> dict:
    payload = {
        "model": model["model_name"], "stream": False, "temperature": 0,
        "max_tokens": max_tokens,
        "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
        "response_format": {"type": "json_object"},
    }
    if "api.deepseek.com" in model["base_url"]:
        payload["thinking"] = {"type": "disabled"}
    request = urllib.request.Request(
        model["base_url"].rstrip("/") + "/chat/completions",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"), method="POST",
        headers={"Authorization": "Bearer " + model["api_key"], "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=25) as response:
        data = json.loads(response.read().decode("utf-8"))
    return _extract_json(data["choices"][0]["message"]["content"])


def analyze_emotion(text: str, config: dict, lexicon: dict, project_root: Path) -> dict:
    local = analyze_lexicon(text, lexicon)
    if config["emotion_mode"] == "lexicon":
        return local
    model = resolve_model(config, "emotion", project_root)
    if not model:
        return local | {"source": "lexicon-no-model"}
    try:
        result = call_json_model(
            model,
            "你是儿童陪伴场景的文本情绪分类器。只输出JSON，不作诊断。label只能是happy、sad、angry、scared、anxious、disgusted、surprised、neutral；attention只能是none、watch、urgent。明确的自伤、暴力、虐待、呼吸困难等安全表达为urgent；持续或强烈负面表达为watch。reason和attention_reason各不超过30个汉字。",
            "分析这句话：" + text,
            350,
        )
        label = result.get("label") if result.get("label") in EMOTION_NAMES else local["label"]
        attention = result.get("attention") if result.get("attention") in ATTENTION_ORDER else local["attention"]
        if ATTENTION_ORDER[local["attention"]] > ATTENTION_ORDER[attention]:
            attention = local["attention"]
        confidence = result.get("confidence", 0.75)
        try:
            confidence = max(0.0, min(1.0, float(confidence)))
        except (TypeError, ValueError):
            confidence = 0.75
        return {
            "label": label, "label_text": EMOTION_NAMES[label],
            "valence": "negative" if label in NEGATIVE else ("positive" if label == "happy" else "neutral"),
            "confidence": round(confidence, 2), "attention": attention,
            "attention_reason": local["attention_reason"] if attention == local["attention"] and attention != "none" else str(result.get("attention_reason", "模型未发现明确留意信号"))[:60],
            "reason": str(result.get("reason", local["reason"]))[:60], "source": "model+lexicon",
            "model_name": model["model_name"], "analyzed_at": datetime.now(timezone.utc).isoformat(),
        }
    except Exception:
        return local | {"source": "lexicon-fallback"}


def local_conversation_summary(messages: list[dict], session_id: str) -> dict:
    user_messages = [m for m in messages if m.get("role") == "user"]
    emotions = [m.get("emotion", {}) for m in user_messages]
    labels = [e.get("label") for e in emotions if e.get("label")]
    dominant = Counter(labels).most_common(1)[0][0] if labels else "neutral"
    attention = max((e.get("attention", "none") for e in emotions), key=lambda value: ATTENTION_ORDER.get(value, 0), default="none")
    attention_reasons = [e.get("attention_reason") for e in emotions if e.get("attention") == attention and e.get("attention_reason")]
    first = (user_messages[0].get("text", "") if user_messages else "尚无用户消息").strip()
    latest = (user_messages[-1].get("text", "") if user_messages else first).strip()
    title = (first[:18] + ("…" if len(first) > 18 else "")) or "未命名会话"
    summary = f"共 {len(messages)} 条消息，用户最近提到：“{latest[:48]}{'…' if len(latest) > 48 else ''}”"
    return {
        "session_id": session_id, "device_id": messages[-1].get("device_id", "") if messages else "",
        "title": title, "summary": summary, "dominant_emotion": dominant,
        "dominant_emotion_text": EMOTION_NAMES.get(dominant, "平静"), "attention": attention,
        "attention_reason": attention_reasons[0] if attention_reasons else "未发现明确的重点留意信号",
        "message_count": len(messages), "source": "local", "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def summarize_conversation(messages: list[dict], session_id: str, config: dict, project_root: Path) -> dict:
    local = local_conversation_summary(messages, session_id)
    if not config["summary_enabled"]:
        return local | {"source": "local-summary-disabled"}
    model = resolve_model(config, "summary", project_root)
    if not model:
        return local | {"source": "local-no-model"}
    transcript = []
    for item in messages[-30:]:
        role = "用户" if item.get("role") == "user" else "助手"
        emotion = item.get("emotion", {}).get("label_text", "")
        transcript.append(f"{role}{'[' + emotion + ']' if emotion else ''}：{str(item.get('text', ''))[:500]}")
    try:
        result = call_json_model(
            model,
            "你是儿童陪伴对话的记录整理助手。只输出JSON，不作医学或心理诊断。字段：title（12字内）、summary（80字内）、dominant_emotion（英文情绪标签）、attention（none/watch/urgent）、attention_reason（40字内）。仅在对话出现明确依据时标记留意。",
            "请总结以下对话：\n" + "\n".join(transcript),
            450,
        )
        dominant = result.get("dominant_emotion") if result.get("dominant_emotion") in EMOTION_NAMES else local["dominant_emotion"]
        attention = result.get("attention") if result.get("attention") in ATTENTION_ORDER else local["attention"]
        if ATTENTION_ORDER[local["attention"]] > ATTENTION_ORDER[attention]:
            attention = local["attention"]
        return local | {
            "title": str(result.get("title") or local["title"])[:24],
            "summary": str(result.get("summary") or local["summary"])[:180],
            "dominant_emotion": dominant, "dominant_emotion_text": EMOTION_NAMES[dominant],
            "attention": attention,
            "attention_reason": local["attention_reason"] if attention == local["attention"] and attention != "none" else str(result.get("attention_reason") or local["attention_reason"])[:80],
            "source": "model", "model_name": model["model_name"],
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
    except Exception:
        return local | {"source": "local-fallback"}
