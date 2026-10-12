"""Ingreso con el nombre de usuario o con el correo de la cuenta.

Es el backend de Django (ModelBackend) con una sola diferencia: si lo escrito no es un nombre de usuario y parece un
correo, se busca la cuenta por su correo. Todo lo demás es igual: el usuario debe estar activo, la contraseña se
comprueba con el mismo hash y los permisos salen de los mismos grupos.

Reglas para no abrir huecos:
  - Un nombre de usuario exacto siempre gana: si alguien tiene el usuario «ana@correo.cl», no se le puede quitar el
    ingreso porque el correo de otra persona sea ese texto.
  - Por correo se ingresa solo si hay exactamente una cuenta con ese correo (sin importar mayúsculas). Si hay dos o
    más, no se adivina cuál es: no se entra por correo y cada una puede ingresar con su usuario.
  - Cuando no se encuentra la cuenta se calcula igualmente un hash, para que no se note por el tiempo de respuesta si
    el usuario o el correo existen. El mensaje de error tampoco lo dice.
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend


class EmailOrUsernameBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        UserModel = get_user_model()
        if username is None:
            username = kwargs.get(UserModel.USERNAME_FIELD)
        if username is None or password is None:
            return None
        user = self.find_user(username)
        if user is None:
            UserModel().set_password(password)  # el mismo trabajo que con una cuenta que sí existe
            return None
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None

    def find_user(self, text):
        """La cuenta que corresponde a lo escrito (usuario o correo), o None si no hay una sola."""
        UserModel = get_user_model()
        text = str(text).strip()
        if not text:
            return None
        try:
            return UserModel._default_manager.get_by_natural_key(text)
        except UserModel.DoesNotExist:
            pass
        if "@" not in text:
            return None
        matches = list(UserModel._default_manager.filter(email__iexact=text)[:2])
        return matches[0] if len(matches) == 1 else None
