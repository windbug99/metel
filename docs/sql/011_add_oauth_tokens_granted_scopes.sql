alter table public.oauth_tokens
  add column if not exists granted_scopes text[];
