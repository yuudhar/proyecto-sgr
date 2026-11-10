"""Versión 28: códigos automáticos, selector con buscador, gráficos y respaldo del tiempo real."""
import importlib.util
import shutil
import subprocess
import unittest
from unittest import mock

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import SimpleTestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from core import charts
from core.datos_prueba import demo_pdf
from core.testing import PortalTestCase
from evidence.models import Evidence
from operations.models import Activity, Followup, ManagementType


class AutomaticCodeTests(PortalTestCase):

    def upload(self, activity):
        return {
            "activity": activity.pk,
            "author_officer": self.officer("F-1001").pk,
            "file_link": SimpleUploadedFile("informe.pdf", demo_pdf("prueba"), content_type="application/pdf"),
        }

    def north_activity(self):
        return Activity.objects.filter(delegation=self.north, deleted_at__isnull=True).first()

    def test_the_evidence_form_does_not_ask_for_the_code(self):
        self.login_as("matias.cavieres")
        form = self.client.get(reverse("core:evidencias_create")).context["form"]
        self.assertNotIn("unique_code", form.fields)

    def test_each_evidence_takes_the_next_code_of_its_delegation(self):
        self.login_as("matias.cavieres")
        for expected in ("EVD-NORTE-0004", "EVD-NORTE-0005"):
            response = self.client.post(reverse("core:evidencias_create"), self.upload(self.north_activity()))
            self.assertEqual(response.status_code, 302)
            self.assertTrue(Evidence.objects.filter(unique_code=expected).exists(), expected)

    def test_archived_evidences_still_count_so_a_code_is_never_reused(self):
        self.login_as("admin")
        last = Evidence.objects.get(unique_code="EVD-NORTE-0003")
        last.deleted_at = last.created_at
        last.save()
        new = Evidence.objects.create(file_link="x", activity=self.north_activity(), author_officer=self.officer("F-1001"))
        self.assertEqual(new.unique_code, "EVD-NORTE-0004")

    def test_a_code_taken_in_the_meantime_is_skipped(self):
        activity = self.north_activity()
        with mock.patch.object(Evidence, "next_code", side_effect=["EVD-NORTE-0001", "EVD-NORTE-0099"]):
            new = Evidence.objects.create(file_link="x", activity=activity, author_officer=self.officer("F-1001"))
        self.assertEqual(new.unique_code, "EVD-NORTE-0099")

    def test_a_code_written_by_hand_in_code_is_respected(self):
        new = Evidence.objects.create(
            unique_code="EVD-NORTE-5000", file_link="x", activity=self.north_activity(), author_officer=self.officer("F-1001")
        )
        self.assertEqual(new.unique_code, "EVD-NORTE-5000")

    def test_the_followup_number_is_assigned_by_the_system_up_to_three(self):
        self.login_as("matias.cavieres")
        activity = self.activity("María Pérez")
        Followup.objects.filter(activity=activity).delete()
        base = {
            "activity": activity.pk,
            "management_type": ManagementType.objects.first().pk,
            "date": activity.date.isoformat(),
            "result": "Se llamó por teléfono.",
        }
        for number in (1, 2, 3):
            response = self.client.post(reverse("core:gestiones_create"), base)
            self.assertEqual(response.status_code, 302)
            self.assertTrue(Followup.objects.filter(activity=activity, sequence_number=number).exists(), number)
        response = self.client.post(reverse("core:gestiones_create"), base)
        self.assertEqual(response.status_code, 200)
        self.assertIn("ya tiene sus 3 gestiones", " ".join(response.context["form"].errors["activity"]))
        self.assertEqual(Followup.objects.filter(activity=activity).count(), 3)

    def test_the_activity_is_preselected_when_coming_from_its_detail(self):
        self.login_as("matias.cavieres")
        activity = self.activity("María Pérez")
        for name in ("core:evidencias_create", "core:gestiones_create"):
            response = self.client.get(reverse(name), {"activity": activity.pk})
            self.assertEqual(str(response.context["form"].initial["activity"]), str(activity.pk), name)


class SearchableSelectTests(PortalTestCase):

    def select_tag(self, page, name):
        start = page.index(f'name="{name}"')
        begin = page.rfind("<select", 0, start)
        return page[begin : page.index(">", start)]

    def test_selects_of_related_records_can_be_searched(self):
        self.login_as("matias.cavieres")
        for url, field in (
            ("core:evidencias_create", "activity"),
            ("core:evidencias_create", "author_officer"),
            ("core:gestiones_create", "activity"),
        ):
            page = self.client.get(reverse(url)).content.decode()
            self.assertIn("data-searchable", self.select_tag(page, field), (url, field))

    def test_the_list_filters_can_be_searched_too(self):
        self.login_as("admin")
        page = self.client.get(reverse("core:atencion")).content.decode()
        self.assertIn("data-searchable", page[page.index('id="filtro-'):][:300])

    def test_the_activity_choices_name_the_item_and_do_not_add_queries_per_activity(self):
        self.login_as("matias.cavieres")
        url = reverse("core:evidencias_create")
        with CaptureQueriesContext(connection) as before:
            response = self.client.get(url)
        field = response.context["form"].fields["activity"]
        first = field.queryset.first()
        self.assertIn(first.item.name, field.label_from_instance(first))
        base = Activity.objects.filter(delegation=self.north, deleted_at__isnull=True).first()
        for _ in range(40):
            base.pk = None
            base.save()
        with CaptureQueriesContext(connection) as after:
            response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(after), len(before))

    def test_the_script_is_loaded_by_the_widgets(self):
        widgets = (settings.BASE_DIR / "core/static/core/js/widgets.js").read_text(encoding="utf-8")
        self.assertIn('from "./searchable-select.js"', widgets)
        self.assertIn("initSearchable(root)", widgets)
        script = (settings.BASE_DIR / "core/static/core/js/searchable-select.js").read_text(encoding="utf-8")
        for needle in ('role", "combobox"', "aria-activedescendant", "MAX_SHOWN", "ArrowDown", "Escape"):
            self.assertIn(needle, script)

    @unittest.skipUnless(shutil.which("node"), "Hace falta Node para probar el buscador")
    def test_the_search_ignores_accents_case_and_word_order(self):
        path = settings.BASE_DIR / "core/static/core/js/searchable-select.js"
        script = (
            f"import {{ matchesAll }} from {path.as_uri()!r};"
            "const checks = ["
            "matchesAll('Actividad 08/10/2026 · Luis Herrera · Visita domiciliaria', 'HERRERA visita'),"
            "matchesAll('María Pérez', 'maria perez'),"
            "matchesAll('María Pérez', 'perez luis'),"
            "matchesAll('Cualquier cosa', '')];"
            "console.log(JSON.stringify(checks));"
        )
        done = subprocess.run(
            ["node", "--input-type=module", "-e", script], capture_output=True, text=True, timeout=30, check=False
        )
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stdout.strip(), "[true,true,false,true]")


class ChartMathTests(SimpleTestCase):

    def test_the_donut_arcs_are_proportional_and_follow_one_another(self):
        chart = charts.donut(
            [{"label": "A", "value": 1, "tone": "ok"}, {"label": "B", "value": 1, "tone": "warn"}, {"label": "C", "value": 2, "tone": "bad"}],
            "Prueba",
        )
        self.assertEqual(chart["total"], 4)
        self.assertEqual([s["length"] for s in chart["segments"]], ["25.000", "25.000", "50.000"])
        self.assertEqual([s["offset"] for s in chart["segments"]], ["0.000", "-25.000", "-50.000"])
        self.assertEqual([s["percent"] for s in chart["segments"]], ["25", "25", "50"])
        self.assertIn("A: 1", chart["summary"])
        self.assertIn("Total 4", chart["summary"])

    def test_an_empty_donut_draws_nothing_and_says_so(self):
        chart = charts.donut([{"label": "A", "value": 0, "tone": "ok"}, {"label": "B", "value": None, "tone": "x"}], "Vacío")
        self.assertEqual(chart["total"], 0)
        self.assertFalse(any(segment["draw"] for segment in chart["segments"]))
        self.assertEqual(chart["segments"][1]["tone"], "neutral")
        self.assertTrue(chart["summary"].endswith("Sin datos."))

    def test_the_bars_are_relative_to_the_maximum_and_never_pass_the_track(self):
        chart = charts.bars([{"label": "A", "value": 50}, {"label": "B", "value": 200}, {"label": "C", "value": None}], "Barras", " %", maximum=100)
        self.assertEqual([row["width"] for row in chart["rows"]], ["50.00", "100.00", "0.00"])
        self.assertEqual(chart["rows"][1]["text"], "200 %")
        automatic = charts.bars([{"label": "A", "value": 5}, {"label": "B", "value": 10}], "Auto")
        self.assertEqual([row["width"] for row in automatic["rows"]], ["50.00", "100.00"])

    def test_the_columns_scale_to_the_tallest_and_tell_every_value(self):
        chart = charts.columns([{"label": "01/10", "value": 2}, {"label": "02/10", "value": 4}, {"label": "03/10", "value": 0}], "Días")
        self.assertEqual(chart["total"], 6)
        self.assertEqual(chart["cols"][1]["height"], "40.00")
        self.assertEqual(chart["cols"][0]["height"], "20.00")
        self.assertEqual(chart["cols"][2]["height"], "0.00")
        self.assertIn("02/10: 4", chart["summary"])


class ChartScreenTests(PortalTestCase):

    def assertAccessibleCharts(self, response):
        page = response.content.decode()
        self.assertIn("chart-donut", page)
        self.assertRegex(page, r'<svg class="donut"[^>]*role="img" aria-label="[^"]+')

    def test_the_dashboard_has_charts_for_an_officer(self):
        self.login_as("matias.cavieres")
        response = self.client.get(reverse("core:dashboard"))
        self.assertAccessibleCharts(response)
        self.assertContains(response, "Mis evidencias del período")
        self.assertContains(response, "Mis compromisos")
        self.assertContains(response, "Atenciones de los últimos 14 días")
        self.assertContains(response, "chart-columns")

    def test_the_dashboard_has_the_traffic_light_chart_for_management(self):
        self.login_as("admin")
        response = self.client.get(reverse("core:dashboard"))
        self.assertAccessibleCharts(response)
        self.assertContains(response, "Metas por semáforo")

    def test_the_delegation_board_has_charts(self):
        self.login_as("admin")
        response = self.client.get(reverse("core:delegation_board"), {"delegacion": self.north.pk})
        self.assertAccessibleCharts(response)
        self.assertContains(response, "Funcionarios por semáforo")
        self.assertContains(response, "Cumplimiento promedio por funcionario")

    def test_the_collective_summary_has_charts(self):
        self.login_as("admin")
        response = self.client.get(reverse("core:commitment_summary"))
        self.assertAccessibleCharts(response)
        self.assertContains(response, "Compromisos por estado")
        self.assertContains(response, "Compromisos realizados por funcionario")

    def test_the_reports_have_charts(self):
        self.login_as("admin")
        response = self.client.get(reverse("core:reports"))
        self.assertAccessibleCharts(response)
        self.assertContains(response, "Evidencias por estado")
        self.assertContains(response, "Actividades por funcionario")

    def test_the_charts_follow_the_numbers_of_the_screen(self):
        self.login_as("matias.cavieres")
        charts_ = self.client.get(reverse("core:dashboard")).context["charts"]
        daily = charts_["daily"]
        self.assertEqual(len(daily["cols"]), 14)
        expected = Activity.objects.filter(author_officer=self.officer("F-1001"), deleted_at__isnull=True)
        self.assertLessEqual(daily["total"], expected.count())


class LiveFallbackTests(PortalTestCase):

    def read(self, *parts):
        return settings.BASE_DIR.joinpath(*parts).read_text(encoding="utf-8")

    def test_the_screens_check_themselves_when_the_websocket_does_not_connect(self):
        script = self.read("core", "static", "core", "js", "live-updates.js")
        self.assertIn("POLL_FALLBACK_MS = 8000", script)
        self.assertIn("POLL_SAFETY_MS", script)
        self.assertIn("function poll()", script)
        self.assertIn("document.hidden", script)
        self.assertIn("Se actualiza cada 8 s", script)

    def test_a_refresh_that_changes_nothing_does_not_touch_the_screen(self):
        script = self.read("core", "static", "core", "js", "live-updates.js")
        self.assertIn("signature(region) === signature(next)", script)
        self.assertIn("csrfmiddlewaretoken", script)

    def test_the_update_script_leaves_the_server_ready_and_proves_the_websocket(self):
        update = self.read("deploy", "actualizar.sh")
        self.assertIn("agregar_websocket.sh", update)
        self.assertIn("probar_websocket.py", update)
        self.assertLess(update.index("agregar_websocket.sh"), update.index("systemctl restart sgr"))
        self.assertLess(update.index("systemctl restart sgr"), update.index("probar_websocket.py"))


class WebsocketProbeTests(SimpleTestCase):

    def probe(self):
        spec = importlib.util.spec_from_file_location("probar_websocket", settings.BASE_DIR / "deploy" / "probar_websocket.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_only_daphne_answers_count_as_reaching_the_application(self):
        probe = self.probe()
        self.assertTrue(probe.reaches_daphne("HTTP/1.1 101 Switching Protocols", ""))
        self.assertTrue(probe.reaches_daphne("HTTP/1.1 403 Access denied", ""))
        self.assertTrue(probe.reaches_daphne("HTTP/1.1 403 Forbidden", "server: daphne"))
        self.assertFalse(probe.reaches_daphne("HTTP/1.1 403 Forbidden", "server: apache"))
        for status in ("HTTP/1.1 404 Not Found", "HTTP/1.1 502 Bad Gateway", "HTTP/1.1 200 OK", "(sin respuesta)"):
            self.assertFalse(probe.reaches_daphne(status, "server: daphne"), status)
