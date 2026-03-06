"use client";

import { Select } from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { useCallback, useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";

import { buildNextPath, dashboardApiGet } from "../../../../../lib/dashboard-v2-client";

type ToolCallItem = {
  id: number;
  tool_name: string;
  status: "success" | "fail";
  error_code: string | null;
  latency_ms: number;
  created_at: string;
  api_key?: {
    id: number | null;
    name: string | null;
    key_prefix: string | null;
  };
};

type ToolCallSummary = {
  calls_24h: number;
  success_24h: number;
  fail_24h: number;
  fail_rate_24h: number;
  blocked_rate_24h: number;
  retryable_fail_rate_24h: number;
  policy_blocked_24h: number;
  quota_exceeded_24h: number;
  access_denied_24h: number;
  resolve_fail_24h: number;
  upstream_temporary_24h: number;
  high_risk_allowed_24h: number;
  policy_override_usage_24h: number;
  top_failure_codes?: Array<{ error_code: string; count: number }>;
};

type ToolCallListPayload = {
  items?: ToolCallItem[];
  summary?: ToolCallSummary;
};

type TrendPoint = {
  bucket_start: string;
  calls: number;
  success_rate: number;
  fail_rate: number;
  blocked_rate: number;
  avg_latency_ms: number;
};

type TrendPayload = {
  items?: TrendPoint[];
};

type FailureBreakdownPayload = {
  total_failures: number;
  categories?: Array<{ category: string; count: number; ratio: number }>;
  error_codes?: Array<{ error_code: string; count: number }>;
};

type ConnectorSummary = {
  connector: string;
  calls: number;
  fail_rate: number;
  avg_latency_ms: number;
  top_error_codes?: Array<{ error_code: string; count: number }>;
};

type ConnectorPayload = {
  items?: ConnectorSummary[];
};

export default function DashboardMcpUsagePage() {
  const pathname = usePathname();
  const router = useRouter();

  const [toolCalls, setToolCalls] = useState<ToolCallItem[]>([]);
  const [toolCallsSummary, setToolCallsSummary] = useState<ToolCallSummary | null>(null);
  const [trendPoints, setTrendPoints] = useState<TrendPoint[]>([]);
  const [failureBreakdown, setFailureBreakdown] = useState<FailureBreakdownPayload | null>(null);
  const [connectorSummary, setConnectorSummary] = useState<ConnectorSummary[]>([]);

  const [toolCallsLoading, setToolCallsLoading] = useState(true);
  const [trendLoading, setTrendLoading] = useState(true);
  const [toolCallsError, setToolCallsError] = useState<string | null>(null);
  const [trendError, setTrendError] = useState<string | null>(null);

  const [statusFilter, setStatusFilter] = useState<"all" | "success" | "fail">("all");
  const [toolNameFilter, setToolNameFilter] = useState("");
  const [fromFilter, setFromFilter] = useState("");
  const [toFilter, setToFilter] = useState("");

  const handle401 = useCallback(() => {
    const next = encodeURIComponent(buildNextPath(pathname, window.location.search));
    router.replace(`/?next=${next}`);
  }, [pathname, router]);

  const fetchToolCalls = useCallback(async () => {
    setToolCallsLoading(true);
    setToolCallsError(null);

    const query = new URLSearchParams();
    query.set("limit", "20");
    query.set("status", statusFilter);
    if (toolNameFilter.trim()) {
      query.set("tool_name", toolNameFilter.trim());
    }
    if (fromFilter) {
      query.set("from", new Date(fromFilter).toISOString());
    }
    if (toFilter) {
      query.set("to", new Date(toFilter).toISOString());
    }

    const result = await dashboardApiGet<ToolCallListPayload>(`/api/tool-calls?${query.toString()}`);
    if (result.status === 401) {
      handle401();
      setToolCallsLoading(false);
      return;
    }
    if (result.status === 403) {
      setToolCallsError("Access denied while loading usage.");
      setToolCallsLoading(false);
      return;
    }
    if (!result.ok || !result.data) {
      setToolCallsError(result.error ?? "Failed to load usage.");
      setToolCallsLoading(false);
      return;
    }

    setToolCalls(Array.isArray(result.data.items) ? result.data.items : []);
    setToolCallsSummary(result.data.summary ?? null);
    setToolCallsLoading(false);
  }, [fromFilter, handle401, statusFilter, toFilter, toolNameFilter]);

  const fetchTrendAndBreakdown = useCallback(async () => {
    setTrendLoading(true);
    setTrendError(null);

    const [trendsRes, breakdownRes, connectorsRes] = await Promise.all([
      dashboardApiGet<TrendPayload>("/api/tool-calls/trends?days=7&bucket=day"),
      dashboardApiGet<FailureBreakdownPayload>("/api/tool-calls/failure-breakdown?days=7"),
      dashboardApiGet<ConnectorPayload>("/api/tool-calls/connectors?days=7"),
    ]);

    if (trendsRes.status === 401 || breakdownRes.status === 401 || connectorsRes.status === 401) {
      handle401();
      setTrendLoading(false);
      return;
    }

    const anyDenied = [trendsRes, breakdownRes, connectorsRes].some((res) => res.status === 403);
    if (anyDenied) {
      setTrendError("Access denied while loading trends.");
      setTrendLoading(false);
      return;
    }

    if (!trendsRes.ok || !breakdownRes.ok || !connectorsRes.ok || !trendsRes.data || !breakdownRes.data || !connectorsRes.data) {
      setTrendError("Failed to load usage trends.");
      setTrendLoading(false);
      return;
    }

    setTrendPoints(Array.isArray(trendsRes.data.items) ? trendsRes.data.items : []);
    setFailureBreakdown(breakdownRes.data ?? null);
    setConnectorSummary(Array.isArray(connectorsRes.data.items) ? connectorsRes.data.items : []);
    setTrendLoading(false);
  }, [handle401]);

  useEffect(() => {
    void fetchToolCalls();
  }, [fetchToolCalls]);

  useEffect(() => {
    void fetchTrendAndBreakdown();
  }, [fetchTrendAndBreakdown]);

  useEffect(() => {
    const handler = (event: Event) => {
      const custom = event as CustomEvent<{ path?: string }>;
      if (custom.detail?.path === pathname) {
        void fetchToolCalls();
        void fetchTrendAndBreakdown();
      }
    };
    window.addEventListener("dashboard:v2:refresh", handler as EventListener);
    return () => {
      window.removeEventListener("dashboard:v2:refresh", handler as EventListener);
    };
  }, [fetchToolCalls, fetchTrendAndBreakdown, pathname]);

  return (
    <section className="space-y-4">
      <h1 className="text-2xl font-semibold">MCP Usage</h1>
      <p className="text-sm text-muted-foreground">Recent tool calls, 24h execution summary, and 7d usage trends.</p>

      <div className="ds-card p-4">
        <div className="flex flex-wrap items-center gap-2">
          <Select
            value={statusFilter}
            onChange={(event) => setStatusFilter(event.target.value as "all" | "success" | "fail")}
            className="ds-input h-11 rounded-md px-3 text-sm md:h-9"
          >
            <option value="all">All status</option>
            <option value="success">Success</option>
            <option value="fail">Fail</option>
          </Select>
          <Input
            value={toolNameFilter}
            onChange={(event) => setToolNameFilter(event.target.value)}
            placeholder="Filter by tool name (exact)"
            className="ds-input h-11 rounded-md px-3 text-sm md:h-9"
          />
          <Input
            type="datetime-local"
            value={fromFilter}
            onChange={(event) => setFromFilter(event.target.value)}
            className="ds-input h-11 rounded-md px-3 text-sm md:h-9"
          />
          <Input
            type="datetime-local"
            value={toFilter}
            onChange={(event) => setToFilter(event.target.value)}
            className="ds-input h-11 rounded-md px-3 text-sm md:h-9"
          />
          <Button type="button" onClick={() => void fetchToolCalls()} disabled={toolCallsLoading} className="ds-btn h-11 rounded-md px-3 text-sm disabled:opacity-60 md:h-9">
            {toolCallsLoading ? "Loading..." : "Apply"}
          </Button>
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <article className="ds-card p-4">
          <p className="text-xs text-muted-foreground">Calls (24h)</p>
          <p className="mt-1 text-2xl font-semibold">{toolCallsSummary?.calls_24h ?? 0}</p>
        </article>
        <article className="ds-card p-4">
          <p className="text-xs text-muted-foreground">Success (24h)</p>
          <p className="mt-1 text-2xl font-semibold text-chart-2">{toolCallsSummary?.success_24h ?? 0}</p>
        </article>
        <article className="ds-card p-4">
          <p className="text-xs text-muted-foreground">Fail (24h)</p>
          <p className="mt-1 text-2xl font-semibold text-destructive">{toolCallsSummary?.fail_24h ?? 0}</p>
        </article>
        <article className="ds-card p-4">
          <p className="text-xs text-muted-foreground">Fail Rate</p>
          <p className="mt-1 text-xl font-semibold text-destructive">{((toolCallsSummary?.fail_rate_24h ?? 0) * 100).toFixed(1)}%</p>
        </article>
        <article className="ds-card p-4">
          <p className="text-xs text-muted-foreground">Blocked Rate</p>
          <p className="mt-1 text-xl font-semibold text-chart-4">{((toolCallsSummary?.blocked_rate_24h ?? 0) * 100).toFixed(1)}%</p>
        </article>
        <article className="ds-card p-4">
          <p className="text-xs text-muted-foreground">Retryable Fail Rate</p>
          <p className="mt-1 text-xl font-semibold text-primary">{((toolCallsSummary?.retryable_fail_rate_24h ?? 0) * 100).toFixed(1)}%</p>
        </article>
      </div>

      {toolCallsError ? (
        <div className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {toolCallsError}
        </div>
      ) : null}

      <div className="ds-card space-y-2 p-4">
        <p className="text-sm font-medium">Top Failure Codes (24h)</p>
        {(toolCallsSummary?.top_failure_codes ?? []).length === 0 ? <p className="text-xs text-muted-foreground">No failure codes.</p> : null}
        <div className="flex flex-wrap gap-2">
          {(toolCallsSummary?.top_failure_codes ?? []).map((entry) => (
            <span key={`top-fail-${entry.error_code}`} className="rounded-full border border-border px-2 py-1 text-xs">
              {entry.error_code}: {entry.count}
            </span>
          ))}
        </div>
      </div>

      <div className="ds-card space-y-2 p-4">
        <p className="text-sm font-medium">Recent Tool Calls</p>
        {toolCallsLoading ? <p className="text-xs text-muted-foreground">Loading usage...</p> : null}
        {!toolCallsLoading && toolCalls.length === 0 ? <p className="text-xs text-muted-foreground">No tool call logs yet.</p> : null}
        <div className="space-y-2">
          {toolCalls.map((call) => (
            <article key={call.id} className="rounded-md border border-border p-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <p className="text-sm font-medium">{call.tool_name}</p>
                  <p className="text-xs text-muted-foreground">
                    {call.api_key?.name ?? "unknown key"} ({call.api_key?.key_prefix ?? "n/a"}...)
                  </p>
                </div>
                <div className="text-right">
                  <p className={`text-xs font-medium ${call.status === "success" ? "text-chart-2" : "text-destructive"}`}>
                    {call.status}
                  </p>
                  <p className="text-xs text-muted-foreground">{call.latency_ms} ms</p>
                </div>
              </div>
              <p className="mt-1 text-xs text-muted-foreground">{new Date(call.created_at).toLocaleString()}</p>
              {call.error_code ? <p className="mt-1 text-xs text-destructive">error: {call.error_code}</p> : null}
            </article>
          ))}
        </div>
      </div>

      <div className="ds-card p-4">
        <div className="mb-3 flex items-center justify-between gap-2">
          <p className="text-sm font-medium">Usage Trends (7d)</p>
          <Button type="button" onClick={() => void fetchTrendAndBreakdown()} disabled={trendLoading} className="ds-btn h-10 rounded-md px-3 text-xs disabled:opacity-60">
            {trendLoading ? "Loading..." : "Refresh"}
          </Button>
        </div>

        {trendError ? (
          <div className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
            {trendError}
          </div>
        ) : null}

        <div className="grid gap-2 sm:grid-cols-2">
          <article className="rounded-md border border-border p-3">
            <p className="text-xs font-medium">Daily Calls Trend</p>
            <div className="mt-2 space-y-1">
              {trendPoints.slice(-7).map((point) => (
                <p key={`trend-${point.bucket_start}`} className="text-xs">
                  {new Date(point.bucket_start).toLocaleDateString()}: {point.calls} calls, fail {(point.fail_rate * 100).toFixed(1)}%
                </p>
              ))}
            </div>
          </article>
          <article className="rounded-md border border-border p-3">
            <p className="text-xs font-medium">Failure Categories</p>
            <div className="mt-2 space-y-1">
              {(failureBreakdown?.categories ?? []).slice(0, 6).map((item) => (
                <p key={`cat-${item.category}`} className="text-xs">
                  {item.category}: {item.count} ({(item.ratio * 100).toFixed(1)}%)
                </p>
              ))}
            </div>
          </article>
          <article className="rounded-md border border-border p-3">
            <p className="text-xs font-medium">Top Failure Codes</p>
            <div className="mt-2 space-y-1">
              {(failureBreakdown?.error_codes ?? []).slice(0, 6).map((item) => (
                <p key={`ecode-${item.error_code}`} className="text-xs">
                  {item.error_code}: {item.count}
                </p>
              ))}
            </div>
          </article>
          <article className="rounded-md border border-border p-3">
            <p className="text-xs font-medium">Connector Health</p>
            <div className="mt-2 space-y-1">
              {connectorSummary.map((item) => (
                <p key={`connector-${item.connector}`} className="text-xs">
                  {item.connector}: calls {item.calls}, fail {(item.fail_rate * 100).toFixed(1)}%, avg {Math.round(item.avg_latency_ms)}ms
                </p>
              ))}
              {connectorSummary.length === 0 ? <p className="text-xs text-muted-foreground">No connector data.</p> : null}
            </div>
          </article>
        </div>
      </div>
    </section>
  );
}
