"use client";

import { Select } from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { DateRangePicker } from "@/components/ui/date-range-picker";
import { useCallback, useEffect, useMemo, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Loader2 } from "lucide-react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ComposedChart,
  Line,
  Pie,
  PieChart,
  XAxis,
  YAxis,
} from "recharts";

import { buildNextPath, dashboardApiGet } from "../../../../../lib/dashboard-v2-client";
import { resolveDashboardScope } from "../../../../../lib/dashboard-scope";
import PageTitleWithTooltip from "@/components/dashboard-v2/page-title-with-tooltip";
import { ChartContainer, ChartTooltip, ChartTooltipContent } from "@/components/ui/chart";

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
  const searchParams = useSearchParams();
  const scope = useMemo(() => resolveDashboardScope(searchParams), [searchParams]);

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
  const [appliedStatusFilter, setAppliedStatusFilter] = useState<"all" | "success" | "fail">("all");
  const [appliedToolNameFilter, setAppliedToolNameFilter] = useState("");
  const [appliedFromFilter, setAppliedFromFilter] = useState("");
  const [appliedToFilter, setAppliedToFilter] = useState("");

  const handle401 = useCallback(() => {
    const next = encodeURIComponent(buildNextPath(pathname, window.location.search));
    router.replace(`/?next=${next}`);
  }, [pathname, router]);

  const handleApplyFilters = useCallback(() => {
    setAppliedStatusFilter(statusFilter);
    setAppliedToolNameFilter(toolNameFilter);
    setAppliedFromFilter(fromFilter);
    setAppliedToFilter(toFilter);
  }, [fromFilter, statusFilter, toFilter, toolNameFilter]);

  const fetchToolCalls = useCallback(async () => {
    setToolCallsLoading(true);
    setToolCallsError(null);

    const query = new URLSearchParams();
    query.set("limit", "20");
    query.set("status", appliedStatusFilter);
    if (scope.organizationId !== null) {
      query.set("organization_id", String(scope.organizationId));
    }
    if (scope.teamId !== null) {
      query.set("team_id", String(scope.teamId));
    }
    if (appliedToolNameFilter.trim()) {
      query.set("tool_name", appliedToolNameFilter.trim());
    }
    if (appliedFromFilter) {
      query.set("from", new Date(`${appliedFromFilter}T00:00:00`).toISOString());
    }
    if (appliedToFilter) {
      query.set("to", new Date(`${appliedToFilter}T23:59:59.999`).toISOString());
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
  }, [appliedFromFilter, appliedStatusFilter, appliedToFilter, appliedToolNameFilter, handle401, scope.organizationId, scope.teamId]);

  const fetchTrendAndBreakdown = useCallback(async () => {
    setTrendLoading(true);
    setTrendError(null);

    const trendsQuery = new URLSearchParams({ days: "7", bucket: "day" });
    const breakdownQuery = new URLSearchParams({ days: "7" });
    const connectorsQuery = new URLSearchParams({ days: "7" });
    if (scope.organizationId !== null) {
      const organizationId = String(scope.organizationId);
      trendsQuery.set("organization_id", organizationId);
      breakdownQuery.set("organization_id", organizationId);
      connectorsQuery.set("organization_id", organizationId);
    }
    if (scope.teamId !== null) {
      const teamId = String(scope.teamId);
      trendsQuery.set("team_id", teamId);
      breakdownQuery.set("team_id", teamId);
      connectorsQuery.set("team_id", teamId);
    }

    const [trendsRes, breakdownRes, connectorsRes] = await Promise.all([
      dashboardApiGet<TrendPayload>(`/api/tool-calls/trends?${trendsQuery.toString()}`),
      dashboardApiGet<FailureBreakdownPayload>(`/api/tool-calls/failure-breakdown?${breakdownQuery.toString()}`),
      dashboardApiGet<ConnectorPayload>(`/api/tool-calls/connectors?${connectorsQuery.toString()}`),
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
  }, [handle401, scope.organizationId, scope.teamId]);

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

  const callCompositionData = useMemo(
    () => [
      { name: "success", value: toolCallsSummary?.success_24h ?? 0 },
      { name: "fail", value: toolCallsSummary?.fail_24h ?? 0 },
    ],
    [toolCallsSummary?.fail_24h, toolCallsSummary?.success_24h]
  );

  const rateCompareData = useMemo(
    () => [
      { name: "fail", value: Number((((toolCallsSummary?.fail_rate_24h ?? 0) * 100).toFixed(2))) },
      { name: "blocked", value: Number((((toolCallsSummary?.blocked_rate_24h ?? 0) * 100).toFixed(2))) },
      { name: "retryable", value: Number((((toolCallsSummary?.retryable_fail_rate_24h ?? 0) * 100).toFixed(2))) },
    ],
    [toolCallsSummary?.blocked_rate_24h, toolCallsSummary?.fail_rate_24h, toolCallsSummary?.retryable_fail_rate_24h]
  );

  const topFailureCodes24h = useMemo(
    () => (toolCallsSummary?.top_failure_codes ?? []).map((entry) => ({ code: entry.error_code, count: entry.count })),
    [toolCallsSummary?.top_failure_codes]
  );

  const dailyTrendChart = useMemo(
    () =>
      trendPoints.slice(-7).map((point) => ({
        day: new Date(point.bucket_start).toLocaleDateString(),
        calls: point.calls,
        failRate: Number((point.fail_rate * 100).toFixed(2)),
      })),
    [trendPoints]
  );

  const failureCategoryChart = useMemo(
    () =>
      (failureBreakdown?.categories ?? []).slice(0, 6).map((item) => ({
        category: item.category,
        count: item.count,
        ratio: item.ratio,
        colorKey:
          item.category === "policy_blocked" ||
          item.category === "quota_exceeded" ||
          item.category === "access_denied" ||
          item.category === "resolve_fail" ||
          item.category === "upstream_temporary"
            ? item.category
            : "other",
      })),
    [failureBreakdown?.categories]
  );

  const connectorHealthChart = useMemo(
    () =>
      connectorSummary.map((item) => ({
        connector: item.connector,
        calls: item.calls,
        failRate: Number((item.fail_rate * 100).toFixed(2)),
      })),
    [connectorSummary]
  );

  const pageLoading = toolCallsLoading || trendLoading;

  if (pageLoading) {
    return (
      <section className="space-y-4">
        <PageTitleWithTooltip
          title="Usage"
          tooltip="Analyze recent tool calls, trends, failures, and connector health."
        />
        <p className="text-sm text-muted-foreground">Recent tool calls, 24h execution summary, and 7d usage trends.</p>
        <div className="ds-card flex min-h-[220px] items-center justify-center p-4">
          <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
        </div>
      </section>
    );
  }

  return (
    <section className="space-y-4">
      <PageTitleWithTooltip
        title="Usage"
        tooltip="Analyze recent tool calls, trends, failures, and connector health."
      />
      <p className="text-sm text-muted-foreground">Recent tool calls, 24h execution summary, and 7d usage trends.</p>

      <div className="ds-card p-4">
        <div className="flex items-center gap-2">
          <Select
            value={statusFilter}
            onChange={(event) => setStatusFilter(event.target.value as "all" | "success" | "fail")}
            className="ds-input h-11 w-[160px] shrink-0 rounded-md px-3 text-sm md:h-9"
          >
            <option value="all">All status</option>
            <option value="success">Success</option>
            <option value="fail">Fail</option>
          </Select>
          <Input
            value={toolNameFilter}
            onChange={(event) => setToolNameFilter(event.target.value)}
            placeholder="Filter by tool name (exact)"
            className="ds-input h-11 min-w-[280px] flex-1 rounded-md px-3 text-sm md:h-9"
          />
          <DateRangePicker
            from={fromFilter}
            to={toFilter}
            onChange={(next) => {
              setFromFilter(next.from);
              setToFilter(next.to);
            }}
            className="shrink-0"
          />
          <Button type="button" onClick={handleApplyFilters} disabled={toolCallsLoading} className="ds-btn h-11 shrink-0 rounded-md px-3 text-sm disabled:opacity-60 md:h-9">
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

      <div className="grid gap-3 lg:grid-cols-2">
        <article className="ds-card p-4">
          <p className="text-sm font-medium">Call Composition (24h)</p>
          <ChartContainer
            className="mt-3 h-56 w-full"
            config={{
              success: { label: "Success", color: "hsl(var(--chart-2))" },
              fail: { label: "Fail", color: "hsl(var(--destructive))" },
            }}
          >
            <PieChart>
              <Pie data={callCompositionData} dataKey="value" nameKey="name" innerRadius={48} outerRadius={78} paddingAngle={2}>
                <Cell fill="var(--color-success)" />
                <Cell fill="var(--color-fail)" />
              </Pie>
              <ChartTooltip cursor={false} content={<ChartTooltipContent />} />
            </PieChart>
          </ChartContainer>
        </article>

        <article className="ds-card p-4">
          <p className="text-sm font-medium">Rate Comparison (24h)</p>
          <ChartContainer
            className="mt-3 h-56 w-full"
            config={{
              value: { label: "Rate (%)", color: "hsl(var(--chart-4))" },
            }}
          >
            <BarChart data={rateCompareData} margin={{ top: 8, right: 8, left: 8, bottom: 0 }}>
              <CartesianGrid vertical={false} />
              <XAxis dataKey="name" />
              <YAxis />
              <Bar dataKey="value" fill="var(--color-value)" radius={4} />
              <ChartTooltip cursor={false} content={<ChartTooltipContent />} />
            </BarChart>
          </ChartContainer>
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
        {topFailureCodes24h.length > 0 ? (
          <ChartContainer className="h-56 w-full" config={{ count: { label: "Count", color: "hsl(var(--destructive))" } }}>
            <BarChart data={topFailureCodes24h} layout="vertical" margin={{ top: 0, right: 8, left: 8, bottom: 0 }}>
              <CartesianGrid horizontal={false} />
              <XAxis type="number" />
              <YAxis dataKey="code" type="category" width={120} tickLine={false} axisLine={false} />
              <Bar dataKey="count" fill="var(--color-count)" radius={4} />
              <ChartTooltip cursor={false} content={<ChartTooltipContent />} />
            </BarChart>
          </ChartContainer>
        ) : null}
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
            <ChartContainer
              className="mt-2 h-48 w-full"
              config={{
                calls: { label: "Calls", color: "hsl(var(--chart-1))" },
                failRate: { label: "Fail Rate (%)", color: "hsl(var(--destructive))" },
              }}
            >
              <ComposedChart data={dailyTrendChart} margin={{ top: 8, right: 8, left: 8, bottom: 0 }}>
                <CartesianGrid vertical={false} />
                <XAxis dataKey="day" />
                <YAxis yAxisId="left" />
                <YAxis yAxisId="right" orientation="right" />
                <Bar yAxisId="left" dataKey="calls" fill="var(--color-calls)" radius={4} />
                <Line yAxisId="right" type="monotone" dataKey="failRate" stroke="var(--color-failRate)" strokeWidth={2} dot={false} />
                <ChartTooltip cursor={false} content={<ChartTooltipContent />} />
              </ComposedChart>
            </ChartContainer>
          </article>
          <article className="rounded-md border border-border p-3">
            <p className="text-xs font-medium">Failure Categories</p>
            <ChartContainer
              className="mt-2 h-48 w-full"
              config={{
                policy_blocked: { label: "Policy blocked", color: "hsl(var(--chart-4))" },
                quota_exceeded: { label: "Quota exceeded", color: "hsl(var(--chart-5))" },
                access_denied: { label: "Access denied", color: "hsl(var(--destructive))" },
                resolve_fail: { label: "Resolve fail", color: "hsl(var(--chart-3))" },
                upstream_temporary: { label: "Upstream temporary", color: "hsl(var(--chart-2))" },
                other: { label: "Other", color: "hsl(var(--chart-1))" },
              }}
            >
              <PieChart>
                <Pie data={failureCategoryChart} dataKey="count" nameKey="category" innerRadius={40} outerRadius={72}>
                  {failureCategoryChart.map((item) => (
                    <Cell key={`cat-cell-${item.category}`} fill={`var(--color-${item.colorKey})`} />
                  ))}
                </Pie>
                <ChartTooltip
                  cursor={false}
                  content={
                    <ChartTooltipContent
                      formatter={(value, name) => {
                        const numericValue = Array.isArray(value) ? value[0] : value;
                        const item = failureCategoryChart.find((entry) => entry.category === String(name));
                        return `${numericValue} (${(((item?.ratio ?? 0) * 100)).toFixed(1)}%)`;
                      }}
                    />
                  }
                />
              </PieChart>
            </ChartContainer>
          </article>
          <article className="rounded-md border border-border p-3">
            <p className="text-xs font-medium">Top Failure Codes</p>
            <ChartContainer className="mt-2 h-48 w-full" config={{ count: { label: "Count", color: "hsl(var(--destructive))" } }}>
              <BarChart data={(failureBreakdown?.error_codes ?? []).slice(0, 6).map((item) => ({ code: item.error_code, count: item.count }))} layout="vertical" margin={{ top: 0, right: 8, left: 8, bottom: 0 }}>
                <CartesianGrid horizontal={false} />
                <XAxis type="number" />
                <YAxis dataKey="code" type="category" width={110} tickLine={false} axisLine={false} />
                <Bar dataKey="count" fill="var(--color-count)" radius={4} />
                <ChartTooltip cursor={false} content={<ChartTooltipContent />} />
              </BarChart>
            </ChartContainer>
          </article>
          <article className="rounded-md border border-border p-3">
            <p className="text-xs font-medium">Connector Health</p>
            <ChartContainer
              className="mt-2 h-48 w-full"
              config={{
                calls: { label: "Calls", color: "hsl(var(--chart-1))" },
                failRate: { label: "Fail Rate (%)", color: "hsl(var(--destructive))" },
              }}
            >
              <ComposedChart
                data={connectorHealthChart}
                margin={{ top: 8, right: 8, left: 8, bottom: 0 }}
              >
                <CartesianGrid vertical={false} />
                <XAxis dataKey="connector" />
                <YAxis yAxisId="left" />
                <YAxis yAxisId="right" orientation="right" />
                <Bar yAxisId="left" dataKey="calls" fill="var(--color-calls)" radius={4} />
                <Line yAxisId="right" type="monotone" dataKey="failRate" stroke="var(--color-failRate)" strokeWidth={2} dot={false} />
                <ChartTooltip cursor={false} content={<ChartTooltipContent />} />
              </ComposedChart>
            </ChartContainer>
            {connectorSummary.length === 0 ? <p className="text-xs text-muted-foreground">No connector data.</p> : null}
          </article>
        </div>
      </div>
    </section>
  );
}
