create table if not exists public.command_logs (
  id bigserial primary key,
  user_id uuid references auth.users(id) on delete set null,
  channel text not null default 'telegram',
  chat_id bigint,
  command text not null,
  status text not null,
  error_code text,
  detail text,
  created_at timestamptz not null default now()
);

alter table public.command_logs enable row level security;

drop policy if exists "command_logs_select_own" on public.command_logs;
create policy "command_logs_select_own"
  on public.command_logs
  for select
  to authenticated
  using (auth.uid() = user_id);
