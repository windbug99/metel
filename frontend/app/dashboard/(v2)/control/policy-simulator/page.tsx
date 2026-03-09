"use client";

import { Select } from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { useCallback, useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { Loader2 } from "lucide-react";
import PageTitleWithTooltip from "@/components/dashboard-v2/page-title-with-tooltip";

import { buildNextPath, dashboardApiGet, dashboardApiRequest } from "../../../../../lib/dashboard-v2-client";

type ApiKeyItem = {
  id: number;
  name: string;
  key_prefix: string;
};

type SimulateResult = {
  decision: "allowed" | "blocked";
  tool_name: string;
  service: string;
  api_key_id: number | null;
  reasons: Array<{ code?: string; message?: string; source?: string; [key: string]: unknown }>;
  risk?: { allowed?: boolean; reason?: string | null; risk_type?: string | null };
};

export default function DashboardPolicySimulatorPage() {
  const pathname = usePathname();
  const router = useRouter();

  const [apiKeys, setApiKeys] = useState<ApiKeyItem[]>([]);
  const [apiKeysLoading, setApiKeysLoading] = useState(true);
  const [apiKeyId, setApiKeyId] = useState("");
  const [toolName, setToolName] = useState("");
  const [argumentsJson, setArgumentsJson] = useState("{}");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<SimulateResult | null>(null);

  const handle401 = useCallback(() => {
    const next = encodeURIComponent(buildNextPath(pathname, window.location.search));
    router.replace(`/?next=${next}`);
  }, [pathname, router]);

  const fetchApiKeys = useCallback(async () => {
    setApiKeysLoading(true);
    const response = await dashboardApiGet<{ items?: ApiKeyItem[] }>("/api/api-keys");
    if (response.status === 401) {
      handle401();
      setApiKeysLoading(false);
      return;
    }
    if (!response.ok || !response.data) {
      setApiKeysLoading(false);
      return;
    }
    setApiKeys(Array.isArray(response.data.items) ? response.data.items : []);
    setApiKeysLoading(false);
  }, [handle401]);

  const runSimulation = useCallback(async () => {
    const trimmedToolName = toolName.trim();
    if (!trimmedToolName) {
      setError("Tool name is required.");
      return;
    }

    let parsedArguments: Record<string, unknown> = {};
    try {
      const parsed = JSON.parse((argumentsJson || "{}").trim()) as unknown;
      if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) {
        setError("Arguments JSON must be an object.");
        return;
      }
      parsedArguments = parsed as Record<string, unknown>;
    } catch {
      setError("Invalid arguments JSON.");
      return;
    }

    setLoading(true);
    setError(null);
    setResult(null);

    const response = await dashboardApiRequest<SimulateResult>("/api/policies/simulate", {
      method: "POST",
      body: {
        api_key_id: apiKeyId ? Number(apiKeyId) : null,
        tool_name: trimmedToolName,
        arguments: parsedArguments,
      },
    });

    if (response.status === 401) {
      handle401();
      setLoading(false);
      return;
    }
    if (response.status === 403) {
      setError("Access denied while running simulation.");
      setLoading(false);
      return;
    }
    if (!response.ok || !response.data) {
      setError(response.error ?? "Failed to run policy simulation.");
      setLoading(false);
      return;
    }

    setResult(response.data);
    setLoading(false);
  }, [apiKeyId, argumentsJson, handle401, toolName]);

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

  if (apiKeysLoading) {
    return (
      <section className="space-y-4">
        <PageTitleWithTooltip
          title="Policy Simulator"
          tooltip="Simulate policy decisions before executing tool calls."
        />
        <p className="text-sm text-muted-foreground">Preview whether a request is allowed or blocked before execution.</p>
        <div className="ds-card flex min-h-[220px] items-center justify-center p-4">
          <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
        </div>
      </section>
    );
  }

  return (
    <section className="space-y-4">
      <PageTitleWithTooltip
        title="Policy Simulator"
        tooltip="Simulate policy decisions before executing tool calls."
      />
      <p className="text-sm text-muted-foreground">Preview whether a request is allowed or blocked before execution.</p>

      <div className="ds-card space-y-3 p-4">
        <div className="flex flex-wrap items-center gap-2">
          <Select value={apiKeyId} onChange={(event) => setApiKeyId(event.target.value)} className="ds-input h-11 rounded-md px-3 text-sm md:h-9">
            <option value="">No API key scope</option>
            {apiKeys.map((key) => (
              <option key={`sim-key-${key.id}`} value={String(key.id)}>
                {key.name} ({key.key_prefix}...)
              </option>
            ))}
          </Select>
          <Input
            value={toolName}
            onChange={(event) => setToolName(event.target.value)}
            placeholder="Tool name"
            className="ds-input h-11 min-w-[260px] rounded-md px-3 text-sm md:h-9"
          />
          <Button
            type="button"
            onClick={() => void runSimulation()}
            disabled={loading}
            className="ds-btn h-11 rounded-md px-3 text-sm disabled:cursor-not-allowed disabled:opacity-60 md:h-9"
          >
            {loading ? "Simulating..." : "Simulate"}
          </Button>
        </div>
        <textarea
          value={argumentsJson}
          onChange={(event) => setArgumentsJson(event.target.value)}
          placeholder='Arguments JSON, e.g. {"team_id":"team-a","title":"hello"}'
          className="ds-input min-h-[120px] w-full rounded-md px-3 py-2 text-xs font-mono"
        />
      </div>

      {error ? (
        <div className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error}
        </div>
      ) : null}

      {result ? (
        <div className="ds-card p-4">
          <p className="text-sm font-semibold">
            Decision:{" "}
            <span className={result.decision === "allowed" ? "text-chart-2" : "text-destructive"}>{result.decision}</span>
          </p>
          <pre className="mt-2 overflow-x-auto rounded bg-muted/60 p-3 text-[11px] text-muted-foreground">
            {JSON.stringify(result, null, 2)}
          </pre>
        </div>
      ) : null}
    </section>
  );
}
