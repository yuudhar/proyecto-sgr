import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")


SECRET_KEY = os.environ.get(
    "SECRET_KEY", "django-insecure-solo-para-desarrollo-cambiar-en-env"
)

DEBUG = os.environ.get("DEBUG", "True") == "True"

ALLOWED_HOSTS = [
    host.strip()
    for host in os.environ.get("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
    if host.strip()
]


INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'core',
    'organization',
    'accounts',
    'planning',
    'operations',
    'evidence',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'core.middleware.PortalLocaleMiddleware',
    'core.middleware.PortalNoCacheMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'sgr_project.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'core.context_processors.portal',
            ],
        },
    },
]

WSGI_APPLICATION = 'sgr_project.wsgi.application'


DB_ENGINE = os.environ.get("DB_ENGINE", "sqlite").strip().lower()

if DB_ENGINE in ("mysql", "mariadb"):
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.mysql',
            'NAME': os.environ.get("DB_NAME", "sgr_db"),
            'USER': os.environ.get("DB_USER", "root"),
            'PASSWORD': os.environ.get("DB_PASSWORD", ""),
            'HOST': os.environ.get("DB_HOST", "localhost"),
            'PORT': os.environ.get("DB_PORT", "3306"),
            'OPTIONS': {'charset': 'utf8mb4'},
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / os.environ.get("DB_NAME", "db.sqlite3"),
        }
    }


AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True


STATIC_URL = 'static/'


DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


# Correo saliente (lo usa la recuperación de contraseña, accounts/recovery.py).
# Sin EMAIL_HOST en el .env el correo no sale de la máquina: se imprime en la terminal donde corre
# runserver, así se puede probar el flujo sin servidor de correo. Con EMAIL_HOST (Mailtrap, un SMTP
# real) se envía de verdad. Las credenciales van solo en el .env, que nunca se sube al repositorio.
EMAIL_HOST = os.environ.get("EMAIL_HOST", "")
EMAIL_BACKEND = os.environ.get("EMAIL_BACKEND") or (
    'django.core.mail.backends.smtp.EmailBackend'
    if EMAIL_HOST
    else 'django.core.mail.backends.console.EmailBackend'
)
try:
    EMAIL_PORT = int(os.environ.get("EMAIL_PORT") or 587)
except ValueError:
    raise ImproperlyConfigured("EMAIL_PORT del .env tiene que ser un número, por ejemplo 587.") from None
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
# Los puertos 587 y 2525 usan TLS; el 465 usa SSL (EMAIL_USE_SSL=True). Django no deja activar los dos a la vez.
EMAIL_USE_SSL = (os.environ.get("EMAIL_USE_SSL") or "False").strip().lower() == "true"
EMAIL_USE_TLS = (os.environ.get("EMAIL_USE_TLS") or "True").strip().lower() == "true" and not EMAIL_USE_SSL
EMAIL_TIMEOUT = 10  # segundos de espera por el servidor de correo
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL") or "noreply@proyecto.local"


# Interfaz web (Bootstrap)
# Las pantallas fuera de /admin/ salen en español y con la hora de Chile.
# El Admin sigue con LANGUAGE_CODE y TIME_ZONE de más arriba.
PORTAL_LANGUAGE = 'es'
PORTAL_TIME_ZONE = 'America/Santiago'

# Inicio de sesión de las pantallas web. Se ingresa con el usuario o con el correo (accounts/backends.py).
AUTHENTICATION_BACKENDS = ['accounts.backends.EmailOrUsernameBackend']
LOGIN_URL = 'core:login'
LOGIN_REDIRECT_URL = 'core:dashboard'
LOGOUT_REDIRECT_URL = 'core:login'

# Sesiones: Django guarda los datos en la tabla django_session (el navegador solo recibe la cookie
# "sessionid" con una clave). Se deja escrito aunque sea el valor por defecto.
SESSION_ENGINE = 'django.contrib.sessions.backends.db'

# Recuperación de contraseña con código (accounts/recovery.py).
RECOVERY_CODE_SECONDS = 120  # cuánto vale el código desde que se envía
RECOVERY_MAX_ATTEMPTS = 5  # intentos fallidos antes de que el código deje de servir
RECOVERY_MAX_REQUESTS = 5  # códigos que se pueden pedir en una hora para la misma cuenta
RECOVERY_RESEND_SECONDS = 45  # espera, desde que se envía un código, para poder pedir otro desde la misma sesión
RECOVERY_PASSWORD_SECONDS = 600  # tiempo para escribir la contraseña nueva una vez validado el código


# ----------------------------------------------------------------------------------------------------------------
# Producción (AWS). Todo sale del .env o de las variables de entorno del servidor (ver deploy/sgr.env.example y
# docs/aws/DESPLIEGUE_AWS.md). Sin ninguna de estas variables el proyecto se comporta igual que en desarrollo.
# ----------------------------------------------------------------------------------------------------------------
def _env_bool(name, default=False):
    valor = (os.environ.get(name) or "").strip().lower()
    return default if not valor else valor in ("1", "true", "yes", "si", "sí", "on")


def _env_int(name, default=0):
    try:
        return int(os.environ.get(name) or default)
    except ValueError:
        raise ImproperlyConfigured(f"{name} del .env tiene que ser un número entero.") from None


# Con DEBUG apagado no se acepta la clave de ejemplo ni una clave vacía: sería publicar el sitio con una clave conocida.
if not DEBUG and (not SECRET_KEY.strip() or SECRET_KEY.startswith("django-insecure") or SECRET_KEY.startswith("cambia-esto")):
    raise ImproperlyConfigured(
        "Con DEBUG=False hay que definir una SECRET_KEY propia en el .env (la de ejemplo no sirve). "
        "Genera una con: python -c \"import secrets; print(secrets.token_urlsafe(64))\""
    )

# Archivos estáticos: `python manage.py collectstatic` los junta en STATIC_ROOT; nginx los sirve desde ahí
# (o WhiteNoise, con USE_WHITENOISE=True, si no hay nginx).
STATIC_ROOT = BASE_DIR / "staticfiles"
if _env_bool("USE_WHITENOISE"):
    MIDDLEWARE.insert(1, 'whitenoise.middleware.WhiteNoiseMiddleware')
    STORAGES = {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
    }

# Orígenes de confianza para los formularios (CSRF) cuando el sitio se sirve por HTTPS con un dominio: https://sgr.ejemplo.cl
CSRF_TRUSTED_ORIGINS = [
    origen.strip() for origen in os.environ.get("CSRF_TRUSTED_ORIGINS", "").split(",") if origen.strip()
]

# Detrás de nginx o de un balanceador, Django se entera de que la conexión original fue HTTPS por esta cabecera.
if _env_bool("BEHIND_PROXY"):
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# HTTPS=True: cookies solo por HTTPS y redirección de HTTP a HTTPS (la revisión de estado /salud/ queda exenta).
if _env_bool("HTTPS"):
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_SSL_REDIRECT = True
    SECURE_REDIRECT_EXEMPT = [r"^salud/$"]
    SECURE_HSTS_SECONDS = _env_int("SECURE_HSTS_SECONDS", 0)
    SECURE_HSTS_INCLUDE_SUBDOMAINS = SECURE_HSTS_SECONDS > 0
    SECURE_HSTS_PRELOAD = False

# Base de datos: conexiones persistentes y, con SQLite fuera de desarrollo, el modo WAL (varios procesos de gunicorn
# pueden leer mientras otro escribe) y más espera antes de dar «database is locked».
DATABASES['default']['CONN_MAX_AGE'] = _env_int("DB_CONN_MAX_AGE", 0)
if DATABASES['default']['ENGINE'].endswith('sqlite3') and not DEBUG:
    DATABASES['default']['OPTIONS'] = {
        "timeout": 20,
        "init_command": "PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL;",
        "transaction_mode": "IMMEDIATE",
    }

# Caché. Los intentos fallidos de la recuperación de contraseña se cuentan en la caché (accounts/recovery.py), así que con
# más de un proceso de gunicorn tiene que ser compartida:
#   CACHE_BACKEND=locmem (por defecto, un solo proceso) | redis (REDIS_URL) | db (tabla sgr_cache: manage.py createcachetable)
# Con «db» el contador no es atómico entre procesos; en AWS se recomienda redis.
CACHE_BACKEND = (os.environ.get("CACHE_BACKEND") or "locmem").strip().lower()
if CACHE_BACKEND == "redis":
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": os.environ.get("REDIS_URL") or "redis://127.0.0.1:6379/1",
            "KEY_PREFIX": "sgr",
        }
    }
elif CACHE_BACKEND == "db":
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.db.DatabaseCache", "LOCATION": "sgr_cache"}}
elif CACHE_BACKEND != "locmem":
    raise ImproperlyConfigured("CACHE_BACKEND del .env tiene que ser locmem, redis o db.")

# Registro de errores en la salida estándar (systemd/journald y CloudWatch lo recogen). Django, con DEBUG apagado, no
# imprime los errores 500 si no hay un registro configurado. En desarrollo no se cambia nada.
if not DEBUG:
    LOGGING = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {"simple": {"format": "%(asctime)s %(levelname)s %(name)s: %(message)s"}},
        "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "simple"}},
        "root": {"handlers": ["console"], "level": os.environ.get("LOG_LEVEL", "INFO")},
        "loggers": {"django.request": {"handlers": ["console"], "level": "WARNING", "propagate": False}},
    }
