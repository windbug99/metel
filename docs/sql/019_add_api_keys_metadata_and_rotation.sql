alter table if exists public.api_keys
  add column if not exists issued_by text;

alter table if exists public.api_keys
  add column if not exists memo text;

alter table if exists public.api_keys
  add column if not exists tags text[];

alter table if exists public.api_keys
  add column if not exists rotated_from bigint references public.api_keys(id) on delete set null;

create index if not exists idx_api_keys_rotated_from
  on public.api_keys (rotated_from);
