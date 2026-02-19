from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
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
    apple_music_team_id: str | None = None
    apple_music_key_id: str | None = None
    apple_music_private_key: str | None = None
    apple_music_app_name: str = "metel"

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
    llm_autonomous_enabled: bool = False
    llm_autonomous_max_turns: int = 6
    llm_autonomous_max_tool_calls: int = 8
    llm_autonomous_timeout_sec: int = 45
    llm_autonomous_replan_limit: int = 1
    llm_autonomous_strict: bool = False
    llm_autonomous_limit_retry_once: bool = True
    llm_autonomous_rule_fallback_enabled: bool = True
    llm_autonomous_rule_fallback_mutation_enabled: bool = False
    llm_autonomous_progressive_no_fallback_enabled: bool = True
    tool_specs_validate_on_startup: bool = True

    frontend_url: str = "http://localhost:3000"
    allowed_origins: str = "http://localhost:3000"

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    return Settings()
