# Dashboard Menu Structure Improvement Plan (2026-03-07)

## 1. Objective
- 현재 대시보드 메뉴를 `Organization / Team / User` 카테고리로 재구성한다.
- 동일 기능명(예: `Overview`)은 카테고리별 스코프를 명확히 분리한다.
- 정보구조(IA), 라우팅, 권한(RBAC), API 스코프, UI 네비게이션을 일관되게 맞춘다.
- 책임 경계를 고정한다: `Organization=조직 거버넌스`, `Team=팀 운영`, `User=로그인 사용자 개인 설정/관리`.

## 2. Scope
- In scope
  - Sidebar IA 재설계 및 메뉴 그룹 정리
  - 카테고리별 Overview/Usage/Integrations/Access/Audit/Profile 기능 매핑
  - URL/쿼리 스코프 정책 통일(`scope=org|team|user`)
  - 프론트엔드 네비게이션 모델 및 breadcrumb 규칙 개선
  - 페이지별 데이터 조회 스코프 정렬(프론트 + 백엔드 API 파라미터)
  - RBAC 정책 문서화 및 화면 접근 제어 반영
- Out of scope
  - 신규 비즈니스 기능 추가
  - 외부 서비스 연동 확장(Notion/Linear 기능 자체 변경)
  - 데이터 모델 대규모 마이그레이션

## 3. Target IA (Draft)

### 3.1 Organization
- Overview
- Access
  - Organization Settings
  - Organization Policy (global baseline)
  - API Keys
  - Role Requests
- Integrations
  - Webhooks
  - OAuth Governance
- Audit
  - Audit Events
  - Audit Settings

### 3.2 Team
- Overview
- Usage
- Settings
- Policies
  - Team Policy
  - Policy Simulator
- Integrations
  - Webhooks
- API Keys
- Members

### 3.3 User
- Overview
- Profile
- OAuth Connections
- My Requests
- Security

## 4. Functional Mapping Principles
- 스코프 책임 정의
  - `Organization`: 조직 전체에 영향을 주는 정책/통제/감사/표준 설정(거버넌스)
  - `Team`: 단일 팀의 운영 설정/멤버/팀 정책 관리
  - `User`: 로그인한 본인 계정의 개인 설정/연결/요청 관리
- 같은 메뉴명은 카테고리별로 같은 목적이지만 다른 데이터 스코프를 가진다.
  - Example: `Organization > Overview`, `Team > Overview`, `User > Overview`
- 화면 공통 컴포넌트는 재사용하되, 스코프 파라미터와 권한 체크를 분리한다.
- `scope`가 명시되지 않으면 기본값은 항상 `user`다.
- URL 복원 규칙: URL에 유효한 `scope`가 있으면 URL을 우선하고, 없거나 불완전하면 `scope=user`로 정규화한다.
- 정책 우선순위: `Organization Policy`는 baseline, `Team Policy`는 baseline보다 완화할 수 없고 동일/강화만 가능하다.

## 4.1 OAuth Connections Improvement Items
- 방향성
  - 기본 연결 주체는 `User` 유지(`user_id + provider`).
  - `Organization`은 OAuth 연결 자체가 아니라 정책/통제/가시성 역할을 담당.
  - 필요 시 일부 provider만 `Organization-owned connector`를 선택적으로 도입.
- IA 반영
  - `User > OAuth Connections`
    - Connect/Disconnect, provider별 연결 상태, 마지막 갱신 시각
  - `Organization > Integrations > OAuth Governance` (또는 OAuth Policy)
    - 허용 provider 목록
    - 필수 연결 provider 목록
    - 특정 provider 사용 제한/승인 정책
    - 구성원 연결 현황 집계(read-only)
- 구현 항목
  - Frontend
    - User OAuth 화면: 현재 기능 유지 + 상태 표시 표준화
    - Organization OAuth Policy 화면: 허용/필수 provider 정책 관리 UI 추가
    - 정책 위반 상태 배지(예: required provider 미연결) 표시
  - Backend
    - 조직 OAuth 정책 저장 모델 추가(예: `org_oauth_policies`)
    - 정책 조회/수정 API 추가(`GET/PATCH /api/organizations/{id}/oauth-policy`)
    - 정책 검증 훅 추가(툴 실행 전 provider 허용 여부 검사)
    - 구성원 OAuth 연결 현황 집계 API 추가(관리자/오너 전용)
  - RBAC
    - Organization policy write: owner/admin
    - Organization policy read: member 이상(민감 정보 제외)
    - User OAuth token write/read: 본인만
  - 응답 필드 가시성 계약
    - member read 응답: provider 허용/필수 여부, 정책 버전, 위반 여부 집계
    - admin/owner read 응답: 위 항목 + 승인 워크플로우 설정
    - 비노출(전 역할): access token/refresh token 원문, provider별 민감 credential
- 단계적 롤아웃
  - Step 1: User OAuth 화면 안정화 (현행 유지)
  - Step 2: Organization OAuth Policy(read-only) 노출
  - Step 3: 정책 write + 런타임 enforcement 적용
  - Step 4: (본 계획 범위 밖) 선택 provider 대상 organization-owned connector 별도 PoC 트랙 검토

## 5. Routing & State Strategy

### 5.1 URL Strategy
- Canonical 표준(단일)
  - `?scope=org&org={orgId}`
  - `?scope=team&org={orgId}&team={teamId}`
  - `?scope=user`
- Legacy path(`/dashboard/org/*` 등)는 모두 canonical query URL로 리다이렉트한다.
- 정규화 규칙
  - `scope=org`인데 `org`가 없으면 `scope=user`로 리다이렉트
  - `scope=team`인데 `org` 또는 `team`이 없으면 `scope=user`로 리다이렉트
  - `scope=user`에서는 `org/team` 쿼리를 무시하고 제거

### 5.2 Navigation State
- 전역 상태
  - `selectedScope`, `selectedOrg`, `selectedTeam`
  - `currentUserId`(auth 기반, 읽기 전용)
- 사이드바
  - 카테고리 전환 시 메뉴 트리/활성 경로 동기화
- breadcrumb
  - `Category > Menu > Submenu` 형태로 일관화

## 6. RBAC Design Alignment
- Organization scope
  - owner/admin 중심 write, member read 제한
  - 팀 고유 운영값 직접 변경은 불가(조직 baseline/가드레일만 관리)
- Team scope
  - 팀 멤버 read, team admin/owner write
  - Organization baseline 위반 변경은 API에서 거부
- User scope
  - 로그인한 본인 데이터만 read/write
  - 타 사용자 데이터 조회/수정은 본 계획에서 미지원
- 화면 단 접근 + 액션 단 접근을 분리
  - 페이지 진입 가능 여부
  - 버튼/폼 액션 가능 여부

## 7. Implementation Plan

### Phase 1. IA & Contract Definition
- 메뉴 트리 확정
- 각 메뉴의 스코프/권한/데이터 소스 매트릭스 작성
- 라우팅 규칙 및 fallback 규칙 확정
- 산출물
  - IA 표
  - 메뉴-권한 매핑표
  - URL 스코프 표준서

### Phase 2. Frontend Navigation Refactor
- `nav-model`을 카테고리 중심으로 재구성
- 사이드바 그룹/라벨/활성화 로직 개편
- breadcrumb 스코프 반영
- 산출물
  - sidebar/nav 코드
  - breadcrumb 규칙 반영 코드

### Phase 3. Page Scope Refactor
- Overview/Usage/Integrations/OAuth/Profile/Access/Audit 페이지별 스코프 일치화
- 각 페이지에 공통 scope resolver 적용
- 스코프 전환 시 쿼리 동기화 보장
- 산출물
  - 페이지별 scope 처리 코드
  - 공통 유틸(필요 시)

### Phase 4. Backend Scope & RBAC Hardening
- API별 스코프 파라미터 정책 통일
- org/team/user 스코프 검증 강화
- member/admin/owner 액션 제한 재검증
- 산출물
  - 라우트 보완 코드
  - RBAC 테스트 케이스

### Phase 5. QA, Migration, Rollout
- 회귀 테스트(네비게이션/권한/데이터 정합)
- 구 URL 접근 fallback 및 리다이렉트 정책 적용
- staged rollout 후 모니터링
- 산출물
  - QA checklist
  - rollout checklist
  - issue log

## 8. Work Breakdown Structure (WBS)
- Task 1: IA 도식화 및 합의
- Task 2: scope/query 표준 유틸 설계
- Task 3: sidebar 카테고리 렌더링 구현
- Task 4: overview 다중 스코프 렌더링 분리
- Task 5: usage 스코프 정렬(org/team/user)
- Task 6: integrations/oAuth 스코프 정책 확정 및 반영
- Task 7: rbac UI gate + API gate 동기화
- Task 8: 테스트 작성 및 실행
- Task 9: 문서 업데이트 및 배포 점검

## 9. Risk & Mitigation
- Risk: 기존 쿼리 파라미터와 신규 스코프 충돌
  - Mitigation: canonical query normalizer + redirect
- Risk: 권한 경계 불일치(UI 허용/API 거부 또는 역상황)
  - Mitigation: 화면/액션 단위 권한 매트릭스 기반 점검
- Risk: Organization/Team 정책 경계 혼선
  - Mitigation: baseline(Organization) vs override(Team) 정책 우선순위 규칙을 API 계약으로 강제
- Risk: 기존 링크 북마크 깨짐
  - Mitigation: legacy route redirect map 유지
- Risk: 운영 데이터 스코프 오해
  - Mitigation: 화면 상단 scope badge/label 명시

## 10. Validation Checklist
- 카테고리 전환 시 메뉴/본문/브레드크럼 일치
- 동일 이름 메뉴(Overview)에서 스코프별 데이터가 다르게 로드
- role(owner/admin/member)별 가시성/액션 권한 정상 동작
- URL 공유 시 동일 스코프 재현
- 잘못된/불완전 쿼리 접근 시 canonical URL로 정규화
- `scope=user`에서 항상 로그인 사용자 본인 데이터만 노출
- Team 정책 저장 시 Organization baseline 위반 요청이 차단
- OAuth 정책 응답에서 민감 credential 필드가 마스킹/비노출
- 모바일/데스크탑 모두 메뉴 동작 정상

## 11. Deliverables
- 코드
  - Sidebar IA 개편
  - 페이지 scope 처리 및 권한 가드
  - API 스코프 보완
- 문서
  - IA 문서 업데이트
  - RBAC 운영 문서 업데이트
  - 테스트/배포 체크리스트

## 12. Suggested Execution Order
1. IA 확정
2. 라우팅/스코프 표준 유틸 적용
3. Sidebar/Breadcrumb 반영
4. Overview → Usage → Integrations/OAuth 순으로 페이지 개편
5. RBAC/API 보강
6. 회귀 테스트 및 staged 배포

## 13. Menu-Permission-API Mapping Matrix (Draft)

### 13.1 공통 규칙
- Role 정의
  - `owner`: 조직 소유자
  - `admin`: 조직/팀 관리자
  - `member`: 일반 구성원
- Scope 규칙
  - `org`: `?scope=org&org={orgId}`
  - `team`: `?scope=team&org={orgId}&team={teamId}`
  - `user`: `?scope=user` (로그인 사용자 본인)
- 정책 우선순위
  - `Organization Policy`는 baseline.
  - `Team Policy`는 baseline보다 완화 불가(동일/강화만 가능).

### 13.2 Organization (거버넌스)

| Menu | Scope | Page Read | Action Write | API (예시) | 비고 |
|---|---|---|---|---|---|
| Overview | org | member+ | 없음(조회 중심) | `GET /api/organizations/{orgId}/overview` | 조직 KPI/현황 |
| Access > Organization Settings | org | admin+ | owner/admin | `GET/PATCH /api/organizations/{orgId}` | 조직 기본 설정 |
| Access > Organization Policy (global baseline) | org | member+ (민감 제외) | owner/admin | `GET/PATCH /api/organizations/{orgId}/policy` | 팀 정책의 baseline |
| Access > API Keys | org | admin+ | owner/admin | `GET/POST/DELETE /api/organizations/{orgId}/api-keys` | key secret은 생성 시 1회 노출 |
| Access > Role Requests | org | member+ (본인 요청) / admin+ (전체) | admin+ (승인/반려) | `GET /api/organizations/{orgId}/role-requests`, `POST /api/organizations/{orgId}/role-requests/{id}/approve` | 요청자 범위 필터 필요 |
| Integrations > Webhooks | org | admin+ | owner/admin | `GET/POST/PATCH/DELETE /api/organizations/{orgId}/webhooks` | 서명 secret 마스킹 |
| Integrations > OAuth Governance | org | member+ (민감 제외) | owner/admin | `GET/PATCH /api/organizations/{orgId}/oauth-policy` | provider 허용/필수/제한 정책 |
| Audit > Audit Events | org | admin+ | 없음(조회 중심) | `GET /api/organizations/{orgId}/audit-events` | 다운로드 권한 admin+ |
| Audit > Audit Settings | org | admin+ | owner/admin | `GET/PATCH /api/organizations/{orgId}/audit-settings` | 보존기간/필터 정책 |

### 13.3 Team (팀 운영)

| Menu | Scope | Page Read | Action Write | API (예시) | 비고 |
|---|---|---|---|---|---|
| Overview | team | team member+ | 없음(조회 중심) | `GET /api/organizations/{orgId}/teams/{teamId}/overview` | 팀 단위 현황 |
| Usage | team | team member+ | 없음(조회 중심) | `GET /api/organizations/{orgId}/teams/{teamId}/usage` | 팀 사용량 |
| Settings | team | team member+ | team admin/owner | `GET/PATCH /api/organizations/{orgId}/teams/{teamId}` | 팀 메타/운영 설정 |
| Policies > Team Policy | team | team member+ | team admin/owner | `GET/PATCH /api/organizations/{orgId}/teams/{teamId}/policy` | 저장 시 org baseline 위반 검증 |
| Policies > Policy Simulator | team | team member+ | team admin/owner | `POST /api/organizations/{orgId}/teams/{teamId}/policy-simulator` | 시뮬레이션 결과 저장 없음 |
| Integrations > Webhooks | team | team admin+ | team admin/owner | `GET/POST/PATCH/DELETE /api/organizations/{orgId}/teams/{teamId}/webhooks` | 팀 전용 웹훅 |
| API Keys | team | team admin+ | team admin/owner | `GET/POST/DELETE /api/organizations/{orgId}/teams/{teamId}/api-keys` | 조직 키와 분리 |
| Members | team | team member+ | team admin/owner | `GET /api/organizations/{orgId}/teams/{teamId}/members`, `POST/DELETE /api/organizations/{orgId}/teams/{teamId}/members` | 멤버 추가/제거 |

### 13.4 User (로그인 사용자 개인)

| Menu | Scope | Page Read | Action Write | API (예시) | 비고 |
|---|---|---|---|---|---|
| Overview | user | self | self | `GET /api/users/me/overview` | 본인 대시보드 |
| Profile | user | self | self | `GET/PATCH /api/users/me/profile` | 이름/알림 등 개인 설정 |
| OAuth Connections | user | self | self | `GET /api/users/me/oauth-connections`, `POST /api/users/me/oauth-connections/{provider}`, `DELETE /api/users/me/oauth-connections/{provider}` | token 원문 비노출 |
| My Requests | user | self | self | `GET /api/users/me/requests`, `POST /api/users/me/requests` | 권한 요청/변경 요청 |
| Security | user | self | self | `GET/PATCH /api/users/me/security` | MFA/세션/비밀번호 정책 |

### 13.5 화면/API 권한 동기화 체크포인트
- 페이지 진입 권한과 버튼 액션 권한을 분리해 검증한다.
- 모든 write API는 UI gate와 무관하게 서버 RBAC를 최종 강제한다.
- `scope=user`에서 `org/team` 파라미터가 유입되면 무시/제거 후 `me` API만 호출한다.
- Team policy write 시 `Organization Policy` baseline 검증 실패 코드는 `403` 또는 `422`로 표준화한다.

## 14. Backend Endpoint RBAC Test Cases (Draft)

### 14.1 테스트 기준
- 인증 없는 요청은 전 엔드포인트 `401`.
- 인증은 되었으나 권한 부족인 경우 `403`.
- 스코프/파라미터 불완전 또는 잘못된 입력은 `400` 또는 정규화 리다이렉트(게이트웨이 정책에 따름).
- `scope=user` 계열은 항상 `me` 기반 리소스로 강제한다.

### 14.2 Organization Scope

| ID | Endpoint | Role | Expect | Notes |
|---|---|---|---|---|
| ORG-01 | `GET /api/organizations/{orgId}/overview` | member | 200 | 조직 멤버 읽기 허용 |
| ORG-02 | `GET /api/organizations/{orgId}/overview` | non-member | 403 | 조직 외 사용자 차단 |
| ORG-03 | `PATCH /api/organizations/{orgId}` | admin | 200 | 조직 설정 수정 허용 |
| ORG-04 | `PATCH /api/organizations/{orgId}` | member | 403 | 설정 write 차단 |
| ORG-05 | `GET /api/organizations/{orgId}/policy` | member | 200 | 민감 필드 제외 응답 |
| ORG-06 | `PATCH /api/organizations/{orgId}/policy` | owner | 200 | baseline 수정 허용 |
| ORG-07 | `PATCH /api/organizations/{orgId}/policy` | member | 403 | baseline 수정 차단 |
| ORG-08 | `GET /api/organizations/{orgId}/api-keys` | admin | 200 | 목록 조회 허용 |
| ORG-09 | `POST /api/organizations/{orgId}/api-keys` | admin | 201 | 생성 시 secret 1회 노출 |
| ORG-10 | `DELETE /api/organizations/{orgId}/api-keys/{keyId}` | member | 403 | 키 삭제 차단 |
| ORG-11 | `GET /api/organizations/{orgId}/audit-events` | admin | 200 | 감사 로그 조회 허용 |
| ORG-12 | `GET /api/organizations/{orgId}/audit-events` | member | 403 | 감사 로그 읽기 제한 |
| ORG-13 | `PATCH /api/organizations/{orgId}/oauth-policy` | admin | 200 | 정책 변경 허용 |
| ORG-14 | `GET /api/organizations/{orgId}/oauth-policy` | member | 200 | 허용 필드만 노출 |
| ORG-15 | `GET /api/organizations/{orgId}/oauth-policy` | member | 200 + field-check | token/credential 필드 비노출 검증 |

### 14.3 Team Scope

| ID | Endpoint | Role | Expect | Notes |
|---|---|---|---|---|
| TEAM-01 | `GET /api/organizations/{orgId}/teams/{teamId}/overview` | team member | 200 | 팀 멤버 읽기 허용 |
| TEAM-02 | `GET /api/organizations/{orgId}/teams/{teamId}/overview` | org member (not in team) | 403 | 팀 비소속 차단 |
| TEAM-03 | `PATCH /api/organizations/{orgId}/teams/{teamId}` | team admin | 200 | 팀 설정 수정 허용 |
| TEAM-04 | `PATCH /api/organizations/{orgId}/teams/{teamId}` | team member | 403 | 팀 설정 수정 차단 |
| TEAM-05 | `GET /api/organizations/{orgId}/teams/{teamId}/policy` | team member | 200 | 팀 정책 읽기 허용 |
| TEAM-06 | `PATCH /api/organizations/{orgId}/teams/{teamId}/policy` | team admin | 200 | baseline 준수 시 허용 |
| TEAM-07 | `PATCH /api/organizations/{orgId}/teams/{teamId}/policy` | team admin | 422 | baseline 완화 시 거부 |
| TEAM-08 | `POST /api/organizations/{orgId}/teams/{teamId}/policy-simulator` | team member | 200 | 시뮬레이션 허용 |
| TEAM-09 | `POST /api/organizations/{orgId}/teams/{teamId}/webhooks` | team admin | 201 | 팀 웹훅 생성 허용 |
| TEAM-10 | `POST /api/organizations/{orgId}/teams/{teamId}/webhooks` | team member | 403 | 팀 웹훅 write 차단 |
| TEAM-11 | `POST /api/organizations/{orgId}/teams/{teamId}/members` | team admin | 201 | 멤버 추가 허용 |
| TEAM-12 | `DELETE /api/organizations/{orgId}/teams/{teamId}/members/{userId}` | team member | 403 | 멤버 제거 차단 |
| TEAM-13 | `POST /api/organizations/{orgId}/teams/{teamId}/api-keys` | team admin | 201 | 팀 키 생성 허용 |
| TEAM-14 | `POST /api/organizations/{orgId}/teams/{teamId}/api-keys` | org admin (not team admin) | 403 | 팀 운영 권한 분리 검증 |

### 14.4 User Scope (`me` only)

| ID | Endpoint | Actor | Expect | Notes |
|---|---|---|---|---|
| USER-01 | `GET /api/users/me/overview` | self | 200 | 본인 조회 허용 |
| USER-02 | `PATCH /api/users/me/profile` | self | 200 | 본인 수정 허용 |
| USER-03 | `GET /api/users/{userId}/profile` | authenticated user | 403 or 404 | 타 사용자 직접 접근 차단 |
| USER-04 | `GET /api/users/me/oauth-connections` | self | 200 | 연결 목록 조회 |
| USER-05 | `POST /api/users/me/oauth-connections/{provider}` | self | 200/201 | provider 연결 |
| USER-06 | `DELETE /api/users/me/oauth-connections/{provider}` | self | 204 | provider 해제 |
| USER-07 | `GET /api/users/me/oauth-connections` | self | 200 + field-check | access/refresh token 원문 비노출 |
| USER-08 | `GET /api/users/me/requests` | self | 200 | 본인 요청 목록 |
| USER-09 | `POST /api/users/me/requests` | self | 201 | 본인 요청 생성 |
| USER-10 | `PATCH /api/users/me/security` | self | 200 | MFA/보안 설정 수정 |

### 14.5 Scope Normalization & Guard

| ID | Input | Expect | Notes |
|---|---|---|---|
| NORM-01 | `scope=org` without `org` | 400 or normalized to `scope=user` | 정책 문서 기준으로 일관 처리 |
| NORM-02 | `scope=team` without `org/team` | 400 or normalized to `scope=user` | 불완전 쿼리 처리 |
| NORM-03 | `scope=user&org=...&team=...` | 200 + org/team 무시 | `me` API만 사용 |
| NORM-04 | user scope에서 org endpoint 호출 | 403 | 스코프-엔드포인트 불일치 차단 |
| NORM-05 | team endpoint에 타 org의 teamId 주입 | 403 | org-team 소속 검증 |

### 14.6 감사/보안 추가 검증
- 감사 로그에 민감값(token, secret, credential 원문)이 기록되지 않는지 확인한다.
- RBAC 거부(`403`) 시 일관된 에러 코드/메시지 스키마를 반환하는지 확인한다.
- 정책 위반 거부(`422`) 시 어떤 baseline 항목을 위반했는지 machine-readable 필드를 포함하는지 확인한다.

## 15. Improvement Work Checklist (Current Status)

기준일: 2026-03-08

### 15.1 Phase 1. IA & Contract Definition
- [x] `Organization=거버넌스 / Team=운영 / User=개인` 책임 경계 확정 및 문서 반영
- [x] 메뉴-권한-API 매핑표 초안 작성(Section 13)
- [x] 백엔드 RBAC 테스트 케이스 초안 작성(Section 14)
- [x] `scope` 기본값/정규화 규칙 확정(`scope=user` default, canonical 규칙)

### 15.2 Phase 2. Frontend Navigation Refactor
- [x] 전역 쿼리 키에 `scope` 포함(`scope/org/team/range`)
- [x] dashboard shell 공통 scope resolver 적용(canonical 정규화/불완전 쿼리 교정)
- [x] Org/Team 선택 UI와 scope 동기화(`org` 선택 시 `scope=org`, `team` 선택 시 `scope=team`)
- [x] query scope 정적 점검 스크립트 현행 구조 반영 및 통과
- [x] Breadcrumb를 `Category > Menu > Submenu`로 전환 완료

### 15.3 Phase 3. Page Scope Refactor
- [x] `scope=user`에서 `org/team` 제거 및 `me` 중심 호출 가드 적용(공통 shell 레벨)
- [x] 공통 scope 해석 유틸 적용(`resolveDashboardScope`) 및 Overview/Audit Events 연동
- [x] MCP Usage 페이지 org/team 스코프 쿼리 전달 연동(`organization_id/team_id`)
- [x] Integrations(Webhooks) 페이지 org/team 스코프 쿼리 전달 및 non-user write 가드 적용
- [x] Integrations(OAuth) 페이지 scope 분기 적용(`user=OAuth Connections`, `org/team=OAuth Governance(read-only)`)
- [x] Audit(Events/Settings) 페이지 scope 분기 적용(`user=개인`, `org=거버넌스`, `team=운영 read/export`)
- [x] 페이지별 데이터 호출 스코프 일치화 완료
- [x] Overview/Usage/Integrations/Audit 각 페이지의 org/team/user 분리 렌더링 완결

### 15.4 Phase 4. Backend Scope & RBAC Hardening
- [x] `Organization Role Requests` 조회 범위 분리(`member=self`, `admin/owner=org`)
- [x] Team policy baseline 위반 시 `422 policy_baseline_violation` 강제
- [x] Organization Policy API 추가(`GET/PATCH /api/organizations/{id}/policy`)
- [x] Organization OAuth Policy API 추가(`GET/PATCH /api/organizations/{id}/oauth-policy`)
- [x] OAuth policy read 응답의 member 민감 필드 마스킹 적용
- [x] 관련 단위 테스트 추가/보정 및 통과

### 15.5 Phase 5. QA, Migration, Rollout
- [x] 로컬 테스트 환경에 `pytest` 구성(.venv)
- [x] 핵심 회귀 세트 통과(`organizations/teams/rbac/idor`)
- [x] SQL 마이그레이션 적용(`032_create_org_policy_tables.sql`) 및 스테이징 검증
- [x] 전체 백엔드 테스트 스위트/스모크 실행(2026-03-08, env 주입 + `decide_*` 3개 미존재 모듈 테스트 제외)
- [x] staged rollout 체크리스트 및 운영 모니터링 로그 업데이트

### 15.6 Current Progress Summary
- 완료: 29
- 진행 중: 0
- 미착수: 3

### 15.7 Completion Scope Clarification (2026-03-08)
- [x] 완료(백엔드/권한/스코프): Organization Policy/OAuth Policy API, baseline enforcement, rollout gate 자동화, QA/RBAC gate 통과
- [x] 완료(네비게이션 동작): scope/org/team/range canonical query 정규화, breadcrumb/category 동기화, 무한 요청 루프 수정
- [ ] 미완료(시각 IA 재배치): 사이드바를 `Organization/Team/User` 3개 대분류로 완전 분리하는 최종 메뉴 정보구조 개편
- [ ] 미완료(UI 라벨 체계): `Access/Integrations/Audit` 하위 메뉴를 대분류별 트리로 전면 재배열
- 비고:
  - 현재 화면은 안정화/권한/스코프 개선이 우선 반영된 상태이며, 메뉴의 "보이는 구조"는 부분 개편 상태다.
  - 따라서 기능적 개선은 완료에 가깝지만, IA 시각 개편은 후속 UI 작업이 필요하다.

### 15.8 Next Phase: IA UI Refactor Checklist (Visual Menu Restructure)
- 목표:
  - 사이드바를 `Organization / Team / User` 3개 대분류 기반 트리로 시각적으로 재배치한다.
  - 현재의 평면/혼합 메뉴를 책임 경계 중심 구조로 정렬한다.
- 작업 체크리스트:
  - [x] 정보구조 1차 반영: `Organization/Team/User` 3대분류 사이드바 그룹 렌더링 적용
  - [x] 사이드바 그룹 렌더러 개편: 기존 top-level 혼합 메뉴를 대분류 하위로 재배치
  - [x] Team 섹션 하위 트리 재배치: `Overview/Usage/Team Policy/Agent Guide/API Keys/Policy Simulator/Audit Events`
  - [x] User 섹션 신설/노출 규칙 1차 반영: `Profile/OAuth Connections`
  - [x] Scope 전환 UX 1차 개선: 섹션 메뉴 클릭 시 query(`scope/org/team`) 자동 정규화
  - [ ] 라벨/문구 통일: breadcrumb/페이지 타이틀/사이드바 텍스트 동기화
  - [ ] 모바일 레이아웃 검증: drawer 펼침/접힘, 탭 타겟, overflow 점검
  - [ ] 권한 기반 가시성 재검증: owner/admin/member 메뉴 노출 표 재확인
  - [x] 정적 점검 스크립트 업데이트: 메뉴 구조 변경에 맞게 `run_dashboard_v2_*_static_check.sh` 갱신
  - [ ] QA stage gate 재실행 및 PASS 기록
- 완료 기준(DoD):
  - [ ] 사이드바에서 `Organization / Team / User` 3개 대분류가 명확히 구분된다.
  - [ ] 역할별(owner/admin/member) 메뉴 노출이 매핑표(Section 13)와 일치한다.
  - [ ] `dashboard-v2-qa-gate`와 `rbac-stage-gate` 재실행 결과가 모두 PASS다.
  - [ ] 변경 스크린샷(데스크탑/모바일)과 함께 문서/로그가 업데이트된다.

## 16. Staged Rollout Checklist (2026-03-08 update)
- [x] Frontend query-scope static checks PASS
- [x] Frontend type-check(`tsc --noEmit`) PASS
- [x] Backend targeted regression PASS(`organizations/teams/tool_calls/integrations/rbac/idor`)
- [x] Backend broad smoke PASS(`284 passed, 5 skipped`) with controlled exclusions
- [x] Staging 실행 자동화 스크립트 준비
  - `backend/scripts/apply_org_policy_migration_032.sh`
  - `backend/scripts/run_org_policy_scope_smoke.sh`
  - `backend/scripts/run_org_policy_rollout_stage_gate.sh`
  - `backend/scripts/run_org_policy_rollout_from_env_file.sh`
  - `backend/.env.stage.example`
- [x] Staging DB migration apply (`032_create_org_policy_tables.sql`)
- [x] Staging smoke after migration (organization/team policy + oauth-policy read/write)
- [x] Production predeploy/rollout gate full PASS append (2026-03-08)

실행 순서(스테이징):
1. `STAGING_DB_URL='<postgres-url>' backend/scripts/apply_org_policy_migration_032.sh`
2. `API_BASE_URL='https://<staging-api>' ORG_ID='<org-id>' TEAM_ID='<team-id>' OWNER_JWT='...' ADMIN_JWT='...' MEMBER_JWT='...' backend/scripts/run_org_policy_scope_smoke.sh`
3. (권장 통합) `API_BASE_URL='https://<staging-api>' ORG_ID='<org-id>' TEAM_ID='<team-id>' OWNER_JWT='...' ADMIN_JWT='...' MEMBER_JWT='...' STAGING_DB_URL='<postgres-url>' APPLY_MIGRATION=1 RUN_PREDEPLOY_GATE=1 backend/scripts/run_org_policy_rollout_stage_gate.sh`
4. (파일기반) `cp backend/.env.stage.example backend/.env.stage` 후 값 입력, `backend/scripts/run_org_policy_rollout_from_env_file.sh`

## 17. Stage Execution Log (Template)
- 실행일시:
- 실행자:
- 대상 환경(API/DB):
- 명령:
  - `backend/scripts/run_org_policy_rollout_from_env_file.sh`
- 결과:
  - migration 032: `PASS|FAIL` (요약)
  - org policy scope smoke: `PASS|FAIL` (요약)
  - predeploy gate: `PASS|FAIL|SKIP` (요약)
  - monitoring snapshot: `PASS|FAIL` (요약)
- 후속 조치:
  - 

## 18. Stage Execution Log (Actual, 2026-03-08)
- 실행일시: 2026-03-08
- 실행자: tomato
- 대상 환경(API/DB): `https://metel-production.up.railway.app` + staging postgres
- 명령:
  - `backend/scripts/run_org_policy_rollout_from_env_file.sh`
- 결과:
  - migration 032: PASS (table exists + RLS policy count `2/2` 확인)
  - token validation: PASS (owner/admin/member role matrix 통과)
  - org policy scope smoke: PASS (`pass=11 fail=0`, team policy `422 baseline enforcement` 포함)
  - dashboard v2 predeploy gate: PASS (`pass=7 fail=0 skip=0`)
  - rbac rollout stage gate(full_guard): PASS
  - monitoring snapshot: PASS
  - final stage gate: `org-policy-stage-gate PASS`
- 후속 조치:
  - 메뉴 IA 시각 개편(Organization/Team/User 대분류 재배치) 별도 UI phase로 진행
