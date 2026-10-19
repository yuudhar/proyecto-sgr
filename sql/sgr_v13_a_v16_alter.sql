-- ===========================================================================================================
-- SGR · De la v13/v15 a la v16: cambios en la base del servidor (MariaDB 10.11, base sgr_django)
--
-- NO hace falta ejecutarlo: `python manage.py migrate` (que corre deploy/actualizar.sh) aplica estos mismos
-- cambios con las migraciones evidence 0002 y 0003 y accounts 0005. Este archivo solo los deja a la vista, por si
-- se quieren revisar o aplicar a mano desde phpMyAdmin (en ese caso, marca también las migraciones como aplicadas).
-- No borra ni cambia datos: solo permite vacío en una columna y agrega una.
-- ===========================================================================================================

-- 1) Una revisión del Super Usuario no tiene funcionario verificador (evidence 0002).
ALTER TABLE `evidence_validation`
  MODIFY `reviewer_officer_id` bigint(20) NULL;

-- 2) Foto de perfil del usuario: ruta del archivo PNG o JPG subido (accounts 0005).
ALTER TABLE `accounts_userprofile`
  ADD COLUMN `photo` varchar(255) NULL;

-- 3) La columna evidence_evidence.file_link sigue igual (varchar(255)): ahora guarda la ruta del archivo
--    subido (evidence 0003). Las evidencias antiguas conservan su texto y se muestran como «el archivo no
--    está en el sistema» hasta que alguien suba el archivo.
