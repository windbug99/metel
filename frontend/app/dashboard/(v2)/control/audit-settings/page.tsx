"use client";

import { Select } from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useCallback, useEffect, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Loader2 } from "lucide-react";

import { buildNextPath, dashboardApiGet, dashboardApiRequest } from "../../../../../lib/dashboard-v2-client";
import { resolveDashboardScope } from "../../../../../lib/dashboard-scope";
import { supabase } from "../../../../../lib/supabase";
import AlertBanner from "../../../../../components/dashboard-v2/alert-banner";
import PageTitleWithTooltip from "@/components/dashboard-v2/page-title-with-tooltip";

type PermissionSnapshot = {
  permissions?: {
    can_read_audit_settings?: boolean;
    can_update_audit_settings?: boolean;
  };
};

type AuditSettings = {
  retention_days: number;
  export_enabled: boolean;
  masking_policy: Record<string, unknown>;
  updated_at?: string | null;
};

type TeamItem = {
  id: number;
  name: string;
};

const RECOMMENDED_MASK_KEYS = ["token", "access_token", "authorization", "password", "secret"];
const SAMPLE_AUDIT_PAYLOAD = {
  actor: {
    user_id: "9f8e7d6c-1234-4abc-9def-000000000001",
    email: "owner@example.com",
  },
  request: {
    authorization: "Bearer eyJhbGciOi...",
    ip: "203.0.113.10",
  },
  integration: {
    token: "xoxb-1234-secret-token",
    access_token: "ghp_example_access_token",
  },
  credentials: {
    password: "plain-text-password",
    secret: "internal-secret-value",
  },
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

function normalizeMaskKeys(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  const deduped = new Set<string>();
  for (const item of value) {
    const key = String(item ?? "").trim().toLowerCase();
    if (key) {
      deduped.add(key);
    }
  }
  return Array.from(deduped);
}

function applyMaskPolicy(value: unknown, maskKeys: Set<string>): unknown {
  if (Array.isArray(value)) {
    return value.map((item) => applyMaskPolicy(item, maskKeys));
  }
  if (value && typeof value === "object") {
    const next: Record<string, unknown> = {};
    for (const [key, fieldValue] of Object.entries(value as Record<string, unknown>)) {
      if (maskKeys.has(key.toLowerCase())) {
        next[key] = "***";
      } else {
        next[key] = applyMaskPolicy(fieldValue, maskKeys);
      }
    }
    return next;
  }
  return value;
}

export default function DashboardAuditSettingsPage() {
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();
  const scopeState = resolveDashboardScope(searchParams);
  const isUserScope = scopeState.scope === "user";
  const isOrgScope = scopeState.scope === "org";
  const isTeamScope = scopeState.scope === "team";

  const [canReadSettings, setCanReadSettings] = useState(false);
  const [canUpdateSettings, setCanUpdateSettings] = useState(false);

  const [settings, setSettings] = useState<AuditSettings | null>(null);
  const [retentionDraft, setRetentionDraft] = useState("90");
  const [exportEnabledDraft, setExportEnabledDraft] = useState(false);
  const [maskingPolicyDraft, setMaskingPolicyDraft] = useState("{}");
  const [maskingPolicyBaseDraft, setMaskingPolicyBaseDraft] = useState<Record<string, unknown>>({});
  const [maskKeysDraft, setMaskKeysDraft] = useState<string[]>([]);
  const [maskKeyInputDraft, setMaskKeyInputDraft] = useState("");
  const [maskingEditorMode, setMaskingEditorMode] = useState<"basic" | "advanced">("basic");

  const [teams, setTeams] = useState<TeamItem[]>([]);
  const [teamFilter, setTeamFilter] = useState("");

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [exporting, setExporting] = useState<"jsonl" | "csv" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const handle401 = useCallback(() => {
    const next = encodeURIComponent(buildNextPath(pathname, window.location.search));
    router.replace(`/?next=${next}`);
  }, [pathname, router]);

  const getAuthHeaders = useCallback(async (): Promise<HeadersInit | null> => {
    const {
      data: { session },
    } = await supabase.auth.getSession();
    const accessToken = session?.access_token;
    if (!accessToken) {
      handle401();
      return null;
    }
    return { Authorization: `Bearer ${accessToken}` };
  }, [handle401]);

  const fetchScopeOptions = useCallback(async () => {
    if (!isOrgScope || scopeState.organizationId === null) {
      setTeams([]);
      return;
    }
    const teamRes = await dashboardApiGet<{ items?: TeamItem[] }>(`/api/teams?organization_id=${scopeState.organizationId}`);

    if (teamRes.status === 401) {
      handle401();
      return;
    }

    if (teamRes.ok && teamRes.data) {
      setTeams(Array.isArray(teamRes.data.items) ? teamRes.data.items : []);
    } else {
      setTeams([]);
    }
  }, [handle401, isOrgScope, scopeState.organizationId]);

  const fetchAuditSettings = useCallback(async () => {
    setLoading(true);
    setError(null);
    if (isUserScope) {
      setCanReadSettings(false);
      setCanUpdateSettings(false);
      setSettings(null);
      setLoading(false);
      return;
    }

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

    const canRead = Boolean(permissionsRes.data.permissions?.can_read_audit_settings);
    const canUpdate = Boolean(permissionsRes.data.permissions?.can_update_audit_settings) && isOrgScope;
    setCanReadSettings(canRead);
    setCanUpdateSettings(canUpdate);

    await fetchScopeOptions();

    if (!canRead) {
      setSettings(null);
      setLoading(false);
      return;
    }

    const settingsRes = await dashboardApiGet<AuditSettings>("/api/audit/settings");
    if (settingsRes.status === 401) {
      handle401();
      setLoading(false);
      return;
    }
    if (settingsRes.status === 403) {
      setError("Access denied while loading audit settings.");
      setLoading(false);
      return;
    }
    if (!settingsRes.ok || !settingsRes.data) {
      setError(settingsRes.error ?? "Failed to load audit settings.");
      setLoading(false);
      return;
    }

    setSettings(settingsRes.data);
    setRetentionDraft(String(settingsRes.data.retention_days ?? 90));
    setExportEnabledDraft(Boolean(settingsRes.data.export_enabled));
    const nextPolicy = (settingsRes.data.masking_policy ?? {}) as Record<string, unknown>;
    setMaskingPolicyBaseDraft(nextPolicy);
    setMaskKeysDraft(normalizeMaskKeys(nextPolicy.mask_keys));
    setMaskingPolicyDraft(JSON.stringify(nextPolicy, null, 2));
    setLoading(false);
  }, [fetchScopeOptions, handle401, isOrgScope, isUserScope]);

  const addMaskKey = useCallback(() => {
    const next = String(maskKeyInputDraft || "").trim().toLowerCase();
    if (!next) {
      return;
    }
    setMaskKeysDraft((prev) => (prev.includes(next) ? prev : [...prev, next]));
    setMaskKeyInputDraft("");
  }, [maskKeyInputDraft]);

  const removeMaskKey = useCallback((key: string) => {
    setMaskKeysDraft((prev) => prev.filter((item) => item !== key));
  }, []);

  const handleSave = useCallback(async () => {
    setSaving(true);
    setError(null);
    setMessage(null);

    const retention = Number(retentionDraft);
    if (!Number.isFinite(retention) || retention < 1) {
      setError("Retention days must be 1 or greater.");
      setSaving(false);
      return;
    }

    let maskingPolicy: Record<string, unknown> = {};
    if (maskingEditorMode === "advanced") {
      try {
        maskingPolicy = JSON.parse(maskingPolicyDraft) as Record<string, unknown>;
      } catch {
        setError("Masking policy JSON is invalid.");
        setSaving(false);
        return;
      }
    } else {
      maskingPolicy = {
        ...maskingPolicyBaseDraft,
        mask_keys: normalizeMaskKeys(maskKeysDraft),
      };
    }

    const response = await dashboardApiRequest<AuditSettings>("/api/audit/settings", {
      method: "PATCH",
      body: {
        retention_days: retention,
        export_enabled: exportEnabledDraft,
        masking_policy: maskingPolicy,
      },
    });

    if (response.status === 401) {
      handle401();
      setSaving(false);
      return;
    }
    if (response.status === 403) {
      setError("Owner role required to update audit settings.");
      setSaving(false);
      return;
    }
    if (!response.ok) {
      setError(response.error ?? "Failed to save audit settings.");
      setSaving(false);
      return;
    }

    await fetchAuditSettings();
    setMessage("Audit settings saved.");
    setSaving(false);
  }, [exportEnabledDraft, fetchAuditSettings, handle401, maskKeysDraft, maskingEditorMode, maskingPolicyBaseDraft, maskingPolicyDraft, retentionDraft]);

  const handleExport = useCallback(
    async (format: "jsonl" | "csv") => {
      setExporting(format);
      setError(null);
      setMessage(null);

      const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL;
      if (!apiBaseUrl) {
        setError("NEXT_PUBLIC_API_BASE_URL is not configured.");
        setExporting(null);
        return;
      }

      const headers = await getAuthHeaders();
      if (!headers) {
        setExporting(null);
        return;
      }

      try {
        const query = new URLSearchParams({ format, limit: "500" });
        if (scopeState.organizationId !== null) {
          query.set("organization_id", String(scopeState.organizationId));
        }
        if (isTeamScope && scopeState.teamId !== null) {
          query.set("team_id", String(scopeState.teamId));
        } else if (isOrgScope && teamFilter) {
          query.set("team_id", teamFilter);
        }

        const response = await fetch(`${apiBaseUrl}/api/audit/export?${query.toString()}`, {
          method: "GET",
          headers,
        });

        if (response.status === 401) {
          handle401();
          setExporting(null);
          return;
        }
        if (response.status === 403) {
          setError("Access denied while exporting audit events.");
          setExporting(null);
          return;
        }
        if (!response.ok) {
          setError(`Failed to export audit events (status ${response.status}).`);
          setExporting(null);
          return;
        }

        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const anchor = document.createElement("a");
        anchor.href = url;
        anchor.download = format === "csv" ? "audit-events.csv" : "audit-events.jsonl";
        document.body.appendChild(anchor);
        anchor.click();
        anchor.remove();
        window.URL.revokeObjectURL(url);
        setMessage(`Audit ${format.toUpperCase()} export completed.`);
      } catch {
        setError("Failed to export audit events.");
      } finally {
        setExporting(null);
      }
    },
    [getAuthHeaders, handle401, isOrgScope, isTeamScope, scopeState.organizationId, scopeState.teamId, teamFilter]
  );

  useEffect(() => {
    void fetchAuditSettings();
  }, [fetchAuditSettings]);

  useEffect(() => {
    if (isTeamScope && scopeState.teamId !== null) {
      setTeamFilter(String(scopeState.teamId));
      return;
    }
    if (!isOrgScope) {
      setTeamFilter("");
    }
  }, [isOrgScope, isTeamScope, scopeState.teamId]);

  useEffect(() => {
    const handler = (event: Event) => {
      const custom = event as CustomEvent<{ path?: string }>;
      if (custom.detail?.path === pathname) {
        void fetchAuditSettings();
      }
    };
    window.addEventListener("dashboard:v2:refresh", handler as EventListener);
    return () => {
      window.removeEventListener("dashboard:v2:refresh", handler as EventListener);
    };
  }, [fetchAuditSettings, pathname]);

  return (
    <section className="space-y-4">
      <PageTitleWithTooltip
        title="Audit Settings"
        tooltip="Configure retention and export policy, masking rules, and download audit exports."
      />
      <p className="text-sm text-muted-foreground">
        {isUserScope
          ? "Audit governance is managed at organization scope."
          : isTeamScope
          ? "Team scope provides read/export under organization governance."
          : "Manage retention, export policy, masking JSON, and audit export downloads."}
      </p>

      {error ? <AlertBanner message={error} tone="danger" /> : null}
      {message ? <p className="text-sm text-chart-2">{message}</p> : null}

      {loading ? (
        <div className="ds-card flex min-h-[220px] items-center justify-center p-4">
          <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
        </div>
      ) : null}

      {!loading && isUserScope ? (
        <div className="ds-card p-4">
          <p className="text-sm text-muted-foreground">Switch to organization scope to view audit governance settings.</p>
        </div>
      ) : null}

      {!loading && !isUserScope && !canReadSettings ? (
        <div className="ds-card p-4">
          <p className="text-sm text-muted-foreground">Your role does not have permission to read audit settings.</p>
        </div>
      ) : null}

      {!loading && !isUserScope && canReadSettings ? (
        <>
          <div className="ds-card p-4">
            <p className="mb-3 text-sm font-semibold">Settings</p>
            <div className="flex flex-wrap items-center gap-2">
              <label className="text-sm text-muted-foreground">Retention days</label>
              <Input
                type="number"
                min={1}
                value={retentionDraft}
                onChange={(event) => setRetentionDraft(event.target.value)}
                disabled={!canUpdateSettings}
                className="ds-input h-11 w-28 rounded-md px-3 text-sm md:h-9"
              />
              <label className="inline-flex items-center gap-2 text-sm text-muted-foreground">
                <Checkbox
                  checked={exportEnabledDraft}
                  onCheckedChange={setExportEnabledDraft}
                  disabled={!canUpdateSettings}
                />
                Export enabled
              </label>
              <Button
                type="button"
                onClick={() => void handleSave()}
                disabled={!canUpdateSettings || saving}
                className="ds-btn h-11 rounded-md px-3 text-sm disabled:cursor-not-allowed disabled:opacity-60 md:h-9"
              >
                {saving ? "Saving..." : "Save Settings"}
              </Button>
            </div>

            <div className="mt-3 rounded-md border border-border p-3">
              <div className="mb-2 flex items-center justify-between gap-2">
                <p className="text-sm font-medium">Masking Policy</p>
                <Tabs
                  value={maskingEditorMode}
                  onValueChange={(value) => setMaskingEditorMode(value as "basic" | "advanced")}
                >
                  <TabsList className="h-8">
                    <TabsTrigger value="basic" className="h-7 px-2 text-xs">Basic</TabsTrigger>
                    <TabsTrigger value="advanced" className="h-7 px-2 text-xs">Advanced JSON</TabsTrigger>
                  </TabsList>
                </Tabs>
              </div>

              {maskingEditorMode === "basic" ? (
                <div className="space-y-3">
                  <p className="text-xs text-muted-foreground">
                    Add keys that should be masked in audit payloads. Example: token, password, secret.
                  </p>
                  <div className="flex flex-wrap items-center gap-2">
                    <Input
                      value={maskKeyInputDraft}
                      onChange={(event) => setMaskKeyInputDraft(event.target.value)}
                      onKeyDown={(event) => {
                        if (event.key === "Enter") {
                          event.preventDefault();
                          addMaskKey();
                        }
                      }}
                      disabled={!canUpdateSettings}
                      placeholder="Add mask key (e.g. api_key)"
                      className="ds-input h-10 min-w-[240px] flex-1 rounded-md px-3 text-sm"
                    />
                    <Button
                      type="button"
                      onClick={addMaskKey}
                      disabled={!canUpdateSettings}
                      className="ds-btn h-10 rounded-md px-3 text-xs disabled:opacity-60"
                    >
                      Add key
                    </Button>
                    <Button
                      type="button"
                      onClick={() => setMaskKeysDraft(RECOMMENDED_MASK_KEYS)}
                      disabled={!canUpdateSettings}
                      className="h-10 rounded-md border border-border bg-card px-3 text-xs text-foreground hover:bg-accent"
                    >
                      Use recommended keys
                    </Button>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {maskKeysDraft.length === 0 ? <p className="text-xs text-muted-foreground">No mask keys added.</p> : null}
                    {maskKeysDraft.map((key) => (
                      <span key={`mask-key-${key}`} className="inline-flex items-center gap-1 rounded-full border border-border px-2 py-1 text-xs">
                        {key}
                        {canUpdateSettings ? (
                          <button
                            type="button"
                            onClick={() => removeMaskKey(key)}
                            className="text-muted-foreground hover:text-foreground"
                            aria-label={`Remove ${key}`}
                          >
                            x
                          </button>
                        ) : null}
                      </span>
                    ))}
                  </div>
                  <div className="grid gap-2 lg:grid-cols-2">
                    <div className="rounded-md border border-border p-2">
                      <p className="mb-1 text-xs font-medium text-muted-foreground">Preview (before masking)</p>
                      <pre className="overflow-x-auto text-[11px] text-muted-foreground">
                        {JSON.stringify(SAMPLE_AUDIT_PAYLOAD, null, 2)}
                      </pre>
                    </div>
                    <div className="rounded-md border border-border p-2">
                      <p className="mb-1 text-xs font-medium text-muted-foreground">Preview (after masking)</p>
                      <pre className="overflow-x-auto text-[11px] text-muted-foreground">
                        {JSON.stringify(applyMaskPolicy(SAMPLE_AUDIT_PAYLOAD, new Set(normalizeMaskKeys(maskKeysDraft))), null, 2)}
                      </pre>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="space-y-2">
                  <p className="text-xs text-muted-foreground">
                    Advanced mode accepts raw JSON. Use when you need custom policy fields beyond mask_keys.
                  </p>
                  <textarea
                    value={maskingPolicyDraft}
                    onChange={(event) => setMaskingPolicyDraft(event.target.value)}
                    disabled={!canUpdateSettings}
                    className="ds-input min-h-[140px] w-full rounded-md px-3 py-2 text-sm font-mono"
                    placeholder='{"mask_keys":["token","secret"]}'
                  />
                </div>
              )}
            </div>

            {!canUpdateSettings ? <p className="mt-2 text-xs text-muted-foreground">Audit settings update is organization owner-only (team scope is read-only).</p> : null}
            <p className="mt-2 text-xs text-muted-foreground">updated_at: {asDate(settings?.updated_at)}</p>
          </div>

          <div className="ds-card p-4">
            <p className="mb-3 text-sm font-semibold">Audit Export (JSONL/CSV)</p>
            <div className="flex flex-wrap items-center gap-2">
              {isOrgScope ? (
                <Select
                  value={teamFilter}
                  onChange={(event) => setTeamFilter(event.target.value)}
                  className="ds-input h-11 rounded-md px-3 text-sm md:h-9"
                >
                  <option value="">All teams in org</option>
                  {teams.map((team) => (
                    <option key={`audit-export-team-${team.id}`} value={String(team.id)}>
                      Team #{team.id} - {team.name}
                    </option>
                  ))}
                </Select>
              ) : null}

              <Button
                type="button"
                onClick={() => void handleExport("jsonl")}
                disabled={exporting !== null}
                className="ds-btn h-11 rounded-md px-3 text-sm disabled:cursor-not-allowed disabled:opacity-60 md:h-9"
              >
                {exporting === "jsonl" ? "Exporting..." : "Export JSONL"}
              </Button>
              <Button
                type="button"
                onClick={() => void handleExport("csv")}
                disabled={exporting !== null}
                className="ds-btn h-11 rounded-md px-3 text-sm disabled:cursor-not-allowed disabled:opacity-60 md:h-9"
              >
                {exporting === "csv" ? "Exporting..." : "Export CSV"}
              </Button>
            </div>
          </div>
        </>
      ) : null}
    </section>
  );
}
