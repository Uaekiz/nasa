-- Read-only inspection; run from an idle administrative psql prompt.
\set ON_ERROR_STOP on
\set ECHO none
\set AUTOCOMMIT on

SELECT current_database() AS connected_database, current_user AS connected_role;
SELECT datname, pg_get_userbyid(datdba) AS database_owner
  FROM pg_database WHERE datname = 'pyrosphere_rag';
SELECT rolname, rolcanlogin, rolsuper, rolcreatedb, rolcreaterole,
  rolpassword IS NOT NULL AS has_password
  FROM pg_authid WHERE rolname = 'pyrosphere_rag_app';
SELECT name, default_version FROM pg_available_extensions WHERE name = 'vector';

SELECT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'pyrosphere_rag') AS rag_inspect_database_exists \gset
\if :rag_inspect_database_exists
  \connect pyrosphere_rag
  SELECT nspname, pg_get_userbyid(nspowner) AS schema_owner,
    obj_description(oid, 'pg_namespace') AS schema_marker
    FROM pg_namespace WHERE nspname = 'rag';
  SELECT schemaname, tablename, tableowner FROM pg_tables
    WHERE schemaname = 'rag' ORDER BY tablename;
  SELECT e.extname, e.extversion, n.nspname AS extension_schema
    FROM pg_extension e JOIN pg_namespace n ON n.oid = e.extnamespace
    WHERE e.extname = 'vector';
  \connect postgres
\else
  \echo 'Target database is absent; it has no schema or extension to inspect yet.'
\endif
\echo 'Inspection finished. No roles, passwords, databases, schemas, or tables were changed.'
