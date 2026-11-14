"""In-memory test store for orchestration tests; never a production persistence fallback."""

from contextlib import nullcontext
from copy import deepcopy
import math

from app.rag_config import RagError
from app.rag_corpus import Corpus, content_hash, record_key, text_hash
from app.vector_store import PgVectorStore


def synthetic_corpus(count=3):
    records = [{
        "investigationId": "PSI-69", "sourceId": "PSI-69:synthetic-test-only:v1",
        "sourceTestId": str(index), "sourceType": "CSV", "sourceFile": "databases/synthetic.csv",
        "rowNumber": index + 1,
        "fields": {
            "FLEX Test #": str(index), "FLEX Identifier": "SYNTHETIC-DUP" if index < 3 else "SYNTHETIC-OTHER",
            "Fuel": "Methanol" if index % 2 else "Heptane", "Test end": "Extinction",
            "Burning rate; mm": "~0.5",
        },
        "text": f"Synthetic test {index}; not NASA evidence.",
    } for index in range(1, count + 1)]
    manifest = {"sourceId": records[0]["sourceId"], "sha256": "synthetic-only"}
    return Corpus(records, manifest, content_hash(records))


class MemoryStore:
    assert_configuration = staticmethod(PgVectorStore.assert_configuration)

    def __init__(self):
        self.metadata = None
        self.data = {}
        self.vectors = {}
        self.batches = 0
        self.search_calls = []

    def lock(self, *, shared=False):
        return nullcontext()

    def bootstrap(self, profile):
        self.profile = profile
        if self.metadata is None:
            self.metadata = {"configuration": profile.configuration, "status": "BUILDING", "corpus_hash": "", "expected_count": 0}
        else:
            self.assert_configuration(self.metadata, profile)

    def state(self):
        return deepcopy(self.metadata)

    def cache(self):
        return deepcopy(self.data)

    def begin_snapshot(self, corpus):
        self.metadata.update(status="BUILDING", corpus_hash=corpus.fingerprint, expected_count=len(corpus.records))

    def write_batch(self, records, vectors):
        for record in records:
            key = record_key(record)
            self.data[key] = {"record": deepcopy(record), "content_hash": content_hash(record), "text_hash": text_hash(record)}
            if key in vectors:
                self.vectors[key] = list(vectors[key])
        self.batches += 1

    def finish_snapshot(self, corpus):
        self.data = {key: value for key, value in self.data.items() if key in corpus.by_key}
        assert set(self.data) == set(corpus.by_key)
        self.metadata["status"] = "READY"

    def ready(self, corpus):
        if self.metadata is None or self.metadata["status"] != "READY":
            raise RagError("INDEX_NOT_READY", "Synthetic test index is incomplete.")
        if self.metadata["corpus_hash"] != corpus.fingerprint:
            raise RagError("STALE_INDEX", "Synthetic test index is stale.")
        return self.state()

    def selected(self, filters):
        result = []
        for key, value in self.data.items():
            record = value["record"]
            tests = (
                ("source_ids", record["sourceId"]), ("investigation_ids", record["investigationId"]),
                ("test_ids", record["sourceTestId"]), ("flex_identifiers", record["fields"]["FLEX Identifier"]),
            )
            if any(filters.get(name) and actual not in filters[name] for name, actual in tests):
                continue
            if filters.get("fuel") and record["fields"]["Fuel"] != filters["fuel"]:
                continue
            if filters.get("outcome") and record["fields"]["Test end"] != filters["outcome"]:
                continue
            result.append((key, record))
        return result

    def candidate_count(self, filters):
        return len(self.selected(filters))

    def search(self, filters, vector=None):
        self.search_calls.append((deepcopy(filters), vector))
        rows = []
        for key, record in self.selected(filters):
            distance = None
            if vector is not None:
                stored = self.vectors[key]
                dot = sum(a * b for a, b in zip(stored, vector, strict=True))
                distance = 1 - dot / math.sqrt(sum(a * a for a in stored) * sum(b * b for b in vector))
            rows.append({"record": deepcopy(record), "cosine_distance": distance})
        rows.sort(key=lambda row: (row["cosine_distance"] or 0, row["record"]["rowNumber"]))
        return rows[:5]
