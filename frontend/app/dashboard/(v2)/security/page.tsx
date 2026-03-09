"use client";

import { useCallback, useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import AlertBanner from "../../../../components/dashboard-v2/alert-banner";
import { buildNextPath, dashboardApiGet, dashboardApiRequest } from "../../../../lib/dashboard-v2-client";
import PageTitleWithTooltip from "@/components/dashboard-v2/page-title-with-tooltip";

type UserSecuritySettings = {
  user_id: string;
  mfa_enabled: boolean;
  session_timeout_minutes: number;
  password_rotation_days: number;
  updated_at?: string | null;
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

export default function DashboardSecurityPage() {
  const pathname = usePathname();
  const router = useRouter();

  const [settings, setSettings] = useState<UserSecuritySettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const [mfaDraft, setMfaDraft] = useState<"enabled" | "disabled">("disabled");
  const [sessionTimeoutDraft, setSessionTimeoutDraft] = useState("60");
  const [passwordRotationDraft, setPasswordRotationDraft] = useState("90");

  const handle401 = useCallback(() => {
    const next = encodeURIComponent(buildNextPath(pathname, window.location.search));
    router.replace(`/?next=${next}`);
  }, [pathname, router]);

  const loadSettings = useCallback(async () => {
    setLoading(true);
    setError(null);
    setMessage(null);

    const response = await dashboardApiGet<UserSecuritySettings>("/api/users/me/security");
    if (response.status === 401) {
      handle401();
      setLoading(false);
      return;
    }
    if (!response.ok || !response.data) {
      setError(response.error ?? "Failed to load security settings.");
      setLoading(false);
      return;
    }

    setSettings(response.data);
    setMfaDraft(response.data.mfa_enabled ? "enabled" : "disabled");
    setSessionTimeoutDraft(String(response.data.session_timeout_minutes));
    setPasswordRotationDraft(String(response.data.password_rotation_days));
    setLoading(false);
  }, [handle401]);

  const handleSave = useCallback(async () => {
    const sessionTimeoutMinutes = Number.parseInt(sessionTimeoutDraft, 10);
    const passwordRotationDays = Number.parseInt(passwordRotationDraft, 10);
    if (!Number.isFinite(sessionTimeoutMinutes) || sessionTimeoutMinutes < 15 || sessionTimeoutMinutes > 1440) {
      setError("Session timeout must be between 15 and 1440 minutes.");
      return;
    }
    if (!Number.isFinite(passwordRotationDays) || passwordRotationDays < 30 || passwordRotationDays > 365) {
      setError("Password rotation must be between 30 and 365 days.");
      return;
    }

    setSaving(true);
    setError(null);
    setMessage(null);
    const response = await dashboardApiRequest<UserSecuritySettings>("/api/users/me/security", {
      method: "PATCH",
      body: {
        mfa_enabled: mfaDraft === "enabled",
        session_timeout_minutes: sessionTimeoutMinutes,
        password_rotation_days: passwordRotationDays,
      },
    });

    if (response.status === 401) {
      handle401();
      setSaving(false);
      return;
    }
    if (!response.ok || !response.data) {
      setError(response.error ?? "Failed to save security settings.");
      setSaving(false);
      return;
    }

    setSettings(response.data);
    setMfaDraft(response.data.mfa_enabled ? "enabled" : "disabled");
    setSessionTimeoutDraft(String(response.data.session_timeout_minutes));
    setPasswordRotationDraft(String(response.data.password_rotation_days));
    setMessage("Security settings saved.");
    setSaving(false);
  }, [handle401, mfaDraft, passwordRotationDraft, sessionTimeoutDraft]);

  useEffect(() => {
    void loadSettings();
  }, [loadSettings]);

  if (loading) {
    return (
      <section className="space-y-4">
        <PageTitleWithTooltip
          title="Security"
          tooltip="Manage your personal MFA, session timeout, and password rotation settings."
        />
        <p className="text-sm text-muted-foreground">Manage personal MFA/session/password policy preferences.</p>
        <div className="ds-card flex min-h-[220px] items-center justify-center p-4">
          <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
        </div>
      </section>
    );
  }

  return (
    <section className="space-y-4">
      <PageTitleWithTooltip
        title="Security"
        tooltip="Manage your personal MFA, session timeout, and password rotation settings."
      />
      <p className="text-sm text-muted-foreground">
        Manage personal MFA/session/password policy preferences.
      </p>

      {error ? <AlertBanner message={error} tone="danger" /> : null}
      <div className="ds-card space-y-4 p-4">
          <div className="grid gap-3 xl:grid-cols-3">
            <label className="space-y-1">
              <span className="text-xs text-muted-foreground">MFA</span>
              <Select
                value={mfaDraft}
                onChange={(event) => setMfaDraft(event.target.value as "enabled" | "disabled")}
                className="ds-input h-11 rounded-md px-3 text-sm md:h-9"
              >
                <option value="enabled">Enabled</option>
                <option value="disabled">Disabled</option>
              </Select>
            </label>

            <label className="space-y-1">
              <span className="text-xs text-muted-foreground">Session Timeout (minutes)</span>
              <Input
                type="number"
                min={15}
                max={1440}
                step={1}
                value={sessionTimeoutDraft}
                onChange={(event) => setSessionTimeoutDraft(event.target.value)}
                className="h-11 rounded-md px-3 text-sm md:h-9"
              />
            </label>

            <label className="space-y-1">
              <span className="text-xs text-muted-foreground">Password Rotation (days)</span>
              <Input
                type="number"
                min={30}
                max={365}
                step={1}
                value={passwordRotationDraft}
                onChange={(event) => setPasswordRotationDraft(event.target.value)}
                className="h-11 rounded-md px-3 text-sm md:h-9"
              />
            </label>
          </div>

          <div className="flex items-center justify-between border-t border-border pt-4">
            <p className="text-xs text-muted-foreground">Last updated: {asDate(settings?.updated_at)}</p>
            <Button
              type="button"
              onClick={() => void handleSave()}
              disabled={saving}
              className="ds-btn h-11 rounded-md px-3 text-sm disabled:cursor-not-allowed disabled:opacity-60 md:h-9"
            >
              {saving ? "Saving..." : "Save settings"}
            </Button>
          </div>

          {message ? <p className="text-sm text-muted-foreground">{message}</p> : null}
      </div>
    </section>
  );
}
