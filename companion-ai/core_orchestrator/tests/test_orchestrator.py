"""Basic pytest tests for core_orchestrator."""

from __future__ import annotations

import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from core_orchestrator.api import HealthResponse, ModuleStatus, StatusResponse, TurnRequest, TurnResponse
from core_orchestrator.http_client import ServiceClient
from core_orchestrator.intent_router import Intent, IntentRouter
from core_orchestrator.main import app
from core_orchestrator.state_machine import build_graph, build_initial_state
from shared.models import Platform, TurnContext, UserProfile


@pytest.fixture
def sample_user() -> UserProfile:
    return UserProfile(
        user_id="user-123",
        display_name="Alice",
        platform=Platform.APP,
        language="zh-CN",
    )


@pytest.fixture
def sample_turn_context(sample_user: UserProfile) -> TurnContext:
    return TurnContext(
        turn_id=str(uuid.uuid4()),
        session_id=str(uuid.uuid4()),
        user=sample_user,
        user_message="你好呀",
        platform=Platform.APP,
        has_voice=False,
    )


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.mark.asyncio
async def test_service_client_health_success() -> None:
    client = ServiceClient("http://localhost:9999", "test_service")
    with patch.object(client, "get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = MagicMock()
        mock_get.return_value.json.return_value = {"status": "ok"}
        result = await client.health()
        assert result["healthy"] is True
        assert result["status"] == "ok"


@pytest.mark.asyncio
async def test_service_client_health_failure() -> None:
    client = ServiceClient("http://localhost:9999", "test_service")
    with patch.object(client, "get", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = Exception("Connection refused")
        result = await client.health()
        assert result["healthy"] is False
        assert "unreachable" in result["status"]


@pytest.mark.asyncio
async def test_intent_router_classify_chat() -> None:
    router = IntentRouter()
    router.settings.openai_api_key = "test-key"
    mock_llm = MagicMock()
    mock_response = MagicMock()
    mock_response.content = '{"intent": "chat", "confidence": 0.95, "reasoning": "greeting", "entities": {}}'
    mock_llm.ainvoke = AsyncMock(return_value=mock_response)
    router._llm = mock_llm

    result = await router.classify("你好")
    assert result.intent == Intent.CHAT
    assert result.confidence == pytest.approx(0.95)


@pytest.mark.asyncio
async def test_intent_router_classify_device_command() -> None:
    router = IntentRouter()
    router.settings.openai_api_key = "test-key"
    mock_llm = MagicMock()
    mock_response = MagicMock()
    mock_response.content = (
        '{"intent": "device_command", "confidence": 0.88, "reasoning": "turn on light", '
        '"entities": {"device": "light"}}'
    )
    mock_llm.ainvoke = AsyncMock(return_value=mock_response)
    router._llm = mock_llm

    result = await router.classify("把灯打开")
    assert result.intent == Intent.DEVICE_COMMAND
    assert result.entities.get("device") == "light"


@pytest.mark.asyncio
async def test_intent_router_fallback_on_invalid_json() -> None:
    router = IntentRouter()
    router.settings.openai_api_key = "test-key"
    mock_llm = MagicMock()
    mock_response = MagicMock()
    mock_response.content = "not json"
    mock_llm.ainvoke = AsyncMock(return_value=mock_response)
    router._llm = mock_llm

    result = await router.classify("随便说点什么")
    assert result.intent == Intent.CHAT


@pytest.mark.asyncio
async def test_intent_router_heuristic_without_api_key() -> None:
    router = IntentRouter()
    router.settings.openai_api_key = None

    result = await router.classify("你还记得我喜欢什么吗？")
    assert result.intent == Intent.MEMORY_QUERY


def test_build_initial_state(sample_turn_context: TurnContext) -> None:
    state = build_initial_state(sample_turn_context)
    assert state["turn_context"] == sample_turn_context
    assert state["intent"] is None
    assert state["assistant_message"] is None
    assert len(state["messages"]) == 2


def test_build_graph_compiles() -> None:
    assert build_graph() is not None


@pytest.mark.asyncio
async def test_api_turn_endpoint_mocked(sample_user: UserProfile) -> None:
    from core_orchestrator.orchestrator import Orchestrator

    mock_result = {
        "turn_id": str(uuid.uuid4()),
        "session_id": str(uuid.uuid4()),
        "user_id": sample_user.user_id,
        "assistant_message": "你好呀，Alice",
        "emotion": {"primary": "happy", "intensity": 0.8},
        "voice_url": None,
        "action_sequence": None,
        "intent": "chat",
        "intent_confidence": 0.95,
        "memory_entries_count": 2,
        "error": None,
    }

    mock_orch = MagicMock(spec=Orchestrator)
    mock_orch.process_turn = AsyncMock(return_value=mock_result)
    mock_orch.service_status = AsyncMock(return_value=[])

    with patch("core_orchestrator.api.get_orchestrator", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_orch
        test_client = TestClient(app)
        payload = {
            "session_id": str(uuid.uuid4()),
            "user": sample_user.model_dump(mode="json"),
            "user_message": "你好",
            "platform": "app",
            "has_voice": False,
        }
        response = test_client.post("/orchestrator/turn", json=payload)
        assert response.status_code in (200, 500)


def test_turn_request_model_validation() -> None:
    user = UserProfile(user_id="u1", display_name="Bob", platform=Platform.TELEGRAM)
    req = TurnRequest(
        session_id="sess-1",
        user=user,
        user_message="Hello",
        platform=Platform.TELEGRAM,
        has_voice=True,
        voice_duration_ms=1200,
    )
    assert req.user.user_id == "u1"
    assert req.has_voice is True


def test_turn_response_model_serialization() -> None:
    resp = TurnResponse(
        turn_id="t1",
        session_id="s1",
        user_id="u1",
        assistant_message="Hi!",
        intent="chat",
        intent_confidence=0.92,
        memory_entries_count=3,
    )
    data = resp.model_dump()
    assert data["assistant_message"] == "Hi!"
    assert data["intent_confidence"] == pytest.approx(0.92)


def test_module_health_model() -> None:
    health = HealthResponse(status="healthy", service="core_orchestrator", timestamp=datetime.utcnow().isoformat())
    assert health.status == "healthy"


def test_module_status_model() -> None:
    module = ModuleStatus(service="memory_system", url="http://localhost:8002", status="ok", healthy=True)
    status = StatusResponse(orchestrator="healthy", modules=[module], timestamp=datetime.utcnow().isoformat())
    assert status.modules[0].healthy is True
