create table if not exists public.org_invites (
  id bigserial primary key,
  organization_id bigint not null references public.organizations(id) on delete cascade,
  token text not null unique,
  invited_email text,
  role text not null default 'member',
  invited_by uuid not null references public.users(id) on delete cascade,
  expires_at timestamptz not null,
  accepted_by uuid references public.users(id) on delete set null,
  accepted_at timestamptz,
  revoked_at timestamptz,
  created_at timestamptz not null default now()
);

create index if not exists idx_org_invites_organization_id
  on public.org_invites (organization_id);

create index if not exists idx_org_invites_token
  on public.org_invites (token);

create table if not exists public.org_role_change_requests (
  id bigserial primary key,
  organization_id bigint not null references public.organizations(id) on delete cascade,
  target_user_id uuid not null references public.users(id) on delete cascade,
  requested_role text not null,
  reason text,
  status text not null default 'pending',
  requested_by uuid not null references public.users(id) on delete cascade,
  reviewed_by uuid references public.users(id) on delete set null,
  reviewed_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists idx_org_role_change_requests_organization_id
  on public.org_role_change_requests (organization_id, created_at desc);

create index if not exists idx_org_role_change_requests_target_user_id
  on public.org_role_change_requests (target_user_id);

alter table if exists public.org_invites enable row level security;
alter table if exists public.org_role_change_requests enable row level security;

drop policy if exists "org_invites_select_org_member" on public.org_invites;
create policy "org_invites_select_org_member"
  on public.org_invites
  for select
  using (
    exists (
      select 1
      from public.org_memberships m
      where m.organization_id = org_invites.organization_id
        and m.user_id = auth.uid()
    )
  );

drop policy if exists "org_invites_insert_org_owner" on public.org_invites;
create policy "org_invites_insert_org_owner"
  on public.org_invites
  for insert
  with check (
    exists (
      select 1
      from public.organizations o
      where o.id = org_invites.organization_id
        and o.created_by = auth.uid()
    )
  );

drop policy if exists "org_invites_update_org_owner" on public.org_invites;
create policy "org_invites_update_org_owner"
  on public.org_invites
  for update
  using (
    exists (
      select 1
      from public.organizations o
      where o.id = org_invites.organization_id
        and o.created_by = auth.uid()
    )
  )
  with check (
    exists (
      select 1
      from public.organizations o
      where o.id = org_invites.organization_id
        and o.created_by = auth.uid()
    )
  );

drop policy if exists "org_role_change_requests_select_org_member" on public.org_role_change_requests;
create policy "org_role_change_requests_select_org_member"
  on public.org_role_change_requests
  for select
  using (
    exists (
      select 1
      from public.org_memberships m
      where m.organization_id = org_role_change_requests.organization_id
        and m.user_id = auth.uid()
    )
  );

drop policy if exists "org_role_change_requests_insert_org_owner" on public.org_role_change_requests;
create policy "org_role_change_requests_insert_org_owner"
  on public.org_role_change_requests
  for insert
  with check (
    exists (
      select 1
      from public.organizations o
      where o.id = org_role_change_requests.organization_id
        and o.created_by = auth.uid()
    )
  );

drop policy if exists "org_role_change_requests_update_org_owner" on public.org_role_change_requests;
create policy "org_role_change_requests_update_org_owner"
  on public.org_role_change_requests
  for update
  using (
    exists (
      select 1
      from public.organizations o
      where o.id = org_role_change_requests.organization_id
        and o.created_by = auth.uid()
    )
  )
  with check (
    exists (
      select 1
      from public.organizations o
      where o.id = org_role_change_requests.organization_id
        and o.created_by = auth.uid()
    )
  );
