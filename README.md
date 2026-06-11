# VeraDoc Backend

VeraDoc is an AI-powered forensic document verification platform. The backend is built with **Django REST Framework** and handles document uploads, Groq Vision analysis, Tavily web corroboration, Squad payments, and JWT authentication.

## Tech Stack

| Layer | Technology |
|---|---|
| Framework | Django 5 + Django REST Framework |
| Database | PostgreSQL |
| Migrations | Django migrations (`manage.py migrate`) |
| AI | Groq API (Vision) |
| Web search | Tavily API |
| Payments | Squad API |
| File storage | Local disk or Cloudinary |

## Project Layout

```
VeraDocBackend/
├── manage.py                 # Django CLI entry point
├── veradoc/                  # Django project (settings, root URLs, WSGI)
│   ├── settings.py
│   ├── urls.py
│   ├── wsgi.py
│   └── asgi.py
├── accounts/                 # Users, JWT auth, Google OAuth, OTP, /api/auth, /api/user
├── credits/                  # Credit packs, Squad checkout, /api/credits
├── verifications/            # Document verify pipeline, history, /api/verify, /api/verifications
├── common/                   # Shared models (OTP, webhooks), security, exceptions
├── services/                 # Framework-agnostic business logic (Groq, Tavily, Squad, storage)
├── storage/                  # Local uploads (when FILE_STORAGE_DRIVER=local)
└── requirements.txt
```

### App responsibilities

- **accounts** — `User` model, registration/login, JWT refresh, Google OAuth, email verification OTP, password reset, account management.
- **credits** — Credit pack catalog, Squad purchase initiation/verification, credit balance grants via webhook.
- **verifications** — Document upload, AI forensic pipeline (background thread), verification history and status polling.
- **common** — `OtpCode`, `WebhookEvent` models, password/JWT helpers, DRF exception handler, background task helper.
- **services** — Groq analyzer, Tavily search, forensic hybrid engine, file storage, Squad client, email delivery.

The API contract is unchanged from the FastAPI era — same paths, request bodies, and response shapes. See `VeraDoc_API_Documentation.md`.

## Prerequisites

- Python 3.12+
- PostgreSQL
- `poppler-utils` (PDF → image): `brew install poppler` (macOS) or `apt-get install poppler-utils` (Linux)

## Environment

Copy `.env.example` to `.env`. Key variables:

```ini
ENV=local
DATABASE_URL=postgresql://user:password@localhost:5432/veradoc
JWT_SECRET=your_super_secret_jwt_key
GROQ_API_KEY=gsk_...
SQUAD_SECRET_KEY=sandbox_sk_...
FRONTEND_URL=http://localhost:3000
CORS_ORIGINS=http://localhost:3000
```

`DATABASE_URL` may use the legacy `postgresql+psycopg://` prefix — it is normalized automatically for Django.

## Local Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver 0.0.0.0:8000
```

For production-style serving:

```bash
gunicorn veradoc.wsgi:application --bind 0.0.0.0:8000 --workers 2 --threads 4 --timeout 120
```

Docker Compose:

```bash
cp .env.example .env   # fill secrets
docker compose up --build
```

### Migrating from Alembic (existing database)

If your database was created with the old FastAPI/Alembic migrations:

```bash
python manage.py migrate --fake-initial
```

This marks Django's initial migrations as applied without recreating existing tables.

## AI Verification Pipeline

1. User uploads a document (PDF, PNG, JPG) via `POST /api/verify/initiate`.
2. `pdf2image` + Pillow prepare an optimized image for Groq Vision.
3. Groq returns a trust score, flags, and extracted entities.
4. Tavily corroborates institution claims when configured.
5. The hybrid consistency engine produces the final verdict (`AUTHENTIC`, `NEEDS REVIEW`, or `FAKE`).
