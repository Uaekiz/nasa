"""Hidden application-password entry and non-destructive connection verification."""

import argparse
from getpass import getpass
import json
import math
import os
from pathlib import Path
import re
import secrets
import sys
import tempfile
from urllib.parse import quote

from dotenv import dotenv_values
import psycopg
from psycopg import sql
from psycopg.rows import dict_row

from .rag_config import APP_DATABASE, APP_ROLE, BASE_DIR, DatabaseSettings, RagError
from .vector_store import SCHEMA_MARKER, verify_application_identity


ENV_PATH = BASE_DIR / ".env"


def application_url(password: str, host: str = "localhost", port: int = 5432) -> str:
    if not password:
        raise RagError("APPLICATION_PASSWORD_REQUIRED", "Enter the existing application-role password at the hidden prompt.")
    if not 1 <= port <= 65535 or not host or re.search(r"[\s/@?#]", host):
        raise RagError("INVALID_DATABASE_ADDRESS", "Provide a hostname or IP address and a valid PostgreSQL port.")
    hostname = f"[{host}]" if ":" in host and not host.startswith("[") else host
    return f"postgresql://{quote(APP_ROLE, safe='')}:{quote(password, safe='')}@{hostname}:{port}/{APP_DATABASE}"


def save_local_configuration(url: str, path: Path = ENV_PATH) -> bool:
    """Fill only empty/missing application keys; preserve unrelated configuration."""
    try:
        before = path.read_bytes() if path.exists() else None
        values = dotenv_values(path) if before is not None else {}
    except (OSError, UnicodeError) as error:
        raise RagError("CONFIGURATION_UNREADABLE", "Cannot read the local application configuration.") from error
    desired = {"RAG_DATABASE_URL": url, "RAG_DB_SCHEMA": "rag"}
    for key, value in desired.items():
        if values.get(key) and values[key] != value:
            raise RagError("CONFIGURATION_CONFLICT", f"Existing {key} differs. It was not overwritten; review .env locally.")
        if os.environ.get(key) and os.environ[key] != value:
            raise RagError("CONFIGURATION_CONFLICT", f"The process environment already defines a different {key}; it was not changed.")
    text = before.decode("utf-8-sig") if before is not None else "# Local application configuration. Never commit this file.\n"
    newline = "\r\n" if before is not None and b"\r\n" in before else "\n"
    lines = text.splitlines(keepends=True)
    for key, value in desired.items():
        matches = [index for index, line in enumerate(lines) if re.match(r"^\s*(?:export\s+)?" + key + r"\s*=", line)]
        if len(matches) > 1:
            raise RagError("CONFIGURATION_CONFLICT", f"Multiple {key} entries exist; review .env locally before proceeding.")
        if values.get(key) == value:
            continue
        replacement = f"{key}={value}{newline}"
        if matches:
            lines[matches[0]] = replacement
        else:
            if lines and not lines[-1].endswith(("\n", "\r")):
                lines[-1] += newline
            lines.append(replacement)
    content = "".join(lines).encode("utf-8")
    if content == before:
        return False
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(prefix=".env.pending.", dir=path.parent, delete=False) as stream:
            temporary_path = Path(stream.name)
            stream.write(content)
        current = path.read_bytes() if path.exists() else None
        if current != before:
            raise RagError("CONFIGURATION_CONFLICT", "The local configuration changed during setup and was not overwritten.")
        os.replace(temporary_path, path)
        temporary_path = None
    except OSError as error:
        raise RagError("CONFIGURATION_WRITE_FAILED", "Cannot save the local application configuration.") from error
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
    return True


def verify_connection(url: str, schema: str = "rag") -> dict:
    settings = DatabaseSettings(url, schema)
    try:
        with psycopg.connect(
            settings.url, connect_timeout=5, autocommit=True, row_factory=dict_row,
            application_name="pyrosphere-rag-setup", options="-c statement_timeout=30000 -c lock_timeout=5000",
        ) as connection:
            identity = verify_application_identity(connection)
            namespace = connection.execute(
                "SELECT pg_get_userbyid(nspowner)=current_user AS owned, "
                "obj_description(oid,'pg_namespace') AS marker, "
                "has_schema_privilege(current_user,oid,'USAGE') AS usage, "
                "has_schema_privilege(current_user,oid,'CREATE') AS create_permission "
                "FROM pg_namespace WHERE nspname=%s", (settings.schema,),
            ).fetchone()
            if namespace is None or not namespace["owned"] or namespace["marker"] != SCHEMA_MARKER:
                raise RagError("SCHEMA_NOT_OWNED", "The intended application schema is absent, unmarked, or owned by another role.")
            if not namespace["usage"] or not namespace["create_permission"]:
                raise RagError("SCHEMA_PERMISSION_REQUIRED", "The application role needs USAGE and CREATE in its own schema.")
            extension = connection.execute(
                "SELECT e.extversion AS version, n.nspname AS namespace FROM pg_extension e "
                "JOIN pg_namespace n ON n.oid=e.extnamespace WHERE e.extname='vector'"
            ).fetchone()
            result = {
                "database": identity["database"], "role": identity["role"], "schema": settings.schema,
                "applicationConnection": "VERIFIED", "schemaPermissions": "VERIFIED",
                "vectorExtension": extension["version"] if extension else None,
                "vectorOperation": "BLOCKED", "probeRolledBack": False,
            }
            if extension is None:
                result["blocker"] = "pgvector is not installed in the target database. Install matching server files and rerun provisioning."
                return result
            probe = sql.Identifier(settings.schema, "_setup_probe_" + secrets.token_hex(8))
            vector_type = sql.Identifier(extension["namespace"], "vector")
            with connection.transaction(force_rollback=True):
                connection.execute(sql.SQL("CREATE TABLE {} (embedding {}(3) NOT NULL)").format(probe, vector_type))
                connection.execute(sql.SQL("INSERT INTO {} VALUES (%s::{})").format(probe, vector_type), ("[1,0,0]",))
                row = connection.execute(sql.SQL(
                    "SELECT embedding OPERATOR({}.<=>) %s::{} AS distance FROM {}"
                ).format(sql.Identifier(extension["namespace"]), vector_type, probe), ("[0,1,0]",)).fetchone()
                distance = row["distance"]
                if not math.isfinite(distance) or not math.isclose(distance, 1.0, abs_tol=1e-6):
                    raise RagError("VECTOR_CHECK_FAILED", "The application vector operation returned an unexpected result.")
            result.update(vectorOperation="VERIFIED", cosineDistance=distance, probeRolledBack=True)
            return result
    except psycopg.Error as error:
        raise RagError(
            "DATABASE_ACCESS_FAILED", "Application connection or verification failed. Check the local password, provisioning, and server availability."
        ) from error


def main() -> int:
    parser = argparse.ArgumentParser(description="Configure and verify the dedicated application connection without printing passwords.")
    parser.add_argument("action", choices=("configure", "verify"))
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=5432)
    args = parser.parse_args()
    try:
        if args.action == "configure":
            if not sys.stdin.isatty():
                raise RagError("INTERACTIVE_TERMINAL_REQUIRED", "Run configure in your own interactive PowerShell terminal for hidden password entry.")
            password = getpass(f"Existing password for {APP_ROLE} (hidden): ")
            url = application_url(password, args.host, args.port)
            result = verify_connection(url)
            changed = save_local_configuration(url)
            result["configuration"] = "SAVED" if changed else "UNCHANGED"
            result["configurationFile"] = str(ENV_PATH)
        else:
            settings = DatabaseSettings.from_environment()
            result = verify_connection(settings.url, settings.schema)
        print(json.dumps(result, indent=2))
        return 0 if result["vectorOperation"] == "VERIFIED" else 2
    except (RagError, EOFError) as error:
        if isinstance(error, RagError):
            print(f"Error [{error.code}]: {error}", file=sys.stderr)
        else:
            print("Error: Run configure in your own interactive terminal so the password stays local.", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Setup cancelled. Existing role passwords and database objects were not changed.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
