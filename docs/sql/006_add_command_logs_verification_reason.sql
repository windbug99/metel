alter table public.command_logs
  add column if not exists verification_reason text;