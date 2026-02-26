#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPORT_DIR="${ROOT_DIR}/../docs/reports"
ARCHIVE_ROOT="${REPORT_DIR}/archive/skill_llm_transform"
TS="$(date -u +%Y%m%d_%H%M%SZ)"
ARCHIVE_DIR="${ARCHIVE_ROOT}/${TS}"

RUN_ROLLOUT="${RUN_ROLLOUT:-true}"
RUN_SLO="${RUN_SLO:-true}"
SYNC_MD="${SYNC_MD:-true}"

DAYS="${DAYS:-3}"
LIMIT="${LIMIT:-200}"
MIN_SAMPLE="${MIN_SAMPLE:-30}"
CURRENT_PERCENT="${CURRENT_PERCENT:-0}"

STAGE6_CORE_PASS="${STAGE6_CORE_PASS:-true}"
N_TO_N_E2E_PASS="${N_TO_N_E2E_PASS:-true}"
ZERO_MATCH_E2E_PASS="${ZERO_MATCH_E2E_PASS:-true}"

mkdir -p "${REPORT_DIR}" "${ARCHIVE_DIR}"

cd "${ROOT_DIR}"
if [[ -f ".venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

if [[ "${RUN_ROLLOUT}" == "true" ]]; then
  echo "[dod-cycle] running rollout cycle"
  DAYS="${DAYS}" LIMIT="${LIMIT}" MIN_SAMPLE="${MIN_SAMPLE}" CURRENT_PERCENT="${CURRENT_PERCENT}" \
    APPLY_DECISION=false ./scripts/run_skill_llm_transform_rollout_cycle.sh
fi

if [[ "${RUN_SLO}" == "true" ]]; then
  echo "[dod-cycle] running SLO guard"
  DAYS="${DAYS}" LIMIT="${LIMIT}" MIN_SAMPLE="${MIN_SAMPLE}" \
    ./scripts/run_skill_llm_transform_slo_guard.sh || true
fi

echo "[dod-cycle] evaluating DoD"
DOD_ARGS=(
  --rollout-report "${REPORT_DIR}/skill_llm_transform_rollout_latest.json"
  --slo-report "${REPORT_DIR}/skill_llm_transform_slo_latest.json"
  --output-json "${REPORT_DIR}/skill_llm_transform_dod_latest.json"
)
if [[ "${STAGE6_CORE_PASS}" == "true" ]]; then
  DOD_ARGS+=(--stage6-core-pass)
fi
if [[ "${N_TO_N_E2E_PASS}" == "true" ]]; then
  DOD_ARGS+=(--n_to_n_e2e_pass)
fi
if [[ "${ZERO_MATCH_E2E_PASS}" == "true" ]]; then
  DOD_ARGS+=(--zero_match_e2e_pass)
fi
python scripts/eval_skill_llm_transform_dod.py "${DOD_ARGS[@]}"

if [[ "${SYNC_MD}" == "true" ]]; then
  echo "[dod-cycle] syncing markdown DoD checkboxes"
  python scripts/update_skill_llm_transform_dod_md.py \
    --dod-json "${REPORT_DIR}/skill_llm_transform_dod_latest.json" \
    --plan-md "${ROOT_DIR}/../docs/work-20260226-skill-llm-transform-pipeline-plan.md"
fi

echo "[dod-cycle] archiving reports to ${ARCHIVE_DIR}"
for file in \
  skill_llm_transform_rollout_latest.json \
  skill_llm_transform_rollout_decision_latest.json \
  skill_llm_transform_slo_latest.json \
  skill_llm_transform_slo_latest.md \
  skill_llm_transform_dod_latest.json
do
  if [[ -f "${REPORT_DIR}/${file}" ]]; then
    cp "${REPORT_DIR}/${file}" "${ARCHIVE_DIR}/${file}"
  fi
done

python - <<'PY'
import json
from datetime import datetime, timezone
from pathlib import Path

root = Path("../docs/reports")
dod_path = root / "skill_llm_transform_dod_latest.json"
hist_path = root / "skill_llm_transform_dod_history.jsonl"

if not dod_path.exists():
    raise SystemExit(0)

data = json.loads(dod_path.read_text(encoding="utf-8"))
record = {
    "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    "metrics": data.get("metrics", {}),
    "checklist": data.get("checklist", {}),
}
with hist_path.open("a", encoding="utf-8") as fp:
    fp.write(json.dumps(record, ensure_ascii=False) + "\n")
print("[dod-cycle] appended history:", hist_path)
PY

echo "[dod-cycle] done"
echo "[dod-cycle] latest DoD: ${REPORT_DIR}/skill_llm_transform_dod_latest.json"
echo "[dod-cycle] history: ${REPORT_DIR}/skill_llm_transform_dod_history.jsonl"
echo "[dod-cycle] archive dir: ${ARCHIVE_DIR}"
