from copy import deepcopy
import unittest
from unittest.mock import AsyncMock

from app.embedding_client import EmbeddingError, EmbeddingResult
from app.indexing import index_corpus
from app.model_profile import ModelProfile
from app.rag_config import DatabaseSettings, RagError
from app.rag_corpus import Corpus, content_hash, load_corpus, record_key
from app.vector_store import filter_clause, vector_literal
from rag_test_support import MemoryStore, synthetic_corpus


PROFILE = ModelProfile("qwen3-embedding:0.6b", "synthetic-digest", 3)


def fake_result(texts):
    return EmbeddingResult(PROFILE.model, [[1.0, float(index + 1), 0.0] for index in range(len(texts))], 2.0, 1.0, 0.5)


class IndexRecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_interruption_preserves_committed_batches_and_rerun_embeds_only_missing_rows(self):
        corpus = synthetic_corpus(5)
        store = MemoryStore()
        calls = []

        async def interrupt(texts):
            calls.append(texts)
            if len(calls) == 2:
                raise EmbeddingError("EMBEDDING_TIMEOUT", "Synthetic interruption.")
            return fake_result(texts)

        with self.assertRaises(EmbeddingError):
            await index_corpus(store, corpus, PROFILE, batch_size=2, embed=interrupt)
        self.assertEqual(len(store.data), 2)
        self.assertEqual(store.state()["status"], "BUILDING")
        with self.assertRaises(RagError):
            store.ready(corpus)
        resume = AsyncMock(side_effect=fake_result)
        result = await index_corpus(store, corpus, PROFILE, batch_size=2, embed=resume)
        self.assertEqual(result["indexedRecordCount"], 5)
        self.assertEqual(result["embeddedRecords"], 3)
        self.assertEqual(result["reusedEmbeddings"], 2)
        self.assertEqual(sum(len(call.args[0]) for call in resume.await_args_list), 3)
        self.assertEqual(len(store.data), 5)
        self.assertEqual(store.state()["status"], "READY")
        rerun = AsyncMock(side_effect=AssertionError("An unchanged rerun must not embed."))
        batches = store.batches
        result = await index_corpus(store, corpus, PROFILE, embed=rerun)
        self.assertEqual(result["embeddedRecords"], 0)
        self.assertEqual(result["reusedEmbeddings"], 5)
        self.assertEqual(store.batches, batches)
        rerun.assert_not_awaited()

    async def test_changed_text_reembeds_only_that_record(self):
        corpus = synthetic_corpus()
        store = MemoryStore()
        await index_corpus(store, corpus, PROFILE, embed=AsyncMock(side_effect=fake_result))
        changed = deepcopy(corpus.records)
        changed[1]["text"] = "Changed synthetic fixture, not NASA evidence."
        updated = Corpus(changed, corpus.manifest, content_hash(changed))
        embed = AsyncMock(side_effect=fake_result)
        result = await index_corpus(store, updated, PROFILE, embed=embed)
        embed.assert_awaited_once_with([changed[1]["text"]])
        self.assertEqual(result["embeddedRecords"], 1)
        self.assertEqual(result["reusedEmbeddings"], 2)

    async def test_recovery_after_all_batches_commit_but_before_ready_needs_no_new_embeddings(self):
        corpus = synthetic_corpus()
        store = MemoryStore()
        await index_corpus(store, corpus, PROFILE, embed=AsyncMock(side_effect=fake_result))
        store.metadata["status"] = "BUILDING"
        embed = AsyncMock(side_effect=AssertionError("Committed vectors must be reused."))
        result = await index_corpus(store, corpus, PROFILE, embed=embed)
        self.assertEqual(result["embeddedRecords"], 0)
        self.assertEqual(result["reusedEmbeddings"], 3)
        self.assertEqual(store.state()["status"], "READY")
        embed.assert_not_awaited()

    async def test_incompatible_model_digest_dimensions_and_format_are_rejected(self):
        corpus = synthetic_corpus()
        store = MemoryStore()
        await index_corpus(store, corpus, PROFILE, embed=AsyncMock(side_effect=fake_result))
        before = store.cache()
        for profile in (
            ModelProfile(PROFILE.model, "changed-digest", 3),
            ModelProfile(PROFILE.model, PROFILE.digest, 4),
            ModelProfile(PROFILE.model, PROFILE.digest, 3, query_instruction="Different formatting."),
        ):
            with self.subTest(profile=profile):
                embed = AsyncMock()
                with self.assertRaises(RagError) as caught:
                    await index_corpus(store, corpus, profile, embed=embed)
                self.assertEqual(caught.exception.code, "INCOMPATIBLE_INDEX")
                embed.assert_not_awaited()
        self.assertEqual(store.cache(), before)

    async def test_invalid_vectors_do_not_commit_a_batch(self):
        store = MemoryStore()
        invalid = EmbeddingResult(PROFILE.model, [[0, 0, 0]], 1, None, None)
        with self.assertRaises(RagError):
            await index_corpus(store, synthetic_corpus(1), PROFILE, embed=AsyncMock(return_value=invalid))
        self.assertEqual(store.data, {})
        self.assertEqual(store.state()["status"], "BUILDING")

    async def test_model_digest_change_during_embedding_cannot_commit_the_batch(self):
        store = MemoryStore()
        check = AsyncMock(side_effect=[None, RagError("INCOMPATIBLE_INDEX", "Synthetic model replacement.")])
        with self.assertRaises(RagError):
            await index_corpus(store, synthetic_corpus(1), PROFILE, embed=AsyncMock(side_effect=fake_result), check_identity=check)
        self.assertEqual(store.data, {})


class CorpusAndSqlSafetyTests(unittest.TestCase):
    def test_actual_corpus_is_validated_and_duplicate_flex_identifiers_remain_distinct(self):
        corpus = load_corpus(mode="flex")
        self.assertEqual(len(corpus.records), 274)
        repeated = [record for record in corpus.records if record["fields"]["FLEX Identifier"] == "193F001"]
        self.assertEqual({record["sourceTestId"] for record in repeated}, {"70", "73"})
        self.assertNotEqual(record_key(repeated[0]), record_key(repeated[1]))
        self.assertTrue(all("experimentId" not in record for record in corpus.records))

    def test_backend_and_system_schema_names_are_rejected(self):
        for name in ("public", "backend", "pg_catalog", "pyrosphere_rag;DROP SCHEMA public", "rag;DROP SCHEMA public"):
            with self.subTest(name=name), self.assertRaises(RagError):
                DatabaseSettings("postgresql://example", name)

    def test_missing_database_url_is_explicit(self):
        with self.assertRaises(RagError) as caught:
            DatabaseSettings("")
        self.assertEqual(caught.exception.code, "DATABASE_NOT_CONFIGURED")

    def test_filter_values_are_bound_parameters(self):
        malicious = "Methanol' OR true --"
        clause, parameters = filter_clause({"source_ids": ["source"], "investigation_ids": ["PSI-69"], "fuel": malicious})
        rendered = clause.as_string()
        self.assertNotIn(malicious, rendered)
        self.assertIn('"source_id" = ANY(%s)', rendered)
        self.assertIn('"investigation_id" = ANY(%s)', rendered)
        self.assertIn('"fuel" = %s', rendered)
        self.assertEqual(parameters[-1], malicious)
        with self.assertRaises(RagError):
            filter_clause({"unknown_filter": "value"})

    def test_invalid_pgvector_components_are_rejected(self):
        for vector in ([0, 0, 0], [1, 2], [True, 0, 1], [float("nan"), 0, 1], [10 ** 1000, 0, 1]):
            with self.subTest(vector_type=type(vector[0]).__name__), self.assertRaises(RagError):
                vector_literal(vector, 3)
