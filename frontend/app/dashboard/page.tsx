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

type LinearStatus = {
  connected: boolean;
  integration?: {
    workspace_name: string | null;
    workspace_id: string | null;
    updated_at: string | null;
  } | null;
} | null;

type GoogleStatus = {
  connected: boolean;
  integration?: {
    workspace_name: string | null;
    workspace_id: string | null;
    updated_at: string | null;
  } | null;
} | null;

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

function ServiceLogo({ src, alt }: { src: string; alt: string }) {
  return (
    <img
      src={src}
      alt={alt}
      width={20}
      height={20}
      className="h-5 w-5 rounded-sm object-contain"
    />
  );
}

export default function DashboardPage() {
  const router = useRouter();
  const [loading, setLoading] = useState(true);
  const [profile, setProfile] = useState<UserProfile>(null);
  const [notionStatus, setNotionStatus] = useState<NotionStatus>(null);
  const [notionStatusError, setNotionStatusError] = useState<string | null>(null);
  const [disconnecting, setDisconnecting] = useState(false);
  const [linearStatus, setLinearStatus] = useState<LinearStatus>(null);
  const [linearStatusError, setLinearStatusError] = useState<string | null>(null);
  const [linearConnecting, setLinearConnecting] = useState(false);
  const [linearDisconnecting, setLinearDisconnecting] = useState(false);
  const [googleStatus, setGoogleStatus] = useState<GoogleStatus>(null);
  const [googleStatusError, setGoogleStatusError] = useState<string | null>(null);
  const [googleConnecting, setGoogleConnecting] = useState(false);
  const [googleDisconnecting, setGoogleDisconnecting] = useState(false);
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
  const [loggingOut, setLoggingOut] = useState(false);

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

  const fetchLinearStatus = useCallback(
    async () => {
      if (!apiBaseUrl) {
        return;
      }

      try {
        const headers = await getAuthHeaders();
        const response = await fetch(
          `${apiBaseUrl}/api/oauth/linear/status`,
          { headers }
        );
        if (response.ok) {
          const data: LinearStatus = await response.json();
          setLinearStatus(data);
          setLinearStatusError(null);
        } else {
          setLinearStatusError("Failed to fetch Linear status.");
        }
      } catch {
        setLinearStatusError("Network error while fetching Linear status.");
      }
    },
    [apiBaseUrl, getAuthHeaders]
  );

  const fetchGoogleStatus = useCallback(
    async () => {
      if (!apiBaseUrl) {
        return;
      }

      try {
        const headers = await getAuthHeaders();
        const response = await fetch(
          `${apiBaseUrl}/api/oauth/google/status`,
          { headers }
        );
        if (response.ok) {
          const data: GoogleStatus = await response.json();
          setGoogleStatus(data);
          setGoogleStatusError(null);
        } else {
          setGoogleStatusError("Failed to fetch Google status.");
        }
      } catch {
        setGoogleStatusError("Network error while fetching Google status.");
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
    }
    if (url.searchParams.has("linear")) {
      url.searchParams.delete("linear");
    }
    if (url.searchParams.has("google")) {
      url.searchParams.delete("google");
    }
    window.history.replaceState({}, "", url.toString());
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
        await fetchLinearStatus();
        await fetchGoogleStatus();
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
  }, [router, fetchNotionStatus, fetchLinearStatus, fetchGoogleStatus, fetchTelegramStatus, fetchCommandLogs]);

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

  const handleDisconnectLinear = async () => {
    if (!apiBaseUrl || !profile?.id || linearDisconnecting) {
      return;
    }

    setLinearDisconnecting(true);
    try {
      const headers = await getAuthHeaders();
      const response = await fetch(
        `${apiBaseUrl}/api/oauth/linear/disconnect`,
        { method: "DELETE", headers }
      );
      if (!response.ok) {
        setLinearStatusError("Failed to disconnect Linear.");
        return;
      }
      setLinearStatus({ connected: false, integration: null });
      setLinearStatusError(null);
    } catch {
      setLinearStatusError("Network error while disconnecting Linear.");
    } finally {
      setLinearDisconnecting(false);
    }
  };

  const handleConnectLinear = async () => {
    if (!apiBaseUrl || !profile?.id || linearConnecting) {
      return;
    }

    setLinearConnecting(true);
    try {
      const headers = await getAuthHeaders();
      const response = await fetch(`${apiBaseUrl}/api/oauth/linear/start`, {
        method: "POST",
        headers,
      });
      const payload = await response.json();
      if (!response.ok || !payload?.auth_url) {
        setLinearStatusError("Failed to start Linear connection.");
        return;
      }
      window.location.href = payload.auth_url;
    } catch {
      setLinearStatusError("Network error while starting Linear connection.");
    } finally {
      setLinearConnecting(false);
    }
  };

  const handleDisconnectGoogle = async () => {
    if (!apiBaseUrl || !profile?.id || googleDisconnecting) {
      return;
    }

    setGoogleDisconnecting(true);
    try {
      const headers = await getAuthHeaders();
      const response = await fetch(
        `${apiBaseUrl}/api/oauth/google/disconnect`,
        { method: "DELETE", headers }
      );
      if (!response.ok) {
        setGoogleStatusError("Failed to disconnect Google.");
        return;
      }
      setGoogleStatus({ connected: false, integration: null });
      setGoogleStatusError(null);
    } catch {
      setGoogleStatusError("Network error while disconnecting Google.");
    } finally {
      setGoogleDisconnecting(false);
    }
  };

  const handleConnectGoogle = async () => {
    if (!apiBaseUrl || !profile?.id || googleConnecting) {
      return;
    }

    setGoogleConnecting(true);
    try {
      const headers = await getAuthHeaders();
      const response = await fetch(`${apiBaseUrl}/api/oauth/google/start`, {
        method: "POST",
        headers,
      });
      const payload = await response.json();
      if (!response.ok || !payload?.auth_url) {
        setGoogleStatusError("Failed to start Google connection.");
        return;
      }
      window.location.href = payload.auth_url;
    } catch {
      setGoogleStatusError("Network error while starting Google connection.");
    } finally {
      setGoogleConnecting(false);
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

  const handleLogout = async () => {
    if (loggingOut) {
      return;
    }
    setLoggingOut(true);
    try {
      await supabase.auth.signOut();
      router.replace("/");
    } finally {
      setLoggingOut(false);
    }
  };

  if (loading) {
    return (
      <main className="relative min-h-screen overflow-hidden bg-[#050506] text-[#f5f5f5]">
        <div className="pointer-events-none absolute inset-0 opacity-70">
          <div className="absolute inset-0 bg-[linear-gradient(to_right,#1a1a1c_1px,transparent_1px),linear-gradient(to_bottom,#1a1a1c_1px,transparent_1px)] bg-[size:56px_56px]" />
          <div className="absolute inset-0 bg-[radial-gradient(circle_at_18%_12%,#1d2430_0px,transparent_380px),radial-gradient(circle_at_84%_8%,#2a1f2a_0px,transparent_340px),radial-gradient(circle_at_50%_82%,#122025_0px,transparent_420px)]" />
        </div>
        <div className="relative mx-auto max-w-[1080px] px-6 py-16">
          <p className="text-sm text-[#a5adbc]">Loading dashboard...</p>
        </div>
      </main>
    );
  }

  return (
    <main className="relative min-h-screen overflow-hidden bg-[#050506] text-[#f5f5f5]">
      <div className="pointer-events-none absolute inset-0 opacity-70">
        <div className="absolute inset-0 bg-[linear-gradient(to_right,#1a1a1c_1px,transparent_1px),linear-gradient(to_bottom,#1a1a1c_1px,transparent_1px)] bg-[size:56px_56px]" />
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_18%_12%,#1d2430_0px,transparent_380px),radial-gradient(circle_at_84%_8%,#2a1f2a_0px,transparent_340px),radial-gradient(circle_at_50%_82%,#122025_0px,transparent_420px)]" />
      </div>
      <div className="relative mx-auto max-w-[1080px] px-6 py-14">
      <header className="rounded-2xl border border-[#2a2a33] bg-[#111116] p-7 shadow-sm">
        <p className="font-mono text-xs uppercase tracking-wider text-[#8d96a8]">metel</p>
        <h1 className="mt-2 text-4xl font-semibold tracking-tight text-[#f7f8fa]">Dashboard</h1>
        <p className="mt-2 text-sm text-[#a5adbc]">
          Control messenger links, service integrations, and autonomous agent logs.
        </p>
      </header>

      <section className="mt-6 rounded-2xl border border-[#2a2a33] bg-[#111116] p-6 shadow-sm">
        <div className="flex items-center justify-between gap-2">
          <h2 className="text-lg font-semibold text-[#f7f8fa]">User</h2>
          <button
            type="button"
            onClick={() => {
              void handleLogout();
            }}
            disabled={loggingOut}
            className="rounded-md border border-[#353540] px-3 py-2 text-sm font-medium text-[#edf0f5] disabled:opacity-50"
          >
            {loggingOut ? "Logging out..." : "Logout"}
          </button>
        </div>
        <div className="mt-4 grid gap-4 sm:grid-cols-3">
          <div>
            <p className="text-xs text-[#8d96a8]">Email</p>
            <p className="mt-1 text-sm text-[#edf0f5]">{profile?.email ?? "-"}</p>
          </div>
          <div>
            <p className="text-xs text-[#8d96a8]">User ID</p>
            <p className="mt-1 break-all text-sm text-[#edf0f5]">{profile?.id ?? "-"}</p>
          </div>
          <div>
            <p className="text-xs text-[#8d96a8]">Created</p>
            <p className="mt-1 text-sm text-[#edf0f5]">
              {profile?.created_at ? new Date(profile.created_at).toLocaleString() : "-"}
            </p>
          </div>
        </div>
      </section>

      <section className="mt-6 rounded-2xl border border-[#2a2a33] bg-[#111116] p-6 shadow-sm">
        <h2 className="text-lg font-semibold text-[#f7f8fa]">Messenger Connection</h2>
        <div className="mt-4 grid gap-4 md:grid-cols-2">
          <article className="rounded-xl border border-[#2a2a33] bg-[#15151b] p-4">
            <div className="flex items-center justify-between">
              <p className="flex items-center gap-2 text-base font-semibold text-[#edf0f5]">
                <ServiceLogo src="/logos/telegram.svg" alt="Telegram" />
                Telegram
              </p>
              <p className="text-xs text-[#a5adbc]">{telegramStatus?.connected ? "Connected" : "Not connected"}</p>
            </div>
            <p className="mt-2 text-sm text-[#bcc2cf]">
              Account: {telegramStatus?.telegram_username ? `@${telegramStatus.telegram_username}` : "-"}
            </p>
            <button
              type="button"
              onClick={() => {
                if (telegramStatus?.connected) {
                  void handleDisconnectTelegram();
                  return;
                }
                void handleConnectTelegram();
              }}
              disabled={!apiBaseUrl || !profile?.id || telegramConnecting || telegramDisconnecting}
              className="mt-3 inline-block rounded-md border border-[#353540] bg-[#111116] px-4 py-2 text-sm font-medium text-[#edf0f5] disabled:opacity-50"
            >
              {telegramStatus?.connected
                ? (telegramDisconnecting ? "Disconnecting..." : "Disconnect")
                : (telegramConnecting ? "Generating link..." : "Connect")}
            </button>
          </article>

          <article className="rounded-xl border border-[#2a2a33] bg-[#15151b] p-4 opacity-60">
            <div className="flex items-center justify-between">
              <p className="flex items-center gap-2 text-base font-semibold text-[#edf0f5]">
                <ServiceLogo src="/logos/slack.svg" alt="Slack" />
                Slack
              </p>
              <p className="text-xs text-[#a5adbc]">Disabled</p>
            </div>
            <p className="mt-2 text-sm text-[#bcc2cf]">Slack connection is not enabled in this prototype.</p>
            <button
              type="button"
              disabled
              className="mt-3 inline-block rounded-md border border-[#353540] bg-[#111116] px-4 py-2 text-sm font-medium text-[#edf0f5] disabled:opacity-50"
            >
              Connect
            </button>
          </article>
        </div>
        {telegramStatusError ? <p className="mt-3 text-sm text-amber-300">{telegramStatusError}</p> : null}
        {!apiBaseUrl || !profile?.id ? (
          <p className="mt-3 text-sm text-amber-300">
            Set NEXT_PUBLIC_API_BASE_URL to enable messenger connection.
          </p>
        ) : null}
        {telegramConnectInfo && !telegramStatus?.connected ? (
          <div className="mt-4 rounded-lg border border-[#2a2a33] bg-[#15151b] p-4">
            <p className="text-sm text-[#bcc2cf]">
              If Start does not respond in Telegram, copy and send this command manually to{" "}
              {telegramConnectInfo.botUsername ? `@${telegramConnectInfo.botUsername}` : "your bot"}.
            </p>
            <p className="font-mono mt-2 break-all rounded border border-[#2a2a33] bg-[#111116] p-2 text-xs text-[#bcc2cf]">
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
                className="inline-block rounded-md border border-[#353540] px-3 py-2 text-sm font-medium text-[#edf0f5]"
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
                className="inline-block rounded-md border border-[#353540] px-3 py-2 text-sm font-medium text-[#edf0f5]"
              >
                Open Telegram Again
              </button>
            </div>
            <p className="mt-2 text-xs text-[#a5adbc]">
              {telegramPolling ? "Auto-checking connection status..." : "Auto-check stopped. Re-run connect if needed."}
            </p>
            <p className="mt-1 text-xs text-[#8d96a8]">
              Expires in about {Math.max(1, Math.floor(telegramConnectInfo.expiresInSeconds / 60))} min
            </p>
          </div>
        ) : null}
      </section>

      <section className="mt-6 rounded-2xl border border-[#2a2a33] bg-[#111116] p-6 shadow-sm">
        <h2 className="text-lg font-semibold text-[#f7f8fa]">Service Connection</h2>
        <div className="mt-4 grid gap-4 md:grid-cols-2">
          <article className="rounded-xl border border-[#2a2a33] bg-[#15151b] p-4">
            <div className="flex items-center justify-between">
              <p className="flex items-center gap-2 text-base font-semibold text-[#edf0f5]">
                <ServiceLogo src="/logos/notion.svg" alt="Notion" />
                Notion
              </p>
              <p className="text-xs text-[#a5adbc]">{notionStatus?.connected ? "Connected" : "Not connected"}</p>
            </div>
            <p className="mt-2 text-sm text-[#bcc2cf]">
              Workspace: {notionStatus?.integration?.workspace_name ?? "-"}
            </p>
            <button
              type="button"
              onClick={() => {
                if (notionStatus?.connected) {
                  void handleDisconnectNotion();
                  return;
                }
                void handleConnectNotion();
              }}
              disabled={!apiBaseUrl || !profile?.id || disconnecting}
              className="mt-3 inline-block rounded-md border border-[#353540] bg-[#111116] px-4 py-2 text-sm font-medium text-[#edf0f5] disabled:opacity-50"
            >
              {notionStatus?.connected ? (disconnecting ? "Disconnecting..." : "Disconnect") : "Connect"}
            </button>
          </article>

          <article className="rounded-xl border border-[#2a2a33] bg-[#15151b] p-4">
            <div className="flex items-center justify-between">
              <p className="flex items-center gap-2 text-base font-semibold text-[#edf0f5]">
                <ServiceLogo src="/logos/linear.svg" alt="Linear" />
                Linear
              </p>
              <p className="text-xs text-[#a5adbc]">{linearStatus?.connected ? "Connected" : "Not connected"}</p>
            </div>
            <p className="mt-2 text-sm text-[#bcc2cf]">
              User: {linearStatus?.integration?.workspace_name ?? "-"}
            </p>
            <button
              type="button"
              onClick={() => {
                if (linearStatus?.connected) {
                  void handleDisconnectLinear();
                  return;
                }
                void handleConnectLinear();
              }}
              disabled={!apiBaseUrl || !profile?.id || linearConnecting || linearDisconnecting}
              className="mt-3 inline-block rounded-md border border-[#353540] bg-[#111116] px-4 py-2 text-sm font-medium text-[#edf0f5] disabled:opacity-50"
            >
              {linearStatus?.connected
                ? (linearDisconnecting ? "Disconnecting..." : "Disconnect")
                : (linearConnecting ? "Connecting..." : "Connect")}
            </button>
          </article>

          <article className="rounded-xl border border-[#2a2a33] bg-[#15151b] p-4">
            <div className="flex items-center justify-between">
              <p className="flex items-center gap-2 text-base font-semibold text-[#edf0f5]">
                <ServiceLogo src="/logos/google.svg" alt="Google" />
                Google Calendar
              </p>
              <p className="text-xs text-[#a5adbc]">{googleStatus?.connected ? "Connected" : "Not connected"}</p>
            </div>
            <p className="mt-2 text-sm text-[#bcc2cf]">
              Workspace: {googleStatus?.integration?.workspace_name ?? "-"}
            </p>
            <button
              type="button"
              onClick={() => {
                if (googleStatus?.connected) {
                  void handleDisconnectGoogle();
                  return;
                }
                void handleConnectGoogle();
              }}
              disabled={!apiBaseUrl || !profile?.id || googleConnecting || googleDisconnecting}
              className="mt-3 inline-block rounded-md border border-[#353540] bg-[#111116] px-4 py-2 text-sm font-medium text-[#edf0f5] disabled:opacity-50"
            >
              {googleStatus?.connected
                ? (googleDisconnecting ? "Disconnecting..." : "Disconnect")
                : (googleConnecting ? "Connecting..." : "Connect")}
            </button>
          </article>

          <article className="rounded-xl border border-[#2a2a33] bg-[#15151b] p-4 opacity-60">
            <div className="flex items-center justify-between">
              <p className="flex items-center gap-2 text-base font-semibold text-[#edf0f5]">
                <ServiceLogo src="/logos/spotify.svg" alt="Spotify" />
                Spotify
              </p>
              <p className="text-xs text-[#a5adbc]">Disabled</p>
            </div>
            <p className="mt-2 text-sm text-[#bcc2cf]">
              Spotify integration is disabled due to current API limit.
            </p>
            <button
              type="button"
              disabled
              className="mt-3 inline-block rounded-md border border-[#353540] bg-[#111116] px-4 py-2 text-sm font-medium text-[#edf0f5] disabled:opacity-50"
            >
              Connect
            </button>
          </article>
        </div>
        {notionStatusError ? <p className="mt-3 text-sm text-amber-300">{notionStatusError}</p> : null}
        {linearStatusError ? <p className="mt-3 text-sm text-amber-300">{linearStatusError}</p> : null}
        {googleStatusError ? <p className="mt-3 text-sm text-amber-300">{googleStatusError}</p> : null}
        {!apiBaseUrl || !profile?.id ? (
          <p className="mt-3 text-sm text-amber-300">
            Set NEXT_PUBLIC_API_BASE_URL to enable service connection.
          </p>
        ) : null}
      </section>

      <section className="mt-6 rounded-2xl border border-[#2a2a33] bg-[#111116] p-6 shadow-sm">
        <div className="flex items-center justify-between gap-2">
          <h2 className="text-lg font-semibold text-[#f7f8fa]">Execution Logs (latest 20)</h2>
          <div className="flex flex-wrap items-center gap-2">
            <select
              value={commandLogStatusFilter}
              onChange={(event) => {
                setCommandLogStatusFilter(event.target.value as "all" | "success" | "error");
              }}
              className="rounded-md border border-[#353540] bg-[#111116] px-2 py-2 text-sm text-[#edf0f5]"
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
              className="rounded-md border border-[#353540] bg-[#111116] px-2 py-2 text-sm text-[#edf0f5]"
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
              className="rounded-md border border-[#353540] bg-[#111116] px-3 py-2 text-sm font-medium text-[#edf0f5] disabled:opacity-50"
            >
              {commandLogsLoading ? "Refreshing..." : "Refresh"}
            </button>
          </div>
        </div>
        <div className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
          <div className="rounded-md border border-[#2a2a33] bg-[#15151b] p-3">
            <p className="text-xs text-[#a5adbc]">Agent Logs</p>
            <p className="mt-1 text-sm font-semibold text-[#edf0f5]">{agentTelemetry.total}</p>
          </div>
          <div className="rounded-md border border-[#2a2a33] bg-[#15151b] p-3">
            <p className="text-xs text-[#a5adbc]">Execution Mode</p>
            <p className="mt-1 text-sm font-semibold text-[#edf0f5]">
              auto {agentTelemetry.autonomous} / rule {agentTelemetry.rule}
            </p>
          </div>
          <div className="rounded-md border border-[#2a2a33] bg-[#15151b] p-3">
            <p className="text-xs text-[#a5adbc]">Plan Source</p>
            <p className="mt-1 text-sm font-semibold text-[#edf0f5]">
              llm {agentTelemetry.llmPlan} / rule {agentTelemetry.rulePlan}
            </p>
          </div>
          <div className="rounded-md border border-[#2a2a33] bg-[#15151b] p-3">
            <p className="text-xs text-[#a5adbc]">Success / Error</p>
            <p className="mt-1 text-sm font-semibold text-[#edf0f5]">
              {agentTelemetry.success} / {agentTelemetry.error}
            </p>
          </div>
        </div>
        <div className="mt-3 grid gap-2 sm:grid-cols-2">
          <div className="rounded-md border border-[#2a2a33] bg-[#15151b] p-3">
            <p className="text-xs text-[#a5adbc]">Autonomous Success Rate (target 80%+)</p>
            <p className="mt-1 text-sm font-semibold text-[#edf0f5]">
              {(agentTelemetry.autonomousSuccessRate * 100).toFixed(1)}%
              {" "}
              <span
                className={
                  agentTelemetry.autonomousSuccessRate >= 0.8
                    ? "text-emerald-700"
                    : "text-amber-300"
                }
              >
                {agentTelemetry.autonomousSuccessRate >= 0.8 ? "PASS" : "CHECK"}
              </span>
            </p>
            <p className="mt-1 text-xs text-[#a5adbc]">
              autonomous success {agentTelemetry.autonomousSuccess} / {agentTelemetry.autonomous}
            </p>
          </div>
          <div className="rounded-md border border-[#2a2a33] bg-[#15151b] p-3">
            <p className="text-xs text-[#a5adbc]">Fallback Rate (target 20% or less)</p>
            <p className="mt-1 text-sm font-semibold text-[#edf0f5]">
              {(agentTelemetry.fallbackRate * 100).toFixed(1)}%
              {" "}
              <span
                className={
                  agentTelemetry.fallbackRate <= 0.2
                    ? "text-emerald-700"
                    : "text-amber-300"
                }
              >
                {agentTelemetry.fallbackRate <= 0.2 ? "PASS" : "CHECK"}
              </span>
            </p>
            <p className="mt-1 text-xs text-[#a5adbc]">
              fallback {agentTelemetry.fallbackCount} / {agentTelemetry.total}
            </p>
          </div>
        </div>
        {agentTelemetry.fallbackCount > 0 ? (
          <div className="mt-3 rounded-md border border-amber-500/40 bg-amber-500/10 p-3">
            <p className="text-xs font-medium text-amber-300">
              autonomous fallback count: {agentTelemetry.fallbackCount}
            </p>
            <p className="mt-1 break-all text-xs text-amber-300">
              top reasons:{" "}
              {agentTelemetry.topFallbackReasons.map(([reason, count]) => `${reason}(${count})`).join(", ")}
            </p>
          </div>
        ) : null}
        {agentTelemetry.verificationCount > 0 ? (
          <div className="mt-3 rounded-md border border-rose-500/40 bg-rose-500/10 p-3">
            <p className="text-xs font-medium text-rose-300">
              verification reason records: {agentTelemetry.verificationCount}
            </p>
            <p className="mt-1 break-all text-xs text-rose-300">
              top reasons:{" "}
              {agentTelemetry.topVerificationReasons.map(([reason, count]) => `${reason}(${count})`).join(", ")}
            </p>
          </div>
        ) : null}
        {commandLogsError ? <p className="mt-3 text-sm text-amber-300">{commandLogsError}</p> : null}
        <p className="mt-3 text-xs text-[#a5adbc]">
          Showing: {filteredCommandLogs.length} / {commandLogs.length}
        </p>
        {filteredCommandLogs.length > 0 ? (
          <ul className="mt-4 space-y-2">
            {filteredCommandLogs.map((log) => (
              <li key={log.id} className="overflow-hidden rounded-md border border-[#2a2a33] bg-[#15151b] p-3">
                <p className="text-sm font-medium text-[#edf0f5]">
                  {log.command} · {log.status}
                </p>
                <p className="mt-1 text-xs text-[#a5adbc]">
                  {new Date(log.created_at).toLocaleString()} · {log.channel}
                </p>
                {(log.plan_source || log.execution_mode) ? (
                  <p className="mt-1 break-all text-xs text-[#a5adbc]">
                    mode: {log.plan_source || "-"} / {log.execution_mode || "-"}
                    {log.autonomous_fallback_reason ? ` · fallback=${log.autonomous_fallback_reason}` : ""}
                    {log.verification_reason ? ` · verify=${log.verification_reason}` : ""}
                  </p>
                ) : null}
                {(log.llm_provider || log.llm_model) ? (
                  <p className="mt-1 break-all text-xs text-[#a5adbc]">
                    llm: {log.llm_provider || "-"} / {log.llm_model || "-"}
                  </p>
                ) : null}
                {log.error_code ? (
                  <p className="mt-1 break-all text-xs text-amber-300">error_code: {log.error_code}</p>
                ) : null}
                {log.detail ? (
                  <p className="mt-1 whitespace-pre-wrap break-all text-xs text-[#a5adbc]">detail: {log.detail}</p>
                ) : null}
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-3 text-sm text-[#a5adbc]">No logs match the current filters.</p>
        )}
      </section>
      </div>
    </main>
  );
}
