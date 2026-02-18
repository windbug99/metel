create table if not exists public.oauth_tokens (
  id bigserial primary key,
  user_id uuid not null references auth.users(id) on delete cascade,
  provider text not null,
  access_token_encrypted text not null,
  workspace_id text,
  workspace_name text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (user_id, provider)
);

alter table public.oauth_tokens enable row level security;

drop policy if exists "oauth_tokens_select_own" on public.oauth_tokens;
create policy "oauth_tokens_select_own"
  on public.oauth_tokens
  for select
  to authenticated
  using (auth.uid() = user_id);
