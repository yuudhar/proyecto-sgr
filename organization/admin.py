from django.contrib import admin

from core.admin_mixins import DelegationScopedAdminMixin, SoftDeleteAdminMixin

from .models import (
    Beneficiary,
    Delegation,
    Item,
    Officer,
    Position,
    PositionItem,
    Service,
    Territory,
)


class OfficerInline(admin.TabularInline):

    model = Officer
    extra = 0
    fields = ("name", "institutional_id", "position", "status")
    show_change_link = True


@admin.register(Delegation)
class DelegationAdmin(SoftDeleteAdminMixin, admin.ModelAdmin):
    list_display = ("name", "status", "scope", "managers")
    search_fields = ("name", "scope")
    list_filter = ("status",)
    ordering = ("name",)
    inlines = [OfficerInline]


@admin.register(Position)
class PositionAdmin(SoftDeleteAdminMixin, admin.ModelAdmin):
    list_display = ("name", "valid_from", "valid_until")
    search_fields = ("name",)
    ordering = ("name",)


@admin.register(Item)
class ItemAdmin(SoftDeleteAdminMixin, admin.ModelAdmin):
    list_display = ("name", "parent_item", "calculation_type")
    search_fields = ("name",)
    list_filter = ("calculation_type",)
    list_select_related = ("parent_item",)
    ordering = ("name",)


@admin.register(Service)
class ServiceAdmin(SoftDeleteAdminMixin, admin.ModelAdmin):
    list_display = ("name", "status")
    search_fields = ("name",)
    list_filter = ("status",)
    ordering = ("name",)


@admin.register(Beneficiary)
class BeneficiaryAdmin(SoftDeleteAdminMixin, admin.ModelAdmin):
    list_display = ("name", "rut", "phone", "address")
    search_fields = ("name", "rut", "address")
    ordering = ("name",)


@admin.register(PositionItem)
class PositionItemAdmin(SoftDeleteAdminMixin, admin.ModelAdmin):
    list_display = (
        "position",
        "item",
        "kind",
        "weight",
        "max_cap",
        "valid_from",
        "valid_until",
    )
    search_fields = ("position__name", "item__name")
    list_filter = ("position", "kind")
    list_select_related = ("position", "item")
    ordering = ("position__name", "item__name")


@admin.register(Territory)
class TerritoryAdmin(DelegationScopedAdminMixin, admin.ModelAdmin):
    delegation_lookup = "delegation"
    list_display = ("name", "delegation")
    search_fields = ("name", "delegation__name")
    list_filter = ("delegation",)
    list_select_related = ("delegation",)
    ordering = ("delegation__name", "name")


@admin.register(Officer)
class OfficerAdmin(DelegationScopedAdminMixin, admin.ModelAdmin):
    delegation_lookup = "delegation"
    list_display = (
        "name",
        "institutional_id",
        "delegation",
        "position",
        "status",
    )
    search_fields = ("name", "institutional_id", "delegation__name")
    list_filter = ("delegation", "position", "status")
    list_select_related = ("delegation", "position")
    ordering = ("delegation__name", "name")
