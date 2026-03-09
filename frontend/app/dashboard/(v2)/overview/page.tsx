"use client";

import { useCallback, useEffect, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Loader2 } from "lucide-react";

import { buildNextPath, dashboardApiGet } from "../../../../lib/dashboard-v2-client";
import { resolveDashboardScope } from "../../../../lib/dashboard-scope";
import PageTitleWithTooltip from "@/components/dashboard-v2/page-title-with-tooltip";

type OverviewPayload = {
  window_hours: number;
  kpis: {
    total_calls: number;
    success_rate: number;
    fail_rate: number;
    avg_latency_ms: number;
    p95_latency_ms: number;
    retry_rate?: number;
    policy_block_rate?: number;
  };
  top?: {
    called_tools?: Array<{ tool_name: string; count: number }>;
    failed_tools?: Array<{ tool_name: string; count: number }>;
    blocked_tools?: Array<{ tool_name: string; count: number }>;
  };
  anomalies?: Array<{
    type: string;
    severity: string;
    message: string;
    context?: Record<string, unknown>;
  }>;
};

export default function DashboardOverviewPage() {
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();
  const [data, setData] = useState<OverviewPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const scopeState = resolveDashboardScope(searchParams);
  const scopeLabel =
    scopeState.scope === "team"
      ? `Team Scope (org=${scopeState.organizationId ?? "-"}, team=${scopeState.teamId ?? "-"})`
      : scopeState.scope === "org"
      ? `Organization Scope (org=${scopeState.organizationId ?? "-"})`
      : "User Scope (me)";

  const fetchOverview = useCallback(async () => {
    setLoading(true);
    setError(null);

    const range = searchParams.get("range") === "7d" ? 168 : 24;
    const params = new URLSearchParams();
    params.set("hours", String(range));
    if (scopeState.organizationId !== null) {
      params.set("organization_id", String(scopeState.organizationId));
    }
    if (scopeState.teamId !== null) {
      params.set("team_id", String(scopeState.teamId));
    }

    const result = await dashboardApiGet<OverviewPayload>(`/api/tool-calls/overview?${params.toString()}`);
    if (result.status === 401) {
      const next = encodeURIComponent(buildNextPath(pathname, window.location.search));
      router.replace(`/?next=${next}`);
      setLoading(false);
      return;
    }
    if (result.status === 403) {
      setError("Access denied while loading overview.");
      setLoading(false);
      return;
    }
    if (!result.ok || !result.data) {
      setError(result.error ?? "Failed to load overview metrics.");
      setLoading(false);
      return;
    }

    setData(result.data);
    setLoading(false);
  }, [pathname, router, scopeState.organizationId, scopeState.teamId, searchParams]);

  useEffect(() => {
    void fetchOverview();
  }, [fetchOverview]);

  useEffect(() => {
    const handler = (event: Event) => {
      const custom = event as CustomEvent<{ path?: string }>;
      if (custom.detail?.path === pathname) {
        void fetchOverview();
      }
    };
    window.addEventListener("dashboard:v2:refresh", handler as EventListener);
    return () => {
      window.removeEventListener("dashboard:v2:refresh", handler as EventListener);
    };
  }, [fetchOverview, pathname]);

  if (loading) {
    return (
      <section className="space-y-4">
        <PageTitleWithTooltip title="Overview" tooltip="View scope-specific usage KPIs, top tools, and anomalies." />
        <p className="text-sm text-muted-foreground">{scopeLabel}</p>
        <div className="ds-card flex min-h-[220px] items-center justify-center p-4">
          <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
        </div>
      </section>
    );
  }

  return (
    <section className="space-y-4">
      <PageTitleWithTooltip title="Overview" tooltip="View scope-specific usage KPIs, top tools, and anomalies." />
      <p className="text-sm text-muted-foreground">{scopeLabel}</p>

      {error ? (
        <div className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error}
        </div>
      ) : null}

      {data ? (
        <div className="space-y-3">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <article className="ds-card p-4">
              <p className="text-xs text-muted-foreground">Total Calls</p>
              <p className="mt-2 text-2xl font-semibold">{data.kpis.total_calls}</p>
            </article>
            <article className="ds-card p-4">
              <p className="text-xs text-muted-foreground">Success Rate</p>
              <p className="mt-2 text-2xl font-semibold text-chart-2">{(data.kpis.success_rate * 100).toFixed(1)}%</p>
            </article>
            <article className="ds-card p-4">
              <p className="text-xs text-muted-foreground">Fail Rate</p>
              <p className="mt-2 text-2xl font-semibold text-destructive">{(data.kpis.fail_rate * 100).toFixed(1)}%</p>
            </article>
            <article className="ds-card p-4">
              <p className="text-xs text-muted-foreground">Avg Latency</p>
              <p className="mt-2 text-2xl font-semibold">{Math.round(data.kpis.avg_latency_ms)} ms</p>
            </article>
            <article className="ds-card p-4">
              <p className="text-xs text-muted-foreground">P95 Latency</p>
              <p className="mt-2 text-2xl font-semibold">{Math.round(data.kpis.p95_latency_ms)} ms</p>
            </article>
            <article className="ds-card p-4">
              <p className="text-xs text-muted-foreground">Retry / Policy Block</p>
              <p className="mt-2 text-lg font-semibold">
                {((data.kpis.retry_rate ?? 0) * 100).toFixed(1)}% / {((data.kpis.policy_block_rate ?? 0) * 100).toFixed(1)}%
              </p>
            </article>
          </div>

          <div className="grid gap-3 lg:grid-cols-3">
            <article className="ds-card p-4">
              <p className="text-sm font-semibold">Top Called Tools</p>
              <div className="mt-2 space-y-1">
                {(data.top?.called_tools ?? []).slice(0, 5).map((item) => (
                  <p key={`called-${item.tool_name}`} className="text-xs text-muted-foreground">
                    {item.tool_name}: {item.count}
                  </p>
                ))}
                {(data.top?.called_tools ?? []).length === 0 ? <p className="text-xs text-muted-foreground">No data.</p> : null}
              </div>
            </article>
            <article className="ds-card p-4">
              <p className="text-sm font-semibold">Top Failed Tools</p>
              <div className="mt-2 space-y-1">
                {(data.top?.failed_tools ?? []).slice(0, 5).map((item) => (
                  <p key={`failed-${item.tool_name}`} className="text-xs text-muted-foreground">
                    {item.tool_name}: {item.count}
                  </p>
                ))}
                {(data.top?.failed_tools ?? []).length === 0 ? <p className="text-xs text-muted-foreground">No data.</p> : null}
              </div>
            </article>
            <article className="ds-card p-4">
              <p className="text-sm font-semibold">Top Blocked Tools</p>
              <div className="mt-2 space-y-1">
                {(data.top?.blocked_tools ?? []).slice(0, 5).map((item) => (
                  <p key={`blocked-${item.tool_name}`} className="text-xs text-muted-foreground">
                    {item.tool_name}: {item.count}
                  </p>
                ))}
                {(data.top?.blocked_tools ?? []).length === 0 ? <p className="text-xs text-muted-foreground">No data.</p> : null}
              </div>
            </article>
          </div>

          {(data.anomalies ?? []).length > 0 ? (
            <div className="rounded-md border border-chart-4/40 bg-chart-4/10 p-3">
              <p className="text-xs font-medium text-chart-4">Recent anomalies</p>
              <div className="mt-2 space-y-1">
                {(data.anomalies ?? []).slice(0, 8).map((anomaly, idx) => (
                  <p key={`${anomaly.type}-${idx}`} className="text-xs text-muted-foreground">
                    [{anomaly.severity}] {anomaly.message}
                  </p>
                ))}
              </div>
            </div>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
