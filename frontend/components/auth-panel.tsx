"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { supabase } from "../lib/supabase";

type UserState = {
  email: string;
} | null;

type AuthPanelProps = {
  className?: string;
  signInButtonClassName?: string;
};

export default function AuthPanel({ className, signInButtonClassName }: AuthPanelProps) {
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

  useEffect(() => {
    if (!loading && user) {
      router.replace("/dashboard");
    }
  }, [loading, user, router]);

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

  const containerClassName = className ?? "mt-8 rounded-xl border border-gray-200 p-5";
  const defaultSignInButtonClassName =
    signInButtonClassName ??
    "rounded-md border border-neutral-900 bg-neutral-900 px-4 py-2 text-sm font-medium text-white hover:bg-neutral-800";

  if (loading) {
    return (
      <section className={containerClassName}>
        <div className="space-y-3">
          <p className="text-sm text-gray-600">Checking auth state...</p>
          <button
            type="button"
            onClick={signInWithGoogle}
            className={defaultSignInButtonClassName}
          >
            Sign in with Google
          </button>
        </div>
      </section>
    );
  }

  return (
    <section className={containerClassName}>
      {errorMessage ? <p className="mb-3 text-sm text-red-600">Auth check error: {errorMessage}</p> : null}
      {user ? (
        <div className="space-y-3">
          <p className="text-sm text-gray-700">Signed in: {user.email}</p>
          <a
            href="/dashboard"
            className="inline-block rounded-md border border-gray-300 px-4 py-2 text-sm font-medium text-gray-900 hover:bg-gray-100"
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
          <p className="text-sm text-gray-700">Sign in to connect your services.</p>
          <button
            type="button"
            onClick={signInWithGoogle}
            className={defaultSignInButtonClassName}
          >
            Sign in with Google
          </button>
        </div>
      )}
    </section>
  );
}
