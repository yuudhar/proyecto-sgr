"""Configuración de gunicorn para el SGR (se usa con: gunicorn -c deploy/gunicorn.conf.py sgr_project.wsgi).

Todo se puede cambiar con variables de entorno (en /etc/sgr/sgr.env o en el .env); los valores por defecto sirven
para una instancia pequeña de EC2 (2 vCPU).
"""

import multiprocessing
import os

bind = os.environ.get("GUNICORN_BIND", "127.0.0.1:8000")
# Con más de un proceso la caché de la recuperación de contraseña debe ser compartida (CACHE_BACKEND=redis).
workers = int(os.environ.get("GUNICORN_WORKERS", max(2, multiprocessing.cpu_count())))
threads = int(os.environ.get("GUNICORN_THREADS", 2))
worker_class = "gthread"
timeout = int(os.environ.get("GUNICORN_TIMEOUT", 60))
graceful_timeout = 30
keepalive = 5
max_requests = 2000  # reinicia cada proceso de vez en cuando para que no se hinche
max_requests_jitter = 200
accesslog = "-"  # a la salida estándar: lo recoge systemd/journald (y CloudWatch si se instala el agente)
errorlog = "-"
loglevel = os.environ.get("GUNICORN_LOGLEVEL", "info")
forwarded_allow_ips = os.environ.get("GUNICORN_FORWARDED_ALLOW_IPS", "127.0.0.1")
