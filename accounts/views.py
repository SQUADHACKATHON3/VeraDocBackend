import urllib.parse
from datetime import datetime, timezone

import httpx
from django.conf import settings
from django.db import transaction
from django.http import HttpResponseRedirect
from jose import JWTError, jwt
from rest_framework import status
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from accounts.models import User
from accounts.serializers import (
    ForgotPasswordSerializer,
    LoginSerializer,
    MeSerializer,
    RegisterSerializer,
    ResetPasswordSerializer,
    TokenSerializer,
    VerifyEmailSerializer,
)
from common.background import run_in_background
from common.models import OtpType
from common.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    verify_password,
)
from services.email_service import log_otp_code, send_otp_email_task, should_log_otp_codes
from services.otp_service import OtpVerifyResult, create_otp, get_last_otp_created_at, verify_and_consume_otp


def _oauth_login_redirect(*, error: str) -> HttpResponseRedirect:
    url = (
        f"{settings.FRONTEND_URL.rstrip('/')}/auth/login"
        f"?error={urllib.parse.quote(error)}"
    )
    return HttpResponseRedirect(url)


def _oauth_success_redirect(*, access_token: str, refresh_token: str) -> HttpResponseRedirect:
    url = (
        f"{settings.FRONTEND_URL.rstrip('/')}/auth/callback"
        f"?token={urllib.parse.quote(access_token)}"
        f"&refresh_token={urllib.parse.quote(refresh_token)}"
    )
    return HttpResponseRedirect(url)


@api_view(["POST"])
@permission_classes([AllowAny])
def register(request):
    serializer = RegisterSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    if User.objects.filter(email=data["email"]).exists():
        return Response({"detail": "Email already registered"}, status=status.HTTP_409_CONFLICT)

    user = User.objects.create(
        name=data["name"],
        organisation=data["organisation"],
        email=data["email"],
        password_hash=hash_password(data["password"]),
    )

    code = create_otp(email=user.email, otp_type=OtpType.EMAIL_VERIFICATION, user_id=str(user.id))
    log_otp_code(to=user.email, code=code, otp_type="email_verification")
    run_in_background(send_otp_email_task, to=user.email, code=code, otp_type="email_verification")

    response = {
        "message": "Account created successfully. Check your email for a verification code.",
        "credits": user.credits,
    }
    if should_log_otp_codes():
        response["devOtp"] = code
    return Response(response, status=status.HTTP_201_CREATED)


@api_view(["POST"])
@permission_classes([AllowAny])
def login(request):
    serializer = LoginSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    try:
        user = User.objects.get(email=data["email"])
    except User.DoesNotExist:
        return Response({"detail": "Invalid credentials"}, status=status.HTTP_401_UNAUTHORIZED)

    if not user.password_hash or not verify_password(data["password"], user.password_hash):
        return Response({"detail": "Invalid credentials"}, status=status.HTTP_401_UNAUTHORIZED)

    return Response(
        TokenSerializer(
            {
                "access_token": create_access_token(str(user.id)),
                "refresh_token": create_refresh_token(str(user.id)),
            }
        ).data
    )


@api_view(["POST"])
@permission_classes([AllowAny])
def refresh(request):
    refresh_token = request.query_params.get("refresh_token") or request.data.get("refresh_token")
    if not refresh_token:
        return Response({"detail": "Unauthorized"}, status=status.HTTP_401_UNAUTHORIZED)

    try:
        payload = jwt.decode(refresh_token, settings.JWT_SECRET, algorithms=["HS256"])
    except JWTError:
        return Response({"detail": "Unauthorized"}, status=status.HTTP_401_UNAUTHORIZED)

    if payload.get("type") != "refresh":
        return Response({"detail": "Unauthorized"}, status=status.HTTP_401_UNAUTHORIZED)

    user_id = payload.get("sub")
    if not user_id or not User.objects.filter(pk=user_id).exists():
        return Response({"detail": "Unauthorized"}, status=status.HTTP_401_UNAUTHORIZED)

    return Response(
        TokenSerializer(
            {
                "access_token": create_access_token(user_id),
                "refresh_token": create_refresh_token(user_id),
            }
        ).data
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def me(request):
    return Response(MeSerializer(request.user).data)


@api_view(["GET"])
@permission_classes([AllowAny])
def google_login(request):
    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_REDIRECT_URI:
        return Response({"detail": "Google OAuth is not configured on this server."}, status=503)

    state = create_access_token("oauth", expires_minutes=10, extra={"purpose": "google_oauth"})
    params = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
        "prompt": "select_account",
        "state": state,
    }
    url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(params)
    return Response({"url": url})


@api_view(["GET"])
@permission_classes([AllowAny])
@authentication_classes([])
def google_callback(request):
    code = request.query_params.get("code")
    state = request.query_params.get("state")
    error = request.query_params.get("error")

    if error:
        return _oauth_login_redirect(error="Google sign-in was cancelled.")

    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET or not settings.GOOGLE_REDIRECT_URI:
        return _oauth_login_redirect(error="Google sign-in is not configured on this server.")

    if not code:
        return _oauth_login_redirect(error="Google sign-in failed. Missing authorization code.")

    if not state:
        return _oauth_login_redirect(error="Google sign-in failed. Missing security state.")

    try:
        state_payload = jwt.decode(state, settings.JWT_SECRET, algorithms=["HS256"])
    except JWTError:
        return _oauth_login_redirect(error="Google sign-in failed. Invalid security state.")

    if state_payload.get("purpose") != "google_oauth":
        return _oauth_login_redirect(error="Google sign-in failed. Invalid security state.")

    try:
        with httpx.Client(timeout=15) as client:
            token_resp = client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "code": code,
                    "client_id": settings.GOOGLE_CLIENT_ID,
                    "client_secret": settings.GOOGLE_CLIENT_SECRET,
                    "redirect_uri": settings.GOOGLE_REDIRECT_URI,
                    "grant_type": "authorization_code",
                },
            )
            if token_resp.status_code != 200:
                return _oauth_login_redirect(error="Google sign-in failed. Could not exchange token.")

            token_data = token_resp.json()
            access_token_google = token_data.get("access_token")
            if not access_token_google:
                return _oauth_login_redirect(error="Google sign-in failed. No access token returned.")

            userinfo_resp = client.get(
                "https://www.googleapis.com/oauth2/v3/userinfo",
                headers={"Authorization": f"Bearer {access_token_google}"},
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

        with transaction.atomic():
            user = User.objects.filter(google_id=google_id).first()
            if not user:
                existing = User.objects.filter(email=email).first()
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
                    user.save(update_fields=["google_id", "email_verified"])
                else:
                    user = User.objects.create(
                        name=name,
                        organisation="",
                        email=email,
                        password_hash=None,
                        google_id=google_id,
                        email_verified=True,
                    )
            else:
                user.google_id = google_id
                user.email_verified = True
                if not user.name:
                    user.name = name
                user.save(update_fields=["google_id", "email_verified", "name"])

        return _oauth_success_redirect(
            access_token=create_access_token(str(user.id)),
            refresh_token=create_refresh_token(str(user.id)),
        )
    except Exception:
        return _oauth_login_redirect(error="Google sign-in failed. Please try again.")


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def verify_email(request):
    serializer = VerifyEmailSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    user = request.user

    if user.email_verified:
        return Response({"message": "Email already verified"})

    result = verify_and_consume_otp(
        email=user.email, otp_type=OtpType.EMAIL_VERIFICATION, code=serializer.validated_data["otp"]
    )
    if result == OtpVerifyResult.locked:
        return Response({"detail": "Too many failed attempts. Request a new code."}, status=429)
    if result != OtpVerifyResult.ok:
        return Response({"detail": "Invalid or expired OTP"}, status=status.HTTP_400_BAD_REQUEST)

    user.email_verified = True
    user.save(update_fields=["email_verified"])
    return Response({"message": "Email verified successfully"})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def resend_otp(request):
    user = request.user
    if user.email_verified:
        return Response({"message": "Email already verified"})

    last = get_last_otp_created_at(email=user.email, otp_type=OtpType.EMAIL_VERIFICATION)
    if last:
        elapsed = (datetime.now(timezone.utc) - last.replace(tzinfo=timezone.utc)).total_seconds()
        if elapsed < settings.OTP_RESEND_COOLDOWN_SECONDS:
            return Response(
                {
                    "detail": (
                        f"Please wait {int(settings.OTP_RESEND_COOLDOWN_SECONDS - elapsed)} "
                        "seconds before requesting another code."
                    )
                },
                status=429,
            )

    code = create_otp(email=user.email, otp_type=OtpType.EMAIL_VERIFICATION, user_id=str(user.id))
    log_otp_code(to=user.email, code=code, otp_type="email_verification")
    run_in_background(send_otp_email_task, to=user.email, code=code, otp_type="email_verification")

    body = {"message": "OTP sent successfully"}
    if should_log_otp_codes():
        body["devOtp"] = code
    return Response(body)


@api_view(["POST"])
@permission_classes([AllowAny])
def forgot_password(request):
    serializer = ForgotPasswordSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    email = serializer.validated_data["email"]

    try:
        user = User.objects.get(email=email)
    except User.DoesNotExist:
        return Response({"detail": "No account found with that email address."}, status=status.HTTP_404_NOT_FOUND)

    last = get_last_otp_created_at(email=email, otp_type=OtpType.PASSWORD_RESET)
    if last:
        elapsed = (datetime.now(timezone.utc) - last.replace(tzinfo=timezone.utc)).total_seconds()
        if elapsed < settings.OTP_RESEND_COOLDOWN_SECONDS:
            return Response(
                {
                    "detail": (
                        f"Please wait {int(settings.OTP_RESEND_COOLDOWN_SECONDS - elapsed)} "
                        "seconds before requesting another code."
                    )
                },
                status=429,
            )

    code = create_otp(email=email, otp_type=OtpType.PASSWORD_RESET, user_id=str(user.id))
    log_otp_code(to=email, code=code, otp_type="password_reset")
    run_in_background(send_otp_email_task, to=email, code=code, otp_type="password_reset")
    return Response({"message": "If an account exists, a reset code has been sent"})


@api_view(["POST"])
@permission_classes([AllowAny])
def reset_password(request):
    serializer = ResetPasswordSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    result = verify_and_consume_otp(
        email=data["email"], otp_type=OtpType.PASSWORD_RESET, code=data["otp"]
    )
    if result == OtpVerifyResult.locked:
        return Response({"detail": "Too many failed attempts. Request a new code."}, status=429)
    if result != OtpVerifyResult.ok:
        return Response({"detail": "Invalid or expired OTP"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        user = User.objects.get(email=data["email"])
    except User.DoesNotExist:
        return Response({"detail": "User not found"}, status=status.HTTP_404_NOT_FOUND)

    user.password_hash = hash_password(data["newPassword"])
    user.save(update_fields=["password_hash"])
    return Response({"message": "Password reset successfully"})
