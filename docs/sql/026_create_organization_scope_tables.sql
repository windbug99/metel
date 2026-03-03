create table if not exists public.organizations (
  id bigserial primary key,
  name text not null,
  created_by uuid not null references auth.users(id) on delete cascade,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.org_memberships (
  id bigserial primary key,
  organization_id bigint not null references public.organizations(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  role text not null default 'member',
  created_at timestamptz not null default now(),
  unique (organization_id, user_id)
);

create index if not exists idx_organizations_created_by
  on public.organizations (created_by);

create index if not exists idx_org_memberships_user_id
  on public.org_memberships (user_id);

create index if not exists idx_org_memberships_organization_id
  on public.org_memberships (organization_id);

alter table if exists public.organizations enable row level security;
alter table if exists public.org_memberships enable row level security;

drop policy if exists "organizations_select_member" on public.organizations;
create policy "organizations_select_member"
  on public.organizations
  for select
  to authenticated
  using (
    exists (
      select 1
      from public.org_memberships m
      where m.organization_id = organizations.id
        and m.user_id = auth.uid()
    )
  );

drop policy if exists "organizations_insert_owner" on public.organizations;
create policy "organizations_insert_owner"
  on public.organizations
  for insert
  to authenticated
  with check (created_by = auth.uid());

drop policy if exists "organizations_update_owner" on public.organizations;
create policy "organizations_update_owner"
  on public.organizations
  for update
  to authenticated
  using (created_by = auth.uid())
  with check (created_by = auth.uid());

drop policy if exists "org_memberships_select_member" on public.org_memberships;
create policy "org_memberships_select_member"
  on public.org_memberships
  for select
  to authenticated
  using (
    exists (
      select 1
      from public.org_memberships mine
      where mine.organization_id = org_memberships.organization_id
        and mine.user_id = auth.uid()
    )
  );

drop policy if exists "org_memberships_insert_owner" on public.org_memberships;
create policy "org_memberships_insert_owner"
  on public.org_memberships
  for insert
  to authenticated
  with check (
    exists (
      select 1
      from public.organizations o
      where o.id = org_memberships.organization_id
        and o.created_by = auth.uid()
    )
  );

drop policy if exists "org_memberships_update_owner" on public.org_memberships;
create policy "org_memberships_update_owner"
  on public.org_memberships
  for update
  to authenticated
  using (
    exists (
      select 1
      from public.organizations o
      where o.id = org_memberships.organization_id
        and o.created_by = auth.uid()
    )
  )
  with check (
    exists (
      select 1
      from public.organizations o
      where o.id = org_memberships.organization_id
        and o.created_by = auth.uid()
    )
  );

drop policy if exists "org_memberships_delete_owner" on public.org_memberships;
create policy "org_memberships_delete_owner"
  on public.org_memberships
  for delete
  to authenticated
  using (
    exists (
      select 1
      from public.organizations o
      where o.id = org_memberships.organization_id
        and o.created_by = auth.uid()
    )
  );
