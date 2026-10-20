"""Reference-host data inventory, bounded exports and durable erasure receipts."""

import asyncio
import json
from contextlib import suppress
from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, ConfigDict
from sqlalchemy import Column, String, Text, delete, inspect, literal_column, or_, select

from memory_system.lifecycle import lock_memory_epoch
from memory_system.session_store import ConversationTurnORM, SessionDigestORM, SessionOwnerORM
from persona_engine.relationship_review import RelationshipReviewORM  # noqa: F401 -- register inventory
from shared_runtime.config import get_settings
from shared_runtime.database import AsyncSessionLocal, Base
from shared_runtime.user_lifecycle import UserBusyError, erase_user_work, user_scoped
from user_profile import get_default_store
from voice_layer.media_access import VoiceAssetORM, delete_voice_files

get_default_store()  # register the lazy user_profiles model before host schema init
router = APIRouter(prefix="/privacy", tags=["privacy"])
_MAX_ROWS = 100000
_MAX_BYTES = 50 * 1024 * 1024
_EXCLUDED = {"memory_user_epochs", "privacy_erasure_jobs"}
_SECRET_FIELDS = {"api_key", "access_key", "session_token", "device_token", "authorization", "password", "token"}


class ErasureJobORM(Base):
    __tablename__ = "privacy_erasure_jobs"
    user_id = Column(String(128), primary_key=True)
    job_id = Column(String(36), nullable=False)
    status = Column(String(24), nullable=False)
    pending_json = Column(Text, nullable=False, default="{}")
    updated_at = Column(String(64), nullable=False)


class EraseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirmation: str


def _now():
    return datetime.now(UTC).isoformat()


def _public(value):
    if isinstance(value, dict):
        return {key: _public(item) for key, item in value.items() if key.lower() not in _SECRET_FIELDS}
    if isinstance(value, (list, tuple)):
        return [_public(item) for item in value]
    return value


def _row(row):
    data = dict(row)
    for name, value in tuple(data.items()):
        if name.endswith("_json") and isinstance(value, str):
            with suppress(ValueError):
                data[name] = json.loads(value)
    return _public(jsonable_encoder(data))


def user_tables():
    return [table for table in Base.metadata.sorted_tables if "user_id" in table.c and table.name not in _EXCLUDED]


async def no_pending_erasure(user_id):
    async with AsyncSessionLocal() as session:
        status = await session.scalar(select(ErasureJobORM.status).where(ErasureJobORM.user_id == user_id))
    return status != "pending"


async def _sessions(session, user_id, *, include_mixed=False):
    known = set(
        (await session.scalars(select(SessionOwnerORM.session_id).where(SessionOwnerORM.user_id == user_id))).all()
    )
    known.update(
        (
            await session.scalars(select(ConversationTurnORM.session_id).where(ConversationTurnORM.user_id == user_id))
        ).all()
    )
    # Legacy sessions containing multiple/anonymous users have no safely attributable digest.
    if known and not include_mixed:
        mixed = set(
            (
                await session.scalars(
                    select(ConversationTurnORM.session_id).where(
                        ConversationTurnORM.session_id.in_(known),
                        (ConversationTurnORM.user_id != user_id) | ConversationTurnORM.user_id.is_(None),
                    )
                )
            ).all()
        )
        known -= mixed
    return sorted(known)


async def _legacy_user_condition(session, user_id):
    table = Base.metadata.tables.get("users")
    if table is None:
        return None, None
    identifier = user_id
    conditions = []
    if session.bind.dialect.name == "postgresql":
        connection = await session.connection()
        columns = await connection.run_sync(lambda conn: {col["name"] for col in inspect(conn).get_columns("users")})
        if "user_id" in columns:
            conditions.append(literal_column("users.user_id") == user_id)
        try:
            identifier = UUID(user_id)
        except ValueError:
            return (table, or_(*conditions)) if conditions else (None, None)
    conditions.append(table.c.id == identifier)
    return table, or_(*conditions)


@user_scoped()
async def export_data(user_id):
    async with AsyncSessionLocal() as session:
        byte_count = 0

        async def collect(query):
            nonlocal byte_count
            rows = []
            stream = await session.stream(query.limit(_MAX_ROWS + 1))
            try:
                async for row in stream.mappings():
                    item = _row(row)
                    byte_count += len(json.dumps(item, ensure_ascii=False).encode("utf-8"))
                    if len(rows) >= _MAX_ROWS or byte_count > _MAX_BYTES:
                        raise HTTPException(413, "数据超过单次导出上限，请联系宿主管理员导出完整分区。")
                    rows.append(item)
            finally:
                await stream.close()
            return rows

        data = {}
        for table in user_tables():
            # Vector coefficients are derived indexes rather than personal source records.
            columns = [column for column in table.c if column.name != "embedding"]
            data[table.name] = await collect(select(*columns).where(table.c.user_id == user_id))
        session_ids = await _sessions(session, user_id)
        data["session_digests"] = await collect(
            select(SessionDigestORM.__table__).where(SessionDigestORM.session_id.in_(session_ids))
        )
        runs = Base.metadata.tables["task_runs"]
        steps = Base.metadata.tables["task_steps"]
        data["task_steps"] = await collect(
            select(steps).where(steps.c.run_id.in_(select(runs.c.id).where(runs.c.user_id == user_id)))
        )
        legacy, condition = await _legacy_user_condition(session, user_id)
        if legacy is not None:
            data["users"] = await collect(select(legacy).where(condition))
    from memory_system.short_term import short_term_memory

    data["transient_context"] = _public(await short_term_memory.get_user_context(user_id))
    try:
        from device_coordination.api import get_gateway

        gateway = get_gateway()
    except RuntimeError:
        gateway = None
    data["device_gateway"] = _public(await gateway.export_user_data(user_id)) if gateway else {"status": "not_started"}
    from gateway_adapter.api import get_sessions

    try:
        platform_sessions = get_sessions().list_for_user(user_id)
    except RuntimeError:
        platform_sessions = []
    data["platform_sessions"] = [
        {
            "platform": item.platform.value,
            "platform_session_id": item.platform_session_id,
            "companion_session_id": item.companion_session_id,
        }
        for item in platform_sessions
    ]
    external = {"graph": "not_used"}
    settings = get_settings()
    if not settings.lite_mode and settings.enable_knowledge_graph:
        # SQL relations are already exported; an unavailable external store is explicit.
        from memory_system.graph_lifecycle import cleanup_pending
        from memory_system.graph_store import graph_store

        try:
            async with asyncio.timeout(10):
                if await cleanup_pending(user_id):
                    external["graph"] = {"status": "pending_memory_clear", "complete": False}
                else:
                    external["graph"] = await graph_store.get_neighborhood(user_id, limit=_MAX_ROWS + 1)
        except Exception:
            external["graph"] = {"status": "unavailable", "complete": False}
    return {
        "format": "companion.user-data.v1",
        "user_id": user_id,
        "exported_at": _now(),
        "data": data,
        "external": external,
        "scope": "宿主保存的当前用户数据；不包含浏览器缓存、宿主备份、服务商保留记录和第三方工具的外部结果。",
    }


async def _cleanup_local(user_id, session_ids):
    from core_orchestrator.state_machine import clear_debug_user_data
    clear_debug_user_data(user_id)
    from action_executor.push_bus import get_proactive_push_bus
    from memory_system.short_term import short_term_memory
    from memory_system.working import get_working_memory
    from persona_engine.runtime import get_emotion_engine, get_relationship_tracker

    await get_proactive_push_bus().forget_user(user_id)
    for session_id in session_ids:
        await get_working_memory().invalidate(session_id)
    await short_term_memory.delete_user_context(user_id)
    for engine in (get_emotion_engine(), get_relationship_tracker()):
        engine._memory_store.pop(user_id, None)
    from gateway_adapter.api import get_sessions

    with suppress(RuntimeError):
        get_sessions().remove_all_for_user(user_id)


async def _cleanup_resource(name, payload, user_id):
    if name == "local":
        await _cleanup_local(user_id, payload)
    elif name == "voice_files":
        delete_voice_files(payload)
    elif name == "devices":
        from device_coordination.api import get_gateway

        try:
            gateway = get_gateway()
        except RuntimeError:
            if not get_settings().lite_mode:
                raise
        else:
            await gateway.delete_user_data(user_id)
    elif name == "graph":
        from memory_system.graph_store import graph_store
        from memory_system.lifecycle import capture_memory_epoch

        await graph_store.delete_user_data(user_id, epoch=await capture_memory_epoch(user_id))
    else:
        raise ValueError("Unknown erasure resource")


async def _retry_cleanup(user_id):
    async with AsyncSessionLocal() as session:
        job = await session.get(ErasureJobORM, user_id)
        if job is None:
            return {"status": "none", "pending": []}
        pending = json.loads(job.pending_json)
        job_id = job.job_id
    for name, payload in tuple(pending.items()):
        try:
            async with asyncio.timeout(10):
                await _cleanup_resource(name, payload, user_id)
        except Exception:
            continue  # Receipt contains resource names, never credentials or exception text.
        del pending[name]
        async with AsyncSessionLocal() as session:
            job = await session.get(ErasureJobORM, user_id)
            job.pending_json = json.dumps(pending)
            job.status = "pending" if pending else "completed"
            job.updated_at = _now()
            await session.commit()
    return {"job_id": job_id, "status": "pending" if pending else "completed", "pending": list(pending)}


async def erase_data(user_id):
    async with erase_user_work(user_id):
        if not await no_pending_erasure(user_id):
            return await _retry_cleanup(user_id)
        async with AsyncSessionLocal() as session:
            await lock_memory_epoch(session, user_id, bump=True)
            session_ids = await _sessions(session, user_id, include_mixed=True)
            from core_orchestrator.platforms import revoke_platform_bindings

            await revoke_platform_bindings(session, user_id)
            files = list(
                (await session.scalars(select(VoiceAssetORM.filename).where(VoiceAssetORM.user_id == user_id))).all()
            )
            runs = Base.metadata.tables["task_runs"]
            steps = Base.metadata.tables["task_steps"]
            await session.execute(
                delete(steps).where(steps.c.run_id.in_(select(runs.c.id).where(runs.c.user_id == user_id)))
            )
            await session.execute(delete(SessionDigestORM).where(SessionDigestORM.session_id.in_(session_ids)))
            for table in reversed(user_tables()):
                await session.execute(delete(table).where(table.c.user_id == user_id))
            legacy, condition = await _legacy_user_condition(session, user_id)
            if legacy is not None:
                await session.execute(delete(legacy).where(condition))
            pending = {"local": session_ids, "voice_files": files, "devices": True}
            settings = get_settings()
            if not settings.lite_mode and settings.enable_knowledge_graph:
                pending["graph"] = True
            job = await session.get(ErasureJobORM, user_id)
            if job is None:
                job = ErasureJobORM(user_id=user_id)
                session.add(job)
            job.job_id, job.status, job.pending_json, job.updated_at = (
                str(uuid4()),
                "pending",
                json.dumps(pending),
                _now(),
            )
            await session.commit()
        return await _retry_cleanup(user_id)


@router.get("/user/{user_id}/export")
async def export_endpoint(user_id: str):
    from starlette.responses import Response

    payload = json.dumps(await export_data(user_id), ensure_ascii=False, default=str).encode("utf-8")
    if len(payload) > _MAX_BYTES:
        raise HTTPException(413, "数据超过 50 MiB 导出上限，请联系宿主管理员。")
    return Response(
        payload,
        media_type="application/json",
        headers={"Cache-Control": "no-store", "Content-Disposition": 'attachment; filename="companion-user-data.json"'},
    )


@router.get("/user/{user_id}/status")
async def status_endpoint(user_id: str):
    async with AsyncSessionLocal() as session:
        job = await session.get(ErasureJobORM, user_id)
        return {
            "job_id": job.job_id if job else None,
            "status": job.status if job else "none",
            "pending": list(json.loads(job.pending_json)) if job else [],
            "updated_at": job.updated_at if job else None,
        }


@router.post("/user/{user_id}/erase")
async def erase_endpoint(user_id: str, request: EraseRequest):
    if request.confirmation != "删除我的全部数据":
        raise HTTPException(400, "请输入“删除我的全部数据”确认清理。")
    try:
        result = await erase_data(user_id)
    except UserBusyError as error:
        raise HTTPException(409, str(error)) from None
    from starlette.responses import JSONResponse

    return JSONResponse(
        result, status_code=202 if result["status"] == "pending" else 200, headers={"Cache-Control": "no-store"}
    )
