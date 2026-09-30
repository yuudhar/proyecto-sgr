from django.contrib import admin

from core.admin_mixins import DelegationScopedAdminMixin

from .models import Evidence, Validation


class ValidationInline(admin.TabularInline):
    model = Validation
    extra = 0
    fields = ("decision", "reviewer_officer", "result")
    show_change_link = True


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
