from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import auth, credits, user, verifications, verify
from app.core.config import settings
from app.services.redis_client import close_redis


def _parse_cors_origins() -> list[str]:
    raw = (settings.cors_origins or "").strip()
    if not raw:
        return []
    return [o.strip() for o in raw.split(",") if o.strip()]


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    close_redis()


app = FastAPI(title="VeraDoc API", version="1.0.0", lifespan=lifespan)

_origins = _parse_cors_origins()
_allow_credentials = settings.cors_allow_credentials
if not _origins:
    _origins = ["*"]
    _allow_credentials = False
elif "*" in _origins:
    _allow_credentials = False

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(_: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=500, content={"error": "Internal server error", "detail": str(exc)})


@app.get("/")
def health() -> dict:
    return {"status": "VeraDoc API running"}


app.include_router(auth.router)
app.include_router(credits.router)
app.include_router(verify.router)
app.include_router(verifications.router)
app.include_router(user.router)

