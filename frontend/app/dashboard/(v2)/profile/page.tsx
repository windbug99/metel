"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { usePathname, useRouter } from "next/navigation";

import { buildNextPath } from "../../../../lib/dashboard-v2-client";
import { detectBrowserTimezone, updateUserTimezone, upsertUserProfile } from "../../../../lib/profile";
import { supabase } from "../../../../lib/supabase";
import AlertBanner from "../../../../components/dashboard-v2/alert-banner";

type UserProfile = {
  id: string;
  email: string | null;
  full_name: string | null;
  timezone: string | null;
  created_at: string | null;
};

function asDate(value?: string | null): string {
  if (!value) {
    return "-";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString();
}

export default function DashboardProfilePage() {
  const pathname = usePathname();
  const router = useRouter();

  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [timezoneDraft, setTimezoneDraft] = useState("UTC");
  const [timezoneSaving, setTimezoneSaving] = useState(false);
  const [timezoneMessage, setTimezoneMessage] = useState<string | null>(null);
  const browserTimezone = useMemo(() => detectBrowserTimezone(), []);

  const timezoneOptions = useMemo(() => {
    try {
      const supported = Intl.supportedValuesOf?.("timeZone");
      if (Array.isArray(supported) && supported.length > 0) {
        return supported;
      }
    } catch {
      // ignore
    }
    return ["UTC", "Asia/Seoul", "America/Los_Angeles", "America/New_York", "Europe/London"];
  }, []);

  const loadProfile = useCallback(async () => {
    setLoading(true);
    setError(null);
    setTimezoneMessage(null);

    const { error: upsertError } = await upsertUserProfile();
    if (upsertError) {
      setError("Failed to initialize user profile.");
      setLoading(false);
      return;
    }

    const {
      data: { user },
      error: userError,
    } = await supabase.auth.getUser();
    if (userError || !user) {
      const next = encodeURIComponent(buildNextPath(pathname, window.location.search));
      router.replace(`/?next=${next}`);
      setLoading(false);
      return;
    }

    const { data, error: profileError } = await supabase
      .from("users")
      .select("id,email,full_name,timezone,created_at")
      .eq("id", user.id)
      .maybeSingle();
    if (profileError) {
      setError("Failed to load profile.");
      setLoading(false);
      return;
    }

    const nextProfile = (data as UserProfile | null) ?? null;
    setProfile(nextProfile);
    setTimezoneDraft(nextProfile?.timezone ?? browserTimezone);
    setLoading(false);
  }, [browserTimezone, pathname, router]);

  const handleSaveTimezone = useCallback(async () => {
    if (!profile) {
      return;
    }
    setTimezoneSaving(true);
    setTimezoneMessage(null);
    setError(null);

    const result = await updateUserTimezone(timezoneDraft);
    if (result.error) {
      setError("Failed to save timezone.");
      setTimezoneSaving(false);
      return;
    }
    setProfile((prev) => (prev ? { ...prev, timezone: timezoneDraft } : prev));
    setTimezoneMessage("Timezone saved.");
    setTimezoneSaving(false);
  }, [profile, timezoneDraft]);

  useEffect(() => {
    void loadProfile();
  }, [loadProfile]);

  useEffect(() => {
    const handler = (event: Event) => {
      const custom = event as CustomEvent<{ path?: string }>;
      if (custom.detail?.path === pathname) {
        void loadProfile();
      }
    };
    window.addEventListener("dashboard:v2:refresh", handler as EventListener);
    return () => {
      window.removeEventListener("dashboard:v2:refresh", handler as EventListener);
    };
  }, [loadProfile, pathname]);

  return (
    <section className="space-y-4">
      <h1 className="text-2xl font-semibold">Profile</h1>
      <p className="text-sm text-[var(--text-secondary)]">Manage your profile and timezone preference.</p>

      {error ? <AlertBanner message={error} tone="danger" /> : null}
      {loading ? <p className="text-sm text-[var(--muted)]">Loading profile...</p> : null}

      {!loading && profile ? (
        <div className="ds-card space-y-4 p-4">
          <div className="space-y-1">
            <p className="text-xs text-[var(--muted)]">User ID</p>
            <p className="font-mono text-xs">{profile.id}</p>
          </div>
          <div className="space-y-1">
            <p className="text-xs text-[var(--muted)]">Email</p>
            <p className="text-sm">{profile.email ?? "-"}</p>
          </div>
          <div className="space-y-1">
            <p className="text-xs text-[var(--muted)]">Full name</p>
            <p className="text-sm">{profile.full_name ?? "-"}</p>
          </div>
          <div className="space-y-1">
            <p className="text-xs text-[var(--muted)]">Joined at</p>
            <p className="text-sm">{asDate(profile.created_at)}</p>
          </div>

          <div className="border-t border-[var(--border)] pt-4">
            <p className="mb-2 text-sm font-medium">Timezone</p>
            <div className="flex flex-wrap items-center gap-2">
              <select
                value={timezoneDraft}
                onChange={(event) => setTimezoneDraft(event.target.value)}
                className="ds-input h-11 min-w-[280px] rounded-md px-3 text-sm md:h-9"
              >
                {timezoneOptions.map((tz) => (
                  <option key={tz} value={tz}>
                    {tz}
                  </option>
                ))}
              </select>
              <button
                type="button"
                onClick={() => void handleSaveTimezone()}
                disabled={timezoneSaving}
                className="ds-btn h-11 rounded-md px-3 text-sm disabled:cursor-not-allowed disabled:opacity-60 md:h-9"
              >
                {timezoneSaving ? "Saving..." : "Save timezone"}
              </button>
              <span className="text-xs text-[var(--muted)]">Browser: {browserTimezone}</span>
            </div>
            {timezoneMessage ? <p className="mt-2 text-sm text-[var(--text-secondary)]">{timezoneMessage}</p> : null}
          </div>
        </div>
      ) : null}
    </section>
  );
}
