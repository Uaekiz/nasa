"""Explicit live HTTP checks against the existing READY FLEX index; never indexes."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import re
from time import perf_counter

import httpx
from psycopg import sql

from .answer_evidence import assess_coverage
from .rag_config import BASE_DIR, DatabaseSettings
from .rag_corpus import content_hash, load_corpus
from .retrieval import RetrievalFilters, plan_query
from .vector_store import open_store


CASES = (
    ("test_70", "Summarize FLEX test 70.", "ANSWERED", [71], {}),
    ("duplicate_identifier", "Show both records for identifier 193F001.", "ANSWERED", [71, 74], {}),
    ("filtered_semantic", "Show examples of Methanol FLEX tests with reported extinction.", "PARTIAL", None, {}),
    ("unsupported_fabric", "What do the FLEX data say about solid fabric flammability?", "INSUFFICIENT_EVIDENCE", [], {}),
    ("numeric_maximum", "Which FLEX test has the maximum burn time?", "INSUFFICIENT_EVIDENCE", [], {}),
    ("unmapped_experiment", "Summarize FLEX test 70.", "INSUFFICIENT_EVIDENCE", [], {"experimentIds": ["unmapped-backend-id"]}),
    ("other_investigation", "Summarize FLEX test 70.", "INSUFFICIENT_EVIDENCE", [], {"investigationIds": ["PSI-25"]}),
    ("unsupported_cause", "Why did FLEX test 70 end in extinction?", "INSUFFICIENT_EVIDENCE", [], {}),
    ("test_70_warm_repeat", "Summarize FLEX test 70.", "ANSWERED", [71], {}),
)


def index_snapshot(corpus):
    with open_store(DatabaseSettings.from_environment()) as store:
        with store.lock(shared=True):
            state = store.ready(corpus)
            rows = store.connection.execute(sql.SQL(
                "SELECT source_id, row_number, content_hash, md5(embedding::text) AS vector_hash, "
                "updated_at::text FROM {} ORDER BY source_id, row_number"
            ).format(store.records_table)).fetchall()
    return {"status": state["status"], "count": len(rows), "fingerprint": content_hash(rows)}


def validate_answer(body, question, corpus, investigation_ids):
    sources = body["sources"]
    citation_ids = [source["citationId"] for source in sources]
    assert len(citation_ids) == len(set(citation_ids))
    assert set(re.findall(r"\[(S\d+)\]", body["answer"])) == set(citation_ids)
    records = []
    for source in sources:
        original = corpus.by_key[(source["sourceId"], source["rowNumber"])]
        assert source["investigationId"] == original["investigationId"]
        assert source["sourceTestId"] == original["sourceTestId"]
        assert source["sourceFile"] == original["sourceFile"]
        assert source["sourceType"] == "CSV" and source["experimentId"] is None
        assert source["pdfPage"] is None and source["printedPage"] is None
        records.append(original)
    if records:
        plan = plan_query(question, corpus, RetrievalFilters(investigation_ids=tuple(investigation_ids)))
        coverage = assess_coverage(question, {"route": plan.route, "filters": plan.filters,
                                  "eligibleRecordCount": len(records), "matches": [{"record": record} for record in records]})
        for source, original in zip(sources, records, strict=True):
            line = next(line for line in body["answer"].splitlines() if f"[{source['citationId']}]" in line)
            assert f"FLEX test {original['sourceTestId']} " in line
            assert f"FLEX Identifier {original['fields']['FLEX Identifier']}" in line
            for header in coverage.required_fields:
                value = original["fields"][header]
                if value.strip().casefold() in {"", "none", "n/a", "na", "-", "–", "—"}:
                    assert "does not give" in line or "does not provide" in line
                else:
                    assert value in line
    assert "mm/s" not in body["answer"]
    timings = body["timings"]
    assert all(isinstance(value, (int, float)) and value >= 0 for value in timings.values())
    assert timings["ragTotalMs"] + 0.002 >= timings["retrievalMs"] + timings["generationMs"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    corpus = load_corpus()  # Compares every staged record and cell with the original CSV.
    before = index_snapshot(corpus)
    source_path = BASE_DIR.parent / (
        corpus.manifest["sourceFile"] if "sourceFile" in corpus.manifest
        else next(s["sourceFile"] for s in corpus.manifest["sources"] if s["investigationId"] == "PSI-69")
    )
    source_hash = hashlib.sha256(source_path.read_bytes()).hexdigest()
    report = {"endpoint": args.base_url, "before": before, "sourceSha256": source_hash, "cases": []}
    with httpx.Client(timeout=125.0, trust_env=False) as client:
        health = client.get(args.base_url + "/rag/v1/health")
        assert health.status_code == 200 and health.json() == {"status": "UP"}
        report["health"] = health.json()
        for index, (name, question, expected_status, expected_rows, overrides) in enumerate(CASES, 1):
            payload = {"requestId": f"00000000-0000-4000-8000-{index:012d}", "question": question,
                       "investigationIds": ["PSI-69"], "experimentIds": [], "analysisContext": None, **overrides}
            started = perf_counter()
            response = client.post(args.base_url + "/rag/v1/answer", json=payload)
            body = response.json()
            entry = {"name": name, "request": payload, "httpStatus": response.status_code,
                     "wallMs": round((perf_counter() - started) * 1000, 3), "response": body}
            report["cases"].append(entry)
            print(json.dumps(entry, ensure_ascii=False), flush=True)
            assert response.status_code == 200, f"{name}: technical failure"
            assert body["requestId"] == payload["requestId"]
            assert body["status"] == expected_status, name
            if expected_rows is not None:
                assert [source["rowNumber"] for source in body["sources"]] == expected_rows, name
            validate_answer(body, question, corpus, payload["investigationIds"])
            if name == "filtered_semantic":
                assert len(body["sources"]) == 5
                for source in body["sources"]:
                    fields = corpus.by_key[(source["sourceId"], source["rowNumber"])]["fields"]
                    assert fields["Fuel"] == "Methanol" and fields["Test end"] == "Extinction"
            if name == "numeric_maximum":
                assert "STRUCTURED_ANALYSIS_REQUIRED" in [warning["code"] for warning in body["warnings"]]
            if not body["sources"]:
                assert body["modelTier"] == "NONE" and body["modelUsed"] is None
                assert body["timings"]["generationMs"] == 0
    report["after"] = index_snapshot(corpus)
    assert report["after"] == before, "The persisted index changed during read-only endpoint checks."
    assert hashlib.sha256(source_path.read_bytes()).hexdigest() == source_hash
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    destination = BASE_DIR / "data" / "processed" / f"flex_answer_validation_{stamp}.json"
    with destination.open("x", encoding="utf-8") as output:
        json.dump(report, output, ensure_ascii=False, indent=2)
        output.write("\n")
    print(f"PASS: {len(CASES)} live endpoint cases; {before['count']} unchanged persisted records. Report: {destination}")


if __name__ == "__main__":
    main()
