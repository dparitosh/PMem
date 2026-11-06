-- First installation only. Run interactively as the PostgreSQL administrator:
-- psql -U postgres -v depo_role=depo_app -v depo_database=depo -v depo_schema=semantic -f create-depo-database.sql
-- Existing objects cause a failure; this never resets an existing role/password.
\set ON_ERROR_STOP on
SET password_encryption = 'scram-sha-256';

\if :{?depo_role}
\else
  \echo 'ERROR: pass -v depo_role=<application-role>'
  \quit 3
\endif
\if :{?depo_database}
\else
  \echo 'ERROR: pass -v depo_database=<database-name>'
  \quit 3
\endif
\if :{?depo_schema}
\else
  \echo 'ERROR: pass -v depo_schema=<schema-name>'
  \quit 3
\endif

CREATE ROLE :"depo_role" LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;
\password :"depo_role"
-- Keep database ownership with the administrator. DEPO owns only its
-- dedicated application schema and cannot administer the whole database.
CREATE DATABASE :"depo_database";
REVOKE ALL ON DATABASE :"depo_database" FROM PUBLIC;
\connect :"depo_database"
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
CREATE SCHEMA :"depo_schema" AUTHORIZATION :"depo_role";
GRANT CONNECT ON DATABASE :"depo_database" TO :"depo_role";
