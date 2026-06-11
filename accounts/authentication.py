from uuid import UUID

from django.contrib.auth.models import AnonymousUser
from jose import JWTError, jwt
from rest_framework import authentication, exceptions

from accounts.models import User
from django.conf import settings


class JWTAuthentication(authentication.BaseAuthentication):
    """Bearer JWT auth matching the former FastAPI token format."""

    keyword = "Bearer"

    def authenticate(self, request):
        auth = request.META.get("HTTP_AUTHORIZATION") or ""
        if not auth.startswith(f"{self.keyword} "):
            return None

        token = auth[len(self.keyword) + 1 :].strip()
        if not token:
            raise exceptions.AuthenticationFailed("Unauthorized")

        try:
            payload = jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])
        except JWTError as exc:
            raise exceptions.AuthenticationFailed("Unauthorized") from exc

        if payload.get("type") != "access":
            raise exceptions.AuthenticationFailed("Unauthorized")

        sub = payload.get("sub")
        if not sub:
            raise exceptions.AuthenticationFailed("Unauthorized")

        try:
            user_id = UUID(str(sub))
        except (ValueError, TypeError) as exc:
            raise exceptions.AuthenticationFailed("Unauthorized") from exc

        try:
            user = User.objects.get(pk=user_id)
        except User.DoesNotExist as exc:
            raise exceptions.AuthenticationFailed("Unauthorized") from exc

        return (user, token)
