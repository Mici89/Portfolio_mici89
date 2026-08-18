-- The Docker image initially grants MYSQL_USER full access to MYSQL_DATABASE.
-- Reduce the benchmark account to read-only after all seed data has loaded.
REVOKE ALL PRIVILEGES, GRANT OPTION FROM 'ai_reader'@'%';
GRANT SELECT, SHOW VIEW ON legacy_enterprise.* TO 'ai_reader'@'%';

CREATE USER IF NOT EXISTS 'ai_writer'@'%'
IDENTIFIED BY 'local_writer_ChangeMe_2026';
GRANT SELECT, INSERT, UPDATE, DELETE ON legacy_enterprise.* TO 'ai_writer'@'%';
FLUSH PRIVILEGES;
