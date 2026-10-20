"""Create/rotate a host access key without printing credentials or storing plaintext in config."""

import argparse
import hashlib
import json
import os
import secrets
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shared_runtime.access import AccessConfig, AccessKey  # noqa: E402


def _private(path):
    if os.name == "nt":
        identity = os.environ.get("USERDOMAIN", "") + "\\" + os.environ["USERNAME"]
        subprocess.run(
            ["icacls", str(path), "/inheritance:r", "/grant:r", identity + ":(F)"], check=True, capture_output=True
        )
    else:
        path.chmod(0o600)


def generate_key(*, config: Path, output: Path, user_id: str, role="user"):
    if config.is_symlink():
        raise ValueError("访问配置不能是符号链接。")
    config, output = config.resolve(), output.absolute()
    if output.exists() or output.is_symlink() or config == output:
        raise ValueError("凭据输出文件已存在，请指定一个新的文件名。")
    key = secrets.token_urlsafe(32)
    entry = AccessKey(user_id=user_id, role=role, sha256=hashlib.sha256(key.encode()).hexdigest())
    entries = AccessConfig.model_validate_json(config.read_bytes()).access_keys if config.exists() else []
    updated = AccessConfig(access_keys=[old for old in entries if old.user_id != user_id] + [entry])
    temporary = config.with_name(config.name + "." + secrets.token_hex(8) + ".tmp")
    created = False
    try:
        # Restrict access while still empty, before either plaintext or hashes are written.
        with output.open("x", encoding="utf-8") as target:
            created = True
            _private(output)
            json.dump({"user_id": user_id, "access_key": key}, target, ensure_ascii=False)
        with temporary.open("x", encoding="utf-8") as target:
            _private(temporary)
            target.write(updated.model_dump_json(indent=2))
        os.replace(temporary, config)
    except BaseException:
        if created:
            output.unlink(missing_ok=True)
        temporary.unlink(missing_ok=True)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user-id", required=True)
    parser.add_argument("--role", choices=("user", "admin"), default="user")
    parser.add_argument(
        "--config", type=Path, default=Path(__file__).resolve().parents[1] / "companion_access_config.json"
    )
    parser.add_argument("--output", type=Path, required=True, help="New private credential file; never printed")
    args = parser.parse_args()
    try:
        generate_key(config=args.config, output=args.output, user_id=args.user_id, role=args.role)
    except Exception:
        parser.exit(1, "保存失败，请检查用户编号、配置格式、文件权限和输出文件是否已存在。\n")
    print("访问配置已保存。请从指定的私有凭据文件读取访问密钥。")


if __name__ == "__main__":
    main()
