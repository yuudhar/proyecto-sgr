DROP DATABASE IF EXISTS `sgr_django_der`;
CREATE DATABASE `sgr_django_der` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE `sgr_django_der`;

SET SQL_MODE = "NO_AUTO_VALUE_ON_ZERO";
START TRANSACTION;
SET time_zone = "+00:00";

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!40101 SET NAMES utf8mb4 */;

CREATE TABLE `accounts_roleprofile` (
  `id` bigint(20) NOT NULL,
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  `deleted_at` datetime(6) DEFAULT NULL,
  `description` varchar(255) NOT NULL,
  `scope` varchar(10) NOT NULL,
  `status` varchar(20) NOT NULL,
  `group_id` int(11) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `accounts_userprofile` (
  `id` bigint(20) NOT NULL,
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  `deleted_at` datetime(6) DEFAULT NULL,
  `status` varchar(20) NOT NULL,
  `officer_id` bigint(20) DEFAULT NULL,
  `user_id` int(11) NOT NULL,
  `photo` varchar(255) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `accounts_userroledelegation` (
  `id` bigint(20) NOT NULL,
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  `deleted_at` datetime(6) DEFAULT NULL,
  `delegation_id` bigint(20) DEFAULT NULL,
  `role_id` int(11) NOT NULL,
  `user_id` int(11) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `auth_group` (
  `id` int(11) NOT NULL,
  `name` varchar(150) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `auth_group_permissions` (
  `id` bigint(20) NOT NULL,
  `group_id` int(11) NOT NULL,
  `permission_id` int(11) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `auth_permission` (
  `id` int(11) NOT NULL,
  `name` varchar(255) NOT NULL,
  `content_type_id` int(11) NOT NULL,
  `codename` varchar(100) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `auth_user` (
  `id` int(11) NOT NULL,
  `password` varchar(128) NOT NULL,
  `last_login` datetime(6) DEFAULT NULL,
  `is_superuser` tinyint(1) NOT NULL,
  `username` varchar(150) NOT NULL,
  `first_name` varchar(150) NOT NULL,
  `last_name` varchar(150) NOT NULL,
  `email` varchar(254) NOT NULL,
  `is_staff` tinyint(1) NOT NULL,
  `is_active` tinyint(1) NOT NULL,
  `date_joined` datetime(6) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `auth_user_groups` (
  `id` bigint(20) NOT NULL,
  `user_id` int(11) NOT NULL,
  `group_id` int(11) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `auth_user_user_permissions` (
  `id` bigint(20) NOT NULL,
  `user_id` int(11) NOT NULL,
  `permission_id` int(11) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `core_auditlog` (
  `id` bigint(20) NOT NULL,
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  `deleted_at` datetime(6) DEFAULT NULL,
  `event` varchar(100) NOT NULL,
  `date` datetime(6) NOT NULL,
  `affected_entity` varchar(50) NOT NULL,
  `record_id` int(10) UNSIGNED NOT NULL CHECK (`record_id` >= 0),
  `previous_value` longtext DEFAULT NULL,
  `new_value` longtext DEFAULT NULL,
  `user_id` int(11) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `django_admin_log` (
  `id` int(11) NOT NULL,
  `action_time` datetime(6) NOT NULL,
  `object_id` longtext DEFAULT NULL,
  `object_repr` varchar(200) NOT NULL,
  `action_flag` smallint(5) UNSIGNED NOT NULL CHECK (`action_flag` >= 0),
  `change_message` longtext NOT NULL,
  `content_type_id` int(11) DEFAULT NULL,
  `user_id` int(11) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `django_content_type` (
  `id` int(11) NOT NULL,
  `app_label` varchar(100) NOT NULL,
  `model` varchar(100) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `django_migrations` (
  `id` bigint(20) NOT NULL,
  `app` varchar(255) NOT NULL,
  `name` varchar(255) NOT NULL,
  `applied` datetime(6) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `django_session` (
  `session_key` varchar(40) NOT NULL,
  `session_data` longtext NOT NULL,
  `expire_date` datetime(6) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `evidence_evidence` (
  `id` bigint(20) NOT NULL,
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  `deleted_at` datetime(6) DEFAULT NULL,
  `unique_code` varchar(50) NOT NULL,
  `file_link` varchar(255) NOT NULL,
  `uploaded_at` datetime(6) NOT NULL,
  `review_status` varchar(30) NOT NULL,
  `metadata` longtext DEFAULT NULL,
  `activity_id` bigint(20) NOT NULL,
  `author_officer_id` bigint(20) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `evidence_validation` (
  `id` bigint(20) NOT NULL,
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  `deleted_at` datetime(6) DEFAULT NULL,
  `decision` varchar(30) NOT NULL,
  `date` datetime(6) NOT NULL,
  `notes` longtext DEFAULT NULL,
  `result` varchar(50) DEFAULT NULL,
  `version` varchar(20) NOT NULL,
  `evidence_id` bigint(20) NOT NULL,
  `reviewer_officer_id` bigint(20) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `operations_activity` (
  `id` bigint(20) NOT NULL,
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  `deleted_at` datetime(6) DEFAULT NULL,
  `date` date NOT NULL,
  `request_description` longtext NOT NULL,
  `action_taken` longtext NOT NULL,
  `contact_name` varchar(100) NOT NULL,
  `phone` varchar(20) NOT NULL,
  `status` varchar(30) NOT NULL,
  `requires_visit` tinyint(1) NOT NULL,
  `added_to_pipeline` tinyint(1) NOT NULL,
  `author_officer_id` bigint(20) NOT NULL,
  `beneficiary_id` bigint(20) DEFAULT NULL,
  `delegation_id` bigint(20) NOT NULL,
  `item_id` bigint(20) NOT NULL,
  `service_id` bigint(20) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `operations_commitment` (
  `id` bigint(20) NOT NULL,
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  `deleted_at` datetime(6) DEFAULT NULL,
  `source` varchar(100) DEFAULT NULL,
  `request_date` date DEFAULT NULL,
  `description` longtext DEFAULT NULL,
  `requester` varchar(100) NOT NULL,
  `requester_type` varchar(10) NOT NULL,
  `due_date` date NOT NULL,
  `support` varchar(100) DEFAULT NULL,
  `status` varchar(30) NOT NULL,
  `notes` longtext DEFAULT NULL,
  `delegation_id` bigint(20) NOT NULL,
  `responsible_officer_id` bigint(20) NOT NULL,
  `territory_id` bigint(20) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `operations_followup` (
  `id` bigint(20) NOT NULL,
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  `deleted_at` datetime(6) DEFAULT NULL,
  `sequence_number` smallint(5) UNSIGNED NOT NULL CHECK (`sequence_number` >= 0),
  `date` date NOT NULL,
  `result` varchar(255) NOT NULL,
  `scheduled_visit_date` date DEFAULT NULL,
  `visit_date` date DEFAULT NULL,
  `report_delivery_date` date DEFAULT NULL,
  `benefit_delivery_date` date DEFAULT NULL,
  `activity_id` bigint(20) NOT NULL,
  `management_type_id` bigint(20) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `operations_managementtype` (
  `id` bigint(20) NOT NULL,
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  `deleted_at` datetime(6) DEFAULT NULL,
  `name` varchar(80) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `organization_beneficiary` (
  `id` bigint(20) NOT NULL,
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  `deleted_at` datetime(6) DEFAULT NULL,
  `rut` varchar(12) NOT NULL,
  `name` varchar(150) NOT NULL,
  `phone` varchar(20) DEFAULT NULL,
  `address` varchar(200) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `organization_delegation` (
  `id` bigint(20) NOT NULL,
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  `deleted_at` datetime(6) DEFAULT NULL,
  `name` varchar(100) NOT NULL,
  `status` varchar(20) NOT NULL,
  `managers` varchar(255) DEFAULT NULL,
  `scope` varchar(100) DEFAULT NULL,
  `color` varchar(7) NOT NULL,
  `address` varchar(200) NOT NULL,
  `commune` varchar(100) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `organization_item` (
  `id` bigint(20) NOT NULL,
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  `deleted_at` datetime(6) DEFAULT NULL,
  `name` varchar(150) NOT NULL,
  `calculation_type` varchar(20) NOT NULL,
  `parent_item_id` bigint(20) DEFAULT NULL,
  `description` varchar(255) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `organization_officer` (
  `id` bigint(20) NOT NULL,
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  `deleted_at` datetime(6) DEFAULT NULL,
  `institutional_id` varchar(20) NOT NULL,
  `name` varchar(150) NOT NULL,
  `status` varchar(20) NOT NULL,
  `delegation_id` bigint(20) NOT NULL,
  `position_id` bigint(20) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `organization_position` (
  `id` bigint(20) NOT NULL,
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  `deleted_at` datetime(6) DEFAULT NULL,
  `name` varchar(100) NOT NULL,
  `valid_from` date NOT NULL,
  `valid_until` date DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `organization_positionitem` (
  `id` bigint(20) NOT NULL,
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  `deleted_at` datetime(6) DEFAULT NULL,
  `weight` decimal(5,2) NOT NULL,
  `valid_from` date NOT NULL,
  `valid_until` date DEFAULT NULL,
  `kind` varchar(20) NOT NULL,
  `max_cap` decimal(10,2) DEFAULT NULL,
  `item_id` bigint(20) NOT NULL,
  `position_id` bigint(20) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `organization_service` (
  `id` bigint(20) NOT NULL,
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  `deleted_at` datetime(6) DEFAULT NULL,
  `name` varchar(100) NOT NULL,
  `status` varchar(20) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `organization_territory` (
  `id` bigint(20) NOT NULL,
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  `deleted_at` datetime(6) DEFAULT NULL,
  `name` varchar(100) NOT NULL,
  `delegation_id` bigint(20) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `planning_adjustment` (
  `id` bigint(20) NOT NULL,
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  `deleted_at` datetime(6) DEFAULT NULL,
  `kind` varchar(20) NOT NULL,
  `reason` varchar(255) NOT NULL,
  `percentage_value` decimal(5,2) NOT NULL,
  `date` datetime(6) NOT NULL,
  `officer_id` bigint(20) NOT NULL,
  `responsible_user_id` int(11) NOT NULL,
  `period_id` bigint(20) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `planning_goal` (
  `id` bigint(20) NOT NULL,
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  `deleted_at` datetime(6) DEFAULT NULL,
  `target_value` decimal(10,2) NOT NULL,
  `unit` varchar(50) NOT NULL,
  `weight` decimal(5,2) NOT NULL,
  `version` int(10) UNSIGNED NOT NULL CHECK (`version` >= 0),
  `item_id` bigint(20) NOT NULL,
  `officer_id` bigint(20) DEFAULT NULL,
  `position_id` bigint(20) DEFAULT NULL,
  `period_id` bigint(20) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `planning_indicator` (
  `id` bigint(20) NOT NULL,
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  `deleted_at` datetime(6) DEFAULT NULL,
  `progress` decimal(10,2) NOT NULL,
  `compliance` decimal(5,2) NOT NULL,
  `weighting` decimal(5,2) NOT NULL,
  `status_light` varchar(20) NOT NULL,
  `calculated_at` datetime(6) NOT NULL,
  `goal_id` bigint(20) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE `planning_period` (
  `id` bigint(20) NOT NULL,
  `created_at` datetime(6) NOT NULL,
  `updated_at` datetime(6) NOT NULL,
  `deleted_at` datetime(6) DEFAULT NULL,
  `start_date` date NOT NULL,
  `end_date` date NOT NULL,
  `computable_days` int(10) UNSIGNED NOT NULL CHECK (`computable_days` >= 0),
  `status` varchar(20) NOT NULL,
  `collective_threshold` decimal(5,2) NOT NULL,
  `amber_threshold` decimal(5,2) NOT NULL,
  `weighted_cap` decimal(5,2) NOT NULL,
  `parameters_version` varchar(20) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

ALTER TABLE `accounts_roleprofile`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `group_id` (`group_id`);

ALTER TABLE `accounts_userprofile`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `user_id` (`user_id`),
  ADD UNIQUE KEY `officer_id` (`officer_id`);

ALTER TABLE `accounts_userroledelegation`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `uq_usuario_rol_delegacion` (`user_id`,`role_id`,`delegation_id`),
  ADD KEY `accounts_userroledel_delegation_id_a9c8c262_fk_organizat` (`delegation_id`),
  ADD KEY `accounts_userroledelegation_role_id_d5bc2d6a_fk_auth_group_id` (`role_id`);

ALTER TABLE `auth_group`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `name` (`name`);

ALTER TABLE `auth_group_permissions`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `auth_group_permissions_group_id_permission_id_0cd325b0_uniq` (`group_id`,`permission_id`),
  ADD KEY `auth_group_permissio_permission_id_84c5c92e_fk_auth_perm` (`permission_id`);

ALTER TABLE `auth_permission`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `auth_permission_content_type_id_codename_01ab375a_uniq` (`content_type_id`,`codename`);

ALTER TABLE `auth_user`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `username` (`username`);

ALTER TABLE `auth_user_groups`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `auth_user_groups_user_id_group_id_94350c0c_uniq` (`user_id`,`group_id`),
  ADD KEY `auth_user_groups_group_id_97559544_fk_auth_group_id` (`group_id`);

ALTER TABLE `auth_user_user_permissions`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `auth_user_user_permissions_user_id_permission_id_14a6b632_uniq` (`user_id`,`permission_id`),
  ADD KEY `auth_user_user_permi_permission_id_1fbb5f2c_fk_auth_perm` (`permission_id`);

ALTER TABLE `core_auditlog`
  ADD PRIMARY KEY (`id`),
  ADD KEY `core_auditlog_user_id_3797aaab_fk_auth_user_id` (`user_id`);

ALTER TABLE `django_admin_log`
  ADD PRIMARY KEY (`id`),
  ADD KEY `django_admin_log_content_type_id_c4bce8eb_fk_django_co` (`content_type_id`),
  ADD KEY `django_admin_log_user_id_c564eba6_fk_auth_user_id` (`user_id`);

ALTER TABLE `django_content_type`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `django_content_type_app_label_model_76bd3d3b_uniq` (`app_label`,`model`);

ALTER TABLE `django_migrations`
  ADD PRIMARY KEY (`id`);

ALTER TABLE `django_session`
  ADD PRIMARY KEY (`session_key`),
  ADD KEY `django_session_expire_date_a5c62663` (`expire_date`);

ALTER TABLE `evidence_evidence`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `unique_code` (`unique_code`),
  ADD KEY `evidence_evidence_activity_id_0f5c510b_fk_operations_activity_id` (`activity_id`),
  ADD KEY `evidence_evidence_author_officer_id_8a68c44f_fk_organizat` (`author_officer_id`);

ALTER TABLE `evidence_validation`
  ADD PRIMARY KEY (`id`),
  ADD KEY `evidence_validation_evidence_id_cc0a0327_fk_evidence_evidence_id` (`evidence_id`),
  ADD KEY `evidence_validation_reviewer_officer_id_3e66f1fc_fk_organizat` (`reviewer_officer_id`);

ALTER TABLE `operations_activity`
  ADD PRIMARY KEY (`id`),
  ADD KEY `operations_activity_author_officer_id_541accc5_fk_organizat` (`author_officer_id`),
  ADD KEY `operations_activity_beneficiary_id_c644adc2_fk_organizat` (`beneficiary_id`),
  ADD KEY `operations_activity_delegation_id_1d50e689_fk_organizat` (`delegation_id`),
  ADD KEY `operations_activity_item_id_bc7fb032_fk_organization_item_id` (`item_id`),
  ADD KEY `operations_activity_service_id_5569328a_fk_organizat` (`service_id`);

ALTER TABLE `operations_commitment`
  ADD PRIMARY KEY (`id`),
  ADD KEY `operations_commitmen_delegation_id_40bdfd9e_fk_organizat` (`delegation_id`),
  ADD KEY `operations_commitmen_responsible_officer__28e13bc7_fk_organizat` (`responsible_officer_id`),
  ADD KEY `operations_commitmen_territory_id_cf446f34_fk_organizat` (`territory_id`);

ALTER TABLE `operations_followup`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `uq_activity_followup` (`activity_id`,`sequence_number`),
  ADD KEY `operations_followup_management_type_id_99f8051b_fk_operation` (`management_type_id`);

ALTER TABLE `operations_managementtype`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `name` (`name`);

ALTER TABLE `organization_beneficiary`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `rut` (`rut`);

ALTER TABLE `organization_delegation`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `name` (`name`);

ALTER TABLE `organization_item`
  ADD PRIMARY KEY (`id`),
  ADD KEY `organization_item_parent_item_id_5d2e054a_fk_organizat` (`parent_item_id`);

ALTER TABLE `organization_officer`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `institutional_id` (`institutional_id`),
  ADD KEY `organization_officer_delegation_id_ff127796_fk_organizat` (`delegation_id`),
  ADD KEY `organization_officer_position_id_d6fa7362_fk_organizat` (`position_id`);

ALTER TABLE `organization_position`
  ADD PRIMARY KEY (`id`);

ALTER TABLE `organization_positionitem`
  ADD PRIMARY KEY (`id`),
  ADD KEY `organization_positio_item_id_2590b223_fk_organizat` (`item_id`),
  ADD KEY `organization_positio_position_id_abe02fa5_fk_organizat` (`position_id`);

ALTER TABLE `organization_service`
  ADD PRIMARY KEY (`id`);

ALTER TABLE `organization_territory`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `uq_territory_delegation` (`name`,`delegation_id`),
  ADD KEY `organization_territo_delegation_id_df5ccbc0_fk_organizat` (`delegation_id`);

ALTER TABLE `planning_adjustment`
  ADD PRIMARY KEY (`id`),
  ADD KEY `planning_adjustment_officer_id_2e052aab_fk_organizat` (`officer_id`),
  ADD KEY `planning_adjustment_responsible_user_id_ba3f37d4_fk_auth_user_id` (`responsible_user_id`),
  ADD KEY `planning_adjustment_period_id_8c03143a_fk_planning_period_id` (`period_id`);

ALTER TABLE `planning_goal`
  ADD PRIMARY KEY (`id`),
  ADD KEY `planning_goal_item_id_e0b0c5b3_fk_organization_item_id` (`item_id`),
  ADD KEY `planning_goal_officer_id_048697b6_fk_organization_officer_id` (`officer_id`),
  ADD KEY `planning_goal_position_id_69d1ed64_fk_organization_position_id` (`position_id`),
  ADD KEY `planning_goal_period_id_bf349c87_fk_planning_period_id` (`period_id`);

ALTER TABLE `planning_indicator`
  ADD PRIMARY KEY (`id`),
  ADD KEY `planning_indicator_goal_id_3fa43af3_fk_planning_goal_id` (`goal_id`);

ALTER TABLE `planning_period`
  ADD PRIMARY KEY (`id`);

ALTER TABLE `accounts_roleprofile`
  MODIFY `id` bigint(20) NOT NULL AUTO_INCREMENT;

ALTER TABLE `accounts_userprofile`
  MODIFY `id` bigint(20) NOT NULL AUTO_INCREMENT;

ALTER TABLE `accounts_userroledelegation`
  MODIFY `id` bigint(20) NOT NULL AUTO_INCREMENT;

ALTER TABLE `auth_group`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT;

ALTER TABLE `auth_group_permissions`
  MODIFY `id` bigint(20) NOT NULL AUTO_INCREMENT;

ALTER TABLE `auth_permission`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT;

ALTER TABLE `auth_user`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT;

ALTER TABLE `auth_user_groups`
  MODIFY `id` bigint(20) NOT NULL AUTO_INCREMENT;

ALTER TABLE `auth_user_user_permissions`
  MODIFY `id` bigint(20) NOT NULL AUTO_INCREMENT;

ALTER TABLE `core_auditlog`
  MODIFY `id` bigint(20) NOT NULL AUTO_INCREMENT;

ALTER TABLE `django_admin_log`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT;

ALTER TABLE `django_content_type`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT;

ALTER TABLE `django_migrations`
  MODIFY `id` bigint(20) NOT NULL AUTO_INCREMENT;

ALTER TABLE `evidence_evidence`
  MODIFY `id` bigint(20) NOT NULL AUTO_INCREMENT;

ALTER TABLE `evidence_validation`
  MODIFY `id` bigint(20) NOT NULL AUTO_INCREMENT;

ALTER TABLE `operations_activity`
  MODIFY `id` bigint(20) NOT NULL AUTO_INCREMENT;

ALTER TABLE `operations_commitment`
  MODIFY `id` bigint(20) NOT NULL AUTO_INCREMENT;

ALTER TABLE `operations_followup`
  MODIFY `id` bigint(20) NOT NULL AUTO_INCREMENT;

ALTER TABLE `operations_managementtype`
  MODIFY `id` bigint(20) NOT NULL AUTO_INCREMENT;

ALTER TABLE `organization_beneficiary`
  MODIFY `id` bigint(20) NOT NULL AUTO_INCREMENT;

ALTER TABLE `organization_delegation`
  MODIFY `id` bigint(20) NOT NULL AUTO_INCREMENT;

ALTER TABLE `organization_item`
  MODIFY `id` bigint(20) NOT NULL AUTO_INCREMENT;

ALTER TABLE `organization_officer`
  MODIFY `id` bigint(20) NOT NULL AUTO_INCREMENT;

ALTER TABLE `organization_position`
  MODIFY `id` bigint(20) NOT NULL AUTO_INCREMENT;

ALTER TABLE `organization_positionitem`
  MODIFY `id` bigint(20) NOT NULL AUTO_INCREMENT;

ALTER TABLE `organization_service`
  MODIFY `id` bigint(20) NOT NULL AUTO_INCREMENT;

ALTER TABLE `organization_territory`
  MODIFY `id` bigint(20) NOT NULL AUTO_INCREMENT;

ALTER TABLE `planning_adjustment`
  MODIFY `id` bigint(20) NOT NULL AUTO_INCREMENT;

ALTER TABLE `planning_goal`
  MODIFY `id` bigint(20) NOT NULL AUTO_INCREMENT;

ALTER TABLE `planning_indicator`
  MODIFY `id` bigint(20) NOT NULL AUTO_INCREMENT;

ALTER TABLE `planning_period`
  MODIFY `id` bigint(20) NOT NULL AUTO_INCREMENT;

ALTER TABLE `accounts_roleprofile`
  ADD CONSTRAINT `accounts_roleprofile_group_id_2f65c810_fk_auth_group_id` FOREIGN KEY (`group_id`) REFERENCES `auth_group` (`id`);

ALTER TABLE `accounts_userprofile`
  ADD CONSTRAINT `accounts_userprofile_officer_id_d8f05183_fk_organizat` FOREIGN KEY (`officer_id`) REFERENCES `organization_officer` (`id`),
  ADD CONSTRAINT `accounts_userprofile_user_id_92240672_fk_auth_user_id` FOREIGN KEY (`user_id`) REFERENCES `auth_user` (`id`);

ALTER TABLE `accounts_userroledelegation`
  ADD CONSTRAINT `accounts_userroledel_delegation_id_a9c8c262_fk_organizat` FOREIGN KEY (`delegation_id`) REFERENCES `organization_delegation` (`id`),
  ADD CONSTRAINT `accounts_userroledelegation_role_id_d5bc2d6a_fk_auth_group_id` FOREIGN KEY (`role_id`) REFERENCES `auth_group` (`id`),
  ADD CONSTRAINT `accounts_userroledelegation_user_id_932b999c_fk_auth_user_id` FOREIGN KEY (`user_id`) REFERENCES `auth_user` (`id`);

ALTER TABLE `auth_group_permissions`
  ADD CONSTRAINT `auth_group_permissio_permission_id_84c5c92e_fk_auth_perm` FOREIGN KEY (`permission_id`) REFERENCES `auth_permission` (`id`),
  ADD CONSTRAINT `auth_group_permissions_group_id_b120cbf9_fk_auth_group_id` FOREIGN KEY (`group_id`) REFERENCES `auth_group` (`id`);

ALTER TABLE `auth_permission`
  ADD CONSTRAINT `auth_permission_content_type_id_2f476e4b_fk_django_co` FOREIGN KEY (`content_type_id`) REFERENCES `django_content_type` (`id`);

ALTER TABLE `auth_user_groups`
  ADD CONSTRAINT `auth_user_groups_group_id_97559544_fk_auth_group_id` FOREIGN KEY (`group_id`) REFERENCES `auth_group` (`id`),
  ADD CONSTRAINT `auth_user_groups_user_id_6a12ed8b_fk_auth_user_id` FOREIGN KEY (`user_id`) REFERENCES `auth_user` (`id`);

ALTER TABLE `auth_user_user_permissions`
  ADD CONSTRAINT `auth_user_user_permi_permission_id_1fbb5f2c_fk_auth_perm` FOREIGN KEY (`permission_id`) REFERENCES `auth_permission` (`id`),
  ADD CONSTRAINT `auth_user_user_permissions_user_id_a95ead1b_fk_auth_user_id` FOREIGN KEY (`user_id`) REFERENCES `auth_user` (`id`);

ALTER TABLE `core_auditlog`
  ADD CONSTRAINT `core_auditlog_user_id_3797aaab_fk_auth_user_id` FOREIGN KEY (`user_id`) REFERENCES `auth_user` (`id`);

ALTER TABLE `django_admin_log`
  ADD CONSTRAINT `django_admin_log_content_type_id_c4bce8eb_fk_django_co` FOREIGN KEY (`content_type_id`) REFERENCES `django_content_type` (`id`),
  ADD CONSTRAINT `django_admin_log_user_id_c564eba6_fk_auth_user_id` FOREIGN KEY (`user_id`) REFERENCES `auth_user` (`id`);

ALTER TABLE `evidence_evidence`
  ADD CONSTRAINT `evidence_evidence_activity_id_0f5c510b_fk_operations_activity_id` FOREIGN KEY (`activity_id`) REFERENCES `operations_activity` (`id`),
  ADD CONSTRAINT `evidence_evidence_author_officer_id_8a68c44f_fk_organizat` FOREIGN KEY (`author_officer_id`) REFERENCES `organization_officer` (`id`);

ALTER TABLE `evidence_validation`
  ADD CONSTRAINT `evidence_validation_evidence_id_cc0a0327_fk_evidence_evidence_id` FOREIGN KEY (`evidence_id`) REFERENCES `evidence_evidence` (`id`),
  ADD CONSTRAINT `evidence_validation_reviewer_officer_id_3e66f1fc_fk_organizat` FOREIGN KEY (`reviewer_officer_id`) REFERENCES `organization_officer` (`id`);

ALTER TABLE `operations_activity`
  ADD CONSTRAINT `operations_activity_author_officer_id_541accc5_fk_organizat` FOREIGN KEY (`author_officer_id`) REFERENCES `organization_officer` (`id`),
  ADD CONSTRAINT `operations_activity_beneficiary_id_c644adc2_fk_organizat` FOREIGN KEY (`beneficiary_id`) REFERENCES `organization_beneficiary` (`id`),
  ADD CONSTRAINT `operations_activity_delegation_id_1d50e689_fk_organizat` FOREIGN KEY (`delegation_id`) REFERENCES `organization_delegation` (`id`),
  ADD CONSTRAINT `operations_activity_item_id_bc7fb032_fk_organization_item_id` FOREIGN KEY (`item_id`) REFERENCES `organization_item` (`id`),
  ADD CONSTRAINT `operations_activity_service_id_5569328a_fk_organizat` FOREIGN KEY (`service_id`) REFERENCES `organization_service` (`id`);

ALTER TABLE `operations_commitment`
  ADD CONSTRAINT `operations_commitmen_delegation_id_40bdfd9e_fk_organizat` FOREIGN KEY (`delegation_id`) REFERENCES `organization_delegation` (`id`),
  ADD CONSTRAINT `operations_commitmen_responsible_officer__28e13bc7_fk_organizat` FOREIGN KEY (`responsible_officer_id`) REFERENCES `organization_officer` (`id`),
  ADD CONSTRAINT `operations_commitmen_territory_id_cf446f34_fk_organizat` FOREIGN KEY (`territory_id`) REFERENCES `organization_territory` (`id`);

ALTER TABLE `operations_followup`
  ADD CONSTRAINT `operations_followup_activity_id_0498eb10_fk_operation` FOREIGN KEY (`activity_id`) REFERENCES `operations_activity` (`id`),
  ADD CONSTRAINT `operations_followup_management_type_id_99f8051b_fk_operation` FOREIGN KEY (`management_type_id`) REFERENCES `operations_managementtype` (`id`);

ALTER TABLE `organization_item`
  ADD CONSTRAINT `organization_item_parent_item_id_5d2e054a_fk_organizat` FOREIGN KEY (`parent_item_id`) REFERENCES `organization_item` (`id`);

ALTER TABLE `organization_officer`
  ADD CONSTRAINT `organization_officer_delegation_id_ff127796_fk_organizat` FOREIGN KEY (`delegation_id`) REFERENCES `organization_delegation` (`id`),
  ADD CONSTRAINT `organization_officer_position_id_d6fa7362_fk_organizat` FOREIGN KEY (`position_id`) REFERENCES `organization_position` (`id`);

ALTER TABLE `organization_positionitem`
  ADD CONSTRAINT `organization_positio_item_id_2590b223_fk_organizat` FOREIGN KEY (`item_id`) REFERENCES `organization_item` (`id`),
  ADD CONSTRAINT `organization_positio_position_id_abe02fa5_fk_organizat` FOREIGN KEY (`position_id`) REFERENCES `organization_position` (`id`);

ALTER TABLE `organization_territory`
  ADD CONSTRAINT `organization_territo_delegation_id_df5ccbc0_fk_organizat` FOREIGN KEY (`delegation_id`) REFERENCES `organization_delegation` (`id`);

ALTER TABLE `planning_adjustment`
  ADD CONSTRAINT `planning_adjustment_officer_id_2e052aab_fk_organizat` FOREIGN KEY (`officer_id`) REFERENCES `organization_officer` (`id`),
  ADD CONSTRAINT `planning_adjustment_period_id_8c03143a_fk_planning_period_id` FOREIGN KEY (`period_id`) REFERENCES `planning_period` (`id`),
  ADD CONSTRAINT `planning_adjustment_responsible_user_id_ba3f37d4_fk_auth_user_id` FOREIGN KEY (`responsible_user_id`) REFERENCES `auth_user` (`id`);

ALTER TABLE `planning_goal`
  ADD CONSTRAINT `planning_goal_item_id_e0b0c5b3_fk_organization_item_id` FOREIGN KEY (`item_id`) REFERENCES `organization_item` (`id`),
  ADD CONSTRAINT `planning_goal_officer_id_048697b6_fk_organization_officer_id` FOREIGN KEY (`officer_id`) REFERENCES `organization_officer` (`id`),
  ADD CONSTRAINT `planning_goal_period_id_bf349c87_fk_planning_period_id` FOREIGN KEY (`period_id`) REFERENCES `planning_period` (`id`),
  ADD CONSTRAINT `planning_goal_position_id_69d1ed64_fk_organization_position_id` FOREIGN KEY (`position_id`) REFERENCES `organization_position` (`id`);

ALTER TABLE `planning_indicator`
  ADD CONSTRAINT `planning_indicator_goal_id_3fa43af3_fk_planning_goal_id` FOREIGN KEY (`goal_id`) REFERENCES `planning_goal` (`id`);
COMMIT;

/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
