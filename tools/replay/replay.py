#!/usr/bin/env python
"""
Replay stored Pub/Sub push payloads to the receiver endpoint for testing.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import httpx


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay Pub/Sub notifications")
    parser.add_argument("--endpoint", required=True, help="Receiver push endpoint URL")
    parser.add_argument("--payload", required=True, help="Path to JSON payload file")
    args = parser.parse_args()

    payload = json.loads(Path(args.payload).read_text(encoding="utf-8"))

    with httpx.Client(timeout=10) as client:
        resp = client.post(args.endpoint, json=payload)
        resp.raise_for_status()
        print(f"Replay successful: {resp.status_code}")


if __name__ == "__main__":
    main()


