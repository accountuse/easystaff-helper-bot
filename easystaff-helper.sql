CREATE DATABASE IF NOT EXISTS `easystaff_helper` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS 'easystaff_helper'@'127.0.0.1' IDENTIFIED BY '1234';
CREATE USER IF NOT EXISTS 'easystaff_helper'@'172.23.%' IDENTIFIED BY '1234';
GRANT SELECT,INSERT,UPDATE,DELETE,CREATE,ALTER,INDEX ON `easystaff_helper`.* TO 'easystaff_helper'@'127.0.0.1';
GRANT SELECT,INSERT,UPDATE,DELETE,CREATE,ALTER,INDEX ON `easystaff_helper`.* TO 'easystaff_helper'@'172.23.%';
FLUSH PRIVILEGES;

USE `easystaff_helper`;

CREATE TABLE IF NOT EXISTS users (
  user_id BIGINT UNSIGNED PRIMARY KEY,
  username VARCHAR(64),
  first_name VARCHAR(64),
  last_name VARCHAR(64),
  first_usage DATETIME NOT NULL,
  last_usage DATETIME NOT NULL,
  KEY idx_users_username (username)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS user_stats (
  id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
  user_id BIGINT UNSIGNED NOT NULL,
  usage_datetime DATETIME NOT NULL,
  KEY idx_user_stats_user_id (user_id),
  CONSTRAINT fk_user_stats_user FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
