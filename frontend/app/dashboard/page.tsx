"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { supabase } from "../../lib/supabase";
import { upsertUserProfile } from "../../lib/profile";

type UserProfile = {
  id: string;
  email: string | null;
  full_name: string | null;
  created_at: string;
} | null;

type NotionStatus = {
  connected: boolean;
  integration?: {
    workspace_name: string | null;
    workspace_id: string | null;
    updated_at: string | null;
  } | null;
} | null;

type NotionPage = {
  id: string;
  title: string;
  url: string;
  last_edited_time: string;
};

type TelegramStatus = {
  connected: boolean;
  telegram_chat_id?: number | null;
  telegram_username?: string | null;
} | null;

type TelegramConnectInfo = {
  deepLink: string;
  tgDeepLink: string;
  startCommand: string;
  botUsername: string;
  expiresInSeconds: number;
} | null;

type CommandLog = {
  id: number;
  channel: string;
  command: string;
  status: string;
  error_code: string | null;
  detail: string | null;
  plan_source: string | null;
  execution_mode: string | null;
  autonomous_fallback_reason: string | null;
  verification_reason: string | null;
  llm_provider: string | null;
  llm_model: string | null;
  created_at: string;
};

export default function DashboardPage() {
  const router = useRouter();
  const [loading, setLoading] = useState(true);
  const [profile, setProfile] = useState<UserProfile>(null);
  const [notionStatus, setNotionStatus] = useState<NotionStatus>(null);
  const [notionStatusError, setNotionStatusError] = useState<string | null>(null);
  const [disconnecting, setDisconnecting] = useState(false);
  const [loadingPages, setLoadingPages] = useState(false);
  const [pagesError, setPagesError] = useState<string | null>(null);
  const [notionPages, setNotionPages] = useState<NotionPage[]>([]);
  const [telegramStatus, setTelegramStatus] = useState<TelegramStatus>(null);
  const [telegramStatusError, setTelegramStatusError] = useState<string | null>(null);
  const [telegramDisconnecting, setTelegramDisconnecting] = useState(false);
  const [telegramConnecting, setTelegramConnecting] = useState(false);
  const [telegramConnectInfo, setTelegramConnectInfo] = useState<TelegramConnectInfo>(null);
  const [telegramPolling, setTelegramPolling] = useState(false);
  const [commandLogs, setCommandLogs] = useState<CommandLog[]>([]);
  const [commandLogsLoading, setCommandLogsLoading] = useState(false);
  const [commandLogsError, setCommandLogsError] = useState<string | null>(null);
  const [commandLogStatusFilter, setCommandLogStatusFilter] = useState<"all" | "success" | "error">("all");
  const [commandLogCommandFilter, setCommandLogCommandFilter] = useState<string>("all");

  const telegramPollIntervalRef = useRef<number | null>(null);
  const telegramPollTimeoutRef = useRef<number | null>(null);

  const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL;

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

  const fetchNotionStatus = useCallback(
    async () => {
      if (!apiBaseUrl) {
        return;
      }

      try {
        const headers = await getAuthHeaders();
        const notionResponse = await fetch(
          `${apiBaseUrl}/api/oauth/notion/status`,
          { headers }
        );
        if (notionResponse.ok) {
          const notionData: NotionStatus = await notionResponse.json();
          setNotionStatus(notionData);
          setNotionStatusError(null);
        } else {
          setNotionStatusError("Failed to fetch Notion status.");
        }
      } catch {
        setNotionStatusError("Network error while fetching Notion status.");
      }
    },
    [apiBaseUrl, getAuthHeaders]
  );

  const fetchTelegramStatus = useCallback(async () => {
    if (!apiBaseUrl) {
      return;
    }

    try {
      const headers = await getAuthHeaders();
      const response = await fetch(`${apiBaseUrl}/api/telegram/status`, { headers });
      if (response.ok) {
        const data: TelegramStatus = await response.json();
        setTelegramStatus(data);
        setTelegramStatusError(null);
        if (data?.connected) {
          setTelegramConnectInfo(null);
          setTelegramPolling(false);
          if (telegramPollIntervalRef.current) {
            window.clearInterval(telegramPollIntervalRef.current);
            telegramPollIntervalRef.current = null;
          }
          if (telegramPollTimeoutRef.current) {
            window.clearTimeout(telegramPollTimeoutRef.current);
            telegramPollTimeoutRef.current = null;
          }
        }
      } else {
        setTelegramStatusError("Failed to fetch Telegram status.");
      }
    } catch {
      setTelegramStatusError("Network error while fetching Telegram status.");
    }
  }, [apiBaseUrl, getAuthHeaders]);

  const startTelegramStatusPolling = useCallback(() => {
    if (telegramPollIntervalRef.current) {
      window.clearInterval(telegramPollIntervalRef.current);
    }
    if (telegramPollTimeoutRef.current) {
      window.clearTimeout(telegramPollTimeoutRef.current);
    }

    setTelegramPolling(true);
    telegramPollIntervalRef.current = window.setInterval(() => {
      void fetchTelegramStatus();
    }, 3000);
    telegramPollTimeoutRef.current = window.setTimeout(() => {
      if (telegramPollIntervalRef.current) {
        window.clearInterval(telegramPollIntervalRef.current);
        telegramPollIntervalRef.current = null;
      }
      setTelegramPolling(false);
    }, 120000);
  }, [fetchTelegramStatus]);

  const fetchCommandLogs = useCallback(async () => {
    setCommandLogsLoading(true);
    try {
      const { data, error } = await supabase
        .from("command_logs")
        .select(
          "id, channel, command, status, error_code, detail, plan_source, execution_mode, autonomous_fallback_reason, verification_reason, llm_provider, llm_model, created_at"
        )
        .order("created_at", { ascending: false })
        .limit(20);

      if (error) {
        setCommandLogsError("Failed to fetch command logs.");
        return;
      }

      setCommandLogs(Array.isArray(data) ? (data as CommandLog[]) : []);
      setCommandLogsError(null);
    } catch {
      setCommandLogsError("Network error while fetching command logs.");
    } finally {
      setCommandLogsLoading(false);
    }
  }, []);

  const commandFilterOptions = useMemo(() => {
    const unique = Array.from(new Set(commandLogs.map((log) => log.command).filter(Boolean)));
    return unique.sort((a, b) => a.localeCompare(b));
  }, [commandLogs]);

  const filteredCommandLogs = useMemo(() => {
    return commandLogs.filter((log) => {
      if (commandLogStatusFilter !== "all" && log.status !== commandLogStatusFilter) {
        return false;
      }
      if (commandLogCommandFilter !== "all" && log.command !== commandLogCommandFilter) {
        return false;
      }
      return true;
    });
  }, [commandLogs, commandLogStatusFilter, commandLogCommandFilter]);

  const agentTelemetry = useMemo(() => {
    const agentLogs = commandLogs.filter((log) => log.command === "agent_plan");
    const total = agentLogs.length;
    const autonomous = agentLogs.filter((log) => log.execution_mode === "autonomous").length;
    const rule = agentLogs.filter((log) => log.execution_mode === "rule").length;
    const llmPlan = agentLogs.filter((log) => log.plan_source === "llm").length;
    const rulePlan = agentLogs.filter((log) => log.plan_source === "rule").length;
    const success = agentLogs.filter((log) => log.status === "success").length;
    const error = agentLogs.filter((log) => log.status === "error").length;
    const autonomousSuccess = agentLogs.filter(
      (log) => log.execution_mode === "autonomous" && log.status === "success"
    ).length;
    const fallbackLogs = agentLogs.filter((log) => Boolean(log.autonomous_fallback_reason));
    const fallbackReasonCount = fallbackLogs.reduce<Record<string, number>>((acc, log) => {
      const key = log.autonomous_fallback_reason ?? "unknown";
      acc[key] = (acc[key] ?? 0) + 1;
      return acc;
    }, {});
    const topFallbackReasons = Object.entries(fallbackReasonCount)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 3);
    const verificationLogs = agentLogs.filter((log) => Boolean(log.verification_reason));
    const verificationReasonCount = verificationLogs.reduce<Record<string, number>>((acc, log) => {
      const key = log.verification_reason ?? "unknown";
      acc[key] = (acc[key] ?? 0) + 1;
      return acc;
    }, {});
    const topVerificationReasons = Object.entries(verificationReasonCount)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 3);

    const autonomousSuccessRate = autonomous > 0 ? autonomousSuccess / autonomous : 0;
    const fallbackRate = total > 0 ? fallbackLogs.length / total : 0;

    return {
      total,
      autonomous,
      rule,
      llmPlan,
      rulePlan,
      success,
      error,
      autonomousSuccess,
      autonomousSuccessRate,
      fallbackCount: fallbackLogs.length,
      fallbackRate,
      topFallbackReasons,
      verificationCount: verificationLogs.length,
      topVerificationReasons
    };
  }, [commandLogs]);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    const url = new URL(window.location.href);
    if (url.searchParams.has("notion")) {
      url.searchParams.delete("notion");
      window.history.replaceState({}, "", url.toString());
    }
  }, []);

  useEffect(() => {
    return () => {
      if (telegramPollIntervalRef.current) {
        window.clearInterval(telegramPollIntervalRef.current);
      }
      if (telegramPollTimeoutRef.current) {
        window.clearTimeout(telegramPollTimeoutRef.current);
      }
    };
  }, []);

  useEffect(() => {
    let mounted = true;

    const load = async () => {
      try {
        const {
          data: { user }
        } = await supabase.auth.getUser();

        if (!mounted) {
          return;
        }

        if (!user) {
          router.replace("/");
          return;
        }

        const { data } = await supabase
          .from("users")
          .select("id, email, full_name, created_at")
          .eq("id", user.id)
          .single();

        if (!data) {
          await upsertUserProfile();
        }

        const { data: refreshed } = await supabase
          .from("users")
          .select("id, email, full_name, created_at")
          .eq("id", user.id)
          .single();

        await fetchNotionStatus();
        await fetchTelegramStatus();
        await fetchCommandLogs();

        if (!mounted) {
          return;
        }

        setProfile(refreshed ?? data ?? null);
      } finally {
        if (mounted) {
          setLoading(false);
        }
      }
    };

    void load();

    return () => {
      mounted = false;
    };
  }, [router, fetchNotionStatus, fetchTelegramStatus, fetchCommandLogs]);

  const handleDisconnectNotion = async () => {
    if (!apiBaseUrl || !profile?.id || disconnecting) {
      return;
    }

    setDisconnecting(true);
    try {
      const headers = await getAuthHeaders();
      const response = await fetch(
        `${apiBaseUrl}/api/oauth/notion/disconnect`,
        { method: "DELETE", headers }
      );
      if (!response.ok) {
        setNotionStatusError("Failed to disconnect Notion.");
        return;
      }
      setNotionStatus({ connected: false, integration: null });
      setNotionStatusError(null);
    } catch {
      setNotionStatusError("Network error while disconnecting Notion.");
    } finally {
      setDisconnecting(false);
    }
  };

  const handleConnectNotion = async () => {
    if (!apiBaseUrl || !profile?.id) {
      return;
    }

    try {
      const headers = await getAuthHeaders();
      const response = await fetch(`${apiBaseUrl}/api/oauth/notion/start`, {
        method: "POST",
        headers,
      });
      const payload = await response.json();
      if (!response.ok || !payload?.auth_url) {
        setNotionStatusError("Failed to start Notion connection.");
        return;
      }
      window.location.href = payload.auth_url;
    } catch {
      setNotionStatusError("Network error while starting Notion connection.");
    }
  };

  const handleConnectTelegram = async () => {
    if (!apiBaseUrl || !profile?.id || telegramConnecting) {
      return;
    }

    setTelegramConnecting(true);
    try {
      const headers = await getAuthHeaders();
      const response = await fetch(`${apiBaseUrl}/api/telegram/connect-link`, {
        method: "POST",
        headers,
      });
      const payload = await response.json();
      if (!response.ok || !payload?.deep_link) {
        const message =
          payload?.error?.message ?? payload?.detail ?? "Failed to create Telegram connection link.";
        setTelegramStatusError(message);
        return;
      }
      const startCommand = typeof payload.start_command === "string" ? payload.start_command : "";
      const botUsername = typeof payload.bot_username === "string" ? payload.bot_username : "";
      const expiresInSeconds = typeof payload.expires_in_seconds === "number" ? payload.expires_in_seconds : 1800;
      const tgDeepLink = typeof payload.tg_deep_link === "string" ? payload.tg_deep_link : "";
      setTelegramConnectInfo({
        deepLink: payload.deep_link,
        tgDeepLink,
        startCommand,
        botUsername,
        expiresInSeconds,
      });
      if (tgDeepLink) {
        window.location.href = tgDeepLink;
        window.setTimeout(() => {
          window.open(payload.deep_link, "_blank", "noopener,noreferrer");
        }, 500);
      } else {
        window.open(payload.deep_link, "_blank", "noopener,noreferrer");
      }
      setTelegramStatusError(null);
      startTelegramStatusPolling();
    } catch {
      setTelegramStatusError("Network error while starting Telegram connection.");
    } finally {
      setTelegramConnecting(false);
    }
  };

  const handleDisconnectTelegram = async () => {
    if (!apiBaseUrl || !profile?.id || telegramDisconnecting) {
      return;
    }

    setTelegramDisconnecting(true);
    try {
      const headers = await getAuthHeaders();
      const response = await fetch(`${apiBaseUrl}/api/telegram/disconnect`, {
        method: "DELETE",
        headers,
      });
      if (!response.ok) {
        setTelegramStatusError("Failed to disconnect Telegram.");
        return;
      }
      setTelegramStatus({ connected: false, telegram_chat_id: null, telegram_username: null });
      setTelegramConnectInfo(null);
      setTelegramStatusError(null);
      await fetchTelegramStatus();
    } catch {
      setTelegramStatusError("Network error while disconnecting Telegram.");
    } finally {
      setTelegramDisconnecting(false);
    }
  };

  const copyText = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setTelegramStatusError("Copied. Paste and run the command in Telegram.");
    } catch {
      setTelegramStatusError("Clipboard copy failed. Please copy manually.");
    }
  };

  const handleLoadNotionPages = async () => {
    if (!apiBaseUrl || !profile?.id || loadingPages || !notionStatus?.connected) {
      return;
    }

    setLoadingPages(true);
    setPagesError(null);
    try {
      const headers = await getAuthHeaders();
      const response = await fetch(
        `${apiBaseUrl}/api/oauth/notion/pages?page_size=5`,
        { headers }
      );
      const payload = await response.json();
      if (!response.ok || !payload?.ok) {
        const message =
          payload?.error?.message ?? payload?.detail ?? "Failed to fetch Notion pages.";
        setPagesError(message);
        return;
      }
      setNotionPages(Array.isArray(payload.pages) ? payload.pages : []);
    } catch {
      setPagesError("Network error while fetching Notion pages.");
    } finally {
      setLoadingPages(false);
    }
  };

  if (loading) {
    return (
      <main className="mx-auto max-w-5xl px-6 py-16">
        <p className="text-sm text-gray-600">Loading dashboard...</p>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-5xl px-6 py-14">
      <header className="rounded-2xl border border-gray-200 bg-white p-7 shadow-sm">
        <p className="font-mono text-xs uppercase tracking-wider text-gray-500">metel</p>
        <h1 className="mt-2 text-4xl font-semibold tracking-tight text-black">Dashboard</h1>
        <p className="mt-2 text-sm text-gray-600">
          Control messenger links, service integrations, and autonomous agent logs.
        </p>
      </header>

      <section className="mt-6 rounded-2xl border border-gray-200 bg-white p-6 shadow-sm">
        <h2 className="text-lg font-semibold text-black">User</h2>
        <div className="mt-4 grid gap-4 sm:grid-cols-3">
          <div>
            <p className="text-xs text-gray-500">Email</p>
            <p className="mt-1 text-sm text-gray-900">{profile?.email ?? "-"}</p>
          </div>
          <div>
            <p className="text-xs text-gray-500">User ID</p>
            <p className="mt-1 break-all text-sm text-gray-900">{profile?.id ?? "-"}</p>
          </div>
          <div>
            <p className="text-xs text-gray-500">Created</p>
            <p className="mt-1 text-sm text-gray-900">
              {profile?.created_at ? new Date(profile.created_at).toLocaleString() : "-"}
            </p>
          </div>
        </div>
      </section>

      <section className="mt-6 rounded-2xl border border-gray-200 bg-white p-6 shadow-sm">
        <h2 className="text-lg font-semibold text-black">Messenger Connection</h2>
        {telegramStatusError ? (
          <p className="mt-3 text-sm text-amber-700">{telegramStatusError}</p>
        ) : null}
        <p className="mt-3 text-sm text-gray-700">
          Status: {telegramStatus?.connected ? "Connected" : "Not connected"}
        </p>
        {telegramStatus?.connected ? (
          <p className="mt-1 text-sm text-gray-700">
            Account: {telegramStatus.telegram_username ? `@${telegramStatus.telegram_username}` : "-"}
          </p>
        ) : null}
        {apiBaseUrl && profile?.id ? (
          <div className="mt-4 flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => {
                void handleConnectTelegram();
              }}
              disabled={telegramConnecting}
              className="inline-block rounded-md bg-black px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
            >
              {telegramConnecting ? "Generating link..." : "Connect Telegram"}
            </button>
            {telegramStatus?.connected ? (
              <button
                type="button"
                onClick={handleDisconnectTelegram}
                disabled={telegramDisconnecting}
                className="inline-block rounded-md border border-gray-300 px-4 py-2 text-sm font-medium text-gray-900 disabled:opacity-50"
              >
                {telegramDisconnecting ? "Disconnecting..." : "Disconnect"}
              </button>
            ) : null}
          </div>
        ) : (
          <p className="mt-3 text-sm text-amber-700">
            Set NEXT_PUBLIC_API_BASE_URL to enable Telegram connection.
          </p>
        )}
        {telegramConnectInfo && !telegramStatus?.connected ? (
          <div className="mt-4 rounded-lg border border-gray-200 bg-gray-50 p-4">
            <p className="text-sm text-gray-700">
              If Start does not respond in Telegram, copy and send this command manually to{" "}
              {telegramConnectInfo.botUsername ? `@${telegramConnectInfo.botUsername}` : "your bot"}.
            </p>
            <p className="font-mono mt-2 break-all rounded border border-gray-200 bg-white p-2 text-xs text-gray-700">
              {telegramConnectInfo.startCommand || "(no start command)"}
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => {
                  if (telegramConnectInfo.startCommand) {
                    void copyText(telegramConnectInfo.startCommand);
                  }
                }}
                className="inline-block rounded-md border border-gray-300 px-3 py-2 text-sm font-medium text-gray-900"
              >
                Copy Start Command
              </button>
              <button
                type="button"
                onClick={() => {
                  if (telegramConnectInfo.tgDeepLink) {
                    window.location.href = telegramConnectInfo.tgDeepLink;
                    window.setTimeout(() => {
                      window.open(telegramConnectInfo.deepLink, "_blank", "noopener,noreferrer");
                    }, 500);
                    return;
                  }
                  window.open(telegramConnectInfo.deepLink, "_blank", "noopener,noreferrer");
                }}
                className="inline-block rounded-md border border-gray-300 px-3 py-2 text-sm font-medium text-gray-900"
              >
                Open Telegram Again
              </button>
            </div>
            <p className="mt-2 text-xs text-gray-600">
              {telegramPolling ? "Auto-checking connection status..." : "Auto-check stopped. Re-run connect if needed."}
            </p>
            <p className="mt-1 text-xs text-gray-500">
              Expires in about {Math.max(1, Math.floor(telegramConnectInfo.expiresInSeconds / 60))} min
            </p>
          </div>
        ) : null}
      </section>

      <section className="mt-6 rounded-2xl border border-gray-200 bg-white p-6 shadow-sm">
        <h2 className="text-lg font-semibold text-black">Service Connection</h2>
        {notionStatusError ? (
          <p className="mt-3 text-sm text-amber-700">{notionStatusError}</p>
        ) : null}
        <p className="mt-3 text-sm text-gray-700">
          Notion: {notionStatus?.connected ? "Connected" : "Not connected"}
        </p>
        {notionStatus?.connected ? (
          <p className="mt-1 text-sm text-gray-700">
            Workspace: {notionStatus.integration?.workspace_name ?? "-"}
          </p>
        ) : null}
        {apiBaseUrl && profile?.id ? (
          <div className="mt-4 flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => {
                void handleConnectNotion();
              }}
              className="inline-block rounded-md bg-black px-4 py-2 text-sm font-medium text-white"
            >
              Connect Notion
            </button>
            {notionStatus?.connected ? (
              <button
                type="button"
                onClick={handleDisconnectNotion}
                disabled={disconnecting}
                className="inline-block rounded-md border border-gray-300 px-4 py-2 text-sm font-medium text-gray-900 disabled:opacity-50"
              >
                {disconnecting ? "Disconnecting..." : "Disconnect"}
              </button>
            ) : null}
          </div>
        ) : (
          <p className="mt-3 text-sm text-amber-700">
            Set NEXT_PUBLIC_API_BASE_URL to enable Notion connection.
          </p>
        )}
        {notionStatus?.connected ? (
          <div className="mt-6 rounded-lg border border-gray-200 bg-gray-50 p-4">
            <div className="flex items-center justify-between gap-2">
              <h3 className="text-base font-semibold text-gray-900">Recent Notion Pages</h3>
              <button
                type="button"
                onClick={handleLoadNotionPages}
                disabled={loadingPages}
                className="rounded-md border border-gray-300 bg-white px-3 py-2 text-sm font-medium text-gray-900 disabled:opacity-50"
              >
                {loadingPages ? "Loading..." : "Fetch"}
              </button>
            </div>
            {pagesError ? <p className="mt-3 text-sm text-amber-700">{pagesError}</p> : null}
            {notionPages.length > 0 ? (
              <ul className="mt-3 space-y-2">
                {notionPages.map((page) => (
                  <li key={page.id} className="rounded-md border border-gray-200 bg-white p-3">
                    <a
                      href={page.url}
                      target="_blank"
                      rel="noreferrer"
                      className="text-sm font-medium text-blue-700 underline"
                    >
                      {page.title}
                    </a>
                    <p className="mt-1 text-xs text-gray-600">
                      {new Date(page.last_edited_time).toLocaleString()}
                    </p>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="mt-3 text-sm text-gray-600">Click fetch to load recent pages.</p>
            )}
          </div>
        ) : null}
      </section>

      <section className="mt-6 rounded-2xl border border-gray-200 bg-white p-6 shadow-sm">
        <div className="flex items-center justify-between gap-2">
          <h2 className="text-lg font-semibold text-black">Execution Logs (latest 20)</h2>
          <div className="flex flex-wrap items-center gap-2">
            <select
              value={commandLogStatusFilter}
              onChange={(event) => {
                setCommandLogStatusFilter(event.target.value as "all" | "success" | "error");
              }}
              className="rounded-md border border-gray-300 px-2 py-2 text-sm text-gray-900"
            >
              <option value="all">Status: All</option>
              <option value="success">Status: Success</option>
              <option value="error">Status: Error</option>
            </select>
            <select
              value={commandLogCommandFilter}
              onChange={(event) => {
                setCommandLogCommandFilter(event.target.value);
              }}
              className="rounded-md border border-gray-300 px-2 py-2 text-sm text-gray-900"
            >
              <option value="all">Command: All</option>
              {commandFilterOptions.map((commandName) => (
                <option key={commandName} value={commandName}>
                  {commandName}
                </option>
              ))}
            </select>
            <button
              type="button"
              onClick={() => {
                void fetchCommandLogs();
              }}
              disabled={commandLogsLoading}
              className="rounded-md border border-gray-300 px-3 py-2 text-sm font-medium text-gray-900 disabled:opacity-50"
            >
              {commandLogsLoading ? "Refreshing..." : "Refresh"}
            </button>
          </div>
        </div>
        <div className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
          <div className="rounded-md border border-gray-200 bg-gray-50 p-3">
            <p className="text-xs text-gray-600">Agent Logs</p>
            <p className="mt-1 text-sm font-semibold text-gray-900">{agentTelemetry.total}</p>
          </div>
          <div className="rounded-md border border-gray-200 bg-gray-50 p-3">
            <p className="text-xs text-gray-600">Execution Mode</p>
            <p className="mt-1 text-sm font-semibold text-gray-900">
              auto {agentTelemetry.autonomous} / rule {agentTelemetry.rule}
            </p>
          </div>
          <div className="rounded-md border border-gray-200 bg-gray-50 p-3">
            <p className="text-xs text-gray-600">Plan Source</p>
            <p className="mt-1 text-sm font-semibold text-gray-900">
              llm {agentTelemetry.llmPlan} / rule {agentTelemetry.rulePlan}
            </p>
          </div>
          <div className="rounded-md border border-gray-200 bg-gray-50 p-3">
            <p className="text-xs text-gray-600">Success / Error</p>
            <p className="mt-1 text-sm font-semibold text-gray-900">
              {agentTelemetry.success} / {agentTelemetry.error}
            </p>
          </div>
        </div>
        <div className="mt-3 grid gap-2 sm:grid-cols-2">
          <div className="rounded-md border border-gray-200 bg-gray-50 p-3">
            <p className="text-xs text-gray-600">Autonomous Success Rate (target 80%+)</p>
            <p className="mt-1 text-sm font-semibold text-gray-900">
              {(agentTelemetry.autonomousSuccessRate * 100).toFixed(1)}%
              {" "}
              <span
                className={
                  agentTelemetry.autonomousSuccessRate >= 0.8
                    ? "text-emerald-700"
                    : "text-amber-700"
                }
              >
                {agentTelemetry.autonomousSuccessRate >= 0.8 ? "PASS" : "CHECK"}
              </span>
            </p>
            <p className="mt-1 text-xs text-gray-600">
              autonomous success {agentTelemetry.autonomousSuccess} / {agentTelemetry.autonomous}
            </p>
          </div>
          <div className="rounded-md border border-gray-200 bg-gray-50 p-3">
            <p className="text-xs text-gray-600">Fallback Rate (target 20% or less)</p>
            <p className="mt-1 text-sm font-semibold text-gray-900">
              {(agentTelemetry.fallbackRate * 100).toFixed(1)}%
              {" "}
              <span
                className={
                  agentTelemetry.fallbackRate <= 0.2
                    ? "text-emerald-700"
                    : "text-amber-700"
                }
              >
                {agentTelemetry.fallbackRate <= 0.2 ? "PASS" : "CHECK"}
              </span>
            </p>
            <p className="mt-1 text-xs text-gray-600">
              fallback {agentTelemetry.fallbackCount} / {agentTelemetry.total}
            </p>
          </div>
        </div>
        {agentTelemetry.fallbackCount > 0 ? (
          <div className="mt-3 rounded-md border border-amber-200 bg-amber-50 p-3">
            <p className="text-xs font-medium text-amber-800">
              autonomous fallback count: {agentTelemetry.fallbackCount}
            </p>
            <p className="mt-1 text-xs text-amber-800">
              top reasons:{" "}
              {agentTelemetry.topFallbackReasons.map(([reason, count]) => `${reason}(${count})`).join(", ")}
            </p>
          </div>
        ) : null}
        {agentTelemetry.verificationCount > 0 ? (
          <div className="mt-3 rounded-md border border-rose-200 bg-rose-50 p-3">
            <p className="text-xs font-medium text-rose-800">
              verification reason records: {agentTelemetry.verificationCount}
            </p>
            <p className="mt-1 text-xs text-rose-800">
              top reasons:{" "}
              {agentTelemetry.topVerificationReasons.map(([reason, count]) => `${reason}(${count})`).join(", ")}
            </p>
          </div>
        ) : null}
        {commandLogsError ? <p className="mt-3 text-sm text-amber-700">{commandLogsError}</p> : null}
        <p className="mt-3 text-xs text-gray-600">
          Showing: {filteredCommandLogs.length} / {commandLogs.length}
        </p>
        {filteredCommandLogs.length > 0 ? (
          <ul className="mt-4 space-y-2">
            {filteredCommandLogs.map((log) => (
              <li key={log.id} className="rounded-md border border-gray-200 p-3">
                <p className="text-sm font-medium text-gray-900">
                  {log.command} · {log.status}
                </p>
                <p className="mt-1 text-xs text-gray-600">
                  {new Date(log.created_at).toLocaleString()} · {log.channel}
                </p>
                {(log.plan_source || log.execution_mode) ? (
                  <p className="mt-1 text-xs text-gray-600">
                    mode: {log.plan_source || "-"} / {log.execution_mode || "-"}
                    {log.autonomous_fallback_reason ? ` · fallback=${log.autonomous_fallback_reason}` : ""}
                    {log.verification_reason ? ` · verify=${log.verification_reason}` : ""}
                  </p>
                ) : null}
                {(log.llm_provider || log.llm_model) ? (
                  <p className="mt-1 text-xs text-gray-600">
                    llm: {log.llm_provider || "-"} / {log.llm_model || "-"}
                  </p>
                ) : null}
                {log.error_code ? (
                  <p className="mt-1 text-xs text-amber-700">error_code: {log.error_code}</p>
                ) : null}
                {log.detail ? (
                  <p className="mt-1 text-xs text-gray-600">detail: {log.detail}</p>
                ) : null}
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-3 text-sm text-gray-600">No logs match the current filters.</p>
        )}
      </section>
    </main>
  );
}
