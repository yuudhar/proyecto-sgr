-- =====================================================================
-- SGR - De la v3 a la v5: color de la delegación
--
-- Agrega Delegacion.color a una base creada con
-- sgr_v3_modelo_relacional_completo.sql, sin tocar los datos que ya tiene.
-- Las delegaciones existentes quedan con el color por defecto (#920000) y
-- se pueden cambiar después desde la pantalla de delegaciones.
--
-- Pide MySQL 8.0.16 o más reciente (o MariaDB 10.2.1+) para que el CHECK se aplique.
-- =====================================================================

USE sgr_db;

ALTER TABLE Delegacion
    ADD COLUMN color VARCHAR(7) NOT NULL DEFAULT '#920000' AFTER ambito,
    ADD CONSTRAINT chk_delegacion_color CHECK (color REGEXP '^#[0-9A-Fa-f]{6}$');
