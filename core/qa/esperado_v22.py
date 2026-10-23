ESPERADO = {
    "RealDeleteTests": {
        "the_catalogs_that_can_be_deleted_for_good_are_the_expected_ones": "Solo se pueden eliminar de verdad Beneficiarios, Territorios, Servicios, Cargos, Tipos de gestión, Agenda y Roles.",
        "a_record_that_nobody_uses_is_deleted_for_good": "Un registro que nadie usa se elimina de la base y deja el evento en la auditoría.",
        "every_catalog_deletes_an_unused_record_and_says_so": "Cada catálogo elimina un registro sin uso y avisa con un mensaje de éxito.",
        "a_record_in_use_is_not_deleted_and_the_reason_is_shown": "Un registro en uso no se elimina y se muestra el motivo.",
        "a_territory_with_commitments_is_not_deleted": "Un territorio con compromisos no se elimina.",
        "the_list_tells_sweetalert_why_a_delete_is_blocked": "El listado entrega a SweetAlert2 el motivo por el que no se puede eliminar.",
        "archive_and_delete_are_two_separate_actions_where_both_exist": "Donde existen las dos acciones, «Archivar» y «Eliminar» son botones distintos.",
        "a_catalog_that_only_archives_keeps_its_single_delete_button": "Un mantenedor que solo archiva conserva su único botón «Eliminar».",
        "the_edit_modal_offers_archive_and_delete": "La ventana de edición ofrece archivar y eliminar.",
        "an_archived_record_can_still_be_deleted_for_good": "Un registro archivado también se puede eliminar de verdad.",
        "the_no_javascript_archive_page_says_archivar": "Sin JavaScript, la página de archivar dice «Archivar» y la de un mantenedor que solo archiva sigue diciendo «Eliminar».",
        "without_the_delete_permission_nothing_is_deleted": "Sin el permiso de eliminar (o sin sesión) no se elimina nada.",
        "a_delete_only_works_by_post": "Eliminar solo funciona por POST: abrir la página de confirmación no borra.",
    },
    "ListToolsTests": {
        "every_catalog_with_a_real_delete_has_search_and_a_filter": "Cada catálogo con eliminación real tiene buscador y al menos un filtro.",
        "catalogs_without_fields_to_filter_get_the_state_filter": "Beneficiarios, Cargos y Tipos de gestión, que no tienen campos para filtrar, usan el filtro de estado.",
        "the_state_filter_shows_only_the_archived_ones": "El filtro de estado «Inactivo» muestra solo los archivados.",
        "the_state_filter_combines_with_search_and_keeps_the_page_links": "El filtro de estado se combina con la búsqueda y los enlaces de página conservan ambos.",
        "items_can_now_be_searched": "El listado de Ítems ahora tiene buscador.",
    },
}
