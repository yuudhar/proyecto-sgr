"""Funciones de cada cargo según el descriptor de funciones (RF-050): qué se muestra en la ficha personal."""


def duties_of(position):
    """Descripción y funciones vigentes de un cargo, agrupadas en el orden del descriptor.

    Devuelve un diccionario con la `description` del cargo y `groups`, una lista de `{"title", "items"}` donde
    cada función trae su número (`order`) y su `text`. Las funciones sin agrupación quedan en un solo grupo sin
    título. Si el funcionario no tiene cargo o el cargo no tiene funciones, `groups` va vacío.
    """
    if position is None:
        return {"position": None, "description": "", "groups": [], "total": 0}
    groups = []
    by_title = {}
    functions = position.functions.filter(deleted_at__isnull=True).order_by("order", "id")
    total = 0
    for function in functions:
        title = function.group.strip()
        if title not in by_title:
            by_title[title] = {"title": title, "items": []}
            groups.append(by_title[title])
        by_title[title]["items"].append({"order": function.order, "text": function.text})
        total += 1
    return {"position": position, "description": position.description, "groups": groups, "total": total}
