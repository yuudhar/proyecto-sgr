from django.contrib import admin

from core.admin_mixins import SoftDeleteAdminMixin

from .models import Adjustment, Goal, Indicator, Period


@admin.register(Period)
class PeriodAdmin(SoftDeleteAdminMixin, admin.ModelAdmin):
    list_display = (
        "__str__",
        "status",
        "computable_days",
        "collective_threshold",
        "amber_threshold",
        "weighted_cap",
    )
    list_filter = ("status",)
    ordering = ("-start_date",)
    date_hierarchy = "start_date"


@admin.register(Goal)
class GoalAdmin(SoftDeleteAdminMixin, admin.ModelAdmin):
    list_display = (
        "item",
        "officer",
        "position",
        "period",
        "target_value",
        "unit",
        "weight",
    )
    search_fields = ("item__name", "officer__name", "position__name")
    list_filter = ("period", "position")
    list_select_related = ("item", "officer", "position", "period")
    ordering = ("-period__start_date",)


@admin.register(Indicator)
class IndicatorAdmin(SoftDeleteAdminMixin, admin.ModelAdmin):
    list_display = (
        "goal",
        "progress",
        "compliance",
        "weighting",
        "status_light",
        "calculated_at",
    )
    list_filter = ("status_light",)
    list_select_related = ("goal",)
    ordering = ("-calculated_at",)
    date_hierarchy = "calculated_at"
    readonly_fields = ("created_at", "updated_at", "calculated_at")


@admin.register(Adjustment)
class AdjustmentAdmin(SoftDeleteAdminMixin, admin.ModelAdmin):
    list_display = (
        "officer",
        "kind",
        "percentage_value",
        "period",
        "responsible_user",
        "date",
    )
    search_fields = ("officer__name", "reason")
    list_filter = ("kind", "period")
    list_select_related = ("officer", "period", "responsible_user")
    ordering = ("-date",)
    date_hierarchy = "date"
