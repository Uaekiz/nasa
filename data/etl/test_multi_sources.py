import os
import unittest

import load_experiments as etl
import test_load_experiments as flex_tests


@unittest.skipUnless(os.getenv("PYROSPHERE_IMPORT_TEST_DB") == "1", "isolated DB tests are opt-in")
class MultiSourceImportTests(unittest.TestCase):
    setUp = flex_tests.ImportTransactionTests.setUp
    cleanup_schema = flex_tests.ImportTransactionTests.cleanup_schema
    snapshot = flex_tests.ImportTransactionTests.snapshot

    def test_all_sources_twice_preserve_flex_ids_and_independent_workbook_cells(self):
        etl.import_flex(self.conn, self.manifest, self.records)
        flex_ids = self.snapshot()[1]
        manifest, records = etl.prepare_verified(list(etl.DATASETS))
        first = etl.import_verified(self.conn, manifest, records)
        before = self.snapshot()
        second = etl.import_verified(self.conn, manifest, records)
        self.assertEqual(first["PSI-25"]["created"], 129)
        self.assertEqual(first["PSI-101"]["created"], 109)
        self.assertEqual(first["PSI-100"]["created"], 2)
        self.assertTrue(all(s["created"] == 0 for s in second.values()))
        self.assertEqual(before, self.snapshot())
        self.assertEqual([r for r in before[1] if r[0].startswith("PSI-69:")], flex_ids)
        with self.conn.cursor() as cur:
            cur.execute("SELECT investigation_id,count(*) FROM core.experiments GROUP BY investigation_id ORDER BY investigation_id")
            self.assertEqual(dict(cur.fetchall()), {"PSI-69": 274, "PSI-25": 129, "PSI-100": 2, "PSI-101": 109})
            cur.execute("SELECT source_id,sheet_name,row_number,headers,raw_cells,original_cells FROM core.experiment_source_rows")
            rows = {(r[0],r[1],r[2]): r for r in cur.fetchall()}
            self.assertEqual(len(rows), 643)
            for source_records in records.values():
                for record in source_records:
                    row = rows[(record["sourceId"],record.get("sheetName", ""),record["rowNumber"])]
                    self.assertEqual(row[3], list(record["fields"]))
                    self.assertEqual(row[4], list(record["fields"].values()))
                    self.assertEqual(row[5], record.get("originalCells"))
            cur.execute("SELECT count(*) FROM core.experiment_measurements m JOIN core.experiments e USING (experiment_id) WHERE e.investigation_id='PSI-100' AND m.category='MEASUREMENT'")
            self.assertEqual(cur.fetchone()[0], 0)
            cur.execute("SELECT experiment_date,date_raw FROM core.experiments WHERE investigation_id='PSI-101'")
            self.assertTrue(all(date is None and raw for date,raw in cur.fetchall()))
            cur.execute("SELECT count(*) FROM core.reported_findings WHERE source_id='PSI-25:test-matrix:v1'")
            self.assertEqual(cur.fetchone()[0], 129)
            cur.execute("SELECT count(*) FROM core.experiment_measurements WHERE value<0 AND quality_status='VERIFIED'")
            self.assertEqual(cur.fetchone()[0], 0)

    def test_failed_workbook_link_rolls_back_all_new_investigations(self):
        from copy import deepcopy
        manifest, records = etl.prepare_verified(list(etl.DATASETS))
        records = deepcopy(records)
        records["PSI-25:test-matrix:v1"][0]["sheetName"] = "Wrong investigator"
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, "investigator"):
            etl.import_verified(self.conn, manifest, records)
        self.assertEqual(before, self.snapshot())
