create table if not exists pending_actions (
  user_id text primary key,
  intent text not null,
  action text not null,
  task_id text not null,
  plan_json jsonb not null,
  plan_source text not null default 'rule',
  collected_slots jsonb not null default '{}'::jsonb,
  missing_slots jsonb not null default '[]'::jsonb,
  expires_at double precision not null,
  status text not null default 'active',
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);

create index if not exists idx_pending_actions_status_expires
  on pending_actions (status, expires_at);
