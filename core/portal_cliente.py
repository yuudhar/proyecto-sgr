"""Portal del Cliente: su inicio, el listado de sus atenciones y el detalle de cada una.

Todas las consultas parten de core.clients.own_activities(request.user): el filtro es el usuario autenticado,
nunca un dato que mande el navegador. Una atención ajena responde 404, igual que una que no existe.
"""

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, render
from django.urls import reverse

from core.clients import client_beneficiary, is_client, own_activities
from core.crud import query_string, registry
from operations.models import Activity

TONES = {
    Activity.Status.REGISTERED: "info",
    Activity.Status.IN_PROGRESS: "warn",
    Activity.Status.CLOSED: "ok",
}
PLURALS = {
    Activity.Status.REGISTERED: "Registradas",
    Activity.Status.IN_PROGRESS: "En proceso",
    Activity.Status.CLOSED: "Cerradas",
}
PAGE_SIZE = 10
HOME_LATEST = 5
SEARCH_MAX = 100


def client_only(view):
    """La vista es solo del perfil Cliente: cualquier otra cuenta tiene su propio panel."""

    @login_required
    def wrapper(request, *args, **kwargs):
        if not is_client(request.user):
            raise PermissionDenied("El portal del cliente es solo para cuentas del perfil Cliente.")
        return view(request, *args, **kwargs)

    wrapper.__name__ = view.__name__
    wrapper.__doc__ = view.__doc__
    return wrapper


def code_of(activity):
    return registry.get("actividades").code_of(activity)


def status_counts(queryset):
    found = dict(queryset.order_by().values_list("status").annotate(total=Count("pk")))
    return [
        {"value": value, "label": PLURALS.get(value, label), "total": found.get(value, 0), "tone": TONES.get(value, "neutral")}
        for value, label in Activity.Status.choices
    ]


def row_of(activity):
    return {
        "pk": activity.pk,
        "code": code_of(activity),
        "date": activity.date,
        "item": activity.item.name if activity.item_id else "",
        "request": activity.request_description,
        "status": activity.status,
        "status_label": activity.get_status_display(),
        "tone": TONES.get(activity.status, "neutral"),
        "followups": getattr(activity, "followup_total", 0),
        "url": reverse("core:portal_activity", args=[activity.pk]),
    }


@client_only
def home(request):
    beneficiary = client_beneficiary(request.user)
    activities = own_activities(request.user)
    latest = (
        activities.select_related("item")
        .annotate(followup_total=Count("followups", filter=Q(followups__deleted_at__isnull=True)))
        .order_by("-date", "-pk")[:HOME_LATEST]
    )
    return render(
        request,
        "core/portal/home.html",
        {
            "beneficiary": beneficiary,
            "counts": status_counts(activities),
            "total": activities.count(),
            "latest": [row_of(activity) for activity in latest],
            "breadcrumbs": [("Mi portal", None)],
        },
    )


@client_only
def activities(request):
    beneficiary = client_beneficiary(request.user)
    queryset = own_activities(request.user).select_related("item").annotate(
        followup_total=Count("followups", filter=Q(followups__deleted_at__isnull=True))
    )
    text = request.GET.get("q", "").strip()[:SEARCH_MAX]
    if text:
        queryset = queryset.filter(
            Q(request_description__icontains=text)
            | Q(action_taken__icontains=text)
            | Q(item__name__icontains=text)
        )
    status = request.GET.get("estado", "")
    if status in Activity.Status.values:
        queryset = queryset.filter(status=status)
    else:
        status = ""
    paginator = Paginator(queryset.order_by("-date", "-pk"), PAGE_SIZE)
    page = paginator.get_page(request.GET.get("page"))
    return render(
        request,
        "core/portal/activities.html",
        {
            "beneficiary": beneficiary,
            "rows": [row_of(activity) for activity in page.object_list],
            "page": page,
            "page_range": list(paginator.get_elided_page_range(page.number, on_each_side=2, on_ends=1)),
            "ellipsis": paginator.ELLIPSIS,
            "page_query": query_string(request, drop=("page",)),
            "q": text,
            "status": status,
            "statuses": Activity.Status.choices,
            "has_filters": bool(text or status),
            "breadcrumbs": [("Mi portal", reverse("core:portal_home")), ("Mis atenciones", None)],
        },
    )


@client_only
def activity(request, pk):
    obj = get_object_or_404(
        own_activities(request.user).select_related("item", "service", "delegation", "author_officer"), pk=pk
    )
    followups = obj.followups.filter(deleted_at__isnull=True).select_related("management_type").order_by("sequence_number")
    return render(
        request,
        "core/portal/activity.html",
        {
            "obj": obj,
            "code": code_of(obj),
            "followups": followups,
            "status_tone": TONES.get(obj.status, "neutral"),
            "breadcrumbs": [
                ("Mi portal", reverse("core:portal_home")),
                ("Mis atenciones", reverse("core:portal_activities")),
                (code_of(obj), None),
            ],
        },
    )
