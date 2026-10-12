"""Ayudas comunes de las pruebas de las pantallas web."""

from io import StringIO

from django.contrib.auth.models import Group, Permission, User
from django.core.management import call_command
from django.test import TestCase

from accounts.models import UserProfile
from operations.models import Activity
from organization.models import Delegation, Item, Officer

PASSWORD = "Hola123!"
ALL_USERS = ("admin", "matias.cavieres", "matias.quiroz", "coordinacion1", "jefatura1", "consulta1")


class PortalTestCase(TestCase):
    """Datos de demostración y ayudas comunes."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo_data", stdout=StringIO())
        cls.north = Delegation.objects.get(name="Delegación Norte")
        cls.south = Delegation.objects.get(name="Delegación Sur")

    def login_as(self, username):
        user = User.objects.get(username=username)
        self.client.force_login(user)
        return user

    def give_perm(self, user, label):
        """Agrega un permiso ("app.codename") directamente al usuario, para probar un rol con más o menos permisos."""
        app_label, codename = label.split(".")
        user.user_permissions.add(Permission.objects.get(content_type__app_label=app_label, codename=codename))

    def officer(self, institutional_id):
        return Officer.objects.get(institutional_id=institutional_id)

    def activity(self, contact_name):
        return Activity.objects.get(contact_name=contact_name)

    def menu_labels(self, response):
        """Textos de todas las entradas del menú lateral (las de arriba y las de los grupos)."""
        labels = {item.label for item in response.context["menu_top"]}
        for group in response.context["menu_groups"]:
            labels.update(item.label for item in group.items)
        return labels

    def activity_data(self, **changes):
        """Datos de un formulario de actividad válido para matias.cavieres (Norte)."""
        data = {
            "date": "2026-10-01",
            "item": Item.objects.get(name="Visita Domiciliaria").pk,
            "service": "",
            "beneficiary": "",
            "contact_name": "Rosa Prueba",
            "phone": "",
            "request_description": "Consulta de prueba.",
            "action_taken": "",
            "status": Activity.Status.REGISTERED,
            "delegation": self.north.pk,
            "author_officer": self.officer("F-1001").pk,
        }
        data.update(changes)
        return data

    def intake_data(self, **changes):
        """Datos del formulario de ingreso de atención (el de «Registrar atención») para matias.cavieres (Norte)."""
        data = {
            "requester": "Rosa Prueba",
            "phone": "",
            "attention_type": Item.objects.get(name="Atención Social").pk,
            "item": Item.objects.get(name="Visita Domiciliaria").pk,
            "service": "",
            "request_description": "Consulta de prueba.",
            "action_taken": "",
        }
        data.update(changes)
        return data

    def make_user(self, username, groups=(), officer=None):
        """Crea un usuario con sus grupos y, si se indica, vinculado a un funcionario."""
        user = User.objects.create_user(username, password=PASSWORD)
        for name in groups:
            user.groups.add(Group.objects.get(name=name))
        if officer is not None:
            UserProfile.objects.create(user=user, officer=officer, status=UserProfile.Status.ACTIVE)
        return user

    def activity_form_data(self, activity, **changes):
        """Datos del formulario de edición de una actividad ya guardada, tal como los envía el navegador."""
        data = {
            "date": activity.date.isoformat(),
            "item": activity.item_id,
            "service": activity.service_id or "",
            "beneficiary": activity.beneficiary_id or "",
            "contact_name": activity.contact_name,
            "phone": activity.phone or "",
            "request_description": activity.request_description,
            "action_taken": activity.action_taken or "",
            "status": activity.status,
            "delegation": activity.delegation_id,
            "author_officer": activity.author_officer_id,
        }
        if activity.requires_visit:
            data["requires_visit"] = "on"
        if activity.added_to_pipeline:
            data["added_to_pipeline"] = "on"
        data.update(changes)
        return data
