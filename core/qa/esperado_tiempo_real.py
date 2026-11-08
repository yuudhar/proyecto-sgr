ESPERADO = {
    "AsgiApplicationTests": {
        "the_project_is_served_as_asgi_with_daphne_first": "Daphne va antes de staticfiles, Channels y la app websocket están instaladas y existen ASGI_APPLICATION y la capa de canales.",
        "the_router_separates_http_and_websocket_and_has_the_two_routes": "El enrutador separa HTTP y WebSocket y registra solo las rutas ws/crud/<slug>/ y ws/live/.",
        "a_signed_in_browser_opens_the_socket_through_the_whole_stack": "Un navegador con sesión abre el WebSocket a través de toda la pila (origen, sesión, usuario y enrutamiento).",
        "a_socket_from_a_foreign_origin_is_refused": "Una conexión desde un origen ajeno es rechazada.",
        "a_socket_without_a_session_is_refused": "Una conexión sin sesión es rechazada."
    },
    "LiveListTests": {
        "the_list_page_connects_to_the_live_updates": "El listado trae el indicador «En vivo» y el script que se conecta y vuelve a pedir la tabla por HTTP.",
        "the_deleted_users_view_is_live_too": "La vista «Usuarios eliminados» también se actualiza en vivo (desde la v28).",
        "an_edit_is_announced_to_the_same_delegation_only_after_the_commit": "Una edición se avisa a la misma delegación solo después del commit y la otra delegación no se entera.",
        "creating_archiving_restoring_and_deleting_all_announce": "Crear, archivar, restaurar y eliminar avisan el cambio.",
        "a_failed_save_announces_nothing": "Un guardado que falla no avisa nada.",
        "the_socket_needs_the_permission_to_view_that_module": "Sin el permiso de ver el módulo no se puede escuchar sus cambios.",
        "an_unknown_module_is_refused": "Un módulo que no existe es rechazado.",
        "a_manager_viewing_all_delegations_hears_every_delegation": "Quien ve todas las delegaciones escucha los cambios de cualquiera de ellas.",
        "every_module_can_be_watched_with_its_route_slug": "Todos los mantenedores tienen un identificador compatible con la ruta del WebSocket."
    },
    "LiveDashboardTests": {
        "the_summary_pages_connect_to_the_live_updates": "El dashboard, el tablero de delegación y la pantalla de validar traen la región en vivo, el indicador y el script.",
        "a_live_refresh_does_not_count_as_a_new_visit": "El refresco en vivo del dashboard no cuenta como una visita nueva.",
        "the_live_socket_needs_a_session": "Sin sesión no se puede escuchar los cambios en vivo.",
        "a_change_by_one_user_reaches_the_other_in_the_same_delegation_only": "Un cambio hecho por una persona le llega a otra de la misma delegación (y a quien ve todas), una sola vez, y no a otra delegación.",
        "a_general_change_reaches_every_delegation": "Un cambio general (por ejemplo el período) llega a todas las delegaciones.",
        "moving_a_record_between_delegations_notifies_both": "Si un registro cambia de delegación, se avisa a la anterior y a la nueva.",
        "deleting_and_changing_other_dashboard_data_also_announce": "Compromisos, evidencias y eliminaciones también avisan.",
        "a_rolled_back_change_announces_nothing": "Un cambio que se deshace antes del commit no avisa nada.",
        "data_the_summary_screens_do_not_show_stays_quiet": "Un dato que esas pantallas no muestran (por ejemplo un territorio) no genera avisos.",
        "the_real_edit_screen_announces_to_the_dashboard": "Recorrido completo: guardar una atención desde su formulario avisa a quien tiene el dashboard abierto."
    },
    "UserPhotoByAdminTests": {
        "the_detail_shows_the_photo_or_says_there_is_none": "La ficha del usuario muestra su foto, o «Sin dato» si no tiene.",
        "the_edit_form_accepts_files_and_shows_the_current_photo": "El formulario de editar usuario acepta archivos y muestra la foto actual; «Quitar la foto» aparece solo si hay una.",
        "the_superuser_sets_and_replaces_the_photo_of_another_person": "El Super Usuario sube o reemplaza la foto de otra persona; la anterior se borra al confirmar y queda registrado quién lo hizo.",
        "the_superuser_removes_the_photo_of_another_person": "El Super Usuario quita la foto de otra persona: se borra el archivo y queda en la auditoría.",
        "saving_without_touching_the_photo_keeps_it": "Guardar el usuario sin tocar la foto la conserva.",
        "invalid_files_are_rejected_and_nothing_changes": "Un archivo falso, de otro tipo o de más de 2 MB se rechaza y no cambia nada.",
        "a_new_photo_and_remove_together_is_an_error": "Subir una foto y marcar quitarla a la vez da error.",
        "a_new_user_can_be_created_with_a_photo": "Al crear un usuario se puede subir su foto.",
        "the_person_sees_the_photo_the_superuser_gave_them": "La persona ve en su perfil la foto que le puso el Super Usuario.",
        "only_the_superuser_can_change_someone_elses_photo": "Quien no es Super Usuario no puede cambiar la foto de otra persona."
    },
    "DaphneDeployTests": {
        "the_service_runs_daphne_on_the_asgi_application": "El servicio del servidor ejecuta Daphne sobre la aplicación ASGI y ya no gunicorn.",
        "apache_passes_the_websocket_before_everything_else": "Apache pasa /ws/ al servicio por WebSocket antes de la regla general.",
        "nginx_passes_the_upgrade_headers_for_the_websocket": "nginx envía las cabeceras Upgrade y Connection para el WebSocket.",
        "the_upgrade_script_for_an_existing_server_is_safe_to_repeat": "El script para un servidor ya instalado se puede repetir, valida Apache y guarda una copia.",
        "the_requirements_pin_channels_and_daphne": "Channels y Daphne están fijados por versión en requirements.txt."
    },
    "LiveEverywhereTests": {
        "the_attention_page_refreshes_only_its_results": "La pantalla Atención se actualiza sola en los resultados, sin tocar el buscador que la persona está escribiendo.",
        "a_list_listens_to_its_own_module_and_to_any_other_change": "Un listado escucha los avisos de su mantenedor y también los cambios que se hacen desde otras pantallas.",
        "every_record_sheet_is_live_and_knows_its_module": "La ficha de un registro (territorio, funcionario, actividad, evidencia) se actualiza sola y escucha los cambios de su mantenedor.",
        "the_reports_and_the_administration_hub_are_live": "Informes y Administración se actualizan solos cuando otra persona cambia datos.",
        "a_refresh_of_a_sheet_returns_the_same_region": "Al pedir de nuevo una ficha, el servidor devuelve la región en vivo que el navegador reemplaza.",
        "the_other_screens_with_forms_stay_still": "Los formularios de alta y edición no se reemplazan solos, para no borrar lo que la persona escribe."
    },
    "LiveCatalogChangesTests": {
        "a_catalog_change_reaches_every_delegation": "Un cambio en un catálogo (por ejemplo un territorio) avisa a todas las delegaciones.",
        "a_beneficiary_change_is_announced": "Guardar un beneficiario avisa a las pantallas abiertas.",
        "an_audit_entry_reaches_the_audit_list_but_not_the_dashboards": "Una entrada nueva de auditoría llega al listado de auditoría abierto, pero no a los dashboards.",
        "an_edited_audit_entry_announces_nothing": "Reguardar una entrada de auditoría ya existente no avisa nada."
    },
    "AssetVersionTests": {
        "the_styles_and_scripts_carry_the_version_of_the_delivery": "Los estilos y scripts del sistema llevan la versión de la entrega en su dirección, así el navegador no usa archivos viejos.",
        "the_vendor_libraries_keep_their_plain_address": "Las librerías de terceros (Bootstrap, iconos, SweetAlert2) conservan su dirección normal."
    },
    "EveryScreenIsLiveExceptFormsTests": {
        "every_list_is_live_including_the_deleted_users_view": "Todos los listados de los mantenedores, también «Usuarios eliminados», se actualizan solos.",
        "the_registration_and_edit_forms_are_not_live": "Los formularios de registro y edición (nuevo usuario, nuevo funcionario, mi perfil) no se actualizan solos, para no borrar lo que la persona escribe.",
        "the_evidence_validation_form_is_not_live": "El formulario de validar una evidencia tampoco se reemplaza solo."
    }
}
