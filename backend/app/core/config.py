from functools import lru_cache
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic_settings import BaseSettings, SettingsConfigDict


SUPPORTED_JWT_ALGORITHMS = frozenset({"HS256", "HS384", "HS512"})
MINIMUM_JWT_SECRET_LENGTH = 24


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
    link_session_secret: str = ""
    link_session_ttl_seconds: int = 900
    cors_allowed_origins: str = "http://127.0.0.1:5173,http://localhost:5173"
    rate_limit_link_creation_per_minute: int = 30
    rate_limit_window_seconds: int = 60
    rate_limit_password_attempts_per_minute: int = 10
    analytics_stream_name: str = "stream:clicks"
    analytics_consumer_group: str = "click_group"
    analytics_consumer_name: str = ""
    analytics_batch_size: int = 100
    analytics_block_ms: int = 2000
    analytics_claim_min_idle_ms: int = 60000
    geolite2_city_db_path: str | None = None
    geoip_mock_country_code: str = "XX"
    geoip_mock_city: str = "Mock City"

    @property
    def resolved_link_session_secret(self) -> str:
        """Signing key for password-challenge cookies.

        Falls back to the JWT secret so a single configured secret is enough
        for a local deployment, while production can rotate the two
        independently.
        """

        return self.link_session_secret or self.jwt_secret

    @property
    def cookies_require_secure_transport(self) -> bool:
        """Cookies are only marked Secure when the public origin is HTTPS."""

        return self.public_base_url.lower().startswith("https://")

    @property
    def cors_origins(self) -> list[str]:
        """Browser origins that may call the API.

        The front end is served from a different origin than the API, so the
        browser sends a preflight request before every call. Without these
        origins the request is blocked before it leaves the browser.
        """

        return [
            origin.strip()
            for origin in self.cors_allowed_origins.split(",")
            if origin.strip()
        ]

    @property
    def normalized_database_url(self) -> str:
        """The database URL with the driver specific options translated.

        Managed Postgres providers hand out libpq style URLs that end in
        ``?sslmode=require``. The asyncpg driver does not know that option
        and refuses the connection with "connect() got an unexpected keyword
        argument 'sslmode'". Renaming it to ``ssl`` lets the URL be pasted
        exactly as the provider shows it.
        """

        if "sslmode=" not in self.database_url:
            return self.database_url

        parts = urlsplit(self.database_url)
        query = parse_qsl(parts.query, keep_blank_values=True)
        if any(key == "ssl" for key, _value in query):
            return self.database_url

        translated = [
            ("ssl" if key == "sslmode" else key, value) for key, value in query
        ]
        return urlunsplit(
            (parts.scheme, parts.netloc, parts.path, urlencode(translated), parts.fragment)
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()


def validate_settings(current: Settings | None = None) -> None:
    """Fail fast on an insecure or incomplete deployment configuration.

    Called during application startup so a missing secret is a clear startup
    error instead of a runtime 500 on the first login.
    """

    active = current or settings

    if not active.jwt_secret:
        raise RuntimeError("JWT_SECRET is not configured")
    if len(active.jwt_secret) < MINIMUM_JWT_SECRET_LENGTH:
        raise RuntimeError(
            f"JWT_SECRET must be at least {MINIMUM_JWT_SECRET_LENGTH} characters long"
        )
    if active.jwt_algorithm not in SUPPORTED_JWT_ALGORITHMS:
        allowed = ", ".join(sorted(SUPPORTED_JWT_ALGORITHMS))
        raise RuntimeError(f"JWT_ALGORITHM must be one of {allowed}")
    if not active.resolved_link_session_secret:
        raise RuntimeError("LINK_SESSION_SECRET is not configured")
    if active.rate_limit_link_creation_per_minute < 1:
        raise RuntimeError("RATE_LIMIT_LINK_CREATION_PER_MINUTE must be at least 1")
    if active.rate_limit_window_seconds < 1:
        raise RuntimeError("RATE_LIMIT_WINDOW_SECONDS must be at least 1")
    if active.link_session_ttl_seconds < 1:
        raise RuntimeError("LINK_SESSION_TTL_SECONDS must be at least 1")
