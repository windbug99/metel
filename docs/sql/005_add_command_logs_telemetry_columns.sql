alter table public.command_logs
  add column if not exists plan_source text,
  add column if not exists execution_mode text,
  add column if not exists autonomous_fallback_reason text,
  add column if not exists llm_provider text,
  add column if not exists llm_model text;

