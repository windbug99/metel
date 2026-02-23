# Stage 6 Run Commands

이 문서는 Staging/Production 전환 시 그대로 실행할 수 있는 명령 모음입니다.

## 1) Staging 사전 점검

```bash
cd backend
. .venv/bin/activate
python scripts/check_skill_v2_rollout_prereqs.py --check-dns
```

예상 결과:
- Supabase/환경변수/preflight 체크 통과

## 2) Shadow 모드(0%)로 운영 시작

Staging 환경변수:
- `SKILL_ROUTER_V2_ENABLED=true`
- `SKILL_RUNNER_V2_ENABLED=true`
- `SKILL_ROUTER_V2_LLM_ENABLED=true`
- `SKILL_V2_SHADOW_MODE=true`
- `SKILL_V2_TRAFFIC_PERCENT=0`

## 3) Shadow 지표 수집/판정 (3일)

```bash
cd backend
DAYS=3 ./scripts/run_skill_v2_rollout_gate.sh
```

출력/리포트:
- `docs/reports/skill_v2_rollout_latest.json`

PASS 기준:
- `shadow_count >= min_sample`
- `shadow_ok_rate >= 0.85`

## 4) Canary 10% 승격 판단

```bash
cd backend
DAYS=3 CURRENT_PERCENT=0 ./scripts/run_skill_v2_rollout_cycle.sh
```

의사결정 결과:
- `docs/reports/skill_v2_rollout_decision_latest.json`

`.env` 자동 반영까지 하려면:

```bash
cd backend
DAYS=3 CURRENT_PERCENT=0 APPLY_DECISION=true ENV_FILE=.env ./scripts/run_skill_v2_rollout_cycle.sh
```

## 5) Canary 30% / 100% 승격

10% -> 30%:

```bash
cd backend
DAYS=3 CURRENT_PERCENT=10 ./scripts/run_skill_v2_rollout_cycle.sh
```

30% -> 100%:

```bash
cd backend
DAYS=3 CURRENT_PERCENT=30 ./scripts/run_skill_v2_rollout_cycle.sh
```

각 단계 PASS 기준:
- `v2_success_rate >= 0.85`
- `v2_error_rate <= 0.15`
- `v2_latency_p95_ms <= 12000`

## 6) 전면 전환 후

환경변수:
- `SKILL_V2_SHADOW_MODE=false`
- `SKILL_V2_TRAFFIC_PERCENT=100`

후속:
- V1 제거는 별도 PR에서 수행

## 7) 빠른 점검용 명령

원커맨드 점검(preflight + gate + decision dry-run):

```bash
cd backend
DAYS=3 CURRENT_PERCENT=0 ./scripts/stage6_quickcheck.sh
```

기본 출력 파일:
- `docs/reports/skill_v2_rollout_latest.json`
- `docs/reports/skill_v2_rollout_decision_latest.json`

## 8) Telegram E2E 자동 실행 + 자동 채점

로컬/스테이징에서 텔레그램으로 테스트 문장을 자동 발송하고 `command_logs` 기준으로 PASS/FAIL 리포트를 생성:

```bash
cd backend
. .venv/bin/activate
python scripts/run_stage6_telegram_e2e.py --chat-id <TELEGRAM_CHAT_ID> --reset-pending --reset-between-chains
```

옵션:
- `--dry-run`: 문장 목록만 출력
- `--poll-timeout-sec 60`: 각 문장 결과 대기시간 조정
- `--output-json ../docs/reports/stage6_telegram_e2e_latest.json`: 리포트 경로 지정

출력:
- 기본 리포트: `docs/reports/stage6_telegram_e2e_latest.json`

리포트만 다시 계산:

```bash
cd backend
. .venv/bin/activate
python scripts/eval_skill_v2_rollout.py \
  --days 3 \
  --limit 500 \
  --min-sample 30 \
  --target-v2-success 0.85 \
  --max-v2-error-rate 0.15 \
  --max-v2-p95-latency-ms 12000 \
  --output-json ../docs/reports/skill_v2_rollout_latest.json
```

결정 JSON만 재생성:

```bash
cd backend
. .venv/bin/activate
python scripts/decide_skill_v2_rollout.py \
  --report-json ../docs/reports/skill_v2_rollout_latest.json \
  --current-percent 10 \
  --require-shadow-ok-for-promote \
  > ../docs/reports/skill_v2_rollout_decision_latest.json
```
