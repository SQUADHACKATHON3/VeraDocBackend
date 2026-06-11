from django.urls import path

from credits import views

urlpatterns = [
    path("packs", views.list_packs),
    path("purchase/initiate", views.initiate_credit_purchase),
    path("purchases/<uuid:purchase_id>/verify", views.verify_credit_purchase),
    path("purchases/<uuid:purchase_id>", views.purchase_status),
]
