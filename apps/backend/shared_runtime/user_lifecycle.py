"""Single-process user work ownership and erasure barriers, independent of the host."""

import asyncio
import functools
import inspect
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field


class StaleUserOperation(asyncio.CancelledError):
    """Old work must unwind, including code with broad ``except Exception`` handlers."""


class UserBusyError(RuntimeError):
    pass


@dataclass
class _State:
    generation: int = 0
    blocked: bool = False
    deleting: bool = False
    tasks: dict = field(default_factory=dict)


_states: dict[str, _State] = {}
_context: ContextVar[dict[str, int] | None] = ContextVar("companion_user_work", default=None)
_admission_check = None


def set_user_admission_check(check):
    """Reference hosts may inject a durable pending-cleanup check."""
    global _admission_check
    _admission_check = check


def assert_user_context():
    for user_id, generation in (_context.get() or {}).items():
        state = _states.get(user_id)
        if state and (state.blocked or state.generation != generation):
            raise StaleUserOperation("User data has been cleared or is being cleared")


def user_unavailable(user_id):
    state = _states.get(user_id)
    return bool(state and (state.blocked or (_context.get() or {}).get(user_id, state.generation) != state.generation))


@asynccontextmanager
async def user_operation(user_id: str | None, *, postcheck=True):
    if not user_id:
        yield
        return
    assert_user_context()
    state = _states.setdefault(user_id, _State())
    if state.blocked:
        raise StaleUserOperation("User data is being cleared")
    generation = state.generation
    if user_id not in (_context.get() or {}) and _admission_check and not await _admission_check(user_id):
        raise StaleUserOperation("User data cleanup is pending")
    # The durable check yielded; erasure may have started while it was running.
    assert_user_context()
    if state.blocked or generation != state.generation:
        raise StaleUserOperation("User data is being cleared")
    token = _context.set({**(_context.get() or {}), user_id: state.generation})
    task = asyncio.current_task()
    state.tasks[task] = state.tasks.get(task, 0) + 1
    try:
        yield
        if postcheck:
            assert_user_context()
    except asyncio.CancelledError:
        if user_unavailable(user_id):
            raise StaleUserOperation("User data has been cleared or is being cleared") from None
        raise
    finally:
        state.tasks[task] -= 1
        if not state.tasks[task]:
            del state.tasks[task]
        _context.reset(token)


def user_scoped(parameter="user_id"):
    """Wrap an async entry point, retaining its normal injected/standalone API."""

    def decorate(function):
        signature = inspect.signature(function)

        @functools.wraps(function)
        async def call(*args, **kwargs):
            bound = signature.bind(*args, **kwargs).arguments
            parts = parameter.split(".")
            value = bound.get(parts[0])
            for part in parts[1:]:
                value = getattr(value, part)
            async with user_operation(value):
                return await function(*args, **kwargs)

        return call

    return decorate


@asynccontextmanager
async def erase_user_work(user_id: str, timeout=10.0):
    """Block ingress, invalidate inherited contexts, and join active work before erasing.

    A worker that refuses cancellation leaves the user blocked. A subsequent erase
    retry can proceed once it has unwound. Never report a completed deletion then.
    """
    state = _states.setdefault(user_id, _State())
    if state.deleting:
        raise UserBusyError("数据清理正在进行，请稍后重试。")
    state.deleting = state.blocked = True
    state.generation += 1
    settled = False
    try:
        tasks = [task for task in state.tasks if task is not asyncio.current_task() and not task.done()]
        for task in tasks:
            task.cancel()
        if tasks:
            _, pending = await asyncio.wait(tasks, timeout=timeout)
            if pending:
                raise UserBusyError("后台任务仍在停止，数据尚未删除，请稍后重试。")
        settled = True
        yield
    finally:
        state.deleting = False
        if settled:
            state.blocked = False
