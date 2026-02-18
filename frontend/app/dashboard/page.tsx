"use client";

import { useEffect, useState } from "react";
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

export default function DashboardPage() {
  const router = useRouter();
  const [loading, setLoading] = useState(true);
  const [profile, setProfile] = useState<UserProfile>(null);
  const [notionStatus, setNotionStatus] = useState<NotionStatus>(null);
  const [notionStatusError, setNotionStatusError] = useState<string | null>(null);

  const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL;

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

        if (apiBaseUrl) {
          try {
            const notionResponse = await fetch(
              `${apiBaseUrl}/api/oauth/notion/status?user_id=${encodeURIComponent(user.id)}`
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
        }

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
  }, [router, apiBaseUrl]);

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
          <a
            href={`${apiBaseUrl}/api/oauth/notion/start?user_id=${encodeURIComponent(profile.id)}`}
            className="mt-4 inline-block rounded-md bg-gray-900 px-4 py-2 text-sm font-medium text-white"
          >
            Notion 연결하기
          </a>
        ) : (
          <p className="mt-3 text-sm text-amber-700">
            NEXT_PUBLIC_API_BASE_URL 설정 후 Notion 연동 버튼을 사용할 수 있습니다.
          </p>
        )}
      </section>
    </main>
  );
}
