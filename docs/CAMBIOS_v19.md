# Cambios de la v19 respecto de la v18

La v19 no cambia el sistema ni la base de datos: no hay migraciones nuevas ni pantallas distintas. Cambia cómo se trabajan los datos.

## Se trabaja sobre la base real, sin semillas

- Se quitó el comando `seed_demo_data` (cargaba usuarios, delegaciones y registros ficticios). Los datos viven en la base del servidor (MariaDB, administrada desde phpMyAdmin).
- Para una base vacía quedan solo los comandos de arranque: `seed_roles`, `seed_management_types` y `createsuperuser`.
- Los datos que necesitan las pruebas automáticas pasaron a `core/datos_prueba.py` y solo se cargan en la base temporal de las pruebas; ya no son un comando de `manage.py`.
- `cargar_volumen_estres` se conserva (con `--limpiar`), pero ahora pide que la base ya tenga funcionarios e ítems.
- `deploy/actualizar.sh`, `deploy/al2023/instalar_al2023.sh`, el README y las guías de despliegue ya no mencionan los datos de demostración.

## Scripts de la base (carpeta `sql/`)

- `sgr_django_v19.sql`: estructura real de `sgr_django` (32 tablas), reemplaza a `sgr_django_estructura_mariadb.sql` (que era de la v13).
- `sgr_django_v19_dbeaver.sql`: el mismo esquema en una base aparte (`sgr_django_der`) para abrirlo en DBeaver y sacar los diagramas ER.
- `sgr_v19_modelo_relacional_completo_en.sql`: diseño de 22 tablas en inglés, reemplaza a `sgr_v10_...`.

## Verificación

- `python manage.py check` y `makemigrations --check`: sin cambios.
- Suite completa: 827 pruebas aprobadas. El registro `docs/pruebas/registro_pruebas_funcionales.csv` y `.xlsx` se generó de nuevo.
