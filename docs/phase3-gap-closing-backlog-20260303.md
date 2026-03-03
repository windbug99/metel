# Phase 3 Gap-Closing Backlog (Updated: 2026-03-03, after SQL 025)

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
    - 잔여: team/org 기준 필터 고도화(현재 사용자 단위 중심)
  - P3-G7 Event Integration
    - 완료: webhook 구독/전송/조회/수동 retry + exponential backoff 재시도 엔진 + process-retries API
    - 잔여: dead-letter 정책 명시/자동화 운영(옵션)
  - P3-G8 Admin/Ops
    - 완료: diagnostics, rate-limit/quota, system-health, external-health, incident-banner API+UI
    - 잔여: 작업 큐 상태(큐 도입 시), 공지 이력 관리(옵션)

- DB/RLS 적용 완료:
  - `021_create_team_policy_tables.sql`
  - `022_create_event_webhook_tables.sql`
  - `023_enable_rls_phase3_tables.sql`
  - `024_create_audit_settings_table.sql`
  - `025_create_incident_banners_table.sql`

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
- 상태: 대부분 완료
- 완료:
  - `/api/audit/events`, `/api/audit/events/{id}`, `/api/audit/export`
  - `/api/audit/settings` (retention/masking/export_enabled)
  - Audit Settings UI + export 버튼
- 잔여:
  - team/org 필터 확장

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
- 잔여:
  - dead-letter 운영 규칙 명시/자동화(선택)

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
2. Audit team/org 필터 확장
3. Webhook dead-letter 운영 정책 정리

## 4) 테스트/운영 TODO

- 테스트 추가:
  - `test_teams_route.py`
  - `test_integrations_route.py`
  - `test_admin_route.py`
  - `test_mcp_routes.py` (team policy merge / webhook emit / retry)
  - `test_audit_route.py` (`/api/audit/settings`, export_enabled 차단 케이스)
  - `test_api_keys_route.py` (drilldown 케이스)
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
