"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { supabase } from "@/lib/supabase";
import { upsertUserProfile } from "@/lib/profile";

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

  const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL;

  const fetchNotionStatus = useCallback(
    async (userId: string) => {
      if (!apiBaseUrl) {
        return;
      }

      try {
        const notionResponse = await fetch(
          `${apiBaseUrl}/api/oauth/notion/status?user_id=${encodeURIComponent(userId)}`
        );
        if (notionResponse.ok) {
          const notionData: NotionStatus = await notionResponse.json();
          setNotionStatus(notionData);
          setNotionStatusError(null);
        } else {
          setNotionStatusError("Notion 상태 조회에 실패했습니다.");
        }
      } catch {
        setNotionStatusError("Notion 상태 조회 중 네트워크 오류가 발생했습니다.");
      }
    },
    [apiBaseUrl]
  );

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

        await fetchNotionStatus(user.id);

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
  }, [router, fetchNotionStatus]);

  const handleDisconnectNotion = async () => {
    if (!apiBaseUrl || !profile?.id || disconnecting) {
      return;
    }

    setDisconnecting(true);
    try {
      const response = await fetch(
        `${apiBaseUrl}/api/oauth/notion/disconnect?user_id=${encodeURIComponent(profile.id)}`,
        { method: "DELETE" }
      );
      if (!response.ok) {
        setNotionStatusError("Notion 연결해제에 실패했습니다.");
        return;
      }
      setNotionStatus({ connected: false, integration: null });
      setNotionStatusError(null);
    } catch {
      setNotionStatusError("Notion 연결해제 중 네트워크 오류가 발생했습니다.");
    } finally {
      setDisconnecting(false);
    }
  };

  const handleLoadNotionPages = async () => {
    if (!apiBaseUrl || !profile?.id || loadingPages || !notionStatus?.connected) {
      return;
    }

    setLoadingPages(true);
    setPagesError(null);
    try {
      const response = await fetch(
        `${apiBaseUrl}/api/oauth/notion/pages?user_id=${encodeURIComponent(profile.id)}&page_size=5`
      );
      const payload = await response.json();
      if (!response.ok || !payload?.ok) {
        const message =
          payload?.error?.message ?? payload?.detail ?? "Notion 페이지 조회에 실패했습니다.";
        setPagesError(message);
        return;
      }
      setNotionPages(Array.isArray(payload.pages) ? payload.pages : []);
    } catch {
      setPagesError("Notion 페이지 조회 중 네트워크 오류가 발생했습니다.");
    } finally {
      setLoadingPages(false);
    }
  };

  if (loading) {
    return (
      <main className="mx-auto max-w-3xl px-6 py-16">
        <p className="text-sm text-gray-600">대시보드 로딩 중...</p>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-3xl px-6 py-16">
      <h1 className="text-3xl font-bold">Dashboard</h1>
      <div className="mt-6 rounded-xl border border-gray-200 p-5">
        <p className="text-sm text-gray-700">이메일: {profile?.email ?? "-"}</p>
        <p className="mt-2 text-sm text-gray-700">User ID: {profile?.id ?? "-"}</p>
        <p className="mt-2 text-sm text-gray-700">가입일: {profile?.created_at ?? "-"}</p>
      </div>
      <section className="mt-6 rounded-xl border border-gray-200 p-5">
        <h2 className="text-xl font-semibold">Notion 연동</h2>
        {notionStatusError ? (
          <p className="mt-3 text-sm text-amber-700">{notionStatusError}</p>
        ) : null}
        <p className="mt-3 text-sm text-gray-700">
          상태: {notionStatus?.connected ? "연결됨" : "미연결"}
        </p>
        {notionStatus?.connected ? (
          <p className="mt-1 text-sm text-gray-700">
            Workspace: {notionStatus.integration?.workspace_name ?? "-"}
          </p>
        ) : null}
        {apiBaseUrl && profile?.id ? (
          <div className="mt-4 flex gap-2">
            <a
              href={`${apiBaseUrl}/api/oauth/notion/start?user_id=${encodeURIComponent(profile.id)}`}
              className="inline-block rounded-md bg-gray-900 px-4 py-2 text-sm font-medium text-white"
            >
              Notion 연결하기
            </a>
            {notionStatus?.connected ? (
              <button
                type="button"
                onClick={handleDisconnectNotion}
                disabled={disconnecting}
                className="inline-block rounded-md border border-gray-300 px-4 py-2 text-sm font-medium text-gray-900 disabled:opacity-50"
              >
                {disconnecting ? "연결해제 중..." : "연결해제"}
              </button>
            ) : null}
          </div>
        ) : (
          <p className="mt-3 text-sm text-amber-700">
            NEXT_PUBLIC_API_BASE_URL 설정 후 Notion 연동 버튼을 사용할 수 있습니다.
          </p>
        )}
        {notionStatus?.connected ? (
          <div className="mt-6 rounded-lg border border-gray-200 p-4">
            <div className="flex items-center justify-between gap-2">
              <h3 className="text-lg font-semibold">최근 Notion 페이지</h3>
              <button
                type="button"
                onClick={handleLoadNotionPages}
                disabled={loadingPages}
                className="rounded-md border border-gray-300 px-3 py-2 text-sm font-medium text-gray-900 disabled:opacity-50"
              >
                {loadingPages ? "조회 중..." : "페이지 조회"}
              </button>
            </div>
            {pagesError ? <p className="mt-3 text-sm text-amber-700">{pagesError}</p> : null}
            {notionPages.length > 0 ? (
              <ul className="mt-3 space-y-2">
                {notionPages.map((page) => (
                  <li key={page.id} className="rounded-md border border-gray-200 p-3">
                    <a
                      href={page.url}
                      target="_blank"
                      rel="noreferrer"
                      className="text-sm font-medium text-blue-700 underline"
                    >
                      {page.title}
                    </a>
                    <p className="mt-1 text-xs text-gray-600">{page.last_edited_time}</p>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="mt-3 text-sm text-gray-600">조회 버튼을 눌러 최근 페이지를 불러오세요.</p>
            )}
          </div>
        ) : null}
      </section>
    </main>
  );
}
