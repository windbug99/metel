create table if not exists public.pipeline_step_logs (
  id bigserial primary key,
  run_id text not null,
  request_id text not null,
  user_id uuid references auth.users(id) on delete set null,
  task_index integer not null,
  task_id text not null,
  sentence text not null,
  service text,
  api text,
  catalog_id text,
  contract_version text not null default 'v1',
  llm_status text not null default 'success',
  validation_status text not null default 'passed',
  call_status text not null default 'succeeded',
  missing_required_fields jsonb not null default '[]'::jsonb,
  validation_error_code text,
  failure_reason text,
  request_payload jsonb,
  normalized_response jsonb,
  raw_response jsonb,
  created_at timestamptz not null default now()
);

create index if not exists idx_pipeline_step_logs_run_task
  on public.pipeline_step_logs (run_id, task_index);

create index if not exists idx_pipeline_step_logs_user_created
  on public.pipeline_step_logs (user_id, created_at desc);

alter table public.pipeline_step_logs enable row level security;

drop policy if exists "pipeline_step_logs_select_own" on public.pipeline_step_logs;
create policy "pipeline_step_logs_select_own"
  on public.pipeline_step_logs
  for select
  to authenticated
  using (auth.uid() = user_id);

drop policy if exists "pipeline_step_logs_service_role_all" on public.pipeline_step_logs;
create policy "pipeline_step_logs_service_role_all"
  on public.pipeline_step_logs
  for all
  to service_role
  using (true)
  with check (true);

alter table public.command_logs
  add column if not exists run_id text,
  add column if not exists request_id text,
  add column if not exists catalog_id text,
  add column if not exists final_status text,
  add column if not exists failed_task_id text,
  add column if not exists failure_reason text,
  add column if not exists missing_required_fields jsonb default '[]'::jsonb;

create index if not exists idx_command_logs_run_id
  on public.command_logs (run_id);

