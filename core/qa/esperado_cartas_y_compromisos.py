ESPERADO = {
    "CartasBoardTests": {
        "the_screen_is_called_cartas_and_the_old_address_is_gone": "La pantalla se llama «Cartas» y la dirección antigua de Felicitaciones y reclamos ya no existe.",
        "the_list_is_a_board_with_a_column_for_compliments_and_one_for_complaints": "El listado es un canvas con una columna de felicitaciones y otra de reclamos.",
        "the_cards_show_the_effect_and_the_indicators_count_the_letters": "Las tarjetas muestran el efecto y los indicadores cuentan las cartas de la delegación.",
        "the_board_respects_the_filters_and_the_own_delegation": "El canvas respeta los filtros y no muestra cartas de otra delegación.",
        "the_codes_of_the_cards_start_with_car": "El código de cada tarjeta empieza con CAR.",
        "the_roles_screen_lists_the_module_as_cartas": "La matriz de permisos de Roles nombra el módulo «Cartas».",
    },
    "CompromisosBoardTests": {
        "the_menu_has_compromisos_next_to_the_agenda": "El menú Operación tiene «Compromisos» junto a «Agenda colectiva».",
        "the_list_is_a_board_with_the_four_states": "El listado es un canvas con cuatro columnas: Ingresado, Pendiente, En proceso y Realizado.",
        "the_agenda_and_compromisos_do_not_share_their_lists": "La agenda y Compromisos no comparten listado, pero la ficha abre desde cualquiera de las dos.",
        "the_indicators_count_by_state_and_give_the_resolution_rate": "Los indicadores cuentan por estado y entregan la tasa de resolución.",
        "a_commitment_created_by_hand_in_compromisos_is_physical": "Un compromiso creado a mano en Compromisos queda marcado como de terreno.",
    },
    "CompromisosMoveTests": {
        "a_card_moves_to_the_next_state_and_it_is_left_in_the_history": "Un botón de la tarjeta pasa el compromiso al estado siguiente y lo deja en el historial.",
        "a_move_the_rules_do_not_allow_is_refused_and_nothing_changes": "Un cambio que las reglas no permiten se rechaza y no cambia nada.",
        "a_made_up_state_is_refused": "Un estado inventado se rechaza.",
        "the_cards_only_offer_the_buttons_that_are_allowed": "Cada tarjeta solo ofrece los botones de los estados a los que se puede pasar.",
        "a_reader_gets_403_and_sees_no_buttons": "Un lector recibe 403 al intentar el cambio y no ve los botones.",
        "a_card_of_another_delegation_cannot_be_moved": "Una tarjeta de otra delegación responde 404 y no se mueve.",
        "the_move_needs_a_post_and_a_session": "El cambio exige POST y una sesión iniciada.",
    },
    "AttentionWithVisitTests": {
        "an_attention_with_a_visit_creates_a_physical_commitment": "Una atención con visita crea sola su compromiso de terreno, con estado inicial en el historial.",
        "the_new_commitment_shows_up_in_compromisos_and_not_in_the_agenda": "El compromiso nuevo aparece en Compromisos y no en la agenda colectiva.",
        "the_message_says_the_commitment_went_to_compromisos": "El aviso dice que el compromiso se creó en Compromisos.",
        "the_pipeline_box_alone_still_goes_to_the_agenda": "La casilla del tubo, sola, sigue creando el compromiso en la agenda colectiva.",
        "both_boxes_create_a_single_physical_commitment": "Con las dos casillas se crea un solo compromiso, de terreno.",
        "a_visit_without_date_and_territory_is_refused": "Una visita sin fecha comprometida ni territorio se rechaza y no crea nada.",
        "without_any_box_no_commitment_is_created": "Sin ninguna casilla no se crea compromiso.",
        "the_form_shows_the_date_and_the_territory_for_either_box": "El formulario muestra la fecha y el territorio al marcar cualquiera de las dos casillas.",
    },
    "ReportsCountEverythingTests": {
        "the_collective_summary_counts_the_physical_commitments_too": "El resumen colectivo cuenta también los compromisos de terreno.",
    },
}
