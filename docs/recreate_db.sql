-- ==========================================
-- 1. Create Tables
-- ==========================================

CREATE TABLE "public"."agents" (
    "id" bigint NOT NULL DEFAULT nextval('agents_id_seq'::regclass),
    "organization_id" bigint NOT NULL,
    "team_id" bigint NOT NULL,
    "name" text NOT NULL,
    "description" text,
    "status" text NOT NULL DEFAULT 'active'::text,
    "is_active" boolean NOT NULL DEFAULT true,
    "created_by" uuid NOT NULL,
    "created_at" timestamp with time zone NOT NULL DEFAULT now(),
    "updated_at" timestamp with time zone NOT NULL DEFAULT now()
);

CREATE TABLE "public"."api_keys" (
    "id" bigint NOT NULL DEFAULT nextval('api_keys_id_seq'::regclass),
    "user_id" uuid NOT NULL,
    "name" text NOT NULL DEFAULT 'default'::text,
    "key_prefix" text NOT NULL,
    "key_hash" text NOT NULL,
    "is_active" boolean NOT NULL DEFAULT true,
    "last_used_at" timestamp with time zone,
    "revoked_at" timestamp with time zone,
    "created_at" timestamp with time zone NOT NULL DEFAULT now(),
    "allowed_tools" ARRAY,
    "policy_json" jsonb,
    "issued_by" text,
    "memo" text,
    "tags" ARRAY,
    "rotated_from" bigint,
    "team_id" bigint
);

CREATE TABLE "public"."audit_settings" (
    "id" bigint NOT NULL DEFAULT nextval('audit_settings_id_seq'::regclass),
    "user_id" uuid NOT NULL,
    "retention_days" integer NOT NULL DEFAULT 90,
    "export_enabled" boolean NOT NULL DEFAULT true,
    "masking_policy" jsonb NOT NULL DEFAULT '{}'::jsonb,
    "updated_at" timestamp with time zone NOT NULL DEFAULT now()
);

CREATE TABLE "public"."connector_job_runs" (
    "id" bigint NOT NULL DEFAULT nextval('connector_job_runs_id_seq'::regclass),
    "user_id" uuid NOT NULL,
    "provider" text NOT NULL,
    "job_type" text NOT NULL,
    "external_job_id" text,
    "resource_id" text,
    "resource_title" text,
    "status" text NOT NULL,
    "request_payload" jsonb,
    "result_payload" jsonb,
    "download_urls" ARRAY,
    "error_message" text,
    "created_at" timestamp with time zone NOT NULL DEFAULT now(),
    "updated_at" timestamp with time zone NOT NULL DEFAULT now()
);

CREATE TABLE "public"."incident_banner_revisions" (
    "id" bigint NOT NULL DEFAULT nextval('incident_banner_revisions_id_seq'::regclass),
    "user_id" uuid NOT NULL,
    "enabled" boolean NOT NULL DEFAULT false,
    "message" text,
    "severity" text NOT NULL DEFAULT 'info'::text,
    "starts_at" timestamp with time zone,
    "ends_at" timestamp with time zone,
    "status" text NOT NULL DEFAULT 'pending'::text,
    "requested_by" uuid NOT NULL,
    "approved_by" uuid,
    "approved_at" timestamp with time zone,
    "created_at" timestamp with time zone NOT NULL DEFAULT now(),
    "updated_at" timestamp with time zone NOT NULL DEFAULT now(),
    "organization_id" bigint
);

CREATE TABLE "public"."incident_banners" (
    "id" bigint NOT NULL DEFAULT nextval('incident_banners_id_seq'::regclass),
    "user_id" uuid NOT NULL,
    "enabled" boolean NOT NULL DEFAULT false,
    "message" text,
    "severity" text NOT NULL DEFAULT 'info'::text,
    "starts_at" timestamp with time zone,
    "ends_at" timestamp with time zone,
    "updated_at" timestamp with time zone NOT NULL DEFAULT now(),
    "organization_id" bigint
);

CREATE TABLE "public"."oauth_pending_states" (
    "state" text NOT NULL,
    "user_id" uuid NOT NULL,
    "provider" text NOT NULL,
    "code_verifier" text NOT NULL,
    "created_at" timestamp with time zone NOT NULL DEFAULT now(),
    "expires_at" timestamp with time zone NOT NULL
);

CREATE TABLE "public"."oauth_tokens" (
    "id" bigint NOT NULL DEFAULT nextval('oauth_tokens_id_seq'::regclass),
    "user_id" uuid NOT NULL,
    "provider" text NOT NULL,
    "access_token_encrypted" text NOT NULL,
    "workspace_id" text,
    "workspace_name" text,
    "created_at" timestamp with time zone NOT NULL DEFAULT now(),
    "updated_at" timestamp with time zone NOT NULL DEFAULT now(),
    "granted_scopes" ARRAY,
    "refresh_token_encrypted" text,
    "token_expires_at" timestamp with time zone,
    "provider_account_id" text,
    "provider_team_id" text,
    "provider_metadata" jsonb
);

CREATE TABLE "public"."org_invites" (
    "id" bigint NOT NULL DEFAULT nextval('org_invites_id_seq'::regclass),
    "organization_id" bigint NOT NULL,
    "token" text NOT NULL,
    "invited_email" text,
    "role" text NOT NULL DEFAULT 'member'::text,
    "invited_by" uuid NOT NULL,
    "expires_at" timestamp with time zone NOT NULL,
    "accepted_by" uuid,
    "accepted_at" timestamp with time zone,
    "revoked_at" timestamp with time zone,
    "created_at" timestamp with time zone NOT NULL DEFAULT now()
);

CREATE TABLE "public"."org_memberships" (
    "id" bigint NOT NULL DEFAULT nextval('org_memberships_id_seq'::regclass),
    "organization_id" bigint NOT NULL,
    "user_id" uuid NOT NULL,
    "role" text NOT NULL DEFAULT 'member'::text,
    "created_at" timestamp with time zone NOT NULL DEFAULT now()
);

CREATE TABLE "public"."org_oauth_policies" (
    "id" bigint NOT NULL DEFAULT nextval('org_oauth_policies_id_seq'::regclass),
    "organization_id" bigint NOT NULL,
    "policy_json" jsonb NOT NULL DEFAULT '{}'::jsonb,
    "version" integer NOT NULL DEFAULT 1,
    "updated_by" uuid,
    "created_at" timestamp with time zone NOT NULL DEFAULT now(),
    "updated_at" timestamp with time zone NOT NULL DEFAULT now()
);

CREATE TABLE "public"."org_policies" (
    "id" bigint NOT NULL DEFAULT nextval('org_policies_id_seq'::regclass),
    "organization_id" bigint NOT NULL,
    "policy_json" jsonb NOT NULL DEFAULT '{}'::jsonb,
    "updated_by" uuid,
    "created_at" timestamp with time zone NOT NULL DEFAULT now(),
    "updated_at" timestamp with time zone NOT NULL DEFAULT now()
);

CREATE TABLE "public"."org_role_change_requests" (
    "id" bigint NOT NULL DEFAULT nextval('org_role_change_requests_id_seq'::regclass),
    "organization_id" bigint NOT NULL,
    "target_user_id" uuid NOT NULL,
    "requested_role" text NOT NULL,
    "reason" text,
    "status" text NOT NULL DEFAULT 'pending'::text,
    "requested_by" uuid NOT NULL,
    "reviewed_by" uuid,
    "reviewed_at" timestamp with time zone,
    "created_at" timestamp with time zone NOT NULL DEFAULT now(),
    "updated_at" timestamp with time zone NOT NULL DEFAULT now(),
    "request_type" text NOT NULL DEFAULT 'change_request'::text,
    "review_reason" text,
    "cancelled_by" uuid,
    "cancelled_at" timestamp with time zone
);

CREATE TABLE "public"."organizations" (
    "id" bigint NOT NULL DEFAULT nextval('organizations_id_seq'::regclass),
    "name" text NOT NULL,
    "created_by" uuid NOT NULL,
    "created_at" timestamp with time zone NOT NULL DEFAULT now(),
    "updated_at" timestamp with time zone NOT NULL DEFAULT now()
);

CREATE TABLE "public"."policy_revisions" (
    "id" bigint NOT NULL DEFAULT nextval('policy_revisions_id_seq'::regclass),
    "team_id" bigint NOT NULL,
    "source" text NOT NULL DEFAULT 'team_policy_update'::text,
    "policy_json" jsonb NOT NULL DEFAULT '{}'::jsonb,
    "created_by" uuid,
    "created_at" timestamp with time zone NOT NULL DEFAULT now()
);

CREATE TABLE "public"."team_memberships" (
    "id" bigint NOT NULL DEFAULT nextval('team_memberships_id_seq'::regclass),
    "team_id" bigint NOT NULL,
    "user_id" uuid NOT NULL,
    "role" text NOT NULL DEFAULT 'member'::text,
    "created_at" timestamp with time zone NOT NULL DEFAULT now()
);

CREATE TABLE "public"."team_policies" (
    "id" bigint NOT NULL DEFAULT nextval('team_policies_id_seq'::regclass),
    "team_id" bigint NOT NULL,
    "policy_json" jsonb NOT NULL DEFAULT '{}'::jsonb,
    "created_at" timestamp with time zone NOT NULL DEFAULT now(),
    "updated_at" timestamp with time zone NOT NULL DEFAULT now()
);

CREATE TABLE "public"."teams" (
    "id" bigint NOT NULL DEFAULT nextval('teams_id_seq'::regclass),
    "user_id" uuid NOT NULL,
    "name" text NOT NULL,
    "description" text,
    "is_active" boolean NOT NULL DEFAULT true,
    "created_at" timestamp with time zone NOT NULL DEFAULT now(),
    "updated_at" timestamp with time zone NOT NULL DEFAULT now(),
    "organization_id" bigint
);

CREATE TABLE "public"."tool_calls" (
    "id" bigint NOT NULL DEFAULT nextval('tool_calls_id_seq'::regclass),
    "request_id" text,
    "user_id" uuid NOT NULL,
    "api_key_id" bigint NOT NULL,
    "tool_name" text NOT NULL,
    "status" text NOT NULL,
    "error_code" text,
    "latency_ms" integer NOT NULL DEFAULT 0,
    "created_at" timestamp with time zone NOT NULL DEFAULT now(),
    "trace_id" text,
    "connector" text,
    "request_payload" jsonb,
    "resolved_payload" jsonb,
    "risk_result" jsonb,
    "upstream_status" integer,
    "retry_count" integer NOT NULL DEFAULT 0,
    "backoff_ms" integer NOT NULL DEFAULT 0,
    "masked_fields" ARRAY,
    "agent_id" bigint
);

CREATE TABLE "public"."user_security_settings" (
    "user_id" uuid NOT NULL,
    "mfa_enabled" boolean NOT NULL DEFAULT false,
    "session_timeout_minutes" integer NOT NULL DEFAULT 60,
    "password_rotation_days" integer NOT NULL DEFAULT 90,
    "updated_at" timestamp with time zone NOT NULL DEFAULT now()
);

CREATE TABLE "public"."users" (
    "id" uuid NOT NULL,
    "email" text,
    "full_name" text,
    "avatar_url" text,
    "created_at" timestamp with time zone NOT NULL DEFAULT now(),
    "updated_at" timestamp with time zone NOT NULL DEFAULT now(),
    "telegram_chat_id" bigint,
    "telegram_username" text,
    "timezone" text
);

CREATE TABLE "public"."webhook_deliveries" (
    "id" bigint NOT NULL DEFAULT nextval('webhook_deliveries_id_seq'::regclass),
    "subscription_id" bigint NOT NULL,
    "user_id" uuid NOT NULL,
    "event_type" text NOT NULL,
    "payload" jsonb NOT NULL DEFAULT '{}'::jsonb,
    "status" text NOT NULL DEFAULT 'pending'::text,
    "http_status" integer,
    "error_message" text,
    "retry_count" integer NOT NULL DEFAULT 0,
    "next_retry_at" timestamp with time zone,
    "delivered_at" timestamp with time zone,
    "created_at" timestamp with time zone NOT NULL DEFAULT now()
);

CREATE TABLE "public"."webhook_subscriptions" (
    "id" bigint NOT NULL DEFAULT nextval('webhook_subscriptions_id_seq'::regclass),
    "user_id" uuid NOT NULL,
    "name" text NOT NULL,
    "endpoint_url" text NOT NULL,
    "secret" text,
    "event_types" ARRAY NOT NULL DEFAULT '{}'::text[],
    "is_active" boolean NOT NULL DEFAULT true,
    "last_delivery_at" timestamp with time zone,
    "created_at" timestamp with time zone NOT NULL DEFAULT now(),
    "updated_at" timestamp with time zone NOT NULL DEFAULT now()
);

-- ==========================================
-- 2. Create Indexes
-- ==========================================

CREATE UNIQUE INDEX users_pkey ON public.users USING btree (id);
CREATE UNIQUE INDEX users_telegram_chat_id_key ON public.users USING btree (telegram_chat_id) WHERE (telegram_chat_id IS NOT NULL);

CREATE UNIQUE INDEX teams_pkey ON public.teams USING btree (id);
CREATE INDEX idx_teams_user_id_created_at ON public.teams USING btree (user_id, created_at DESC);
CREATE INDEX idx_teams_organization_id_created_at ON public.teams USING btree (organization_id, created_at DESC);

CREATE UNIQUE INDEX team_memberships_pkey ON public.team_memberships USING btree (id);
CREATE UNIQUE INDEX team_memberships_team_id_user_id_key ON public.team_memberships USING btree (team_id, user_id);
CREATE INDEX idx_team_memberships_team_id ON public.team_memberships USING btree (team_id);

CREATE UNIQUE INDEX tool_calls_pkey ON public.tool_calls USING btree (id);
CREATE INDEX idx_tool_calls_api_key_created_at ON public.tool_calls USING btree (api_key_id, created_at DESC);
CREATE INDEX idx_tool_calls_user_created_at ON public.tool_calls USING btree (user_id, created_at DESC);
CREATE INDEX idx_tool_calls_trace_id ON public.tool_calls USING btree (trace_id);
CREATE INDEX idx_tool_calls_connector_created_at ON public.tool_calls USING btree (connector, created_at DESC);
CREATE INDEX idx_tool_calls_agent_id_created_at ON public.tool_calls USING btree (agent_id, created_at DESC);

CREATE UNIQUE INDEX team_policies_pkey ON public.team_policies USING btree (id);
CREATE UNIQUE INDEX team_policies_team_id_key ON public.team_policies USING btree (team_id);
CREATE INDEX idx_team_policies_policy_json_gin ON public.team_policies USING gin (policy_json);

CREATE UNIQUE INDEX api_keys_pkey ON public.api_keys USING btree (id);
CREATE UNIQUE INDEX api_keys_key_hash_key ON public.api_keys USING btree (key_hash);
CREATE INDEX idx_api_keys_user_id_created_at ON public.api_keys USING btree (user_id, created_at DESC);
CREATE INDEX idx_api_keys_policy_json_gin ON public.api_keys USING gin (policy_json);
CREATE INDEX idx_api_keys_rotated_from ON public.api_keys USING btree (rotated_from);
CREATE INDEX idx_api_keys_team_id ON public.api_keys USING btree (team_id);

CREATE UNIQUE INDEX audit_settings_pkey ON public.audit_settings USING btree (id);
CREATE UNIQUE INDEX audit_settings_user_id_key ON public.audit_settings USING btree (user_id);
CREATE INDEX idx_audit_settings_user_id ON public.audit_settings USING btree (user_id);

CREATE UNIQUE INDEX policy_revisions_pkey ON public.policy_revisions USING btree (id);
CREATE INDEX idx_policy_revisions_team_id_created_at ON public.policy_revisions USING btree (team_id, created_at DESC);

CREATE UNIQUE INDEX webhook_subscriptions_pkey ON public.webhook_subscriptions USING btree (id);
CREATE INDEX idx_webhook_subscriptions_user_id_created_at ON public.webhook_subscriptions USING btree (user_id, created_at DESC);

CREATE UNIQUE INDEX webhook_deliveries_pkey ON public.webhook_deliveries USING btree (id);
CREATE INDEX idx_webhook_deliveries_user_id_created_at ON public.webhook_deliveries USING btree (user_id, created_at DESC);
CREATE INDEX idx_webhook_deliveries_subscription_id_created_at ON public.webhook_deliveries USING btree (subscription_id, created_at DESC);

CREATE UNIQUE INDEX incident_banners_pkey ON public.incident_banners USING btree (id);
CREATE INDEX idx_incident_banners_user_id ON public.incident_banners USING btree (user_id);
CREATE UNIQUE INDEX idx_incident_banners_organization_id_unique ON public.incident_banners USING btree (organization_id) WHERE (organization_id IS NOT NULL);

CREATE UNIQUE INDEX organizations_pkey ON public.organizations USING btree (id);
CREATE INDEX idx_organizations_created_by ON public.organizations USING btree (created_by);

CREATE UNIQUE INDEX org_memberships_pkey ON public.org_memberships USING btree (id);
CREATE UNIQUE INDEX org_memberships_organization_id_user_id_key ON public.org_memberships USING btree (organization_id, user_id);
CREATE INDEX idx_org_memberships_user_id ON public.org_memberships USING btree (user_id);
CREATE INDEX idx_org_memberships_organization_id ON public.org_memberships USING btree (organization_id);

CREATE UNIQUE INDEX org_invites_pkey ON public.org_invites USING btree (id);
CREATE UNIQUE INDEX org_invites_token_key ON public.org_invites USING btree (token);
CREATE INDEX idx_org_invites_organization_id ON public.org_invites USING btree (organization_id);
CREATE INDEX idx_org_invites_token ON public.org_invites USING btree (token);

CREATE UNIQUE INDEX incident_banner_revisions_pkey ON public.incident_banner_revisions USING btree (id);
CREATE INDEX idx_incident_banner_revisions_user_id_created_at ON public.incident_banner_revisions USING btree (user_id, created_at DESC);
CREATE INDEX idx_incident_banner_revisions_organization_id_created_at ON public.incident_banner_revisions USING btree (organization_id, created_at DESC);

CREATE UNIQUE INDEX agents_pkey ON public.agents USING btree (id);
CREATE UNIQUE INDEX agents_team_id_name_key ON public.agents USING btree (team_id, name);
CREATE INDEX idx_agents_org_team_created_at ON public.agents USING btree (organization_id, team_id, created_at DESC);
CREATE INDEX idx_agents_team_id ON public.agents USING btree (team_id);

CREATE UNIQUE INDEX user_security_settings_pkey ON public.user_security_settings USING btree (user_id);

CREATE UNIQUE INDEX org_policies_pkey ON public.org_policies USING btree (id);
CREATE UNIQUE INDEX org_policies_organization_id_key ON public.org_policies USING btree (organization_id);
CREATE INDEX idx_org_policies_org_id ON public.org_policies USING btree (organization_id);

CREATE UNIQUE INDEX org_role_change_requests_pkey ON public.org_role_change_requests USING btree (id);
CREATE INDEX idx_org_role_change_requests_organization_id ON public.org_role_change_requests USING btree (organization_id, created_at DESC);
CREATE INDEX idx_org_role_change_requests_target_user_id ON public.org_role_change_requests USING btree (target_user_id);
CREATE INDEX idx_org_role_change_requests_requested_by ON public.org_role_change_requests USING btree (requested_by, created_at DESC);
CREATE INDEX idx_org_role_change_requests_status ON public.org_role_change_requests USING btree (status, created_at DESC);

CREATE UNIQUE INDEX org_oauth_policies_pkey ON public.org_oauth_policies USING btree (id);
CREATE UNIQUE INDEX org_oauth_policies_organization_id_key ON public.org_oauth_policies USING btree (organization_id);
CREATE INDEX idx_org_oauth_policies_org_id ON public.org_oauth_policies USING btree (organization_id);

CREATE UNIQUE INDEX oauth_tokens_pkey ON public.oauth_tokens USING btree (id);
CREATE UNIQUE INDEX oauth_tokens_user_id_provider_key ON public.oauth_tokens USING btree (user_id, provider);

CREATE UNIQUE INDEX oauth_pending_states_pkey ON public.oauth_pending_states USING btree (state);
CREATE INDEX oauth_pending_states_user_provider_idx ON public.oauth_pending_states USING btree (user_id, provider);
CREATE INDEX oauth_pending_states_expires_at_idx ON public.oauth_pending_states USING btree (expires_at);

CREATE UNIQUE INDEX connector_job_runs_pkey ON public.connector_job_runs USING btree (id);
CREATE UNIQUE INDEX connector_job_runs_provider_job_type_external_job_id_key ON public.connector_job_runs USING btree (provider, job_type, external_job_id);
CREATE INDEX idx_connector_job_runs_user_updated_at ON public.connector_job_runs USING btree (user_id, updated_at DESC);
CREATE INDEX idx_connector_job_runs_provider_job_type ON public.connector_job_runs USING btree (provider, job_type, updated_at DESC);

-- ==========================================
-- 3. Create Foreign Keys
-- ==========================================

ALTER TABLE "public"."team_policies" ADD CONSTRAINT "fk_team_policies_team_id" FOREIGN KEY ("team_id") REFERENCES "public"."teams"("id");
ALTER TABLE "public"."policy_revisions" ADD CONSTRAINT "fk_policy_revisions_team_id" FOREIGN KEY ("team_id") REFERENCES "public"."teams"("id");
ALTER TABLE "public"."api_keys" ADD CONSTRAINT "fk_api_keys_team_id" FOREIGN KEY ("team_id") REFERENCES "public"."teams"("id");
ALTER TABLE "public"."tool_calls" ADD CONSTRAINT "fk_tool_calls_api_key_id" FOREIGN KEY ("api_key_id") REFERENCES "public"."api_keys"("id");
ALTER TABLE "public"."api_keys" ADD CONSTRAINT "fk_api_keys_rotated_from" FOREIGN KEY ("rotated_from") REFERENCES "public"."api_keys"("id");
ALTER TABLE "public"."team_memberships" ADD CONSTRAINT "fk_team_memberships_team_id" FOREIGN KEY ("team_id") REFERENCES "public"."teams"("id");
ALTER TABLE "public"."webhook_deliveries" ADD CONSTRAINT "fk_webhook_deliveries_subscription_id" FOREIGN KEY ("subscription_id") REFERENCES "public"."webhook_subscriptions"("id");
ALTER TABLE "public"."org_memberships" ADD CONSTRAINT "fk_org_memberships_organization_id" FOREIGN KEY ("organization_id") REFERENCES "public"."organizations"("id");
ALTER TABLE "public"."org_invites" ADD CONSTRAINT "fk_org_invites_organization_id" FOREIGN KEY ("organization_id") REFERENCES "public"."organizations"("id");
ALTER TABLE "public"."org_invites" ADD CONSTRAINT "fk_org_invites_invited_by" FOREIGN KEY ("invited_by") REFERENCES "public"."users"("id");
ALTER TABLE "public"."org_invites" ADD CONSTRAINT "fk_org_invites_accepted_by" FOREIGN KEY ("accepted_by") REFERENCES "public"."users"("id");
ALTER TABLE "public"."org_role_change_requests" ADD CONSTRAINT "fk_org_role_change_requests_organization_id" FOREIGN KEY ("organization_id") REFERENCES "public"."organizations"("id");
ALTER TABLE "public"."org_role_change_requests" ADD CONSTRAINT "fk_org_role_change_requests_target_user_id" FOREIGN KEY ("target_user_id") REFERENCES "public"."users"("id");
ALTER TABLE "public"."org_role_change_requests" ADD CONSTRAINT "fk_org_role_change_requests_requested_by" FOREIGN KEY ("requested_by") REFERENCES "public"."users"("id");
ALTER TABLE "public"."org_role_change_requests" ADD CONSTRAINT "fk_org_role_change_requests_reviewed_by" FOREIGN KEY ("reviewed_by") REFERENCES "public"."users"("id");
ALTER TABLE "public"."incident_banner_revisions" ADD CONSTRAINT "fk_incident_banner_revisions_user_id" FOREIGN KEY ("user_id") REFERENCES "public"."users"("id");
ALTER TABLE "public"."incident_banner_revisions" ADD CONSTRAINT "fk_incident_banner_revisions_requested_by" FOREIGN KEY ("requested_by") REFERENCES "public"."users"("id");
ALTER TABLE "public"."incident_banner_revisions" ADD CONSTRAINT "fk_incident_banner_revisions_approved_by" FOREIGN KEY ("approved_by") REFERENCES "public"."users"("id");
ALTER TABLE "public"."teams" ADD CONSTRAINT "fk_teams_organization_id" FOREIGN KEY ("organization_id") REFERENCES "public"."organizations"("id");
ALTER TABLE "public"."agents" ADD CONSTRAINT "fk_agents_organization_id" FOREIGN KEY ("organization_id") REFERENCES "public"."organizations"("id");
ALTER TABLE "public"."agents" ADD CONSTRAINT "fk_agents_team_id" FOREIGN KEY ("team_id") REFERENCES "public"."teams"("id");
ALTER TABLE "public"."tool_calls" ADD CONSTRAINT "fk_tool_calls_agent_id" FOREIGN KEY ("agent_id") REFERENCES "public"."agents"("id");
ALTER TABLE "public"."org_policies" ADD CONSTRAINT "fk_org_policies_organization_id" FOREIGN KEY ("organization_id") REFERENCES "public"."organizations"("id");
ALTER TABLE "public"."org_policies" ADD CONSTRAINT "fk_org_policies_updated_by" FOREIGN KEY ("updated_by") REFERENCES "public"."users"("id");
ALTER TABLE "public"."org_oauth_policies" ADD CONSTRAINT "fk_org_oauth_policies_organization_id" FOREIGN KEY ("organization_id") REFERENCES "public"."organizations"("id");
ALTER TABLE "public"."org_oauth_policies" ADD CONSTRAINT "fk_org_oauth_policies_updated_by" FOREIGN KEY ("updated_by") REFERENCES "public"."users"("id");
ALTER TABLE "public"."org_role_change_requests" ADD CONSTRAINT "fk_org_role_change_requests_cancelled_by" FOREIGN KEY ("cancelled_by") REFERENCES "public"."users"("id");
ALTER TABLE "public"."user_security_settings" ADD CONSTRAINT "fk_user_security_settings_user_id" FOREIGN KEY ("user_id") REFERENCES "public"."users"("id");
ALTER TABLE "public"."incident_banners" ADD CONSTRAINT "fk_incident_banners_organization_id" FOREIGN KEY ("organization_id") REFERENCES "public"."organizations"("id");
ALTER TABLE "public"."incident_banner_revisions" ADD CONSTRAINT "fk_incident_banner_revisions_organization_id" FOREIGN KEY ("organization_id") REFERENCES "public"."organizations"("id");

-- ==========================================
-- 4. Create Policies
-- ==========================================

CREATE POLICY "users_select_own" ON "public"."users" AS PERMISSIVE FOR SELECT TO authenticated USING ((auth.uid() = id)) ;
CREATE POLICY "users_insert_own" ON "public"."users" AS PERMISSIVE FOR INSERT TO authenticated WITH CHECK ((auth.uid() = id)) ;
CREATE POLICY "users_update_own" ON "public"."users" AS PERMISSIVE FOR UPDATE TO authenticated USING ((auth.uid() = id)) WITH CHECK ((auth.uid() = id)) ;
CREATE POLICY "oauth_tokens_select_own" ON "public"."oauth_tokens" AS PERMISSIVE FOR SELECT TO authenticated USING ((auth.uid() = user_id)) ;
CREATE POLICY "api_keys_select_own" ON "public"."api_keys" AS PERMISSIVE FOR SELECT TO authenticated USING ((auth.uid() = user_id)) ;
CREATE POLICY "api_keys_insert_own" ON "public"."api_keys" AS PERMISSIVE FOR INSERT TO authenticated WITH CHECK ((auth.uid() = user_id)) ;
CREATE POLICY "api_keys_update_own" ON "public"."api_keys" AS PERMISSIVE FOR UPDATE TO authenticated USING ((auth.uid() = user_id)) WITH CHECK ((auth.uid() = user_id)) ;
CREATE POLICY "tool_calls_select_own" ON "public"."tool_calls" AS PERMISSIVE FOR SELECT TO authenticated USING ((auth.uid() = user_id)) ;
CREATE POLICY "teams_select_own" ON "public"."teams" AS PERMISSIVE FOR SELECT TO authenticated USING ((auth.uid() = user_id)) ;
CREATE POLICY "teams_insert_own" ON "public"."teams" AS PERMISSIVE FOR INSERT TO authenticated WITH CHECK ((auth.uid() = user_id)) ;
CREATE POLICY "teams_update_own" ON "public"."teams" AS PERMISSIVE FOR UPDATE TO authenticated USING ((auth.uid() = user_id)) WITH CHECK ((auth.uid() = user_id)) ;
CREATE POLICY "webhook_subscriptions_delete_own" ON "public"."webhook_subscriptions" AS PERMISSIVE FOR DELETE TO authenticated USING ((auth.uid() = user_id)) ;
CREATE POLICY "team_memberships_select_team_owner_or_self" ON "public"."team_memberships" AS PERMISSIVE FOR SELECT TO authenticated USING (((auth.uid() = user_id) OR (EXISTS ( SELECT 1
   FROM teams t
  WHERE ((t.id = team_memberships.team_id) AND (t.user_id = auth.uid())))))) ;
CREATE POLICY "team_memberships_insert_team_owner" ON "public"."team_memberships" AS PERMISSIVE FOR INSERT TO authenticated WITH CHECK ((EXISTS ( SELECT 1
   FROM teams t
  WHERE ((t.id = team_memberships.team_id) AND (t.user_id = auth.uid()))))) ;
CREATE POLICY "team_memberships_update_team_owner" ON "public"."team_memberships" AS PERMISSIVE FOR UPDATE TO authenticated USING ((EXISTS ( SELECT 1
   FROM teams t
  WHERE ((t.id = team_memberships.team_id) AND (t.user_id = auth.uid()))))) WITH CHECK ((EXISTS ( SELECT 1
   FROM teams t
  WHERE ((t.id = team_memberships.team_id) AND (t.user_id = auth.uid()))))) ;
CREATE POLICY "team_memberships_delete_team_owner" ON "public"."team_memberships" AS PERMISSIVE FOR DELETE TO authenticated USING ((EXISTS ( SELECT 1
   FROM teams t
  WHERE ((t.id = team_memberships.team_id) AND (t.user_id = auth.uid()))))) ;
CREATE POLICY "team_policies_select_team_owner" ON "public"."team_policies" AS PERMISSIVE FOR SELECT TO authenticated USING ((EXISTS ( SELECT 1
   FROM teams t
  WHERE ((t.id = team_policies.team_id) AND (t.user_id = auth.uid()))))) ;
CREATE POLICY "webhook_deliveries_select_own" ON "public"."webhook_deliveries" AS PERMISSIVE FOR SELECT TO authenticated USING ((auth.uid() = user_id)) ;
CREATE POLICY "team_policies_insert_team_owner" ON "public"."team_policies" AS PERMISSIVE FOR INSERT TO authenticated WITH CHECK ((EXISTS ( SELECT 1
   FROM teams t
  WHERE ((t.id = team_policies.team_id) AND (t.user_id = auth.uid()))))) ;
CREATE POLICY "team_policies_update_team_owner" ON "public"."team_policies" AS PERMISSIVE FOR UPDATE TO authenticated USING ((EXISTS ( SELECT 1
   FROM teams t
  WHERE ((t.id = team_policies.team_id) AND (t.user_id = auth.uid()))))) WITH CHECK ((EXISTS ( SELECT 1
   FROM teams t
  WHERE ((t.id = team_policies.team_id) AND (t.user_id = auth.uid()))))) ;
CREATE POLICY "policy_revisions_select_team_owner" ON "public"."policy_revisions" AS PERMISSIVE FOR SELECT TO authenticated USING ((EXISTS ( SELECT 1
   FROM teams t
  WHERE ((t.id = policy_revisions.team_id) AND (t.user_id = auth.uid()))))) ;
CREATE POLICY "policy_revisions_insert_team_owner" ON "public"."policy_revisions" AS PERMISSIVE FOR INSERT TO authenticated WITH CHECK ((EXISTS ( SELECT 1
   FROM teams t
  WHERE ((t.id = policy_revisions.team_id) AND (t.user_id = auth.uid()))))) ;
CREATE POLICY "webhook_subscriptions_select_own" ON "public"."webhook_subscriptions" AS PERMISSIVE FOR SELECT TO authenticated USING ((auth.uid() = user_id)) ;
CREATE POLICY "webhook_subscriptions_insert_own" ON "public"."webhook_subscriptions" AS PERMISSIVE FOR INSERT TO authenticated WITH CHECK ((auth.uid() = user_id)) ;
CREATE POLICY "webhook_subscriptions_update_own" ON "public"."webhook_subscriptions" AS PERMISSIVE FOR UPDATE TO authenticated USING ((auth.uid() = user_id)) WITH CHECK ((auth.uid() = user_id)) ;
CREATE POLICY "webhook_deliveries_insert_own" ON "public"."webhook_deliveries" AS PERMISSIVE FOR INSERT TO authenticated WITH CHECK ((auth.uid() = user_id)) ;
CREATE POLICY "webhook_deliveries_update_own" ON "public"."webhook_deliveries" AS PERMISSIVE FOR UPDATE TO authenticated USING ((auth.uid() = user_id)) WITH CHECK ((auth.uid() = user_id)) ;
CREATE POLICY "audit_settings_select_own" ON "public"."audit_settings" AS PERMISSIVE FOR SELECT TO authenticated USING ((auth.uid() = user_id)) ;
CREATE POLICY "audit_settings_insert_own" ON "public"."audit_settings" AS PERMISSIVE FOR INSERT TO authenticated WITH CHECK ((auth.uid() = user_id)) ;
CREATE POLICY "audit_settings_update_own" ON "public"."audit_settings" AS PERMISSIVE FOR UPDATE TO authenticated USING ((auth.uid() = user_id)) WITH CHECK ((auth.uid() = user_id)) ;
CREATE POLICY "incident_banners_select_own" ON "public"."incident_banners" AS PERMISSIVE FOR SELECT TO authenticated USING ((auth.uid() = user_id)) ;
CREATE POLICY "incident_banners_insert_own" ON "public"."incident_banners" AS PERMISSIVE FOR INSERT TO authenticated WITH CHECK ((auth.uid() = user_id)) ;
CREATE POLICY "incident_banners_update_own" ON "public"."incident_banners" AS PERMISSIVE FOR UPDATE TO authenticated USING ((auth.uid() = user_id)) WITH CHECK ((auth.uid() = user_id)) ;
CREATE POLICY "organizations_select_member" ON "public"."organizations" AS PERMISSIVE FOR SELECT TO authenticated USING ((EXISTS ( SELECT 1
   FROM org_memberships m
  WHERE ((m.organization_id = organizations.id) AND (m.user_id = auth.uid()))))) ;
CREATE POLICY "organizations_insert_owner" ON "public"."organizations" AS PERMISSIVE FOR INSERT TO authenticated WITH CHECK ((created_by = auth.uid())) ;
CREATE POLICY "organizations_update_owner" ON "public"."organizations" AS PERMISSIVE FOR UPDATE TO authenticated USING ((created_by = auth.uid())) WITH CHECK ((created_by = auth.uid())) ;
CREATE POLICY "org_memberships_select_member" ON "public"."org_memberships" AS PERMISSIVE FOR SELECT TO authenticated USING ((EXISTS ( SELECT 1
   FROM org_memberships mine
  WHERE ((mine.organization_id = org_memberships.organization_id) AND (mine.user_id = auth.uid()))))) ;
CREATE POLICY "org_memberships_insert_owner" ON "public"."org_memberships" AS PERMISSIVE FOR INSERT TO authenticated WITH CHECK ((EXISTS ( SELECT 1
   FROM organizations o
  WHERE ((o.id = org_memberships.organization_id) AND (o.created_by = auth.uid()))))) ;
CREATE POLICY "org_memberships_update_owner" ON "public"."org_memberships" AS PERMISSIVE FOR UPDATE TO authenticated USING ((EXISTS ( SELECT 1
   FROM organizations o
  WHERE ((o.id = org_memberships.organization_id) AND (o.created_by = auth.uid()))))) WITH CHECK ((EXISTS ( SELECT 1
   FROM organizations o
  WHERE ((o.id = org_memberships.organization_id) AND (o.created_by = auth.uid()))))) ;
CREATE POLICY "org_memberships_delete_owner" ON "public"."org_memberships" AS PERMISSIVE FOR DELETE TO authenticated USING ((EXISTS ( SELECT 1
   FROM organizations o
  WHERE ((o.id = org_memberships.organization_id) AND (o.created_by = auth.uid()))))) ;
CREATE POLICY "org_invites_select_org_member" ON "public"."org_invites" AS PERMISSIVE FOR SELECT TO public USING ((EXISTS ( SELECT 1
   FROM org_memberships m
  WHERE ((m.organization_id = org_invites.organization_id) AND (m.user_id = auth.uid()))))) ;
CREATE POLICY "org_invites_insert_org_owner" ON "public"."org_invites" AS PERMISSIVE FOR INSERT TO public WITH CHECK ((EXISTS ( SELECT 1
   FROM organizations o
  WHERE ((o.id = org_invites.organization_id) AND (o.created_by = auth.uid()))))) ;
CREATE POLICY "org_invites_update_org_owner" ON "public"."org_invites" AS PERMISSIVE FOR UPDATE TO public USING ((EXISTS ( SELECT 1
   FROM organizations o
  WHERE ((o.id = org_invites.organization_id) AND (o.created_by = auth.uid()))))) WITH CHECK ((EXISTS ( SELECT 1
   FROM organizations o
  WHERE ((o.id = org_invites.organization_id) AND (o.created_by = auth.uid()))))) ;
CREATE POLICY "org_role_change_requests_select_org_member" ON "public"."org_role_change_requests" AS PERMISSIVE FOR SELECT TO public USING ((EXISTS ( SELECT 1
   FROM org_memberships m
  WHERE ((m.organization_id = org_role_change_requests.organization_id) AND (m.user_id = auth.uid()))))) ;
CREATE POLICY "org_role_change_requests_insert_org_owner" ON "public"."org_role_change_requests" AS PERMISSIVE FOR INSERT TO public WITH CHECK ((EXISTS ( SELECT 1
   FROM organizations o
  WHERE ((o.id = org_role_change_requests.organization_id) AND (o.created_by = auth.uid()))))) ;
CREATE POLICY "org_role_change_requests_update_org_owner" ON "public"."org_role_change_requests" AS PERMISSIVE FOR UPDATE TO public USING ((EXISTS ( SELECT 1
   FROM organizations o
  WHERE ((o.id = org_role_change_requests.organization_id) AND (o.created_by = auth.uid()))))) WITH CHECK ((EXISTS ( SELECT 1
   FROM organizations o
  WHERE ((o.id = org_role_change_requests.organization_id) AND (o.created_by = auth.uid()))))) ;
CREATE POLICY "incident_banner_revisions_select_own" ON "public"."incident_banner_revisions" AS PERMISSIVE FOR SELECT TO public USING ((user_id = auth.uid())) ;
CREATE POLICY "incident_banner_revisions_insert_own" ON "public"."incident_banner_revisions" AS PERMISSIVE FOR INSERT TO public WITH CHECK (((user_id = auth.uid()) AND (requested_by = auth.uid()))) ;
CREATE POLICY "incident_banner_revisions_update_own" ON "public"."incident_banner_revisions" AS PERMISSIVE FOR UPDATE TO public USING ((user_id = auth.uid())) WITH CHECK ((user_id = auth.uid())) ;
CREATE POLICY "agents_select_member_scope" ON "public"."agents" AS PERMISSIVE FOR SELECT TO authenticated USING (((EXISTS ( SELECT 1
   FROM team_memberships tm
  WHERE ((tm.team_id = agents.team_id) AND (tm.user_id = auth.uid())))) OR (EXISTS ( SELECT 1
   FROM org_memberships om
  WHERE ((om.organization_id = agents.organization_id) AND (om.user_id = auth.uid()) AND (lower(COALESCE(om.role, 'member'::text)) = ANY (ARRAY['owner'::text, 'admin'::text]))))))) ;
CREATE POLICY "user_security_settings_update_own" ON "public"."user_security_settings" AS PERMISSIVE FOR UPDATE TO authenticated USING ((auth.uid() = user_id)) WITH CHECK ((auth.uid() = user_id)) ;
CREATE POLICY "user_security_settings_select_own" ON "public"."user_security_settings" AS PERMISSIVE FOR SELECT TO authenticated USING ((auth.uid() = user_id)) ;
CREATE POLICY "user_security_settings_insert_own" ON "public"."user_security_settings" AS PERMISSIVE FOR INSERT TO authenticated WITH CHECK ((auth.uid() = user_id)) ;
CREATE POLICY "org_policies_select_org_member" ON "public"."org_policies" AS PERMISSIVE FOR SELECT TO public USING ((EXISTS ( SELECT 1
   FROM org_memberships m
  WHERE ((m.organization_id = org_policies.organization_id) AND (m.user_id = auth.uid()))))) ;
CREATE POLICY "org_policies_upsert_org_owner" ON "public"."org_policies" AS PERMISSIVE FOR ALL TO public USING ((EXISTS ( SELECT 1
   FROM org_memberships m
  WHERE ((m.organization_id = org_policies.organization_id) AND (m.user_id = auth.uid()) AND (m.role = ANY (ARRAY['owner'::text, 'admin'::text])))))) WITH CHECK ((EXISTS ( SELECT 1
   FROM org_memberships m
  WHERE ((m.organization_id = org_policies.organization_id) AND (m.user_id = auth.uid()) AND (m.role = ANY (ARRAY['owner'::text, 'admin'::text])))))) ;
CREATE POLICY "org_oauth_policies_select_org_member" ON "public"."org_oauth_policies" AS PERMISSIVE FOR SELECT TO public USING ((EXISTS ( SELECT 1
   FROM org_memberships m
  WHERE ((m.organization_id = org_oauth_policies.organization_id) AND (m.user_id = auth.uid()))))) ;
CREATE POLICY "org_oauth_policies_upsert_org_owner" ON "public"."org_oauth_policies" AS PERMISSIVE FOR ALL TO public USING ((EXISTS ( SELECT 1
   FROM org_memberships m
  WHERE ((m.organization_id = org_oauth_policies.organization_id) AND (m.user_id = auth.uid()) AND (m.role = ANY (ARRAY['owner'::text, 'admin'::text])))))) WITH CHECK ((EXISTS ( SELECT 1
   FROM org_memberships m
  WHERE ((m.organization_id = org_oauth_policies.organization_id) AND (m.user_id = auth.uid()) AND (m.role = ANY (ARRAY['owner'::text, 'admin'::text])))))) ;
CREATE POLICY "connector_job_runs_select_own" ON "public"."connector_job_runs" AS PERMISSIVE FOR SELECT TO authenticated USING ((auth.uid() = user_id)) ;
CREATE POLICY "connector_job_runs_insert_own" ON "public"."connector_job_runs" AS PERMISSIVE FOR INSERT TO authenticated WITH CHECK ((auth.uid() = user_id)) ;
CREATE POLICY "connector_job_runs_update_own" ON "public"."connector_job_runs" AS PERMISSIVE FOR UPDATE TO authenticated USING ((auth.uid() = user_id)) WITH CHECK ((auth.uid() = user_id)) ;
