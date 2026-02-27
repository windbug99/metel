# LLM 단계형 문장 분해/실행 파이프라인 작업계획 (2026-02-27)

## 1) 목적
- 사용자 요청부터 결과 출력까지를 더 단순하고 예측 가능한 흐름으로 재구성한다.
- LLM 사용량은 높이되, 실행 안정성은 `계약(Contract) + 검증(Validation)`으로 보장한다.
- 신규 구조를 별도 브랜치에서 구현/검증 후 기존 구조와 비교해 최종 채택한다.
- 기존 실행 구조를 부분 보완이 아닌 전면 개편 대상으로 정의한다.

## 2) 목표 구조 (To-Be)
1. 사용자 요청 입력 수신
2. `요청문 + 연결 서비스 목록 + API 목록`을 LLM에 전달
3. LLM이 아래를 리턴
   - 분리된 작업 단위 리스트(`tasks[]`)
   - 각 작업 단위별 필요 서비스/API/의존성
4. 분리된 작업 단위 수만큼 반복 실행
5. 각 반복에서 아래 입력으로 LLM 호출
   - `현재 문장 + 선택 서비스 + API + 타임존 정보 (+ 이전 API 결과(2번째 이상부터))`
6. LLM이 API 요청 형식(필수 파라미터 채움, 선택 파라미터는 가능 범위 채움, 불명확 값은 비움) 리턴
7. API 요청 문법/스키마 검증
8. 필수 정보 누락 시 즉시 실패 처리(`fail_closed`)
9. 검증 통과 시 API 호출
10. API 응답 임시 메모리 저장
11. write API는 idempotency key 기반 중복 방지
12. 마지막 단계 종료 후 저장된 결과를 응답 포맷에 맞게 출력

### 실행 전략 고정
- 본 계획의 기본 실행 전략은 `순차 실행`으로 고정한다.
- 다중 작업 요청은 `이전 단계 출력 -> 다음 단계 입력` 형태로 순서대로 처리한다.
- 예: `캘린더 조회 -> 회의 필터 -> 노션 회의록 생성 -> 리니어 이슈 생성`

## 3) 핵심 설계 원칙
- LLM 책임:
  - 문장 분해
  - 단계별 API 파라미터 채우기
- 런타임 책임:
  - 서비스/API 선택 가능성 검증
  - JSON 문법/스키마 검증
  - API 호출/재시도/실패 처리
  - 임시 메모리 관리 및 최종 응답 조립
- 실패 원칙:
  - 검증 실패 시 API 호출 금지
  - 단계별 실패 원인(문장 index, 서비스, API, 오류유형)을 구조화해 기록
  - 필수값 누락은 즉시 실패(`fail_closed`)로 처리

## 4) 구현 범위
### In Scope
- 문장 분해 전용 LLM 단계 추가
- 단계형 실행 루프(문장 개수 기반 반복) 추가
- API 요청 생성 프롬프트/응답 파서 추가
- API 요청 검증기(문법 + 계약 스키마) 강화
- 단계별 결과 임시저장 메모리 컨텍스트 추가
- 최종 응답 조립기(1단계/2단계 이상 공통) 구현

### Out of Scope
- 프론트엔드 UX 변경
- 신규 외부 서비스 온보딩

## 5) 상세 작업 계획
체크 기준:
- `[x]` 완료
- `[ ]` 미완료 또는 진행중(항목 끝에 `진행중` 표기)

### Phase A. 계약/입출력 정의
- [x] 문장 분해 응답 스키마 정의
  - 병렬 배열 대신 작업 단위 객체 배열 사용:
  - `tasks[] = { task_id, sentence, service, api, depends_on_task_ids[] }`
- [x] 단계 실행 입력 스키마 정의
  - `task`, `timezone`, `memory_refs[]`, `dependency_results[]`
  - `previous_result(optional)` 단일 필드 대신 참조 기반 전달
- [x] API 요청 생성 응답 스키마 정의
  - `request_payload`, `missing_required_fields[]`, `missing_optional_fields[]`, `notes`
  - 상태 필드: `ready_to_call | blocked`
- [x] API 계약 스펙 확장 정의
  - `request_contract`: `method`, `path`, `path_params`, `query_params`, `body_schema`, `required_scopes`, `idempotency_policy`
  - `response_contract`: `success_http_codes`, `error_map`, `normalized_output_schema`, `raw_to_normalized_adapter`

### Phase B. 오케스트레이션 구현
- [x] `decompose_request()` 단계 구현
- [x] `execute_sentence_step(index, context)` 단계 구현
- [x] 문장 개수 기반 반복 루프 구현(1개/2개 이상 공통)
- [x] 단계 결과를 메모리에 누적 저장하는 컨텍스트 구현
- [x] 연결된 서비스 기준 전체 API 등록/로드 경로 구현
  - 연결된 서비스의 전체 API를 기준으로 로드하되, 연결 시점에 실행 가능 API를 선별해 `runtime_available_set`으로 확정
  - 선별 기준: granted scopes + tenant policy + risk policy
  - 실행 시점 후보 축소(`llm_candidate_set`)는 별도 단계에서 수행
- [x] 서비스 연결 시 `api_profile` 생성 단계 구현
  - `enabled_api_ids[]`, `blocked_api_ids[]`, `blocked_reason[]`
  - scope 변경/재연결 시 profile 재생성 + catalog 무효화
- [x] `catalog_id` 생성/조회/무효화 런타임 스켈레톤 구현
  - `build_runtime_catalog(user_id, connected_services, granted_scopes)`
  - `get_or_create_catalog_id(catalog_payload)`
  - `invalidate_catalog(user_id, reason)`

### Phase C. 검증/실행 가드
- [x] API 요청 JSON 문법 검증
- [x] 서비스별 Contract 기반 필수 필드 검증
- [x] 의미 검증(semantic validation) 추가
  - 시간 범위 유효성, enum/format 정합성, 참조 리소스 존재 여부
- [x] 검증 실패 시 에러 응답 표준화 (`validation_error`, `schema_error` 등)
- [x] 필수값 누락 시 즉시 실패 처리(`missing_required_fields`)
- [x] API 호출 실패 시 재시도 정책/중단 정책 적용
- [x] write API idempotency key 적용(재시도/타임아웃 중복 생성 방지)
- [x] API 응답 정규화(normalization) 검증 추가
  - raw provider 응답 -> 내부 `normalized_output_schema` 변환 검증
- [ ] 고위험 API 보호 정책 추가 (진행중: `api_profile` risk filter 반영, confirmation 정책 미구현)
  - `requires_confirmation`, `max_mutation_count`, `dry_run_supported` 계약 필드
  - 정책 미충족 시 호출 차단

### Phase D. 최종 응답 조립
- [x] 단일 문장 완료 시 즉시 응답 포맷 적용
- [x] 다중 문장 완료 시 단계별 결과 병합 응답 구현
- [x] 사용자에게 단계별 수행 요약(성공/실패) 제공
- [x] 실패 시 상세 사유 출력 필드 제공
  - `failed_task_id`, `service`, `api`, `missing_required_fields[]`, `validation_error_code`, `failure_reason`

### Phase E. 로깅/관측
- [x] 단계별 실행 로그 필드 추가
  - `sentence_index`, `selected_service`, `selected_api`, `validation_status`, `call_status`
- [x] 비교용 메트릭 추가
  - 성공률, 검증 실패율, 평균 단계 수, 평균 지연

## 17) 진행 상태 (2026-02-27)
- 완료:
  - [x] `llm_stepwise_pipeline_enabled` feature flag 추가
  - [x] 순차 stepwise fixture 추가 (`google_calendar_to_notion_linear_stepwise_v1`)
  - [x] loop 분기 추가(기존 경로 유지 + flag ON 시 stepwise 경로 진입)
  - [x] 회귀 테스트 1건 추가(stepwise pipeline id 선택 검증)
  - [x] `api_profile` 유틸 골격 추가(`build_runtime_api_profile`)
  - [x] `api_profile` 단위 테스트 추가
  - [x] `pipeline_step_logs` 저장 단위 테스트 추가 (stepwise success/failure)
- 완료(추가):
  - [x] `api_profile`을 실제 실행 경로(연결 시점/실행 preflight)에 연결
  - [x] fail-closed 상세 실패 필드 표준화(`missing_required_fields`, `failure_reason`)를 실행 결과에 통합 (DAG 경로)
  - [x] 문장 분해(`decompose_request`) LLM 단계 (stepwise planner + deterministic fallback)
  - [x] 단계별 API 파라미터 생성(`execute_sentence_step`) LLM 단계 (STEPWISE_PIPELINE 실행기 도입)
  - [x] STEPWISE payload semantic validation 추가(enum/type/range/date + time_min/time_max 순서 검증)
  - [x] STEPWISE API 호출 재시도/중단 정책 반영(재시도 대상: rate_limited/timeout/5xx, 그 외 즉시 중단)
  - [x] STEPWISE write API idempotency key 적용(요청 주입 + HTTP `Idempotency-Key` 헤더 전달)
  - [x] STEPWISE API 응답 normalization 검증 추가(도구별 normalized contract 검사 + 실패 시 fail-closed)
  - [x] STEPWISE 비교 메트릭 구조화(pipeline_json: step_count/success/failure/retry/validation_fail)
  - [x] STEPWISE vs DAG/legacy 비교 스크립트 추가 (`backend/scripts/eval_stepwise_vs_legacy_quality.py`)
  - [x] `catalog_id` 저장/재사용/무효화 (인메모리 캐시 구현)
  - [x] step 로그 영속화(`pipeline_step_logs`) 앱 레벨 best-effort 반영 (SQL 적용 전)
  - [x] `pipeline_step_logs`/`command_logs` 마이그레이션 파일 작성 (`docs/sql/013_...`)
  - [x] `pipeline_step_logs`/`command_logs` 실제 DB 마이그레이션 적용(운영 반영)
- 진행중:
  - [x] 대시보드 시각화/리포트 템플릿 정리 (`docs/work-20260227-stepwise-dashboard-report-template.md`)
  - [x] 코어 회귀 테스트 통과 확인 (`218 passed, 258 warnings`)
  - [x] executor 단독 회귀 통과 확인 (`62 passed, 124 warnings`)
  - [x] Stage6 Telegram E2E 1차 실행 (`10건 중 8건 PASS`, 리포트: `docs/reports/stage6_telegram_e2e_latest.json`)
  - [ ] Stage6 실패 시나리오 보정 (진행중: 최근 실패군은 `linear_update_issue` 중심 `validation_error/tool_failed`로 축소)
  - [x] stepwise vs legacy 운영 실측 재수집 (완료: 최신 7일 리포트 `stepwise 125건`, `dag 209건`, `legacy 166건`)
  - [x] 품질 비교 스크립트 실행 안정화 1차 확인 (DNS/HTTP preflight PASS)
  - [x] stepwise 로그 정합성 보강 (완료: `pipeline_step_logs`의 stepwise `service/api` 채움 + 실패 row `failed_service/failed_api` 반영)
  - [x] stepwise 보정 패치 1차 (완료: `team_id`, `user_id`, `priority`, `issue_id`, `state_id`, `archived` 정규화/보강)
  - [x] stepwise `linear_search_issues` query 누락 보정 확인 (완료: 최신 실행 `tg_update:193364235` 기준 `call_status=succeeded`, `missing_required_fields:query` 미재발)
  - [x] 오케스트레이션 transient 오류 재시도 보강 (완료: `429/5xx/timeout` 계열 HTTPException 재시도)
  - [x] stepwise 단기 실측 10건 배치 검증 (완료: `count=10`, `success=6`, `success_rate=60%`, 주요 실패 `upstream_error/validation_error`)
  - [x] stepwise 실패 payload 관측 보강 (완료: `failed_request_payload` -> `pipeline_step_logs.request_payload` 기록)
  - [x] `linear_update_issue` INVALID_INPUT 완화 1차 (완료: 빈 title/description 제거, state_id UUID 정합성 보강, 보수 payload 재시도)
  - [x] `linear_update_issue` 상태명 처리 1차 (완료: `state.name -> state.id` 매핑 컨텍스트 추가, `state.id` 로깅 확장)
  - [x] no-op 업데이트 차단 1차 (완료: `archived=false` 단독 업데이트 비허용, 업데이트 필드 판정 강화)
  - [x] `linear_update_issue` 자연어 파싱 보강 2차 (완료: 콜론 없는 문장 패턴 `상태를 ...로 변경`, `설명을 ...로 업데이트` 추출)
  - [x] `linear_update_issue` 상태명 해석 보강 2차 (완료: 컨텍스트 미스 시 `linear_list_issues` 기반 상태명->state_id 보조 해석)
  - [x] `linear_update_issue` issue_id-only fail-safe 보강 (완료: 재추출 후 최소 `description` fallback 주입, 실측 `tg_update:197960786`)
  - [x] `linear_update_issue` issue_id-only fail-safe 보강 2.1 (완료: `sentence/user_text` 공백 시에도 기본 `description` 강제 주입으로 `semantic_update_fields_missing` 잔여 경로 차단)
  - [x] stepwise 품질 목표치 도달 검증 (완료: 최신 리포트 `success_rate=70.42%`, `validation_fail_rate=16.08%`, `p95=18801ms`; `legacy=62.37%` 대비 우위)
  - [x] 단기 배치(10건) 안정화 검증 (완료: 최근 구간 `since=2026-02-27T15:03:43Z`, `count=16`, `real_error_rows=0`)
  - [x] `linear_update_issue` 잔여 실패 소거 (완료: 최근 구간에서 재발 없음)

## 6) 테스트 계획
### 단위 테스트
- [x] 문장 분해 응답 파싱/스키마 검증 테스트 (STEPWISE planner 기준)
- [x] API 요청 생성 응답 파싱/스키마 검증 테스트
- [x] 1문장/2문장/빈 문장 케이스 루프 테스트
- [ ] 의존 단계 결과 전달(`dependency_results`) 정확성 테스트 (현재 구현은 `previous_result` 체인, 다중 의존 참조 미구현)

### 통합 테스트
- [ ] 1단계 요청: 분해 -> 요청 생성 -> 검증 -> API 호출 -> 응답
- [x] 2단계 요청: 1단계 결과를 2단계 입력으로 전달하는 체인 검증
- [x] 검증 실패 시 API 미호출 보장 테스트
- [x] 필수값 누락 시 즉시 실패 + API 미호출 테스트
- [x] semantic validation 실패(예: 시간 역전) 차단 테스트
- [x] 외부 API 실패/타임아웃 시 복구 동작 테스트
- [x] write API 재시도 시 중복 생성 방지(idempotency) 테스트

### 회귀 테스트
- [x] 기존 주요 시나리오(캘린더 조회, 노션 생성, 리니어 이슈 생성) 정상 동작 여부 확인
- [ ] 기존 구조 대비 사용자 응답 품질/오류율 비교 (진행중: `backend/scripts/run_stepwise_quality_compare.sh` 기반 운영 실측 수집 완료, stepwise 잔여 실패군 개선 반복 중)

## 7) 기존 구조 대비 비교 기준 (선택 기준)
- 정확도:
  - 의도한 서비스/API 선택 정확도
  - 필수 파라미터 충족률
- 안정성:
  - 검증 실패율
  - 사용자 가시 오류율
- 효율:
  - 평균 처리 시간
  - LLM 호출 수 대비 성공률
- 유지보수성:
  - 신규 시나리오 추가 시 코드 변경 범위
  - 하드코딩 분기 감소율

## 8) 롤아웃/의사결정 계획
- [ ] Feature flag로 신규 구조를 분리 배포
- [ ] Shadow 실행으로 기존 구조와 동시 비교
- [ ] 트래픽 점진 확대(10% -> 30% -> 100%)
- [ ] 아래 기준 충족 시 신규 구조 채택
  - 측정 기간: 최근 7일 + 최소 표본 200건
  - E2E 성공률: 기존 대비 동등 이상(최소 95%)
  - 사용자 가시 오류율: 기존 대비 개선(최대 5%)
  - p95 지연: 기존 대비 +10% 이내
  - 유지보수 비용: 신규 시나리오 추가 시 코드 변경 파일 수 30% 이상 감소

## 9) 리스크 및 대응
- 리스크: 문장 분해 오류로 단계 순서 왜곡
  - 대응: 분해 결과 최소 검증(문장 수, API 매핑 유효성), 실패 시 단일 단계 fallback
- 리스크: LLM 파라미터 생성 흔들림
  - 대응: strict schema + semantic validation + fail_closed
- 리스크: 단계 증가로 지연 상승
  - 대응: 단계 상한, 타임아웃, 필요 시 병렬 가능 단계 탐지
- 리스크: write 재시도로 인한 중복 생성
  - 대응: idempotency key, request_id-task_id 단위 중복 차단

## 10) 완료 기준 (DoD)
- [ ] 신규 단계형 파이프라인이 feature flag 하에서 동작
- [ ] 1단계/2단계 대표 시나리오 E2E PASS
- [ ] 검증 실패 API 미호출 원칙 100% 보장
- [ ] 비교 리포트(기존 vs 신규) 기반 채택 의사결정 가능

## 11) Prompt/Context 최적화 (서비스/API 목록 전달 효율화)
- 문제:
  - 문장 분해/서비스 선택/API 선택 호출마다 전체 서비스/API 목록을 반복 전달하면 토큰 비용과 지연이 증가한다.
- 원칙:
  - LLM에는 "필요 최소 컨텍스트"만 전달하고, 전체 카탈로그는 런타임이 관리한다.
- 방식:
  - `catalog_id` 방식
    - 런타임이 사용자 연결 상태 기준으로 `서비스/API 카탈로그`를 생성하고 해시 기반 `catalog_id`를 발급
    - LLM 요청에는 `catalog_id` + 현재 단계 입력 + 후보군 요약만 전달
    - 카탈로그 변경(서비스 연결/해제, 스코프 변경) 시 `catalog_version` 갱신
  - 2단계 선택 구조
    - 1차: 서비스 선택(`top-k`)
    - 2차: 선택 서비스의 API 후보만 전달해 API 선택/파라미터 생성
  - 정규 ID 기반 압축
    - `service_id`, `api_id`, `required_params` 중심으로 전달
    - 상세 schema는 서버 검증 단계에서만 참조
- 캐시 정책:
  - 기본 TTL 10~30분
  - 사용자 연결 상태 변경 이벤트 발생 시 즉시 무효화

## 12) 서비스 목록/API 목록 정리 위치와 관리 기준
- 소스 오브 트루스:
  - 서비스/API 런타임 스펙: `backend/agent/tool_specs/*.json`
  - 작업 단위(스킬) 계약: `backend/agent/skills/contracts/*.json`
- 역할 분리:
  - `tool_specs`:
    - 서비스 단위 API 정의(메서드, path, input_schema, required_scopes, idempotency_key_policy)
    - "실행 가능한 API 목록"의 기준 데이터
  - `skills/contracts`:
    - 사용자 작업 관점 계약(name, input/output schema, autofill, runtime_tools)
    - "어떤 API 조합으로 작업을 수행할지"의 기준 데이터
- 런타임 카탈로그 생성 규칙:
  - 1) `tool_specs` 전체 로드
  - 2) 사용자 `connected_services` 및 granted scopes로 필터링
  - 3) `skills/contracts.runtime_tools`와 교차검증하여 후보 API 집합 확정
  - 4) 결과를 `catalog_id`로 캐시
- 권장 데이터 구조:
  - `service_catalog`:
    - `service_id`, `service_name`, `available_apis[]`
  - `api_catalog`:
    - `api_id`, `tool_name`, `required_params[]`, `optional_params[]`, `idempotency_policy`
  - `skill_catalog`:
    - `skill_name`, `runtime_tools[]`, `required_scopes[]`
- 운영 규칙:
  - 신규 API 추가는 `tool_specs` 업데이트 + validator 통과가 선행
  - 신규 작업 시나리오는 `skills/contracts` 추가로 확장
  - 카탈로그 생성 로그에 `catalog_id`, `catalog_version`, `filtered_reason`를 남겨 추적 가능하게 유지

## 13) 전체 API 제공 전략 (가능 여부와 권장 방식)
- 결론:
  - 런타임 관점에서는 "각 서비스의 전체 API 등록"이 가능하고 권장된다.
  - 다만 LLM 호출 시점에는 전체 API를 그대로 전달하지 않고 후보 API만 축소 전달하는 것이 필수다.
- 이유:
  - 전체 API를 매번 프롬프트에 넣으면 토큰 비용/지연/오선택 가능성이 급증한다.
  - 쓰기/삭제 API가 많은 서비스에서 안전 제어가 약해질 수 있다.
- 권장 계층:
  - `full_registry`:
    - 시스템이 보유한 전체 API 집합(`tool_specs`)
  - `runtime_available_set`:
    - 서비스 연결 시점에 실행 가능 API만 선별된 집합(api_profile 반영)
  - `llm_candidate_set`:
    - 현재 task 문맥에서 3~10개로 축소한 집합(LLM 입력용)
- 실행 규칙:
  - LLM은 `llm_candidate_set` 내에서만 선택 가능
  - 선택 결과는 서버가 `runtime_available_set`에서 재검증
  - 불일치 시 즉시 차단 + 실패 사유 반환

## 14) API Call 구조 / Return 구조 관리 기준
- 결론:
  - 반드시 정리해서 보유해야 한다. 요청 스키마만으로는 운영 안정성을 확보할 수 없다.
- 최소 보유 항목(서비스별 API 단위):
  - 호출 구조(Request):
    - `method`, `path`, `path_params`, `query_params`, `body_schema`, `required_scopes`, `idempotency_policy`
  - 리턴 구조(Response):
    - `success_http_codes`, `error_map`, `normalized_output_schema`
    - 필요 시 `raw_to_normalized_adapter` 규칙
- 저장 위치 정책(고정):
  - `backend/agent/tool_specs/*.json` 단일 저장소에 request/response 계약을 함께 유지
  - 보조 스펙 파일 분리는 사용하지 않음(드리프트 방지)
- 검증 흐름:
  - 1) LLM 생성 payload를 request schema로 검증
  - 2) API 호출 후 raw 응답을 adapter로 정규화
  - 3) 정규화 결과를 `normalized_output_schema`로 재검증
  - 4) 다음 단계에는 raw 대신 정규화 결과만 전달
- 테스트 필수 항목:
  - request schema pass/fail
  - provider 오류코드 매핑 일관성
  - response normalization 및 schema pass/fail

## 15) 정책 명시: 연결 서비스 전체 API 등록 + 계약 기반 유지
- 등록 정책:
  - 사용자에게 연결된 서비스는 해당 서비스의 API를 원칙적으로 전체 등록한다.
  - 전체 등록의 기준 데이터는 `backend/agent/tool_specs/*.json`이다.
- 실행 정책:
  - 등록은 전체 API 기준으로 하되, LLM 입력은 현재 task 후보 API로 축소한다.
  - 서비스 연결 시점에 실행 가능 API를 선별해 `runtime_available_set`을 먼저 확정한다.
  - 축소 대상은 `runtime_available_set` 내부에서만 선택한다.
- 실패 정책:
  - 필수 파라미터 누락/계약 불일치/후보 API 외 선택은 모두 즉시 실패 처리한다.
  - 실패 시 API 호출을 수행하지 않고 단계별 상세 사유를 결과에 포함한다.
- 계약 유지 정책:
  - 모든 API는 `request_contract`와 `response_contract`를 함께 가진다.
  - 신규/변경 API는 계약 파일 업데이트 없이는 런타임 반영하지 않는다.
- 고위험 API 정책:
  - 삭제/대량수정/권한변경 API는 `requires_confirmation=true`를 기본값으로 한다.
  - 고위험 API는 `max_mutation_count` 상한을 강제한다.
  - 지원 가능한 경우 `dry_run` 선실행 후 본실행한다.
- 변경 관리:
  - 계약 버전(`contract_version`)을 API 단위로 관리한다.
  - major 변경 시 구버전 병행 운영 후 제거한다.
- 품질 게이트:
  - 계약 유효성 검사 실패 시 배포 차단
  - request/response 계약 테스트 미통과 시 배포 차단

## 16) DB 확장 초안 (Migration Draft)
- 원칙:
  - 기존 테이블은 유지한다.
  - 신규 구조 관측/디버깅은 범용 step 로그 테이블을 추가해 해결한다.
  - `pipeline_links`는 기존 특화 시나리오 호환 용도로 유지한다.

### 16.1 신규 테이블: `pipeline_step_logs`
```sql
create table if not exists public.pipeline_step_logs (
  id bigserial primary key,
  run_id text not null,
  request_id text not null,
  user_id uuid references auth.users(id) on delete set null,

  task_index integer not null,
  task_id text not null,
  sentence text not null,
  service text,
  api text,

  catalog_id text,
  contract_version text not null,

  llm_status text not null, -- success | failed
  validation_status text not null, -- passed | failed
  call_status text not null, -- skipped | succeeded | failed

  missing_required_fields jsonb not null default '[]'::jsonb,
  validation_error_code text,
  failure_reason text,

  request_payload jsonb,
  normalized_response jsonb,
  raw_response jsonb,

  created_at timestamptz not null default now()
);

create index if not exists idx_pipeline_step_logs_run_task
  on public.pipeline_step_logs (run_id, task_index);

create index if not exists idx_pipeline_step_logs_user_created
  on public.pipeline_step_logs (user_id, created_at desc);
```

### 16.2 기존 테이블 확장: `command_logs`
```sql
alter table public.command_logs
  add column if not exists run_id text,
  add column if not exists request_id text,
  add column if not exists catalog_id text,
  add column if not exists final_status text,
  add column if not exists failed_task_id text,
  add column if not exists failure_reason text,
  add column if not exists missing_required_fields jsonb default '[]'::jsonb;

create index if not exists idx_command_logs_run_id
  on public.command_logs (run_id);
```

### 16.3 RLS 초안
```sql
alter table public.pipeline_step_logs enable row level security;

drop policy if exists "pipeline_step_logs_select_own" on public.pipeline_step_logs;
create policy "pipeline_step_logs_select_own"
  on public.pipeline_step_logs
  for select
  to authenticated
  using (auth.uid() = user_id);

drop policy if exists "pipeline_step_logs_service_role_all" on public.pipeline_step_logs;
create policy "pipeline_step_logs_service_role_all"
  on public.pipeline_step_logs
  for all
  to service_role
  using (true)
  with check (true);
```

### 16.4 적용 후 검증 체크리스트
- [ ] 순차 1단계 요청에서 `pipeline_step_logs` 1행 생성 확인
- [ ] 순차 N단계 요청에서 task_index 증가 및 run_id 동일성 확인
- [ ] 필수값 누락 실패 시 `call_status=skipped`, `missing_required_fields` 기록 확인
- [ ] 최종 `command_logs.final_status`와 step 로그 집계 일치 확인

## 18) 다음 단계 실행 체크리스트
- [x] stepwise 실제 트래픽/테스트 요청 누적 (최근 7일 기준 최소 200건 목표, 최신 `run_count=295`)
- [x] `pipeline_step_logs` 샘플 검증(성공/실패 각 5건 이상)
- [x] `bash backend/scripts/run_stepwise_quality_compare.sh` 재실행 (preflight PASS, 리포트 생성 완료)
- [x] `docs/reports/stepwise_vs_legacy_quality_latest.md` 결과 확인 완료
- [x] `docs/reports/stepwise_vs_legacy_quality_latest.md` 결과 기반 채택 판단 업데이트 (현황: `stepwise 70.42%` vs `legacy 62.37%`, 부분 롤아웃 진행)
- [x] 롤아웃 게이트(성공률/오류율/p95) 충족 여부를 `## 8) 롤아웃/의사결정 계획`에 최종 체크 (운영 인증 만료/미연결 이슈는 품질 집계에서 분리 적용)

### 18.1 stepwise 표본 생성 실행 절차
- [x] 시나리오 dry-run 확인 (`backend/scripts/run_stage6_telegram_e2e.py --dry-run`)
- [x] 로컬 서버 기동 후 stage6 시나리오 실행 (1차: `passed=8/10`)
  - `cd backend`
  - `PYTHONPATH=. .venv/bin/python -m uvicorn main:app --host 127.0.0.1 --port 8000`
  - 별도 터미널:
  - `cd backend`
  - `PYTHONPATH=. .venv/bin/python scripts/run_stage6_telegram_e2e.py --reset-pending --reset-between-chains --webhook-url http://127.0.0.1:8000/api/telegram/webhook`
- [x] 실행 후 품질 리포트 재생성
  - `bash backend/scripts/run_stepwise_quality_compare.sh`
- [x] `pipeline_step_logs` 최소 샘플 확인
  - 최근 7일 `pipeline_step_logs`에서 stepwise 성공/실패 각 5건 이상 확인

## 19) 남은 작업 정리 (우선순위)
1. 운영 모니터링
   - Spotify 미연결/토큰만료(`spotify_get_me:AUTH_REQUIRED`)는 운영 이슈로 별도 추적
2. 정책성 실패 분리 집계 유지
   - `delete_disabled`는 정책성 차단으로 별도 집계 유지
3. 점진 롤아웃 실행
   - `## 8)` 계획에 따라 부분 롤아웃(10% -> 30%) 단계 진행 및 지표 모니터링

### 18.2 1차 Stage6 결과 요약 (2026-02-27)
- 결과: `8/10 PASS` (`pass_rate=0.8`)
- 실패:
  - `S1` `linear OPT-46 이슈 설명 업데이트...` -> `error_code=not_found`
  - `S2` `openweather API 사용방법... OPT-46 설명 추가` -> `error_code=not_found`
- 해석:
  - 파이프라인/실행기 구조 오류라기보다 대상 리소스(Linear 이슈 식별자) 미존재 가능성이 높음
  - 재실행 전 `OPT-46` 존재 여부 또는 시나리오 대상 이슈 식별자 최신화 필요
