create table if not exists public.audit_settings (
  id bigserial primary key,
  user_id uuid not null unique references auth.users(id) on delete cascade,
  retention_days int not null default 90,
  export_enabled boolean not null default true,
  masking_policy jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now()
);

create index if not exists idx_audit_settings_user_id
  on public.audit_settings (user_id);

alter table if exists public.audit_settings enable row level security;

drop policy if exists "audit_settings_select_own" on public.audit_settings;
create policy "audit_settings_select_own"
  on public.audit_settings
  for select
  to authenticated
  using (auth.uid() = user_id);

drop policy if exists "audit_settings_insert_own" on public.audit_settings;
create policy "audit_settings_insert_own"
  on public.audit_settings
  for insert
  to authenticated
  with check (auth.uid() = user_id);

drop policy if exists "audit_settings_update_own" on public.audit_settings;
create policy "audit_settings_update_own"
  on public.audit_settings
  for update
  to authenticated
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);
