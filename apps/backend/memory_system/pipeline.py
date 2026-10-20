"""5-stage memory pipeline implemented as Celery tasks.

Stages:
  1. Raw Archive — store raw conversation turn
  2. Entity Extraction — extract entities and relationships via LLM
  3. Importance Scoring — score memory importance 0-1
  4. Conflict Resolution — deduplicate and resolve conflicting memories
  5. Long-term Storage — write to vector DB + knowledge graph
"""

import json
import re
import uuid
from concurrent.futures import Future
from datetime import datetime, timedelta
from threading import Thread
from typing import Any, Dict, List, Optional

import httpx
import structlog
from celery import Celery

from memory_system.db import AsyncSessionLocal
from memory_system.graph_lifecycle import write_extracted_graph
from memory_system.importance import apply_importance, enrich_frequency, ground_extraction, importance_evidence
from memory_system.lifecycle import StaleMemoryWriteError, capture_memory_epoch
from memory_system.vector_store import store_memory
from shared_contracts.models import EmotionTag, MemoryCategory, MemoryEntry
from shared_runtime.config import get_settings
from shared_runtime.llm_client import get_effective_chat_config

logger = structlog.get_logger(__name__)

settings = get_settings()

celery_app = Celery(
    "memory_pipeline",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=300,
    worker_prefetch_multiplier=1,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run_async(coro: Any) -> Any:
    """Run a coroutine from sync code, even if an event loop is already active."""
    import asyncio

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    result: Future[Any] = Future()

    def _runner() -> None:
        try:
            value = asyncio.run(coro)
        except Exception as exc:
            result.set_exception(exc)
        else:
            result.set_result(value)

    thread = Thread(target=_runner, daemon=True)
    thread.start()
    thread.join()
    return result.result()


async def _llm_chat(
    messages: List[Dict[str, str]],
    model: Optional[str] = None,
    temperature: float = 0.3,
    json_mode: bool = False,
) -> str:
    """Call OpenAI-compatible chat completion API. Reads runtime LLM config first."""
    config = get_effective_chat_config()
    api_key = config["api_key"]
    if not api_key:
        raise RuntimeError("LLM API key not configured")
    base_url = config["base_url"]
    chosen_model = model or config["model"]
    payload: Dict[str, Any] = {
        "model": chosen_model,
        "messages": messages,
        "temperature": temperature,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    if "volces.com" in base_url:
        payload["thinking"] = {"type": "disabled"}

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            f"{base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]


def _strip_json_fence(text_in: str) -> str:
    """Some LLMs wrap JSON in ```json fences even with response_format. Strip them."""
    s = text_in.strip()
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s)
        s = re.sub(r"\s*```\s*$", "", s)
    return s.strip()


# ---------------------------------------------------------------------------
# Stage 1: Raw Archive
# ---------------------------------------------------------------------------

@celery_app.task(bind=True, max_retries=3)
def stage1_raw_archive(self, turn_data: Dict[str, Any]) -> Dict[str, Any]:
    """Store raw conversation turn in short-term / staging area.

    For MVP we simply pass through the turn data enriched with archive metadata.
    """
    logger.info(
        "pipeline.stage1_start",
        turn_id=turn_data.get("turn_id"),
        user_id=turn_data.get("user_id"),
    )
    turn_data["archive_id"] = str(uuid.uuid4())
    turn_data["archived_at"] = datetime.utcnow().isoformat()
    logger.info("pipeline.stage1_done", archive_id=turn_data["archive_id"])
    return turn_data


# ---------------------------------------------------------------------------
# Stage 2: Entity Extraction
# ---------------------------------------------------------------------------

@celery_app.task(bind=True, max_retries=3)
def stage2_entity_extraction(self, turn_data: Dict[str, Any]) -> Dict[str, Any]:
    """Extract entities and relationships from the conversation text using LLM."""
    logger.info("pipeline.stage2_start", turn_id=turn_data.get("turn_id"))

    user_message = turn_data.get("user_message", "")
    assistant_message = turn_data.get("assistant_message", "")
    combined = f"User: {user_message}\nAssistant: {assistant_message}"

    prompt = f"""Analyze the following conversation and extract structured information.
Return ONLY a JSON object with this exact schema:
{{
  "entities": [
    {{"name": "string", "type": "person|place|thing|concept|emotion|preference", "properties": {{}}}}
  ],
  "relationships": [
    {{"source": "string", "target": "string", "type": "KNOWS|EXPERIENCED|PREFERS|FELT|RELATED_TO", "properties": {{}}}}
  ],
  "events": [
    {{"name": "string", "properties": {{}}}}
  ],
  "preferences": [
    {{"key": "string", "value": "any", "strength": 0.0-1.0}}
  ],
  "emotions": [
    {{"tag": "string", "intensity": 0.0-1.0, "trigger": "string"}}
  ]
}}

Conversation:
{combined}
"""

    try:
        result = _run_async(
            _llm_chat(
                [
                    {
                        "role": "system",
                        "content": "Extract only facts stated by the user. Assistant suggestions are not user facts. Use literal user words for entity and event names. Output valid JSON only.",
                    },
                    {"role": "user", "content": prompt},
                ],
                json_mode=True,
            )
        )
        extracted = json.loads(result)
    except Exception as exc:
        logger.error("pipeline.stage2_failed", error=str(exc))
        self.retry(countdown=10, exc=exc)
        raise

    extracted = ground_extraction(extracted, user_message)
    turn_data["extracted"] = extracted
    logger.info(
        "pipeline.stage2_done",
        entities=len(extracted.get("entities", [])),
        relationships=len(extracted.get("relationships", [])),
    )
    return turn_data


# ---------------------------------------------------------------------------
# Stage 3: Importance Scoring
# ---------------------------------------------------------------------------

@celery_app.task(bind=True, max_retries=3)
def stage3_importance_scoring(self, turn_data: Dict[str, Any]) -> Dict[str, Any]:
    """Score memory importance on a 0-1 scale using LLM."""
    logger.info("pipeline.stage3_start", turn_id=turn_data.get("turn_id"))
    if "low_information" in importance_evidence(turn_data).reasons:
        return apply_importance(turn_data)
    _run_async(enrich_frequency(turn_data))

    user_message = turn_data.get("user_message", "")
    assistant_message = turn_data.get("assistant_message", "")
    combined = f"User: {user_message}\nAssistant: {assistant_message}"

    prompt = f"""Rate the long-term importance of the following conversation for building a deep companionship.
Consider: emotional depth, personal disclosure, relationship milestones, preferences revealed, and future relevance.
Return ONLY a JSON object: {{"importance": float between 0 and 1, "reason": "brief explanation", "category": "fact|emotion|event|preference|relationship_milestone|routine"}}

Conversation:
{combined}
"""

    try:
        result = _run_async(
            _llm_chat(
                [
                    {
                        "role": "system",
                        "content": "You are a memory importance scoring assistant. Output valid JSON only.",
                    },
                    {"role": "user", "content": prompt},
                ],
                json_mode=True,
            )
        )
        scored = json.loads(_strip_json_fence(result))
    except Exception as exc:
        logger.warning("pipeline.stage3_rule_fallback", error=type(exc).__name__)
        scored = {}

    apply_importance(turn_data, scored if isinstance(scored, dict) else {})
    logger.info("pipeline.stage3_done", importance=turn_data["importance"])
    return turn_data


# ---------------------------------------------------------------------------
# Stage 4: Conflict Resolution
# ---------------------------------------------------------------------------

@celery_app.task(bind=True, max_retries=3)
def stage4_conflict_resolution(self, turn_data: Dict[str, Any]) -> Dict[str, Any]:
    """Deduplicate and resolve conflicting memories.

    For MVP we perform simple string similarity on extracted entities
    and mark potential conflicts for later human review.
    """
    logger.info("pipeline.stage4_start", turn_id=turn_data.get("turn_id"))

    extracted = turn_data.get("extracted", {})
    entities = extracted.get("entities", [])

    # Simple dedup by normalized name
    seen: Dict[str, Dict[str, Any]] = {}
    deduped = []
    for ent in entities:
        norm = ent.get("name", "").lower().strip()
        if norm and norm not in seen:
            seen[norm] = ent
            deduped.append(ent)
        else:
            # Merge properties
            existing = seen[norm]
            existing["properties"] = {**(existing.get("properties") or {}), **(ent.get("properties") or {})}

    extracted["entities"] = deduped
    turn_data["extracted"] = extracted
    turn_data["conflicts_resolved"] = len(entities) - len(deduped)
    logger.info(
        "pipeline.stage4_done",
        deduped=len(deduped),
        conflicts=turn_data["conflicts_resolved"],
    )
    return turn_data


# ---------------------------------------------------------------------------
# Stage 5: Long-term Storage
# ---------------------------------------------------------------------------

@celery_app.task(bind=True, max_retries=3)
def stage5_long_term_storage(self, turn_data: Dict[str, Any]) -> Dict[str, Any]:
    """Write processed memory to vector DB and knowledge graph."""

    logger.info("pipeline.stage5_start", turn_id=turn_data.get("turn_id"))
    if "low_information" in importance_evidence(turn_data).reasons:
        return turn_data | {"memory_entry_id": None, "memory_skipped": "low_information"}

    user_id = turn_data["user_id"]
    turn_id = turn_data["turn_id"]
    importance = turn_data.get("importance", 0.5)
    category_str = turn_data.get("suggested_category", "fact")
    extracted = turn_data.get("extracted", {})

    try:
        category = MemoryCategory(category_str)
    except ValueError:
        category = MemoryCategory.FACT

    emotion_tags = []
    for em in extracted.get("emotions", []):
        tag = em.get("tag", "neutral")
        try:
            emotion_tags.append(EmotionTag(tag.lower()))
        except ValueError:
            emotion_tags.append(EmotionTag.NEUTRAL)

    # Build memory content from user message + extracted summary
    content_parts = [turn_data.get("user_message", "")]
    if extracted.get("entities"):
        content_parts.append(
            "Extracted entities: "
            + ", ".join(e.get("name", "") for e in extracted["entities"])
        )
    content = "\n".join(content_parts)

    entry = MemoryEntry(
        entry_id=str(uuid.uuid4()),
        user_id=user_id,
        category=category,
        content=content,
        importance=importance,
        emotion_tags=emotion_tags,
        source_turn_id=turn_id,
        created_at=datetime.utcnow(),
        expires_at=None if importance > 0.6 else datetime.utcnow() + timedelta(days=90),
    )

    async def _store() -> None:
        if "source_epoch" not in turn_data:
            turn_data["source_epoch"] = await capture_memory_epoch(user_id)
        async with AsyncSessionLocal() as session:
            await store_memory(session, entry, extracted=extracted, expected_epoch=turn_data.get("source_epoch"))

        await write_extracted_graph(user_id, turn_data["source_epoch"], extracted, memory_id=entry.entry_id)

    try:
        _run_async(_store())
    except StaleMemoryWriteError:
        return turn_data | {"memory_entry_id": None, "memory_skipped": "user_cleared"}

    turn_data["memory_entry_id"] = entry.entry_id
    logger.info(
        "pipeline.stage5_done",
        memory_entry_id=entry.entry_id,
        category=category.value,
        importance=importance,
    )
    return turn_data


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

@celery_app.task
def run_memory_pipeline(turn_data: Dict[str, Any]) -> Dict[str, Any]:
    """Run the full 5-stage pipeline synchronously (for simple invocation)."""
    result = stage1_raw_archive(turn_data)
    result = stage2_entity_extraction(result)
    result = stage3_importance_scoring(result)
    result = stage4_conflict_resolution(result)
    result = stage5_long_term_storage(result)
    return result


# ---------------------------------------------------------------------------
# Async sync runner (no Celery) — used in lite_mode / monolithic deployment.
# ---------------------------------------------------------------------------


async def _stage1_archive(td: Dict[str, Any]) -> Dict[str, Any]:
    td["archive_id"] = str(uuid.uuid4())
    td["archived_at"] = datetime.utcnow().isoformat()
    return td


async def _stage2_extract(td: Dict[str, Any]) -> Dict[str, Any]:
    user_message = td.get("user_message", "")
    assistant_message = td.get("assistant_message", "")
    combined = f"User: {user_message}\nAssistant: {assistant_message}"

    prompt = f"""Analyze the following conversation and extract structured information.
Return ONLY a JSON object with this exact schema:
{{
  "entities": [
    {{"name": "string", "type": "person|place|thing|concept|emotion|preference", "properties": {{}}}}
  ],
  "relationships": [
    {{"source": "string", "target": "string", "type": "KNOWS|EXPERIENCED|PREFERS|FELT|RELATED_TO", "properties": {{}}}}
  ],
  "events": [
    {{"name": "string", "properties": {{}}}}
  ],
  "preferences": [
    {{"key": "string", "value": "any", "strength": 0.0-1.0}}
  ],
  "emotions": [
    {{"tag": "string", "intensity": 0.0-1.0, "trigger": "string"}}
  ]
}}

Conversation:
{combined}
"""

    try:
        raw = await _llm_chat(
            [
                {
                    "role": "system",
                    "content": "Extract only facts stated by the user. Assistant suggestions are not user facts. Use literal user words for entity and event names. Output valid JSON only.",
                },
                {"role": "user", "content": prompt},
            ],
            json_mode=True,
        )
        td["extracted"] = ground_extraction(json.loads(_strip_json_fence(raw)), user_message)
    except Exception as exc:
        logger.warning("pipeline.async.stage2_failed", error=str(exc))
        td["extracted"] = {"entities": [], "relationships": [], "events": [], "preferences": [], "emotions": []}
    return td


async def _stage3_score(td: Dict[str, Any]) -> Dict[str, Any]:
    if "low_information" in importance_evidence(td).reasons:
        return apply_importance(td)
    await enrich_frequency(td)
    user_message = td.get("user_message", "")
    assistant_message = td.get("assistant_message", "")
    combined = f"User: {user_message}\nAssistant: {assistant_message}"

    prompt = f"""Rate the long-term importance of the following conversation for building a deep companionship.
Consider: emotional depth, personal disclosure, relationship milestones, preferences revealed, future relevance.
Return ONLY a JSON object: {{"importance": float between 0 and 1, "reason": "brief explanation", "category": "fact|emotion|event|preference|relationship_milestone|routine"}}

Conversation:
{combined}
"""

    try:
        raw = await _llm_chat(
            [
                {"role": "system", "content": "You score memory importance. Output valid JSON only."},
                {"role": "user", "content": prompt},
            ],
            json_mode=True,
        )
        scored = json.loads(_strip_json_fence(raw))
    except Exception as exc:
        logger.warning("pipeline.async.stage3_rule_fallback", error=type(exc).__name__)
        scored = {}
    return apply_importance(td, scored if isinstance(scored, dict) else {})


async def _stage4_dedupe(td: Dict[str, Any]) -> Dict[str, Any]:
    extracted = td.get("extracted", {}) or {}
    entities = extracted.get("entities", []) or []
    seen: Dict[str, Dict[str, Any]] = {}
    deduped: List[Dict[str, Any]] = []
    for ent in entities:
        norm = (ent.get("name") or "").lower().strip()
        if not norm:
            continue
        if norm not in seen:
            seen[norm] = ent
            deduped.append(ent)
        else:
            existing = seen[norm]
            existing["properties"] = {**(existing.get("properties") or {}), **(ent.get("properties") or {})}
    extracted["entities"] = deduped
    td["extracted"] = extracted
    td["conflicts_resolved"] = len(entities) - len(deduped)
    return td


async def _stage5_store(td: Dict[str, Any]) -> Dict[str, Any]:
    if "low_information" in importance_evidence(td).reasons:
        return td | {"memory_entry_id": None, "memory_skipped": "low_information"}
    user_id = td["user_id"]
    if "source_epoch" not in td:
        td["source_epoch"] = await capture_memory_epoch(user_id)
    turn_id = td["turn_id"]
    importance = td.get("importance", 0.5)
    category_str = td.get("suggested_category", "fact")
    extracted = td.get("extracted", {}) or {}

    try:
        category = MemoryCategory(category_str)
    except ValueError:
        category = MemoryCategory.FACT

    emotion_tags: List[EmotionTag] = []
    for em in extracted.get("emotions", []) or []:
        tag = (em.get("tag") or "neutral").lower()
        try:
            emotion_tags.append(EmotionTag(tag))
        except ValueError:
            emotion_tags.append(EmotionTag.NEUTRAL)

    content_parts = [td.get("user_message", "")]
    ent_names = [e.get("name", "") for e in extracted.get("entities", []) if e.get("name")]
    if ent_names:
        content_parts.append("Extracted entities: " + ", ".join(ent_names))
    content = "\n".join(p for p in content_parts if p)

    entry = MemoryEntry(
        entry_id=str(uuid.uuid4()),
        user_id=user_id,
        category=category,
        content=content,
        importance=importance,
        emotion_tags=emotion_tags,
        source_turn_id=turn_id,
        created_at=datetime.utcnow(),
        expires_at=None if importance > 0.6 else datetime.utcnow() + timedelta(days=90),
    )

    async with AsyncSessionLocal() as session:
        try:
            await store_memory(session, entry, extracted=extracted, expected_epoch=td.get("source_epoch"))
        except StaleMemoryWriteError:
            return td | {"memory_entry_id": None, "memory_skipped": "user_cleared"}

    try:
        await write_extracted_graph(user_id, td["source_epoch"], extracted, memory_id=entry.entry_id)
    except Exception as exc:
        logger.warning("pipeline.async.graph_failed", error=type(exc).__name__)

    td["memory_entry_id"] = entry.entry_id
    td["memory_category"] = category.value
    return td


async def run_pipeline_async(turn_data: Dict[str, Any]) -> Dict[str, Any]:
    """Execute all 5 pipeline stages without Celery — used in monolithic mode."""
    turn_data = dict(turn_data)
    if "source_epoch" not in turn_data:
        turn_data["source_epoch"] = await capture_memory_epoch(turn_data["user_id"])
    log = logger.bind(turn_id=turn_data.get("turn_id"))
    log.info("pipeline.async.start")
    td = await _stage1_archive(turn_data)
    td = await _stage2_extract(td)
    td = await _stage3_score(td)
    td = await _stage4_dedupe(td)
    td = await _stage5_store(td)
    log.info(
        "pipeline.async.done",
        memory_entry_id=td.get("memory_entry_id"),
        importance=td.get("importance"),
        category=td.get("memory_category"),
    )
    return td
