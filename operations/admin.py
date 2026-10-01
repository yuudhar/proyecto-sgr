from django.contrib import admin

from core.admin_mixins import DelegationScopedAdminMixin, SoftDeleteAdminMixin

from .models import Activity, Commitment, Followup, ManagementType


class FollowupInline(admin.TabularInline):
    model = Followup
    extra = 0
    fields = ("sequence_number", "management_type", "date", "result")
    show_change_link = True


@admin.register(ManagementType)
class ManagementTypeAdmin(SoftDeleteAdminMixin, admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)
    ordering = ("name",)


@admin.register(Activity)
class ActivityAdmin(DelegationScopedAdminMixin, admin.ModelAdmin):
    delegation_lookup = "delegation"
    list_display = (
        "date",
        "item",
        "delegation",
        "author_officer",
        "status",
        "requires_visit",
        "added_to_pipeline",
    )
    search_fields = (
        "contact_name",
        "phone",
        "beneficiary__name",
        "beneficiary__rut",
    )
    list_filter = (
        "delegation",
        "status",
        "requires_visit",
        "added_to_pipeline",
        "item",
    )
    list_select_related = (
        "delegation",
        "item",
        "author_officer",
        "beneficiary",
        "service",
    )
    ordering = ("-date",)
    date_hierarchy = "date"
    inlines = [FollowupInline]


@admin.register(Followup)
class FollowupAdmin(DelegationScopedAdminMixin, admin.ModelAdmin):
    delegation_lookup = "activity__delegation"
    list_display = (
        "activity",
        "sequence_number",
        "management_type",
        "date",
        "result",
    )
    list_filter = ("management_type", "sequence_number")
    list_select_related = ("activity", "management_type")
    ordering = ("-date",)
    date_hierarchy = "date"


@admin.register(Commitment)
class CommitmentAdmin(DelegationScopedAdminMixin, admin.ModelAdmin):
    delegation_lookup = "delegation"
    list_display = (
        "requester",
        "territory",
        "delegation",
        "requester_type",
        "responsible_officer",
        "due_date",
        "status",
    )
    search_fields = ("requester", "territory__name", "description")
    list_filter = ("delegation", "status", "requester_type")
    list_select_related = ("territory", "delegation", "responsible_officer")
    ordering = ("-due_date",)
    date_hierarchy = "due_date"
