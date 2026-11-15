# Set up the existing local RAG database

The detected instance is native Windows PostgreSQL 18.0, service
`postgresql-x64-18`, with installation root
`C:\Program Files\PostgreSQL\18`, data directory `C:\PostgreSQL\data`, and
port 5432. Its localhost authentication rules require SCRAM passwords. The
saved pgAdmin registration uses administrative user `postgres`, maintenance
database `postgres`, and host `localhost`. No usable libpq password/service file
or database environment credentials were found during inspection.

The required target is database `pyrosphere_rag`, application role
`pyrosphere_rag_app`, and schema `rag`. No database/role existence claims can be
made before authentication. Nothing in this procedure resets a password,
changes authentication rules, replaces the server, or deletes existing objects.

## 1. Enter the administrator password locally

Run this exact command in your own PowerShell terminal:

```powershell
& 'C:\Program Files\PostgreSQL\18\bin\psql.exe' -X -h localhost -p 5432 -U postgres -d postgres -W
```

Enter the existing password for the registered administrative connection at
the hidden prompt. Do not put it in command arguments, paste it into chat, or
change an existing role's password. If the password is unknown, obtain it from
the person who installed/manages this instance. No password guessing or reset
procedure is used here.

These read-only queries reveal whether objects already exist and whether the
server can make pgvector available:

```sql
SELECT datname FROM pg_database WHERE datname = 'pyrosphere_rag';
SELECT rolname FROM pg_roles WHERE rolname = 'pyrosphere_rag_app';
SELECT name, default_version FROM pg_available_extensions WHERE name = 'vector';
```

For a complete read-only inventory, including the target schema, its tables,
and installed vector extension when the database exists, run:

```sql
\i 'C:/NASA/nasa/rag-service/scripts/inspect_local.sql'
```

It shows only whether the application role has a password, never the password
or its stored verifier. It returns to maintenance database `postgres`.

## 2. Create only missing objects

Inside that administrative `psql` session:

```sql
\i 'C:/NASA/nasa/rag-service/scripts/provision_local.sql'
```

The script checks existence before creation and uses `ON_ERROR_STOP`:

- A new application role has LOGIN but no superuser, CREATEDB, CREATEROLE,
  replication, or BYPASSRLS attributes. Its initial password is entered through
  hidden `\password` prompts inside the new-role transaction. Creation is rolled
  back if no initial password is set or the two entries do not match. During
  this block only, `ON_ERROR_STOP` is disabled so a client-side mismatch cannot
  skip cleanup. After rollback, the script raises an error and stops before
  database creation. Existing role passwords/attributes are
  preserved; an incompatible existing role is reported rather than altered.
- A missing database is created with the administrator as its owner. Ownership,
  settings and tables in an existing database are preserved. If its existing
  access policy denies the application CONNECT, the script stops for review
  instead of changing that policy.
- A missing `rag` schema is created with `pyrosphere_rag_app` as owner and the
  application's schema marker. An existing schema must already have the same
  owner and marker; an unknown schema is never adopted, cleared or reset.
- An installed vector extension is left in its existing namespace. If absent
  but available, it is created in this target database. If server files are
  missing, that limitation is reported and the other newly provisioned objects
  remain available for the next step.

Do not run the script with `psql --echo-all` or log hidden password input. An
administrator is used only for provisioning; normal data access rejects it.
Run from an idle prompt such as `postgres=#`, not `postgres=*#` or `postgres=!#`.
The script explicitly enables AUTOCOMMIT. Its role transaction is committed or
rolled back before the standalone `CREATE DATABASE` phase; database creation
is never placed inside an explicit transaction. A manual ROLLBACK warning that
no transaction is in progress does not prove that earlier objects are absent;
inspect the current catalogs before drawing that conclusion.

The opt-in native provisioning regression sets `RAG_PROVISION_TEST_BIN` to the
PostgreSQL `bin` directory and runs `test_provision_local.py`. It creates a
private, disposable cluster under ignored `.local/provision-tests` on another
port, verifies password-mismatch rollback, successful retry, and preservation
of existing objects, then stops and removes only that private cluster. It never
connects to the existing instance on port 5432.

## 3. Install the matching pgvector build when needed

Inspection found neither `share\extension\vector.control` nor `lib\vector.dll`
in the PostgreSQL 18 installation. Visual Studio 2026 C++ Build Tools were
available. A pinned pgvector 0.8.7 build was compiled successfully under
`rag-service/.local/pgvector-v0.8.7`, using the actual PostgreSQL 18 headers and
libraries. The checkout and all build products are ignored by Git.

To reproduce only the build from PowerShell:

```powershell
Set-Location C:\NASA\nasa\rag-service
& .\scripts\build_pgvector.ps1
```

This command does not install server files. If vector is still absent, open
Command Prompt as Administrator and run:

```bat
call "C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\Common7\Tools\VsDevCmd.bat" -host_arch=x64 -arch=x64
set "PGROOT=C:\Program Files\PostgreSQL\18"
cd /d "C:\NASA\nasa\rag-service\.local\pgvector-v0.8.7"
nmake /F Makefile.win install
```

These are the [upstream Windows build/install steps](https://github.com/pgvector/pgvector#windows)
applied to the detected instance. They install extension files, not a replacement
PostgreSQL server or data directory. Do not install over a separately installed
extension; if vector is already available, use the SQL check instead. No cluster
initialization, service replacement, HBA change, or data-directory move is needed.

Rerun `provision_local.sql` in the administrative `psql` session after installation.
It then creates the extension only if it is still absent. Leave the session
with `\q` before using the application tools.

## 4. Save the application connection without displaying its password

From your own interactive PowerShell terminal:

```powershell
Set-Location C:\NASA\nasa\rag-service
& .\.venv\Scripts\python.exe -m app.database_setup configure
```

Enter the existing password for `pyrosphere_rag_app` at the hidden prompt. If
the role was just created, use the application password chosen in step 2, not
the administrative password. An existing role's password is never reset.

The helper first authenticates as the application role and checks database and
schema permissions. It writes only missing/empty application keys in the ignored
`.env`, preserving unrelated settings and existing line endings. A different
nonempty connection or schema value causes a conflict instead of an overwrite.
It also refuses to silently override conflicting process environment settings.

The exact URI structure required by the installed psycopg driver is:

```text
postgresql://pyrosphere_rag_app:<URL_ENCODED_APP_PASSWORD>@localhost:5432/pyrosphere_rag
```

The helper URL-encodes credentials automatically, including special characters
and Unicode, and never prints the URI/password. `.env.example` has a blank URI
and a placeholder-only URI comment. `.env.admin`, if used for an explicitly
provided administrative URI, is also ignored and is not loaded by normal
operations. The interactive procedure does not require saving an administrator
password in that file.

If authentication/schema verification succeeds while vector is missing, the
helper saves the valid application connection but exits with code 2 and reports
`vectorOperation: BLOCKED`. Complete step 3 and verify again; this is not an
indexing success.

## 5. Verify before indexing

```powershell
& .\.venv\Scripts\python.exe -m app.database_setup verify
```

The checks require a direct connection to database `pyrosphere_rag` as
`pyrosphere_rag_app`, without administrative role attributes; schema ownership,
marker, USAGE and CREATE privileges; the target database's vector extension;
and an actual cosine operation with expected distance 1.0. A randomly named
probe table is created only in `rag`, used, and rolled back with its entire
transaction. No existing table is altered or deleted.

## 6. Continue indexing and retrieval

Only after the application/vector checks succeed:

```powershell
& .\.venv\Scripts\python.exe -m app.indexing --batch-size 8
& .\.venv\Scripts\python.exe -m app.indexing --batch-size 8
& .\.venv\Scripts\python.exe -m app.retrieval_checks --cold
```

The first command must actually persist 274 validated source records before a
success is reported. The second should report zero newly embedded records and
274 reused embeddings. The final command checks exact IDs, both rows sharing
`193F001`, filtered extinction retrieval, unsupported fabric questions, numerical
query rejection, CSV values, and separately observed cold/warm query timings.
`/rag/v1/answer`, original datasets, evidence provenance and the model client
remain unchanged by this setup.
