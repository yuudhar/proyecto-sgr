from django.urls import path

from accounts import views

app_name = "accounts"

urlpatterns = [
    path("recuperar/", views.RecoveryRequestView.as_view(), name="recover"),
    path("recuperar/enviado/", views.RecoveryDoneView.as_view(), name="recover_done"),
    path("recuperar/<uidb64>/<token>/", views.RecoveryConfirmView.as_view(), name="recover_confirm"),
]
