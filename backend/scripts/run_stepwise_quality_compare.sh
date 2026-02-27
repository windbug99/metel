#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPORT_DIR="${ROOT_DIR}/../docs/reports"
mkdir -p "${REPORT_DIR}"

LIMIT="${LIMIT:-500}"
DAYS="${DAYS:-7}"

echo "[stepwise-compare] running stepwise vs dag/legacy quality compare"
echo "[stepwise-compare] limit=${LIMIT} days=${DAYS}"

cd "${ROOT_DIR}"
if [[ -f ".venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

echo "[stepwise-compare] preflight: supabase connectivity"
PYTHONPATH=. python scripts/check_supabase_connectivity.py --timeout-sec 5

PYTHONPATH=. python scripts/eval_stepwise_vs_legacy_quality.py \
  --limit "${LIMIT}" \
  --days "${DAYS}" \
  --output "${REPORT_DIR}/stepwise_vs_legacy_quality_latest.md" \
  --output-json "${REPORT_DIR}/stepwise_vs_legacy_quality_latest.json"

echo "[stepwise-compare] PASS"
