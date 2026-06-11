from rest_framework import permissions


class EmailVerified(permissions.BasePermission):
    message = "Email verification required. Check your inbox or POST /api/auth/resend-otp."

    def has_permission(self, request, view) -> bool:
        user = request.user
        if user is None or not hasattr(user, "email_verified"):
            return False
        return bool(user.email_verified)
