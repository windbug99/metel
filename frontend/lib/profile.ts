import { supabase } from "./supabase";

export function detectBrowserTimezone(): string {
  try {
    const tz = Intl.DateTimeFormat().resolvedOptions().timeZone;
    if (typeof tz === "string" && tz.trim()) {
      return tz.trim();
    }
  } catch {
    // fall through
  }
  return "UTC";
}

export async function upsertUserProfile() {
  const {
    data: { user },
    error: userError
  } = await supabase.auth.getUser();

  if (userError || !user) {
    return { error: userError ?? new Error("No authenticated user") };
  }

  const fullName = typeof user.user_metadata?.full_name === "string" ? user.user_metadata.full_name : null;
  const avatarUrl = typeof user.user_metadata?.avatar_url === "string" ? user.user_metadata.avatar_url : null;
  const { error } = await supabase.from("users").upsert(
    {
      id: user.id,
      email: user.email ?? null,
      full_name: fullName,
      avatar_url: avatarUrl,
      updated_at: new Date().toISOString()
    },
    { onConflict: "id" }
  );

  return { error };
}

export async function updateUserTimezone(timezone: string) {
  const {
    data: { user },
    error: userError
  } = await supabase.auth.getUser();

  if (userError || !user) {
    return { error: userError ?? new Error("No authenticated user") };
  }

  const { error } = await supabase
    .from("users")
    .update({
      timezone,
      updated_at: new Date().toISOString()
    })
    .eq("id", user.id);

  return { error };
}
