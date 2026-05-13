# VeraDocBackend (FastAPI)

Single FastAPI backend for VeraDoc (auth, uploads, Squad payments, Groq verification).

## Quickstart (local)

### 1) Create env

Create `.env` from `.env.example`.

### 2) Install deps

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3) Run Postgres + Redis (Docker)

```bash
docker run --name veradoc-postgres -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=veradoc -p 5432:5432 -d postgres:16
docker run --name veradoc-redis -p 6379:6379 -d redis:7
```

### 4) Migrate DB

```bash
alembic upgrade head
```

### 5) Run API

```bash
uvicorn app.main:app --reload --port 8000
```

### 6) Run worker

```bash
celery -A app.tasks.celery_app worker -l info
```

## API

Routes follow the shapes in `VeraDoc_API_Documentation.md` (ported to FastAPI).

