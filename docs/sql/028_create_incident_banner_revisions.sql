create table if not exists public.incident_banner_revisions (
  id bigserial primary key,
  user_id uuid not null references public.users(id) on delete cascade,
  enabled boolean not null default false,
  message text,
  severity text not null default 'info',
  starts_at timestamptz,
  ends_at timestamptz,
  status text not null default 'pending',
  requested_by uuid not null references public.users(id) on delete cascade,
  approved_by uuid references public.users(id) on delete set null,
  approved_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists idx_incident_banner_revisions_user_id_created_at
  on public.incident_banner_revisions (user_id, created_at desc);

alter table if exists public.incident_banner_revisions enable row level security;

drop policy if exists "incident_banner_revisions_select_own" on public.incident_banner_revisions;
create policy "incident_banner_revisions_select_own"
  on public.incident_banner_revisions
  for select
  using (user_id = auth.uid());

drop policy if exists "incident_banner_revisions_insert_own" on public.incident_banner_revisions;
create policy "incident_banner_revisions_insert_own"
  on public.incident_banner_revisions
  for insert
  with check (user_id = auth.uid() and requested_by = auth.uid());

drop policy if exists "incident_banner_revisions_update_own" on public.incident_banner_revisions;
create policy "incident_banner_revisions_update_own"
  on public.incident_banner_revisions
  for update
  using (user_id = auth.uid())
  with check (user_id = auth.uid());
