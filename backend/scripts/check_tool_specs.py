from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.registry import ToolSpecValidationError, validate_registry_on_startup


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate and summarize tool specs.")
    parser.add_argument("--json", action="store_true", help="Print JSON output")
    args = parser.parse_args()

    try:
        summary = validate_registry_on_startup()
    except ToolSpecValidationError as exc:
        if args.json:
            print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        else:
            print(f"[FAIL] tool spec validation error: {exc}")
        return 1

    if args.json:
        print(json.dumps({"ok": True, **summary}, ensure_ascii=False))
    else:
        print("[OK] tool specs validated")
        print(f"- services: {summary['service_count']}")
        print(f"- tools: {summary['tool_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
