from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.skill_contracts import validate_all_contracts


def main() -> int:
    total, failures = validate_all_contracts()
    print(f"[skill-contracts] total={total}")
    if not failures:
        print("[skill-contracts] PASS")
        return 0

    print("[skill-contracts] FAIL")
    for file_path, errors in failures.items():
        print(f"- {file_path}")
        for error in errors:
            print(f"  - {error}")

    print(json.dumps({"total": total, "failures": failures}, ensure_ascii=False, indent=2))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
