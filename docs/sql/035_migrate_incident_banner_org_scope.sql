-- Migrate incident banner storage from user scope to organization scope.
-- Safe to run multiple times.

alter table if exists public.incident_banners
  add column if not exists organization_id bigint references public.organizations(id) on delete cascade;

alter table if exists public.incident_banner_revisions
  add column if not exists organization_id bigint references public.organizations(id) on delete cascade;

-- Backfill organization_id from org_memberships when possible.
update public.incident_banners b
set organization_id = m.organization_id
from (
  select user_id, min(organization_id) as organization_id
  from public.org_memberships
  group by user_id
) m
where b.organization_id is null
  and b.user_id = m.user_id;

update public.incident_banner_revisions r
set organization_id = m.organization_id
from (
  select user_id, min(organization_id) as organization_id
  from public.org_memberships
  group by user_id
) m
where r.organization_id is null
  and r.user_id = m.user_id;

-- Move uniqueness from user_id -> organization_id.
alter table if exists public.incident_banners
  drop constraint if exists incident_banners_user_id_key;

create unique index if not exists idx_incident_banners_organization_id_unique
  on public.incident_banners (organization_id)
  where organization_id is not null;

create index if not exists idx_incident_banner_revisions_organization_id_created_at
  on public.incident_banner_revisions (organization_id, created_at desc);
