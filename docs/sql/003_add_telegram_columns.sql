alter table public.users
  add column if not exists telegram_chat_id bigint,
  add column if not exists telegram_username text;

create unique index if not exists users_telegram_chat_id_key
  on public.users (telegram_chat_id)
  where telegram_chat_id is not null;
