"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

import { buildNextPath, dashboardApiGet } from "../../lib/dashboard-v2-client";
import { supabase } from "../../lib/supabase";
import DashboardAppSidebar from "./app-sidebar";
import AlertBanner from "./alert-banner";
import { SiteHeader } from "./sidebar07/site-header";
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar";
import {
  GLOBAL_QUERY_KEYS,
  PAGE_QUERY_KEYS,
  buildNavItems,
  currentPageKey,
  pageTitle,
  type PermissionSnapshot,
} from "./nav-model";

export default function DashboardV2Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();
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

  const navItems = useMemo(() => buildNavItems(permissionSnapshot), [permissionSnapshot]);

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
  const orgIds = permissionSnapshot?.org_ids ?? [];
  const teamIds = permissionSnapshot?.team_ids ?? [];
  const isMemberRole = permissionSnapshot?.role === "member";

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

  useEffect(() => {
    if (!permissionSnapshot) {
      return;
    }
    const params = new URLSearchParams(searchParams.toString());
    let changed = false;

    const orgParam = params.get("org");
    if (orgIds.length === 1 && (!orgParam || orgParam === "all")) {
      params.set("org", String(orgIds[0]));
      changed = true;
    } else if (isMemberRole && orgIds.length > 0 && orgParam === "all") {
      params.set("org", String(orgIds[0]));
      changed = true;
    }

    const teamParam = params.get("team");
    if (teamIds.length === 1 && (!teamParam || teamParam === "all")) {
      params.set("team", String(teamIds[0]));
      changed = true;
    } else if (isMemberRole && teamIds.length > 0 && teamParam === "all") {
      params.set("team", String(teamIds[0]));
      changed = true;
    }

    if (!changed) {
      return;
    }
    const encoded = params.toString();
    router.replace(encoded ? `${pathname}?${encoded}` : pathname);
  }, [isMemberRole, orgIds, pathname, permissionSnapshot, router, searchParams, teamIds]);

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
    <div className={`${theme === "dark" ? "theme-dark" : "theme-light"} min-h-screen bg-background text-foreground`}>
      <SidebarProvider>
        <DashboardAppSidebar
          pathname={pathname}
          navItems={navItems}
          buildNavHref={buildNavHref}
          roleLabel={permissionSnapshot?.role ?? "loading"}
          currentOrg={currentOrg}
          orgIds={orgIds}
          isMemberRole={isMemberRole}
          setGlobalQuery={setGlobalQuery}
          signingOut={signingOut}
          onSignOut={() => void handleSignOut()}
        />
        <SidebarInset className="min-w-0">
          <SiteHeader
            title={title}
            globalSearchEnabled={globalSearchEnabled}
            currentTeam={currentTeam}
            currentRange={currentRange}
            teamIds={teamIds}
            setGlobalQuery={setGlobalQuery}
            triggerRefresh={triggerRefresh}
            toggleTheme={toggleTheme}
            theme={theme}
          />

          {!globalSearchEnabled ? (
            <p className="border-b border-border px-4 py-2 text-[11px] text-muted-foreground md:px-6">
              Global Search is disabled until backend search API scope is finalized.
            </p>
          ) : null}

          <div className="flex flex-1 flex-col gap-4 p-4 pt-0 md:p-6 md:pt-0">
            {forbiddenBanner ? (
              <AlertBanner
                message={forbiddenBanner}
                tone="warning"
                dismissible
                onDismiss={() => setForbiddenBanner(null)}
              />
            ) : null}
            {permissionError ? <AlertBanner message={permissionError} tone="danger" /> : null}
            {permissionLoading ? <p className="mb-3 text-sm text-muted-foreground">Loading permissions...</p> : null}
            {children}
          </div>
        </SidebarInset>
      </SidebarProvider>
    </div>
  );
}
