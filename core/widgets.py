"""Campos de formulario propios: selector de color, buscador de una lista, perfiles con su descripción,
delegaciones de un usuario, matriz de permisos y lista que depende de otra."""

from django import forms

from accounts.models import role_details
from core.colors import HEX_COLOR, clean_color
from core.roles import ACTIONS, PERMISSION_MODULES, permission_key, role_info


class ColorWidget(forms.TextInput):
    """Texto #RRGGBB con una muestra del color y, con JavaScript, el selector de color del navegador.

    Sin JavaScript queda el campo de texto con su muestra, que también sirve.
    """

    template_name = "core/widgets/color.html"

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        text = str(value or "")
        # La muestra va dentro de un estilo: solo se escribe si el texto es exactamente un color.
        context["widget"]["swatch"] = text if HEX_COLOR.fullmatch(text) else ""
        return context


class LookupWidget(forms.TextInput):
    """Texto libre con sugerencias y un botón de lupa que abre la lista para elegir de ahí.

    options es una lista de (texto a escribir en el campo, detalle que se ve junto a él).
    search_label es lo que dice el cuadro de búsqueda de la ventana de la lupa ("Buscar por RUT, nombre o dirección").
    """

    template_name = "core/widgets/lookup.html"

    def __init__(self, attrs=None, options=(), search_label=""):
        super().__init__(attrs)
        self.options = list(options)
        self.search_label = search_label

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        list_id = f"{context['widget']['attrs'].get('id', name)}_opciones"
        context["widget"]["attrs"]["list"] = list_id
        context["widget"]["list_id"] = list_id
        context["widget"]["options"] = self.options
        context["widget"]["search_label"] = self.search_label
        return context


class RolesWidget(forms.CheckboxSelectMultiple):
    """Casillas de los perfiles de un usuario, cada una con lo que permite hacer ese perfil."""

    template_name = "core/widgets/roles.html"

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        for _group, options, _index in context["widget"]["optgroups"]:
            for option in options:
                info = role_info(str(option["label"]))
                group = getattr(option["value"], "instance", None)
                if group is not None:
                    # Lo que dice la ficha del rol (la que se escribe en el mantenedor de Roles) manda sobre el texto de fábrica.
                    info["description"] = role_details(group).description or info["description"]
                option["info"] = info
        return context


class DelegationsWidget(forms.CheckboxSelectMultiple):
    """Casillas de las delegaciones adicionales de un usuario, cada una con su color y su código.

    Sin JavaScript sirve igual: son casillas normales. El color solo acompaña: la delegación se reconoce por su
    código y su nombre, que son lo que dice cada casilla.
    """

    template_name = "core/widgets/delegations.html"

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        for _group, options, _index in context["widget"]["optgroups"]:
            for option in options:
                delegation = getattr(option["value"], "instance", None)
                # El color va dentro de un estilo: solo se escribe si es exactamente un #RRGGBB.
                option["color"] = clean_color(delegation.color) if delegation is not None else clean_color("")
        return context


class PermissionMatrixWidget(forms.CheckboxSelectMultiple):
    """Matriz de permisos de un perfil: una fila por módulo y una columna por acción (Ver, Crear, Editar, Eliminar).

    Cada casilla es un permiso de Django. Si un módulo no tiene una acción (por ejemplo, la auditoría no se
    edita), esa celda queda con una raya. Sin JavaScript sirve igual: son casillas normales.
    """

    template_name = "core/widgets/permissions.html"

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        selected = {str(item) for item in (value or [])}
        base_id = context["widget"]["attrs"].get("id", name)

        # (módulo, acción) -> (id del permiso, texto de la acción)
        found = {}
        for choice, _label in self.choices:
            permission = getattr(choice, "instance", None)
            if permission is not None:
                found[permission_key(permission)] = str(choice.value)

        sections = []
        for title, modules in PERMISSION_MODULES:
            rows = []
            for module_label, key in modules:
                cells = []
                for action, action_label in ACTIONS:
                    pk = found.get((key, action))
                    cells.append(
                        {
                            "action": action,
                            "label": action_label,
                            "exists": pk is not None,
                            "name": name,
                            "value": pk,
                            "id": f"{base_id}_{pk}",
                            "checked": pk in selected,
                        }
                    )
                rows.append({"label": module_label, "cells": cells})
            sections.append({"title": title, "rows": rows})
        context["widget"]["sections"] = sections
        context["widget"]["actions"] = [{"key": key, "label": label} for key, label in ACTIONS]
        return context


class DependentSelect(forms.Select):
    """Lista desplegable que depende de otra: solo muestra las opciones del valor elegido en la primera.

    depends_on es el id de la lista de la que depende y parent_attr, el atributo de cada registro que dice de
    cuál depende (por ejemplo "parent_item_id"). Cada opción lleva data-parent (la opción de la primera lista
    a la que pertenece) y data-name (su nombre corto); con JavaScript solo se ven las del valor elegido
    (core/static/core/js/widgets.js) y sin JavaScript se ven todas, cada una con el nombre de su padre.

    choose_if_options dice que hay que elegir una opción solo cuando la primera lista deja alguna para elegir
    (la Sub Atención de un Tipo que no tiene sub atenciones se deja vacía). Eso lo hace el navegador con JavaScript;
    sin JavaScript la lista no marca nada como obligatorio y el servidor revisa lo que corresponde.
    """

    def __init__(
        self,
        attrs=None,
        choices=(),
        depends_on="",
        parent_attr="parent_item_id",
        empty_parent="",
        empty_children="",
        cleared_message="",
        choose_if_options=False,
    ):
        super().__init__(attrs, choices)
        self.depends_on = depends_on
        self.parent_attr = parent_attr
        self.choose_if_options = choose_if_options
        # Textos de la lista cuando todavía no se eligió la primera, cuando la elegida no tiene opciones y cuando
        # la selección se limpia porque dejó de ser válida.
        self.empty_parent = empty_parent
        self.empty_children = empty_children
        self.cleared_message = cleared_message

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        extra = context["widget"]["attrs"]
        extra["data-depends-on"] = self.depends_on
        if self.choose_if_options:
            extra["data-choose-if-options"] = "1"
        for key, text in (
            ("data-empty-parent", self.empty_parent),
            ("data-empty-children", self.empty_children),
            ("data-cleared-message", self.cleared_message),
        ):
            if text:
                extra[key] = text
        return context

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        instance = getattr(value, "instance", None)
        if instance is not None:
            parent = getattr(instance, self.parent_attr, None)
            option["attrs"]["data-parent"] = "" if parent is None else str(parent)
            option["attrs"]["data-name"] = str(getattr(instance, "name", ""))
        return option
