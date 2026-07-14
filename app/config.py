from functools import lru_cache
import os


class Settings:
    app_name: str = os.getenv("APP_NAME", "Ddeolyee API")
    app_env: str = os.getenv("APP_ENV", "local")
    database_url: str = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg://last_call:last_call@localhost:5432/last_call_market",
    )
    access_token_ttl_minutes: int = int(os.getenv("ACCESS_TOKEN_TTL_MINUTES", "120"))


@lru_cache
def get_settings() -> Settings:
    return Settings()
