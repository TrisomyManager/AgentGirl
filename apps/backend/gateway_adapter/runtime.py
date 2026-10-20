"""Opt-in, host-injected platform conversations with durable replay boundaries."""

import asyncio
import json
from contextlib import suppress

import httpx
import structlog

from shared_runtime.log_safety import install_http_url_redaction
from shared_runtime.user_lifecycle import StaleUserOperation, user_operation

from .config import ConfigSource, PlatformConfigError
from .delivery import BotDelivery, split_text
from .store import InboxStore

logger = structlog.get_logger(__name__)


class PlatformRuntime:
    def __init__(self, *, source=None, store=None, generate=None, client=None, delivery=None):
        self.source = source or ConfigSource.from_environment()
        self.store = store or InboxStore()
        self.generate = generate
        install_http_url_redaction()
        self.client = client or httpx.AsyncClient(timeout=35, follow_redirects=False, trust_env=False)
        self._owns_client = client is None
        self.delivery = delivery or BotDelivery(self.client)
        self._ingress_lock = asyncio.Lock()
        self._tasks = []
        self._worker_task = None
        self._receivers = {}
        self._stopping = False
        self._wake = asyncio.Event()
        self.receiver_states = {}
        self.qq_callback_ready = False

    def config(self):
        return self.source.load()

    def status(self):
        try:
            config = self.config()
        except PlatformConfigError:
            return {"state": "invalid", "accounts": []}
        return {
            "state": "enabled" if config.enabled else "disabled",
            "accounts": [
                {
                    "id": account.id,
                    "platform": account.platform,
                    "reply": bool(config.enabled and account.enabled and account.receive and account.reply),
                    "receive_state": (
                        "disabled"
                        if not config.enabled or not account.enabled or not account.receive
                        else ("waiting_callback" if self.qq_callback_ready else "unavailable")
                        if account.platform == "qq"
                        else self.receiver_states.get(account.id, "starting")
                    ),
                }
                for account in config.accounts
            ],
        }

    async def accept(self, message, *, account_version=None):
        resolved = self.config().resolve(message)
        if resolved is None:
            return "ignored"
        account, binding, key = resolved
        if account_version is not None and account.fingerprint() != account_version:
            return "revoked"
        async with user_operation(binding.user_id), self._ingress_lock:
            # A queued caller might have outlived a revocation or config update.
            current = self.config().resolve(message)
            if current is None or current[2] != key or current[0].fingerprint() != account.fingerprint():
                return "revoked"
            result = await self.store.accept(message, account, binding, key)
        self._wake.set()
        return result

    async def authorized(self, row, *, account_version=None):
        try:
            resolved = self.config().resolve(self.store.message(row))
        except PlatformConfigError:
            return None
        if resolved is None:
            return None
        account, binding, key = resolved
        if (
            key != row.binding_key
            or binding.user_id != row.user_id
            or not account.reply
            or (account_version is not None and account.fingerprint() != account_version)
        ):
            return None
        if await self.store.revoked(key):
            return None
        return account, binding

    async def process_one(self):
        row = await self.store.next()
        if row is None:
            return False
        try:
            async with user_operation(row.user_id):
                resolved = await self.authorized(row)
                if not resolved or self.generate is None:
                    await self.store.transition(row.id, row.status, "revoked", reason="binding_unavailable")
                    return True
                account, binding = resolved
                task = asyncio.create_task(self._process(row, account, binding), name="platform-bound-turn")

                async def monitor():
                    while not task.done():
                        await asyncio.sleep(0.25)
                        try:
                            allowed = await self.authorized(row, account_version=account.fingerprint())
                        except Exception:
                            allowed = False
                        if not allowed:
                            task.cancel()
                            return

                watcher = asyncio.create_task(monitor(), name="platform-binding-monitor")
                try:
                    await task
                except asyncio.CancelledError:
                    if asyncio.current_task().cancelling():
                        raise
                    # Watcher revoked a child. Stop delivery without killing the inbox worker.
                finally:
                    await drain_tasks([task, watcher])
        except StaleUserOperation:
            # Erasure owns the old rows. No detached writes may recreate them.
            while asyncio.current_task().cancelling():
                asyncio.current_task().uncancel()
        return True

    async def _process(self, row, account, binding):
        state = row.status
        try:
            if state == "pending":
                if not await self.store.transition(row.id, "pending", "processing"):
                    return
                state = "processing"
                async with asyncio.timeout(120):
                    text = await self.generate(binding, self.store.message(row), row.session_id, row.id)
                parts = split_text(text, account.platform)
                if not parts:
                    await self.store.transition(row.id, state, "ignored", reason="reply_suppressed")
                    return
                if not await self.store.transition(row.id, state, "generated", reply_text=text):
                    return
                state = "generated"
            else:
                parts = split_text(row.reply_text, account.platform)
            ids = json.loads(row.sent_ids_json)
            if not await self.authorized(row, account_version=account.fingerprint()):
                await self.store.transition(row.id, state, "revoked", reason="binding_changed")
                return
            if not await self.store.transition(row.id, state, "sending"):
                return
            state = "sending"
            for index, part in enumerate(parts):
                if not await self.authorized(row, account_version=account.fingerprint()):
                    await self.store.transition(
                        row.id, state, "unknown", reason="binding_changed", sent_ids_json=json.dumps(ids)
                    )
                    return
                receipt = await self.delivery.send(account, self.store.message(row), part, index + 1)
                if receipt.outcome != "confirmed" or not receipt.message_id:
                    status = "rejected" if receipt.outcome == "rejected" else "unknown"
                    await self.store.transition(
                        row.id, state, status, reason="delivery_" + status, sent_ids_json=json.dumps(ids)
                    )
                    return
                ids.append(receipt.message_id)
                # Persist each confirmed part before beginning the next mutation.
                if not await self.store.transition(row.id, state, state, sent_ids_json=json.dumps(ids)):
                    return
                if index + 1 < len(parts):
                    await asyncio.sleep(1)
            await self.store.transition(row.id, state, "sent", sent_ids_json=json.dumps(ids))
        except asyncio.CancelledError:
            # Privacy contexts refuse this write; erasure then removes the row itself.
            with suppress(StaleUserOperation):
                await self.store.transition(
                    row.id, state, "unknown" if state == "sending" else "interrupted", reason="cancelled"
                )
            raise
        except Exception as error:
            logger.warning("platform.turn_failed", reason=type(error).__name__)
            await self.store.transition(
                row.id, state, "unknown" if state == "sending" else "failed", reason="operation_failed"
            )

    async def start(self, *, receive=True):
        config = self.config()  # Explicit invalid config fails startup, without printing credentials.
        if not config.enabled:
            return
        await self.register_config(config)
        await self.store.recover()
        self._worker_task = asyncio.create_task(self._worker(), name="platform-inbox-worker")
        self._tasks.append(self._worker_task)
        if receive:
            self._tasks.append(asyncio.create_task(self._supervise_receivers(), name="platform-receiver-supervisor"))

    async def _worker(self):
        while not self._stopping:
            try:
                if await self.process_one():
                    continue
            except asyncio.CancelledError:
                raise
            except Exception as error:
                logger.warning("platform.inbox_unavailable", reason=type(error).__name__)
            self._wake.clear()
            with suppress(TimeoutError):
                await asyncio.wait_for(self._wake.wait(), timeout=1)

    async def _supervise_receivers(self):
        from .receivers import discord_receiver, telegram_receiver

        factories = {"telegram": telegram_receiver, "discord": discord_receiver}
        while not self._stopping:
            try:
                config = self.config()
                await self.register_config(config)
                accounts = {
                    a.id: a
                    for a in config.accounts
                    if config.enabled and a.enabled and a.receive and a.platform in factories
                }
            except PlatformConfigError:
                accounts = {}  # File disappearance or a malformed edit revokes, never falls back.
            except Exception as error:
                accounts = {}
                logger.warning("platform.receiver_configuration_unavailable", reason=type(error).__name__)
            for identifier, (version, task) in list(self._receivers.items()):
                if identifier not in accounts or accounts[identifier].fingerprint() != version or task.done():
                    await drain_tasks([task])
                    del self._receivers[identifier]
                    self.receiver_states.pop(identifier, None)
            for identifier, account in accounts.items():
                if identifier not in self._receivers:
                    self.receiver_states[identifier] = "starting"
                    task = asyncio.create_task(factories[account.platform](self, account), name="platform-receiver")
                    self._receivers[identifier] = account.fingerprint(), task
            await asyncio.sleep(1)

    async def register_config(self, config):
        for binding in config.bindings:
            try:
                async with user_operation(binding.user_id), self._ingress_lock:
                    await self.store.register(config.account(binding.account_id), binding)
            except StaleUserOperation:
                # A deleting user does not take down receiving for other owners.
                while asyncio.current_task().cancelling():
                    asyncio.current_task().uncancel()

    async def close(self):
        self._stopping = True
        tasks = self._tasks + [task for _, task in self._receivers.values()]
        try:
            await drain_tasks(tasks)
        finally:
            if self._owns_client:
                await self.client.aclose()


async def drain_tasks(tasks):
    async def cleanup():
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    await settle_cleanup(cleanup())


async def settle_cleanup(awaitable):
    child = asyncio.create_task(awaitable)
    cancelled = False
    while not child.done():
        try:
            await asyncio.shield(child)
        except asyncio.CancelledError:
            cancelled = True
    child.result()
    if cancelled:
        raise asyncio.CancelledError
