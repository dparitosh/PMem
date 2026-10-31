-- Run with psql as the PostgreSQL administrator:
-- psql -U postgres -v depo_role=depo_app -f create-depo-test-database.sql
-- Reuses an existing role; never changes its password or production grants.
\set ON_ERROR_STOP on
\if :{?depo_role}
\else
  \echo 'ERROR: pass -v depo_role=<existing-application-role>'
  \quit 3
\endif

-- Existing database causes a failure rather than overwriting test data.
CREATE DATABASE depo_acceptance_test;
REVOKE ALL ON DATABASE depo_acceptance_test FROM PUBLIC;
GRANT CONNECT, CREATE ON DATABASE depo_acceptance_test TO :"depo_role";
\connect depo_acceptance_test
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
\echo 'Test database provisioned. Set DEPO_TEST_DATABASE_URL privately to this database and run test_xml_analytics_postgres.py.'
\echo 'The integration test creates unique schemas and rolls back its objects.'
