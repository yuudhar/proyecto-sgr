ESPERADO = {
    "DateHelperTests": {
        "months_back_keeps_the_day_when_it_exists": "Retroceder meses conserva el día cuando existe, también al cruzar de año.",
        "months_back_uses_the_last_day_of_the_month_when_the_day_does_not_exist": "Retroceder meses usa el último día del mes cuando el día no existe (29 de febrero, día 31).",
        "the_limit_comes_from_the_setting": "El límite sale del ajuste BACKDATE_MONTHS.",
        "the_default_limit_is_twelve_months": "El límite normal es de 12 meses hacia atrás.",
    },
    "CommitmentLimitTests": {
        "the_form_tells_the_browser_the_earliest_date": "El formulario de compromisos le indica al navegador la fecha más antigua, la de hoy como tope y el mensaje de 12 meses.",
        "a_date_from_1997_is_refused_with_a_message": "Una fecha de solicitud de 1997 se rechaza con un mensaje que dice cuál es la más antigua que se acepta.",
        "the_day_before_the_limit_is_refused_and_the_limit_itself_is_accepted": "El día anterior al límite se rechaza y el día del límite se acepta.",
        "an_old_commitment_can_be_edited_while_its_date_is_left_alone": "Un compromiso antiguo se puede seguir editando mientras no se toque su fecha, y el navegador no le pone tope.",
        "an_old_commitment_cannot_move_to_another_old_date": "Un compromiso antiguo no puede pasar a otra fecha antigua.",
    },
    "FollowupLimitTests": {
        "the_form_tells_the_browser_the_earliest_date": "El formulario de gestiones le indica al navegador la fecha más antigua en la fecha de la gestión, la visita y las dos entregas.",
        "an_old_date_of_the_management_is_refused": "Una fecha de gestión de hace más de 12 meses se rechaza y no se guarda.",
        "an_old_visit_date_is_refused": "Una fecha de visita de hace más de 12 meses se rechaza.",
        "a_recent_date_is_accepted": "Una fecha reciente se acepta.",
    },
    "FeedbackLimitTests": {
        "an_old_date_is_refused": "Una carta con fecha de hace más de 12 meses se rechaza.",
        "the_limit_day_and_today_are_not_refused_for_being_too_old": "El día del límite y hoy no se rechazan por antiguos.",
    },
    "AbsenceLimitTests": {
        "the_form_tells_the_browser_the_earliest_date": "El formulario de ausencias le indica al navegador la fecha más antigua para «desde».",
        "an_absence_that_started_in_1997_is_refused": "Una ausencia que empezó en 1997 se rechaza y no se guarda.",
        "the_limit_day_is_accepted": "El día del límite se acepta como inicio de una ausencia.",
        "an_old_absence_can_still_be_corrected_without_touching_its_dates": "Una ausencia antigua se puede corregir sin tocar sus fechas.",
    },
    "QuarterRequestLimitTests": {
        "a_manual_date_older_than_twelve_months_is_refused_by_the_form": "En una solicitud manual de cambio de trimestre, una fecha de hace más de 12 meses se rechaza en el formulario.",
    },
}
