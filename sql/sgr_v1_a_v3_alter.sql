-- =====================================================================
-- SGR - ALTER v1 -> v3
-- Para una base sgr_db que YA fue creada con el script original (v1) y
-- en la que no quieres perder los datos. (Si no te importan los datos,
-- es mas simple ejecutar sgr_v3_modelo_relacional_completo.sql, que
-- recrea todo.)
--
-- Unico cambio: Beneficiario.direccion (calle y numero de la vivienda).
-- Es opcional, por lo que no se pierde nada.
-- Ejecutar en DBeaver sobre la conexion MySQL/MariaDB (Alt+X).
-- =====================================================================

USE sgr_db;

ALTER TABLE Beneficiario
    ADD COLUMN direccion VARCHAR(200) NOT NULL DEFAULT '' AFTER telefono;
