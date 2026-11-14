"""Explicit live smoke test: two existing FLEX records and one English query."""

import asyncio
import json
from pathlib import Path
import sys

from .embedding_client import EmbeddingError, embed_texts


BASE_DIR = Path(__file__).resolve().parent.parent
EVIDENCE_PATH = BASE_DIR / "data" / "processed" / "flex_psi69_evidence.json"
MANIFEST_PATH = BASE_DIR / "source_manifest.json"
QUERY = "Which FLEX tests used methanol and ended in disruption?"


def load_smoke_records(
    evidence_path: Path = EVIDENCE_PATH,
    manifest_path: Path = MANIFEST_PATH,
) -> list[dict]:
    """Select exactly the first and last evidence records without modifying them."""
    try:
        records = json.loads(evidence_path.read_text(encoding="utf-8"))
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("Cannot read the existing FLEX evidence JSON or source manifest.") from error
    if not isinstance(manifest, dict) or not isinstance(records, list) or len(records) < 2:
        raise ValueError("The smoke test requires a source manifest and at least two evidence records.")
    selected = [records[0], records[-1]]
    for record in selected:
        if not isinstance(record, dict) or any(
            not isinstance(manifest.get(key), str) or record.get(key) != manifest[key]
            for key in ("investigationId", "sourceId", "sourceFile")
        ):
            raise ValueError("Selected evidence provenance does not match the source manifest.")
        if record["investigationId"] != "PSI-69" or record.get("sourceType") != "CSV":
            raise ValueError("The smoke test requires existing PSI-69 CSV evidence.")
        if not isinstance(record.get("text"), str) or not record["text"].strip():
            raise ValueError("A selected evidence record has no usable text.")
        if type(record.get("rowNumber")) is not int or record["rowNumber"] < 2:
            raise ValueError("A selected evidence record has invalid CSV row provenance.")
        fields = record.get("fields")
        test_id = record.get("sourceTestId")
        if not isinstance(fields, dict) or not isinstance(test_id, str) or not test_id.strip():
            raise ValueError("A selected evidence record has no original test identifier.")
        if test_id != fields.get("FLEX Test #"):
            raise ValueError("A selected evidence test identifier differs from its original CSV field.")
    if selected[0]["rowNumber"] == selected[1]["rowNumber"]:
        raise ValueError("The smoke test requires two distinct evidence rows.")
    return selected


async def run_smoke_test() -> dict:
    records = load_smoke_records()
    print("Embedding exactly two existing FLEX records and one English query.", flush=True)
    result = await embed_texts([record["text"] for record in records] + [QUERY])
    return {
        "model": result.model,
        "inputCount": 3,
        "vectorCount": len(result.embeddings),
        "dimensions": [len(vector) for vector in result.embeddings],
        "elapsedMs": round(result.elapsed_ms, 3),
        "serverDurationMs": result.server_duration_ms,
        "loadDurationMs": result.load_duration_ms,
        "evidence": [
            {key: record[key] for key in (
                "investigationId", "sourceId", "sourceTestId", "sourceFile", "rowNumber",
            )}
            for record in records
        ],
        "query": QUERY,
    }


def main() -> int:
    try:
        summary = asyncio.run(run_smoke_test())
    except EmbeddingError as error:
        print(f"Error [{error.code}]: {error}", file=sys.stderr)
        return 1
    except ValueError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
