from django.http import JsonResponse
from django.urls import include, path


def health(_request):
    return JsonResponse({"status": "VeraDoc API running"})


def api_health(_request):
    return JsonResponse({"status": "ok", "service": "veradoc-api"})


urlpatterns = [
    path("", health),
    path("api/health", api_health),
    path("api/auth/", include("accounts.urls")),
    path("api/user/", include("accounts.user_urls")),
    path("api/credits/", include("credits.urls")),
    path("api/verify/", include("verifications.verify_urls")),
    path("api/verifications/", include("verifications.urls")),
]
