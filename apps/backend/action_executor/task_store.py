"""Durable bounded task receipts. Interrupted work is never replayed automatically."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, Integer, String, UniqueConstraint, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, mapped_column

from shared_runtime.database import AsyncSessionLocal, Base


def _now():
    return datetime.now(UTC)


class TaskRunORM(Base):
    __tablename__ = "task_runs"
    __table_args__ = (UniqueConstraint("user_id", "session_id", "turn_id", name="uq_task_turn"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(128), index=True)
    session_id: Mapped[str] = mapped_column(String(128))
    turn_id: Mapped[str] = mapped_column(String(128))
    request: Mapped[str] = mapped_column(String(12000))
    status: Mapped[str] = mapped_column(String(32), default="running")
    message: Mapped[str] = mapped_column(String(16000), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class TaskStepORM(Base):
    __tablename__ = "task_steps"
    __table_args__ = (UniqueConstraint("run_id", "position", name="uq_task_step"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(36), index=True)
    position: Mapped[int] = mapped_column(Integer)
    tool_name: Mapped[str] = mapped_column(String(256))
    arguments: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(32), default="running")
    result: Mapped[dict] = mapped_column(JSON, default=dict)


class TaskStore:
    async def create(self, *, user_id: str, session_id: str, turn_id: str, request: str):
        run = TaskRunORM(
            id=str(uuid.uuid4()),
            user_id=user_id,
            session_id=session_id,
            turn_id=turn_id,
            request=request,
            status="running",
            message="",
        )
        async with AsyncSessionLocal() as session:
            session.add(run)
            try:
                await session.commit()
                return await self.get(run.id, user_id), True
            except IntegrityError:
                await session.rollback()
                existing = await session.scalar(
                    select(TaskRunORM).where(
                        TaskRunORM.user_id == user_id,
                        TaskRunORM.session_id == session_id,
                        TaskRunORM.turn_id == turn_id,
                    )
                )
                if existing is None:
                    raise
                return await self.get(existing.id, user_id), False

    async def get(self, run_id: str, user_id: str):
        async with AsyncSessionLocal() as session:
            run = await session.scalar(select(TaskRunORM).where(TaskRunORM.id == run_id, TaskRunORM.user_id == user_id))
            if run is None:
                return None
            steps = (
                await session.scalars(
                    select(TaskStepORM).where(TaskStepORM.run_id == run_id).order_by(TaskStepORM.position)
                )
            ).all()
            return {
                "id": run.id,
                "user_id": run.user_id,
                "session_id": run.session_id,
                "turn_id": run.turn_id,
                "request": run.request,
                "status": run.status,
                "message": run.message,
                "created_at": run.created_at.isoformat(),
                "updated_at": run.updated_at.isoformat(),
                "steps": [
                    {
                        "position": step.position,
                        "tool_name": step.tool_name,
                        "arguments": step.arguments,
                        "status": step.status,
                        "result": step.result,
                    }
                    for step in steps
                ],
            }

    async def list_for_user(self, user_id: str, limit: int = 30):
        async with AsyncSessionLocal() as session:
            ids = (
                await session.scalars(
                    select(TaskRunORM.id)
                    .where(TaskRunORM.user_id == user_id)
                    .order_by(TaskRunORM.created_at.desc())
                    .limit(limit)
                )
            ).all()
        return [await self.get(run_id, user_id) for run_id in ids]

    async def finish(self, run_id: str, user_id: str, status: str, message: str):
        async with AsyncSessionLocal() as session:
            await session.execute(
                update(TaskRunORM)
                .where(TaskRunORM.id == run_id, TaskRunORM.user_id == user_id, TaskRunORM.status == "running")
                .values(status=status, message=message[:16000], updated_at=_now())
            )
            await session.commit()
        return await self.get(run_id, user_id)

    async def cancel(self, run_id: str, user_id: str):
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                update(TaskRunORM)
                .where(
                    TaskRunORM.id == run_id,
                    TaskRunORM.user_id == user_id,
                    TaskRunORM.status.in_(["running", "awaiting_input"]),
                )
                .values(
                    status="cancelled",
                    message="已停止任务。已完成的操作保留；正在执行的操作需要核对结果。",
                    updated_at=_now(),
                )
            )
            await session.commit()
            return bool(result.rowcount)

    async def resume(self, run_id: str, user_id: str, clarification: str):
        async with AsyncSessionLocal() as session:
            run = await session.scalar(select(TaskRunORM).where(TaskRunORM.id == run_id, TaskRunORM.user_id == user_id))
            if not run or run.status != "awaiting_input":
                return None
            request = (run.request + "\n用户补充：" + clarification)[:12000]
            result = await session.execute(
                update(TaskRunORM)
                .where(TaskRunORM.id == run_id, TaskRunORM.user_id == user_id, TaskRunORM.status == "awaiting_input")
                .values(status="running", message="", request=request, updated_at=_now())
            )
            await session.commit()
            if not result.rowcount:
                return None
        return await self.get(run_id, user_id)

    async def start_step(self, run_id: str, position: int, name: str, arguments: dict):
        async with AsyncSessionLocal() as session:
            session.add(
                TaskStepORM(
                    id=str(uuid.uuid4()),
                    run_id=run_id,
                    position=position,
                    tool_name=name,
                    arguments=arguments,
                    status="running",
                    result={},
                )
            )
            await session.commit()

    async def finish_step(self, run_id: str, position: int, status: str, result: dict):
        async with AsyncSessionLocal() as session:
            await session.execute(
                update(TaskStepORM)
                .where(TaskStepORM.run_id == run_id, TaskStepORM.position == position)
                .values(status=status, result=result)
            )
            await session.commit()

    async def recover_interrupted(self):
        async with AsyncSessionLocal() as session:
            # Called once by the single reference-host process at startup.
            await session.execute(
                update(TaskStepORM)
                .where(TaskStepORM.status == "running")
                .values(status="outcome_unknown", result={"error": "host_restarted"})
            )
            await session.execute(
                update(TaskRunORM)
                .where(TaskRunORM.status == "running")
                .values(
                    status="interrupted",
                    message="服务重启中断了任务。请先核对已执行步骤，任务不会自动重做。",
                    updated_at=_now(),
                )
            )
            await session.commit()


task_store = TaskStore()
