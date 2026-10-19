USE sgr_db;

ALTER TABLE Delegacion DROP CONSTRAINT chk_delegacion_color;
ALTER TABLE Delegacion DROP COLUMN color;
