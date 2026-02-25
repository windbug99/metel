alter table public.pipeline_links
  add column if not exists error_code text,
  add column if not exists compensation_status text default 'not_required';
