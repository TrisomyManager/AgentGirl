"""Behavioral contracts for durable emotion, independent signals and atomic turns."""

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import select

from persona_engine.emotion_engine import EmotionEngine
from persona_engine.reaction import ReactionClassifier, ReactionSignal, rule_reaction
from persona_engine.reaction_service import ReactionService
from persona_engine.relationship_tracker import RelationshipTracker, apply_interaction
from persona_engine.state_store import PersonaEventORM, PersonaStateStore
from shared_contracts.models import EmotionState, RelationshipMetrics
from shared_runtime.config import get_settings
from shared_runtime.database import AsyncSessionLocal
from shared_runtime.response_behavior import response_behavior


@pytest.fixture
async def service():
    store = PersonaStateStore(AsyncSessionLocal)
    await store.initialize()
    return ReactionService(EmotionEngine(state_store=store), RelationshipTracker(state_store=store))


def test_continuous_transition_preserves_negative_valence_and_limits_sudden_changes():
    engine = EmotionEngine()
    current = EmotionState(primary="angry", valence=-0.9, arousal=0.8)
    relationship = RelationshipMetrics(user_id="u", intimacy=0.8)
    moved = engine.predict(current, relationship, sentiment="positive")
    assert -0.9 < moved.valence < 0
    assert moved.valence - current.valence <= 0.450001
    assert abs(moved.arousal - current.arousal) <= 0.3
    sad = engine.predict(None, relationship, sentiment="negative")
    assert sad.valence < 0


def test_relaxation_is_deterministic_across_refresh_frequency_and_aware_timestamps():
    engine = EmotionEngine()
    now = datetime.now(UTC)
    state = EmotionState(primary="sad", intensity=0.9, valence=-0.8, arousal=0.8, timestamp=now)
    direct = engine.relax(state, now=now + timedelta(hours=1))
    first = engine.relax(state, now=now + timedelta(minutes=30))
    second = engine.relax(first, now=now + timedelta(hours=1))
    assert second.valence == pytest.approx(direct.valence)
    assert second.arousal == pytest.approx(direct.arousal)
    assert -0.8 < direct.valence < engine._baseline.valence
    assert engine.relax(state.model_copy(update={"timestamp": now.replace(tzinfo=None)}), now=now).valence == -0.8


async def test_restart_restores_state_and_users_are_isolated(service):
    user = uuid4().hex
    saved, relationship = await service.commit(user, "t1", "我好难过", rule_reaction("我好难过"))
    restarted_store = PersonaStateStore(AsyncSessionLocal)
    restarted = EmotionEngine(state_store=restarted_store)
    loaded = await restarted.get_current_emotion(user)
    assert loaded.valence == pytest.approx(saved.valence, abs=0.001)
    assert relationship.total_interactions == 1
    assert (await restarted.get_current_emotion(uuid4().hex)).trigger == "baseline"
    assert (await restarted_store.get_relationship(user)).total_interactions == 1


async def test_concurrent_turns_and_duplicate_replay_are_atomic(service):
    user = uuid4().hex
    reactions = await asyncio.gather(
        *[service.commit(user, f"t{index % 6}", "谢谢你", rule_reaction("谢谢你")) for index in range(18)]
    )
    assert len(reactions) == 18
    relationship = await service.tracker.get_metrics(user)
    assert relationship.total_interactions == 6
    assert relationship.trust == pytest.approx(1 - 0.985**6, abs=0.00001)
    async with AsyncSessionLocal() as session:
        events = (await session.execute(select(PersonaEventORM).where(PersonaEventORM.user_id == user))).scalars().all()
        assert len(events) == 6


async def test_failed_state_update_rolls_back_both_outputs_and_event(service):
    user = uuid4().hex
    original, _ = await service.commit(user, "first", "开心")

    def fail(emotion, relationship):
        relationship.total_interactions = 99
        emotion.valence = -1
        raise RuntimeError("interrupted mutation")

    with pytest.raises(RuntimeError):
        await service.engine.state_store.update(user, fail, event_id="broken")
    assert (await service.engine.state_store.get_emotion(user)).valence == original.valence
    assert (await service.tracker.get_metrics(user)).total_interactions == 1


async def test_milestone_cannot_overwrite_concurrent_completed_turns(service):
    user = uuid4().hex
    await asyncio.gather(
        service.tracker.record_milestone(user, "first_voice_call", event_id="first-call"),
        service.tracker.record_milestone(user, "first_voice_call", event_id="first-call"),
        service.commit(user, "text", "我在这里"),
    )
    metrics = await service.tracker.get_metrics(user)
    assert metrics.total_interactions == 1
    assert metrics.intimacy == pytest.approx(0.1, abs=0.00001)


async def test_preview_never_commits_an_unfinished_turn(service):
    user = uuid4().hex
    current = await service.engine.get_current_emotion(user)
    prediction = service.predict(current, RelationshipMetrics(user_id=user), rule_reaction("我好难过"))
    assert prediction.valence < current.valence
    assert await service.engine.state_store.get_emotion(user) is None
    assert (await service.tracker.get_metrics(user)).total_interactions == 0


def test_disclosing_sadness_does_not_reduce_trust_and_large_values_never_shrink_on_a_gain():
    relationship = RelationshipMetrics(user_id="u", trust=0.9, intimacy=0.9, affection=0.9)
    sad = apply_interaction(relationship, sentiment="negative", has_disclosure=True)
    assert sad.trust == relationship.trust
    assert sad.intimacy > relationship.intimacy
    warm = apply_interaction(relationship, sentiment="positive")
    assert warm.trust > relationship.trust
    assert warm.affection > relationship.affection
    assert apply_interaction(relationship, hostile=True).trust < relationship.trust


def test_emotion_drives_reply_parameters_and_serious_topics_suppress_emoji():
    happy = EmotionState(primary="happy", valence=0.8, arousal=0.7)
    lively = response_behavior(happy)
    support = response_behavior(happy, user_message="我失眠了很难过")
    assert lively.max_tokens > support.max_tokens
    assert lively.temperature > support.temperature
    assert lively.emoji and support.emoji is None
    assert "不使用 emoji" in support.instruction
    assert response_behavior(happy, intent="task").max_tokens > lively.max_tokens


def test_negated_emotion_and_user_sadness_are_not_hostility():
    assert rule_reaction("我不难过").sentiment == "neutral"
    assert not rule_reaction("我难过想哭").hostile
    assert rule_reaction("你骗我").hostile


@pytest.mark.parametrize(
    "raw", ["不是 JSON", "{}", '{"valence": 5}', '{"valence": NaN}', '{"confidence": 0.1, "sentiment": "positive"}']
)
async def test_invalid_or_uncertain_model_response_falls_back_and_closes_client(raw, monkeypatch):
    monkeypatch.setattr(get_settings(), "reaction_use_llm", True)
    client = AsyncMock()
    client.has_configured_provider = lambda: True
    client.generate.return_value = {"assistant_message": raw}
    reaction = await ReactionClassifier(lambda: client).classify("我好难过")
    assert reaction.source == "rules" and reaction.sentiment == "negative"
    client.close.assert_awaited_once()


async def test_independent_model_signal_uses_configured_model_and_never_receives_reply(monkeypatch):
    monkeypatch.setattr(get_settings(), "reaction_use_llm", True)
    monkeypatch.setattr(get_settings(), "reaction_model", "host-small-classifier")
    client = AsyncMock()
    client.has_configured_provider = lambda: True
    client.generate.return_value = {
        "assistant_message": ReactionSignal(
            sentiment="negative", valence=-0.6, arousal=0.3, confidence=0.9, intent="support"
        ).model_dump_json()
    }
    signal = await ReactionClassifier(lambda: client).classify("今天发生的事让我很失望")
    assert signal.source == "model" and signal.intent == "support"
    assert client.generate.call_args.kwargs["model"] == "host-small-classifier"
    assert "assistant_message" not in client.generate.call_args.kwargs["user_message"]


async def test_classifier_timeout_is_bounded_and_cancellation_is_not_swallowed(monkeypatch):
    monkeypatch.setattr(get_settings(), "reaction_use_llm", True)
    monkeypatch.setattr(get_settings(), "reaction_timeout_seconds", 0.01)
    client = AsyncMock()
    client.has_configured_provider = lambda: True

    async def slow(**_kwargs):
        await asyncio.sleep(5)

    client.generate.side_effect = slow
    classifier = ReactionClassifier(lambda: client)
    assert (await classifier.classify("我害怕")).source == "rules"
    client.generate.side_effect = asyncio.CancelledError
    with pytest.raises(asyncio.CancelledError):
        await classifier.classify("我害怕")


def test_emotion_timestamp_json_is_unambiguous_utc():
    state = EmotionState(timestamp=datetime(2026, 10, 19, 10))
    assert datetime.fromisoformat(state.model_dump(mode="json")["timestamp"]).tzinfo is not None


async def test_offline_review_repairs_only_versioned_missing_receipts_without_changing_current_emotion(service):
    from persona_engine.relationship_review import RelationshipReviewer

    user = uuid4().hex
    before, _ = await service.commit(user, "online", "谢谢你")
    timestamp = datetime.now(UTC) - timedelta(hours=1)
    reaction = rule_reaction("其实我有个秘密")

    def turn(tid, version=1):
        return {
            "turn_id": tid,
            "user_message": "其实我有个秘密",
            "timestamp": timestamp.isoformat(),
            "metadata": {"user_id": user, "reaction": reaction.model_dump(), "persona_observation_version": version},
        }

    reviewer = RelationshipReviewer(service.engine.state_store)
    first = await reviewer.review(user, "2026-10-19", [turn("online"), turn("missing"), turn("legacy", None)], "first")
    assert first["observed_turns"] == 2
    assert first["legacy_turns_not_recredited"] == 1
    metrics = await service.tracker.get_metrics(user)
    assert metrics.total_interactions == 2
    assert metrics.intimacy > 0
    assert (await service.engine.state_store.get_emotion(user)).model_dump() == before.model_dump()
    assert (await reviewer.review(user, "2026-10-19", [turn("missing")], "first"))["status"] == "unchanged"
    await reviewer.review(user, "2026-10-19", [turn("online"), turn("missing"), turn("later")], "changed")
    assert (await service.tracker.get_metrics(user)).total_interactions == 3
    assert not await reviewer.list_reviews(uuid4().hex)


async def test_offline_review_does_not_mark_a_historical_user_active_today(service):
    from persona_engine.emotion_engine import utc
    from persona_engine.relationship_review import RelationshipReviewer

    user = uuid4().hex
    timestamp = datetime.now(UTC) - timedelta(days=2)
    await RelationshipReviewer(service.engine.state_store).review(
        user,
        "2026-10-17",
        [
            {
                "turn_id": "historical",
                "user_message": "我每天跑步",
                "timestamp": timestamp.isoformat(),
                "metadata": {"user_id": user, "persona_observation_version": 1},
            }
        ],
        "historical",
    )
    relationship = await service.engine.state_store.get_relationship(user)
    assert utc(relationship.last_seen) == timestamp
    assert await service.engine.state_store.get_emotion(user) is None
