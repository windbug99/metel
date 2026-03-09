"use client";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { useCallback, useEffect, useMemo, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Loader2 } from "lucide-react";

import { buildNextPath, dashboardApiGet, dashboardApiRequest } from "../../../../../lib/dashboard-v2-client";
import { resolveDashboardScope } from "../../../../../lib/dashboard-scope";
import PageTitleWithTooltip from "@/components/dashboard-v2/page-title-with-tooltip";

type OAuthStatus = {
  connected: boolean;
  integration?: {
    workspace_name?: string | null;
    workspace_id?: string | null;
    updated_at?: string | null;
  } | null;
};

type OAuthStartPayload = {
  ok: boolean;
  auth_url: string;
};

type OrganizationOAuthPolicy = {
  allowed_providers?: string[];
  required_providers?: string[];
  blocked_providers?: string[];
  approval_workflow?: Record<string, unknown> | null;
};

type PermissionSnapshot = {
  permissions?: {
    can_manage_integrations?: boolean;
  };
};

type OrganizationOAuthPolicyPayload = {
  item?: {
    organization_id?: number | string;
    policy_json?: OrganizationOAuthPolicy;
    version?: number;
    updated_at?: string | null;
  };
};

function formatDate(value?: string | null): string {
  if (!value) {
    return "-";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString();
}

function ServiceRow({
  name,
  status,
  error,
  busy,
  onConnect,
  onDisconnect,
}: {
  name: string;
  status: OAuthStatus | null;
  error: string | null;
  busy: boolean;
  onConnect: () => void;
  onDisconnect: () => void;
}) {
  return (
    <article className="rounded-md border border-border p-3">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-sm font-medium">{name}</p>
          <p className="text-xs text-muted-foreground">{status?.connected ? "Connected" : "Not connected"}</p>
        </div>

        {status?.connected ? (
          <Button
            type="button"
            onClick={onDisconnect}
            disabled={busy}
            className="ds-btn h-10 rounded-md px-3 text-xs disabled:cursor-not-allowed disabled:opacity-60"
          >
            Disconnect
          </Button>
        ) : (
          <Button
            type="button"
            onClick={onConnect}
            disabled={busy}
            className="ds-btn h-10 rounded-md px-3 text-xs disabled:cursor-not-allowed disabled:opacity-60"
          >
            Connect
          </Button>
        )}
      </div>

      {status?.integration?.workspace_name ? (
        <p className="mt-2 text-xs text-muted-foreground">Workspace: {status.integration.workspace_name}</p>
      ) : null}
      {status?.integration?.updated_at ? (
        <p className="mt-1 text-xs text-muted-foreground">Updated: {formatDate(status.integration.updated_at)}</p>
      ) : null}
      {error ? <p className="mt-2 text-xs text-destructive">{error}</p> : null}
    </article>
  );
}

export default function DashboardOAuthConnectionsPage() {
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();
  const scope = useMemo(() => resolveDashboardScope(searchParams), [searchParams]);

  const [notionStatus, setNotionStatus] = useState<OAuthStatus | null>(null);
  const [linearStatus, setLinearStatus] = useState<OAuthStatus | null>(null);

  const [notionError, setNotionError] = useState<string | null>(null);
  const [linearError, setLinearError] = useState<string | null>(null);

  const [statusLoading, setStatusLoading] = useState(true);
  const [notionBusy, setNotionBusy] = useState(false);
  const [linearBusy, setLinearBusy] = useState(false);
  const [policyLoading, setPolicyLoading] = useState(true);
  const [policyError, setPolicyError] = useState<string | null>(null);
  const [oauthPolicy, setOauthPolicy] = useState<OrganizationOAuthPolicyPayload["item"] | null>(null);
  const [canManagePolicy, setCanManagePolicy] = useState(false);
  const [activePolicyTab, setActivePolicyTab] = useState<"allowed" | "required" | "blocked">("allowed");
  const [allowedDraft, setAllowedDraft] = useState<string[]>([]);
  const [requiredDraft, setRequiredDraft] = useState<string[]>([]);
  const [blockedDraft, setBlockedDraft] = useState<string[]>([]);
  const [savingPolicy, setSavingPolicy] = useState(false);
  const [policySaveMessage, setPolicySaveMessage] = useState<string | null>(null);

  const handle401 = useCallback(() => {
    const next = encodeURIComponent(buildNextPath(pathname, window.location.search));
    router.replace(`/?next=${next}`);
  }, [pathname, router]);

  const fetchStatus = useCallback(async () => {
    if (scope.scope !== "user") {
      setStatusLoading(false);
      return;
    }
    setStatusLoading(true);
    const [notionRes, linearRes] = await Promise.all([
      dashboardApiGet<OAuthStatus>("/api/oauth/notion/status"),
      dashboardApiGet<OAuthStatus>("/api/oauth/linear/status"),
    ]);

    if (notionRes.status === 401 || linearRes.status === 401) {
      handle401();
      setStatusLoading(false);
      return;
    }

    if (notionRes.ok && notionRes.data) {
      setNotionStatus(notionRes.data);
      setNotionError(null);
    } else {
      setNotionError("Failed to load Notion status.");
    }

    if (linearRes.ok && linearRes.data) {
      setLinearStatus(linearRes.data);
      setLinearError(null);
    } else {
      setLinearError("Failed to load Linear status.");
    }
    setStatusLoading(false);
  }, [handle401, scope.scope]);

  const fetchOrgPolicy = useCallback(async () => {
    if (scope.scope === "user") {
      setPolicyLoading(false);
      return;
    }
    if (scope.organizationId === null) {
      setOauthPolicy(null);
      setPolicyError("Organization scope is required to view OAuth governance.");
      setPolicyLoading(false);
      return;
    }
    setPolicyLoading(true);
    setPolicyError(null);
    const [meRes, res] = await Promise.all([
      dashboardApiGet<PermissionSnapshot>("/api/me/permissions"),
      dashboardApiGet<OrganizationOAuthPolicyPayload>(`/api/organizations/${scope.organizationId}/oauth-policy`),
    ]);
    if (meRes.status === 401 || res.status === 401) {
      handle401();
      setPolicyLoading(false);
      return;
    }
    setCanManagePolicy(Boolean(meRes.data?.permissions?.can_manage_integrations));
    if (!res.ok || !res.data?.item) {
      setOauthPolicy(null);
      setPolicyError(res.error ?? "Failed to load OAuth governance policy.");
      setPolicyLoading(false);
      return;
    }
    setOauthPolicy(res.data.item);
    const policy = res.data.item.policy_json ?? {};
    const normalizeProviders = (items: string[] | undefined): string[] => {
      if (!Array.isArray(items)) {
        return [];
      }
      return Array.from(
        new Set(items.map((item) => String(item ?? "").trim().toLowerCase()).filter((item) => item.length > 0))
      ).sort();
    };
    setAllowedDraft(normalizeProviders(policy.allowed_providers));
    setRequiredDraft(normalizeProviders(policy.required_providers));
    setBlockedDraft(normalizeProviders(policy.blocked_providers));
    setPolicySaveMessage(null);
    setPolicyLoading(false);
  }, [handle401, scope.organizationId, scope.scope]);

  const toggleProvider = useCallback((target: "allowed" | "required" | "blocked", provider: string) => {
    const apply = (prev: string[]) => {
      if (prev.includes(provider)) {
        return prev.filter((item) => item !== provider);
      }
      return [...prev, provider].sort();
    };
    if (target === "allowed") {
      setAllowedDraft(apply);
    } else if (target === "required") {
      setRequiredDraft(apply);
    } else {
      setBlockedDraft(apply);
    }
    setPolicySaveMessage(null);
  }, []);

  const saveOrgPolicy = useCallback(async () => {
    if (scope.scope !== "org" || scope.organizationId === null || !canManagePolicy) {
      return;
    }
    setSavingPolicy(true);
    setPolicyError(null);
    setPolicySaveMessage(null);
    const currentPolicy = oauthPolicy?.policy_json ?? {};
    const response = await dashboardApiRequest<OrganizationOAuthPolicyPayload>(`/api/organizations/${scope.organizationId}/oauth-policy`, {
      method: "PATCH",
      body: {
        allowed_providers: allowedDraft,
        required_providers: requiredDraft,
        blocked_providers: blockedDraft,
        approval_workflow:
          currentPolicy && typeof currentPolicy.approval_workflow === "object"
            ? currentPolicy.approval_workflow
            : null,
      },
    });
    if (response.status === 401) {
      handle401();
      setSavingPolicy(false);
      return;
    }
    if (response.status === 403) {
      setPolicyError("Admin role required to update OAuth governance policy.");
      setSavingPolicy(false);
      return;
    }
    if (!response.ok || !response.data?.item) {
      setPolicyError(response.error ?? "Failed to update OAuth governance policy.");
      setSavingPolicy(false);
      return;
    }
    setOauthPolicy(response.data.item);
    setPolicySaveMessage("OAuth governance policy updated.");
    setSavingPolicy(false);
  }, [allowedDraft, blockedDraft, canManagePolicy, handle401, oauthPolicy?.policy_json, requiredDraft, scope.organizationId, scope.scope]);

  const handleConnect = useCallback(
    async (provider: "notion" | "linear") => {
      const setBusy = provider === "notion" ? setNotionBusy : setLinearBusy;
      const setErr = provider === "notion" ? setNotionError : setLinearError;
      setBusy(true);
      setErr(null);

      const res = await dashboardApiRequest<OAuthStartPayload>(`/api/oauth/${provider}/start`, {
        method: "POST",
      });
      if (res.status === 401) {
        handle401();
        setBusy(false);
        return;
      }
      if (!res.ok || !res.data?.auth_url) {
        setErr(`Failed to start ${provider} OAuth.`);
        setBusy(false);
        return;
      }

      window.location.href = res.data.auth_url;
    },
    [handle401]
  );

  const handleDisconnect = useCallback(
    async (provider: "notion" | "linear") => {
      const setBusy = provider === "notion" ? setNotionBusy : setLinearBusy;
      const setErr = provider === "notion" ? setNotionError : setLinearError;
      setBusy(true);
      setErr(null);

      const res = await dashboardApiRequest(`/api/oauth/${provider}/disconnect`, {
        method: "DELETE",
      });
      if (res.status === 401) {
        handle401();
        setBusy(false);
        return;
      }
      if (!res.ok) {
        setErr(`Failed to disconnect ${provider} OAuth.`);
        setBusy(false);
        return;
      }

      await fetchStatus();
      setBusy(false);
    },
    [fetchStatus, handle401]
  );

  useEffect(() => {
    if (scope.scope === "user") {
      setPolicyError(null);
      setOauthPolicy(null);
      void fetchStatus();
      return;
    }
    setNotionError(null);
    setLinearError(null);
    void fetchOrgPolicy();
  }, [fetchOrgPolicy, fetchStatus, scope.scope]);

  useEffect(() => {
    const handler = (event: Event) => {
      const custom = event as CustomEvent<{ path?: string }>;
      if (custom.detail?.path === pathname) {
        if (scope.scope === "user") {
          void fetchStatus();
        } else {
          void fetchOrgPolicy();
        }
      }
    };
    window.addEventListener("dashboard:v2:refresh", handler as EventListener);
    return () => {
      window.removeEventListener("dashboard:v2:refresh", handler as EventListener);
    };
  }, [fetchOrgPolicy, fetchStatus, pathname, scope.scope]);

  const providerCatalog = useMemo(() => {
    return Array.from(new Set(["notion", "linear", ...allowedDraft, ...requiredDraft, ...blockedDraft])).sort();
  }, [allowedDraft, blockedDraft, requiredDraft]);

  if (scope.scope !== "user") {
    return (
      <section className="space-y-4">
        <PageTitleWithTooltip
          title="OAuth Governance"
          tooltip="Manage organization OAuth provider governance policies."
        />
        <p className="text-sm text-muted-foreground">
          {scope.scope === "team" ? "Team scope is read-only and follows organization OAuth governance." : "Organization-level OAuth policy and guardrails."}
        </p>

        {policyError ? (
          <div className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
            {policyError}
          </div>
        ) : null}

        <div className="ds-card space-y-3 p-4">
          {policyLoading ? (
            <div className="flex min-h-[180px] items-center justify-center">
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            </div>
          ) : null}
          {!policyLoading ? (
            <>
              <p className="text-xs text-muted-foreground">
                Version: {oauthPolicy?.version ?? 1} | Updated: {formatDate(oauthPolicy?.updated_at ?? null)}
              </p>
              {scope.scope === "org" ? (
                <div className="space-y-3">
                  <p className="text-sm font-medium">Policy Editor</p>
                  <div className="flex flex-wrap items-center gap-2">
                    {[
                      { key: "allowed" as const, label: "Allowed Providers" },
                      { key: "required" as const, label: "Required Providers" },
                      { key: "blocked" as const, label: "Blocked Providers" },
                    ].map((tab) => (
                      <Button
                        key={tab.key}
                        type="button"
                        onClick={() => setActivePolicyTab(tab.key)}
                        className={`h-9 rounded-md px-3 text-xs ${
                          activePolicyTab === tab.key ? "bg-sidebar-accent text-sidebar-accent-foreground" : "ds-btn"
                        }`}
                        disabled={savingPolicy}
                      >
                        {tab.label}
                      </Button>
                    ))}
                  </div>

                  <div className="space-y-2 rounded-md border border-border p-3">
                    <p className="text-xs text-muted-foreground">
                      Toggle providers for <span className="font-medium text-foreground">{activePolicyTab}</span> policy.
                    </p>
                    <div className="grid gap-2 sm:grid-cols-2">
                      {providerCatalog.map((provider) => {
                        const checked =
                          activePolicyTab === "allowed"
                            ? allowedDraft.includes(provider)
                            : activePolicyTab === "required"
                              ? requiredDraft.includes(provider)
                              : blockedDraft.includes(provider);
                        return (
                          <label key={provider} className="flex items-center justify-between rounded-md border border-border px-3 py-2 text-sm">
                            <span>{provider}</span>
                            <Checkbox
                              checked={checked}
                              onCheckedChange={() => toggleProvider(activePolicyTab, provider)}
                              disabled={!canManagePolicy || savingPolicy}
                            />
                          </label>
                        );
                      })}
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <Button
                      type="button"
                      className="ds-btn h-10 rounded-md px-3 text-xs disabled:cursor-not-allowed disabled:opacity-60"
                      onClick={() => void saveOrgPolicy()}
                      disabled={!canManagePolicy || savingPolicy}
                    >
                      {savingPolicy ? "Saving..." : "Save Policy"}
                    </Button>
                    {!canManagePolicy ? (
                      <p className="text-xs text-muted-foreground">You do not have permission to modify this policy.</p>
                    ) : null}
                    {policySaveMessage ? <p className="text-xs text-emerald-500">{policySaveMessage}</p> : null}
                  </div>
                </div>
              ) : (
                <p className="text-xs text-muted-foreground">Team scope is read-only. Update policy in organization scope.</p>
              )}
            </>
          ) : null}
        </div>
      </section>
    );
  }

  return (
    <section className="space-y-4">
      <PageTitleWithTooltip
        title="OAuth Connections"
        tooltip="Connect or disconnect personal Notion and Linear accounts."
      />
      <p className="text-sm text-muted-foreground">Connect Notion and Linear to expose MCP tools.</p>

      <div className="ds-card space-y-3 p-4">
        {statusLoading ? (
          <div className="flex min-h-[180px] items-center justify-center">
            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
          </div>
        ) : (
          <>
            <ServiceRow
              name="Notion"
              status={notionStatus}
              error={notionError}
              busy={notionBusy}
              onConnect={() => void handleConnect("notion")}
              onDisconnect={() => void handleDisconnect("notion")}
            />
            <ServiceRow
              name="Linear"
              status={linearStatus}
              error={linearError}
              busy={linearBusy}
              onConnect={() => void handleConnect("linear")}
              onDisconnect={() => void handleDisconnect("linear")}
            />
          </>
        )}
      </div>
    </section>
  );
}
