"""Cross-module platform privacy tests belong in the reference host."""

import json
from unittest.mock import AsyncMock
from uuid import uuid4

from sqlalchemy import select

from core_orchestrator.platforms import generate_platform_reply, revoke_platform_bindings
from core_orchestrator.tests.test_access_policy import secure_host as secure_host_fixture
from gateway_adapter.config import PlatformsConfig
from gateway_adapter.store import InboxORM, InboxStore, RevocationORM
from shared_contracts import PlatformMessage
from shared_runtime.database import AsyncSessionLocal, Base, engine

secure_host = secure_host_fixture


def setup_data():
    suffix = uuid4().hex[:12]
    config = PlatformsConfig.model_validate_json(
        json.dumps(
            {
                "enabled": True,
                "accounts": [
                    {
                        "id": "bot_" + suffix,
                        "platform": "telegram",
                        "enabled": True,
                        "receive": True,
                        "reply": True,
                        "token": "123:synthetic",
                    }
                ],
                "bindings": [
                    {
                        "id": "test",
                        "account_id": "bot_" + suffix,
                        "enabled": True,
                        "user_id": "owner_" + suffix,
                        "actor_id": "11",
                        "conversation_id": "22",
                        "audience": "private",
                    }
                ],
            }
        )
    )
    message = PlatformMessage(
        platform="telegram",
        account_id=config.accounts[0].id,
        event_id="1",
        message_id="7",
        actor_id="11",
        conversation_id="22",
        audience="private",
        text="synthetic input",
    )
    return config, message


async def test_public_reply_does_not_open_private_memory_persona_or_tools(monkeypatch):
    from shared_runtime.llm_client import LLMClient

    config, message = setup_data()
    generate = AsyncMock(return_value={"assistant_message": "公共回复"})
    close = AsyncMock()
    monkeypatch.setattr(LLMClient, "generate", generate)
    monkeypatch.setattr(LLMClient, "close", close)
    import core_orchestrator.orchestrator

    private = AsyncMock(side_effect=AssertionError("Public channel opened private orchestrator"))
    monkeypatch.setattr(core_orchestrator.orchestrator, "get_orchestrator", private)
    text = await generate_platform_reply(config.bindings[0], message.model_copy(update={"audience": "room"}), "s", "t")
    assert text == "公共回复"
    private.assert_not_awaited()
    assert generate.call_args.kwargs["user_message"] == "synthetic input"
    assert "synthetic-owner" not in generate.call_args.kwargs["system_prompt"]
    close.assert_awaited_once()


async def test_private_reply_claims_owned_session_and_injects_host_identity(monkeypatch):
    import core_orchestrator.orchestrator
    from memory_system.session_store import PersistentSessionMemory

    config, message = setup_data()
    authorize = AsyncMock(return_value=True)
    monkeypatch.setattr(PersistentSessionMemory, "authorize_session", authorize)
    process = AsyncMock(return_value={"assistant_message": "private reply"})
    monkeypatch.setattr(
        core_orchestrator.orchestrator,
        "get_orchestrator",
        AsyncMock(return_value=type("Orch", (), {"process_turn": process})()),
    )
    assert await generate_platform_reply(config.bindings[0], message, "owned-session", "fixed-turn") == "private reply"
    authorize.assert_awaited_once_with("owned-session", config.bindings[0].user_id, claim=True)
    turn = process.call_args.args[0]
    assert turn.user.user_id == config.bindings[0].user_id and turn.turn_id == "fixed-turn"
    assert not turn.request_voice_reply


async def test_platform_data_export_erase_and_late_ingress_revocation(monkeypatch, tmp_path):
    import main
    from core_orchestrator.privacy import erase_data, export_data
    from gateway_adapter.config import binding_fingerprint

    main.create_app()  # Register the complete host inventory before creating the schema.

    config, message = setup_data()
    monkeypatch.delenv("COMPANION_PLATFORMS_CONFIG_FILE", raising=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    store = InboxStore()
    account, binding = config.accounts[0], config.bindings[0]
    key = binding_fingerprint(account, binding)
    await store.register(account, binding)
    await store.accept(message, account, binding, key)
    exported = await export_data(binding.user_id)
    assert exported["data"]["platform_inbox"][0]["source_json"]["text"] == "synthetic input"
    assert "123:synthetic" not in json.dumps(exported)
    erased = await erase_data(binding.user_id)
    assert erased["status"] == "completed"
    async with AsyncSessionLocal() as session:
        assert not await session.scalar(select(InboxORM.id).where(InboxORM.user_id == binding.user_id))
        receipt = await session.get(RevocationORM, key)
        assert receipt and set(receipt.__table__.columns.keys()) == {"binding_key", "created_at"}
    assert await store.accept(message, account, binding, key) == "revoked"


async def test_invalid_configuration_does_not_prevent_erasing_registered_binding(monkeypatch, tmp_path):
    from gateway_adapter.config import binding_fingerprint

    config, _ = setup_data()
    path = tmp_path / "invalid.json"
    path.write_text("{invalid", encoding="utf-8")
    monkeypatch.setenv("COMPANION_PLATFORMS_CONFIG_FILE", str(path))
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    await InboxStore().register(config.accounts[0], config.bindings[0])
    async with AsyncSessionLocal() as session:
        await revoke_platform_bindings(session, config.bindings[0].user_id)
        await session.commit()
    assert await InboxStore().revoked(binding_fingerprint(config.accounts[0], config.bindings[0]))


async def test_platform_receipts_follow_reference_host_ownership(secure_host):
    _, client, keys = secure_host
    headers = {"Authorization": "Bearer " + keys["alice"]}
    assert (await client.get("/gateway/platforms/alice/receipts", headers=headers)).status_code == 200
    assert (await client.get("/gateway/platforms/bob/receipts", headers=headers)).status_code == 403
    assert (await client.post("/qq/testbot", content=b"{}", headers=headers)).status_code in {403, 404}
