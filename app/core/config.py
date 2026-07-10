from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
    )

    database_url: str
    database_sync_url: str
    redis_url: str = "redis://localhost:6379/0"
    anthropic_api_key: str
    anthropic_model: str = "claude-haiku-4-5"
    confidence_threshold: float = 0.85
    otlp_endpoint: str = "http://localhost:4317"
    log_level: str = "INFO"
    access_token: str = ""


settings = Settings()
