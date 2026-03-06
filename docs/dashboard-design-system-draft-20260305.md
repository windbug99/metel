# Dashboard Design System (2026-03-06)

기준 프리셋:
- create URL: `https://ui.shadcn.com/create?base=radix&style=nova&baseColor=zinc&theme=teal&iconLibrary=lucide&font=geist&menuAccent=subtle&menuColor=default&radius=small&item=preview`
- Base: `radix`
- Style: `nova`
- Base Color: `zinc`
- Theme Accent: `teal`
- Icon Library: `lucide`
- Font: `geist`
- Menu Accent: `subtle`
- Menu Color: `default`
- Radius: `small`

## 1. Scope

이 문서는 Dashboard V2의 UI 토큰, 컴포넌트 스타일, 레이아웃 기준을 정의한다.
다른 문서/과거 초안 기준은 폐기하고 본 문서를 단일 기준(Source of Truth)으로 사용한다.

적용 범위:
- `frontend/app/globals.css`
- `frontend/components/dashboard-v2/**`
- `frontend/app/dashboard/(v2)/**`
- dashboard shell/sidebar/topbar/cards/forms/tables

## 2. Typography

폰트:
- Primary UI Font: `Geist Sans`
- Mono/Data Font: `Geist Mono`

기본 타입:
- body: `14px / 22px / 500`
- body-sm: `13px / 20px / 500`
- caption: `12px / 16px / 500`
- h1: `24px / 32px / 700`
- h2: `20px / 28px / 700`
- h3: `16px / 24px / 600`
- display: `28px / 36px / 700`

사이드바 메뉴:
- depth0 menu item: `text-sm font-medium`
- depth1 submenu item: `text-sm font-medium`
- section label: `text-xs font-medium`

## 3. Radius, Border, Elevation

Radius:
- global radius token: `--radius: 0.375rem` (small)
- card/input/button: `--radius`

Border:
- 기본 border 두께: `1px`
- 사용 클래스: `border` (필요 시 `border-2` 명시)

Shadow:
- light `--shadow-sm`: `0 1px 2px rgba(16, 24, 40, 0.06)`
- light `--shadow-md`: `0 6px 18px rgba(16, 24, 40, 0.08)`
- dark `--shadow-sm`: `0 1px 2px rgba(2, 6, 23, 0.5)`
- dark `--shadow-md`: `0 10px 24px rgba(2, 6, 23, 0.55)`

## 4. Color Tokens

원칙:
- 모든 대시보드 UI 색상은 semantic token으로만 사용
- 신규 하드코딩 색상(hex/rgb/hsl) 금지
- 상태색은 semantic alias로만 사용

### 4.1 Light Tokens (`:root`)

- `--background: oklch(1 0 0)`
- `--foreground: oklch(0.141 0.005 285.823)`
- `--card: oklch(1 0 0)`
- `--card-foreground: oklch(0.141 0.005 285.823)`
- `--popover: oklch(1 0 0)`
- `--popover-foreground: oklch(0.141 0.005 285.823)`
- `--primary: oklch(0.21 0.006 285.885)`
- `--primary-foreground: oklch(0.985 0 0)`
- `--secondary: oklch(0.967 0.001 286.375)`
- `--secondary-foreground: oklch(0.21 0.006 285.885)`
- `--muted: oklch(0.967 0.001 286.375)`
- `--muted-foreground: oklch(0.552 0.016 285.938)`
- `--accent: oklch(0.967 0.001 286.375)`
- `--accent-foreground: oklch(0.21 0.006 285.885)`
- `--destructive: oklch(0.577 0.245 27.325)`
- `--border: oklch(0.92 0.004 286.32)`
- `--input: oklch(0.92 0.004 286.32)`
- `--ring: oklch(0.705 0.015 286.067)`
- `--chart-1: oklch(0.646 0.222 41.116)`
- `--chart-2: oklch(0.6 0.118 184.704)`
- `--chart-3: oklch(0.398 0.07 227.392)`
- `--chart-4: oklch(0.828 0.189 84.429)`
- `--chart-5: oklch(0.769 0.188 70.08)`

Sidebar tokens (light):
- `--sidebar: oklch(0.985 0 0)`
- `--sidebar-foreground: oklch(0.141 0.005 285.823)`
- `--sidebar-primary: oklch(0.21 0.006 285.885)`
- `--sidebar-primary-foreground: oklch(0.985 0 0)`
- `--sidebar-accent: oklch(0.967 0.001 286.375)`
- `--sidebar-accent-foreground: oklch(0.21 0.006 285.885)`
- `--sidebar-border: oklch(0.92 0.004 286.32)`
- `--sidebar-ring: oklch(0.705 0.015 286.067)`

### 4.2 Dark Tokens (`.dark`)

- `--background: oklch(0.141 0.005 285.823)`
- `--foreground: oklch(0.985 0 0)`
- `--card: oklch(0.21 0.006 285.885)`
- `--card-foreground: oklch(0.985 0 0)`
- `--popover: oklch(0.21 0.006 285.885)`
- `--popover-foreground: oklch(0.985 0 0)`
- `--primary: oklch(0.92 0.004 286.32)`
- `--primary-foreground: oklch(0.21 0.006 285.885)`
- `--secondary: oklch(0.274 0.006 286.033)`
- `--secondary-foreground: oklch(0.985 0 0)`
- `--muted: oklch(0.274 0.006 286.033)`
- `--muted-foreground: oklch(0.705 0.015 286.067)`
- `--accent: oklch(0.274 0.006 286.033)`
- `--accent-foreground: oklch(0.985 0 0)`
- `--destructive: oklch(0.704 0.191 22.216)`
- `--border: oklch(1 0 0 / 10%)`
- `--input: oklch(1 0 0 / 15%)`
- `--ring: oklch(0.552 0.016 285.938)`
- `--chart-1: oklch(0.488 0.243 264.376)`
- `--chart-2: oklch(0.696 0.17 162.48)`
- `--chart-3: oklch(0.769 0.188 70.08)`
- `--chart-4: oklch(0.627 0.265 303.9)`
- `--chart-5: oklch(0.645 0.246 16.439)`

Sidebar tokens (dark):
- `--sidebar: oklch(0.21 0.006 285.885)`
- `--sidebar-foreground: oklch(0.985 0 0)`
- `--sidebar-primary: oklch(0.488 0.243 264.376)`
- `--sidebar-primary-foreground: oklch(0.985 0 0)`
- `--sidebar-accent: oklch(0.274 0.006 286.033)`
- `--sidebar-accent-foreground: oklch(0.985 0 0)`
- `--sidebar-border: oklch(1 0 0 / 10%)`
- `--sidebar-ring: oklch(0.552 0.016 285.938)`

### 4.3 Semantic Aliases

- `--success: var(--chart-2)`
- `--warning: var(--chart-4)`
- `--info: var(--chart-1)`
- `--danger: var(--destructive)`

Compatibility aliases:
- `--surface: var(--card)`
- `--surface-subtle: var(--muted)`
- `--text-secondary: var(--muted-foreground)`
- `--brand-500: var(--primary)`
- `--brand-600: var(--primary)`

## 5. Sidebar / Topbar Layout Rules

- Sidebar: 화면 높이 100% 고정 (`h-svh`) + 독립 스크롤
- Content: 본문 영역만 스크롤 (`overflow-y-auto`)
- Topbar: 고정 높이 (`h-16`)
- Sidebar header(조직 선택 영역): Topbar와 동일 높이 (`h-16`)
- 메뉴 시각 톤: `menuAccent=subtle`, `menuColor=default`

## 6. Profile Menu Rules

- sidebar footer profile 버튼:
  - 아바타 이미지는 사용하지 않음
  - 로그인 사용자 `username`, `email` 출력
- profile dropdown action:
  - `Settings`
  - `Sign out`

동작:
- `Settings` -> `/dashboard/profile`
- `Sign out` -> auth sign out

## 7. Validation Checklist

- [ ] Light/Dark 토큰이 `globals.css`와 문서 값이 일치한다.
- [ ] `:root`와 `.dark`에 `--muted`, `--border`가 모두 존재한다.
- [ ] Sidebar 메뉴가 `text-sm font-medium`을 사용한다.
- [ ] 본문 상단 padding `24px`(`pt-6`) 적용.
- [ ] 대시보드 컴포넌트에서 하드코딩 색상 신규 사용 없음.

## 8. Implementation Order

1. `globals.css` 토큰 정합성 반영 (`--muted`, `--border` 포함)
2. dashboard shell/sidebar/topbar 타이포/border/radius 점검
3. 컴포넌트별 semantic token 사용 점검
4. 타입체크/빌드 검증

