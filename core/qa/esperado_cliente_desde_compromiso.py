ESPERADO = {
    "ButtonTests": {
        "the_button_is_offered_for_an_external_requester_of_the_agenda": "La ficha de un compromiso de la agenda con solicitante externo ofrece «Crear cuenta de cliente» a quien puede crear usuarios y beneficiarios.",
        "the_button_is_not_offered_to_someone_who_cannot_create_users": "Quien no puede crear usuarios no ve el botón.",
        "the_button_needs_both_permissions": "El botón pide los dos permisos: crear usuarios y crear beneficiarios.",
        "the_button_is_not_offered_for_an_internal_requester": "Un solicitante interno no tiene botón.",
        "a_field_commitment_has_no_button": "Un compromiso de terreno no tiene botón: su persona ya viene de la atención.",
    },
    "CreationTests": {
        "the_form_starts_with_the_name_of_the_requester": "La pantalla parte con el nombre del solicitante.",
        "a_new_rut_creates_the_beneficiary_and_goes_to_the_new_user": "Un RUT nuevo crea el beneficiario con sus datos y sigue a «Nuevo usuario».",
        "a_wrong_rut_is_refused_and_nothing_is_created": "Un RUT con dígito verificador malo se rechaza y no se crea nada.",
        "a_rut_that_already_exists_reuses_the_beneficiary": "Un RUT que ya existe reutiliza el beneficiario, sin duplicarlo ni cambiarle los datos.",
        "a_beneficiary_that_already_has_an_account_is_not_offered_again": "Un beneficiario que ya tiene cuenta no se ofrece de nuevo y se avisa con qué usuario ingresa.",
        "the_creation_is_left_in_the_audit_log": "La creación del beneficiario queda en la auditoría.",
    },
    "AccessTests": {
        "someone_without_the_permissions_is_refused": "Sin los permisos la pantalla responde 403, tanto al abrirla como al enviarla, y no se crea nada.",
        "an_internal_or_field_commitment_does_not_open": "Un compromiso interno o de terreno no abre esta pantalla (404).",
        "a_commitment_of_another_delegation_does_not_open_for_someone_with_a_delegation": "Una persona con delegación no abre un compromiso de otra delegación (404).",
        "the_page_needs_a_session": "Sin sesión la pantalla lleva al ingreso.",
    },
    "NewUserStartTests": {
        "the_new_user_starts_as_a_client_of_the_beneficiary": "«Nuevo usuario» parte con el perfil Cliente y el beneficiario elegidos.",
        "a_beneficiary_with_an_account_does_not_prefill": "Un beneficiario que ya tiene cuenta no se rellena.",
        "a_wrong_value_does_not_prefill": "Un valor que no es un identificador, o que no existe, no rellena nada.",
        "the_whole_path_leaves_a_client_account": "El camino completo, desde la agenda hasta guardar el usuario, deja una cuenta de cliente ligada al beneficiario.",
    },
}
