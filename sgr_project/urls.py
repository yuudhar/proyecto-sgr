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
    path('accounts/', include('django.contrib.auth.urls')),
    path('', include('accounts.urls')),
    path('', include('core.urls')),
]
