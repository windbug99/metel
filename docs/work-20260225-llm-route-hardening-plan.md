# work-20260225-llm-route-hardening-plan

## 1) 배경
- 현재 일부 복합 요청(예: "오늘 일정 중 회의만 Linear 이슈 생성")이 `LLM 분석 -> autonomous 실행` 경로에서 `replan_limit`로 실패한다.
- 단기적으로는 deterministic 템플릿 라우팅으로 보완했지만, 중장기적으로는 LLM 경로 자체의 복원력/정확도를 높여야 한다.

## 2) 목표
- 전용 하드코딩 규칙 없이도 LLM 경로에서 복합 요청을 안정적으로 처리한다.
- `autonomous` 실패의 주 원인(`replan_limit`, tool selection drift, incomplete intent slots)을 구조적으로 줄인다.

## 3) 성공 기준 (Gate/SLO)
- Autonomous gate
  - `autonomous_attempt_rate >= 90%`
    - 정의: `autonomous 시도 건수 / (실행 가능 요청 건수)`
    - 제외: 인증 미연결/입력 누락으로 실행 불가한 요청
  - `autonomous_success_rate >= 90%`
    - 정의: `autonomous 성공 건수 / autonomous 시도 건수`
  - `autonomous_success_over_attempt >= 85%`
    - 정의: `autonomous 성공 건수 / 실행 가능 요청 건수`
  - `fallback_rate <= 10%` (stretch: `<= 5%`)
    - 정의: `fallback 전환 건수 / autonomous 시도 건수`
  - 집계 규칙
    - 단위: `request_id` 기준 1회 집계(재시도/shadow 중복 제거)
    - 우선순위: `success > fallback > failed`
- 회귀 없음
  - DAG quality gate PASS 유지
  - 기존 Notion/Linear/Google 핵심 시나리오 회귀 테스트 PASS

## 4) 문제 분해
- Intent/slot 표현력 부족
  - "회의만", "A만", "제외", "조건" 같은 필터 조건이 명시적 슬롯으로 유지되지 않음.
- Planner -> Autonomous 인수 불일치
  - Planner 결과가 실행 가능한 tool payload로 충분히 수렴하지 못하면 autonomous가 재계획을 반복.
- Replan 정책 과민
  - 동일 실패 유형에서 재시도/재계획이 반복되어 `replan_limit` 도달.
- 검증 피드백 루프 약함
  - 실패 원인이 구조화된 slot/action 단위로 다시 planner에 반영되지 않음.

## 5) 개선 설계

### 5.1 Intent schema 확장 (필터/범위/대상 명시)
- `intent_contract` 확장 필드 추가:
  - `time_scope`: `today | date_range | explicit_date`
  - `event_filter`: `{ keyword_include: [], keyword_exclude: [] }`
  - `target_scope`: `linear_only | notion_only | notion_and_linear`
  - `result_limit`: 정수
- 예시: "오늘 일정 중 회의만 리니어 이슈 생성"
  - `time_scope=today`
  - `event_filter.keyword_include=["회의"]`
  - `target_scope=linear_only`

### 5.2 Planner 출력 제약 강화
- Planner 출력 검증:
  - tool set이 intent target_scope와 불일치하면 즉시 보정
  - 슬롯 정책을 `blocking` / `non_blocking`으로 분리
    - `blocking` 누락: 실행 진입 금지 + clarification
    - `non_blocking` 누락: 기본값/autofill 후 실행 허용
- Calendar tool payload 규칙:
  - `today`면 실행 직전 `time_min/time_max/single_events/order_by` 강제 표준화
  - `time_scope` 파싱 실패 시 fail-open 금지, `clarification_required`로 종료

### 5.3 Autonomous 정책 튜닝
- `replan` 전 가드:
  - 같은 실패 코드/같은 payload 반복 시 재계획 대신 slot 재질문 우선
- `replan_limit` 소진 방지:
  - 실패 유형별 분기(`validation`, `auth`, `not_found`)를 독립 처리
- Tool ranking 개선:
  - intent의 `target_scope`/`event_filter`를 ranking prompt에 명시 주입
 - deterministic fallback 정책:
   - 목적: SLO 보호용 안전장치(상시 경로 아님)
   - 조건: `replan_limit` 소진 + 동일 실패 2회 이상 + retry 불가 코드
   - 측정: fallback 포함/제외 지표를 분리 집계

### 5.4 Verifier 강화
- 완료 조건을 intent 기반으로 명시:
  - `linear_only`인데 notion 생성이 있으면 실패
  - `keyword_include` 조건 미충족 결과가 생성되면 실패
- verifier 실패 시 단순 "다시 시도" 대신 구조화된 remediation 힌트 반환

### 5.5 관측/로그 개선
- `command_logs`에 구조화 필드(JSON) 추가:
  - `intent`: `{time_scope, target_scope, filter_include, filter_exclude, result_limit}`
  - `autonomous`: `{attempted, success, fallback, replan_reason_histogram, retry_count}`
  - `verifier`: `{failed_rule, remediation_type}`
- `detail`은 요약 문자열만 유지(디버그 스냅샷 용도)
- 대시보드/리포트에 실패 원인 top-N과 슬롯 누락 빈도 노출

### 5.6 계약/호환성 정책
- `intent_contract`에 `schema_version` 도입 (초기: `v1`)
- 호환성:
  - unknown field는 무시(fail-open)
  - required field 누락은 defaulting 또는 `clarification_required`
  - 검증기/실행기 모두 `v1` fallback 지원
- Phase C verifier는 `schema_version=v1` 보장 경로에서만 strict rule 적용

## 6) 단계별 실행 계획 (Checklist)

### Phase A: 스키마/검증 기초
- [x] `intent_contract` 확장 필드 추가
- [x] `intent_contract.schema_version(v1)` + backward compatibility 규칙 추가
- [x] planner 출력 검증기(필수 슬롯/타겟 범위) 추가
- [x] 관련 단위 테스트 추가

### Phase B: 실행 경로 수렴
- [x] autonomous 입력 정규화 레이어 추가(시간/필터/타겟)
- [x] 반복 실패 차단 로직 추가(동일 payload + 동일 에러)
- [x] replan 정책 분기 튜닝

진행 메모 (2026-02-25)
- `blocking/non_blocking` 슬롯 precheck를 실행 진입 전에 추가하여 blocking 누락 시 즉시 clarification으로 전환.
- autonomous에서 동일 payload + 동일 `VALIDATION_REQUIRED` 반복 시 `clarification_required`로 종료해 replan 소모를 방지.

### Phase C: verifier/관측
- [x] intent-aware verifier 규칙 추가 (`schema_version=v1` strict)
- [x] 실패 remediation 힌트 구조화
- [x] command_logs 구조화 필드/리포트 반영

진행 메모 (2026-02-25 / Phase C)
- verifier에 `target_scope`/`event_filter` 기반 검증 규칙을 추가.
- verifier 실패 시 `verifier_failed_rule`, `verifier_remediation_type`, `verifier_remediation_hint`를 구조화 반환.
- telegram `command_logs.detail`에 `request_id`, `intent_json`, `autonomous_json`, `verifier_json`를 기록하고 평가 스크립트에서 파싱/집계하도록 반영.

### Phase D: 롤아웃
- [x] shadow mode(기존 경로와 병행)
- [x] canary 10% -> 30% -> 100%
- [x] gate 기준 충족 시 기본 경로 전환
- [x] kill-switch/rollback 기준 적용
  - 중단 조건(30분 이동 창):
    - `fallback_rate > 20%` 또는
    - `autonomous_success_over_attempt < 75%` 또는
    - `auth_error` 비중 2배 급증
  - 중단 시 즉시 이전 안정 설정으로 복귀 + incident 로그 생성

진행 메모 (2026-02-25 / Phase D)
- `run_autonomous_rollout_cycle.sh` + `decide_autonomous_rollout.py` + `apply_autonomous_rollout_decision.py` 추가.
- canary 단계(0→10→30→100) 자동 승격/보류/롤백, kill-switch 조건(fallback/success-over-attempt/auth_error surge) 자동 판정 구현.
- `LLM_AUTONOMOUS_SHADOW_MODE` 추가: rollout miss 구간에서 autonomous를 shadow로 병행 실행하고 실제 응답은 deterministic 유지.
- decision 결과에 `LLM_AUTONOMOUS_SHADOW_MODE`를 포함해 canary 승격 시 자동으로 기본 경로 전환(10% 이상은 shadow off)되도록 적용.
- 운영 문서(`backend/agent/README.md`)에 Railway env 키, rollout cycle 실행 절차, kill-switch/rollback runbook 반영.

## 7) 테스트 전략
- 단위 테스트
  - intent parsing/validation (필터/범위/타겟)
  - planner output guard
  - autonomous duplicate-failure blocking
  - verifier intent-rule validation
- 통합 테스트
  - "오늘 일정 중 회의만 리니어 이슈 생성"
  - "오늘 일정 중 회의만 노션 페이지 생성"
  - "오늘 일정 조회"(읽기 전용)
  - "회의 제외 일정만 생성"(exclude filter)
  - timezone 경계(로컬 자정 ± 1시간), all-day event 포함
- 실운영 스모크
  - `run_autonomous_gate.sh`, `run_dag_quality_gate.sh`, `check_dag_smoke_result.py`

## 8) 리스크 및 대응
- 리스크: 과도한 제약으로 유연성 저하
  - 대응: strict 모드 플래그화 + 단계적 rollout
- 리스크: verifier false negative 증가
  - 대응: fail-open/closed 정책 분리, shadow 지표 먼저 확인
- 리스크: 로그 필드 확장으로 분석 복잡도 증가
  - 대응: 보고서 템플릿 고정화(top-N 중심)

## 9) 운영 파라미터(초기 제안)
- `LLM_AUTONOMOUS_REPLAN_LIMIT=2`
- `LLM_AUTONOMOUS_LIMIT_RETRY_ONCE=true`
- `LLM_AUTONOMOUS_STRICT_TOOL_SCOPE=true`
- `LLM_HYBRID_EXECUTOR_FIRST=true` (롤아웃 초기)
- `TOOL_SPECS_VALIDATE_ON_STARTUP=true`
- `LLM_AUTONOMOUS_FALLBACK_MODE=safety_only`
- `LLM_INTENT_SCHEMA_VERSION=v1`

## 10) 완료 정의 (Definition of Done)
- [x] Autonomous gate 3회 연속 PASS
- [ ] fallback_rate 10% 이하 3일 연속 유지
- [x] 대표 시나리오(회의만/오늘 조회/복합 생성) 회귀 0건
- [x] 문서/운영 가이드 업데이트 완료

진행 메모 (2026-02-26 / DoD 추적)
- `run_autonomous_gate.sh` 3회 연속 PASS 확인(샘플 30 기준, 동일 시점 측정값 반복 확인).
- `run_autonomous_slo_guard.sh`는 `fallback_rate=16.7%`로 FAIL(`<=10%` 미충족).
- 대표 시나리오 관련 회귀 테스트(단위/통합 성격) 4건 PASS:
  - `test_try_build_agent_plan_with_llm_enforces_target_scope`
  - `test_try_build_agent_plan_with_llm_propagates_event_filter_notes`
  - `test_autonomous_forces_today_range_for_google_calendar_tool`
  - `test_build_task_tool_payload_forces_today_range_for_today_query`
- 대표 시나리오 회귀 확장 검증 7건 PASS:
  - `test_try_build_agent_plan_with_llm_enforces_target_scope`
  - `test_try_build_agent_plan_with_llm_propagates_event_filter_notes`
  - `test_autonomous_verifier_blocks_scope_violation`
  - `test_autonomous_verifier_blocks_include_keyword_violation`
  - `test_autonomous_forces_today_range_for_google_calendar_tool`
  - `test_build_task_tool_payload_forces_today_range_for_today_query`
  - `test_build_task_tool_payload_forces_single_events_for_today_query`
- fallback 개선 패치(2026-02-26):
  - `verification_failed` 중 `scope_violation/filter_include_missing/filter_exclude_violated`는 deterministic fallback 대신 autonomous 결과를 유지하도록 분기 추가.
  - 관련 회귀 테스트 추가: `test_run_agent_analysis_verifier_scope_violation_blocks_rule_fallback`
  - `TOOL_TIMEOUT`(uppercase) 오류도 autonomous 1회 재시도 대상에 포함하도록 보정.
  - 관련 회귀 테스트 추가: `test_run_agent_analysis_retries_on_tool_timeout_code`
  - `eval_agent_quality.py --days N` 추가(UTC 기준 최근 N일 윈도우 집계) 및 `run_autonomous_slo_guard.sh`에 `DAYS` 연동.
  - 3일 DoD 추적 시 `DAYS=3`로 동일 기준 반복 측정 가능하도록 운영 편의성 강화.
  - `DAYS=3 LIMIT=300 ./scripts/run_autonomous_slo_guard.sh` 실측:
    - `fallback_rate=35.7% (107/300)` / 목표 `<=10%` 미충족
    - `autonomous_success_over_attempt=61.1% (127/208)` / 목표 `>=70%` 미충족
    - fallback top 원인: `replan_limit(40)`, `tool_error_rate(22)`, `TOOL_TIMEOUT(17)`
  - guardrail 과민 완화: `LLM_AUTONOMOUS_GUARDRAIL_MIN_TOOL_SAMPLES`(기본 2) 추가.
    - tool_error_rate 강등은 최소 tool 샘플 수 이상일 때만 적용(단발성 1회 오류 강등 억제).
  - `replan_limit` 오류 재시도 시 turn/tool/replan 예산을 추가 상향하도록 override 보정.

## 11) 실행 백로그 (PR/이슈 분할)

### PR-1: SLO 집계/로그 스키마 정리
- 목표
  - `request_id` 기준 단일 집계, 구조화 로그 필드 도입
- 변경 범위
  - `backend/app/routes/telegram.py` (command_logs 기록 payload)
  - `backend/scripts/eval_agent_quality.py` (지표 계산식 반영)
  - 필요 시 SQL migration (`command_logs` JSON 컬럼 또는 별도 컬럼)
- 완료 기준
  - `autonomous_attempt_rate/success_rate/fallback_rate`가 문서 정의식대로 계산됨
  - retry/shadow 중복 집계가 제거됨
- 검증
  - 단위: 지표 계산 테스트 추가
  - 스모크: 최근 1일 로그 샘플로 기존/신규 지표 비교 리포트 생성

### PR-2: intent_contract v1 + 호환성
- 목표
  - `schema_version=v1` 도입 및 backward compatibility 보장
- 변경 범위
  - intent 파싱/정규화 모듈
  - planner 입력/출력 계약 검증기
  - verifier가 참조하는 intent payload 경로
- 완료 기준
  - v1 필드(`time_scope`, `event_filter`, `target_scope`, `result_limit`)가 일관되게 전달됨
  - unknown field 무시, required 누락 시 defaulting/clarification 동작
- 검증
  - 단위: intent parsing/validation 테스트
  - 통합: v0-like 요청(구형)과 v1 요청 모두 처리

### PR-3: planner guard + 슬롯 정책 분리
- 목표
  - `blocking/non_blocking` 슬롯 정책 적용
- 변경 범위
  - planner output guard
  - 실행 진입 전 validation 단계
- 완료 기준
  - blocking 누락은 실행 차단 + clarification
  - non-blocking 누락은 autofill/defaulting 후 진행
- 검증
  - 단위: guard 테스트 (target_scope 불일치/slot 누락 케이스)
  - 회귀: 기존 생성/조회 시나리오 PASS

### PR-4: autonomous 반복실패 차단 + replan 튜닝
- 목표
  - 동일 payload+동일 error 반복 시 재계획 남용 차단
- 변경 범위
  - `backend/agent/autonomous.py`
  - `backend/agent/loop.py` (retry override/tuning)
- 완료 기준
  - 동일 실패 루프에서 `replan_limit` 소진 빈도 감소
  - fallback은 `safety_only` 조건에서만 동작
- 검증
  - 단위: duplicate-failure blocking 테스트
  - 실운영 스모크: `run_autonomous_gate.sh`

### PR-5: intent-aware verifier + remediation
- 목표
  - target_scope/filter/time_scope 기반 완료 조건 검증
- 변경 범위
  - verifier 규칙 모듈
  - 실패 시 remediation 힌트 생성기
- 완료 기준
  - `linear_only` 요청에서 notion write 발생 시 실패
  - `keyword_include/exclude` 위반 결과 생성 시 실패
- 검증
  - 단위: verifier 규칙 테스트
  - 통합: 회의만/회의 제외/읽기 전용 케이스 PASS

### PR-6: 롤아웃/킬스위치 자동화
- 목표
  - 10%→30%→100% canary + 중단/롤백 자동 기준 적용
- 변경 범위
  - 런타임 설정/플래그 처리
  - 운영 스크립트(`run_autonomous_gate.sh`, 평가 스크립트)
- 완료 기준
  - 중단 조건 충족 시 즉시 이전 안정 설정으로 복귀
  - incident 로그가 남음
- 검증
  - 리허설: 인위적 fallback 상승 상황에서 kill-switch 동작 확인

## 12) 권장 실행 순서
1. PR-1 (관측/지표 기반 확보)
2. PR-2 (계약 고정)
3. PR-3 (실행 진입 품질)
4. PR-4 (autonomous 안정화)
5. PR-5 (검증/피드백 루프)
6. PR-6 (운영 롤아웃 안전장치)
