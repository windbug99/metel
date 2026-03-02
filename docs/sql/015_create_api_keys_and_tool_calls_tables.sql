create table if not exists public.api_keys (
  id bigserial primary key,
  user_id uuid not null references auth.users(id) on delete cascade,
  name text not null default 'default',
  key_prefix text not null,
  key_hash text not null unique,
  is_active boolean not null default true,
  last_used_at timestamptz,
  revoked_at timestamptz,
  created_at timestamptz not null default now()
);

create index if not exists idx_api_keys_user_id_created_at
  on public.api_keys (user_id, created_at desc);

create table if not exists public.tool_calls (
  id bigserial primary key,
  request_id text,
  user_id uuid not null references auth.users(id) on delete cascade,
  api_key_id bigint not null references public.api_keys(id) on delete cascade,
  tool_name text not null,
  status text not null check (status in ('success', 'fail')),
  error_code text,
  latency_ms int not null default 0,
  created_at timestamptz not null default now()
);

create index if not exists idx_tool_calls_api_key_created_at
  on public.tool_calls (api_key_id, created_at desc);

create index if not exists idx_tool_calls_user_created_at
  on public.tool_calls (user_id, created_at desc);

alter table public.api_keys enable row level security;
alter table public.tool_calls enable row level security;

drop policy if exists "api_keys_select_own" on public.api_keys;
create policy "api_keys_select_own"
  on public.api_keys
  for select
  to authenticated
  using (auth.uid() = user_id);

drop policy if exists "api_keys_insert_own" on public.api_keys;
create policy "api_keys_insert_own"
  on public.api_keys
  for insert
  to authenticated
  with check (auth.uid() = user_id);

drop policy if exists "api_keys_update_own" on public.api_keys;
create policy "api_keys_update_own"
  on public.api_keys
  for update
  to authenticated
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);

drop policy if exists "tool_calls_select_own" on public.tool_calls;
create policy "tool_calls_select_own"
  on public.tool_calls
  for select
  to authenticated
  using (auth.uid() = user_id);
