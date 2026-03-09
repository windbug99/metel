"use client";

import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Select } from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { useCallback, useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { ChevronsUpDown, Loader2 } from "lucide-react";
import { DropdownMenu, DropdownMenuCheckboxItem, DropdownMenuContent, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";

import { buildNextPath, dashboardApiGet, dashboardApiRequest } from "../../../../../lib/dashboard-v2-client";
import StatusBadge from "../../../../../components/dashboard-v2/status-badge";
import PageTitleWithTooltip from "@/components/dashboard-v2/page-title-with-tooltip";

type ApiKeyItem = {
  id: number;
  name: string;
  key_prefix: string;
  is_active: boolean;
  team_id: number | null;
  allowed_tools: string[] | null;
  policy_json: Record<string, unknown> | null;
  memo: string | null;
  tags: string[] | null;
  issued_by: string | null;
  rotated_from: number | null;
  last_used_at: string | null;
  created_at: string | null;
  revoked_at: string | null;
};

type TeamItem = {
  id: number;
  name: string;
};

type ToolOptionItem = {
  tool_name: string;
  service: string;
};

type DrilldownPayload = {
  api_key: { id: number; name: string; key_prefix: string };
  window_days: number;
  summary: {
    total_calls: number;
    success_count: number;
    fail_count: number;
    success_rate: number;
    fail_rate: number;
    avg_latency_ms: number;
    p95_latency_ms: number;
  };
  top_error_codes: Array<{ error_code: string; count: number }>;
  top_tools: Array<{ tool_name: string; count: number }>;
  trend: Array<{ day: string; calls: number; success: number; fail: number; success_rate: number; fail_rate: number }>;
};

type CreateApiKeyPayload = {
  id: number;
  name: string;
  key_prefix: string;
  api_key?: string;
};

type RotateApiKeyPayload = {
  id: number;
  name: string;
  key_prefix: string;
  api_key?: string;
};

function parseCsvList(value: string): string[] | null {
  const items = value
    .split(",")
    .map((item) => item.trim())
    .filter((item) => item.length > 0);
  return items.length > 0 ? items : null;
}

function csvHasValue(csv: string, value: string): boolean {
  const normalized = value.trim();
  if (!normalized) {
    return false;
  }
  return (parseCsvList(csv) ?? []).includes(normalized);
}

function updateCsvSelection(csv: string, value: string, checked: boolean): string {
  const normalized = value.trim();
  if (!normalized) {
    return csv;
  }
  const current = parseCsvList(csv) ?? [];
  const next = checked ? Array.from(new Set([...current, normalized])) : current.filter((item) => item !== normalized);
  return next.join(", ");
}

function toolsDropdownLabel(csv: string): string {
  const selected = parseCsvList(csv) ?? [];
  if (selected.length === 0) {
    return "Allowed tools (optional)";
  }
  if (selected.length === 1) {
    return selected[0] ?? "Allowed tools (optional)";
  }
  return `${selected[0]} +${selected.length - 1}`;
}

function stringifyJson(value: unknown): string {
  try {
    return JSON.stringify(value ?? {}, null, 2);
  } catch {
    return "{}";
  }
}

function parseJsonObject(value: string): Record<string, unknown> | null {
  const text = value.trim();
  if (!text) {
    return null;
  }
  const parsed = JSON.parse(text) as unknown;
  if (parsed === null) {
    return null;
  }
  if (typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error("policy_json must be a JSON object.");
  }
  return parsed as Record<string, unknown>;
}

export default function DashboardApiKeysPage() {
  const pathname = usePathname();
  const router = useRouter();
  const [items, setItems] = useState<ApiKeyItem[]>([]);
  const [teams, setTeams] = useState<TeamItem[]>([]);
  const [toolOptions, setToolOptions] = useState<ToolOptionItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [createName, setCreateName] = useState("default");
  const [createTeamId, setCreateTeamId] = useState("");
  const [createMemo, setCreateMemo] = useState("");
  const [createAllowedTools, setCreateAllowedTools] = useState("");
  const [createTags, setCreateTags] = useState("");
  const [createPolicyJson, setCreatePolicyJson] = useState("{}");

  const [creating, setCreating] = useState(false);
  const [createdApiKey, setCreatedApiKey] = useState<string | null>(null);

  const [nameDraft, setNameDraft] = useState<Record<number, string>>({});
  const [teamDraft, setTeamDraft] = useState<Record<number, string>>({});
  const [memoDraft, setMemoDraft] = useState<Record<number, string>>({});
  const [allowedToolsDraft, setAllowedToolsDraft] = useState<Record<number, string>>({});
  const [tagsDraft, setTagsDraft] = useState<Record<number, string>>({});
  const [policyDraft, setPolicyDraft] = useState<Record<number, string>>({});

  const [updatingId, setUpdatingId] = useState<number | null>(null);
  const [rotatingId, setRotatingId] = useState<number | null>(null);
  const [revokingId, setRevokingId] = useState<number | null>(null);

  const [drilldownById, setDrilldownById] = useState<Record<number, DrilldownPayload | null>>({});
  const [drilldownLoadingId, setDrilldownLoadingId] = useState<number | null>(null);

  const fetchApiKeys = useCallback(async () => {
    setLoading(true);
    setError(null);

    const result = await dashboardApiGet<{ items?: ApiKeyItem[] }>("/api/api-keys");
    if (result.status === 401) {
      const next = encodeURIComponent(buildNextPath(pathname, window.location.search));
      router.replace(`/?next=${next}`);
      setLoading(false);
      return;
    }
    if (result.status === 403) {
      setError("Access denied while loading API keys.");
      setLoading(false);
      return;
    }
    if (!result.ok || !result.data) {
      setError(result.error ?? "Failed to load API keys.");
      setLoading(false);
      return;
    }

    const nextItems = Array.isArray(result.data.items) ? result.data.items : [];
    setItems(nextItems);

    const nextName: Record<number, string> = {};
    const nextTeam: Record<number, string> = {};
    const nextMemo: Record<number, string> = {};
    const nextAllowedTools: Record<number, string> = {};
    const nextTags: Record<number, string> = {};
    const nextPolicy: Record<number, string> = {};
    for (const item of nextItems) {
      nextName[item.id] = item.name ?? "";
      nextTeam[item.id] = item.team_id === null ? "" : String(item.team_id);
      nextMemo[item.id] = item.memo ?? "";
      nextAllowedTools[item.id] = (item.allowed_tools ?? []).join(", ");
      nextTags[item.id] = (item.tags ?? []).join(", ");
      nextPolicy[item.id] = stringifyJson(item.policy_json ?? {});
    }
    setNameDraft(nextName);
    setTeamDraft(nextTeam);
    setMemoDraft(nextMemo);
    setAllowedToolsDraft(nextAllowedTools);
    setTagsDraft(nextTags);
    setPolicyDraft(nextPolicy);

    const teamResult = await dashboardApiGet<{ items?: TeamItem[] }>("/api/teams");
    if (teamResult.ok && teamResult.data) {
      setTeams(Array.isArray(teamResult.data.items) ? teamResult.data.items : []);
    }

    const toolOptionsResult = await dashboardApiGet<{ items?: ToolOptionItem[] }>("/api/api-keys/tool-options");
    if (toolOptionsResult.ok && toolOptionsResult.data) {
      setToolOptions(Array.isArray(toolOptionsResult.data.items) ? toolOptionsResult.data.items : []);
    }

    setLoading(false);
  }, [pathname, router]);

  const handleCreateApiKey = useCallback(async () => {
    setCreating(true);
    setCreatedApiKey(null);
    setError(null);

    let policyJson: Record<string, unknown> | null = null;
    try {
      policyJson = parseJsonObject(createPolicyJson);
    } catch (createError) {
      setError(createError instanceof Error ? createError.message : "Invalid policy JSON.");
      setCreating(false);
      return;
    }

    const result = await dashboardApiRequest<CreateApiKeyPayload>("/api/api-keys", {
      method: "POST",
      body: {
        name: createName.trim() || "default",
        team_id: createTeamId ? Number(createTeamId) : null,
        memo: createMemo.trim() || null,
        allowed_tools: parseCsvList(createAllowedTools),
        tags: parseCsvList(createTags),
        policy_json: policyJson,
      },
    });
    if (result.status === 401) {
      const next = encodeURIComponent(buildNextPath(pathname, window.location.search));
      router.replace(`/?next=${next}`);
      setCreating(false);
      return;
    }
    if (result.status === 403) {
      setError("Access denied while creating API key.");
      setCreating(false);
      return;
    }
    if (!result.ok || !result.data) {
      setError(result.error ?? "Failed to create API key.");
      setCreating(false);
      return;
    }

    setCreatedApiKey(result.data.api_key ?? null);
    setCreateTeamId("");
    setCreateMemo("");
    setCreateAllowedTools("");
    setCreateTags("");
    setCreatePolicyJson("{}");
    await fetchApiKeys();
    setCreating(false);
  }, [createAllowedTools, createMemo, createName, createPolicyJson, createTags, createTeamId, fetchApiKeys, pathname, router]);

  const handleUpdateApiKey = useCallback(
    async (id: number) => {
      setUpdatingId(id);
      setError(null);

      let policyJson: Record<string, unknown> | null = null;
      try {
        policyJson = parseJsonObject(policyDraft[id] ?? "{}");
      } catch (updateError) {
        setError(updateError instanceof Error ? updateError.message : "Invalid policy JSON.");
        setUpdatingId(null);
        return;
      }

      const result = await dashboardApiRequest(`/api/api-keys/${id}`, {
        method: "PATCH",
        body: {
          name: (nameDraft[id] ?? "").trim(),
          team_id: (teamDraft[id] ?? "").trim() ? Number((teamDraft[id] ?? "").trim()) : null,
          memo: (memoDraft[id] ?? "").trim() || null,
          allowed_tools: parseCsvList(allowedToolsDraft[id] ?? ""),
          tags: parseCsvList(tagsDraft[id] ?? ""),
          policy_json: policyJson,
        },
      });
      if (result.status === 401) {
        const next = encodeURIComponent(buildNextPath(pathname, window.location.search));
        router.replace(`/?next=${next}`);
        setUpdatingId(null);
        return;
      }
      if (result.status === 403) {
        setError("Access denied while updating API key.");
        setUpdatingId(null);
        return;
      }
      if (!result.ok) {
        setError(result.error ?? "Failed to update API key.");
        setUpdatingId(null);
        return;
      }

      await fetchApiKeys();
      setUpdatingId(null);
    },
    [allowedToolsDraft, fetchApiKeys, memoDraft, nameDraft, pathname, policyDraft, router, tagsDraft, teamDraft]
  );

  const handleRotateApiKey = useCallback(
    async (id: number) => {
      setRotatingId(id);
      setError(null);
      setCreatedApiKey(null);

      const result = await dashboardApiRequest<RotateApiKeyPayload>(`/api/api-keys/${id}/rotate`, {
        method: "POST",
      });
      if (result.status === 401) {
        const next = encodeURIComponent(buildNextPath(pathname, window.location.search));
        router.replace(`/?next=${next}`);
        setRotatingId(null);
        return;
      }
      if (result.status === 403) {
        setError("Access denied while rotating API key.");
        setRotatingId(null);
        return;
      }
      if (!result.ok || !result.data) {
        setError(result.error ?? "Failed to rotate API key.");
        setRotatingId(null);
        return;
      }

      setCreatedApiKey(result.data.api_key ?? null);
      await fetchApiKeys();
      setRotatingId(null);
    },
    [fetchApiKeys, pathname, router]
  );

  const handleRevokeApiKey = useCallback(
    async (id: number) => {
      setRevokingId(id);
      setError(null);

      const result = await dashboardApiRequest(`/api/api-keys/${id}`, {
        method: "DELETE",
      });
      if (result.status === 401) {
        const next = encodeURIComponent(buildNextPath(pathname, window.location.search));
        router.replace(`/?next=${next}`);
        setRevokingId(null);
        return;
      }
      if (result.status === 403) {
        setError("Access denied while revoking API key.");
        setRevokingId(null);
        return;
      }
      if (!result.ok) {
        setError(result.error ?? "Failed to revoke API key.");
        setRevokingId(null);
        return;
      }

      await fetchApiKeys();
      setRevokingId(null);
    },
    [fetchApiKeys, pathname, router]
  );

  const handleLoadDrilldown = useCallback(
    async (id: number) => {
      setDrilldownLoadingId(id);
      setError(null);

      const result = await dashboardApiGet<DrilldownPayload>(`/api/api-keys/${id}/drilldown?days=7`);
      if (result.status === 401) {
        const next = encodeURIComponent(buildNextPath(pathname, window.location.search));
        router.replace(`/?next=${next}`);
        setDrilldownLoadingId(null);
        return;
      }
      if (result.status === 403) {
        setError("Access denied while loading API key drill-down.");
        setDrilldownLoadingId(null);
        return;
      }
      if (!result.ok || !result.data) {
        setError(result.error ?? "Failed to load API key drill-down.");
        setDrilldownLoadingId(null);
        return;
      }

      setDrilldownById((prev) => ({ ...prev, [id]: result.data ?? null }));
      setDrilldownLoadingId(null);
    },
    [pathname, router]
  );

  const copyApiKey = useCallback(async () => {
    if (!createdApiKey) {
      return;
    }
    try {
      await navigator.clipboard.writeText(createdApiKey);
    } catch {
      // ignore clipboard failures on unsupported browsers
    }
  }, [createdApiKey]);

  useEffect(() => {
    void fetchApiKeys();
  }, [fetchApiKeys]);

  useEffect(() => {
    const handler = (event: Event) => {
      const custom = event as CustomEvent<{ path?: string }>;
      if (custom.detail?.path === pathname) {
        void fetchApiKeys();
      }
    };
    window.addEventListener("dashboard:v2:refresh", handler as EventListener);
    return () => {
      window.removeEventListener("dashboard:v2:refresh", handler as EventListener);
    };
  }, [fetchApiKeys, pathname]);

  if (loading) {
    return (
      <section className="space-y-4">
        <PageTitleWithTooltip title="API Keys" tooltip="Create, rotate, revoke, and inspect scoped API keys." />
        <p className="text-sm text-muted-foreground">Issue, rotate, revoke, and inspect API keys with scoped policies.</p>
        <div className="ds-card flex min-h-[220px] items-center justify-center p-4">
          <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
        </div>
      </section>
    );
  }

  return (
    <section className="space-y-4">
      <PageTitleWithTooltip title="API Keys" tooltip="Create, rotate, revoke, and inspect scoped API keys." />
      <p className="text-sm text-muted-foreground">Create, update, rotate, revoke, and drill down API key activity.</p>

      <div className="ds-card p-4">
        <p className="mb-3 text-sm font-semibold">Create API key</p>
        <div className="grid gap-2 lg:grid-cols-2">
          <Input
            value={createName}
            onChange={(event) => setCreateName(event.target.value)}
            placeholder="Key name"
            className="ds-input h-11 rounded-md px-3 text-sm md:h-9"
          />
          <Select
            value={createTeamId}
            onChange={(event) => setCreateTeamId(event.target.value)}
            className="ds-input h-11 rounded-md px-3 text-sm md:h-9"
          >
            <option value="">No team scope</option>
            {teams.map((team) => (
              <option key={`create-key-team-${team.id}`} value={String(team.id)}>
                Team #{team.id} - {team.name}
              </option>
            ))}
          </Select>
          <Input
            value={createMemo}
            onChange={(event) => setCreateMemo(event.target.value)}
            placeholder="Memo (optional)"
            className="ds-input h-11 rounded-md px-3 text-sm md:h-9"
          />
          <Input
            value={createTags}
            onChange={(event) => setCreateTags(event.target.value)}
            placeholder="Tags CSV (optional)"
            className="ds-input h-11 rounded-md px-3 text-sm md:h-9"
          />
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                type="button"
                variant="outline"
                className="ds-input h-11 w-full justify-between rounded-md px-3 text-sm md:h-9 lg:col-span-2"
              >
                <span className="truncate text-left">{toolsDropdownLabel(createAllowedTools)}</span>
                <ChevronsUpDown className="h-4 w-4 text-muted-foreground" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="start" className="max-h-72 w-[var(--radix-dropdown-menu-trigger-width)] overflow-y-auto">
              {toolOptions.length === 0 ? <p className="px-2 py-1 text-xs text-muted-foreground">No tool options</p> : null}
              {toolOptions.map((tool) => (
                <DropdownMenuCheckboxItem
                  key={`create-tool-${tool.tool_name}`}
                  checked={csvHasValue(createAllowedTools, tool.tool_name)}
                  onCheckedChange={(checked) => setCreateAllowedTools((prev) => updateCsvSelection(prev, tool.tool_name, checked === true))}
                  onSelect={(event) => event.preventDefault()}
                >
                  <span className="font-mono text-xs">{tool.tool_name}</span>
                </DropdownMenuCheckboxItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>
          <textarea
            value={createPolicyJson}
            onChange={(event) => setCreatePolicyJson(event.target.value)}
            placeholder='Policy JSON, e.g. {"allowed_services":["notion"]}'
            className="ds-input min-h-[120px] rounded-md px-3 py-2 text-xs font-mono lg:col-span-2"
          />
          <Button
            type="button"
            onClick={() => void handleCreateApiKey()}
            disabled={creating}
            className="ds-btn h-11 rounded-md px-3 text-sm disabled:cursor-not-allowed disabled:opacity-60 md:h-9 lg:col-span-2"
          >
            {creating ? "Creating..." : "Create API key"}
          </Button>
        </div>

        {createdApiKey ? (
          <div className="mt-3 rounded-md border border-chart-4/40 bg-chart-4/10 p-3">
            <p className="text-xs font-medium text-chart-4">Copy now. This key is shown only once.</p>
            <div className="mt-2 flex items-center gap-2">
              <code className="block flex-1 overflow-x-auto rounded bg-card px-2 py-1 text-xs">{createdApiKey}</code>
              <Button type="button" onClick={() => void copyApiKey()} className="ds-btn h-9 rounded-md px-3 text-xs">
                Copy
              </Button>
            </div>
          </div>
        ) : null}
      </div>

      {error ? (
        <div className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error}
        </div>
      ) : null}

      {!error ? (
        <div className="space-y-3">
          {items.map((item) => {
            const drilldown = drilldownById[item.id] ?? null;
            return (
              <article key={item.id} className="ds-card space-y-3 p-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <p className="text-sm font-semibold">{item.name}</p>
                    <p className="font-mono text-xs text-muted-foreground">{item.key_prefix}</p>
                  </div>
                  <StatusBadge kind="key" value={item.is_active ? "active" : "revoked"} />
                </div>

                <div className="grid gap-2 lg:grid-cols-2">
                  <Input
                    value={nameDraft[item.id] ?? ""}
                    onChange={(event) => setNameDraft((prev) => ({ ...prev, [item.id]: event.target.value }))}
                    className="ds-input h-11 rounded-md px-3 text-sm md:h-9"
                  />
                  <Select
                    value={teamDraft[item.id] ?? ""}
                    onChange={(event) => setTeamDraft((prev) => ({ ...prev, [item.id]: event.target.value }))}
                    className="ds-input h-11 rounded-md px-3 text-sm md:h-9"
                  >
                    <option value="">No team scope</option>
                    {teams.map((team) => (
                      <option key={`key-${item.id}-team-${team.id}`} value={String(team.id)}>
                        Team #{team.id} - {team.name}
                      </option>
                    ))}
                  </Select>
                  <Input
                    value={memoDraft[item.id] ?? ""}
                    onChange={(event) => setMemoDraft((prev) => ({ ...prev, [item.id]: event.target.value }))}
                    placeholder="Memo"
                    className="ds-input h-11 rounded-md px-3 text-sm md:h-9"
                  />
                  <Input
                    value={tagsDraft[item.id] ?? ""}
                    onChange={(event) => setTagsDraft((prev) => ({ ...prev, [item.id]: event.target.value }))}
                    placeholder="Tags CSV"
                    className="ds-input h-11 rounded-md px-3 text-sm md:h-9"
                  />
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <Button
                        type="button"
                        variant="outline"
                        className="ds-input h-11 w-full justify-between rounded-md px-3 text-sm md:h-9 lg:col-span-2"
                      >
                        <span className="truncate text-left">{toolsDropdownLabel(allowedToolsDraft[item.id] ?? "")}</span>
                        <ChevronsUpDown className="h-4 w-4 text-muted-foreground" />
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="start" className="max-h-72 w-[var(--radix-dropdown-menu-trigger-width)] overflow-y-auto">
                      {toolOptions.length === 0 ? <p className="px-2 py-1 text-xs text-muted-foreground">No tool options</p> : null}
                      {toolOptions.map((tool) => (
                        <DropdownMenuCheckboxItem
                          key={`edit-${item.id}-tool-${tool.tool_name}`}
                          checked={csvHasValue(allowedToolsDraft[item.id] ?? "", tool.tool_name)}
                          onCheckedChange={(checked) =>
                            setAllowedToolsDraft((prev) => ({
                              ...prev,
                              [item.id]: updateCsvSelection(prev[item.id] ?? "", tool.tool_name, checked === true),
                            }))
                          }
                          onSelect={(event) => event.preventDefault()}
                        >
                          <span className="font-mono text-xs">{tool.tool_name}</span>
                        </DropdownMenuCheckboxItem>
                      ))}
                    </DropdownMenuContent>
                  </DropdownMenu>
                  <textarea
                    value={policyDraft[item.id] ?? "{}"}
                    onChange={(event) => setPolicyDraft((prev) => ({ ...prev, [item.id]: event.target.value }))}
                    className="ds-input min-h-[120px] rounded-md px-3 py-2 text-xs font-mono lg:col-span-2"
                  />
                </div>

                <div className="flex flex-wrap items-center gap-2">
                  <Button
                    type="button"
                    onClick={() => void handleUpdateApiKey(item.id)}
                    disabled={updatingId === item.id}
                    className="ds-btn h-11 rounded-md px-3 text-xs disabled:cursor-not-allowed disabled:opacity-60 md:h-9"
                  >
                    {updatingId === item.id ? "Saving..." : "Save"}
                  </Button>
                  <Button
                    type="button"
                    onClick={() => void handleRotateApiKey(item.id)}
                    disabled={rotatingId === item.id || !item.is_active}
                    className="ds-btn h-11 rounded-md px-3 text-xs disabled:cursor-not-allowed disabled:opacity-60 md:h-9"
                  >
                    {rotatingId === item.id ? "Rotating..." : "Rotate"}
                  </Button>
                  <Button
                    type="button"
                    onClick={() => void handleRevokeApiKey(item.id)}
                    disabled={revokingId === item.id || !item.is_active}
                    className="ds-btn h-11 rounded-md px-3 text-xs disabled:cursor-not-allowed disabled:opacity-60 md:h-9"
                  >
                    {revokingId === item.id ? "Revoking..." : "Revoke"}
                  </Button>
                  <Button
                    type="button"
                    onClick={() => void handleLoadDrilldown(item.id)}
                    disabled={drilldownLoadingId === item.id}
                    className="ds-btn h-11 rounded-md px-3 text-xs disabled:cursor-not-allowed disabled:opacity-60 md:h-9"
                  >
                    {drilldownLoadingId === item.id ? "Loading..." : "Load 7d Drill-down"}
                  </Button>
                </div>

                <p className="text-xs text-muted-foreground">
                  created: {item.created_at ? new Date(item.created_at).toLocaleString() : "-"} · last used: {item.last_used_at ? new Date(item.last_used_at).toLocaleString() : "-"} · revoked: {item.revoked_at ? new Date(item.revoked_at).toLocaleString() : "-"}
                </p>

                {drilldown ? (
                  <div className="rounded-md border border-border p-3">
                    <p className="mb-2 text-sm font-medium">7-day Drill-down</p>
                    <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
                      <div className="rounded border border-border p-2 text-xs">Calls: {drilldown.summary.total_calls}</div>
                      <div className="rounded border border-border p-2 text-xs">Success: {drilldown.summary.success_count}</div>
                      <div className="rounded border border-border p-2 text-xs">Fail: {drilldown.summary.fail_count}</div>
                      <div className="rounded border border-border p-2 text-xs">P95: {drilldown.summary.p95_latency_ms} ms</div>
                    </div>

                    <div className="mt-3 grid gap-2 lg:grid-cols-2">
                      <div className="rounded border border-border p-2">
                        <p className="mb-1 text-xs font-medium">Top error codes</p>
                        {(drilldown.top_error_codes ?? []).length === 0 ? <p className="text-xs text-muted-foreground">No errors.</p> : null}
                        {(drilldown.top_error_codes ?? []).map((entry) => (
                          <p key={`err-${item.id}-${entry.error_code}`} className="text-xs">
                            {entry.error_code}: {entry.count}
                          </p>
                        ))}
                      </div>
                      <div className="rounded border border-border p-2">
                        <p className="mb-1 text-xs font-medium">Top tools</p>
                        {(drilldown.top_tools ?? []).length === 0 ? <p className="text-xs text-muted-foreground">No calls.</p> : null}
                        {(drilldown.top_tools ?? []).map((entry) => (
                          <p key={`tool-${item.id}-${entry.tool_name}`} className="text-xs">
                            {entry.tool_name}: {entry.count}
                          </p>
                        ))}
                      </div>
                    </div>

                    <div className="mt-3 overflow-x-auto rounded border border-border">
                      <Table className="min-w-[640px] text-xs">
                        <TableHeader className="bg-muted/60 text-left text-[11px] text-muted-foreground">
                          <TableRow>
                            <TableHead className="px-2 py-2">Day</TableHead>
                            <TableHead className="px-2 py-2">Calls</TableHead>
                            <TableHead className="px-2 py-2">Success</TableHead>
                            <TableHead className="px-2 py-2">Fail</TableHead>
                            <TableHead className="px-2 py-2">Success Rate</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {(drilldown.trend ?? []).map((row) => (
                            <TableRow key={`trend-${item.id}-${row.day}`} className="border-t border-border">
                              <TableCell className="px-2 py-2">{row.day}</TableCell>
                              <TableCell className="px-2 py-2">{row.calls}</TableCell>
                              <TableCell className="px-2 py-2">{row.success}</TableCell>
                              <TableCell className="px-2 py-2">{row.fail}</TableCell>
                              <TableCell className="px-2 py-2">{(row.success_rate * 100).toFixed(1)}%</TableCell>
                            </TableRow>
                          ))}
                          {(drilldown.trend ?? []).length === 0 ? (
                            <TableRow>
                              <TableCell className="px-2 py-3 text-muted-foreground" colSpan={5}>
                                No trend rows.
                              </TableCell>
                            </TableRow>
                          ) : null}
                        </TableBody>
                      </Table>
                    </div>
                  </div>
                ) : null}
              </article>
            );
          })}

          {items.length === 0 ? <p className="text-sm text-muted-foreground">No API keys found.</p> : null}
        </div>
      ) : null}
    </section>
  );
}
