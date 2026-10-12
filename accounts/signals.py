"""Señales de las cuentas: cada rol (grupo de Django) nace con su ficha, y cada ingreso parte con su delegación."""

from django.contrib.auth.models import Group
from django.contrib.auth.signals import user_logged_in
from django.db.models.signals import post_save
from django.dispatch import receiver

from core.access import SESSION_DELEGATION

from .models import RoleProfile, role_defaults


@receiver(post_save, sender=Group)
def create_role_profile(sender, instance, created, raw=False, **kwargs):
    """Al crearse un grupo (desde Roles, el Admin o seed_roles) se le crea su ficha con los valores de siempre.

    Si el rol se crea desde el mantenedor de Roles, el formulario guarda enseguida la descripción, el alcance y
    el estado que eligió la persona (ver RoleCrud.after_save en core/registry.py).
    """
    if created and not raw:
        RoleProfile.objects.get_or_create(group=instance, defaults=role_defaults(instance.name))


@receiver(user_logged_in)
def start_in_own_delegation(sender, request=None, **kwargs):
    """Cada ingreso parte con la delegación de siempre (Clase 6: el estado temporal de la sesión no pasa de un ingreso
    a otro). La que se elige en la franja de arriba vale mientras dure la sesión."""
    session = getattr(request, "session", None)
    if session is not None:
        session.pop(SESSION_DELEGATION, None)
