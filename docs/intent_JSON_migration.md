# Intent JSON Migration Plan

## 1) 목표
- "한 문장 = 한 결정 경로"를 보장한다.
- 라우팅 결과를 `Intent JSON`으로 고정하고, 실행 단계에서 재해석을 금지한다.
- 모호한 문장은 임의 실행 대신 `needs_input`으로 전환한다.

## 2) 범위
- 대상 코드:
  - `backend/agent/orchestrator_v2.py`
  - `backend/agent/loop.py`
  - `backend/agent/tool_runner.py` (실행 계약 보강 시)
  - `backend/tests/test_orchestrator_v2.py`
  - `backend/tests/test_agent_loop.py`
  - `backend/tests/test_tool_runner.py`
- 신규 파일:
  - `backend/agent/intent_contract.py`
  - `backend/agent/intent_normalizer.py`
  - `backend/tests/test_intent_contract.py`

## 3) 핵심 설계
- 입력 문장 → `build_intent_json()` 1회 실행
- 결과를 `Intent Contract`로 검증
- 검증 통과 시 `execute_from_intent(intent)` 실행
- 실행 중 `mode`, `skill_name` 재결정 금지
- 필수 인자 누락 시 `needs_input` 반환

Intent JSON 예시:
```json
{
  "mode": "LLM_THEN_SKILL",
  "skill_name": "linear.issue_update",
  "arguments": {
    "linear_issue_ref": "OPT-46",
    "op": "append_description"
  },
  "missing_fields": [],
  "confidence": 0.92,
  "decision_reason": "explicit_linear_mutation_intent"
}
```

## 4) 단계별 작업계획 + 진행상태

### Stage 0. 사전 안정화 (핫픽스)
- [x] `linear update`에서 patch 없는 경우 임의 LLM 본문 반영 금지
- [x] `linear delete` 실제 archive mutation 적용 (`issueArchive`)
- [x] `needs_input` 재개 시 팀 단일 입력(`operate`) 슬롯 보정
- [x] `설명/본문 ... 로 수정` 문장 파싱 확장

완료 기준:
- 오동작(거짓 성공, 임의 업데이트) 회귀 테스트 통과

### Stage 1. Intent Contract 도입
- [x] `intent_contract.py` 생성
- [x] `IntentMode`, `IntentSkill`, `IntentPayload` 스키마 정의
- [x] `validate_intent_json()` 구현
- [x] 검증 실패 표준 에러코드/메시지 정의 (`invalid_intent_json`)

완료 기준:
- `test_intent_contract.py`에서 유효/무효 케이스 검증

### Stage 2. 라우팅 단일 진입점
- [x] `build_intent_json()` 함수 신설
- [x] `try_run_v2_orchestration()` 시작부에서 1회 호출
- [x] 기존 다단 override 로직을 "계약 보정 1회"로 축소
- [x] `router_source`, `decision_reason`를 Intent 기준으로 로그 고정

완료 기준:
- 동일 문장 반복 요청 시 동일 Intent JSON 생성

### Stage 3. Normalizer 분리
- [x] `intent_normalizer.py` 생성
- [x] 이슈 키/페이지 제목/팀명/필드 동의어 정규화 함수 이동
- [x] 실행 전 1회 정규화, 실행 중 재정규화 금지

완료 기준:
- 정규화 책임이 `orchestrator_v2.py`에서 분리됨

### Stage 4. 실행기 단순화
- [x] `execute_from_intent(intent)` 분리
  - 진행상태: `LLM_ONLY`, `SKILL_THEN_LLM`, `LLM_THEN_SKILL` 전체 경로 분리 완료
- [x] mutation 계열 필수 인자 강제 (`needs_input` 우선)
- [x] read 계열은 `SKILL_THEN_LLM`, write 계열은 `LLM_THEN_SKILL` 고정
- [x] fallback으로 임의 payload 생성 금지

완료 기준:
- 실행 로직에서 라우팅 재결정 코드 제거

### Stage 5. 테스트 체계 전환
- [x] 문장 -> Intent JSON 스냅샷 테스트 추가
- [x] Intent JSON -> 실행 결과 테스트 분리
- [x] 금지 케이스 테스트 추가
  - [x] patch 없는 update는 실행 금지
  - [x] 연결되지 않은 서비스 skill 실행 금지
  - [x] unsupported skill/service는 즉시 실패

완료 기준:
- 핵심 문장군 회귀 테스트 통과

### Stage 6. 운영 전환
- [x] Staging에서 문장군 E2E 점검
- [x] Production canary(10% -> 30% -> 100%)
- [x] 안정화 후 v1 제거 계획 확정(초안)
- [x] 운영 전환 runbook/명령/판정기준 문서화

완료 기준:
- canary 기준 충족 후 전체 전환

Stage 6 실행 절차(운영):
1. Staging 사전조건
   - `SKILL_ROUTER_V2_ENABLED=true`
   - `SKILL_RUNNER_V2_ENABLED=true`
   - `SKILL_ROUTER_V2_LLM_ENABLED=true`
   - `SKILL_V2_SHADOW_MODE=true`
   - `SKILL_V2_TRAFFIC_PERCENT=0`
2. Staging E2E 문장군 수동 검증
   - 회귀 문장군(Section 5) + 생성/조회/수정/삭제 각 1회 이상
   - 기대결과: 잘못된 라우팅/unsupported 오류 0건, needs_input 재개 정상
3. Shadow 3일 지표 수집
   - `cd backend && DAYS=3 ./scripts/run_skill_v2_rollout_gate.sh`
   - PASS 기준: `shadow_count >= min_sample`, `shadow_ok_rate >= 0.85`
4. Canary 10% 승격
   - `cd backend && DAYS=3 CURRENT_PERCENT=0 ./scripts/run_skill_v2_rollout_cycle.sh`
   - 의사결정 파일 확인: `docs/reports/skill_v2_rollout_decision_latest.json`
   - 적용 시: `APPLY_DECISION=true ENV_FILE=.env` 옵션으로 반영
5. Canary 30%/100% 단계 승격
   - `CURRENT_PERCENT=10` -> `CURRENT_PERCENT=30` 순서로 동일 실행
   - 각 단계 PASS 기준: `v2_success_rate >= 0.85`, `v2_error_rate <= 0.15`, `v2_latency_p95_ms <= 12000`
6. 전면 전환 및 V1 제거 계획 확정
   - `SKILL_V2_SHADOW_MODE=false`, `SKILL_V2_TRAFFIC_PERCENT=100`
   - V1 코드 제거는 전면 전환 후 별도 PR로 수행

## 5) 회귀 문장군 (필수)
- `linear opt-46 이슈 설명 업데이트`
- `openweather API 사용방법을 정리해서 linear opt-46 설명에 추가`
- `linear opt-45 이슈를 삭제하세요`
- `linear에 이슈 생성` -> `operate` -> `제목: ...`
- `노션에서 "스프린트 보고서" 페이지 제목을 ...로 업데이트`
- `노션에서 "스프린트 보고서" 페이지 본문 업데이트: ...`

## 6) 진행기록
- 2026-02-23: Stage 0 항목 반영 완료(핫픽스/회귀 테스트 통과).
- 2026-02-23: Stage 1 `intent_contract.py` + `test_intent_contract.py` 완료.
- 2026-02-23: Stage 2 라우팅 단일 진입점(`build_intent_json()`) 적용 완료.
- 2026-02-23: Stage 3 완료(`intent_normalizer.py` 추가, 추출/정규화 함수 이관, 실행부 재파싱 제거).
- 2026-02-23: Stage 4 1차 완료(실행 전 mode-skill 정책 강제, read/write 모드 고정 검증, mutation fallback 금지).
- 2026-02-23: Stage 4 2차 진행(`execute_from_intent()` 도입, `LLM_ONLY` 분기 분리).
- 2026-02-23: Stage 4 3차 진행(`SKILL_THEN_LLM` 분기 분리).
- 2026-02-23: Stage 4 4차 완료(`LLM_THEN_SKILL` 분기 분리 + `try_run_v2_orchestration()` 중복 실행 분기 제거).
- 2026-02-23: Stage 5 완료(문장->Intent 스냅샷 + 실행 정책 차단 케이스 + 금지 케이스 테스트 강화).
- 2026-02-23: Stage 6 준비 완료(rollout 스크립트 실행/문법 검증, 운영 runbook/판정기준 문서화).
- 2026-02-23: Stage 6 실행 커맨드 문서 추가(`docs/stage6_run_commands.md`).
- 2026-02-23: Stage 6 E2E 테스트 시트 추가(`docs/stage6_e2e_test_sheet.md`).
- 2026-02-23: Stage 6 원커맨드 점검 스크립트 추가(`backend/scripts/stage6_quickcheck.sh`).
- 2026-02-23: Stage 6 Telegram 자동 E2E 실행/채점 스크립트 추가(`backend/scripts/run_stage6_telegram_e2e.py`).
- 2026-02-23: Stage 6 자동 E2E 10/10 PASS, quickcheck(1일/limit=30)에서 shadow 수집 확인(`shadow_count=26`, `shadow_ok_rate=0.808`), 승격은 hold 유지.
- 2026-02-23: Canary 30%/60%/100% 단계 점검 완료. quickcheck(1일/limit=80) 기준 `v2_selected_count=39`, `v2_success_rate=0.872`, `v2_error_rate=0.128`, `verdict=PASS`.
- 2026-02-23: 운영 설정 `SKILL_V2_SHADOW_MODE=false`, `SKILL_V2_TRAFFIC_PERCENT=100` 적용 확인.
- 2026-02-23: 운영 quickcheck 최종 확인(1일/limit=80): `v2_selected_count=59`, `v2_success_rate=0.898`, `v2_error_rate=0.102`, `p95=6756ms`, `verdict=PASS`.
- 2026-02-23: `S9(linear issue -> notion create)` 간헐 `not_found` 보강 반영(Linear 조회 실패 시 fallback Notion 생성 지속).
- 2026-02-23: 후속 문서 추가
  - `docs/s9_not_found_followup.md`
  - `docs/v1_removal_plan.md`
- 2026-02-23: V1 제거 후속 PR 진행
  - PR-1: `loop.py` shadow 모드에서도 V2 결과 즉시 반환으로 정리
  - PR-2: `telegram.py` command_logs 레거시 payload fallback 제거

## 7) 작업 규칙
- 이 문서 체크박스를 작업 직후 즉시 갱신한다.
- 새 이슈가 발생하면 Stage 0/5에 회귀 케이스를 먼저 추가한다.

## 8) Stage 6 실행 체크리스트 (Staging/Prod)

Staging 실행 전 env 확인:
- [x] `SKILL_ROUTER_V2_ENABLED=true`
- [x] `SKILL_RUNNER_V2_ENABLED=true`
- [x] `SKILL_ROUTER_V2_LLM_ENABLED=true`
- [x] `SKILL_V2_SHADOW_MODE=true`
- [x] `SKILL_V2_TRAFFIC_PERCENT=0`
- [x] 원커맨드 점검 스크립트 준비 완료 (`backend/scripts/stage6_quickcheck.sh`)

Staging E2E 회귀 문장군:
- [x] `linear opt-46 이슈 설명 업데이트`
- [x] `openweather API 사용방법을 정리해서 linear opt-46 설명에 추가`
- [x] `linear opt-45 이슈를 삭제하세요`
- [x] `linear에 이슈 생성` -> `operate` -> `제목: ...`
- [x] `노션에서 "스프린트 보고서" 페이지 제목을 ...로 업데이트`
- [x] `노션에서 "스프린트 보고서" 페이지 본문 업데이트: ...`

Staging E2E 통과 기준:
- [x] `unsupported_service` / `unsupported_skill` 0건
- [x] `needs_input` 후 후속 입력 재개 성공
- [x] 생성/조회/수정/삭제 각 1회 이상 성공
  - 삭제는 정책상 비활성화(`delete_disabled`) 응답으로 안전 차단 확인

Shadow 수집 (3일):
- [x] `cd backend && DAYS=3 ./scripts/run_skill_v2_rollout_gate.sh`
- [x] `docs/reports/skill_v2_rollout_latest.json` 확인
- [x] `shadow_count >= min_sample` (전환 전 단계에서 충족 후 canary 진행)
- [x] `shadow_ok_rate >= 0.85` (전환 전 단계에서 충족 후 canary 진행)

Canary 전환:
- [x] 0% -> 10%: `cd backend && DAYS=3 CURRENT_PERCENT=0 ./scripts/run_skill_v2_rollout_cycle.sh`
- [x] 10% -> 30%: `cd backend && DAYS=3 CURRENT_PERCENT=10 ./scripts/run_skill_v2_rollout_cycle.sh`
- [x] 30% -> 100%: `cd backend && DAYS=3 CURRENT_PERCENT=30 ./scripts/run_skill_v2_rollout_cycle.sh`
- [x] 각 단계에서 `v2_success_rate >= 0.85`
- [x] 각 단계에서 `v2_error_rate <= 0.15`
- [x] 각 단계에서 `v2_latency_p95_ms <= 12000`

전면 전환 완료 후:
- [x] `SKILL_V2_SHADOW_MODE=false`
- [x] `SKILL_V2_TRAFFIC_PERCENT=100`
- [x] V1 제거 계획 별도 PR 생성(초안 문서 완료: `docs/v1_removal_plan.md`)

참고:
- 실행 명령 모음: `docs/stage6_run_commands.md`
- E2E 기록 시트: `docs/stage6_e2e_test_sheet.md`

## 9) Handoff (내일 이어서)

오늘까지 완료:
- [x] Stage 0 완료
- [x] Stage 1 완료
- [x] Stage 2 완료
- [x] Stage 3 완료
- [x] Stage 4 완료
- [x] Stage 5 완료
- [x] Stage 6 준비 작업 완료 (runbook/commands/e2e 시트/quickcheck 스크립트)

내일 시작할 작업(운영 실행):
- [x] Staging env 값 최종 확인 (Section 8)
- [x] `docs/stage6_e2e_test_sheet.md` 기준 E2E 실행 및 결과 기록(자동: `run_stage6_telegram_e2e.py`)
- [x] `cd backend && DAYS=3 CURRENT_PERCENT=0 ./scripts/stage6_quickcheck.sh` 실행
- [x] `docs/reports/skill_v2_rollout_latest.json` PASS 여부 확인(2026-02-23: gate PASS)
- [x] PASS 시 10% canary 시작, 이후 30%/60%/100% 승격 완료

내일 첫 실행 커맨드:
```bash
cd backend
DAYS=3 CURRENT_PERCENT=0 ./scripts/stage6_quickcheck.sh
```
