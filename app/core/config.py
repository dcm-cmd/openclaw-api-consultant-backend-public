from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    openclaw_base_url: str = "http://127.0.0.1:18889"
    openclaw_hooks_token: str = ""
    openclaw_gateway_base_url: str = Field(default="http://127.0.0.1:18889", alias="OPENCLAW_GATEWAY_BASE_URL")
    openclaw_gateway_token: str = Field(default="", alias="OPENCLAW_GATEWAY_TOKEN")
    openclaw_agent_id: str = "consultant-main"
    openclaw_session_key_prefix: str = Field(default="hook:consultant:", alias="OPENCLAW_SESSION_KEY_PREFIX")
    openclaw_state_dir: str = Field(default="/openclaw-state", alias="BACKEND_OPENCLAW_STATE_DIR")
    openclaw_session_poll_interval_seconds: float = Field(default=1.0, alias="BACKEND_OPENCLAW_SESSION_POLL_INTERVAL_SECONDS")
    openclaw_session_timeout_seconds: int = Field(default=60, alias="BACKEND_OPENCLAW_SESSION_TIMEOUT_SECONDS")
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/openclaw_consultant"

    class Config:
        env_file = ".env"
        extra = "allow"


settings = Settings()
