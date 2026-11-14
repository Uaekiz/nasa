import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from app.embedding_client import EmbeddingResult
from app.embedding_smoke import EVIDENCE_PATH, MANIFEST_PATH, QUERY, load_smoke_records, run_smoke_test


class EmbeddingSmokeTests(unittest.IsolatedAsyncioTestCase):
    async def test_only_two_actual_records_and_one_query_are_submitted_without_modifying_evidence(self):
        before = EVIDENCE_PATH.read_bytes()
        manifest_before = MANIFEST_PATH.read_bytes()
        records = json.loads(before.decode("utf-8"))
        result = EmbeddingResult("test-only-model", [[1, 0], [0, 1], [1, 1]], 12.5, 10.0, 2.0)
        mock_embed = AsyncMock(return_value=result)
        with patch("app.embedding_smoke.embed_texts", mock_embed), patch("builtins.print"):
            summary = await run_smoke_test()
        mock_embed.assert_awaited_once_with([records[0]["text"], records[-1]["text"], QUERY])
        self.assertEqual(summary["inputCount"], 3)
        self.assertEqual(summary["dimensions"], [2, 2, 2])
        self.assertEqual(summary["elapsedMs"], 12.5)
        for descriptor, record in zip(summary["evidence"], (records[0], records[-1]), strict=True):
            for key, value in descriptor.items():
                self.assertEqual(value, record[key])
            self.assertNotIn("experimentId", descriptor)
        self.assertEqual(EVIDENCE_PATH.read_bytes(), before)
        self.assertEqual(MANIFEST_PATH.read_bytes(), manifest_before)

    async def test_provenance_mismatch_is_rejected_before_embedding(self):
        with tempfile.TemporaryDirectory() as directory:
            evidence = Path(directory) / "evidence.json"
            manifest = Path(directory) / "manifest.json"
            records = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))
            records[0]["sourceId"] = "synthetic-mismatched-source"
            evidence.write_text(json.dumps([records[0], records[-1]]), encoding="utf-8")
            manifest.write_bytes(MANIFEST_PATH.read_bytes())
            with self.assertRaisesRegex(ValueError, "provenance does not match"):
                load_smoke_records(evidence, manifest)

    async def test_missing_evidence_is_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "Cannot read the existing FLEX evidence"):
                load_smoke_records(Path(directory) / "missing.json", MANIFEST_PATH)


if __name__ == "__main__":
    unittest.main()
