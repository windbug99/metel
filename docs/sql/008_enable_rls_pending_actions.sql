-- pending_actions: RLS 활성화 + service_role 전용 접근 정책
-- 적용 대상: Supabase SQL Editor / migration pipeline

alter table if exists pending_actions enable row level security;
alter table if exists pending_actions force row level security;

-- 클라이언트(anon/authenticated) 직접 접근 차단
revoke all on table pending_actions from anon;
revoke all on table pending_actions from authenticated;

-- 서비스 역할 접근 권한 명시
grant all on table pending_actions to service_role;

drop policy if exists pending_actions_service_role_all on pending_actions;
create policy pending_actions_service_role_all
on pending_actions
as permissive
for all
to service_role
using (true)
with check (true);
