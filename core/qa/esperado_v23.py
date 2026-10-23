ESPERADO = {
    "DeletedUsersTests": {
        "deleting_a_user_moves_it_to_the_deleted_users_place": "Eliminar un usuario no lo borra de la base: queda inactivo, marcado como eliminado y con el evento en la auditoría.",
        "a_deleted_user_leaves_the_normal_list_and_appears_in_the_deleted_one": "Un usuario eliminado sale del listado normal y aparece en «Usuarios eliminados», con búsqueda y botón Restaurar.",
        "the_normal_list_links_to_the_deleted_users": "El listado de usuarios enlaza a «Usuarios eliminados» y esa vista enlaza de vuelta.",
        "a_deleted_user_cannot_sign_in": "Un usuario eliminado no puede ingresar al sistema.",
        "a_deleted_user_is_restored_but_stays_inactive": "Restaurar devuelve al usuario al listado, pero sigue inactivo hasta que se active en Editar.",
        "the_confirmation_page_explains_where_the_user_goes": "La página de confirmación explica que el usuario pasa a «Usuarios eliminados» y no elimina nada al abrirla.",
        "a_deleted_user_cannot_be_edited": "Un usuario eliminado no se puede editar y su ficha lo indica con la fecha.",
        "a_user_without_a_profile_can_also_be_deleted": "También se puede eliminar un usuario que no tiene perfil asociado.",
        "you_cannot_delete_your_own_account": "Nadie puede eliminar su propia cuenta.",
        "the_list_row_shows_a_delete_button_that_explains_the_own_account_block": "El botón Eliminar de la propia cuenta avisa con SweetAlert2 por qué no se puede.",
    },
    "OnlySuperuserDeletesUsersTests": {
        "a_manager_with_the_delete_permission_cannot_delete_users": "Un gestor con el permiso de eliminar usuarios, pero que no es Super Usuario, recibe 403 al intentarlo.",
        "a_manager_cannot_restore_users": "Un gestor que no es Super Usuario tampoco puede restaurar usuarios: ni siquiera los ve.",
        "a_manager_sees_no_delete_button_and_no_deleted_users_place": "Un gestor no ve botones de eliminar ni el enlace a «Usuarios eliminados».",
        "a_manager_never_sees_the_deleted_users": "Un gestor nunca ve los usuarios eliminados, ni por URL ni con filtros.",
        "the_superuser_does_see_and_restore_them": "El Super Usuario sí los ve y los restaura.",
    },
}
