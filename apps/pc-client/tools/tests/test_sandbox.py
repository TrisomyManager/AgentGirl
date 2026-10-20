import json
import os
import queue
import secrets
import subprocess
import sys
import threading
from pathlib import Path
from unittest.mock import Mock

import httpx
import pytest

import policy
from policy import DEFAULT_CAPABILITIES, OPTIONAL_CAPABILITIES, ExecutionPolicy
from registry import get_registry
from handlers import browser, clipboard, filesystem, process, system  # noqa: F401


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    root = tmp_path / "workspace"
    root.mkdir()
    monkeypatch.setattr(
        policy,
        "_policy",
        ExecutionPolicy(DEFAULT_CAPABILITIES | OPTIONAL_CAPABILITIES, root),
    )
    return root


def test_default_policy_disables_sensitive_capabilities_even_if_caller_claims_approval():
    restricted = ExecutionPolicy()
    for name in [
        *OPTIONAL_CAPABILITIES,
        "launch_app",
        "remote_shell",
        "volume_control",
    ]:
        with pytest.raises(PermissionError):
            restricted.authorize(name, {}, approved=True)


@pytest.mark.parametrize(
    "url",
    [
        "file:///C:/secret.txt",
        "javascript:alert(1)",
        "http://localhost",
        "http://127.0.0.1",
        "http://2130706433",
        "http://0177.0.0.1",
        "http://0x7f000001",
        "https://user:pass@example.com",
        "https://example.com\\@127.0.0.1",
        "https://example.com\n",
        "http://[::1]",
    ],
)
def test_url_scope_rejects_local_credentials_and_ambiguous_forms(url):
    assert not policy.public_url(url)


def test_confirmation_paths_links_limits_and_create_only_writes(workspace, tmp_path):
    reg = get_registry()
    assert not reg.exec("write_file", {"path": "new.txt", "content": "hello"}).ok
    assert reg.exec(
        "write_file", {"path": "new.txt", "content": "你好"}, approved=True
    ).ok
    assert not reg.exec(
        "write_file", {"path": "new.txt", "content": "overwrite"}, approved=True
    ).ok
    assert (workspace / "new.txt").read_text("utf-8") == "你好"
    assert (
        reg.exec("read_file", {"path": "new.txt"}, approved=True).data["content"]
        == "你好"
    )
    outside = tmp_path / "outside.txt"
    outside.write_text("private outside marker", encoding="utf-8")
    sibling = tmp_path / "workspace-other"
    sibling.mkdir()
    (sibling / "secret.txt").write_text("outside", encoding="utf-8")
    for path in [
        "../outside.txt",
        str(outside),
        str(sibling / "secret.txt"),
        "new.txt:stream",
        "CON.txt",
        "COM¹.txt",
    ]:
        assert not reg.exec("read_file", {"path": path}, approved=True).ok
        assert not reg.exec(
            "write_file", {"path": path, "content": "changed"}, approved=True
        ).ok
    os.link(outside, workspace / "hard-link.txt")
    assert not reg.exec("read_file", {"path": "hard-link.txt"}, approved=True).ok
    assert not reg.exec(
        "write_file", {"path": "run.py", "content": "pass"}, approved=True
    ).ok
    assert not reg.exec(
        "write_file", {"path": "big.txt", "content": "x" * 50001}, approved=True
    ).ok
    (workspace / "large.txt").write_text("中" * 30000, encoding="utf-8")
    large = reg.exec("read_file", {"path": "large.txt"}, approved=True)
    assert (
        large.ok
        and large.data["truncated"]
        and len(large.data["content"].encode()) <= 50000
    )
    assert outside.read_text("utf-8") == "private outside marker"


def test_windows_junction_or_symbolic_link_cannot_escape_workspace(workspace, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "private.txt").write_text("outside")
    link = workspace / "linked"
    if sys.platform == "win32":
        import _winapi

        _winapi.CreateJunction(str(outside), str(link))
    else:
        link.symlink_to(outside, target_is_directory=True)
    try:
        assert (
            not get_registry()
            .exec("read_file", {"path": "linked/private.txt"}, approved=True)
            .ok
        )
        assert (
            not get_registry()
            .exec(
                "write_file", {"path": "linked/new.txt", "content": "x"}, approved=True
            )
            .ok
        )
    finally:
        if sys.platform == "win32":
            os.rmdir(link)  # Removes only this junction, never the destination.
        else:
            link.unlink()
    assert not (outside / "new.txt").exists()


def test_notification_and_clipboard_text_are_data_not_powershell_source(
    workspace, monkeypatch
):
    run = Mock(return_value=subprocess.CompletedProcess([], 0, stdout=""))
    monkeypatch.setattr(subprocess, "run", run)
    marker = '"; $(SYNTHETIC_COMMAND) `value` 中文'
    system._win_notify(marker, marker)
    args, kwargs = run.call_args
    assert marker not in args[0][-1]
    assert json.loads(kwargs["input"])["title"] == marker
    clipboard._win_clipboard_write(marker)
    args, kwargs = run.call_args
    assert marker not in args[0][-1] and json.loads(kwargs["input"])["text"] == marker


def test_private_real_server_requires_token_origin_and_explicit_approval(tmp_path):
    root = tmp_path / "scope"
    root.mkdir()
    token = secrets.token_hex(32)
    env = {
        key: value
        for key, value in os.environ.items()
        if key.upper() in {"PATH", "SYSTEMROOT", "TEMP", "TMP", "WINDIR", "USERPROFILE", "HOMEDRIVE", "HOMEPATH", "HOME"}
    }
    env.update(
        XIAONUAN_TOOL_TOKEN=token,
        XIAONUAN_SANDBOX_ROOT=str(root),
        XIAONUAN_TOOL_CAPABILITIES="list_files,read_file,write_file",
        PYTHONUTF8="1",
    )
    child = subprocess.Popen(
        [sys.executable, str(Path(__file__).resolve().parents[1] / "server.py")],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    ready = queue.Queue()
    reader = threading.Thread(
        target=lambda: ready.put(child.stdout.readline()), daemon=True
    )
    reader.start()
    try:
        port = json.loads(ready.get(timeout=6))["port"]
        with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=5, trust_env=False) as client:
            assert client.get("/tools/list").status_code == 403
            client.headers["Authorization"] = "Bearer " + token
            assert (
                client.get(
                    "/tools/list", headers={"Origin": "https://untrusted.example"}
                ).status_code
                == 403
            )
            assert (
                client.get(
                    "/tools/list", headers={"Host": "untrusted.example"}
                ).status_code
                == 403
            )
            response = client.get("/tools/list")
            assert (
                response.status_code == 200
                and "access-control-allow-origin" not in response.headers
            )
            assert "remote_shell" not in {
                tool["name"] for tool in response.json()["tools"]
            }
            body = {
                "name": "write_file",
                "params": {
                    "path": "receipt.txt",
                    "content": "synthetic file roundtrip",
                },
            }
            assert client.post("/tools/exec", json=body).json()["ok"] is False
            assert not (root / "receipt.txt").exists()
            assert client.post("/tools/exec", json={**body, "approved": True}).json()[
                "ok"
            ]
            result = client.post(
                "/tools/exec",
                json={
                    "name": "read_file",
                    "params": {"path": "receipt.txt"},
                    "approved": True,
                },
            )
            assert result.json()["data"]["content"] == "synthetic file roundtrip"
            assert not client.post(
                "/tools/exec",
                json={"name": "remote_shell", "params": {}, "approved": True},
            ).json()["ok"]
            assert (
                client.post(
                    "/tools/exec",
                    content='{"name":"read_file","params":NaN}',
                    headers={"Content-Type": "application/json"},
                ).status_code
                == 400
            )
    finally:
        child.terminate()
        child.wait(timeout=5)
        reader.join(timeout=1)
        child.stdout.close()
