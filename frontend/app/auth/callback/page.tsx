"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { supabase } from "@/lib/supabase";

export default function AuthCallbackPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const code = useMemo(() => searchParams.get("code"), [searchParams]);

  useEffect(() => {
    const completeOAuth = async () => {
      if (!code) {
        setErrorMessage("인증 코드가 없습니다.");
        return;
      }

      const { error } = await supabase.auth.exchangeCodeForSession(code);

      if (error) {
        setErrorMessage(error.message);
        return;
      }

      router.replace("/");
    };

    void completeOAuth();
  }, [code, router]);

  return (
    <main className="mx-auto max-w-xl px-6 py-16">
      <h1 className="text-2xl font-semibold">로그인 처리 중...</h1>
      {errorMessage ? <p className="mt-4 text-sm text-red-600">{errorMessage}</p> : null}
    </main>
  );
}
