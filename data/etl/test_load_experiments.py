"""Run with python -m unittest discover -s data/etl -v.

Set PYROSPHERE_IMPORT_TEST_DB=1 to also use disposable schemas in the configured DB.
Only those generated schemas are removed; core and RAG data are never changed.
"""
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch
import uuid

import psycopg
from psycopg import sql

import load_experiments as etl


class CellTests(unittest.TestCase):
    def test_partial_dates_never_acquire_a_year(self):
        from datetime import date
        self.assertIsNone(etl.parse_date_value("21-Jul"))
        self.assertIsNone(etl.parse_date_value("22-Jul"))
        self.assertIsNone(etl.parse_date_value(""))
        self.assertEqual(etl.parse_date_value("3/5/2009"), date(2009, 3, 5))

    def test_missing_cells_never_become_numbers_and_keep_original_text(self):
        for raw in ("", " n/a ", "none", "–", "—", "-"):
            with self.subTest(raw=raw):
                parsed = etl.convert_measurement(etl.parse_cell(raw), "mmHg_to_kPa")
                self.assertEqual(parsed["quality_status"], "MISSING")
                self.assertEqual(parsed["raw_value"], raw)
                for key in ("value", "start_value", "end_value", "min_value", "max_value"):
                    self.assertIsNone(parsed[key])

    def test_qualifiers_and_unknown_cells_are_preserved(self):
        for raw, qualifier in (("~6", "APPROXIMATE"), (">500", "GREATER_THAN"),
                               ("11 to 3", "CHANGING"), ("1.5 - 5", "RANGE")):
            self.assertEqual(etl.parse_cell(raw)["qualifier"], qualifier)
        self.assertEqual(etl.parse_cell("insignificant")["quality_status"], "REQUIRES_REVIEW")

    def test_source_and_rag_provenance_match_without_writing_rag_files(self):
        before = etl.SOURCE_MANIFEST.read_bytes()
        manifest, records = etl.prepare_flex()
        self.assertEqual(len(records), 274)
        self.assertEqual([r["rowNumber"] for r in records], list(range(2, 276)))
        self.assertEqual(manifest["investigations"][0]["sources"][0]["sourceId"], records[0]["sourceId"])
        self.assertEqual(etl.SOURCE_MANIFEST.read_bytes(), before)


@unittest.skipUnless(os.getenv("PYROSPHERE_IMPORT_TEST_DB") == "1", "isolated DB tests are opt-in")
class ImportTransactionTests(unittest.TestCase):
    def setUp(self):
        self.schema = "flex_import_test_" + uuid.uuid4().hex
        self.conn = psycopg.connect(**etl.DB_CONFIG, autocommit=True, connect_timeout=5)
        self.addCleanup(self.cleanup_schema)
        self.conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(self.schema)))
        ddl = (etl.ROOT / "backend/src/main/resources/db/migration/V2__data_model.sql").read_text(encoding="utf-8")
        self.conn.execute(ddl.replace("core.", self.schema + "."))
        schema = self.schema

        class IsolatedCursor(psycopg.Cursor):
            def execute(self, query, params=None, **kwargs):
                if isinstance(query, str):
                    query = query.replace("core.", schema + ".")
                return super().execute(query, params, **kwargs)

        self.conn.cursor_factory = IsolatedCursor
        self.manifest, self.records = etl.prepare_flex()

    def cleanup_schema(self):
        # An Identifier quotes the exact UUID schema created by this test.
        self.conn.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(self.schema)))
        self.conn.close()

    def snapshot(self):
        with self.conn.cursor() as cur:
            tables = ("investigations", "sources", "experiments", "experiment_measurements",
                      "reported_findings", "experiment_warnings", "experiment_id_sequence")
            counts = {}
            for table in tables:
                cur.execute(f"SELECT count(*) FROM core.{table}")
                counts[table] = cur.fetchone()[0]
            cur.execute("SELECT experiment_id, row_fingerprint, source_row_number FROM core.experiments ORDER BY experiment_id")
            identities = cur.fetchall()
            cur.execute("SELECT last_value FROM core.experiment_id_sequence ORDER BY investigation_id")
            return counts, identities, cur.fetchall()

    def test_twice_keeps_counts_ids_sequence_and_all_original_cells(self):
        first = etl.import_flex(self.conn, self.manifest, self.records)
        before = self.snapshot()
        second = etl.import_flex(self.conn, self.manifest, self.records)
        self.assertEqual(first, {"created": 274, "updated": 0, "rows": 274})
        self.assertEqual(second, {"created": 0, "updated": 274, "rows": 274})
        self.assertEqual(before, self.snapshot())
        self.assertEqual(before[0]["experiment_measurements"], 274 * 9)
        self.assertEqual(before[2], [(274,)])
        with self.conn.cursor() as cur:
            cur.execute("SELECT source_row_number, source_test_id, raw_row FROM core.experiments ORDER BY source_row_number")
            for (row_number, test_id, raw_row), record in zip(cur.fetchall(), self.records, strict=True):
                self.assertEqual(row_number, record["rowNumber"])
                self.assertEqual(test_id, record["sourceTestId"])
                self.assertEqual(raw_row, list(record["fields"].values()))
            cur.execute("SELECT DISTINCT investigation_id FROM core.investigations")
            self.assertEqual(cur.fetchall(), [("PSI-69",)])
            cur.execute("SELECT metadata FROM core.sources")
            self.assertEqual(cur.fetchone()[0]["headers"], list(self.records[0]["fields"]))
            cur.execute("SELECT count(*) FROM core.experiment_measurements WHERE name = 'Burning rate' AND quality_status = 'VERIFIED'")
            self.assertEqual(cur.fetchone()[0], 0)
            cur.execute("SELECT count(*) FROM core.experiment_measurements WHERE unit = 'mm/s'")
            self.assertEqual(cur.fetchone()[0], 0)
            cur.execute("SELECT count(*) FROM core.experiment_measurements WHERE quality_status = 'MISSING' AND value IS NOT NULL")
            self.assertEqual(cur.fetchone()[0], 0)
            for record in (self.records[0], self.records[23], self.records[39], self.records[-1]):
                cur.execute("SELECT experiment_id FROM core.experiments WHERE source_row_number = %s", (record["rowNumber"],))
                experiment_id = cur.fetchone()[0]
                cur.execute("SELECT name, raw_value, value, unit, original_value, conversion_method FROM core.experiment_measurements WHERE experiment_id = %s ORDER BY display_order", (experiment_id,))
                for measurement, spec in zip(cur.fetchall(), etl.DATASETS["PSI-69"]["conditions"] + etl.DATASETS["PSI-69"]["measurements"], strict=True):
                    self.assertEqual(measurement[1], record["fields"][spec["header"]])
                    if spec["name"] == "Ambient pressure":
                        self.assertAlmostEqual(measurement[2], float(measurement[1]) * 0.133322, places=6)
                        self.assertEqual(measurement[4], float(measurement[1]))
                        self.assertIn("mmHg", measurement[5])

    def test_error_rolls_back_catalog_ids_and_partially_written_measurements(self):
        insert = etl.insert_measurement
        calls = 0

        def fail_midway(*args):
            nonlocal calls
            calls += 1
            if calls == 13:
                args[0].execute("SELECT 1 / 0")
            return insert(*args)

        empty = self.snapshot()
        with patch.object(etl, "insert_measurement", side_effect=fail_midway):
            with self.assertRaises(psycopg.errors.DivisionByZero):
                etl.import_flex(self.conn, self.manifest, self.records)
        self.assertEqual(self.snapshot(), empty)
        etl.import_flex(self.conn, self.manifest, self.records)
        before = self.snapshot()
        calls = 0
        with patch.object(etl, "insert_measurement", side_effect=fail_midway):
            with self.assertRaises(psycopg.errors.DivisionByZero):
                etl.import_flex(self.conn, self.manifest, self.records)
        self.assertEqual(self.snapshot(), before)

    def test_source_mapping_conflict_is_rejected_without_new_identity(self):
        etl.import_flex(self.conn, self.manifest, self.records)
        before = self.snapshot()
        changed = json.loads(json.dumps(self.records))
        changed[0]["fields"]["Fuel"] = "changed-test-only"
        with self.assertRaisesRegex(ValueError, "Source identity conflict"):
            etl.import_flex(self.conn, self.manifest, changed)
        self.assertEqual(self.snapshot(), before)

    def test_allocator_respects_existing_ids_when_sequence_is_behind(self):
        etl.import_flex(self.conn, self.manifest, self.records)
        self.conn.execute("UPDATE core.experiment_id_sequence SET last_value = 0")
        with self.conn.transaction():
            with self.conn.cursor() as cur:
                self.assertEqual(etl.next_experiment_id(cur, "PSI-69"), "PSI-69:run-0275")


if __name__ == "__main__":
    unittest.main()
