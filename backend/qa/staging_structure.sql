-- MySQL dump 10.13  Distrib 8.0.45, for Win64 (x86_64)
--
-- Host: localhost    Database: student_db
-- ------------------------------------------------------
-- Server version	8.0.45

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!50503 SET NAMES utf8mb4 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;

--
-- Table structure for table `addition_logs`
--

DROP TABLE IF EXISTS `addition_logs`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `addition_logs` (
  `id` int NOT NULL AUTO_INCREMENT,
  `usn` varchar(100) DEFAULT NULL,
  `student_name` varchar(150) DEFAULT NULL,
  `added_by` varchar(100) DEFAULT NULL,
  `timestamp` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=226 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `audit_log`
--

DROP TABLE IF EXISTS `audit_log`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `audit_log` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `username` varchar(100) DEFAULT NULL,
  `role` varchar(20) DEFAULT NULL,
  `action` varchar(80) NOT NULL,
  `target_table` varchar(100) DEFAULT NULL,
  `target_id` varchar(200) DEFAULT NULL,
  `summary` text,
  `success` tinyint(1) DEFAULT '1',
  `error_info` text,
  `ip_address` varchar(60) DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_al_username` (`username`),
  KEY `idx_al_action` (`action`),
  KEY `idx_al_created_at` (`created_at`)
) ENGINE=InnoDB AUTO_INCREMENT=15742 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `db_backups`
--

DROP TABLE IF EXISTS `db_backups`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `db_backups` (
  `id` int NOT NULL AUTO_INCREMENT,
  `backup_name` varchar(255) NOT NULL,
  `backup_path` text NOT NULL,
  `backup_type` enum('manual','auto_daily','auto_weekly','pre_restore') DEFAULT 'manual',
  `size_bytes` bigint DEFAULT '0',
  `status` enum('running','success','failed','verified') DEFAULT 'running',
  `verified` tinyint(1) DEFAULT '0',
  `created_by` varchar(100) DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `completed_at` timestamp NULL DEFAULT NULL,
  `error_message` text,
  `record_count` int DEFAULT '0',
  PRIMARY KEY (`id`),
  UNIQUE KEY `backup_name` (`backup_name`)
) ENGINE=InnoDB AUTO_INCREMENT=129 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `deletion_logs`
--

DROP TABLE IF EXISTS `deletion_logs`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `deletion_logs` (
  `id` int NOT NULL AUTO_INCREMENT,
  `usn` varchar(100) DEFAULT NULL,
  `student_name` varchar(150) DEFAULT NULL,
  `deleted_by` varchar(100) DEFAULT NULL,
  `timestamp` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `restore_token` char(36) DEFAULT NULL,
  `restored` tinyint(1) DEFAULT '0',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=1596 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `export_logs`
--

DROP TABLE IF EXISTS `export_logs`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `export_logs` (
  `id` int NOT NULL AUTO_INCREMENT,
  `format` varchar(20) NOT NULL,
  `record_count` int DEFAULT NULL,
  `exported_by` varchar(100) DEFAULT NULL,
  `timestamp` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=1430 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `field_registry`
--

DROP TABLE IF EXISTS `field_registry`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `field_registry` (
  `id` int NOT NULL AUTO_INCREMENT,
  `original_name` varchar(255) NOT NULL,
  `canonical_name` varchar(255) NOT NULL,
  `aliases` json DEFAULT NULL,
  `data_type` varchar(50) DEFAULT 'text',
  `is_dynamic` tinyint(1) DEFAULT '1',
  `searchable` tinyint(1) DEFAULT '1',
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `canonical_name` (`canonical_name`)
) ENGINE=InnoDB AUTO_INCREMENT=83 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `file_delete_provenance_snapshots`
--

DROP TABLE IF EXISTS `file_delete_provenance_snapshots`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `file_delete_provenance_snapshots` (
  `id` int NOT NULL AUTO_INCREMENT,
  `undo_token` varchar(100) NOT NULL,
  `source_filename` varchar(255) NOT NULL,
  `usn` varchar(100) NOT NULL,
  `field_name` varchar(100) NOT NULL,
  `field_value` text,
  `import_id` int DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_fdps_token` (`undo_token`),
  KEY `idx_fdps_filename` (`source_filename`),
  KEY `idx_fdps_usn` (`usn`)
) ENGINE=InnoDB AUTO_INCREMENT=15728 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `global_undo_snapshots`
--

DROP TABLE IF EXISTS `global_undo_snapshots`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `global_undo_snapshots` (
  `id` int NOT NULL AUTO_INCREMENT,
  `undo_token` varchar(100) NOT NULL,
  `operation_type` varchar(50) NOT NULL,
  `snapshot_data` longtext NOT NULL,
  `performed_by` varchar(100) DEFAULT NULL,
  `timestamp` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `description` text,
  `undone` tinyint(1) DEFAULT '0',
  `committed` tinyint(1) DEFAULT '0',
  `post_state_data` longtext,
  `undone_by` varchar(100) DEFAULT NULL,
  `undone_at` timestamp NULL DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `undo_token` (`undo_token`),
  KEY `idx_gus_ts` (`timestamp`),
  KEY `idx_gus_op` (`operation_type`)
) ENGINE=InnoDB AUTO_INCREMENT=1833 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `marks`
--

DROP TABLE IF EXISTS `marks`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `marks` (
  `id` int NOT NULL AUTO_INCREMENT,
  `usn` varchar(100) DEFAULT NULL,
  `semester` int NOT NULL,
  `sgpa` decimal(4,2) DEFAULT NULL,
  `cgpa` decimal(4,2) DEFAULT NULL,
  `year` int DEFAULT NULL,
  `extra_column` varchar(255) DEFAULT NULL,
  `name` varchar(255) DEFAULT NULL,
  `father_name` varchar(255) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_usn_sem` (`usn`,`semester`),
  KEY `idx_marks_semester` (`semester`),
  KEY `idx_marks_sgpa` (`sgpa`)
) ENGINE=InnoDB AUTO_INCREMENT=40747 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `password_reset_requests`
--

DROP TABLE IF EXISTS `password_reset_requests`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `password_reset_requests` (
  `id` int NOT NULL AUTO_INCREMENT,
  `user_id` int NOT NULL,
  `otp_hash` char(64) NOT NULL,
  `otp_created_at` datetime NOT NULL,
  `otp_expires_at` datetime NOT NULL,
  `otp_used_at` datetime DEFAULT NULL,
  `attempt_count` int NOT NULL DEFAULT '0',
  `reset_token_hash` char(64) DEFAULT NULL,
  `reset_token_expires_at` datetime DEFAULT NULL,
  `reset_token_used_at` datetime DEFAULT NULL,
  `created_ip` varchar(60) DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_prr_user` (`user_id`),
  KEY `idx_prr_otp` (`otp_hash`),
  KEY `idx_prr_reset_token` (`reset_token_hash`(32)),
  CONSTRAINT `password_reset_requests_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=26 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `password_reset_tokens`
--

DROP TABLE IF EXISTS `password_reset_tokens`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `password_reset_tokens` (
  `id` int NOT NULL AUTO_INCREMENT,
  `user_id` int NOT NULL,
  `token_hash` char(64) NOT NULL,
  `expires_at` datetime NOT NULL,
  `used` tinyint(1) DEFAULT '0',
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `otp_hash` char(64) DEFAULT NULL,
  `otp_created_at` datetime DEFAULT NULL,
  `otp_expires_at` datetime DEFAULT NULL,
  `otp_verified_at` datetime DEFAULT NULL,
  `otp_used_at` datetime DEFAULT NULL,
  `attempt_count` int NOT NULL DEFAULT '0',
  `purpose` varchar(40) NOT NULL DEFAULT 'PASSWORD_RESET',
  `reset_token_hash` char(64) DEFAULT NULL,
  `reset_token_expires_at` datetime DEFAULT NULL,
  `reset_token_used_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_reset_token_hash` (`token_hash`),
  KEY `idx_reset_user` (`user_id`),
  CONSTRAINT `password_reset_tokens_ibfk_1` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=12 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `query_cache`
--

DROP TABLE IF EXISTS `query_cache`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `query_cache` (
  `id` int NOT NULL AUTO_INCREMENT,
  `user_query` text NOT NULL,
  `query_hash` varchar(64) NOT NULL,
  `sql_query` text NOT NULL,
  `result_json` longtext,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `query_hash` (`query_hash`),
  KEY `idx_hash` (`query_hash`)
) ENGINE=InnoDB AUTO_INCREMENT=15 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `query_history`
--

DROP TABLE IF EXISTS `query_history`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `query_history` (
  `id` int NOT NULL AUTO_INCREMENT,
  `user_role` varchar(20) DEFAULT NULL,
  `natural_query` text NOT NULL,
  `generated_query` text,
  `execution_time` float DEFAULT NULL,
  `timestamp` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_qh_ts` (`timestamp`)
) ENGINE=InnoDB AUTO_INCREMENT=11922 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `readmission_requests`
--

DROP TABLE IF EXISTS `readmission_requests`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `readmission_requests` (
  `id` int NOT NULL AUTO_INCREMENT,
  `usn` varchar(100) NOT NULL,
  `requested_semester` int DEFAULT NULL,
  `request_date` date DEFAULT NULL,
  `scheme` varchar(40) DEFAULT NULL,
  `eligibility_outcome` varchar(60) DEFAULT NULL,
  `eligibility_flags` json DEFAULT NULL,
  `status` varchar(30) NOT NULL DEFAULT 'Requested',
  `approved_semester` int DEFAULT NULL,
  `approval_date` date DEFAULT NULL,
  `approval_ref` varchar(200) DEFAULT NULL,
  `rejoin_date` date DEFAULT NULL,
  `decided_by` varchar(100) DEFAULT NULL,
  `remarks` text,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_rr_usn` (`usn`),
  KEY `idx_rr_status` (`status`)
) ENGINE=InnoDB AUTO_INCREMENT=135 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `schema_metadata`
--

DROP TABLE IF EXISTS `schema_metadata`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `schema_metadata` (
  `id` int NOT NULL AUTO_INCREMENT,
  `table_name` varchar(100) NOT NULL,
  `column_name` varchar(100) NOT NULL,
  `data_type` varchar(50) NOT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `is_primary_key` tinyint(1) DEFAULT '0',
  `is_foreign_key` tinyint(1) DEFAULT '0',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_table_col` (`table_name`,`column_name`)
) ENGINE=InnoDB AUTO_INCREMENT=28336 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `security_logs`
--

DROP TABLE IF EXISTS `security_logs`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `security_logs` (
  `log_id` int NOT NULL AUTO_INCREMENT,
  `user_role` varchar(20) DEFAULT NULL,
  `attempted_query` text NOT NULL,
  `reason` text NOT NULL,
  `timestamp` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`log_id`)
) ENGINE=InnoDB AUTO_INCREMENT=177 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `semester_data`
--

DROP TABLE IF EXISTS `semester_data`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `semester_data` (
  `id` int NOT NULL AUTO_INCREMENT,
  `usn` varchar(50) NOT NULL,
  `semester` int NOT NULL,
  `sgpa` decimal(4,2) DEFAULT NULL,
  `cgpa` decimal(4,2) DEFAULT NULL,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_usn_sem` (`usn`,`semester`)
) ENGINE=InnoDB AUTO_INCREMENT=11 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `semester_gpa`
--

DROP TABLE IF EXISTS `semester_gpa`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `semester_gpa` (
  `id` int NOT NULL AUTO_INCREMENT,
  `student_id` int DEFAULT NULL,
  `semester` int NOT NULL,
  `sgpa` decimal(4,2) DEFAULT NULL,
  `cgpa` decimal(4,2) DEFAULT NULL,
  `year` int DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `student_id` (`student_id`),
  CONSTRAINT `semester_gpa_ibfk_1` FOREIGN KEY (`student_id`) REFERENCES `students` (`student_id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `soft_deleted_students`
--

DROP TABLE IF EXISTS `soft_deleted_students`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `soft_deleted_students` (
  `id` int NOT NULL AUTO_INCREMENT,
  `usn` varchar(100) NOT NULL,
  `student_json` longtext NOT NULL,
  `marks_json` longtext,
  `deleted_by` varchar(100) DEFAULT NULL,
  `deleted_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `restore_token` char(36) NOT NULL,
  `restored` tinyint(1) DEFAULT '0',
  PRIMARY KEY (`id`),
  KEY `idx_usn` (`usn`),
  KEY `idx_token` (`restore_token`)
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `student_backlogs`
--

DROP TABLE IF EXISTS `student_backlogs`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `student_backlogs` (
  `id` int NOT NULL AUTO_INCREMENT,
  `usn` varchar(100) NOT NULL,
  `subject` varchar(200) DEFAULT NULL,
  `semester` int DEFAULT NULL,
  `year` varchar(20) DEFAULT NULL,
  `raw_text` text,
  `cleared` tinyint(1) DEFAULT '0',
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_sb_usn` (`usn`),
  KEY `idx_sb_semester` (`semester`)
) ENGINE=InnoDB AUTO_INCREMENT=2007 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `student_fees`
--

DROP TABLE IF EXISTS `student_fees`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `student_fees` (
  `id` int NOT NULL AUTO_INCREMENT,
  `usn` varchar(100) NOT NULL,
  `fee_type` varchar(50) NOT NULL,
  `year` int DEFAULT NULL,
  `status` varchar(30) DEFAULT NULL,
  `amount_paid` varchar(100) DEFAULT NULL,
  `remaining_amount` varchar(100) DEFAULT NULL,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_usn_feetype_year` (`usn`,`fee_type`,`year`),
  KEY `idx_sf_usn` (`usn`)
) ENGINE=InnoDB AUTO_INCREMENT=4018 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `student_field_sources`
--

DROP TABLE IF EXISTS `student_field_sources`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `student_field_sources` (
  `id` int NOT NULL AUTO_INCREMENT,
  `usn` varchar(100) NOT NULL,
  `field_name` varchar(100) NOT NULL,
  `field_value` text,
  `source_filename` varchar(255) NOT NULL,
  `import_id` int DEFAULT NULL,
  `uploaded_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `is_active` tinyint(1) DEFAULT '1',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_sfs_usn_field_src` (`usn`,`field_name`,`source_filename`),
  KEY `idx_sfs_usn` (`usn`),
  KEY `idx_sfs_field` (`field_name`),
  KEY `idx_sfs_source` (`source_filename`),
  KEY `idx_sfs_active` (`is_active`)
) ENGINE=InnoDB AUTO_INCREMENT=30507 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `student_history`
--

DROP TABLE IF EXISTS `student_history`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `student_history` (
  `id` int NOT NULL AUTO_INCREMENT,
  `usn` varchar(100) NOT NULL,
  `field_name` varchar(100) DEFAULT NULL,
  `old_value` text,
  `new_value` text,
  `updated_by` varchar(100) DEFAULT NULL,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_usn` (`usn`)
) ENGINE=InnoDB AUTO_INCREMENT=154 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `student_identity_links`
--

DROP TABLE IF EXISTS `student_identity_links`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `student_identity_links` (
  `id` int NOT NULL AUTO_INCREMENT,
  `usn` varchar(100) NOT NULL,
  `related_usn` varchar(100) NOT NULL,
  `relation_type` varchar(40) NOT NULL,
  `note` varchar(500) DEFAULT NULL,
  `created_by` varchar(100) DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_link` (`usn`,`related_usn`,`relation_type`),
  KEY `idx_link_usn` (`usn`),
  KEY `idx_link_related` (`related_usn`)
) ENGINE=InnoDB AUTO_INCREMENT=649 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `student_lifecycle_events`
--

DROP TABLE IF EXISTS `student_lifecycle_events`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `student_lifecycle_events` (
  `id` int NOT NULL AUTO_INCREMENT,
  `usn` varchar(100) NOT NULL,
  `event_type` varchar(40) NOT NULL,
  `from_status` varchar(30) DEFAULT NULL,
  `to_status` varchar(30) NOT NULL,
  `effective_date` date DEFAULT NULL,
  `last_enrolled_semester` int DEFAULT NULL,
  `last_enrolled_academic_year` varchar(20) DEFAULT NULL,
  `requested_semester` int DEFAULT NULL,
  `approved_semester` int DEFAULT NULL,
  `request_date` date DEFAULT NULL,
  `approval_date` date DEFAULT NULL,
  `rejoin_date` date DEFAULT NULL,
  `scheme` varchar(40) DEFAULT NULL,
  `academic_year` varchar(20) DEFAULT NULL,
  `reason` varchar(500) DEFAULT NULL,
  `document_ref` varchar(500) DEFAULT NULL,
  `approval_ref` varchar(200) DEFAULT NULL,
  `remarks` text,
  `eligibility_flags` json DEFAULT NULL,
  `actor_username` varchar(100) DEFAULT NULL,
  `actor_role` varchar(20) DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `reason_category` varchar(40) DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_le_usn` (`usn`),
  KEY `idx_le_to_status` (`to_status`),
  KEY `idx_le_created` (`created_at`),
  KEY `idx_le_effective` (`effective_date`)
) ENGINE=InnoDB AUTO_INCREMENT=1140 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `student_lifecycle_status`
--

DROP TABLE IF EXISTS `student_lifecycle_status`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `student_lifecycle_status` (
  `usn` varchar(100) NOT NULL,
  `current_status` varchar(30) NOT NULL DEFAULT 'Active',
  `effective_date` date DEFAULT NULL,
  `last_enrolled_semester` int DEFAULT NULL,
  `last_enrolled_academic_year` varchar(20) DEFAULT NULL,
  `scheme` varchar(40) DEFAULT NULL,
  `reason` varchar(500) DEFAULT NULL,
  `document_ref` varchar(500) DEFAULT NULL,
  `updated_by` varchar(100) DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `reason_category` varchar(40) DEFAULT NULL,
  PRIMARY KEY (`usn`),
  KEY `idx_ls_status` (`current_status`),
  KEY `idx_ls_scheme` (`scheme`),
  KEY `idx_ls_effective` (`effective_date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `student_personal`
--

DROP TABLE IF EXISTS `student_personal`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `student_personal` (
  `id` int NOT NULL AUTO_INCREMENT,
  `student_id` int DEFAULT NULL,
  `father_name` varchar(100) DEFAULT NULL,
  `mother_name` varchar(100) DEFAULT NULL,
  `blood_group` varchar(10) DEFAULT NULL,
  `address` text,
  PRIMARY KEY (`id`),
  KEY `student_id` (`student_id`),
  CONSTRAINT `student_personal_ibfk_1` FOREIGN KEY (`student_id`) REFERENCES `students` (`student_id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `students`
--

DROP TABLE IF EXISTS `students`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `students` (
  `student_id` int NOT NULL AUTO_INCREMENT,
  `usn` varchar(100) DEFAULT NULL,
  `name` varchar(100) NOT NULL,
  `dob` date DEFAULT NULL,
  `year_of_joining` int DEFAULT NULL,
  `current_sem` int DEFAULT '0',
  `status` varchar(20) DEFAULT 'ACTIVE',
  `father_name` varchar(150) DEFAULT NULL,
  `mother_name` varchar(150) DEFAULT NULL,
  `blood_group` varchar(5) DEFAULT NULL,
  `address` text,
  `gender` varchar(10) DEFAULT NULL,
  `religion` varchar(50) DEFAULT NULL,
  `category` varchar(20) DEFAULT NULL,
  `email` varchar(255) DEFAULT NULL,
  `phone` varchar(20) DEFAULT NULL,
  `year_and_branch` varchar(100) DEFAULT NULL,
  `caste` varchar(100) DEFAULT NULL,
  `sub_caste` varchar(100) DEFAULT NULL,
  `permanent_address` text,
  `current_address` text,
  `aadhar_no` varchar(20) DEFAULT NULL,
  `source_file` varchar(255) DEFAULT NULL,
  `admission_year` int DEFAULT NULL,
  `current_year` int DEFAULT NULL,
  `student_type` varchar(50) DEFAULT NULL,
  `estimated_semester` int DEFAULT NULL,
  `branch` varchar(50) DEFAULT NULL,
  `division` varchar(50) DEFAULT NULL,
  `domain` varchar(100) DEFAULT NULL,
  `fld_3rd_sem_sgpa` decimal(4,2) DEFAULT NULL,
  `region` varchar(100) DEFAULT NULL,
  `village` varchar(100) DEFAULT NULL,
  `area_type` varchar(20) DEFAULT NULL,
  `area` varchar(100) DEFAULT NULL,
  `taluk` varchar(100) DEFAULT NULL,
  `district` varchar(100) DEFAULT NULL,
  `state` varchar(100) DEFAULT NULL,
  `extra_column` varchar(255) DEFAULT NULL,
  `cgpa` decimal(5,2) DEFAULT NULL,
  `emergency_contact_number` varchar(20) DEFAULT NULL,
  `dynamic_data` json DEFAULT NULL,
  `father_occupation` varchar(100) DEFAULT NULL,
  `mother_occupation` varchar(100) DEFAULT NULL,
  `parents_phone` varchar(20) DEFAULT NULL,
  `hk_status` varchar(20) DEFAULT NULL,
  `quota` varchar(100) DEFAULT NULL,
  `distance_from_college` varchar(50) DEFAULT NULL,
  `kannada_medium` varchar(10) DEFAULT NULL,
  `physically_handicapped` varchar(10) DEFAULT NULL,
  `pin_code` varchar(10) DEFAULT NULL,
  `post_office` varchar(100) DEFAULT NULL,
  `backlogs` text,
  `snq_quota` varchar(10) DEFAULT NULL,
  `lifecycle_status` varchar(30) NOT NULL DEFAULT 'Active',
  `usn_provisional` tinyint(1) NOT NULL DEFAULT '0',
  PRIMARY KEY (`student_id`),
  UNIQUE KEY `usn` (`usn`),
  KEY `idx_stu_name` (`name`(50)),
  KEY `idx_stu_status` (`status`),
  KEY `idx_stu_yr_joining` (`year_of_joining`),
  KEY `idx_stu_adm_year` (`admission_year`),
  KEY `idx_stu_cur_sem` (`current_sem`)
) ENGINE=InnoDB AUTO_INCREMENT=11542 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `students_dynamic`
--

DROP TABLE IF EXISTS `students_dynamic`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `students_dynamic` (
  `id` int NOT NULL AUTO_INCREMENT,
  `usn` varchar(50) NOT NULL,
  `name` varchar(150) DEFAULT NULL,
  `email` varchar(150) DEFAULT NULL,
  `phone` varchar(20) DEFAULT NULL,
  `branch` varchar(100) DEFAULT NULL,
  `department` varchar(100) DEFAULT NULL,
  `semester` int DEFAULT NULL,
  `cgpa` decimal(4,2) DEFAULT NULL,
  `sgpa` decimal(4,2) DEFAULT NULL,
  `status` varchar(30) DEFAULT NULL,
  `gender` varchar(10) DEFAULT NULL,
  `batch` varchar(20) DEFAULT NULL,
  `section` varchar(10) DEFAULT NULL,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `unnamed_2` varchar(150) DEFAULT NULL,
  `1st_sem` text,
  `2nd_sem` text,
  `3rd_sem` text,
  `4th_sem` text,
  `5th_sem` text,
  `unnamed_3` varchar(150) DEFAULT NULL,
  `unnamed_4` varchar(150) DEFAULT NULL,
  `unnamed_6` varchar(150) DEFAULT NULL,
  `unnamed_7` varchar(150) DEFAULT NULL,
  `unnamed_9` varchar(150) DEFAULT NULL,
  `unnamed_10` varchar(150) DEFAULT NULL,
  `unnamed_12` varchar(150) DEFAULT NULL,
  `unnamed_13` varchar(150) DEFAULT NULL,
  `unnamed_15` varchar(150) DEFAULT NULL,
  `unnamed_16` varchar(150) DEFAULT NULL,
  `unnamed_18` varchar(150) DEFAULT NULL,
  `unnamed_19` varchar(150) DEFAULT NULL,
  `unnamed_20` varchar(150) DEFAULT NULL,
  `unnamed_21` varchar(150) DEFAULT NULL,
  `unnamed_22` varchar(150) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_usn` (`usn`)
) ENGINE=InnoDB AUTO_INCREMENT=271 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `upload_versions`
--

DROP TABLE IF EXISTS `upload_versions`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `upload_versions` (
  `id` int NOT NULL AUTO_INCREMENT,
  `filename` varchar(255) DEFAULT NULL,
  `rows_parsed` int DEFAULT '0',
  `students_added` int DEFAULT '0',
  `students_updated` int DEFAULT '0',
  `students_unchanged` int DEFAULT '0',
  `marks_added` int DEFAULT '0',
  `marks_updated` int DEFAULT '0',
  `skipped_rows` int DEFAULT '0',
  `status` enum('success','failed','rolled_back') DEFAULT 'success',
  `undo_token` varchar(100) DEFAULT NULL,
  `performed_by` varchar(100) DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `error_message` text,
  PRIMARY KEY (`id`),
  KEY `idx_uv_created_at` (`created_at`),
  KEY `idx_uv_status` (`status`)
) ENGINE=InnoDB AUTO_INCREMENT=124 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `uploaded_data`
--

DROP TABLE IF EXISTS `uploaded_data`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `uploaded_data` (
  `id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(255) DEFAULT NULL,
  `usn` varchar(255) DEFAULT NULL,
  `semesterone` varchar(255) DEFAULT NULL,
  `semestertwo` varchar(255) DEFAULT NULL,
  `semesterthree` varchar(255) DEFAULT NULL,
  `semesterfour` varchar(255) DEFAULT NULL,
  `semesterfive` varchar(255) DEFAULT NULL,
  `source_file` varchar(255) DEFAULT NULL,
  `unnamed3` varchar(255) DEFAULT NULL,
  `unnamed4` varchar(255) DEFAULT NULL,
  `unnamed6` varchar(255) DEFAULT NULL,
  `unnamed7` varchar(255) DEFAULT NULL,
  `unnamed9` varchar(255) DEFAULT NULL,
  `unnamed10` varchar(255) DEFAULT NULL,
  `unnamed12` varchar(255) DEFAULT NULL,
  `unnamed13` varchar(255) DEFAULT NULL,
  `unnamed15` varchar(255) DEFAULT NULL,
  `unnamed16` varchar(255) DEFAULT NULL,
  `cgpa` varchar(255) DEFAULT NULL,
  `unnamed18` varchar(255) DEFAULT NULL,
  `unnamed21` varchar(255) DEFAULT NULL,
  `unnamed22` varchar(255) DEFAULT NULL,
  `mathematics` varchar(255) DEFAULT NULL,
  `grade` varchar(255) DEFAULT NULL,
  `gradecredit` varchar(255) DEFAULT NULL,
  `physics` varchar(255) DEFAULT NULL,
  `mathematicsgrade` varchar(255) DEFAULT NULL,
  `mathematicsgradecredit` varchar(255) DEFAULT NULL,
  `programmingusingc` varchar(255) DEFAULT NULL,
  `physicsgrade` varchar(255) DEFAULT NULL,
  `physicsgradecredit` varchar(255) DEFAULT NULL,
  `communicativeenglish` varchar(255) DEFAULT NULL,
  `programmingusingcgrade` varchar(255) DEFAULT NULL,
  `programmingusingcgradecredit` varchar(255) DEFAULT NULL,
  `samskrutikakannada` varchar(255) DEFAULT NULL,
  `communicativeenglishgrade` varchar(255) DEFAULT NULL,
  `communicativeenglishgradecredit` varchar(255) DEFAULT NULL,
  `innovationanddesignthinking` varchar(255) DEFAULT NULL,
  `samskrutikakannadagrade` varchar(255) DEFAULT NULL,
  `samskrutikakannadagradecredit` varchar(255) DEFAULT NULL,
  `electronicsengineering` varchar(255) DEFAULT NULL,
  `innovationanddesignthinkinggrade` varchar(255) DEFAULT NULL,
  `innovationanddesignthinkinggradecredit` varchar(255) DEFAULT NULL,
  `cybersecurity` varchar(255) DEFAULT NULL,
  `electronicsengineeringgrade` varchar(255) DEFAULT NULL,
  `electronicsengineeringgradecredit` varchar(255) DEFAULT NULL,
  `total` varchar(255) DEFAULT NULL,
  `sgpa` varchar(255) DEFAULT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=382 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `uploaded_files`
--

DROP TABLE IF EXISTS `uploaded_files`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `uploaded_files` (
  `id` int NOT NULL AUTO_INCREMENT,
  `filename` varchar(255) DEFAULT NULL,
  `content_type` varchar(100) DEFAULT NULL,
  `file_type` varchar(20) DEFAULT NULL,
  `size_bytes` int DEFAULT NULL,
  `uploaded_by` varchar(50) DEFAULT NULL,
  `uploaded_at` datetime DEFAULT NULL,
  `db_status` varchar(20) DEFAULT NULL,
  `row_count` int DEFAULT NULL,
  `gpa_rows` int DEFAULT NULL,
  `students_saved` int DEFAULT NULL,
  `marks_saved` int DEFAULT NULL,
  `trashed_at` datetime DEFAULT NULL,
  `trash_path` varchar(512) DEFAULT NULL,
  `trash_undo_token` varchar(36) DEFAULT NULL,
  `data_reconciled_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `filename` (`filename`)
) ENGINE=InnoDB AUTO_INCREMENT=133 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `users`
--

DROP TABLE IF EXISTS `users`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `users` (
  `id` int NOT NULL AUTO_INCREMENT,
  `username` varchar(50) NOT NULL,
  `email` varchar(100) NOT NULL,
  `password_hash` varchar(255) NOT NULL,
  `role` varchar(20) NOT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `theme` varchar(20) DEFAULT 'system',
  PRIMARY KEY (`id`),
  UNIQUE KEY `username` (`username`),
  UNIQUE KEY `email` (`email`)
) ENGINE=InnoDB AUTO_INCREMENT=18 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `users_old_backup`
--

DROP TABLE IF EXISTS `users_old_backup`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `users_old_backup` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `name` varchar(255) NOT NULL DEFAULT '',
  `username` varchar(50) NOT NULL,
  `email` varchar(100) NOT NULL,
  `password_hash` varchar(255) NOT NULL,
  `role` varchar(20) NOT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `id` (`id`),
  UNIQUE KEY `username` (`username`),
  UNIQUE KEY `email` (`email`),
  CONSTRAINT `users_old_backup_chk_1` CHECK ((`role` in (_utf8mb4'Admin',_utf8mb4'Staff')))
) ENGINE=InnoDB AUTO_INCREMENT=3 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `validation_log`
--

DROP TABLE IF EXISTS `validation_log`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `validation_log` (
  `id` int NOT NULL AUTO_INCREMENT,
  `usn` varchar(50) DEFAULT NULL,
  `field_name` varchar(100) DEFAULT NULL,
  `issue` varchar(255) DEFAULT NULL,
  `raw_value` text,
  `logged_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=84 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `vtu_scheme_rules`
--

DROP TABLE IF EXISTS `vtu_scheme_rules`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `vtu_scheme_rules` (
  `id` int NOT NULL AUTO_INCREMENT,
  `scheme_code` varchar(40) NOT NULL,
  `admission_category` varchar(30) NOT NULL DEFAULT '',
  `rule_key` varchar(80) NOT NULL,
  `rule_value` varchar(255) DEFAULT NULL,
  `source_url` varchar(500) DEFAULT NULL,
  `clause_ref` varchar(255) DEFAULT NULL,
  `effective_date` date DEFAULT NULL,
  `verification_status` varchar(30) NOT NULL DEFAULT 'pending',
  `applies_from_batch` int DEFAULT NULL,
  `applies_to_batch` int DEFAULT NULL,
  `notes` text,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_rule` (`scheme_code`,`admission_category`,`rule_key`),
  KEY `idx_rule_scheme` (`scheme_code`),
  KEY `idx_rule_verify` (`verification_status`)
) ENGINE=InnoDB AUTO_INCREMENT=1165 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping routines for database 'student_db'
--
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

-- Dump completed on 2026-10-11 14:13:19
