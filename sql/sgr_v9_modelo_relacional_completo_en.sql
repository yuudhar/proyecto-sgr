-- WARNING: this deletes the sgr_db database (if it exists) and recreates it empty.
DROP DATABASE IF EXISTS sgr_db;
CREATE DATABASE sgr_db CHARACTER SET utf8mb4;
USE sgr_db;

-- RESULTS MANAGEMENT SYSTEM (SGR) - Relational Model (ENGLISH VERSION)
-- PROJECT VERSION: v9   (base model: v4 of Analysis and Design)
-- 22 tables - To run in DBeaver (MySQL / MariaDB)
--
-- This is the same script as sgr_v3_modelo_relacional_completo.sql, with
-- table names, column names, constraint names and default values translated
-- to English (table names match the Django models of the project).
-- Structure, data types, relationships and seed data are exactly the same,
-- except for the AUDIT FIELDS and the FIELDS ADDED BY THE DJANGO PROJECT
-- described below.
--
-- ENGLISH SCRIPT v3 = v2 + audit fields: created_at, updated_at and deleted_at
-- (soft delete) are added to the 20 tables that are Django models (BaseModel).
-- User corresponds to UserProfile in Django.
--
-- ENGLISH SCRIPT v9 = v3 + the fields the Django project added afterwards.
-- Each one is marked in the code with NEW v5 / NEW v8 (A1) / NEW v9 (A2):
--   Delegation  -> address, commune                                (v8, A1)
--               -> color, with a CHECK so it is written as #RRGGBB (v5)
--   Item        -> description                                     (v8, A1)
--   Role        -> description, scope and status                   (v8, A1)
--                  scope: 'own' = its delegation, 'all' = every delegation
--                  Role corresponds to Group + RoleProfile in Django.
--   Role and User_Role_Delegation also carry the three audit fields now
--   (in Django both are BaseModel tables: RoleProfile since v8 and
--   UserRoleDelegation since v9), so all 22 tables have created_at,
--   updated_at and deleted_at.
-- The CHECK on Delegation.color is only enforced by MySQL 8.0.16+ or
-- MariaDB 10.2.1+ (older MySQL versions accept it but ignore it).
--
-- CHANGE WITH RESPECT TO THE ORIGINAL MODEL (still 22 tables):
--   Beneficiary.address  -> street and number of the home (a single
--   field, optional: it stays empty if unknown).
-- Everything else stays exactly the same.
--
-- v4: 19 base tables (checked against the 11 minimum entities of
--     Guia_Proyecto_Software_SGR_Alumnos.pdf) + Beneficiary,
--     Territory and Management_Type, added after the exhaustive
--     cross-check against the 20 slides of the real SGR Matrix (PPT).
-- Final verification: the 19 screenshots embedded in the PPT were
-- reviewed (not only the text) and the redundant text column
-- territory in Commitment was removed (rubric: design oriented to
-- avoiding unnecessary redundancies).
--
-- NAME EQUIVALENCE (Spanish -> English):
--   Delegacion -> Delegation          Cargo -> Position
--   Funcionario -> Officer            Usuario -> User
--   Rol -> Role                       Usuario_Rol_Delegacion -> User_Role_Delegation
--   Item -> Item                      Servicio -> Service
--   Tipo_Gestion -> Management_Type   Beneficiario -> Beneficiary
--   Territorio -> Territory           Cargo_Item -> Position_Item
--   Periodo -> Period                 Meta -> Goal
--   Indicador -> Indicator            Ajuste -> Adjustment
--   Actividad -> Activity             Gestion_Atencion -> Followup
--   Evidencia -> Evidence             Validacion -> Validation
--   Compromiso -> Commitment          Auditoria -> Audit_Log
-- =====================================================================


-- NOTE: Position is also the name of a MySQL function, so every reference
-- to it is written with a space: REFERENCES Position (id_position).

-- NOTE: the first lines of this script delete the current sgr_db database
-- (the Spanish version too, with all its data) and recreate it with the 22
-- tables in English. The data is test data and can be lost.
-- If the Django .env file also points to sgr_db (DB_ENGINE=mysql), this also
-- deletes the Django tables and users. In that case use another name for
-- Django (e.g. DB_NAME=sgr_django).
-- =====================================================================

SET FOREIGN_KEY_CHECKS = 0;

-- ---------------------------------------------------------------------
-- ORGANIZATION AND SECURITY
-- ---------------------------------------------------------------------

CREATE TABLE Delegation (
    id_delegation INT AUTO_INCREMENT PRIMARY KEY,
    name          VARCHAR(100) NOT NULL UNIQUE,
    status        VARCHAR(20)  NOT NULL DEFAULT 'active',
    managers      VARCHAR(255),
    scope         VARCHAR(100),
    address       VARCHAR(200) NOT NULL DEFAULT '',          -- NEW v8 (A1): street and number of the office (empty if unknown)
    commune       VARCHAR(100) NOT NULL DEFAULT '',          -- NEW v8 (A1)
    color         VARCHAR(7)   NOT NULL DEFAULT '#920000',  -- NEW v5: #RRGGBB, identifies the delegation on screen
    created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,   -- AUDIT
    updated_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    deleted_at    DATETIME NULL,
    CONSTRAINT chk_delegation_color CHECK (color REGEXP '^#[0-9A-Fa-f]{6}$')
) ENGINE=InnoDB;

CREATE TABLE Position (
    id_position INT AUTO_INCREMENT PRIMARY KEY,
    name        VARCHAR(100) NOT NULL,
    valid_from  DATE NOT NULL,
    valid_until DATE,
    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,   -- AUDIT
    updated_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    deleted_at  DATETIME NULL
) ENGINE=InnoDB;

CREATE TABLE Officer (
    id_officer               INT AUTO_INCREMENT PRIMARY KEY,
    institutional_id         VARCHAR(20) NOT NULL UNIQUE,
    name                     VARCHAR(150) NOT NULL,
    status                   VARCHAR(20) NOT NULL DEFAULT 'active',
    Delegation_id_delegation INT NOT NULL,
    Position_id_position     INT NOT NULL,
    created_at               DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,   -- AUDIT
    updated_at               DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    deleted_at               DATETIME NULL,
    CONSTRAINT fk_officer_delegation FOREIGN KEY (Delegation_id_delegation) REFERENCES Delegation(id_delegation),
    CONSTRAINT fk_officer_position FOREIGN KEY (Position_id_position) REFERENCES Position (id_position)
) ENGINE=InnoDB;

CREATE TABLE User (
    id_user            INT AUTO_INCREMENT PRIMARY KEY,
    email              VARCHAR(150) NOT NULL UNIQUE,
    password_hash      VARCHAR(255) NOT NULL,
    status             VARCHAR(20) NOT NULL DEFAULT 'active',
    Officer_id_officer INT,
    created_at         DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,   -- AUDIT
    updated_at         DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    deleted_at         DATETIME NULL,
    CONSTRAINT fk_user_officer FOREIGN KEY (Officer_id_officer) REFERENCES Officer(id_officer)
) ENGINE=InnoDB;

CREATE TABLE Role (
    id_role     INT AUTO_INCREMENT PRIMARY KEY,
    name        VARCHAR(50) NOT NULL UNIQUE,
    description VARCHAR(255) NOT NULL DEFAULT '',          -- NEW v8 (A1)
    scope       VARCHAR(10)  NOT NULL DEFAULT 'own',       -- NEW v8 (A1): 'own' = its delegation, 'all' = every delegation
    status      VARCHAR(20)  NOT NULL DEFAULT 'active',    -- NEW v8 (A1)
    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,   -- AUDIT (NEW v8)
    updated_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    deleted_at  DATETIME NULL
) ENGINE=InnoDB;

CREATE TABLE User_Role_Delegation (
    id_user_role             INT AUTO_INCREMENT PRIMARY KEY,
    User_id_user             INT NOT NULL,
    Role_id_role             INT NOT NULL,
    Delegation_id_delegation INT NULL,
    created_at               DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,   -- AUDIT (NEW v9, A2)
    updated_at               DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    deleted_at               DATETIME NULL,
    CONSTRAINT fk_urd_user FOREIGN KEY (User_id_user) REFERENCES User(id_user),
    CONSTRAINT fk_urd_role FOREIGN KEY (Role_id_role) REFERENCES Role(id_role),
    CONSTRAINT fk_urd_delegation FOREIGN KEY (Delegation_id_delegation) REFERENCES Delegation(id_delegation),
    UNIQUE KEY uq_user_role_delegation (User_id_user, Role_id_role, Delegation_id_delegation)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- CATALOGS
-- ---------------------------------------------------------------------

CREATE TABLE Item (
    id_item             INT AUTO_INCREMENT PRIMARY KEY,
    Item_id_parent_item INT NULL,                                             -- NEW v3: CARE_TYPE -> CARE_SUBTYPE
    name                VARCHAR(150) NOT NULL,
    description         VARCHAR(255) NOT NULL DEFAULT '',                         -- NEW v8 (A1)
    calculation_type    VARCHAR(20) NOT NULL DEFAULT 'quantitative',
    created_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,   -- AUDIT
    updated_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    deleted_at          DATETIME NULL,
    CONSTRAINT fk_item_parent FOREIGN KEY (Item_id_parent_item) REFERENCES Item(id_item)
) ENGINE=InnoDB;

CREATE TABLE Service (
    id_service INT AUTO_INCREMENT PRIMARY KEY,
    name       VARCHAR(100) NOT NULL,
    status     VARCHAR(20) NOT NULL DEFAULT 'active',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,   -- AUDIT
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    deleted_at DATETIME NULL
) ENGINE=InnoDB;

-- NEW in v2: catalog of management types (Social Area: in person,
-- field visit, report delivery, benefit delivery, etc.)
CREATE TABLE Management_Type (
    id_management_type INT AUTO_INCREMENT PRIMARY KEY,
    name               VARCHAR(80) NOT NULL UNIQUE,
    created_at         DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,   -- AUDIT
    updated_at         DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    deleted_at         DATETIME NULL
) ENGINE=InnoDB;

-- NEW in v4: the neighbour/user served (RUT, name, phone).
-- Own table (not loose columns) because the same RUT repeats
-- across several activities over time.
-- v3: the home address is added (street and number).
CREATE TABLE Beneficiary (
    id_beneficiary INT AUTO_INCREMENT PRIMARY KEY,
    rut            VARCHAR(12) NOT NULL UNIQUE,
    name           VARCHAR(150) NOT NULL,
    phone          VARCHAR(20),
    address        VARCHAR(200) NOT NULL DEFAULT '',   -- NEW v3: street and number (empty if unknown)
    created_at     DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,   -- AUDIT
    updated_at     DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    deleted_at     DATETIME NULL
) ENGINE=InnoDB;

-- NEW in v4: geographic subdivision inside a delegation
-- (Latorre, Toqui, Zorrilla...), seen in the collective agenda.
CREATE TABLE Territory (
    id_territory             INT AUTO_INCREMENT PRIMARY KEY,
    name                     VARCHAR(100) NOT NULL,
    Delegation_id_delegation INT NOT NULL,
    created_at               DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,   -- AUDIT
    updated_at               DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    deleted_at               DATETIME NULL,
    CONSTRAINT fk_territory_delegation FOREIGN KEY (Delegation_id_delegation) REFERENCES Delegation(id_delegation),
    UNIQUE KEY uq_territory_delegation (name, Delegation_id_delegation)
) ENGINE=InnoDB;

CREATE TABLE Position_Item (
    id_position_item     INT AUTO_INCREMENT PRIMARY KEY,
    Position_id_position INT NOT NULL,
    Item_id_item         INT NOT NULL,
    weight               DECIMAL(5,2) NOT NULL,
    valid_from           DATE NOT NULL,
    valid_until          DATE,
    kind                 ENUM('NORMAL','BONUS','PENALTY') NOT NULL DEFAULT 'NORMAL',  -- NEW v2
    max_cap              DECIMAL(10,2) NULL,                                  -- NEW v2
    created_at           DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,   -- AUDIT
    updated_at           DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    deleted_at           DATETIME NULL,
    CONSTRAINT fk_positionitem_position FOREIGN KEY (Position_id_position) REFERENCES Position (id_position),
    CONSTRAINT fk_positionitem_item FOREIGN KEY (Item_id_item) REFERENCES Item(id_item)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- MEASUREMENT
-- ---------------------------------------------------------------------

CREATE TABLE Period (
    id_period            INT AUTO_INCREMENT PRIMARY KEY,
    start_date           DATE NOT NULL,
    end_date             DATE NOT NULL,
    computable_days      INT NOT NULL,
    status               VARCHAR(20) NOT NULL DEFAULT 'planned',
    collective_threshold DECIMAL(5,2) NOT NULL DEFAULT 80.00,
    amber_threshold      DECIMAL(5,2) NOT NULL DEFAULT 60.00,
    weighted_cap         DECIMAL(5,2) NOT NULL DEFAULT 150.00,
    parameters_version   VARCHAR(20) NOT NULL DEFAULT '1',
    created_at           DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,   -- AUDIT
    updated_at           DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    deleted_at           DATETIME NULL
) ENGINE=InnoDB;

CREATE TABLE Goal (
    id_goal              INT AUTO_INCREMENT PRIMARY KEY,
    target_value         DECIMAL(10,2) NOT NULL,
    unit                 VARCHAR(50) NOT NULL,
    weight               DECIMAL(5,2) NOT NULL,
    version              INT NOT NULL DEFAULT 1,
    Item_id_item         INT NOT NULL,
    Officer_id_officer   INT NULL,
    Position_id_position INT NULL,
    Period_id_period     INT NOT NULL,
    created_at           DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,   -- AUDIT
    updated_at           DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    deleted_at           DATETIME NULL,
    CONSTRAINT fk_goal_item FOREIGN KEY (Item_id_item) REFERENCES Item(id_item),
    CONSTRAINT fk_goal_officer FOREIGN KEY (Officer_id_officer) REFERENCES Officer(id_officer),
    CONSTRAINT fk_goal_position FOREIGN KEY (Position_id_position) REFERENCES Position (id_position),
    CONSTRAINT fk_goal_period FOREIGN KEY (Period_id_period) REFERENCES Period(id_period),
    CONSTRAINT chk_goal_target_value CHECK (target_value > 0)
) ENGINE=InnoDB;

CREATE TABLE Indicator (
    id_indicator  INT AUTO_INCREMENT PRIMARY KEY,
    progress      DECIMAL(10,2) NOT NULL,
    compliance    DECIMAL(5,2) NOT NULL,
    weighting     DECIMAL(5,2) NOT NULL,
    status_light  VARCHAR(20) NOT NULL,
    calculated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    Goal_id_goal  INT NOT NULL,
    created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,   -- AUDIT
    updated_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    deleted_at    DATETIME NULL,
    CONSTRAINT fk_indicator_goal FOREIGN KEY (Goal_id_goal) REFERENCES Goal(id_goal)
) ENGINE=InnoDB;

CREATE TABLE Adjustment (
    id_adjustment       INT AUTO_INCREMENT PRIMARY KEY,
    kind                VARCHAR(20) NOT NULL,
    reason              VARCHAR(255) NOT NULL,
    percentage_value    DECIMAL(5,2) NOT NULL,
    date                DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    Officer_id_officer  INT NOT NULL,
    Period_id_period    INT NOT NULL,
    User_id_responsible INT NOT NULL,
    created_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,   -- AUDIT
    updated_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    deleted_at          DATETIME NULL,
    CONSTRAINT fk_adjustment_officer FOREIGN KEY (Officer_id_officer) REFERENCES Officer(id_officer),
    CONSTRAINT fk_adjustment_period FOREIGN KEY (Period_id_period) REFERENCES Period(id_period),
    CONSTRAINT fk_adjustment_user FOREIGN KEY (User_id_responsible) REFERENCES User(id_user)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- OPERATIONS
-- ---------------------------------------------------------------------

CREATE TABLE Activity (
    id_activity                INT AUTO_INCREMENT PRIMARY KEY,
    date                       DATE NOT NULL,
    request_description        TEXT,
    action_taken               TEXT,
    contact_name               VARCHAR(100),
    phone                      VARCHAR(20),
    Beneficiary_id_beneficiary INT NULL,                                      -- NEW v4
    status                     VARCHAR(30) NOT NULL DEFAULT 'registered',
    requires_visit             BOOLEAN NOT NULL DEFAULT FALSE,                -- NEW v2
    added_to_pipeline          BOOLEAN NOT NULL DEFAULT FALSE,                -- NEW v2
    Item_id_item               INT NOT NULL,
    Service_id_service         INT NULL,
    Delegation_id_delegation   INT NOT NULL,
    Officer_id_author          INT NOT NULL,
    created_at                 DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,   -- AUDIT
    updated_at                 DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    deleted_at                 DATETIME NULL,
    CONSTRAINT fk_activity_item FOREIGN KEY (Item_id_item) REFERENCES Item(id_item),
    CONSTRAINT fk_activity_service FOREIGN KEY (Service_id_service) REFERENCES Service(id_service),
    CONSTRAINT fk_activity_delegation FOREIGN KEY (Delegation_id_delegation) REFERENCES Delegation(id_delegation),
    CONSTRAINT fk_activity_officer FOREIGN KEY (Officer_id_author) REFERENCES Officer(id_officer),
    CONSTRAINT fk_activity_beneficiary FOREIGN KEY (Beneficiary_id_beneficiary) REFERENCES Beneficiary(id_beneficiary)
) ENGINE=InnoDB;

CREATE TABLE Followup (
    id_followup                        INT AUTO_INCREMENT PRIMARY KEY,
    sequence_number                    TINYINT NOT NULL,
    Management_Type_id_management_type INT NULL,                              -- NEW v2
    date                               DATE NOT NULL,
    result                             VARCHAR(255) NOT NULL,
    scheduled_visit_date               DATE NULL,                             -- NEW v2
    visit_date                         DATE NULL,                             -- NEW v2
    report_delivery_date               DATE NULL,                             -- NEW v2
    benefit_delivery_date              DATE NULL,                             -- NEW v2
    Activity_id_activity               INT NOT NULL,
    created_at                         DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,   -- AUDIT
    updated_at                         DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    deleted_at                         DATETIME NULL,
    CONSTRAINT fk_followup_activity FOREIGN KEY (Activity_id_activity) REFERENCES Activity(id_activity),
    CONSTRAINT fk_followup_type FOREIGN KEY (Management_Type_id_management_type) REFERENCES Management_Type(id_management_type),
    CONSTRAINT chk_followup_sequence CHECK (sequence_number BETWEEN 1 AND 3),
    UNIQUE KEY uq_activity_followup (Activity_id_activity, sequence_number)
) ENGINE=InnoDB;

CREATE TABLE Evidence (
    id_evidence          INT AUTO_INCREMENT PRIMARY KEY,
    unique_code          VARCHAR(50) NOT NULL UNIQUE,
    file_link            VARCHAR(255) NOT NULL,
    uploaded_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    review_status        VARCHAR(30) NOT NULL DEFAULT 'pending',
    metadata             TEXT,
    Activity_id_activity INT NOT NULL,
    Officer_id_author    INT NOT NULL,
    created_at           DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,   -- AUDIT
    updated_at           DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    deleted_at           DATETIME NULL,
    CONSTRAINT fk_evidence_activity FOREIGN KEY (Activity_id_activity) REFERENCES Activity(id_activity),
    CONSTRAINT fk_evidence_officer FOREIGN KEY (Officer_id_author) REFERENCES Officer(id_officer)
) ENGINE=InnoDB;

CREATE TABLE Validation (
    id_validation        INT AUTO_INCREMENT PRIMARY KEY,
    decision             VARCHAR(30) NOT NULL,
    date                 DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    notes                TEXT,
    result               VARCHAR(50),
    version              VARCHAR(20) NOT NULL DEFAULT '1',
    Evidence_id_evidence INT NOT NULL,
    Officer_id_reviewer  INT NOT NULL,
    created_at           DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,   -- AUDIT
    updated_at           DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    deleted_at           DATETIME NULL,
    CONSTRAINT fk_validation_evidence FOREIGN KEY (Evidence_id_evidence) REFERENCES Evidence(id_evidence),
    CONSTRAINT fk_validation_officer FOREIGN KEY (Officer_id_reviewer) REFERENCES Officer(id_officer)
) ENGINE=InnoDB;

CREATE TABLE Commitment (
    id_commitment            INT AUTO_INCREMENT PRIMARY KEY,
    source                   VARCHAR(100),
    request_date             DATE NULL,                                       -- NEW v3
    description              TEXT NULL,                                       -- NEW v3
    requester                VARCHAR(100) NOT NULL,
    requester_type           ENUM('INTERNAL','EXTERNAL') NOT NULL DEFAULT 'EXTERNAL',  -- NEW v2
    Territory_id_territory   INT NOT NULL,                                    -- NEW v4 (replaces the text column territory, avoids redundancy)
    due_date                 DATE NOT NULL,
    support                  VARCHAR(100),
    status                   VARCHAR(30) NOT NULL DEFAULT 'entered',
    notes                    TEXT,
    Officer_id_responsible   INT NOT NULL,
    Delegation_id_delegation INT NOT NULL,
    created_at               DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,   -- AUDIT
    updated_at               DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    deleted_at               DATETIME NULL,
    CONSTRAINT fk_commitment_officer FOREIGN KEY (Officer_id_responsible) REFERENCES Officer(id_officer),
    CONSTRAINT fk_commitment_delegation FOREIGN KEY (Delegation_id_delegation) REFERENCES Delegation(id_delegation),
    CONSTRAINT fk_commitment_territory FOREIGN KEY (Territory_id_territory) REFERENCES Territory(id_territory)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- AUDIT
-- ---------------------------------------------------------------------

CREATE TABLE Audit_Log (
    id_audit_log    BIGINT AUTO_INCREMENT PRIMARY KEY,
    event           VARCHAR(100) NOT NULL,
    date            DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    affected_entity VARCHAR(50) NOT NULL,
    record_id       INT NOT NULL,
    previous_value  TEXT,
    new_value       TEXT,
    User_id_user    INT NOT NULL,
    created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,   -- AUDIT
    updated_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    deleted_at      DATETIME NULL,
    CONSTRAINT fk_audit_log_user FOREIGN KEY (User_id_user) REFERENCES User(id_user)
) ENGINE=InnoDB;

-- Seed of the Management_Type catalog
INSERT INTO Management_Type (name) VALUES
    ('In-person user service'),
    ('Field visit'),
    ('Report delivery'),
    ('Benefit delivery'),
    ('Emergency'),
    ('Other tasks');

SET FOREIGN_KEY_CHECKS = 1;

-- =====================================================================
-- END - project v9 (model v4): 22 tables created
-- (19 base tables checked against the professors official guide +
--  Beneficiary + Territory + Management_Type, from the exhaustive
--  cross-check against the 20 slides of the real SGR Matrix)
-- =====================================================================
