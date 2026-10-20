"""FastAPI routers for the persona_engine micro-service."""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import uuid4

import structlog
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from persona_engine.conversation_preferences import ConversationPreferences, conversation_preferences_store
from persona_engine.emotion_engine import EmotionEngine
from persona_engine.persona_store import get_persona_profile_async
from persona_engine.reaction import ReactionSignal
from persona_engine.reaction_service import ReactionService
from persona_engine.relationship_tracker import RelationshipTracker
from persona_engine.tone_generator import ToneGenerator
from shared_contracts.models import EmotionState, EmotionTag, PersonaProfile, RelationshipMetrics
from shared_runtime.image_input import IMAGE_FAILED, IMAGE_PROMPT, IMAGE_UNAVAILABLE, ImageInputError, normalize_images
from shared_runtime.llm_client import LLMClient
from shared_runtime.response_behavior import response_behavior

logger = structlog.get_logger("persona_engine.api")
router = APIRouter(prefix="/persona", tags=["persona"])

_POSITIVE_HINTS = ("开心", "高兴", "喜欢", "爱", "顺利", "太好了", "不错", "棒")
_NEGATIVE_HINTS = ("难过", "伤心", "烦", "累", "生气", "焦虑", "害怕", "崩溃", "压力")


class GetProfileRequest(BaseModel):
    user_id: str = Field(..., description="Target user ID")


class GetProfileResponse(BaseModel):
    persona: PersonaProfile
    emotion: EmotionState
    relationship: RelationshipMetrics
    tone_text: str = Field(..., description="Generated system-prompt tone fragment")


class UpdateEmotionRequest(BaseModel):
    user_id: str
    event_type: str = Field(
        ...,
        pattern="^(user_message|memory_recall|time_of_day|decay)$",
        description="What triggered the emotion update",
    )
    sentiment: str | None = Field(default=None, pattern="^(positive|negative|neutral)$")
    memory_emotion_tags: list[EmotionTag] | None = Field(default=None)
    hour: int | None = Field(default=None, ge=0, le=23)
    message_content: str | None = Field(default=None)


class UpdateEmotionResponse(BaseModel):
    new_emotion: EmotionState


class RelationshipRequest(BaseModel):
    user_id: str


class RelationshipResponse(BaseModel):
    relationship: RelationshipMetrics


class DailyDigestRequest(BaseModel):
    user_id: str


class DailyDigestResponse(BaseModel):
    digest: str = Field(..., description="Chinese relationship summary for system prompt injection")
    relationship: RelationshipMetrics
    current_emotion: EmotionState


class GenerateResponseRequest(BaseModel):
    user_id: str
    session_id: str
    user_message: str = Field(..., description="Raw user input")
    system_prompt: str = Field(..., description="Full system prompt built by core orchestrator")
    emotion: dict[str, Any] | None = Field(default=None, description="Current emotion state")
    relationship: dict[str, Any] | None = Field(default=None, description="Current relationship metrics")
    model: str | None = Field(default=None, description="Override default LLM model")
    turn_id: str = Field(default_factory=lambda: uuid4().hex, max_length=128)
    reaction: ReactionSignal | None = None
    image_urls: list[str] = Field(default_factory=list)


class GenerateResponseResponse(BaseModel):
    assistant_message: str = Field(..., description="AI-generated reply")
    new_emotion: EmotionState | None = Field(default=None, description="Emotion after this turn")
    sentiment: str = Field(..., pattern="^(positive|negative|neutral)$")
    tokens_used: int | None = Field(default=None)
    model: str = Field(..., description="Actual model used")
    reaction: ReactionSignal | None = None


class ClassifyReactionRequest(BaseModel):
    user_message: str = Field(min_length=1, max_length=12000)


class ObserveTurnRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=128)
    turn_id: str = Field(min_length=1, max_length=128)
    user_message: str = Field(min_length=1, max_length=12000)
    reaction: ReactionSignal | None = None


@router.post("/observe_turn")
async def observe_turn(body: ObserveTurnRequest, request: Request):
    service = ReactionService(_emotion_engine(request), _relationship_tracker(request))
    persona = await get_persona_profile_async()
    emotion, relationship = await service.commit(
        body.user_id, body.turn_id, body.user_message, body.reaction, baseline=persona.emotional_baseline,
    )
    return {"emotion": emotion, "relationship": relationship}


@router.get("/conversation_preferences/{user_id}", response_model=ConversationPreferences)
async def get_conversation_preferences(user_id: str):
    return await conversation_preferences_store.get(user_id)


@router.put("/conversation_preferences/{user_id}", response_model=ConversationPreferences)
async def save_conversation_preferences(user_id: str, preferences: ConversationPreferences):
    return await conversation_preferences_store.save(user_id, preferences)


@router.post("/classify_reaction", response_model=ReactionSignal)
async def classify_reaction(body: ClassifyReactionRequest, request: Request):
    service = ReactionService(_emotion_engine(request), _relationship_tracker(request))
    return await service.classifier.classify(body.user_message)


@router.get("/relationship_reviews/{user_id}")
async def relationship_reviews(user_id: str, request: Request, limit: int = Query(default=7, ge=1, le=30)):
    from persona_engine.relationship_review import RelationshipReviewer

    store = _relationship_tracker(request).state_store
    if store is None:
        return {"reviews": []}
    return {"reviews": await RelationshipReviewer(store).list_reviews(user_id, limit)}


def _emotion_engine(request: Request) -> EmotionEngine:
    engine = getattr(request.app.state, "emotion_engine", None)
    if engine is None:
        raise HTTPException(status_code=503, detail="Emotion engine not initialised")
    return engine


def _relationship_tracker(request: Request) -> RelationshipTracker:
    tracker = getattr(request.app.state, "relationship_tracker", None)
    if tracker is None:
        raise HTTPException(status_code=503, detail="Relationship tracker not initialised")
    return tracker


def _tone_generator(request: Request) -> ToneGenerator:
    generator = getattr(request.app.state, "tone_generator", None)
    if generator is None:
        raise HTTPException(status_code=503, detail="Tone generator not initialised")
    return generator


def _llm_client(request: Request) -> LLMClient:
    client = getattr(request.app.state, "llm_client", None)
    if client is None:
        raise HTTPException(status_code=503, detail="LLM client not initialised")
    return client


def _local_sentiment(text: str) -> str:
    lowered = text.lower()
    if any(token in lowered for token in _NEGATIVE_HINTS):
        return "negative"
    if any(token in lowered for token in _POSITIVE_HINTS):
        return "positive"
    return "neutral"


def _extract_memory_lines(system_prompt: str) -> list[str]:
    # prompt_engine.py uses the Chinese section header 【记忆片段】
    if "【记忆片段】" not in system_prompt:
        return []

    lines: list[str] = []
    capture = False
    for line in system_prompt.splitlines():
        stripped = line.strip()
        if "【记忆片段】" in stripped:
            capture = True
            continue
        if capture and stripped.startswith("- "):
            lines.append(stripped[2:])
            continue
        if capture and stripped and not stripped.startswith("- "):
            break
    return lines


def _build_local_response(
    persona: PersonaProfile,
    user_message: str,
    system_prompt: str,
    sentiment: str,
) -> str:
    message = user_message.strip()
    memories = _extract_memory_lines(system_prompt)

    if any(token in message for token in ("你叫什么", "你是谁")):
        return f"我是{persona.name}，会一直在这里陪你聊天。"

    if any(token in message for token in ("记得", "还记得", "上次", "刚才", "之前")):
        if memories:
            return f"我记得你提到过：{memories[0]}。如果你愿意，我们可以接着聊这件事。"
        return "我现在还没有想起特别具体的细节，不过从这次开始我会认真记住我们聊过的内容。"

    if any(token in message for token in ("你好", "嗨", "在吗", "早上好", "晚上好")):
        return f"我在呢，我是{persona.name}。今天你最想先聊哪件事？"

    if sentiment == "negative":
        return "听起来你现在不太舒服。我先陪着你，你愿意把最难受的那一部分慢慢说给我听吗？"

    if sentiment == "positive":
        return "这听起来真的很不错，我也替你开心。你最想分享的是哪一段？"

    if memories:
        return f"我记得你之前提到过：{memories[0]}。关于你刚刚说的这件事，我在认真听。"

    return "我在认真听你说。你可以继续讲，我会尽量记住对你重要的内容。"


@router.post("/get_profile", response_model=GetProfileResponse)
async def get_profile(body: GetProfileRequest, request: Request) -> dict[str, Any]:
    """Return PersonaProfile + current emotion + relationship metrics for a user."""
    user_id = body.user_id
    logger.info("api.get_profile", user_id=user_id)

    persona = await get_persona_profile_async()
    emotion = await _emotion_engine(request).get_current_emotion(user_id)
    relationship = await _relationship_tracker(request).get_metrics(user_id)
    tone_text = _tone_generator(request).generate_tone(emotion, relationship)

    return {
        "persona": persona,
        "emotion": emotion,
        "relationship": relationship,
        "tone_text": tone_text,
    }


@router.post("/update_emotion", response_model=UpdateEmotionResponse)
async def update_emotion(body: UpdateEmotionRequest, request: Request) -> dict[str, Any]:
    """Update emotion state from an external event."""
    user_id = body.user_id
    event_type = body.event_type
    logger.info("api.update_emotion", user_id=user_id, event_type=event_type)

    emotion_engine = _emotion_engine(request)
    tracker = _relationship_tracker(request)
    relationship = await tracker.get_metrics(user_id)

    if event_type == "user_message":
        if not body.sentiment:
            raise HTTPException(status_code=422, detail="`sentiment` required for user_message")
        new_emotion = await emotion_engine.transition_from_user_message(
            user_id=user_id,
            sentiment=body.sentiment,
            relationship=relationship,
            message_content=body.message_content or "",
        )
        await tracker.record_interaction(user_id=user_id, sentiment=body.sentiment)
    elif event_type == "memory_recall":
        new_emotion = await emotion_engine.transition_from_memory_recall(
            user_id=user_id,
            memory_emotion_tags=body.memory_emotion_tags or [],
            relationship=relationship,
        )
    elif event_type == "time_of_day":
        new_emotion = await emotion_engine.transition_from_time_of_day(user_id=user_id, hour=body.hour)
    elif event_type == "decay":
        new_emotion = await emotion_engine.decay_toward_baseline(user_id)
    else:
        raise HTTPException(status_code=422, detail=f"Unsupported event_type: {event_type}")

    return {"new_emotion": new_emotion}


@router.post("/relationship", response_model=RelationshipResponse)
async def get_relationship(body: RelationshipRequest, request: Request) -> dict[str, Any]:
    relationship = await _relationship_tracker(request).get_metrics(body.user_id)
    return {"relationship": relationship}


@router.post("/daily_digest", response_model=DailyDigestResponse)
async def daily_digest(body: DailyDigestRequest, request: Request) -> dict[str, Any]:
    user_id = body.user_id
    logger.info("api.daily_digest", user_id=user_id)

    relationship = await _relationship_tracker(request).get_metrics(user_id)
    current_emotion = await _emotion_engine(request).get_current_emotion(user_id)
    digest = _tone_generator(request).generate_daily_digest(relationship, [current_emotion])

    return {
        "digest": digest,
        "relationship": relationship,
        "current_emotion": current_emotion,
    }


@router.post("/generate_response", response_model=GenerateResponseResponse)
async def generate_response(body: GenerateResponseRequest, request: Request) -> dict[str, Any]:
    """Generate assistant response, analyze sentiment, and update emotion state."""
    try:
        images = await asyncio.to_thread(normalize_images, body.image_urls) if body.image_urls else []
    except ImageInputError as exc:
        raise HTTPException(422, str(exc)) from None
    user_id = body.user_id
    logger.info(
        "api.generate_response",
        user_id=user_id,
        session_id=body.session_id,
        model=body.model,
    )

    llm_client = _llm_client(request)
    emotion_engine = _emotion_engine(request)
    tracker = _relationship_tracker(request)
    persona = await get_persona_profile_async()

    system_prompt = body.system_prompt
    if images:
        system_prompt += IMAGE_PROMPT
    voice_pref = (body.emotion or {}).get("voice_preference")
    if voice_pref:
        system_prompt += f"\n\nVoice preference: {voice_pref}"

    service = ReactionService(emotion_engine, tracker)
    reaction = body.reaction or await service.classifier.classify(body.user_message)
    sentiment = reaction.sentiment
    relationship = await tracker.get_metrics(user_id)
    predicted = service.predict(await emotion_engine.get_current_emotion(user_id), relationship, reaction,
                                baseline=persona.emotional_baseline)
    behavior = response_behavior(predicted, user_message=body.user_message, intent=reaction.intent)
    system_prompt += "\n\n【本轮回应方式】" + behavior.instruction

    assistant_message: str
    tokens_used: int | None
    model_used: str

    if llm_client.has_configured_provider():
        try:
            gen_result = await llm_client.generate(
                system_prompt=system_prompt,
                user_message=body.user_message,
                model=body.model,
                temperature=behavior.temperature,
                max_tokens=behavior.max_tokens,
                **({"image_urls": images} if images else {}),
            )
            assistant_message = gen_result["assistant_message"]
            tokens_used = gen_result.get("tokens_used")
            model_used = gen_result.get("model", body.model or "unknown")
        except Exception as exc:
            if images:
                raise HTTPException(502, IMAGE_FAILED) from None
            logger.warning("api.generate_response_fallback", error=str(exc))
            assistant_message = _build_local_response(persona, body.user_message, system_prompt, sentiment)
            tokens_used = None
            model_used = "local-fallback"
    else:
        if images:
            raise HTTPException(503, IMAGE_UNAVAILABLE)
        assistant_message = _build_local_response(persona, body.user_message, system_prompt, sentiment)
        tokens_used = None
        model_used = "local-fallback"

    new_emotion, _relationship = await service.commit(
        user_id, body.turn_id, body.user_message, reaction, baseline=persona.emotional_baseline,
    )

    logger.info(
        "api.generate_response_done",
        user_id=user_id,
        sentiment=sentiment,
        new_emotion=new_emotion.primary.value,
        tokens_used=tokens_used,
        model=model_used,
    )

    return {
        "assistant_message": assistant_message,
        "new_emotion": new_emotion,
        "sentiment": sentiment,
        "tokens_used": tokens_used,
        "model": model_used,
        "reaction": reaction,
    }
