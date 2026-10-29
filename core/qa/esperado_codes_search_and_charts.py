ESPERADO = {
    "AutomaticCodeTests": {
        "the_evidence_form_does_not_ask_for_the_code": "El formulario de evidencia no pide el código único.",
        "each_evidence_takes_the_next_code_of_its_delegation": "Cada evidencia subida toma el siguiente código de su delegación (EVD-NORTE-0004, 0005…).",
        "archived_evidences_still_count_so_a_code_is_never_reused": "Las evidencias archivadas siguen contando: un código nunca se reutiliza.",
        "a_code_taken_in_the_meantime_is_skipped": "Si otra persona toma el código al mismo tiempo, se reintenta con el siguiente.",
        "a_code_written_by_hand_in_code_is_respected": "Un código entregado por el programa (carga de datos) se respeta tal cual.",
        "the_followup_number_is_assigned_by_the_system_up_to_three": "El número de gestión se asigna solo (1, 2, 3) y la cuarta gestión de una atención se rechaza con un mensaje claro.",
        "the_activity_is_preselected_when_coming_from_its_detail": "Al abrir evidencia o gestión desde la ficha de una atención, la atención ya viene elegida."
    },
    "SearchableSelectTests": {
        "selects_of_related_records_can_be_searched": "Los selectores de actividad y funcionario de los formularios se pueden buscar escribiendo.",
        "the_list_filters_can_be_searched_too": "Los filtros de los listados también se pueden buscar escribiendo.",
        "the_activity_choices_name_the_item_and_do_not_add_queries_per_activity": "Cada actividad de la lista nombra su ítem y agregar 40 actividades no suma consultas a la base.",
        "the_script_is_loaded_by_the_widgets": "El buscador se carga junto con los demás widgets y declara su accesibilidad (combobox, teclado, límite de filas).",
        "the_search_ignores_accents_case_and_word_order": "La búsqueda ignora tildes, mayúsculas y el orden de las palabras."
    },
    "ChartMathTests": {
        "the_donut_arcs_are_proportional_and_follow_one_another": "Los arcos del anillo son proporcionales y se suceden sin huecos.",
        "an_empty_donut_draws_nothing_and_says_so": "Un anillo sin datos no dibuja arcos y lo dice.",
        "the_bars_are_relative_to_the_maximum_and_never_pass_the_track": "Las barras son relativas al máximo y nunca se pasan del riel.",
        "the_columns_scale_to_the_tallest_and_tell_every_value": "Las columnas se escalan a la más alta y el texto alternativo dice cada valor."
    },
    "ChartScreenTests": {
        "the_dashboard_has_charts_for_an_officer": "El inicio del funcionario muestra anillos de evidencias y compromisos y las atenciones de los últimos 14 días.",
        "the_dashboard_has_the_traffic_light_chart_for_management": "El inicio de coordinación muestra el anillo de metas por semáforo.",
        "the_delegation_board_has_charts": "El tablero de delegación muestra el anillo de semáforos y las barras de cumplimiento por funcionario.",
        "the_collective_summary_has_charts": "El resumen colectivo muestra compromisos por estado y realizados por funcionario.",
        "the_reports_have_charts": "Los informes muestran evidencias por estado y actividades por funcionario.",
        "the_charts_follow_the_numbers_of_the_screen": "Los gráficos usan los mismos números que ya muestra la pantalla."
    },
    "LiveFallbackTests": {
        "the_screens_check_themselves_when_the_websocket_does_not_connect": "Si el WebSocket no conecta, la pantalla se revisa sola cada 8 segundos (y cada 60 s como respaldo con WebSocket).",
        "a_refresh_that_changes_nothing_does_not_touch_the_screen": "Una revisión que no encuentra cambios no toca la pantalla (se ignora el token CSRF y el indicador).",
        "the_update_script_leaves_the_server_ready_and_proves_the_websocket": "actualizar.sh deja a Apache y al servicio listos para el WebSocket y lo prueba al terminar."
    },
    "WebsocketProbeTests": {
        "only_daphne_answers_count_as_reaching_the_application": "La prueba del WebSocket solo da por bueno un 101, o el «403 Access denied» propio de Daphne (no el «Forbidden» de Apache)."
    }
}
