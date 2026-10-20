"""Validate/copy hashed access config into an application-owned Docker volume."""

import argparse
import os
from pathlib import Path

from shared_runtime.access import AccessConfig


def initialize(source: Path, data: Path, uid=10001, gid=10001):
    config = AccessConfig.model_validate_json(source.read_bytes())
    data.mkdir(parents=True, exist_ok=True)
    for folder in (data, data / "config", data / "voice"):
        folder.mkdir(exist_ok=True)
        folder.chmod(0o700)
        if os.name != "nt":
            os.chown(folder, uid, gid)
    target = data / "access.json"
    temporary = data / "access.json.tmp"
    if temporary.is_symlink() or target.is_symlink():
        raise ValueError("Access configuration cannot be a symlink")
    with temporary.open("w", encoding="utf-8") as output:
        temporary.chmod(0o600)
        output.write(config.model_dump_json())
    if os.name != "nt":
        os.chown(temporary, uid, gid)
    temporary.replace(target)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path("/seed/access.json"))
    parser.add_argument("--data", type=Path, default=Path("/data"))
    args = parser.parse_args()
    initialize(args.source, args.data)


if __name__ == "__main__":
    main()
