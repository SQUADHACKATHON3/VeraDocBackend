from django.urls import path

from verifications import views

urlpatterns = [
    path("", views.list_verifications),
    path("<uuid:verification_id>", views.get_verification),
]
