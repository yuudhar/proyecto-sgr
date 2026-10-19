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
            UserModel().set_password(password)
            return None
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None

    def find_user(self, text):
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
