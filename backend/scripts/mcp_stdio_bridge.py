#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from urllib import error as urlerror
from urllib import request as urlrequest
from typing import Any

PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "metel-http-bridge"
SERVER_VERSION = "0.1.0"


class BridgeConfigError(RuntimeError):
    pass


def _load_env() -> tuple[str, str]:
    base_url = (os.getenv("API_BASE_URL") or "").strip().rstrip("/")
    api_key = (os.getenv("API_KEY") or "").strip()
    if not base_url:
        raise BridgeConfigError("API_BASE_URL is required")
    if not api_key:
        raise BridgeConfigError("API_KEY is required")
    return base_url, api_key


def _write_json(payload: dict[str, Any]) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
    sys.stdout.buffer.write(header)
    sys.stdout.buffer.write(body)
    sys.stdout.buffer.flush()


def _read_json() -> dict[str, Any] | None:
    headers: dict[str, str] = {}
    while True:
        line = sys.stdin.buffer.readline()
        if not line:
            return None
        # Header terminator.
        if line in (b"\r\n", b"\n"):
            break
        text = line.decode("utf-8", errors="replace").strip()
        if ":" not in text:
            continue
        key, value = text.split(":", 1)
        headers[key.strip().lower()] = value.strip()

    length_text = headers.get("content-length")
    if not length_text:
        return None
    length = int(length_text)
    payload = sys.stdin.buffer.read(length)
    if not payload:
        return None
    parsed = json.loads(payload.decode("utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError("invalid_request_body")
    return parsed


def _error_response(req_id: Any, code: int, message: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
    error: dict[str, Any] = {"code": code, "message": message}
    if data:
        error["data"] = data
    return {"jsonrpc": "2.0", "id": req_id, "error": error}


def _ok_response(req_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _post_jsonrpc(*, base_url: str, api_key: str, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
    url = f"{base_url}{endpoint}"
    body = json.dumps(payload).encode("utf-8")
    req = urlrequest.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    with urlrequest.urlopen(req, timeout=30) as resp:
        raw = resp.read()
    parsed = json.loads(raw.decode("utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError("upstream_non_object_response")
    return parsed


def _handle_initialize(req_id: Any) -> dict[str, Any]:
    return _ok_response(
        req_id,
        {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
        },
    )


def _handle_tools_list(*, req_id: Any, base_url: str, api_key: str) -> dict[str, Any]:
    upstream = _post_jsonrpc(
        base_url=base_url,
        api_key=api_key,
        endpoint="/mcp/list_tools",
        payload={"jsonrpc": "2.0", "id": "bridge-list-tools", "method": "list_tools"},
    )
    if "error" in upstream:
        error = upstream["error"]
        return _error_response(
            req_id,
            int(error.get("code", -32000)),
            str(error.get("message", "upstream_error")),
            error.get("data"),
        )

    raw_tools = (((upstream.get("result") or {}).get("tools")) or [])
    tools: list[dict[str, Any]] = []
    for item in raw_tools:
        if not isinstance(item, dict):
            continue
        tools.append(
            {
                "name": item.get("name"),
                "description": item.get("description", ""),
                "inputSchema": item.get("input_schema", {"type": "object", "properties": {}}),
            }
        )
    return _ok_response(req_id, {"tools": tools})


def _handle_tools_call(*, req_id: Any, params: dict[str, Any], base_url: str, api_key: str) -> dict[str, Any]:
    tool_name = str(params.get("name") or "").strip()
    arguments = params.get("arguments") if isinstance(params.get("arguments"), dict) else {}
    if not tool_name:
        return _error_response(req_id, -32602, "invalid_params", {"reason": "name is required"})

    upstream = _post_jsonrpc(
        base_url=base_url,
        api_key=api_key,
        endpoint="/mcp/call_tool",
        payload={
            "jsonrpc": "2.0",
            "id": "bridge-call-tool",
            "method": "call_tool",
            "params": {"name": tool_name, "arguments": arguments},
        },
    )

    if "error" in upstream:
        error = upstream["error"]
        text = json.dumps({"error": error}, ensure_ascii=False)
        return _ok_response(req_id, {"content": [{"type": "text", "text": text}], "isError": True})

    result = upstream.get("result")
    text = json.dumps({"result": result}, ensure_ascii=False)
    return _ok_response(
        req_id,
        {
            "content": [{"type": "text", "text": text}],
            "structuredContent": result if isinstance(result, dict) else {"value": result},
        },
    )


def _dispatch(request: dict[str, Any], *, base_url: str, api_key: str) -> dict[str, Any] | None:
    req_id = request.get("id")
    method = request.get("method")
    params = request.get("params") if isinstance(request.get("params"), dict) else {}

    # Notifications have no id and must not receive a response.
    if req_id is None:
        return None

    if method == "initialize":
        return _handle_initialize(req_id)
    if method == "notifications/initialized":
        return None
    if method == "ping":
        return _ok_response(req_id, {})
    if method == "tools/list":
        return _handle_tools_list(req_id=req_id, base_url=base_url, api_key=api_key)
    if method == "tools/call":
        return _handle_tools_call(req_id=req_id, params=params, base_url=base_url, api_key=api_key)
    return _error_response(req_id, -32601, f"method_not_found: {method}")


def main() -> int:
    try:
        base_url, api_key = _load_env()
    except BridgeConfigError as exc:
        print(f"[mcp-bridge] config_error: {exc}", file=sys.stderr)
        return 2

    while True:
        request: dict[str, Any] | None = None
        try:
            parsed = _read_json()
            if parsed is None:
                break
            if not isinstance(parsed, dict):
                _write_json(_error_response(None, -32600, "invalid_request_body"))
                continue
            request = parsed
            response = _dispatch(request, base_url=base_url, api_key=api_key)
            if response is not None:
                _write_json(response)
        except urlerror.HTTPError as exc:
            status = exc.code
            payload = _error_response(
                request.get("id") if isinstance(request, dict) else None,
                -32000,
                "upstream_http_error",
                {"status_code": status},
            )
            _write_json(payload)
        except urlerror.URLError as exc:
            payload = _error_response(
                request.get("id") if isinstance(request, dict) else None,
                -32002,
                "upstream_network_error",
                {"detail": str(exc.reason)},
            )
            _write_json(payload)
        except Exception as exc:  # pragma: no cover
            payload = _error_response(
                request.get("id") if isinstance(request, dict) else None,
                -32001,
                "bridge_internal_error",
                {"detail": str(exc)},
            )
            _write_json(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
