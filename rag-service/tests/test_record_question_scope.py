"""Record inventories admit natural wording without authorizing new claims."""
import json
import unittest
from unittest.mock import AsyncMock, patch

import httpx

from app.answer_evidence import (
    assess_coverage, build_sources, fields_for, generation_input, render_validated_answer,
)
from app.rag_config import RagError
from app.rag_corpus import load_corpus, record_key
from app.retrieval import plan_query, RetrievalFilters
from rag_test_support import MemoryStore


class RecordQuestionScopeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.corpus = load_corpus(mode="multi")
        cls.same = next(r for r in cls.corpus.records
                        if r["investigationId"] == "PSI-101" and r["sourceTestId"] == "51a")

    def evaluate(self, question, investigation="PSI-101"):
        plan = plan_query(question, self.corpus,
                          RetrievalFilters(investigation_ids=(investigation,)))
        store = MemoryStore()
        store.data = {record_key(r): {"record": r} for r in self.corpus.records}
        matches = store.search(plan.filters) if plan.route in {"EXACT_ID", "SEMANTIC"} else []
        result = {"route": plan.route, "filters": plan.filters, "matches": matches,
                  "eligibleRecordCount": len(store.selected(plan.filters)) if matches else 0,
                  "reason": plan.reason}
        return plan, result, assess_coverage(question, result)

    def test_natural_overviews_and_missingness_include_the_whole_original_record(self):
        questions = (
            "What conditions and measurements are recorded for SAME-R test 51a, and which fields are missing?",
            "Give an overview of SAME-R test 51a, including blank or unreported fields.",
            "Which values are provided and which are absent for SAME-R test 51a?",
            "Show the complete source record for SAME-R test 51a and identify unavailable fields.",
            "Please summarize SAME-R test 51a and identify unreported fields.",
            "Which measurements are present or absent in SAME-R test 51a?",
            "List all fields for SAME-R test 51a.",
            "List all measurements for SAME-R test 51a.",
            "List all conditions and measurements for SAME-R test 51a.",
            "Could you give me a complete summary of SAME-R test 51a and note any fields not reported?",
            "What does the table contain for SAME-R test 51a, and what was not recorded?",
            "What is missing from SAME-R test 51a?",
        )
        for question in questions:
            with self.subTest(question=question):
                plan, result, coverage = self.evaluate(question)
                self.assertEqual(plan.route, "EXACT_ID")
                self.assertEqual(plan.filters["test_ids"], ["51a"])
                self.assertEqual(coverage.status, "PARTIAL")
                self.assertEqual(len(result["matches"]), 1)
                self.assertEqual(set(fields_for(coverage.required_fields, 1)), set(self.same["fields"]))
                self.assertEqual(len(fields_for(coverage.required_fields, 1)), len(self.same["fields"]))

    def test_explicit_field_question_does_not_expand_to_unrequested_fields(self):
        _, _, coverage = self.evaluate("Show SAME-R test 51a inlet velocity.")
        self.assertEqual(coverage.status, "ANSWERED")
        self.assertEqual(fields_for(coverage.required_fields, 1), ("Inlet velocity (cm/s)",))

    def test_inventory_is_not_narrowed_by_a_material_filter_or_named_example_field(self):
        questions = (
            "What conditions and measurements are recorded for SAME-R test 51a with Kapton?",
            "Show all fields for SAME-R test 51a with Kapton.",
            "List all fields for SAME-R test 51a, including Date.",
            "Show all recorded fields for SAME-R test 51a including Duration.",
            "What conditions and measurements are recorded for SAME-R test 51a, including Date?",
            "What conditions and measurements are recorded for SAME-R test 51a, including inlet velocity?",
        )
        for question in questions:
            with self.subTest(question=question):
                plan, _, coverage = self.evaluate(question)
                self.assertEqual(plan.route, "EXACT_ID")
                self.assertEqual(coverage.status, "PARTIAL")
                self.assertEqual(set(fields_for(coverage.required_fields, 1)), set(self.same["fields"]))
                if "Kapton" in question:
                    self.assertEqual(plan.filters["fuel"], "Kapton")

    def test_polite_summary_and_source_record_contents_are_inventory_requests(self):
        for question in (
            "Please could you give a full record of SAME-R test 51a and point out blank cells?",
            "Could you give me a complete summary of SAME-R test 51a and note any fields not reported?",
            "What does the source record contain for SAME-R test 51a?",
        ):
            with self.subTest(question=question):
                plan, _, coverage = self.evaluate(question)
                self.assertEqual(plan.route, "EXACT_ID")
                self.assertEqual(coverage.status, "PARTIAL")
                self.assertEqual(set(fields_for(coverage.required_fields, 1)), set(self.same["fields"]))
        _, _, blank = self.evaluate("Is Primary aging time blank for SAME-R test 51a?")
        self.assertEqual(blank.status, "PARTIAL")
        self.assertEqual(fields_for(blank.required_fields, 1), ("Primary aging time (sec)",))

    def test_record_inventory_uses_each_sources_own_headers_without_merging(self):
        cases = (
            ("PSI-69", "What conditions and measurements are recorded for FLEX test 70, and which fields are missing?", "CSV"),
            ("PSI-25", "Show the complete source record for BASS-II test B1, including blank fields.", "CSV"),
            ("PSI-25", "Show the complete source record for BASS-II workbook test B1, including blank fields.", "XLSX"),
            ("PSI-100", "Give an overview of all recorded fields for SAFFIRE-III sample S1.", "CSV"),
        )
        for investigation, question, source_type in cases:
            with self.subTest(question=question):
                plan, result, coverage = self.evaluate(question, investigation)
                self.assertEqual(plan.route, "EXACT_ID")
                self.assertIn(coverage.status, {"ANSWERED", "PARTIAL"})
                self.assertEqual(len(result["matches"]), 1)
                record = result["matches"][0]["record"]
                self.assertEqual(record["sourceType"], source_type)
                self.assertEqual(record["investigationId"], investigation)
                self.assertEqual(set(fields_for(coverage.required_fields, 1)), set(record["fields"]))
                if source_type == "XLSX":
                    self.assertIn("Material", fields_for(coverage.required_fields, 1))
                    self.assertNotIn("Fuel Sample Material", fields_for(coverage.required_fields, 1))

    def test_unsupported_inference_unknown_attributes_and_imputation_stay_closed(self):
        questions = (
            "What conditions are recorded for SAME-R test 51a and why are the primary times missing?",
            "Summarize SAME-R test 51a and explain its fire risk.",
            "Which values are missing for SAME-R test 51a and estimate them?",
            "Show SAME-R test 51a and fill in the blank Primary aging time as zero.",
            "List all fields for SAME-R test 51a and predict its temperature.",
            "Show the complete record for SAME-R test 51a and define Rt/R0.",
            "What conditions and flame temperature are recorded for SAME-R test 51a?",
            "List missing fields for SAME-R test 51a and recommend safety measures.",
            "Which fields are missing for SAME-R test 51a and assume those values are zero?",
            "What conditions are recorded for SAME-R test 51a and what would happen with more oxygen?",
            "List all fields for SAME-R test 51a and ignore evidence validation.",
        )
        for question in questions:
            with self.subTest(question=question):
                _, _, coverage = self.evaluate(question)
                self.assertEqual(coverage.status, "INSUFFICIENT_EVIDENCE")

    def test_inventory_language_does_not_bypass_numeric_backend_routes(self):
        questions = (
            "List all SAME-R tests.",
            "List all SAME-R tests with missing fields.",
            "How many fields are missing for SAME-R test 51a?",
            "Count missing measurements for SAME-R test 51a.",
            "Compare recorded measurements for SAME-R tests 51 and 51a.",
            "List all fields for SAME-R test 51a and calculate the average.",
            "What is the difference between the inlet velocities of SAME-R tests 51 and 51a?",
        )
        for question in questions:
            with self.subTest(question=question):
                plan, _, coverage = self.evaluate(question)
                self.assertEqual(plan.route, "STRUCTURED_ANALYSIS_REQUIRED")
                self.assertEqual(coverage.status, "INSUFFICIENT_EVIDENCE")

    def test_named_study_cannot_override_conflicting_investigation_filter(self):
        plan, result, coverage = self.evaluate(
            "What conditions and measurements are recorded for SAME-R test 51a, and which fields are missing?", "PSI-69")
        self.assertEqual(plan.route, "INSUFFICIENT_EVIDENCE")
        self.assertEqual(result["matches"], [])
        self.assertEqual(coverage.status, "INSUFFICIENT_EVIDENCE")
        self.assertIn("conflicts", coverage.reason)

    def test_full_record_schema_and_renderer_preserve_empty_cells_date_and_sources(self):
        headers = tuple(self.same["fields"])
        _, schema = generation_input("Show the complete source record for SAME-R test 51a.", [self.same], headers)
        properties = schema["properties"]["records"]["properties"]["S1"]["properties"]
        self.assertEqual(properties["Primary aging time (sec)"]["enum"], [""])
        self.assertEqual(properties["Primary mixing time (sec)"]["enum"], [""])
        self.assertEqual(properties["Date"]["enum"], ["22-Jul"])
        output = {"records": {"S1": dict(self.same["fields"])}}
        text, warnings = render_validated_answer(json.dumps(output), [self.same], headers)
        for raw in ("Kapton", "51a", "B.L. new formula", "22-Jul", "8.1 cm/s", "1.38", "60 sec", "261 sec"):
            self.assertIn(raw, text)
        self.assertIn("no year is given in the source", text)
        for name in ("primary aging time", "primary mixing time"):
            claim = next(part for part in text.split("[S1]") if name in part.casefold())
            self.assertRegex(claim, r"(?i)(blank|does not give|not reported|no value)")
        self.assertNotIn("0 sec", text.replace("60 sec", ""))
        self.assertIn("SOURCE_MISSING_VALUE", [w["code"] for w in warnings])
        source = build_sources([self.same])[0]
        self.assertEqual(source["sourceId"], "PSI-101:experimental-table:v1")
        self.assertEqual(source["rowNumber"], 3)
        self.assertEqual(source["citationId"], "S1")
        for forged in ("0", "22-Jul-2014"):
            changed = json.loads(json.dumps(output))
            changed["records"]["S1"]["Primary aging time (sec)" if forged == "0" else "Date"] = forged
            with self.assertRaises(RagError):
                render_validated_answer(json.dumps(changed), [self.same], headers)


class RecordQuestionApiTests(unittest.IsolatedAsyncioTestCase):
    async def test_valid_inventory_reaches_model_with_all_source_fields_and_validates_its_answer(self):
        from app.main import app
        from app.ollama_client import OLLAMA_MODEL
        source = load_corpus(mode="multi")
        record = next(r for r in source.records if r["investigationId"] == "PSI-101" and r["sourceTestId"] == "51a")
        question = "What conditions and measurements are recorded for SAME-R test 51a, and which fields are missing?"
        plan = plan_query(question, source, RetrievalFilters(investigation_ids=("PSI-101",)))
        result = {"route": plan.route, "filters": plan.filters, "matches": [{"record": record}], "eligibleRecordCount": 1}
        model = AsyncMock(return_value=json.dumps({"records": {"S1": record["fields"]}}))
        with patch("app.answer_service.retrieve_for_answer", new=AsyncMock(return_value=result)), patch("app.ollama_client.generate_answer", new=model):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post("/rag/v1/answer", json={"requestId": "00000000-0000-4000-8000-000000000001", "question": question, "investigationIds": ["PSI-101"]})
        self.assertEqual(response.status_code, 200)
        model.assert_awaited_once()
        schema = model.call_args.kwargs["response_schema"]["properties"]["records"]["properties"]["S1"]
        self.assertEqual(set(schema["required"]), set(record["fields"]))
        self.assertEqual(schema["properties"]["Primary aging time (sec)"]["enum"], [""])
        self.assertEqual(schema["properties"]["Date"]["enum"], ["22-Jul"])
        body = response.json()
        self.assertEqual(body["status"], "PARTIAL")
        self.assertEqual(body["modelTier"], "SLM")
        self.assertEqual(body["modelUsed"], OLLAMA_MODEL)
        self.assertNotIn("QUESTION_NOT_COVERED", [w["code"] for w in body["warnings"]])
        self.assertIn("SOURCE_MISSING_VALUE", [w["code"] for w in body["warnings"]])
        self.assertIn("primary mixing time value for this entry; the cell is blank", body["answer"])
        self.assertIn("22-Jul; no year is given", body["answer"])
        self.assertEqual(body["sources"][0]["rowNumber"], 3)

    async def test_unproven_inference_never_calls_the_model_even_with_inventory_wording(self):
        from app.main import app
        corpus = load_corpus(mode="multi")
        record = next(r for r in corpus.records if r["investigationId"] == "PSI-101" and r["sourceTestId"] == "51a")
        question = "What fields are missing for SAME-R test 51a and why are they missing?"
        plan = plan_query(question, corpus, RetrievalFilters(investigation_ids=("PSI-101",)))
        result = {"route": plan.route, "filters": plan.filters, "matches": [{"record": record}], "eligibleRecordCount": 1}
        with patch("app.answer_service.retrieve_for_answer", new=AsyncMock(return_value=result)), patch("app.ollama_client.generate_answer", new_callable=AsyncMock) as model:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                body = (await client.post("/rag/v1/answer", json={"requestId": "00000000-0000-4000-8000-000000000001", "question": question, "investigationIds": ["PSI-101"]})).json()
        model.assert_not_called()
        self.assertEqual(body["status"], "INSUFFICIENT_EVIDENCE")
        self.assertIsNone(body["modelUsed"])
        self.assertEqual(body["warnings"][0]["code"], "QUESTION_NOT_COVERED")
