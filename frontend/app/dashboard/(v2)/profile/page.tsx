"use client";

import { Select } from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useCallback, useEffect, useMemo, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { Loader2 } from "lucide-react";

import { buildNextPath, dashboardApiRequest } from "../../../../lib/dashboard-v2-client";
import { detectBrowserTimezone, updateUserTimezone, upsertUserProfile } from "../../../../lib/profile";
import { supabase } from "../../../../lib/supabase";
import AlertBanner from "../../../../components/dashboard-v2/alert-banner";
import PageTitleWithTooltip from "@/components/dashboard-v2/page-title-with-tooltip";

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
  const [themeDraft, setThemeDraft] = useState<"light" | "dark">("light");
  const [themeMessage, setThemeMessage] = useState<string | null>(null);
  const [inviteTokenDraft, setInviteTokenDraft] = useState("");
  const [inviteAccepting, setInviteAccepting] = useState(false);
  const [inviteMessage, setInviteMessage] = useState<string | null>(null);
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
    const stored = window.localStorage.getItem("dashboard-v2-theme");
    if (stored === "light" || stored === "dark") {
      setThemeDraft(stored);
      return;
    }
    const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    setThemeDraft(prefersDark ? "dark" : "light");
  }, []);

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

  const handleSaveTheme = useCallback(() => {
    window.localStorage.setItem("dashboard-v2-theme", themeDraft);
    window.dispatchEvent(
      new CustomEvent("dashboard:v2:theme", {
        detail: { theme: themeDraft },
      })
    );
    setThemeMessage("Theme updated.");
  }, [themeDraft]);

  const handleAcceptInvite = useCallback(async () => {
    const token = inviteTokenDraft.trim();
    if (!token) {
      setError("Invite token is required.");
      return;
    }
    setInviteAccepting(true);
    setInviteMessage(null);
    setError(null);
    const result = await dashboardApiRequest("/api/organizations/invites/accept", {
      method: "POST",
      body: { token },
    });
    if (result.status === 401) {
      const next = encodeURIComponent(buildNextPath(pathname, window.location.search));
      router.replace(`/?next=${next}`);
      setInviteAccepting(false);
      return;
    }
    if (result.status === 403 || result.status === 404 || result.status === 409) {
      setError("Invite acceptance failed. Check token, role, and invite status.");
      setInviteAccepting(false);
      return;
    }
    if (!result.ok) {
      setError(result.error ?? "Failed to accept invite.");
      setInviteAccepting(false);
      return;
    }
    setInviteTokenDraft("");
    setInviteMessage("Invite accepted. Organization list was refreshed.");
    window.dispatchEvent(
      new CustomEvent("dashboard:v2:refresh", {
        detail: { path: "/dashboard/access/organizations" },
      })
    );
    setInviteAccepting(false);
  }, [inviteTokenDraft, pathname, router]);

  if (loading) {
    return (
      <section className="space-y-4">
        <PageTitleWithTooltip
          title="Profile"
          tooltip="Manage your personal profile preferences and account settings."
        />
        <p className="text-sm text-muted-foreground">Manage your profile and timezone preference.</p>
        <div className="ds-card flex min-h-[220px] items-center justify-center p-4">
          <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
        </div>
      </section>
    );
  }

  return (
    <section className="space-y-4">
      <PageTitleWithTooltip
        title="Profile"
        tooltip="Manage your personal profile preferences and account settings."
      />
      <p className="text-sm text-muted-foreground">Manage your profile and timezone preference.</p>

      {error ? <AlertBanner message={error} tone="danger" /> : null}

      {profile ? (
        <div className="ds-card space-y-4 p-4">
          <div className="space-y-1">
            <p className="text-xs text-muted-foreground">User ID</p>
            <p className="font-mono text-xs">{profile.id}</p>
          </div>
          <div className="space-y-1">
            <p className="text-xs text-muted-foreground">Email</p>
            <p className="text-sm">{profile.email ?? "-"}</p>
          </div>
          <div className="space-y-1">
            <p className="text-xs text-muted-foreground">Full name</p>
            <p className="text-sm">{profile.full_name ?? "-"}</p>
          </div>
          <div className="space-y-1">
            <p className="text-xs text-muted-foreground">Joined at</p>
            <p className="text-sm">{asDate(profile.created_at)}</p>
          </div>

          <div className="border-t border-border pt-4">
            <p className="mb-2 text-sm font-medium">Timezone</p>
            <div className="flex flex-wrap items-center gap-2">
              <Select
                value={timezoneDraft}
                onChange={(event) => setTimezoneDraft(event.target.value)}
                className="ds-input h-11 min-w-[280px] rounded-md px-3 text-sm md:h-9"
              >
                {timezoneOptions.map((tz) => (
                  <option key={tz} value={tz}>
                    {tz}
                  </option>
                ))}
              </Select>
              <Button
                type="button"
                onClick={() => void handleSaveTimezone()}
                disabled={timezoneSaving}
                className="ds-btn h-11 rounded-md px-3 text-sm disabled:cursor-not-allowed disabled:opacity-60 md:h-9"
              >
                {timezoneSaving ? "Saving..." : "Save timezone"}
              </Button>
              <span className="text-xs text-muted-foreground">Browser: {browserTimezone}</span>
            </div>
            {timezoneMessage ? <p className="mt-2 text-sm text-muted-foreground">{timezoneMessage}</p> : null}
          </div>

          <div className="border-t border-border pt-4">
            <p className="mb-2 text-sm font-medium">Theme</p>
            <div className="flex flex-wrap items-center gap-2">
              <Select
                value={themeDraft}
                onChange={(event) => setThemeDraft(event.target.value as "light" | "dark")}
                className="ds-input h-11 min-w-[180px] rounded-md px-3 text-sm md:h-9"
              >
                <option value="light">Light</option>
                <option value="dark">Dark</option>
              </Select>
              <Button
                type="button"
                onClick={() => void handleSaveTheme()}
                className="ds-btn h-11 rounded-md px-3 text-sm disabled:cursor-not-allowed disabled:opacity-60 md:h-9"
              >
                Save theme
              </Button>
            </div>
            {themeMessage ? <p className="mt-2 text-sm text-muted-foreground">{themeMessage}</p> : null}
          </div>

          <div className="border-t border-border pt-4">
            <p className="mb-2 text-sm font-medium">Accept invite token</p>
            <div className="flex items-center gap-2">
              <Input
                value={inviteTokenDraft}
                onChange={(event) => setInviteTokenDraft(event.target.value)}
                placeholder="Invite token"
                className="h-11 flex-1 rounded-md px-3 text-sm md:h-9"
              />
              <Button
                type="button"
                onClick={() => void handleAcceptInvite()}
                disabled={inviteAccepting}
                className="h-11 shrink-0 rounded-md px-3 text-sm disabled:cursor-not-allowed disabled:opacity-60 md:h-9"
              >
                {inviteAccepting ? "Accepting..." : "Accept Invite"}
              </Button>
            </div>
            {inviteMessage ? <p className="mt-2 text-sm text-muted-foreground">{inviteMessage}</p> : null}
          </div>
        </div>
      ) : null}
    </section>
  );
}
