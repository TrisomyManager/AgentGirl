#!/usr/bin/env python3
"""CLI wrapper; use `python -m xiaonuan_pc_client` for the same behavior."""

from __future__ import annotations

import argparse

from xiaonuan_pc_client.main import run_sync


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="PC simulator for Xiaonuan Device Operation Gateway (register, heartbeat, claim_next, command_result).",
    )
    parser.parse_args()
    run_sync()
