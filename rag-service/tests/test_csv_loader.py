import csv
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from app.csv_loader import (
    CsvIngestionError,
    MANIFEST_PATH,
    REPOSITORY_DIR,
    extract_records,
    save_records,
)


class FlexSourceTests(unittest.TestCase):
    def test_all_source_cells_and_row_provenance_are_preserved(self):
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        path = REPOSITORY_DIR / manifest["sourceFile"]
        before = path.read_bytes()
        rows = list(csv.reader(io.StringIO(before.decode("cp1252"), newline="")))
        records = extract_records()
        self.assertEqual(len(rows) - 1, 274)
        self.assertEqual(len(records), len(rows) - 1)
        self.assertEqual(len({(row["sourceId"], row["rowNumber"]) for row in records}), 274)
        for row_number, (record, row) in enumerate(zip(records, rows[1:], strict=True), 2):
            self.assertEqual(record["fields"], dict(zip(rows[0], row, strict=True)))
            self.assertEqual(list(record["fields"]), rows[0])
            self.assertEqual(record["sourceFile"], manifest["sourceFile"])
            self.assertEqual(record["investigationId"], "PSI-69")
            self.assertEqual(record["sourceId"], manifest["sourceId"])
            self.assertEqual(record["sourceTestId"], row[0])
            self.assertEqual(record["rowNumber"], row_number)
            self.assertNotIn("experimentId", record)
            self.assertNotIn("mm/s", record["text"])
            for header, value in zip(rows[0], row, strict=True):
                self.assertIn(f"{header}: {json.dumps(value, ensure_ascii=False)}", record["text"])
        self.assertEqual(path.read_bytes(), before)

    def test_representative_missing_values_qualifiers_and_duplicate_identifiers(self):
        records = extract_records()
        by_id = {record["sourceTestId"]: record for record in records}
        first = by_id["1"]
        self.assertEqual(first["rowNumber"], 2)
        self.assertEqual(first["fields"]["Burning rate; mm"], "0.52")
        self.assertEqual(first["fields"]["Test end"], "Disruption")
        self.assertEqual(by_id["9"]["fields"]["Test GMT"], "")
        self.assertEqual(by_id["24"]["fields"]["Droplet initial diameter; mm"], "\u2013")
        self.assertEqual(by_id["40"]["fields"]["Visible flame extinction diameter; mm"], "\u2013")
        burn_times = {record["fields"]["Burn time; s"] for record in records}
        self.assertTrue({"~6", "~9"} <= burn_times)
        repeated = [record for record in records if record["fields"]["FLEX Identifier"] == "193F001"]
        self.assertEqual(len(repeated), 2)
        self.assertNotEqual(repeated[0]["sourceTestId"], repeated[1]["sourceTestId"])
        self.assertEqual(by_id["274"]["rowNumber"], 275)
        self.assertEqual(by_id["274"]["fields"]["FLEX Identifier"], "H19H201")


class CsvSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.repository = Path(self.temporary.name)
        self.source = self.repository / "databases" / "Flex-1" / "synthetic.csv"
        self.source.parent.mkdir(parents=True)
        self.manifest_path = self.repository / "manifest.json"
        self.output_root = self.repository / "rag-service" / "data" / "processed"
        self.manifest = {
            "sourceId": "PSI-69:synthetic-test-only:v1",
            "investigationId": "PSI-69",
            "sourceType": "CSV",
            "sourceFile": "databases/Flex-1/synthetic.csv",
            "encoding": "cp1252",
            "sourceTestIdField": "FLEX Test #",
            "expectedTestCount": 1,
        }

    def set_source(self, content, *, count=1):
        data = content.encode("cp1252") if isinstance(content, str) else content
        self.source.write_bytes(data)
        self.manifest["sha256"] = hashlib.sha256(data).hexdigest()
        self.manifest["expectedTestCount"] = count
        self.manifest_path.write_text(json.dumps(self.manifest), encoding="utf-8")

    def extract(self):
        return extract_records(self.manifest_path, repository_dir=self.repository)

    def test_quoted_values_whitespace_and_units_remain_raw(self):
        self.set_source(
            'FLEX Test #,FLEX Identifier,Burning rate; mm,Note\r\n'
            '007,synthetic, >0.5 ,"n/a, \u2013; first line\nsecond line"\r\n'
        )
        record = self.extract()[0]
        self.assertEqual(record["sourceTestId"], "007")
        self.assertEqual(record["fields"]["Burning rate; mm"], " >0.5 ")
        self.assertEqual(record["fields"]["Note"], "n/a, \u2013; first line\nsecond line")
        self.assertNotIn("mm/s", record["text"])

    def test_blank_rows_do_not_create_tests_or_shift_provenance(self):
        self.set_source("FLEX Test #,FLEX Identifier\n\n1,synthetic\n,\n")
        records = self.extract()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["rowNumber"], 3)

    def test_repeated_test_ids_are_not_used_to_drop_source_rows(self):
        self.set_source("FLEX Test #,FLEX Identifier\n1,synthetic-a\n1,synthetic-b\n", count=2)
        records = self.extract()
        self.assertEqual([record["rowNumber"] for record in records], [2, 3])
        self.assertEqual([record["sourceTestId"] for record in records], ["1", "1"])

    def test_note_rows_and_missing_identifiers_are_rejected_for_review(self):
        for row in ("Footnote,synthetic", "1,", ",synthetic"):
            with self.subTest(row=row):
                self.set_source("FLEX Test #,FLEX Identifier\n" + row + "\n")
                with self.assertRaisesRegex(CsvIngestionError, "not a recognized FLEX test row"):
                    self.extract()

    def test_duplicate_headers_and_wrong_row_width_are_rejected(self):
        for content, message in (
            ("FLEX Test #,FLEX Identifier,FLEX Identifier\n1,a,b\n", "Duplicate CSV headers"),
            ("FLEX Test #,FLEX Identifier\n1,a,extra\n", "has 3 cells; expected 2"),
        ):
            with self.subTest(message=message):
                self.set_source(content)
                with self.assertRaisesRegex(CsvIngestionError, message):
                    self.extract()

    def test_missing_csv_and_wrong_encoding_have_clear_errors(self):
        self.set_source(b"FLEX Test #,FLEX Identifier\n1,\x81\n")
        with self.assertRaisesRegex(CsvIngestionError, "Cannot decode.*cp1252"):
            self.extract()
        self.source.unlink()
        with self.assertRaisesRegex(CsvIngestionError, "Cannot read source CSV.*FileNotFoundError"):
            self.extract()

    def test_changed_source_requires_manifest_review(self):
        self.set_source("FLEX Test #,FLEX Identifier\n1,synthetic\n")
        self.source.write_bytes(self.source.read_bytes() + b"\n")
        with self.assertRaisesRegex(CsvIngestionError, "SHA-256 differs from the manifest"):
            self.extract()

    def test_unexpected_record_count_is_rejected(self):
        self.set_source("FLEX Test #,FLEX Identifier\n1,synthetic\n", count=2)
        with self.assertRaisesRegex(CsvIngestionError, "Extracted 1 test records.*expects 2"):
            self.extract()

    def test_json_round_trip_is_utf8_and_rerun_does_not_duplicate_records(self):
        self.set_source("FLEX Test #,FLEX Identifier,Note\n1,synthetic,\u2013\n")
        records = self.extract()
        output = self.output_root / "records.json"
        self.assertTrue(save_records(records, output, output_root=self.output_root))
        original = output.read_bytes()
        modified = output.stat().st_mtime_ns
        self.assertIn("\u2013".encode("utf-8"), original)
        self.assertEqual(json.loads(original), records)
        self.assertFalse(save_records(self.extract(), output, output_root=self.output_root))
        self.assertEqual(output.stat().st_mtime_ns, modified)
        self.assertEqual(len(json.loads(output.read_text(encoding="utf-8"))), 1)

    def test_existing_output_and_source_are_protected(self):
        self.set_source("FLEX Test #,FLEX Identifier\n1,synthetic\n")
        records = self.extract()
        self.output_root.mkdir(parents=True)
        output = self.output_root / "records.json"
        output.write_bytes(b"Existing output must survive.")
        with self.assertRaisesRegex(CsvIngestionError, "existing file was not changed"):
            save_records(records, output, output_root=self.output_root)
        self.assertEqual(output.read_bytes(), b"Existing output must survive.")
        before = self.source.read_bytes()
        with self.assertRaisesRegex(CsvIngestionError, "inside rag-service/data/processed"):
            save_records(records, self.source, output_root=self.output_root)
        self.assertEqual(self.source.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
