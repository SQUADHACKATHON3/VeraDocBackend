from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    env: str = "local"

    jwt_secret: str
    jwt_access_token_expires_minutes: int = 30
    jwt_refresh_token_expires_days: int = 30

    database_url: str

    redis_url: str | None = None
    """Optional. e.g. Render Key Value / Redis URL for caching or rate limits. Omitted = Redis disabled."""

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
    """Use `local` (disk) or `cloudinary` for uploads."""

    cloudinary_url: str | None = None
    """Set `CLOUDINARY_URL` from the Cloudinary dashboard when `file_storage_driver` is `cloudinary`."""

    verification_primary_region: str = "NG"
    """Issuing context for prompts and search bias. Default Nigeria; later unlock other ISO-style codes (e.g. GH, KE)."""

    hybrid_verdict_score_consistency: bool = True
    """When True, apply deterministic band checks on model verdict vs trust_score (reduces incoherent AUTHENTIC)."""

    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173,http://127.0.0.1:5173"
    """Comma-separated `Access-Control-Allow-Origin` values. Use your deployed frontend origin(s) in production."""

    cors_allow_credentials: bool = True
    """Set False if you use `cors_origins='*'` (browsers forbid credentials with wildcard origin)."""


settings = Settings()  # type: ignore[call-arg]

