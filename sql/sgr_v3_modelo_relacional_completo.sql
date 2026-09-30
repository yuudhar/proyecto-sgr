-- =====================================================================
-- SISTEMA DE GESTION DE RESULTADOS (SGR) - Modelo Relacional
-- VERSION DEL PROYECTO: v3   (modelo base: v4 de Analisis y Diseño)
-- 22 tablas - Para ejecutar en DBeaver (MySQL / MariaDB)
--
-- UNICO CAMBIO RESPECTO AL MODELO ORIGINAL (siguen siendo 22 tablas):
--   Beneficiario.direccion  -> calle y numero de la vivienda (un solo
--   campo, opcional: queda vacio si no se conoce).
-- Todo lo demas (incluidas Cargo y Rol) queda exactamente igual.
--
-- v4: 19 tablas base (verificadas contra las 11 entidades minimas de
--     Guia_Proyecto_Software_SGR_Alumnos.pdf) + Beneficiario,
--     Territorio y Tipo_Gestion, agregadas tras el cruce exhaustivo
--     contra las 20 diapositivas de la Matriz SGR real (PPT).
-- Verificacion final: se revisaron las 19 capturas de pantalla
-- incrustadas en el PPT (no solo el texto) y se elimino la columna
-- de texto redundante 'territorio' en Compromiso (rubrica: "diseno
-- orientado a evitar redundancias innecesarias").
-- =====================================================================

-- ATENCION: esto borra por completo la base sgr_db actual (las 19
-- tablas y todos los datos que tengas cargados) antes de recrearla
-- limpia con las 22 tablas. Confirmado por el alumno que los datos
-- actuales son de prueba y se pueden perder.
-- OJO: si el .env de Django tambien apunta a sgr_db (DB_ENGINE=mysql),
-- esto borra tambien las tablas y usuarios de Django. En ese caso usa
-- otro nombre para Django (ej. DB_NAME=sgr_django).
DROP DATABASE IF EXISTS sgr_db;

CREATE DATABASE sgr_db CHARACTER SET utf8mb4;
USE sgr_db;

SET FOREIGN_KEY_CHECKS = 0;

-- ---------------------------------------------------------------------
-- ORGANIZACION Y SEGURIDAD
-- ---------------------------------------------------------------------

CREATE TABLE Delegacion (
    id_delegacion   INT AUTO_INCREMENT PRIMARY KEY,
    nombre          VARCHAR(100) NOT NULL UNIQUE,
    estado          VARCHAR(20)  NOT NULL DEFAULT 'activa',
    responsables    VARCHAR(255),
    ambito          VARCHAR(100)
) ENGINE=InnoDB;

CREATE TABLE Cargo (
    id_cargo        INT AUTO_INCREMENT PRIMARY KEY,
    nombre          VARCHAR(100) NOT NULL,
    vigencia_desde  DATE NOT NULL,
    vigencia_hasta  DATE
) ENGINE=InnoDB;

CREATE TABLE Funcionario (
    id_funcionario          INT AUTO_INCREMENT PRIMARY KEY,
    identificador_institucional VARCHAR(20) NOT NULL UNIQUE,
    nombre                  VARCHAR(150) NOT NULL,
    estado                  VARCHAR(20) NOT NULL DEFAULT 'activo',
    Delegacion_id_delegacion INT NOT NULL,
    Cargo_id_cargo          INT NOT NULL,
    CONSTRAINT fk_funcionario_delegacion FOREIGN KEY (Delegacion_id_delegacion) REFERENCES Delegacion(id_delegacion),
    CONSTRAINT fk_funcionario_cargo FOREIGN KEY (Cargo_id_cargo) REFERENCES Cargo(id_cargo)
) ENGINE=InnoDB;

CREATE TABLE Usuario (
    id_usuario      INT AUTO_INCREMENT PRIMARY KEY,
    email           VARCHAR(150) NOT NULL UNIQUE,
    password_hash   VARCHAR(255) NOT NULL,
    estado          VARCHAR(20) NOT NULL DEFAULT 'activo',
    Funcionario_id_funcionario INT,
    CONSTRAINT fk_usuario_funcionario FOREIGN KEY (Funcionario_id_funcionario) REFERENCES Funcionario(id_funcionario)
) ENGINE=InnoDB;

CREATE TABLE Rol (
    id_rol          INT AUTO_INCREMENT PRIMARY KEY,
    nombre          VARCHAR(50) NOT NULL UNIQUE
) ENGINE=InnoDB;

CREATE TABLE Usuario_Rol_Delegacion (
    id_usuario_rol  INT AUTO_INCREMENT PRIMARY KEY,
    Usuario_id_usuario INT NOT NULL,
    Rol_id_rol      INT NOT NULL,
    Delegacion_id_delegacion INT NULL,
    CONSTRAINT fk_urd_usuario FOREIGN KEY (Usuario_id_usuario) REFERENCES Usuario(id_usuario),
    CONSTRAINT fk_urd_rol FOREIGN KEY (Rol_id_rol) REFERENCES Rol(id_rol),
    CONSTRAINT fk_urd_delegacion FOREIGN KEY (Delegacion_id_delegacion) REFERENCES Delegacion(id_delegacion),
    UNIQUE KEY uq_usuario_rol_delegacion (Usuario_id_usuario, Rol_id_rol, Delegacion_id_delegacion)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- CATALOGOS
-- ---------------------------------------------------------------------

CREATE TABLE Item (
    id_item         INT AUTO_INCREMENT PRIMARY KEY,
    Item_id_item_padre INT NULL,                              -- NUEVO v3: TIPO_ATENCION -> SUB_ATENCION
    nombre          VARCHAR(150) NOT NULL,
    tipo_calculo    VARCHAR(20) NOT NULL DEFAULT 'cuantitativo',
    CONSTRAINT fk_item_padre FOREIGN KEY (Item_id_item_padre) REFERENCES Item(id_item)
) ENGINE=InnoDB;

CREATE TABLE Servicio (
    id_servicio     INT AUTO_INCREMENT PRIMARY KEY,
    nombre          VARCHAR(100) NOT NULL,
    estado          VARCHAR(20) NOT NULL DEFAULT 'activo'
) ENGINE=InnoDB;

-- NUEVO en v2: catálogo de tipos de gestión (Área Social: presencial,
-- visita a terreno, entrega de informe, entrega de beneficio, etc.)
CREATE TABLE Tipo_Gestion (
    id_tipo_gestion INT AUTO_INCREMENT PRIMARY KEY,
    nombre          VARCHAR(80) NOT NULL UNIQUE
) ENGINE=InnoDB;

-- NUEVO en v4: el vecino/usuario atendido (RUT, nombre, teléfono).
-- Tabla propia (no columnas sueltas) porque el mismo RUT se repite
-- en varias actividades a lo largo del tiempo.
-- v3: se agrega la direccion de la vivienda (calle y numero).
CREATE TABLE Beneficiario (
    id_beneficiario INT AUTO_INCREMENT PRIMARY KEY,
    rut             VARCHAR(12) NOT NULL UNIQUE,
    nombre          VARCHAR(150) NOT NULL,
    telefono        VARCHAR(20),
    direccion       VARCHAR(200) NOT NULL DEFAULT ''          -- NUEVO v3: calle y numero (vacio si no se conoce)
) ENGINE=InnoDB;

-- NUEVO en v4: subdivisión geográfica dentro de una delegación
-- (Latorre, Toqui, Zorrilla...), vista en la agenda colectiva.
CREATE TABLE Territorio (
    id_territorio   INT AUTO_INCREMENT PRIMARY KEY,
    nombre          VARCHAR(100) NOT NULL,
    Delegacion_id_delegacion INT NOT NULL,
    CONSTRAINT fk_territorio_delegacion FOREIGN KEY (Delegacion_id_delegacion) REFERENCES Delegacion(id_delegacion),
    UNIQUE KEY uq_territorio_delegacion (nombre, Delegacion_id_delegacion)
) ENGINE=InnoDB;

CREATE TABLE Cargo_Item (
    id_cargo_item   INT AUTO_INCREMENT PRIMARY KEY,
    Cargo_id_cargo  INT NOT NULL,
    Item_id_item    INT NOT NULL,
    ponderador      DECIMAL(5,2) NOT NULL,
    vigencia_desde  DATE NOT NULL,
    vigencia_hasta  DATE,
    tipo            ENUM('NORMAL','BONIFICACION','PENALIZACION') NOT NULL DEFAULT 'NORMAL', -- NUEVO v2
    tope_maximo     DECIMAL(10,2) NULL,                                                      -- NUEVO v2
    CONSTRAINT fk_cargoitem_cargo FOREIGN KEY (Cargo_id_cargo) REFERENCES Cargo(id_cargo),
    CONSTRAINT fk_cargoitem_item FOREIGN KEY (Item_id_item) REFERENCES Item(id_item)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- MEDICION
-- ---------------------------------------------------------------------

CREATE TABLE Periodo (
    id_periodo          INT AUTO_INCREMENT PRIMARY KEY,
    fecha_inicio        DATE NOT NULL,
    fecha_termino        DATE NOT NULL,
    dias_computables     INT NOT NULL,
    estado               VARCHAR(20) NOT NULL DEFAULT 'planificado',
    umbral_colectivo     DECIMAL(5,2) NOT NULL DEFAULT 80.00,
    umbral_ambar         DECIMAL(5,2) NOT NULL DEFAULT 60.00,
    tope_ponderado        DECIMAL(5,2) NOT NULL DEFAULT 150.00,
    version_parametros    VARCHAR(20) NOT NULL DEFAULT '1'
) ENGINE=InnoDB;

CREATE TABLE Meta (
    id_meta         INT AUTO_INCREMENT PRIMARY KEY,
    valor_objetivo  DECIMAL(10,2) NOT NULL,
    unidad          VARCHAR(50) NOT NULL,
    ponderador      DECIMAL(5,2) NOT NULL,
    version         INT NOT NULL DEFAULT 1,
    Item_id_item    INT NOT NULL,
    Funcionario_id_funcionario INT NULL,
    Cargo_id_cargo  INT NULL,
    Periodo_id_periodo INT NOT NULL,
    CONSTRAINT fk_meta_item FOREIGN KEY (Item_id_item) REFERENCES Item(id_item),
    CONSTRAINT fk_meta_funcionario FOREIGN KEY (Funcionario_id_funcionario) REFERENCES Funcionario(id_funcionario),
    CONSTRAINT fk_meta_cargo FOREIGN KEY (Cargo_id_cargo) REFERENCES Cargo(id_cargo),
    CONSTRAINT fk_meta_periodo FOREIGN KEY (Periodo_id_periodo) REFERENCES Periodo(id_periodo),
    CONSTRAINT chk_meta_valor_objetivo CHECK (valor_objetivo > 0)
) ENGINE=InnoDB;

CREATE TABLE Indicador (
    id_indicador    INT AUTO_INCREMENT PRIMARY KEY,
    avance          DECIMAL(10,2) NOT NULL,
    cumplimiento    DECIMAL(5,2) NOT NULL,
    ponderacion     DECIMAL(5,2) NOT NULL,
    semaforo        VARCHAR(20) NOT NULL,
    fecha_calculo   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    Meta_id_meta    INT NOT NULL,
    CONSTRAINT fk_indicador_meta FOREIGN KEY (Meta_id_meta) REFERENCES Meta(id_meta)
) ENGINE=InnoDB;

CREATE TABLE Ajuste (
    id_ajuste       INT AUTO_INCREMENT PRIMARY KEY,
    tipo            VARCHAR(20) NOT NULL,
    motivo          VARCHAR(255) NOT NULL,
    valor_pct       DECIMAL(5,2) NOT NULL,
    fecha           DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    Funcionario_id_funcionario INT NOT NULL,
    Periodo_id_periodo INT NOT NULL,
    Usuario_id_responsable INT NOT NULL,
    CONSTRAINT fk_ajuste_funcionario FOREIGN KEY (Funcionario_id_funcionario) REFERENCES Funcionario(id_funcionario),
    CONSTRAINT fk_ajuste_periodo FOREIGN KEY (Periodo_id_periodo) REFERENCES Periodo(id_periodo),
    CONSTRAINT fk_ajuste_usuario FOREIGN KEY (Usuario_id_responsable) REFERENCES Usuario(id_usuario)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- OPERACION
-- ---------------------------------------------------------------------

CREATE TABLE Actividad (
    id_actividad        INT AUTO_INCREMENT PRIMARY KEY,
    fecha               DATE NOT NULL,
    solicitud_problema  TEXT,
    accion              TEXT,
    contacto            VARCHAR(100),
    telefono            VARCHAR(20),
    Beneficiario_id_beneficiario INT NULL,                    -- NUEVO v4
    estado              VARCHAR(30) NOT NULL DEFAULT 'registrada',
    requiere_visita     BOOLEAN NOT NULL DEFAULT FALSE,        -- NUEVO v2
    ingreso_a_tubo      BOOLEAN NOT NULL DEFAULT FALSE,        -- NUEVO v2
    Item_id_item        INT NOT NULL,
    Servicio_id_servicio INT NULL,
    Delegacion_id_delegacion INT NOT NULL,
    Funcionario_id_autor INT NOT NULL,
    CONSTRAINT fk_actividad_item FOREIGN KEY (Item_id_item) REFERENCES Item(id_item),
    CONSTRAINT fk_actividad_servicio FOREIGN KEY (Servicio_id_servicio) REFERENCES Servicio(id_servicio),
    CONSTRAINT fk_actividad_delegacion FOREIGN KEY (Delegacion_id_delegacion) REFERENCES Delegacion(id_delegacion),
    CONSTRAINT fk_actividad_funcionario FOREIGN KEY (Funcionario_id_autor) REFERENCES Funcionario(id_funcionario),
    CONSTRAINT fk_actividad_beneficiario FOREIGN KEY (Beneficiario_id_beneficiario) REFERENCES Beneficiario(id_beneficiario)
) ENGINE=InnoDB;

CREATE TABLE Gestion_Atencion (
    id_gestion      INT AUTO_INCREMENT PRIMARY KEY,
    numero_gestion  TINYINT NOT NULL,
    Tipo_Gestion_id_tipo_gestion INT NULL,                    -- NUEVO v2
    fecha           DATE NOT NULL,
    resultado       VARCHAR(255) NOT NULL,
    fecha_programada_visita DATE NULL,                        -- NUEVO v2
    fecha_visita            DATE NULL,                        -- NUEVO v2
    fecha_entrega_informe   DATE NULL,                        -- NUEVO v2
    fecha_entrega_beneficio DATE NULL,                        -- NUEVO v2
    Actividad_id_actividad INT NOT NULL,
    CONSTRAINT fk_gestion_actividad FOREIGN KEY (Actividad_id_actividad) REFERENCES Actividad(id_actividad),
    CONSTRAINT fk_gestion_tipo FOREIGN KEY (Tipo_Gestion_id_tipo_gestion) REFERENCES Tipo_Gestion(id_tipo_gestion),
    CONSTRAINT chk_gestion_numero CHECK (numero_gestion BETWEEN 1 AND 3),
    UNIQUE KEY uq_actividad_gestion (Actividad_id_actividad, numero_gestion)
) ENGINE=InnoDB;

CREATE TABLE Evidencia (
    id_evidencia    INT AUTO_INCREMENT PRIMARY KEY,
    codigo_unico    VARCHAR(50) NOT NULL UNIQUE,
    archivo_vinculo VARCHAR(255) NOT NULL,
    fecha_carga     DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    estado_revision VARCHAR(30) NOT NULL DEFAULT 'pendiente',
    metadatos       TEXT,
    Actividad_id_actividad INT NOT NULL,
    Funcionario_id_autor INT NOT NULL,
    CONSTRAINT fk_evidencia_actividad FOREIGN KEY (Actividad_id_actividad) REFERENCES Actividad(id_actividad),
    CONSTRAINT fk_evidencia_funcionario FOREIGN KEY (Funcionario_id_autor) REFERENCES Funcionario(id_funcionario)
) ENGINE=InnoDB;

CREATE TABLE Validacion (
    id_validacion   INT AUTO_INCREMENT PRIMARY KEY,
    decision        VARCHAR(30) NOT NULL,
    fecha           DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    observacion     TEXT,
    resultado       VARCHAR(50),
    version         VARCHAR(20) NOT NULL DEFAULT '1',
    Evidencia_id_evidencia INT NOT NULL,
    Funcionario_id_verificador INT NOT NULL,
    CONSTRAINT fk_validacion_evidencia FOREIGN KEY (Evidencia_id_evidencia) REFERENCES Evidencia(id_evidencia),
    CONSTRAINT fk_validacion_funcionario FOREIGN KEY (Funcionario_id_verificador) REFERENCES Funcionario(id_funcionario)
) ENGINE=InnoDB;

CREATE TABLE Compromiso (
    id_compromiso   INT AUTO_INCREMENT PRIMARY KEY,
    origen          VARCHAR(100),
    fecha_solicitud DATE NULL,                                 -- NUEVO v3
    descripcion     TEXT NULL,                                 -- NUEVO v3
    solicitante     VARCHAR(100) NOT NULL,
    tipo_solicitante ENUM('INT','EXT') NOT NULL DEFAULT 'EXT', -- NUEVO v2
    Territorio_id_territorio INT NOT NULL,                     -- NUEVO v4 (reemplaza la columna de texto 'territorio', evita redundancia)
    fecha_comprometida DATE NOT NULL,
    apoyo           VARCHAR(100),
    estado          VARCHAR(30) NOT NULL DEFAULT 'ingresado',
    observacion     TEXT,
    Funcionario_id_responsable INT NOT NULL,
    Delegacion_id_delegacion INT NOT NULL,
    CONSTRAINT fk_compromiso_funcionario FOREIGN KEY (Funcionario_id_responsable) REFERENCES Funcionario(id_funcionario),
    CONSTRAINT fk_compromiso_delegacion FOREIGN KEY (Delegacion_id_delegacion) REFERENCES Delegacion(id_delegacion),
    CONSTRAINT fk_compromiso_territorio FOREIGN KEY (Territorio_id_territorio) REFERENCES Territorio(id_territorio)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- AUDITORIA
-- ---------------------------------------------------------------------

CREATE TABLE Auditoria (
    id_auditoria        BIGINT AUTO_INCREMENT PRIMARY KEY,
    evento              VARCHAR(100) NOT NULL,
    fecha               DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    entidad_afectada    VARCHAR(50) NOT NULL,
    identificador_registro INT NOT NULL,
    valor_anterior      TEXT,
    valor_nuevo         TEXT,
    Usuario_id_usuario  INT NOT NULL,
    CONSTRAINT fk_auditoria_usuario FOREIGN KEY (Usuario_id_usuario) REFERENCES Usuario(id_usuario)
) ENGINE=InnoDB;

-- Seed del catálogo Tipo_Gestion
INSERT INTO Tipo_Gestion (nombre) VALUES
    ('Atención a usuario presencial'),
    ('Visita a terreno'),
    ('Entrega de informe'),
    ('Entrega de beneficio'),
    ('Emergencia'),
    ('Otras gestiones');

SET FOREIGN_KEY_CHECKS = 1;

-- =====================================================================
-- FIN - v3 del proyecto (modelo v4): 22 tablas creadas
-- (19 base verificadas contra la guia oficial del profesor +
--  Beneficiario + Territorio + Tipo_Gestion, del cruce exhaustivo
--  contra las 20 diapositivas de la Matriz SGR real)
-- =====================================================================
