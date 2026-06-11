from django.urls import path

from verifications import verify_views

urlpatterns = [
    path("initiate", verify_views.initiate),
    path("webhook", verify_views.squad_webhook),
    path("<uuid:verification_id>/status", verify_views.status_poll),
]
