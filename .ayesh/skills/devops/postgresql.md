---
name: postgresql
description: "Manajemen database PostgreSQL. Trigger: /postgresql"
---

# PostgreSQL Database Management

## Koneksi
```bash
psql -U postgres
psql -U username -d database
psql -h hostname -p 5432 -U username -d database
psql -U username -d database -f script.sql
psql -U username -d database -c "SELECT version();"
```

### psql Commands
```
\l              -- list databases
\c dbname       -- switch database
\dt             -- list tables
\d tablename    -- table structure
\du             -- list users
\dn             -- list schemas
\df             -- list functions
\di             -- list indexes
\q              -- exit
\timing         -- show execution time
\x              -- extended display
```

## User & Permission
```sql
CREATE USER username WITH PASSWORD 'password';
CREATE ROLE username WITH LOGIN PASSWORD 'password';
CREATE USER admin WITH SUPERUSER PASSWORD 'password';

GRANT ALL PRIVILEGES ON DATABASE dbname TO username;
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA public TO username;
GRANT USAGE ON SCHEMA schema_name TO username;

ALTER DEFAULT PRIVILEGES IN SCHEMA public
GRANT SELECT ON TABLES TO readonly_user;

\du username
SELECT * FROM information_schema.role_table_grants WHERE grantee = 'username';
ALTER USER username WITH PASSWORD 'newpassword';
```

## Database Operations
```sql
CREATE DATABASE dbname;
CREATE DATABASE dbname OWNER username ENCODING 'UTF8';
DROP DATABASE dbname;

SELECT pg_database.datname, pg_size_pretty(pg_database_size(pg_database.datname))
FROM pg_database ORDER BY pg_database_size(pg_database.datname) DESC;

SELECT relname, pg_size_pretty(pg_total_relation_size(relid))
FROM pg_catalog.pg_statio_user_tables ORDER BY pg_total_relation_size(relid) DESC;
```

## Backup & Restore
```bash
# pg_dump
pg_dump -U username dbname > backup.sql
pg_dump -U username -Fc dbname > backup.dump
pg_dumpall -U postgres > all_backup.sql
pg_dump -U username --schema-only dbname > schema.sql
pg_dump -U username --data-only dbname > data.sql
pg_dump -U username -t tablename dbname > table.sql
pg_dump -U username -Fd -j 4 dbname -f backup_dir/

# Restore
psql -U username -d dbname < backup.sql
pg_restore -U username -d dbname backup.dump
pg_restore -U username -d dbname -j 4 backup_dir/
```

## Performance Monitoring
```sql
SELECT * FROM pg_stat_activity;
SELECT pid, usename, application_name, state, query
FROM pg_stat_activity WHERE state != 'idle';
SELECT pg_terminate_backend(pid);
SELECT * FROM pg_locks WHERE NOT granted;

SELECT relname, seq_scan, idx_scan, n_tup_ins, n_tup_upd, n_tup_del
FROM pg_stat_user_tables;

SELECT indexrelname, idx_scan, idx_tup_read, idx_tup_fetch
FROM pg_stat_user_indexes;
```

## Query Optimization
```sql
EXPLAIN SELECT * FROM table WHERE condition;
EXPLAIN ANALYZE SELECT * FROM table WHERE condition;
EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT) SELECT * FROM table;

ANALYZE tablename;
REINDEX TABLE tablename;
REINDEX DATABASE dbname;
VACUUM tablename;
VACUUM FULL tablename;
VACUUM ANALYZE tablename;
```

## Slow Query Analysis
```sql
CREATE EXTENSION pg_stat_statements;

SELECT query, calls, total_time, mean_time, rows
FROM pg_stat_statements
ORDER BY total_time DESC LIMIT 10;

SELECT pg_stat_statements_reset();
```

## Table Maintenance
```sql
SELECT schemaname, relname, n_dead_tup, n_live_tup,
       round(n_dead_tup * 100.0 / nullif(n_live_tup + n_dead_tup, 0), 2) AS dead_ratio
FROM pg_stat_user_tables
WHERE n_dead_tup > 1000
ORDER BY n_dead_tup DESC;
```

## Troubleshooting
| Masalah | Solusi |
|---------|--------|
| Koneksi terlalu banyak | `pg_stat_activity`, cek max_connections |
| Query lambat | `EXPLAIN ANALYZE`, cek index |
| Lock waiting | `pg_locks`, `pg_stat_activity` |
| Disk penuh | Cek WAL, bersihkan data lama |
| Replikasi delay | `pg_stat_replication` |
