# Dashboard V2 Sidebar-07 Rebuild Plan (2026-03-06)

## 1) Goal

- Rebuild dashboard shell UI from scratch using shadcn components.
- Align layout structure as closely as possible to `ui.shadcn.com/blocks#sidebar-07`.
- Apply `docs/dashboard-design-system-draft-20260305.md` style rules.
- Remove prior patch-style fixes (z-index, manual offset hacks) from shell behavior.

## 2) Current Problem Summary

- Sidebar appears as floating layer above topbar/body on desktop.
- Shell composition has diverged from sidebar-07 block patterns.
- Existing sidebar/topbar/body coupling is fragile under responsive and state changes.

## 3) Rebuild Principles

- Use a single layout contract:
  - `SidebarProvider -> AppSidebar -> SidebarInset -> SiteHeader -> Content`
- Keep shadcn sidebar primitives as source of truth.
- Avoid CSS hacks for offset (`ml`, absolute compensation, custom z-index band-aids).
- Isolate shell UI components by role:
  - team switcher
  - nav main
  - nav user
  - site header
- Preserve existing business logic:
  - RBAC-driven menu visibility
  - query-state (`org/team/range`) sync
  - auth redirect (401), forbidden banner (403), refresh event

## 4) Step-by-Step Implementation

### Step 1: Sidebar-07 Structure Components

- Add new components under `frontend/components/dashboard-v2/sidebar07/`:
  - `team-switcher.tsx`
  - `nav-main.tsx`
  - `nav-user.tsx`
  - `site-header.tsx`
- Implement these using shadcn primitives:
  - `Sidebar`, `SidebarHeader`, `SidebarContent`, `SidebarFooter`
  - `SidebarGroup`, `SidebarMenu`, `SidebarMenuButton`, `SidebarMenuSub*`
  - `SidebarTrigger`, `Breadcrumb`, `Separator`, `Input`, `Button`, `DropdownMenu`

### Step 2: New AppSidebar / Header Wiring

- Rebuild `dashboard-v2/app-sidebar.tsx` to compose:
  - `TeamSwitcher`
  - `NavMain`
  - `NavUser`
- Set sidebar mode as block-like:
  - `variant="inset"`
  - `collapsible="icon"`

### Step 3: Shell Replacement

- Replace shell rendering in `dashboard-v2/shell.tsx`:
  - Keep logic/state hooks unchanged.
  - Replace UI composition with new sidebar07 components.
  - Content wrapper follows block pattern (`flex flex-1 flex-col ...`).
- Remove dependency on legacy `topbar.tsx` / `nav-list.tsx` in shell flow.

### Step 4: Design-System Styling Pass

- Ensure shell-level classes follow design draft:
  - title/description typography
  - spacing scale
  - semantic tokens only (`background`, `muted`, `border`, `foreground`, etc.)
- Keep existing page-level styles untouched in this rebuild pass.

### Step 5: Validation

- Static/type:
  - `pnpm -C frontend tsc --noEmit`
- Structural checks:
  - Sidebar no longer overlays topbar/body in desktop.
  - Sidebar collapse/expand still keeps body alignment.
  - Mobile trigger opens sheet drawer correctly.
- Smoke paths:
  - `/dashboard/overview`
  - `/dashboard/access/organizations`
  - `/dashboard/integrations/webhooks`

## 5) Rollout / Safety

- Commit in small steps:
  1. new sidebar07 components
  2. shell wiring swap
  3. style alignment cleanup
- If a regression appears, rollback only latest step, not full branch.

## 6) Definition of Done

- Visual structure matches sidebar-07 shell contract.
- No floating sidebar overlap on desktop.
- Existing RBAC/query/auth-refresh behavior remains intact.
- Typecheck passes.

## 7) Execution Status (2026-03-06)

- Step 1: completed
  - Added:
    - `frontend/components/dashboard-v2/sidebar07/team-switcher.tsx`
    - `frontend/components/dashboard-v2/sidebar07/nav-main.tsx`
    - `frontend/components/dashboard-v2/sidebar07/nav-user.tsx`
    - `frontend/components/dashboard-v2/sidebar07/site-header.tsx`
- Step 2: completed
  - Rebuilt `frontend/components/dashboard-v2/app-sidebar.tsx`
  - Applied `Sidebar variant="inset" collapsible="icon"`
- Step 3: completed
  - Rewired `frontend/components/dashboard-v2/shell.tsx` to use `SiteHeader`
  - Removed legacy shell dependencies:
    - deleted `frontend/components/dashboard-v2/topbar.tsx`
    - deleted `frontend/components/dashboard-v2/nav-list.tsx`
- Step 4: completed
  - Replaced non-semantic color vars in:
    - `frontend/components/dashboard-v2/alert-banner.tsx`
    - `frontend/components/dashboard-v2/status-badge.tsx`
- Step 5: completed
  - `cd frontend && pnpm tsc --noEmit` passed

Result:
- Rebuild baseline is fully switched to shadcn sidebar-07 shell contract.

## 8) Design-System Rollout Status (2026-03-06, follow-up)

- Global token system updated in `frontend/app/globals.css`
  - radius small (`--radius: 0.375rem`)
  - semantic status aliases (`--success`, `--warning`, `--info`, `--danger`)
  - motion/elevation tokens (`--duration-fast`, `--duration-base`, `--easing-standard`, `--shadow-sm`, `--shadow-md`)
  - Geist typography baseline and dashboard utility classes (`.ds-h1`, `.ds-h2`, `.ds-body-sm`, `.ds-caption`)
- Dashboard V2 pages moved off legacy custom var class usage
  - replaced `text-[var(--...)]` / `bg-[var(--...)]` / `border-[var(--...)]` with semantic utility classes
  - verified no remaining `var(--brand|--muted|--text-secondary|--danger|--warning|--success|--surface|--status)` usage in `dashboard/(v2)` and `components/dashboard-v2`
- Validation
  - `cd frontend && pnpm tsc --noEmit` passed
