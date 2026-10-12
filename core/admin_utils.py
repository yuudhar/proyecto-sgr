from django.core.exceptions import PermissionDenied

NO_DELEGATION_MESSAGE = "El usuario no tiene una delegación asignada; contacte a Coordinación."


def get_user_delegation(request):
    """Delegación de la persona según su funcionario; None para el superusuario.

    La usa el Django Admin, que no tiene selector de delegación: allí cada persona trabaja en la de su funcionario.
    Las pantallas web usan core.access.request_delegation, que además respeta la delegación elegida en la franja
    de arriba.
    """

    if request.user.is_superuser:
        return None

    profile = getattr(request.user, "profile", None)
    if (
        profile is None
        or profile.officer_id is None
        or profile.officer.delegation_id is None
    ):
        raise PermissionDenied(NO_DELEGATION_MESSAGE)

    return profile.officer.delegation
