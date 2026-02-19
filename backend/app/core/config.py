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

    telegram_bot_token: str | None = None
    telegram_link_secret: str | None = None
    telegram_webhook_secret: str | None = None
    telegram_bot_username: str | None = None

    openai_api_key: str | None = None
    google_api_key: str | None = None
    llm_planner_enabled: bool = False
    llm_planner_provider: str = "openai"
    llm_planner_model: str = "gpt-4o-mini"
    llm_planner_fallback_provider: str | None = None
    llm_planner_fallback_model: str | None = None

    frontend_url: str = "http://localhost:3000"
    allowed_origins: str = "http://localhost:3000"

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    return Settings()
