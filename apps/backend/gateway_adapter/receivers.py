"""Provider receive transports. Only the host config enables a receiver."""

import asyncio

import structlog

from .config import PlatformConfigError
from .platforms.http_delivery import request_json
from .platforms.incoming import discord_message, telegram_message
from .runtime import drain_tasks, settle_cleanup
from .store import InboxFullError

logger = structlog.get_logger(__name__)


def active(runtime, account):
    try:
        config = runtime.config()
        current = config.account(account.id)
        return bool(
            config.enabled
            and current
            and current.enabled
            and current.receive
            and current.fingerprint() == account.fingerprint()
        )
    except PlatformConfigError:
        return False


async def telegram_poll_once(runtime, account, *, bot_id, bot_username):
    key = account.identity_key()
    position = await runtime.store.cursor(key)
    payload = {"timeout": 25, "limit": 50, "allowed_updates": ["message"]}
    if position is not None:
        payload["offset"] = position + 1
    response = await request_json(
        runtime.client,
        "POST",
        f"https://api.telegram.org/bot{account.token.get_secret_value()}/getUpdates",
        json=payload,
        max_bytes=1024 * 1024,
    )
    data = response.data or {}
    updates = data.get("result")
    if data.get("ok") is not True or not isinstance(updates, list) or len(updates) > 50:
        raise RuntimeError("Telegram polling unavailable")
    previous = position
    for update in updates:
        identifier = update.get("update_id") if isinstance(update, dict) else None
        if type(identifier) is not int or identifier < 0:
            raise RuntimeError("Invalid Telegram update ID")
        if previous is not None and identifier <= previous:
            raise RuntimeError("Non-monotonic Telegram updates")
        if not active(runtime, account):
            return
        message = telegram_message(update, account.id, bot_id=bot_id, bot_username=bot_username)
        if message is not None:
            await runtime.accept(message, account_version=account.fingerprint())
        # Next getUpdates acknowledges only updates durably accepted or safely ignored.
        await runtime.store.advance(key, identifier)
        previous = identifier


async def telegram_receiver(runtime, account):
    base = f"https://api.telegram.org/bot{account.token.get_secret_value()}"
    delay = 2
    while active(runtime, account):
        try:
            me = (await request_json(runtime.client, "GET", base + "/getMe")).data or {}
            info = me.get("result") or {}
            webhook = (await request_json(runtime.client, "GET", base + "/getWebhookInfo")).data or {}
            hook = webhook.get("result") or {}
            if (
                me.get("ok") is not True
                or not isinstance(info, dict)
                or info.get("is_bot") is not True
                or type(info.get("id")) is not int
                or not isinstance(info.get("username"), str)
                or webhook.get("ok") is not True
                or not isinstance(hook, dict)
                or not isinstance(hook.get("url"), str)
                or hook.get("url")
            ):
                raise RuntimeError("Telegram bot or polling configuration unavailable")
            while active(runtime, account):
                await telegram_poll_once(runtime, account, bot_id=str(info["id"]), bot_username=info["username"])
                runtime.receiver_states[account.id] = "connected"
                delay = 2
                await asyncio.sleep(0.1)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            runtime.receiver_states[account.id] = "unavailable"
            logger.warning("platform.telegram_receive_unavailable", reason=type(error).__name__)
        await asyncio.sleep(delay)
        delay = min(60, delay * 2)


def discord_sdk_message(message, account_id, bot_id):
    """Keep provider objects and quoted bodies outside the normalized contract."""
    snapshots = getattr(message, "message_snapshots", [])
    return discord_message(
        {
            "op": 0,
            "t": "MESSAGE_CREATE",
            "d": {
                "id": str(message.id),
                "channel_id": str(message.channel.id),
                "guild_id": str(message.guild.id) if message.guild else None,
                "author": {"id": str(message.author.id), "bot": message.author.bot},
                "webhook_id": message.webhook_id,
                "content": message.content,
                "mentions": [{"id": str(user.id)} for user in message.mentions],
                "message_snapshots": [True] if snapshots else [],
            },
        },
        account_id,
        bot_id=str(bot_id),
    )


async def discord_receiver(runtime, account):
    try:
        import discord
    except ImportError:
        runtime.receiver_states[account.id] = "unavailable"
        logger.warning("platform.discord_dependency_missing")
        await asyncio.Event().wait()
        return
    queue = asyncio.Queue(maxsize=100)

    class BoundClient(discord.Client):
        def dispatch(self, event, /, *args, **kwargs):
            if event == "ready":
                runtime.receiver_states[account.id] = "connected"
            elif event == "disconnect":
                runtime.receiver_states[account.id] = "starting"
            if event == "message" and self.user and active(runtime, account):
                try:
                    message = discord_sdk_message(args[0], account.id, self.user.id)
                    if message is not None and runtime.config().resolve(message):
                        queue.put_nowait(message)
                except asyncio.QueueFull:
                    # Discord has no per-message acknowledgement. Make the gap explicit.
                    logger.error("platform.discord_inbox_overflow")
                except Exception as error:
                    logger.warning("platform.discord_event_ignored", reason=type(error).__name__)
            super().dispatch(event, *args, **kwargs)

    intents = discord.Intents.none()
    intents.guilds = True
    intents.guild_messages = True
    intents.dm_messages = True
    intents.message_content = account.message_content
    client = BoundClient(intents=intents, max_messages=None, allowed_mentions=discord.AllowedMentions.none())

    async def consume():
        while True:
            message = await queue.get()
            try:
                while True:
                    try:
                        await runtime.accept(message, account_version=account.fingerprint())
                        break
                    except InboxFullError:
                        await asyncio.sleep(1)
            finally:
                queue.task_done()

    worker = asyncio.create_task(consume(), name="discord-bound-inbox")
    connection = asyncio.create_task(client.start(account.token.get_secret_value()), name="discord-gateway")
    try:
        done, _ = await asyncio.wait([worker, connection], return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            await task
    except asyncio.CancelledError:
        raise
    except Exception as error:
        runtime.receiver_states[account.id] = "unavailable"
        logger.warning("platform.discord_receive_unavailable", reason=type(error).__name__)
        await asyncio.sleep(30)
    finally:

        async def cleanup():
            await drain_tasks([worker, connection])
            # discord.py 2.7.1's public close() leaves its delayed READY task
            # running. Own that one SDK task as well; the extra is pinned to 2.7.
            ready = getattr(client._connection, "_ready_task", None)
            if ready is not None:
                await drain_tasks([ready])
            heartbeat = getattr(client.ws, "_keep_alive", None)
            await client.close()
            if heartbeat is not None and heartbeat.is_alive():
                await asyncio.to_thread(heartbeat.join, 5)
                if heartbeat.is_alive():
                    raise RuntimeError("Discord heartbeat did not stop")

        await settle_cleanup(cleanup())
