from copy import deepcopy
import json
import unittest
from unittest.mock import AsyncMock

from app.answer_evidence import assess_coverage, fields_for, generation_input, render_validated_answer, build_sources
from app.rag_config import RagError
from app.rag_corpus import Corpus, content_hash, load_corpus, record_key
from app.retrieval import plan_query, RetrievalFilters
from app.indexing import index_corpus
from rag_test_support import MemoryStore
from test_rag_indexing import PROFILE, fake_result


class MultiSourceEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.corpus = load_corpus(mode="multi")

    def result(self, question, inv):
        plan = plan_query(question, self.corpus, RetrievalFilters(investigation_ids=(inv,)))
        store = MemoryStore()
        store.data = {record_key(r): {"record": r} for r in self.corpus.records}
        matches = store.search(plan.filters) if plan.route in {"EXACT_ID", "SEMANTIC"} else []
        return {"route": plan.route, "filters": plan.filters, "matches": matches,
                "eligibleRecordCount": len(store.selected(plan.filters)) if matches else 0, "reason": plan.reason}

    def test_counts_original_cells_and_sheet_row_identity(self):
        from collections import Counter
        self.assertEqual(Counter(r["investigationId"] for r in self.corpus.records),
                         {"PSI-69": 274, "PSI-25": 258, "PSI-100": 2, "PSI-101": 109})
        self.assertEqual(len(self.corpus.by_key), 643)
        workbook = [r for r in self.corpus.records if r["sourceType"] == "XLSX" and r["rowNumber"] == 2]
        self.assertEqual(len(workbook), 6)
        self.assertEqual(len({record_key(r) for r in workbook}), 6)
        self.assertIn("Actual Date", next(iter(workbook[0]["fields"])))
        self.assertIn("A2", workbook[0]["originalCells"])

    def test_each_investigation_and_source_are_filtered_before_search(self):
        for inv, question in [("PSI-69", "Summarize FLEX test 70."), ("PSI-25", "Show BASS-II test B1."),
            ("PSI-25", "Show BASS-II workbook test B1."), ("PSI-100", "Show SAFFIRE-III sample S1."),
            ("PSI-101", "Show SAME-R test 51a.")]:
            with self.subTest(question=question):
                result = self.result(question, inv)
                self.assertEqual(assess_coverage(question, result).status, "ANSWERED")
                self.assertEqual(len(result["matches"]), 1)
                self.assertTrue(all(m["record"]["investigationId"] == inv for m in result["matches"]))
                self.assertEqual(result["matches"][0]["record"]["sourceType"], "XLSX" if "workbook" in question else "CSV")

    def test_mixed_sources_use_separate_original_field_schemas_and_citations(self):
        question = "Show BASS-II test B1 from CSV and workbook."
        result = self.result(question, "PSI-25")
        records = [m["record"] for m in result["matches"]]
        self.assertEqual(len(records), 2)
        coverage = assess_coverage(question, result)
        self.assertEqual(coverage.status, "ANSWERED")
        self.assertIsInstance(coverage.required_fields, dict)
        output = {"records": {f"S{i}": {h: r["fields"][h] for h in fields_for(coverage.required_fields, i)} for i,r in enumerate(records,1)}}
        text, warnings = render_validated_answer(json.dumps(output), records, coverage.required_fields)
        self.assertIn("Bhattacharjee worksheet, row 2", text)
        self.assertIn("INDEPENDENT_WORKBOOK_SOURCE", [w["code"] for w in warnings])
        self.assertEqual(build_sources(records)[1]["sheetName"], "Bhattacharjee")
        _, schema = generation_input(question, records, coverage.required_fields)
        self.assertNotEqual(schema["properties"]["records"]["properties"]["S1"], schema["properties"]["records"]["properties"]["S2"])
        # A numerically/semantically similar value from the other source is still a forgery.
        output["records"]["S1"]["Fuel Sample Material"] = records[1]["fields"]["Material"]
        with self.assertRaises(RagError): render_validated_answer(json.dumps(output), records, coverage.required_fields)

    def test_unsupported_investigations_fields_causes_and_numeric_analysis_stay_closed(self):
        for question in ("Show SAFFIRE-I sample S1.", "Show BASS-I test 1.", "Show FLEX-2 test 1."):
            self.assertEqual(plan_query(question, self.corpus).route, "INSUFFICIENT_EVIDENCE")
        for inv, question in [("PSI-100", "Show SAFFIRE-III sample S1 burn time."),
            ("PSI-25", "Why did BASS-II test B1 burn?"), ("PSI-101", "Recommend fire protection for SAME-R test 51.")]:
            self.assertEqual(assess_coverage(question, self.result(question, inv)).status, "INSUFFICIENT_EVIDENCE")
        self.assertEqual(plan_query("Which BASS-II test has the highest final CO?", self.corpus).route, "STRUCTURED_ANALYSIS_REQUIRED")
        result = self.result("Show FLEX test 70.", "PSI-25")
        self.assertFalse(result["matches"])

    def test_material_filter_uses_original_field_for_each_investigation(self):
        plan = plan_query("Show SAME-R test 51a.", self.corpus, RetrievalFilters(investigation_ids=("PSI-101",), fuel="Kapton"))
        self.assertEqual(plan.filters["fuel"], "Kapton")
        with self.assertRaises(RagError):
            plan_query("Show SAME-R test 51a.", self.corpus, RetrievalFilters(investigation_ids=("PSI-101",), fuel="Methanol"))

    def test_multiple_investigations_preserve_their_own_fields(self):
        question = "Show FLEX test 70 and BASS-II test B1."
        plan = plan_query(question, self.corpus, RetrievalFilters(investigation_ids=("PSI-69", "PSI-25")))
        self.assertEqual(plan.route, "EXACT_ID")
        records = [r for r in self.corpus.records if r["sourceId"] in plan.filters["source_ids"] and r["sourceTestId"] in plan.filters["test_ids"]]
        self.assertEqual({r["investigationId"] for r in records}, {"PSI-69", "PSI-25"})
        coverage = assess_coverage(question, {"route": plan.route, "filters": plan.filters, "matches": [{"record": r} for r in records], "eligibleRecordCount": 2})
        self.assertEqual(coverage.status, "ANSWERED")
        self.assertIsInstance(coverage.required_fields, dict)


class SnapshotScopeTests(unittest.IsolatedAsyncioTestCase):
    async def test_partial_source_snapshots_cannot_prune_other_investigations(self):
        corpus = load_corpus(mode="multi")
        store = MemoryStore()
        await index_corpus(store, corpus, PROFILE, embed=AsyncMock(side_effect=fake_result))
        before = deepcopy(store.cache())
        flex = [r for r in corpus.records if r["investigationId"] == "PSI-69"]
        partial = Corpus(flex, corpus.manifest, content_hash(flex))
        with self.assertRaises(RagError) as caught:
            await index_corpus(store, partial, PROFILE, embed=AsyncMock(side_effect=AssertionError("must not embed")))
        self.assertEqual(caught.exception.code, "INCOMPLETE_SOURCE_SCOPE")
        self.assertEqual(store.cache(), before)
        self.assertEqual(store.state()["status"], "READY")


class CapabilitiesTests(unittest.IsolatedAsyncioTestCase):
    async def test_capabilities_use_the_ready_index_and_its_actual_sources(self):
        import httpx
        from unittest.mock import MagicMock, patch
        from app.main import app
        store = MagicMock()
        store.lock.return_value.__enter__.return_value = None
        corpus = load_corpus(mode="multi")
        with patch("app.rag_corpus.load_corpus", return_value=corpus), patch("app.vector_store.open_store") as opened:
            opened.return_value.__enter__.return_value = store
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get("/rag/v1/capabilities")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["language"], "en")
        self.assertEqual(len(body["items"]), 4)
        bass = next(i for i in body["items"] if i["investigationId"] == "PSI-25")
        self.assertEqual(bass["evidenceRows"], 258)
        self.assertEqual(len(bass["sourceIds"]), 2)
        self.assertIn("Show BASS-II workbook test B1.", bass["examples"])
        store.ready.assert_called_once_with(corpus)

    async def test_unready_capabilities_never_return_a_static_catalog(self):
        import httpx
        from unittest.mock import patch
        from app.main import app
        with patch("app.rag_corpus.load_corpus", side_effect=RagError("STALE_INDEX", "Not ready")):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get("/rag/v1/capabilities")
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("items", response.json())
