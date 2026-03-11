alter table public.oauth_tokens
  add column if not exists refresh_token_encrypted text,
  add column if not exists token_expires_at timestamptz,
  add column if not exists provider_account_id text,
  add column if not exists provider_team_id text,
  add column if not exists provider_metadata jsonb;

create table if not exists public.oauth_pending_states (
  state text primary key,
  user_id uuid not null references auth.users(id) on delete cascade,
  provider text not null,
  code_verifier text not null,
  created_at timestamptz not null default now(),
  expires_at timestamptz not null
);

create index if not exists oauth_pending_states_user_provider_idx
  on public.oauth_pending_states (user_id, provider);

create index if not exists oauth_pending_states_expires_at_idx
  on public.oauth_pending_states (expires_at);

alter table public.oauth_pending_states enable row level security;
