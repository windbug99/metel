#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


def _read_line(stream) -> dict[str, Any]:
    line = stream.readline()
    if not line:
        raise RuntimeError("bridge_no_output")
    try:
        payload = json.loads(line)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"bridge_invalid_json:{line}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("bridge_non_object_response")
    return payload


def main() -> int:
    base_url = (os.getenv("API_BASE_URL") or "").strip()
    api_key = (os.getenv("API_KEY") or "").strip()
    if not base_url or not api_key:
        print("ERROR: API_BASE_URL and API_KEY are required", file=sys.stderr)
        return 2

    bridge = Path(__file__).resolve().parent / "mcp_stdio_bridge.py"
    env = dict(os.environ)
    env.setdefault("PYTHONUNBUFFERED", "1")

    proc = subprocess.Popen(
        [sys.executable, str(bridge)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )

    try:
        assert proc.stdin is not None
        assert proc.stdout is not None

        initialize = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2024-11-05"}}
        proc.stdin.write(json.dumps(initialize) + "\n")
        proc.stdin.flush()
        init_resp = _read_line(proc.stdout)
        if "error" in init_resp:
            print(f"FAIL initialize: {json.dumps(init_resp, ensure_ascii=False)}")
            return 1

        list_tools = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
        proc.stdin.write(json.dumps(list_tools) + "\n")
        proc.stdin.flush()
        list_resp = _read_line(proc.stdout)
        if "error" in list_resp:
            print(f"FAIL tools/list: {json.dumps(list_resp, ensure_ascii=False)}")
            return 1

        tools = (((list_resp.get("result") or {}).get("tools")) or [])
        if not isinstance(tools, list):
            print(f"FAIL tools/list invalid shape: {json.dumps(list_resp, ensure_ascii=False)}")
            return 1

        print(f"OK tools_count={len(tools)}")
        if not tools:
            print("WARN tools list is empty. Check OAuth connection and API key allowed_tools.")
        else:
            names = [str(item.get("name")) for item in tools if isinstance(item, dict)]
            print("tools:", ", ".join(names))
        return 0
    finally:
        if proc.stdin:
            proc.stdin.close()
        proc.terminate()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=2)


if __name__ == "__main__":
    raise SystemExit(main())
