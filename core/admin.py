from django.contrib import admin

from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):

    list_display = (
        "date",
        "event",
        "affected_entity",
        "record_id",
        "user",
    )
    list_filter = ("affected_entity", "event")
    search_fields = ("affected_entity", "event", "user__username")
    list_select_related = ("user",)
    ordering = ("-date",)
    date_hierarchy = "date"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
