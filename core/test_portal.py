import csv
from decimal import Decimal
from io import StringIO

from django.contrib.auth.models import Group, User
from django.test import SimpleTestCase
from django.urls import NoReverseMatch, reverse
from django.utils import timezone

from core import ui
from core.crud import registry
from core.models import AuditLog
from core.testing import ALL_USERS, PASSWORD, PortalTestCase
from core.views import safe_cell
from evidence.models import Evidence, Validation
from operations.models import Activity, Commitment, Followup, ManagementType
from organization.models import Item, Officer, Position, Territory
from planning.models import Adjustment, Goal, Indicator, Period


class LoginTests(PortalTestCase):
    def test_login_page_is_in_spanish_and_public(self):
        response = self.client.get(reverse("core:login"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<html lang="es">')
        self.assertContains(response, "Usuario")
        self.assertContains(response, "Contraseña")

    def test_valid_credentials_go_to_dashboard(self):
        response = self.client.post(
            reverse("core:login"), {"username": "matias.cavieres", "password": PASSWORD}
        )
        self.assertRedirects(response, reverse("core:dashboard"))

    def test_wrong_password_shows_error_and_keeps_user_out(self):
        response = self.client.post(
            reverse("core:login"), {"username": "matias.cavieres", "password": "otra"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors)
        self.assertContains(response, "El usuario, el correo o la contraseña no son correctos")
        self.assertEqual(self.client.get(reverse("core:dashboard")).status_code, 302)

    def test_empty_fields_are_rejected_with_a_message_for_each_one(self):
        response = self.client.post(reverse("core:login"), {"username": "", "password": ""})
        self.assertEqual(response.status_code, 200)
        errors = response.context["form"].errors
        self.assertIn("username", errors)
        self.assertIn("password", errors)
        self.assertContains(response, "obligatorio")
        self.assertEqual(self.client.get(reverse("core:dashboard")).status_code, 302)

    def test_a_valid_user_without_password_is_rejected(self):
        response = self.client.post(reverse("core:login"), {"username": "matias.cavieres", "password": ""})
        self.assertEqual(response.status_code, 200)
        self.assertIn("password", response.context["form"].errors)
        self.assertNotIn("username", response.context["form"].errors)
        self.assertEqual(self.client.get(reverse("core:dashboard")).status_code, 302)

    def test_a_password_without_user_is_rejected(self):
        response = self.client.post(reverse("core:login"), {"username": "", "password": PASSWORD})
        self.assertEqual(response.status_code, 200)
        self.assertIn("username", response.context["form"].errors)
        self.assertNotIn("password", response.context["form"].errors)
        self.assertEqual(self.client.get(reverse("core:dashboard")).status_code, 302)

    def test_logged_user_visiting_login_goes_to_dashboard(self):
        self.login_as("admin")
        response = self.client.get(reverse("core:login"))
        self.assertRedirects(response, reverse("core:dashboard"))

    def test_next_parameter_never_leaves_the_site(self):
        response = self.client.post(
            reverse("core:login") + "?next=https://ejemplo.invalid/",
            {"username": "admin", "password": PASSWORD},
        )
        self.assertRedirects(response, reverse("core:dashboard"))

    def test_logout_needs_post(self):
        self.login_as("admin")
        self.assertEqual(self.client.get(reverse("core:logout")).status_code, 405)
        self.assertEqual(self.client.get(reverse("core:dashboard")).status_code, 200)
        response = self.client.post(reverse("core:logout"))
        self.assertRedirects(response, reverse("core:login"))
        self.assertEqual(self.client.get(reverse("core:dashboard")).status_code, 302)

    def test_anonymous_users_are_sent_to_login_everywhere(self):
        urls = [
            reverse("core:dashboard"),
            reverse("core:validate_list"),
            reverse("core:validate_evidence", args=[1]),
            reverse("core:delegation_board"),
            reverse("core:reports"),
            reverse("core:administration"),
        ]
        for crud in registry.all():
            urls.append(crud.url("list"))
            urls.append(crud.url("detail", 1))
            if crud.allow_add:
                urls.append(crud.url("create"))
        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 302)
                self.assertTrue(response["Location"].startswith(reverse("core:login")))

    def test_old_mockup_addresses_still_work(self):
        self.login_as("matias.cavieres")
        for old, new in (
            ("/actividades/registrar/", "core:actividades_create"),
            ("/evidencias/cargar/", "core:evidencias_create"),
            ("/catalogo/servicios/", "core:servicios_list"),
        ):
            with self.subTest(old=old):
                response = self.client.get(old)
                self.assertRedirects(response, reverse(new), fetch_redirect_response=False)

    def test_admin_keeps_its_own_language(self):
        response = self.client.get("/admin/login/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Log in")


class RoleTests(PortalTestCase):
    def test_menu_follows_each_role(self):
        self.login_as("matias.cavieres")
        labels = self.menu_labels(self.client.get(reverse("core:dashboard")))
        self.assertIn("Atención", labels)
        self.assertIn("Validar evidencias", labels)
        self.assertNotIn("Períodos", labels)

        self.login_as("coordinacion1")
        labels = self.menu_labels(self.client.get(reverse("core:dashboard")))
        self.assertIn("Períodos", labels)
        self.assertIn("Metas", labels)
        self.assertIn("Ajustes", labels)
        self.assertIn("Informes", labels)
        self.assertNotIn("Atención", labels)
        self.assertNotIn("Validar evidencias", labels)

        self.login_as("admin")
        labels = self.menu_labels(self.client.get(reverse("core:dashboard")))
        self.assertIn("Auditoría", labels)

    def test_admin_panel_link_only_for_staff_users(self):
        for username in ALL_USERS:
            with self.subTest(username=username):
                user = self.login_as(username)
                labels = self.menu_labels(self.client.get(reverse("core:dashboard")))
                self.assertEqual("Panel de administración" in labels, user.is_staff)
        outsider = User.objects.create_user("sin.panel", password=PASSWORD)
        outsider.groups.add(Group.objects.get(name="Funcionario"))
        self.client.force_login(outsider)
        labels = self.menu_labels(self.client.get(reverse("core:dashboard")))
        self.assertNotIn("Panel de administración", labels)

    def test_pages_without_permission_answer_403(self):
        cases = (
            ("coordinacion1", reverse("core:atencion")),
            ("coordinacion1", reverse("core:validate_list")),
            ("matias.cavieres", reverse("core:periodos_list")),
            ("matias.cavieres", reverse("core:delegation_board")),
            ("matias.cavieres", reverse("core:reports")),
            ("matias.cavieres", reverse("core:auditoria_list")),
            ("jefatura1", reverse("core:actividades_create")),
            ("jefatura1", reverse("core:validate_list")),
        )
        for username, url in cases:
            with self.subTest(username=username, url=url):
                self.login_as(username)
                self.assertEqual(self.client.get(url).status_code, 403)

    def test_forged_posts_without_permission_are_rejected(self):
        self.login_as("jefatura1")
        before = Activity.objects.count()
        response = self.client.post(
            reverse("core:actividades_create"), self.intake_data(requester="Colada")
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(Activity.objects.count(), before)

        self.login_as("matias.cavieres")
        before = Period.objects.count()
        response = self.client.post(
            reverse("core:periodos_create"),
            {
                "start_date": "2027-01-01",
                "end_date": "2027-12-31",
                "computable_days": 240,
                "status": "planned",
            },
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(Period.objects.count(), before)

    def test_jefatura_reads_but_cannot_change(self):
        self.login_as("jefatura1")
        response = self.client.get(reverse("core:atencion"))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["can_add"])
        self.assertFalse(response.context["any_actions"])
        activity = self.activity("María Pérez")
        detail = self.client.get(reverse("core:actividades_detail", args=[activity.pk]))
        self.assertEqual(detail.status_code, 200)
        self.assertFalse(detail.context["can_edit"])
        self.assertEqual(
            self.client.get(reverse("core:actividades_update", args=[activity.pk])).status_code, 403
        )
        self.assertEqual(
            self.client.post(reverse("core:actividades_archive", args=[activity.pk])).status_code, 403
        )

    def test_coordination_cannot_edit_delegation_records(self):
        self.login_as("coordinacion1")
        activity = self.activity("María Pérez")
        for name in ("actividades_detail", "actividades_update", "actividades_archive"):
            with self.subTest(name=name):
                url = reverse(f"core:{name}", args=[activity.pk])
                self.assertEqual(self.client.get(url).status_code, 403)

    def test_user_without_officer_gets_a_notice_and_no_data(self):
        user = User.objects.create_user("sin.funcionario", password=PASSWORD)
        user.groups.add(Group.objects.get(name="Funcionario"))
        self.client.force_login(user)
        response = self.client.get(reverse("core:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["no_delegation"])
        self.assertContains(response, "no tiene una delegación asignada")
        self.assertEqual(self.client.get(reverse("core:atencion")).status_code, 403)
        self.assertEqual(self.client.get(reverse("core:actividades_create")).status_code, 403)

    def test_dashboard_shows_own_goals_and_global_semaphore(self):
        self.login_as("matias.cavieres")
        response = self.client.get(reverse("core:dashboard"))
        lines = response.context["goal_lines"]
        self.assertEqual({line["item"].name for line in lines}, {"Visita Domiciliaria", "Entrega de Ayudas Sociales"})
        self.assertNotIn("light_counts", response.context)

        self.login_as("coordinacion1")
        response = self.client.get(reverse("core:dashboard"))
        counts = {row["light"]: row["total"] for row in response.context["light_counts"]}
        self.assertEqual(counts, {"green": 1, "amber": 1, "red": 1})


class ScopingTests(PortalTestCase):
    def contacts(self, response):
        index = [column.label for column in response.context["columns"]].index("Contacto")
        return {row.cells[index].text for row in response.context["rows"]}

    def test_lists_only_show_own_delegation(self):
        self.login_as("matias.cavieres")
        north = self.contacts(self.client.get(reverse("core:atencion")))
        self.assertIn("María Pérez", north)
        self.assertNotIn("Ana Rojas", north)

        self.login_as("matias.quiroz")
        south = self.contacts(self.client.get(reverse("core:atencion")))
        self.assertIn("Ana Rojas", south)
        self.assertNotIn("María Pérez", south)

        self.login_as("admin")
        everything = self.contacts(self.client.get(reverse("core:atencion")))
        self.assertTrue({"María Pérez", "Ana Rojas"} <= everything)

    def test_search_does_not_leak_other_delegation(self):
        self.login_as("matias.quiroz")
        url = reverse("core:atencion")
        self.assertEqual(self.client.get(url, {"q": "Ana"}).context["page"].paginator.count, 1)
        self.assertEqual(self.client.get(url, {"q": "Carla"}).context["page"].paginator.count, 0)
        response = self.client.get(url, {"delegation": self.north.pk})
        self.assertNotIn("María Pérez", self.contacts(response))

    def test_other_delegation_records_are_not_found(self):
        user = self.login_as("matias.quiroz")
        self.give_perm(user, "operations.delete_activity")
        activity = self.activity("María Pérez")
        evidence = Evidence.objects.get(unique_code="EVD-NORTE-0001")
        urls = [
            reverse("core:actividades_detail", args=[activity.pk]),
            reverse("core:actividades_update", args=[activity.pk]),
            reverse("core:actividades_archive", args=[activity.pk]),
            reverse("core:evidencias_detail", args=[evidence.pk]),
            reverse("core:validate_evidence", args=[evidence.pk]),
        ]
        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 404)
        for name in ("actividades_archive", "actividades_restore", "actividades_update"):
            with self.subTest(post=name):
                url = reverse(f"core:{name}", args=[activity.pk])
                self.assertEqual(self.client.post(url, self.activity_data()).status_code, 404)
        activity.refresh_from_db()
        self.assertIsNone(activity.deleted_at)

    def test_board_and_reports_are_limited_for_delegation_users(self):
        self.login_as("jefatura1")
        board = self.client.get(reverse("core:delegation_board"), {"delegacion": self.south.pk})
        self.assertEqual(board.context["delegation"], self.north)
        self.assertFalse(board.context["can_pick_delegation"])

        report = self.client.get(
            reverse("core:reports"), {"delegacion": self.south.pk, "formato": "csv"}
        )
        names = {row["Funcionario"] for row in self.read_csv(report)}
        self.assertIn("Matías Cavieres", names)
        self.assertNotIn("Matías Quiroz", names)

    def read_csv(self, response):
        text = response.content.decode("utf-8-sig")
        return list(csv.DictReader(StringIO(text), delimiter=";"))

    def test_global_users_choose_the_delegation(self):
        self.login_as("coordinacion1")
        board = self.client.get(reverse("core:delegation_board"), {"delegacion": self.south.pk})
        self.assertEqual(board.context["delegation"], self.south)
        self.assertTrue(board.context["can_pick_delegation"])


class ForgedFormTests(PortalTestCase):
    def setUp(self):
        self.login_as("matias.cavieres")

    def test_activity_delegation_is_always_the_users(self):
        response = self.client.post(
            reverse("core:actividades_create"), self.intake_data(delegation=self.south.pk)
        )
        created = Activity.objects.get(contact_name="Rosa Prueba")
        self.assertRedirects(response, reverse("core:actividades_detail", args=[created.pk]))
        self.assertEqual(created.delegation, self.north)

    def test_activity_officer_is_always_the_one_who_registers_it(self):
        response = self.client.post(
            reverse("core:actividades_create"),
            self.intake_data(author_officer=self.officer("F-2001").pk, delegation=self.south.pk),
        )
        created = Activity.objects.get(contact_name="Rosa Prueba")
        self.assertRedirects(response, reverse("core:actividades_detail", args=[created.pk]))
        self.assertEqual(created.author_officer, self.officer("F-1001"))
        self.assertEqual(created.delegation, self.north)

    def test_followup_for_activity_of_other_delegation_is_rejected(self):
        foreign = self.activity("Ana Rojas")
        response = self.client.post(
            reverse("core:gestiones_create"),
            {
                "activity": foreign.pk,
                "sequence_number": 3,
                "management_type": ManagementType.objects.first().pk,
                "date": "2026-10-02",
                "result": "Intento ajeno",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("activity", response.context["form"].errors)
        self.assertFalse(Followup.objects.filter(result="Intento ajeno").exists())

    def test_evidence_for_activity_of_other_delegation_is_rejected(self):
        foreign = self.activity("Ana Rojas")
        response = self.client.post(
            reverse("core:evidencias_create"),
            {
                "activity": foreign.pk,
                "unique_code": "EVD-NORTE-0099",
                "file_link": "evidencias/ajena.pdf",
                "author_officer": self.officer("F-1001").pk,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("activity", response.context["form"].errors)
        self.assertFalse(Evidence.objects.filter(unique_code="EVD-NORTE-0099").exists())

    def test_commitment_with_territory_of_other_delegation_is_rejected(self):
        foreign = Territory.objects.filter(delegation=self.south).first()
        response = self.client.post(
            reverse("core:agenda_create"),
            {
                "requester": "Junta ajena",
                "requester_type": "EXTERNAL",
                "request_date": "2026-10-01",
                "territory": foreign.pk,
                "due_date": "2026-11-01",
                "status": "submitted",
                "responsible_officer": self.officer("F-1001").pk,
                "delegation": self.north.pk,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("territory", response.context["form"].errors)
        self.assertFalse(Commitment.objects.filter(requester="Junta ajena").exists())

    def test_update_cannot_move_the_activity_to_another_officer(self):
        activity = self.activity("María Pérez")
        response = self.client.post(
            reverse("core:actividades_update", args=[activity.pk]),
            self.activity_data(
                contact_name="María Pérez", author_officer=self.officer("F-2001").pk
            ),
        )
        self.assertEqual(response.status_code, 200)
        activity.refresh_from_db()
        self.assertEqual(activity.author_officer, self.officer("F-1001"))

    def test_form_choices_exclude_other_delegation(self):
        create_form = self.client.get(reverse("core:actividades_create")).context["form"]
        self.assertNotIn("author_officer", create_form.fields)
        self.assertNotIn("delegation", create_form.fields)
        activity = self.activity("María Pérez")
        form = self.client.get(reverse("core:actividades_update", args=[activity.pk])).context["form"]
        officers = set(form.fields["author_officer"].queryset.values_list("delegation", flat=True))
        self.assertEqual(officers, {self.north.pk})
        self.assertTrue(form.fields["delegation"].disabled)

    def test_model_rule_is_kept_for_the_superuser(self):
        self.login_as("admin")
        response = self.client.post(
            reverse("core:actividades_create"),
            self.intake_data(delegation=self.south.pk, author_officer=self.officer("F-1001").pk),
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("delegation", response.context["form"].errors)
        self.assertContains(response, "debe coincidir con la delegación del funcionario")

    def test_inactive_choices_do_not_show_archived_records(self):
        archived = Activity.objects.filter(deleted_at__isnull=False).first()
        self.assertIsNotNone(archived)
        response = self.client.get(reverse("core:evidencias_create"))
        offered = set(response.context["form"].fields["activity"].queryset.values_list("pk", flat=True))
        self.assertNotIn(archived.pk, offered)


class CrudFlowTests(PortalTestCase):
    def test_create_update_archive_and_restore_an_activity(self):
        user = self.login_as("matias.cavieres")
        response = self.client.post(reverse("core:actividades_create"), self.intake_data())
        created = Activity.objects.get(contact_name="Rosa Prueba")
        detail = reverse("core:actividades_detail", args=[created.pk])
        self.assertRedirects(response, detail, fetch_redirect_response=False)
        self.assertContains(
            self.client.get(detail), f"Atención registrada para Rosa Prueba. Identificador: ATN{created.pk:05d}."
        )
        self.assertEqual(created.author_officer, self.officer("F-1001"))

        response = self.client.post(
            reverse("core:actividades_update", args=[created.pk]),
            self.activity_data(contact_name="Rosa Editada"),
        )
        self.assertRedirects(response, detail)
        created.refresh_from_db()
        self.assertEqual(created.contact_name, "Rosa Editada")

        archive_url = reverse("core:actividades_archive", args=[created.pk])
        self.assertEqual(self.client.get(archive_url).status_code, 403)
        self.assertEqual(self.client.post(archive_url).status_code, 403)
        created.refresh_from_db()
        self.assertIsNone(created.deleted_at)

        self.give_perm(user, "operations.delete_activity")
        self.assertContains(self.client.get(archive_url), "Eliminar")
        response = self.client.post(archive_url)
        self.assertRedirects(response, reverse("core:atencion"))
        created.refresh_from_db()
        self.assertIsNotNone(created.deleted_at)
        log = AuditLog.objects.get(event="Registro archivado", record_id=created.pk)
        self.assertEqual(log.affected_entity, "Activity")
        self.assertEqual(log.user.username, "matias.cavieres")

        listing = self.client.get(reverse("core:atencion"))
        self.assertNotIn("Rosa Editada", ScopingTests.contacts(self, listing))
        with_archived = self.client.get(reverse("core:atencion"), {"archivados": "1"})
        self.assertIn("Rosa Editada", ScopingTests.contacts(self, with_archived))
        edit_url = reverse("core:actividades_update", args=[created.pk])
        self.assertRedirects(self.client.get(edit_url), detail)
        self.assertEqual(
            self.client.post(edit_url, self.activity_data(contact_name="Otra")).status_code, 403
        )

        restore_url = reverse("core:actividades_restore", args=[created.pk])
        self.assertEqual(self.client.get(restore_url).status_code, 405)
        self.assertRedirects(self.client.post(restore_url), detail)
        created.refresh_from_db()
        self.assertIsNone(created.deleted_at)
        self.assertTrue(AuditLog.objects.filter(event="Registro restaurado", record_id=created.pk).exists())

    def test_required_fields_show_messages_and_keep_what_was_typed(self):
        self.login_as("matias.cavieres")
        response = self.client.post(
            reverse("core:actividades_create"),
            self.intake_data(attention_type="", item="", requester="", request_description="Texto que se conserva"),
        )
        self.assertEqual(response.status_code, 200)
        form = response.context["form"]
        self.assertIn("attention_type", form.errors)
        self.assertIn("requester", form.errors)
        self.assertContains(response, "Este campo es obligatorio.")
        self.assertContains(response, "is-invalid")
        self.assertContains(response, "Texto que se conserva")

    def test_followup_rules_are_checked_by_the_form(self):
        self.login_as("matias.cavieres")
        activity = self.activity("María Pérez")
        base = {
            "activity": activity.pk,
            "management_type": ManagementType.objects.first().pk,
            "date": activity.date.isoformat(),
            "result": "Se llamó por teléfono.",
        }
        # El número de gestión lo asigna el sistema: no se escribe en el formulario.
        response = self.client.get(reverse("core:gestiones_create"))
        self.assertNotIn("sequence_number", response.context["form"].fields)
        # Un número escrito a mano se ignora: la gestión toma el primer número libre (la 3).
        response = self.client.post(
            reverse("core:gestiones_create"), {**base, "sequence_number": 1}
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Followup.objects.filter(activity=activity, sequence_number=3).exists())
        # Con las 3 gestiones hechas, la cuarta se rechaza.
        response = self.client.post(reverse("core:gestiones_create"), base)
        self.assertEqual(response.status_code, 200)
        self.assertIn("activity", response.context["form"].errors)
        self.assertEqual(Followup.objects.filter(activity=activity).count(), 3)

    def test_get_form_from_activity_detail_preselects_the_activity(self):
        self.login_as("matias.cavieres")
        activity = self.activity("María Pérez")
        response = self.client.get(reverse("core:gestiones_create"), {"activity": activity.pk})
        self.assertEqual(str(response.context["form"].initial["activity"]), str(activity.pk))
        foreign = self.activity("Ana Rojas")
        response = self.client.get(reverse("core:gestiones_create"), {"activity": foreign.pk})
        self.assertFalse(response.context["form"].fields["activity"].queryset.filter(pk=foreign.pk).exists())

    def test_evidence_code_is_assigned_per_delegation(self):
        self.login_as("matias.cavieres")
        response = self.client.get(reverse("core:evidencias_create"))
        self.assertNotIn("unique_code", response.context["form"].fields)
        north = Evidence.objects.create(
            file_link="x", activity=self.activity("María Pérez"), author_officer=self.officer("F-1001")
        )
        south = Evidence.objects.create(
            file_link="x", activity=self.activity("Ana Rojas"), author_officer=self.officer("F-2001")
        )
        self.assertEqual(north.unique_code, "EVD-NORTE-0004")
        self.assertEqual(south.unique_code, "EVD-SUR-0004")

    def test_coordination_manages_periods_and_adjustments(self):
        self.login_as("coordinacion1")
        response = self.client.post(
            reverse("core:periodos_create"),
            {
                "start_date": "2027-01-01",
                "end_date": "2027-12-31",
                "computable_days": 240,
                "status": "planned",
                "collective_threshold": "80",
                "amber_threshold": "60",
                "weighted_cap": "150",
                "parameters_version": "1",
            },
        )
        period = Period.objects.get(start_date="2027-01-01")
        self.assertRedirects(response, reverse("core:periodos_detail", args=[period.pk]))

        response = self.client.post(
            reverse("core:ajustes_create"),
            {
                "officer": self.officer("F-1001").pk,
                "kind": "bonus",
                "percentage_value": "5",
                "period": period.pk,
                "reason": "Reconocimiento de prueba",
            },
        )
        self.assertEqual(response.status_code, 302)
        adjustment = Adjustment.objects.get(reason="Reconocimiento de prueba")
        self.assertEqual(adjustment.responsible_user.username, "coordinacion1")

    def test_validations_cannot_be_created_edited_or_archived_by_url(self):
        self.login_as("admin")
        validation = Validation.objects.first()
        for name in ("validaciones_create", "validaciones_update", "validaciones_archive"):
            with self.subTest(name=name):
                args = [] if name.endswith("create") else [validation.pk]
                with self.assertRaises(NoReverseMatch):
                    reverse(f"core:{name}", args=args)

    def test_list_parameters_are_safe(self):
        self.login_as("admin")
        url = reverse("core:atencion")
        for params in (
            {"orden": "contact_name", "dir": "desc"},
            {"orden": "no_existe; DROP TABLE x"},
            {"page": "9999"},
            {"page": "abc"},
            {"status": "no_existe"},
            {"q": "<script>alert(1)</script>"},
            {"requires_visit": "1", "q": "María"},
        ):
            with self.subTest(params=params):
                self.assertEqual(self.client.get(url, params).status_code, 200)
        response = self.client.get(url, {"q": "<script>alert(1)</script>"})
        self.assertNotContains(response, "<script>alert(1)</script>")

    def test_names_with_html_are_escaped_everywhere(self):
        self.login_as("matias.cavieres")
        self.client.post(
            reverse("core:actividades_create"),
            self.intake_data(requester="Rosa Negrita"),
        )
        Activity.objects.filter(contact_name="Rosa Negrita").update(contact_name="<b>negrita</b>")
        created = Activity.objects.get(contact_name="<b>negrita</b>")
        for url in (
            reverse("core:atencion"),
            reverse("core:actividades_detail", args=[created.pk]),
            reverse("core:actividades_update", args=[created.pk]),
            reverse("core:dashboard"),
        ):
            with self.subTest(url=url):
                self.assertNotContains(self.client.get(url), "<b>negrita</b>")


class PlanningRuleTests(PortalTestCase):
    def setUp(self):
        self.login_as("coordinacion1")

    def period_data(self, **changes):
        data = {
            "start_date": "2027-01-01",
            "end_date": "2027-12-31",
            "computable_days": 240,
            "status": "planned",
            "collective_threshold": "80",
            "amber_threshold": "60",
            "weighted_cap": "150",
            "parameters_version": "1",
        }
        data.update(changes)
        return data

    def test_period_end_cannot_be_before_start(self):
        response = self.client.post(
            reverse("core:periodos_create"),
            self.period_data(start_date="2027-06-01", end_date="2027-01-01"),
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("end_date", response.context["form"].errors)
        self.assertFalse(Period.objects.filter(start_date="2027-06-01").exists())

    def test_amber_threshold_must_be_below_the_collective_one(self):
        for amber in ("80", "95"):
            with self.subTest(amber=amber):
                response = self.client.post(
                    reverse("core:periodos_create"), self.period_data(amber_threshold=amber)
                )
                self.assertEqual(response.status_code, 200)
                self.assertIn("amber_threshold", response.context["form"].errors)
        self.assertFalse(Period.objects.filter(start_date="2027-01-01").exists())

    def test_goal_belongs_to_one_officer_or_one_position_not_both_nor_none(self):
        base = {
            "item": Item.objects.get(name="Visita Domiciliaria").pk,
            "period": Period.objects.get(status="active").pk,
            "target_value": "20",
            "unit": "visitas",
            "weight": "50",
            "version": "1",
        }
        officer = self.officer("F-1002").pk
        position = Position.objects.get(name="Coordinador de Terreno").pk
        url = reverse("core:metas_create")

        both = self.client.post(url, {**base, "officer": officer, "position": position})
        self.assertEqual(both.status_code, 200)
        self.assertIn("position", both.context["form"].errors)

        none = self.client.post(url, {**base, "officer": "", "position": ""})
        self.assertEqual(none.status_code, 200)
        self.assertIn("officer", none.context["form"].errors)
        self.assertFalse(Goal.objects.filter(unit="visitas", weight=50).exists())

        personal = self.client.post(url, {**base, "officer": officer, "position": ""})
        self.assertEqual(personal.status_code, 302)
        by_position = self.client.post(url, {**base, "officer": "", "position": position})
        self.assertEqual(by_position.status_code, 302)

    def test_goal_target_must_be_positive(self):
        response = self.client.post(
            reverse("core:metas_create"),
            {
                "item": Item.objects.get(name="Visita Domiciliaria").pk,
                "period": Period.objects.get(status="active").pk,
                "officer": self.officer("F-1002").pk,
                "target_value": "0",
                "unit": "visitas",
                "weight": "50",
                "version": "1",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("target_value", response.context["form"].errors)

    def test_indicator_light_is_calculated_from_the_period_thresholds(self):
        self.login_as("admin")
        goal = Goal.objects.filter(period__status="active", officer__isnull=False).first()
        url = reverse("core:indicadores_create")
        self.assertNotIn("status_light", self.client.get(url).context["form"].fields)
        for compliance, light in (("95", "green"), ("80", "green"), ("70", "amber"), ("59.9", "red")):
            with self.subTest(compliance=compliance):
                response = self.client.post(
                    url,
                    {"goal": goal.pk, "progress": "10", "compliance": compliance, "weighting": "100"},
                )
                self.assertEqual(response.status_code, 302)
                created = Indicator.objects.filter(goal=goal).order_by("-pk").first()
                self.assertEqual(created.status_light, light)

    def test_editing_the_indicator_recalculates_its_light(self):
        self.login_as("admin")
        indicator = Indicator.objects.get(status_light="amber")
        response = self.client.post(
            reverse("core:indicadores_update", args=[indicator.pk]),
            {
                "goal": indicator.goal_id,
                "progress": indicator.progress,
                "compliance": "85",
                "weighting": indicator.weighting,
            },
        )
        self.assertEqual(response.status_code, 302)
        indicator.refresh_from_db()
        self.assertEqual(indicator.status_light, "green")


class ValidationFlowTests(PortalTestCase):
    def evidence(self, code):
        return Evidence.objects.get(unique_code=code)

    def review_url(self, code):
        return reverse("core:validate_evidence", args=[self.evidence(code).pk])

    def test_list_shows_only_pending_evidence_of_the_delegation(self):
        self.login_as("matias.cavieres")
        response = self.client.get(reverse("core:validate_list"))
        codes = {item["evidence"].unique_code for item in response.context["items"]}
        self.assertEqual(codes, {"EVD-NORTE-0001"})

        self.login_as("matias.quiroz")
        response = self.client.get(reverse("core:validate_list"))
        codes = {item["evidence"].unique_code for item in response.context["items"]}
        self.assertTrue(codes)
        self.assertTrue(all(code.startswith("EVD-SUR-") for code in codes))

    def test_approve_updates_evidence_and_records_the_reviewer(self):
        self.login_as("matias.cavieres")
        evidence = self.evidence("EVD-NORTE-0001")
        response = self.client.post(
            self.review_url("EVD-NORTE-0001"),
            {"decision": "approved", "result": "Evidencia conforme", "notes": ""},
        )
        self.assertRedirects(response, reverse("core:evidencias_detail", args=[evidence.pk]))
        evidence.refresh_from_db()
        self.assertEqual(evidence.review_status, Evidence.ReviewStatus.APPROVED)
        validation = Validation.objects.get(evidence=evidence, result="Evidencia conforme")
        self.assertEqual(validation.reviewer_officer, self.officer("F-1001"))
        self.assertEqual(validation.decision, Validation.Decision.APPROVED)
        log = AuditLog.objects.get(event="Evidencia validada", record_id=evidence.pk)
        self.assertIn("review_status=approved", log.new_value)
        listed = self.client.get(reverse("core:validate_list")).context["items"]
        self.assertEqual(listed, [])

    def test_flagged_needs_a_reason_and_keeps_evidence_pending(self):
        self.login_as("matias.cavieres")
        evidence = self.evidence("EVD-NORTE-0001")
        before = Validation.objects.count()
        response = self.client.post(
            self.review_url("EVD-NORTE-0001"),
            {"decision": "flagged", "result": "Falta el sello", "notes": "  "},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("notes", response.context["form"].errors)
        self.assertEqual(Validation.objects.count(), before)

        response = self.client.post(
            self.review_url("EVD-NORTE-0001"),
            {"decision": "flagged", "result": "Falta el sello", "notes": "Adjuntar el sello municipal."},
        )
        self.assertRedirects(response, reverse("core:evidencias_detail", args=[evidence.pk]))
        evidence.refresh_from_db()
        self.assertEqual(evidence.review_status, Evidence.ReviewStatus.PENDING)
        self.assertEqual(Validation.objects.count(), before + 1)
        item = self.client.get(reverse("core:validate_list")).context["items"][0]
        self.assertTrue(item["flagged"])

    def test_reject_needs_a_reason_and_marks_evidence_rejected(self):
        self.login_as("matias.cavieres")
        evidence = self.evidence("EVD-NORTE-0001")
        response = self.client.post(
            self.review_url("EVD-NORTE-0001"), {"decision": "rejected", "result": "No cumple", "notes": ""}
        )
        self.assertEqual(response.status_code, 200)
        response = self.client.post(
            self.review_url("EVD-NORTE-0001"),
            {"decision": "rejected", "result": "No cumple", "notes": "El archivo no corresponde."},
        )
        self.assertEqual(response.status_code, 302)
        evidence.refresh_from_db()
        self.assertEqual(evidence.review_status, Evidence.ReviewStatus.REJECTED)

    def test_result_and_decision_are_required_and_limited(self):
        self.login_as("matias.cavieres")
        before = Validation.objects.count()
        for data in (
            {"decision": "approved", "result": "", "notes": ""},
            {"decision": "", "result": "Algo", "notes": ""},
            {"decision": "inventada", "result": "Algo", "notes": ""},
            {"decision": "approved", "result": "x" * 51, "notes": ""},
        ):
            with self.subTest(data=data):
                response = self.client.post(self.review_url("EVD-NORTE-0001"), data)
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context["form"].errors)
        self.assertEqual(Validation.objects.count(), before)

    def test_reviewer_is_not_chosen_it_is_the_logged_in_officer(self):
        self.login_as("matias.cavieres")
        response = self.client.get(self.review_url("EVD-NORTE-0001"))
        self.assertNotIn("reviewer_officer", response.context["form"].fields)
        response = self.client.post(
            self.review_url("EVD-NORTE-0001"),
            {
                "decision": "approved",
                "result": "Conforme",
                "reviewer_officer": self.officer("F-2001").pk,
            },
        )
        self.assertEqual(response.status_code, 302)
        validation = Validation.objects.get(result="Conforme")
        self.assertEqual(validation.reviewer_officer, self.officer("F-1001"))

    def test_superuser_validates_without_choosing_and_is_shown_as_super_user(self):
        self.login_as("admin")
        url = self.review_url("EVD-NORTE-0001")
        self.assertNotIn("reviewer_officer", self.client.get(url).context["form"].fields)
        ok = self.client.post(url, {"decision": "approved", "result": "Conforme", "notes": ""})
        self.assertEqual(ok.status_code, 302)
        validation = Validation.objects.get(result="Conforme")
        self.assertIsNone(validation.reviewer_officer)
        self.assertEqual(validation.reviewer_name, "Super Usuario")
        page = self.client.get(url)
        self.assertContains(page, "Por Super Usuario")

    def test_nobody_validates_their_own_evidence(self):
        evidence = self.evidence("EVD-NORTE-0001")
        evidence.author_officer = self.officer("F-1001")
        evidence.save()
        self.login_as("matias.cavieres")
        before = Validation.objects.count()
        response = self.client.post(
            self.review_url("EVD-NORTE-0001"), {"decision": "approved", "result": "Conforme", "notes": ""}
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(Validation.objects.count(), before)
        listed = self.client.get(reverse("core:validate_list")).context["items"]
        self.assertNotIn("EVD-NORTE-0001", [item["evidence"].unique_code for item in listed])
        detail = self.client.get(reverse("core:evidencias_detail", args=[evidence.pk]))
        self.assertNotContains(detail, reverse("core:validate_evidence", args=[evidence.pk]))

    def test_verifier_without_officer_cannot_validate(self):
        user = User.objects.create_user("verificador.suelto", password=PASSWORD)
        user.groups.add(Group.objects.get(name="Verificador"))
        self.client.force_login(user)
        evidence = self.evidence("EVD-NORTE-0001")
        self.assertEqual(
            self.client.get(reverse("core:validate_evidence", args=[evidence.pk])).status_code, 403
        )

    def test_user_without_validation_permission_is_refused(self):
        self.login_as("jefatura1")
        response = self.client.post(
            self.review_url("EVD-NORTE-0001"), {"decision": "approved", "result": "Conforme"}
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Validation.objects.filter(result="Conforme").exists())

    def test_archived_evidence_cannot_be_validated(self):
        self.login_as("admin")
        archived = Evidence.objects.filter(deleted_at__isnull=False).first()
        self.assertIsNotNone(archived)
        response = self.client.get(reverse("core:validate_evidence", args=[archived.pk]))
        self.assertEqual(response.status_code, 404)


class BoardAndReportTests(PortalTestCase):
    def read_csv(self, response):
        text = response.content.decode("utf-8-sig")
        return list(csv.DictReader(StringIO(text), delimiter=";"))

    def test_board_calculates_each_officers_average_and_light(self):
        self.login_as("admin")
        response = self.client.get(reverse("core:delegation_board"), {"delegacion": self.north.pk})
        self.assertEqual(response.status_code, 200)
        by_name = {row["officer"].name: row for row in response.context["results"]}
        cavieres = by_name["Matías Cavieres"]
        self.assertEqual(cavieres["average"], Decimal("40.0"))
        self.assertEqual(cavieres["light"], "red")
        self.assertEqual(cavieres["goal_total"], 2)
        self.assertEqual(by_name["Diego Fuentes"]["average"], None)
        self.assertEqual(response.context["average"], Decimal("25.0"))

    def test_board_period_choice_falls_back_to_the_current_one(self):
        self.login_as("admin")
        current = Period.objects.get(status="active")
        for value in ("", "abc", "999999"):
            with self.subTest(value=value):
                response = self.client.get(reverse("core:delegation_board"), {"periodo": value})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.context["period"], current)
        closed = Period.objects.exclude(pk=current.pk).get(status="closed")
        response = self.client.get(reverse("core:delegation_board"), {"periodo": closed.pk})
        self.assertEqual(response.context["period"], closed)

    def test_report_page_and_csv_for_all_delegations(self):
        self.login_as("coordinacion1")
        page = self.client.get(reverse("core:reports"))
        self.assertEqual(page.status_code, 200)
        self.assertEqual(page.context["totals"]["approved"], 2)
        response = self.client.get(reverse("core:reports"), {"formato": "csv"})
        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn("attachment; filename=\"informe-sgr-", response["Content-Disposition"])
        self.assertTrue(response.content.startswith("﻿".encode("utf-8")))
        rows = self.read_csv(response)
        self.assertEqual(
            len(rows), Officer.objects.filter(status="active", deleted_at__isnull=True).count()
        )
        quiroz = next(row for row in rows if row["Funcionario"] == "Matías Quiroz")
        self.assertEqual(quiroz["Cumplimiento promedio (%)"], "52,5")

    def test_csv_cells_cannot_become_spreadsheet_formulas(self):
        for text in ("=SUMA(A1)", "+56911111111", "-1+1", "@cmd"):
            with self.subTest(text=text):
                self.assertEqual(safe_cell(text), "'" + text)
        self.assertEqual(safe_cell("María"), "María")
        self.assertEqual(safe_cell(None), "")

    def test_report_without_periods_does_not_break(self):
        Period.objects.update(deleted_at=timezone.now())
        self.login_as("admin")
        for url in (reverse("core:reports"), reverse("core:delegation_board"), reverse("core:dashboard")):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)


class CacheHeaderTests(PortalTestCase):
    def test_portal_pages_ask_the_browser_not_to_store_them(self):
        self.login_as("admin")
        for url in (reverse("core:dashboard"), reverse("core:atencion"), reverse("core:login")):
            with self.subTest(url=url):
                self.assertIn("no-store", self.client.get(url)["Cache-Control"])

    def test_admin_keeps_its_own_cache_rules(self):
        self.login_as("admin")
        response = self.client.get("/admin/")
        self.assertNotEqual(response.get("Cache-Control", ""), "")
        self.assertEqual(response.status_code, 200)


class SweepTests(PortalTestCase):

    def test_every_page_answers_200_or_403_for_every_role(self):
        for username in ALL_USERS:
            self.login_as(username)
            for crud in registry.all():
                with self.subTest(username=username, crud=crud.slug):
                    response = self.client.get(crud.url("list"))
                    self.assertIn(response.status_code, (200, 403))
                    if response.status_code == 200 and response.context["rows"]:
                        row = response.context["rows"][0]
                        self.assertEqual(self.client.get(row.detail_url).status_code, 200)
                        if row.edit_url:
                            self.assertEqual(self.client.get(row.edit_url).status_code, 200)
                        if row.archive_url:
                            self.assertEqual(self.client.get(row.archive_url).status_code, 200)
                    if crud.allow_add:
                        self.assertIn(self.client.get(crud.url("create")).status_code, (200, 403))
            for name in ("dashboard", "validate_list", "delegation_board", "reports", "administration"):
                with self.subTest(username=username, page=name):
                    self.assertIn(self.client.get(reverse(f"core:{name}")).status_code, (200, 403))

    def test_superuser_sees_every_list_with_data(self):
        self.login_as("admin")
        for crud in registry.all():
            with self.subTest(crud=crud.slug):
                response = self.client.get(crud.url("list"))
                self.assertEqual(response.status_code, 200)
                self.assertGreater(response.context["page"].paginator.count, 0)

    def test_archived_records_are_listed_only_on_request(self):
        self.login_as("admin")
        archived = Activity.objects.filter(deleted_at__isnull=False).first()
        url = reverse("core:atencion")
        normal = {row.obj.pk for row in self.client.get(url).context["rows"]}
        extra = {row.obj.pk for row in self.client.get(url, {"archivados": "1"}).context["rows"]}
        self.assertNotIn(archived.pk, normal)
        self.assertIn(archived.pk, extra)
        detail = self.client.get(reverse("core:actividades_detail", args=[archived.pk]))
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, "Este registro está archivado")
        self.assertFalse(detail.context["can_edit"])


class UiHelperTests(SimpleTestCase):
    def test_numbers_use_comma_and_dots(self):
        self.assertEqual(ui.fmt_number(Decimal("52.50")), "52,5")
        self.assertEqual(ui.fmt_number(Decimal("80.00")), "80")
        self.assertEqual(ui.fmt_number(1250.5), "1.250,5")
        self.assertEqual(ui.fmt_number(Decimal("-8.00")), "-8")
        self.assertEqual(ui.fmt_number(None), "")

    def test_iso_dates_become_day_month_year(self):
        self.assertEqual(
            ui.humanize_dates("Actividad 2026-10-06 · María"), "Actividad 06/10/2026 · María"
        )
        self.assertEqual(
            ui.humanize_dates("Período 2026-01-01 – 2026-12-31"), "Período 01/01/2026 – 31/12/2026"
        )
        self.assertEqual(ui.humanize_dates("Sin fechas"), "Sin fechas")

    def test_semaphore_uses_the_period_thresholds(self):
        thresholds = (Decimal("80"), Decimal("60"))
        self.assertEqual(ui.light_for_compliance(Decimal("80"), *thresholds), "green")
        self.assertEqual(ui.light_for_compliance(Decimal("79.9"), *thresholds), "amber")
        self.assertEqual(ui.light_for_compliance(Decimal("60"), *thresholds), "amber")
        self.assertEqual(ui.light_for_compliance(Decimal("59.9"), *thresholds), "red")

    def test_meter_bar_stays_inside_the_scale_but_shows_the_real_value(self):
        from core.templatetags.core_ui import meter

        over = meter(Decimal("150"), "green", Decimal("80"), Decimal("60"))
        self.assertEqual(over["raw"], "100.00")
        self.assertEqual(over["width"], "100.00")
        self.assertEqual(over["text"], "150 %")
        under = meter(Decimal("-5"), "red", Decimal("80"), Decimal("60"))
        self.assertEqual(under["raw"], "0.00")

    def test_unknown_values_get_a_neutral_tone(self):
        self.assertEqual(ui.tone_for("no_existe"), ("neutral", ""))
        self.assertEqual(ui.tone_for("approved")[0], "ok")
        self.assertEqual(ui.tone_for("rejected")[0], "bad")
