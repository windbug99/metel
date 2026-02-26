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

## 2) Shadow 모드(0%)로 운영 시작 (과거 단계 기록)

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

## 6) 전면 전환 후 (현재 운영 기준)

환경변수:
- `SKILL_V2_SHADOW_MODE=false`
- `SKILL_V2_TRAFFIC_PERCENT=100`

후속:
- V1 제거는 별도 PR에서 수행
- 삭제 계열(Linear/Notion)은 정책상 비활성화되어 `delete_disabled`로 응답

## 7) 현재 운영 점검(권장)

운영 값:
- `SKILL_ROUTER_V2_ENABLED=true`
- `SKILL_RUNNER_V2_ENABLED=true`
- `SKILL_ROUTER_V2_LLM_ENABLED=true`
- `SKILL_V2_SHADOW_MODE=false`
- `SKILL_V2_TRAFFIC_PERCENT=100`

빠른 게이트 확인:

```bash
cd backend
DAYS=1 LIMIT=80 CURRENT_PERCENT=100 ./scripts/stage6_quickcheck.sh
```

## 8) 빠른 점검용 명령

원커맨드 점검(preflight + gate + decision dry-run):

```bash
cd backend
DAYS=3 CURRENT_PERCENT=0 ./scripts/stage6_quickcheck.sh
```

기본 출력 파일:
- `docs/reports/skill_v2_rollout_latest.json`
- `docs/reports/skill_v2_rollout_decision_latest.json`

## 9) Telegram E2E 자동 실행 + 자동 채점

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

## 10) Skill+LLM Transform 경로 점검 (신규)

환경변수:
- `SKILL_LLM_TRANSFORM_PIPELINE_ENABLED=true`
- `SKILL_LLM_TRANSFORM_PIPELINE_SHADOW_MODE=false`
- `SKILL_LLM_TRANSFORM_PIPELINE_TRAFFIC_PERCENT=100`

shadow-only 검증(기존 경로 응답 유지 + 신규 경로 병행 실행):
- `SKILL_LLM_TRANSFORM_PIPELINE_ENABLED=true`
- `SKILL_LLM_TRANSFORM_PIPELINE_SHADOW_MODE=true`
- `SKILL_LLM_TRANSFORM_PIPELINE_TRAFFIC_PERCENT=0`

권장 점검:

```bash
cd backend
. .venv/bin/activate
PYTHONPATH=. pytest -q \
  tests/test_transform_contracts.py \
  tests/test_pipeline_dag.py \
  tests/test_pipeline_dsl_schema.py \
  tests/test_pipeline_fixture_e2e.py::test_google_calendar_to_notion_minutes_fixture_e2e \
  tests/test_pipeline_fixture_e2e.py::test_google_calendar_to_linear_minutes_fixture_e2e \
  tests/test_agent_loop.py::test_run_agent_analysis_calendar_notion_minutes_uses_dag_template \
  tests/test_agent_loop.py::test_run_agent_analysis_calendar_notion_minutes_flag_off_uses_legacy_path
```

## 11) Skill+LLM Transform 점진 확대/롤백 자동화 (신규)

shadow-only 시작(기존 경로 응답 유지):
- `SKILL_LLM_TRANSFORM_PIPELINE_ENABLED=true`
- `SKILL_LLM_TRANSFORM_PIPELINE_SHADOW_MODE=true`
- `SKILL_LLM_TRANSFORM_PIPELINE_TRAFFIC_PERCENT=0`

게이트 + 결정(dry-run):

```bash
cd backend
DAYS=3 CURRENT_PERCENT=0 ./scripts/run_skill_llm_transform_rollout_cycle.sh
```

결정 자동 적용까지:

```bash
cd backend
DAYS=3 CURRENT_PERCENT=0 APPLY_DECISION=true ENV_FILE=.env ./scripts/run_skill_llm_transform_rollout_cycle.sh
```

10% -> 30%:

```bash
cd backend
DAYS=3 CURRENT_PERCENT=10 ./scripts/run_skill_llm_transform_rollout_cycle.sh
```

30% -> 100%:

```bash
cd backend
DAYS=3 CURRENT_PERCENT=30 ./scripts/run_skill_llm_transform_rollout_cycle.sh

# 배포 시각 이후 데이터만 평가 (권장)
SINCE_UTC=2026-02-26T12:13:45Z CURRENT_PERCENT=30 ./scripts/run_skill_llm_transform_rollout_cycle.sh
```

출력 파일:
- `docs/reports/skill_llm_transform_rollout_latest.json`
- `docs/reports/skill_llm_transform_rollout_decision_latest.json`

## 12) Skill+LLM Transform DoD SLO Guard (신규)

운영 지표 + 핵심 E2E 불변식(N->N, zero-match success) 자동 검증:

```bash
cd backend
DAYS=3 LIMIT=200 MIN_SAMPLE=30 ./scripts/run_skill_llm_transform_slo_guard.sh

# 배포 시각 이후 데이터만 평가 (권장)
SINCE_UTC=2026-02-26T12:13:45Z LIMIT=200 MIN_SAMPLE=30 ./scripts/run_skill_llm_transform_slo_guard.sh
```

추가 임계값(옵션):
- `MAX_TRANSFORM_ERROR_RATE=0.10`
- `MAX_VERIFY_FAIL_BEFORE_WRITE=0`
- `MIN_COMPOSED_PIPELINE_COUNT=10`

출력 파일:
- `docs/reports/skill_llm_transform_slo_latest.md`
- `docs/reports/skill_llm_transform_slo_latest.json`

## 13) Skill+LLM Transform DoD 자동 판정 (신규)

SLO/rollout 리포트 기반으로 DoD 체크리스트를 자동 산출:

```bash
cd backend
. .venv/bin/activate
python scripts/eval_skill_llm_transform_dod.py \
  --rollout-report ../docs/reports/skill_llm_transform_rollout_latest.json \
  --slo-report ../docs/reports/skill_llm_transform_slo_latest.json \
  --stage6-core-pass \
  --n_to_n_e2e_pass \
  --zero_match_e2e_pass \
  --output-json ../docs/reports/skill_llm_transform_dod_latest.json
```

출력 파일:
- `docs/reports/skill_llm_transform_dod_latest.json`

## 14) Skill+LLM Transform DoD 문서 체크박스 동기화 (신규)

자동 판정 JSON을 계획 문서 체크박스에 반영:

```bash
cd backend
. .venv/bin/activate
python scripts/update_skill_llm_transform_dod_md.py \
  --dod-json ../docs/reports/skill_llm_transform_dod_latest.json \
  --plan-md ../docs/work-20260226-skill-llm-transform-pipeline-plan.md
```

## 15) Skill+LLM Transform DoD 누적/재평가 사이클 (신규)

롤아웃 + SLO + DoD 평가 + 문서 동기화 + 스냅샷 아카이브를 1회 실행:

```bash
cd backend
DAYS=3 LIMIT=200 MIN_SAMPLE=30 CURRENT_PERCENT=100 \
STAGE6_CORE_PASS=true N_TO_N_E2E_PASS=true ZERO_MATCH_E2E_PASS=true \
./scripts/run_skill_llm_transform_dod_cycle.sh

# 배포 시각 이후 데이터만 평가 (권장)
SINCE_UTC=2026-02-26T12:13:45Z LIMIT=200 MIN_SAMPLE=30 CURRENT_PERCENT=30 \
STAGE6_CORE_PASS=true N_TO_N_E2E_PASS=true ZERO_MATCH_E2E_PASS=true \
./scripts/run_skill_llm_transform_dod_cycle.sh
```

생성/누적 파일:
- `docs/reports/skill_llm_transform_dod_latest.json`
- `docs/reports/skill_llm_transform_dod_history.jsonl`
- `docs/reports/archive/skill_llm_transform/<UTC_TIMESTAMP>/...`

주기 실행 예시(cron, UTC 1시간마다):

```bash
0 * * * * cd /Users/tomato/cursor/metel/backend && DAYS=3 LIMIT=200 MIN_SAMPLE=30 CURRENT_PERCENT=100 ./scripts/run_skill_llm_transform_dod_cycle.sh >> /tmp/skill_llm_transform_dod_cycle.log 2>&1
```

## 16) Skill+LLM Transform compile miss 원인 집계 (신규)

`rollout_*_miss` 요청의 컴파일 미매칭 원인/서비스 분포를 집계:

```bash
cd backend
. .venv/bin/activate
python scripts/eval_skill_llm_transform_compile_miss.py \
  --days 1 \
  --limit 500 \
  --top 10 \
  --output-json ../docs/reports/skill_llm_transform_compile_miss_latest.json
```

배포 시각 이후만 보고 싶으면:

```bash
python scripts/eval_skill_llm_transform_compile_miss.py \
  --since 2026-02-26T12:13:45Z \
  --limit 500 \
  --top 10 \
  --output-json ../docs/reports/skill_llm_transform_compile_miss_latest.json
```
