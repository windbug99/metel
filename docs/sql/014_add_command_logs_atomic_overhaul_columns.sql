alter table public.command_logs
  add column if not exists atomic_tool_name text,
  add column if not exists atomic_verified boolean,
  add column if not exists atomic_verification_reason text,
  add column if not exists atomic_verification_retry_attempted boolean,
  add column if not exists atomic_verification_checks jsonb default '{}'::jsonb;

create index if not exists idx_command_logs_atomic_verified_created
  on public.command_logs (atomic_verified, created_at desc);

create index if not exists idx_command_logs_atomic_tool_created
  on public.command_logs (atomic_tool_name, created_at desc);
