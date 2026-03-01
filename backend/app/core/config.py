from functools import lru_cache
from pydantic_settings import BaseSettings
from pydantic_settings import SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    supabase_url: str
    supabase_service_role_key: str

    notion_client_id: str
    notion_client_secret: str
    notion_redirect_uri: str
    notion_state_secret: str
    notion_token_encryption_key: str | None = None
    notion_default_parent_page_id: str | None = None
    notion_api_version: str = "2025-09-03"
    spotify_client_id: str | None = None
    spotify_client_secret: str | None = None
    spotify_redirect_uri: str | None = None
    spotify_state_secret: str | None = None
    linear_client_id: str | None = None
    linear_client_secret: str | None = None
    linear_redirect_uri: str | None = None
    linear_state_secret: str | None = None
    google_client_id: str | None = None
    google_client_secret: str | None = None
    google_redirect_uri: str | None = None
    google_state_secret: str | None = None

    telegram_bot_token: str | None = None
    telegram_link_secret: str | None = None
    telegram_webhook_secret: str | None = None
    telegram_bot_username: str | None = None

    openai_api_key: str | None = None
    google_api_key: str | None = None
    llm_planner_enabled: bool = False
    llm_planner_rule_fallback_enabled: bool = True
    llm_planner_provider: str = "openai"
    llm_planner_model: str = "gpt-4o-mini"
    llm_planner_fallback_provider: str | None = None
    llm_planner_fallback_model: str | None = None
    llm_intent_schema_version: str = "v1"
    llm_request_timeout_sec: int = 20
    llm_request_max_retries: int = 1
    llm_autonomous_enabled: bool = False
    llm_autonomous_traffic_percent: int = 100
    llm_autonomous_shadow_mode: bool = False
    llm_autonomous_max_turns: int = 6
    llm_autonomous_max_tool_calls: int = 8
    llm_autonomous_timeout_sec: int = 45
    llm_autonomous_replan_limit: int = 1
    llm_autonomous_strict: bool = False
    llm_autonomous_strict_tool_scope: bool = True
    llm_autonomous_limit_retry_once: bool = True
    llm_autonomous_rule_fallback_enabled: bool = True
    llm_autonomous_rule_fallback_mutation_enabled: bool = False
    llm_autonomous_progressive_no_fallback_enabled: bool = True
    llm_autonomous_verifier_enabled: bool = False
    llm_autonomous_verifier_fail_closed: bool = False
    llm_autonomous_verifier_max_history: int = 8
    llm_autonomous_verifier_require_tool_evidence: bool = True
    llm_autonomous_guardrail_enabled: bool = True
    llm_autonomous_guardrail_tool_error_rate_threshold: float = 0.6
    llm_autonomous_guardrail_min_tool_samples: int = 2
    llm_autonomous_guardrail_replan_ratio_threshold: float = 0.5
    llm_autonomous_guardrail_cross_service_block_threshold: int = 1
    llm_hybrid_executor_first: bool = False
    llm_response_finalizer_enabled: bool = False
    tool_specs_validate_on_startup: bool = True

    frontend_url: str = "http://localhost:3000"
    allowed_origins: str = "http://localhost:3000"
    pending_action_storage: str = "db"
    pending_action_ttl_seconds: int = 900
    pending_action_table: str = "pending_actions"
    pipeline_links_table: str = "pipeline_links"
    slot_loop_enabled: bool = True
    slot_loop_rollout_percent: int = 100
    slot_loop_metrics_enabled: bool = True
    slot_schema_path: str | None = None
    telegram_user_preface_enabled: bool = True
    telegram_user_preface_llm_enabled: bool = True
    telegram_user_preface_max_chars: int = 240
    conversation_mode_enabled: bool = True
    skill_router_v2_enabled: bool = False
    skill_runner_v2_enabled: bool = False
    skill_router_v2_llm_enabled: bool = False
    skill_v2_shadow_mode: bool = False
    skill_v2_traffic_percent: int = 100
    skill_v2_allowlist: str | None = None
    skill_llm_transform_pipeline_enabled: bool = False
    skill_llm_transform_pipeline_shadow_mode: bool = False
    skill_llm_transform_pipeline_traffic_percent: int = 100
    skill_llm_transform_pipeline_allowlist: str | None = None
    atomic_overhaul_enabled: bool = False
    atomic_overhaul_shadow_mode: bool = False
    atomic_overhaul_traffic_percent: int = 100
    atomic_overhaul_allowlist: str | None = None
    atomic_overhaul_legacy_fallback_enabled: bool = True
    llm_stepwise_pipeline_enabled: bool = False
    stepwise_force_enabled: bool = False
    stepwise_tool_retry_max_attempts: int = 2
    stepwise_tool_retry_backoff_ms: int = 300
    telegram_debug_report_enabled: bool = False
    telegram_message_max_chars: int = 3500
    rule_reparse_for_llm_plan_enabled: bool = False
    delete_operations_enabled: bool = False
    auto_fill_no_question_enabled: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
