# Phase 3 Kickoff Backlog (2026-03-03)

기준:
- `docs/overhaul-20260302.md`
- `docs/phase2-status-20260303.md`

목표:
- MCP Gateway + Safe Execution Core에서
- AI Action Control Platform(Execution Control Platform)으로 전환 시작

## 1) Phase 3 최소 범위 (MVP)

이번 착수 범위는 아래 4개로 제한한다.

1. API Key별 세분 권한 정책
2. 고위험 작업 예외 허용 정책(키 단위)
3. Audit 로그 조회 API/기본 UI
4. Usage Dashboard 지표 확장(권한/정책 관점)

## 2) 백로그 (우선순위 순)

## P3-01. API Key Policy Schema

작업:
- `api_keys`에 정책 필드 추가(예: `policy_json`)
- 예시 정책:
  - `allow_high_risk: false`
  - `allowed_services: ["notion", "linear"]`
  - `allowed_tools: [...]` (기존 유지)
  - `deny_tools: [...]`

완료 기준:
- 키별 정책 저장/조회/수정 가능
- 잘못된 정책 입력은 validation 에러 반환

진행 상태(2026-03-03):
- 구현 완료: `api_keys.policy_json`(jsonb) 추가 및 API create/list/patch 반영
- validation 반영: `allow_high_risk`, `allowed_services`, `deny_tools`

## P3-02. Risk Gate 키별 예외 허용

작업:
- `risk_gate.py`에서 키 정책을 인자로 받아 판단
- 기본 차단 유지 + 키 정책으로 예외 허용
  - 예: `allow_high_risk=true`일 때 `notion_update_page(archived=true)` 허용

완료 기준:
- 기본값은 기존과 동일(차단)
- 정책이 있는 키에서만 선택 허용
- 로그에 `policy_decision` 기록

진행 상태(2026-03-03):
- 1차 구현 완료: `policy_json.allow_high_risk=true`일 때 Risk Gate 차단 해제
- 남은 작업: `policy_decision` 상세 로그 필드 추가

## P3-03. Tool Access Control 고도화

작업:
- `allowed_tools` + `deny_tools` 동시 지원
- 서비스 단위 allow/deny 추가
- 권한 불일치 에러 표준화 (`access_denied`, `service_not_allowed`)

완료 기준:
- 키별로 서비스/툴 권한 분리 동작
- 정책 충돌 시 일관된 우선순위 규칙 적용(deny 우선)

진행 상태(2026-03-03):
- 1차 구현 완료:
  - `list_tools`에서 `allowed_services`, `deny_tools` 필터 반영
  - `call_tool`에서 `deny_tools`/`allowed_services` 권한 차단 반영
  - 에러 코드: `access_denied`, `service_not_allowed`
- 남은 작업:
  - 감사 로그에 `policy_decision`/`policy_source` 세분 필드 추가

## P3-04. Audit API

작업:
- `/api/audit/events` 추가
- `tool_calls` 기반으로 아래 필드 포함:
  - actor(api_key/user)
  - action(tool_name)
  - decision(success/fail/policy_blocked)
  - error_code
  - timestamp

완료 기준:
- 최근 이벤트 조회 가능
- 필터(user/key/tool/status/date) 지원

진행 상태(2026-03-03):
- 구현 완료: `/api/audit/events` 추가
- 반영 필드: actor / action / decision / error_code / timestamp
- 필터 지원: status, tool_name, api_key_id, error_code, from, to

## P3-05. Audit UI (기본)

작업:
- Dashboard에 Audit 탭 또는 섹션 추가
- 최근 50개 이벤트 + 필터
- 정책 차단 이벤트 강조

완료 기준:
- 운영자가 누가 어떤 요청을 막혔는지 바로 확인 가능

진행 상태(2026-03-03):
- 1차 구현 완료: Dashboard에 Audit Events 섹션 추가
- 반영 항목:
  - 최근 이벤트 리스트(action/actor/outcome/error/timestamp)
  - 요약 카드(allowed/policy_blocked/access_denied/failed)

## P3-06. Usage Dashboard 확장

작업:
- 기존 24h 지표에 추가:
  - `access_denied_count`
  - `high_risk_allowed_count`
  - `policy_override_usage`

완료 기준:
- 정책 운영 상태를 대시보드에서 수치로 확인 가능

진행 상태(2026-03-03):
- 부분 완료:
  - `access_denied_count`는 Audit summary에서 확인 가능
  - 정책 차단/실패 관련 지표는 MCP Usage + Audit 영역에서 확인 가능
- 남은 작업:
  - `high_risk_allowed_count`, `policy_override_usage` 전용 지표 분리

## P3-07. Error Code/Policy Code 정리

작업:
- `error_codes.py`에 Phase 3 코드 추가
  - `access_denied`
  - `service_not_allowed`
  - `policy_conflict`

완료 기준:
- 권한/정책 오류가 tool execution 오류와 분리되어 식별 가능

진행 상태(2026-03-03):
- 구현 완료:
  - `error_codes.py`에 `policy_conflict` 코드 추가
  - API Key create/patch에서 정책 충돌 검증 및 `409 policy_conflict` 반환
  - 충돌 규칙:
    - `allowed_tools` ∩ `deny_tools` 금지
    - `allowed_tools`가 `allowed_services` 범위를 벗어나는 경우 금지

## P3-08. 테스트 게이트

작업:
- 단위 테스트 추가:
  - 키별 고위험 허용/차단
  - deny 우선순위
  - audit 조회 필터
- 회귀 스크립트에 포함

완료 기준:
- CI에서 Phase 3 핵심 정책 회귀 차단

진행 상태(2026-03-03):
- 구현 완료:
  - `test_api_keys_route.py`에 `policy_conflict` 회귀 테스트 추가
  - `test_audit_route.py`를 core regression 스크립트에 포함
  - `backend/scripts/run_phase3_regression.sh` 추가 (정책/감사 중심 회귀)
  - CI 워크플로우 `backend-phase3-regression.yml` 추가
    - backend: policy/audit 회귀 테스트
    - frontend: dashboard typecheck(`pnpm -s tsc --noEmit`)

## 3) 권장 구현 순서 (1~2주)

1주차:
1. P3-01 API Key policy schema
2. P3-02 Risk Gate 키별 예외
3. P3-03 Access Control 고도화

2주차:
1. P3-04 Audit API
2. P3-05 Audit UI
3. P3-06 Dashboard 지표 확장
4. P3-08 테스트 게이트

## 4) 즉시 착수 항목

- [x] SQL 마이그레이션 초안 작성 (`docs/sql/017_add_api_keys_policy_json.sql`)
- [x] `api_keys` 정책 필드 스키마 확정
- [x] `risk_gate.py` 인터페이스 확장 설계
- [x] `test_mcp_routes.py`에 정책 예외 케이스 스켈레톤 추가

## 5) Done 정의

- 키별 정책으로 위험 작업 허용/차단을 명확히 통제 가능
- 정책/권한 위반 이벤트가 감사 로그와 대시보드에서 즉시 식별 가능
- 배포 전 자동 테스트에서 정책 회귀를 차단 가능
