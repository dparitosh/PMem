-- Optional analytics capability for an existing deployment.
-- Run as database owner with psql connected to the DEPO application database:
-- psql -U postgres -d depo -v depo_role=depo_app -f enable-depo-analytics.sql
-- Review first: CREATE permits this role to create schemas in this database.
-- It does not grant superuser, role administration or database creation.
\set ON_ERROR_STOP on
\if :{?depo_role}
\else
  \echo 'ERROR: pass -v depo_role=<existing-application-role>'
  \quit 3
\endif
BEGIN;
SELECT current_database() AS depo_database \gset
GRANT CREATE ON DATABASE :"depo_database" TO :"depo_role";
COMMIT;
