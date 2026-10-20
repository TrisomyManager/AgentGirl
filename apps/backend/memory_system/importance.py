"""Evidence-based importance rules shared by synchronous and async pipelines."""

import math
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ImportanceEvidence:
    score: float
    category: str
    reasons: tuple[str, ...]


def importance_evidence(turn: dict) -> ImportanceEvidence:
    message = str(turn.get("user_message") or "").strip()
    normalized = re.sub(r"[\s，。！？!?.,~～]", "", message).lower()
    if normalized in {"", "嗯", "哦", "好", "好的", "行", "谢谢", "ok", "yes", "hi", "你好", "哈哈"}:
        return ImportanceEvidence(0.1, "routine", ("low_information",))

    score, category = 0.35, "fact"
    reasons = []
    if re.search(r"记住|不要忘|别忘|remember (?:that|this)|重要的是", message, re.I):
        score = 0.9
        reasons.append("explicit_memory_request")
    if re.search(r"我叫|我的名字|我住在|我的生日|过敏|my name|allergic|birthday", message, re.I):
        score = max(score, 0.85)
        reasons.append("stable_personal_fact")
    if re.search(r"我(?:很|最|不)?喜欢|我讨厌|我不吃|我更喜欢|i (?:like|love|prefer|hate)", message, re.I):
        score, category = max(score, 0.75), "preference"
        reasons.append("stated_preference")
    if re.search(r"明天|后天|下周|面试|考试|纪念日|手术|约定|tomorrow|next week|anniversary", message, re.I):
        score, category = max(score, 0.7), "event"
        reasons.append("future_relevance")
    emotion = str(turn.get("emotion") or "").lower()
    if emotion in {"sad", "fearful", "angry", "anxious", "excited"} or re.search(
        r"很难过|特别开心|崩溃|害怕|失眠|失恋", message
    ):
        score = max(score, 0.65)
        reasons.append("emotional_intensity")
        if category == "fact":
            category = "emotion"
    try:
        occurrences = max(1, min(20, int((turn.get("metadata") or {}).get("occurrence_count", 1))))
    except (TypeError, ValueError):
        occurrences = 1
    if occurrences > 1:
        score = min(0.95, score + min(0.15, math.log2(occurrences) * 0.05))
        reasons.append("repeated_mention")
    return ImportanceEvidence(round(score, 4), category, tuple(reasons or ["ordinary_content"]))


def apply_importance(turn: dict, model_result: dict | None = None) -> dict:
    evidence = importance_evidence(turn)
    model_result = model_result or {}
    try:
        model_score = float(model_result["importance"])
        if not math.isfinite(model_score):
            raise ValueError("non-finite score")
        score = 0.65 * min(1.0, max(0.0, model_score)) + 0.35 * evidence.score
        # Explicit requests and durable facts should not disappear because of a low model score.
        if {"explicit_memory_request", "stable_personal_fact"} & set(evidence.reasons):
            score = max(score, evidence.score)
    except (KeyError, TypeError, ValueError):
        score = evidence.score
    if "low_information" in evidence.reasons:
        score = min(score, 0.15)
    category = model_result.get("category", evidence.category)
    if category not in {"fact", "emotion", "event", "preference", "relationship_milestone", "routine"}:
        category = evidence.category
    turn.update(
        importance=round(score, 4),
        importance_reason="; ".join(evidence.reasons),
        importance_evidence={"rule_score": evidence.score, "reasons": list(evidence.reasons)},
        suggested_category=category,
    )
    return turn


async def enrich_frequency(turn: dict) -> dict:
    """Count actual earlier mentions for this user rather than trusting client-provided frequency."""
    user_id, message = turn.get("user_id"), str(turn.get("user_message") or "").strip()
    if not user_id or len(message) < 4:
        return turn
    from sqlalchemy import func, or_, select

    from memory_system.db import MemoryORM
    from shared_runtime.database import AsyncSessionLocal

    count = 0
    try:
        async with AsyncSessionLocal() as session:
            statement = (
                select(func.count())
                .select_from(MemoryORM)
                .where(
                    MemoryORM.user_id == user_id,
                    MemoryORM.content.startswith(message[:180], autoescape=True),
                )
            )
            if turn.get("turn_id"):
                statement = statement.where(
                    or_(MemoryORM.source_turn_id.is_(None), MemoryORM.source_turn_id != turn["turn_id"])
                )
            count = (await session.execute(statement)).scalar_one()
    except Exception:
        # Importance rules still work when the storage service is temporarily unavailable.
        count = 0
    turn["metadata"] = dict(turn.get("metadata") or {}) | {"occurrence_count": count + 1}
    return turn


def ground_extraction(extracted: dict, user_message: str) -> dict:
    """Keep user-grounded facts; assistant suggestions are not evidence about the user."""
    if not isinstance(extracted, dict):
        extracted = {}
    source = user_message.lower()

    def mentioned(value):
        return isinstance(value, str) and bool(value.strip()) and value.strip().lower() in source

    def grounded_properties(properties):
        return (
            {key: value for key, value in (properties or {}).items() if mentioned(str(value))}
            if isinstance(properties, dict)
            else {}
        )

    entities = []
    for entity in extracted.get("entities", []) or []:
        if isinstance(entity, dict) and mentioned(entity.get("name")):
            entities.append(entity | {"properties": grounded_properties(entity.get("properties"))})
    names = {str(entity["name"]).strip().lower() for entity in entities}
    relationships = []
    for relation in extracted.get("relationships", []) or []:
        if (
            isinstance(relation, dict)
            and str(relation.get("source", "")).lower() in names
            and str(relation.get("target", "")).lower() in names
        ):
            relationships.append(relation | {"properties": grounded_properties(relation.get("properties"))})
    events = [
        event | {"properties": grounded_properties(event.get("properties"))}
        for event in extracted.get("events", []) or []
        if isinstance(event, dict) and mentioned(event.get("name"))
    ]
    preferences = [
        preference
        for preference in extracted.get("preferences", []) or []
        if isinstance(preference, dict) and mentioned(preference.get("value"))
    ]
    emotions = [emotion for emotion in extracted.get("emotions", []) or [] if isinstance(emotion, dict)]
    return {
        "entities": entities,
        "relationships": relationships,
        "events": events,
        "preferences": preferences,
        "emotions": emotions,
    }
