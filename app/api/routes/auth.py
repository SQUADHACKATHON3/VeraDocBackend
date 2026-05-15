from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.responses import RedirectResponse
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.config import settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    verify_password,
)
from app.models.otp_code import OtpType
from app.models.user import User
from app.schemas.auth import (
    ForgotPasswordIn,
    LoginIn,
    MeOut,
    RegisterIn,
    ResetPasswordIn,
    TokenOut,
    VerifyEmailIn,
)
from app.services.email_service import log_otp_code, send_otp_email_task, should_log_otp_codes
from app.services.otp_service import (
    OtpVerifyResult,
    create_otp,
    get_last_otp_created_at,
    verify_and_consume_otp,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _oauth_login_redirect(*, error: str) -> RedirectResponse:
    import urllib.parse

    url = (
        f"{settings.frontend_url.rstrip('/')}/auth/login"
        f"?error={urllib.parse.quote(error)}"
    )
    return RedirectResponse(url=url, status_code=302)


def _oauth_success_redirect(*, access_token: str, refresh_token: str) -> RedirectResponse:
    import urllib.parse

    url = (
        f"{settings.frontend_url.rstrip('/')}/auth/callback"
        f"?token={urllib.parse.quote(access_token)}"
        f"&refresh_token={urllib.parse.quote(refresh_token)}"
    )
    return RedirectResponse(url=url, status_code=302)


# ── Register ──────────────────────────────────────────────────────────────────

@router.post("/register", status_code=201)
def register(
    payload: RegisterIn,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> dict:
    existing = db.scalar(select(User).where(User.email == payload.email))
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")
    user = User(
        name=payload.name,
        organisation=payload.organisation,
        email=payload.email,
        password_hash=hash_password(payload.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    code = create_otp(db, email=user.email, otp_type=OtpType.email_verification, user_id=str(user.id))
    log_otp_code(to=user.email, code=code, otp_type="email_verification")
    background_tasks.add_task(
        send_otp_email_task, to=user.email, code=code, otp_type="email_verification"
    )

    response: dict = {
        "message": "Account created successfully. Check your email for a verification code.",
        "credits": user.credits,
    }
    if should_log_otp_codes():
        response["devOtp"] = code
    return response


# ── Login ─────────────────────────────────────────────────────────────────────

@router.post("/login", response_model=TokenOut)
def login(payload: LoginIn, db: Session = Depends(get_db)) -> TokenOut:
    user = db.scalar(select(User).where(User.email == payload.email))
    if not user or not user.password_hash or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    return TokenOut(
        access_token=create_access_token(str(user.id)),
        refresh_token=create_refresh_token(str(user.id)),
    )


# ── Refresh ───────────────────────────────────────────────────────────────────

@router.post("/refresh", response_model=TokenOut)
def refresh(refresh_token: str, db: Session = Depends(get_db)) -> TokenOut:
    try:
        payload = jwt.decode(refresh_token, settings.jwt_secret, algorithms=["HS256"])
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")
    user_id = payload.get("sub")
    if not user_id or not db.get(User, user_id):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")
    return TokenOut(
        access_token=create_access_token(user_id),
        refresh_token=create_refresh_token(user_id),
    )


# ── Me ────────────────────────────────────────────────────────────────────────

@router.get("/me", response_model=MeOut)
def me(user: User = Depends(get_current_user)) -> MeOut:
    return MeOut(
        id=user.id,
        name=user.name,
        organisation=user.organisation,
        email=user.email,
        credits=user.credits,
        emailVerified=user.email_verified,
    )


# ── Google OAuth ──────────────────────────────────────────────────────────────

@router.get("/google")
def google_login() -> dict:
    """Return the Google OAuth authorization URL. Frontend redirects the user there."""
    if not settings.google_client_id or not settings.google_redirect_uri:
        raise HTTPException(status_code=503, detail="Google OAuth is not configured on this server.")
    import urllib.parse

    state = create_access_token("oauth", expires_minutes=10, extra={"purpose": "google_oauth"})
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
        "prompt": "select_account",
        "state": state,
    }
    url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(params)
    return {"url": url}


@router.get("/google/callback")
async def google_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_db),
) -> RedirectResponse:
    """Exchange code for tokens, upsert user, redirect to frontend with JWT tokens."""
    if error:
        return _oauth_login_redirect(error="Google sign-in was cancelled.")

    if not settings.google_client_id or not settings.google_client_secret or not settings.google_redirect_uri:
        return _oauth_login_redirect(error="Google sign-in is not configured on this server.")

    if not code:
        return _oauth_login_redirect(error="Google sign-in failed. Missing authorization code.")

    if not state:
        return _oauth_login_redirect(error="Google sign-in failed. Missing security state.")

    try:
        state_payload = jwt.decode(state, settings.jwt_secret, algorithms=["HS256"])
    except JWTError:
        return _oauth_login_redirect(error="Google sign-in failed. Invalid security state.")

    if state_payload.get("purpose") != "google_oauth":
        return _oauth_login_redirect(error="Google sign-in failed. Invalid security state.")

    import httpx as _httpx

    try:
        token_resp = _httpx.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "redirect_uri": settings.google_redirect_uri,
                "grant_type": "authorization_code",
            },
            timeout=15,
        )
        if token_resp.status_code != 200:
            return _oauth_login_redirect(error="Google sign-in failed. Could not exchange token.")

        token_data = token_resp.json()
        access_token_google = token_data.get("access_token")
        if not access_token_google:
            return _oauth_login_redirect(error="Google sign-in failed. No access token returned.")

        userinfo_resp = _httpx.get(
            "https://www.googleapis.com/oauth2/v3/userinfo",
            headers={"Authorization": f"Bearer {access_token_google}"},
            timeout=15,
        )
        if userinfo_resp.status_code != 200:
            return _oauth_login_redirect(error="Google sign-in failed. Could not load profile.")

        info = userinfo_resp.json()
        google_id: str = info.get("sub") or ""
        email: str = info.get("email") or ""
        if not google_id or not email:
            return _oauth_login_redirect(error="Google sign-in failed. Email permission is required.")

        name: str = info.get("name") or email.split("@")[0]
        if not info.get("email_verified", True):
            return _oauth_login_redirect(error="Your Google email must be verified.")

        user = db.scalar(select(User).where(User.google_id == google_id))
        if not user:
            existing = db.scalar(select(User).where(User.email == email))
            if existing:
                if existing.google_id and existing.google_id != google_id:
                    return _oauth_login_redirect(
                        error="This email is already linked to a different Google account."
                    )
                if existing.password_hash and not existing.email_verified:
                    return _oauth_login_redirect(
                        error="An account exists with this email but is not verified. "
                        "Verify your email or reset your password first."
                    )
                user = existing
                user.google_id = google_id
                user.email_verified = True
            else:
                user = User(
                    name=name,
                    organisation="",
                    email=email,
                    password_hash=None,
                    google_id=google_id,
                    email_verified=True,
                )
                db.add(user)
        else:
            user.google_id = google_id
            user.email_verified = True
            if not user.name:
                user.name = name

        db.commit()
        db.refresh(user)

        return _oauth_success_redirect(
            access_token=create_access_token(str(user.id)),
            refresh_token=create_refresh_token(str(user.id)),
        )
    except Exception:
        db.rollback()
        return _oauth_login_redirect(error="Google sign-in failed. Please try again.")


# ── Email Verification OTP ────────────────────────────────────────────────────

@router.post("/verify-email")
def verify_email(
    payload: VerifyEmailIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    if user.email_verified:
        return {"message": "Email already verified"}
    result = verify_and_consume_otp(
        db, email=user.email, otp_type=OtpType.email_verification, code=payload.otp
    )
    if result == OtpVerifyResult.locked:
        raise HTTPException(status_code=429, detail="Too many failed attempts. Request a new code.")
    if result != OtpVerifyResult.ok:
        raise HTTPException(status_code=400, detail="Invalid or expired OTP")
    user.email_verified = True
    db.add(user)
    db.commit()
    return {"message": "Email verified successfully"}


@router.post("/resend-otp")
def resend_otp(
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    if user.email_verified:
        return {"message": "Email already verified"}

    last = get_last_otp_created_at(db, email=user.email, otp_type=OtpType.email_verification)
    if last:
        elapsed = (datetime.now(timezone.utc) - last.replace(tzinfo=timezone.utc)).total_seconds()
        if elapsed < settings.otp_resend_cooldown_seconds:
            raise HTTPException(
                status_code=429,
                detail=f"Please wait {int(settings.otp_resend_cooldown_seconds - elapsed)} seconds before requesting another code.",
            )

    code = create_otp(db, email=user.email, otp_type=OtpType.email_verification, user_id=str(user.id))
    log_otp_code(to=user.email, code=code, otp_type="email_verification")
    background_tasks.add_task(
        send_otp_email_task, to=user.email, code=code, otp_type="email_verification"
    )
    body: dict = {"message": "OTP sent successfully"}
    if should_log_otp_codes():
        body["devOtp"] = code
    return body


# ── Forgot / Reset Password ───────────────────────────────────────────────────

@router.post("/forgot-password")
def forgot_password(
    payload: ForgotPasswordIn,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> dict:
    user = db.scalar(select(User).where(User.email == payload.email))
    if not user:
        # Spec says 404 for UX; change to always-200 if you prefer security over UX.
        raise HTTPException(status_code=404, detail="No account found with that email address.")

    last = get_last_otp_created_at(db, email=payload.email, otp_type=OtpType.password_reset)
    if last:
        elapsed = (datetime.now(timezone.utc) - last.replace(tzinfo=timezone.utc)).total_seconds()
        if elapsed < settings.otp_resend_cooldown_seconds:
            raise HTTPException(
                status_code=429,
                detail=f"Please wait {int(settings.otp_resend_cooldown_seconds - elapsed)} seconds before requesting another code.",
            )

    code = create_otp(db, email=payload.email, otp_type=OtpType.password_reset, user_id=str(user.id))
    log_otp_code(to=payload.email, code=code, otp_type="password_reset")
    background_tasks.add_task(
        send_otp_email_task, to=payload.email, code=code, otp_type="password_reset"
    )
    return {"message": "If an account exists, a reset code has been sent"}


@router.post("/reset-password")
def reset_password(
    payload: ResetPasswordIn,
    db: Session = Depends(get_db),
) -> dict:
    if len(payload.newPassword) < 8:
        raise HTTPException(status_code=422, detail="Password must be at least 8 characters")

    result = verify_and_consume_otp(
        db, email=payload.email, otp_type=OtpType.password_reset, code=payload.otp
    )
    if result == OtpVerifyResult.locked:
        raise HTTPException(status_code=429, detail="Too many failed attempts. Request a new code.")
    if result != OtpVerifyResult.ok:
        raise HTTPException(status_code=400, detail="Invalid or expired OTP")

    user = db.scalar(select(User).where(User.email == payload.email))
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.password_hash = hash_password(payload.newPassword)
    db.add(user)
    db.commit()
    return {"message": "Password reset successfully"}
