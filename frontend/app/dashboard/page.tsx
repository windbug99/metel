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
  team_id?: number | null;
  allowed_tools?: string[] | null;
  policy_json?: {
    allow_high_risk?: boolean;
    allowed_services?: string[];
    deny_tools?: string[];
    allowed_linear_team_ids?: string[];
  } | null;
  memo?: string | null;
  tags?: string[] | null;
  issued_by?: string | null;
  rotated_from?: number | null;
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

type OverviewPayload = {
  window_hours: number;
  kpis: {
    total_calls: number;
    success_rate: number;
    fail_rate: number;
    avg_latency_ms: number;
    p95_latency_ms: number;
    retry_rate: number;
    policy_block_rate: number;
  };
  top: {
    called_tools: Array<{ tool_name: string; count: number }>;
    failed_tools: Array<{ tool_name: string; count: number }>;
    blocked_tools: Array<{ tool_name: string; count: number }>;
  };
  anomalies: Array<{
    type: string;
    severity: string;
    message: string;
    context?: Record<string, unknown>;
  }>;
};

type TrendPoint = {
  bucket_start: string;
  calls: number;
  success_rate: number;
  fail_rate: number;
  blocked_rate: number;
  avg_latency_ms: number;
};

type FailureBreakdown = {
  total_failures: number;
  categories: Array<{ category: string; count: number; ratio: number }>;
  error_codes: Array<{ error_code: string; count: number }>;
};

type ConnectorSummary = {
  connector: string;
  calls: number;
  fail_rate: number;
  avg_latency_ms: number;
  top_error_codes: Array<{ error_code: string; count: number }>;
};

type AuditEventItem = {
  id: number;
  request_id: string | null;
  trace_id?: string | null;
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
    upstream_status?: number | null;
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

type AuditSettings = {
  retention_days: number;
  export_enabled: boolean;
  masking_policy: Record<string, unknown>;
  updated_at: string | null;
};

type PolicySimulationResult = {
  decision: string;
  tool_name: string;
  service: string;
  api_key_id: number | null;
  reasons: Array<{ code: string; message: string; source: string; team_id?: string }>;
  risk: { allowed: boolean; reason?: string | null; risk_type?: string | null };
};

type AuditDetail = {
  id: number;
  request_id: string | null;
  trace_id: string | null;
  timestamp: string;
  action: { tool_name: string; connector: string | null };
  actor: { api_key: { id: number | null; name: string | null; key_prefix: string | null } };
  outcome: {
    decision: string;
    status: string;
    error_code: string | null;
    upstream_status: number | null;
    latency_ms: number | null;
    retry_count: number | null;
    backoff_ms: number | null;
  };
  execution: {
    request_payload: Record<string, unknown> | null;
    resolved_payload: Record<string, unknown> | null;
    risk_result: Record<string, unknown> | null;
    masked_fields: string[];
  };
};

type TeamItem = {
  id: number;
  name: string;
  description: string | null;
  is_active: boolean;
  policy_json?: Record<string, unknown>;
  policy_updated_at?: string | null;
};

type PolicyRevisionItem = {
  id: number;
  team_id: number;
  source: string;
  policy_json: Record<string, unknown>;
  created_by: string | null;
  created_at: string;
};

type TeamMemberItem = {
  id: number;
  user_id: string;
  role: string;
  created_at: string;
};

type ApiKeyDrilldown = {
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

type WebhookItem = {
  id: number;
  name: string;
  endpoint_url: string;
  event_types: string[];
  is_active: boolean;
  last_delivery_at: string | null;
  created_at: string;
};

type WebhookDeliveryItem = {
  id: number;
  subscription_id: number;
  event_type: string;
  status: string;
  http_status: number | null;
  error_message: string | null;
  retry_count: number;
  next_retry_at: string | null;
  delivered_at: string | null;
  created_at: string;
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
  const [newApiKeyMemo, setNewApiKeyMemo] = useState("");
  const [newApiKeyTags, setNewApiKeyTags] = useState("");
  const [newApiKeyPolicyJson, setNewApiKeyPolicyJson] = useState("");
  const [newApiKeyTeamId, setNewApiKeyTeamId] = useState("");
  const [createdApiKey, setCreatedApiKey] = useState<string | null>(null);
  const [revokingApiKeyId, setRevokingApiKeyId] = useState<number | null>(null);
  const [updatingApiKeyId, setUpdatingApiKeyId] = useState<number | null>(null);
  const [rotatingApiKeyId, setRotatingApiKeyId] = useState<number | null>(null);
  const [apiKeyAllowedDraft, setApiKeyAllowedDraft] = useState<Record<number, string>>({});
  const [apiKeyMemoDraft, setApiKeyMemoDraft] = useState<Record<number, string>>({});
  const [apiKeyTagsDraft, setApiKeyTagsDraft] = useState<Record<number, string>>({});
  const [apiKeyPolicyDraft, setApiKeyPolicyDraft] = useState<Record<number, string>>({});
  const [apiKeyTeamDraft, setApiKeyTeamDraft] = useState<Record<number, string>>({});
  const [apiKeyDrilldownLoadingId, setApiKeyDrilldownLoadingId] = useState<number | null>(null);
  const [apiKeyDrilldown, setApiKeyDrilldown] = useState<Record<number, ApiKeyDrilldown>>({});
  const [toolCalls, setToolCalls] = useState<ToolCallItem[]>([]);
  const [toolCallsSummary, setToolCallsSummary] = useState<ToolCallSummary | null>(null);
  const [toolCallsLoading, setToolCallsLoading] = useState(false);
  const [toolCallsError, setToolCallsError] = useState<string | null>(null);
  const [overview, setOverview] = useState<OverviewPayload | null>(null);
  const [overviewLoading, setOverviewLoading] = useState(false);
  const [overviewError, setOverviewError] = useState<string | null>(null);
  const [trendPoints, setTrendPoints] = useState<TrendPoint[]>([]);
  const [trendLoading, setTrendLoading] = useState(false);
  const [trendError, setTrendError] = useState<string | null>(null);
  const [failureBreakdown, setFailureBreakdown] = useState<FailureBreakdown | null>(null);
  const [connectorSummary, setConnectorSummary] = useState<ConnectorSummary[]>([]);
  const [toolCallStatusFilter, setToolCallStatusFilter] = useState<"all" | "success" | "fail">("all");
  const [toolCallNameFilter, setToolCallNameFilter] = useState("");
  const [toolCallFromFilter, setToolCallFromFilter] = useState("");
  const [toolCallToFilter, setToolCallToFilter] = useState("");
  const [auditEvents, setAuditEvents] = useState<AuditEventItem[]>([]);
  const [auditSummary, setAuditSummary] = useState<AuditSummary | null>(null);
  const [auditLoading, setAuditLoading] = useState(false);
  const [auditError, setAuditError] = useState<string | null>(null);
  const [auditDetail, setAuditDetail] = useState<AuditDetail | null>(null);
  const [auditDetailLoading, setAuditDetailLoading] = useState(false);
  const [auditSettings, setAuditSettings] = useState<AuditSettings | null>(null);
  const [auditSettingsLoading, setAuditSettingsLoading] = useState(false);
  const [auditSettingsSaving, setAuditSettingsSaving] = useState(false);
  const [auditRetentionDraft, setAuditRetentionDraft] = useState("90");
  const [auditExportEnabledDraft, setAuditExportEnabledDraft] = useState(true);
  const [auditMaskingPolicyDraft, setAuditMaskingPolicyDraft] = useState("{}");
  const [simulatorApiKeyId, setSimulatorApiKeyId] = useState("");
  const [simulatorToolName, setSimulatorToolName] = useState("notion_search");
  const [simulatorArguments, setSimulatorArguments] = useState("{}");
  const [simulatorLoading, setSimulatorLoading] = useState(false);
  const [simulatorResult, setSimulatorResult] = useState<PolicySimulationResult | null>(null);
  const [simulatorError, setSimulatorError] = useState<string | null>(null);
  const [teams, setTeams] = useState<TeamItem[]>([]);
  const [teamsLoading, setTeamsLoading] = useState(false);
  const [teamsError, setTeamsError] = useState<string | null>(null);
  const [creatingTeam, setCreatingTeam] = useState(false);
  const [newTeamName, setNewTeamName] = useState("");
  const [newTeamDescription, setNewTeamDescription] = useState("");
  const [newTeamPolicyJson, setNewTeamPolicyJson] = useState("");
  const [teamNameDraft, setTeamNameDraft] = useState<Record<number, string>>({});
  const [teamDescriptionDraft, setTeamDescriptionDraft] = useState<Record<number, string>>({});
  const [teamPolicyDraft, setTeamPolicyDraft] = useState<Record<number, string>>({});
  const [teamActiveDraft, setTeamActiveDraft] = useState<Record<number, boolean>>({});
  const [teamUpdateLoadingId, setTeamUpdateLoadingId] = useState<number | null>(null);
  const [teamRevisions, setTeamRevisions] = useState<Record<number, PolicyRevisionItem[]>>({});
  const [teamRevisionLoadingId, setTeamRevisionLoadingId] = useState<number | null>(null);
  const [teamRollbackLoadingId, setTeamRollbackLoadingId] = useState<number | null>(null);
  const [teamMembers, setTeamMembers] = useState<Record<number, TeamMemberItem[]>>({});
  const [teamMembersLoadingId, setTeamMembersLoadingId] = useState<number | null>(null);
  const [teamMemberActionLoadingId, setTeamMemberActionLoadingId] = useState<number | null>(null);
  const [teamMemberDeleteLoadingId, setTeamMemberDeleteLoadingId] = useState<number | null>(null);
  const [teamMemberUserDraft, setTeamMemberUserDraft] = useState<Record<number, string>>({});
  const [teamMemberRoleDraft, setTeamMemberRoleDraft] = useState<Record<number, string>>({});
  const [webhooks, setWebhooks] = useState<WebhookItem[]>([]);
  const [deliveries, setDeliveries] = useState<WebhookDeliveryItem[]>([]);
  const [integrationsLoading, setIntegrationsLoading] = useState(false);
  const [integrationsError, setIntegrationsError] = useState<string | null>(null);
  const [processingWebhookRetries, setProcessingWebhookRetries] = useState(false);
  const [creatingWebhook, setCreatingWebhook] = useState(false);
  const [newWebhookName, setNewWebhookName] = useState("");
  const [newWebhookUrl, setNewWebhookUrl] = useState("");
  const [newWebhookSecret, setNewWebhookSecret] = useState("");
  const [newWebhookEvents, setNewWebhookEvents] = useState("tool_called, tool_succeeded, tool_failed, policy_blocked");
  const [adminLoading, setAdminLoading] = useState(false);
  const [adminError, setAdminError] = useState<string | null>(null);
  const [connectorDiagnostics, setConnectorDiagnostics] = useState<ConnectorDiagnosticItem[]>([]);
  const [rateLimitEvents, setRateLimitEvents] = useState<RateLimitEventItem[]>([]);
  const [systemHealth, setSystemHealth] = useState<SystemHealthPayload | null>(null);
  const [externalHealth, setExternalHealth] = useState<ExternalHealthItem[]>([]);
  const [incidentBanner, setIncidentBanner] = useState<IncidentBanner | null>(null);
  const [incidentEnabledDraft, setIncidentEnabledDraft] = useState(false);
  const [incidentSeverityDraft, setIncidentSeverityDraft] = useState<"info" | "warning" | "critical">("info");
  const [incidentMessageDraft, setIncidentMessageDraft] = useState("");
  const [incidentStartsAtDraft, setIncidentStartsAtDraft] = useState("");
  const [incidentEndsAtDraft, setIncidentEndsAtDraft] = useState("");
  const [incidentSaving, setIncidentSaving] = useState(false);

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
      setApiKeyMemoDraft((prev) => {
        const next = { ...prev };
        for (const item of items) {
          if (next[item.id] !== undefined) {
            continue;
          }
          next[item.id] = item.memo ?? "";
        }
        return next;
      });
      setApiKeyTagsDraft((prev) => {
        const next = { ...prev };
        for (const item of items) {
          if (next[item.id] !== undefined) {
            continue;
          }
          next[item.id] = (item.tags ?? []).join(", ");
        }
        return next;
      });
      setApiKeyPolicyDraft((prev) => {
        const next = { ...prev };
        for (const item of items) {
          if (next[item.id] !== undefined) {
            continue;
          }
          next[item.id] = item.policy_json ? JSON.stringify(item.policy_json, null, 2) : "";
        }
        return next;
      });
      setApiKeyTeamDraft((prev) => {
        const next = { ...prev };
        for (const item of items) {
          if (next[item.id] !== undefined) {
            continue;
          }
          next[item.id] = item.team_id ? String(item.team_id) : "";
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

  const fetchOverview = useCallback(async () => {
    if (!apiBaseUrl) {
      return;
    }
    setOverviewLoading(true);
    try {
      const headers = await getAuthHeaders();
      const response = await fetch(`${apiBaseUrl}/api/tool-calls/overview?hours=24`, { headers });
      if (!response.ok) {
        throw new Error("failed_tool_calls_overview");
      }
      setOverview((await response.json()) as OverviewPayload);
      setOverviewError(null);
    } catch {
      setOverviewError("Failed to load overview.");
    } finally {
      setOverviewLoading(false);
    }
  }, [apiBaseUrl, getAuthHeaders]);

  const fetchTrendAndBreakdown = useCallback(async () => {
    if (!apiBaseUrl) {
      return;
    }
    setTrendLoading(true);
    try {
      const headers = await getAuthHeaders();
      const [trendsRes, breakdownRes, connectorsRes] = await Promise.all([
        fetch(`${apiBaseUrl}/api/tool-calls/trends?days=7&bucket=day`, { headers }),
        fetch(`${apiBaseUrl}/api/tool-calls/failure-breakdown?days=7`, { headers }),
        fetch(`${apiBaseUrl}/api/tool-calls/connectors?days=7`, { headers }),
      ]);
      if (!trendsRes.ok || !breakdownRes.ok || !connectorsRes.ok) {
        throw new Error("failed_usage_trends");
      }
      const trendsPayload = (await trendsRes.json()) as { items?: TrendPoint[] };
      const breakdownPayload = (await breakdownRes.json()) as FailureBreakdown;
      const connectorsPayload = (await connectorsRes.json()) as { items?: ConnectorSummary[] };
      setTrendPoints(Array.isArray(trendsPayload.items) ? trendsPayload.items : []);
      setFailureBreakdown(breakdownPayload ?? null);
      setConnectorSummary(Array.isArray(connectorsPayload.items) ? connectorsPayload.items : []);
      setTrendError(null);
    } catch {
      setTrendError("Failed to load usage trends.");
    } finally {
      setTrendLoading(false);
    }
  }, [apiBaseUrl, getAuthHeaders]);

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

  const fetchAuditSettings = useCallback(async () => {
    if (!apiBaseUrl) {
      return;
    }
    setAuditSettingsLoading(true);
    try {
      const headers = await getAuthHeaders();
      const response = await fetch(`${apiBaseUrl}/api/audit/settings`, { headers });
      if (!response.ok) {
        throw new Error("failed_audit_settings");
      }
      const payload = (await response.json()) as AuditSettings;
      setAuditSettings(payload);
      setAuditRetentionDraft(String(payload.retention_days ?? 90));
      setAuditExportEnabledDraft(Boolean(payload.export_enabled));
      setAuditMaskingPolicyDraft(JSON.stringify(payload.masking_policy ?? {}, null, 2));
      setAuditError(null);
    } catch {
      setAuditError("Failed to load audit settings.");
    } finally {
      setAuditSettingsLoading(false);
    }
  }, [apiBaseUrl, getAuthHeaders]);

  const fetchAuditEventDetail = useCallback(
    async (eventId: number) => {
      if (!apiBaseUrl) {
        return;
      }
      setAuditDetailLoading(true);
      try {
        const headers = await getAuthHeaders();
        const response = await fetch(`${apiBaseUrl}/api/audit/events/${eventId}`, { headers });
        if (!response.ok) {
          throw new Error("failed_audit_event_detail");
        }
        setAuditDetail((await response.json()) as AuditDetail);
      } catch {
        setAuditError("Failed to load audit event detail.");
      } finally {
        setAuditDetailLoading(false);
      }
    },
    [apiBaseUrl, getAuthHeaders]
  );

  const handleSaveAuditSettings = async () => {
    if (!apiBaseUrl) {
      return;
    }
    setAuditSettingsSaving(true);
    try {
      const retention = Number(auditRetentionDraft);
      if (!Number.isFinite(retention) || retention < 1) {
        setAuditError("Retention days must be 1 or greater.");
        return;
      }
      let maskingPolicy: Record<string, unknown> = {};
      try {
        maskingPolicy = JSON.parse(auditMaskingPolicyDraft) as Record<string, unknown>;
      } catch {
        setAuditError("Masking policy JSON is invalid.");
        return;
      }
      const headers = await getAuthHeaders();
      const response = await fetch(`${apiBaseUrl}/api/audit/settings`, {
        method: "PATCH",
        headers: { ...headers, "Content-Type": "application/json" },
        body: JSON.stringify({
          retention_days: retention,
          export_enabled: auditExportEnabledDraft,
          masking_policy: maskingPolicy,
        }),
      });
      if (!response.ok) {
        throw new Error("failed_update_audit_settings");
      }
      await fetchAuditSettings();
      setAuditError(null);
    } catch {
      setAuditError("Failed to save audit settings.");
    } finally {
      setAuditSettingsSaving(false);
    }
  };

  const handleExportAudit = async (format: "jsonl" | "csv") => {
    if (!apiBaseUrl) {
      return;
    }
    try {
      const headers = await getAuthHeaders();
      const response = await fetch(`${apiBaseUrl}/api/audit/export?format=${format}&limit=500`, { headers });
      if (!response.ok) {
        throw new Error("failed_export_audit");
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
      setAuditError(null);
    } catch {
      setAuditError("Failed to export audit events.");
    }
  };

  const runPolicySimulation = useCallback(async () => {
    if (!apiBaseUrl) {
      return;
    }
    setSimulatorLoading(true);
    setSimulatorError(null);
    setSimulatorResult(null);
    try {
      let argsPayload: Record<string, unknown> = {};
      try {
        argsPayload = JSON.parse(simulatorArguments) as Record<string, unknown>;
      } catch {
        setSimulatorError("Arguments JSON is invalid.");
        return;
      }
      const headers = await getAuthHeaders();
      const response = await fetch(`${apiBaseUrl}/api/policies/simulate`, {
        method: "POST",
        headers: { ...headers, "Content-Type": "application/json" },
        body: JSON.stringify({
          api_key_id: simulatorApiKeyId ? Number(simulatorApiKeyId) : null,
          tool_name: simulatorToolName.trim(),
          arguments: argsPayload,
        }),
      });
      if (!response.ok) {
        throw new Error("failed_policy_simulation");
      }
      setSimulatorResult((await response.json()) as PolicySimulationResult);
    } catch {
      setSimulatorError("Failed to run policy simulation.");
    } finally {
      setSimulatorLoading(false);
    }
  }, [apiBaseUrl, getAuthHeaders, simulatorApiKeyId, simulatorArguments, simulatorToolName]);

  const fetchTeams = useCallback(async () => {
    if (!apiBaseUrl) {
      return;
    }
    setTeamsLoading(true);
    try {
      const headers = await getAuthHeaders();
      const response = await fetch(`${apiBaseUrl}/api/teams`, { headers });
      if (!response.ok) {
        throw new Error("failed_team_list");
      }
      const payload = (await response.json()) as { items?: TeamItem[] };
      const items = Array.isArray(payload.items) ? payload.items : [];
      setTeams(items);
      setTeamNameDraft((prev) => {
        const next = { ...prev };
        for (const item of items) {
          if (next[item.id] !== undefined) {
            continue;
          }
          next[item.id] = item.name ?? "";
        }
        return next;
      });
      setTeamDescriptionDraft((prev) => {
        const next = { ...prev };
        for (const item of items) {
          if (next[item.id] !== undefined) {
            continue;
          }
          next[item.id] = item.description ?? "";
        }
        return next;
      });
      setTeamPolicyDraft((prev) => {
        const next = { ...prev };
        for (const item of items) {
          if (next[item.id] !== undefined) {
            continue;
          }
          next[item.id] = JSON.stringify(item.policy_json ?? {}, null, 2);
        }
        return next;
      });
      setTeamActiveDraft((prev) => {
        const next = { ...prev };
        for (const item of items) {
          if (next[item.id] !== undefined) {
            continue;
          }
          next[item.id] = Boolean(item.is_active);
        }
        return next;
      });
      setTeamsError(null);
    } catch {
      setTeamsError("Failed to load teams.");
    } finally {
      setTeamsLoading(false);
    }
  }, [apiBaseUrl, getAuthHeaders]);

  const fetchIntegrations = useCallback(async () => {
    if (!apiBaseUrl) {
      return;
    }
    setIntegrationsLoading(true);
    try {
      const headers = await getAuthHeaders();
      const [webhooksRes, deliveriesRes] = await Promise.all([
        fetch(`${apiBaseUrl}/api/integrations/webhooks`, { headers }),
        fetch(`${apiBaseUrl}/api/integrations/deliveries?limit=20`, { headers }),
      ]);
      if (!webhooksRes.ok || !deliveriesRes.ok) {
        throw new Error("failed_integrations");
      }
      const webhookPayload = (await webhooksRes.json()) as { items?: WebhookItem[] };
      const deliveryPayload = (await deliveriesRes.json()) as { items?: WebhookDeliveryItem[] };
      setWebhooks(Array.isArray(webhookPayload.items) ? webhookPayload.items : []);
      setDeliveries(Array.isArray(deliveryPayload.items) ? deliveryPayload.items : []);
      setIntegrationsError(null);
    } catch {
      setIntegrationsError("Failed to load integration status.");
    } finally {
      setIntegrationsLoading(false);
    }
  }, [apiBaseUrl, getAuthHeaders]);

  const fetchAdminOps = useCallback(async () => {
    if (!apiBaseUrl) {
      return;
    }
    setAdminLoading(true);
    try {
      const headers = await getAuthHeaders();
      const [diagnosticsRes, rateLimitRes, healthRes, externalHealthRes, incidentRes] = await Promise.all([
        fetch(`${apiBaseUrl}/api/admin/connectors/diagnostics`, { headers }),
        fetch(`${apiBaseUrl}/api/admin/rate-limit-events?days=7&limit=20`, { headers }),
        fetch(`${apiBaseUrl}/api/admin/system-health`, { headers }),
        fetch(`${apiBaseUrl}/api/admin/external-health?days=1`, { headers }),
        fetch(`${apiBaseUrl}/api/admin/incident-banner`, { headers }),
      ]);
      if (!diagnosticsRes.ok || !rateLimitRes.ok || !healthRes.ok || !externalHealthRes.ok || !incidentRes.ok) {
        throw new Error("failed_admin_ops");
      }
      const diagnosticsPayload = (await diagnosticsRes.json()) as { items?: ConnectorDiagnosticItem[] };
      const rateLimitPayload = (await rateLimitRes.json()) as { items?: RateLimitEventItem[] };
      const externalHealthPayload = (await externalHealthRes.json()) as { items?: ExternalHealthItem[] };
      const incidentPayload = (await incidentRes.json()) as IncidentBanner;
      setConnectorDiagnostics(Array.isArray(diagnosticsPayload.items) ? diagnosticsPayload.items : []);
      setRateLimitEvents(Array.isArray(rateLimitPayload.items) ? rateLimitPayload.items : []);
      setSystemHealth((await healthRes.json()) as SystemHealthPayload);
      setExternalHealth(Array.isArray(externalHealthPayload.items) ? externalHealthPayload.items : []);
      setIncidentBanner(incidentPayload);
      setIncidentEnabledDraft(Boolean(incidentPayload.enabled));
      setIncidentSeverityDraft((incidentPayload.severity ?? "info") as "info" | "warning" | "critical");
      setIncidentMessageDraft(incidentPayload.message ?? "");
      setIncidentStartsAtDraft(incidentPayload.starts_at ? incidentPayload.starts_at.slice(0, 16) : "");
      setIncidentEndsAtDraft(incidentPayload.ends_at ? incidentPayload.ends_at.slice(0, 16) : "");
      setAdminError(null);
    } catch {
      setAdminError("Failed to load admin diagnostics.");
    } finally {
      setAdminLoading(false);
    }
  }, [apiBaseUrl, getAuthHeaders]);

  const handleSaveIncidentBanner = async () => {
    if (!apiBaseUrl) {
      return;
    }
    setIncidentSaving(true);
    try {
      const headers = await getAuthHeaders();
      const response = await fetch(`${apiBaseUrl}/api/admin/incident-banner`, {
        method: "PATCH",
        headers: { ...headers, "Content-Type": "application/json" },
        body: JSON.stringify({
          enabled: incidentEnabledDraft,
          severity: incidentSeverityDraft,
          message: incidentMessageDraft.trim() || null,
          starts_at: incidentStartsAtDraft ? new Date(incidentStartsAtDraft).toISOString() : null,
          ends_at: incidentEndsAtDraft ? new Date(incidentEndsAtDraft).toISOString() : null,
        }),
      });
      if (!response.ok) {
        throw new Error("failed_save_incident_banner");
      }
      await fetchAdminOps();
      setAdminError(null);
    } catch {
      setAdminError("Failed to save incident banner.");
    } finally {
      setIncidentSaving(false);
    }
  };

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

      await Promise.all([
        refreshStatuses(),
        fetchApiKeys(),
        fetchOverview(),
        fetchTrendAndBreakdown(),
        fetchToolCalls(),
        fetchAuditEvents(),
        fetchAuditSettings(),
        fetchTeams(),
        fetchIntegrations(),
        fetchAdminOps(),
      ]);
      setLoading(false);
    };

    void bootstrap();

    return () => {
      mounted = false;
    };
  }, [
    browserTimezone,
    fetchApiKeys,
    fetchOverview,
    fetchTrendAndBreakdown,
    fetchToolCalls,
    fetchAuditEvents,
    fetchAuditSettings,
    fetchTeams,
    fetchIntegrations,
    fetchAdminOps,
    fetchUserProfile,
    refreshStatuses,
    router,
  ]);

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
      const tags = newApiKeyTags
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean);
      let parsedPolicy: Record<string, unknown> | null = null;
      if (newApiKeyPolicyJson.trim()) {
        try {
          parsedPolicy = JSON.parse(newApiKeyPolicyJson) as Record<string, unknown>;
        } catch {
          setApiKeysError("Policy JSON is invalid.");
          return;
        }
      }
      const response = await fetch(`${apiBaseUrl}/api/api-keys`, {
        method: "POST",
        headers: { ...headers, "Content-Type": "application/json" },
        body: JSON.stringify({
          name: newApiKeyName.trim() || "default",
          team_id: newApiKeyTeamId ? Number(newApiKeyTeamId) : null,
          allowed_tools: allowedTools.length > 0 ? allowedTools : null,
          memo: newApiKeyMemo.trim() || null,
          tags: tags.length > 0 ? tags : null,
          policy_json: parsedPolicy,
        })
      });
      if (!response.ok) {
        throw new Error("failed_create_api_key");
      }
      const payload = (await response.json()) as { api_key?: string };
      setCreatedApiKey(payload.api_key ?? null);
      setNewApiKeyTeamId("");
      await Promise.all([fetchApiKeys(), fetchOverview(), fetchTrendAndBreakdown(), fetchToolCalls(), fetchAuditEvents(), fetchAuditSettings(), fetchTeams(), fetchIntegrations(), fetchAdminOps()]);
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
      await Promise.all([fetchApiKeys(), fetchOverview(), fetchTrendAndBreakdown(), fetchToolCalls(), fetchAuditEvents(), fetchAuditSettings(), fetchTeams(), fetchIntegrations(), fetchAdminOps()]);
    } catch {
      setApiKeysError("Failed to revoke API key.");
    } finally {
      setRevokingApiKeyId(null);
    }
  };

  const handleUpdateApiKeySettings = async (id: number) => {
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
      const tags = (apiKeyTagsDraft[id] ?? "")
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean);
      let policyJson: Record<string, unknown> | null = null;
      const rawPolicy = (apiKeyPolicyDraft[id] ?? "").trim();
      if (rawPolicy) {
        try {
          policyJson = JSON.parse(rawPolicy) as Record<string, unknown>;
        } catch {
          setApiKeysError("Policy JSON is invalid.");
          return;
        }
      }
      const response = await fetch(`${apiBaseUrl}/api/api-keys/${id}`, {
        method: "PATCH",
        headers: { ...headers, "Content-Type": "application/json" },
        body: JSON.stringify({
          team_id: (apiKeyTeamDraft[id] ?? "").trim() ? Number((apiKeyTeamDraft[id] ?? "").trim()) : null,
          allowed_tools: allowedTools.length > 0 ? allowedTools : null,
          memo: (apiKeyMemoDraft[id] ?? "").trim() || null,
          tags: tags.length > 0 ? tags : null,
          policy_json: policyJson,
        }),
      });
      if (!response.ok) {
        throw new Error("failed_update_api_key");
      }
      await fetchApiKeys();
    } catch {
      setApiKeysError("Failed to update API key settings.");
    } finally {
      setUpdatingApiKeyId(null);
    }
  };

  const handleRotateApiKey = async (id: number) => {
    if (!apiBaseUrl) {
      return;
    }
    setRotatingApiKeyId(id);
    setCreatedApiKey(null);
    try {
      const headers = await getAuthHeaders();
      const response = await fetch(`${apiBaseUrl}/api/api-keys/${id}/rotate`, {
        method: "POST",
        headers,
      });
      if (!response.ok) {
        throw new Error("failed_rotate_api_key");
      }
      const payload = (await response.json()) as { api_key?: string };
      setCreatedApiKey(payload.api_key ?? null);
      await Promise.all([fetchApiKeys(), fetchOverview(), fetchTrendAndBreakdown(), fetchToolCalls(), fetchAuditEvents(), fetchAuditSettings(), fetchTeams(), fetchIntegrations(), fetchAdminOps()]);
    } catch {
      setApiKeysError("Failed to rotate API key.");
    } finally {
      setRotatingApiKeyId(null);
    }
  };

  const fetchApiKeyDrilldown = useCallback(
    async (keyId: number) => {
      if (!apiBaseUrl) {
        return;
      }
      setApiKeyDrilldownLoadingId(keyId);
      try {
        const headers = await getAuthHeaders();
        const response = await fetch(`${apiBaseUrl}/api/api-keys/${keyId}/drilldown?days=7`, { headers });
        if (!response.ok) {
          throw new Error("failed_api_key_drilldown");
        }
        const payload = (await response.json()) as ApiKeyDrilldown;
        setApiKeyDrilldown((prev) => ({ ...prev, [keyId]: payload }));
        setApiKeysError(null);
      } catch {
        setApiKeysError("Failed to load API key drill-down.");
      } finally {
        setApiKeyDrilldownLoadingId(null);
      }
    },
    [apiBaseUrl, getAuthHeaders]
  );

  const handleCreateTeam = async () => {
    if (!apiBaseUrl || !newTeamName.trim()) {
      return;
    }
    setCreatingTeam(true);
    try {
      let parsedPolicy: Record<string, unknown> | null = null;
      if (newTeamPolicyJson.trim()) {
        try {
          parsedPolicy = JSON.parse(newTeamPolicyJson) as Record<string, unknown>;
        } catch {
          setTeamsError("Team policy JSON is invalid.");
          return;
        }
      }
      const headers = await getAuthHeaders();
      const response = await fetch(`${apiBaseUrl}/api/teams`, {
        method: "POST",
        headers: { ...headers, "Content-Type": "application/json" },
        body: JSON.stringify({
          name: newTeamName.trim(),
          description: newTeamDescription.trim() || null,
          policy_json: parsedPolicy,
        }),
      });
      if (!response.ok) {
        throw new Error("failed_create_team");
      }
      setNewTeamName("");
      setNewTeamDescription("");
      setNewTeamPolicyJson("");
      await fetchTeams();
      setTeamsError(null);
    } catch {
      setTeamsError("Failed to create team.");
    } finally {
      setCreatingTeam(false);
    }
  };

  const handleUpdateTeam = async (teamId: number) => {
    if (!apiBaseUrl) {
      return;
    }
    setTeamUpdateLoadingId(teamId);
    try {
      const headers = await getAuthHeaders();
      const rawPolicy = (teamPolicyDraft[teamId] ?? "").trim();
      let policyJson: Record<string, unknown> | null = null;
      if (rawPolicy) {
        try {
          policyJson = JSON.parse(rawPolicy) as Record<string, unknown>;
        } catch {
          setTeamsError("Team policy JSON is invalid.");
          return;
        }
      }
      const response = await fetch(`${apiBaseUrl}/api/teams/${teamId}`, {
        method: "PATCH",
        headers: { ...headers, "Content-Type": "application/json" },
        body: JSON.stringify({
          name: (teamNameDraft[teamId] ?? "").trim(),
          description: (teamDescriptionDraft[teamId] ?? "").trim() || null,
          is_active: Boolean(teamActiveDraft[teamId]),
          policy_json: policyJson,
        }),
      });
      if (!response.ok) {
        throw new Error("failed_update_team");
      }
      await fetchTeams();
      setTeamsError(null);
    } catch {
      setTeamsError("Failed to update team.");
    } finally {
      setTeamUpdateLoadingId(null);
    }
  };

  const fetchTeamRevisions = useCallback(
    async (teamId: number) => {
      if (!apiBaseUrl) {
        return;
      }
      setTeamRevisionLoadingId(teamId);
      try {
        const headers = await getAuthHeaders();
        const response = await fetch(`${apiBaseUrl}/api/teams/${teamId}/policy-revisions?limit=20`, { headers });
        if (!response.ok) {
          throw new Error("failed_team_revisions");
        }
        const payload = (await response.json()) as { items?: PolicyRevisionItem[] };
        setTeamRevisions((prev) => ({ ...prev, [teamId]: Array.isArray(payload.items) ? payload.items : [] }));
        setTeamsError(null);
      } catch {
        setTeamsError("Failed to load team policy revisions.");
      } finally {
        setTeamRevisionLoadingId(null);
      }
    },
    [apiBaseUrl, getAuthHeaders]
  );

  const handleRollbackTeamRevision = async (teamId: number, revisionId: number) => {
    if (!apiBaseUrl) {
      return;
    }
    setTeamRollbackLoadingId(revisionId);
    try {
      const headers = await getAuthHeaders();
      const response = await fetch(`${apiBaseUrl}/api/teams/${teamId}/policy-revisions/${revisionId}/rollback`, {
        method: "POST",
        headers,
      });
      if (!response.ok) {
        throw new Error("failed_team_policy_rollback");
      }
      await Promise.all([fetchTeams(), fetchTeamRevisions(teamId)]);
      setTeamsError(null);
    } catch {
      setTeamsError("Failed to rollback team policy revision.");
    } finally {
      setTeamRollbackLoadingId(null);
    }
  };

  const fetchTeamMembers = useCallback(
    async (teamId: number) => {
      if (!apiBaseUrl) {
        return;
      }
      setTeamMembersLoadingId(teamId);
      try {
        const headers = await getAuthHeaders();
        const response = await fetch(`${apiBaseUrl}/api/teams/${teamId}/members`, { headers });
        if (!response.ok) {
          throw new Error("failed_team_members");
        }
        const payload = (await response.json()) as { items?: TeamMemberItem[] };
        setTeamMembers((prev) => ({ ...prev, [teamId]: Array.isArray(payload.items) ? payload.items : [] }));
        setTeamsError(null);
      } catch {
        setTeamsError("Failed to load team members.");
      } finally {
        setTeamMembersLoadingId(null);
      }
    },
    [apiBaseUrl, getAuthHeaders]
  );

  const handleUpsertTeamMember = async (teamId: number) => {
    if (!apiBaseUrl) {
      return;
    }
    const userId = (teamMemberUserDraft[teamId] ?? "").trim();
    if (!userId) {
      setTeamsError("Team member user_id is required.");
      return;
    }
    setTeamMemberActionLoadingId(teamId);
    try {
      const headers = await getAuthHeaders();
      const response = await fetch(`${apiBaseUrl}/api/teams/${teamId}/members`, {
        method: "POST",
        headers: { ...headers, "Content-Type": "application/json" },
        body: JSON.stringify({
          user_id: userId,
          role: (teamMemberRoleDraft[teamId] ?? "member").trim() || "member",
        }),
      });
      if (!response.ok) {
        throw new Error("failed_team_member_upsert");
      }
      setTeamMemberUserDraft((prev) => ({ ...prev, [teamId]: "" }));
      setTeamMemberRoleDraft((prev) => ({ ...prev, [teamId]: "member" }));
      await fetchTeamMembers(teamId);
      setTeamsError(null);
    } catch {
      setTeamsError("Failed to add or update team member.");
    } finally {
      setTeamMemberActionLoadingId(null);
    }
  };

  const handleDeleteTeamMember = async (teamId: number, membershipId: number) => {
    if (!apiBaseUrl) {
      return;
    }
    setTeamMemberDeleteLoadingId(membershipId);
    try {
      const headers = await getAuthHeaders();
      const response = await fetch(`${apiBaseUrl}/api/teams/${teamId}/members/${membershipId}`, {
        method: "DELETE",
        headers,
      });
      if (!response.ok) {
        throw new Error("failed_team_member_delete");
      }
      await fetchTeamMembers(teamId);
      setTeamsError(null);
    } catch {
      setTeamsError("Failed to delete team member.");
    } finally {
      setTeamMemberDeleteLoadingId(null);
    }
  };

  const handleCreateWebhook = async () => {
    if (!apiBaseUrl || !newWebhookName.trim() || !newWebhookUrl.trim()) {
      return;
    }
    setCreatingWebhook(true);
    try {
      const headers = await getAuthHeaders();
      const eventTypes = newWebhookEvents
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean);
      const response = await fetch(`${apiBaseUrl}/api/integrations/webhooks`, {
        method: "POST",
        headers: { ...headers, "Content-Type": "application/json" },
        body: JSON.stringify({
          name: newWebhookName.trim(),
          endpoint_url: newWebhookUrl.trim(),
          secret: newWebhookSecret.trim() || null,
          event_types: eventTypes,
        }),
      });
      if (!response.ok) {
        throw new Error("failed_create_webhook");
      }
      setNewWebhookName("");
      setNewWebhookUrl("");
      setNewWebhookSecret("");
      await fetchIntegrations();
      setIntegrationsError(null);
    } catch {
      setIntegrationsError("Failed to create webhook.");
    } finally {
      setCreatingWebhook(false);
    }
  };

  const handleProcessWebhookRetries = async () => {
    if (!apiBaseUrl) {
      return;
    }
    setProcessingWebhookRetries(true);
    try {
      const headers = await getAuthHeaders();
      const response = await fetch(`${apiBaseUrl}/api/integrations/deliveries/process-retries?limit=100`, {
        method: "POST",
        headers,
      });
      if (!response.ok) {
        throw new Error("failed_process_webhook_retries");
      }
      await fetchIntegrations();
      setIntegrationsError(null);
    } catch {
      setIntegrationsError("Failed to process webhook retries.");
    } finally {
      setProcessingWebhookRetries(false);
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
          <p className="text-sm text-gray-600">Execution control platform console for API keys, policy, audit, and ops.</p>
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
        <div className="mb-4 flex items-center justify-between gap-2">
          <div>
            <h2 className="text-base font-semibold text-gray-900">Execution Overview (24h)</h2>
            <p className="mt-1 text-sm text-gray-600">Core KPI, top tools, and anomaly signals.</p>
          </div>
          <button
            type="button"
            onClick={() => void Promise.all([fetchOverview(), fetchTrendAndBreakdown()])}
            disabled={overviewLoading || trendLoading}
            className="rounded-md border border-gray-300 px-3 py-1.5 text-xs font-medium text-gray-900 hover:bg-gray-100 disabled:opacity-60"
          >
            Refresh
          </button>
        </div>
        <div className="grid gap-2 sm:grid-cols-4">
          <article className="rounded-lg border border-gray-200 p-3">
            <p className="text-xs text-gray-500">Total Calls</p>
            <p className="mt-1 text-lg font-semibold text-gray-900">{overview?.kpis.total_calls ?? 0}</p>
          </article>
          <article className="rounded-lg border border-gray-200 p-3">
            <p className="text-xs text-gray-500">Success Rate</p>
            <p className="mt-1 text-lg font-semibold text-emerald-700">{((overview?.kpis.success_rate ?? 0) * 100).toFixed(1)}%</p>
          </article>
          <article className="rounded-lg border border-gray-200 p-3">
            <p className="text-xs text-gray-500">Fail Rate</p>
            <p className="mt-1 text-lg font-semibold text-rose-700">{((overview?.kpis.fail_rate ?? 0) * 100).toFixed(1)}%</p>
          </article>
          <article className="rounded-lg border border-gray-200 p-3">
            <p className="text-xs text-gray-500">Avg / P95 Latency</p>
            <p className="mt-1 text-lg font-semibold text-indigo-700">
              {Math.round(overview?.kpis.avg_latency_ms ?? 0)} / {overview?.kpis.p95_latency_ms ?? 0} ms
            </p>
          </article>
          <article className="rounded-lg border border-gray-200 p-3">
            <p className="text-xs text-gray-500">Retry Rate</p>
            <p className="mt-1 text-lg font-semibold text-indigo-700">{((overview?.kpis.retry_rate ?? 0) * 100).toFixed(1)}%</p>
          </article>
          <article className="rounded-lg border border-gray-200 p-3">
            <p className="text-xs text-gray-500">Policy Block Rate</p>
            <p className="mt-1 text-lg font-semibold text-amber-700">{((overview?.kpis.policy_block_rate ?? 0) * 100).toFixed(1)}%</p>
          </article>
        </div>
        {overviewError ? <p className="mt-2 text-xs text-red-600">{overviewError}</p> : null}
        {overviewLoading ? <p className="mt-2 text-xs text-gray-500">Loading overview...</p> : null}
        <div className="mt-4 grid gap-2 sm:grid-cols-3">
          <article className="rounded-lg border border-gray-200 p-3">
            <p className="text-xs font-medium text-gray-700">Top Called</p>
            <div className="mt-2 space-y-1">
              {(overview?.top.called_tools ?? []).slice(0, 5).map((item) => (
                <p key={`called-${item.tool_name}`} className="text-xs text-gray-700">
                  {item.tool_name}: {item.count}
                </p>
              ))}
            </div>
          </article>
          <article className="rounded-lg border border-gray-200 p-3">
            <p className="text-xs font-medium text-gray-700">Top Failed</p>
            <div className="mt-2 space-y-1">
              {(overview?.top.failed_tools ?? []).slice(0, 5).map((item) => (
                <p key={`failed-${item.tool_name}`} className="text-xs text-gray-700">
                  {item.tool_name}: {item.count}
                </p>
              ))}
            </div>
          </article>
          <article className="rounded-lg border border-gray-200 p-3">
            <p className="text-xs font-medium text-gray-700">Top Blocked</p>
            <div className="mt-2 space-y-1">
              {(overview?.top.blocked_tools ?? []).slice(0, 5).map((item) => (
                <p key={`blocked-${item.tool_name}`} className="text-xs text-gray-700">
                  {item.tool_name}: {item.count}
                </p>
              ))}
            </div>
          </article>
        </div>
        {(overview?.anomalies?.length ?? 0) > 0 ? (
          <div className="mt-4 rounded-lg border border-amber-200 bg-amber-50 p-3">
            <p className="text-xs font-medium text-amber-900">Recent anomalies</p>
            <div className="mt-2 space-y-1">
              {overview?.anomalies.map((anomaly, idx) => (
                <p key={`${anomaly.type}-${idx}`} className="text-xs text-amber-900">
                  [{anomaly.severity}] {anomaly.message}
                </p>
              ))}
            </div>
          </div>
        ) : null}
      </section>

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
          <select
            value={newApiKeyTeamId}
            onChange={(event) => setNewApiKeyTeamId(event.target.value)}
            className="rounded-md border border-gray-300 px-3 py-2 text-sm"
          >
            <option value="">No team scope</option>
            {teams.map((team) => (
              <option key={`new-key-team-${team.id}`} value={String(team.id)}>
                Team #{team.id} - {team.name}
              </option>
            ))}
          </select>
          <input
            value={newApiKeyAllowedTools}
            onChange={(event) => setNewApiKeyAllowedTools(event.target.value)}
            placeholder="Allowed tools (comma separated)"
            className="min-w-[260px] rounded-md border border-gray-300 px-3 py-2 text-sm"
          />
          <input
            value={newApiKeyTags}
            onChange={(event) => setNewApiKeyTags(event.target.value)}
            placeholder="Tags (comma separated)"
            className="min-w-[220px] rounded-md border border-gray-300 px-3 py-2 text-sm"
          />
          <input
            value={newApiKeyMemo}
            onChange={(event) => setNewApiKeyMemo(event.target.value)}
            placeholder="Memo"
            className="min-w-[220px] rounded-md border border-gray-300 px-3 py-2 text-sm"
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
        <textarea
          value={newApiKeyPolicyJson}
          onChange={(event) => setNewApiKeyPolicyJson(event.target.value)}
          placeholder='Policy JSON (optional), e.g. {"deny_tools":["linear_list_issues"]}'
          className="mt-2 min-h-[72px] w-full rounded-md border border-gray-300 px-3 py-2 text-xs"
        />
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
                    {key.key_prefix}... · {key.is_active ? "active" : "revoked"} · team: {key.team_id ?? "none"}
                  </p>
                  <p className="text-xs text-gray-500">
                    issued_by: {key.issued_by ?? "n/a"} · last_used: {key.last_used_at ? new Date(key.last_used_at).toLocaleString() : "never"}
                  </p>
                  <div className="mt-2 flex flex-wrap items-center gap-2">
                    <select
                      value={apiKeyTeamDraft[key.id] ?? ""}
                      onChange={(event) =>
                        setApiKeyTeamDraft((prev) => ({
                          ...prev,
                          [key.id]: event.target.value,
                        }))
                      }
                      className="min-w-[200px] rounded-md border border-gray-300 px-2 py-1 text-xs"
                    >
                      <option value="">No team scope</option>
                      {teams.map((team) => (
                        <option key={`key-${key.id}-team-${team.id}`} value={String(team.id)}>
                          Team #{team.id} - {team.name}
                        </option>
                      ))}
                    </select>
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
                    <input
                      value={apiKeyTagsDraft[key.id] ?? ""}
                      onChange={(event) =>
                        setApiKeyTagsDraft((prev) => ({
                          ...prev,
                          [key.id]: event.target.value,
                        }))
                      }
                      placeholder="Tags (comma separated)"
                      className="min-w-[220px] rounded-md border border-gray-300 px-2 py-1 text-xs"
                    />
                    <input
                      value={apiKeyMemoDraft[key.id] ?? ""}
                      onChange={(event) =>
                        setApiKeyMemoDraft((prev) => ({
                          ...prev,
                          [key.id]: event.target.value,
                        }))
                      }
                      placeholder="Memo"
                      className="min-w-[220px] rounded-md border border-gray-300 px-2 py-1 text-xs"
                    />
                    <button
                      type="button"
                      onClick={() => void handleUpdateApiKeySettings(key.id)}
                      disabled={updatingApiKeyId === key.id}
                      className="rounded-md border border-gray-300 px-2 py-1 text-xs font-medium text-gray-900 hover:bg-gray-100 disabled:opacity-60"
                    >
                      {updatingApiKeyId === key.id ? "Saving..." : "Save key settings"}
                    </button>
                    <button
                      type="button"
                      onClick={() => void handleRotateApiKey(key.id)}
                      disabled={!key.is_active || rotatingApiKeyId === key.id}
                      className="rounded-md border border-gray-300 px-2 py-1 text-xs font-medium text-gray-900 hover:bg-gray-100 disabled:opacity-60"
                    >
                      {rotatingApiKeyId === key.id ? "Rotating..." : "Rotate"}
                    </button>
                    <button
                      type="button"
                      onClick={() => void fetchApiKeyDrilldown(key.id)}
                      disabled={apiKeyDrilldownLoadingId === key.id}
                      className="rounded-md border border-gray-300 px-2 py-1 text-xs font-medium text-gray-900 hover:bg-gray-100 disabled:opacity-60"
                    >
                      {apiKeyDrilldownLoadingId === key.id ? "Loading..." : "Load Drill-down"}
                    </button>
                  </div>
                  <textarea
                    value={apiKeyPolicyDraft[key.id] ?? ""}
                    onChange={(event) =>
                      setApiKeyPolicyDraft((prev) => ({
                        ...prev,
                        [key.id]: event.target.value,
                      }))
                    }
                    placeholder='Policy JSON, e.g. {"allowed_services":["notion"],"deny_tools":["linear_list_issues"]}'
                    className="mt-2 min-h-[80px] w-full rounded-md border border-gray-300 px-2 py-1 text-xs"
                  />
                  <div className="mt-2 flex gap-2">
                    <button
                      type="button"
                      onClick={() => void handleUpdateApiKeySettings(key.id)}
                      disabled={updatingApiKeyId === key.id}
                      className="rounded-md border border-gray-300 px-2 py-1 text-xs font-medium text-gray-900 hover:bg-gray-100 disabled:opacity-60"
                    >
                      {updatingApiKeyId === key.id ? "Saving..." : "Save policy JSON"}
                    </button>
                  </div>
                  {apiKeyDrilldown[key.id] ? (
                    <div className="mt-2 rounded-md border border-gray-200 bg-gray-50 p-2">
                      <p className="text-xs font-medium text-gray-700">Key Drill-down (7d)</p>
                      <p className="mt-1 text-xs text-gray-700">
                        calls {apiKeyDrilldown[key.id].summary.total_calls} · success{" "}
                        {(apiKeyDrilldown[key.id].summary.success_rate * 100).toFixed(1)}% · fail{" "}
                        {(apiKeyDrilldown[key.id].summary.fail_rate * 100).toFixed(1)}% · avg/p95{" "}
                        {Math.round(apiKeyDrilldown[key.id].summary.avg_latency_ms)}/{apiKeyDrilldown[key.id].summary.p95_latency_ms}ms
                      </p>
                      <div className="mt-1 space-y-1">
                        {apiKeyDrilldown[key.id].top_error_codes.slice(0, 4).map((item) => (
                          <p key={`key-${key.id}-err-${item.error_code}`} className="text-[11px] text-gray-600">
                            error {item.error_code}: {item.count}
                          </p>
                        ))}
                      </div>
                    </div>
                  ) : null}
                  <p className="mt-1 text-xs text-gray-500">Empty value means all Phase 1 tools are allowed.</p>
                </div>
                <div className="flex flex-col gap-2">
                  <button
                    type="button"
                    onClick={() => void handleRevokeApiKey(key.id)}
                    disabled={!key.is_active || revokingApiKeyId === key.id}
                    className="rounded-md border border-gray-300 px-3 py-1.5 text-xs font-medium text-gray-900 hover:bg-gray-100 disabled:opacity-60"
                  >
                    {revokingApiKeyId === key.id ? "Revoking..." : "Revoke"}
                  </button>
                </div>
              </article>
            ))
          )}
        </div>
      </section>

      <section className="mb-8 rounded-xl border border-gray-200 p-5">
        <h2 className="text-base font-semibold text-gray-900">Policy Simulator</h2>
        <p className="mt-1 text-sm text-gray-600">Preview whether a request is allowed or blocked before execution.</p>
        <div className="mt-4 flex flex-wrap items-center gap-2">
          <select
            value={simulatorApiKeyId}
            onChange={(event) => setSimulatorApiKeyId(event.target.value)}
            className="rounded-md border border-gray-300 px-3 py-2 text-xs"
          >
            <option value="">No API key scope</option>
            {apiKeys.map((key) => (
              <option key={key.id} value={String(key.id)}>
                {key.name} ({key.key_prefix}...)
              </option>
            ))}
          </select>
          <input
            value={simulatorToolName}
            onChange={(event) => setSimulatorToolName(event.target.value)}
            placeholder="Tool name"
            className="min-w-[240px] rounded-md border border-gray-300 px-3 py-2 text-xs"
          />
          <button
            type="button"
            onClick={() => void runPolicySimulation()}
            disabled={simulatorLoading}
            className="rounded-md border border-gray-300 px-3 py-2 text-xs font-medium text-gray-900 hover:bg-gray-100 disabled:opacity-60"
          >
            {simulatorLoading ? "Simulating..." : "Simulate"}
          </button>
        </div>
        <textarea
          value={simulatorArguments}
          onChange={(event) => setSimulatorArguments(event.target.value)}
          placeholder='Arguments JSON, e.g. {"team_id":"team-a","title":"hello"}'
          className="mt-2 min-h-[80px] w-full rounded-md border border-gray-300 px-3 py-2 text-xs"
        />
        {simulatorError ? <p className="mt-2 text-xs text-red-600">{simulatorError}</p> : null}
        {simulatorResult ? (
          <div className="mt-3 rounded-md border border-gray-200 bg-gray-50 p-3">
            <p className="text-xs font-medium text-gray-800">
              Decision: <span className={simulatorResult.decision === "allowed" ? "text-emerald-700" : "text-rose-700"}>{simulatorResult.decision}</span>
            </p>
            <pre className="mt-2 overflow-x-auto text-[11px] text-gray-700">{JSON.stringify(simulatorResult, null, 2)}</pre>
          </div>
        ) : null}
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

      <section className="mb-8 rounded-xl border border-gray-200 p-5">
        <div className="mb-4 flex items-center justify-between gap-2">
          <div>
            <h2 className="text-base font-semibold text-gray-900">Usage Trends (7d)</h2>
            <p className="mt-1 text-sm text-gray-600">Volume, quality trend, failure categories, and connector health.</p>
          </div>
          <button
            type="button"
            onClick={() => void fetchTrendAndBreakdown()}
            disabled={trendLoading}
            className="rounded-md border border-gray-300 px-3 py-1.5 text-xs font-medium text-gray-900 hover:bg-gray-100 disabled:opacity-60"
          >
            Refresh
          </button>
        </div>
        {trendError ? <p className="mb-2 text-xs text-red-600">{trendError}</p> : null}
        {trendLoading ? <p className="mb-2 text-xs text-gray-500">Loading trends...</p> : null}
        <div className="grid gap-2 sm:grid-cols-2">
          <article className="rounded-lg border border-gray-200 p-3">
            <p className="text-xs font-medium text-gray-700">Daily Calls Trend</p>
            <div className="mt-2 space-y-1">
              {trendPoints.slice(-7).map((point) => (
                <p key={point.bucket_start} className="text-xs text-gray-700">
                  {new Date(point.bucket_start).toLocaleDateString()}: {point.calls} calls, fail {(point.fail_rate * 100).toFixed(1)}%
                </p>
              ))}
            </div>
          </article>
          <article className="rounded-lg border border-gray-200 p-3">
            <p className="text-xs font-medium text-gray-700">Failure Categories</p>
            <div className="mt-2 space-y-1">
              {(failureBreakdown?.categories ?? []).slice(0, 6).map((item) => (
                <p key={item.category} className="text-xs text-gray-700">
                  {item.category}: {item.count} ({(item.ratio * 100).toFixed(1)}%)
                </p>
              ))}
            </div>
          </article>
          <article className="rounded-lg border border-gray-200 p-3">
            <p className="text-xs font-medium text-gray-700">Top Failure Codes</p>
            <div className="mt-2 space-y-1">
              {(failureBreakdown?.error_codes ?? []).slice(0, 6).map((item) => (
                <p key={item.error_code} className="text-xs text-gray-700">
                  {item.error_code}: {item.count}
                </p>
              ))}
            </div>
          </article>
          <article className="rounded-lg border border-gray-200 p-3">
            <p className="text-xs font-medium text-gray-700">Connector Health</p>
            <div className="mt-2 space-y-1">
              {connectorSummary.map((item) => (
                <p key={item.connector} className="text-xs text-gray-700">
                  {item.connector}: calls {item.calls}, fail {(item.fail_rate * 100).toFixed(1)}%, avg {Math.round(item.avg_latency_ms)}ms
                </p>
              ))}
            </div>
          </article>
        </div>
      </section>

      <section className="rounded-xl border border-gray-200 p-5">
        <div className="mb-4 flex items-center justify-between gap-2">
          <div>
            <h2 className="text-base font-semibold text-gray-900">Audit Events</h2>
            <p className="mt-1 text-sm text-gray-600">Who ran what, and whether it was allowed or blocked.</p>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => void handleExportAudit("jsonl")}
              className="rounded-md border border-gray-300 px-3 py-1.5 text-xs font-medium text-gray-900 hover:bg-gray-100 disabled:opacity-60"
            >
              Export JSONL
            </button>
            <button
              type="button"
              onClick={() => void handleExportAudit("csv")}
              className="rounded-md border border-gray-300 px-3 py-1.5 text-xs font-medium text-gray-900 hover:bg-gray-100 disabled:opacity-60"
            >
              Export CSV
            </button>
            <button
              type="button"
              onClick={() => void Promise.all([fetchAuditEvents(), fetchAuditSettings()])}
              disabled={auditLoading || auditSettingsLoading}
              className="rounded-md border border-gray-300 px-3 py-1.5 text-xs font-medium text-gray-900 hover:bg-gray-100 disabled:opacity-60"
            >
              Refresh
            </button>
          </div>
        </div>

        <div className="mb-4 rounded-lg border border-gray-200 bg-gray-50 p-3">
          <p className="text-xs font-medium text-gray-700">Audit Settings</p>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <label className="text-xs text-gray-700">Retention days</label>
            <input
              type="number"
              min={1}
              value={auditRetentionDraft}
              onChange={(event) => setAuditRetentionDraft(event.target.value)}
              className="w-24 rounded-md border border-gray-300 px-2 py-1 text-xs"
            />
            <label className="flex items-center gap-1 text-xs text-gray-700">
              <input
                type="checkbox"
                checked={auditExportEnabledDraft}
                onChange={(event) => setAuditExportEnabledDraft(event.target.checked)}
              />
              export enabled
            </label>
            <button
              type="button"
              onClick={() => void handleSaveAuditSettings()}
              disabled={auditSettingsSaving}
              className="rounded-md border border-gray-300 px-2 py-1 text-xs font-medium text-gray-900 hover:bg-gray-100 disabled:opacity-60"
            >
              {auditSettingsSaving ? "Saving..." : "Save Settings"}
            </button>
          </div>
          <textarea
            value={auditMaskingPolicyDraft}
            onChange={(event) => setAuditMaskingPolicyDraft(event.target.value)}
            placeholder='Masking policy JSON, e.g. {"mask_keys":["token","secret"]}'
            className="mt-2 min-h-[74px] w-full rounded-md border border-gray-300 px-2 py-1 text-xs"
          />
          <p className="mt-1 text-[11px] text-gray-500">
            updated_at: {auditSettings?.updated_at ? new Date(auditSettings.updated_at).toLocaleString() : "n/a"}
          </p>
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
                <div className="mt-2">
                  <button
                    type="button"
                    onClick={() => void fetchAuditEventDetail(event.id)}
                    disabled={auditDetailLoading}
                    className="rounded-md border border-gray-300 px-2 py-1 text-xs font-medium text-gray-900 hover:bg-gray-100 disabled:opacity-60"
                  >
                    {auditDetailLoading ? "Loading..." : "Details"}
                  </button>
                </div>
              </article>
            ))
          )}
        </div>
        {auditDetail ? (
          <div className="mt-4 rounded-lg border border-gray-200 bg-gray-50 p-3">
            <p className="text-xs font-medium text-gray-800">Selected Audit Detail: #{auditDetail.id}</p>
            <pre className="mt-2 overflow-x-auto text-[11px] text-gray-700">{JSON.stringify(auditDetail, null, 2)}</pre>
          </div>
        ) : null}
      </section>

      <section className="mt-8 rounded-xl border border-gray-200 p-5">
        <div className="mb-4 flex items-center justify-between gap-2">
          <div>
            <h2 className="text-base font-semibold text-gray-900">Team Policy</h2>
            <p className="mt-1 text-sm text-gray-600">Manage team-level default policies and membership scope.</p>
          </div>
          <button
            type="button"
            onClick={() => void fetchTeams()}
            disabled={teamsLoading}
            className="rounded-md border border-gray-300 px-3 py-1.5 text-xs font-medium text-gray-900 hover:bg-gray-100 disabled:opacity-60"
          >
            Refresh
          </button>
        </div>
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <input
            value={newTeamName}
            onChange={(event) => setNewTeamName(event.target.value)}
            placeholder="Team name"
            className="rounded-md border border-gray-300 px-3 py-2 text-xs"
          />
          <input
            value={newTeamDescription}
            onChange={(event) => setNewTeamDescription(event.target.value)}
            placeholder="Description (optional)"
            className="min-w-[220px] rounded-md border border-gray-300 px-3 py-2 text-xs"
          />
          <button
            type="button"
            onClick={() => void handleCreateTeam()}
            disabled={creatingTeam}
            className="rounded-md border border-gray-300 px-3 py-2 text-xs font-medium text-gray-900 hover:bg-gray-100 disabled:opacity-60"
          >
            {creatingTeam ? "Creating..." : "Create Team"}
          </button>
        </div>
        <textarea
          value={newTeamPolicyJson}
          onChange={(event) => setNewTeamPolicyJson(event.target.value)}
          placeholder='Team policy JSON (optional), e.g. {"allowed_services":["notion"],"deny_tools":["linear_list_issues"]}'
          className="min-h-[72px] w-full rounded-md border border-gray-300 px-3 py-2 text-xs"
        />
        {teamsError ? <p className="mt-2 text-xs text-red-600">{teamsError}</p> : null}
        {teamsLoading ? <p className="mt-2 text-xs text-gray-500">Loading teams...</p> : null}
        <div className="mt-3 space-y-2">
          {teams.length === 0 ? (
            <p className="text-xs text-gray-500">No teams yet.</p>
          ) : (
            teams.map((team) => (
              <article key={team.id} className="rounded-lg border border-gray-200 p-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="text-sm font-medium text-gray-900">Team #{team.id}</p>
                  <label className="flex items-center gap-1 text-xs text-gray-700">
                    <input
                      type="checkbox"
                      checked={Boolean(teamActiveDraft[team.id])}
                      onChange={(event) =>
                        setTeamActiveDraft((prev) => ({
                          ...prev,
                          [team.id]: event.target.checked,
                        }))
                      }
                    />
                    active
                  </label>
                </div>
                <p className="mt-1 text-xs text-gray-500">
                  policy updated {team.policy_updated_at ? new Date(team.policy_updated_at).toLocaleString() : "n/a"}
                </p>
                <div className="mt-2 grid gap-2 sm:grid-cols-2">
                  <input
                    value={teamNameDraft[team.id] ?? ""}
                    onChange={(event) =>
                      setTeamNameDraft((prev) => ({
                        ...prev,
                        [team.id]: event.target.value,
                      }))
                    }
                    placeholder="Team name"
                    className="rounded-md border border-gray-300 px-2 py-1 text-xs"
                  />
                  <input
                    value={teamDescriptionDraft[team.id] ?? ""}
                    onChange={(event) =>
                      setTeamDescriptionDraft((prev) => ({
                        ...prev,
                        [team.id]: event.target.value,
                      }))
                    }
                    placeholder="Description"
                    className="rounded-md border border-gray-300 px-2 py-1 text-xs"
                  />
                </div>
                <textarea
                  value={teamPolicyDraft[team.id] ?? ""}
                  onChange={(event) =>
                    setTeamPolicyDraft((prev) => ({
                      ...prev,
                      [team.id]: event.target.value,
                    }))
                  }
                  placeholder='Policy JSON, e.g. {"allowed_services":["notion"],"deny_tools":["linear_list_issues"]}'
                  className="mt-2 min-h-[92px] w-full rounded-md border border-gray-300 px-2 py-1 text-xs"
                />
                <div className="mt-2 flex flex-wrap items-center gap-2">
                  <button
                    type="button"
                    onClick={() => void handleUpdateTeam(team.id)}
                    disabled={teamUpdateLoadingId === team.id}
                    className="rounded-md border border-gray-300 px-2 py-1 text-xs font-medium text-gray-900 hover:bg-gray-100 disabled:opacity-60"
                  >
                    {teamUpdateLoadingId === team.id ? "Saving..." : "Save Team Policy"}
                  </button>
                  <button
                    type="button"
                    onClick={() => void fetchTeamRevisions(team.id)}
                    disabled={teamRevisionLoadingId === team.id}
                    className="rounded-md border border-gray-300 px-2 py-1 text-xs font-medium text-gray-900 hover:bg-gray-100 disabled:opacity-60"
                  >
                    {teamRevisionLoadingId === team.id ? "Loading..." : "Load Revisions"}
                  </button>
                </div>
                {(teamRevisions[team.id] ?? []).length > 0 ? (
                  <div className="mt-2 rounded-md border border-gray-200 bg-gray-50 p-2">
                    <p className="text-xs font-medium text-gray-700">Policy Revisions</p>
                    <div className="mt-2 space-y-2">
                      {(teamRevisions[team.id] ?? []).slice(0, 10).map((revision) => (
                        <div key={revision.id} className="rounded border border-gray-200 bg-white p-2">
                          <p className="text-[11px] text-gray-600">
                            #{revision.id} · {revision.source} · {new Date(revision.created_at).toLocaleString()}
                          </p>
                          <div className="mt-1">
                            <button
                              type="button"
                              onClick={() => void handleRollbackTeamRevision(team.id, revision.id)}
                              disabled={teamRollbackLoadingId === revision.id}
                              className="rounded-md border border-gray-300 px-2 py-1 text-[11px] font-medium text-gray-900 hover:bg-gray-100 disabled:opacity-60"
                            >
                              {teamRollbackLoadingId === revision.id ? "Rolling back..." : "Rollback to this revision"}
                            </button>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                ) : null}
                <div className="mt-3 rounded-md border border-gray-200 p-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <button
                      type="button"
                      onClick={() => void fetchTeamMembers(team.id)}
                      disabled={teamMembersLoadingId === team.id}
                      className="rounded-md border border-gray-300 px-2 py-1 text-xs font-medium text-gray-900 hover:bg-gray-100 disabled:opacity-60"
                    >
                      {teamMembersLoadingId === team.id ? "Loading..." : "Load Members"}
                    </button>
                    <input
                      value={teamMemberUserDraft[team.id] ?? ""}
                      onChange={(event) =>
                        setTeamMemberUserDraft((prev) => ({
                          ...prev,
                          [team.id]: event.target.value,
                        }))
                      }
                      placeholder="member user_id (uuid)"
                      className="min-w-[260px] rounded-md border border-gray-300 px-2 py-1 text-xs"
                    />
                    <select
                      value={teamMemberRoleDraft[team.id] ?? "member"}
                      onChange={(event) =>
                        setTeamMemberRoleDraft((prev) => ({
                          ...prev,
                          [team.id]: event.target.value,
                        }))
                      }
                      className="rounded-md border border-gray-300 px-2 py-1 text-xs"
                    >
                      <option value="member">member</option>
                      <option value="admin">admin</option>
                    </select>
                    <button
                      type="button"
                      onClick={() => void handleUpsertTeamMember(team.id)}
                      disabled={teamMemberActionLoadingId === team.id}
                      className="rounded-md border border-gray-300 px-2 py-1 text-xs font-medium text-gray-900 hover:bg-gray-100 disabled:opacity-60"
                    >
                      {teamMemberActionLoadingId === team.id ? "Saving..." : "Add / Update Member"}
                    </button>
                  </div>
                  {(teamMembers[team.id] ?? []).length > 0 ? (
                    <div className="mt-2 space-y-1">
                      {(teamMembers[team.id] ?? []).map((member) => (
                        <div key={`team-${team.id}-member-${member.id}`} className="flex items-center justify-between gap-2">
                          <p className="text-xs text-gray-700">
                            {member.user_id} · {member.role}
                          </p>
                          <button
                            type="button"
                            onClick={() => void handleDeleteTeamMember(team.id, member.id)}
                            disabled={teamMemberDeleteLoadingId === member.id}
                            className="rounded-md border border-gray-300 px-2 py-1 text-[11px] font-medium text-gray-900 hover:bg-gray-100 disabled:opacity-60"
                          >
                            {teamMemberDeleteLoadingId === member.id ? "Deleting..." : "Delete"}
                          </button>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="mt-2 text-xs text-gray-500">No loaded members.</p>
                  )}
                </div>
              </article>
            ))
          )}
        </div>
      </section>

      <section className="mt-8 rounded-xl border border-gray-200 p-5">
        <div className="mb-4 flex items-center justify-between gap-2">
          <div>
            <h2 className="text-base font-semibold text-gray-900">Integrations (Webhook)</h2>
            <p className="mt-1 text-sm text-gray-600">Manage event subscriptions and delivery status.</p>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => void handleProcessWebhookRetries()}
              disabled={processingWebhookRetries}
              className="rounded-md border border-gray-300 px-3 py-1.5 text-xs font-medium text-gray-900 hover:bg-gray-100 disabled:opacity-60"
            >
              {processingWebhookRetries ? "Processing..." : "Process Retries"}
            </button>
            <button
              type="button"
              onClick={() => void fetchIntegrations()}
              disabled={integrationsLoading}
              className="rounded-md border border-gray-300 px-3 py-1.5 text-xs font-medium text-gray-900 hover:bg-gray-100 disabled:opacity-60"
            >
              Refresh
            </button>
          </div>
        </div>
        <div className="grid gap-2 sm:grid-cols-2">
          <input
            value={newWebhookName}
            onChange={(event) => setNewWebhookName(event.target.value)}
            placeholder="Webhook name"
            className="rounded-md border border-gray-300 px-3 py-2 text-xs"
          />
          <input
            value={newWebhookUrl}
            onChange={(event) => setNewWebhookUrl(event.target.value)}
            placeholder="Endpoint URL"
            className="rounded-md border border-gray-300 px-3 py-2 text-xs"
          />
          <input
            value={newWebhookSecret}
            onChange={(event) => setNewWebhookSecret(event.target.value)}
            placeholder="Secret (optional)"
            className="rounded-md border border-gray-300 px-3 py-2 text-xs"
          />
          <input
            value={newWebhookEvents}
            onChange={(event) => setNewWebhookEvents(event.target.value)}
            placeholder="Event types (comma separated)"
            className="rounded-md border border-gray-300 px-3 py-2 text-xs"
          />
        </div>
        <button
          type="button"
          onClick={() => void handleCreateWebhook()}
          disabled={creatingWebhook}
          className="mt-2 rounded-md border border-gray-300 px-3 py-2 text-xs font-medium text-gray-900 hover:bg-gray-100 disabled:opacity-60"
        >
          {creatingWebhook ? "Creating..." : "Create Webhook"}
        </button>
        {integrationsError ? <p className="mt-2 text-xs text-red-600">{integrationsError}</p> : null}
        {integrationsLoading ? <p className="mt-2 text-xs text-gray-500">Loading webhooks...</p> : null}
        <div className="mt-3 grid gap-2 sm:grid-cols-2">
          <article className="rounded-lg border border-gray-200 p-3">
            <p className="text-xs font-medium text-gray-700">Subscriptions</p>
            <div className="mt-2 space-y-1">
              {webhooks.length === 0 ? (
                <p className="text-xs text-gray-500">No subscriptions.</p>
              ) : (
                webhooks.slice(0, 8).map((hook) => (
                  <p key={hook.id} className="text-xs text-gray-700">
                    {hook.name} ({hook.is_active ? "active" : "disabled"}) · {hook.event_types.join(", ")}
                  </p>
                ))
              )}
            </div>
          </article>
          <article className="rounded-lg border border-gray-200 p-3">
            <p className="text-xs font-medium text-gray-700">Recent Deliveries</p>
            <div className="mt-2 space-y-1">
              {deliveries.length === 0 ? (
                <p className="text-xs text-gray-500">No deliveries.</p>
              ) : (
                deliveries.slice(0, 8).map((delivery) => (
                  <p key={delivery.id} className="text-xs text-gray-700">
                    #{delivery.id} {delivery.event_type} · {delivery.status}
                    {delivery.http_status ? ` (${delivery.http_status})` : ""} · retry {delivery.retry_count}
                    {delivery.next_retry_at ? ` · next ${new Date(delivery.next_retry_at).toLocaleString()}` : ""}
                  </p>
                ))
              )}
            </div>
          </article>
        </div>
      </section>

      <section className="mt-8 rounded-xl border border-gray-200 p-5">
        <div className="mb-4 flex items-center justify-between gap-2">
          <div>
            <h2 className="text-base font-semibold text-gray-900">Admin / Ops</h2>
            <p className="mt-1 text-sm text-gray-600">Connector diagnostics, rate-limit events, and system health.</p>
          </div>
          <button
            type="button"
            onClick={() => void fetchAdminOps()}
            disabled={adminLoading}
            className="rounded-md border border-gray-300 px-3 py-1.5 text-xs font-medium text-gray-900 hover:bg-gray-100 disabled:opacity-60"
          >
            Refresh
          </button>
        </div>
        {adminError ? <p className="mb-2 text-xs text-red-600">{adminError}</p> : null}
        {adminLoading ? <p className="mb-2 text-xs text-gray-500">Loading diagnostics...</p> : null}
        <div className="grid gap-2 sm:grid-cols-2">
          <article className="rounded-lg border border-gray-200 p-3">
            <p className="text-xs font-medium text-gray-700">System Health</p>
            <p className="mt-1 text-sm font-semibold text-gray-900">{systemHealth?.status ?? "unknown"}</p>
            <p className="mt-1 text-xs text-gray-500">
              DB: {systemHealth?.services.database.ok ? "ok" : "degraded"}
              {systemHealth?.services.database.error ? ` (${systemHealth.services.database.error})` : ""}
            </p>
          </article>
          <article className="rounded-lg border border-gray-200 p-3">
            <p className="text-xs font-medium text-gray-700">Incident Banner</p>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <label className="flex items-center gap-1 text-xs text-gray-700">
                <input
                  type="checkbox"
                  checked={incidentEnabledDraft}
                  onChange={(event) => setIncidentEnabledDraft(event.target.checked)}
                />
                enabled
              </label>
              <select
                value={incidentSeverityDraft}
                onChange={(event) => setIncidentSeverityDraft(event.target.value as "info" | "warning" | "critical")}
                className="rounded-md border border-gray-300 px-2 py-1 text-xs"
              >
                <option value="info">info</option>
                <option value="warning">warning</option>
                <option value="critical">critical</option>
              </select>
              <button
                type="button"
                onClick={() => void handleSaveIncidentBanner()}
                disabled={incidentSaving}
                className="rounded-md border border-gray-300 px-2 py-1 text-xs font-medium text-gray-900 hover:bg-gray-100 disabled:opacity-60"
              >
                {incidentSaving ? "Saving..." : "Save Banner"}
              </button>
            </div>
            <input
              value={incidentMessageDraft}
              onChange={(event) => setIncidentMessageDraft(event.target.value)}
              placeholder="Incident message"
              className="mt-2 w-full rounded-md border border-gray-300 px-2 py-1 text-xs"
            />
            <div className="mt-2 grid gap-2 sm:grid-cols-2">
              <input
                type="datetime-local"
                value={incidentStartsAtDraft}
                onChange={(event) => setIncidentStartsAtDraft(event.target.value)}
                className="rounded-md border border-gray-300 px-2 py-1 text-xs"
              />
              <input
                type="datetime-local"
                value={incidentEndsAtDraft}
                onChange={(event) => setIncidentEndsAtDraft(event.target.value)}
                className="rounded-md border border-gray-300 px-2 py-1 text-xs"
              />
            </div>
            <p className="mt-1 text-[11px] text-gray-500">
              updated: {incidentBanner?.updated_at ? new Date(incidentBanner.updated_at).toLocaleString() : "n/a"}
            </p>
          </article>
        </div>

        <div className="mt-2 grid gap-2 sm:grid-cols-3">
          <article className="rounded-lg border border-gray-200 p-3">
            <p className="text-xs font-medium text-gray-700">Connector Diagnostics</p>
            <div className="mt-2 space-y-1">
              {connectorDiagnostics.length === 0 ? (
                <p className="text-xs text-gray-500">No diagnostics.</p>
              ) : (
                connectorDiagnostics.slice(0, 8).map((item, idx) => (
                  <p key={`${item.provider}-${idx}`} className="text-xs text-gray-700">
                    {item.provider}: {item.workspace_name ?? item.workspace_id ?? "n/a"} ({item.status})
                  </p>
                ))
              )}
            </div>
          </article>
          <article className="rounded-lg border border-gray-200 p-3">
            <p className="text-xs font-medium text-gray-700">External Connector Health (24h)</p>
            <div className="mt-2 space-y-1">
              {externalHealth.length === 0 ? (
                <p className="text-xs text-gray-500">No health samples.</p>
              ) : (
                externalHealth.slice(0, 8).map((item) => (
                  <p key={item.connector} className="text-xs text-gray-700">
                    {item.connector}: {item.status} · fail {(item.fail_rate * 100).toFixed(1)}% · calls {item.calls}
                  </p>
                ))
              )}
            </div>
          </article>
          <article className="rounded-lg border border-gray-200 p-3">
            <p className="text-xs font-medium text-gray-700">Rate-limit / Quota Hits</p>
            <div className="mt-2 space-y-1">
              {rateLimitEvents.length === 0 ? (
                <p className="text-xs text-gray-500">No events.</p>
              ) : (
                rateLimitEvents.slice(0, 8).map((item) => (
                  <p key={item.id} className="text-xs text-gray-700">
                    {item.error_code}: {item.tool_name}
                  </p>
                ))
              )}
            </div>
          </article>
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
