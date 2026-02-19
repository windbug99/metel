"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { supabase } from "../lib/supabase";

type UserState = {
  email: string;
} | null;

export default function AuthPanel() {
  const router = useRouter();
  const [user, setUser] = useState<UserState>(null);
  const [loading, setLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;

    const syncUser = async () => {
      try {
        const result = await Promise.race([
          supabase.auth.getUser(),
          new Promise<never>((_, reject) => {
            setTimeout(() => reject(new Error("Auth request timeout")), 8000);
          })
        ]);

        if (!mounted) {
          return;
        }

        const {
          data: { user: authUser }
        } = result;

        setErrorMessage(null);
        setUser(authUser?.email ? { email: authUser.email } : null);
      } catch (error) {
        if (!mounted) {
          return;
        }
        setUser(null);
        setErrorMessage(error instanceof Error ? error.message : "Failed to load auth state.");
      } finally {
        if (mounted) {
          setLoading(false);
        }
      }
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
    return <p className="mt-6 text-sm text-gray-500">Checking auth state...</p>;
  }

  return (
    <section className="mt-8 rounded-xl border border-gray-200 p-5">
      {errorMessage ? <p className="mb-3 text-sm text-red-600">Auth check error: {errorMessage}</p> : null}
      {user ? (
        <div className="space-y-3">
          <p className="text-sm text-gray-700">Signed in: {user.email}</p>
          <a
            href="/dashboard"
            className="inline-block rounded-md border border-gray-300 px-4 py-2 text-sm font-medium text-gray-900"
          >
            Open Dashboard
          </a>
          <button
            type="button"
            onClick={signOut}
            className="rounded-md bg-gray-900 px-4 py-2 text-sm font-medium text-white"
          >
            Sign out
          </button>
        </div>
      ) : (
        <div className="space-y-3">
          <p className="text-sm text-gray-700">Sign in with Google.</p>
          <button
            type="button"
            onClick={signInWithGoogle}
            className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white"
          >
            Sign in with Google
          </button>
        </div>
      )}
    </section>
  );
}
