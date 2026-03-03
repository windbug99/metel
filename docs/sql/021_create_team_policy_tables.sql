create table if not exists public.teams (
  id bigserial primary key,
  user_id uuid not null references auth.users(id) on delete cascade,
  name text not null,
  description text,
  is_active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists idx_teams_user_id_created_at
  on public.teams (user_id, created_at desc);

create table if not exists public.team_memberships (
  id bigserial primary key,
  team_id bigint not null references public.teams(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  role text not null default 'member',
  created_at timestamptz not null default now(),
  unique(team_id, user_id)
);

create index if not exists idx_team_memberships_team_id
  on public.team_memberships (team_id);

create table if not exists public.team_policies (
  id bigserial primary key,
  team_id bigint not null unique references public.teams(id) on delete cascade,
  policy_json jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists idx_team_policies_policy_json_gin
  on public.team_policies using gin (policy_json);

create table if not exists public.policy_revisions (
  id bigserial primary key,
  team_id bigint not null references public.teams(id) on delete cascade,
  source text not null default 'team_policy_update',
  policy_json jsonb not null default '{}'::jsonb,
  created_by uuid references auth.users(id) on delete set null,
  created_at timestamptz not null default now()
);

create index if not exists idx_policy_revisions_team_id_created_at
  on public.policy_revisions (team_id, created_at desc);

alter table if exists public.api_keys
  add column if not exists team_id bigint references public.teams(id) on delete set null;

create index if not exists idx_api_keys_team_id
  on public.api_keys (team_id);
