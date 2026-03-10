"use client";

import Image from "next/image";
import { Button } from "@/components/ui/button";
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

function formatProviderLabel(provider: string): string {
  const value = String(provider ?? "").trim().toLowerCase();
  if (!value) {
    return "-";
  }
  return value.charAt(0).toUpperCase() + value.slice(1);
}

function providerLogoSrc(provider: string): string | null {
  const value = String(provider ?? "").trim().toLowerCase();
  if (value === "linear") {
    return "/logos/linear.svg";
  }
  if (value === "notion") {
    return "/logos/notion.svg";
  }
  if (value === "github") {
    return "/logos/github.svg";
  }
  return null;
}

type OAuthProvider = "notion" | "linear" | "github";

function normalizeProviders(items: string[]): string[] {
  return Array.from(new Set(items.map((item) => String(item ?? "").trim().toLowerCase()).filter((item) => item.length > 0))).sort();
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
  const [githubStatus, setGithubStatus] = useState<OAuthStatus | null>(null);

  const [notionError, setNotionError] = useState<string | null>(null);
  const [linearError, setLinearError] = useState<string | null>(null);
  const [githubError, setGithubError] = useState<string | null>(null);

  const [statusLoading, setStatusLoading] = useState(true);
  const [notionBusy, setNotionBusy] = useState(false);
  const [linearBusy, setLinearBusy] = useState(false);
  const [githubBusy, setGithubBusy] = useState(false);
  const [policyLoading, setPolicyLoading] = useState(true);
  const [policyError, setPolicyError] = useState<string | null>(null);
  const [oauthPolicy, setOauthPolicy] = useState<OrganizationOAuthPolicyPayload["item"] | null>(null);
  const [canManagePolicy, setCanManagePolicy] = useState(false);
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
    const [notionRes, linearRes, githubRes] = await Promise.all([
      dashboardApiGet<OAuthStatus>("/api/oauth/notion/status"),
      dashboardApiGet<OAuthStatus>("/api/oauth/linear/status"),
      dashboardApiGet<OAuthStatus>("/api/oauth/github/status"),
    ]);

    if (notionRes.status === 401 || linearRes.status === 401 || githubRes.status === 401) {
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

    if (githubRes.ok && githubRes.data) {
      setGithubStatus(githubRes.data);
      setGithubError(null);
    } else {
      setGithubError("Failed to load GitHub status.");
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
    setAllowedDraft(normalizeProviders(Array.isArray(policy.allowed_providers) ? policy.allowed_providers : []));
    setRequiredDraft(normalizeProviders(Array.isArray(policy.required_providers) ? policy.required_providers : []));
    setBlockedDraft(normalizeProviders(Array.isArray(policy.blocked_providers) ? policy.blocked_providers : []));
    setPolicySaveMessage(null);
    setPolicyLoading(false);
  }, [handle401, scope.organizationId, scope.scope]);

  const setProviderPolicyState = useCallback((provider: string, nextState: "allowed" | "required" | "blocked" | "off") => {
    const normalized = String(provider ?? "").trim().toLowerCase();
    if (!normalized) {
      return;
    }
    const nextAllowed = new Set(allowedDraft);
    const nextRequired = new Set(requiredDraft);
    const nextBlocked = new Set(blockedDraft);

    nextAllowed.delete(normalized);
    nextRequired.delete(normalized);
    nextBlocked.delete(normalized);

    if (nextState === "allowed") {
      nextAllowed.add(normalized);
    } else if (nextState === "required") {
      nextAllowed.add(normalized);
      nextRequired.add(normalized);
    } else if (nextState === "blocked") {
      nextBlocked.add(normalized);
    }

    setAllowedDraft(normalizeProviders(Array.from(nextAllowed)));
    setRequiredDraft(normalizeProviders(Array.from(nextRequired)));
    setBlockedDraft(normalizeProviders(Array.from(nextBlocked)));
    setPolicySaveMessage(null);
  }, [allowedDraft, blockedDraft, requiredDraft]);

  const saveOrgPolicy = useCallback(async () => {
    if (scope.scope !== "org" || scope.organizationId === null || !canManagePolicy) {
      return;
    }
    setSavingPolicy(true);
    setPolicyError(null);
    setPolicySaveMessage(null);

    const normalizedAllowed = normalizeProviders(allowedDraft);
    const normalizedRequired = normalizeProviders(requiredDraft);
    const normalizedBlocked = normalizeProviders(blockedDraft);
    const allowedSet = new Set(normalizedAllowed);
    const requiredSet = new Set(normalizedRequired);
    const blockedSet = new Set(normalizedBlocked);

    const requiredOutsideAllowed = normalizedRequired.filter((provider) => !allowedSet.has(provider));
    if (requiredOutsideAllowed.length > 0) {
      setPolicyError("Invalid policy: required providers must be included in allowed providers.");
      setSavingPolicy(false);
      return;
    }
    const blockedAndRequired = normalizedBlocked.filter((provider) => requiredSet.has(provider));
    if (blockedAndRequired.length > 0 || [...requiredSet].some((provider) => blockedSet.has(provider))) {
      setPolicyError("Invalid policy: blocked providers cannot overlap with required providers.");
      setSavingPolicy(false);
      return;
    }

    const currentPolicy = oauthPolicy?.policy_json ?? {};
    const response = await dashboardApiRequest<OrganizationOAuthPolicyPayload>(`/api/organizations/${scope.organizationId}/oauth-policy`, {
      method: "PATCH",
      body: {
        allowed_providers: normalizedAllowed,
        required_providers: normalizedRequired,
        blocked_providers: normalizedBlocked,
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
      const rawError = response.error ?? "Failed to update OAuth governance policy.";
      if (rawError.includes("invalid_oauth_policy:required_not_subset_of_allowed")) {
        setPolicyError("Invalid policy: required providers must be included in allowed providers.");
      } else if (rawError.includes("invalid_oauth_policy:blocked_conflicts_required")) {
        setPolicyError("Invalid policy: blocked providers cannot overlap with required providers.");
      } else {
        setPolicyError(rawError);
      }
      setSavingPolicy(false);
      return;
    }
    setOauthPolicy(response.data.item);
    setPolicySaveMessage("OAuth governance policy updated.");
    setSavingPolicy(false);
  }, [allowedDraft, blockedDraft, canManagePolicy, handle401, oauthPolicy?.policy_json, requiredDraft, scope.organizationId, scope.scope]);

  const handleConnect = useCallback(
    async (provider: OAuthProvider) => {
      const setBusy = provider === "notion" ? setNotionBusy : provider === "linear" ? setLinearBusy : setGithubBusy;
      const setErr = provider === "notion" ? setNotionError : provider === "linear" ? setLinearError : setGithubError;
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
    async (provider: OAuthProvider) => {
      const setBusy = provider === "notion" ? setNotionBusy : provider === "linear" ? setLinearBusy : setGithubBusy;
      const setErr = provider === "notion" ? setNotionError : provider === "linear" ? setLinearError : setGithubError;
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
    setGithubError(null);
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
    return Array.from(new Set(["notion", "linear", "github", ...allowedDraft, ...requiredDraft, ...blockedDraft])).sort();
  }, [allowedDraft, blockedDraft, requiredDraft]);

  const providerStateSummary = useMemo(() => {
    return {
      allowed: allowedDraft.length,
      required: requiredDraft.length,
      blocked: blockedDraft.length,
    };
  }, [allowedDraft.length, blockedDraft.length, requiredDraft.length]);

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
                  <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                    <span className="rounded-full border border-border px-2 py-1">Allowed {providerStateSummary.allowed}</span>
                    <span className="rounded-full border border-border px-2 py-1">Required {providerStateSummary.required}</span>
                    <span className="rounded-full border border-border px-2 py-1">Blocked {providerStateSummary.blocked}</span>
                  </div>

                  <div className="space-y-2 rounded-md border border-border p-3">
                    <p className="text-xs text-muted-foreground">
                      Set each provider policy directly. Required providers are auto-included in Allowed.
                    </p>
                    <div className="grid gap-2 sm:grid-cols-2">
                      {providerCatalog.map((provider) => {
                        const currentState = requiredDraft.includes(provider)
                          ? "required"
                          : blockedDraft.includes(provider)
                            ? "blocked"
                            : allowedDraft.includes(provider)
                              ? "allowed"
                              : "off";
                        const logoSrc = providerLogoSrc(provider);
                        return (
                          <article key={provider} className="space-y-2 rounded-md border border-border px-3 py-2 text-sm">
                            <div className="flex items-center justify-between gap-2">
                              <span className="flex items-center gap-2">
                                {logoSrc ? (
                                  <Image src={logoSrc} alt={`${formatProviderLabel(provider)} logo`} width={16} height={16} className="h-4 w-4 shrink-0" />
                                ) : (
                                  <span className="inline-flex h-4 w-4 shrink-0 items-center justify-center rounded-sm border border-border text-[10px]">
                                    {formatProviderLabel(provider).slice(0, 1)}
                                  </span>
                                )}
                                <span>{formatProviderLabel(provider)}</span>
                              </span>
                              <span className="rounded-full border border-border px-2 py-0.5 text-[10px] text-muted-foreground">
                                {currentState}
                              </span>
                            </div>
                            <div className="grid grid-cols-4 gap-1">
                              {[
                                { key: "allowed" as const, label: "Allow" },
                                { key: "required" as const, label: "Require" },
                                { key: "blocked" as const, label: "Block" },
                                { key: "off" as const, label: "Off" },
                              ].map((option) => (
                                <button
                                  key={`${provider}-${option.key}`}
                                  type="button"
                                  onClick={() => setProviderPolicyState(provider, option.key)}
                                  disabled={!canManagePolicy || savingPolicy}
                                  className={`h-8 rounded-md border px-2 text-[11px] ${
                                    currentState === option.key
                                      ? "border-primary bg-primary/10 text-primary"
                                      : "border-border text-muted-foreground hover:bg-accent"
                                  } disabled:cursor-not-allowed disabled:opacity-50`}
                                >
                                  {option.label}
                                </button>
                              ))}
                            </div>
                          </article>
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
        tooltip="Connect or disconnect personal Notion, Linear, and GitHub accounts."
      />
      <p className="text-sm text-muted-foreground">Connect Notion, Linear, and GitHub to expose MCP tools.</p>

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
            <ServiceRow
              name="GitHub"
              status={githubStatus}
              error={githubError}
              busy={githubBusy}
              onConnect={() => void handleConnect("github")}
              onDisconnect={() => void handleDisconnect("github")}
            />
          </>
        )}
      </div>
    </section>
  );
}
