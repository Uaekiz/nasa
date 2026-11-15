"""Scenario inputs, English deterministic comparisons and honest model fallback."""
import json
import unittest
from unittest.mock import AsyncMock, patch

import httpx
from app.main import app
from app.rag_config import RagError
from app.scenario_evidence import find_scenario_evidence
from app.scenario_narrative import build_next_checks, explain_scenario
from test_scenario_evidence import PARAMS


class ScenarioNarrativeTests(unittest.IsolatedAsyncioTestCase):
    def evidence(self, **params):
        return find_scenario_evidence("SIBAL Fabric", {**PARAMS, "material": "SIBAL Fabric", **params})

    async def test_model_orders_only_existing_check_ids_and_cannot_write_wrong_comparison_prose(self):
        evidence = self.evidence()
        order = list(reversed(build_next_checks(evidence)))
        with patch("app.scenario_narrative.generate_answer", new=AsyncMock(return_value=json.dumps({"checkOrder": order}))) as model:
            result = await explain_scenario(evidence, PARAMS)
        self.assertEqual(result["status"], "MODEL_ORDERED_CHECKS")
        self.assertIsNotNone(result["modelUsed"])
        self.assertEqual(result["modelRole"], "ORDERED_CHECK_IDS_ONLY")
        self.assertIn("did not write the observations", result["message"])
        self.assertEqual([check["text"] for check in result["nextChecks"]], [build_next_checks(evidence)[key]["text"] for key in order])
        self.assertIn("controlled English", model.call_args.kwargs["system_prompt"])
        ids = {version["citationId"] for source in evidence["sources"] for version in (source, *source["alternateRecords"])}
        self.assertTrue(all(set(point["citationIds"]) <= ids for point in result["observations"] + result["nextChecks"]))

    async def test_comparison_text_keeps_high_low_equal_and_direction_deterministic(self):
        for value, phrase in ((16, "14 cm/s lower"), (30, "numeric values are equal"), (35, "5 cm/s higher")):
            evidence = self.evidence(airflowCmS=value)
            with patch("app.scenario_narrative.generate_answer", new=AsyncMock(side_effect=RagError("OLLAMA_UNAVAILABLE", "test"))):
                result = await explain_scenario(evidence, {**PARAMS, "airflowCmS": value})
            saffire = [point["text"] for point in result["observations"] if point["citationIds"] == ["S1"]]
            self.assertTrue(any(phrase in text for text in saffire), saffire)
            self.assertTrue(any("label matches" in text for text in saffire))
            self.assertEqual(result["status"], "DETERMINISTIC")
            self.assertIsNone(result["modelUsed"])
            self.assertIn("OLLAMA_UNAVAILABLE", result["fallbackReason"])

    async def test_invalid_duplicate_or_fabricated_model_output_never_replaces_source_text(self):
        evidence = self.evidence()
        default_order = list(build_next_checks(evidence).values())
        for output in ('{"checkOrder":["invented"]}', '{"checkOrder":[],"cause":"low oxygen"}',
                       '{"checkOrder":[],"checkOrder":[]}', 'The scenario is safe.'):
            with patch("app.scenario_narrative.generate_answer", new=AsyncMock(return_value=output)):
                result = await explain_scenario(evidence, PARAMS)
            self.assertEqual(result["status"], "DETERMINISTIC")
            self.assertIsNone(result["modelUsed"])
            self.assertEqual(result["nextChecks"], default_order)
            self.assertIn("INVALID_MODEL_ORDER", result["fallbackReason"])
            self.assertNotIn("low oxygen", json.dumps(result))
            self.assertNotIn("scenario is safe", json.dumps(result))

    async def test_model_timeout_keeps_sources_and_deterministic_observations(self):
        evidence = self.evidence()
        with patch("app.scenario_narrative.generate_answer", new=AsyncMock(side_effect=TimeoutError())):
            result = await explain_scenario(evidence, PARAMS)
        self.assertEqual(result["status"], "DETERMINISTIC")
        self.assertTrue(result["observations"])
        self.assertIn("MODEL_TIMEOUT", result["fallbackReason"])

    async def test_no_sources_never_calls_model_or_claims_screenshot_inspection(self):
        evidence = find_scenario_evidence("unknown", {**PARAMS, "material": "unknown"})
        with patch("app.scenario_narrative.generate_answer", new_callable=AsyncMock) as model:
            result = await explain_scenario(evidence, PARAMS)
        model.assert_not_called()
        self.assertEqual(result["status"], "SKIPPED")
        self.assertEqual(result["observations"], [])


class ScenarioApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
        self.addAsyncCleanup(self.client.aclose)

    async def test_all_existing_fields_and_default_unspecified_phases_reach_evidence(self):
        params = {key: value for key, value in PARAMS.items() if not key.endswith("MeasurementPhase")}
        with patch("app.scenario_narrative.generate_answer", new=AsyncMock(side_effect=RagError("OLLAMA_UNAVAILABLE", "test"))):
            response = await self.client.post("/rag/v1/scenarios/evidence", json={"material": "PMMA Film", "params": params})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        for parameter, value in params.items():
            self.assertEqual(body["scenarioInputs"][parameter], value)
        self.assertEqual(body["scenarioInputs"]["coMeasurementPhase"], "UNSPECIFIED")
        self.assertEqual(len(body["parameterCoverage"]), 10)
        self.assertEqual(body["narrative"]["status"], "DETERMINISTIC")
        self.assertTrue(body["sources"])

    async def test_missing_invalid_nonfinite_boolean_unknown_and_conflicting_inputs_are_rejected(self):
        invalid = []
        for key in PARAMS:
            if key.endswith("MeasurementPhase"): continue
            params = dict(PARAMS)
            del params[key]
            invalid.append(params)
        for key, value in (("pressureKpa", 0), ("gravityG", -1), ("temperatureC", -274),
                           ("ignitionPowerW", -1), ("coPpm", -1), ("co2Percent", 101),
                           ("oxygenPercent", True), ("airflowCmS", "16"), ("flowDirection", "unknown"),
                           ("coMeasurementPhase", "guess"), ("material", "  "), ("unexpected", 3)):
            invalid.append({**PARAMS, key: value})
        for params in invalid:
            with patch("app.main.find_scenario_evidence") as evidence:
                response = await self.client.post("/rag/v1/scenarios/evidence", json={"material": "PMMA Film", "params": params})
            self.assertEqual(response.status_code, 400, params)
            self.assertEqual(response.json()["error"]["code"], "VALIDATION_ERROR")
            evidence.assert_not_called()
        response = await self.client.post("/rag/v1/scenarios/evidence", json={"material": "Methanol", "params": PARAMS})
        self.assertEqual(response.status_code, 400)
        for token in ("NaN", "Infinity", "-Infinity"):
            content = json.dumps({"material": "PMMA Film", "params": PARAMS}).replace('"pressureKpa": 101.3', '"pressureKpa": ' + token)
            response = await self.client.post("/rag/v1/scenarios/evidence", content=content, headers={"Content-Type": "application/json"})
            self.assertEqual(response.status_code, 400)

    async def test_model_failure_returns_successful_source_envelope_but_source_failure_is_an_error(self):
        with patch("app.main.find_scenario_evidence", side_effect=RagError("STALE_INDEX", "Reviewed source validation failed.")):
            response = await self.client.post("/rag/v1/scenarios/evidence", json={"material": "PMMA Film", "params": PARAMS})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["error"]["code"], "RAG_UNAVAILABLE")
        self.assertNotIn("sources", response.json())
