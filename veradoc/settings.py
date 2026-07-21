"""
Django settings for the VeraDoc API project.

Environment variables mirror the former FastAPI/Pydantic settings (.env.example).
"""
from __future__ import annotations

import os
from pathlib import Path

import dj_database_url
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def _database_url() -> str:
    raw = os.environ.get("DATABASE_URL", "")
    if raw.startswith("postgresql+psycopg://"):
        return "postgresql://" + raw[len("postgresql+psycopg://") :]
    if raw.startswith("postgres://"):
        return "postgresql://" + raw[len("postgres://") :]
    return raw


# Normalize SQLAlchemy-style DB URLs for Django (postgresql+psycopg:// → postgresql://)
if os.environ.get("DATABASE_URL"):
    os.environ["DATABASE_URL"] = _database_url()

SECRET_KEY = os.environ.get("JWT_SECRET", "change-me-in-production")
AUTH_USER_MODEL = "accounts.User"
DEBUG = os.environ.get("ENV", "local").lower() == "local"
ALLOWED_HOSTS = ["*"]


INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "rest_framework",
    "corsheaders",
    "common",
    "accounts",
    "credits",
    "verifications",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
]

ROOT_URLCONF = "veradoc.urls"
WSGI_APPLICATION = "veradoc.wsgi.application"

DATABASES = {
    "default": dj_database_url.config(
        default=_database_url() or "postgresql://postgres:postgres@localhost:5432/veradoc",
        conn_max_age=600,
    )
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
USE_TZ = True
TIME_ZONE = "UTC"

# ── CORS ──────────────────────────────────────────────────────────────────────
_cors_raw = os.environ.get(
    "CORS_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173,http://127.0.0.1:5173",
)
CORS_ALLOWED_ORIGINS = [o.strip() for o in _cors_raw.split(",") if o.strip()]
CORS_ALLOW_CREDENTIALS = os.environ.get("CORS_ALLOW_CREDENTIALS", "true").lower() == "true"
if not CORS_ALLOWED_ORIGINS:
    CORS_ALLOW_ALL_ORIGINS = True
    CORS_ALLOW_CREDENTIALS = False
elif "*" in CORS_ALLOWED_ORIGINS:
    CORS_ALLOW_ALL_ORIGINS = True
    CORS_ALLOW_CREDENTIALS = False

# ── DRF ───────────────────────────────────────────────────────────────────────
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "accounts.authentication.JWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "EXCEPTION_HANDLER": "common.exceptions.custom_exception_handler",
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    "UNAUTHENTICATED_USER": None,
}

# ── VeraDoc application settings ──────────────────────────────────────────────
ENV = os.environ.get("ENV", "local")

JWT_SECRET = SECRET_KEY
JWT_ACCESS_TOKEN_EXPIRES_MINUTES = int(os.environ.get("JWT_ACCESS_TOKEN_EXPIRES_MINUTES", "30"))
JWT_REFRESH_TOKEN_EXPIRES_DAYS = int(os.environ.get("JWT_REFRESH_TOKEN_EXPIRES_DAYS", "30"))

REDIS_URL = os.environ.get("REDIS_URL") or None

SQUAD_BASE_URL = os.environ.get("SQUAD_BASE_URL", "https://sandbox-api-d.squadco.com")
SQUAD_SECRET_KEY = os.environ.get("SQUAD_SECRET_KEY", "")
SQUAD_CURRENCY = os.environ.get("SQUAD_CURRENCY", "NGN")
SQUAD_VERIFICATION_AMOUNT_KOBO = int(os.environ.get("SQUAD_VERIFICATION_AMOUNT_KOBO", "100000"))
SQUAD_CALLBACK_URL = os.environ.get("SQUAD_CALLBACK_URL") or None
CREDIT_PRICE_KOBO = int(os.environ.get("CREDIT_PRICE_KOBO", "70000"))

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL = os.environ.get("GROQ_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct")
TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY") or None

FILE_STORAGE_DRIVER = os.environ.get("FILE_STORAGE_DRIVER", "local")
LOCAL_STORAGE_DIR = os.environ.get("LOCAL_STORAGE_DIR", str(BASE_DIR / "storage"))
CLOUDINARY_URL = os.environ.get("CLOUDINARY_URL") or None

VERIFICATION_PRIMARY_REGION = os.environ.get("VERIFICATION_PRIMARY_REGION", "NG")
HYBRID_VERDICT_SCORE_CONSISTENCY = os.environ.get("HYBRID_VERDICT_SCORE_CONSISTENCY", "true").lower() == "true"

FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:3000")

GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID") or None
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET") or None
GOOGLE_REDIRECT_URI = os.environ.get("GOOGLE_REDIRECT_URI") or None

EMAIL_DRIVER = os.environ.get("EMAIL_DRIVER", "resend")
SMTP_HOST = os.environ.get("SMTP_HOST") or None
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER") or None
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD") or None
SMTP_FROM = os.environ.get("SMTP_FROM", "noreply@veradoc.app")
SMTP_TLS = os.environ.get("SMTP_TLS", "true").lower() == "true"

RESEND_API_KEY = os.environ.get("RESEND_API_KEY") or None
RESEND_FROM = os.environ.get("RESEND_FROM", "noreply@veradoc.app")

OTP_TTL_MINUTES = int(os.environ.get("OTP_TTL_MINUTES", "10"))
OTP_RESEND_COOLDOWN_SECONDS = int(os.environ.get("OTP_RESEND_COOLDOWN_SECONDS", "60"))
OTP_MAX_ATTEMPTS = int(os.environ.get("OTP_MAX_ATTEMPTS", "5"))
OTP_LOG_CODES = os.environ.get("OTP_LOG_CODES", "").lower() in ("1", "true", "yes")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
}
