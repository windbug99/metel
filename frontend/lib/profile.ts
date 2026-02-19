import { supabase } from "./supabase";

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
