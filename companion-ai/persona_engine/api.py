"""FastAPI routers for the persona_engine micro-service."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import structlog
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from persona_engine.emotion_engine import EmotionEngine
from persona_engine.persona_store import get_persona_profile_async
from persona_engine.relationship_tracker import RelationshipTracker
from persona_engine.tone_generator import ToneGenerator
from shared.llm_client import LLMClient
from shared.models import EmotionState, EmotionTag, PersonaProfile, RelationshipMetrics

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
    sentiment: Optional[str] = Field(default=None, pattern="^(positive|negative|neutral)$")
    memory_emotion_tags: Optional[List[EmotionTag]] = Field(default=None)
    hour: Optional[int] = Field(default=None, ge=0, le=23)
    message_content: Optional[str] = Field(default=None)


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
    emotion: Optional[Dict[str, Any]] = Field(default=None, description="Current emotion state")
    relationship: Optional[Dict[str, Any]] = Field(default=None, description="Current relationship metrics")
    model: Optional[str] = Field(default=None, description="Override default LLM model")


class GenerateResponseResponse(BaseModel):
    assistant_message: str = Field(..., description="AI-generated reply")
    new_emotion: Optional[EmotionState] = Field(default=None, description="Emotion after this turn")
    sentiment: str = Field(..., pattern="^(positive|negative|neutral)$")
    tokens_used: Optional[int] = Field(default=None)
    model: str = Field(..., description="Actual model used")


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


def _extract_memory_lines(system_prompt: str) -> List[str]:
    # prompt_engine.py uses the Chinese section header 【记忆片段】
    if "【记忆片段】" not in system_prompt:
        return []

    lines: List[str] = []
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
async def get_profile(body: GetProfileRequest, request: Request) -> Dict[str, Any]:
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
async def update_emotion(body: UpdateEmotionRequest, request: Request) -> Dict[str, Any]:
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
async def get_relationship(body: RelationshipRequest, request: Request) -> Dict[str, Any]:
    relationship = await _relationship_tracker(request).get_metrics(body.user_id)
    return {"relationship": relationship}


@router.post("/daily_digest", response_model=DailyDigestResponse)
async def daily_digest(body: DailyDigestRequest, request: Request) -> Dict[str, Any]:
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
async def generate_response(body: GenerateResponseRequest, request: Request) -> Dict[str, Any]:
    """Generate assistant response, analyze sentiment, and update emotion state."""
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
    voice_pref = (body.emotion or {}).get("voice_preference")
    if voice_pref:
        system_prompt += f"\n\nVoice preference: {voice_pref}"

    sentiment = await llm_client.analyze_sentiment(body.user_message)

    assistant_message: str
    tokens_used: Optional[int]
    model_used: str

    if llm_client.has_configured_provider():
        try:
            gen_result = await llm_client.generate(
                system_prompt=system_prompt,
                user_message=body.user_message,
                model=body.model,
                temperature=0.7,
                max_tokens=1024,
            )
            assistant_message = gen_result["assistant_message"]
            tokens_used = gen_result.get("tokens_used")
            model_used = gen_result.get("model", body.model or "unknown")
        except Exception as exc:
            logger.warning("api.generate_response_fallback", error=str(exc))
            assistant_message = _build_local_response(persona, body.user_message, system_prompt, sentiment)
            tokens_used = None
            model_used = "local-fallback"
    else:
        assistant_message = _build_local_response(persona, body.user_message, system_prompt, sentiment)
        tokens_used = None
        model_used = "local-fallback"

    relationship = RelationshipMetrics(**body.relationship) if body.relationship else await tracker.get_metrics(user_id)
    new_emotion = await emotion_engine.transition_from_user_message(
        user_id=user_id,
        sentiment=sentiment or _local_sentiment(body.user_message),
        relationship=relationship,
        message_content=body.user_message,
    )
    await tracker.record_interaction(user_id=user_id, sentiment=sentiment)

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
    }
