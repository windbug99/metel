"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { supabase } from "../../../lib/supabase";
import { upsertUserProfile } from "../../../lib/profile";

export default function AuthCallbackPage() {
  const router = useRouter();
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    const completeOAuth = async () => {
      const code = new URLSearchParams(window.location.search).get("code");

      if (!code) {
        setErrorMessage("Missing auth code.");
        return;
      }

      const { error } = await supabase.auth.exchangeCodeForSession(code);

      if (error) {
        setErrorMessage(error.message);
        return;
      }

      const { error: profileError } = await upsertUserProfile();

      if (profileError) {
        setErrorMessage(profileError.message);
        return;
      }

      router.replace("/");
    };

    void completeOAuth();
  }, [router]);

  return (
    <main className="mx-auto max-w-xl px-6 py-16">
      <h1 className="text-2xl font-semibold">Completing sign-in...</h1>
      {errorMessage ? <p className="mt-4 text-sm text-red-600">{errorMessage}</p> : null}
    </main>
  );
}
