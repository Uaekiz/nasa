"""Source values, units, grouping and boundaries for scenario comparisons."""
from copy import deepcopy
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from app.rag_corpus import load_corpus
from app.scenario_evidence import (
    PARAMETERS, compare_conditions, condition_order, find_scenario_evidence, record_differences,
)


PARAMS = {"oxygenPercent": 21.0, "pressureKpa": 101.3, "airflowCmS": 16.0,
          "gravityG": 0.16, "temperatureC": 23.0, "ignitionPowerW": 85.0,
          "material": "PMMA Film", "flowDirection": "CONCURRENT", "coPpm": 18.0,
          "co2Percent": 0.38, "coMeasurementPhase": "UNSPECIFIED", "co2MeasurementPhase": "UNSPECIFIED"}


class ScenarioEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.corpus = load_corpus(mode="multi")

    def record(self, inv, test, source_type="CSV"):
        return next(r for r in self.corpus.records if r["investigationId"] == inv
                    and r["sourceTestId"] == test and r["sourceType"] == source_type)

    def comparison(self, record, parameter, **patches):
        return next(item for item in compare_conditions(record, {**PARAMS, **patches}) if item["parameter"] == parameter)

    def test_all_inputs_are_accounted_for_without_missing_values_becoming_zero(self):
        record = self.record("PSI-25", "B1")
        comparisons = compare_conditions(record, PARAMS)
        self.assertEqual([item["parameter"] for item in comparisons], list(PARAMETERS))
        for parameter in ("pressureKpa", "gravityG", "temperatureC", "ignitionPowerW", "airflowCmS"):
            item = self.comparison(record, parameter)
            self.assertEqual(item["status"], "NOT_COMPARABLE")
            self.assertIsNone(item["difference"])
            self.assertIsNone(item["normalizedSourceValue"])
        self.assertIn("Fan display", self.comparison(record, "airflowCmS")["reason"])

    def test_explicit_initial_and_final_co_do_not_get_silently_interchanged(self):
        record = self.record("PSI-25", "B1")
        unspecified = self.comparison(record, "coPpm")
        self.assertEqual(unspecified["status"], "NOT_COMPARABLE")
        self.assertIsNone(unspecified["sourceValue"])
        initial = self.comparison(record, "coPpm", coMeasurementPhase="INITIAL")
        final = self.comparison(record, "coPpm", coMeasurementPhase="FINAL")
        self.assertEqual((initial["sourceField"], initial["sourceValue"], initial["difference"]), ("Initial CO (ppm)", "0", 18))
        self.assertEqual((final["sourceField"], final["sourceValue"], final["difference"]), ("Final CO (ppm)", "6", 12))
        co2 = self.comparison(record, "co2Percent", co2MeasurementPhase="FINAL")
        self.assertEqual(co2["sourceField"], "Final CO2 % by vol")
        self.assertEqual(co2["unit"], "percentage points")
        self.assertAlmostEqual(co2["difference"], -.06)

    def test_source_qualifiers_negative_readings_and_empty_cells_are_not_exact_comparisons(self):
        record = deepcopy(self.record("PSI-25", "B1"))
        for raw in ("", "–", "~6", ">500", "1 to 3", "-1"):
            record["fields"]["Final CO (ppm)"] = raw
            item = self.comparison(record, "coPpm", coMeasurementPhase="FINAL")
            self.assertEqual(item["status"], "NOT_COMPARABLE", raw)
            self.assertEqual(item["sourceValue"], raw)
            self.assertIsNone(item["difference"])

    def test_saffire_airflow_direction_and_scenario_minus_source_are_deterministic(self):
        record = self.record("PSI-100", "S1")
        lower = self.comparison(record, "airflowCmS")
        self.assertEqual(lower["sourceValue"], "30 cm/s")
        self.assertEqual(lower["difference"], -14)
        equal = self.comparison(record, "airflowCmS", airflowCmS=30)
        self.assertEqual(equal["difference"], 0)
        higher = self.comparison(record, "airflowCmS", airflowCmS=35)
        self.assertEqual(higher["difference"], 5)
        self.assertEqual(self.comparison(record, "flowDirection")["status"], "MATCH")
        self.assertEqual(self.comparison(record, "flowDirection", flowDirection="OPPOSED")["status"], "DIFFERENT")

    def test_flex_pressure_uses_the_existing_importer_conversion_but_not_ambiguous_gases(self):
        record = self.record("PSI-69", "1")
        pressure = self.comparison(record, "pressureKpa", material="Methanol")
        self.assertEqual(pressure["sourceValue"], "757.7")
        self.assertEqual(pressure["normalizedSourceValue"], 101.018079)
        self.assertEqual(pressure["difference"], .281921)
        self.assertEqual(self.comparison(record, "oxygenPercent")["status"], "NOT_COMPARABLE")
        self.assertEqual(self.comparison(record, "coPpm", coMeasurementPhase="INITIAL")["status"], "NOT_COMPARABLE")

    def test_unit_labelled_fields_can_be_compared_without_inventing_unlabelled_units(self):
        record = deepcopy(self.record("PSI-100", "S1"))
        record["fields"].update({"Gravity (g)": "0.16", "Temperature (°C)": "23", "Ignition power (W)": "85"})
        for parameter in ("gravityG", "temperatureC", "ignitionPowerW"):
            self.assertEqual(self.comparison(record, parameter)["difference"], 0)
        record["fields"]["Temperature (°C)"] = "~23"
        self.assertIsNone(self.comparison(record, "temperatureC")["difference"])

    def test_bass_order_uses_initial_oxygen_not_the_last_numeric_co_value(self):
        first = deepcopy(self.record("PSI-25", "B1"))
        second = deepcopy(first)
        first["fields"]["Calibrated  initial O2 % by vol "] = "21"
        first["fields"]["Final CO (ppm)"] = "500"
        second["fields"]["Calibrated  initial O2 % by vol "] = "30"
        second["fields"]["Final CO (ppm)"] = "18"
        params = {**PARAMS, "coMeasurementPhase": "FINAL"}
        self.assertLess(condition_order(first, params), condition_order(second, params))

    def test_primary_and_alternate_cells_keep_citations_links_differences_and_raw_storage(self):
        evidence = find_scenario_evidence("PMMA Film", PARAMS)
        source = evidence["sources"][0]
        self.assertEqual(source["sourceType"], "CSV")
        alternate = source["alternateRecords"][0]
        self.assertEqual(alternate["sourceType"], "XLSX")
        self.assertEqual(alternate["citationId"], "S1A1")
        self.assertEqual(source["documentUrl"], "/files/PSI-25_Experimental%20table_BASS-II.csv")
        self.assertEqual(alternate["documentUrl"], "/files/bass_ii_workbook.xlsx")
        self.assertTrue(source["originalUrl"].startswith("https://psi.nasa.gov/"))
        self.assertTrue(source["recordDifferences"])
        self.assertIn("Fuel Sample Material", source["fields"])
        self.assertNotIn("Material", source["fields"])
        self.assertIn("Material", alternate["fields"])
        self.assertEqual(evidence["scenarioInputs"], PARAMS)
        self.assertEqual({item["parameter"] for item in evidence["parameterCoverage"]}, set(PARAMETERS))

    def test_specimen_classes_do_not_become_each_others_flame_evidence(self):
        for material, inv, kind in (("Methanol", "PSI-69", "DROPLET"), ("Kapton", "PSI-101", "SMOKE"), ("PMMA Film", "PSI-25", "SOLID")):
            evidence = find_scenario_evidence(material, {**PARAMS, "material": material})
            self.assertTrue(evidence["sources"])
            self.assertEqual({source["investigationId"] for source in evidence["sources"]}, {inv})
            self.assertEqual({source["sourceClass"] for source in evidence["sources"]}, {kind})
        missing = find_scenario_evidence("unreviewed material", {**PARAMS, "material": "unreviewed material"})
        self.assertEqual(missing["sources"], [])
        self.assertTrue(all(item["status"] == "NO_SOURCE" for item in missing["parameterCoverage"]))

    def test_csv_and_workbook_disagreement_is_retained_even_if_only_one_material_wording_matches(self):
        primary = deepcopy(self.record("PSI-25", "B1"))
        alternate = deepcopy(self.record("PSI-25", "B1", "XLSX"))
        alternate["fields"]["Material"] = "a differently recorded material"
        with patch("app.scenario_evidence.load_corpus", return_value=SimpleNamespace(records=[primary, alternate])):
            result = find_scenario_evidence("PMMA Film", PARAMS)
        self.assertEqual(result["matchedRecordCount"], 1)
        self.assertEqual(result["matchedExperimentCount"], 1)
        self.assertEqual(len(result["sources"][0]["alternateRecords"]), 1)
        diff = next(d for d in result["sources"][0]["recordDifferences"] if d["field"] == "material")
        self.assertEqual(diff["alternateValue"], "a differently recorded material")
        self.assertFalse(result["sources"][0]["alternateRecords"][0]["materialNameMatched"])

    def test_same_test_marker_from_a_different_pi_is_not_grouped_as_an_alternate(self):
        primary = deepcopy(self.record("PSI-25", "B1"))
        other = deepcopy(self.record("PSI-25", "B1", "XLSX"))
        other["sheetName"] = "Different investigator"
        with patch("app.scenario_evidence.load_corpus", return_value=SimpleNamespace(records=[primary, other])):
            result = find_scenario_evidence("PMMA Film", PARAMS)
        self.assertEqual(result["matchedExperimentCount"], 2)
        self.assertTrue(all(not source["alternateRecords"] for source in result["sources"]))
