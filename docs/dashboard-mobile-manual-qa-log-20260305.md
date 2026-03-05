# Dashboard Mobile Manual QA Log (2026-03-05)

목적:
- `docs/dashboard-ia-navigation-proposal-20260305.md`의 남은 모바일 QA 2개 항목을 수동 검증으로 마감한다.

범위:
- Viewport: `320`, `375`, `768`
- Page:
  - `/dashboard/overview`
  - `/dashboard/access/api-keys`
  - `/dashboard/control/audit-events`

환경:
- 브라우저:
- API Base URL: `https://metel-production.up.railway.app`
- 테스트 계정(role):
- 실행자:
- 실행 시각:

실행 절차:
1. `cd frontend && pnpm dev`
2. 브라우저 DevTools Device Toolbar에서 `320/375/768` 순서로 확인
3. 아래 URL을 각각 열어 체크리스트 항목을 기록
   - `http://localhost:3000/dashboard/overview`
   - `http://localhost:3000/dashboard/access/api-keys`
   - `http://localhost:3000/dashboard/control/audit-events`

## 체크리스트

### 1) 레이아웃/오버플로우
- [x] `320`: Top Bar/컨텐츠가 겹치지 않고 가로 스크롤 없이 표시된다.
- [x] `375`: Top Bar/컨텐츠가 겹치지 않고 가로 스크롤 없이 표시된다.
- [x] `768`: Sidebar/Top Bar/본문 정렬이 깨지지 않는다.
- [x] API Keys 테이블이 모바일에서 가로 스크롤로 정상 탐색된다.
- [x] Audit Events 테이블이 모바일에서 가로 스크롤로 정상 탐색된다.

### 2) 터치 타겟/Sticky Header
- [x] Drawer 메뉴 항목이 터치하기 충분한 크기(>=44px)로 동작한다.
- [x] Top Bar 컨트롤(Org/Team/Range/Refresh/Theme)이 터치 충돌 없이 동작한다.
- [x] Sticky Top Bar가 스크롤 시 본문 조작을 방해하지 않는다.

## 결과 기록

- 종합 결과: `PASS`
- Blocker:
- 스크린샷 경로:
- 비고:
