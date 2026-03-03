create table if not exists public.incident_banners (
  id bigserial primary key,
  user_id uuid not null unique references auth.users(id) on delete cascade,
  enabled boolean not null default false,
  message text,
  severity text not null default 'info',
  starts_at timestamptz,
  ends_at timestamptz,
  updated_at timestamptz not null default now()
);

create index if not exists idx_incident_banners_user_id
  on public.incident_banners (user_id);

alter table if exists public.incident_banners enable row level security;

drop policy if exists "incident_banners_select_own" on public.incident_banners;
create policy "incident_banners_select_own"
  on public.incident_banners
  for select
  to authenticated
  using (auth.uid() = user_id);

drop policy if exists "incident_banners_insert_own" on public.incident_banners;
create policy "incident_banners_insert_own"
  on public.incident_banners
  for insert
  to authenticated
  with check (auth.uid() = user_id);

drop policy if exists "incident_banners_update_own" on public.incident_banners;
create policy "incident_banners_update_own"
  on public.incident_banners
  for update
  to authenticated
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);
