alter table public.api_keys
  add column if not exists allowed_tools text[];
