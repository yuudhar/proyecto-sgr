
from django.core.exceptions import PermissionDenied


def get_user_delegation(request):

    if request.user.is_superuser:
        return None

    profile = getattr(request.user, "profile", None)
    if (
        profile is None
        or profile.officer_id is None
        or profile.officer.delegation_id is None
    ):
        raise PermissionDenied(
            "El usuario no tiene una delegación asignada; contacte a Coordinación."
        )

    return profile.officer.delegation
