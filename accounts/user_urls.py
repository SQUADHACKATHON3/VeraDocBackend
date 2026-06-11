from django.urls import path

from accounts import user_views

urlpatterns = [
    path("password", user_views.change_password),
    path("", user_views.delete_account),
]
