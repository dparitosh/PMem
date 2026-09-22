-- First installation only. Run interactively as the PostgreSQL administrator.
-- Existing objects cause a failure; this never resets an existing role/password.
\set ON_ERROR_STOP on
SET password_encryption = 'scram-sha-256';
CREATE ROLE depo_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;
\password depo_app
CREATE DATABASE depo OWNER depo_app;
REVOKE ALL ON DATABASE depo FROM PUBLIC;
\connect depo
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
CREATE SCHEMA semantic AUTHORIZATION depo_app;
GRANT CONNECT ON DATABASE depo TO depo_app;
