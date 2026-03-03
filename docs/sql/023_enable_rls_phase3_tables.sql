alter table if exists public.teams enable row level security;
alter table if exists public.team_memberships enable row level security;
alter table if exists public.team_policies enable row level security;
alter table if exists public.policy_revisions enable row level security;
alter table if exists public.webhook_subscriptions enable row level security;
alter table if exists public.webhook_deliveries enable row level security;

drop policy if exists "teams_select_own" on public.teams;
create policy "teams_select_own"
  on public.teams
  for select
  to authenticated
  using (auth.uid() = user_id);

drop policy if exists "teams_insert_own" on public.teams;
create policy "teams_insert_own"
  on public.teams
  for insert
  to authenticated
  with check (auth.uid() = user_id);

drop policy if exists "teams_update_own" on public.teams;
create policy "teams_update_own"
  on public.teams
  for update
  to authenticated
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);

drop policy if exists "team_memberships_select_team_owner_or_self" on public.team_memberships;
create policy "team_memberships_select_team_owner_or_self"
  on public.team_memberships
  for select
  to authenticated
  using (
    auth.uid() = user_id
    or exists (
      select 1
      from public.teams t
      where t.id = team_memberships.team_id
        and t.user_id = auth.uid()
    )
  );

drop policy if exists "team_memberships_insert_team_owner" on public.team_memberships;
create policy "team_memberships_insert_team_owner"
  on public.team_memberships
  for insert
  to authenticated
  with check (
    exists (
      select 1
      from public.teams t
      where t.id = team_memberships.team_id
        and t.user_id = auth.uid()
    )
  );

drop policy if exists "team_memberships_update_team_owner" on public.team_memberships;
create policy "team_memberships_update_team_owner"
  on public.team_memberships
  for update
  to authenticated
  using (
    exists (
      select 1
      from public.teams t
      where t.id = team_memberships.team_id
        and t.user_id = auth.uid()
    )
  )
  with check (
    exists (
      select 1
      from public.teams t
      where t.id = team_memberships.team_id
        and t.user_id = auth.uid()
    )
  );

drop policy if exists "team_memberships_delete_team_owner" on public.team_memberships;
create policy "team_memberships_delete_team_owner"
  on public.team_memberships
  for delete
  to authenticated
  using (
    exists (
      select 1
      from public.teams t
      where t.id = team_memberships.team_id
        and t.user_id = auth.uid()
    )
  );

drop policy if exists "team_policies_select_team_owner" on public.team_policies;
create policy "team_policies_select_team_owner"
  on public.team_policies
  for select
  to authenticated
  using (
    exists (
      select 1
      from public.teams t
      where t.id = team_policies.team_id
        and t.user_id = auth.uid()
    )
  );

drop policy if exists "team_policies_insert_team_owner" on public.team_policies;
create policy "team_policies_insert_team_owner"
  on public.team_policies
  for insert
  to authenticated
  with check (
    exists (
      select 1
      from public.teams t
      where t.id = team_policies.team_id
        and t.user_id = auth.uid()
    )
  );

drop policy if exists "team_policies_update_team_owner" on public.team_policies;
create policy "team_policies_update_team_owner"
  on public.team_policies
  for update
  to authenticated
  using (
    exists (
      select 1
      from public.teams t
      where t.id = team_policies.team_id
        and t.user_id = auth.uid()
    )
  )
  with check (
    exists (
      select 1
      from public.teams t
      where t.id = team_policies.team_id
        and t.user_id = auth.uid()
    )
  );

drop policy if exists "policy_revisions_select_team_owner" on public.policy_revisions;
create policy "policy_revisions_select_team_owner"
  on public.policy_revisions
  for select
  to authenticated
  using (
    exists (
      select 1
      from public.teams t
      where t.id = policy_revisions.team_id
        and t.user_id = auth.uid()
    )
  );

drop policy if exists "policy_revisions_insert_team_owner" on public.policy_revisions;
create policy "policy_revisions_insert_team_owner"
  on public.policy_revisions
  for insert
  to authenticated
  with check (
    exists (
      select 1
      from public.teams t
      where t.id = policy_revisions.team_id
        and t.user_id = auth.uid()
    )
  );

drop policy if exists "webhook_subscriptions_select_own" on public.webhook_subscriptions;
create policy "webhook_subscriptions_select_own"
  on public.webhook_subscriptions
  for select
  to authenticated
  using (auth.uid() = user_id);

drop policy if exists "webhook_subscriptions_insert_own" on public.webhook_subscriptions;
create policy "webhook_subscriptions_insert_own"
  on public.webhook_subscriptions
  for insert
  to authenticated
  with check (auth.uid() = user_id);

drop policy if exists "webhook_subscriptions_update_own" on public.webhook_subscriptions;
create policy "webhook_subscriptions_update_own"
  on public.webhook_subscriptions
  for update
  to authenticated
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);

drop policy if exists "webhook_subscriptions_delete_own" on public.webhook_subscriptions;
create policy "webhook_subscriptions_delete_own"
  on public.webhook_subscriptions
  for delete
  to authenticated
  using (auth.uid() = user_id);

drop policy if exists "webhook_deliveries_select_own" on public.webhook_deliveries;
create policy "webhook_deliveries_select_own"
  on public.webhook_deliveries
  for select
  to authenticated
  using (auth.uid() = user_id);

drop policy if exists "webhook_deliveries_insert_own" on public.webhook_deliveries;
create policy "webhook_deliveries_insert_own"
  on public.webhook_deliveries
  for insert
  to authenticated
  with check (auth.uid() = user_id);

drop policy if exists "webhook_deliveries_update_own" on public.webhook_deliveries;
create policy "webhook_deliveries_update_own"
  on public.webhook_deliveries
  for update
  to authenticated
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);
