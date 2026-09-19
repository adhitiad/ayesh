---
name: mysql
description: "Manajemen database MySQL/MariaDB. Trigger: /mysql"
---

# MySQL Database Management

## Koneksi
```bash
mysql -u root -p
mysql -h hostname -P 3306 -u user -p database
mysql -u user -p database < script.sql
mysql -u user -p -e "SHOW DATABASES;"
```

## User & Permission
```sql
SELECT user, host FROM mysql.user;
CREATE USER 'username'@'%' IDENTIFIED BY 'password';
GRANT ALL PRIVILEGES ON database.* TO 'username'@'%';
GRANT SELECT, INSERT ON database.table TO 'username'@'%';
FLUSH PRIVILEGES;
SHOW GRANTS FOR 'username'@'%';
```

## Database Operations
```sql
SHOW DATABASES;
CREATE DATABASE dbname CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
DROP DATABASE dbname;
USE dbname;
SHOW TABLES;
DESCRIBE tablename;
SHOW CREATE TABLE tablename;
```

## Backup & Restore
```bash
mysqldump -u root -p database > backup.sql
mysqldump -u root -p --all-databases > all_backup.sql
mysqldump -u root -p --no-data database > schema.sql
mysqldump -u root -p database | gzip > backup.sql.gz

mysql -u root -p database < backup.sql
gunzip < backup.sql.gz | mysql -u root -p database
```

## Performance Monitoring
```sql
SHOW PROCESSLIST;
SHOW FULL PROCESSLIST;
SHOW STATUS;
SHOW GLOBAL STATUS LIKE 'Threads%';
SHOW GLOBAL STATUS LIKE 'Connections';
SHOW VARIABLES LIKE 'max_connections';
SHOW VARIABLES LIKE '%buffer%';
SHOW VARIABLES LIKE 'slow_query%';
SHOW GLOBAL STATUS LIKE 'Slow_queries';
```

## Slow Query
```sql
SET GLOBAL slow_query_log = 'ON';
SET GLOBAL long_query_time = 1;
SHOW VARIABLES LIKE 'slow_query_log_file';
EXPLAIN SELECT * FROM table WHERE condition;
EXPLAIN ANALYZE SELECT * FROM table WHERE condition;
```

## Lock Debugging
```sql
SHOW ENGINE INNODB STATUS\G
SELECT * FROM information_schema.INNODB_LOCKS;
SELECT * FROM information_schema.INNODB_LOCK_WAITS;
SELECT * FROM information_schema.INNODB_TRX;
```

## Replication
```sql
SHOW MASTER STATUS;
SHOW SLAVE STATUS\G
-- Slave_IO_Running: Yes
-- Slave_SQL_Running: Yes
-- Seconds_Behind_Master: 0
```

## Troubleshooting
| Masalah | Solusi |
|---------|--------|
| Koneksi terlalu banyak | `SHOW PROCESSLIST`, cek max_connections |
| Query lambat | `EXPLAIN`, cek index |
| Lock waiting | `SHOW ENGINE INNODB STATUS` |
| Replikasi delay | `SHOW SLAVE STATUS`, cek network |
| Disk penuh | Cek binlog, bersihkan log lama |
