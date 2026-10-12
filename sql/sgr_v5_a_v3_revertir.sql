-- =====================================================================
-- SGR - De la v5 a la v3: quita el color de la delegación
--
-- Deshace sgr_v3_a_v5_alter.sql. Los colores que se hayan guardado se pierden.
--
-- DROP CONSTRAINT funciona desde MySQL 8.0.19 y en MariaDB 10.2.1+
-- (en un MySQL 8.0.16 o 8.0.17 se escribe DROP CHECK chk_delegacion_color).
-- =====================================================================

USE sgr_db;

ALTER TABLE Delegacion DROP CONSTRAINT chk_delegacion_color;
ALTER TABLE Delegacion DROP COLUMN color;
