from django.contrib.auth.models import Group
from django.contrib.auth.signals import user_logged_in
from django.db.models.signals import post_save
from django.dispatch import receiver

from core.access import SESSION_DELEGATION

from .models import RoleProfile, role_defaults


@receiver(post_save, sender=Group)
def create_role_profile(sender, instance, created, raw=False, **kwargs):
    if created and not raw:
        RoleProfile.objects.get_or_create(group=instance, defaults=role_defaults(instance.name))


@receiver(user_logged_in)
def start_in_own_delegation(sender, request=None, **kwargs):
    session = getattr(request, "session", None)
    if session is not None:
        session.pop(SESSION_DELEGATION, None)
