from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.routes import auth, credits, user, verifications, verify

app = FastAPI(title="VeraDoc API", version="1.0.0")


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

