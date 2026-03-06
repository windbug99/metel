"use client";

import { Button } from "@/components/ui/button";
import { useCallback, useEffect, useMemo, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

import { buildNextPath, dashboardApiGet } from "../../lib/dashboard-v2-client";
import { supabase } from "../../lib/supabase";
import DashboardAppSidebar from "./app-sidebar";
import AlertBanner from "./alert-banner";
import { SiteHeader } from "./sidebar07/site-header";
import { useIsMobile } from "@/hooks/use-mobile";
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
  const [viewerUsername, setViewerUsername] = useState("user");
  const [viewerEmail, setViewerEmail] = useState("");
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);
  const isMobile = useIsMobile();

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
    let active = true;

    const hydrateViewer = async () => {
      const { data } = await supabase.auth.getUser();
      if (!active) {
        return;
      }
      const user = data.user;
      if (!user) {
        return;
      }

      const username =
        String(user.user_metadata?.username ?? "").trim() ||
        String(user.user_metadata?.name ?? "").trim() ||
        String(user.user_metadata?.full_name ?? "").trim() ||
        (user.email ? user.email.split("@")[0] : "") ||
        "user";

      setViewerUsername(username);
      setViewerEmail(user.email ?? "");
    };

    void hydrateViewer();

    return () => {
      active = false;
    };
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

  useEffect(() => {
    const applyThemeFromStorage = () => {
      const stored = window.localStorage.getItem("dashboard-v2-theme");
      if (stored === "light" || stored === "dark") {
        setTheme(stored);
      }
    };

    const onThemeEvent = (event: Event) => {
      const custom = event as CustomEvent<{ theme?: "light" | "dark" }>;
      const next = custom.detail?.theme;
      if (next === "light" || next === "dark") {
        setTheme(next);
      } else {
        applyThemeFromStorage();
      }
    };

    const onStorage = (event: StorageEvent) => {
      if (event.key === "dashboard-v2-theme") {
        applyThemeFromStorage();
      }
    };

    window.addEventListener("dashboard:v2:theme", onThemeEvent as EventListener);
    window.addEventListener("storage", onStorage);
    return () => {
      window.removeEventListener("dashboard:v2:theme", onThemeEvent as EventListener);
      window.removeEventListener("storage", onStorage);
    };
  }, []);

  useEffect(() => {
    const root = document.documentElement;
    const body = document.body;
    const darkMode = theme === "dark";
    root.classList.toggle("dark", darkMode);
    body.classList.toggle("theme-dark", darkMode);
    return () => {
      root.classList.remove("dark");
      body.classList.remove("theme-dark");
    };
  }, [theme]);

  const handleSignOut = useCallback(async () => {
    setSigningOut(true);
    await supabase.auth.signOut();
    router.replace("/");
  }, [router]);

  const toggleSidebar = useCallback(() => {
    if (isMobile) {
      setMobileSidebarOpen((prev) => !prev);
      return;
    }
    setSidebarCollapsed((prev) => !prev);
  }, [isMobile]);

  const openCreateOrganizationModal = useCallback(() => {
    if (pathname.startsWith("/dashboard/access/organizations")) {
      window.dispatchEvent(new Event("dashboard:v2:open-create-organization"));
      return;
    }
    window.sessionStorage.setItem("dashboard:v2:open-create-organization", "1");
    router.push(buildNavHref("/dashboard/access/organizations"));
    if (isMobile) {
      setMobileSidebarOpen(false);
    }
  }, [buildNavHref, isMobile, pathname, router]);

  return (
    <div className="h-svh overflow-hidden bg-background text-foreground">
      <div className="flex h-svh w-full overflow-hidden">
        <DashboardAppSidebar
          pathname={pathname}
          navItems={navItems}
          buildNavHref={buildNavHref}
          roleLabel={permissionSnapshot?.role ?? "loading"}
          currentOrg={currentOrg}
          orgIds={orgIds}
          isMemberRole={isMemberRole}
          setGlobalQuery={setGlobalQuery}
          onAddOrganization={openCreateOrganizationModal}
          signingOut={signingOut}
          onSignOut={() => void handleSignOut()}
          username={viewerUsername}
          email={viewerEmail}
          collapsed={sidebarCollapsed}
          mobileOpen={mobileSidebarOpen}
          onCloseMobile={() => setMobileSidebarOpen(false)}
        />
        {mobileSidebarOpen ? (
          <Button
            type="button"
            className="fixed inset-0 z-30 bg-black/50 md:hidden"
            onClick={() => setMobileSidebarOpen(false)}
            aria-label="Close Sidebar Overlay"
          />
        ) : null}
        <main className="flex h-svh min-w-0 flex-1 flex-col overflow-hidden">
          <SiteHeader
            title={title}
            globalSearchEnabled={globalSearchEnabled}
            currentTeam={currentTeam}
            currentRange={currentRange}
            teamIds={teamIds}
            setGlobalQuery={setGlobalQuery}
            triggerRefresh={triggerRefresh}
            onToggleSidebar={toggleSidebar}
          />

          <div className="min-h-0 flex-1 overflow-y-auto">
            <div className="flex flex-col gap-4 p-4 pt-6 md:p-6">
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
          </div>
        </main>
      </div>
    </div>
  );
}
