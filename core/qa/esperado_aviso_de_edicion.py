ESPERADO = {
    "FormMarkupTests": {
        "the_edit_form_tells_the_browser_where_to_ask_and_which_channel_to_listen_to": "El formulario de edición indica la dirección de revisión y el canal en vivo que debe escuchar el navegador.",
        "the_create_form_has_nothing_to_watch": "El formulario de crear no vigila nada, porque todavía no existe el registro.",
        "the_script_is_loaded_on_every_page": "El script del aviso se carga en todas las páginas del portal.",
    },
    "CheckTests": {
        "an_unchanged_record_is_not_stale": "Un registro que nadie tocó responde que no está desactualizado.",
        "after_someone_else_saves_it_says_who_and_what_changed": "Si otra persona guardó, el aviso dice quién y qué cambió.",
        "the_answer_does_not_carry_the_record": "La respuesta del aviso no trae los datos del registro, solo el mensaje.",
        "without_a_version_to_compare_it_is_not_stale": "Sin una versión con la cual comparar, no se avisa nada.",
        "an_archived_record_is_reported_as_gone": "Un registro archivado mientras se edita se informa como ya no disponible.",
        "a_record_out_of_reach_is_reported_as_gone_without_details": "Un registro fuera del alcance de la persona se informa como no disponible, sin detalles.",
        "someone_who_cannot_edit_gets_a_403": "Quien no tiene permiso de editar recibe 403 en la revisión.",
        "it_asks_for_a_session": "La revisión exige haber iniciado sesión.",
        "saving_still_asks_to_review_after_the_warning": "Aunque se ignore el aviso, al guardar el servidor sigue pidiendo revisar los cambios ajenos.",
        "every_editable_crud_has_its_check_route": "Todo mantenedor que se puede editar tiene su ruta de revisión.",
    },
}
