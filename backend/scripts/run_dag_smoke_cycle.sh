#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

ATTEMPTS="${ATTEMPTS:-8}"
SLEEP_SEC="${SLEEP_SEC:-15}"
MIN_SAMPLE="${MIN_SAMPLE:-1}"
LIMIT="${LIMIT:-1}"
SMOKE_LIMIT="${SMOKE_LIMIT:-20}"

echo "[dag-smoke-cycle] start"
echo "[dag-smoke-cycle] attempts=${ATTEMPTS} sleep_sec=${SLEEP_SEC}"
echo "[dag-smoke-cycle] hint: send Telegram request while this loop is running"

cd "${ROOT_DIR}"
if [[ -f ".venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

for ((i=1; i<=ATTEMPTS; i++)); do
  echo "[dag-smoke-cycle] attempt ${i}/${ATTEMPTS}"

  set +e
  MIN_SAMPLE="${MIN_SAMPLE}" LIMIT="${LIMIT}" "${ROOT_DIR}/scripts/run_dag_quality_gate.sh"
  gate_rc=$?
  PYTHONPATH=. python "${ROOT_DIR}/scripts/check_dag_smoke_result.py" --limit "${SMOKE_LIMIT}"
  smoke_rc=$?
  set -e

  if [[ ${gate_rc} -eq 0 && ${smoke_rc} -eq 0 ]]; then
    echo "[dag-smoke-cycle] PASS"
    exit 0
  fi

  if [[ ${i} -lt ${ATTEMPTS} ]]; then
    echo "[dag-smoke-cycle] not ready yet, sleeping ${SLEEP_SEC}s"
    sleep "${SLEEP_SEC}"
  fi
done

echo "[dag-smoke-cycle] FAIL (attempts exhausted)"
exit 1
