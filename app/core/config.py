from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    env: str = "local"

    jwt_secret: str
    jwt_access_token_expires_minutes: int = 30
    jwt_refresh_token_expires_days: int = 30

    database_url: str

    redis_url: str
    celery_broker_url: str
    celery_result_backend: str

    squad_base_url: str = "https://sandbox-api-d.squadco.com"
    squad_secret_key: str
    squad_currency: str = "NGN"
    squad_verification_amount_kobo: int = 100000  # legacy; unused for verify (credits now)
    squad_callback_url: str | None = None
    """Optional. Legacy frontend URL pattern (e.g. Next.js after pay). Not used by this backend code today."""

    squad_webhook_callback_url: str = "http://127.0.0.1:8000/api/verify/webhook"
    """Squad `callback_url` on /transaction/initiate: server-to-server payment notify URL (our POST /api/verify/webhook)."""
    credit_price_kobo: int = 70000  # per credit, kobo (70000 = ₦700)

    groq_api_key: str
    groq_model: str = "meta-llama/llama-4-scout-17b-16e-instruct"

    # Optional: Tavily web search to corroborate extracted institution/program claims
    tavily_api_key: str | None = None

    file_storage_driver: str = "local"
    local_storage_dir: str = "./storage"


settings = Settings()  # type: ignore[call-arg]

