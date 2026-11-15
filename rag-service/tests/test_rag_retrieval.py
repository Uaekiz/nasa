from unittest.mock import AsyncMock, patch
import os
import unittest

from app.embedding_client import EmbeddingResult
from app.indexing import index_corpus
from app.model_profile import format_query
from app.rag_config import RagError
from app.rag_corpus import load_corpus
from app.retrieval import RetrievalFilters, plan_query, retrieve_records
from rag_test_support import MemoryStore, synthetic_corpus
from test_rag_indexing import PROFILE, fake_result


class RetrievalRoutingTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        environment = patch.dict(os.environ, {"OLLAMA_EMBEDDING_MODEL": PROFILE.model})
        environment.start()
        self.addCleanup(environment.stop)
        self.corpus = synthetic_corpus(8)
        self.store = MemoryStore()
        await index_corpus(self.store, self.corpus, PROFILE, embed=AsyncMock(side_effect=fake_result))

    async def test_exact_test_ids_bypass_embeddings(self):
        embed = AsyncMock(side_effect=AssertionError("Exact IDs must not use embedding."))
        profile_loader = AsyncMock(side_effect=AssertionError("Exact IDs must not require Ollama."))
        result = await retrieve_records("Show FLEX test #2.", self.store, self.corpus, embed=embed, profile_loader=profile_loader)
        self.assertEqual(result["route"], "EXACT_ID")
        self.assertEqual([match["record"]["sourceTestId"] for match in result["matches"]], ["2"])
        self.assertIsNone(result["matches"][0]["cosineDistance"])
        embed.assert_not_awaited()
        profile_loader.assert_not_awaited()

    async def test_duplicate_identifier_lookup_retains_both_rows(self):
        result = await retrieve_records("Show SYNTHETIC-DUP.", self.store, self.corpus)
        self.assertEqual({match["record"]["sourceTestId"] for match in result["matches"]}, {"1", "2"})

    async def test_fuel_source_and_investigation_filters_apply_before_ranking(self):
        embed = AsyncMock(return_value=EmbeddingResult(PROFILE.model, [[1, 1, 0]], 5, 4, 1))
        filters = RetrievalFilters((self.corpus.manifest["sourceId"],), ("PSI-69",), "heptane")
        question = "Find FLEX tests reported as extinction."
        result = await retrieve_records(
            question, self.store, self.corpus, filters=filters, embed=embed,
            profile_loader=AsyncMock(return_value=PROFILE),
        )
        embed.assert_awaited_once_with(format_query(question))
        self.assertEqual(len(result["matches"]), 4)
        self.assertTrue(all(match["record"]["fields"]["Fuel"] == "Heptane" for match in result["matches"]))
        self.assertEqual(self.store.search_calls[-1][0]["outcome"], "Extinction")
        self.assertFalse(result["sufficientEvidence"])
        self.assertEqual(result["status"], "CANDIDATES_ONLY")

    async def test_empty_filters_return_no_neighbors_and_do_not_embed(self):
        embed = AsyncMock()
        result = await retrieve_records(
            "Find extinction tests.", self.store, self.corpus,
            filters=RetrievalFilters(investigation_ids=("PSI-25",)), embed=embed,
        )
        self.assertEqual(result["matches"], [])
        self.assertEqual(result["status"], "INSUFFICIENT_EVIDENCE")
        embed.assert_not_awaited()

    async def test_unsupported_fabric_and_numerical_questions_never_search_or_embed(self):
        for question, status in (
            ("Describe flame spread on solid cotton fabric.", "INSUFFICIENT_EVIDENCE"),
            ("How many methanol tests are there?", "STRUCTURED_ANALYSIS_REQUIRED"),
            ("Which test has the maximum burning rate?", "STRUCTURED_ANALYSIS_REQUIRED"),
            ("Compare test 1 and test 2 numerically.", "STRUCTURED_ANALYSIS_REQUIRED"),
            ("Find oxygen fractions > 0.3.", "STRUCTURED_ANALYSIS_REQUIRED"),
            ("Which droplet burns for the most time?", "STRUCTURED_ANALYSIS_REQUIRED"),
        ):
            with self.subTest(question=question):
                embed = AsyncMock()
                result = await retrieve_records(question, None, self.corpus, embed=embed)
                self.assertEqual(result["status"], status)
                self.assertFalse(result["sufficientEvidence"])
                self.assertEqual(result["matches"], [])
                embed.assert_not_awaited()

    async def test_changed_model_digest_is_rejected_before_query_embedding(self):
        from app.model_profile import ModelProfile
        embed = AsyncMock()
        with self.assertRaises(RagError) as caught:
            await retrieve_records(
                "Find extinction records.", self.store, self.corpus, embed=embed,
                profile_loader=AsyncMock(return_value=ModelProfile(PROFILE.model, "new-digest", 3)),
            )
        self.assertEqual(caught.exception.code, "INCOMPATIBLE_INDEX")
        embed.assert_not_awaited()

    async def test_returned_values_must_match_original_source_records(self):
        key = next(iter(self.store.data))
        self.store.data[key]["record"]["fields"]["Burning rate; mm"] = "invented-value"
        with self.assertRaises(RagError) as caught:
            await retrieve_records("Show test 1.", self.store, self.corpus)
        self.assertEqual(caught.exception.code, "CORRUPT_INDEX")

    def test_actual_repeated_flex_identifier_routes_deterministically(self):
        corpus = load_corpus(mode="flex")
        plan = plan_query("Show FLEX Identifier 193F001.", corpus)
        self.assertEqual(plan.route, "EXACT_ID")
        self.assertEqual(plan.filters["flex_identifiers"], ["193F001"])

    def test_multiple_explicit_ids_and_conflicting_fuels(self):
        plan = plan_query("Show FLEX tests 70 and 73.", self.corpus)
        self.assertEqual(plan.filters["test_ids"], ["70", "73"])
        with self.assertRaises(RagError):
            plan_query("Find methanol extinction records.", self.corpus, RetrievalFilters(fuel="Heptane"))
        with self.assertRaises(RagError):
            plan_query("Find extinction records.", self.corpus, RetrievalFilters(fuel="Cotton"))


if __name__ == "__main__":
    unittest.main()
