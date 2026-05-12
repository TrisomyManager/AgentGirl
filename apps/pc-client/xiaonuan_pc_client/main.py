"""PC simulator client for Device Operation Gateway (claim + token auth)."""

from __future__ import annotations

import asyncio
import os
import platform
import sys
import time

import httpx

BASE = os.environ.get("XIAONUAN_API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
DEVICE_ID = os.environ.get("XIAONUAN_DEVICE_ID", "pc-sim-001")
USER_ID = os.environ.get("XIAONUAN_USER_ID", "user_001")
FULL_NAME = os.environ.get("XIAONUAN_DEVICE_NAME", "我的电脑")
PLATFORM = "app"
DEVICE_TYPE = "pc"
CAPABILITIES = ["ping", "show_notification", "open_url", "get_device_status"]
CLIENT_VERSION = "1.0.0"

device_token: str | None = None


async def register(http: httpx.AsyncClient) -> None:
    global device_token
    r = await http.post(
        f"{BASE}/device/register",
        json={
            "device_id": DEVICE_ID,
            "user_id": USER_ID,
            "device_type": DEVICE_TYPE,
            "device_name": FULL_NAME,
            "platform": PLATFORM,
            "capabilities": CAPABILITIES,
        },
    )
    r.raise_for_status()
    body = r.json()
    device_token = body.get("device_token")
    if not device_token:
        raise RuntimeError("register response missing device_token")
    print(f"[register] 成功 device={DEVICE_ID} user={USER_ID}")


async def heartbeat(http: httpx.AsyncClient) -> None:
    assert device_token
    r = await http.post(
        f"{BASE}/device/heartbeat",
        json={"device_id": DEVICE_ID, "device_token": device_token},
    )
    r.raise_for_status()
    print("[heartbeat] 已更新在线状态")


async def report_result(
    http: httpx.AsyncClient,
    command_id: str,
    status: str,
    *,
    result=None,
    error=None,
) -> None:
    assert device_token
    body: dict = {
        "command_id": command_id,
        "device_id": DEVICE_ID,
        "device_token": device_token,
        "status": status,
    }
    if result is not None:
        body["result"] = result
    if error is not None:
        body["error"] = error
    r = await http.post(f"{BASE}/device/command_result", json=body)
    r.raise_for_status()
    print(f"[result] 已上报 command_id={command_id} status={status}")


async def mark_running(http: httpx.AsyncClient, command_id: str) -> None:
    assert device_token
    r = await http.post(
        f"{BASE}/device/commands/{command_id}/mark_running",
        json={"device_id": DEVICE_ID, "device_token": device_token},
    )
    r.raise_for_status()
    print(f"[running] command_id={command_id}")


async def claim_next(http: httpx.AsyncClient) -> dict | None:
    assert device_token
    r = await http.post(
        f"{BASE}/device/commands/claim_next",
        json={"device_id": DEVICE_ID, "device_token": device_token},
    )
    r.raise_for_status()
    body = r.json()
    cmd = body.get("command")
    if cmd:
        print(f"[claimed] command_id={cmd.get('command_id')} action={cmd.get('command')}")
    return cmd if isinstance(cmd, dict) else None


async def execute_command(http: httpx.AsyncClient, cmd: dict) -> None:
    command_id = cmd["command_id"]
    action = cmd.get("command") or cmd.get("action")
    payload = cmd.get("payload") or {}

    result = None
    try:
        if action == "ping":
            print("[exec] pong")
            result = {"pong": True}
        elif action == "show_notification":
            print(f"[exec] NOTIFICATION: {payload.get('text', '')}")
        elif action == "open_url":
            url = payload.get("url", "")
            if not isinstance(url, str) or not url.startswith(("http://", "https://")):
                raise ValueError(f"invalid url: {url}")
            print(f"[exec] WOULD OPEN: {url}")
            result = {"opened": url}
        elif action == "get_device_status":
            result = {
                "platform": platform.system(),
                "current_time": time.time(),
                "client_version": CLIENT_VERSION,
                "capabilities": CAPABILITIES,
            }
        else:
            raise ValueError(f"unknown action: {action}")

        await report_result(http, command_id, "succeeded", result=result)
        print(f"[done] command_id={command_id} 执行成功")
    except Exception as exc:
        await report_result(http, command_id, "failed", error=str(exc))
        print(f"[done] command_id={command_id} 执行失败: {exc}")


async def poll_once(http: httpx.AsyncClient) -> None:
    cmd = await claim_next(http)
    if not cmd:
        return
    await mark_running(http, cmd["command_id"])
    await execute_command(http, cmd)


async def main() -> None:
    async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as http:
        print("正在注册设备…")
        await register(http)

        print(f"模拟客户端运行中。device={DEVICE_ID} user={USER_ID}")
        print(f"API: {BASE} 平台: {PLATFORM} 能力: {CAPABILITIES}")
        print("通过 claim_next 领取指令；Ctrl+C 退出。\n")

        loop = asyncio.get_event_loop()
        last_heartbeat = 0.0

        while True:
            now = loop.time()

            if now - last_heartbeat >= 10.0:
                try:
                    await heartbeat(http)
                except Exception as exc:
                    print(f"[heartbeat] 错误: {exc}")
                last_heartbeat = now

            try:
                await poll_once(http)
            except Exception as exc:
                print(f"[poll] 错误: {exc}")

            await asyncio.sleep(3)


def run_sync() -> None:
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n模拟客户端已停止。")
        sys.exit(0)
