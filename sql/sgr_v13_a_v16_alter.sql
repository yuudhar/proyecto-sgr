ALTER TABLE `evidence_validation`
  MODIFY `reviewer_officer_id` bigint(20) NULL;

ALTER TABLE `accounts_userprofile`
  ADD COLUMN `photo` varchar(255) NULL;
