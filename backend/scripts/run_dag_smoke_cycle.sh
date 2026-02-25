#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

ATTEMPTS="${ATTEMPTS:-8}"
SLEEP_SEC="${SLEEP_SEC:-15}"
MIN_SAMPLE="${MIN_SAMPLE:-1}"
LIMIT="${LIMIT:-1}"
SMOKE_LIMIT="${SMOKE_LIMIT:-20}"
STOP_ON_PASS="${STOP_ON_PASS:-1}"
AUTO_INJECT_WEBHOOK="${AUTO_INJECT_WEBHOOK:-0}"
WEBHOOK_URL="${WEBHOOK_URL:-http://127.0.0.1:8000/api/telegram/webhook}"
CHAT_ID="${CHAT_ID:-0}"
SMOKE_TEXT="${SMOKE_TEXT:-구글캘린더 오늘 회의를 notion 페이지로 만들고 linear 이슈로 등록해줘. linear 팀은 operate}"
SMOKE_TEXTS="${SMOKE_TEXTS:-}"
SMOKE_TEXTS_FILE="${SMOKE_TEXTS_FILE:-}"

declare -a _SMOKE_TEXT_POOL=()
if [[ -n "${SMOKE_TEXTS_FILE}" && -f "${SMOKE_TEXTS_FILE}" ]]; then
  while IFS= read -r line || [[ -n "${line}" ]]; do
    line_trimmed="$(echo "${line}" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
    [[ -z "${line_trimmed}" ]] && continue
    [[ "${line_trimmed}" == \#* ]] && continue
    _SMOKE_TEXT_POOL+=("${line_trimmed}")
  done < "${SMOKE_TEXTS_FILE}"
fi
if [[ ${#_SMOKE_TEXT_POOL[@]} -eq 0 && -n "${SMOKE_TEXTS}" ]]; then
  OLD_IFS="${IFS}"
  IFS='|'
  read -r -a _RAW_TEXTS <<< "${SMOKE_TEXTS}"
  IFS="${OLD_IFS}"
  _buffer=""
  for token in "${_RAW_TEXTS[@]}"; do
    if [[ "${token}" == "" ]]; then
      if [[ -n "${_buffer}" ]]; then
        _SMOKE_TEXT_POOL+=("${_buffer}")
      fi
      _buffer=""
      continue
    fi
    if [[ -z "${_buffer}" ]]; then
      _buffer="${token}"
    else
      _buffer="${_buffer}|${token}"
    fi
  done
  if [[ -n "${_buffer}" ]]; then
    _SMOKE_TEXT_POOL+=("${_buffer}")
  fi
fi
if [[ ${#_SMOKE_TEXT_POOL[@]} -eq 0 ]]; then
  _SMOKE_TEXT_POOL=("${SMOKE_TEXT}")
fi

echo "[dag-smoke-cycle] start"
echo "[dag-smoke-cycle] attempts=${ATTEMPTS} sleep_sec=${SLEEP_SEC}"
echo "[dag-smoke-cycle] stop_on_pass=${STOP_ON_PASS}"
if [[ "${AUTO_INJECT_WEBHOOK}" == "1" ]]; then
  echo "[dag-smoke-cycle] mode=auto_inject webhook_url=${WEBHOOK_URL}"
  echo "[dag-smoke-cycle] smoke_text_count=${#_SMOKE_TEXT_POOL[@]}"
else
  echo "[dag-smoke-cycle] hint: send Telegram request while this loop is running"
fi

cd "${ROOT_DIR}"
if [[ -f ".venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

SINCE_ISO="$(python - <<'PY'
from datetime import datetime, timezone
print(datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z"))
PY
)"
echo "[dag-smoke-cycle] since_iso=${SINCE_ISO}"
pass_count=0
fail_count=0

for ((i=1; i<=ATTEMPTS; i++)); do
  echo "[dag-smoke-cycle] attempt ${i}/${ATTEMPTS}"

  if [[ "${AUTO_INJECT_WEBHOOK}" == "1" ]]; then
    text_index=$(( (i - 1) % ${#_SMOKE_TEXT_POOL[@]} ))
    selected_text="${_SMOKE_TEXT_POOL[${text_index}]}"
    echo "[dag-smoke-cycle] inject_text_index=${text_index}"
    set +e
    PYTHONPATH=. python "${ROOT_DIR}/scripts/send_telegram_webhook_text.py" \
      --webhook-url "${WEBHOOK_URL}" \
      --chat-id "${CHAT_ID}" \
      --text "${selected_text}"
    inject_rc=$?
    set -e
    if [[ ${inject_rc} -ne 0 ]]; then
      echo "[dag-smoke-cycle] webhook inject failed (attempt ${i})"
    fi
    sleep 2
  fi

  set +e
  MIN_SAMPLE="${MIN_SAMPLE}" LIMIT="${LIMIT}" "${ROOT_DIR}/scripts/run_dag_quality_gate.sh"
  gate_rc=$?
  PYTHONPATH=. python "${ROOT_DIR}/scripts/check_dag_smoke_result.py" --limit "${SMOKE_LIMIT}" --since-iso "${SINCE_ISO}"
  smoke_rc=$?
  set -e

  if [[ ${gate_rc} -eq 0 && ${smoke_rc} -eq 0 ]]; then
    pass_count=$((pass_count + 1))
    echo "[dag-smoke-cycle] PASS (attempt ${i})"
    if [[ "${STOP_ON_PASS}" == "1" ]]; then
      exit 0
    fi
  else
    fail_count=$((fail_count + 1))
  fi

  if [[ ${i} -lt ${ATTEMPTS} ]]; then
    echo "[dag-smoke-cycle] not ready yet, sleeping ${SLEEP_SEC}s"
    sleep "${SLEEP_SEC}"
  fi
done

echo "[dag-smoke-cycle] finished attempts=${ATTEMPTS} pass=${pass_count} fail=${fail_count}"
if [[ ${fail_count} -eq 0 ]]; then
  echo "[dag-smoke-cycle] PASS"
  exit 0
fi
echo "[dag-smoke-cycle] FAIL"
exit 1
