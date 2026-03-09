"use client";

import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { useCallback, useEffect, useMemo, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Loader2 } from "lucide-react";

import { buildNextPath, dashboardApiGet, dashboardApiRequest } from "../../../../../lib/dashboard-v2-client";
import { resolveDashboardScope } from "../../../../../lib/dashboard-scope";
import PageTitleWithTooltip from "@/components/dashboard-v2/page-title-with-tooltip";

type PermissionSnapshot = {
  permissions?: {
    can_manage_integrations?: boolean;
  };
};

type WebhookItem = {
  id: number;
  name: string;
  endpoint_url: string;
  event_types: string[];
  is_active: boolean;
  last_delivery_at: string | null;
  created_at: string | null;
  updated_at: string | null;
};

type DeliveryItem = {
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

type WebhookProvider = "slack" | "generic";

type EventPreset = {
  id: string;
  label: string;
  events: string[];
};

function formatDate(value?: string | null): string {
  if (!value) {
    return "-";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString();
}

function normalizeEventTypes(value: string[]): string[] {
  return Array.from(new Set(value.map((item) => item.trim()).filter((item) => item.length > 0)));
}

function validateWebhookUrl(provider: WebhookProvider, rawUrl: string): { valid: boolean; message: string } {
  const value = rawUrl.trim();
  if (!value) {
    return { valid: false, message: "Webhook URL is required." };
  }
  if (provider === "slack") {
    const slackPattern = /^https:\/\/hooks\.slack\.com\/services\/[^/]+\/[^/]+\/[^/]+$/;
    if (!slackPattern.test(value)) {
      return { valid: false, message: "Use a valid Slack Incoming Webhook URL format." };
    }
    return { valid: true, message: "Slack webhook URL format looks valid." };
  }
  const genericPattern = /^https?:\/\/.+/;
  if (!genericPattern.test(value)) {
    return { valid: false, message: "Use a valid http(s) endpoint URL." };
  }
  return { valid: true, message: "Endpoint URL format looks valid." };
}

export default function DashboardIntegrationsWebhooksPage() {
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();
  const scope = useMemo(() => resolveDashboardScope(searchParams), [searchParams]);

  const [canManage, setCanManage] = useState(false);
  const [webhooks, setWebhooks] = useState<WebhookItem[]>([]);
  const [deliveries, setDeliveries] = useState<DeliveryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [newWebhookName, setNewWebhookName] = useState("");
  const [webhookProvider, setWebhookProvider] = useState<WebhookProvider>("slack");
  const [guideCompleted, setGuideCompleted] = useState(false);
  const [newWebhookUrl, setNewWebhookUrl] = useState("");
  const [newWebhookSecret, setNewWebhookSecret] = useState("");
  const [newWebhookEvents, setNewWebhookEvents] = useState<string[]>(["tool_called", "tool_succeeded", "tool_failed"]);
  const [eventPresetId, setEventPresetId] = useState("slack-alerts");

  const [creatingWebhook, setCreatingWebhook] = useState(false);
  const [testingWebhookId, setTestingWebhookId] = useState<number | null>(null);
  const [createTestResult, setCreateTestResult] = useState<{ ok: boolean; message: string } | null>(null);
  const [testResultByWebhookId, setTestResultByWebhookId] = useState<Record<number, { ok: boolean; message: string }>>({});
  const [processingRetries, setProcessingRetries] = useState(false);
  const [retryingDeliveryId, setRetryingDeliveryId] = useState<number | null>(null);

  const eventOptions = useMemo(
    () => ["tool_called", "tool_succeeded", "tool_failed", "policy_blocked", "quota_exceeded", "rate_limit_exceeded"],
    []
  );

  const eventPresets = useMemo<EventPreset[]>(
    () => [
      { id: "slack-alerts", label: "Slack Alerts", events: ["tool_failed", "policy_blocked", "quota_exceeded"] },
      { id: "slack-audit", label: "Slack Audit", events: ["tool_called", "tool_succeeded", "tool_failed"] },
      { id: "all-events", label: "All Events", events: [...eventOptions] },
    ],
    [eventOptions]
  );

  const urlValidation = useMemo(() => validateWebhookUrl(webhookProvider, newWebhookUrl), [newWebhookUrl, webhookProvider]);
  const canCreateWebhook = canManage && guideCompleted && urlValidation.valid && newWebhookEvents.length > 0 && newWebhookName.trim().length > 0;

  const handle401 = useCallback(() => {
    const next = encodeURIComponent(buildNextPath(pathname, window.location.search));
    router.replace(`/?next=${next}`);
  }, [pathname, router]);

  const fetchIntegrations = useCallback(async () => {
    setLoading(true);
    setError(null);
    const webhooksQuery = new URLSearchParams();
    const deliveriesQuery = new URLSearchParams({ limit: "50" });
    if (scope.organizationId !== null) {
      const organizationId = String(scope.organizationId);
      webhooksQuery.set("organization_id", organizationId);
      deliveriesQuery.set("organization_id", organizationId);
    }
    if (scope.teamId !== null) {
      const teamId = String(scope.teamId);
      webhooksQuery.set("team_id", teamId);
      deliveriesQuery.set("team_id", teamId);
    }

    const [permissionsRes, webhooksRes, deliveriesRes] = await Promise.all([
      dashboardApiGet<PermissionSnapshot>("/api/me/permissions"),
      dashboardApiGet<{ items?: WebhookItem[] }>(`/api/integrations/webhooks?${webhooksQuery.toString()}`),
      dashboardApiGet<{ items?: DeliveryItem[] }>(`/api/integrations/deliveries?${deliveriesQuery.toString()}`),
    ]);

    if (permissionsRes.status === 401 || webhooksRes.status === 401 || deliveriesRes.status === 401) {
      handle401();
      setLoading(false);
      return;
    }

    if (!permissionsRes.ok || !webhooksRes.ok || !deliveriesRes.ok || !permissionsRes.data || !webhooksRes.data || !deliveriesRes.data) {
      setError("Failed to load integrations data.");
      setLoading(false);
      return;
    }

    setCanManage(scope.scope === "org" && Boolean(permissionsRes.data.permissions?.can_manage_integrations));
    setWebhooks(Array.isArray(webhooksRes.data.items) ? webhooksRes.data.items : []);
    setDeliveries(Array.isArray(deliveriesRes.data.items) ? deliveriesRes.data.items : []);
    setLoading(false);
  }, [handle401, scope.organizationId, scope.scope, scope.teamId]);

  const handleCreateWebhook = useCallback(async () => {
    if (!canCreateWebhook) {
      return;
    }
    setCreatingWebhook(true);
    setError(null);
    setCreateTestResult(null);

    const response = await dashboardApiRequest<{ item?: WebhookItem }>("/api/integrations/webhooks", {
      method: "POST",
      body: {
        name: newWebhookName.trim(),
        endpoint_url: newWebhookUrl.trim(),
        secret: newWebhookSecret.trim() || null,
        event_types: normalizeEventTypes(newWebhookEvents),
      },
    });

    if (response.status === 401) {
      handle401();
      setCreatingWebhook(false);
      return;
    }
    if (response.status === 403) {
      setError("Admin role required to create webhook.");
      setCreatingWebhook(false);
      return;
    }
    if (!response.ok) {
      setError(response.error ?? "Failed to create webhook.");
      setCreatingWebhook(false);
      return;
    }

    const createdWebhookId = Number(response.data?.item?.id ?? 0);
    if (!Number.isFinite(createdWebhookId) || createdWebhookId <= 0) {
      setError("Webhook was created but test could not start (missing webhook id).");
      await fetchIntegrations();
      setCreatingWebhook(false);
      return;
    }

    setTestingWebhookId(createdWebhookId);
    const testResponse = await dashboardApiRequest(`/api/integrations/webhooks/${createdWebhookId}/test`, { method: "POST" });
    if (testResponse.status === 401) {
      handle401();
      setTestingWebhookId(null);
      setCreatingWebhook(false);
      return;
    }
    if (testResponse.status === 403) {
      const message = "Webhook created, but test failed: admin role required to test delivery.";
      setCreateTestResult({ ok: false, message });
      setTestResultByWebhookId((prev) => ({ ...prev, [createdWebhookId]: { ok: false, message } }));
      setTestingWebhookId(null);
      await fetchIntegrations();
      setCreatingWebhook(false);
      return;
    }
    if (!testResponse.ok) {
      const message = testResponse.error ?? "Webhook created, but test delivery failed.";
      setCreateTestResult({ ok: false, message });
      setTestResultByWebhookId((prev) => ({ ...prev, [createdWebhookId]: { ok: false, message } }));
      setTestingWebhookId(null);
      await fetchIntegrations();
      setCreatingWebhook(false);
      return;
    }

    const successMessage = "Webhook created and test event sent successfully.";
    setCreateTestResult({ ok: true, message: successMessage });
    setTestResultByWebhookId((prev) => ({ ...prev, [createdWebhookId]: { ok: true, message: "Test event sent." } }));
    setTestingWebhookId(null);
    setNewWebhookName("");
    setNewWebhookUrl("");
    setNewWebhookSecret("");
    setNewWebhookEvents(["tool_called", "tool_succeeded", "tool_failed"]);
    setEventPresetId("slack-alerts");
    setGuideCompleted(false);
    await fetchIntegrations();
    setCreatingWebhook(false);
  }, [canCreateWebhook, fetchIntegrations, handle401, newWebhookEvents, newWebhookName, newWebhookSecret, newWebhookUrl]);

  const handleTestWebhook = useCallback(
    async (webhookId: number) => {
      setTestingWebhookId(webhookId);
      setError(null);
      const response = await dashboardApiRequest(`/api/integrations/webhooks/${webhookId}/test`, { method: "POST" });
      if (response.status === 401) {
        handle401();
        setTestingWebhookId(null);
        return;
      }
      if (response.status === 403) {
        const message = "Admin role required to send test event.";
        setError(message);
        setTestResultByWebhookId((prev) => ({ ...prev, [webhookId]: { ok: false, message } }));
        setTestingWebhookId(null);
        return;
      }
      if (!response.ok) {
        const message = response.error ?? "Failed to send test event.";
        setError(message);
        setTestResultByWebhookId((prev) => ({ ...prev, [webhookId]: { ok: false, message } }));
        setTestingWebhookId(null);
        return;
      }
      setTestResultByWebhookId((prev) => ({ ...prev, [webhookId]: { ok: true, message: "Test event sent." } }));
      setTestingWebhookId(null);
      await fetchIntegrations();
    },
    [fetchIntegrations, handle401]
  );

  const handleProcessRetries = useCallback(async () => {
    setProcessingRetries(true);
    setError(null);

    const response = await dashboardApiRequest("/api/integrations/deliveries/process-retries?limit=100", {
      method: "POST",
    });

    if (response.status === 401) {
      handle401();
      setProcessingRetries(false);
      return;
    }
    if (response.status === 403) {
      setError("Admin role required to process retries.");
      setProcessingRetries(false);
      return;
    }
    if (!response.ok) {
      setError(response.error ?? "Failed to process webhook retries.");
      setProcessingRetries(false);
      return;
    }

    await fetchIntegrations();
    setProcessingRetries(false);
  }, [fetchIntegrations, handle401]);

  const handleRetryDelivery = useCallback(
    async (deliveryId: number) => {
      setRetryingDeliveryId(deliveryId);
      setError(null);

      const response = await dashboardApiRequest(`/api/integrations/deliveries/${deliveryId}/retry`, {
        method: "POST",
      });

      if (response.status === 401) {
        handle401();
        setRetryingDeliveryId(null);
        return;
      }
      if (response.status === 403) {
        setError("Admin role required to retry delivery.");
        setRetryingDeliveryId(null);
        return;
      }
      if (!response.ok) {
        setError(response.error ?? "Failed to retry delivery.");
        setRetryingDeliveryId(null);
        return;
      }

      await fetchIntegrations();
      setRetryingDeliveryId(null);
    },
    [fetchIntegrations, handle401]
  );

  useEffect(() => {
    void fetchIntegrations();
  }, [fetchIntegrations]);

  useEffect(() => {
    const handler = (event: Event) => {
      const custom = event as CustomEvent<{ path?: string }>;
      if (custom.detail?.path === pathname) {
        void fetchIntegrations();
      }
    };
    window.addEventListener("dashboard:v2:refresh", handler as EventListener);
    return () => {
      window.removeEventListener("dashboard:v2:refresh", handler as EventListener);
    };
  }, [fetchIntegrations, pathname]);

  if (loading) {
    return (
      <section className="space-y-4">
        <PageTitleWithTooltip
          title="Integrations"
          tooltip="Manage webhook subscriptions, deliveries, and retry operations."
        />
        <p className="text-sm text-muted-foreground">Manage event subscriptions, delivery status, and retry processing.</p>
        <div className="ds-card flex min-h-[220px] items-center justify-center p-4">
          <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
        </div>
      </section>
    );
  }

  const writeDisabledReason =
    scope.scope !== "org"
      ? "Webhook write actions are available in organization scope."
      : "Integration write actions are read-only for your role.";

  return (
    <section className="space-y-4">
      <PageTitleWithTooltip
        title="Integrations"
        tooltip="Manage webhook subscriptions, deliveries, and retry operations."
      />
      <p className="text-sm text-muted-foreground">Manage event subscriptions, delivery status, and retry processing.</p>

      <div className="ds-card p-4">
        <p className="mb-3 text-sm font-semibold">Create Webhook</p>
        <div className="mb-3 grid gap-2 lg:grid-cols-2">
          <article className="rounded-md border border-border p-3">
            <p className="text-xs text-muted-foreground">Step 1. Choose destination</p>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <Button
                type="button"
                variant={webhookProvider === "slack" ? "default" : "outline"}
                className="h-9 rounded-md px-3 text-xs"
                onClick={() => {
                  setWebhookProvider("slack");
                  setEventPresetId("slack-alerts");
                  const preset = eventPresets.find((item) => item.id === "slack-alerts");
                  if (preset) {
                    setNewWebhookEvents([...preset.events]);
                  }
                }}
                disabled={!canManage || creatingWebhook}
              >
                Slack
              </Button>
              <Button
                type="button"
                variant={webhookProvider === "generic" ? "default" : "outline"}
                className="h-9 rounded-md px-3 text-xs"
                onClick={() => setWebhookProvider("generic")}
                disabled={!canManage || creatingWebhook}
              >
                Generic Webhook
              </Button>
            </div>
          </article>
          <article className="rounded-md border border-border p-3">
            <p className="text-xs text-muted-foreground">Step 2. Setup guide</p>
            {webhookProvider === "slack" ? (
              <div className="mt-2 space-y-1 text-xs text-muted-foreground">
                <p>1) Open Slack App settings and enable Incoming Webhooks.</p>
                <p>2) Choose a channel and copy the generated webhook URL.</p>
                <p>3) Paste it below and save this connection.</p>
                <a
                  href="https://api.slack.com/messaging/webhooks"
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex text-primary underline underline-offset-2"
                >
                  Open Slack Incoming Webhooks Docs
                </a>
              </div>
            ) : (
              <p className="mt-2 text-xs text-muted-foreground">Use any HTTPS endpoint that can receive POST webhook events.</p>
            )}
            <label className="mt-2 flex items-center gap-2 text-xs">
              <input
                type="checkbox"
                checked={guideCompleted}
                onChange={(event) => setGuideCompleted(event.target.checked)}
                disabled={!canManage || creatingWebhook}
              />
              I completed the setup steps
            </label>
          </article>
        </div>
        <div className="grid gap-2 lg:grid-cols-2">
          <Input
            value={newWebhookName}
            onChange={(event) => setNewWebhookName(event.target.value)}
            disabled={!canManage}
            placeholder={webhookProvider === "slack" ? "e.g. Slack Alerts - Prod" : "Webhook name"}
            className="ds-input h-11 min-w-[220px] flex-1 rounded-md px-3 text-sm md:h-9"
          />
          <Input
            value={newWebhookUrl}
            onChange={(event) => setNewWebhookUrl(event.target.value)}
            disabled={!canManage}
            placeholder={webhookProvider === "slack" ? "https://hooks.slack.com/services/..." : "Endpoint URL"}
            className="ds-input h-11 min-w-[260px] flex-1 rounded-md px-3 text-sm md:h-9"
          />
          <div className="lg:col-span-2">
            <p className={`text-xs ${urlValidation.valid ? "text-emerald-500" : "text-muted-foreground"}`}>{urlValidation.message}</p>
          </div>
          <Input
            value={newWebhookSecret}
            onChange={(event) => setNewWebhookSecret(event.target.value)}
            disabled={!canManage}
            placeholder="Secret (optional)"
            className="ds-input h-11 min-w-[180px] flex-1 rounded-md px-3 text-sm md:h-9"
          />
          <select
            value={eventPresetId}
            onChange={(event) => {
              const nextPreset = event.target.value;
              setEventPresetId(nextPreset);
              const preset = eventPresets.find((item) => item.id === nextPreset);
              if (preset) {
                setNewWebhookEvents([...preset.events]);
              }
            }}
            disabled={!canManage || creatingWebhook}
            className="ds-input h-11 min-w-[260px] rounded-md px-3 text-sm md:h-9"
          >
            {eventPresets.map((preset) => (
              <option key={preset.id} value={preset.id}>
                Preset: {preset.label}
              </option>
            ))}
          </select>
          <div className="lg:col-span-2">
            <p className="mb-2 text-xs text-muted-foreground">Step 3. Choose event types</p>
            <div className="flex flex-wrap gap-2">
              {eventOptions.map((eventType) => {
                const active = newWebhookEvents.includes(eventType);
                return (
                  <Button
                    key={eventType}
                    type="button"
                    variant={active ? "default" : "outline"}
                    className="h-8 rounded-md px-2 text-[11px]"
                    disabled={!canManage || creatingWebhook}
                    onClick={() =>
                      setNewWebhookEvents((prev) => {
                        if (prev.includes(eventType)) {
                          return prev.filter((item) => item !== eventType);
                        }
                        return normalizeEventTypes([...prev, eventType]);
                      })
                    }
                  >
                    {eventType}
                  </Button>
                );
              })}
            </div>
          </div>
          <div className="lg:col-span-2">
            <p className="text-xs text-muted-foreground">Selected: {newWebhookEvents.join(", ") || "-"}</p>
          </div>
          <div className="lg:col-span-2">
            {!canManage ? <p className="mb-2 text-xs text-muted-foreground">{writeDisabledReason}</p> : null}
            {!guideCompleted && canManage ? <p className="mb-2 text-xs text-muted-foreground">Complete setup step checkbox to enable save.</p> : null}
          </div>
          <Button
            type="button"
            onClick={() => void handleCreateWebhook()}
            disabled={!canCreateWebhook || creatingWebhook}
            className="ds-btn h-11 shrink-0 rounded-md px-3 text-sm disabled:cursor-not-allowed disabled:opacity-60 md:h-9 lg:col-span-2"
          >
            {creatingWebhook ? (testingWebhookId ? "Creating & Testing..." : "Creating...") : "Create & Test"}
          </Button>
          {createTestResult ? (
            <p className={`text-xs ${createTestResult.ok ? "text-emerald-500" : "text-destructive"} lg:col-span-2`}>{createTestResult.message}</p>
          ) : null}
        </div>
      </div>

      {error ? (
        <div className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error}
        </div>
      ) : null}

      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold">Webhook Operations</h2>
          {!canManage ? <p className="text-xs text-muted-foreground">{writeDisabledReason}</p> : null}
        </div>
        <Button
          type="button"
          onClick={() => void handleProcessRetries()}
          disabled={!canManage || processingRetries}
          className="ds-btn h-11 rounded-md px-3 text-sm disabled:cursor-not-allowed disabled:opacity-60 md:h-9"
        >
          {processingRetries ? "Processing..." : "Process Retries"}
        </Button>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <article className="ds-card p-4">
          <p className="text-sm font-semibold">Subscriptions</p>
          <div className="mt-2 space-y-2">
            {webhooks.length === 0 ? <p className="text-xs text-muted-foreground">No subscriptions.</p> : null}
            {webhooks.slice(0, 12).map((hook) => (
              <div key={`hook-${hook.id}`} className="rounded-md border border-border px-2 py-2">
                <p className="text-xs">
                  {hook.name} ({hook.is_active ? "active" : "disabled"}) · {hook.event_types.join(", ")}
                </p>
                <div className="mt-1 flex items-center gap-2">
                  <Button
                    type="button"
                    onClick={() => void handleTestWebhook(hook.id)}
                    disabled={!canManage || testingWebhookId === hook.id}
                    className="ds-btn h-8 rounded-md px-2 text-[11px] disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    {testingWebhookId === hook.id ? "Testing..." : "Send Test"}
                  </Button>
                  {testResultByWebhookId[hook.id] ? (
                    <span className={`text-[11px] ${testResultByWebhookId[hook.id]?.ok ? "text-emerald-500" : "text-destructive"}`}>
                      {testResultByWebhookId[hook.id]?.message}
                    </span>
                  ) : null}
                </div>
              </div>
            ))}
          </div>
        </article>

        <article className="ds-card p-4">
          <p className="text-sm font-semibold">Recent Deliveries</p>
          <div className="mt-2 space-y-2">
            {deliveries.length === 0 ? <p className="text-xs text-muted-foreground">No deliveries.</p> : null}
            {deliveries.slice(0, 20).map((delivery) => (
              <div key={`delivery-${delivery.id}`} className="rounded-md border border-border px-2 py-2">
                <p className="text-xs">
                  #{delivery.id} {delivery.event_type} · {delivery.status}
                  {delivery.http_status ? ` (${delivery.http_status})` : ""} · retry {delivery.retry_count}
                </p>
                <p className="text-[11px] text-muted-foreground">
                  next: {formatDate(delivery.next_retry_at)} · created: {formatDate(delivery.created_at)}
                </p>
                {delivery.error_message ? <p className="text-[11px] text-destructive">{delivery.error_message}</p> : null}
                <div className="mt-1">
                  <Button
                    type="button"
                    onClick={() => void handleRetryDelivery(delivery.id)}
                    disabled={!canManage || retryingDeliveryId === delivery.id}
                    className="ds-btn h-9 rounded-md px-2 text-[11px] disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    {retryingDeliveryId === delivery.id ? "Retrying..." : "Retry"}
                  </Button>
                </div>
              </div>
            ))}
          </div>
        </article>
      </div>
    </section>
  );
}
