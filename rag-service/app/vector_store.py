"""PostgreSQL persistence restricted to a marked, RAG-owned schema."""

from contextlib import contextmanager
import json
import math

import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .rag_config import APP_DATABASE, APP_ROLE, DatabaseSettings, RagError
from .rag_corpus import Corpus, content_hash, record_key, text_hash
from .model_profile import ModelProfile, expected_profile
from .source_catalog import field_value


SCHEMA_MARKER = "PyroSphere RAG evidence store; schema version 1"


def verify_application_identity(connection) -> dict:
    identity = connection.execute(
        "SELECT current_database() AS database, current_user AS role, session_user AS session_role, "
        "rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls "
        "FROM pg_roles WHERE rolname = current_user"
    ).fetchone()
    if identity is None or identity["database"] != APP_DATABASE:
        raise RagError("WRONG_DATABASE", f"Normal RAG operations require database {APP_DATABASE}.")
    if identity["role"] != APP_ROLE or identity["session_role"] != APP_ROLE:
        raise RagError("APPLICATION_ROLE_REQUIRED", f"Normal RAG operations must connect directly as {APP_ROLE}.")
    if any(identity[key] for key in ("rolsuper", "rolcreatedb", "rolcreaterole", "rolreplication", "rolbypassrls")):
        raise RagError("APPLICATION_ROLE_PRIVILEGES", "The application role has administrative attributes; no role attributes were changed.")
    return identity


def vector_literal(vector: list[float], dimensions: int) -> str:
    if len(vector) != dimensions or not vector:
        raise RagError("INCOMPATIBLE_INDEX", "Embedding dimensions differ from the index configuration.")
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in vector):
        raise RagError("INVALID_VECTOR", "Embedding components must be numeric.")
    try:
        invalid = any(not math.isfinite(value) or abs(value) > 3.402823466e38 for value in vector)
    except OverflowError:
        invalid = True
    if invalid:
        raise RagError("INVALID_VECTOR", "Embedding components must be finite pgvector float32 values.")
    if not any(value != 0 for value in vector):
        raise RagError("INVALID_VECTOR", "A zero embedding cannot be used for cosine distance.")
    return json.dumps(vector, allow_nan=False, separators=(",", ":"))


def filter_clause(filters: dict) -> tuple[sql.Composed, list]:
    clauses = [sql.SQL("index_id = 1")]
    parameters = []
    columns = {
        "source_ids": "source_id", "investigation_ids": "investigation_id",
        "test_ids": "source_test_id", "flex_identifiers": "flex_identifier",
        "sheet_names": "sheet_name",
    }
    if set(filters) - (set(columns) | {"fuel", "outcome"}):
        raise RagError("INVALID_FILTER", "An unsupported retrieval filter was supplied.")
    for name, column in columns.items():
        values = filters.get(name)
        if values:
            clauses.append(sql.SQL("{} = ANY(%s)").format(sql.Identifier(column)))
            parameters.append(list(values))
    for name, column in (("fuel", "fuel"), ("outcome", "reported_outcome")):
        if filters.get(name) is not None:
            clauses.append(sql.SQL("{} = %s").format(sql.Identifier(column)))
            parameters.append(filters[name])
    return sql.SQL(" AND ").join(clauses), parameters


@contextmanager
def open_store(settings: DatabaseSettings):
    try:
        with psycopg.connect(
            settings.url, connect_timeout=5, autocommit=True, row_factory=dict_row,
            application_name="pyrosphere-rag", options="-c statement_timeout=30000 -c lock_timeout=5000",
        ) as connection:
            verify_application_identity(connection)
            yield PgVectorStore(connection, settings.schema, settings.index_name)
    except (psycopg.errors.QueryCanceled, psycopg.errors.ConnectionTimeout) as error:
        raise RagError("DATABASE_TIMEOUT", "The PostgreSQL connection or RAG query timed out.") from error
    except psycopg.errors.LockNotAvailable as error:
        raise RagError("DATABASE_TIMEOUT", "The PostgreSQL RAG operation exceeded its lock wait limit.") from error
    except psycopg.OperationalError as error:
        raise RagError(
            "DATABASE_UNAVAILABLE",
            "Cannot connect to or continue using PostgreSQL. Check RAG_DATABASE_URL and database access.",
        ) from error
    except psycopg.Error as error:
        raise RagError(
            "DATABASE_ERROR",
            f"PostgreSQL rejected a RAG operation ({type(error).__name__}). "
            "Check schema ownership, extension installation, and the setup instructions.",
        ) from error


class PgVectorStore:
    def __init__(self, connection, schema: str, index_name="legacy"):
        # Validate even when constructed directly by an integration test.
        DatabaseSettings("validated-connection", schema, index_name)
        self.connection = connection
        self.schema = schema
        self.index_name = index_name
        suffix = "" if index_name == "legacy" else "_" + index_name
        self.state_table_name = "index_state" + suffix
        self.records_table_name = "evidence_records" + suffix
        self.state_table = sql.Identifier(schema, self.state_table_name)
        self.records_table = sql.Identifier(schema, self.records_table_name)
        self.vector_namespace = None
        self.profile = None

    @contextmanager
    def lock(self, *, shared: bool = False):
        acquire = sql.SQL("pg_try_advisory_lock_shared" if shared else "pg_try_advisory_lock")
        release = sql.SQL("pg_advisory_unlock_shared" if shared else "pg_advisory_unlock")
        key = f"pyrosphere-rag:{self.schema}" + ("" if self.index_name == "legacy" else f":{self.index_name}")
        result = self.connection.execute(
            sql.SQL("SELECT {}(hashtextextended(%s, 0)) AS acquired").format(acquire), (key,)
        ).fetchone()
        if not result["acquired"]:
            raise RagError("INDEX_BUSY", "Another indexing or retrieval operation is using this RAG index.")
        try:
            yield
        finally:
            if not self.connection.closed:
                self.connection.execute(
                    sql.SQL("SELECT {}(hashtextextended(%s, 0))").format(release), (key,)
                )

    def _owned_schema(self, *, create: bool):
        row = self.connection.execute(
            "SELECT pg_get_userbyid(nspowner) = current_user AS owned, "
            "obj_description(oid, 'pg_namespace') AS marker FROM pg_namespace WHERE nspname = %s",
            (self.schema,),
        ).fetchone()
        if row is None:
            if not create:
                raise RagError("INDEX_NOT_READY", "The RAG schema does not exist. Run the indexer first.")
            self.connection.execute(sql.SQL("CREATE SCHEMA {} AUTHORIZATION CURRENT_USER").format(sql.Identifier(self.schema)))
            self.connection.execute(
                sql.SQL("COMMENT ON SCHEMA {} IS {}").format(sql.Identifier(self.schema), sql.Literal(SCHEMA_MARKER))
            )
        elif not row["owned"] or row["marker"] != SCHEMA_MARKER:
            raise RagError("SCHEMA_NOT_OWNED", "Refusing to use an unmarked schema or a schema owned by another role.")

    def _extension(self):
        row = self.connection.execute(
            "SELECT n.nspname AS namespace FROM pg_extension e "
            "JOIN pg_namespace n ON n.oid = e.extnamespace WHERE e.extname = 'vector'"
        ).fetchone()
        if row is None:
            raise RagError("PGVECTOR_UNAVAILABLE", "An administrator must install CREATE EXTENSION vector in this database.")
        self.vector_namespace = row["namespace"]

    def bootstrap(self, profile: ModelProfile):
        self._extension()
        with self.connection.transaction():
            self._owned_schema(create=True)
            self.connection.execute(sql.SQL("""
                CREATE TABLE IF NOT EXISTS {} (
                    id smallint PRIMARY KEY CHECK (id = 1),
                    configuration jsonb NOT NULL,
                    corpus_hash text NOT NULL DEFAULT '',
                    source_hash text NOT NULL DEFAULT '',
                    expected_count integer NOT NULL DEFAULT 0,
                    status text NOT NULL CHECK (status IN ('BUILDING', 'READY')),
                    updated_at timestamptz NOT NULL DEFAULT now()
                )
            """).format(self.state_table))
            state = self.state()
            if state is None:
                self.connection.execute(
                    sql.SQL("INSERT INTO {} (id, configuration, status) VALUES (1, %s, 'BUILDING')").format(self.state_table),
                    (Jsonb(profile.configuration),),
                )
            else:
                self.assert_configuration(state, profile)
            sheet_definition = sql.SQL("sheet_name text NOT NULL DEFAULT '',") if profile.schema_version >= 2 else sql.SQL("")
            sheet_key = sql.SQL("sheet_name,") if profile.schema_version >= 2 else sql.SQL("")
            self.connection.execute(sql.SQL("""
                CREATE TABLE IF NOT EXISTS {records} (
                    index_id smallint NOT NULL DEFAULT 1 REFERENCES {state}(id),
                    source_id text NOT NULL,
                    {sheet_definition}
                    row_number integer NOT NULL CHECK (row_number >= 2),
                    investigation_id text NOT NULL,
                    source_test_id text NOT NULL,
                    source_file text NOT NULL,
                    fuel text NOT NULL,
                    flex_identifier text NOT NULL,
                    reported_outcome text NOT NULL,
                    record jsonb NOT NULL,
                    content_hash text NOT NULL,
                    text_hash text NOT NULL,
                    embedding {vector_type}({dimensions}) NOT NULL,
                    updated_at timestamptz NOT NULL DEFAULT now(),
                    PRIMARY KEY (index_id, source_id, {sheet_key} row_number)
                )
            """).format(
                records=self.records_table, state=self.state_table,
                vector_type=sql.Identifier(self.vector_namespace, "vector"), dimensions=sql.Literal(profile.dimensions),
                sheet_definition=sheet_definition, sheet_key=sheet_key,
            ))
            column = self.connection.execute(
                "SELECT a.atttypmod AS dimensions, t.typname FROM pg_attribute a "
                "JOIN pg_type t ON t.oid = a.atttypid "
                "WHERE a.attrelid = to_regclass(%s) AND a.attname = 'embedding' AND NOT a.attisdropped",
                (f"{self.schema}.{self.records_table_name}",),
            ).fetchone()
            if column is None or column["dimensions"] != profile.dimensions or column["typname"] != "vector":
                raise RagError("INCOMPATIBLE_INDEX", "The stored vector column has incompatible dimensions or type.")
            self.connection.execute(sql.SQL(
                "CREATE INDEX IF NOT EXISTS {index} ON {records} "
                "(index_id, source_id, investigation_id, fuel, source_test_id)"
            ).format(index=sql.Identifier("evidence_source_filters" + ("" if self.index_name == "legacy" else "_" + self.index_name)), records=self.records_table))
        self.profile = profile

    def state(self) -> dict | None:
        return self.connection.execute(sql.SQL("SELECT * FROM {} WHERE id = 1").format(self.state_table)).fetchone()

    @staticmethod
    def assert_configuration(state: dict, profile: ModelProfile):
        if state["configuration"] != profile.configuration:
            raise RagError(
                "INCOMPATIBLE_INDEX",
                "Index model, digest, dimensions, schema version, or query/document format differs. "
                "Use a new RAG_DB_SCHEMA; the existing index was not replaced.",
            )

    def cache(self) -> dict:
        rows = self.connection.execute(sql.SQL(
            "SELECT source_id, row_number, content_hash, text_hash, record FROM {} WHERE index_id = 1"
        ).format(self.records_table)).fetchall()
        return {record_key(row["record"]): row for row in rows}

    def begin_snapshot(self, corpus: Corpus):
        self.connection.execute(sql.SQL(
            "UPDATE {} SET status = 'BUILDING', corpus_hash = %s, source_hash = %s, "
            "expected_count = %s, updated_at = now() WHERE id = 1"
        ).format(self.state_table), (corpus.fingerprint, corpus.manifest["sha256"], len(corpus.records)))

    def write_batch(self, records: list[dict], vectors: dict):
        with self.connection.transaction():
            for record in records:
                vector = vectors.get(record_key(record))
                values = (
                    record["investigationId"], record["sourceTestId"], record["sourceFile"],
                    " ".join(field_value(record, "fuel").split()), field_value(record, "identifier"), field_value(record, "outcome"),
                    Jsonb(record), content_hash(record), text_hash(record), record["sourceId"], record["rowNumber"],
                )
                multi = self.profile.schema_version >= 2
                sheet_column = sql.SQL(", sheet_name") if multi else sql.SQL("")
                sheet_parameter = sql.SQL(", %s") if multi else sql.SQL("")
                sheet_condition = sql.SQL(" AND sheet_name=%s") if multi else sql.SQL("")
                if multi:
                    values = (*values, record.get("sheetName", ""))
                if vector is None:
                    result = self.connection.execute((sql.SQL(
                        "UPDATE {} SET investigation_id=%s, source_test_id=%s, source_file=%s, fuel=%s, "
                        "flex_identifier=%s, reported_outcome=%s, record=%s, content_hash=%s, text_hash=%s, "
                        "updated_at=now() WHERE index_id=1 AND source_id=%s AND row_number=%s"
                    ) + sheet_condition).format(self.records_table), values)
                    if result.rowcount != 1:
                        raise RagError("CORRUPT_INDEX", "An embedding selected for reuse is missing.")
                else:
                    literal = vector_literal(vector, self.profile.dimensions)
                    self.connection.execute(sql.SQL("""
                        INSERT INTO {records} (
                            investigation_id, source_test_id, source_file, fuel, flex_identifier,
                            reported_outcome, record, content_hash, text_hash, source_id, row_number{sheet_column}, embedding
                        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s{sheet_parameter},%s::{vector_type})
                        ON CONFLICT (index_id, source_id, row_number{sheet_column}) DO UPDATE SET
                            investigation_id=EXCLUDED.investigation_id, source_test_id=EXCLUDED.source_test_id,
                            source_file=EXCLUDED.source_file, fuel=EXCLUDED.fuel,
                            flex_identifier=EXCLUDED.flex_identifier, reported_outcome=EXCLUDED.reported_outcome,
                            record=EXCLUDED.record, content_hash=EXCLUDED.content_hash,
                            text_hash=EXCLUDED.text_hash, embedding=EXCLUDED.embedding, updated_at=now()
                    """).format(records=self.records_table, vector_type=sql.Identifier(self.vector_namespace, "vector"),
                        sheet_column=sheet_column, sheet_parameter=sheet_parameter),
                        (*values, literal),
                    )

    def finish_snapshot(self, corpus: Corpus):
        with self.connection.transaction():
            # Source removal is never implicit. A partial/shrinking snapshot fails
            # before indexing; this final check also refuses unexpected persisted rows.
            cache = self.cache()
            if set(cache) != set(corpus.by_key) or any(
                cache[record_key(record)]["record"] != record
                or cache[record_key(record)]["content_hash"] != content_hash(record)
                or cache[record_key(record)]["text_hash"] != text_hash(record)
                for record in corpus.records
            ):
                raise RagError("CORRUPT_INDEX", "Persisted records do not match the complete validated source snapshot.")
            self.connection.execute(sql.SQL(
                "UPDATE {} SET status='READY', updated_at=now() WHERE id=1"
            ).format(self.state_table))

    def ready(self, corpus: Corpus) -> dict:
        self._owned_schema(create=False)
        self._extension()
        exists = self.connection.execute("SELECT to_regclass(%s) AS name", (f"{self.schema}.{self.state_table_name}",)).fetchone()
        if exists["name"] is None:
            raise RagError("INDEX_NOT_READY", "The RAG schema has no initialized index.")
        state = self.state()
        if state is None or state["status"] != "READY":
            raise RagError("INDEX_NOT_READY", "Indexing is incomplete. Rerun the indexer to recover committed batches.")
        if (
            state["corpus_hash"] != corpus.fingerprint or state["expected_count"] != len(corpus.records)
            or state["source_hash"] != corpus.manifest["sha256"]
        ):
            raise RagError("STALE_INDEX", "The stored index does not match the current validated evidence snapshot.")
        try:
            self.profile = ModelProfile(**state["configuration"])
        except (TypeError, ValueError) as error:
            raise RagError("INCOMPATIBLE_INDEX", "Index configuration is not recognized.") from error
        self.assert_configuration(state, expected_profile(self.profile.model, self.profile.digest, self.profile.dimensions, schema_version=self.profile.schema_version))
        if self.candidate_count({}) != len(corpus.records):
            raise RagError("INDEX_NOT_READY", "Stored record count is incomplete; rerun the indexer.")
        return state

    def candidate_count(self, filters: dict) -> int:
        clause, parameters = filter_clause(filters)
        return self.connection.execute(
            sql.SQL("SELECT count(*) AS count FROM {} WHERE {}").format(self.records_table, clause), parameters
        ).fetchone()["count"]

    def search(self, filters: dict, vector: list[float] | None = None) -> list[dict]:
        clause, parameters = filter_clause(filters)
        if vector is None:
            query = sql.SQL(
                "SELECT record, NULL::double precision AS cosine_distance FROM {} WHERE {} "
                "ORDER BY source_id, row_number LIMIT 5"
            ).format(self.records_table, clause)
        else:
            # Exhaustive search over 274 rows: materialize filters before cosine ranking.
            query = sql.SQL("""
                WITH candidates AS MATERIALIZED (
                    SELECT record, embedding, source_id, row_number FROM {records} WHERE {clause}
                )
                SELECT record, embedding OPERATOR({vector_schema}.<=>) %s::{vector_type} AS cosine_distance
                FROM candidates ORDER BY cosine_distance, source_id, row_number LIMIT 5
            """).format(
                records=self.records_table, clause=clause, vector_schema=sql.Identifier(self.vector_namespace),
                vector_type=sql.Identifier(self.vector_namespace, "vector"),
            )
            parameters.append(vector_literal(vector, self.profile.dimensions))
        return self.connection.execute(query, parameters).fetchall()
