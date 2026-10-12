from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

from core.health import salud
from core.views import PortalLoginView, PortalLogoutView

urlpatterns = [
    # Revisión de estado del servicio (balanceador, evidencias): sin sesión y sin datos sensibles
    path('salud/', salud, name='salud'),
    path('admin/', admin.site.urls),
    # Rutas de acceso de Django bajo /accounts/: login, logout y las de contraseña.
    # Las cuatro primeras reemplazan a las de Django por las pantallas del portal y van antes del
    # include para que mande la primera que calce: el ingreso y la salida son los del portal, y la
    # recuperación por enlace del correo se cambió por la del código (ver accounts/).
    path('accounts/login/', PortalLoginView.as_view()),
    path('accounts/logout/', PortalLogoutView.as_view()),
    path('accounts/password_change/', RedirectView.as_view(pattern_name='core:profile')),
    path('accounts/password_reset/', RedirectView.as_view(pattern_name='accounts:recover')),
    path('accounts/', include('django.contrib.auth.urls')),
    path('', include('accounts.urls')),
    path('', include('core.urls')),
]
