from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import httpx
import pytest


async def test_health_is_ready_only_inside_successful_host_lifecycle(monkeypatch):
    import main

    monkeypatch.setattr(main, "_ENABLED_MODULES", {})
    monkeypatch.setattr(main.settings, "access_config_file", "")
    monkeypatch.setattr(main, "init_database_schema", AsyncMock())
    monkeypatch.setattr(main, "close_database", AsyncMock())
    app = main.create_app()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get("/health")).status_code == 503
        async with app.router.lifespan_context(app):
            response = await client.get("/health")
            assert response.status_code == 200
            assert response.json()["startup"] == {"database": "ready"}
        assert (await client.get("/health")).status_code == 503
    main.close_database.assert_awaited_once()


async def test_failed_module_startup_closes_preceding_resources_and_never_reports_healthy(monkeypatch):
    import main
    import memory_system.main
    import persona_engine.main

    events = []

    @asynccontextmanager
    async def first(_app):
        events.append("start")
        try:
            yield
        finally:
            events.append("close")

    @asynccontextmanager
    async def broken(_app):
        raise RuntimeError("synthetic startup error")
        yield  # pragma: no cover -- defines the async context manager

    monkeypatch.setattr(main, "_ENABLED_MODULES", {"persona_engine": True, "memory_system": True})
    monkeypatch.setattr(main.settings, "access_config_file", "")
    monkeypatch.setattr(main, "init_database_schema", AsyncMock())
    monkeypatch.setattr(main, "close_database", AsyncMock())
    monkeypatch.setattr(persona_engine.main, "lifespan", first)
    monkeypatch.setattr(memory_system.main, "lifespan", broken)
    app = main.create_app()
    with pytest.raises(RuntimeError, match="synthetic startup error"):
        async with app.router.lifespan_context(app):
            pytest.fail("host started despite a failed required module")
    assert events == ["start", "close"]
    assert not app.state.ready and app.state.startup_modules["memory_system"] == "failed"
    main.close_database.assert_awaited_once()
