USE sgr_db;

ALTER TABLE Delegacion
    ADD COLUMN color VARCHAR(7) NOT NULL DEFAULT '#920000' AFTER ambito,
    ADD CONSTRAINT chk_delegacion_color CHECK (color REGEXP '^#[0-9A-Fa-f]{6}$');
