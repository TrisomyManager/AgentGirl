"""Host-approved local plugins with worker-owned resources and atomic reloads.

Python plugins are trusted host code, not a sandbox. Chat cannot install code,
choose paths, change grants or enable plugins. Each generation owns its scopes
in one worker, just like official MCP transport lifecycles.
"""

from __future__ import annotations

import asyncio
import hashlib
import inspect
from contextvars import Context, copy_context
import json
import re
import sys
import types
from contextlib import AsyncExitStack
from dataclasses import dataclass
from itertools import islice
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from jsonschema import Draft202012Validator, FormatChecker
from pydantic import BaseModel, ConfigDict, Field, field_validator

from action_executor.registry import ActionResult
from action_executor.tool_schema import canonical_schema

_ID = r"^[a-z][a-z0-9_]{0,31}$"
_IDENTITY = {"user_id", "session_id", "turn_id", "operation_id"}


class PluginGrant(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str = Field(pattern=_ID)
    enabled: bool = False
    allowed_users: list[str] = Field(default_factory=list, max_length=1000)
    allow_mutations: bool = False
    timeout_seconds: float = Field(default=10, ge=0.1, le=30, allow_inf_nan=False)

    @field_validator("allowed_users")
    @classmethod
    def explicit_users(cls, users):
        if any(not user.strip() or user.strip() == "*" for user in users):
            raise ValueError("Explicit users required")
        return users


class PluginManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=_ID)
    name: str = Field(min_length=1, max_length=80)
    version: str = Field(min_length=1, max_length=32)
    api_version: Literal[1] = 1
    entrypoint: Literal["plugin.py"] = "plugin.py"


@dataclass(frozen=True)
class PluginCallContext:
    user_id: str
    session_id: str = ""
    turn_id: str = ""
    operation_id: str = ""


class PluginAPI:
    """Passed only during setup. Register cleanup before acquiring resources."""

    def __init__(self, resources: AsyncExitStack):
        self.resources = resources
        self.tools: dict[str, tuple[dict, Any, bool]] = {}
        self.sealed = False

    def add_tool(self, name: str, description: str, schema: dict, handler, *, read_only: bool = True):
        if self.sealed or not re.fullmatch(_ID, name) or len(self.tools) >= 32 or name in self.tools:
            raise ValueError("Invalid or duplicate plugin tool")
        if not inspect.iscoroutinefunction(handler) or not 1 <= len(description) <= 1000:
            raise ValueError("Plugin tools need async handlers and bounded descriptions")
        schema = canonical_schema("plugin__" + name, schema)
        self.tools[name] = (
            {
                "name": name,
                "description": description,
                "inputSchema": schema,
                "annotations": {
                    "readOnlyHint": read_only,
                    "destructiveHint": not read_only,
                    "idempotentHint": read_only,
                    "openWorldHint": False,
                },
            },
            handler,
            read_only,
        )


def _unavailable(code="plugin_unavailable"):
    return ActionResult(ok=False, message="该扩展暂时不可用，请稍后重试。", data={"error": code})


class _Worker:
    def __init__(self, code: bytes, source: Path, grant: PluginGrant):
        self.code, self.source, self.grant = code, source, grant
        self.name = "_companion_plugin_" + grant.id + "_" + uuid4().hex
        self.queue: asyncio.Queue = asyncio.Queue(maxsize=32)
        self.ready = asyncio.get_running_loop().create_future()
        self.api: PluginAPI | None = None
        self.accepting = True
        self.task = asyncio.create_task(self._run(), name="plugin:" + grant.id, context=Context())

    async def start(self):
        try:
            await asyncio.wait_for(asyncio.shield(self.ready), 5)
        except BaseException:
            await self.close()
            raise

    async def _run(self):
        job = None
        try:
            async with AsyncExitStack() as resources:
                module = types.ModuleType(self.name)
                module.__file__ = str(self.source)
                sys.modules[self.name] = module
                # Compile source directly: same-second edits must not reuse stale pyc.
                exec(compile(self.code, str(self.source), "exec"), module.__dict__)
                api = PluginAPI(resources)
                setup = getattr(module, "setup", None)
                if not inspect.iscoroutinefunction(setup):
                    raise ValueError("Plugin requires async setup(api)")
                async with asyncio.timeout(5):
                    await setup(api)
                if not api.tools:
                    raise ValueError("Plugin exports no tools")
                self.api = api
                api.sealed = True
                self.ready.set_result(None)
                while (job := await self.queue.get()) is not None:
                    name, arguments, context, future, execution, caller_context = job
                    if future.cancelled():
                        continue
                    handler, read_only = api.tools[name][1:]

                    async def owned_call():
                        from shared_runtime.user_lifecycle import user_operation

                        async with user_operation(context.user_id):
                            return await handler(arguments, context)

                    operation = asyncio.create_task(owned_call(), name="plugin-tool:" + name, context=caller_context)
                    execution.append(operation)
                    try:
                        async with asyncio.timeout(self.grant.timeout_seconds):
                            result = await operation
                        if not isinstance(result, ActionResult):
                            raise ValueError("Invalid plugin result")
                        encoded = json.dumps({"message": result.message, "data": result.data}, allow_nan=False)
                        if len(encoded.encode()) > 65536:
                            raise ValueError("Plugin result too large")
                    except asyncio.CancelledError:
                        if asyncio.current_task().cancelling():
                            raise
                        result = _unavailable("plugin_interrupted" if read_only else "outcome_unknown")
                    except Exception:
                        result = _unavailable("plugin_call_failed" if read_only else "outcome_unknown")
                    if not future.done():
                        future.set_result(result)
                    job = None
        except BaseException as exc:
            if not self.ready.done():
                self.ready.set_exception(RuntimeError("Plugin setup failed"))
            if isinstance(exc, asyncio.CancelledError):
                raise
        finally:
            self.accepting = False
            if job is not None and not job[3].done():
                readonly = self.api.tools[job[0]][2] if self.api else True
                job[3].set_result(_unavailable("plugin_interrupted" if readonly else "outcome_unknown"))
            self._discard_queued()
            sys.modules.pop(self.name, None)

    def _discard_queued(self):
        while not self.queue.empty():
            item = self.queue.get_nowait()
            if item is not None and not item[3].done():
                item[3].set_result(_unavailable())

    async def call(self, name, arguments, context):
        if not self.accepting or self.task.done():
            return _unavailable()
        future = asyncio.get_running_loop().create_future()
        execution = []
        try:
            self.queue.put_nowait((name, arguments, context, future, execution, copy_context()))
        except asyncio.QueueFull:
            return _unavailable("plugin_busy")
        try:
            return await asyncio.wait_for(asyncio.shield(future), self.grant.timeout_seconds + 1)
        except TimeoutError:
            readonly = self.api.tools[name][2] if self.api else True
            return _unavailable("outcome_unknown" if execution and not readonly else "plugin_timeout")
        finally:
            if not future.done():
                future.cancel()
                for task in execution:
                    task.cancel()
                if execution:
                    await asyncio.gather(*execution, return_exceptions=True)

    async def close(self):
        self.accepting = False
        self._discard_queued()
        if not self.task.done():
            self.queue.put_nowait(None)
        try:
            await asyncio.wait_for(asyncio.shield(self.task), self.grant.timeout_seconds + 6)
        except TimeoutError:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
        except asyncio.CancelledError:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
            raise
        if self.ready.done() and not self.ready.cancelled():
            self.ready.exception()  # retrieve setup failures even during cancellation


class PluginManager:
    def __init__(self, directory: Path | None = None, config_file: Path | None = None, *, poll_seconds=1):
        self.directory, self.config_file = directory, config_file
        self.poll_seconds = max(0.1, poll_seconds)
        self._workers: dict[str, _Worker] = {}
        self._revisions: dict[str, str] = {}
        self._failed: dict[str, tuple[str, dict]] = {}
        self._status: dict[str, dict] = {}
        self._lock = asyncio.Lock()
        self._installation_lock = asyncio.Lock()
        self._watcher: asyncio.Task | None = None

    def status(self):
        return [dict(value) for value in self._status.values()]

    def _snapshot(self):
        if self.directory is None:
            return {}, {}
        configuration = {"plugins": []}
        if self.config_file is not None:
            if self.config_file.stat().st_size > 65536:
                raise ValueError("Plugin configuration too large")
            configuration = json.loads(self.config_file.read_text(encoding="utf-8"))
        if set(configuration) != {"plugins"} or len(configuration["plugins"]) > 64:
            raise ValueError("Invalid plugin configuration")
        grants = [PluginGrant.model_validate(item) for item in configuration["plugins"]]
        if len({grant.id for grant in grants}) != len(grants):
            raise ValueError("Duplicate plugin grants")
        root = self.directory.resolve()
        result, invalid = {}, {}
        if root.is_dir():
            folders = list(islice(root.iterdir(), 129))
            if len(folders) > 128:
                raise ValueError("Too many plugin entries")
            for folder in folders:
                if not re.fullmatch(_ID, folder.name) or not folder.is_dir():
                    continue
                try:
                    manifest_path = folder / "plugin.json"
                    if not folder.resolve().is_relative_to(root) or not manifest_path.resolve().is_relative_to(root):
                        raise ValueError("Plugin directory escapes root")
                    if manifest_path.stat().st_size > 16384:
                        raise ValueError("Manifest too large")
                    info = PluginManifest.model_validate_json(manifest_path.read_bytes())
                    if info.id != folder.name:
                        raise ValueError("Plugin identity mismatch")
                    invalid[info.id] = {"id": info.id, "name": info.name, "version": info.version, "status": "disabled"}
                except Exception:
                    invalid[folder.name] = {"id": folder.name, "status": "invalid_manifest"}
        for grant in grants:
            if not grant.enabled:
                continue
            folder = (root / grant.id).resolve()
            if not folder.is_relative_to(root) or not folder.is_dir():
                continue  # Removed directories retire their tools.
            try:
                manifest_file, entry = folder / "plugin.json", folder / "plugin.py"
                if any(not path.resolve().is_relative_to(folder) for path in (manifest_file, entry)):
                    raise ValueError("Plugin files must remain inside their directory")
                if manifest_file.stat().st_size > 16384 or entry.stat().st_size > 1024 * 1024:
                    raise ValueError("Plugin source too large")
                raw = manifest_file.read_bytes()
                manifest = PluginManifest.model_validate_json(raw)
                if manifest.id != grant.id:
                    raise ValueError("Plugin identity mismatch")
                code = entry.read_bytes()
                revision = hashlib.sha256(raw + code + grant.model_dump_json().encode()).hexdigest()
                result[grant.id] = (grant, manifest, code, entry, revision)
            except Exception:
                invalid[grant.id] = {"id": grant.id, "status": "invalid_manifest"}
        return result, invalid

    async def refresh(self):
        async with self._lock:
            try:
                snapshot, invalid = await asyncio.to_thread(self._snapshot)
            except Exception:
                # Revocation must fail closed; broken host config cannot preserve old grants.
                snapshot = {}
                invalid = {}
                invalid = {"configuration": {"id": "configuration", "status": "invalid_config"}}
            self._status = invalid
            self._failed = {key: value for key, value in self._failed.items() if key in snapshot}
            for identifier in list(self._workers):
                if identifier not in snapshot:
                    worker = self._workers.pop(identifier)
                    self._revisions.pop(identifier, None)
                    await worker.close()
                    self._status[identifier] = {"id": identifier, "status": "disabled"}
            for identifier, (grant, manifest, code, entry, revision) in snapshot.items():
                if self._failed.get(identifier, (None,))[0] == revision:
                    self._status[identifier] = self._failed[identifier][1]
                    continue
                if self._revisions.get(identifier) == revision:
                    self._status[identifier] = {
                        "id": identifier,
                        "name": manifest.name,
                        "version": manifest.version,
                        "status": "loaded",
                        "revision": revision[:12],
                        "tools_count": len(self._workers[identifier].api.tools),
                    }
                    continue
                candidate = _Worker(code, entry, grant)
                try:
                    await candidate.start()
                except asyncio.CancelledError:
                    raise
                except Exception:
                    self._status[identifier] = {"id": identifier, "name": manifest.name, "status": "load_failed"}
                    # Never retain broader old permissions after a grant change.
                    old = self._workers.get(identifier)
                    if old and old.grant != grant:
                        self._workers.pop(identifier)
                        self._revisions.pop(identifier, None)
                        await old.close()
                    self._status[identifier]["using_previous"] = identifier in self._workers
                    self._failed[identifier] = (revision, dict(self._status[identifier]))
                    continue
                self._failed.pop(identifier, None)
                old = self._workers.get(identifier)
                self._workers[identifier] = candidate
                self._revisions[identifier] = revision
                self._status[identifier] = {
                    "id": identifier,
                    "name": manifest.name,
                    "version": manifest.version,
                    "status": "loaded",
                    "revision": revision[:12],
                    "tools_count": len(candidate.api.tools),
                }
                if old:
                    await old.close()

    async def start(self):
        await self.refresh()
        if self.directory is not None and self._watcher is None:
            self._watcher = asyncio.create_task(self._watch(), name="plugin-watcher")

    async def _watch(self):
        while True:
            await asyncio.sleep(self.poll_seconds)
            await self.refresh()

    def tools_for(self, user_id: str):
        tools = []
        for identifier, worker in self._workers.items():
            if user_id not in worker.grant.allowed_users or not worker.accepting or not worker.api:
                continue
            for name, (meta, _, read_only) in worker.api.tools.items():
                if read_only or worker.grant.allow_mutations:
                    tools.append({**meta, "name": f"plugin_{identifier}__{name}"})
        return tools

    def owns(self, name: str) -> bool:
        return any(
            name == f"plugin_{identifier}__{tool}"
            for identifier, worker in self._workers.items()
            if worker.api
            for tool in worker.api.tools
        )

    async def call(self, name: str, arguments: dict, context: PluginCallContext):
        match = re.fullmatch(r"plugin_([a-z][a-z0-9_]{0,31})__([a-z][a-z0-9_]{0,31})", name)
        worker = self._workers.get(match[1]) if match else None
        if not worker or not worker.api or context.user_id not in worker.grant.allowed_users:
            return _unavailable("plugin_not_authorized")
        tool = worker.api.tools.get(match[2])
        if not tool or (not tool[2] and not worker.grant.allow_mutations):
            return _unavailable("plugin_not_authorized")
        try:
            if not isinstance(arguments, dict) or arguments.keys() & _IDENTITY:
                raise ValueError("Host identity is not a tool argument")
            if len(json.dumps(arguments, allow_nan=False).encode()) > 65536:
                raise ValueError("Arguments too large")
            Draft202012Validator(tool[0]["inputSchema"], format_checker=FormatChecker()).validate(arguments)
        except Exception:
            return _unavailable("invalid_arguments")
        return await worker.call(match[2], dict(arguments), context)

    async def close(self):
        if self._watcher:
            self._watcher.cancel()
            await asyncio.gather(self._watcher, return_exceptions=True)
            self._watcher = None
        async with self._lock:
            workers, self._workers = list(self._workers.values()), {}
            self._revisions.clear()
            self._failed.clear()
            await asyncio.gather(*(worker.close() for worker in workers))


plugin_manager = PluginManager()
