"use client";

import { useCallback, useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";

import { buildNextPath, dashboardApiGet, dashboardApiRequest } from "../../../../../lib/dashboard-v2-client";

type OAuthStatus = {
  connected: boolean;
  integration?: {
    workspace_name?: string | null;
    workspace_id?: string | null;
    updated_at?: string | null;
  } | null;
};

type OAuthStartPayload = {
  ok: boolean;
  auth_url: string;
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

function ServiceRow({
  name,
  status,
  error,
  busy,
  onConnect,
  onDisconnect,
}: {
  name: string;
  status: OAuthStatus | null;
  error: string | null;
  busy: boolean;
  onConnect: () => void;
  onDisconnect: () => void;
}) {
  return (
    <article className="rounded-md border border-[var(--border)] p-3">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-sm font-medium">{name}</p>
          <p className="text-xs text-[var(--muted)]">{status?.connected ? "Connected" : "Not connected"}</p>
        </div>

        {status?.connected ? (
          <button
            type="button"
            onClick={onDisconnect}
            disabled={busy}
            className="ds-btn h-10 rounded-md px-3 text-xs disabled:cursor-not-allowed disabled:opacity-60"
          >
            Disconnect
          </button>
        ) : (
          <button
            type="button"
            onClick={onConnect}
            disabled={busy}
            className="ds-btn h-10 rounded-md px-3 text-xs disabled:cursor-not-allowed disabled:opacity-60"
          >
            Connect
          </button>
        )}
      </div>

      {status?.integration?.workspace_name ? (
        <p className="mt-2 text-xs text-[var(--muted)]">Workspace: {status.integration.workspace_name}</p>
      ) : null}
      {status?.integration?.updated_at ? (
        <p className="mt-1 text-xs text-[var(--muted)]">Updated: {formatDate(status.integration.updated_at)}</p>
      ) : null}
      {error ? <p className="mt-2 text-xs text-[var(--danger-500)]">{error}</p> : null}
    </article>
  );
}

export default function DashboardOAuthConnectionsPage() {
  const pathname = usePathname();
  const router = useRouter();

  const [notionStatus, setNotionStatus] = useState<OAuthStatus | null>(null);
  const [linearStatus, setLinearStatus] = useState<OAuthStatus | null>(null);

  const [notionError, setNotionError] = useState<string | null>(null);
  const [linearError, setLinearError] = useState<string | null>(null);

  const [notionBusy, setNotionBusy] = useState(false);
  const [linearBusy, setLinearBusy] = useState(false);

  const handle401 = useCallback(() => {
    const next = encodeURIComponent(buildNextPath(pathname, window.location.search));
    router.replace(`/?next=${next}`);
  }, [pathname, router]);

  const fetchStatus = useCallback(async () => {
    const [notionRes, linearRes] = await Promise.all([
      dashboardApiGet<OAuthStatus>("/api/oauth/notion/status"),
      dashboardApiGet<OAuthStatus>("/api/oauth/linear/status"),
    ]);

    if (notionRes.status === 401 || linearRes.status === 401) {
      handle401();
      return;
    }

    if (notionRes.ok && notionRes.data) {
      setNotionStatus(notionRes.data);
      setNotionError(null);
    } else {
      setNotionError("Failed to load Notion status.");
    }

    if (linearRes.ok && linearRes.data) {
      setLinearStatus(linearRes.data);
      setLinearError(null);
    } else {
      setLinearError("Failed to load Linear status.");
    }
  }, [handle401]);

  const handleConnect = useCallback(
    async (provider: "notion" | "linear") => {
      const setBusy = provider === "notion" ? setNotionBusy : setLinearBusy;
      const setErr = provider === "notion" ? setNotionError : setLinearError;
      setBusy(true);
      setErr(null);

      const res = await dashboardApiRequest<OAuthStartPayload>(`/api/oauth/${provider}/start`, {
        method: "POST",
      });
      if (res.status === 401) {
        handle401();
        setBusy(false);
        return;
      }
      if (!res.ok || !res.data?.auth_url) {
        setErr(`Failed to start ${provider} OAuth.`);
        setBusy(false);
        return;
      }

      window.location.href = res.data.auth_url;
    },
    [handle401]
  );

  const handleDisconnect = useCallback(
    async (provider: "notion" | "linear") => {
      const setBusy = provider === "notion" ? setNotionBusy : setLinearBusy;
      const setErr = provider === "notion" ? setNotionError : setLinearError;
      setBusy(true);
      setErr(null);

      const res = await dashboardApiRequest(`/api/oauth/${provider}/disconnect`, {
        method: "DELETE",
      });
      if (res.status === 401) {
        handle401();
        setBusy(false);
        return;
      }
      if (!res.ok) {
        setErr(`Failed to disconnect ${provider} OAuth.`);
        setBusy(false);
        return;
      }

      await fetchStatus();
      setBusy(false);
    },
    [fetchStatus, handle401]
  );

  useEffect(() => {
    void fetchStatus();
  }, [fetchStatus]);

  useEffect(() => {
    const handler = (event: Event) => {
      const custom = event as CustomEvent<{ path?: string }>;
      if (custom.detail?.path === pathname) {
        void fetchStatus();
      }
    };
    window.addEventListener("dashboard:v2:refresh", handler as EventListener);
    return () => {
      window.removeEventListener("dashboard:v2:refresh", handler as EventListener);
    };
  }, [fetchStatus, pathname]);

  return (
    <section className="space-y-4">
      <h1 className="text-2xl font-semibold">OAuth Connections</h1>
      <p className="text-sm text-[var(--text-secondary)]">Connect Notion and Linear to expose MCP tools.</p>

      <div className="ds-card space-y-3 p-4">
        <ServiceRow
          name="Notion"
          status={notionStatus}
          error={notionError}
          busy={notionBusy}
          onConnect={() => void handleConnect("notion")}
          onDisconnect={() => void handleDisconnect("notion")}
        />
        <ServiceRow
          name="Linear"
          status={linearStatus}
          error={linearError}
          busy={linearBusy}
          onConnect={() => void handleConnect("linear")}
          onDisconnect={() => void handleDisconnect("linear")}
        />
      </div>
    </section>
  );
}
