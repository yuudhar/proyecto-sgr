"""Pantallas especiales: ingreso, perfil, atención, inicio, validación de evidencias, tablero e informes.

Las pantallas de listado, ficha y formulario de cada modelo están en core/crud.py;
aquí van las que no calzan con ese esquema. Todas respetan las mismas reglas de
acceso del Django Admin: permisos por modelo y alcance por delegación.
"""

import csv
from decimal import ROUND_HALF_UP, Decimal
from urllib.parse import urlsplit

from django.contrib import messages
from django.contrib.auth import update_session_auth_hash, views as auth_views
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Count, Prefetch, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import Resolver404, resolve, reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from core import export, ui
from core.access import (
    active_delegation,
    authorized_delegations,
    delegation_choice,
    is_global_user,
    remember_delegation,
    request_delegation,
    request_officer,
)
from core.audit import log_event, log_export
from core.crud import CODE_COLUMN, PAGE_SIZES, SESSION_PAGE_SIZE, Col, CrudListView, query_string, registry
from core.forms import PortalAuthenticationForm, PortalPasswordChangeForm, ValidationForm
from core.rules import rut_with_wrong_digit
from evidence.models import Evidence, Validation
from operations.models import Activity, Commitment
from organization.models import Delegation, Officer
from planning.models import Adjustment, Goal, Indicator, Period


# ---------------------------------------------------------------------------
# Ingreso y salida
# ---------------------------------------------------------------------------


class PortalLoginView(auth_views.LoginView):
    """Ingreso. Usa la plantilla por defecto de LoginView: templates/registration/login.html."""

    authentication_form = PortalAuthenticationForm
    redirect_authenticated_user = True


class PortalLogoutView(auth_views.LogoutView):
    """Cierra la sesión. Solo acepta POST, así que el botón de arriba es un formulario.

    Cerrar la sesión borra todo lo que había en request.session: otra persona que use el mismo
    navegador no hereda nada. El aviso se agrega después, ya con la sesión vacía, y se muestra en
    la pantalla de ingreso a la que se redirige.
    """

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        messages.info(request, "Cerraste tu sesión.")
        return response


@login_required
def profile(request):
    """Mi perfil: los datos de la cuenta (que ya trae el menú) y el cambio de contraseña."""
    form = PortalPasswordChangeForm(request.user, request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        update_session_auth_hash(request, user)  # la sesión actual sigue abierta con la contraseña nueva
        log_event(user, "Contraseña cambiada", user)
        messages.success(request, "Cambiaste tu contraseña.")
        return redirect("core:profile")
    return render(
        request,
        "core/profile.html",
        {
            "form": form,
            "breadcrumbs": [("Inicio", reverse("core:dashboard")), ("Mi perfil", None)],
        },
    )


@login_required
@require_POST
def set_page_size(request):
    """Guarda en la sesión cuántas filas por página quiere ver la persona y la devuelve a donde estaba.

    Es el ejemplo de estado temporal de la sesión: no es un dato permanente (no va a la base de
    datos), vale para todos los listados y se olvida al cerrar sesión. Después de guardar, el aviso
    de éxito (messages) se muestra en la página a la que se redirige.
    """
    try:
        size = int(request.POST.get("filas", ""))
    except ValueError:
        size = None
    if size not in PAGE_SIZES:
        messages.error(request, "Esa cantidad de filas no está disponible.")
    else:
        request.session[SESSION_PAGE_SIZE] = size
        messages.success(
            request,
            f"Listo: los listados muestran {size} filas por página mientras dure tu sesión.",
            extra_tags="toast",  # un cambio de preferencia: aviso corto en la esquina, no una ventana al centro
        )
    target = request.POST.get("next", "")
    if not url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        target = reverse("core:dashboard")
    return redirect(target)


def context_label(delegation):
    """«DEL01 · Delegación Norte», o «Todas las delegaciones» si no hay una delegación."""
    if delegation is None:
        return "Todas las delegaciones"
    return f"{registry.get('delegaciones').code_of(delegation)} · {delegation.name}"


def context_return_url(request):
    """A dónde volver después de cambiar de delegación.

    A la misma pantalla de donde se vino, sin su búsqueda ni su página (eran de la delegación anterior). Si la persona
    estaba mirando o editando un registro, ese registro puede no existir en la delegación nueva: vuelve al listado del
    módulo. Solo se aceptan direcciones de este mismo sitio y del portal.
    """
    home = reverse("core:dashboard")
    target = request.POST.get("next", "")
    if not target or not url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return home
    path = urlsplit(target).path
    try:
        match = resolve(path)
    except Resolver404:
        return home
    if match.namespace != "core" or not match.url_name or match.url_name in {"set_context", "page_size", "logout"}:
        return home
    if "pk" in match.kwargs:
        if match.url_name == "validate_evidence":
            return reverse("core:validate_list")
        try:
            return registry.get(match.url_name.rsplit("_", 1)[0]).url("list")
        except KeyError:
            return home
    return path


@login_required
@require_POST
def set_context(request):
    """Cambia la delegación en la que trabaja la persona (el selector de la franja de arriba).

    La elegida se guarda en la sesión (Clase 6: estado temporal de quien inició sesión, como las filas por página),
    pero a diferencia de ese ajuste decide qué datos se ven y dónde se puede cambiar algo, así que el servidor
    comprueba cada vez que esté autorizada para esta persona (Clase 7: ocultar una opción no es control de acceso).
    Un id enviado a mano que no corresponda responde 403 y queda en la auditoría. Todas las pantallas leen la
    delegación activa desde core/access.py, de modo que listados, filtros, exportaciones y formularios cambian juntos.
    """
    raw = request.POST.get("delegacion", "")
    allowed, chosen = delegation_choice(request, raw)
    if not allowed:
        log_event(
            request.user,
            "Cambio de delegación rechazado",
            request.user,
            new=f"Delegación pedida: {str(raw)[:40] or '(vacía)'}",
        )
        raise PermissionDenied("No tienes autorizada esa delegación.")
    before = active_delegation(request)
    remember_delegation(request, chosen)
    if getattr(before, "pk", None) == getattr(chosen, "pk", None):
        messages.info(request, f"Ya estabas trabajando en: {context_label(chosen)}.", extra_tags="toast")
    else:
        log_event(
            request.user,
            "Cambio de delegación activa",
            request.user,
            previous=context_label(before),
            new=context_label(chosen),
        )
        messages.success(
            request,
            f"Ahora trabajas en: {context_label(chosen)}. Los listados, filtros, exportaciones y formularios usan esta delegación.",
            extra_tags="toast",
        )
    return redirect(context_return_url(request))


# ---------------------------------------------------------------------------
# Atención
# ---------------------------------------------------------------------------


class AtencionView(CrudListView):
    """Atención: se busca a la persona por RUT, nombre u otro dato y salen sus atenciones.

    Es el listado de Actividades con una pantalla pensada para atender: un cuadro de
    búsqueda grande, el botón para registrar una atención nueva y, en cada fila, otro
    para volver a atender a la misma persona. Sin búsqueda muestra las últimas atenciones.
    """

    template_name = "core/atencion.html"
    export_title = "Atención"
    export_slug = "atenciones"

    def get_columns(self, request):
        specs = [
            Col(CODE_COLUMN),
            "date",
            Col("contact_name", "Contacto", link=True),
            Col("beneficiary__rut", "RUT"),
            Col("attention_type", "Tipo de atención"),
            Col("sub_attention", "Sub atención"),
            "author_officer",
            "status",
        ]
        if active_delegation(request) is None:
            specs.insert(-1, "delegation")  # quien mira todas las delegaciones necesita saber de cuál es cada atención
        return self.crud.resolve_columns(specs)

    def extra_context(self, request):
        text = request.GET.get("q", "").strip()
        return {
            "wrong_rut": rut_with_wrong_digit(text),
            "breadcrumbs": [("Inicio", reverse("core:dashboard")), ("Atención", None)],
        }


# ---------------------------------------------------------------------------
# Datos compartidos por varias pantallas
# ---------------------------------------------------------------------------


def current_period():
    """Período vigente; si no hay ninguno, el más reciente."""
    periods = Period.objects.filter(deleted_at__isnull=True).order_by("-start_date")
    return periods.filter(status=Period.Status.ACTIVE).first() or periods.first()


def latest_indicators(goal_ids):
    """Último indicador calculado de cada meta: {id de meta: indicador}."""
    latest = {}
    indicators = Indicator.objects.filter(
        goal_id__in=goal_ids, deleted_at__isnull=True
    ).order_by("goal_id", "-calculated_at", "-pk")
    for indicator in indicators:
        latest.setdefault(indicator.goal_id, indicator)
    return latest


def goals_of(officer, goals):
    """Metas que le corresponden a un funcionario: las suyas y las de su cargo."""
    return [
        goal
        for goal in goals
        if goal.officer_id == officer.pk
        or (goal.officer_id is None and goal.position_id == officer.position_id)
    ]


def mean(values):
    """Promedio sin redondear; None si no hay valores. Con este valor se decide el semáforo."""
    values = list(values)
    if not values:
        return None
    return sum(values, Decimal(0)) / len(values)


def rounded(value):
    """El valor con un decimal (.05 sube), tal como se muestra en pantalla; None se queda en None."""
    if value is None:
        return None
    return value.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def light_of(value, period):
    """Semáforo de un promedio con los umbrales del período; vacío si no hay promedio."""
    if value is None:
        return ""
    return ui.light_for_compliance(value, period.collective_threshold, period.amber_threshold)


def pick_period(request):
    """Período elegido con ?periodo=<id>; por defecto el vigente. Devuelve (período, opciones)."""
    periods = list(Period.objects.filter(deleted_at__isnull=True).order_by("-start_date"))
    chosen = request.GET.get("periodo", "")
    for period in periods:
        if str(period.pk) == chosen:
            return period, periods
    default = current_period()
    return default, periods


def pick_delegation(request, allow_all=False):
    """Delegación a mostrar. Devuelve (delegación o None, opciones, puede_elegir).

    Sigue la delegación en que trabaja la persona (el selector de la franja de arriba). Solo quien mira todas las
    delegaciones elige además aquí con ?delegacion=<id> (o "todas" si allow_all); sin delegación asignada se
    responde el 403 del Admin.
    """
    active = active_delegation(request)
    if active is not None:
        return active, [active], False

    options = list(
        Delegation.objects.filter(deleted_at__isnull=True).order_by("name")
    )
    chosen = request.GET.get("delegacion", "")
    if allow_all and chosen in ("", "todas"):
        return None, options, True
    for delegation in options:
        if str(delegation.pk) == chosen:
            return delegation, options, True
    return (options[0] if options else None), options, True


def mini_table(crud, request, queryset, paths, limit=5):
    """Columnas y filas de un listado corto, con las mismas celdas del mantenedor."""
    by_path = {column.path: column for column in crud.columns}
    columns = [by_path[path] for path in paths]
    rows = [
        crud.make_row(request, obj, columns=columns, actions=False)
        for obj in queryset[:limit]
    ]
    for row in rows:
        # La primera celda lleva a la ficha, salvo que el listado ya marque otra columna.
        if row.cells and not any(cell.link for cell in row.cells):
            row.cells[0].link = True
    return columns, rows


# ---------------------------------------------------------------------------
# Inicio
# ---------------------------------------------------------------------------


def goal_lines(goals, indicators):
    """Una línea por meta con su último indicador, lista para dibujar."""
    lines = []
    for goal in goals:
        indicator = indicators.get(goal.pk)
        lines.append(
            {
                "goal": goal,
                "item": goal.item,
                "target": ui.fmt_number(goal.target_value),
                "unit": goal.unit,
                "scope": "Meta personal" if goal.officer_id else "Meta del cargo",
                "indicator": indicator,
                "progress": ui.fmt_number(indicator.progress) if indicator else "",
                "compliance": indicator.compliance if indicator else None,
                "light": indicator.status_light if indicator else "",
            }
        )
    return lines


@login_required
def dashboard(request):
    user = request.user

    # Cuántas veces entró la persona al inicio durante esta sesión. request.session se usa como un
    # diccionario: get trae el valor anterior (0 la primera vez) y la asignación lo guarda. El número
    # sigue ahí al refrescar o cambiar de página, y se pierde al cerrar la sesión.
    visits = request.session.get("dashboard_visits", 0) + 1
    request.session["dashboard_visits"] = visits

    officer = request_officer(request)
    period = current_period()
    today = timezone.localdate()

    context = {
        "greeting_name": user.first_name or user.get_username(),
        "period": period,
        "visits": visits,
        "breadcrumbs": None,
    }

    # Alcance: quien no tiene ninguna delegación autorizada (y no ve todas) no puede consultar datos.
    if not is_global_user(request) and not authorized_delegations(request):
        context["no_delegation"] = True
        return render(request, "core/dashboard.html", context)

    activities = registry.get("actividades")
    evidences = registry.get("evidencias")
    commitments = registry.get("agenda")

    # Metas del funcionario en el período vigente.
    if officer is not None and period is not None:
        goals = list(
            Goal.objects.filter(deleted_at__isnull=True, period=period)
            .filter(Q(officer=officer) | Q(officer__isnull=True, position=officer.position))
            .select_related("item")
            .order_by("item__name")
        )
        context["goal_lines"] = goal_lines(goals, latest_indicators([g.pk for g in goals]))

    # Semáforo general: para quienes ven todas las delegaciones; con una elegida arriba, solo las metas de esa
    # (más las metas por cargo, que son de todas, igual que en el mantenedor de Indicadores).
    if period is not None and is_global_user(request) and user.has_perm("planning.view_indicator"):
        goals = Goal.objects.filter(deleted_at__isnull=True, period=period)
        chosen = active_delegation(request)
        if chosen is not None:
            goals = goals.filter(Q(officer__delegation=chosen) | Q(officer__isnull=True))
        goals = list(goals)
        indicators = latest_indicators([g.pk for g in goals])
        counts = {"green": 0, "amber": 0, "red": 0}
        for indicator in indicators.values():
            counts[indicator.status_light] = counts.get(indicator.status_light, 0) + 1
        context["light_counts"] = [
            {"light": key, "label": ui.LIGHT_LABELS[key], "total": counts[key]}
            for key in ("green", "amber", "red")
        ]
        context["goals_without_indicator"] = len(goals) - len(indicators)

    # Pendientes (solo lo que el usuario puede ver).
    pending = []
    if activities.has_perm(user, "view"):
        activity_qs = activities.get_queryset(request)
        month = activity_qs.filter(date__year=today.year, date__month=today.month)
        if officer is not None:
            month = month.filter(author_officer=officer)
        pending.append(
            {
                "label": "Mis actividades de este mes" if officer else "Actividades de este mes",
                "total": month.count(),
                "icon": activities.icon,
                "url": activities.url("list"),
                "tone": "neutral",
            }
        )
        visits = activity_qs.filter(requires_visit=True).exclude(status=Activity.Status.CLOSED).count()
        pending.append(
            {
                "label": "Visitas por realizar",
                "total": visits,
                "icon": "bi-house-door",
                "url": f"{activities.url('list')}?requires_visit=1",
                "tone": "warn" if visits else "neutral",
            }
        )
    if evidences.has_perm(user, "view"):
        to_review = evidences.get_queryset(request)
        url = f"{evidences.url('list')}?review_status=pending"
        label = "Evidencias pendientes de revisión"
        if user.has_perm("evidence.add_validation"):
            try:
                # Se cuentan las mismas evidencias que aparecen en la pantalla de validación.
                to_review = reviewable_evidence(request)[1]
                url, label = reverse("core:validate_list"), "Evidencias por revisar"
            except PermissionDenied:
                pass
        to_review = to_review.filter(review_status=Evidence.ReviewStatus.PENDING).count()
        pending.append(
            {
                "label": label,
                "total": to_review,
                "icon": evidences.icon,
                "url": url,
                "tone": "warn" if to_review else "neutral",
            }
        )
    if commitments.has_perm(user, "view"):
        commitment_qs = commitments.get_queryset(request).exclude(
            status=Commitment.Status.FULFILLED
        )
        overdue = commitment_qs.filter(due_date__lt=today).count()
        pending.append(
            {
                "label": "Compromisos abiertos",
                "total": commitment_qs.count(),
                "detail": f"{overdue} vencido(s)" if overdue else "",
                "icon": commitments.icon,
                "url": commitments.url("list"),
                "tone": "bad" if overdue else "neutral",
            }
        )
    context["pending"] = pending

    # Atajos según permisos.
    shortcuts = []
    if activities.can_add(user):
        shortcuts.append(("Registrar actividad", activities.url("create"), "bi-plus-circle"))
    if evidences.can_add(user):
        shortcuts.append(("Cargar evidencia", evidences.url("create"), "bi-cloud-arrow-up"))
    if commitments.can_add(user):
        shortcuts.append(("Nuevo compromiso", commitments.url("create"), "bi-calendar-plus"))
    if user.has_perm("evidence.add_validation"):
        shortcuts.append(("Validar evidencias", reverse("core:validate_list"), "bi-patch-check"))
    if user.has_perm("planning.view_indicator"):
        shortcuts.append(("Tablero de delegación", reverse("core:delegation_board"), "bi-columns-gap"))
        shortcuts.append(("Informes", reverse("core:reports"), "bi-file-earmark-bar-graph"))
    context["shortcuts"] = shortcuts

    # Listados cortos.
    if activities.has_perm(user, "view"):
        recent = activities.get_queryset(request).order_by("-date", "-pk")
        if officer is not None:
            recent = recent.filter(author_officer=officer)
        columns, rows = mini_table(
            activities, request, recent, ["date", "contact_name", "attention_type", "status"]
        )
        context["recent_activities"] = {"columns": columns, "rows": rows, "list_url": activities.url("list")}
    if commitments.has_perm(user, "view"):
        upcoming = (
            commitments.get_queryset(request)
            .exclude(status=Commitment.Status.FULFILLED)
            .order_by("due_date", "pk")
        )
        columns, rows = mini_table(
            commitments, request, upcoming, ["requester", "due_date", "status"]
        )
        context["upcoming_commitments"] = {"columns": columns, "rows": rows, "list_url": commitments.url("list")}

    return render(request, "core/dashboard.html", context)


# ---------------------------------------------------------------------------
# Validación de evidencias
# ---------------------------------------------------------------------------

# Estado de la evidencia después de cada decisión: observar no la aprueba ni la rechaza,
# queda pendiente hasta que el funcionario la corrija y se vuelva a revisar.
STATUS_AFTER_DECISION = {
    Validation.Decision.APPROVED: Evidence.ReviewStatus.APPROVED,
    Validation.Decision.REJECTED: Evidence.ReviewStatus.REJECTED,
    Validation.Decision.FLAGGED: Evidence.ReviewStatus.PENDING,
}

DECISION_DONE = {
    Validation.Decision.APPROVED: "aprobada",
    Validation.Decision.REJECTED: "rechazada",
    Validation.Decision.FLAGGED: "observada",
}


def reviewable_evidence(request):
    """Mantenedor de evidencias y las evidencias que el usuario puede revisar.

    Quien revisa solo ve las de la delegación en que trabaja: la que eligió arriba o, si no eligió, la de su
    funcionario, aunque además sea de Coordinación (así lo hace el formulario de validación del Admin). El
    superusuario que mira todas las ve todas. Sin delegación se responde 403.
    """
    crud = registry.get("evidencias")
    if not crud.has_perm(request.user, "view"):
        raise PermissionDenied
    evidences = crud.get_queryset(request)
    delegation = request_delegation(request)
    if delegation is not None:
        evidences = evidences.filter(activity__delegation=delegation)
    return crud, evidences


@login_required
@permission_required("evidence.add_validation", raise_exception=True)
def validate_list(request):
    crud, evidences = reviewable_evidence(request)
    history = Prefetch(
        "validations",
        queryset=Validation.objects.filter(deleted_at__isnull=True).order_by("-date"),
    )
    pending = (
        evidences.filter(review_status=Evidence.ReviewStatus.PENDING)
        .select_related("activity", "author_officer")
        .prefetch_related(history)
        .order_by("uploaded_at", "pk")
    )
    items = []
    for evidence in pending:
        reviews = list(evidence.validations.all())
        last = reviews[0] if reviews else None
        items.append(
            {
                "evidence": evidence,
                "uploaded": ui.fmt_datetime(evidence.uploaded_at),
                "flagged": last is not None and last.decision == Validation.Decision.FLAGGED,
                "last_result": last.result if last else "",
                "review_url": reverse("core:validate_evidence", args=[evidence.pk]),
                "detail_url": crud.url("detail", evidence.pk),
            }
        )

    validations = registry.get("validaciones")
    recent = None
    if validations.has_perm(request.user, "view"):
        columns, rows = mini_table(
            validations,
            request,
            validations.get_queryset(request).order_by("-date", "-pk"),
            ["evidence", "decision", "reviewer_officer", "date"],
            limit=8,
        )
        recent = {"columns": columns, "rows": rows, "list_url": validations.url("list")}

    return render(
        request,
        "core/validate_list.html",
        {
            "items": items,
            "recent": recent,
            "breadcrumbs": [("Inicio", reverse("core:dashboard")), ("Validar evidencias", None)],
        },
    )


@login_required
@permission_required("evidence.add_validation", raise_exception=True)
def validate_evidence(request, pk):
    crud, evidences = reviewable_evidence(request)
    evidence = get_object_or_404(
        evidences.select_related(
            "activity", "activity__item", "activity__delegation", "author_officer"
        ),
        pk=pk,
    )

    # Quien revisa es su propio funcionario. El superusuario no tiene uno: elige entre
    # los funcionarios activos de la delegación de la evidencia.
    officer = request_officer(request)
    reviewers = None
    if officer is None:
        if not request.user.is_superuser:
            raise PermissionDenied("Tu usuario no tiene un funcionario asociado para validar.")
        reviewers = Officer.objects.filter(
            delegation=evidence.activity.delegation,
            status=Officer.Status.ACTIVE,
            deleted_at__isnull=True,
        )

    form = ValidationForm(request.POST or None, reviewers=reviewers)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            validation = form.save(commit=False)
            validation.evidence = evidence
            validation.reviewer_officer = (
                form.cleaned_data["reviewer_officer"] if reviewers is not None else officer
            )
            validation.save()

            previous = evidence.review_status
            evidence.review_status = STATUS_AFTER_DECISION[validation.decision]
            evidence.save(update_fields=["review_status", "updated_at"])
            log_event(
                request.user,
                "Evidencia validada",
                evidence,
                previous=f"review_status={previous}",
                new=f"review_status={evidence.review_status}, decision={validation.decision}",
            )
        messages.success(
            request,
            f"Evidencia «{evidence.unique_code}» {DECISION_DONE[validation.decision]}.",
        )
        return redirect("core:validate_list")

    history = list(
        evidence.validations.filter(deleted_at__isnull=True)
        .select_related("reviewer_officer")
        .order_by("-date", "-pk")
    )
    activity_crud = registry.get("actividades")
    return render(
        request,
        "core/validate_form.html",
        {
            "evidence": evidence,
            "form": form,
            "history": history,
            "activity_url": (
                activity_crud.url("detail", evidence.activity_id)
                if activity_crud.has_perm(request.user, "view")
                else ""
            ),
            "evidence_url": crud.url("detail", evidence.pk),
            "breadcrumbs": [
                ("Inicio", reverse("core:dashboard")),
                ("Validar evidencias", reverse("core:validate_list")),
                (evidence.unique_code, None),
            ],
        },
    )


# ---------------------------------------------------------------------------
# Tablero por delegación
# ---------------------------------------------------------------------------


def officer_results(officers, goals, indicators, period):
    """Resultados por funcionario: sus metas, el cumplimiento promedio y el semáforo."""
    results = []
    for officer in officers:
        own = goals_of(officer, goals)
        lines = goal_lines(own, indicators)
        compliances = [line["compliance"] for line in lines if line["compliance"] is not None]
        exact = mean(compliances)
        results.append(
            {
                "officer": officer,
                "lines": lines,
                "goal_total": len(own),
                "exact_average": exact,
                "average": rounded(exact),
                "light": light_of(exact, period),
            }
        )
    return results


@login_required
@permission_required("planning.view_indicator", raise_exception=True)
def delegation_board(request):
    delegation, delegations, can_pick = pick_delegation(request)
    period, periods = pick_period(request)

    context = {
        "delegation": delegation,
        "delegations": delegations,
        "can_pick_delegation": can_pick,
        "period": period,
        "periods": periods,
        "breadcrumbs": [("Inicio", reverse("core:dashboard")), ("Tablero de delegación", None)],
    }
    if delegation is None or period is None:
        return render(request, "core/delegation_board.html", context)

    officers = list(
        Officer.objects.filter(
            delegation=delegation, status=Officer.Status.ACTIVE, deleted_at__isnull=True
        )
        .select_related("position")
        .order_by("name")
    )
    goals = list(
        Goal.objects.filter(deleted_at__isnull=True, period=period).select_related("item")
    )
    indicators = latest_indicators([goal.pk for goal in goals])
    results = officer_results(officers, goals, indicators, period)

    delegation_mean = mean(
        row["exact_average"] for row in results if row["exact_average"] is not None
    )
    lights = {"green": 0, "amber": 0, "red": 0}
    for row in results:
        if row["light"]:
            lights[row["light"]] += 1

    tiles = []
    user = request.user
    if user.has_perm("evidence.view_evidence"):
        tiles.append(
            {
                "label": "Evidencias pendientes de revisión",
                "total": Evidence.objects.filter(
                    deleted_at__isnull=True,
                    review_status=Evidence.ReviewStatus.PENDING,
                    activity__delegation=delegation,
                ).count(),
            }
        )
    if user.has_perm("operations.view_commitment"):
        tiles.append(
            {
                "label": "Compromisos abiertos",
                "total": Commitment.objects.filter(
                    deleted_at__isnull=True, delegation=delegation
                )
                .exclude(status=Commitment.Status.FULFILLED)
                .count(),
            }
        )
    if user.has_perm("operations.view_activity"):
        tiles.append(
            {
                "label": "Actividades del período",
                "total": Activity.objects.filter(
                    deleted_at__isnull=True,
                    delegation=delegation,
                    date__range=(period.start_date, period.end_date),
                ).count(),
            }
        )

    context.update(
        {
            "results": results,
            "average": rounded(delegation_mean),
            "average_light": light_of(delegation_mean, period),
            "light_counts": [
                {"light": key, "label": ui.LIGHT_LABELS[key], "total": lights[key]}
                for key in ("green", "amber", "red")
            ],
            "tiles": tiles,
        }
    )
    return render(request, "core/delegation_board.html", context)


# ---------------------------------------------------------------------------
# Informes
# ---------------------------------------------------------------------------


def safe_cell(value):
    """Evita que Excel interprete como fórmula un texto que parte con =, +, - o @."""
    text = "" if value is None else str(value)
    return f"'{text}" if text[:1] in ("=", "+", "-", "@") else text


def report_rows(delegation, period, with_adjustment):
    """Una fila por funcionario activo: actividades, evidencias, cumplimiento y, si se pide, ajuste."""
    in_period = Q(authored_activities__deleted_at__isnull=True) & Q(
        authored_activities__date__range=(period.start_date, period.end_date)
    )

    def evidence_count(status):
        return Count(
            "authored_evidence",
            filter=Q(
                authored_evidence__deleted_at__isnull=True,
                authored_evidence__review_status=status,
                authored_evidence__uploaded_at__date__range=(period.start_date, period.end_date),
            ),
            distinct=True,
        )

    officers = Officer.objects.filter(status=Officer.Status.ACTIVE, deleted_at__isnull=True)
    if delegation is not None:
        officers = officers.filter(delegation=delegation)
    officers = (
        officers.select_related("delegation", "position")
        .annotate(
            activity_total=Count("authored_activities", filter=in_period, distinct=True),
            approved_total=evidence_count(Evidence.ReviewStatus.APPROVED),
            pending_total=evidence_count(Evidence.ReviewStatus.PENDING),
            rejected_total=evidence_count(Evidence.ReviewStatus.REJECTED),
        )
        .order_by("delegation__name", "name")
    )
    officers = list(officers)

    goals = list(Goal.objects.filter(deleted_at__isnull=True, period=period).select_related("item"))
    indicators = latest_indicators([goal.pk for goal in goals])

    net = {}
    if with_adjustment:
        for adjustment in Adjustment.objects.filter(deleted_at__isnull=True, period=period):
            sign = 1 if adjustment.kind == Adjustment.Kind.BONUS else -1
            net[adjustment.officer_id] = (
                net.get(adjustment.officer_id, Decimal(0)) + sign * adjustment.percentage_value
            )

    rows = []
    for officer in officers:
        compliances = [
            indicators[goal.pk].compliance
            for goal in goals_of(officer, goals)
            if goal.pk in indicators
        ]
        exact = mean(compliances)
        rows.append(
            {
                "officer": officer,
                "activities": officer.activity_total,
                "approved": officer.approved_total,
                "pending": officer.pending_total,
                "rejected": officer.rejected_total,
                "average": rounded(exact),
                "light": light_of(exact, period),
                "adjustment": net.get(officer.pk, Decimal(0)),
            }
        )
    return rows


def report_csv(rows, period, with_adjustment):
    """Informe en CSV listo para Excel en español: separador «;» y coma decimal."""
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = (
        f'attachment; filename="informe-sgr-{period.start_date:%Y-%m-%d}.csv"'
    )
    response.write("﻿")  # marca para que Excel reconozca los acentos
    writer = csv.writer(response, delimiter=";")
    header = [
        "Funcionario",
        "Delegación",
        "Cargo",
        "Actividades",
        "Evidencias aprobadas",
        "Evidencias pendientes",
        "Evidencias rechazadas",
        "Cumplimiento promedio (%)",
    ]
    if with_adjustment:
        header.append("Ajuste neto (%)")
    writer.writerow(header)
    for row in rows:
        officer = row["officer"]
        line = [
            safe_cell(officer.name),
            safe_cell(officer.delegation),
            safe_cell(officer.position),
            row["activities"],
            row["approved"],
            row["pending"],
            row["rejected"],
            ui.fmt_number(row["average"]) if row["average"] is not None else "",
        ]
        if with_adjustment:
            line.append(ui.fmt_number(row["adjustment"]))
        writer.writerow(line)
    return response


def report_xlsx(request, rows, period, delegation, with_adjustment):
    """Informe en Excel con los mismos datos que la tabla de la pantalla."""
    headers = [
        "Funcionario",
        "Delegación",
        "Cargo",
        "Actividades",
        "Evidencias aprobadas",
        "Evidencias pendientes",
        "Evidencias rechazadas",
        "Cumplimiento promedio (%)",
    ]
    kinds = ["text", "text", "text", "number", "number", "number", "number", "percent"]
    if with_adjustment:
        headers.append("Ajuste neto (%)")
        kinds.append("percent")
    lines = []
    for row in rows:
        officer = row["officer"]
        line = [
            officer.name,
            str(officer.delegation),
            str(officer.position),
            row["activities"],
            row["approved"],
            row["pending"],
            row["rejected"],
            row["average"] if row["average"] is not None else "",
        ]
        if with_adjustment:
            line.append(row["adjustment"])
        lines.append(line)
    summary = f"{delegation.name if delegation else 'Todas las delegaciones'}. {ui.humanize_dates(period)}"
    content = export.build_workbook(
        "Informe de gestión", headers, kinds, lines, summary, request.user, total=len(lines)
    )
    log_export(request.user, "Informe", len(lines), summary)
    response = HttpResponse(content, content_type=export.CONTENT_TYPE)
    response["Content-Disposition"] = f'attachment; filename="{export.file_name("informe-sgr")}"'
    return response


@login_required
@permission_required("planning.view_indicator", raise_exception=True)
def reports(request):
    delegation, delegations, can_pick = pick_delegation(request, allow_all=True)
    period, periods = pick_period(request)

    context = {
        "delegation": delegation,
        "delegations": delegations,
        "can_pick_delegation": can_pick,
        "period": period,
        "periods": periods,
        "breadcrumbs": [("Inicio", reverse("core:dashboard")), ("Informes", None)],
    }
    if period is None:
        return render(request, "core/reports.html", context)

    # El ajuste neto solo lo ve quien puede consultar los ajustes.
    with_adjustment = request.user.has_perm("planning.view_adjustment")
    rows = report_rows(delegation, period, with_adjustment)
    if request.GET.get("formato") == "csv":
        return report_csv(rows, period, with_adjustment)
    if request.GET.get("formato") == "xlsx":
        return report_xlsx(request, rows, period, delegation, with_adjustment)

    context.update(
        {
            "rows": rows,
            "with_adjustment": with_adjustment,
            "totals": {
                "activities": sum(r["activities"] for r in rows),
                "approved": sum(r["approved"] for r in rows),
                "pending": sum(r["pending"] for r in rows),
                "rejected": sum(r["rejected"] for r in rows),
            },
            "scope_label": delegation.name if delegation else "Todas las delegaciones",
            "csv_url": query_string(request, formato="csv"),
            "xlsx_url": query_string(request, formato="xlsx"),
        }
    )
    return render(request, "core/reports.html", context)


# ---------------------------------------------------------------------------
# Administración
# ---------------------------------------------------------------------------


@login_required
def administration(request):
    """Portada de Administración: los mantenedores a los que el usuario puede entrar."""
    from core.menus import visible_entries

    _, groups = visible_entries(request.user)
    groups = [g for g in groups if g.key == "administracion"]
    if not groups:
        raise PermissionDenied
    hub_url = reverse("core:administration")
    sections = []
    for title, items in groups[0].sections:
        items = [item for item in items if item.url != hub_url]  # la portada no se enlaza a sí misma
        if items:
            sections.append((title, items))
    period = current_period()
    show_period = period is not None and registry.get("periodos").has_perm(request.user, "view")
    return render(
        request,
        "core/administration.html",
        {
            "sections": sections,
            "period": period if show_period else None,
            "breadcrumbs": [("Inicio", reverse("core:dashboard")), ("Administración", None)],
        },
    )
