#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ -x ".venv/bin/python" ]]; then
  PYTHON_BIN=".venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="python3"
else
  echo "python3 (or .venv/bin/python) is required" >&2
  exit 1
fi

"$PYTHON_BIN" -m pytest -q \
  tests/test_api_keys_route.py \
  tests/test_policies_route.py \
  tests/test_mcp_routes.py \
  tests/test_tool_calls_route.py \
  tests/test_audit_route.py \
  tests/test_tenant_isolation_route.py
