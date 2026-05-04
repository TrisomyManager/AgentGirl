"""pytest suite for persona_engine.

Covers:
- persona_store YAML loading
- emotion_engine transitions and decay
- relationship_tracker updates and decay
- tone_generator output shape
- FastAPI router integration (using TestClient)
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict

import pytest

# Ensure repo root is on PYTHONPATH
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from shared.models import EmotionState, EmotionTag, RelationshipMetrics

from persona_engine.emotion_engine import EmotionEngine
from persona_engine.persona_store import get_persona_profile, load_persona
from persona_engine.relationship_tracker import RelationshipTracker
from persona_engine.tone_generator import ToneGenerator


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def soul_path() -> Path:
    return _PROJECT_ROOT / "persona_engine" / "data" / "soul.yaml"


@pytest.fixture
def persona_profile(soul_path):
    return get_persona_profile(soul_path)


@pytest.fixture
def emotion_engine():
    return EmotionEngine(redis_client=None)


@pytest.fixture
def relationship_tracker():
    return RelationshipTracker(redis_client=None, db_pool=None)


@pytest.fixture
def tone_generator(persona_profile):
    return ToneGenerator(persona=persona_profile)


@pytest.fixture
def sample_relationship():
    return RelationshipMetrics(
        user_id="u_test_001",
        intimacy=0.5,
        trust=0.4,
        familiarity=0.3,
        affection=0.45,
        total_interactions=12,
        first_seen=datetime.utcnow() - timedelta(days=7),
        last_seen=datetime.utcnow(),
    )


# ---------------------------------------------------------------------------
# persona_store
# ---------------------------------------------------------------------------

class TestPersonaStore:
    def test_load_persona_raw(self, soul_path):
        raw = load_persona(soul_path)
        assert isinstance(raw, dict)
        assert raw["name"] == "小暖"
        assert "core_traits" in raw
        assert len(raw["core_traits"]) >= 5

    def test_get_persona_profile(self, soul_path):
        profile = get_persona_profile(soul_path)
        assert profile.name == "小暖"
        assert profile.persona_id == "default"
        assert profile.emotional_baseline.primary == EmotionTag.CALM
        assert profile.voice_preference is not None


# ---------------------------------------------------------------------------
# emotion_engine
# ---------------------------------------------------------------------------

class TestEmotionEngine:
    @pytest.mark.asyncio
    async def test_get_current_emotion_returns_baseline(self, emotion_engine):
        state = await emotion_engine.get_current_emotion("u_1")
        assert state.primary == EmotionTag.CALM
        assert 0.0 <= state.intensity <= 1.0

    @pytest.mark.asyncio
    async def test_transition_positive_sentiment(self, emotion_engine, sample_relationship):
        new_state = await emotion_engine.transition_from_user_message(
            user_id="u_1",
            sentiment="positive",
            relationship=sample_relationship,
        )
        assert new_state.primary in {
            EmotionTag.HAPPY,
            EmotionTag.AFFECTIONATE,
            EmotionTag.EXCITED,
            EmotionTag.SURPRISED,
        }
        assert new_state.trigger == "user_msg:positive"

    @pytest.mark.asyncio
    async def test_transition_negative_sentiment(self, emotion_engine, sample_relationship):
        new_state = await emotion_engine.transition_from_user_message(
            user_id="u_1",
            sentiment="negative",
            relationship=sample_relationship,
        )
        assert new_state.primary in {
            EmotionTag.CONCERNED,
            EmotionTag.SAD,
            EmotionTag.FEARFUL,
            EmotionTag.ANGRY,
        }

    @pytest.mark.asyncio
    async def test_transition_neutral_sentiment(self, emotion_engine, sample_relationship):
        new_state = await emotion_engine.transition_from_user_message(
            user_id="u_1",
            sentiment="neutral",
            relationship=sample_relationship,
        )
        assert new_state.primary in {
            EmotionTag.CALM,
            EmotionTag.NEUTRAL,
            EmotionTag.SURPRISED,
            EmotionTag.HAPPY,
        }

    @pytest.mark.asyncio
    async def test_transition_respects_graph(self, emotion_engine, sample_relationship):
        # Seed an angry state
        angry = EmotionState(
            primary=EmotionTag.ANGRY,
            intensity=0.8,
            valence=-0.7,
            arousal=0.8,
            trigger="seed",
        )
        await emotion_engine.set_emotion("u_graph", angry)

        # Positive sentiment from angry should not jump to affectionate directly
        # if not in transition graph; engine will pick closest reachable.
        new_state = await emotion_engine.transition_from_user_message(
            user_id="u_graph",
            sentiment="positive",
            relationship=sample_relationship,
        )
        # ANGRY reachable set is [SAD, CONCERNED, NEUTRAL, CALM]
        assert new_state.primary in {
            EmotionTag.SAD,
            EmotionTag.CONCERNED,
            EmotionTag.NEUTRAL,
            EmotionTag.CALM,
        }

    @pytest.mark.asyncio
    async def test_memory_recall_transition(self, emotion_engine, sample_relationship):
        await emotion_engine.set_emotion("u_mem", emotion_engine._baseline)
        new_state = await emotion_engine.transition_from_memory_recall(
            user_id="u_mem",
            memory_emotion_tags=[EmotionTag.HAPPY, EmotionTag.AFFECTIONATE],
            relationship=sample_relationship,
        )
        assert new_state.trigger == "memory_recall"
        assert new_state.valence > emotion_engine._baseline.valence

    @pytest.mark.asyncio
    async def test_time_of_day_transition(self, emotion_engine):
        # Night hours should push toward CALM
        new_state = await emotion_engine.transition_from_time_of_day("u_tod", hour=23)
        assert new_state.primary == EmotionTag.CALM
        assert new_state.trigger == "time_of_day:23"

    @pytest.mark.asyncio
    async def test_decay_toward_baseline(self, emotion_engine):
        # Seed an extreme state in the past
        extreme = EmotionState(
            primary=EmotionTag.EXCITED,
            intensity=0.95,
            valence=0.9,
            arousal=0.9,
            timestamp=datetime.utcnow() - timedelta(hours=2),
            trigger="seed",
        )
        await emotion_engine.set_emotion("u_decay", extreme)

        decayed = await emotion_engine.decay_toward_baseline("u_decay")
        assert decayed.intensity < extreme.intensity
        assert decayed.arousal < extreme.arousal
        assert decayed.trigger == "decay"

    @pytest.mark.asyncio
    async def test_intensity_modulated_by_intimacy(self, emotion_engine):
        low_intimacy = RelationshipMetrics(user_id="u_low", intimacy=0.0)
        high_intimacy = RelationshipMetrics(user_id="u_high", intimacy=0.9)

        low_state = await emotion_engine.transition_from_user_message(
            "u_low", "positive", low_intimacy
        )
        high_state = await emotion_engine.transition_from_user_message(
            "u_high", "positive", high_intimacy
        )
        # Higher intimacy should on average produce higher intensity
        assert high_state.intensity >= low_state.intensity - 0.2  # allow random jitter


# ---------------------------------------------------------------------------
# relationship_tracker
# ---------------------------------------------------------------------------

class TestRelationshipTracker:
    @pytest.mark.asyncio
    async def test_get_metrics_new_user(self, relationship_tracker):
        metrics = await relationship_tracker.get_metrics("u_new")
        assert metrics.user_id == "u_new"
        assert metrics.total_interactions == 0
        assert metrics.intimacy == 0.0

    @pytest.mark.asyncio
    async def test_record_interaction_positive(self, relationship_tracker):
        m1 = await relationship_tracker.record_interaction("u_pos", sentiment="positive")
        assert m1.total_interactions == 1
        assert m1.trust > 0.0
        assert m1.affection > 0.0

    @pytest.mark.asyncio
    async def test_record_interaction_with_disclosure(self, relationship_tracker):
        m1 = await relationship_tracker.record_interaction(
            "u_disc", sentiment="neutral", has_disclosure=True
        )
        assert m1.intimacy > 0.0

    @pytest.mark.asyncio
    async def test_record_interaction_routine(self, relationship_tracker):
        m1 = await relationship_tracker.record_interaction(
            "u_routine", sentiment="neutral", is_routine=True
        )
        assert m1.familiarity > 0.0

    @pytest.mark.asyncio
    async def test_record_milestone(self, relationship_tracker):
        m0 = await relationship_tracker.get_metrics("u_mil")
        m1 = await relationship_tracker.record_milestone("u_mil", "shared_secret")
        assert m1.intimacy > m0.intimacy
        assert m1.trust > m0.trust

    @pytest.mark.asyncio
    async def test_decay_on_inactivity(self, relationship_tracker):
        # Manually seed an old metric in Redis is not possible without Redis,
        # so we test the _apply_decay helper directly.
        old = RelationshipMetrics(
            user_id="u_decay",
            intimacy=0.8,
            trust=0.8,
            familiarity=0.8,
            affection=0.8,
            last_seen=datetime.utcnow() - timedelta(days=10),
        )
        decayed = relationship_tracker._apply_decay(old)
        # 10 days * 0.005 daily = 0.05 decay for intimacy -> 0.75 (below original 0.8)
        assert decayed.intimacy <= old.intimacy
        assert decayed.trust <= old.trust
        # Should not fall below floor
        assert decayed.intimacy >= 0.05
        assert decayed.trust >= 0.10


# ---------------------------------------------------------------------------
# tone_generator
# ---------------------------------------------------------------------------

class TestToneGenerator:
    def test_generate_tone_contains_name(self, tone_generator, sample_relationship):
        emotion = EmotionState(primary=EmotionTag.HAPPY, intensity=0.6, valence=0.7, arousal=0.6)
        tone = tone_generator.generate_tone(emotion, sample_relationship)
        assert "小暖" in tone
        assert "当前情绪" in tone
        assert "关系提示" in tone
        assert "风格约束" in tone

    def test_generate_tone_depth_high(self, tone_generator):
        deep = RelationshipMetrics(
            user_id="u_deep",
            intimacy=0.9,
            trust=0.9,
            familiarity=0.8,
            affection=0.9,
        )
        emotion = EmotionState(primary=EmotionTag.AFFECTIONATE, intensity=0.7, valence=0.8, arousal=0.4)
        tone = tone_generator.generate_tone(emotion, deep)
        assert "亲密" in tone or "亲昵" in tone

    def test_generate_daily_digest(self, tone_generator, sample_relationship):
        emotion = EmotionState(primary=EmotionTag.CALM, intensity=0.4, valence=0.2, arousal=0.2)
        digest = tone_generator.generate_daily_digest(sample_relationship, [emotion])
        assert "每日关系感知" in digest
        assert "小暖" in digest
        assert str(sample_relationship.total_interactions) in digest


# ---------------------------------------------------------------------------
# FastAPI integration
# ---------------------------------------------------------------------------

class TestAPI:
    @pytest.fixture(scope="class")
    def client(self):
        from fastapi.testclient import TestClient
        from persona_engine.main import create_app

        app = create_app()
        # Override state with no-Redis / no-DB engines for pure unit tests
        from persona_engine.emotion_engine import EmotionEngine
        from persona_engine.relationship_tracker import RelationshipTracker
        from persona_engine.tone_generator import ToneGenerator
        from persona_engine.persona_store import get_persona_profile

        app.state.emotion_engine = EmotionEngine(redis_client=None)
        app.state.relationship_tracker = RelationshipTracker(redis_client=None, db_pool=None)
        app.state.tone_generator = ToneGenerator(persona=get_persona_profile())

        return TestClient(app)

    def test_health(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_get_profile(self, client):
        resp = client.post("/persona/get_profile", json={"user_id": "u_api_1"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["persona"]["name"] == "小暖"
        assert "emotion" in data
        assert "relationship" in data
        assert "tone_text" in data
        assert isinstance(data["tone_text"], str)

    def test_update_emotion_user_message(self, client):
        resp = client.post(
            "/persona/update_emotion",
            json={"user_id": "u_api_1", "event_type": "user_message", "sentiment": "positive"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "new_emotion" in data
        assert data["new_emotion"]["trigger"] == "user_msg:positive"

    def test_update_emotion_missing_sentiment(self, client):
        resp = client.post(
            "/persona/update_emotion",
            json={"user_id": "u_api_1", "event_type": "user_message"},
        )
        assert resp.status_code == 422

    def test_update_emotion_memory_recall(self, client):
        resp = client.post(
            "/persona/update_emotion",
            json={
                "user_id": "u_api_1",
                "event_type": "memory_recall",
                "memory_emotion_tags": ["happy", "affectionate"],
            },
        )
        assert resp.status_code == 200
        assert "new_emotion" in resp.json()

    def test_update_emotion_time_of_day(self, client):
        resp = client.post(
            "/persona/update_emotion",
            json={"user_id": "u_api_1", "event_type": "time_of_day", "hour": 23},
        )
        assert resp.status_code == 200
        assert resp.json()["new_emotion"]["trigger"] == "time_of_day:23"

    def test_update_emotion_decay(self, client):
        resp = client.post(
            "/persona/update_emotion",
            json={"user_id": "u_api_1", "event_type": "decay"},
        )
        assert resp.status_code == 200
        assert resp.json()["new_emotion"]["trigger"] == "decay"

    def test_relationship(self, client):
        resp = client.post("/persona/relationship", json={"user_id": "u_api_rel"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["relationship"]["user_id"] == "u_api_rel"

    def test_daily_digest(self, client):
        resp = client.post("/persona/daily_digest", json={"user_id": "u_api_1"})
        assert resp.status_code == 200
        data = resp.json()
        assert "digest" in data
        assert "每日关系感知" in data["digest"]
        assert "relationship" in data
        assert "current_emotion" in data
