"use client";

import { useCallback, useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";

import { buildNextPath, dashboardApiGet, dashboardApiRequest } from "../../../../../lib/dashboard-v2-client";
import StatusBadge from "../../../../../components/dashboard-v2/status-badge";

type ApiKeyItem = {
  id: number;
  name: string;
  key_prefix: string;
  is_active: boolean;
  last_used_at: string | null;
};

type TeamItem = {
  id: number;
  name: string;
};

type CreateApiKeyPayload = {
  id: number;
  name: string;
  key_prefix: string;
  api_key?: string;
};

export default function DashboardApiKeysPage() {
  const pathname = usePathname();
  const router = useRouter();
  const [items, setItems] = useState<ApiKeyItem[]>([]);
  const [teams, setTeams] = useState<TeamItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [createName, setCreateName] = useState("default");
  const [createTeamId, setCreateTeamId] = useState("");
  const [createMemo, setCreateMemo] = useState("");
  const [creating, setCreating] = useState(false);
  const [createdApiKey, setCreatedApiKey] = useState<string | null>(null);

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
    setItems(Array.isArray(result.data.items) ? result.data.items : []);

    const teamResult = await dashboardApiGet<{ items?: TeamItem[] }>("/api/teams");
    if (teamResult.ok && teamResult.data) {
      setTeams(Array.isArray(teamResult.data.items) ? teamResult.data.items : []);
    }
    setLoading(false);
  }, [pathname, router]);

  const handleCreateApiKey = useCallback(async () => {
    setCreating(true);
    setCreatedApiKey(null);
    setError(null);

    const result = await dashboardApiRequest<CreateApiKeyPayload>("/api/api-keys", {
      method: "POST",
      body: {
        name: createName.trim() || "default",
        team_id: createTeamId ? Number(createTeamId) : null,
        memo: createMemo.trim() || null,
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
    await fetchApiKeys();
    setCreating(false);
  }, [createMemo, createName, createTeamId, fetchApiKeys, pathname, router]);

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

  return (
    <section className="space-y-4">
      <h1 className="text-2xl font-semibold">API Keys</h1>
      <p className="text-sm text-[var(--text-secondary)]">API Keys list is now fetched in page scope.</p>

      <div className="ds-card p-4">
        <p className="mb-3 text-sm font-medium">Create API key</p>
        <div className="flex flex-wrap items-center gap-2">
          <input
            value={createName}
            onChange={(event) => setCreateName(event.target.value)}
            placeholder="Key name"
            className="ds-input h-11 rounded-md px-3 text-sm md:h-9"
          />
          <select
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
          </select>
          <input
            value={createMemo}
            onChange={(event) => setCreateMemo(event.target.value)}
            placeholder="Memo (optional)"
            className="ds-input h-11 min-w-[220px] rounded-md px-3 text-sm md:h-9"
          />
          <button
            type="button"
            onClick={() => void handleCreateApiKey()}
            disabled={creating}
            className="ds-btn h-11 rounded-md px-3 text-sm disabled:cursor-not-allowed disabled:opacity-60 md:h-9"
          >
            {creating ? "Creating..." : "Create API key"}
          </button>
        </div>
        {createdApiKey ? (
          <div className="mt-3 rounded-md border border-[var(--warning-500)]/40 bg-[color-mix(in_srgb,var(--warning-500)_12%,white)] p-3">
            <p className="text-xs font-medium text-[var(--warning-500)]">Copy now. This key is shown only once.</p>
            <div className="mt-2 flex items-center gap-2">
              <code className="block flex-1 overflow-x-auto rounded bg-[var(--surface)] px-2 py-1 text-xs">{createdApiKey}</code>
              <button type="button" onClick={() => void copyApiKey()} className="ds-btn h-9 rounded-md px-3 text-xs">
                Copy
              </button>
            </div>
          </div>
        ) : null}
      </div>

      {loading ? <p className="text-sm text-[var(--muted)]">Loading API keys...</p> : null}
      {error ? (
        <div className="rounded-md border border-[var(--danger-500)]/40 bg-[color-mix(in_srgb,var(--danger-500)_12%,white)] px-3 py-2 text-sm text-[var(--danger-500)]">
          {error}
        </div>
      ) : null}

      {!loading && !error ? (
        <div className="ds-card overflow-x-auto">
          <table className="min-w-[640px] text-sm">
            <thead className="bg-[var(--surface-subtle)] text-left text-xs text-[var(--muted)]">
              <tr>
                <th className="px-4 py-3">Name</th>
                <th className="px-4 py-3">Prefix</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Last Used</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.id} className="border-t border-[var(--border)]">
                  <td className="px-4 py-3">{item.name}</td>
                  <td className="px-4 py-3 font-mono text-xs">{item.key_prefix}</td>
                  <td className="px-4 py-3">
                    <StatusBadge kind="key" value={item.is_active ? "active" : "revoked"} />
                  </td>
                  <td className="px-4 py-3">{item.last_used_at ? new Date(item.last_used_at).toLocaleString() : "-"}</td>
                </tr>
              ))}
              {items.length === 0 ? (
                <tr>
                  <td className="px-4 py-4 text-[var(--muted)]" colSpan={4}>
                    No API keys found.
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      ) : null}
    </section>
  );
}
