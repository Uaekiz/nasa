-- Run in the existing PostgreSQL instance as its known administrative user.
-- Never run this file with an application connection or with psql --echo-all.
-- Start at an idle prompt such as postgres=#, outside any caller transaction.
\set ON_ERROR_STOP on
\set ECHO none
\set AUTOCOMMIT on

-- Initialize state on every retry; never reuse a previous psql variable value.
\set rag_new_password_set false

\echo 'Current RAG object inventory before provisioning:'
SELECT datname AS existing_database FROM pg_database WHERE datname = 'pyrosphere_rag';
SELECT rolname AS existing_application_role, rolcanlogin,
  rolpassword IS NOT NULL AS has_password
  FROM pg_authid WHERE rolname = 'pyrosphere_rag_app';

SELECT current_user AS administrative_role, current_database() AS maintenance_database;
SELECT rolsuper AS rag_is_admin FROM pg_roles WHERE rolname = current_user \gset
\if :rag_is_admin
\else
  \echo 'Provisioning requires an administrative session. No credentials were guessed.'
  \quit 3
\endif

SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pyrosphere_rag_app') AS rag_role_exists \gset
\if :rag_role_exists
  \echo 'Application role already exists; its password and attributes will not be changed.'
\else
  -- A client-side password mismatch must not abort the file before ROLLBACK.
  -- The following block is the only place where ON_ERROR_STOP is disabled.
  \set ON_ERROR_STOP off
  BEGIN;
  CREATE ROLE pyrosphere_rag_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS;
  \echo 'Choose a NEW application-role password at the hidden prompts. This is not the administrator password.'
  \password pyrosphere_rag_app
  SELECT rolpassword IS NOT NULL AS rag_new_password_set FROM pg_authid WHERE rolname = 'pyrosphere_rag_app' \gset
  \if :rag_new_password_set
    COMMIT;
  \else
    ROLLBACK;
  \endif
  \set ON_ERROR_STOP on
  \if :rag_new_password_set
    \echo 'New application role and initial password were committed.'
  \else
    -- Raise only after rollback, so an interactive caller keeps an idle prompt.
    DO $rag_password_failure$
    BEGIN
      RAISE EXCEPTION 'Application password setup failed or did not match. New role creation was rolled back; database creation was not attempted. Retry the script.';
    END
    $rag_password_failure$;
  \endif
\endif

SELECT EXISTS (
  SELECT 1 FROM pg_authid WHERE rolname = 'pyrosphere_rag_app'
  AND rolcanlogin AND rolpassword IS NOT NULL
  AND NOT (rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls)
) AS rag_app_role_compatible \gset
\if :rag_app_role_compatible
\else
  \echo 'The existing application role is incompatible or has no password. Its attributes and password were preserved; administrative review is required.'
  \quit 3
\endif

-- The role transaction above has ended on every path that reaches this phase.
-- AUTOCOMMIT prevents psql from issuing an implicit BEGIN before CREATE DATABASE.
\set AUTOCOMMIT on
SELECT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'pyrosphere_rag') AS rag_database_exists \gset
\if :rag_database_exists
  \echo 'Database already exists; ownership, settings, and tables will not be changed.'
\else
  -- The administrative creator owns the database. The application owns only its schema.
  CREATE DATABASE pyrosphere_rag;
\endif

SELECT has_database_privilege('pyrosphere_rag_app', 'pyrosphere_rag', 'CONNECT') AS rag_can_connect \gset
\if :rag_can_connect
\else
  \echo 'The application role lacks CONNECT on the existing database. No existing database privileges were changed.'
  \quit 3
\endif

\connect pyrosphere_rag
SELECT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'rag') AS rag_schema_exists \gset
\if :rag_schema_exists
  SELECT pg_get_userbyid(nspowner) = 'pyrosphere_rag_app'
    AND obj_description(oid, 'pg_namespace') IS NOT DISTINCT FROM 'PyroSphere RAG evidence store; schema version 1'
    AS rag_schema_compatible FROM pg_namespace WHERE nspname = 'rag' \gset
  \if :rag_schema_compatible
    \echo 'The existing marked application schema is compatible and was preserved.'
  \else
    \echo 'The existing rag schema is unmarked or has a different owner. It was not adopted or altered.'
    \quit 3
  \endif
\else
  BEGIN;
  CREATE SCHEMA rag AUTHORIZATION pyrosphere_rag_app;
  COMMENT ON SCHEMA rag IS 'PyroSphere RAG evidence store; schema version 1';
  COMMIT;
\endif

SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector') AS rag_vector_installed \gset
\if :rag_vector_installed
  \echo 'The pgvector extension already exists and was preserved in its current schema.'
\else
  SELECT EXISTS (SELECT 1 FROM pg_available_extensions WHERE name = 'vector') AS rag_vector_available \gset
  \if :rag_vector_available
    CREATE EXTENSION vector WITH SCHEMA public;
  \else
    \echo 'pgvector server files are unavailable. Install a build matching this Windows PostgreSQL 18 server, then rerun this script.'
  \endif
\endif

SELECT current_database() AS target_database,
  has_schema_privilege('pyrosphere_rag_app', 'rag', 'USAGE') AS app_schema_usage,
  has_schema_privilege('pyrosphere_rag_app', 'rag', 'CREATE') AS app_schema_create;
SELECT extname, extversion FROM pg_extension WHERE extname = 'vector';
\echo 'Next: quit psql and run the application configuration command. The administrator connection is not used by indexing.'
