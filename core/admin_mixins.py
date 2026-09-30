
from django.contrib import admin, messages
from django.utils import timezone

from core.admin_utils import get_user_delegation


@admin.action(
    description="Archivar seleccionados (borrado lógico)",
    permissions=["change"],
)
def archive_selected(modeladmin, request, queryset):

    updated = queryset.filter(deleted_at__isnull=True).update(
        deleted_at=timezone.now()
    )
    modeladmin.message_user(
        request,
        f"{updated} registro(s) archivado(s).",
        level=messages.SUCCESS,
    )


class SoftDeleteAdminMixin:

    actions = [archive_selected]
    readonly_fields = ("created_at", "updated_at")

    def _showing_archived(self, request):
        return request.GET.get("show_archived") == "1"

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if self._showing_archived(request):
            return qs
        return qs.filter(deleted_at__isnull=True)

    def get_list_display(self, request):
        list_display = list(super().get_list_display(request))
        if self._showing_archived(request) and "deleted_at" not in list_display:
            list_display.append("deleted_at")
        return list_display

    def has_delete_permission(self, request, obj=None):
        return False


class DelegationScopedAdminMixin(SoftDeleteAdminMixin):

    delegation_lookup = "delegation"

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser or request.user.groups.filter(
            name="Coordinación"
        ).exists():
            return qs
        delegation = get_user_delegation(request)
        if delegation is None:
            return qs
        return qs.filter(**{self.delegation_lookup: delegation})

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if not request.user.is_superuser:
            delegation = get_user_delegation(request)

            if db_field.name == "delegation":
                from organization.models import Delegation

                kwargs["queryset"] = Delegation.objects.filter(pk=delegation.pk)

            elif db_field.name.endswith("officer"):
                from organization.models import Officer

                kwargs["queryset"] = Officer.objects.filter(
                    delegation=delegation, deleted_at__isnull=True
                )

            elif db_field.name == "territory":
                from organization.models import Territory

                kwargs["queryset"] = Territory.objects.filter(
                    delegation=delegation, deleted_at__isnull=True
                )

            elif db_field.name == "activity":
                from operations.models import Activity

                kwargs["queryset"] = Activity.objects.filter(
                    delegation=delegation, deleted_at__isnull=True
                )

            elif db_field.name == "evidence":
                from evidence.models import Evidence

                kwargs["queryset"] = Evidence.objects.filter(
                    activity__delegation=delegation, deleted_at__isnull=True
                )

        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        if not request.user.is_superuser and hasattr(obj, "delegation_id"):
            obj.delegation = get_user_delegation(request)
        super().save_model(request, obj, form, change)

    def has_change_permission(self, request, obj=None):
        allowed = super().has_change_permission(request, obj)
        if not allowed:
            return False
        if obj is None or request.user.is_superuser:
            return True

        delegation = get_user_delegation(request)
        value = obj
        for step in self.delegation_lookup.split("__"):
            value = getattr(value, step, None)
            if value is None:
                return False
        return value.pk == delegation.pk
