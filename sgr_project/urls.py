from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

from core.health import salud
from core.views import PortalLoginView, PortalLogoutView

urlpatterns = [
    path('salud/', salud, name='salud'),
    path('admin/', admin.site.urls),
    path('accounts/login/', PortalLoginView.as_view()),
    path('accounts/logout/', PortalLogoutView.as_view()),
    path('accounts/password_change/', RedirectView.as_view(pattern_name='core:profile')),
    path('accounts/password_reset/', RedirectView.as_view(pattern_name='accounts:recover')),
    # Las pantallas de contraseña olvidada que trae Django llevan a las del portal (el enlace del correo es el de «accounts»).
    path('accounts/password_reset/done/', RedirectView.as_view(pattern_name='accounts:recover_done')),
    path('accounts/reset/done/', RedirectView.as_view(pattern_name='core:login')),
    path('accounts/reset/<uidb64>/<token>/', RedirectView.as_view(pattern_name='accounts:recover_confirm')),
    path('accounts/', include('django.contrib.auth.urls')),
    path('', include('accounts.urls')),
    path('', include('core.urls')),
]

# 400 con la pantalla del portal y sin detalles técnicos; 403, 404 y 500 usan templates/403.html, 404.html y 500.html.
handler400 = 'core.errors.bad_request'
