"""Actual Ollama answers and cell/citation checks without starting another HTTP service."""
import argparse
import asyncio
import json
import os
from contextlib import nullcontext
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import httpx
from .answer_evidence import assess_coverage, fields_for
from .rag_corpus import load_corpus, record_key
from .retrieval import plan_query, RetrievalFilters
from .rag_config import BASE_DIR, DatabaseSettings, RagError
from .multi_index import legacy_snapshot

CASES = [
    ("PSI-69", "Summarize FLEX test 70.", "ANSWERED", 1),
    ("PSI-69", "Show both records for identifier 193F001.", "ANSWERED", 2),
    ("PSI-25", "Show BASS-II test B1.", "ANSWERED", 1),
    ("PSI-25", "Show BASS-II workbook test B1.", "ANSWERED", 1),
    ("PSI-25", "Show BASS-II test B1 from CSV and workbook.", "ANSWERED", 2),
    ("PSI-100", "Show SAFFIRE-III sample S1.", "ANSWERED", 1),
    ("PSI-101", "Show SAME-R test 51a.", "ANSWERED", 1),
    ("PSI-101", "Show SAME-R test 51a date.", "ANSWERED", 1),
    ("PSI-101", "What conditions and measurements are recorded for SAME-R test 51a, and which fields are missing?", "PARTIAL", 1),
    ("PSI-101", "Give an overview of SAME-R test 51a, including blank or unreported fields.", "PARTIAL", 1),
    ("PSI-101", "List all fields for SAME-R test 51a.", "PARTIAL", 1),
    (["PSI-69", "PSI-25"], "Show FLEX test 70 and BASS-II test B1.", "ANSWERED", 2),
    ("PSI-69", "Show examples of Methanol FLEX tests with reported extinction.", "PARTIAL", 5),
    ("PSI-25", "Show examples of BASS-II tests.", "PARTIAL", 5),
    ("PSI-100", "Show examples of SAFFIRE-III samples.", "PARTIAL", 2),
    ("PSI-101", "Show examples of SAME-R tests.", "PARTIAL", 5),
    ("PSI-25", "Show FLEX test 70.", "INSUFFICIENT_EVIDENCE", 0),
    ("PSI-100", "Show SAFFIRE-I sample S1.", "INSUFFICIENT_EVIDENCE", 0),
    ("PSI-100", "Show SAFFIRE-III sample S1 burn time.", "INSUFFICIENT_EVIDENCE", 0),
    ("PSI-25", "Why did BASS-II test B1 burn?", "INSUFFICIENT_EVIDENCE", 0),
    ("PSI-25", "Which BASS-II test has the highest final CO?", "INSUFFICIENT_EVIDENCE", 0),
]


async def check(base_url=None, reject_model_output=False):
    if base_url and reject_model_output:
        raise ValueError("The rejection fixture is only available for in-process checks.")
    os.environ["RAG_CORPUS_MODE"] = "multi"
    os.environ["RAG_INDEX_NAME"] = "nasa_multi_v1"
    from .main import app
    corpus = load_corpus(mode="multi")
    settings = DatabaseSettings.from_environment()
    before = legacy_snapshot(DatabaseSettings(settings.url, "rag"))
    transport = None if base_url else httpx.ASGITransport(app=app)
    cases = [case for case in CASES if "examples" not in case[1]] if reject_model_output else CASES
    report = {"transport": "existing HTTP endpoint" if base_url else "in-process ASGI; actual PostgreSQL",
              "generation": "explicit rejected-output fixture; no model success claimed" if reject_model_output else "actual local Ollama", "cases": []}
    fixture = patch("app.ollama_client.generate_answer", new=AsyncMock(side_effect=RagError("INVALID_GENERATION_RESPONSE", "Deliberately rejected test output."))) if reject_model_output else nullcontext()
    with fixture:
        async with httpx.AsyncClient(transport=transport, base_url=base_url or "http://in-process", timeout=125, trust_env=False) as client:
            for inv, question, expected, count in cases:
                investigation_ids = inv if isinstance(inv, list) else [inv]
                payload = {"requestId": str(uuid4()), "question": question, "investigationIds": investigation_ids, "experimentIds": []}
                response = await client.post("/rag/v1/answer", json=payload)
                body = response.json()
                report["cases"].append({"investigationId": inv, "question": question, "httpStatus": response.status_code, "response": body})
                print(json.dumps({"question": question, "http": response.status_code, "status": body.get("status"), "model": body.get("modelUsed"), "sources": len(body.get("sources", []))}), flush=True)
                assert response.status_code == 200, body
                assert body["status"] == ("PARTIAL" if reject_model_output and count else expected), body
                assert len(body["sources"]) == count, body
                records = []
                for source in body["sources"]:
                    key = (source["sourceId"], source["sheetName"], source["rowNumber"]) if source["sheetName"] else (source["sourceId"], source["rowNumber"])
                    record = corpus.by_key[key]
                    assert record["investigationId"] in investigation_ids
                    assert source["sourceTestId"] == record["sourceTestId"]
                    records.append(record)
                if records:
                    plan = plan_query(question, corpus, RetrievalFilters(investigation_ids=tuple(investigation_ids)))
                    coverage = assess_coverage(question, {"route": plan.route, "filters": plan.filters, "matches": [{"record": r} for r in records], "eligibleRecordCount": len(records)})
                    for i, record in enumerate(records, 1):
                        line = next(line for line in body["answer"].splitlines() if f"[S{i}]" in line)
                        for header in fields_for(coverage.required_fields, i):
                            raw = record["fields"][header]
                            if raw.strip().casefold() in {"", "none", "n/a", "na", "-", "–", "—"}:
                                assert "does not give" in line or "does not provide" in line
                            else:
                                assert raw in line, (header, raw, line)
                        assert line.endswith(f"[S{i}]")
                        if record["investigationId"] == "PSI-69":
                            assert "mm/s" not in line
                        if record["investigationId"] == "PSI-101" and "Date" in fields_for(coverage.required_fields, i):
                            assert "22-Jul; no year is given in the source" in line
                    if reject_model_output:
                        assert body["modelTier"] == "NONE" and body["modelUsed"] is None
                        assert "MODEL_OUTPUT_REJECTED" in [w["code"] for w in body["warnings"]]
                        assert "The model output could not be validated" in body["answer"]
                    else:
                        assert body["modelTier"] == "SLM" and body["modelUsed"]
                else:
                    assert body["modelUsed"] is None and body["modelTier"] == "NONE"
    assert legacy_snapshot(DatabaseSettings(settings.url, "rag")) == before
    report["legacyFlexIndexUnchanged"] = before
    target = BASE_DIR / (".local/nasa-provenance/source-fallback-checks.json" if reject_model_output else ".local/nasa-provenance/multi-answer-checks.json")
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"PASS: {len(cases)} answer cases; legacy FLEX index unchanged. Report: {target}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", help="Optionally check the existing HTTP endpoint after you restart RAG")
    parser.add_argument("--reject-model-output", action="store_true", help="Test safe fallback with a deliberately rejected generation fixture and real DB retrieval; no Ollama success is claimed")
    args = parser.parse_args()
    asyncio.run(check(args.base_url, args.reject_model_output))
