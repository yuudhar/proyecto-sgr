"""Direcciones de la recuperación de contraseña."""

from django.urls import path

from accounts import views

app_name = "accounts"

urlpatterns = [
    path("recuperar/", views.request_code, name="recover"),
    path("recuperar/codigo/", views.enter_code, name="recover_code"),
    path("recuperar/reenviar/", views.resend_code, name="recover_resend"),
    path("recuperar/nueva/", views.new_password, name="recover_password"),
]
