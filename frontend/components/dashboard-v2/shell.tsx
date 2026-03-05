"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

import { buildNextPath, dashboardApiGet } from "../../lib/dashboard-v2-client";
import { supabase } from "../../lib/supabase";
import AlertBanner from "./alert-banner";

type PermissionSnapshot = {
  user_id: string;
  role: string;
  permissions: {
    can_read_admin_ops: boolean;
  };
};

type NavItem = {
  href: string;
  label: string;
  visible: boolean;
};

const GLOBAL_QUERY_KEYS = ["org", "team", "range"] as const;
const PAGE_QUERY_KEYS: Record<string, string[]> = {
  overview: ["overview_window"],
  profile: ["profile_tab"],
  apiKeys: ["keys_status"],
  organizations: ["orgs_tab"],
  teamPolicy: ["team_tab"],
  policySimulator: ["sim_mode"],
  mcpUsage: ["usage_status"],
  mcpGuide: ["guide_tab"],
  integrations: ["integration_status"],
  oauthConnections: ["oauth_state"],
  auditEvents: ["audit_status"],
  auditSettings: ["audit_settings_tab"],
  adminOps: ["ops_tab"],
};

function currentPageKey(pathname: string): keyof typeof PAGE_QUERY_KEYS {
  if (pathname.startsWith("/dashboard/profile")) {
    return "profile";
  }
  if (pathname.startsWith("/dashboard/access/api-keys")) {
    return "apiKeys";
  }
  if (pathname.startsWith("/dashboard/access/organizations")) {
    return "organizations";
  }
  if (pathname.startsWith("/dashboard/access/team-policy")) {
    return "teamPolicy";
  }
  if (pathname.startsWith("/dashboard/control/policy-simulator")) {
    return "policySimulator";
  }
  if (pathname.startsWith("/dashboard/control/mcp-usage")) {
    return "mcpUsage";
  }
  if (pathname.startsWith("/dashboard/control/mcp-guide")) {
    return "mcpGuide";
  }
  if (pathname.startsWith("/dashboard/integrations/webhooks")) {
    return "integrations";
  }
  if (pathname.startsWith("/dashboard/integrations/oauth")) {
    return "oauthConnections";
  }
  if (pathname.startsWith("/dashboard/control/audit-events")) {
    return "auditEvents";
  }
  if (pathname.startsWith("/dashboard/control/audit-settings")) {
    return "auditSettings";
  }
  if (pathname.startsWith("/dashboard/admin/ops")) {
    return "adminOps";
  }
  return "overview";
}

function pageTitle(pathname: string): string {
  if (pathname.startsWith("/dashboard/profile")) {
    return "Profile";
  }
  if (pathname.startsWith("/dashboard/access/api-keys")) {
    return "API Keys";
  }
  if (pathname.startsWith("/dashboard/access/organizations")) {
    return "Organizations";
  }
  if (pathname.startsWith("/dashboard/access/team-policy")) {
    return "Team Policy";
  }
  if (pathname.startsWith("/dashboard/control/policy-simulator")) {
    return "Policy Simulator";
  }
  if (pathname.startsWith("/dashboard/control/mcp-usage")) {
    return "MCP Usage";
  }
  if (pathname.startsWith("/dashboard/control/mcp-guide")) {
    return "MCP Guide";
  }
  if (pathname.startsWith("/dashboard/integrations/webhooks")) {
    return "Integrations";
  }
  if (pathname.startsWith("/dashboard/integrations/oauth")) {
    return "OAuth Connections";
  }
  if (pathname.startsWith("/dashboard/control/audit-events")) {
    return "Audit Events";
  }
  if (pathname.startsWith("/dashboard/control/audit-settings")) {
    return "Audit Settings";
  }
  if (pathname.startsWith("/dashboard/admin/ops")) {
    return "Admin / Ops";
  }
  return "Overview";
}

export default function DashboardV2Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [theme, setTheme] = useState<"light" | "dark">("light");
  const [permissionSnapshot, setPermissionSnapshot] = useState<PermissionSnapshot | null>(null);
  const [permissionLoading, setPermissionLoading] = useState(true);
  const [permissionError, setPermissionError] = useState<string | null>(null);
  const [forbiddenBanner, setForbiddenBanner] = useState<string | null>(null);
  const [signingOut, setSigningOut] = useState(false);

  const title = useMemo(() => pageTitle(pathname), [pathname]);
  const globalSearchEnabled = process.env.NEXT_PUBLIC_DASHBOARD_GLOBAL_SEARCH_ENABLED === "true";
  const pageKey = useMemo(() => currentPageKey(pathname), [pathname]);

  const currentPathWithQuery = useMemo(() => {
    return buildNextPath(pathname, searchParams.toString() ? `?${searchParams.toString()}` : "");
  }, [pathname, searchParams]);

  const navItems = useMemo<NavItem[]>(() => {
    const canReadAdminOps = Boolean(permissionSnapshot?.permissions?.can_read_admin_ops);
    return [
      { href: "/dashboard/overview", label: "Overview", visible: true },
      { href: "/dashboard/profile", label: "Profile", visible: true },
      { href: "/dashboard/access/api-keys", label: "API Keys", visible: true },
      { href: "/dashboard/access/organizations", label: "Organizations", visible: true },
      { href: "/dashboard/access/team-policy", label: "Team Policy", visible: true },
      { href: "/dashboard/control/policy-simulator", label: "Policy Simulator", visible: true },
      { href: "/dashboard/control/mcp-usage", label: "MCP Usage", visible: true },
      { href: "/dashboard/control/mcp-guide", label: "MCP Guide", visible: true },
      { href: "/dashboard/integrations/webhooks", label: "Integrations", visible: true },
      { href: "/dashboard/integrations/oauth", label: "OAuth", visible: true },
      { href: "/dashboard/control/audit-events", label: "Audit Events", visible: true },
      { href: "/dashboard/control/audit-settings", label: "Audit Settings", visible: true },
      { href: "/dashboard/admin/ops", label: "Admin / Ops", visible: canReadAdminOps },
    ];
  }, [permissionSnapshot]);

  const buildNavHref = useCallback(
    (targetPath: string) => {
      const params = new URLSearchParams();
      for (const key of GLOBAL_QUERY_KEYS) {
        const value = searchParams.get(key);
        if (value) {
          params.set(key, value);
        }
      }
      const encoded = params.toString();
      return encoded ? `${targetPath}?${encoded}` : targetPath;
    },
    [searchParams]
  );

  const currentOrg = searchParams.get("org") ?? "all";
  const currentTeam = searchParams.get("team") ?? "all";
  const currentRange = searchParams.get("range") ?? "24h";

  const setGlobalQuery = useCallback(
    (next: Partial<Record<(typeof GLOBAL_QUERY_KEYS)[number], string>>) => {
      const params = new URLSearchParams(searchParams.toString());
      for (const key of GLOBAL_QUERY_KEYS) {
        const value = next[key];
        if (value === undefined) {
          continue;
        }
        if (!value || value === "all") {
          params.delete(key);
          continue;
        }
        params.set(key, value);
      }
      const encoded = params.toString();
      router.replace(encoded ? `${pathname}?${encoded}` : pathname);
    },
    [pathname, router, searchParams]
  );

  const fetchPermissions = useCallback(async () => {
    const result = await dashboardApiGet<PermissionSnapshot>("/api/me/permissions");
    if (result.status === 401) {
      const next = encodeURIComponent(currentPathWithQuery);
      router.replace(`/?next=${next}`);
      setPermissionLoading(false);
      return;
    }
    if (result.status === 403) {
      setForbiddenBanner("권한이 없어 요청이 거부되었습니다. 역할/범위를 확인해주세요.");
      setPermissionError("Access denied while loading permissions.");
      setPermissionLoading(false);
      return;
    }
    if (!result.ok || !result.data) {
      setPermissionError(result.error ?? "Failed to load permission snapshot.");
      setPermissionLoading(false);
      return;
    }

    setPermissionSnapshot(result.data);
    setPermissionError(null);
    setPermissionLoading(false);
  }, [currentPathWithQuery, router]);

  useEffect(() => {
    void fetchPermissions();
  }, [fetchPermissions]);

  useEffect(() => {
    const stored = window.localStorage.getItem("dashboard-v2-theme");
    if (stored === "light" || stored === "dark") {
      setTheme(stored);
      return;
    }
    const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    setTheme(prefersDark ? "dark" : "light");
  }, []);

  useEffect(() => {
    const allowed = new Set<string>([...GLOBAL_QUERY_KEYS, ...PAGE_QUERY_KEYS[pageKey]]);
    const params = new URLSearchParams(searchParams.toString());
    let changed = false;

    for (const key of Array.from(params.keys())) {
      if (!allowed.has(key)) {
        params.delete(key);
        changed = true;
      }
    }

    if (!changed) {
      return;
    }
    const encoded = params.toString();
    router.replace(encoded ? `${pathname}?${encoded}` : pathname);
  }, [pageKey, pathname, router, searchParams]);

  const visibleNavItems = navItems.filter((item) => item.visible);

  const triggerRefresh = useCallback(() => {
    void fetchPermissions();
    if (typeof window !== "undefined") {
      window.dispatchEvent(
        new CustomEvent("dashboard:v2:refresh", {
          detail: { path: pathname, at: Date.now() },
        })
      );
    }
  }, [fetchPermissions, pathname]);

  const toggleTheme = useCallback(() => {
    setTheme((prev) => {
      const next = prev === "light" ? "dark" : "light";
      window.localStorage.setItem("dashboard-v2-theme", next);
      return next;
    });
  }, []);

  const handleSignOut = useCallback(async () => {
    setSigningOut(true);
    await supabase.auth.signOut();
    router.replace("/");
  }, [router]);

  return (
    <div className={`${theme === "dark" ? "theme-dark" : "theme-light"} min-h-screen bg-[var(--background)] text-[var(--foreground)]`}>
      <div className="mx-auto flex w-full max-w-[1440px]">
        <aside className="sticky top-0 hidden h-screen w-64 shrink-0 border-r border-[var(--border)] bg-[var(--surface)] p-4 md:block">
          <p className="text-lg font-semibold">metel Dashboard</p>
          <p className="mt-1 text-xs text-[var(--muted)]">Route-based V2 Preview</p>
          <p className="mt-1 text-xs text-[var(--muted)]">role: {permissionSnapshot?.role ?? "loading"}</p>
          <nav className="mt-6 space-y-2">
            {visibleNavItems.map((item) => {
              const active = pathname === item.href;
              return (
                <Link
                  key={item.href}
                  href={buildNavHref(item.href)}
                  className={`block rounded-md px-3 py-2 text-sm ${
                    active
                      ? "bg-[var(--brand-100)] text-[var(--brand-600)]"
                      : "text-[var(--text-secondary)] hover:bg-[var(--surface-subtle)]"
                  }`}
                >
                  {item.label}
                </Link>
              );
            })}
          </nav>
          <div className="mt-8 border-t border-[var(--border)] pt-4">
            <Link href="/dashboard/legacy" className="text-xs text-[var(--muted)] underline">
              Go to legacy single-page dashboard
            </Link>
          </div>
        </aside>

        <main className="min-w-0 flex-1">
          <header className="sticky top-0 z-20 border-b border-[var(--border)] bg-[var(--surface)]/95 backdrop-blur">
            <div className="flex flex-col gap-3 px-4 py-3 md:flex-row md:items-center md:justify-between md:px-6">
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  className="ds-btn h-11 rounded-md px-3 text-sm md:hidden"
                  onClick={() => setDrawerOpen((prev) => !prev)}
                  aria-label="Toggle navigation drawer"
                >
                  Menu
                </button>
                <p className="text-xs text-[var(--muted)]">Dashboard / {title}</p>
              </div>
              <div className="flex flex-wrap items-center gap-2 md:justify-end">
                <input
                  type="search"
                  disabled={!globalSearchEnabled}
                  placeholder={
                    globalSearchEnabled ? "Search request_id / api_key / user_id / tool_name" : "Global search (coming soon)"
                  }
                  className="ds-input hidden h-10 w-64 rounded-md px-3 text-xs disabled:cursor-not-allowed disabled:bg-[var(--surface-subtle)] md:block"
                />
                <select
                  value={currentOrg}
                  onChange={(event) => setGlobalQuery({ org: event.target.value })}
                  className="ds-input h-11 min-w-[84px] rounded-md px-2 text-sm md:h-8 md:text-xs"
                >
                  <option value="all">Org: All</option>
                  <option value="1">Org: #1</option>
                  <option value="2">Org: #2</option>
                </select>
                <select
                  value={currentTeam}
                  onChange={(event) => setGlobalQuery({ team: event.target.value })}
                  className="ds-input h-11 min-w-[84px] rounded-md px-2 text-sm md:h-8 md:text-xs"
                >
                  <option value="all">Team: All</option>
                  <option value="1">Team: #1</option>
                  <option value="2">Team: #2</option>
                </select>
                <select
                  value={currentRange}
                  onChange={(event) => setGlobalQuery({ range: event.target.value })}
                  className="ds-input h-11 min-w-[72px] rounded-md px-2 text-sm md:h-8 md:text-xs"
                >
                  <option value="24h">24h</option>
                  <option value="7d">7d</option>
                </select>
                <button
                  type="button"
                  onClick={triggerRefresh}
                  className="ds-btn h-11 rounded-md px-3 text-sm md:h-8 md:text-xs"
                >
                  Refresh
                </button>
                <button
                  type="button"
                  onClick={toggleTheme}
                  className="ds-btn h-11 rounded-md px-3 text-sm md:h-8 md:text-xs"
                >
                  {theme === "dark" ? "Light" : "Dark"}
                </button>
                <button
                  type="button"
                  onClick={() => void handleSignOut()}
                  disabled={signingOut}
                  className="ds-btn h-11 rounded-md px-3 text-sm disabled:cursor-not-allowed disabled:opacity-60 md:h-8 md:text-xs"
                >
                  {signingOut ? "Signing out..." : "Sign out"}
                </button>
              </div>
            </div>
            {!globalSearchEnabled ? (
              <p className="border-t border-[var(--border)] px-4 py-2 text-[11px] text-[var(--muted)] md:px-6">
                Global Search is disabled until backend search API scope is finalized.
              </p>
            ) : null}
            {drawerOpen ? (
              <nav className="space-y-1 border-t border-[var(--border)] px-4 py-3 md:hidden">
                {visibleNavItems.map((item) => {
                  const active = pathname === item.href;
                  return (
                    <Link
                      key={item.href}
                      href={buildNavHref(item.href)}
                      className={`block rounded-md px-3 py-3 text-sm ${
                        active
                          ? "bg-[var(--brand-100)] text-[var(--brand-600)]"
                          : "text-[var(--text-secondary)] hover:bg-[var(--surface-subtle)]"
                      }`}
                      onClick={() => setDrawerOpen(false)}
                    >
                      {item.label}
                    </Link>
                  );
                })}
              </nav>
            ) : null}
          </header>

          <div className="p-4 md:p-6">
            {forbiddenBanner ? (
              <AlertBanner
                message={forbiddenBanner}
                tone="warning"
                dismissible
                onDismiss={() => setForbiddenBanner(null)}
              />
            ) : null}
            {permissionError ? <AlertBanner message={permissionError} tone="danger" /> : null}
            {permissionLoading ? <p className="mb-3 text-sm text-[var(--muted)]">Loading permissions...</p> : null}
            {children}
          </div>
        </main>
      </div>
    </div>
  );
}
