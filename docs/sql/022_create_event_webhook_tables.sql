create table if not exists public.webhook_subscriptions (
  id bigserial primary key,
  user_id uuid not null references auth.users(id) on delete cascade,
  name text not null,
  endpoint_url text not null,
  secret text,
  event_types text[] not null default '{}'::text[],
  is_active boolean not null default true,
  last_delivery_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists idx_webhook_subscriptions_user_id_created_at
  on public.webhook_subscriptions (user_id, created_at desc);

create table if not exists public.webhook_deliveries (
  id bigserial primary key,
  subscription_id bigint not null references public.webhook_subscriptions(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  event_type text not null,
  payload jsonb not null default '{}'::jsonb,
  status text not null default 'pending',
  http_status int,
  error_message text,
  retry_count int not null default 0,
  next_retry_at timestamptz,
  delivered_at timestamptz,
  created_at timestamptz not null default now()
);

create index if not exists idx_webhook_deliveries_user_id_created_at
  on public.webhook_deliveries (user_id, created_at desc);

create index if not exists idx_webhook_deliveries_subscription_id_created_at
  on public.webhook_deliveries (subscription_id, created_at desc);
