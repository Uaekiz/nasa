import json
import re
import unittest
from unittest.mock import AsyncMock, patch

import httpx
from app.main import app
from app.answer_evidence import render_validated_answer
from app.rag_corpus import load_corpus
from app.retrieval import plan_query, RetrievalFilters
from app.rag_config import RagError
from app.source_catalog import profile_for


class SourceNarrativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.corpus = load_corpus(mode="multi")

    def record(self, investigation, test, source_type="CSV"):
        return next(r for r in self.corpus.records if r["investigationId"] == investigation and r["sourceTestId"] == test and r["sourceType"] == source_type)

    def render(self, record, headers):
        data = json.dumps({"records": {"S1": {h: record["fields"][h] for h in headers}}})
        text, warnings = render_validated_answer(data, [record], headers)
        # Every rendered sentence ends at its own citation, including missingness.
        self.assertTrue(text.endswith("[S1]"))
        self.assertNotRegex(text, r"[.!?] (?!\[S1\])")
        return text, warnings

    def test_flex_values_units_identity_and_approximation_match_source_cells(self):
        record = self.record("PSI-69", "70")
        text, _ = self.render(record, ("Fuel", "Test end", "Burn time; s", "Burning rate; mm"))
        self.assertIn("FLEX test 70 (FLEX Identifier 193F001) used Heptane. [S1]", text)
        self.assertIn("outcome was Extinction, and the reported burn time was 1.6 s. [S1]", text)
        self.assertIn("column records 0.41; its rate unit is ambiguous", text)
        self.assertNotIn("mm/s", text)
        approx = next(r for r in self.corpus.records if r["investigationId"] == "PSI-69" and r["fields"]["Burn time; s"] == "~6")
        text, _ = self.render(approx, ("Fuel", "Burn time; s"))
        self.assertIn("recorded as ~6 s", text)
        self.assertNotRegex(text, r"(?<!~)\b6 s")

    def test_same_partial_dates_and_undefined_terms_are_not_expanded(self):
        text, _ = self.render(self.record("PSI-101", "51a"), ("Sample Type", "Date", "Inlet velocity (cm/s)", "Rt/R0"))
        self.assertIn("date is recorded as 22-Jul; no year is given in the source. [S1]", text)
        self.assertNotRegex(text, r"\b(?:19|20)\d{2}\b")
        self.assertIn("cm/s. [S1]", text)
        self.assertIn("Rt/R0 value was recorded as", text)
        for invented in ("radius ratio", "temperature", "because", "risk", "recommend"):
            self.assertNotIn(invented, text.lower())

    def test_bass_raw_material_qualifiers_and_workbook_provenance_remain_distinct(self):
        csv = self.record("PSI-25", "B1")
        workbook = self.record("PSI-25", "B1", "XLSX")
        for record in (csv, workbook):
            material = "Material" if record["sourceType"] == "XLSX" else "Fuel Sample Material"
            text, _ = self.render(record, (material, "Final CO (ppm)"))
            self.assertIn(record["fields"][material], text)
            self.assertIn("6 ppm", text)
            self.assertEqual("Bhattacharjee worksheet, row 2" in text, record["sourceType"] == "XLSX")
        record = next(r for r in self.corpus.records if r["investigationId"] == "PSI-25" and any(v.startswith(">") for v in r["fields"].values()))
        header = next(h for h, v in record["fields"].items() if v.startswith(">"))
        text, _ = self.render(record, (header,))
        self.assertIn(record["fields"][header], text)

    def test_saffire_only_reports_real_conditions_and_keeps_missing_measurements(self):
        record = self.record("PSI-100", "S1")
        text, warnings = self.render(record, ("Material", "Sample Thickness", "Sample Length", "Sample Width", "Air Flow ", "Direction"))
        for value in (".33 cm", "94 cm", "40.6 cm", "30 cm/s", "Concurrent "):
            self.assertIn(value, text)
        self.assertIn("does not provide burn time, burning rate or a measured outcome. [S1]", text)
        self.assertIn("CONDITIONS_ONLY_SOURCE", [w["code"] for w in warnings])
        self.assertNotRegex(text, r"\b(?:flame|temperature|risk|prediction|recommendation)\b")

    def test_exact_validator_remains_mandatory_before_narrative(self):
        record = self.record("PSI-101", "51a")
        for forged in ("22-Jul-2014", "22 July", "22-Jul because airflow increased"):
            with self.assertRaises(RagError):
                render_validated_answer(json.dumps({"records": {"S1": {"Date": forged}}}), [record], ("Date",))

    def test_all_643_source_summaries_preserve_original_nonmissing_cells_and_citations(self):
        for record in self.corpus.records:
            headers = profile_for(record)["summary"]
            data = json.dumps({"records": {"S1": {h: record["fields"][h] for h in headers}}})
            text, _ = render_validated_answer(data, [record], headers)
            for header in headers:
                raw = record["fields"][header]
                if raw.strip().casefold() not in {"", "none", "n/a", "na", "-", "–", "—"}:
                    self.assertIn(raw, text, (record["sourceId"], record["rowNumber"], header))
            self.assertEqual(set(re.findall(r"\[(S\d+)\]", text)), {"S1"})


class NarrativeScopeTests(unittest.IsolatedAsyncioTestCase):
    async def test_conflicting_question_and_scope_cannot_silently_answer_another_study(self):
        corpus = load_corpus(mode="multi")
        for question, investigation in (("Show FLEX test 70.", "PSI-25"), ("Show SAME-R test 51a.", "PSI-69"), ("Show SAFFIRE-III sample S1.", "PSI-101")):
            plan = plan_query(question, corpus, RetrievalFilters(investigation_ids=(investigation,)))
            self.assertEqual(plan.route, "INSUFFICIENT_EVIDENCE")
            with patch("app.answer_service.retrieve_for_answer", new=AsyncMock(return_value={"route": plan.route, "reason": plan.reason, "matches": []})), patch("app.ollama_client.generate_answer", new_callable=AsyncMock) as generate:
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                    response = await client.post("/rag/v1/answer", json={"requestId": "00000000-0000-4000-8000-000000000001", "question": question, "investigationIds": [investigation]})
                body = response.json()
                self.assertEqual(body["status"], "INSUFFICIENT_EVIDENCE")
                self.assertEqual(body["sources"], [])
                self.assertIsNone(body["modelUsed"])
                generate.assert_not_called()
