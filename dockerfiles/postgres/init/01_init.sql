-- 01_init.sql
-- Runs automatically on first container start.
-- Creates the separate metadata database that Superset needs.

-- Create superset metadata database (the main dataplatform DB is
-- already created by POSTGRES_DB env var).
-- NOTE: 02_mta.sql (mounted from ./database/mta.sql) creates the MTA tables.
SELECT 'CREATE DATABASE superset'
  WHERE NOT EXISTS (
    SELECT FROM pg_database WHERE datname = 'superset'
  )\gexec

-- No explicit GRANT needed: the POSTGRES_USER that runs init scripts
-- is already the owner/superuser of both databases.
