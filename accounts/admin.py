from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.models import User

from core.admin_mixins import SoftDeleteAdminMixin

from .models import UserProfile


class UserProfileInline(admin.StackedInline):

    model = UserProfile
    can_delete = False
    fk_name = "user"
    extra = 0
    autocomplete_fields = ("officer",)


class UserAdmin(DjangoUserAdmin):
    inlines = (*DjangoUserAdmin.inlines, UserProfileInline)
    list_display = (*DjangoUserAdmin.list_display, "get_delegation")

    @admin.display(description="Delegación")
    def get_delegation(self, obj):
        profile = getattr(obj, "profile", None)
        if profile and profile.officer_id:
            return profile.officer.delegation
        return "—"


admin.site.unregister(User)
admin.site.register(User, UserAdmin)


@admin.register(UserProfile)
class UserProfileAdmin(SoftDeleteAdminMixin, admin.ModelAdmin):
    list_display = ("user", "officer", "status")
    search_fields = ("user__username", "officer__name")
    list_filter = ("status",)
    list_select_related = ("user", "officer")
    autocomplete_fields = ("officer",)
