create table if not exists public.pipeline_links (
  id bigserial primary key,
  user_id uuid references auth.users(id) on delete cascade,
  event_id text not null,
  notion_page_id text,
  linear_issue_id text,
  run_id text not null,
  status text not null default 'succeeded',
  updated_at timestamptz not null default now(),
  unique(user_id, event_id)
);

create index if not exists idx_pipeline_links_user_updated
  on public.pipeline_links (user_id, updated_at desc);

alter table public.pipeline_links enable row level security;

drop policy if exists "pipeline_links_select_own" on public.pipeline_links;
create policy "pipeline_links_select_own"
  on public.pipeline_links
  for select
  to authenticated
  using (auth.uid() = user_id);

drop policy if exists "pipeline_links_service_role_all" on public.pipeline_links;
create policy "pipeline_links_service_role_all"
  on public.pipeline_links
  for all
  to service_role
  using (true)
  with check (true);
