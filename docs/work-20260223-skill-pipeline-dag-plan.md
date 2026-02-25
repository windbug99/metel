# Skill Pipeline DAG 에이전트화 작업 계획 (2026-02-23)

## 0) 진행 체크리스트 (업데이트: 2026-02-25)
- [x] 새 작업 브랜치 생성 (`feature-20260223-skill-pipeline-dag-impl`)
- [x] Pipeline DSL 스키마/기본 제약 반영 (`backend/agent/pipeline_dsl_schema.json`)
- [x] DAG 런타임 MVP 추가 (`backend/agent/pipeline_dag.py`)
- [x] `when` 미니문법 평가기 추가 (`evaluate_when`)
- [x] `$ref` resolver 추가 (`resolve_ref`)
- [x] `for_each` 순차 fan-out + `verify` 노드 실행 지원
- [x] executor에 `PIPELINE_DAG` 어댑터 연결 (`backend/agent/executor.py`)
- [x] 실패 응답 계약 필드 1차 반영 (`failed_item_ref`, `failed_step`, `reason`, `retry_hint`, `compensation_status`)
- [x] orchestrator에서 대표 시나리오를 DAG로 컴파일하는 진입 경로 추가
- [x] Transform LLM JSON schema 보정 재시도(최대 2회) 구현
- [x] Google Calendar -> Notion -> Linear 데모 파이프라인 fixture/E2E 연결
- [x] all-or-nothing 보상 트랜잭션(Saga) 적용 (1차: item 실패 시 역순 보상 훅/상태 반영)
- [x] write idempotency key 강제 및 중복 생성 차단 (1차: 동일 payload mutation 재호출 시 결과 재사용)
- [x] DAG 품질 리포트/게이트 스크립트 추가 (`eval_dag_quality.py`, `run_dag_quality_gate.sh`)
- [x] 운영 루프에 DAG 게이트 통합 및 정책 추천 병합 적용 (`run_hybrid_learning_loop.sh`, `apply_agent_policy_recommendations.py`)
- [x] `pipeline_links` 영속 매핑 구현 (SQL + DAG 성공 시 upsert 연결)
- [x] 실패/보상 상태를 `pipeline_links.status`로 동기화 (`failed|manual_required`)
- [x] `pipeline_links` 실패 원인 컬럼 확장 (`error_code`, `compensation_status`) 및 저장 연동
- [x] `pipeline_links` 조회 API 추가 (`GET /api/pipeline-links/recent`)
- [x] `pipeline_links` 조회 API cursor pagination 추가 (`cursor_updated_at`, `next_cursor_updated_at`)
- [x] `dag_quality`에 `pipeline_links.error_code` 분포 지표 추가
- [x] DAG write allowlist + OAuth scope fail-closed 검증 추가 (`executor` policy guard, `oauth_tokens.granted_scopes`)
- [x] OAuth `granted_scopes` 백필 스크립트 추가 (`backend/scripts/backfill_oauth_granted_scopes.py`)
- [x] 게이트/백필 스크립트 데이터소스 오류 진단 출력 개선 (`SUPABASE_URL`, host, 네트워크 점검 힌트)
- [x] Supabase 연결 프리플라이트 스크립트 추가 (`backend/scripts/check_supabase_connectivity.py`)
- [x] 품질 게이트 스크립트에 Supabase 프리체크 내장 (`run_autonomous_gate.sh`, `run_dag_quality_gate.sh`)
- [x] 스테이징 스모크 자동 검증 스크립트 추가 (`backend/scripts/check_dag_smoke_result.py`)
- [x] `agent.loop` 경로에 calendar->notion->linear DAG fast-path 연결 (`plan_source=dag_template`)
- [x] DAG 실패 시 텔레그램 로그에 `dag_pipeline=1`/`dag_reason` 태깅 보강
- [x] OAuth scope alias 정규화(google `calendar.readonly` URL -> `calendar.read`) 적용
- [x] 스모크 안정화: calendar/notion/linear 노드 timeout/retry 상향 (`pipeline_fixtures`)
- [x] 스모크 안정화: calendar 조회 fan-out 부하 제한(`google.list_today.max_results=1`)
- [x] 스모크 실패 원인 수정: `google.list_today` 입력에 `calendar_id=primary` 기본값 적용
- [x] 스모크 실패 원인 수정: Google 응답 `items/summary` -> `events/title` 정규화 + `description` 기본값 보강
- [x] 스모크 실패 원인 수정: `notion.page_create(title/body)` -> `notion_create_page(parent/properties/children)` payload 매핑
- [x] 스모크 실패 원인 수정: `linear.issue_create.team_ref` -> `team_id` 자동 해석(`linear_list_teams`)
- [x] 배포 후 반복 검증 자동화 스크립트 추가 (`backend/scripts/run_dag_smoke_cycle.sh`)
- [x] 반복 검증 자동화 고도화: webhook 자동 주입 + 최신 로그 기준 스모크 판정 (`send_telegram_webhook_text.py`, `check_dag_smoke_result.py`, `run_dag_smoke_cycle.sh`)

## 0.1) 배포 전 필수 체크리스트 (DAG)
- [x] DB 마이그레이션 적용
  - `docs/sql/009_create_pipeline_links_table.sql`
  - `docs/sql/010_add_pipeline_links_error_columns.sql`
  - `docs/sql/011_add_oauth_tokens_granted_scopes.sql`
- [x] OAuth 기존 토큰 `granted_scopes` 백필 적용
  - dry-run: `cd backend && . .venv/bin/activate && PYTHONPATH=. python scripts/backfill_oauth_granted_scopes.py --limit 1000`
  - apply: `cd backend && . .venv/bin/activate && PYTHONPATH=. python scripts/backfill_oauth_granted_scopes.py --apply --limit 1000`
- [x] DAG 핵심 회귀 테스트 통과
  - `cd backend && . .venv/bin/activate && PYTHONPATH=. pytest -q tests/test_pipeline_dag.py tests/test_pipeline_dag_adapter.py tests/test_pipeline_fixture_e2e.py tests/test_pipeline_links.py tests/test_pipeline_links_route.py tests/test_eval_dag_quality.py tests/test_apply_policy_recommendations.py`
- [ ] 운영 품질 게이트 통과
  - `cd backend && . .venv/bin/activate && ./scripts/run_autonomous_gate.sh`
  - `cd backend && . .venv/bin/activate && ./scripts/run_dag_quality_gate.sh`
  - 현재 상태(2026-02-25): `autonomous=FAIL`, `dag=PASS`
- [x] Supabase 연결 프리체크 PASS
  - `cd backend && . .venv/bin/activate && PYTHONPATH=. python scripts/check_supabase_connectivity.py --timeout-sec 5`
- [x] 스테이징 스모크 시나리오 1회 수행
  - 요청: `구글캘린더 오늘 회의를 notion 페이지로 만들고 linear 이슈로 등록해줘`
  - 확인:
    - `command_logs.detail`에 `dag_pipeline=1`, `pipeline_run_id`
    - `pipeline_links`에 `status=succeeded` row 생성
    - `docs/reports/dag_quality_latest.json` 생성 및 `verdict=PASS`
  - 자동 검증: `cd backend && . .venv/bin/activate && PYTHONPATH=. python scripts/check_dag_smoke_result.py --limit 100`
  - 반복 자동 검증: `cd backend && . .venv/bin/activate && ATTEMPTS=8 SLEEP_SEC=15 ./scripts/run_dag_smoke_cycle.sh`
- [x] 프리배포 자동 점검 스크립트 추가
  - `backend/scripts/predeploy_dag_checklist.sh`
  - 실행: `cd backend && . .venv/bin/activate && ./scripts/predeploy_dag_checklist.sh`

### 실행 메모 (2026-02-25)
- Supabase 연결 확인 완료
  - `check_supabase_connectivity.py`: `dns=OK`, `http status=200`, `verdict=PASS`
- OAuth `granted_scopes` 백필 적용 완료
  - `scanned=5`, `candidates=3`, `updated=3`
- 배포 후 스모크 사이클 성공 1회 확인
  - `run_dag_smoke_cycle.sh`: `verdict=PASS`
  - `pipeline_run_id=prun_95805728037347ee`, `succeeded_pipeline_links=1`
- 스모크 자동화 보강 완료
  - `check_dag_smoke_result.py --since-iso` 추가로 과거 성공 로그 재사용 방지
  - `run_dag_smoke_cycle.sh`에 `AUTO_INJECT_WEBHOOK=1` 모드 추가(웹훅 텍스트 자동 주입)
- 요청문 다양성 자동화 보강 완료
  - `run_dag_smoke_cycle.sh`: `SMOKE_TEXTS`/`SMOKE_TEXTS_FILE` 순환 주입 지원
  - `scripts/smoke_prompts_10.txt`: 10종 요청문 세트 추가
- 최신 게이트 결과 (2026-02-25)
  - `run_dag_quality_gate.sh`: `verdict=PASS`
    - sample size `53/20`
    - `DSL_REF_NOT_FOUND rate=3.8%` (target `<=5%`)
    - `COMPENSATION_FAILED rate=1.9%` (target `<=2%`)
  - `check_dag_smoke_result.py --limit 100`: `verdict=PASS`
    - `pipeline_run_id=prun_cb0c4f49000d4e1b`
    - `succeeded_pipeline_links=1`
  - `run_autonomous_gate.sh`: `verdict=FAIL`
    - sample size `30/20`
    - `autonomous_attempt_rate=0.0%` (0/30)
    - `autonomous_success_rate=0.0%` (0/0)
    - `autonomous_success_over_attempt=0.0%` (0/0)
- 현재 남은 블로커
  - `run_autonomous_gate.sh`: `verdict=FAIL`
    - 최근 30건에서 autonomous 경로 시도 자체가 없음(`autonomous_attempt_rate=0.0%`)
    - 게이트 실패는 품질 저하보다 "샘플 구성 불일치(autonomous 트래픽 부재)" 성격
  - `운영 품질 게이트 통과` 체크박스는 autonomous 게이트 미통과로 인해 유지

## 1) 배경과 목표
- 목표: 연속적인 SKILL 사용 요청을 안정적으로 처리하는 에이전트 런타임 구축
- 대표 시나리오:
  - "구글캘린더에서 오늘 회의일정 조회"
  - "각 회의마다 노션에 회의록 초안 생성"
  - "각 회의를 리니어 이슈로 등록"
- 핵심 원칙:
  - LLM은 `계획 컴파일러`와 `중간 데이터 변환기` 역할만 수행
  - 실행은 deterministic orchestrator가 담당

## 2) 현재 metel 구조 요약
- 이미 보유한 강점
  - Task 기반 계획 구조(`TOOL|LLM`, `depends_on`, `output_schema`)
  - 계획 계약 검증(`plan_contract`) 및 실패 시 fail-closed
  - deterministic task 실행 경로와 autonomous loop 동시 보유
  - skill contract 레이어(`name/version/input_schema/output_schema/runtime_tools`)
- 현재 한계
  - 일반화된 Pipeline DSL(`nodes/edges/when`) 부재
  - `when` 조건식/분기 실행 미지원
  - `$ref`(예: `$n1.items[0].id`) 기반 아티팩트 참조 해석기 부재
  - idempotency 정책 필드는 있으나 실행 강제 약함
  - 노드 공통 retry 정책표/오류코드별 표준 재시도 정책 부재
  - 다건 처리 fan-out/fan-in 패턴 부재

## 3) 제안 아키텍처
## 3.1 실행 모델
- A+B 하이브리드
  - A: LLM 컴파일 단계에서 작은 DAG(Pipeline DSL) 생성
  - B: 실행 단계는 deterministic DAG executor
- LLM 역할 제한
  - Planner/Compiler LLM: 사용자 요청 -> DSL
  - Transform LLM: 텍스트/결과 -> 구조화 JSON

## 3.2 Pipeline DSL (초기 스코프)
- 엔티티
  - `nodes`: skill 또는 llm transform invocation
  - `edges`: 노드 출력 -> 다음 노드 입력 매핑
  - `when`: 안전한 조건식(JSONPath + 비교 연산)
  - `limits`: max_nodes, timeout, retry, budget
- 제약
  - 최대 노드 수 기본 6 (for_each 반복 실행은 동일 노드의 item-level 반복으로 처리)
  - write skill allowlist 기반 제어
  - 임의 코드 실행 금지

## 3.3 실행기 (DAG Orchestrator)
- 핵심 책임
  - DAG 유효성/순환 검증
  - 위상정렬 실행
  - artifacts 저장 및 참조 해석
  - 노드 단위 timeout/retry/cancel
  - trace/log 표준화

## 4) 다건 자동화(핵심 시나리오) 설계
- 필요 기능
  - `for_each` fan-out: calendar events 배열 아이템별 하위 노드 반복
  - fan-in 집계: 전체 성공/실패 집계 및 요약
- 권장 처리 정책
  - all-or-nothing: 일부 실패 허용하지 않음
  - 외부 서비스 트랜잭션 한계를 고려해 Saga 보상 수행 후 실패 반환
    - 예: Notion 생성 성공 후 Linear 생성 실패 시 Notion 페이지 아카이브 보상 시도
  - 재실행은 전체 동기화 기준으로 수행
- idempotency key 기본안
  - 서비스별 기준을 우선하되 metel 공통 키를 함께 사용
  - `hash(user_id + calendar_event_id + action_type + target_workspace)`
- 실행 순서/동시성 기본값
  - 초기 모드: fan-out 순차 처리
  - 안정화 이후 제한 병렬 전환 가능
  - 병렬 전환 시 동시성 제한: `global=10`, `google=5`, `notion=3`, `linear=3`

## 5) 신뢰성/안전 장치
- Budget 2층 구조
  - pipeline budget: 총 시간, 총 tool_calls, 총 llm_calls
  - node budget: timeout/retry
- 검증 전략
  - write 노드 뒤 100% 강한 검증
  - 외부 API eventual consistency 대응을 위한 짧은 백오프 재조회 포함
  - 최종 fan-in 검증:
    - 입력 회의 수 == 생성 Notion 문서 수 == 생성 Linear 이슈 수(허용 오차 0)
- LLM 파라미터 자동 보정(필수)
  - required slot은 사용자 추가 입력 없이 LLM autofill로 100% 채우는 것을 기본 정책으로 함
  - autofill 실패(스키마 불일치/필수 슬롯 미충족) 시 즉시 전체 실패 처리
  - 사용자에게 실패 사유와 재시도 가이드를 반환
  - 실패 사유 문장은 LLM이 명확하게 작성하되, 근거 오류코드는 executor가 제공
- 중복 방지
  - 동일 payload mutation 반복 호출 차단
  - idempotency key 없는 write 실행 금지(점진 도입)

## 5.1 실패 응답 계약 (all-or-nothing)
- 한 문장 요청에서 단 1개 item/step이라도 실패하면 전체 실패
- 사용자 피드백 표준 필드
  - `failed_item_ref`: 실패한 회의/대상 식별자(예: calendar_event_id)
  - `failed_step`: 실패한 스킬/노드명(예: `linear.issue_create`)
  - `error_code`: 분류 가능한 오류코드
  - `reason`: 사용자 친화적 실패 설명
  - `retry_hint`: 재시도/조치 가이드
  - `compensation_status`: 보상 처리 결과(`completed|failed|manual_required`)
- 내부 기록 필드(로그/관측)
  - `pipeline_run_id`, `node_id`, `attempt`, `upstream_status`, `upstream_message`

## 6) 단계별 구현 계획
## Phase 1 (MVP: 1~2주)
- Pipeline DSL v0 추가
  - nodes/depends_on/when(기본 비교식)/limits
- DSL validator 추가
  - 스키마 검증, skill 존재성, 서비스 권한/allowlist 검증
- executor 확장
  - 현재 task orchestration 경로 재사용 + DSL 노드 실행 어댑터
- Transform LLM JSON schema 강제
  - 실패 시 1~2회 보정 재시도 후에도 required slot 미충족이면 전체 실패

### 완료 기준
- 단건 3~5 step 파이프라인(예: read->llm->write) 안정 실행
- 계약 위반 플랜 fail-closed

## Phase 2 (핵심 확장: 1~2주)
- fan-out/fan-in(`for_each`) 추가
- all-or-nothing 실행 + 보상 트랜잭션(Saga) 추가
- write 노드 idempotency 강제

### 완료 기준
- "오늘 회의 N건 -> 노션 N건 -> 리니어 N건" 시나리오 E2E 통과
- 재실행 시 중복 생성 0건

## Phase 3 (운영 안정화: 1주+)
- 오류코드별 retry policy 테이블화
- 상세 observability(event_id 단위 trace)
- 자동 롤백/보상 전략(선택)

### 완료 기준
- 실패 원인 자동 분류 가능
- 운영 리포트에서 재시도 효율/중복 방지 효과 확인 가능

## 7) 데이터/로그 스키마 보강
- execution artifacts
  - `pipeline_run_id`, `node_id`, `node_type`, `status`, `attempt`, `duration_ms`
  - `idempotency_key`, `external_ref`(calendar_event_id 등)
- 요약 지표
  - `fanout_total`, `fanout_success`, `fanout_failed`, `verification_reason`
- 영속 매핑 테이블(신규)
  - `pipeline_links(user_id, event_id, notion_page_id, linear_issue_id, run_id, status, updated_at)`
  - 목적: 전체 동기화/재실행/보상 처리 시 참조 무결성 유지

## 8) 테스트 전략
- 단위 테스트
  - DSL validator(허용/차단 케이스)
  - when 파서/평가기
  - ref resolver
  - idempotency 정책
- 통합 테스트
  - read->transform->write 체인
  - for_each fan-out + 단일 item 실패 시 전체 실패(all-or-nothing) 검증
  - LLM autofill 100% 충족 검증(required slot 미충족 시 즉시 실패)
  - 실패 피드백 계약 필드(`failed_item_ref`, `failed_step`, `reason`, `retry_hint`) 검증
- 회귀 테스트
  - 기존 planner/executor/autonomous 경로 비회귀 확인

## 9) 리스크와 대응
- 리스크: LLM 출력 편차로 플랜 불안정
  - 대응: DSL 강제 + validator fail-closed + rule synthesis fallback
- 리스크: 다건 처리에서 중복 생성
  - 대응: idempotency key 강제 + duplicate mutation block
- 리스크: 비용/지연 증가
  - 대응: 노드/파이프라인 budget, 검증 노드 선택적 적용

## 10) Decision Log (확정)
1. 실패 정책
- 일부 실패 허용하지 않음(all-or-nothing)
- 구현 방식: 실패 시 보상 수행 후 전체 실패 반환 + 사용자 실패 피드백 제공
- 실패 피드백 문장은 LLM이 명확하게 작성

2. 멱등성
- 기본적으로 각 서비스 기준을 따름
- 단, metel 공통 idempotency key를 추가해 교차 서비스 중복 생성 방지
- 멱등키 충돌 시 기존 결과 재사용(`idempotent success`)

3. 재실행
- 전체 동기화 방식으로 수행
- 실행 시작 시점 스냅샷 기준으로 동기화 범위 고정

4. 생성/업데이트 정책
- 사용자 의도 우선
  - 생성 요청은 생성
  - 업데이트 요청은 업데이트
- 모드 자동 전환 금지

5. 매핑 저장
- 현재 구조에 영속 매핑 테이블을 추가
- 권장: `pipeline_links` 테이블 도입(이벤트-노션-리니어 연결)

6. 타임존
- 대시보드에 타임존 설정 기능 추가
- 초기 기본값은 사용자 브라우저 타임존(IANA) 자동 설정
- 런타임 계산은 `users.timezone` 기준 사용

7. `when` 문법 범위
- 최소 문법만 허용
  - 형식: `left op right`
  - `left`: `$node.path`
  - `op`: `== != > >= < <= in`
  - `right`: string/number/bool/null/array literal
- 함수 호출/임의 코드/정규식 실행 금지

8. LLM Transform 실패 처리
- required slot 자동 보정 100% 목표
- 스키마 불일치 시 최대 2회 재시도
- 재시도 후 required slot 미충족이면 전체 실패 + 사용자 피드백 반환

9. 검증 정책
- 100% 검증 적용
- write 이후 즉시 검증 + 백오프 재조회

10. 예산 제한
- "무제한" 대신 운영 안전 최소 한도 적용
  - `max_nodes=6`
  - `max_fanout=50`
  - `max_tool_calls=200`
  - `pipeline_timeout_sec=300`

11. 동시성 제어
- 초기 릴리즈는 fan-out 순차 처리
- 안정화 이후 제한 병렬 전환 시 세마포어 적용
  - `global=10`, `google=5`, `notion=3`, `linear=3`

12. 권한/보안
- write skill allowlist
- 서비스별 OAuth scope 검사
- 사용자별 리소스 접근 경계 강제
- 감사 로그(생성/수정/삭제) 기록
- 민감정보 마스킹 로그 기본 적용

13. 시나리오 우선순위
- 현재 문서의 대표 시나리오를 우선 구현 대상으로 유지
- 제외 시나리오는 현 단계에서 별도 정의하지 않음

14. 릴리즈/게이트
- 권장 방식 수용(점진 rollout + 품질 게이트 기반)

15. 테스트 완료 기준
- 현재 수준의 기준 유지
- 단, 본 문서의 all-or-nothing/fan-out/autofill/실패 피드백 계약 검증은 최소 필수 세트로 포함

## 11) 구현 확정 요약 (추가 질문 반영)
1. 실패 시 보상 정책
- `보상 수행 후 실패 반환`으로 확정
2. 멱등키 충돌 정책
- `기존 결과 재사용(idempotent success)`으로 확정
3. 초기 fan-out 모드
- `순차`로 확정

## 12) 즉시 실행 항목 (다음 작업)
1. [x] DSL 스키마 초안 작성(JSONSchema)
2. [x] `when` 미니문법(연산자/허용 함수) 확정
3. [x] ref 문법(`$node.path`)과 resolver 구현
4. [x] executor에 DSL adapter 계층 추가
5. [x] Google Calendar -> Notion -> Linear 데모 파이프라인 fixture 추가

## 13) 구현 스펙 (DSL)
### 13.1 Pipeline DSL v1 (최소 스키마)
```json
{
  "pipeline_id": "string",
  "version": "1.0",
  "limits": {
    "max_nodes": 6,
    "max_fanout": 50,
    "max_tool_calls": 200,
    "pipeline_timeout_sec": 300
  },
  "nodes": [
    {
      "id": "n1",
      "type": "skill|llm_transform|for_each|verify",
      "name": "google_calendar.list_today",
      "depends_on": [],
      "input": {},
      "when": "$ctx.enabled == true",
      "retry": {"max_attempts": 1, "backoff_ms": 300},
      "timeout_sec": 20
    }
  ]
}
```

### 13.2 Node 타입 계약
| type | 목적 | 필수 필드 | 출력 계약 |
|---|---|---|---|
| `skill` | 외부 도구 실행 | `name`, `input` | skill `output_schema` 준수 |
| `llm_transform` | 슬롯/본문 구조화 | `input`, `output_schema` | JSON schema 100% 준수 |
| `for_each` | 배열 item 반복 | `source_ref`, `item_node_ids` | `item_results[]`, `item_count` |
| `verify` | 정합성/개수 검증 | `rules[]` | `pass`, `reason` |

### 13.3 Ref 문법
- 형식: `$<node_id>.<path>`
- 예시:
  - `$n1.events`
  - `$n2.result.issue_title`
  - `$item.calendar_event_id` (`for_each` 내부 전용)
- 미해결 ref는 즉시 실패(`DSL_REF_NOT_FOUND`)

### 13.4 `when` 미니문법
- 허용 형식: `left op right`
- `left`: `$node.path` 또는 `$item.path` 또는 `$ctx.path`
- `op`: `==`, `!=`, `>`, `>=`, `<`, `<=`, `in`
- `right`: string/number/bool/null/array literal
- 금지: 함수 호출, 정규식 실행, 임의 코드

## 14) 실행 상태전이 스펙
### 14.1 Pipeline 상태
| 현재 상태 | 이벤트 | 다음 상태 | 비고 |
|---|---|---|---|
| `pending` | 실행 시작 | `running` | run_id 발급 |
| `running` | 모든 노드 성공 | `succeeded` | verify 통과 필수 |
| `running` | 노드 실패 | `compensating` | all-or-nothing 정책 |
| `compensating` | 보상 완료 | `failed` | 사용자 실패 피드백 전송 |
| `compensating` | 보상 실패 | `manual_required` | 수동조치 필요 표시 |

### 14.2 Item 상태(`for_each`)
| 상태 | 의미 |
|---|---|
| `item_pending` | 실행 대기 |
| `item_running` | 실행 중 |
| `item_succeeded` | item 성공 |
| `item_failed` | item 실패(즉시 pipeline 보상 진입) |

## 15) 오류코드 및 재시도 정책
| 코드 | 발생 조건 | 재시도 | 사용자 피드백 |
|---|---|---|---|
| `DSL_VALIDATION_FAILED` | DSL 계약 위반 | 없음 | 요청 형식 오류 안내 |
| `DSL_REF_NOT_FOUND` | ref 해석 실패 | 없음 | 내부 참조 실패 안내 |
| `LLM_AUTOFILL_FAILED` | required slot 미충족 | 2회 | 누락 항목/재요청 가이드 |
| `TOOL_AUTH_ERROR` | OAuth/권한 오류 | 없음 | 서비스 재연동 안내 |
| `TOOL_RATE_LIMITED` | 429/쿼터 초과 | 1~2회 | 잠시 후 재시도 안내 |
| `TOOL_TIMEOUT` | 노드 timeout | 1회 | 일시적 지연 안내 |
| `VERIFY_COUNT_MISMATCH` | fan-in 정합성 실패 | 없음 | 일부 처리 누락 안내 |
| `COMPENSATION_FAILED` | 보상 실패 | 없음 | 수동 확인 필요 안내 |
| `PIPELINE_TIMEOUT` | 전체 timeout 초과 | 없음 | 요청 축소/재시도 안내 |

### 15.1 재시도 기본 규칙
- 기본: `skill` 노드만 재시도
- `llm_transform`은 schema 불일치 시에만 최대 2회 재시도
- `verify` 실패는 재시도하지 않고 즉시 실패
- `for_each`는 순차 처리, item 하나 실패 시 다음 item 실행 중단

## 16) 대표 파이프라인 템플릿
### 16.1 Google Calendar -> Notion -> Linear
1. `n1`: `google_calendar.list_today`
2. `n2`: `for_each` on `$n1.events`
3. `n2_1`: `llm_transform` (회의록 초안/이슈 payload 생성)
4. `n2_2`: `notion.page_create`
5. `n2_3`: `linear.issue_create`
6. `n3`: `verify` (입력 회의 수 == notion 생성 수 == linear 생성 수)

### 16.2 실패 피드백 예시 payload
```json
{
  "failed_item_ref": "cal_evt_20260224_0900",
  "failed_step": "linear.issue_create",
  "error_code": "TOOL_AUTH_ERROR",
  "reason": "리니어 인증이 만료되어 이슈를 생성할 수 없습니다.",
  "retry_hint": "리니어 연동을 다시 연결한 뒤 동일 요청을 재시도하세요.",
  "compensation_status": "completed"
}
```

## 17) 로그 기반 지속 최적화 루프 (운영 포함)
### 17.1 목표
- DAG 도입 이후에도 실패율/지연/검증 실패를 지속적으로 낮추기 위해, 로그 기반 정책 튜닝 루프를 상시 운영 체계에 포함한다.
- 모델 파인튜닝보다 먼저 실행 정책(재시도/예산/fallback/실행 모드)을 조정해 안정성을 우선 확보한다.
- 변경은 canary 승격/보류/롤백 규칙으로 통제해 운영 리스크를 최소화한다.

### 17.2 루프 범위(공통)
- 수집 대상 로그:
  - `command_logs`의 `status`, `error_code`, `verification_reason`, `plan_source`, `execution_mode`, `detail`
  - pipeline artifact의 `pipeline_run_id`, `node_id`, `duration_ms`, `attempt`, `idempotency_key`
- 필수 KPI:
  - `Tool/Pipeline Success Rate`
  - `verification_failed_rate`
  - `fallback_rate`
  - `p95_latency`
  - `fanout_failed_ratio`
- 데이터 보호:
  - 민감정보 마스킹 로그를 기본으로 유지
  - 사용자 원문/식별자는 최소 수집 원칙을 적용

### 17.3 운영 사이클 (평가 -> 결정 -> 적용 -> 롤백)
1. 평가(주기 실행)
- 자율/하이브리드 품질 게이트:
  - `cd backend && . .venv/bin/activate && ./scripts/run_autonomous_gate.sh`
  - 산출물: `docs/reports/agent_quality_latest.{md,json}`
- Skill V2 rollout 게이트:
  - `cd backend && DAYS=3 ./scripts/run_skill_v2_rollout_gate.sh`
  - 산출물: `docs/reports/skill_v2_rollout_latest.json`

2. 결정(승격/보류/롤백)
- Skill V2 전환 단계 결정:
  - `cd backend && . .venv/bin/activate && python scripts/decide_skill_v2_rollout.py --report-json ../docs/reports/skill_v2_rollout_latest.json --current-percent <0|10|30|60|100>`
- 자율/하이브리드 정책 추천:
  - `cd backend && . .venv/bin/activate && python scripts/apply_agent_policy_recommendations.py --from-json ../docs/reports/agent_quality_latest.json --env-file .env` (dry-run)

3. 적용(승인 후 제한 반영)
- 자율/하이브리드 정책 반영:
  - `cd backend && APPLY_POLICY=true ./scripts/run_hybrid_learning_loop.sh`
- Skill V2 전환 정책 반영:
  - `cd backend && . .venv/bin/activate && python scripts/apply_skill_v2_rollout_decision.py --decision-json ../docs/reports/skill_v2_rollout_decision_latest.json --env-file .env --apply`
- 원칙:
  - allowlist된 env 키만 변경
  - 기본은 dry-run, 운영자 승인 후 apply

4. 롤백(임계치 이탈 시 즉시)
- 아래 중 1개라도 충족 시 즉시 보류/롤백:
  - 성공률 급락(기준 대비 10%p 이상 하락)
  - auth/server 오류 급증(기준 대비 2배 이상)
  - p95 지연 급증(운영 임계치 초과)
- 조치:
  - `SKILL_RUNNER_V2_ENABLED=false` 또는 `SKILL_ROUTER_V2_ENABLED=false`
  - 필요 시 `LLM_HYBRID_EXECUTOR_FIRST=true`로 deterministic-first 강제

### 17.4 자동화 수준 권장
- 권장 기본값:
  - `자동 평가 + 자동 추천`, `수동 승인 + 자동 반영`
- 금지:
  - 임계치/근거 없이 자동 100% 승격
  - 승인 없는 즉시 정책 반영

### 17.5 DAG 전용 확장 항목(추가 구현)
- 신규 리포트(`dag_quality_latest.json`)를 도입해 아래 지표를 추가 평가:
  - `DSL_VALIDATION_FAILED` 비율
  - `DSL_REF_NOT_FOUND` 비율
  - `VERIFY_COUNT_MISMATCH` 비율
  - `COMPENSATION_FAILED` 비율
  - `idempotent_success_reuse_rate`
- DAG 품질 게이트 스크립트(예: `run_dag_quality_gate.sh`)를 추가해 기존 rollout 사이클에 병합한다.
