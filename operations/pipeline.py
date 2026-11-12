"""RF-018 y tubo de trabajo: una atención marcada «ingresa al tubo» o «requiere visita» crea su compromiso.

Si la atención requiere visita (algo físico), el compromiso va a la sección Compromisos (`physical=True`); si solo
ingresa al tubo de trabajo, va a la agenda colectiva.

El compromiso se arma con lo que ya dice la atención (solicitante, descripción, fecha, delegación y funcionario
responsable) más los dos datos que la atención no tiene y que se piden en el mismo formulario: la fecha comprometida y
el territorio. Queda enlazado a la atención (`Activity.commitment`) para no crearlo dos veces.
"""
from .models import Commitment


def origin_label(activity):
    """«Atención ATN00012»: el identificador que la atención muestra en su listado."""
    return f"Atención ATN{activity.pk:05d}"


def create_commitment(activity, due_date, territory):
    """Crea el compromiso de una atención y lo enlaza. Si la atención ya tiene uno, no crea otro y lo devuelve.

    Es un compromiso de terreno (`physical`) cuando la atención requiere visita.
    """
    if activity.commitment_id:
        return activity.commitment
    commitment = Commitment.objects.create(
        source=origin_label(activity)[:100],
        request_date=activity.date,
        description=activity.request_description or None,
        requester=(activity.contact_name or "Sin nombre")[:100],
        territory=territory,
        due_date=due_date,
        responsible_officer=activity.author_officer,
        delegation=activity.delegation,
        physical=activity.requires_visit,
    )
    type(activity).objects.filter(pk=activity.pk).update(commitment=commitment)
    activity.commitment = commitment
    return commitment
