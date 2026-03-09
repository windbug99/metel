"use client";

import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { DateRangePicker } from "@/components/ui/date-range-picker";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useCallback, useEffect, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { ChevronDown, Loader2 } from "lucide-react";

import { buildNextPath, dashboardApiGet, dashboardApiRequest } from "../../../../../lib/dashboard-v2-client";
import AlertBanner from "../../../../../components/dashboard-v2/alert-banner";
import PageTitleWithTooltip from "@/components/dashboard-v2/page-title-with-tooltip";

type PermissionSnapshot = {
  user_id?: string;
  role: string;
  org_ids?: number[];
  permissions?: {
    can_read_admin_ops?: boolean;
    can_manage_incident_banner?: boolean;
  };
};

type ConnectorDiagnosticItem = {
  provider: string;
  workspace_id: string | null;
  workspace_name: string | null;
  granted_scopes: string[];
  updated_at: string | null;
  status: string;
};

type RateLimitEventItem = {
  id: number;
  request_id: string | null;
  api_key_id: number | null;
  tool_name: string;
  error_code: string | null;
  created_at: string;
};

type SystemHealthPayload = {
  status: string;
  time_utc: string;
  services: {
    database: {
      ok: boolean;
      error: string | null;
    };
  };
};

type ExternalHealthItem = {
  connector: string;
  calls: number;
  failures: number;
  fail_rate: number;
  upstream_temporary: number;
  avg_latency_ms: number;
  last_error_at: string | null;
  status: string;
  top_errors: Array<{ error_code: string; count: number }>;
};

type IncidentBanner = {
  enabled: boolean;
  message: string | null;
  severity: "info" | "warning" | "critical";
  starts_at: string | null;
  ends_at: string | null;
  updated_at: string | null;
};

type IncidentBannerRevisionItem = {
  id: number;
  user_id: string;
  enabled: boolean;
  message: string | null;
  severity: "info" | "warning" | "critical";
  starts_at: string | null;
  ends_at: string | null;
  status: string;
  requested_by: string;
  approved_by: string | null;
  approved_at: string | null;
  created_at: string;
  updated_at: string;
};

function asDate(value?: string | null): string {
  if (!value) {
    return "-";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString();
}

function toStartOfDayISO(value: string): string | null {
  if (!value) {
    return null;
  }
  return new Date(`${value}T00:00:00`).toISOString();
}

function toEndOfDayISO(value: string): string | null {
  if (!value) {
    return null;
  }
  return new Date(`${value}T23:59:59.999`).toISOString();
}

export default function DashboardAdminOpsPage() {
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();

  const [userId, setUserId] = useState<string | null>(null);
  const [role, setRole] = useState<string | null>(null);
  const [canReadAdminOps, setCanReadAdminOps] = useState(false);
  const [canManageIncidentBanner, setCanManageIncidentBanner] = useState(false);
  const [activeOrgId, setActiveOrgId] = useState<number | null>(null);

  const [systemHealth, setSystemHealth] = useState<SystemHealthPayload | null>(null);
  const [connectorDiagnostics, setConnectorDiagnostics] = useState<ConnectorDiagnosticItem[]>([]);
  const [externalHealth, setExternalHealth] = useState<ExternalHealthItem[]>([]);
  const [rateLimitEvents, setRateLimitEvents] = useState<RateLimitEventItem[]>([]);

  const [incidentBanner, setIncidentBanner] = useState<IncidentBanner | null>(null);
  const [incidentRevisions, setIncidentRevisions] = useState<IncidentBannerRevisionItem[]>([]);

  const [incidentEnabledDraft, setIncidentEnabledDraft] = useState(false);
  const [incidentSeverityDraft, setIncidentSeverityDraft] = useState<"info" | "warning" | "critical">("info");
  const [incidentMessageDraft, setIncidentMessageDraft] = useState("");
  const [incidentStartsAtDraft, setIncidentStartsAtDraft] = useState("");
  const [incidentEndsAtDraft, setIncidentEndsAtDraft] = useState("");

  const [loading, setLoading] = useState(true);
  const [incidentSaving, setIncidentSaving] = useState(false);
  const [incidentRevisionSaving, setIncidentRevisionSaving] = useState(false);
  const [incidentRevisionReviewLoadingId, setIncidentRevisionReviewLoadingId] = useState<number | null>(null);

  const [error, setError] = useState<string | null>(null);

  const handle401 = useCallback(() => {
    const next = encodeURIComponent(buildNextPath(pathname, window.location.search));
    router.replace(`/?next=${next}`);
  }, [pathname, router]);

  const fetchAdminOps = useCallback(async () => {
    setLoading(true);
    setError(null);

    const permissionsRes = await dashboardApiGet<PermissionSnapshot>("/api/me/permissions");
    if (permissionsRes.status === 401) {
      handle401();
      setLoading(false);
      return;
    }
    if (!permissionsRes.ok || !permissionsRes.data) {
      setError("Failed to load permission snapshot.");
      setLoading(false);
      return;
    }

    const canRead = Boolean(permissionsRes.data.permissions?.can_read_admin_ops);
    const queryOrgRaw = (searchParams.get("org") ?? "").trim();
    const queryOrg = queryOrgRaw && queryOrgRaw !== "all" ? Number(queryOrgRaw) : null;
    const orgFromQuery = typeof queryOrg === "number" && Number.isFinite(queryOrg) ? queryOrg : null;
    const orgList = Array.isArray(permissionsRes.data.org_ids) ? permissionsRes.data.org_ids : [];
    const fallbackOrg = orgList.length > 0 ? Number(orgList[0]) : null;
    const resolvedOrgId = orgFromQuery ?? fallbackOrg;

    setUserId(permissionsRes.data.user_id ?? null);
    setRole(permissionsRes.data.role ?? null);
    setCanReadAdminOps(canRead);
    setCanManageIncidentBanner(Boolean(permissionsRes.data.permissions?.can_manage_incident_banner));
    setActiveOrgId(resolvedOrgId);

    if (!canRead) {
      setLoading(false);
      return;
    }

    const incidentBannerPath = `/api/admin/incident-banner${resolvedOrgId !== null ? `?organization_id=${resolvedOrgId}` : ""}`;
    const incidentRevisionPath = `/api/admin/incident-banner/revisions?limit=20${resolvedOrgId !== null ? `&organization_id=${resolvedOrgId}` : ""}`;

    const [
      diagnosticsRes,
      rateLimitRes,
      healthRes,
      externalHealthRes,
      incidentRes,
      incidentRevisionsRes,
    ] = await Promise.all([
      dashboardApiGet<{ items?: ConnectorDiagnosticItem[] }>("/api/admin/connectors/diagnostics"),
      dashboardApiGet<{ items?: RateLimitEventItem[] }>("/api/admin/rate-limit-events?days=7&limit=20"),
      dashboardApiGet<SystemHealthPayload>("/api/admin/system-health"),
      dashboardApiGet<{ items?: ExternalHealthItem[] }>("/api/admin/external-health?days=1"),
      dashboardApiGet<IncidentBanner>(incidentBannerPath),
      dashboardApiGet<{ items?: IncidentBannerRevisionItem[] }>(incidentRevisionPath),
    ]);

    if (
      diagnosticsRes.status === 401 ||
      rateLimitRes.status === 401 ||
      healthRes.status === 401 ||
      externalHealthRes.status === 401 ||
      incidentRes.status === 401 ||
      incidentRevisionsRes.status === 401
    ) {
      handle401();
      setLoading(false);
      return;
    }

    if (
      !diagnosticsRes.ok ||
      !rateLimitRes.ok ||
      !healthRes.ok ||
      !externalHealthRes.ok ||
      !incidentRes.ok ||
      !incidentRevisionsRes.ok ||
      !diagnosticsRes.data ||
      !rateLimitRes.data ||
      !healthRes.data ||
      !externalHealthRes.data ||
      !incidentRes.data ||
      !incidentRevisionsRes.data
    ) {
      setError("Failed to load admin diagnostics.");
      setLoading(false);
      return;
    }

    setConnectorDiagnostics(Array.isArray(diagnosticsRes.data.items) ? diagnosticsRes.data.items : []);
    setRateLimitEvents(Array.isArray(rateLimitRes.data.items) ? rateLimitRes.data.items : []);
    setSystemHealth(healthRes.data);
    setExternalHealth(Array.isArray(externalHealthRes.data.items) ? externalHealthRes.data.items : []);

    setIncidentBanner(incidentRes.data);
    setIncidentRevisions(Array.isArray(incidentRevisionsRes.data.items) ? incidentRevisionsRes.data.items : []);
    setIncidentEnabledDraft(Boolean(incidentRes.data.enabled));
    setIncidentSeverityDraft((incidentRes.data.severity ?? "info") as "info" | "warning" | "critical");
    setIncidentMessageDraft(incidentRes.data.message ?? "");
    setIncidentStartsAtDraft(incidentRes.data.starts_at ? incidentRes.data.starts_at.slice(0, 10) : "");
    setIncidentEndsAtDraft(incidentRes.data.ends_at ? incidentRes.data.ends_at.slice(0, 10) : "");

    setLoading(false);
  }, [handle401, searchParams]);

  const handleSaveIncidentBanner = useCallback(async () => {
    setIncidentSaving(true);
    setError(null);

    const response = await dashboardApiRequest(`/api/admin/incident-banner${activeOrgId !== null ? `?organization_id=${activeOrgId}` : ""}`, {
      method: "PATCH",
      body: {
        enabled: incidentEnabledDraft,
        severity: incidentSeverityDraft,
        message: incidentMessageDraft.trim() || null,
        starts_at: toStartOfDayISO(incidentStartsAtDraft),
        ends_at: toEndOfDayISO(incidentEndsAtDraft),
      },
    });

    if (response.status === 401) {
      handle401();
      setIncidentSaving(false);
      return;
    }
    if (response.status === 403) {
      setError("Owner role required to save incident banner.");
      setIncidentSaving(false);
      return;
    }
    if (!response.ok) {
      setError(response.error ?? "Failed to save incident banner.");
      setIncidentSaving(false);
      return;
    }

    await fetchAdminOps();
    setIncidentSaving(false);
  }, [activeOrgId, fetchAdminOps, handle401, incidentEnabledDraft, incidentEndsAtDraft, incidentMessageDraft, incidentSeverityDraft, incidentStartsAtDraft]);

  const handleCreateIncidentBannerRevision = useCallback(async () => {
    setIncidentRevisionSaving(true);
    setError(null);

    const response = await dashboardApiRequest(`/api/admin/incident-banner/revisions${activeOrgId !== null ? `?organization_id=${activeOrgId}` : ""}`, {
      method: "POST",
      body: {
        enabled: incidentEnabledDraft,
        severity: incidentSeverityDraft,
        message: incidentMessageDraft.trim() || null,
        starts_at: toStartOfDayISO(incidentStartsAtDraft),
        ends_at: toEndOfDayISO(incidentEndsAtDraft),
      },
    });

    if (response.status === 401) {
      handle401();
      setIncidentRevisionSaving(false);
      return;
    }
    if (response.status === 403) {
      setError("Owner role required to request incident banner revision.");
      setIncidentRevisionSaving(false);
      return;
    }
    if (!response.ok) {
      setError(response.error ?? "Failed to create incident banner revision.");
      setIncidentRevisionSaving(false);
      return;
    }

    await fetchAdminOps();
    setIncidentRevisionSaving(false);
  }, [activeOrgId, fetchAdminOps, handle401, incidentEnabledDraft, incidentEndsAtDraft, incidentMessageDraft, incidentSeverityDraft, incidentStartsAtDraft]);

  const handleReviewIncidentBannerRevision = useCallback(
    async (revisionId: number, decision: "approve" | "reject") => {
      setIncidentRevisionReviewLoadingId(revisionId);
      setError(null);

      const response = await dashboardApiRequest(`/api/admin/incident-banner/revisions/${revisionId}/review${activeOrgId !== null ? `?organization_id=${activeOrgId}` : ""}`, {
        method: "POST",
        body: { decision },
      });

      if (response.status === 401) {
        handle401();
        setIncidentRevisionReviewLoadingId(null);
        return;
      }
      if (response.status === 403) {
        setError("Owner role required to review incident banner revision.");
        setIncidentRevisionReviewLoadingId(null);
        return;
      }
      if (!response.ok) {
        setError(response.error ?? "Failed to review incident banner revision.");
        setIncidentRevisionReviewLoadingId(null);
        return;
      }

      await fetchAdminOps();
      setIncidentRevisionReviewLoadingId(null);
    },
    [activeOrgId, fetchAdminOps, handle401]
  );

  useEffect(() => {
    void fetchAdminOps();
  }, [fetchAdminOps]);

  useEffect(() => {
    const handler = (event: Event) => {
      const custom = event as CustomEvent<{ path?: string }>;
      if (custom.detail?.path === pathname) {
        void fetchAdminOps();
      }
    };
    window.addEventListener("dashboard:v2:refresh", handler as EventListener);
    return () => {
      window.removeEventListener("dashboard:v2:refresh", handler as EventListener);
    };
  }, [fetchAdminOps, pathname]);

  if (loading) {
    return (
      <section className="space-y-5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <PageTitleWithTooltip
              title="Admin / Ops"
              tooltip="Monitor system health, incidents, diagnostics, and operational events."
            />
            <p className="text-sm text-muted-foreground">Connector diagnostics, rate-limit events, system health, and incident workflow.</p>
          </div>
          <Button
            type="button"
            disabled
            className="ds-btn h-11 rounded-md px-3 text-sm disabled:cursor-not-allowed disabled:opacity-60 md:h-9"
          >
            Loading...
          </Button>
        </div>
        <div className="ds-card flex min-h-[220px] items-center justify-center p-4">
          <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
        </div>
      </section>
    );
  }

  return (
    <section className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <PageTitleWithTooltip
            title="Admin / Ops"
            tooltip="Monitor system health, incidents, diagnostics, and operational events."
          />
          <p className="text-sm text-muted-foreground">Connector diagnostics, rate-limit events, system health, and incident workflow.</p>
        </div>
        <Button
          type="button"
          onClick={() => void fetchAdminOps()}
          disabled={loading}
          className="ds-btn h-11 rounded-md px-3 text-sm disabled:cursor-not-allowed disabled:opacity-60 md:h-9"
        >
          {loading ? "Loading..." : "Refresh"}
        </Button>
      </div>

      {error ? <AlertBanner message={error} tone="danger" /> : null}

      <div className="ds-card p-4 text-sm text-muted-foreground">role: {role ?? "unknown"}</div>

      {!loading && !canReadAdminOps ? (
        <div className="ds-card p-4">
          <p className="text-sm text-muted-foreground">Your role does not have permission to access Admin / Ops modules.</p>
        </div>
      ) : null}

      {canReadAdminOps ? (
        <>
          <div className="grid gap-2">
            <article className="ds-card p-4">
              <p className="text-xs font-medium text-muted-foreground">System Health</p>
              <p className="mt-1 text-sm font-semibold text-[var(--text-primary)]">{systemHealth?.status ?? "unknown"}</p>
              <p className="mt-1 text-xs text-muted-foreground">
                DB: {systemHealth?.services?.database?.ok ? "ok" : "degraded"}
                {systemHealth?.services?.database?.error ? ` (${systemHealth.services.database.error})` : ""}
              </p>
              <p className="mt-1 text-xs text-muted-foreground">time_utc: {asDate(systemHealth?.time_utc)}</p>
            </article>

            <article className="ds-card p-4">
              <p className="text-xs font-medium text-muted-foreground">Incident Banner</p>
              <div className="mt-2 flex flex-wrap items-center gap-2">
                <label className="inline-flex items-center gap-1 text-xs text-muted-foreground">
                  <Switch
                    checked={incidentEnabledDraft}
                    onCheckedChange={setIncidentEnabledDraft}
                    disabled={!canManageIncidentBanner}
                  />
                  Show banner
                </label>
              </div>

              <div className="mt-2 flex flex-wrap items-center gap-2">
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button
                      type="button"
                      variant="outline"
                      disabled={!canManageIncidentBanner}
                      className="h-11 min-w-[120px] justify-between rounded-md px-3 text-sm md:h-9"
                    >
                      {incidentSeverityDraft}
                      <ChevronDown className="h-4 w-4 text-muted-foreground" />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="start" className="w-[140px]">
                    <DropdownMenuRadioGroup
                      value={incidentSeverityDraft}
                      onValueChange={(value) => setIncidentSeverityDraft(value as "info" | "warning" | "critical")}
                    >
                      <DropdownMenuRadioItem value="info">info</DropdownMenuRadioItem>
                      <DropdownMenuRadioItem value="warning">warning</DropdownMenuRadioItem>
                      <DropdownMenuRadioItem value="critical">critical</DropdownMenuRadioItem>
                    </DropdownMenuRadioGroup>
                  </DropdownMenuContent>
                </DropdownMenu>
                <Input
                  value={incidentMessageDraft}
                  onChange={(event) => setIncidentMessageDraft(event.target.value)}
                  disabled={!canManageIncidentBanner}
                  placeholder="Incident title"
                  className="ds-input h-11 min-w-[260px] flex-1 rounded-md px-3 text-sm md:h-9"
                />
                <div className={!canManageIncidentBanner ? "pointer-events-none opacity-60" : undefined}>
                  <DateRangePicker
                    from={incidentStartsAtDraft}
                    to={incidentEndsAtDraft}
                    onChange={(next) => {
                      setIncidentStartsAtDraft(next.from);
                      setIncidentEndsAtDraft(next.to);
                    }}
                    className="min-w-[280px]"
                  />
                </div>
                <Button
                  type="button"
                  onClick={() => void handleSaveIncidentBanner()}
                  disabled={incidentSaving || !canManageIncidentBanner}
                  className="ds-btn h-11 rounded-md px-3 text-sm disabled:cursor-not-allowed disabled:opacity-60 md:h-9"
                >
                  {incidentSaving ? "Saving..." : "Save Banner"}
                </Button>
                <Button
                  type="button"
                  onClick={() => void handleCreateIncidentBannerRevision()}
                  disabled={incidentRevisionSaving || !canManageIncidentBanner}
                  className="ds-btn h-11 rounded-md px-3 text-sm disabled:cursor-not-allowed disabled:opacity-60 md:h-9"
                >
                  {incidentRevisionSaving ? "Requesting..." : "Request Revision"}
                </Button>
              </div>

              {!canManageIncidentBanner ? (
                <p className="mt-1 text-xs text-muted-foreground">Incident banner update/review is owner-only.</p>
              ) : null}
              <p className="mt-1 text-xs text-muted-foreground">updated: {asDate(incidentBanner?.updated_at)}</p>

              <div className="mt-2 rounded-md border border-border bg-card p-2">
                <p className="text-xs font-medium text-muted-foreground">Revision History</p>
                {incidentRevisions.length === 0 ? (
                  <p className="mt-1 text-xs text-muted-foreground">No revisions yet.</p>
                ) : (
                  <div className="mt-1 space-y-1">
                    {incidentRevisions.slice(0, 6).map((rev) => (
                      <div key={`incident-revision-${rev.id}`} className="flex flex-wrap items-center justify-between gap-2">
                        <p className="text-xs text-muted-foreground">
                          #{rev.id} · {rev.severity} · {rev.status} · {asDate(rev.created_at)}
                        </p>

                        {rev.status === "pending" && rev.requested_by !== userId && canManageIncidentBanner ? (
                          <div className="flex items-center gap-1">
                            <Button
                              type="button"
                              onClick={() => void handleReviewIncidentBannerRevision(rev.id, "approve")}
                              disabled={incidentRevisionReviewLoadingId === rev.id}
                              className="h-11 rounded-md border border-chart-2/40 px-3 text-xs font-medium text-chart-2 disabled:opacity-60 md:h-9"
                            >
                              Approve
                            </Button>
                            <Button
                              type="button"
                              onClick={() => void handleReviewIncidentBannerRevision(rev.id, "reject")}
                              disabled={incidentRevisionReviewLoadingId === rev.id}
                              className="h-11 rounded-md border border-destructive/40 px-3 text-xs font-medium text-destructive disabled:opacity-60 md:h-9"
                            >
                              Reject
                            </Button>
                          </div>
                        ) : rev.status === "pending" && rev.requested_by === userId ? (
                          <p className="text-xs text-muted-foreground">Self-review blocked</p>
                        ) : rev.status === "pending" ? (
                          <p className="text-xs text-muted-foreground">Review is owner-only.</p>
                        ) : null}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </article>
          </div>

          <div className="grid gap-2 sm:grid-cols-3">
            <article className="ds-card p-4">
              <p className="text-xs font-medium text-muted-foreground">Connector Diagnostics</p>
              <div className="mt-2 space-y-1">
                {connectorDiagnostics.length === 0 ? (
                  <p className="text-xs text-muted-foreground">No diagnostics.</p>
                ) : (
                  connectorDiagnostics.slice(0, 8).map((item, idx) => (
                    <p key={`${item.provider}-${idx}`} className="text-xs text-muted-foreground">
                      {item.provider}: {item.workspace_name ?? item.workspace_id ?? "n/a"} ({item.status})
                    </p>
                  ))
                )}
              </div>
            </article>

            <article className="ds-card p-4">
              <p className="text-xs font-medium text-muted-foreground">External Connector Health (24h)</p>
              <div className="mt-2 space-y-1">
                {externalHealth.length === 0 ? (
                  <p className="text-xs text-muted-foreground">No health samples.</p>
                ) : (
                  externalHealth.slice(0, 8).map((item) => (
                    <p key={item.connector} className="text-xs text-muted-foreground">
                      {item.connector}: {item.status} · fail {(item.fail_rate * 100).toFixed(1)}% · calls {item.calls}
                    </p>
                  ))
                )}
              </div>
            </article>

            <article className="ds-card p-4">
              <p className="text-xs font-medium text-muted-foreground">Rate-limit / Quota Hits</p>
              <div className="mt-2 space-y-1">
                {rateLimitEvents.length === 0 ? (
                  <p className="text-xs text-muted-foreground">No events.</p>
                ) : (
                  rateLimitEvents.slice(0, 8).map((item) => (
                    <p key={item.id} className="text-xs text-muted-foreground">
                      {item.error_code ?? "unknown"}: {item.tool_name}
                    </p>
                  ))
                )}
              </div>
            </article>
          </div>
        </>
      ) : null}
    </section>
  );
}
