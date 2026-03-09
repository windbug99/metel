"use client";

import { Select } from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
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
    setMaskingPolicyDraft(JSON.stringify(settingsRes.data.masking_policy ?? {}, null, 2));
    setLoading(false);
  }, [fetchScopeOptions, handle401, isOrgScope, isUserScope]);

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
    try {
      maskingPolicy = JSON.parse(maskingPolicyDraft) as Record<string, unknown>;
    } catch {
      setError("Masking policy JSON is invalid.");
      setSaving(false);
      return;
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
  }, [exportEnabledDraft, fetchAuditSettings, handle401, maskingPolicyDraft, retentionDraft]);

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

            <textarea
              value={maskingPolicyDraft}
              onChange={(event) => setMaskingPolicyDraft(event.target.value)}
              disabled={!canUpdateSettings}
              className="ds-input mt-3 min-h-[140px] w-full rounded-md px-3 py-2 text-sm font-mono"
              placeholder='Masking policy JSON, e.g. {"mask_keys":["token","secret"]}'
            />

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
