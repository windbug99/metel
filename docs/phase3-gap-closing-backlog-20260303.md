# Phase 3 Gap-Closing Backlog (Updated: 2026-03-03, post SQL 026 + audit org filter)

기준:
- `docs/overhaul-20260302.md`
- 현재 구현 코드 (`backend/app/routes/*`, `frontend/app/dashboard/page.tsx`)
- 운영 콘솔 요구사항 (Execution Control Platform)

목표:
- Phase3 요구사항을 운영 가능한 수준으로 마감

## 1) 현재 상태 요약

- 완료:
  - P3-G1 Overview 고도화 (KPI/TopN/이상징후 API+UI)
  - P3-G2 API Key 관리 완성
    - rotate, metadata, `team_id` 스코프 UI, key drill-down API/UI
  - P3-G4 Policy Simulation (API+UI)
  - P3-G6 Usage 분석 고도화 (trends/failure-breakdown/connectors API+UI)

- 대부분 완료 (잔여 소규모):
  - P3-G3 Team Policy
    - 완료: 팀 정책 편집, 리비전 조회/롤백, 멤버 추가/삭제 UI/API, 런타임 정책 병합
    - 잔여: UX polish + 권한 세분화(필요 시)
  - P3-G5 Audit 상세화
    - 완료: 상세 필드, 필터, export, `/api/audit/settings`(retention/masking/export_enabled)
    - 완료: team/org 기준 필터(목록/내보내기) 반영
    - 완료: org 운영 모델 최소 UX(조직 생성/멤버 조회/추가/삭제)
  - P3-G7 Event Integration
    - 완료: webhook 구독/전송/조회/수동 retry + exponential backoff 재시도 엔진 + process-retries API
    - 완료: dead-letter 상태 전환(최대 재시도 초과/비활성 구독/잘못된 endpoint)
    - 완료: dead-letter 외부 webhook 알림 자동화(수동 retry / process-retries)
    - 잔여: SIEM/Slack 포맷 표준화 및 라우팅 고도화(선택)
  - P3-G8 Admin/Ops
    - 완료: diagnostics, rate-limit/quota, system-health, external-health, incident-banner API+UI
    - 잔여: 작업 큐 상태(큐 도입 시), 공지 이력 관리(옵션)

- DB/RLS 적용 완료:
  - `021_create_team_policy_tables.sql`
  - `022_create_event_webhook_tables.sql`
  - `023_enable_rls_phase3_tables.sql`
  - `024_create_audit_settings_table.sql`
  - `025_create_incident_banners_table.sql`
  - `026_create_organization_scope_tables.sql`

## 2) 항목별 상태

## P3-G1. Overview 고도화 (Must)
- 상태: 완료
- 근거:
  - `/api/tool-calls/overview`
  - 대시보드 KPI/TopN/Anomaly

## P3-G2. API Key 관리 완성 (Must)
- 상태: 완료
- 근거:
  - rotate API
  - metadata (`issued_by`, `memo`, `tags`, `rotated_from`)
  - `team_id` 선택/수정 UI
  - `/api/api-keys/{id}/drilldown`

## P3-G3. Team Policy 관리 (Must)
- 상태: 대부분 완료
- 완료:
  - 팀/멤버십/정책/리비전/롤백 API
  - Team Policy UI (수정/리비전 조회/롤백)
  - 멤버 추가/삭제 UI
  - 팀 정책 + API Key 정책 병합 런타임 반영
- 잔여:
  - UX polish 및 권한 레벨 정교화(선택)

## P3-G4. Policy Simulation (Should)
- 상태: 완료
- 완료:
  - `/api/policies/simulate`
  - 대시보드 시뮬레이터
  - 팀+키 병합 정책 기준 판정

## P3-G5. Audit 상세화 (Must)
- 상태: 완료
- 완료:
  - `/api/audit/events`, `/api/audit/events/{id}`, `/api/audit/export`
  - `/api/audit/settings` (retention/masking/export_enabled)
  - Audit Settings UI + export 버튼
  - `team_id` + `organization_id` 필터(목록/내보내기) 반영
  - org 멤버십 기반 cross-user audit 조회(상세 포함)

## P3-G6. Usage 분석 고도화 (Must)
- 상태: 완료
- 완료:
  - `/api/tool-calls/trends`
  - `/api/tool-calls/failure-breakdown`
  - `/api/tool-calls/connectors`
  - Usage Trends UI

## P3-G7. Event Integration (Must)
- 상태: 대부분 완료
- 완료:
  - webhook schema + RLS
  - `/api/integrations/webhooks/*`
  - `/api/integrations/deliveries/*`
  - `/api/integrations/deliveries/process-retries`
  - exponential backoff retry (`next_retry_at`, `retry_count`)
  - dead-letter 전환 규칙 구현
  - dead-letter alert webhook 연동 (`DEAD_LETTER_ALERT_WEBHOOK_URL`)
- 잔여:
  - dead-letter SIEM/Slack 표준 포맷/자동 티켓화(선택)

## P3-G8. Admin/Ops 진단 (Should)
- 상태: 대부분 완료
- 완료:
  - `/api/admin/connectors/diagnostics`
  - `/api/admin/rate-limit-events`
  - `/api/admin/system-health`
  - `/api/admin/external-health`
  - `/api/admin/incident-banner` (조회/수정)
  - Admin/Ops UI 확장
- 잔여:
  - 큐 상태 모니터링(큐 도입 시)
  - 배너 이력/승인 워크플로우(선택)

## 3) 남은 작업 우선순위

Sprint D-Next:
1. 테스트 보강 (우선순위 높음)
2. Organization 고도화 UX (초대 링크/권한 승격 승인) (선택)
3. SIEM/Slack 알림 포맷 표준화 (선택)

## 4) 테스트/운영 TODO

- 테스트 추가:
  - `test_teams_route.py` (추가됨)
  - `test_integrations_route.py` (추가됨)
  - `test_event_hooks.py` (dead-letter 전환/집계 케이스 추가)
  - `test_organizations_route.py` (org 조회 케이스 추가)
  - `test_organizations_route.py` (create/member 권한 검증 케이스 확장)
  - `test_admin_route.py` (추가됨)
  - `test_mcp_routes.py` (team policy merge / webhook emit / retry)
  - `test_audit_route.py` (team filter 케이스 추가, settings/export 차단은 `test_audit_settings_route.py`로 분리)
  - `test_api_keys_drilldown_route.py` (추가됨)
- 회귀:
  - `backend/scripts/run_phase3_regression.sh`에 신규 테스트 포함
- 운영:
  - scheduler로 `/api/integrations/deliveries/process-retries` 주기 실행
  - pytest 실행 환경 정리 (CI/local 공통)

## 5) 비범위 (Phase 4 유지)

- 2인 승인/승인 워크플로우 강제
- Organization RBAC 완성형
- SSO (SAML/OIDC)
- Usage-based billing 정산
