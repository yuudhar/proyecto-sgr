ESPERADO = {
    "SectionTests": {
        "the_activity_file_has_the_comments_section_with_a_form": "La ficha de la actividad tiene la sección Comentarios con su formulario.",
        "commitments_of_the_agenda_and_of_the_field_have_it_too": "Los compromisos de la agenda y de terreno también tienen la sección.",
        "the_evidence_file_has_it": "La ficha de la evidencia tiene la sección Comentarios.",
        "other_files_do_not_have_it": "Las demás fichas no muestran la sección de comentarios.",
        "comments_are_shown_oldest_first_with_author_and_date": "Los comentarios se muestran del más antiguo al más nuevo, con autor y fecha.",
        "the_comments_of_one_record_do_not_show_on_another": "Los comentarios de un registro no aparecen en otro.",
        "the_text_is_escaped": "El texto del comentario se escapa y no se interpreta como HTML.",
        "an_archived_record_shows_its_comments_but_no_form": "Un registro archivado muestra sus comentarios pero no el formulario para comentar.",
    },
    "AddTests": {
        "a_comment_is_saved_with_author_record_delegation_and_audit": "El comentario se guarda con autor, registro, delegación y queda en la auditoría.",
        "the_comment_shows_on_the_file_with_the_name_of_who_wrote_it": "El comentario aparece en la ficha con el nombre de quien lo escribió.",
        "an_empty_comment_is_refused": "Un comentario vacío o solo con espacios se rechaza.",
        "a_comment_over_the_limit_is_refused": "Un comentario de más de 1000 caracteres se rechaza con su mensaje.",
        "someone_who_only_consults_sees_them_but_cannot_comment": "Quien solo consulta ve los comentarios pero no puede escribir.",
        "nobody_comments_on_a_record_of_another_delegation": "Nadie puede comentar un registro de otra delegación.",
        "an_archived_record_takes_no_comments": "Un registro archivado no recibe comentarios.",
        "it_needs_post_and_a_session": "Comentar exige sesión iniciada y el método POST.",
        "a_commitment_and_an_evidence_take_comments_too": "Un compromiso y una evidencia también reciben comentarios, guardados con su propio tipo.",
    },
    "DeleteTests": {
        "the_author_deletes_their_own_comment": "El autor puede eliminar su propio comentario y queda en la auditoría.",
        "someone_else_cannot_delete_it_and_does_not_see_the_button": "Otra persona no puede eliminarlo ni ve el botón.",
        "a_super_user_can_delete_any_comment": "El Super Usuario puede eliminar cualquier comentario.",
        "a_comment_of_another_record_cannot_be_deleted_through_this_one": "Un comentario de otro registro no se puede eliminar por la ruta de este.",
        "a_deleted_comment_cannot_be_deleted_again": "Un comentario ya eliminado no se puede eliminar otra vez.",
    },
    "PermissionTests": {
        "the_roles_that_work_on_records_can_comment": "Coordinación, Jefatura, Funcionario y Verificador pueden comentar.",
        "consulta_only_reads_and_the_client_gets_nothing": "Consulta solo lee los comentarios y Cliente no recibe ningún permiso.",
        "nobody_can_edit_a_comment": "Nadie puede editar un comentario: no existe esa ruta.",
    },
    "LiveTests": {
        "a_comment_warns_the_delegation_that_something_changed": "Un comentario nuevo avisa en vivo a la delegación, sin enviar su texto.",
        "the_live_refresh_keeps_what_is_being_typed": "La actualización en vivo conserva lo que alguien está escribiendo en el comentario.",
    },
}
