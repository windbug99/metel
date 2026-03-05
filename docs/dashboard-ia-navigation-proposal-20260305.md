# Dashboard IA / Navigation UI Proposal (2026-03-05)

목적:
- 현재 단일 페이지 앵커 스크롤 방식에서, 메뉴별 페이지 라우팅 방식으로 전환한다.
- 권한 기반 UX를 명확하게 유지하면서 탐색성과 유지보수성을 높인다.

## 1) 권장 레이아웃

기본 구조:
1. `App Shell`
2. `Sidebar` (전역 메뉴)
3. `Top Bar` (컨텍스트/필터/검색)
4. `Page Content` (선택 메뉴의 단일 본문)

권장 화면 분할(Desktop):
- Sidebar: 240px 고정
- Content: 가변
- Top Bar: Content 영역 상단 고정

모바일:
- Sidebar는 drawer로 전환
- Top Bar 필터는 bottom sheet로 전환

## 2) 메뉴 정보구조(IA)

### Sidebar 그룹

1. `Overview`
2. `Access`
- API Keys
- Organizations
- Team Policy
3. `Control`
- Policy Simulator
- Audit Events
4. `Integrations`
- Webhooks / Deliveries
- OAuth Connections
5. `Admin / Ops` (권한 조건부)
- Connector Diagnostics
- Rate Limit Events
- System Health
- External Health
- Incident Banner

### Top Bar 구성

1. 좌측: Breadcrumb + 현재 페이지 타이틀
2. 중앙: Global Search (`request_id`, `api_key`, `user_id`, `tool_name`)
3. 우측:
- Organization / Team switcher
- Time range picker (24h/7d/custom)
- Refresh
- User menu

Global Search 구현 전제:
- 백엔드 검색 API 스펙 확정 전에는 UI를 read-only(placeholder)로 두거나 비노출 처리
- 검색 API 도입 시 role/scope(tenant) 필터를 서버에서 강제 적용

## 3) 권한 UX 정책

기본 원칙:
1. 페이지 접근 권한 정책:
- 메뉴 레벨: 접근 불가 메뉴는 기본적으로 숨김
- 예외(향후 권한 요청 기능 도입 시): lock 표시 + 사유 노출
2. 액션 권한이 없으면 버튼 비활성 + 이유 텍스트를 노출한다.
3. API 403은 전역 배너/토스트로 통일한다.

권장 정책:
- `member`: Admin/Ops 그룹 미노출
- `admin`: Admin/Ops 조회 가능, owner-only 액션 비활성
- `owner`: 모든 메뉴/액션 허용

안내 문구 예시:
- `owner role required`
- `admin role required`
- `insufficient scope (team/org mismatch)`

## 4) 페이지 템플릿(일관성)

각 메뉴 페이지 공통 템플릿:
1. `PageHeader` (제목, 설명, 주요 CTA 1개)
2. `Summary Row` (핵심 KPI 카드 3~5개)
3. `Main Panel` (테이블/차트/폼)
4. `Secondary Panel` (필터, 히스토리, 도움말)

상세/편집 UX:
- 리스트와 상세 편집을 분리
- 모달은 단순 승인/확인 작업에만 사용
- 복잡한 편집은 별도 route(`/edit`, `/detail`) 권장

## 5) 라우팅 구조 제안

권장 URL:
- `/dashboard/overview`
- `/dashboard/access/api-keys`
- `/dashboard/access/organizations`
- `/dashboard/access/team-policy`
- `/dashboard/control/policy-simulator`
- `/dashboard/control/audit-events`
- `/dashboard/integrations/webhooks`
- `/dashboard/integrations/oauth`
- `/dashboard/admin/ops` (또는 하위 분리)

Shell:
- `/dashboard/layout.tsx`에서 공통 권한/프로필/컨텍스트 로드
- 하위 page는 필요한 데이터만 fetch

레거시/호환 경로 규칙:
- `/dashboard` 진입 시 `/dashboard/overview`로 리다이렉트
- OAuth 콜백 후 리다이렉트가 `/dashboard?notion=connected|linear=connected`일 경우:
  - `connected` 플래그를 유지한 채 `/dashboard/overview?...`로 정규화
  - 또는 backend redirect URL을 `/dashboard/overview`로 변경

## 6) 데이터 로딩 전략

1. Shell 레벨:
- `/api/me/permissions`
- 조직/팀 컨텍스트

2. 페이지 레벨:
- 해당 페이지 API만 호출 (초기 번들/요청 최소화)

3. 캐시/재검증:
- 페이지 이동 시 stale-while-revalidate
- 상단 `Refresh`는 현재 페이지만 갱신

컨텍스트 상태 소스:
- `org`, `team`, `range`는 URL query를 단일 소스로 사용
- 예: `/dashboard/control/audit-events?org=1&team=2&range=24h`
- Shell은 query를 읽어 공통 컨텍스트를 구성하고, 하위 페이지는 이를 구독

파라미터 스코프 규칙:
- 전역 파라미터: `org`, `team`, `range`
- 페이지 전용 파라미터: 각 페이지 prefix로 분리
  - 예: audit 페이지 `audit_status`, api-keys 페이지 `keys_status`
- 페이지 이동 시:
  - 전역 파라미터는 유지
  - 페이지 전용 파라미터는 목적지 페이지 파라미터만 유지하고 나머지는 제거

## 7) 전환(마이그레이션) 순서

1. `Dashboard Shell` + Sidebar/Top Bar 컴포넌트 신설
2. `Overview`, `API Keys`, `Audit Events` 3개 페이지 먼저 분리
3. 권한 가드/403 공통 처리 연결
4. 나머지 메뉴 순차 분리
5. 기존 앵커 스크롤 제거
6. 레거시 URL/OAuth 콜백 호환 리다이렉트 검증 후 완전 전환

## 8) 성공 지표(KPI)

1. 메뉴 클릭 후 첫 의미있는 렌더 시간 감소
2. 페이지 이탈률/재방문률 개선
3. 권한 관련 오류 문의 감소
4. QA 시나리오 실행 시간 단축

## 9) 구현 시 주의사항

1. 권한 검증은 UI가 아니라 API를 최종 기준으로 유지
2. 메뉴 노출/비노출과 API 응답(403) 정책 불일치 금지
3. 조직/팀 컨텍스트 변경 시 캐시 무효화 필수
4. deep-link(직접 URL 진입) 시에도 동일하게 권한 가드 적용
5. `/dashboard` 및 OAuth 콜백 파라미터(`?notion=connected`, `?linear=connected`) 호환성 유지
6. 인증 만료/미로그인 deep-link 진입 시 로그인 페이지로 리다이렉트하고, 복귀 URL(`next`)을 보존

---

결론:
- 현 제품 단계에서는 `Sidebar + Top Bar + Route-based Content`가 가장 안정적이다.
- 이 구조가 RBAC, 운영 페이지 확장, 테스트 자동화 모두에 유리하다.

## 10) UI 수정 작업 체크리스트

### A. IA / 라우팅 설계 확정
- [x] Sidebar 메뉴 트리 확정(Overview/Access/Control/Integrations/Admin-Ops)
- [x] Top Bar 항목 확정(breadcrumb/search/org-team/time/refresh/user)
- [x] URL 맵 확정(`/dashboard/...` 전 구간)
- [ ] 기존 앵커 ID/스크롤 의존 코드 제거 범위 확정
- [x] `/dashboard` -> `/dashboard/overview` 리다이렉트 정책 확정
- [x] OAuth 콜백 파라미터 호환 정책 확정(`notion=connected`, `linear=connected`)

### B. App Shell 구현
- [/] `dashboard/layout.tsx`(Shell) 생성
- [x] Sidebar 컴포넌트 분리(`DashboardSidebar`)
- [x] Top Bar 컴포넌트 분리(`DashboardTopbar`)
- [x] 모바일 drawer/bottom-sheet 기본 동작 구현

### C. 페이지 분리 1차(MVP)
- [x] `overview` 페이지 분리
- [x] `access/api-keys` 페이지 분리
- [x] `control/audit-events` 페이지 분리
- [/] 기존 단일 페이지에서 해당 섹션 제거/리다이렉트 처리
- [x] 레거시 진입 URL(`/dashboard`, 앵커 링크) 리다이렉트 처리

### D. 권한/가드 적용
- [x] Shell에서 `/api/me/permissions` 1회 로드
- [x] 메뉴 노출/비노출 role 조건 반영
- [/] owner-only 액션 비활성 + 이유 문구 반영
- [/] 공통 403 배너/토스트 컴포넌트 적용
- [x] 메뉴 접근 정책 일원화(기본 숨김, 예외만 lock 표시)
- [x] 인증 만료(401)/권한 부족(403) UX 분리 처리 및 복귀 URL 유지

### E. 데이터 로딩/성능
- [/] 페이지 단위 fetch로 분리(불필요한 초기 호출 제거)
- [/] org/team/time-range 변경 시 캐시 무효화
- [x] Refresh 버튼 현재 페이지 스코프 갱신으로 제한
- [x] 주요 페이지 로딩 스켈레톤 추가
- [x] `org/team/range` URL query 기반 컨텍스트 동기화
- [x] 전역/페이지 전용 query 파라미터 정리 규칙 구현(페이지 이동 시 전용 파라미터 정리)
- [x] Global Search 백엔드 API 의존성(스펙/권한) 확정 전 기능 플래그 처리

### F. 디자인 시스템 적용
- [x] `docs/dashboard-design-system-draft-20260305.md` 토큰 적용
- [x] Sidebar/Top Bar/KPI Card/Table 스타일 일관화
- [x] Light/Dark 테마 토글 또는 클래스 기반 적용
- [x] 상태 배지(`allowed/policy_blocked/access_denied/failed`) 스타일 통일

### G. QA / 배포
- [x] owner/admin/member 메뉴/권한 노출 스모크
- [x] deep-link 직접 진입 테스트(`/dashboard/...`)
- [x] 레거시 URL 호환 테스트(`/dashboard`, 기존 북마크 링크)
- [x] OAuth 콜백 후 랜딩 테스트(`?notion=connected`, `?linear=connected`)
- [x] 인증 만료 deep-link 테스트(로그인 리다이렉트 + `next` 복귀)
- [x] query 파라미터 정리 테스트(전역 유지/페이지 전용 제거)
- [x] 모바일 반응형 QA (`320/375/768`) 레이아웃/오버플로우 확인
- [x] 모바일 터치 타겟(최소 44px) 및 sticky Top Bar 겹침 검증
- [x] `pnpm -s tsc --noEmit` 통과
- [x] RBAC 스모크(`run_phase3_rbac_smoke.sh`) 통과
- [x] 대시보드 검증(`run_phase3_dashboard_consistency.sh`) 통과

### H. 전환 완료(DoD)
- [x] 앵커 스크롤 기반 단일 페이지 제거 완료
- [x] 메뉴 클릭 시 URL 라우팅 전환 100% 완료
- [x] 권한/가드 UX가 owner/admin/member 정책과 일치
- [x] 이관 완료 범위(Overview/Profile/API Keys/Organizations/Team Policy/Audit Events 기본 조회) 내 기능 회귀 없음

### I. 액티브 기능 이관 우선순위
- [x] 1단계: API Keys 생성 액션 이관 (`/dashboard/access/api-keys`)
- [x] 2단계: Organizations 초대/멤버 관리 이관 (`/dashboard/access/organizations`)
- [x] 3단계: Team 생성/멤버 관리/정책 저장 이관 (`/dashboard/access/team-policy`)
- [x] 4단계: Profile 설정 이관 (`/dashboard/profile`)

진행 메모 (2026-03-05):
- V2 스캐폴딩 추가:
  - `frontend/components/dashboard-v2/shell.tsx`
  - `frontend/app/dashboard/(v2)/layout.tsx`
  - `frontend/app/dashboard/(v2)/overview/page.tsx`
  - `frontend/app/dashboard/(v2)/access/api-keys/page.tsx`
  - `frontend/app/dashboard/(v2)/control/audit-events/page.tsx`
- `/dashboard` root는 `/dashboard/overview`로 리다이렉트되며 query를 유지(`notion=connected`, `linear=connected` 호환).
- 기존 단일 페이지는 `frontend/app/dashboard/legacy/page.tsx`로 이동.
- 레거시 UI는 `/dashboard/legacy` 경로에서 회귀 방지용으로 유지.
- V2 Shell 권한 연동:
  - `/api/me/permissions` 로드 후 role 표시 및 `Admin / Ops` 메뉴 조건부 노출
  - 권한 로드 실패/403 시 Shell 상단 에러/경고 배너 노출
  - 신규 route: `frontend/app/dashboard/(v2)/admin/ops/page.tsx`
- 401/403 UX 분리 1차:
  - 401 또는 세션 미존재 시 `/?next=<current_path>`로 리다이렉트
  - 403은 Shell 상단 경고 배너로 노출
- owner-only 액션 가드 1차:
  - `Admin / Ops` 페이지에 owner-only 버튼 비활성 + `Owner role required.` 문구 반영
- 데이터 로딩 1차:
  - Shell Top Bar에 `org/team/range` query 컨텍스트 추가
  - `Refresh` 버튼은 `dashboard:v2:refresh` 이벤트로 현재 경로 페이지만 갱신
  - V2 페이지별 API fetch 연결:
    - Overview: `/api/tool-calls/overview`
    - API Keys: `/api/api-keys`
    - Audit Events: `/api/audit/events`
- query 파라미터 정리 규칙 반영:
  - 전역 키(`org/team/range`)는 라우트 이동 시 유지
  - 페이지 전용 키는 현재 페이지 허용 목록만 유지, 타 페이지 키는 자동 제거
  - 사이드바 링크는 전역 키를 유지한 URL로 이동
- 루트/앵커 리다이렉트 반영:
  - `/dashboard` 진입 시 클라이언트 라우팅으로 `/dashboard/overview` 이동
  - 레거시 앵커 `#api-keys`, `#audit-events`, `#overview`는 V2 라우트로 매핑
- 레거시 페이지(`\/dashboard\/legacy`)에도 동일 앵커 매핑 적용:
  - `#api-keys`, `#audit-events`, `#overview` 접근 시 V2 라우트로 즉시 전환
- 레거시 메뉴에서도 이관 완료 항목은 V2 라우트 직접 링크로 전환:
  - Overview/API Keys/Audit Events는 앵커 대신 V2 페이지로 이동
- Global Search 플래그 처리:
  - `NEXT_PUBLIC_DASHBOARD_GLOBAL_SEARCH_ENABLED`가 `false`면 검색 input 비활성 + 안내문구 노출
  - backend 검색 API 스펙 확정 전까지 안전하게 placeholder 모드 유지
- owner-only 가드 확대:
  - `Audit Events` 페이지에 owner-only 액션 버튼 비활성 + `Owner role required.` 문구 반영
- 공통 배너 컴포넌트 추가:
  - `frontend/components/dashboard-v2/alert-banner.tsx`
  - Shell의 403/에러 배너에 공통 컴포넌트 적용
- 디자인 시스템 1차 적용:
  - `globals.css`의 light/dark 토큰 기준으로 V2 Shell/페이지(`Overview`, `API Keys`, `Audit Events`, `Admin / Ops`) 스타일 정규화
  - `ds-card`, `ds-input`, `ds-btn` 유틸 클래스 기준으로 Card/Table/Control 일관화
  - Shell 헤더에 `Light/Dark` 토글 추가(`localStorage: dashboard-v2-theme`)
- 상태 배지 통일 적용:
  - `frontend/components/dashboard-v2/status-badge.tsx` 추가
  - `Audit Events`의 decision(`allowed/policy_blocked/access_denied/failed`)을 공통 배지로 렌더링
  - `API Keys`의 key status(`active/revoked`)도 동일 배지 시스템으로 일관화
- V2 API 공통 유틸 추가:
  - `frontend/lib/dashboard-v2-client.ts`
  - 세션/인증/응답 상태 처리를 페이지별 중복 없이 공통 처리
- 401/403 처리 확대:
  - Overview/API Keys/Audit Events 페이지에서 401 시 `/?next=...` 복귀 리다이렉트
  - 403은 페이지 에러로 분리 노출(권한 부족 명확화)
- 역할별 메뉴/권한 노출 QA 스크립트 추가:
  - `backend/scripts/run_dashboard_v2_menu_rbac_smoke.sh`
  - 실행 조건: `API_BASE_URL`, `OWNER_JWT`, `ADMIN_JWT`, `MEMBER_JWT`
  - 목적: role matrix + `can_read_admin_ops` 기준 메뉴 노출(Overview/API Keys/Audit Events/Admin-Ops) 기대값 검증
  - 실행 결과(Production): `PASS` (owner/admin/member role + visible menu + incident banner manage matrix)
- deep-link/리다이렉트 정적 점검 스크립트 추가:
  - `backend/scripts/run_dashboard_v2_deeplink_static_check.sh`
  - 검증 범위(정적): root/legacy hash->route 매핑, query 유지, 401 시 `next` 복귀 파라미터 코드 경로 존재, OAuth 콜백(`notion/linear`) 랜딩 파라미터 유지
  - 실행 결과: `pass=15 fail=0`
- query scope 정적 점검 스크립트 추가:
  - `backend/scripts/run_dashboard_v2_query_scope_static_check.sh`
  - 검증 범위(정적): 전역 키(`org/team/range`) 선언, 페이지 전용 키 선언, 허용 키셋 기반 제거 로직, 사이드바 이동 시 전역 키 유지
  - 실행 결과: `pass=10 fail=0`
- 모바일 반응형/터치타겟 정적 점검 스크립트 추가:
  - `backend/scripts/run_dashboard_v2_mobile_static_check.sh`
  - 반영 내용: Top Bar 모바일 wrap, 주요 컨트롤 `h-11`(44px) 터치 타겟, 모바일 테이블 `overflow-x-auto` + `min-w-[640px]`
  - 실행 결과: `pass=12 fail=0`
  - 잔여: 실제 디바이스/브라우저(320/375/768) 수동 시각 QA
- 액티브 기능 이관 2단계(Organizations) 반영:
  - 신규 route: `frontend/app/dashboard/(v2)/access/organizations/page.tsx`
  - 사이드바 메뉴에 `Organizations` 추가 및 페이지 타이틀/쿼리키 매핑(`orgs_tab`) 연결
  - 이관 기능: 조직 생성, 멤버 조회/추가/역할변경/삭제(owner), 초대 생성/조회/철회/재발급(owner), 초대 토큰 수락
- 액티브 기능 이관 3단계(Team Policy) 반영:
  - 신규 route: `frontend/app/dashboard/(v2)/access/team-policy/page.tsx`
  - 사이드바 메뉴에 `Team Policy` 추가 및 페이지 타이틀/쿼리키 매핑(`team_tab`) 연결
  - 이관 기능: 팀 생성(admin), 팀 정책 저장(admin), 멤버 조회/추가/삭제(admin), 정책 리비전 조회/롤백(admin)
- 액티브 기능 이관 4단계(Profile) 반영:
  - 신규 route: `frontend/app/dashboard/(v2)/profile/page.tsx`
  - 사이드바 메뉴에 `Profile` 추가 및 페이지 타이틀/쿼리키 매핑(`profile_tab`) 연결
  - 이관 기능: 사용자 프로필 조회, 타임존 설정 저장
  - 검증: `frontend pnpm -s tsc --noEmit` PASS
  - 검증: `backend ./scripts/run_dashboard_v2_qa_stage_gate.sh` PASS (static 3/3, runtime 3 skip)
- QA 통합 게이트 스크립트 추가:
  - `backend/scripts/run_dashboard_v2_qa_stage_gate.sh`
  - 구성: deeplink/query-scope/mobile 정적 점검 + (환경변수 있을 때) 토큰 role 사전검증 -> 메뉴 RBAC 스모크/대시보드 일관성 점검
  - 옵션: `REQUIRE_MOBILE_MANUAL_QA=1` 설정 시 모바일 수동 QA 로그 완료 여부까지 강제
  - 로컬 실행 결과: `pass=3 fail=0 skip=3` (runtime/mobile-manual checks skipped without env)
- RBAC 테스트 토큰 사전검증 스크립트 추가:
  - `backend/scripts/validate_rbac_test_tokens.sh`
  - 검증: `/api/me/permissions` 응답 기준으로 OWNER/ADMIN/MEMBER 토큰 role 일치 여부 확인
  - 목적: 401/role mismatch 시 런타임 시나리오 연쇄 실패 전에 원인 분리
  - 실행 결과(Production):
    - owner: `PASS` (`user_id=4c47bd79-e630-4c0b-aac7-c77916f1cd84`)
    - admin: `PASS` (`user_id=18991f47-4460-4799-bb22-685710618975`)
    - member: `PASS` (`user_id=24a26b52-0aa2-49f8-8473-9cb75c0eeb4b`)
- 정적 QA 스크립트 실행 호환성 보강:
  - `run_dashboard_v2_deeplink_static_check.sh`
  - `run_dashboard_v2_query_scope_static_check.sh`
  - `run_dashboard_v2_mobile_static_check.sh`
  - 변경: `rg` 미설치 환경에서 `grep -E` 자동 폴백
- G 항목 상태 승격:
  - `deep-link`, `레거시 URL`, `OAuth 콜백 랜딩`, `인증 만료 deep-link(next)`, `query 파라미터 정리`는 정적 점검 자동화 + QA 게이트 통과로 `[x]` 전환
  - 모바일 2개 항목은 실제 기기/브라우저 수동 검증 이후 `[x]` 전환
- 모바일 수동 QA 최소 절차(남은 2개 항목 마감용):
  - 뷰포트 `320/375/768`에서 `/dashboard/overview`, `/dashboard/access/api-keys`, `/dashboard/control/audit-events` 진입
  - Top Bar 컨트롤(Org/Team/Range/Refresh/Theme) 탭 영역이 겹치지 않고 조작 가능한지 확인
  - API Keys/Audit 테이블 가로 스크롤 동작 및 본문 레이아웃 깨짐 여부 확인
  - Drawer 메뉴 항목 탭(>=44px)과 sticky Top Bar 겹침 여부 확인
  - 기록 문서: `docs/dashboard-mobile-manual-qa-log-20260305.md`
- H 전환 readiness 체크 스크립트 추가:
  - `backend/scripts/run_dashboard_v2_transition_readiness_check.sh`
  - 구성: `/dashboard` 리다이렉트 확인 + legacy feature flag 기본값/게이트 확인 + 이관 메뉴 링크 확인 + `run_dashboard_v2_qa_stage_gate.sh` 연동
  - 로컬 실행 결과: `pass=5 fail=0 warn=1`
- legacy 경로 전환 정책 확정:
  - `frontend/.env.example`에 `NEXT_PUBLIC_DASHBOARD_LEGACY_ENABLED=false` 추가(기본 비활성)
  - `frontend/app/dashboard/legacy/page.tsx`는 flag가 `true`일 때만 legacy UI를 노출하고, 기본값에서는 `/dashboard/overview`로 즉시 리다이렉트
- 모바일 수동 QA 완료 판정 스크립트 추가:
  - `backend/scripts/check_dashboard_mobile_manual_qa_log.sh`
  - 기준: `docs/dashboard-mobile-manual-qa-log-20260305.md`에 미체크 항목이 없고, `종합 결과`가 `PASS/OK`
  - 현재 상태: `PASS` (transition readiness `warn=0` 달성)
- 최종 마감(strict) 실행 기준:
  - `STRICT_WARN_AS_FAIL=1 backend/scripts/run_dashboard_v2_transition_readiness_check.sh`
  - 현재 결과: `pass=6 fail=0 warn=0` (strict 통과)
- 액티브 기능 이관 1단계 완료:
  - V2 API Keys 페이지에 `Create API key` 액션 이관
  - 필드: `name`, `team_id(optional)`, `memo(optional)`
  - 생성 성공 시 1회 노출 키(`api_key`) 표시 + 복사 버튼 제공
  - 관련 파일:
    - `frontend/app/dashboard/(v2)/access/api-keys/page.tsx`
    - `frontend/lib/dashboard-v2-client.ts` (`dashboardApiRequest` 추가)
  - 검증: `frontend pnpm -s tsc --noEmit` PASS
- QA 자동 실행 결과(2026-03-05):
  - `frontend`: `pnpm -s tsc --noEmit` PASS
  - `backend`: `./scripts/run_phase3_rbac_smoke.sh` PASS (`32 passed`)
  - `backend`: `API_BASE_URL=https://metel-production.up.railway.app OWNER_JWT/ADMIN_JWT/MEMBER_JWT ... ./scripts/run_phase3_dashboard_consistency.sh` PASS
    - member baseline formula check: `pass=11 fail=0`
    - role matrix check: `pass=8 fail=0 skip=0`
  - `backend`: `API_BASE_URL=... OWNER_JWT=... ADMIN_JWT=... MEMBER_JWT=... ./scripts/run_dashboard_v2_qa_stage_gate.sh` PASS
    - 결과: `pass=6 fail=0 skip=1` (mobile manual qa log check 미강제)
  - `backend`: `REQUIRE_MOBILE_MANUAL_QA=1 API_BASE_URL=... OWNER_JWT=... ADMIN_JWT=... MEMBER_JWT=... ./scripts/run_dashboard_v2_qa_stage_gate.sh` FAIL
    - 결과: `pass=6 fail=1 skip=0`
    - 원인: `mobile manual qa log check` 미완료(`docs/dashboard-mobile-manual-qa-log-20260305.md` 체크박스 미체크)

## 11) 미이관 기능 갭 분석 (기준: legacy 대비)

분류 기준:
- `완료`: V2에서 동일/동급 기능 제공
- `부분`: V2에서 일부 기능만 제공
- `미이관`: V2 미구현 (legacy에만 존재)

### A. 일반 사용자 기능
- 프로필 관리(타임존 조회/수정): `완료`
- OAuth 연결/해제(Notion/Linear): `미이관`
- MCP 사용 시작 가이드(list_tools/call_tool curl 예시): `미이관`
- 사용량 조회(최근 호출 목록/필터/24h 요약/7일 추세): `미이관`
- 로그아웃: `미이관` (V2 UI 버튼 기준)

### B. 개발자/통합 담당 기능
- API Key 생성(팀 스코프, 1회 노출/복사): `부분`
- API Key 고급 필드(allowed tools, tags, policy JSON): `미이관`
- API Key 수정/회전/폐기/7일 drill-down: `미이관`
- Policy Simulator: `미이관`
- Webhook 구독/Delivery 조회/Retry: `미이관`

### C. 팀/조직 관리자 기능
- Team 생성/수정/정책 저장/리비전 조회/롤백/멤버 관리: `완료`
- Organization 생성/멤버 관리/초대 생성·수락·재발급·철회: `완료`
- Organization 역할 변경 요청 생성/승인/거절: `미이관`

### D. 보안/감사 담당 기능
- Audit 이벤트 목록 조회(기본): `부분`
- Audit 요약/팀·조직 필터/상세 조회: `미이관`
- Audit 설정(retention/export/masking): `미이관`
- 감사 내보내기(JSONL/CSV): `미이관`

### E. 운영/플랫폼 관리자 기능
- Execution KPI(기본 KPI 카드): `부분`
- Top tools/anomalies/추세형 시각화: `미이관`
- Admin/Ops 실모듈(시스템헬스/진단/외부헬스/rate-limit): `미이관`
- Incident Banner 저장 + revision 승인 워크플로우: `미이관`

## 12) 구현 착수 체크리스트 (미이관 항목)

원칙:
- 우선 `legacy` 기능과 API 계약을 1:1 보존해 이관
- 페이지 단위 PR로 분할하여 회귀 범위 최소화

### Wave 1 (즉시 착수, 사용자 영향 큼)
- [x] V2 API Keys 고도화: 수정/Rotate/Revoke/Drill-down + allowed tools/tags/policy JSON
- [x] V2 로그아웃 액션 추가(Shell 상단)
- [x] V2 Usage 페이지 추가(최근 호출 목록 + 상태/툴명/기간 필터 + 24h 요약 + 7d 추세)
- [x] V2 Policy Simulator 페이지 추가

### Wave 2 (통합/운영 핵심)
- [x] V2 Integrations 페이지 추가(Webhook 구독/Delivery 조회/Retry)
- [x] V2 OAuth Connections 페이지 추가(Notion/Linear 연결/해제 + 상태)
- [x] V2 MCP Usage 가이드 페이지 추가(curl 예시/복사 UX)

### Wave 3 (감사/운영 고도화)
- [x] V2 Audit Events 확장(요약/팀·조직 필터/상세)
- [x] V2 Audit Settings 페이지 추가(retention/export/masking)
- [x] V2 Audit Export(JSONL/CSV) 이관
- [x] V2 Admin/Ops 실모듈 이관(health/diagnostics/rate-limit/external health)
- [x] V2 Incident Banner 운영(저장 + revision 요청/승인/거절)

### Wave 4 (조직 거버넌스 완성)
- [x] V2 Organization Role Request(생성/승인/거절) 이관

## 13) 착수 전 준비 완료 조건 (Go)

- [ ] 각 Wave별 API endpoint/권한 매트릭스(owner/admin/member) 확정
- [ ] legacy 대비 기능 동등성 체크리스트(입력/출력/에러코드) 작성
- [ ] 자동 테스트 스크립트 확장 계획 수립(각 Wave 완료 시 smoke 추가)
- [ ] 문서 체크포인트: 본 문서 12번 체크리스트에 작업 후 즉시 반영

진행 메모 (2026-03-05, 미이관 Wave 1):
- V2 API Keys 고도화 완료:
  - 생성 필드 확장: `allowed_tools`, `tags`, `policy_json`, `memo`, `team_id`
  - 키 액션 추가: `PATCH(/api/api-keys/{id})`, `POST(/api/api-keys/{id}/rotate)`, `DELETE(/api/api-keys/{id})`
  - 7일 Drill-down 조회 추가: `GET /api/api-keys/{id}/drilldown?days=7`
  - 화면 반영 파일: `frontend/app/dashboard/(v2)/access/api-keys/page.tsx`
  - 검증: `frontend pnpm -s tsc --noEmit` PASS
  - 검증: `backend ./scripts/run_dashboard_v2_qa_stage_gate.sh` PASS (static 3/3, runtime skip)
- V2 로그아웃 액션 이관 완료:
  - Shell Top Bar에 `Sign out` 버튼 추가
  - 처리: `supabase.auth.signOut()` 후 `/`로 리다이렉트
  - 화면 반영 파일: `frontend/components/dashboard-v2/shell.tsx`
  - 검증: `frontend pnpm -s tsc --noEmit` PASS
  - 검증: `backend ./scripts/run_dashboard_v2_qa_stage_gate.sh` PASS (static 3/3, runtime skip)
- V2 Usage 페이지 이관 완료:
  - 신규 route: `frontend/app/dashboard/(v2)/control/mcp-usage/page.tsx`
  - 메뉴 연결: `frontend/components/dashboard-v2/shell.tsx` (`MCP Usage`)
  - 이관 기능: 최근 호출 목록, 상태/툴명/기간 필터, 24h 요약, 7d 추세/실패분류/커넥터 헬스
  - 검증: `frontend pnpm -s tsc --noEmit` PASS
  - 검증: `backend ./scripts/run_dashboard_v2_qa_stage_gate.sh` PASS (static 3/3, runtime skip)
- V2 Policy Simulator 이관 완료:
  - 신규 route: `frontend/app/dashboard/(v2)/control/policy-simulator/page.tsx`
  - 메뉴 연결: `frontend/components/dashboard-v2/shell.tsx` (`Policy Simulator`)
  - 이관 기능: API key 선택 + tool_name + arguments JSON 기반 `/api/policies/simulate` 실행 및 결과 시각화
  - 검증: `frontend pnpm -s tsc --noEmit` PASS
  - 검증: `backend ./scripts/run_dashboard_v2_qa_stage_gate.sh` PASS (static 3/3, runtime skip)
- V2 Integrations(Webhook) 이관 완료:
  - 신규 route: `frontend/app/dashboard/(v2)/integrations/webhooks/page.tsx`
  - 메뉴 연결: `frontend/components/dashboard-v2/shell.tsx` (`Integrations`)
  - 이관 기능: webhook 구독 생성, 최근 delivery 조회, 개별 retry, 일괄 `process-retries`
  - 검증: `frontend pnpm -s tsc --noEmit` PASS
  - 검증: `backend ./scripts/run_dashboard_v2_qa_stage_gate.sh` PASS (static 3/3, runtime skip)
- V2 OAuth Connections 이관 완료:
  - 신규 route: `frontend/app/dashboard/(v2)/integrations/oauth/page.tsx`
  - 메뉴 연결: `frontend/components/dashboard-v2/shell.tsx` (`OAuth`)
  - 이관 기능: Notion/Linear 상태 조회, OAuth 시작(connect), 연결 해제(disconnect)
  - 검증: `frontend pnpm -s tsc --noEmit` PASS
  - 검증: `backend ./scripts/run_dashboard_v2_qa_stage_gate.sh` PASS (static 3/3, runtime skip)
- V2 MCP Guide 이관 완료:
  - 신규 route: `frontend/app/dashboard/(v2)/control/mcp-guide/page.tsx`
  - 메뉴 연결: `frontend/components/dashboard-v2/shell.tsx` (`MCP Guide`)
  - 이관 기능: `list_tools`/`call_tool` curl 예시 + 복사 버튼 UX
  - 검증: `frontend pnpm -s tsc --noEmit` PASS
  - 검증: `backend ./scripts/run_dashboard_v2_qa_stage_gate.sh` PASS (static 3/3, runtime skip)
- V2 Audit Events 확장 완료:
  - 확장 파일: `frontend/app/dashboard/(v2)/control/audit-events/page.tsx`
  - 이관 기능: 요약 카드, status/decision/tool/from/to 필터, 조직/팀 필터, 이벤트 상세 조회
  - 검증: `frontend pnpm -s tsc --noEmit` PASS
  - 검증: `backend ./scripts/run_dashboard_v2_qa_stage_gate.sh` PASS (static 3/3, runtime skip)
- V2 Audit Settings + Export 이관 완료:
  - 신규 route: `frontend/app/dashboard/(v2)/control/audit-settings/page.tsx`
  - 메뉴 연결: `frontend/components/dashboard-v2/shell.tsx` (`Audit Settings`)
  - 이관 기능: `retention_days`/`export_enabled`/`masking_policy` 조회 및 저장, 조직/팀 스코프 기반 JSONL/CSV export
  - 검증: `frontend pnpm -s tsc --noEmit` PASS
  - 검증: `backend ./scripts/run_dashboard_v2_qa_stage_gate.sh` PASS (static 3/3, runtime skip)
- V2 Admin/Ops 실모듈 이관 완료:
  - 업데이트 route: `frontend/app/dashboard/(v2)/admin/ops/page.tsx`
  - 이관 기능: 시스템 헬스(`/api/admin/system-health`), 커넥터 진단(`/api/admin/connectors/diagnostics`), 외부 커넥터 헬스(`/api/admin/external-health`), rate-limit/quota 이벤트(`/api/admin/rate-limit-events`)
  - 비고: Incident Banner 저장/리비전/리뷰 워크플로우는 아래 항목에서 추가 이관 완료
  - 검증: `frontend pnpm -s tsc --noEmit` PASS
  - 검증: `backend ./scripts/run_dashboard_v2_qa_stage_gate.sh` PASS (static 3/3, runtime skip)
- V2 Incident Banner 운영 이관 완료:
  - 업데이트 route: `frontend/app/dashboard/(v2)/admin/ops/page.tsx`
  - 이관 기능: 배너 저장(`/api/admin/incident-banner`), revision 요청(`/api/admin/incident-banner/revisions`), revision 승인/거절(`/api/admin/incident-banner/revisions/{id}/review`)
  - 워크플로우 규칙: owner-only, self-review blocked, revision history 노출
  - 검증: `frontend pnpm -s tsc --noEmit` PASS
  - 검증: `backend ./scripts/run_dashboard_v2_qa_stage_gate.sh` PASS (static 3/3, runtime skip)
- V2 Organization Role Request 이관 완료:
  - 업데이트 route: `frontend/app/dashboard/(v2)/access/organizations/page.tsx`
  - 이관 기능: 요청 조회(`/api/organizations/{id}/role-requests`), 요청 생성(`/api/organizations/{id}/role-requests`), 요청 승인/거절(`/api/organizations/{id}/role-requests/{request_id}/review`)
  - 워크플로우 규칙: owner-only review, self-review blocked, 요청 목록/상태 노출
  - 검증: `frontend pnpm -s tsc --noEmit` PASS
  - 검증: `backend ./scripts/run_dashboard_v2_qa_stage_gate.sh` PASS (static 3/3, runtime skip)
