DROP DATABASE IF EXISTS sgr_db;
CREATE DATABASE sgr_db CHARACTER SET utf8mb4;
USE sgr_db;

SET FOREIGN_KEY_CHECKS = 0;

CREATE TABLE Delegation (
    id_delegation INT AUTO_INCREMENT PRIMARY KEY,
    name          VARCHAR(100) NOT NULL UNIQUE,
    status        VARCHAR(20)  NOT NULL DEFAULT 'active',
    managers      VARCHAR(255),
    scope         VARCHAR(100),
    address       VARCHAR(200) NOT NULL DEFAULT '',
    commune       VARCHAR(100) NOT NULL DEFAULT '',
    color         VARCHAR(7)   NOT NULL DEFAULT '#920000',
    created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    deleted_at    DATETIME NULL,
    CONSTRAINT chk_delegation_color CHECK (color REGEXP '^#[0-9A-Fa-f]{6}$')
) ENGINE=InnoDB;

CREATE TABLE Position (
    id_position INT AUTO_INCREMENT PRIMARY KEY,
    name        VARCHAR(100) NOT NULL,
    valid_from  DATE NOT NULL,
    valid_until DATE,
    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
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
    created_at               DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
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
    photo              VARCHAR(255) NULL,
    Officer_id_officer INT,
    created_at         DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at         DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    deleted_at         DATETIME NULL,
    CONSTRAINT fk_user_officer FOREIGN KEY (Officer_id_officer) REFERENCES Officer(id_officer)
) ENGINE=InnoDB;

CREATE TABLE Role (
    id_role     INT AUTO_INCREMENT PRIMARY KEY,
    name        VARCHAR(50) NOT NULL UNIQUE,
    description VARCHAR(255) NOT NULL DEFAULT '',
    scope       VARCHAR(10)  NOT NULL DEFAULT 'own',
    status      VARCHAR(20)  NOT NULL DEFAULT 'active',
    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    deleted_at  DATETIME NULL
) ENGINE=InnoDB;

CREATE TABLE User_Role_Delegation (
    id_user_role             INT AUTO_INCREMENT PRIMARY KEY,
    User_id_user             INT NOT NULL,
    Role_id_role             INT NOT NULL,
    Delegation_id_delegation INT NULL,
    created_at               DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at               DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    deleted_at               DATETIME NULL,
    CONSTRAINT fk_urd_user FOREIGN KEY (User_id_user) REFERENCES User(id_user),
    CONSTRAINT fk_urd_role FOREIGN KEY (Role_id_role) REFERENCES Role(id_role),
    CONSTRAINT fk_urd_delegation FOREIGN KEY (Delegation_id_delegation) REFERENCES Delegation(id_delegation),
    UNIQUE KEY uq_user_role_delegation (User_id_user, Role_id_role, Delegation_id_delegation)
) ENGINE=InnoDB;

CREATE TABLE Item (
    id_item             INT AUTO_INCREMENT PRIMARY KEY,
    Item_id_parent_item INT NULL,
    name                VARCHAR(150) NOT NULL,
    description         VARCHAR(255) NOT NULL DEFAULT '',
    calculation_type    VARCHAR(20) NOT NULL DEFAULT 'quantitative',
    created_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    deleted_at          DATETIME NULL,
    CONSTRAINT fk_item_parent FOREIGN KEY (Item_id_parent_item) REFERENCES Item(id_item)
) ENGINE=InnoDB;

CREATE TABLE Service (
    id_service INT AUTO_INCREMENT PRIMARY KEY,
    name       VARCHAR(100) NOT NULL,
    status     VARCHAR(20) NOT NULL DEFAULT 'active',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    deleted_at DATETIME NULL
) ENGINE=InnoDB;

CREATE TABLE Management_Type (
    id_management_type INT AUTO_INCREMENT PRIMARY KEY,
    name               VARCHAR(80) NOT NULL UNIQUE,
    created_at         DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at         DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    deleted_at         DATETIME NULL
) ENGINE=InnoDB;

CREATE TABLE Beneficiary (
    id_beneficiary INT AUTO_INCREMENT PRIMARY KEY,
    rut            VARCHAR(12) NOT NULL UNIQUE,
    name           VARCHAR(150) NOT NULL,
    phone          VARCHAR(20),
    address        VARCHAR(200) NOT NULL DEFAULT '',
    created_at     DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at     DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    deleted_at     DATETIME NULL
) ENGINE=InnoDB;

CREATE TABLE Territory (
    id_territory             INT AUTO_INCREMENT PRIMARY KEY,
    name                     VARCHAR(100) NOT NULL,
    Delegation_id_delegation INT NOT NULL,
    created_at               DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
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
    kind                 ENUM('NORMAL','BONUS','PENALTY') NOT NULL DEFAULT 'NORMAL',
    max_cap              DECIMAL(10,2) NULL,
    created_at           DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at           DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    deleted_at           DATETIME NULL,
    CONSTRAINT fk_positionitem_position FOREIGN KEY (Position_id_position) REFERENCES Position (id_position),
    CONSTRAINT fk_positionitem_item FOREIGN KEY (Item_id_item) REFERENCES Item(id_item)
) ENGINE=InnoDB;

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
    created_at           DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
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
    created_at           DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
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
    created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
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
    created_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    deleted_at          DATETIME NULL,
    CONSTRAINT fk_adjustment_officer FOREIGN KEY (Officer_id_officer) REFERENCES Officer(id_officer),
    CONSTRAINT fk_adjustment_period FOREIGN KEY (Period_id_period) REFERENCES Period(id_period),
    CONSTRAINT fk_adjustment_user FOREIGN KEY (User_id_responsible) REFERENCES User(id_user)
) ENGINE=InnoDB;

CREATE TABLE Activity (
    id_activity                INT AUTO_INCREMENT PRIMARY KEY,
    date                       DATE NOT NULL,
    request_description        TEXT,
    action_taken               TEXT,
    contact_name               VARCHAR(100),
    phone                      VARCHAR(20),
    Beneficiary_id_beneficiary INT NULL,
    status                     VARCHAR(30) NOT NULL DEFAULT 'registered',
    requires_visit             BOOLEAN NOT NULL DEFAULT FALSE,
    added_to_pipeline          BOOLEAN NOT NULL DEFAULT FALSE,
    Item_id_item               INT NOT NULL,
    Service_id_service         INT NULL,
    Delegation_id_delegation   INT NOT NULL,
    Officer_id_author          INT NOT NULL,
    created_at                 DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
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
    Management_Type_id_management_type INT NULL,
    date                               DATE NOT NULL,
    result                             VARCHAR(255) NOT NULL,
    scheduled_visit_date               DATE NULL,
    visit_date                         DATE NULL,
    report_delivery_date               DATE NULL,
    benefit_delivery_date              DATE NULL,
    Activity_id_activity               INT NOT NULL,
    created_at                         DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
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
    created_at           DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
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
    Officer_id_reviewer  INT NULL,
    created_at           DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at           DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    deleted_at           DATETIME NULL,
    CONSTRAINT fk_validation_evidence FOREIGN KEY (Evidence_id_evidence) REFERENCES Evidence(id_evidence),
    CONSTRAINT fk_validation_officer FOREIGN KEY (Officer_id_reviewer) REFERENCES Officer(id_officer)
) ENGINE=InnoDB;

CREATE TABLE Commitment (
    id_commitment            INT AUTO_INCREMENT PRIMARY KEY,
    source                   VARCHAR(100),
    request_date             DATE NULL,
    description              TEXT NULL,
    requester                VARCHAR(100) NOT NULL,
    requester_type           ENUM('INTERNAL','EXTERNAL') NOT NULL DEFAULT 'EXTERNAL',
    Territory_id_territory   INT NOT NULL,
    due_date                 DATE NOT NULL,
    support                  VARCHAR(100),
    status                   VARCHAR(30) NOT NULL DEFAULT 'entered',
    notes                    TEXT,
    Officer_id_responsible   INT NOT NULL,
    Delegation_id_delegation INT NOT NULL,
    created_at               DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at               DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    deleted_at               DATETIME NULL,
    CONSTRAINT fk_commitment_officer FOREIGN KEY (Officer_id_responsible) REFERENCES Officer(id_officer),
    CONSTRAINT fk_commitment_delegation FOREIGN KEY (Delegation_id_delegation) REFERENCES Delegation(id_delegation),
    CONSTRAINT fk_commitment_territory FOREIGN KEY (Territory_id_territory) REFERENCES Territory(id_territory)
) ENGINE=InnoDB;

CREATE TABLE Audit_Log (
    id_audit_log    BIGINT AUTO_INCREMENT PRIMARY KEY,
    event           VARCHAR(100) NOT NULL,
    date            DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    affected_entity VARCHAR(50) NOT NULL,
    record_id       INT NOT NULL,
    previous_value  TEXT,
    new_value       TEXT,
    User_id_user    INT NOT NULL,
    created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    deleted_at      DATETIME NULL,
    CONSTRAINT fk_audit_log_user FOREIGN KEY (User_id_user) REFERENCES User(id_user)
) ENGINE=InnoDB;

INSERT INTO Management_Type (name) VALUES
    ('In-person user service'),
    ('Field visit'),
    ('Report delivery'),
    ('Benefit delivery'),
    ('Emergency'),
    ('Other tasks');

SET FOREIGN_KEY_CHECKS = 1;
