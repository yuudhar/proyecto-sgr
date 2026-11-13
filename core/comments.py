"""Comentarios de coordinación sobre un registro (atención, compromiso o evidencia).

Una persona que ya puede ver el registro deja un comentario con su nombre y la fecha; los demás lo ven en la
misma ficha, y se actualiza solo (el comentario avisa a su delegación como cualquier otro dato en vivo).
El comentario no se edita: quien lo escribió, o un Super Usuario, puede eliminarlo. Todo queda en la auditoría.
"""

from django import forms
from django.urls import reverse

from core import ui
from core.models import Comment

MAX_SHOWN = 100
AUDIT_TEXT_LENGTH = 120


class CommentForm(forms.ModelForm):
    class Meta:
        model = Comment
        fields = ("text",)
        labels = {"text": "Nuevo comentario"}
        widgets = {
            "text": forms.Textarea(
                attrs={
                    "rows": 3,
                    "maxlength": Comment.MAX_LENGTH,
                    "placeholder": "Escribe lo que necesita saber quien revise este registro.",
                    "data-keep-draft": "",
                }
            )
        }
        error_messages = {"text": {"required": "Escribe el comentario antes de enviarlo."}}

    def clean_text(self):
        text = self.cleaned_data["text"].strip()
        if not text:
            raise forms.ValidationError("Escribe el comentario antes de enviarlo.")
        if len(text) > Comment.MAX_LENGTH:
            raise forms.ValidationError(f"El comentario no puede pasar de {Comment.MAX_LENGTH} caracteres.")
        return text


def comments_of(obj):
    return Comment.objects.filter(
        entity=obj.__class__.__name__, record_id=obj.pk, deleted_at__isnull=True
    ).select_related("author")


def author_name(user):
    return user.get_full_name() or user.get_username()


def can_delete(user, comment):
    return comment.author_id == user.pk or user.has_perm("core.delete_comment")


def audit_text(text):
    return text if len(text) <= AUDIT_TEXT_LENGTH else text[: AUDIT_TEXT_LENGTH - 3] + "..."


def panel(request, crud, obj, archived):
    """Datos de la sección «Comentarios» de una ficha, o None si esa ficha no los lleva."""
    user = request.user
    if not crud.comments or not user.has_perm("core.view_comment"):
        return None
    queryset = comments_of(obj)
    total = queryset.count()
    # Se muestran los más recientes, de más antiguo a más nuevo, como una conversación.
    shown = list(queryset.order_by("-created_at", "-id")[:MAX_SHOWN])[::-1]
    items = [
        {
            "author": author_name(comment.author),
            "when": ui.fmt_datetime(comment.created_at),
            "text": comment.text,
            "delete_url": reverse(f"core:{crud.route_name('comment_delete')}", args=[obj.pk, comment.pk])
            if can_delete(user, comment)
            else "",
        }
        for comment in shown
    ]
    can_add = user.has_perm("core.add_comment") and not archived
    return {
        "items": items,
        "total": total,
        "hidden": total - len(items),
        "can_add": can_add,
        "add_url": crud.url("comment", obj.pk) if can_add else "",
        "form": CommentForm() if can_add else None,
    }
