# 확장형 Skill+LLM Transform 파이프라인 개선 계획 (2026-02-26)

## 1) 배경
- 현재 복합 요청(예: "오늘 일정 중 회의만 조회해서 Notion에 상세 회의록 생성")이 하드코딩 분기/고정 템플릿 중심으로 처리되어, 의도 대비 결과 품질이 낮아지는 케이스가 존재한다.
- 서비스/API가 늘어날수록 조합 수(`A->B`, `C->F`, `F->A` 등)가 빠르게 증가해, 시나리오별 하드코딩만으로는 확장/유지보수가 어렵다.

## 2) 최종 목적
- 새로운 서비스를 추가해도 안정된 기본 실행 구조에서 빠르게 온보딩하고 조합 요청에 유연하게 대응한다.
- 사용자 요청/실행 로그를 학습 루프로 반영해 요청문 이해도(intent/slot 인식 정확도)를 지속 개선한다.

## 3) 목표
- 실행 구조를 `SKILL -> LLM_TRANSFORM -> SKILL` 체인으로 일반화하되, 검증/안전 가드는 기존 수준 이상으로 유지한다.
- LLM은 "도구 선택자"가 아니라 "변환기"로 제한해 안정성과 유연성을 동시에 확보한다.

## 4) 현재 구조 (As-Is)
- 진입:
  - Telegram webhook -> `run_agent_analysis` -> `execute_agent_plan`.
- 강점:
  - 고빈도 케이스의 결정론 경로가 안정적.
  - 기존 verifier/fallback/로그 체계가 이미 존재.
- 한계:
  - 복합 요청이 하드코딩 분기/템플릿에 의존.
  - 서비스/조합 증가 시 분기 수가 빠르게 증가.
  - "회의만 필터", "상세 회의록 서식" 같은 중간 의미 변환이 일반화되어 있지 않음.
  - 사용자 요청 이해 오류를 체계적으로 학습/반영하는 루프가 약함.

## 5) 기준 시나리오 (Primary)
- 사용자 요청:
  - "구글캘린더에서 오늘 일정 중 회의일정만 조회해서 노션에 상세한 회의록 서식으로 생성하세요."
- 목표 실행:
  1. `skill.google_calendar_list_events` (today window)
  2. `llm_transform.filter_meeting_events` (events -> meeting_events, schema 강제)
  3. `verify.filter_non_empty`
  4. `for_each(meeting_events)` fan-out
  5. `llm_transform.format_detailed_minutes` (event -> notion_page_payload, schema 강제)
  6. `verify.notion_payload_valid`
  7. `skill.notion_create_page`
  8. `finalize.telegram_response`
- 출력 정책:
  - 회의 N건이면 Notion 페이지 N건 생성(단건 집계 페이지 미사용).
  - 조건 일치 일정이 0건이면 실패가 아니라 성공형 응답으로 종료.

## 6) 설계 원칙
- LLM 역할 제한:
  - LLM은 `transform` 단계에서만 사용.
  - tool 실행/권한 판단/선택은 rule/contract 계층에서 수행(LLM 비관여).
- 출력 계약 강제:
  - 모든 `llm_transform` 출력은 JSON schema 검증 필수.
  - 불일치 시 1~2회 재시도 후 deterministic fallback.
- write 전 검증 필수:
  - 생성/수정 전 `verify`에서 필수 필드, 개수, 제약 조건 확인.
- 중복 방지:
  - idempotency key 및 request_id 기반 중복 생성 차단.

## 7) 아키텍처 변경안

### 7.1 노드 타입
- 유지 타입:
  - `skill`
  - `llm_transform`
  - `verify`
  - `finalize`
- 참고:
  - `skill+llm_transform`을 하나의 job으로 합칠 수는 있으나, 운영 관측/재시도/원인분리에 불리해 기본은 분리 노드로 유지.

### 7.2 Pipeline DSL 확장
- `llm_transform` 노드 필드:
  - `transform_name`
  - `input_ref`
  - `output_schema`
  - `retry_policy` (`max_retries`, `timeout_sec`)
  - `fallback_policy` (`rule_fallback`, `fail_closed`)
- `verify` 노드 필드:
  - `rules` (필수 키/개수/포맷/상호일관성)
  - `on_fail` (`stop`, `fallback`, `clarification`)
- `for_each` 노드 필드:
  - `items_ref`
  - `max_items`
  - `concurrency`
  - `on_item_fail` (`stop_all`, `skip`, `compensate`)

### 7.3 Contract 연동
- skill contract에 추가:
  - 입력/출력 schema version
  - required scopes
  - idempotency 규칙
  - safe retry 가능 여부
- llm transform contract 별도 추가:
  - `filter_meeting_events`
  - `format_detailed_minutes`
- transform contract versioning:
  - `transform_schema_version` 필수(`v1` 시작)
  - minor 호환: unknown field 무시
  - major 변경: `v2` 병행 운영 후 점진 전환

## 8) 단계별 실행 계획

### Phase A: Transform 노드 기반 최소 경로 구현
- [x] `calendar -> notion` 기준 파이프라인 fixture 추가
- [x] `llm_transform.filter_meeting_events` 구현
- [x] `llm_transform.format_detailed_minutes` 구현
- [x] schema validator + retry/fallback 구현

### Phase B: Verify/가드레일 강화
- [x] filter 결과 검증(`>=1`, 필수 키 존재)
- [x] notion payload 검증(title/children 길이/문자수)
- [x] write 전 fail-closed 정책 적용
- [x] idempotency key 연동

### Phase C: 라우팅/컴파일러 연결
- [x] 요청문을 "조회 단계 + 생성 단계"로 컴파일하는 deterministic 컴파일러 추가
- [x] LLM은 컴파일 결과 보정이 아닌 transform payload 생성에만 사용
- [x] 기존 하드코딩 분기보다 신규 파이프라인 우선/후순위 정책 결정
- [x] feature flag (`SKILL_LLM_TRANSFORM_PIPELINE_ENABLED`) 추가
- 우선순위 정책(확정):
  - `SKILL_LLM_TRANSFORM_PIPELINE_ENABLED=true` 이고 minutes intent 매칭 시 `compiled_skill_llm_plan` 경로 실행
  - 그 외 요청은 기존 hard-coded/기존 planner 경로 유지

### Phase D: 운영 롤아웃
- [x] shadow mode로 기존 경로와 병행 실행
- [x] 10% -> 30% -> 100% 점진 확대
- [x] rollback 조건 자동화
- 승격 기준(30분 이동창):
  - `pipeline_success_rate >= 95%`
  - `user_visible_error <= 5%`
  - `llm_transform_fallback <= 15%`
- 중단/롤백 기준(30분 이동창):
  - `pipeline_success_rate < 90%` 또는
  - `user_visible_error > 8%` 또는
  - `duplicate_create_detected >= 1`

## 9) 테스트 계획

### 9.1 단위 테스트
- [x] `filter_meeting_events` schema/필터 정확도 테스트
- [x] `format_detailed_minutes` schema/길이 제약 테스트
- [x] verify 실패/재시도/fallback 테스트

### 9.2 통합 테스트
- [x] "오늘 일정 중 회의만 -> Notion 상세 회의록 생성"
- [x] "오늘 일정 조회 -> Linear 이슈 생성"
- [x] "오늘 일정 중 회의만 -> Linear 회의록 서식 이슈 생성"
- [x] timezone 경계/빈 결과/부분 실패/중복 요청

### 9.3 운영 스모크
- [x] Stage6 시트에 신규 시나리오 추가
- [x] command_logs에 transform/verify 단계별 결과 기록 확인

## 10) 관측 지표 (SLO/KPI)
- 공통 집계 규칙:
  - 단위: `request_id` 기준 1회 집계
  - 기본 윈도우: 최근 24시간 + 최근 7일
  - 최소 표본: 100건 미만은 참고 지표로만 표시
- 신규 서비스 온보딩 리드타임:
  - `first_contract_commit -> first_successful_pipeline_run` 시간
- 조합 시나리오 성공률:
  - `composed_pipeline_success / composed_pipeline_total`
- transform 성공률:
  - `llm_transform_success / llm_transform_total`
- transform fallback률:
  - `llm_transform_fallback / llm_transform_total`
- write 전 검증 실패율:
  - `verify_fail_before_write / write_attempt_total`
- end-to-end 성공률:
  - `pipeline_success / pipeline_total`
- 사용자 체감 실패율:
  - `user_visible_error / total_requests`
- 요청 이해 오류율:
  - `intent_mismatch_or_slot_miss / total_requests`
- 사용자 재요청률:
  - `followup_retry_within_10m / total_requests`

## 11) 사용자 요청 학습 루프
- 데이터 수집:
  - `user_text`, `intent`, `selected_pipeline`, `transform_input/output`, `verify_result`, `final_status`.
- 라벨링 소스:
  - verifier 실패 사유
  - fallback 사유
  - 사용자의 즉시 재요청/정정 패턴
- 주기적 개선:
  - 주 1회 `intent confusion top-N`, `slot 누락 top-N`, `transform schema fail top-N` 리포트 생성
  - 룰/프롬프트/정규화기 업데이트 후 canary 적용
- 안전장치:
  - 학습 데이터 반영 전 regression gate 통과 필수
  - 고위험 write 경로는 shadow 검증 후 승격
- 현재 결정:
  - 학습 데이터 확장은 차후 고려.
  - 당장은 `command_logs` 기반 집계/분석만 사용.

## 12) 예상 리스크 및 대응
- 리스크: LLM transform 출력 변동성
  - 대응: strict schema + retry + deterministic fallback
- 리스크: 지연/비용 증가
  - 대응: transform 호출 횟수 상한, batch 처리, 캐시 가능한 중간 결과 재사용
- 리스크: 부분 성공 후 중복 생성
  - 대응: idempotency key, 보상(rollback), 단계별 상태 저장
- 리스크: 하드코딩 경로와 신규 경로 충돌
  - 대응: feature flag + shadow 비교 + 점진 롤아웃

## 13) 완료 기준 (DoD)
- [ ] Primary 시나리오 3일 연속 성공률 95% 이상
- [ ] transform fallback률 10% 이하
- [ ] write 전 verify 누락 0건
- [ ] 기존 Stage6 핵심 회귀 테스트 전부 PASS
- [ ] rollback 없이 canary 100% 전환 완료
- [ ] 신규 서비스 1건을 하드코딩 분기 추가 없이 contract+pipeline만으로 온보딩 완료
- [ ] 요청 이해 오류율 2주 이동평균 개선 확인
- [ ] N건 입력 시 N페이지 생성 정책이 E2E에서 일관되게 검증됨
- [ ] 조건 불일치 0건 시 성공형 응답 정책이 E2E에서 검증됨

## 14) 구조 개선 이력 (Changelog)
- 2026-02-26
  - 초안 작성: `SKILL -> LLM_TRANSFORM -> SKILL` 일반화 계획 수립.
  - Primary 시나리오 정의(캘린더 회의 필터 -> 상세 회의록 -> Notion 생성).
- 2026-02-26 (update)
  - 문서 목적을 "확장 가능한 기본 구조 + 요청 이해도 학습 루프"로 명시.
  - As-Is 구조/한계 섹션 추가.
  - KPI에 온보딩 리드타임/요청 이해 오류율/재요청률 추가.
  - 개선 이력 섹션 추가(차후 변경 누적 기록 용도).
- 2026-02-26 (review decisions)
  - 다건 처리 정책을 `N회의 -> N페이지 생성`으로 확정.
  - 필터 결과 0건은 실패가 아닌 성공형 응답으로 확정.
  - 컴파일러 책임을 deterministic으로 고정, LLM tool 선택 금지 원칙 명시.
  - `for_each` 노드, transform schema versioning, 롤아웃 승격/중단 임계치 추가.
  - 학습데이터 확장은 보류하고 `command_logs` 기반 분석 우선으로 확정.
- 2026-02-26 (implementation update)
  - `calendar -> linear(minutes)` fixture/transform contract 추가.
  - 통합 테스트에 timezone 경계/빈 결과/부분 실패/중복 이벤트(idempotent dedupe) 케이스 추가.
- 2026-02-26 (rollout update)
  - `SKILL_LLM_TRANSFORM_PIPELINE_SHADOW_MODE`, `SKILL_LLM_TRANSFORM_PIPELINE_TRAFFIC_PERCENT` 설정 추가.
  - rollout miss + shadow mode에서 신규 pipeline을 병행 실행(shadow)하고 기존 경로 응답 유지하도록 반영.
  - rollout gate/decision/apply/cycle 스크립트 추가(`eval/decide/apply/run_skill_llm_transform_rollout_cycle`).
- 2026-02-26 (slo update)
  - DoD 관점 자동 검증 스크립트 추가(`run_skill_llm_transform_slo_guard.sh`).
  - SLO 가드에 `transform_error_rate`, `verify_fail_before_write_count`, `composed_pipeline_count` 임계치 반영.
  - `N건->N페이지`, `0건 성공형 응답` 불변식 E2E 테스트를 가드 실행에 포함.
- 2026-02-26 (next step update)
  - 다음 작업 계획으로 `llm_transform`의 실제 LLM API 호출 전환을 명시.
  - 생성품질 개선은 프롬프트 대수정보다 모델/파라미터 튜닝과 shadow canary를 우선 적용.
- 2026-02-26 (llm transform implementation update)
  - `format_detailed_minutes`, `format_linear_meeting_issue`에 대해 LLM API 기반 transform 호출을 우선 시도하도록 반영.
  - 출력 스키마/필수값 검증 실패 시 deterministic transform contract로 즉시 fallback하도록 보강.
  - 관련 회귀 테스트(`notion minutes llm transform`) 추가.

## 15) 다음 고도화 후보
- 다중 대상(`각 회의마다`, `각 프로젝트별`) fan-out/fan-in 노드 표준화
- transform 결과 신뢰도(score) 기반 동적 검증 강도 조절
- 서비스별 템플릿 라이브러리화(회의록/버그리포트/일일요약)
- `llm_transform`를 deterministic contract에서 실제 LLM API 기반 변환으로 전환
- LLM 생성품질 개선(모델 튜닝 우선)
  - 1차: 후보 모델 A/B 오프라인 리플레이 평가
  - 2차: `temperature/top_p/max_tokens` 표준 파라미터 고정
  - 3차: shadow mode canary 후 점진 승격
  - 4차: 실패 시 deterministic fallback 유지(fail-closed)

## 16) 구현 분해 (PR/티켓 단위)

### PR-1: Pipeline DSL/런타임 최소 확장 (`for_each`, `llm_transform`)
- 목표:
  - 기존 DAG 런타임에 `for_each`, `llm_transform`를 최소 스코프로 추가.
- 변경 파일(예상):
  - `backend/agent/pipeline_dag.py`
  - `backend/agent/pipeline_dsl_schema.json`
  - `backend/agent/pipeline_error_codes.py`
- 구현 항목:
  - `for_each` 노드 실행기 추가 (`items_ref`, `max_items`, `concurrency`)
  - `llm_transform` 노드 실행기 인터페이스 추가
  - 노드별 status/artifact 기록 확장
- 완료 기준:
  - 단일 fixture에서 `skill -> for_each -> llm_transform -> verify -> skill` 실행 가능
  - 실패 코드/재시도/타임아웃이 표준 코드로 반환
- 진행 상태:
  - [x] 완료 (for_each 확장 필드 + backward compatible 적용)

### PR-2: Transform 계약/검증기 추가 (`filter_meeting_events`, `format_detailed_minutes`)
- 목표:
  - transform 출력 스키마 강제 + 재시도 + fallback 정책 구현.
- 변경 파일(예상):
  - `backend/agent/executor.py`
  - `backend/agent/orchestrator_v2.py`
  - `backend/agent/intent_normalizer.py` (필요 시)
  - 신규: `backend/agent/transform_contracts.py` (권장)
- 구현 항목:
  - `transform_schema_version=v1` 검증
  - `filter_meeting_events`: events -> meeting_events
  - `format_detailed_minutes`: event -> notion_page_payload(title, children)
  - schema mismatch 시 `max_retries` 내 재시도 후 rule fallback
- 완료 기준:
  - transform 성공/실패/재시도/fallback이 artifact와 step에 명확히 기록
- 진행 상태:
  - [x] 1차 완료 (transform contract 구현 + executor 연동)

### PR-3: Calendar->Notion Primary 파이프라인 fixture 추가 (N건 -> N페이지)
- 목표:
  - Primary 시나리오를 하드코딩 분기 대신 pipeline fixture 기반으로 실행.
- 변경 파일(예상):
  - `backend/agent/pipeline_fixtures.py`
  - `backend/agent/loop.py`
  - `backend/agent/executor.py`
- 구현 항목:
  - `google_list_today` -> `filter_meeting_events` -> `for_each` -> `format_detailed_minutes` -> `notion_create_page`
  - `meeting_events` 0건일 때 성공형 응답 반환
  - N건 입력 시 N건 생성 보장
- 완료 기준:
  - Primary 시나리오에서 생성 페이지 수가 meeting_events 수와 일치
  - 0건 케이스에서 에러코드 없이 성공 응답
- 진행 상태:
  - [x] 1차 완료 (fixture + loop 분기 + 회귀 테스트 반영)

### PR-4: Verify 정책/Fail-Closed 정리
- 목표:
  - write 직전 검증 누락 방지 및 안전한 실패 처리.
- 변경 파일(예상):
  - `backend/agent/executor.py`
  - `backend/agent/pipeline_dag.py`
- 구현 항목:
  - `verify.filter_non_empty` 규칙 구현
  - `verify.notion_payload_valid` 구현 (title/children/길이 제한)
  - `on_fail` 정책(`stop`, `fallback`, `clarification`) 일관 처리
- 완료 기준:
  - verify 실패 후 write 실행 0건
  - verify 실패 사유가 구조화되어 로그/응답에 노출
- 진행 상태:
  - [x] 1차 완료 (verify `on_fail` 정책 + transform fallback_policy + notion write fail-closed)

### PR-5: Deterministic 컴파일러 연결 + 플래그
- 목표:
  - tool 선택은 rule/contract 계층으로 고정, LLM은 transform 전용으로 제한.
- 변경 파일(예상):
  - `backend/agent/loop.py`
  - `backend/agent/orchestrator_v2.py`
  - `backend/app/core/config.py`
- 구현 항목:
  - `SKILL_LLM_TRANSFORM_PIPELINE_ENABLED` 플래그
  - 요청 패턴을 pipeline fixture로 deterministic 컴파일
  - 기존 하드코딩 경로와 우선순위 명시(플래그 기반)
- 완료 기준:
  - 플래그 ON/OFF로 신규/기존 경로 전환 가능
  - LLM이 tool 선택에 관여하지 않음이 코드상 보장
- 진행 상태:
  - [x] 1차 완료 (minutes 시나리오 deterministic compile + feature flag 경로 격리)

### PR-6: 관측/로그/KPI 집계 반영 (`command_logs` 기반)
- 목표:
  - 운영 판단 가능한 지표를 request_id 기준으로 일관 집계.
- 변경 파일(예상):
  - `backend/app/routes/telegram.py`
  - `backend/scripts/eval_agent_quality.py`
  - `docs/stage6_e2e_test_sheet.md`
- 구현 항목:
  - `transform_success/fallback`, `verify_fail_before_write`, `created_count` 로그 반영
  - request_id 기준 중복 제거 집계 규칙 적용
  - Stage6 시나리오/체크 항목 업데이트
- 완료 기준:
  - 신규 KPI(`composed_pipeline_success`, `intent_mismatch_or_slot_miss`) 산출 가능
  - 대시보드/리포트에서 승격/롤백 기준 확인 가능
- 진행 상태:
  - [x] 1차 완료 (`pipeline_json` 구조화 로그 + eval 집계 필드 확장)

### PR-7: 테스트 팩 (단위/통합/E2E)
- 목표:
  - 정책 결정사항(안전성/단순성)을 회귀 테스트로 고정.
- 변경 파일(예상):
  - `backend/tests/test_pipeline_dag.py`
  - `backend/tests/test_pipeline_fixture_e2e.py`
  - `backend/tests/test_agent_loop.py`
  - 신규/확장: transform, verify 관련 테스트 파일
- 필수 테스트 케이스:
  - N건 입력 -> N페이지 생성
  - meeting 0건 -> 성공형 응답
  - transform schema mismatch -> 재시도 후 fallback
  - verify 실패 -> write 미실행
  - duplicate 요청 -> idempotency로 중복 생성 차단
- 완료 기준:
  - Stage6 핵심 + 신규 시나리오 전부 PASS
  - canary 전 회귀 게이트 통과
- 진행 상태:
  - [x] 1차 완료 (transform/fixture/loop 회귀 테스트 + Stage6 시트/실행 문서 반영)

## 17) 실행 순서 (권장)
1. PR-1 (런타임 확장)  
2. PR-2 (transform 계약/검증)  
3. PR-3 (Primary fixture 적용)  
4. PR-4 (verify fail-closed)  
5. PR-5 (deterministic 컴파일러 + 플래그)  
6. PR-6 (관측/KPI)  
7. PR-7 (테스트 팩/회귀 고정)
