"""Opt-in PostgreSQL tests, restricted to newly created RAG test schemas."""

import asyncio
from copy import deepcopy
import os
import unittest
from unittest.mock import AsyncMock
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row

from app.indexing import index_corpus
from app.model_profile import ModelProfile
from app.rag_config import APP_DATABASE, APP_ROLE, DatabaseSettings, RagError
from app.rag_corpus import load_corpus
from app.vector_store import SCHEMA_MARKER, open_store
from rag_test_support import synthetic_corpus
from test_rag_indexing import PROFILE, fake_result


@unittest.skipUnless(
    os.getenv("RAG_TEST_DATABASE_URL") and os.getenv("RAG_TEST_ADMIN_DATABASE_URL"),
    "Set RAG_TEST_DATABASE_URL and RAG_TEST_ADMIN_DATABASE_URL for disposable-schema PostgreSQL tests.",
)
class PgVectorIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.schema = "rag_test_" + uuid4().hex
        admin_parameters = conninfo_to_dict(os.environ["RAG_TEST_ADMIN_DATABASE_URL"])
        admin_parameters["dbname"] = APP_DATABASE
        self.admin = psycopg.connect(**admin_parameters, connect_timeout=5, autocommit=True, row_factory=dict_row)
        self.addCleanup(self.admin.close)
        self.admin.execute(sql.SQL("CREATE SCHEMA {} AUTHORIZATION {}").format(sql.Identifier(self.schema), sql.Identifier(APP_ROLE)))
        self.addCleanup(self.remove_test_schema)
        self.unmarked = self._testMethodName == "test_unmarked_schema_is_never_modified"
        if not self.unmarked:
            self.admin.execute(sql.SQL("COMMENT ON SCHEMA {} IS {}").format(sql.Identifier(self.schema), sql.Literal(SCHEMA_MARKER)))
        self.settings = DatabaseSettings(os.environ["RAG_TEST_DATABASE_URL"], self.schema)
        self.context = open_store(self.settings)
        self.store = self.context.__enter__()
        self.addCleanup(self.context.__exit__, None, None, None)

    def remove_test_schema(self):
        row = self.admin.execute(
            "SELECT pg_get_userbyid(nspowner)=%s AS owned, "
            "obj_description(oid,'pg_namespace') AS marker FROM pg_namespace WHERE nspname=%s", (APP_ROLE, self.schema),
        ).fetchone()
        if row is not None and row["owned"] and row["marker"] == SCHEMA_MARKER:
            self.admin.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(self.schema)))
        elif row is not None and row["owned"] and self.unmarked and row["marker"] is None:
            self.admin.execute(sql.SQL("DROP SCHEMA {}").format(sql.Identifier(self.schema)))

    def index(self, corpus, *, embed=None, profile=PROFILE, batch_size=2):
        with self.store.lock():
            return asyncio.run(index_corpus(
                self.store, corpus, profile, batch_size=batch_size,
                embed=embed or AsyncMock(side_effect=fake_result),
            ))

    def test_durable_recovery_rerun_and_incompatible_index_rejection(self):
        corpus = synthetic_corpus(5)
        interrupted = AsyncMock(side_effect=[fake_result(["A", "B"]), RuntimeError("Synthetic interruption.")])
        with self.assertRaises(RuntimeError):
            self.index(corpus, embed=interrupted)
        self.assertEqual(len(self.store.cache()), 2)
        self.assertEqual(self.store.state()["status"], "BUILDING")
        with self.assertRaises(RagError):
            self.store.ready(corpus)
        result = self.index(corpus)
        self.assertEqual(result["embeddedRecords"], 3)
        self.assertEqual(result["reusedEmbeddings"], 2)
        result = self.index(corpus, embed=AsyncMock(side_effect=AssertionError("No embedding expected.")))
        self.assertEqual(result["embeddedRecords"], 0)
        self.assertEqual(self.store.candidate_count({}), 5)
        with self.assertRaises(RagError) as caught:
            self.index(corpus, profile=ModelProfile(PROFILE.model, "different-model-digest", 3))
        self.assertEqual(caught.exception.code, "INCOMPATIBLE_INDEX")

    def test_sql_filters_precede_exact_cosine_ranking_and_original_values_survive(self):
        corpus = synthetic_corpus(8)
        self.index(corpus)
        self.store.ready(corpus)
        filters = {"source_ids": [corpus.manifest["sourceId"]], "investigation_ids": ["PSI-69"], "fuel": "Heptane"}
        rows = self.store.search(filters, [1, 1, 0])
        self.assertEqual(len(rows), 4)
        self.assertTrue(all(row["record"]["fields"]["Fuel"] == "Heptane" for row in rows))
        self.assertTrue(all(row["record"]["fields"]["Burning rate; mm"] == "~0.5" for row in rows))
        repeated = self.store.search({"flex_identifiers": ["SYNTHETIC-DUP"]})
        self.assertEqual({row["record"]["sourceTestId"] for row in repeated}, {"1", "2"})
        self.assertEqual(self.store.search({"investigation_ids": ["PSI-25"]}, [1, 1, 0]), [])

    def test_actual_csv_records_round_trip_without_merging_shared_flex_identifier(self):
        corpus = load_corpus(mode="flex")
        selected = [record for record in corpus.records if record["sourceTestId"] in {"24", "70", "73"}]
        from app.rag_corpus import Corpus, content_hash
        subset = Corpus(deepcopy(selected), corpus.manifest, content_hash(selected))
        self.index(subset)
        self.store.ready(subset)
        rows = self.store.search({"flex_identifiers": ["193F001"]})
        self.assertEqual({row["record"]["sourceTestId"] for row in rows}, {"70", "73"})
        for row in rows:
            self.assertEqual(row["record"], subset.by_key[(row["record"]["sourceId"], row["record"]["rowNumber"])])
        dash = self.store.search({"test_ids": ["24"]})[0]["record"]
        self.assertEqual(dash["fields"]["Droplet initial diameter; mm"], "\u2013")
        self.assertEqual(dash["fields"]["Burning rate; mm"], "")

    def test_unmarked_schema_is_never_modified(self):
        with self.assertRaises(RagError) as caught:
            self.index(synthetic_corpus())
        self.assertEqual(caught.exception.code, "SCHEMA_NOT_OWNED")
