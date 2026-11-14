"""Validate staged FLEX evidence against its original CSV before indexing or retrieval."""

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

from .rag_config import BASE_DIR, RagError
from .csv_loader import CsvIngestionError, extract_records


EVIDENCE_PATH = BASE_DIR / "data" / "processed" / "flex_psi69_evidence.json"
MANIFEST_PATH = BASE_DIR / "source_manifest.json"


def content_hash(value: object) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def text_hash(record: dict) -> str:
    return hashlib.sha256(record["text"].encode("utf-8")).hexdigest()


def record_key(record: dict) -> tuple[str, int]:
    return record["sourceId"], record["rowNumber"]


@dataclass(frozen=True)
class Corpus:
    records: list[dict]
    manifest: dict
    fingerprint: str

    @property
    def by_key(self) -> dict[tuple[str, int], dict]:
        return {record_key(record): record for record in self.records}


def load_corpus() -> Corpus:
    try:
        records = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        original_records = extract_records()
    except (OSError, ValueError, CsvIngestionError) as error:
        raise RagError("INVALID_EVIDENCE", "Cannot validate FLEX evidence against its manifest and CSV.") from error
    if records != original_records:
        raise RagError("INVALID_EVIDENCE", "The evidence JSON differs from the original CSV ingestion output.")
    if len({record_key(record) for record in records}) != len(records):
        raise RagError("INVALID_EVIDENCE", "Duplicate evidence provenance keys were found.")
    return Corpus(records, manifest, content_hash({"manifest": manifest, "records": records}))


def verify_match(record: dict, corpus: Corpus) -> None:
    if not isinstance(record, dict) or not {"sourceId", "rowNumber"} <= set(record):
        raise RagError("CORRUPT_INDEX", "A retrieved record has no valid source provenance.")
    if corpus.by_key.get(record_key(record)) != record:
        raise RagError("CORRUPT_INDEX", "A retrieved source record differs from the validated original CSV.")
