"""Reference-host composition for platforms; the gateway stays independent."""

import asyncio
from contextlib import asynccontextmanager

from gateway_adapter.config import ConfigSource, PlatformConfigError, PlatformsConfig
from gateway_adapter.runtime import PlatformRuntime
from gateway_adapter.store import revoke_user_bindings
from shared_contracts.models import TurnContext, UserProfile


async def generate_platform_reply(binding, message, session_id, turn_id):
    from safety_guard import default_guard, safe_fallback_reply

    decision = default_guard.evaluate(message.text, source="input")
    if decision.blocked:
        return safe_fallback_reply(decision)
    if message.audience == "room":
        # Room replies never open the owner's private memory, profile or tools.
        from shared_runtime.llm_client import LLMClient

        client = LLMClient()
        try:
            result = await client.generate(
                system_prompt=(
                    "你是小暖，正在公共群聊中回复一条明确提及你的消息。"
                    "只根据当前消息简洁作答，不假设你知道发送者的任何私人资料，"
                    "不声称查询过记忆或执行了工具。控制在150字以内。"
                ),
                user_message=message.text,
                max_tokens=300,
            )
            text = result.get("assistant_message", "")
        finally:
            await client.close()
        output = default_guard.evaluate(text, source="output")
        return safe_fallback_reply(output) if output.blocked else text
    from core_orchestrator.orchestrator import get_orchestrator
    from memory_system.session_store import PersistentSessionMemory

    await PersistentSessionMemory().authorize_session(session_id, binding.user_id, claim=True)
    result = await (await get_orchestrator()).process_turn(
        TurnContext(
            turn_id=turn_id,
            session_id=session_id,
            user=UserProfile(user_id=binding.user_id, platform=message.platform),
            platform=message.platform,
            user_message=message.text,
            request_voice_reply=False,
        )
    )
    if result.get("reply_suppressed"):
        return ""
    return result.get("assistant_message", "")


@asynccontextmanager
async def platform_lifespan(app):
    runtime = PlatformRuntime(generate=generate_platform_reply)
    app.state.platform_runtime = runtime
    callback = None
    try:
        config = runtime.config()
        if config.enabled:
            for account in config.accounts:
                if account.enabled and account.receive and account.platform == "discord":
                    import discord  # noqa: F401 -- enabled feature must be installed
                if account.enabled and account.receive and account.platform == "qq":
                    from gateway_adapter.platforms.qq_signature import QQSignature

                    QQSignature(account.secret.get_secret_value())
            await runtime.start()
            if any(a.enabled and a.receive and a.platform == "qq" for a in config.accounts):
                from gateway_adapter.callbacks import serve_callbacks

                callback = await serve_callbacks(runtime, config.qq_callback_port)
                runtime.qq_callback_ready = True
        yield
    finally:

        async def cleanup():
            try:
                if callback:
                    server, task, listener = callback
                    server.should_exit = True
                    try:
                        await task
                    finally:
                        listener.close()
            finally:
                runtime.qq_callback_ready = False
                await runtime.close()
                app.state.platform_runtime = None

        task = asyncio.create_task(cleanup())
        cancelled = False
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                cancelled = True
        task.result()
        if cancelled:
            raise asyncio.CancelledError


async def revoke_platform_bindings(session, user_id):
    try:
        config = ConfigSource.from_environment().load()
    except PlatformConfigError:
        config = PlatformsConfig()  # Durable registrations also cover an invalid or removed private file.
    await revoke_user_bindings(session, user_id, config)
