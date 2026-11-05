"""Recalcula los indicadores cuando cambia algo que afecta el avance (RF-022: «cambia al validar o anular»).

Se dispara al guardar o eliminar una actividad, una evidencia o una validación (el avance), una meta (objetivo,
ponderador, ítem) o un período (fechas, umbrales y tope). Se ejecuta después del commit, para ver los datos ya
confirmados; si la transacción se deshace no se recalcula nada.
"""
from django.db import transaction
from django.db.models import Q
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from evidence.models import Evidence, Validation
from operations.models import Activity
from organization.models import Item

from . import calculation
from .models import Absence, Goal, Period


def item_ids_of(item_id, parent_id):
    return {value for value in (item_id, parent_id) if value}


def activity_target(activity):
    return (
        activity.author_officer_id,
        frozenset(item_ids_of(activity.item_id, getattr(activity.item, "parent_item_id", None))),
        activity.date,
    )


def run_later(function, *args):
    if calculation.is_suspended():
        return
    transaction.on_commit(lambda: function(*args))


def recalculate_targets(targets):
    for officer_id, item_ids, on_date in targets:
        calculation.recalculate_for(officer_id, set(item_ids), on_date)


@receiver(pre_save, sender=Activity, dispatch_uid="calc-activity-pre")
def remember_previous_activity(sender, instance, raw=False, **kwargs):
    instance._calc_previous = None
    if raw or instance.pk is None:
        return
    before = Activity.objects.filter(pk=instance.pk).select_related("item").first()
    if before is not None:
        instance._calc_previous = activity_target(before)


@receiver(post_save, sender=Activity, dispatch_uid="calc-activity-save")
def activity_saved(sender, instance, raw=False, **kwargs):
    if raw:
        return
    targets = {activity_target(instance)}
    previous = getattr(instance, "_calc_previous", None)
    if previous is not None:
        targets.add(previous)
    run_later(recalculate_targets, targets)


@receiver(post_delete, sender=Activity, dispatch_uid="calc-activity-delete")
def activity_deleted(sender, instance, **kwargs):
    run_later(recalculate_targets, {activity_target(instance)})


def evidence_changed(evidence):
    activity = Activity.objects.filter(pk=evidence.activity_id).select_related("item").first()
    if activity is not None:
        run_later(recalculate_targets, {activity_target(activity)})


@receiver(post_save, sender=Evidence, dispatch_uid="calc-evidence-save")
def evidence_saved(sender, instance, raw=False, **kwargs):
    if not raw:
        evidence_changed(instance)


@receiver(post_delete, sender=Evidence, dispatch_uid="calc-evidence-delete")
def evidence_deleted(sender, instance, **kwargs):
    evidence_changed(instance)


@receiver(post_save, sender=Validation, dispatch_uid="calc-validation-save")
def validation_saved(sender, instance, raw=False, **kwargs):
    if not raw:
        evidence_changed(instance.evidence)


@receiver(post_delete, sender=Validation, dispatch_uid="calc-validation-delete")
def validation_deleted(sender, instance, **kwargs):
    evidence_changed(instance.evidence)


def recalculate_goal_by_id(goal_id):
    goal = Goal.objects.filter(pk=goal_id).select_related("period", "officer", "item").first()
    if goal is not None:
        calculation.recalculate_goal(goal)


def recalculate_period_by_id(period_id):
    period = Period.objects.filter(pk=period_id).first()
    if period is not None:
        calculation.recalculate_period(period)


@receiver(post_save, sender=Goal, dispatch_uid="calc-goal-save")
def goal_saved(sender, instance, raw=False, **kwargs):
    if not raw:
        run_later(recalculate_goal_by_id, instance.pk)


@receiver(post_save, sender=Period, dispatch_uid="calc-period-save")
def period_saved(sender, instance, raw=False, **kwargs):
    if not raw:
        run_later(recalculate_period_by_id, instance.pk)


@receiver(pre_save, sender=Item, dispatch_uid="calc-item-pre")
def remember_item_scores(sender, instance, raw=False, **kwargs):
    instance._scores_before = None
    if raw or instance.pk is None:
        return
    instance._scores_before = Item.objects.filter(pk=instance.pk).values_list("scores", flat=True).first()


def refresh_item_activities(item_id):
    """RF-043: si un ítem pasa a otorgar o no punto, sus actividades (y las de sus sub atenciones) se reclasifican."""
    targets = set()
    activities = (
        Activity.objects.filter(Q(item_id=item_id) | Q(item__parent_item_id=item_id), deleted_at__isnull=True)
        .select_related("item__parent_item", "beneficiary")
    )
    for activity in activities:
        reason = activity.score_reason()
        if activity.no_score_reason != reason or activity.counts_for_score != (not reason):
            Activity.objects.filter(pk=activity.pk).update(counts_for_score=not reason, no_score_reason=reason)
            targets.add(activity_target(activity))
    if targets:
        recalculate_targets(targets)


@receiver(post_save, sender=Item, dispatch_uid="calc-item-save")
def item_saved(sender, instance, raw=False, created=False, **kwargs):
    if raw or created:
        return
    before = getattr(instance, "_scores_before", None)
    if before is not None and before != instance.scores:
        run_later(refresh_item_activities, instance.pk)


def recalculate_absence_periods(officer_id, start_date, end_date):
    """RF-047: una ausencia cambia la meta del funcionario en los períodos que toca."""
    for period in Period.objects.filter(
        deleted_at__isnull=True, start_date__lte=end_date, end_date__gte=start_date
    ):
        calculation.recalculate_officer(officer_id, period)


@receiver(pre_save, sender=Absence, dispatch_uid="calc-absence-pre")
def remember_previous_absence(sender, instance, raw=False, **kwargs):
    instance._calc_previous = None
    if raw or instance.pk is None:
        return
    before = Absence.objects.filter(pk=instance.pk).values_list("officer_id", "start_date", "end_date").first()
    instance._calc_previous = before


@receiver(post_save, sender=Absence, dispatch_uid="calc-absence-save")
def absence_saved(sender, instance, raw=False, **kwargs):
    if raw:
        return
    run_later(recalculate_absence_periods, instance.officer_id, instance.start_date, instance.end_date)
    previous = getattr(instance, "_calc_previous", None)
    if previous is not None and previous != (instance.officer_id, instance.start_date, instance.end_date):
        run_later(recalculate_absence_periods, *previous)


@receiver(post_delete, sender=Absence, dispatch_uid="calc-absence-delete")
def absence_deleted(sender, instance, **kwargs):
    run_later(recalculate_absence_periods, instance.officer_id, instance.start_date, instance.end_date)
