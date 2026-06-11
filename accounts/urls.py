from django.urls import path

from accounts import views

urlpatterns = [
    path("register", views.register),
    path("login", views.login),
    path("refresh", views.refresh),
    path("me", views.me),
    path("google", views.google_login),
    path("google/callback", views.google_callback),
    path("verify-email", views.verify_email),
    path("resend-otp", views.resend_otp),
    path("forgot-password", views.forgot_password),
    path("reset-password", views.reset_password),
]
