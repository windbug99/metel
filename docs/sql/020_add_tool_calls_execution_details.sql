alter table if exists public.tool_calls
  add column if not exists trace_id text;

alter table if exists public.tool_calls
  add column if not exists connector text;

alter table if exists public.tool_calls
  add column if not exists request_payload jsonb;

alter table if exists public.tool_calls
  add column if not exists resolved_payload jsonb;

alter table if exists public.tool_calls
  add column if not exists risk_result jsonb;

alter table if exists public.tool_calls
  add column if not exists upstream_status int;

alter table if exists public.tool_calls
  add column if not exists retry_count int not null default 0;

alter table if exists public.tool_calls
  add column if not exists backoff_ms int not null default 0;

alter table if exists public.tool_calls
  add column if not exists masked_fields text[];

create index if not exists idx_tool_calls_trace_id
  on public.tool_calls (trace_id);

create index if not exists idx_tool_calls_connector_created_at
  on public.tool_calls (connector, created_at desc);
