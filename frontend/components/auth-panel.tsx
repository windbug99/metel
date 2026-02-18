"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { supabase } from "@/lib/supabase";

type UserState = {
  email: string;
} | null;

export default function AuthPanel() {
  const router = useRouter();
  const [user, setUser] = useState<UserState>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let mounted = true;

    const syncUser = async () => {
      const {
        data: { user: authUser }
      } = await supabase.auth.getUser();

      if (!mounted) {
        return;
      }

      setUser(authUser?.email ? { email: authUser.email } : null);
      setLoading(false);
    };

    const {
      data: { subscription }
    } = supabase.auth.onAuthStateChange(async () => {
      await syncUser();
      router.refresh();
    });

    void syncUser();

    return () => {
      mounted = false;
      subscription.unsubscribe();
    };
  }, [router]);

  const signInWithGoogle = async () => {
    const redirectTo = `${window.location.origin}/auth/callback`;

    const { error } = await supabase.auth.signInWithOAuth({
      provider: "google",
      options: { redirectTo }
    });

    if (error) {
      alert(error.message);
    }
  };

  const signOut = async () => {
    const { error } = await supabase.auth.signOut();

    if (error) {
      alert(error.message);
    }
  };

  if (loading) {
    return <p className="mt-6 text-sm text-gray-500">인증 상태 확인 중...</p>;
  }

  return (
    <section className="mt-8 rounded-xl border border-gray-200 p-5">
      {user ? (
        <div className="space-y-3">
          <p className="text-sm text-gray-700">로그인됨: {user.email}</p>
          <a
            href="/dashboard"
            className="inline-block rounded-md border border-gray-300 px-4 py-2 text-sm font-medium text-gray-900"
          >
            대시보드 이동
          </a>
          <button
            type="button"
            onClick={signOut}
            className="rounded-md bg-gray-900 px-4 py-2 text-sm font-medium text-white"
          >
            로그아웃
          </button>
        </div>
      ) : (
        <div className="space-y-3">
          <p className="text-sm text-gray-700">Google 계정으로 로그인하세요.</p>
          <button
            type="button"
            onClick={signInWithGoogle}
            className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white"
          >
            Google로 로그인
          </button>
        </div>
      )}
    </section>
  );
}
