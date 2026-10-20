"""Docker integration smoke; synthetic keys/data, bounded waits, no production secrets."""

import argparse
import hashlib
import json
import secrets
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from uuid import uuid4


def docker(*arguments):
    return subprocess.run(["docker", *arguments], check=True, capture_output=True, text=True).stdout.strip()


def request(base, path, *, method="GET", token=None, body=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    message = urllib.request.Request(base + path, headers=headers, method=method,
                                     data=json.dumps(body).encode() if body is not None else None)
    try:
        with urllib.request.urlopen(message, timeout=10) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as error:
        return error.code, json.load(error)


def address(name):
    port = docker("port", name, "8000/tcp").splitlines()[0].rsplit(":", 1)[1]
    return "http://127.0.0.1:" + port


def wait_ready(name):
    deadline = time.monotonic() + 90
    base = address(name)
    while time.monotonic() < deadline:
        try:
            status, data = request(base, "/health")
            if status == 200 and data["status"] == "healthy":
                return base
        except (OSError, ValueError):
            pass
        time.sleep(.5)
    raise RuntimeError("Container did not become ready")


def run(image):
    identifier = "companion-ci-" + uuid4().hex
    volume = identifier + "-data"
    key = secrets.token_urlsafe(32)
    user = "ci_user"
    container_created = volume_created = False
    with tempfile.TemporaryDirectory(prefix="companion-container-") as folder:
        config = Path(folder) / "access.json"
        config.write_text(json.dumps({"access_keys": [{"user_id": user, "role": "user",
                          "sha256": hashlib.sha256(key.encode()).hexdigest()}]}), encoding="utf-8")
        try:
            docker("volume", "create", volume)
            volume_created = True
            docker("run", "--rm", "--network", "none", "--user", "0:0",
                   "-v", str(config.resolve()) + ":/seed/access.json:ro", "-v", volume + ":/data",
                   image, "python", "-m", "shared_runtime.container_setup")
            docker("run", "--detach", "--name", identifier, "--read-only", "--cap-drop", "ALL",
                   "--security-opt", "no-new-privileges:true", "--tmpfs", "/tmp:size=128m,mode=1777",
                   "-v", volume + ":/data", "-p", "127.0.0.1::8000",
                   "-e", "COMPANION_ACCESS_CONFIG_FILE=/data/access.json", image)
            container_created = True
            base = wait_ready(identifier)
            assert request(base, "/memory/user/ci_user/list")[0] == 401
            status, login = request(base, "/access/login", method="POST", body={"access_key": key})
            assert status == 200
            token = login["session_token"]
            assert request(base, "/memory/store", method="POST", token=token, body={
                "user_id": user, "content": "synthetic restart receipt", "embedding": [0.] * 1024,
            })[0] == 200
            docker("restart", identifier)
            base = wait_ready(identifier)
            assert request(base, "/memory/user/ci_user/list", token=token)[0] == 401
            status, login = request(base, "/access/login", method="POST", body={"access_key": key})
            assert status == 200
            token = login["session_token"]
            status, exported = request(base, "/privacy/user/ci_user/export", token=token)
            assert status == 200 and "synthetic restart receipt" in json.dumps(exported)
            status, erased = request(base, "/privacy/user/ci_user/erase", method="POST", token=token,
                                     body={"confirmation": "删除我的全部数据"})
            assert status == 200 and erased["status"] == "completed"
            status, exported = request(base, "/privacy/user/ci_user/export", token=token)
            assert status == 200 and not exported["data"]["memories"]
            print("Container smoke passed: readiness, authentication, restart, persistence and erasure.")
        finally:
            if container_created:
                docker("rm", "--force", identifier)
            if volume_created:
                docker("volume", "rm", volume)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", default="companion-ai:local")
    run(parser.parse_args().image)
