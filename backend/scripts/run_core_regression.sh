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
  tests/test_telegram_route_helpers.py \
  tests/test_telegram_command_mapping.py \
  tests/test_agent_loop.py \
  tests/test_agent_executor.py \
  tests/test_planner_llm.py \
  tests/test_slot_schema.py \
  tests/test_tool_runner.py \
  tests/test_agent_task_decomposition.py \
  tests/test_operational_acceptance.py \
  tests/test_registry_extensibility.py \
  tests/test_operational_acceptance_e2e_mock.py
