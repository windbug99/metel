"use client";

import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
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
  description: string;
  events: string[];
};

type TestResult = {
  ok: boolean;
  message: string;
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

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
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

function mergeUnique(values: string[]): string[] {
  return Array.from(new Set(values.map((item) => item.trim()).filter((item) => item.length > 0)));
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

  const [activeTab, setActiveTab] = useState<"subscriptions" | "deliveries">("subscriptions");

  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [createStep, setCreateStep] = useState<1 | 2 | 3>(1);
  const [webhookProvider, setWebhookProvider] = useState<WebhookProvider>("slack");
  const [guideCompleted, setGuideCompleted] = useState(false);
  const [newWebhookName, setNewWebhookName] = useState("Slack Alerts - Prod");
  const [newWebhookUrl, setNewWebhookUrl] = useState("");
  const [newWebhookSecret, setNewWebhookSecret] = useState("");
  const [selectedPresetIds, setSelectedPresetIds] = useState<string[]>(["slack-alerts"]);
  const [manuallyIncludedEvents, setManuallyIncludedEvents] = useState<string[]>([]);
  const [manuallyExcludedEvents, setManuallyExcludedEvents] = useState<string[]>([]);

  const [creatingWebhook, setCreatingWebhook] = useState(false);
  const [testingWebhookId, setTestingWebhookId] = useState<number | null>(null);
  const [createTestResult, setCreateTestResult] = useState<TestResult | null>(null);
  const [testResultByWebhookId, setTestResultByWebhookId] = useState<Record<number, TestResult>>({});

  const [processingRetries, setProcessingRetries] = useState(false);
  const [retryingDeliveryId, setRetryingDeliveryId] = useState<number | null>(null);

  const eventPresets = useMemo<EventPreset[]>(() => {
    if (webhookProvider === "slack") {
      return [
        {
          id: "slack-alerts",
          label: "Slack Alerts",
          description: "Failure/blocked events for incident channels",
          events: ["tool_failed", "policy_blocked", "quota_exceeded", "rate_limit_exceeded"],
        },
        {
          id: "slack-audit",
          label: "Slack Audit",
          description: "Operational activity feed",
          events: ["tool_called", "tool_succeeded", "tool_failed"],
        },
        {
          id: "slack-all",
          label: "All Events",
          description: "Every event type",
          events: ["tool_called", "tool_succeeded", "tool_failed", "policy_blocked", "quota_exceeded", "rate_limit_exceeded"],
        },
      ];
    }
    return [
      {
        id: "generic-core",
        label: "Core Events",
        description: "Core call lifecycle",
        events: ["tool_called", "tool_succeeded", "tool_failed"],
      },
      {
        id: "generic-failures",
        label: "Failure Events",
        description: "Only failure and policy/quota blocks",
        events: ["tool_failed", "policy_blocked", "quota_exceeded", "rate_limit_exceeded"],
      },
    ];
  }, [webhookProvider]);

  const eventOptions = useMemo(
    () => ["tool_called", "tool_succeeded", "tool_failed", "policy_blocked", "quota_exceeded", "rate_limit_exceeded"],
    []
  );

  const presetEvents = useMemo(() => {
    const selected = eventPresets.filter((preset) => selectedPresetIds.includes(preset.id));
    return mergeUnique(selected.flatMap((preset) => preset.events));
  }, [eventPresets, selectedPresetIds]);

  const selectedEvents = useMemo(() => {
    const presetSet = new Set(presetEvents);
    const includeSet = new Set(manuallyIncludedEvents);
    const excludeSet = new Set(manuallyExcludedEvents);
    return eventOptions.filter((eventType) => {
      const fromPreset = presetSet.has(eventType);
      if (fromPreset && excludeSet.has(eventType)) {
        return false;
      }
      if (fromPreset) {
        return true;
      }
      return includeSet.has(eventType);
    });
  }, [eventOptions, manuallyExcludedEvents, manuallyIncludedEvents, presetEvents]);

  const urlValidation = useMemo(() => validateWebhookUrl(webhookProvider, newWebhookUrl), [newWebhookUrl, webhookProvider]);

  const createDisabledReason = useMemo(() => {
    if (!canManage) {
      return scope.scope !== "org"
        ? "Switch to organization scope to create webhooks."
        : "Your role cannot create webhooks.";
    }
    if (!newWebhookName.trim()) {
      return "Title is required.";
    }
    if (!guideCompleted) {
      return "Complete setup step checkbox to continue.";
    }
    if (!urlValidation.valid) {
      return urlValidation.message;
    }
    if (selectedEvents.length === 0) {
      return "Select at least one event preset.";
    }
    return null;
  }, [canManage, guideCompleted, newWebhookName, scope.scope, selectedEvents.length, urlValidation.message, urlValidation.valid]);

  const canCreateWebhook = createDisabledReason === null;

  const writeDisabledReason =
    scope.scope !== "org"
      ? "Webhook write actions are available in organization scope."
      : "Integration write actions are read-only for your role.";

  useEffect(() => {
    if (webhookProvider === "slack") {
      if (!newWebhookName.trim()) {
        setNewWebhookName("Slack Alerts - Prod");
      }
      setSelectedPresetIds((prev) => (prev.length > 0 ? prev : ["slack-alerts"]));
      return;
    }
    if (!newWebhookName.trim()) {
      setNewWebhookName("Webhook Endpoint");
    }
    setSelectedPresetIds((prev) => (prev.length > 0 ? prev : ["generic-core"]));
  }, [newWebhookName, webhookProvider]);

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

  const fetchLatestDeliveryForWebhook = useCallback(
    async (webhookId: number): Promise<DeliveryItem | null> => {
      const query = new URLSearchParams({ limit: "20", webhook_id: String(webhookId) });
      if (scope.organizationId !== null) {
        query.set("organization_id", String(scope.organizationId));
      }
      if (scope.teamId !== null) {
        query.set("team_id", String(scope.teamId));
      }
      const response = await dashboardApiGet<{ items?: DeliveryItem[] }>(`/api/integrations/deliveries?${query.toString()}`);
      if (!response.ok || !response.data) {
        return null;
      }
      const items = Array.isArray(response.data.items) ? response.data.items : [];
      return items[0] ?? null;
    },
    [scope.organizationId, scope.teamId]
  );

  const resolveWebhookTestResult = useCallback(
    async (webhookId: number): Promise<TestResult> => {
      for (let index = 0; index < 8; index += 1) {
        const latest = await fetchLatestDeliveryForWebhook(webhookId);
        if (latest && latest.status === "success") {
          return { ok: true, message: `Delivery success (HTTP ${latest.http_status ?? 200}).` };
        }
        if (latest && (latest.status === "failed" || latest.status === "dead_letter")) {
          const detail = latest.error_message ? ` ${latest.error_message}` : "";
          return { ok: false, message: `Delivery failed${detail}`.trim() };
        }
        await sleep(900);
      }
      return {
        ok: true,
        message: "Test request accepted. Final delivery status may appear in Recent Deliveries shortly.",
      };
    },
    [fetchLatestDeliveryForWebhook]
  );

  const resetCreateDialogState = useCallback(() => {
    setCreateStep(1);
    setWebhookProvider("slack");
    setGuideCompleted(false);
    setNewWebhookName("Slack Alerts - Prod");
    setNewWebhookUrl("");
    setNewWebhookSecret("");
    setSelectedPresetIds(["slack-alerts"]);
    setManuallyIncludedEvents([]);
    setManuallyExcludedEvents([]);
    setCreateTestResult(null);
  }, []);

  const handleCreateWebhook = useCallback(async () => {
    if (!canCreateWebhook) {
      return;
    }

    setCreatingWebhook(true);
    setError(null);
    setCreateTestResult(null);

    const createResponse = await dashboardApiRequest<{ item?: WebhookItem }>("/api/integrations/webhooks", {
      method: "POST",
      body: {
        name: newWebhookName.trim(),
        endpoint_url: newWebhookUrl.trim(),
        secret: newWebhookSecret.trim() || null,
        event_types: selectedEvents,
      },
    });

    if (createResponse.status === 401) {
      handle401();
      setCreatingWebhook(false);
      return;
    }
    if (createResponse.status === 403) {
      setError("Admin role required to create webhook.");
      setCreatingWebhook(false);
      return;
    }
    if (!createResponse.ok) {
      setError(createResponse.error ?? "Failed to create webhook.");
      setCreatingWebhook(false);
      return;
    }

    const createdWebhookId = Number(createResponse.data?.item?.id ?? 0);
    if (!Number.isFinite(createdWebhookId) || createdWebhookId <= 0) {
      setCreateTestResult({ ok: false, message: "Webhook created, but test could not start (missing webhook id)." });
      await fetchIntegrations();
      setCreatingWebhook(false);
      return;
    }

    setTestingWebhookId(createdWebhookId);
    const testResponse = await dashboardApiRequest(`/api/integrations/webhooks/${createdWebhookId}/test`, {
      method: "POST",
    });

    if (testResponse.status === 401) {
      handle401();
      setTestingWebhookId(null);
      setCreatingWebhook(false);
      return;
    }
    if (testResponse.status === 403) {
      const result = { ok: false, message: "Webhook created, but test request denied: admin role required." };
      setCreateTestResult(result);
      setTestResultByWebhookId((prev) => ({ ...prev, [createdWebhookId]: result }));
      setTestingWebhookId(null);
      await fetchIntegrations();
      setCreatingWebhook(false);
      return;
    }
    if (!testResponse.ok) {
      const result = { ok: false, message: testResponse.error ?? "Webhook created, but test request failed." };
      setCreateTestResult(result);
      setTestResultByWebhookId((prev) => ({ ...prev, [createdWebhookId]: result }));
      setTestingWebhookId(null);
      await fetchIntegrations();
      setCreatingWebhook(false);
      return;
    }

    const resolved = await resolveWebhookTestResult(createdWebhookId);
    setCreateTestResult(resolved);
    setTestResultByWebhookId((prev) => ({ ...prev, [createdWebhookId]: resolved }));
    setTestingWebhookId(null);

    await fetchIntegrations();
    setCreatingWebhook(false);

    if (resolved.ok) {
      setCreateDialogOpen(false);
      resetCreateDialogState();
    }
  }, [
    canCreateWebhook,
    fetchIntegrations,
    handle401,
    newWebhookName,
    newWebhookSecret,
    newWebhookUrl,
    resolveWebhookTestResult,
    resetCreateDialogState,
    selectedEvents,
  ]);

  const handleSendTest = useCallback(
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
        const result = { ok: false, message: "Test request denied: admin role required." };
        setTestResultByWebhookId((prev) => ({ ...prev, [webhookId]: result }));
        setError(result.message);
        setTestingWebhookId(null);
        return;
      }
      if (!response.ok) {
        const result = { ok: false, message: response.error ?? "Failed to send test request." };
        setTestResultByWebhookId((prev) => ({ ...prev, [webhookId]: result }));
        setError(result.message);
        setTestingWebhookId(null);
        return;
      }

      setTestResultByWebhookId((prev) => ({
        ...prev,
        [webhookId]: { ok: true, message: "Test request accepted. Checking delivery result..." },
      }));
      const resolved = await resolveWebhookTestResult(webhookId);
      setTestResultByWebhookId((prev) => ({ ...prev, [webhookId]: resolved }));
      setTestingWebhookId(null);
      await fetchIntegrations();
    },
    [fetchIntegrations, handle401, resolveWebhookTestResult]
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

  return (
    <section className="space-y-4">
      <PageTitleWithTooltip
        title="Integrations"
        tooltip="Manage webhook subscriptions, deliveries, and retry operations."
      />
      <p className="text-sm text-muted-foreground">Manage event subscriptions, delivery status, and retry processing.</p>

      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <p className="text-sm font-semibold">Webhook Operations</p>
          {!canManage ? <p className="text-xs text-muted-foreground">{writeDisabledReason}</p> : null}
        </div>
        <div className="flex items-center gap-2">
          <Button
            type="button"
            onClick={() => {
              setCreateDialogOpen(true);
              setCreateStep(1);
              setCreateTestResult(null);
            }}
            disabled={!canManage}
            className="ds-btn h-11 rounded-md px-3 text-sm disabled:cursor-not-allowed disabled:opacity-60 md:h-9"
          >
            Create Webhook
          </Button>
          <Button
            type="button"
            onClick={() => void handleProcessRetries()}
            disabled={!canManage || processingRetries}
            className="ds-btn h-11 rounded-md px-3 text-sm disabled:cursor-not-allowed disabled:opacity-60 md:h-9"
          >
            {processingRetries ? "Processing..." : "Process Retries"}
          </Button>
        </div>
      </div>

      {error ? (
        <div className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error}
        </div>
      ) : null}

      <div className="ds-card p-4">
        <Tabs value={activeTab} onValueChange={(value) => setActiveTab(value as "subscriptions" | "deliveries")} className="space-y-3">
          <TabsList className="h-auto w-full justify-start gap-2 p-1">
            <TabsTrigger value="subscriptions" className="h-9 rounded-md px-3 text-sm">
              Subscriptions
            </TabsTrigger>
            <TabsTrigger value="deliveries" className="h-9 rounded-md px-3 text-sm">
              Recent Deliveries
            </TabsTrigger>
          </TabsList>

          <TabsContent value="subscriptions" className="space-y-2">
            {webhooks.length === 0 ? <p className="text-xs text-muted-foreground">No subscriptions.</p> : null}
            {webhooks.slice(0, 20).map((hook) => (
              <article key={`hook-${hook.id}`} className="rounded-md border border-border p-3">
                <p className="text-sm font-medium">
                  {hook.name} ({hook.is_active ? "active" : "disabled"})
                </p>
                <p className="mt-1 text-xs text-muted-foreground">events: {hook.event_types.join(", ") || "-"}</p>
                <p className="mt-1 text-xs text-muted-foreground">last delivery: {formatDate(hook.last_delivery_at)}</p>
                <div className="mt-2 flex items-center gap-2">
                  <Button
                    type="button"
                    onClick={() => void handleSendTest(hook.id)}
                    disabled={!canManage || testingWebhookId === hook.id}
                    className="ds-btn h-9 rounded-md px-3 text-xs disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    {testingWebhookId === hook.id ? "Testing..." : "Send Test"}
                  </Button>
                  {testResultByWebhookId[hook.id] ? (
                    <p className={`text-xs ${testResultByWebhookId[hook.id].ok ? "text-emerald-500" : "text-destructive"}`}>
                      {testResultByWebhookId[hook.id].message}
                    </p>
                  ) : null}
                </div>
              </article>
            ))}
          </TabsContent>

          <TabsContent value="deliveries" className="space-y-2">
            {deliveries.length === 0 ? <p className="text-xs text-muted-foreground">No deliveries.</p> : null}
            {deliveries.slice(0, 30).map((delivery) => (
              <article key={`delivery-${delivery.id}`} className="rounded-md border border-border px-3 py-2">
                <p className="text-xs">
                  #{delivery.id} · sub #{delivery.subscription_id} · {delivery.event_type} · {delivery.status}
                  {delivery.http_status ? ` (HTTP ${delivery.http_status})` : ""}
                </p>
                <p className="text-[11px] text-muted-foreground">
                  retry {delivery.retry_count} · created {formatDate(delivery.created_at)} · next {formatDate(delivery.next_retry_at)}
                </p>
                {delivery.error_message ? <p className="text-[11px] text-destructive">{delivery.error_message}</p> : null}
                <div className="mt-1">
                  <Button
                    type="button"
                    onClick={() => void handleRetryDelivery(delivery.id)}
                    disabled={!canManage || retryingDeliveryId === delivery.id}
                    className="ds-btn h-8 rounded-md px-2 text-[11px] disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    {retryingDeliveryId === delivery.id ? "Retrying..." : "Retry"}
                  </Button>
                </div>
              </article>
            ))}
          </TabsContent>
        </Tabs>
      </div>

      <Dialog
        open={createDialogOpen}
        onOpenChange={(open) => {
          setCreateDialogOpen(open);
          if (!open) {
            resetCreateDialogState();
          }
        }}
      >
        <DialogContent className="sm:max-w-3xl">
          <DialogHeader>
            <DialogTitle>Create Webhook</DialogTitle>
            <DialogDescription>Step {createStep} of 3</DialogDescription>
          </DialogHeader>

          <div className="space-y-3">
            {createStep === 1 ? (
              <div className="space-y-2 rounded-md border border-border p-3">
                <p className="text-sm font-medium">Step 01. Choose destination</p>
                <p className="text-xs text-muted-foreground">Select where your notifications should be delivered.</p>
                <div className="flex items-center gap-2">
                  <Button
                    type="button"
                    variant={webhookProvider === "slack" ? "default" : "outline"}
                    className="h-9 rounded-md px-3 text-xs"
                    onClick={() => {
                      setWebhookProvider("slack");
                      setSelectedPresetIds(["slack-alerts"]);
                      setManuallyIncludedEvents([]);
                      setManuallyExcludedEvents([]);
                    }}
                    disabled={creatingWebhook}
                  >
                    Slack
                  </Button>
                  <Button
                    type="button"
                    variant={webhookProvider === "generic" ? "default" : "outline"}
                    className="h-9 rounded-md px-3 text-xs"
                    onClick={() => {
                      setWebhookProvider("generic");
                      setSelectedPresetIds(["generic-core"]);
                      setManuallyIncludedEvents([]);
                      setManuallyExcludedEvents([]);
                    }}
                    disabled={creatingWebhook}
                  >
                    Generic Webhook
                  </Button>
                </div>
              </div>
            ) : null}

            {createStep === 2 ? (
              <div className="space-y-3 rounded-md border border-border p-3">
                <p className="text-sm font-medium">Step 02. Setup guide and endpoint</p>
                {webhookProvider === "slack" ? (
                  <div className="space-y-1 text-xs text-muted-foreground">
                    <p>1) Open Slack App settings and enable Incoming Webhooks.</p>
                    <p>2) Choose a channel and copy the generated webhook URL.</p>
                    <p>3) Paste URL below and proceed to Step 03.</p>
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
                  <p className="text-xs text-muted-foreground">Use any HTTPS endpoint that can receive POST webhook events.</p>
                )}

                <div className="grid gap-2 sm:grid-cols-2">
                  <div className="space-y-1">
                    <p className="text-xs text-muted-foreground">Title</p>
                    <Input
                      value={newWebhookName}
                      onChange={(event) => setNewWebhookName(event.target.value)}
                      placeholder={webhookProvider === "slack" ? "e.g. Slack Alerts - Prod" : "Webhook name"}
                      className="h-10"
                      disabled={creatingWebhook}
                    />
                  </div>
                  <div className="space-y-1">
                    <p className="text-xs text-muted-foreground">Webhook URL</p>
                    <Input
                      value={newWebhookUrl}
                      onChange={(event) => setNewWebhookUrl(event.target.value)}
                      placeholder={webhookProvider === "slack" ? "https://hooks.slack.com/services/..." : "https://example.com/webhook"}
                      className="h-10"
                      disabled={creatingWebhook}
                    />
                  </div>
                  <div className="space-y-1 sm:col-span-2">
                    <p className={`text-xs ${urlValidation.valid ? "text-emerald-500" : "text-muted-foreground"}`}>{urlValidation.message}</p>
                  </div>
                  <div className="space-y-1 sm:col-span-2">
                    <p className="text-xs text-muted-foreground">Secret (optional)</p>
                    <Input
                      value={newWebhookSecret}
                      onChange={(event) => setNewWebhookSecret(event.target.value)}
                      placeholder="Secret (optional)"
                      className="h-10"
                      disabled={creatingWebhook}
                    />
                  </div>
                </div>

                <label className="flex items-center gap-2 text-xs">
                  <Checkbox
                    checked={guideCompleted}
                    onCheckedChange={(checked) => setGuideCompleted(checked === true)}
                    disabled={creatingWebhook}
                  />
                  I completed setup steps
                </label>
              </div>
            ) : null}

            {createStep === 3 ? (
              <div className="space-y-3 rounded-md border border-border p-3">
                <p className="text-sm font-medium">Step 03. Choose event presets</p>
                <p className="text-xs text-muted-foreground">Preset selection uses checkboxes as requested. Multiple presets can be selected.</p>
                <div className="space-y-2">
                  {eventPresets.map((preset) => {
                    const checked = selectedPresetIds.includes(preset.id);
                    return (
                      <label key={preset.id} className="flex items-start gap-2 rounded-md border border-border p-2 text-xs">
                        <Checkbox
                          checked={checked}
                          onCheckedChange={(next) => {
                            setSelectedPresetIds((prev) => {
                              if (next === true) {
                                return mergeUnique([...prev, preset.id]);
                              }
                              return prev.filter((id) => id !== preset.id);
                            });
                          }}
                          disabled={creatingWebhook}
                        />
                        <span>
                          <span className="block font-medium text-foreground">{preset.label}</span>
                          <span className="text-muted-foreground">{preset.description}</span>
                          <span className="mt-1 block text-muted-foreground">events: {preset.events.join(", ")}</span>
                        </span>
                      </label>
                    );
                  })}
                </div>
                <div className="space-y-2 rounded-md border border-border p-2">
                  <p className="text-xs font-medium text-foreground">Custom events</p>
                  <p className="text-xs text-muted-foreground">Use checkboxes below to include or exclude specific events.</p>
                  <div className="grid gap-2 sm:grid-cols-2">
                    {eventOptions.map((eventType) => {
                      const checked = selectedEvents.includes(eventType);
                      const fromPreset = presetEvents.includes(eventType);
                      return (
                        <label key={`custom-${eventType}`} className="flex items-center gap-2 rounded-md border border-border px-2 py-1 text-xs">
                          <Checkbox
                            checked={checked}
                            onCheckedChange={(next) => {
                              const enabled = next === true;
                              if (enabled) {
                                if (fromPreset) {
                                  setManuallyExcludedEvents((prev) => prev.filter((item) => item !== eventType));
                                  return;
                                }
                                setManuallyIncludedEvents((prev) => mergeUnique([...prev, eventType]));
                                setManuallyExcludedEvents((prev) => prev.filter((item) => item !== eventType));
                                return;
                              }
                              if (fromPreset) {
                                setManuallyExcludedEvents((prev) => mergeUnique([...prev, eventType]));
                                setManuallyIncludedEvents((prev) => prev.filter((item) => item !== eventType));
                                return;
                              }
                              setManuallyIncludedEvents((prev) => prev.filter((item) => item !== eventType));
                            }}
                            disabled={creatingWebhook}
                          />
                          <span>{eventType}</span>
                          {fromPreset ? <span className="text-[10px] text-muted-foreground">(preset)</span> : null}
                        </label>
                      );
                    })}
                  </div>
                </div>
                <p className="text-xs text-muted-foreground">Selected events ({selectedEvents.length}): {selectedEvents.join(", ") || "-"}</p>
                {createDisabledReason ? <p className="text-xs text-amber-500">{createDisabledReason}</p> : null}
                {createTestResult ? (
                  <p className={`text-xs ${createTestResult.ok ? "text-emerald-500" : "text-destructive"}`}>{createTestResult.message}</p>
                ) : null}
              </div>
            ) : null}
          </div>

          <DialogFooter className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <Button
                type="button"
                variant="outline"
                className="border-border bg-card text-foreground hover:bg-accent hover:text-accent-foreground"
                onClick={() => setCreateDialogOpen(false)}
                disabled={creatingWebhook}
              >
                Cancel
              </Button>
              {createStep > 1 ? (
                <Button
                  type="button"
                  variant="outline"
                  className="border-border bg-card text-foreground hover:bg-accent hover:text-accent-foreground"
                  onClick={() => setCreateStep((prev) => (prev === 1 ? 1 : ((prev - 1) as 1 | 2 | 3)))}
                  disabled={creatingWebhook}
                >
                  Back
                </Button>
              ) : null}
            </div>

            <div className="flex items-center gap-2">
              {createStep < 3 ? (
                <Button
                  type="button"
                  className="bg-sidebar-primary text-sidebar-primary-foreground hover:bg-sidebar-primary/90"
                  onClick={() => setCreateStep((prev) => (prev === 3 ? 3 : ((prev + 1) as 1 | 2 | 3)))}
                  disabled={
                    creatingWebhook ||
                    (createStep === 2 && (!newWebhookName.trim() || !guideCompleted || !urlValidation.valid))
                  }
                >
                  Next
                </Button>
              ) : (
                <Button
                  type="button"
                  onClick={() => void handleCreateWebhook()}
                  disabled={!canCreateWebhook || creatingWebhook}
                  className="bg-sidebar-primary text-sidebar-primary-foreground hover:bg-sidebar-primary/90"
                >
                  {creatingWebhook ? (testingWebhookId ? "Creating & Testing..." : "Creating...") : "Create & Test"}
                </Button>
              )}
            </div>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </section>
  );
}
