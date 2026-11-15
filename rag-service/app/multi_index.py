"""Build/validate a separate multi-source index; never clear or modify the FLEX index."""
import argparse
import asyncio
import json
import os
from pathlib import Path

from dotenv import dotenv_values
import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict

from .rag_config import APP_DATABASE, APP_ROLE, BASE_DIR, DatabaseSettings, RagError
from .rag_corpus import content_hash, load_corpus
from .vector_store import SCHEMA_MARKER, open_store

TARGET_SCHEMA = "rag_nasa_multi_v1"


def provision_schema():
    """Use only the existing local admin configuration, without changing role privileges."""
    values = dotenv_values(BASE_DIR / ".env.admin")
    if values.get("RAG_ADMIN_DATABASE_URL"):
        parameters = conninfo_to_dict(values["RAG_ADMIN_DATABASE_URL"])
    else:
        required = ("RAG_ADMIN_HOST", "RAG_ADMIN_PORT", "RAG_ADMIN_USER", "RAG_ADMIN_PASSWORD")
        if any(not values.get(key) for key in required):
            raise RagError("ADMIN_CONFIG_REQUIRED", "An existing administrative connection is required to create the new owned schema; no credentials were guessed.")
        parameters = dict(host=values[required[0]], port=values[required[1]], user=values[required[2]], password=values[required[3]])
    parameters["dbname"] = APP_DATABASE
    with psycopg.connect(**parameters, connect_timeout=5, autocommit=True) as connection:
        with connection.transaction():
            existing = connection.execute("SELECT pg_get_userbyid(nspowner), obj_description(oid, 'pg_namespace') FROM pg_namespace WHERE nspname=%s", (TARGET_SCHEMA,)).fetchone()
            if existing is not None:
                if existing != (APP_ROLE, SCHEMA_MARKER):
                    raise RagError("SCHEMA_NOT_OWNED", "The intended new schema already exists with a different owner or marker; it was not changed.")
                return
            connection.execute(sql.SQL("CREATE SCHEMA {} AUTHORIZATION {}").format(sql.Identifier(TARGET_SCHEMA), sql.Identifier(APP_ROLE)))
            connection.execute(sql.SQL("COMMENT ON SCHEMA {} IS {}").format(sql.Identifier(TARGET_SCHEMA), sql.Literal(SCHEMA_MARKER)))


def legacy_snapshot(settings):
    with open_store(settings) as store:
        rows = store.connection.execute(sql.SQL("SELECT source_id,row_number,content_hash,md5(embedding::text) AS vector_hash,updated_at::text FROM {} ORDER BY source_id,row_number").format(store.records_table)).fetchall()
        state = store.state()
        return {"schema": settings.schema, "count": len(rows), "rowsHash": content_hash(rows),
            "stateHash": content_hash({**state, "updated_at": str(state["updated_at"])})}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare-schema", action="store_true", help="Create only the new schema using existing admin configuration")
    args = parser.parse_args()
    settings = DatabaseSettings.from_environment()
    # .env may have already been switched after a completed validation. The old
    # baseline always stays in rag; this command never indexes that schema.
    legacy = DatabaseSettings(settings.url, "rag")
    before = legacy_snapshot(legacy)
    path = BASE_DIR / ".local/nasa-provenance/legacy_index_before.json"
    if path.exists() and json.loads(path.read_text(encoding="utf-8")) != before:
        raise RagError("LEGACY_INDEX_CHANGED", "The FLEX baseline differs from its saved snapshot; investigate before indexing.")
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists(): path.write_text(json.dumps(before, indent=2) + "\n", encoding="utf-8")
    if args.prepare_schema:
        provision_schema()
        os.environ["RAG_DB_SCHEMA"] = TARGET_SCHEMA
    else:
        os.environ["RAG_DB_SCHEMA"] = legacy.schema
    os.environ["RAG_INDEX_NAME"] = "nasa_multi_v1"
    os.environ["RAG_CORPUS_MODE"] = "multi"
    from .indexing import run_index
    result = asyncio.run(run_index(8))
    with open_store(DatabaseSettings.from_environment()) as store:
        store.ready(load_corpus(mode="multi"))
    if legacy_snapshot(legacy) != before:
        raise RagError("LEGACY_INDEX_CHANGED", "The legacy index snapshot changed during the operation")
    print(json.dumps({**result, "schema": os.environ["RAG_DB_SCHEMA"], "indexName": "nasa_multi_v1", "legacyFlexIndex": before, "configurationSwitched": False}, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (RagError, psycopg.Error) as error:
        # Do not expose connection strings/passwords in driver exception text.
        print(f"Index preparation failed ({getattr(error, 'code', type(error).__name__)}). No legacy index was cleared.")
        raise SystemExit(1)
