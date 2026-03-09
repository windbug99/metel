"use client";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useCallback, useEffect, useMemo, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

import { dashboardApiGet, dashboardApiRequest } from "../../lib/dashboard-v2-client";
import { supabase } from "../../lib/supabase";
import DashboardAppSidebar from "./app-sidebar";
import AlertBanner from "./alert-banner";
import { SiteHeader } from "./sidebar07/site-header";
import { useIsMobile } from "@/hooks/use-mobile";
import {
  buildBreadcrumb,
  GLOBAL_QUERY_KEYS,
  PAGE_QUERY_KEYS,
  buildNavItems,
  currentPageKey,
  pageTitle,
  type NavItem,
  type PermissionSnapshot,
} from "./nav-model";

type DashboardScope = "org" | "team" | "user";
type IncidentBannerPayload = {
  organization_id?: number | null;
  enabled?: boolean;
  message?: string | null;
  severity?: "info" | "warning" | "critical" | string;
  starts_at?: string | null;
  ends_at?: string | null;
  updated_at?: string | null;
};
type OrganizationOption = {
  id: number;
  name: string;
};

function parseOrgId(value: string): number | null {
  const text = String(value || "").trim();
  if (!text || text === "all") {
    return null;
  }
  const parsed = Number(text);
  return Number.isFinite(parsed) ? parsed : null;
}

function shouldShowIncidentBanner(payload: IncidentBannerPayload | null): boolean {
  if (!payload || !payload.enabled || !String(payload.message || "").trim()) {
    return false;
  }
  const now = Date.now();
  if (payload.starts_at) {
    const start = new Date(payload.starts_at).getTime();
    if (Number.isFinite(start) && now < start) {
      return false;
    }
  }
  if (payload.ends_at) {
    const end = new Date(payload.ends_at).getTime();
    if (Number.isFinite(end) && now > end) {
      return false;
    }
  }
  return true;
}

function normalizeDashboardScope(params: URLSearchParams): boolean {
  let changed = false;
  const rawScope = (params.get("scope") ?? "").trim().toLowerCase();
  const scope: DashboardScope = rawScope === "org" || rawScope === "team" || rawScope === "user" ? rawScope : "user";
  if (rawScope !== scope) {
    params.set("scope", scope);
    changed = true;
  }

  const org = (params.get("org") ?? "").trim();
  const team = (params.get("team") ?? "").trim();

  if (scope === "user") {
    if (params.has("org")) {
      params.delete("org");
      changed = true;
    }
    if (params.has("team")) {
      params.delete("team");
      changed = true;
    }
    return changed;
  }

  if (scope === "org") {
    if (!org || org === "all") {
      params.set("scope", "user");
      params.delete("org");
      params.delete("team");
      return true;
    }
    if (params.has("team")) {
      params.delete("team");
      changed = true;
    }
    return changed;
  }

  if (!org || org === "all" || !team || team === "all") {
    params.set("scope", "user");
    params.delete("org");
    params.delete("team");
    return true;
  }
  return changed;
}

export default function DashboardV2Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();
  const [theme, setTheme] = useState<"light" | "dark">("light");
  const [permissionSnapshot, setPermissionSnapshot] = useState<PermissionSnapshot | null>(null);
  const [permissionLoading, setPermissionLoading] = useState(true);
  const [permissionError, setPermissionError] = useState<string | null>(null);
  const [forbiddenBanner, setForbiddenBanner] = useState<string | null>(null);
  const [orgOptions, setOrgOptions] = useState<OrganizationOption[]>([]);
  const [incidentBanner, setIncidentBanner] = useState<IncidentBannerPayload | null>(null);
  const [dismissedIncidentUpdatedAt, setDismissedIncidentUpdatedAt] = useState<string | null>(null);
  const [signingOut, setSigningOut] = useState(false);
  const [viewerUsername, setViewerUsername] = useState("user");
  const [viewerEmail, setViewerEmail] = useState("");
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);
  const [createOrgDialogOpen, setCreateOrgDialogOpen] = useState(false);
  const [createOrgName, setCreateOrgName] = useState("");
  const [creatingOrg, setCreatingOrg] = useState(false);
  const [createOrgError, setCreateOrgError] = useState<string | null>(null);
  const isMobile = useIsMobile();

  const title = useMemo(() => pageTitle(pathname), [pathname]);
  const globalSearchEnabled = process.env.NEXT_PUBLIC_DASHBOARD_GLOBAL_SEARCH_ENABLED === "true";
  const pageKey = useMemo(() => currentPageKey(pathname), [pathname]);
  const orgIds = permissionSnapshot?.org_ids ?? [];
  const teamIds = permissionSnapshot?.team_ids ?? [];

  const navItems = useMemo(() => buildNavItems(permissionSnapshot), [permissionSnapshot]);

  const buildNavHref = useCallback(
    (targetPath: string, section?: NavItem["section"]) => {
      const params = new URLSearchParams();
      for (const key of GLOBAL_QUERY_KEYS) {
        const value = searchParams.get(key);
        if (value) {
          params.set(key, value);
        }
      }

      if (section === "user") {
        params.set("scope", "user");
        params.delete("org");
        params.delete("team");
      } else if (section === "organization") {
        const orgParam = (params.get("org") ?? "").trim();
        if ((!orgParam || orgParam === "all") && orgIds.length > 0) {
          params.set("org", String(orgIds[0]));
        }
        params.set("scope", params.get("org") ? "org" : "user");
        params.delete("team");
      } else if (section === "team") {
        const orgParam = (params.get("org") ?? "").trim();
        const teamParam = (params.get("team") ?? "").trim();
        if ((!orgParam || orgParam === "all") && orgIds.length > 0) {
          params.set("org", String(orgIds[0]));
        }
        if ((!teamParam || teamParam === "all") && teamIds.length > 0) {
          params.set("team", String(teamIds[0]));
        }
        const hasOrg = Boolean((params.get("org") ?? "").trim());
        const hasTeam = Boolean((params.get("team") ?? "").trim());
        if (hasOrg && hasTeam) {
          params.set("scope", "team");
        } else if (hasOrg) {
          params.set("scope", "org");
          params.delete("team");
        } else {
          params.set("scope", "user");
          params.delete("org");
          params.delete("team");
        }
      }

      normalizeDashboardScope(params);
      const encoded = params.toString();
      return encoded ? `${targetPath}?${encoded}` : targetPath;
    },
    [orgIds, searchParams, teamIds]
  );

  const currentScopeParam = (searchParams.get("scope") ?? "").trim().toLowerCase();
  const currentScope: DashboardScope =
    currentScopeParam === "org" || currentScopeParam === "team" || currentScopeParam === "user" ? currentScopeParam : "user";
  const currentOrg = currentScope === "org" || currentScope === "team" ? searchParams.get("org") ?? "all" : "all";
  const currentTeam = currentScope === "team" ? searchParams.get("team") ?? "all" : "all";
  const currentRange = searchParams.get("range") ?? "24h";
  const isMemberRole = permissionSnapshot?.role === "member";
  const breadcrumb = useMemo(() => buildBreadcrumb(pathname, currentScope), [currentScope, pathname]);
  const activeOrgId = useMemo(() => {
    const fromQuery = parseOrgId(currentOrg);
    if (fromQuery !== null) {
      return fromQuery;
    }
    if (orgIds.length > 0) {
      return Number(orgIds[0]);
    }
    return null;
  }, [currentOrg, orgIds]);
  const currentOrgName = useMemo(() => {
    if (currentOrg === "all") {
      return null;
    }
    const orgId = parseOrgId(currentOrg);
    if (orgId === null) {
      return null;
    }
    const hit = orgOptions.find((item) => item.id === orgId);
    return hit?.name ?? null;
  }, [currentOrg, orgOptions]);

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
      normalizeDashboardScope(params);
      const encoded = params.toString();
      router.replace(encoded ? `${pathname}?${encoded}` : pathname);
    },
    [pathname, router, searchParams]
  );

  const fetchPermissions = useCallback(async () => {
    const result = await dashboardApiGet<PermissionSnapshot>("/api/me/permissions");
    if (result.status === 401) {
      const nextPath =
        typeof window !== "undefined" ? `${window.location.pathname}${window.location.search}` : pathname;
      const next = encodeURIComponent(nextPath);
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
  }, [pathname, router]);

  const fetchOrganizations = useCallback(async () => {
    const result = await dashboardApiGet<{ items?: Array<{ id?: number; name?: string | null }> }>("/api/organizations");
    if (!result.ok || !result.data || !Array.isArray(result.data.items)) {
      return;
    }
    const next = result.data.items
      .map((item) => {
        const id = Number(item.id);
        if (!Number.isFinite(id)) {
          return null;
        }
        return {
          id,
          name: String(item.name || `Org #${id}`),
        };
      })
      .filter((item): item is OrganizationOption => item !== null);
    setOrgOptions(next);
  }, []);

  useEffect(() => {
    void fetchPermissions();
  }, [fetchPermissions]);

  useEffect(() => {
    if (!permissionSnapshot) {
      setOrgOptions([]);
      return;
    }
    void fetchOrganizations();
  }, [fetchOrganizations, permissionSnapshot]);

  useEffect(() => {
    if (!permissionSnapshot || activeOrgId === null) {
      setIncidentBanner(null);
      return;
    }

    let active = true;
    const fetchIncidentBanner = async () => {
      const result = await dashboardApiGet<IncidentBannerPayload>(`/api/admin/incident-banner?organization_id=${activeOrgId}`);
      if (!active) {
        return;
      }
      if (!result.ok || !result.data) {
        setIncidentBanner(null);
        return;
      }
      setIncidentBanner(result.data);
    };

    void fetchIncidentBanner();
    return () => {
      active = false;
    };
  }, [activeOrgId, permissionSnapshot]);

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
    const params = new URLSearchParams(searchParams.toString());
    const changed = normalizeDashboardScope(params);
    if (!changed) {
      return;
    }
    const encoded = params.toString();
    router.replace(encoded ? `${pathname}?${encoded}` : pathname);
  }, [pathname, router, searchParams]);

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
    if (currentScope === "user") {
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

    if (currentScope === "team") {
      const teamParam = params.get("team");
      if (teamIds.length === 1 && (!teamParam || teamParam === "all")) {
        params.set("team", String(teamIds[0]));
        changed = true;
      } else if (isMemberRole && teamIds.length > 0 && teamParam === "all") {
        params.set("team", String(teamIds[0]));
        changed = true;
      }
    }

    if (!changed) {
      return;
    }
    const encoded = params.toString();
    router.replace(encoded ? `${pathname}?${encoded}` : pathname);
  }, [currentScope, isMemberRole, orgIds, pathname, permissionSnapshot, router, searchParams, teamIds]);

  const triggerRefresh = useCallback(() => {
    void fetchPermissions();
    void fetchOrganizations();
    if (typeof window !== "undefined") {
      window.dispatchEvent(
        new CustomEvent("dashboard:v2:refresh", {
          detail: { path: pathname, at: Date.now() },
        })
      );
    }
  }, [fetchOrganizations, fetchPermissions, pathname]);

  useEffect(() => {
    const handler = () => {
      void fetchOrganizations();
    };
    window.addEventListener("dashboard:v2:orgs-updated", handler as EventListener);
    return () => {
      window.removeEventListener("dashboard:v2:orgs-updated", handler as EventListener);
    };
  }, [fetchOrganizations]);

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
    setCreateOrgError(null);
    setCreateOrgDialogOpen(true);
    if (isMobile) {
      setMobileSidebarOpen(false);
    }
  }, [isMobile]);

  const handleCreateOrganization = useCallback(async () => {
    const name = createOrgName.trim();
    if (!name) {
      setCreateOrgError("Organization name is required.");
      return;
    }
    setCreatingOrg(true);
    setCreateOrgError(null);

    const result = await dashboardApiRequest("/api/organizations", {
      method: "POST",
      body: { name },
    });
    if (result.status === 401) {
      const nextPath = typeof window !== "undefined" ? `${window.location.pathname}${window.location.search}` : pathname;
      const next = encodeURIComponent(nextPath);
      router.replace(`/?next=${next}`);
      setCreatingOrg(false);
      return;
    }
    if (result.status === 403) {
      setCreateOrgError("Owner or admin role required to create organization.");
      setCreatingOrg(false);
      return;
    }
    if (!result.ok) {
      setCreateOrgError(result.error ?? "Failed to create organization.");
      setCreatingOrg(false);
      return;
    }

    setCreateOrgName("");
    setCreateOrgDialogOpen(false);
    setCreatingOrg(false);
    void fetchPermissions();
    if (typeof window !== "undefined") {
      window.dispatchEvent(
        new CustomEvent("dashboard:v2:refresh", {
          detail: { path: pathname, at: Date.now() },
        })
      );
    }
  }, [createOrgName, fetchPermissions, pathname, router]);

  return (
    <div className="h-svh overflow-hidden bg-background text-foreground">
      <Dialog open={createOrgDialogOpen} onOpenChange={setCreateOrgDialogOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Create organization</DialogTitle>
            <DialogDescription>Create a new organization and refresh current organization list.</DialogDescription>
          </DialogHeader>
          <form
            className="space-y-3"
            onSubmit={(event) => {
              event.preventDefault();
              void handleCreateOrganization();
            }}
          >
            <Input
              value={createOrgName}
              onChange={(event) => setCreateOrgName(event.target.value)}
              placeholder="Organization name"
              className="h-10"
            />
            {createOrgError ? <p className="text-xs text-destructive">{createOrgError}</p> : null}
            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                className="border-border bg-card text-foreground hover:bg-accent hover:text-accent-foreground"
                onClick={() => setCreateOrgDialogOpen(false)}
              >
                Cancel
              </Button>
              <Button
                type="submit"
                disabled={creatingOrg}
                className="bg-sidebar-primary text-sidebar-primary-foreground hover:bg-sidebar-primary/90"
              >
                {creatingOrg ? "Creating..." : "Create Organization"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
      <div className="flex h-svh w-full overflow-hidden">
        <DashboardAppSidebar
          pathname={pathname}
          navItems={navItems}
          buildNavHref={buildNavHref}
          roleLabel={permissionSnapshot?.role ?? "loading"}
          currentOrg={currentOrg}
          currentOrgName={currentOrgName}
          orgIds={orgIds}
          orgOptions={orgOptions}
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
            currentScope={currentScope}
            currentOrg={currentOrg}
            breadcrumb={breadcrumb}
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
              {shouldShowIncidentBanner(incidentBanner) &&
              dismissedIncidentUpdatedAt !== (incidentBanner?.updated_at ?? null) ? (
                <AlertBanner
                  message={String(incidentBanner?.message || "")}
                  tone={incidentBanner?.severity === "critical" ? "danger" : incidentBanner?.severity === "info" ? "info" : "warning"}
                  dismissible
                  onDismiss={() => setDismissedIncidentUpdatedAt(incidentBanner?.updated_at ?? "manual")}
                />
              ) : null}
              {permissionLoading ? <p className="mb-3 text-sm text-muted-foreground">Loading permissions...</p> : null}
              {children}
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}
