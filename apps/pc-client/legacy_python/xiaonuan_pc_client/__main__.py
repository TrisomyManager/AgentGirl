"""python -m xiaonuan_pc_client"""

from __future__ import annotations

import argparse

from xiaonuan_pc_client.main import run_sync


def main() -> None:
    parser = argparse.ArgumentParser(
        description="PC simulator for Xiaonuan Device Operation Gateway (register, heartbeat, claim_next, command_result).",
    )
    parser.parse_args()
    run_sync()


if __name__ == "__main__":
    main()
