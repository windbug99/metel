"use client";

import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Select } from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { useCallback, useEffect, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Loader2 } from "lucide-react";

import { buildNextPath, dashboardApiGet } from "../../../../../lib/dashboard-v2-client";
import { resolveDashboardScope } from "../../../../../lib/dashboard-scope";
import StatusBadge from "../../../../../components/dashboard-v2/status-badge";
import PageTitleWithTooltip from "@/components/dashboard-v2/page-title-with-tooltip";

type AuditEventItem = {
  id: number;
  request_id: string | null;
  timestamp: string;
  action?: { tool_name?: string | null };
  actor?: { api_key?: { name?: string | null; key_prefix?: string | null } };
  outcome?: {
    decision?: string | null;
    error_code?: string | null;
    latency_ms?: number | null;
  };
};

type AuditSummary = {
  allowed_count: number;
  high_risk_allowed_count: number;
  policy_override_usage: number;
  policy_blocked_count: number;
  access_denied_count: number;
  failed_count: number;
};

type AuditListPayload = {
  items?: AuditEventItem[];
  summary?: AuditSummary;
};

type TeamItem = {
  id: number;
  name: string;
};

type AgentSummaryItem = {
  agent_id: number | null;
  agent_name?: string | null;
};

type AuditDetailPayload = {
  id: number;
  request_id: string | null;
  trace_id: string | null;
  timestamp: string;
  action: { tool_name?: string | null; connector?: string | null };
  actor: {
    user_id?: string | null;
    api_key?: { id?: number | null; name?: string | null; key_prefix?: string | null };
    agent?: { id?: number | null; name?: string | null; team_id?: number | null; organization_id?: number | null };
  };
  outcome: {
    decision?: string | null;
    status?: string | null;
    error_code?: string | null;
    upstream_status?: number | null;
    latency_ms?: number | null;
    retry_count?: number | null;
    backoff_ms?: number | null;
  };
  execution?: {
    request_payload?: unknown;
    resolved_payload?: unknown;
    risk_result?: unknown;
    masked_fields?: unknown;
  };
};

export default function DashboardAuditEventsPage() {
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();

  const [items, setItems] = useState<AuditEventItem[]>([]);
  const [summary, setSummary] = useState<AuditSummary | null>(null);
  const [teams, setTeams] = useState<TeamItem[]>([]);
  const [agents, setAgents] = useState<AgentSummaryItem[]>([]);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [statusFilter, setStatusFilter] = useState<"all" | "success" | "fail">("all");
  const [decisionFilter, setDecisionFilter] = useState<"all" | "allowed" | "policy_blocked" | "access_denied" | "failed" | "policy_override_allowed">("all");
  const [toolNameFilter, setToolNameFilter] = useState("");
  const [teamFilter, setTeamFilter] = useState("");
  const [agentFilter, setAgentFilter] = useState("");
  const [fromFilter, setFromFilter] = useState("");
  const [toFilter, setToFilter] = useState("");

  const [detail, setDetail] = useState<AuditDetailPayload | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const scopeState = resolveDashboardScope(searchParams);
  const isUserScope = scopeState.scope === "user";
  const isOrgScope = scopeState.scope === "org";
  const isTeamScope = scopeState.scope === "team";

  const handle401 = useCallback(() => {
    const next = encodeURIComponent(buildNextPath(pathname, window.location.search));
    router.replace(`/?next=${next}`);
  }, [pathname, router]);

  const fetchAuditEvents = useCallback(async () => {
    setLoading(true);
    setError(null);

    const query = new URLSearchParams();
    query.set("limit", "50");
    query.set("status", statusFilter);
    query.set("decision", decisionFilter);
    if (toolNameFilter.trim()) {
      query.set("tool_name", toolNameFilter.trim());
    }
    if (scopeState.organizationId !== null) {
      query.set("organization_id", String(scopeState.organizationId));
    }
    if (isTeamScope && scopeState.teamId !== null) {
      query.set("team_id", String(scopeState.teamId));
    } else if (isOrgScope && teamFilter) {
      query.set("team_id", teamFilter);
    }
    if (agentFilter) {
      query.set("agent_id", agentFilter);
    }
    if (fromFilter) {
      query.set("from", new Date(fromFilter).toISOString());
    }
    if (toFilter) {
      query.set("to", new Date(toFilter).toISOString());
    }

    const result = await dashboardApiGet<AuditListPayload>(`/api/audit/events?${query.toString()}`);
    if (result.status === 401) {
      handle401();
      setLoading(false);
      return;
    }
    if (result.status === 403) {
      setError("Access denied while loading audit events.");
      setLoading(false);
      return;
    }
    if (!result.ok || !result.data) {
      setError(result.error ?? "Failed to load audit events.");
      setLoading(false);
      return;
    }

    setItems(Array.isArray(result.data.items) ? result.data.items : []);
    setSummary(result.data.summary ?? null);
    setLoading(false);
  }, [agentFilter, decisionFilter, fromFilter, handle401, isOrgScope, isTeamScope, scopeState.organizationId, scopeState.teamId, statusFilter, teamFilter, toFilter, toolNameFilter]);

  const fetchScopeOptions = useCallback(async () => {
    const agentQuery = new URLSearchParams({ days: "7" });
    if (scopeState.organizationId !== null) {
      agentQuery.set("organization_id", String(scopeState.organizationId));
    }
    if (isTeamScope && scopeState.teamId !== null) {
      agentQuery.set("team_id", String(scopeState.teamId));
    } else if (isOrgScope && teamFilter) {
      agentQuery.set("team_id", teamFilter);
    }

    if (isOrgScope && scopeState.organizationId !== null) {
      const [teamRes, agentRes] = await Promise.all([
        dashboardApiGet<{ items?: TeamItem[] }>(`/api/teams?organization_id=${scopeState.organizationId}`),
        dashboardApiGet<{ items?: AgentSummaryItem[] }>(`/api/tool-calls/agents?${agentQuery.toString()}`),
      ]);
      if (teamRes.status === 401 || agentRes.status === 401) {
        handle401();
        return;
      }
      if (teamRes.ok && teamRes.data) {
        setTeams(Array.isArray(teamRes.data.items) ? teamRes.data.items : []);
      } else {
        setTeams([]);
      }
      if (agentRes.ok && agentRes.data) {
        setAgents(Array.isArray(agentRes.data.items) ? agentRes.data.items : []);
      } else {
        setAgents([]);
      }
      return;
    }

    const agentRes = await dashboardApiGet<{ items?: AgentSummaryItem[] }>(`/api/tool-calls/agents?${agentQuery.toString()}`);
    if (agentRes.status === 401) {
      handle401();
      return;
    }
    setTeams([]);
    if (agentRes.ok && agentRes.data) {
      setAgents(Array.isArray(agentRes.data.items) ? agentRes.data.items : []);
    } else {
      setAgents([]);
    }
  }, [handle401, isOrgScope, isTeamScope, scopeState.organizationId, scopeState.teamId, teamFilter]);

  const fetchAuditEventDetail = useCallback(
    async (eventId: number) => {
      setDetailLoading(true);
      setError(null);

      const result = await dashboardApiGet<AuditDetailPayload>(`/api/audit/events/${eventId}`);
      if (result.status === 401) {
        handle401();
        setDetailLoading(false);
        return;
      }
      if (result.status === 403 || result.status === 404) {
        setError("Cannot load audit event detail.");
        setDetailLoading(false);
        return;
      }
      if (!result.ok || !result.data) {
        setError(result.error ?? "Failed to load audit event detail.");
        setDetailLoading(false);
        return;
      }

      setDetail(result.data);
      setDetailLoading(false);
    },
    [handle401]
  );

  useEffect(() => {
    void fetchAuditEvents();
  }, [fetchAuditEvents]);

  useEffect(() => {
    void fetchScopeOptions();
  }, [fetchScopeOptions]);

  useEffect(() => {
    if (isTeamScope && scopeState.teamId !== null) {
      setTeamFilter(String(scopeState.teamId));
    } else if (!isOrgScope) {
      setTeamFilter("");
      setAgentFilter("");
    } else if (scopeState.organizationId === null) {
      setTeamFilter("");
    }
  }, [isOrgScope, isTeamScope, scopeState.organizationId, scopeState.teamId]);

  useEffect(() => {
    const handler = (event: Event) => {
      const custom = event as CustomEvent<{ path?: string }>;
      if (custom.detail?.path === pathname) {
        void fetchAuditEvents();
      }
    };
    window.addEventListener("dashboard:v2:refresh", handler as EventListener);
    return () => {
      window.removeEventListener("dashboard:v2:refresh", handler as EventListener);
    };
  }, [fetchAuditEvents, pathname]);

  if (loading) {
    return (
      <section className="space-y-4">
        <PageTitleWithTooltip
          title="Audit Events"
          tooltip="Search and inspect audit events by status, decision, tool, agent, and date."
        />
        <p className="text-sm text-muted-foreground">
          {isUserScope
            ? "Your personal audit trail."
            : isTeamScope
            ? "Team-scoped audit events under organization governance."
            : "Organization-scoped audit events with optional team drilldown."}
        </p>
        <div className="ds-card flex min-h-[220px] items-center justify-center p-4">
          <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
        </div>
      </section>
    );
  }

  return (
    <section className="space-y-4">
      <PageTitleWithTooltip
        title="Audit Events"
        tooltip="Search and inspect audit events by status, decision, tool, agent, and date."
      />
      <p className="text-sm text-muted-foreground">
        {isUserScope
          ? "Your personal audit trail."
          : isTeamScope
          ? "Team-scoped audit events under organization governance."
          : "Organization-scoped audit events with optional team drilldown."}
      </p>

      <div className="ds-card p-4">
        <div className="space-y-2">
          <div className={isOrgScope ? "grid gap-2 lg:grid-cols-4" : "grid gap-2 lg:grid-cols-3"}>
            <Select
              value={statusFilter}
              onChange={(event) => setStatusFilter(event.target.value as "all" | "success" | "fail")}
              className="ds-input h-11 rounded-md px-3 text-sm md:h-9"
            >
              <option value="all">All status</option>
              <option value="success">Success</option>
              <option value="fail">Fail</option>
            </Select>
            <Select
              value={decisionFilter}
              onChange={(event) =>
                setDecisionFilter(
                  event.target.value as "all" | "allowed" | "policy_blocked" | "access_denied" | "failed" | "policy_override_allowed"
                )
              }
              className="ds-input h-11 rounded-md px-3 text-sm md:h-9"
            >
              <option value="all">All decisions</option>
              <option value="allowed">allowed</option>
              <option value="policy_blocked">policy_blocked</option>
              <option value="access_denied">access_denied</option>
              <option value="failed">failed</option>
              <option value="policy_override_allowed">policy_override_allowed</option>
            </Select>
            <Input
              value={toolNameFilter}
              onChange={(event) => setToolNameFilter(event.target.value)}
              placeholder="Tool name"
              className="ds-input h-11 rounded-md px-3 text-sm md:h-9"
            />
            {isOrgScope ? (
              <Select
                value={teamFilter}
                onChange={(event) => setTeamFilter(event.target.value)}
                className="ds-input h-11 rounded-md px-3 text-sm md:h-9"
              >
                <option value="">All teams in org</option>
                {teams.map((team) => (
                  <option key={`audit-team-${team.id}`} value={String(team.id)}>
                    Team #{team.id} - {team.name}
                  </option>
                ))}
              </Select>
            ) : null}
          </div>

          <div className="grid items-center gap-2 lg:grid-cols-[minmax(220px,1fr)_minmax(220px,1fr)_minmax(220px,1fr)_auto]">
            <Select value={agentFilter} onChange={(event) => setAgentFilter(event.target.value)} className="ds-input h-11 rounded-md px-3 text-sm md:h-9">
              <option value="">All agents</option>
              {agents.map((agent) => (
                <option key={`audit-agent-${String(agent.agent_id ?? "none")}`} value={agent.agent_id === null ? "" : String(agent.agent_id)}>
                  {agent.agent_id === null ? "Unassigned (no filter)" : `Agent #${agent.agent_id} - ${agent.agent_name ?? "Unnamed"}`}
                </option>
              ))}
            </Select>
            <Input type="datetime-local" value={fromFilter} onChange={(event) => setFromFilter(event.target.value)} className="ds-input h-11 rounded-md px-3 text-sm md:h-9" />
            <Input type="datetime-local" value={toFilter} onChange={(event) => setToFilter(event.target.value)} className="ds-input h-11 rounded-md px-3 text-sm md:h-9" />
            <Button
              type="button"
              onClick={() => void fetchAuditEvents()}
              disabled={loading}
              className="ds-btn h-11 whitespace-nowrap rounded-md px-3 text-sm disabled:opacity-60 md:h-9"
            >
              {loading ? "Loading..." : "Apply"}
            </Button>
          </div>
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <article className="ds-card p-4">
          <p className="text-xs text-muted-foreground">Allowed</p>
          <p className="mt-1 text-xl font-semibold text-chart-2">{summary?.allowed_count ?? 0}</p>
        </article>
        <article className="ds-card p-4">
          <p className="text-xs text-muted-foreground">Policy Blocked</p>
          <p className="mt-1 text-xl font-semibold text-chart-4">{summary?.policy_blocked_count ?? 0}</p>
        </article>
        <article className="ds-card p-4">
          <p className="text-xs text-muted-foreground">Access Denied</p>
          <p className="mt-1 text-xl font-semibold text-chart-4">{summary?.access_denied_count ?? 0}</p>
        </article>
        <article className="ds-card p-4">
          <p className="text-xs text-muted-foreground">Failed</p>
          <p className="mt-1 text-xl font-semibold text-destructive">{summary?.failed_count ?? 0}</p>
        </article>
        <article className="ds-card p-4">
          <p className="text-xs text-muted-foreground">High Risk Allowed</p>
          <p className="mt-1 text-xl font-semibold text-primary">{summary?.high_risk_allowed_count ?? 0}</p>
        </article>
        <article className="ds-card p-4">
          <p className="text-xs text-muted-foreground">Policy Override Usage</p>
          <p className="mt-1 text-xl font-semibold text-primary">{((summary?.policy_override_usage ?? 0) * 100).toFixed(1)}%</p>
        </article>
      </div>

      {error ? (
        <div className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error}
        </div>
      ) : null}

      <div className="ds-card overflow-x-auto">
        {loading ? <p className="px-4 py-3 text-sm text-muted-foreground">Loading audit events...</p> : null}
        {!loading && items.length === 0 ? <p className="px-4 py-3 text-sm text-muted-foreground">No audit events found.</p> : null}
        {items.length > 0 ? (
          <Table className="min-w-[640px] text-sm">
            <TableHeader className="bg-muted/60 text-left text-xs text-muted-foreground">
              <TableRow>
                <TableHead className="px-4 py-3">Time</TableHead>
                <TableHead className="px-4 py-3">Tool</TableHead>
                <TableHead className="px-4 py-3">Decision</TableHead>
                <TableHead className="px-4 py-3">Error</TableHead>
                <TableHead className="px-4 py-3">Detail</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.map((item) => (
                <TableRow key={item.id} className="border-t border-border">
                  <TableCell className="px-4 py-3">{new Date(item.timestamp).toLocaleString()}</TableCell>
                  <TableCell className="px-4 py-3">{item.action?.tool_name ?? "-"}</TableCell>
                  <TableCell className="px-4 py-3">
                    <StatusBadge kind="decision" value={item.outcome?.decision} />
                  </TableCell>
                  <TableCell className="px-4 py-3">{item.outcome?.error_code ?? "-"}</TableCell>
                  <TableCell className="px-4 py-3">
                    <Button
                      type="button"
                      onClick={() => void fetchAuditEventDetail(item.id)}
                      disabled={detailLoading}
                      className="ds-btn h-9 rounded-md px-3 text-xs disabled:opacity-60"
                    >
                      {detailLoading ? "Loading..." : "Details"}
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        ) : null}
      </div>

      {detail ? (
        <div className="ds-card p-4">
          <p className="text-sm font-medium">Selected Audit Detail: #{detail.id}</p>
          <pre className="mt-2 overflow-x-auto rounded bg-muted/60 p-3 text-[11px] text-muted-foreground">
            {JSON.stringify(detail, null, 2)}
          </pre>
        </div>
      ) : null}
    </section>
  );
}
