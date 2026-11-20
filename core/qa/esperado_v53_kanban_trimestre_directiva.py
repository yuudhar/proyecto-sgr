ESPERADO = {
    "QuarterInTopbarTests": {
        "it_shows_the_general_quarter_that_contains_today": "La barra de arriba muestra el trimestre que contiene la fecha de hoy («N.º trimestre AAAA» y sus fechas) con el detalle de que es el general.",
        "the_quarter_of_the_users_delegation_wins_over_the_general_one": "Si la delegación de la persona tiene su propio trimestre, la barra muestra ese; la otra delegación sigue viendo el general.",
        "a_yearly_period_is_shown_as_a_period": "Un período anual se muestra como «Período AAAA».",
        "without_a_period_for_today_it_says_so": "Sin un período vigente para hoy, la barra dice «Sin trimestre vigente».",
        "clients_do_not_see_it": "Los clientes no ven el trimestre en su portal.",
    },
    "FeedbackRenameTests": {
        "the_screen_menu_and_button_use_the_new_name": "El menú, el título del listado y el botón dicen «Felicitaciones y reclamos» y «Nueva felicitación o reclamo»; ya no aparece «Cartas».",
        "the_form_and_the_permission_matrix_use_the_new_name": "El formulario y la fila de la matriz de permisos usan el nombre «Felicitaciones y reclamos».",
    },
    "ViewSwitchTests": {
        "every_screen_with_states_has_the_switch_and_both_views_work": "Las 11 pantallas con estado tienen el botón Lista/Kanban y ambas vistas abren: la lista sin tablero y el Kanban con sus columnas.",
        "the_boards_that_existed_open_as_kanban_and_the_new_ones_as_a_list": "Las pantallas que ya eran tablero (Compromisos, Felicitaciones y reclamos…) abren en Kanban; las nuevas (Agenda, Evidencias…) abren en lista.",
        "the_choice_is_remembered_and_kept_when_searching": "La vista elegida se recuerda por pantalla al volver y se mantiene al buscar; elegir en una pantalla no cambia las demás.",
        "an_unknown_view_is_ignored_and_screens_without_states_have_no_switch": "Un valor de vista desconocido se ignora y las pantallas sin estado (Beneficiarios) no muestran el botón.",
        "each_column_counts_the_whole_filtered_set_not_only_the_page": "El número de cada columna del Kanban es el total del conjunto filtrado aunque la página muestre menos tarjetas, y se avisa cuando la columna se ve parcial.",
        "events_move_from_the_board_and_a_reader_cannot_move_them": "Un evento se mueve de estado desde el tablero; una cuenta de consulta recibe 403 y el evento no cambia.",
        "moving_a_commitment_of_the_agenda_keeps_its_status_history": "Mover un compromiso de la agenda desde el tablero cambia su estado y deja el cambio en su historial.",
    },
    "LeaderBeneficiaryTests": {
        "the_lookup_returns_what_the_system_knows_of_a_rut": "La consulta por RUT (con o sin puntos) devuelve el beneficiario con ese RUT, el nombre y correo conocidos y los cargos de directiva que ya tiene; un RUT inválido se marca como tal.",
        "only_who_can_see_directives_or_beneficiaries_may_ask": "Un cliente recibe 403 al consultar un RUT.",
        "saving_links_the_beneficiary_with_the_same_rut": "Al guardar un integrante de directiva queda vinculado al beneficiario con su mismo RUT y la ficha del beneficiario muestra sus directivas.",
        "a_new_person_is_registered_as_beneficiary_only_when_asked": "Con un RUT nuevo no se crea ningún beneficiario, salvo que se marque «Registrar también como beneficiario»: entonces se crea con ese RUT y nombre y queda vinculado.",
        "changing_the_rut_moves_the_link": "Si se cambia el RUT de un integrante, el vínculo pasa al beneficiario del RUT nuevo.",
        "the_form_asks_for_the_rut_first_and_offers_the_beneficiaries": "El formulario pide primero el RUT, ofrece la lista de beneficiarios para elegir y tiene la casilla para registrarlo.",
        "a_beneficiary_in_a_directive_cannot_be_deleted": "Un beneficiario vinculado a una directiva no se puede eliminar.",
    },
}
ESPERADO["QuartersAheadTests"] = {
    "a_quarter_up_to_ten_years_ahead_is_created_in_each_delegation": "«Agregar trimestre» crea trimestres de años futuros hasta 10 años hacia adelante, en cada delegación marcada.",
    "a_quarter_beyond_ten_years_is_refused_with_the_last_allowed_day": "Un trimestre a más de 10 años se rechaza con un mensaje que dice el último día permitido, y no se crea nada.",
    "the_period_form_has_the_same_limit_and_the_browser_knows_it": "El formulario de Períodos tiene el mismo tope (el 31/12 de dentro de 10 años) y el navegador lo conoce para avisar antes de guardar.",
}
