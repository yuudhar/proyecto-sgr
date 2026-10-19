from django import forms

from accounts.models import role_details
from core.colors import HEX_COLOR, clean_color
from core.roles import ACTIONS, PERMISSION_MODULES, permission_key, role_info


class ColorWidget(forms.TextInput):

    template_name = "core/widgets/color.html"

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        text = str(value or "")
        context["widget"]["swatch"] = text if HEX_COLOR.fullmatch(text) else ""
        return context


class LookupWidget(forms.TextInput):

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

    template_name = "core/widgets/roles.html"

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        for _group, options, _index in context["widget"]["optgroups"]:
            for option in options:
                info = role_info(str(option["label"]))
                group = getattr(option["value"], "instance", None)
                if group is not None:
                    info["description"] = role_details(group).description or info["description"]
                option["info"] = info
        return context


class DelegationsWidget(forms.CheckboxSelectMultiple):

    template_name = "core/widgets/delegations.html"

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        for _group, options, _index in context["widget"]["optgroups"]:
            for option in options:
                delegation = getattr(option["value"], "instance", None)
                option["color"] = clean_color(delegation.color) if delegation is not None else clean_color("")
        return context


class PermissionMatrixWidget(forms.CheckboxSelectMultiple):

    template_name = "core/widgets/permissions.html"

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        selected = {str(item) for item in (value or [])}
        base_id = context["widget"]["attrs"].get("id", name)

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
