from django.contrib import admin

from core.admin_mixins import DelegationScopedAdminMixin
from core.admin_utils import get_user_delegation
from organization.models import Officer

from .models import Evidence, Validation


class ValidationInline(admin.TabularInline):
    model = Validation
    extra = 0
    fields = ("decision", "reviewer_officer", "result")
    show_change_link = True

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "reviewer_officer" and not request.user.is_superuser:
            kwargs["queryset"] = Officer.objects.filter(
                delegation=get_user_delegation(request), deleted_at__isnull=True
            )
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(Evidence)
class EvidenceAdmin(DelegationScopedAdminMixin, admin.ModelAdmin):
    delegation_lookup = "activity__delegation"
    list_display = (
        "unique_code",
        "activity",
        "author_officer",
        "review_status",
        "uploaded_at",
    )
    search_fields = ("unique_code", "activity__contact_name")
    list_filter = ("review_status",)
    list_select_related = ("activity", "author_officer")
    ordering = ("-uploaded_at",)
    date_hierarchy = "uploaded_at"
    inlines = [ValidationInline]


@admin.register(Validation)
class ValidationAdmin(DelegationScopedAdminMixin, admin.ModelAdmin):
    delegation_lookup = "evidence__activity__delegation"
    list_display = ("evidence", "decision", "reviewer_officer", "date")
    list_filter = ("decision",)
    list_select_related = ("evidence", "reviewer_officer")
    ordering = ("-date",)
    date_hierarchy = "date"
