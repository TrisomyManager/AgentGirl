"""QQ's signed callback app, served on a separate loopback listener by the host."""

import asyncio
import json
from contextlib import nullcontext

from fastapi import FastAPI, HTTPException, Request

from shared_runtime.user_lifecycle import StaleUserOperation

from .config import PlatformConfigError
from .platforms.incoming import qq_message
from .store import InboxFullError


def create_callback_app(runtime):
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    @app.post("/qq/{account_id}")
    async def qq_callback(account_id: str, request: Request):
        try:
            config = runtime.config()
        except PlatformConfigError:
            raise HTTPException(503, "Callback configuration unavailable") from None
        account = config.account(account_id)
        if not config.enabled or not account or not account.enabled or not account.receive or account.platform != "qq":
            raise HTTPException(404, "Callback unavailable")
        from .platforms.qq_signature import QQSignature

        signatures = request.headers.getlist("x-signature-ed25519")
        timestamps = request.headers.getlist("x-signature-timestamp")
        if len(signatures) != 1 or len(timestamps) != 1:
            raise HTTPException(401, "Callback authentication failed")
        body = bytearray()
        try:
            async with asyncio.timeout(5):
                async for chunk in request.stream():
                    if len(body) + len(chunk) > 1024 * 1024:
                        raise HTTPException(413, "Callback too large")
                    body.extend(chunk)
        except TimeoutError:
            raise HTTPException(408, "Callback timed out") from None
        signature = QQSignature(account.secret.get_secret_value())
        if not signature.verify(bytes(body), signatures[0], timestamps[0]):
            raise HTTPException(401, "Callback authentication failed")
        try:
            current = runtime.config().account(account_id)
            if not current or current.fingerprint() != account.fingerprint() or not runtime.config().enabled:
                raise HTTPException(401, "Callback authentication failed")
        except PlatformConfigError:
            raise HTTPException(503, "Callback configuration unavailable") from None
        try:
            event = json.loads(body)
            if not isinstance(event, dict):
                raise ValueError
            if event.get("op") == 13:
                return signature.challenge(event)
        except (ValueError, UnicodeError):
            raise HTTPException(400, "Invalid callback") from None
        message = qq_message(event, account_id)
        if message is not None:
            try:
                await runtime.accept(message, account_version=account.fingerprint())
            except (InboxFullError, PlatformConfigError):
                raise HTTPException(503, "Callback inbox unavailable") from None
            except StaleUserOperation:
                pass  # An erased binding is intentionally ignored and acknowledged.
            except Exception:
                raise HTTPException(503, "Callback inbox unavailable") from None
        return {"op": 12}

    return app


async def serve_callbacks(runtime, port):
    import socket

    import uvicorn

    class CallbackServer(uvicorn.Server):
        def capture_signals(self):
            return nullcontext()  # The reference host owns process signals.

    # Bind before creating a task, so an occupied port fails host startup.
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        listener.bind(("127.0.0.1", port))
        listener.listen(128)
        listener.setblocking(False)
        server = CallbackServer(
            uvicorn.Config(
                create_callback_app(runtime),
                log_level="warning",
                access_log=False,
                lifespan="off",
                proxy_headers=False,
                timeout_graceful_shutdown=5,
            )
        )
        task = asyncio.create_task(server.serve(sockets=[listener]), name="qq-callback-listener")
        while not server.started:
            if task.done():
                await task
                raise RuntimeError("QQ callback listener failed")
            await asyncio.sleep(0.01)
        return server, task, listener
    except BaseException:
        listener.close()
        raise
