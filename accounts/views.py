from django.contrib import messages
from django.contrib.auth.views import PasswordResetConfirmView
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import FormView, TemplateView

from accounts import recovery
from accounts.forms import RecoveryPasswordForm, RecoveryRequestForm
from core.audit import log_event


class AnonymousOnlyMixin:
    """Las pantallas de recuperación son para quien no tiene sesión: con sesión, la persona va a su perfil."""

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect("core:profile")
        return super().dispatch(request, *args, **kwargs)


class RecoveryRequestView(AnonymousOnlyMixin, FormView):
    """Paso 1: se escribe el correo. Siempre termina en la misma pantalla, exista o no la cuenta."""

    form_class = RecoveryRequestForm
    template_name = "registration/recover_request.html"
    success_url = reverse_lazy("accounts:recover_done")

    def form_valid(self, form):
        form.save(self.request)
        return super().form_valid(form)


class RecoveryDoneView(AnonymousOnlyMixin, TemplateView):
    """Paso 2: «revisa tu correo». No dice si el correo estaba registrado ni lo repite."""

    template_name = "registration/recover_done.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["duration"] = recovery.link_duration()
        return context


class RecoveryConfirmView(AnonymousOnlyMixin, PasswordResetConfirmView):
    """Paso 3: el enlace del correo. Con el enlace vigente se elige la contraseña nueva.

    El enlace se valida con el mecanismo de Django: lo firma la cuenta y su contraseña actual, así que al guardar la
    contraseña nueva el mismo enlace deja de servir. Un enlace inventado, vencido o ya usado muestra el aviso y
    responde 400, sin detalles técnicos. El token se esconde de la barra de direcciones apenas se abre el enlace.
    """

    form_class = RecoveryPasswordForm
    template_name = "registration/recover_confirm.html"
    success_url = reverse_lazy("core:login")

    def get_user(self, uidb64):
        user = super().get_user(uidb64)
        return user if user is not None and user.is_active else None

    def form_valid(self, form):
        response = super().form_valid(form)
        log_event(self.user, recovery.RESET_EVENT, self.user)
        messages.success(self.request, "Cambiaste tu contraseña. Ya puedes ingresar con la nueva.")
        return response

    def render_to_response(self, context, **response_kwargs):
        response = super().render_to_response(context, **response_kwargs)
        if not self.validlink:
            response.status_code = 400
        return response
