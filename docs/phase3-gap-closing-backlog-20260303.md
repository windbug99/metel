# Phase 3 Gap-Closing Backlog (Updated: 2026-03-03, post SQL 028 + optional backlog implementation)

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
    - 완료(확장): Organization invite 링크 발급/수락 API, 권한 변경 요청/승인 API
    - 완료(확장): Organization invite/role-request 기본 UI 반영
    - 잔여: invite 링크 복사/만료 관리 UX polish(선택)
  - P3-G5 Audit 상세화
    - 완료: 상세 필드, 필터, export, `/api/audit/settings`(retention/masking/export_enabled)
    - 완료: team/org 기준 필터(목록/내보내기) 반영
    - 완료: org 운영 모델 최소 UX(조직 생성/멤버 조회/추가/삭제)
  - P3-G7 Event Integration
    - 완료: webhook 구독/전송/조회/수동 retry + exponential backoff 재시도 엔진 + process-retries API
    - 완료: dead-letter 상태 전환(최대 재시도 초과/비활성 구독/잘못된 endpoint)
    - 완료: dead-letter 외부 webhook 알림 자동화(수동 retry / process-retries)
    - 완료(확장): Slack 메시지 포맷 표준화 + SIEM/티켓 webhook(`ALERT_TICKET_WEBHOOK_URL`) 연동
    - 잔여: Jira/Linear 필드 매핑 템플릿 확정(선택)
  - P3-G8 Admin/Ops
    - 완료: diagnostics, rate-limit/quota, system-health, external-health, incident-banner API+UI
    - 완료(확장): incident-banner revisions 이력 조회/승인 API
    - 완료(확장): incident-banner revisions 생성/승인 기본 UI 반영
    - 잔여: 승인자 분리 정책/권한 분리(옵션), 작업 큐 상태(큐 도입 시)

- DB/RLS 적용 완료:
  - `021_create_team_policy_tables.sql`
  - `022_create_event_webhook_tables.sql`
  - `023_enable_rls_phase3_tables.sql`
  - `024_create_audit_settings_table.sql`
  - `025_create_incident_banners_table.sql`
  - `026_create_organization_scope_tables.sql`
  - `027_create_org_invites_and_role_requests.sql`
  - `028_create_incident_banner_revisions.sql`

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
  - Organization invite 발급/수락 API
  - Organization role change request 생성/승인 API
  - Organization invite/role request 기본 UI
- 잔여:
  - invite 링크 복사/만료/재발급 UX polish 및 권한 레벨 정교화(선택)

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
  - Slack 전송 포맷 표준화(`text` + structured payload)
  - 자동 티켓 webhook 연동(`ALERT_TICKET_WEBHOOK_URL`)
- 잔여:
  - Jira/Linear 티켓 템플릿/필드 매핑 표준화(선택)

## P3-G8. Admin/Ops 진단 (Should)
- 상태: 대부분 완료
- 완료:
  - `/api/admin/connectors/diagnostics`
  - `/api/admin/rate-limit-events`
  - `/api/admin/system-health`
  - `/api/admin/external-health`
  - `/api/admin/incident-banner` (조회/수정)
  - `/api/admin/incident-banner/revisions` (생성/조회)
  - `/api/admin/incident-banner/revisions/{id}/review` (승인/반려)
  - incident banner revisions 기본 UI (요청/승인)
  - Admin/Ops UI 확장
- 잔여:
  - 큐 상태 모니터링(큐 도입 시)
  - 배너 승인 UI/승인자 분리 정책(선택)

## 3) 남은 작업 우선순위 (필수/선택)

선택:
1. Organization 초대/승인 UX polish (링크 복사/만료/재발급)
2. SIEM/티켓 연동 표준 템플릿(Jira/Linear 필드 매핑 확정)
3. Admin/Ops 승인자 분리 정책(요청자≠승인자) 도입

## 4) 테스트/운영 TODO

- 테스트:
  - `test_teams_route.py` (추가됨)
  - `test_integrations_route.py` (추가됨)
  - `test_event_hooks.py` (dead-letter 전환/집계 케이스 추가)
  - `test_organizations_route.py` (org 조회 케이스 추가)
  - `test_organizations_route.py` (create/member + update/delete owner 권한 검증 케이스 확장)
  - `test_admin_route.py` (추가됨)
  - `test_dead_letter_alert.py` (Slack payload + ticket webhook 연동 케이스 추가)
  - `test_mcp_routes.py` (team policy merge + webhook emit + retry 케이스 보강 완료)
  - `test_audit_route.py` (team filter 케이스 추가, settings/export 차단은 `test_audit_settings_route.py`로 분리)
  - `test_api_keys_drilldown_route.py` (추가됨)
- 회귀:
  - `backend/scripts/run_phase3_regression.sh` 실행 결과: **74 passed**
- 운영:
  - scheduler로 `backend/scripts/process_webhook_retries.py` 주기 실행 (스크립트 추가 완료)
  - Railway cron 최소 주기 제약: **5분 미만 불가** (`*/5 * * * *` 이상)
  - 검증 명령(터미널):
    - `curl -sS -H "Authorization: Bearer <SUPABASE_ACCESS_TOKEN>" "<API_BASE_URL>/api/integrations/deliveries?status=retrying&limit=20"`
    - `curl -sS -X POST -H "Authorization: Bearer <SUPABASE_ACCESS_TOKEN>" "<API_BASE_URL>/api/integrations/deliveries/process-retries?limit=100"`
    - `curl -sS -H "Authorization: Bearer <SUPABASE_ACCESS_TOKEN>" "<API_BASE_URL>/api/integrations/deliveries?status=dead_letter&limit=20"`
  - 합격 기준:
    - retry 대상이 있으면 `process-retries` 호출 후 `processed` 증가
    - delivery가 `delivered` 또는 `dead_letter`로 전이
    - `dead_lettered >= DEAD_LETTER_ALERT_MIN_COUNT` 시 Slack/SIEM 알림 수신
  - pytest 실행 환경 정리 (CI/local 공통) (완료: `.venv/bin/python -m pytest` 기준)

## 4-1) 운영 검증 진행 상태 (2026-03-03 KST)

- 완료:
  - `process-retries` 수동 실행으로 `processed=1` 확인
  - delivery 재시도 누적(`retry_count` 증가, `next_retry_at` 갱신) 확인
  - dead-letter 최종 전환 확인
    - `dead_lettered=1`
    - `status=dead_letter`
    - `error_message=max_retries_exceeded:http_500`
  - Slack/SIEM 알림 수신 확인 완료
    - 채널: `#plasma`
    - dead-letter alert 메시지 수신 확인 (`source=manual_retry`)
    - `DEAD_LETTER_ALERT_WEBHOOK_URL` 유효성 확인 (`curl -> HTTP 200 / ok`)

## 4-2) Slack/SIEM 수신 확인 방법

- 1차 확인(애플리케이션 기준):
  - dead-letter 발생 직후 `process-retries` 응답에서 `dead_lettered >= DEAD_LETTER_ALERT_MIN_COUNT` 확인
- 2차 확인(Slack 채널 기준):
  - 설정한 Slack 채널에서 dead-letter 경고 메시지 수신 시각/건수 확인
  - 동일 시각대에 중복 경고 과다 발생 여부 확인
- 3차 확인(미수신 시 점검):
  - `DEAD_LETTER_ALERT_WEBHOOK_URL` 값이 Railway 백엔드 서비스 변수에 등록되어 있는지 확인
  - `DEAD_LETTER_ALERT_MIN_COUNT`가 현재 dead-letter 건수보다 크게 설정되어 있지 않은지 확인
  - 백엔드 Deploy/Cron 로그에서 alert webhook 전송 오류(4xx/5xx/timeout) 확인
  - 동일 delivery에 수동 retry를 반복하면 중복 알림이 발생할 수 있음(운영 정책으로 dedupe 고려)

## 4-3) 결론

- **Phase3 필수 범위 완료**
- 잔여는 선택 고도화 과제만 남음

## 5) 비범위 (Phase 4 유지)

- 2인 승인/승인 워크플로우 강제
- Organization RBAC 완성형
- SSO (SAML/OIDC)
- Usage-based billing 정산
