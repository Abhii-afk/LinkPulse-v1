from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "LinkPulse"
    app_env: str = "development"
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    database_url: str = "postgresql+asyncpg://linkpulse:linkpulse@127.0.0.1:5432/linkpulse"
    redis_url: str = "redis://127.0.0.1:6379/0"
    public_base_url: str = "http://127.0.0.1:8000"
    jwt_secret: str = ""
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30
    analytics_stream_name: str = "stream:clicks"
    analytics_consumer_group: str = "click_group"
    analytics_consumer_name: str = ""
    analytics_batch_size: int = 100
    analytics_block_ms: int = 2000
    analytics_claim_min_idle_ms: int = 60000
    geolite2_city_db_path: str | None = None
    geoip_mock_country_code: str = "XX"
    geoip_mock_city: str = "Mock City"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
