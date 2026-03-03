"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import { supabase } from "../../lib/supabase";
import { detectBrowserTimezone, updateUserTimezone, upsertUserProfile } from "../../lib/profile";

type UserProfile = {
  id: string;
  email: string | null;
  full_name: string | null;
  created_at: string;
  timezone: string | null;
} | null;

type OAuthStatus = {
  connected: boolean;
  integration?: {
    workspace_name: string | null;
    workspace_id: string | null;
    updated_at: string | null;
  } | null;
} | null;

type ApiKeyItem = {
  id: number;
  name: string;
  key_prefix: string;
  allowed_tools?: string[] | null;
  is_active: boolean;
  last_used_at: string | null;
  created_at: string;
  revoked_at: string | null;
};

type ToolCallItem = {
  id: number;
  tool_name: string;
  status: "success" | "fail";
  error_code: string | null;
  latency_ms: number;
  created_at: string;
  api_key: {
    id: number | null;
    name: string | null;
    key_prefix: string | null;
  };
};

type ToolCallSummary = {
  recent_success: number;
  recent_fail: number;
  calls_24h: number;
  success_24h: number;
  fail_24h: number;
  fail_rate_24h: number;
  blocked_rate_24h: number;
  retryable_fail_rate_24h: number;
  policy_blocked_24h: number;
  quota_exceeded_24h: number;
  access_denied_24h: number;
  high_risk_allowed_24h: number;
  policy_override_usage_24h: number;
  resolve_fail_24h: number;
  upstream_temporary_24h: number;
  top_failure_codes: Array<{
    error_code: string;
    count: number;
  }>;
};

type AuditEventItem = {
  id: number;
  request_id: string | null;
  timestamp: string;
  action: {
    tool_name: string;
  };
  actor: {
    user_id: string;
    api_key: {
      id: number | null;
      name: string | null;
      key_prefix: string | null;
    };
  };
  outcome: {
    decision: "allowed" | "policy_blocked" | "access_denied" | "failed";
    status: "success" | "fail";
    error_code: string | null;
    latency_ms: number | null;
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

function ServiceLogo({ src, alt }: { src: string; alt: string }) {
  return <img src={src} alt={alt} width={20} height={20} className="h-5 w-5 rounded-sm object-contain" />;
}

export default function DashboardPage() {
  const router = useRouter();
  const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL;

  const [loading, setLoading] = useState(true);
  const [loggingOut, setLoggingOut] = useState(false);

  const [profile, setProfile] = useState<UserProfile>(null);
  const [timezoneDraft, setTimezoneDraft] = useState("UTC");
  const [timezoneSaving, setTimezoneSaving] = useState(false);
  const [timezoneMessage, setTimezoneMessage] = useState<string | null>(null);

  const [notionStatus, setNotionStatus] = useState<OAuthStatus>(null);
  const [linearStatus, setLinearStatus] = useState<OAuthStatus>(null);

  const [notionError, setNotionError] = useState<string | null>(null);
  const [linearError, setLinearError] = useState<string | null>(null);

  const [notionBusy, setNotionBusy] = useState(false);
  const [linearBusy, setLinearBusy] = useState(false);
  const [apiKeys, setApiKeys] = useState<ApiKeyItem[]>([]);
  const [apiKeysLoading, setApiKeysLoading] = useState(false);
  const [apiKeysError, setApiKeysError] = useState<string | null>(null);
  const [creatingApiKey, setCreatingApiKey] = useState(false);
  const [newApiKeyName, setNewApiKeyName] = useState("default");
  const [newApiKeyAllowedTools, setNewApiKeyAllowedTools] = useState("");
  const [createdApiKey, setCreatedApiKey] = useState<string | null>(null);
  const [revokingApiKeyId, setRevokingApiKeyId] = useState<number | null>(null);
  const [updatingApiKeyId, setUpdatingApiKeyId] = useState<number | null>(null);
  const [apiKeyAllowedDraft, setApiKeyAllowedDraft] = useState<Record<number, string>>({});
  const [toolCalls, setToolCalls] = useState<ToolCallItem[]>([]);
  const [toolCallsSummary, setToolCallsSummary] = useState<ToolCallSummary | null>(null);
  const [toolCallsLoading, setToolCallsLoading] = useState(false);
  const [toolCallsError, setToolCallsError] = useState<string | null>(null);
  const [toolCallStatusFilter, setToolCallStatusFilter] = useState<"all" | "success" | "fail">("all");
  const [toolCallNameFilter, setToolCallNameFilter] = useState("");
  const [toolCallFromFilter, setToolCallFromFilter] = useState("");
  const [toolCallToFilter, setToolCallToFilter] = useState("");
  const [auditEvents, setAuditEvents] = useState<AuditEventItem[]>([]);
  const [auditSummary, setAuditSummary] = useState<AuditSummary | null>(null);
  const [auditLoading, setAuditLoading] = useState(false);
  const [auditError, setAuditError] = useState<string | null>(null);

  const browserTimezone = useMemo(() => detectBrowserTimezone(), []);

  const timezoneOptions = useMemo(() => {
    try {
      const supported = Intl.supportedValuesOf?.("timeZone");
      if (Array.isArray(supported) && supported.length > 0) {
        return supported;
      }
    } catch {
      // ignore
    }
    return ["UTC", "Asia/Seoul", "America/Los_Angeles", "America/New_York", "Europe/London"];
  }, []);

  const getAuthHeaders = useCallback(async () => {
    const {
      data: { session }
    } = await supabase.auth.getSession();

    const accessToken = session?.access_token;
    if (!accessToken) {
      throw new Error("No active login session was found.");
    }

    return { Authorization: `Bearer ${accessToken}` };
  }, []);

  const fetchUserProfile = useCallback(async () => {
    const {
      data: { user }
    } = await supabase.auth.getUser();
    if (!user) {
      return null;
    }

    const { data } = await supabase
      .from("users")
      .select("id, email, full_name, created_at, timezone")
      .eq("id", user.id)
      .maybeSingle();

    return (data as UserProfile) ?? null;
  }, []);

  const fetchOAuthStatus = useCallback(
    async (provider: "notion" | "linear") => {
      if (!apiBaseUrl) {
        return;
      }
      const headers = await getAuthHeaders();
      const response = await fetch(`${apiBaseUrl}/api/oauth/${provider}/status`, { headers });
      if (!response.ok) {
        throw new Error(`failed_${provider}_status`);
      }
      return (await response.json()) as OAuthStatus;
    },
    [apiBaseUrl, getAuthHeaders]
  );

  const refreshStatuses = useCallback(async () => {
    try {
      const [notion, linear] = await Promise.all([
        fetchOAuthStatus("notion"),
        fetchOAuthStatus("linear")
      ]);
      setNotionStatus(notion ?? null);
      setLinearStatus(linear ?? null);
      setNotionError(null);
      setLinearError(null);
    } catch {
      setNotionError("Failed to load status.");
      setLinearError("Failed to load status.");
    }
  }, [fetchOAuthStatus]);

  const fetchApiKeys = useCallback(async () => {
    if (!apiBaseUrl) {
      return;
    }
    setApiKeysLoading(true);
    try {
      const headers = await getAuthHeaders();
      const response = await fetch(`${apiBaseUrl}/api/api-keys`, { headers });
      if (!response.ok) {
        throw new Error("failed_api_keys_list");
      }
      const payload = (await response.json()) as { items?: ApiKeyItem[] };
      const items = Array.isArray(payload.items) ? payload.items : [];
      setApiKeys(items);
      setApiKeyAllowedDraft((prev) => {
        const next = { ...prev };
        for (const item of items) {
          if (next[item.id] !== undefined) {
            continue;
          }
          next[item.id] = (item.allowed_tools ?? []).join(", ");
        }
        return next;
      });
      setApiKeysError(null);
    } catch {
      setApiKeysError("Failed to load API keys.");
    } finally {
      setApiKeysLoading(false);
    }
  }, [apiBaseUrl, getAuthHeaders]);

  const fetchToolCalls = useCallback(async () => {
    if (!apiBaseUrl) {
      return;
    }
    setToolCallsLoading(true);
    try {
      const headers = await getAuthHeaders();
      const query = new URLSearchParams({
        limit: "20",
        status: toolCallStatusFilter,
      });
      if (toolCallNameFilter.trim()) {
        query.set("tool_name", toolCallNameFilter.trim());
      }
      if (toolCallFromFilter) {
        query.set("from", new Date(toolCallFromFilter).toISOString());
      }
      if (toolCallToFilter) {
        query.set("to", new Date(toolCallToFilter).toISOString());
      }
      const response = await fetch(`${apiBaseUrl}/api/tool-calls?${query.toString()}`, { headers });
      if (!response.ok) {
        throw new Error("failed_tool_calls_list");
      }
      const payload = (await response.json()) as {
        items?: ToolCallItem[];
        summary?: ToolCallSummary;
      };
      setToolCalls(Array.isArray(payload.items) ? payload.items : []);
      setToolCallsSummary(payload.summary ?? null);
      setToolCallsError(null);
    } catch {
      setToolCallsError("Failed to load tool call usage.");
    } finally {
      setToolCallsLoading(false);
    }
  }, [apiBaseUrl, getAuthHeaders, toolCallFromFilter, toolCallNameFilter, toolCallStatusFilter, toolCallToFilter]);

  const fetchAuditEvents = useCallback(async () => {
    if (!apiBaseUrl) {
      return;
    }
    setAuditLoading(true);
    try {
      const headers = await getAuthHeaders();
      const query = new URLSearchParams({ limit: "20" });
      const response = await fetch(`${apiBaseUrl}/api/audit/events?${query.toString()}`, { headers });
      if (!response.ok) {
        throw new Error("failed_audit_events_list");
      }
      const payload = (await response.json()) as { items?: AuditEventItem[]; summary?: AuditSummary };
      setAuditEvents(Array.isArray(payload.items) ? payload.items : []);
      setAuditSummary(payload.summary ?? null);
      setAuditError(null);
    } catch {
      setAuditError("Failed to load audit events.");
    } finally {
      setAuditLoading(false);
    }
  }, [apiBaseUrl, getAuthHeaders]);

  useEffect(() => {
    let mounted = true;

    const bootstrap = async () => {
      const {
        data: { session }
      } = await supabase.auth.getSession();

      if (!session) {
        router.replace("/");
        return;
      }

      const { data: userData } = await supabase.auth.getUser();
      const user = userData.user;
      if (!user) {
        router.replace("/");
        return;
      }

      const upsertResult = await upsertUserProfile();
      if (upsertResult.error) {
        throw upsertResult.error;
      }
      const profileData = await fetchUserProfile();

      if (!mounted) {
        return;
      }

      setProfile(profileData);
      setTimezoneDraft(profileData?.timezone ?? browserTimezone);

      await Promise.all([refreshStatuses(), fetchApiKeys(), fetchToolCalls(), fetchAuditEvents()]);
      setLoading(false);
    };

    void bootstrap();

    return () => {
      mounted = false;
    };
  }, [browserTimezone, fetchApiKeys, fetchToolCalls, fetchAuditEvents, fetchUserProfile, refreshStatuses, router]);

  const handleOAuthStart = async (provider: "notion" | "linear") => {
    if (!apiBaseUrl) {
      return;
    }

    const setBusy = provider === "notion" ? setNotionBusy : setLinearBusy;
    setBusy(true);

    try {
      const headers = await getAuthHeaders();
      const response = await fetch(`${apiBaseUrl}/api/oauth/${provider}/start`, {
        method: "POST",
        headers
      });

      const payload = (await response.json()) as { auth_url?: string };
      if (!response.ok || !payload.auth_url) {
        throw new Error(`failed_${provider}_start`);
      }
      window.location.href = payload.auth_url;
    } catch {
      const setError = provider === "notion" ? setNotionError : setLinearError;
      setError("Failed to start OAuth flow.");
    } finally {
      setBusy(false);
    }
  };

  const handleDisconnect = async (provider: "notion" | "linear") => {
    if (!apiBaseUrl) {
      return;
    }

    const setBusy = provider === "notion" ? setNotionBusy : setLinearBusy;
    setBusy(true);

    try {
      const headers = await getAuthHeaders();
      const response = await fetch(`${apiBaseUrl}/api/oauth/${provider}/disconnect`, {
        method: "DELETE",
        headers
      });

      if (!response.ok) {
        throw new Error(`failed_${provider}_disconnect`);
      }

      await refreshStatuses();
    } catch {
      const setError = provider === "notion" ? setNotionError : setLinearError;
      setError("Failed to disconnect OAuth.");
    } finally {
      setBusy(false);
    }
  };

  const handleSaveTimezone = async () => {
    if (!profile) {
      return;
    }

    setTimezoneSaving(true);
    setTimezoneMessage(null);
    try {
      const result = await updateUserTimezone(timezoneDraft);
      if (result.error) {
        throw result.error;
      }
      setProfile((prev) => (prev ? { ...prev, timezone: timezoneDraft } : prev));
      setTimezoneMessage("Timezone saved.");
    } catch {
      setTimezoneMessage("Failed to save timezone.");
    } finally {
      setTimezoneSaving(false);
    }
  };

  const handleCreateApiKey = async () => {
    if (!apiBaseUrl) {
      return;
    }

    setCreatingApiKey(true);
    setCreatedApiKey(null);
    try {
      const headers = await getAuthHeaders();
      const allowedTools = newApiKeyAllowedTools
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean);
      const response = await fetch(`${apiBaseUrl}/api/api-keys`, {
        method: "POST",
        headers: { ...headers, "Content-Type": "application/json" },
        body: JSON.stringify({
          name: newApiKeyName.trim() || "default",
          allowed_tools: allowedTools.length > 0 ? allowedTools : null,
        })
      });
      if (!response.ok) {
        throw new Error("failed_create_api_key");
      }
      const payload = (await response.json()) as { api_key?: string };
      setCreatedApiKey(payload.api_key ?? null);
      await Promise.all([fetchApiKeys(), fetchToolCalls(), fetchAuditEvents()]);
    } catch {
      setApiKeysError("Failed to create API key.");
    } finally {
      setCreatingApiKey(false);
    }
  };

  const handleRevokeApiKey = async (id: number) => {
    if (!apiBaseUrl) {
      return;
    }
    setRevokingApiKeyId(id);
    try {
      const headers = await getAuthHeaders();
      const response = await fetch(`${apiBaseUrl}/api/api-keys/${id}`, {
        method: "DELETE",
        headers
      });
      if (!response.ok) {
        throw new Error("failed_revoke_api_key");
      }
      await Promise.all([fetchApiKeys(), fetchToolCalls(), fetchAuditEvents()]);
    } catch {
      setApiKeysError("Failed to revoke API key.");
    } finally {
      setRevokingApiKeyId(null);
    }
  };

  const handleUpdateApiKeyAllowedTools = async (id: number) => {
    if (!apiBaseUrl) {
      return;
    }
    setUpdatingApiKeyId(id);
    try {
      const headers = await getAuthHeaders();
      const raw = apiKeyAllowedDraft[id] ?? "";
      const allowedTools = raw
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean);
      const response = await fetch(`${apiBaseUrl}/api/api-keys/${id}`, {
        method: "PATCH",
        headers: { ...headers, "Content-Type": "application/json" },
        body: JSON.stringify({
          allowed_tools: allowedTools.length > 0 ? allowedTools : null,
        }),
      });
      if (!response.ok) {
        throw new Error("failed_update_api_key");
      }
      await fetchApiKeys();
    } catch {
      setApiKeysError("Failed to update API key allowed tools.");
    } finally {
      setUpdatingApiKeyId(null);
    }
  };

  const copyText = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      // ignore clipboard errors in unsupported environments
    }
  };

  const handleLogout = async () => {
    setLoggingOut(true);
    await supabase.auth.signOut();
    router.replace("/");
    setLoggingOut(false);
  };

  if (loading) {
    return <main className="mx-auto max-w-5xl p-8">Loading dashboard...</main>;
  }

  return (
    <main className="mx-auto max-w-5xl p-8">
      <header className="mb-8 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-gray-900">Dashboard</h1>
          <p className="text-sm text-gray-600">OAuth connections and profile settings for MCP Gateway.</p>
        </div>
        <button
          type="button"
          onClick={handleLogout}
          disabled={loggingOut}
          className="rounded-md border border-gray-300 px-4 py-2 text-sm font-medium text-gray-900 hover:bg-gray-100 disabled:opacity-60"
        >
          {loggingOut ? "Signing out..." : "Sign out"}
        </button>
      </header>

      <section className="mb-8 rounded-xl border border-gray-200 p-5">
        <h2 className="text-base font-semibold text-gray-900">Profile</h2>
        <p className="mt-1 text-sm text-gray-600">{profile?.email ?? "Unknown user"}</p>

        <div className="mt-4 flex flex-wrap items-center gap-2">
          <select
            value={timezoneDraft}
            onChange={(event) => setTimezoneDraft(event.target.value)}
            className="rounded-md border border-gray-300 px-3 py-2 text-sm"
          >
            {timezoneOptions.map((tz) => (
              <option key={tz} value={tz}>
                {tz}
              </option>
            ))}
          </select>
          <button
            type="button"
            onClick={handleSaveTimezone}
            disabled={timezoneSaving}
            className="rounded-md bg-gray-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-60"
          >
            {timezoneSaving ? "Saving..." : "Save timezone"}
          </button>
          <span className="text-xs text-gray-500">Browser: {browserTimezone}</span>
        </div>
        {timezoneMessage ? <p className="mt-2 text-sm text-gray-700">{timezoneMessage}</p> : null}
      </section>

      <section className="mb-8 rounded-xl border border-gray-200 p-5">
        <h2 className="text-base font-semibold text-gray-900">API Keys</h2>
        <p className="mt-1 text-sm text-gray-600">Use API keys for MCP authentication (`Authorization: Bearer metel_xxx`).</p>

        <div className="mt-4 flex flex-wrap items-center gap-2">
          <input
            value={newApiKeyName}
            onChange={(event) => setNewApiKeyName(event.target.value)}
            placeholder="Key name"
            className="rounded-md border border-gray-300 px-3 py-2 text-sm"
          />
          <input
            value={newApiKeyAllowedTools}
            onChange={(event) => setNewApiKeyAllowedTools(event.target.value)}
            placeholder="Allowed tools (comma separated)"
            className="min-w-[260px] rounded-md border border-gray-300 px-3 py-2 text-sm"
          />
          <button
            type="button"
            onClick={() => void handleCreateApiKey()}
            disabled={creatingApiKey}
            className="rounded-md bg-gray-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-60"
          >
            {creatingApiKey ? "Creating..." : "Create API key"}
          </button>
        </div>
        <p className="mt-2 text-xs text-gray-500">Leave allowed tools empty to allow all Phase 1 tools.</p>

        {createdApiKey ? (
          <div className="mt-3 rounded-md border border-amber-300 bg-amber-50 p-3">
            <p className="text-xs font-medium text-amber-900">Copy now. This key is shown only once.</p>
            <div className="mt-2 flex items-center gap-2">
              <code className="block flex-1 overflow-x-auto rounded bg-white px-2 py-1 text-xs text-gray-800">{createdApiKey}</code>
              <button
                type="button"
                onClick={() => void copyText(createdApiKey)}
                className="rounded-md border border-gray-300 px-2 py-1 text-xs font-medium text-gray-800 hover:bg-gray-100"
              >
                Copy
              </button>
            </div>
          </div>
        ) : null}

        {apiKeysError ? <p className="mt-2 text-xs text-red-600">{apiKeysError}</p> : null}
        {apiKeysLoading ? <p className="mt-2 text-xs text-gray-500">Loading keys...</p> : null}

        <div className="mt-4 space-y-2">
          {apiKeys.length === 0 ? (
            <p className="text-xs text-gray-500">No API keys yet.</p>
          ) : (
            apiKeys.map((key) => (
              <article key={key.id} className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-gray-200 p-3">
                <div>
                  <p className="text-sm font-medium text-gray-900">{key.name}</p>
                  <p className="text-xs text-gray-600">
                    {key.key_prefix}... · {key.is_active ? "active" : "revoked"}
                  </p>
                  <div className="mt-2 flex flex-wrap items-center gap-2">
                    <input
                      value={apiKeyAllowedDraft[key.id] ?? ""}
                      onChange={(event) =>
                        setApiKeyAllowedDraft((prev) => ({
                          ...prev,
                          [key.id]: event.target.value,
                        }))
                      }
                      placeholder="Allowed tools (comma separated)"
                      className="min-w-[280px] rounded-md border border-gray-300 px-2 py-1 text-xs"
                    />
                    <button
                      type="button"
                      onClick={() => void handleUpdateApiKeyAllowedTools(key.id)}
                      disabled={updatingApiKeyId === key.id}
                      className="rounded-md border border-gray-300 px-2 py-1 text-xs font-medium text-gray-900 hover:bg-gray-100 disabled:opacity-60"
                    >
                      {updatingApiKeyId === key.id ? "Saving..." : "Save allowed tools"}
                    </button>
                  </div>
                  <p className="mt-1 text-xs text-gray-500">Empty value means all Phase 1 tools are allowed.</p>
                </div>
                <button
                  type="button"
                  onClick={() => void handleRevokeApiKey(key.id)}
                  disabled={!key.is_active || revokingApiKeyId === key.id}
                  className="rounded-md border border-gray-300 px-3 py-1.5 text-xs font-medium text-gray-900 hover:bg-gray-100 disabled:opacity-60"
                >
                  {revokingApiKeyId === key.id ? "Revoking..." : "Revoke"}
                </button>
              </article>
            ))
          )}
        </div>
      </section>

      <section className="mb-8 rounded-xl border border-gray-200 p-5">
        <h2 className="text-base font-semibold text-gray-900">MCP Quick Guide</h2>
        <p className="mt-1 text-sm text-gray-600">Use your API key in `Authorization: Bearer ...` and call JSON-RPC endpoints.</p>
        <div className="mt-3 space-y-3">
          <div>
            <p className="text-xs font-medium text-gray-700">1) List tools</p>
            <pre className="mt-1 overflow-x-auto rounded bg-gray-50 p-3 text-[11px] text-gray-800">{`curl -X POST "$API_BASE_URL/mcp/list_tools" \\
  -H "Authorization: Bearer metel_xxx" \\
  -H "Content-Type: application/json" \\
  -d '{"jsonrpc":"2.0","id":"1","method":"list_tools"}'`}</pre>
          </div>
          <div>
            <p className="text-xs font-medium text-gray-700">2) Call tool</p>
            <pre className="mt-1 overflow-x-auto rounded bg-gray-50 p-3 text-[11px] text-gray-800">{`curl -X POST "$API_BASE_URL/mcp/call_tool" \\
  -H "Authorization: Bearer metel_xxx" \\
  -H "Content-Type: application/json" \\
  -d '{"jsonrpc":"2.0","id":"2","method":"call_tool","params":{"name":"linear_list_issues","arguments":{"first":3}}}'`}</pre>
          </div>
        </div>
      </section>

      <section className="mb-8 rounded-xl border border-gray-200 p-5">
        <div className="flex items-center justify-between gap-2">
          <div>
            <h2 className="text-base font-semibold text-gray-900">MCP Usage</h2>
            <p className="mt-1 text-sm text-gray-600">Recent tool calls and 24h execution summary.</p>
          </div>
          <button
            type="button"
            onClick={() => void fetchToolCalls()}
            disabled={toolCallsLoading}
            className="rounded-md border border-gray-300 px-3 py-1.5 text-xs font-medium text-gray-900 hover:bg-gray-100 disabled:opacity-60"
          >
            Refresh
          </button>
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-2">
          <select
            value={toolCallStatusFilter}
            onChange={(event) => setToolCallStatusFilter(event.target.value as "all" | "success" | "fail")}
            className="rounded-md border border-gray-300 px-3 py-2 text-xs"
          >
            <option value="all">All status</option>
            <option value="success">Success</option>
            <option value="fail">Fail</option>
          </select>
          <input
            value={toolCallNameFilter}
            onChange={(event) => setToolCallNameFilter(event.target.value)}
            placeholder="Filter by tool name (exact)"
            className="rounded-md border border-gray-300 px-3 py-2 text-xs"
          />
          <input
            type="datetime-local"
            value={toolCallFromFilter}
            onChange={(event) => setToolCallFromFilter(event.target.value)}
            className="rounded-md border border-gray-300 px-3 py-2 text-xs"
          />
          <input
            type="datetime-local"
            value={toolCallToFilter}
            onChange={(event) => setToolCallToFilter(event.target.value)}
            className="rounded-md border border-gray-300 px-3 py-2 text-xs"
          />
          <button
            type="button"
            onClick={() => void fetchToolCalls()}
            disabled={toolCallsLoading}
            className="rounded-md border border-gray-300 px-3 py-2 text-xs font-medium text-gray-900 hover:bg-gray-100 disabled:opacity-60"
          >
            Apply
          </button>
        </div>

        <div className="mt-4 grid gap-2 sm:grid-cols-3">
          <article className="rounded-lg border border-gray-200 p-3">
            <p className="text-xs text-gray-500">Calls (24h)</p>
            <p className="mt-1 text-xl font-semibold text-gray-900">{toolCallsSummary?.calls_24h ?? 0}</p>
          </article>
          <article className="rounded-lg border border-gray-200 p-3">
            <p className="text-xs text-gray-500">Success (24h)</p>
            <p className="mt-1 text-xl font-semibold text-emerald-700">{toolCallsSummary?.success_24h ?? 0}</p>
          </article>
          <article className="rounded-lg border border-gray-200 p-3">
            <p className="text-xs text-gray-500">Fail (24h)</p>
            <p className="mt-1 text-xl font-semibold text-rose-700">{toolCallsSummary?.fail_24h ?? 0}</p>
          </article>
          <article className="rounded-lg border border-gray-200 p-3">
            <p className="text-xs text-gray-500">Fail Rate (24h)</p>
            <p className="mt-1 text-xl font-semibold text-rose-700">{((toolCallsSummary?.fail_rate_24h ?? 0) * 100).toFixed(1)}%</p>
          </article>
          <article className="rounded-lg border border-gray-200 p-3">
            <p className="text-xs text-gray-500">Blocked Rate (24h)</p>
            <p className="mt-1 text-xl font-semibold text-amber-700">
              {((toolCallsSummary?.blocked_rate_24h ?? 0) * 100).toFixed(1)}%
            </p>
          </article>
          <article className="rounded-lg border border-gray-200 p-3">
            <p className="text-xs text-gray-500">Retryable Fail Rate (24h)</p>
            <p className="mt-1 text-xl font-semibold text-indigo-700">
              {((toolCallsSummary?.retryable_fail_rate_24h ?? 0) * 100).toFixed(1)}%
            </p>
          </article>
        </div>

        <div className="mt-2 grid gap-2 sm:grid-cols-4">
          <article className="rounded-lg border border-gray-200 p-3">
            <p className="text-xs text-gray-500">Policy Blocked</p>
            <p className="mt-1 text-lg font-semibold text-amber-700">{toolCallsSummary?.policy_blocked_24h ?? 0}</p>
          </article>
          <article className="rounded-lg border border-gray-200 p-3">
            <p className="text-xs text-gray-500">Quota Exceeded</p>
            <p className="mt-1 text-lg font-semibold text-rose-700">{toolCallsSummary?.quota_exceeded_24h ?? 0}</p>
          </article>
          <article className="rounded-lg border border-gray-200 p-3">
            <p className="text-xs text-gray-500">Access Denied</p>
            <p className="mt-1 text-lg font-semibold text-orange-700">{toolCallsSummary?.access_denied_24h ?? 0}</p>
          </article>
          <article className="rounded-lg border border-gray-200 p-3">
            <p className="text-xs text-gray-500">Resolve Fail</p>
            <p className="mt-1 text-lg font-semibold text-orange-700">{toolCallsSummary?.resolve_fail_24h ?? 0}</p>
          </article>
          <article className="rounded-lg border border-gray-200 p-3">
            <p className="text-xs text-gray-500">Upstream Temporary</p>
            <p className="mt-1 text-lg font-semibold text-indigo-700">{toolCallsSummary?.upstream_temporary_24h ?? 0}</p>
          </article>
          <article className="rounded-lg border border-gray-200 p-3">
            <p className="text-xs text-gray-500">High Risk Allowed</p>
            <p className="mt-1 text-lg font-semibold text-cyan-700">{toolCallsSummary?.high_risk_allowed_24h ?? 0}</p>
          </article>
          <article className="rounded-lg border border-gray-200 p-3">
            <p className="text-xs text-gray-500">Policy Override Usage</p>
            <p className="mt-1 text-lg font-semibold text-cyan-700">
              {((toolCallsSummary?.policy_override_usage_24h ?? 0) * 100).toFixed(1)}%
            </p>
          </article>
        </div>

        {toolCallsError ? <p className="mt-2 text-xs text-red-600">{toolCallsError}</p> : null}
        {toolCallsLoading ? <p className="mt-2 text-xs text-gray-500">Loading usage...</p> : null}

        {toolCallsSummary?.top_failure_codes?.length ? (
          <div className="mt-4 rounded-lg border border-gray-200 p-3">
            <p className="text-xs font-medium text-gray-700">Top Failure Codes (24h)</p>
            <div className="mt-2 flex flex-wrap gap-2">
              {toolCallsSummary.top_failure_codes.map((entry) => (
                <span key={entry.error_code} className="rounded-full border border-gray-300 px-2 py-1 text-xs text-gray-700">
                  {entry.error_code}: {entry.count}
                </span>
              ))}
            </div>
          </div>
        ) : null}

        <div className="mt-4 space-y-2">
          {toolCalls.length === 0 ? (
            <p className="text-xs text-gray-500">No tool call logs yet.</p>
          ) : (
            toolCalls.map((call) => (
              <article key={call.id} className="rounded-lg border border-gray-200 p-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <p className="text-sm font-medium text-gray-900">{call.tool_name}</p>
                    <p className="text-xs text-gray-600">
                      {call.api_key?.name ?? "unknown key"} ({call.api_key?.key_prefix ?? "n/a"}...)
                    </p>
                  </div>
                  <div className="text-right">
                    <p className={`text-xs font-medium ${call.status === "success" ? "text-emerald-700" : "text-rose-700"}`}>
                      {call.status}
                    </p>
                    <p className="text-xs text-gray-500">{call.latency_ms} ms</p>
                  </div>
                </div>
                <p className="mt-1 text-xs text-gray-500">{new Date(call.created_at).toLocaleString()}</p>
                {call.error_code ? <p className="mt-1 text-xs text-rose-700">error: {call.error_code}</p> : null}
              </article>
            ))
          )}
        </div>
      </section>

      <section className="rounded-xl border border-gray-200 p-5">
        <div className="mb-4 flex items-center justify-between gap-2">
          <div>
            <h2 className="text-base font-semibold text-gray-900">Audit Events</h2>
            <p className="mt-1 text-sm text-gray-600">Who ran what, and whether it was allowed or blocked.</p>
          </div>
          <button
            type="button"
            onClick={() => void fetchAuditEvents()}
            disabled={auditLoading}
            className="rounded-md border border-gray-300 px-3 py-1.5 text-xs font-medium text-gray-900 hover:bg-gray-100 disabled:opacity-60"
          >
            Refresh
          </button>
        </div>

        <div className="mb-4 grid gap-2 sm:grid-cols-4">
          <article className="rounded-lg border border-gray-200 p-3">
            <p className="text-xs text-gray-500">Allowed</p>
            <p className="mt-1 text-lg font-semibold text-emerald-700">{auditSummary?.allowed_count ?? 0}</p>
          </article>
          <article className="rounded-lg border border-gray-200 p-3">
            <p className="text-xs text-gray-500">Policy Blocked</p>
            <p className="mt-1 text-lg font-semibold text-amber-700">{auditSummary?.policy_blocked_count ?? 0}</p>
          </article>
          <article className="rounded-lg border border-gray-200 p-3">
            <p className="text-xs text-gray-500">Access Denied</p>
            <p className="mt-1 text-lg font-semibold text-orange-700">{auditSummary?.access_denied_count ?? 0}</p>
          </article>
          <article className="rounded-lg border border-gray-200 p-3">
            <p className="text-xs text-gray-500">Failed</p>
            <p className="mt-1 text-lg font-semibold text-rose-700">{auditSummary?.failed_count ?? 0}</p>
          </article>
          <article className="rounded-lg border border-gray-200 p-3">
            <p className="text-xs text-gray-500">High Risk Allowed</p>
            <p className="mt-1 text-lg font-semibold text-cyan-700">{auditSummary?.high_risk_allowed_count ?? 0}</p>
          </article>
          <article className="rounded-lg border border-gray-200 p-3">
            <p className="text-xs text-gray-500">Policy Override Usage</p>
            <p className="mt-1 text-lg font-semibold text-cyan-700">
              {((auditSummary?.policy_override_usage ?? 0) * 100).toFixed(1)}%
            </p>
          </article>
        </div>

        {auditError ? <p className="mb-2 text-xs text-red-600">{auditError}</p> : null}
        {auditLoading ? <p className="mb-2 text-xs text-gray-500">Loading audit events...</p> : null}

        <div className="space-y-2">
          {auditEvents.length === 0 ? (
            <p className="text-xs text-gray-500">No audit events yet.</p>
          ) : (
            auditEvents.map((event) => (
              <article key={event.id} className="rounded-lg border border-gray-200 p-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <p className="text-sm font-medium text-gray-900">{event.action.tool_name}</p>
                    <p className="text-xs text-gray-600">
                      {event.actor.api_key.name ?? "unknown key"} ({event.actor.api_key.key_prefix ?? "n/a"}...)
                    </p>
                  </div>
                  <div className="text-right">
                    <p
                      className={`text-xs font-medium ${
                        event.outcome.decision === "allowed"
                          ? "text-emerald-700"
                          : event.outcome.decision === "policy_blocked"
                            ? "text-amber-700"
                            : event.outcome.decision === "access_denied"
                              ? "text-orange-700"
                              : "text-rose-700"
                      }`}
                    >
                      {event.outcome.decision}
                    </p>
                    <p className="text-xs text-gray-500">{event.outcome.latency_ms ?? 0} ms</p>
                  </div>
                </div>
                <p className="mt-1 text-xs text-gray-500">{new Date(event.timestamp).toLocaleString()}</p>
                {event.outcome.error_code ? <p className="mt-1 text-xs text-rose-700">error: {event.outcome.error_code}</p> : null}
              </article>
            ))
          )}
        </div>
      </section>

      <section className="mt-8 rounded-xl border border-gray-200 p-5">
        <h2 className="text-base font-semibold text-gray-900">OAuth Connections</h2>
        <p className="mt-1 text-sm text-gray-600">Connect Notion and Linear to expose MCP tools.</p>

        <div className="mt-4 space-y-3">
          <ServiceRow
            name="Notion"
            logo="/logos/notion.svg"
            status={notionStatus}
            error={notionError}
            busy={notionBusy}
            onConnect={() => void handleOAuthStart("notion")}
            onDisconnect={() => void handleDisconnect("notion")}
          />
          <ServiceRow
            name="Linear"
            logo="/logos/linear.svg"
            status={linearStatus}
            error={linearError}
            busy={linearBusy}
            onConnect={() => void handleOAuthStart("linear")}
            onDisconnect={() => void handleDisconnect("linear")}
          />
        </div>
      </section>
    </main>
  );
}

function ServiceRow({
  name,
  logo,
  status,
  error,
  busy,
  onConnect,
  onDisconnect
}: {
  name: string;
  logo: string;
  status: OAuthStatus;
  error: string | null;
  busy: boolean;
  onConnect: () => void;
  onDisconnect: () => void;
}) {
  return (
    <article className="rounded-lg border border-gray-200 p-3">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <ServiceLogo src={logo} alt={name} />
          <div>
            <p className="text-sm font-medium text-gray-900">{name}</p>
            <p className="text-xs text-gray-600">{status?.connected ? "Connected" : "Not connected"}</p>
          </div>
        </div>

        {status?.connected ? (
          <button
            type="button"
            onClick={onDisconnect}
            disabled={busy}
            className="rounded-md border border-gray-300 px-3 py-1.5 text-xs font-medium text-gray-900 hover:bg-gray-100 disabled:opacity-60"
          >
            Disconnect
          </button>
        ) : (
          <button
            type="button"
            onClick={onConnect}
            disabled={busy}
            className="rounded-md bg-gray-900 px-3 py-1.5 text-xs font-medium text-white disabled:opacity-60"
          >
            Connect
          </button>
        )}
      </div>

      {status?.integration?.workspace_name ? (
        <p className="mt-2 text-xs text-gray-500">Workspace: {status.integration.workspace_name}</p>
      ) : null}

      {error ? <p className="mt-2 text-xs text-red-600">{error}</p> : null}
    </article>
  );
}
