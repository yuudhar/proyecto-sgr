"""Versión 40: cambio de trimestre de una atención, que pide un funcionario y resuelve Jefatura."""
from datetime import timedelta

from django.contrib.auth.models import Group, User
from django.urls import reverse
from django.utils import timezone

from core.models import AuditLog
from core.testing import PortalTestCase, portal_today
from operations.models import Activity, QuarterChangeRequest
from operations.quarters import next_period, period_of
from organization.models import Officer
from planning.models import Period

Mode = QuarterChangeRequest.Mode
Status = QuarterChangeRequest.Status


class QuarterBase(PortalTestCase):
    """Cuatro trimestres alrededor de hoy: uno cerrado, el de la atención, el actual y uno que aún no empieza."""

    def setUp(self):
        today = portal_today()
        QuarterChangeRequest.objects.all().delete()  # la demostración trae una; cada prueba parte de cero
        Period.objects.update(deleted_at=timezone.now())
        self.closed = Period.objects.create(
            start_date=today - timedelta(days=170), end_date=today - timedelta(days=81),
            computable_days=60, status=Period.Status.CLOSED,
        )
        self.first = Period.objects.create(
            start_date=today - timedelta(days=80), end_date=today - timedelta(days=31),
            computable_days=40, status=Period.Status.ACTIVE,
        )
        self.second = Period.objects.create(
            start_date=today - timedelta(days=30), end_date=today + timedelta(days=59),
            computable_days=60, status=Period.Status.ACTIVE,
        )
        self.third = Period.objects.create(
            start_date=today + timedelta(days=60), end_date=today + timedelta(days=149),
            computable_days=60, status=Period.Status.PLANNED,
        )
        self.today = today
        self.cavieres = self.officer("F-1001")
        self.south_officer = self.officer("F-2001")
        self.clerk = User.objects.get(username="matias.cavieres")
        self.boss = User.objects.get(username="jefatura1")
        self.south_boss = self.make_user("jefatura_sur", ["Jefatura"], self.officer("F-2005"))
        self.activity_in_first = self.make_activity(today - timedelta(days=40), "Rosa Primer Trimestre")

    def make_activity(self, day, name, officer=None, delegation=None):
        base = Activity.objects.filter(delegation=self.north).first()
        return Activity.objects.create(
            date=day,
            item=base.item,
            contact_name=name,
            phone="+56 9 1111 1111",
            request_description="Atención de prueba",
            delegation=delegation or self.north,
            author_officer=officer or self.cavieres,
        )

    def ask(self, activity=None, **changes):
        data = {
            "activity": (activity or self.activity_in_first).pk,
            "mode": Mode.AUTOMATIC,
            "new_date": "",
            "reason": "La atención cayó en un feriado y se registró después.",
        }
        data.update(changes)
        return self.client.post(reverse("core:cambios_trimestre_create"), data)

    def request_for(self, activity=None, **changes):
        values = {
            "activity": activity or self.activity_in_first,
            "delegation": self.north,
            "mode": Mode.MANUAL,
            "previous_date": (activity or self.activity_in_first).date,
            "new_date": self.today - timedelta(days=20),
            "reason": "Motivo de prueba",
            "requested_by": self.clerk,
        }
        values.update(changes)
        return QuarterChangeRequest.objects.create(**values)

    def resolve(self, request_, status, comment=""):
        return self.client.post(
            reverse("core:cambios_trimestre_update", args=[request_.pk]),
            {"status": status, "resolution_comment": comment},
        )

    def columns(self, response):
        return {column["label"]: column["cards"] for column in response.context["board"]["columns"]}


class QuarterHelpersTests(QuarterBase):

    def test_a_date_belongs_to_the_period_that_contains_it_and_archived_periods_do_not_count(self):
        self.assertEqual(period_of(self.today - timedelta(days=40)), self.first)
        self.assertEqual(period_of(self.today), self.second)
        self.assertEqual(period_of(self.today - timedelta(days=300)), None)
        self.second.deleted_at = timezone.now()
        self.second.save()
        self.assertIsNone(period_of(self.today))

    def test_the_next_period_is_the_first_one_that_starts_after_the_end(self):
        self.assertEqual(next_period(self.first), self.second)
        self.assertEqual(next_period(self.second), self.third)
        self.assertIsNone(next_period(self.third))


class QuarterRequestTests(QuarterBase):

    def test_the_menu_and_the_screen_open_for_a_clerk(self):
        self.client.force_login(self.clerk)
        response = self.client.get(reverse("core:cambios_trimestre_list"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("Cambios de trimestre", self.menu_labels(response))

    def test_an_automatic_request_takes_the_first_day_of_the_next_trimestre(self):
        self.client.force_login(self.clerk)
        response = self.ask()
        self.assertEqual(response.status_code, 302)
        found = QuarterChangeRequest.objects.get()
        self.assertEqual(found.new_date, self.second.start_date)
        self.assertEqual(found.previous_date, self.activity_in_first.date)
        self.assertEqual(found.status, Status.PENDING)
        self.assertEqual(found.requested_by, self.clerk)
        self.assertEqual(found.delegation, self.north)

    def test_asking_does_not_move_the_attention(self):
        self.client.force_login(self.clerk)
        self.ask()
        self.activity_in_first.refresh_from_db()
        self.assertEqual(self.activity_in_first.date, self.today - timedelta(days=40))

    def test_a_manual_request_keeps_the_chosen_date(self):
        self.client.force_login(self.clerk)
        chosen = self.today - timedelta(days=12)
        self.ask(mode=Mode.MANUAL, new_date=chosen.isoformat())
        self.assertEqual(QuarterChangeRequest.objects.get().new_date, chosen)

    def test_an_automatic_request_ignores_a_date_sent_by_hand(self):
        self.client.force_login(self.clerk)
        self.ask(mode=Mode.AUTOMATIC, new_date=(self.today - timedelta(days=5)).isoformat())
        self.assertEqual(QuarterChangeRequest.objects.get().new_date, self.second.start_date)

    def test_automatic_is_refused_when_the_next_trimestre_has_not_started(self):
        activity = self.make_activity(self.today - timedelta(days=5), "Rosa Del Trimestre Actual")
        self.client.force_login(self.clerk)
        response = self.ask(activity)
        self.assertContains(response, "no puede ser futura")
        self.assertFalse(QuarterChangeRequest.objects.exists())

    def test_automatic_is_refused_when_there_is_no_next_trimestre(self):
        self.third.deleted_at = timezone.now()
        self.third.save()
        activity = self.make_activity(self.today - timedelta(days=5), "Rosa Sin Siguiente")
        self.client.force_login(self.clerk)
        response = self.ask(activity)
        self.assertContains(response, "Todavía no hay un trimestre siguiente")

    def test_automatic_is_refused_when_the_attention_is_in_no_trimestre(self):
        activity = self.make_activity(self.today - timedelta(days=300), "Rosa Sin Trimestre")
        self.client.force_login(self.clerk)
        response = self.ask(activity)
        self.assertContains(response, "no cae en ningún trimestre")

    def test_a_manual_date_in_the_same_trimestre_is_refused(self):
        self.client.force_login(self.clerk)
        response = self.ask(mode=Mode.MANUAL, new_date=(self.today - timedelta(days=60)).isoformat())
        self.assertContains(response, "mismo trimestre")
        self.assertFalse(QuarterChangeRequest.objects.exists())

    def test_a_manual_date_in_the_future_is_refused(self):
        self.client.force_login(self.clerk)
        response = self.ask(mode=Mode.MANUAL, new_date=(self.today + timedelta(days=70)).isoformat())
        self.assertContains(response, "no puede ser futura")

    def test_a_manual_date_without_trimestre_is_refused(self):
        self.client.force_login(self.clerk)
        response = self.ask(mode=Mode.MANUAL, new_date=(self.today - timedelta(days=300)).isoformat())
        self.assertContains(response, "no cae en ningún trimestre")

    def test_a_closed_trimestre_cannot_receive_attentions(self):
        activity = self.make_activity(self.today - timedelta(days=5), "Rosa Hacia Atrás")
        self.client.force_login(self.clerk)
        response = self.ask(activity, mode=Mode.MANUAL, new_date=(self.today - timedelta(days=100)).isoformat())
        self.assertContains(response, "ya está cerrado")

    def test_a_manual_request_needs_the_date_and_every_request_the_reason(self):
        self.client.force_login(self.clerk)
        response = self.ask(mode=Mode.MANUAL, new_date="")
        self.assertContains(response, "Elige la fecha nueva")
        response = self.ask(reason="")
        self.assertContains(response, "Este campo es obligatorio.")
        self.assertFalse(QuarterChangeRequest.objects.exists())

    def test_an_attention_with_a_pending_request_cannot_have_another(self):
        self.request_for()
        self.client.force_login(self.clerk)
        response = self.ask()
        self.assertContains(response, "ya tiene una solicitud de cambio de trimestre pendiente")
        self.assertEqual(QuarterChangeRequest.objects.count(), 1)

    def test_after_a_rejection_a_new_request_is_allowed(self):
        self.request_for(status=Status.REJECTED)
        self.client.force_login(self.clerk)
        self.ask()
        self.assertEqual(QuarterChangeRequest.objects.count(), 2)

    def test_an_archived_attention_is_not_offered(self):
        self.activity_in_first.deleted_at = timezone.now()
        self.activity_in_first.save()
        self.client.force_login(self.clerk)
        response = self.ask()
        self.assertEqual(response.status_code, 200)
        self.assertFalse(QuarterChangeRequest.objects.exists())

    def test_an_attention_of_another_delegation_is_not_offered(self):
        other = self.make_activity(self.today - timedelta(days=40), "Vecina Del Sur", self.south_officer, self.south)
        self.client.force_login(self.clerk)
        response = self.ask(other)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(QuarterChangeRequest.objects.exists())

    def test_the_form_shows_the_date_only_in_manual_mode(self):
        self.client.force_login(self.clerk)
        response = self.client.get(reverse("core:cambios_trimestre_create"))
        self.assertContains(response, 'data-show-if="id_mode:manual"')
        self.assertContains(response, "data-required-when-shown")


class QuarterResolutionTests(QuarterBase):

    def test_approving_moves_the_attention_to_the_new_trimestre(self):
        asked = self.request_for(mode=Mode.AUTOMATIC, new_date=self.second.start_date)
        self.client.force_login(self.boss)
        response = self.resolve(asked, Status.APPROVED, "De acuerdo.")
        self.assertEqual(response.status_code, 302)
        asked.refresh_from_db()
        self.activity_in_first.refresh_from_db()
        self.assertEqual(asked.status, Status.APPROVED)
        self.assertEqual(self.activity_in_first.date, self.second.start_date)
        self.assertEqual(period_of(self.activity_in_first.date), self.second)
        self.assertEqual(asked.resolved_by, self.boss)
        self.assertIsNotNone(asked.resolved_at)
        self.assertEqual(asked.resolution_comment, "De acuerdo.")

    def test_approving_leaves_a_trace_in_the_audit_log(self):
        asked = self.request_for()
        self.client.force_login(self.boss)
        self.resolve(asked, Status.APPROVED)
        trace = AuditLog.objects.filter(event="Cambio de trimestre aprobado", record_id=self.activity_in_first.pk).first()
        self.assertIsNotNone(trace)
        self.assertEqual(trace.user, self.boss)
        self.assertTrue(AuditLog.objects.filter(event="Registro modificado", affected_entity="QuarterChangeRequest").exists())

    def test_rejecting_needs_a_reason_and_keeps_the_date(self):
        asked = self.request_for()
        self.client.force_login(self.boss)
        response = self.resolve(asked, Status.REJECTED, "")
        self.assertContains(response, "Explica por qué se rechaza")
        asked.refresh_from_db()
        self.assertEqual(asked.status, Status.PENDING)
        self.resolve(asked, Status.REJECTED, "Esa semana ya estaba cerrada.")
        asked.refresh_from_db()
        self.activity_in_first.refresh_from_db()
        self.assertEqual(asked.status, Status.REJECTED)
        self.assertEqual(asked.resolved_by, self.boss)
        self.assertEqual(self.activity_in_first.date, self.today - timedelta(days=40))

    def test_approving_may_go_without_a_comment(self):
        asked = self.request_for()
        self.client.force_login(self.boss)
        self.resolve(asked, Status.APPROVED, "")
        asked.refresh_from_db()
        self.assertEqual(asked.status, Status.APPROVED)

    def test_a_clerk_cannot_resolve_requests(self):
        asked = self.request_for()
        self.client.force_login(self.clerk)
        self.assertEqual(self.resolve(asked, Status.APPROVED).status_code, 403)
        asked.refresh_from_db()
        self.assertEqual(asked.status, Status.PENDING)

    def test_a_boss_of_another_delegation_cannot_resolve(self):
        asked = self.request_for()
        self.client.force_login(self.south_boss)
        self.assertIn(self.resolve(asked, Status.APPROVED).status_code, (403, 404))
        asked.refresh_from_db()
        self.assertEqual(asked.status, Status.PENDING)

    def test_a_resolved_request_cannot_be_resolved_again(self):
        asked = self.request_for()
        self.client.force_login(self.boss)
        self.resolve(asked, Status.REJECTED, "No corresponde.")
        self.assertEqual(self.resolve(asked, Status.APPROVED).status_code, 403)
        asked.refresh_from_db()
        self.assertEqual(asked.status, Status.REJECTED)

    def test_approval_is_refused_when_the_day_is_full(self):
        new_day = self.today - timedelta(days=20)
        for number in range(7):
            self.make_activity(new_day, f"Lleno {number}")
        asked = self.request_for(new_date=new_day)
        self.client.force_login(self.boss)
        response = self.resolve(asked, Status.APPROVED)
        self.assertContains(response, "el máximo es 7 por día")
        asked.refresh_from_db()
        self.assertEqual(asked.status, Status.PENDING)

    def test_approval_is_refused_when_the_attention_changed_its_date_meanwhile(self):
        asked = self.request_for()
        Activity.objects.filter(pk=self.activity_in_first.pk).update(date=self.today - timedelta(days=45))
        self.client.force_login(self.boss)
        response = self.resolve(asked, Status.APPROVED)
        self.assertContains(response, "cambió de fecha")
        asked.refresh_from_db()
        self.assertEqual(asked.status, Status.PENDING)

    def test_approval_is_refused_when_the_target_was_closed_meanwhile(self):
        asked = self.request_for()
        Period.objects.filter(pk=self.second.pk).update(status=Period.Status.CLOSED)
        self.client.force_login(self.boss)
        response = self.resolve(asked, Status.APPROVED)
        self.assertContains(response, "ya no está disponible")
        asked.refresh_from_db()
        self.assertEqual(asked.status, Status.PENDING)

    def test_the_resolution_form_summarizes_the_request(self):
        asked = self.request_for()
        self.client.force_login(self.boss)
        response = self.client.get(reverse("core:cambios_trimestre_update", args=[asked.pk]))
        self.assertContains(response, "Motivo de prueba")
        self.assertContains(response, "Rosa Primer Trimestre")
        self.assertContains(response, "Respuesta")


class QuarterScreenTests(QuarterBase):

    def test_the_list_is_a_board_with_pending_approved_and_rejected(self):
        self.request_for()
        other = self.make_activity(self.today - timedelta(days=41), "Rosa Aprobada")
        self.request_for(other, status=Status.APPROVED)
        self.client.force_login(self.boss)
        response = self.client.get(reverse("core:cambios_trimestre_list"))
        columns = self.columns(response)
        self.assertEqual(list(columns), ["Pendiente", "Aprobada", "Rechazada"])
        self.assertEqual(len(columns["Pendiente"]), 1)
        self.assertEqual(len(columns["Aprobada"]), 1)
        self.assertEqual(len(columns["Rechazada"]), 0)
        kpis = {kpi["label"]: kpi["value"] for kpi in response.context["board"]["kpis"]}
        self.assertEqual((kpis["Solicitudes"], kpis["Pendientes"], kpis["Aprobadas"], kpis["Rechazadas"]), (2, 1, 1, 0))
        self.assertTrue(all(card["code"].startswith("TRI") for card in columns["Pendiente"]))

    def test_each_delegation_sees_only_its_own_requests(self):
        self.request_for()
        self.client.force_login(self.south_boss)
        response = self.client.get(reverse("core:cambios_trimestre_list"))
        self.assertEqual(sum(len(cards) for cards in self.columns(response).values()), 0)

    def test_only_the_boss_gets_the_edit_button_and_only_while_pending(self):
        asked = self.request_for()
        self.client.force_login(self.clerk)
        card = self.columns(self.client.get(reverse("core:cambios_trimestre_list")))["Pendiente"][0]
        self.assertFalse(card["row"].edit_url)
        self.client.force_login(self.boss)
        card = self.columns(self.client.get(reverse("core:cambios_trimestre_list")))["Pendiente"][0]
        self.assertTrue(card["row"].edit_url)
        self.resolve(asked, Status.REJECTED, "No corresponde.")
        card = self.columns(self.client.get(reverse("core:cambios_trimestre_list")))["Rechazada"][0]
        self.assertFalse(card["row"].edit_url)

    def test_the_detail_names_the_current_and_the_target_trimestre(self):
        asked = self.request_for()
        self.client.force_login(self.boss)
        response = self.client.get(reverse("core:cambios_trimestre_detail", args=[asked.pk]))
        self.assertContains(response, "Trimestre actual")
        self.assertContains(response, "Trimestre de destino")

    def test_the_attention_page_lists_its_requests(self):
        self.request_for()
        self.client.force_login(self.boss)
        response = self.client.get(reverse("core:actividades_detail", args=[self.activity_in_first.pk]))
        self.assertContains(response, "Cambios de trimestre")

    def test_a_user_who_can_only_view_cannot_ask(self):
        viewer = self.make_user("consulta_norte", ["Consulta"], self.officer("F-1004"))
        self.give_perm(viewer, "operations.view_quarterchangerequest")
        self.client.force_login(viewer)
        self.assertEqual(self.client.get(reverse("core:cambios_trimestre_list")).status_code, 200)
        self.assertEqual(self.client.get(reverse("core:cambios_trimestre_create")).status_code, 403)

    def test_a_user_without_permission_gets_403(self):
        outsider = self.make_user("sin_permisos", [], self.officer("F-1004"))
        self.client.force_login(outsider)
        self.assertEqual(self.client.get(reverse("core:cambios_trimestre_list")).status_code, 403)

    def test_the_roles_give_funcionario_to_ask_and_jefatura_to_resolve(self):
        funcionario = {p.codename for p in Group.objects.get(name="Funcionario").permissions.all()}
        jefatura = {p.codename for p in Group.objects.get(name="Jefatura").permissions.all()}
        self.assertIn("add_quarterchangerequest", funcionario)
        self.assertNotIn("change_quarterchangerequest", funcionario)
        self.assertIn("change_quarterchangerequest", jefatura)
        self.assertNotIn("add_quarterchangerequest", jefatura)

    def test_the_roles_screen_lists_the_module(self):
        from core.roles import PERMISSION_MODULES

        labels = [label for _, rows in PERMISSION_MODULES for label, _ in rows]
        self.assertIn("Cambios de trimestre", labels)

    def test_the_request_is_in_the_live_models(self):
        from websocket.signals import LIVE_MODELS

        self.assertIn("operations.QuarterChangeRequest", LIVE_MODELS)
