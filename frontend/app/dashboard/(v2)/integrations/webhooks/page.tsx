"use client";

import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { useCallback, useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";

import { buildNextPath, dashboardApiGet, dashboardApiRequest } from "../../../../../lib/dashboard-v2-client";

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

export default function DashboardIntegrationsWebhooksPage() {
  const pathname = usePathname();
  const router = useRouter();

  const [canManage, setCanManage] = useState(false);
  const [webhooks, setWebhooks] = useState<WebhookItem[]>([]);
  const [deliveries, setDeliveries] = useState<DeliveryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [newWebhookName, setNewWebhookName] = useState("");
  const [newWebhookUrl, setNewWebhookUrl] = useState("");
  const [newWebhookSecret, setNewWebhookSecret] = useState("");
  const [newWebhookEvents, setNewWebhookEvents] = useState("tool_called, tool_succeeded, tool_failed");

  const [creatingWebhook, setCreatingWebhook] = useState(false);
  const [processingRetries, setProcessingRetries] = useState(false);
  const [retryingDeliveryId, setRetryingDeliveryId] = useState<number | null>(null);

  const handle401 = useCallback(() => {
    const next = encodeURIComponent(buildNextPath(pathname, window.location.search));
    router.replace(`/?next=${next}`);
  }, [pathname, router]);

  const fetchIntegrations = useCallback(async () => {
    setLoading(true);
    setError(null);

    const [permissionsRes, webhooksRes, deliveriesRes] = await Promise.all([
      dashboardApiGet<PermissionSnapshot>("/api/me/permissions"),
      dashboardApiGet<{ items?: WebhookItem[] }>("/api/integrations/webhooks"),
      dashboardApiGet<{ items?: DeliveryItem[] }>("/api/integrations/deliveries?limit=50"),
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

    setCanManage(Boolean(permissionsRes.data.permissions?.can_manage_integrations));
    setWebhooks(Array.isArray(webhooksRes.data.items) ? webhooksRes.data.items : []);
    setDeliveries(Array.isArray(deliveriesRes.data.items) ? deliveriesRes.data.items : []);
    setLoading(false);
  }, [handle401]);

  const handleCreateWebhook = useCallback(async () => {
    setCreatingWebhook(true);
    setError(null);

    const response = await dashboardApiRequest<{ item?: WebhookItem }>("/api/integrations/webhooks", {
      method: "POST",
      body: {
        name: newWebhookName.trim(),
        endpoint_url: newWebhookUrl.trim(),
        secret: newWebhookSecret.trim() || null,
        event_types: newWebhookEvents
          .split(",")
          .map((item) => item.trim())
          .filter((item) => item.length > 0),
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

    setNewWebhookName("");
    setNewWebhookUrl("");
    setNewWebhookSecret("");
    await fetchIntegrations();
    setCreatingWebhook(false);
  }, [fetchIntegrations, handle401, newWebhookEvents, newWebhookName, newWebhookSecret, newWebhookUrl]);

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

  return (
    <section className="space-y-4">
      <h1 className="text-2xl font-semibold">Integrations (Webhook)</h1>
      <p className="text-sm text-muted-foreground">Manage event subscriptions, delivery status, and retry processing.</p>

      <div className="ds-card p-4">
        <div className="mb-2 flex flex-wrap items-center gap-2">
          <Button
            type="button"
            onClick={() => void handleProcessRetries()}
            disabled={!canManage || processingRetries}
            className="ds-btn h-11 rounded-md px-3 text-sm disabled:cursor-not-allowed disabled:opacity-60 md:h-9"
          >
            {processingRetries ? "Processing..." : "Process Retries"}
          </Button>
          {!canManage ? <p className="text-xs text-muted-foreground">Integration write actions are read-only for your role.</p> : null}
        </div>

        <div className="grid gap-2 sm:grid-cols-2">
          <Input
            value={newWebhookName}
            onChange={(event) => setNewWebhookName(event.target.value)}
            disabled={!canManage}
            placeholder="Webhook name"
            className="ds-input h-11 rounded-md px-3 text-sm md:h-9"
          />
          <Input
            value={newWebhookUrl}
            onChange={(event) => setNewWebhookUrl(event.target.value)}
            disabled={!canManage}
            placeholder="Endpoint URL"
            className="ds-input h-11 rounded-md px-3 text-sm md:h-9"
          />
          <Input
            value={newWebhookSecret}
            onChange={(event) => setNewWebhookSecret(event.target.value)}
            disabled={!canManage}
            placeholder="Secret (optional)"
            className="ds-input h-11 rounded-md px-3 text-sm md:h-9"
          />
          <Input
            value={newWebhookEvents}
            onChange={(event) => setNewWebhookEvents(event.target.value)}
            disabled={!canManage}
            placeholder="Event types (comma separated)"
            className="ds-input h-11 rounded-md px-3 text-sm md:h-9"
          />
        </div>
        <Button
          type="button"
          onClick={() => void handleCreateWebhook()}
          disabled={!canManage || creatingWebhook}
          className="mt-2 ds-btn h-11 rounded-md px-3 text-sm disabled:cursor-not-allowed disabled:opacity-60 md:h-9"
        >
          {creatingWebhook ? "Creating..." : "Create Webhook"}
        </Button>
      </div>

      {loading ? <p className="text-sm text-muted-foreground">Loading webhooks...</p> : null}
      {error ? (
        <div className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error}
        </div>
      ) : null}

      <div className="grid gap-3 sm:grid-cols-2">
        <article className="ds-card p-4">
          <p className="text-sm font-medium">Subscriptions</p>
          <div className="mt-2 space-y-1">
            {webhooks.length === 0 ? <p className="text-xs text-muted-foreground">No subscriptions.</p> : null}
            {webhooks.slice(0, 12).map((hook) => (
              <p key={`hook-${hook.id}`} className="text-xs">
                {hook.name} ({hook.is_active ? "active" : "disabled"}) · {hook.event_types.join(", ")}
              </p>
            ))}
          </div>
        </article>

        <article className="ds-card p-4">
          <p className="text-sm font-medium">Recent Deliveries</p>
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
