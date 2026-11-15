"""Filtered retrieval and exact test lookup without generation or numerical analysis."""

import argparse
import asyncio
from dataclasses import asdict, dataclass, field
from functools import partial
import json
import math
import os
import re
import sys
from time import perf_counter

import httpx

from .rag_config import DatabaseSettings, RagError
from .rag_corpus import Corpus, load_corpus, verify_match
from .model_profile import ModelProfile, format_query, get_model_profile, verify_model_identity, expected_profile
from .embedding_client import DEFAULT_EMBEDDING_MODEL, EMBEDDING_TIMEOUT, EmbeddingError, embed_texts
from .vector_store import open_store
from .record_question import inventory_analysis_text


ANALYSIS_PATTERN = re.compile(
    r"\b(how many|total|count|sum|average|mean|median|maximum|minimum|max|min|highest|lowest|"
    r"largest|smallest|fastest|slowest|longest|shortest|most|least|higher|lower|longer|shorter|"
    r"larger|smaller|faster|slower|greater|less|more than|fewer than|list all|all tests|"
    r"at least|at most|above|below|exceed\w*|compare\w*|comparison|difference|ratio|percent\w*|"
    r"correlation|trend|increase\w*|decrease\w*|versus|vs)\b|[<>]=?|\b(?:top|bottom)\s+\d+",
    re.IGNORECASE,
)
UNSUPPORTED_PATTERN = re.compile(
    r"\b(solid\w*|fabric\w*|textile\w*|cloth|cotton|nylon|foam|polymer\w*|bass(?:-?ii)?|saffire)\b",
    re.IGNORECASE,
)
TEST_SELECTOR = re.compile(r"\b(?:tests?|samples?)(?:\s+(?:id|number|no\.?))?\s*[:#]?\s*([a-z]?\d+[a-z]?(?:\s*(?:,|and)\s*[a-z]?\d+[a-z]?)*)\b", re.I)


@dataclass(frozen=True)
class RetrievalFilters:
    source_ids: tuple[str, ...] = ()
    investigation_ids: tuple[str, ...] = ()
    fuel: str | None = None


@dataclass
class QueryPlan:
    route: str
    filters: dict = field(default_factory=dict)
    reason: str = ""


def plan_query(
    question: str, corpus: Corpus, filters: RetrievalFilters | None = None,
    *, test_ids: list[str] | None = None, flex_identifiers: list[str] | None = None,
) -> QueryPlan:
    from .source_catalog import PROFILES, field_value
    if not isinstance(question, str) or not 1 <= len(question.strip()) <= 4000:
        raise RagError("INVALID_QUESTION", "Provide an English question between 1 and 4000 characters.")
    analysis_text = inventory_analysis_text(question, has_record_selector=bool(
        TEST_SELECTOR.search(question) or test_ids or flex_identifiers
        or re.search(r"\b(?:flex\s+)?identifier\s*[:#]?\s*[a-z0-9-]*\d", question, re.I)))
    if ANALYSIS_PATTERN.search(analysis_text):
        return QueryPlan("STRUCTURED_ANALYSIS_REQUIRED", reason="Numeric aggregation and comparisons require verified backend SQL calculations; similarity search was not used.")
    filters = filters or RetrievalFilters()
    selected = asdict(filters)
    available = {r["investigationId"] for r in corpus.records}
    named = set(re.findall(r"\bPSI-\d+\b", question.upper()))
    for inv, profile in PROFILES.items():
        if any(re.search(r"(?<!\w)" + re.escape(alias) + r"(?![\w-])", question, re.I) for alias in profile["aliases"]):
            named.add(inv)
    unsupported = re.search(r"\b(?:FLEX[- ]2|BASS[- ]I|SAFFIRE[- ](?:I|II|IV|V|VI))(?![\w-])", question, re.I)
    if unsupported or named - available or set(filters.investigation_ids) - available:
        return QueryPlan("INSUFFICIENT_EVIDENCE", reason="The requested investigation has no reviewed source rows in this index.")
    if named and filters.investigation_ids and not named <= set(filters.investigation_ids):
        return QueryPlan("INSUFFICIENT_EVIDENCE", reason="The question conflicts with the selected investigation scope.")
    scope = set(filters.investigation_ids) or named or available
    selected["investigation_ids"] = sorted(scope)
    if scope <= {"PSI-69"} and UNSUPPORTED_PATTERN.search(question):
        return QueryPlan("INSUFFICIENT_EVIDENCE", reason="The selected FLEX droplet CSV does not support solid-material or other-investigation questions.")
    if not named and not filters.investigation_ids and re.search(r"\b(?:BASS|SAFFIRE|SAME)\b", question, re.I):
        return QueryPlan("INSUFFICIENT_EVIDENCE", reason="Specify the supported investigation: BASS-II, SAFFIRE-III, or SAME-R.")
    candidates = [r for r in corpus.records if r["investigationId"] in scope]
    if filters.source_ids:
        candidates = [r for r in candidates if r["sourceId"] in filters.source_ids]
    workbook = bool(re.search(r"\b(?:workbook|xlsx|worksheet)\b", question, re.I))
    csv = bool(re.search(r"\bcsv\b", question, re.I))
    if workbook and not csv:
        candidates = [r for r in candidates if r["sourceType"] == "XLSX"]
    elif (csv and not workbook) or (not filters.source_ids and not workbook):
        candidates = [r for r in candidates if r["sourceType"] == "CSV"]
    selected["source_ids"] = sorted({r["sourceId"] for r in candidates})
    if not candidates:
        return QueryPlan("INSUFFICIENT_EVIDENCE", reason="No reviewed source matches this investigation/source selection.")
    fuels = {" ".join(field_value(r, "fuel").split()).casefold(): " ".join(field_value(r, "fuel").split()) for r in candidates}
    mentioned = [fuel for key, fuel in fuels.items() if key and re.search(r"(?<!\w)" + re.escape(key) + r"(?!\w)", question, re.I)]
    if filters.fuel is not None:
        if filters.fuel.casefold() not in fuels:
            raise RagError("INVALID_FILTER", "Fuel/material must match an original value in the selected investigation and source.")
        selected["fuel"] = fuels[filters.fuel.casefold()]
        if len(mentioned) == 1 and selected["fuel"] != mentioned[0]:
            raise RagError("CONFLICTING_FILTER", "The question's fuel/material conflicts with the explicit filter.")
    elif len(mentioned) == 1:
        selected["fuel"] = mentioned[0]
    selected_ids = list(test_ids or [])
    for match in TEST_SELECTOR.finditer(question):
        selected_ids.extend(re.findall(r"[a-z]?\d+[a-z]?", match.group(1), re.I))
    if question.strip().isascii() and question.strip().isdecimal(): selected_ids.append(question.strip())
    originals = {r["sourceTestId"].casefold(): r["sourceTestId"] for r in candidates}
    selected_ids = [originals.get(value.casefold(), value) for value in selected_ids]
    identifiers = list(flex_identifiers or [])
    for match in re.finditer(r"\bFLEX\s+Identifier\s*[:#]?\s*((?=[a-z0-9-]*\d)[a-z0-9-]+)", question, re.I):
        identifiers.append(match.group(1).upper())
    known_identifiers = {r["fields"].get("FLEX Identifier", "") for r in candidates} - {""}
    identifiers.extend(value for value in sorted(known_identifiers) if re.search(r"(?<!\w)"+re.escape(value)+r"(?!\w)", question, re.I))
    if selected_ids: selected["test_ids"] = list(dict.fromkeys(selected_ids))
    if identifiers: selected["flex_identifiers"] = list(dict.fromkeys(v.upper() for v in identifiers))
    if selected_ids and not named and not filters.investigation_ids:
        matched_investigations = {r["investigationId"] for r in candidates if r["sourceTestId"] in selected_ids}
        if len(matched_investigations) > 1:
            return QueryPlan("INSUFFICIENT_EVIDENCE", reason="This test marker occurs in several investigations. Specify an investigation.")
    if selected_ids or identifiers:
        return QueryPlan("EXACT_ID", selected)
    outcome_text = re.sub(r"\b(?:visible )?(?:flame )?extinction diameter\b", " ", question, flags=re.I)
    requested = [value for value, pattern in (("Extinction", r"\b(?:extinction|extinguish\w*)\b"), ("Disruption", r"\bdisruption\b"), ("Completion", r"\bcompletion\b")) if re.search(pattern, outcome_text, re.I)]
    if requested:
        if scope != {"PSI-69"} or len(requested) > 1 or re.search(r"\b(?:not|never|without|no)\b", outcome_text, re.I):
            return QueryPlan("INSUFFICIENT_EVIDENCE", reason="The selected sources do not verify a single requested outcome condition.")
        selected["outcome"] = requested[0]
    return QueryPlan("SEMANTIC", selected)


def blocked_result(plan: QueryPlan) -> dict:
    return {
        "status": plan.route, "route": plan.route, "sufficientEvidence": False,
        "matches": [], "reason": plan.reason,
        "timings": {"queryEmbeddingMs": 0.0, "searchMs": 0.0, "totalMs": 0.0},
    }


async def retrieve_records(
    question: str, store, corpus: Corpus, *, filters: RetrievalFilters | None = None,
    test_ids: list[str] | None = None, flex_identifiers: list[str] | None = None,
    embed=embed_texts, profile_loader=None, identity_check=None,
) -> dict:
    from .source_catalog import field_value
    started = perf_counter()
    plan = plan_query(question, corpus, filters, test_ids=test_ids, flex_identifiers=flex_identifiers)
    if plan.route not in ("EXACT_ID", "SEMANTIC"):
        result = blocked_result(plan)
        result["timings"]["totalMs"] = round((perf_counter() - started) * 1000, 3)
        return result
    embedding_ms = 0.0
    load_ms = None
    with store.lock(shared=True):
        state = store.ready(corpus)
        profile = ModelProfile(**state["configuration"])
        expected = expected_profile(profile.model, profile.digest, profile.dimensions, schema_version=profile.schema_version)
        store.assert_configuration(state, expected)
        configured_model = os.getenv("OLLAMA_EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL).strip()
        if configured_model != profile.model:
            raise RagError("INCOMPATIBLE_INDEX", "The configured query model differs from the stored record model.")
        eligible = store.candidate_count(plan.filters)
        vector = None
        if plan.route == "SEMANTIC" and eligible:
            if profile_loader is None:
                raise RagError("MODEL_UNAVAILABLE", "Semantic retrieval requires model identity verification.")
            current_profile = await profile_loader()
            store.assert_configuration(state, current_profile)
            embedded = await embed(format_query(question, profile))
            if embedded.model != profile.model or embedded.dimensions != profile.dimensions:
                raise RagError("INCOMPATIBLE_INDEX", "The query embedding differs from the index model or dimensions.")
            if identity_check is not None:
                await identity_check(profile)
            vector = embedded.embeddings[0]
            embedding_ms = embedded.elapsed_ms
            load_ms = embedded.load_duration_ms
        search_started = perf_counter()
        rows = store.search(plan.filters, vector) if eligible else []
        search_ms = (perf_counter() - search_started) * 1000
        matches = []
        for rank, row in enumerate(rows, 1):
            record = row["record"]
            verify_match(record, corpus)
            for name, actual in (("investigation_ids", record["investigationId"]), ("source_ids", record["sourceId"]),
                                 ("test_ids", record["sourceTestId"]), ("flex_identifiers", field_value(record, "identifier"))):
                if plan.filters.get(name) and actual not in plan.filters[name]:
                    raise RagError("CORRUPT_INDEX", "A retrieved record violates the explicit source/investigation/test scope.")
            distance = row["cosine_distance"]
            if distance is not None and (not isinstance(distance, (int, float)) or not math.isfinite(distance)):
                raise RagError("CORRUPT_INDEX", "The vector index returned an invalid cosine distance.")
            if plan.filters.get("fuel") is not None and " ".join(field_value(record, "fuel").split()) != plan.filters["fuel"]:
                raise RagError("CORRUPT_INDEX", "A retrieved record violates the fuel filter.")
            matches.append({"rank": rank, "cosineDistance": distance, "record": record})
    return {
        "status": ("EXACT_MATCH" if plan.route == "EXACT_ID" else "CANDIDATES_ONLY") if matches else "INSUFFICIENT_EVIDENCE",
        "route": plan.route, "sufficientEvidence": False, "filters": plan.filters,
        "eligibleRecordCount": eligible, "matches": matches,
        "reason": "Source records are retrieval candidates. Claim-level sufficiency has not been assessed; distance is not scientific confidence.",
        "timings": {
            "queryEmbeddingMs": round(embedding_ms, 3), "modelLoadMs": load_ms,
            "searchMs": round(search_ms, 3), "totalMs": round((perf_counter() - started) * 1000, 3),
        },
    }


async def run_retrieval(question: str, filters: RetrievalFilters, *, test_ids=None, flex_identifiers=None) -> dict:
    started = perf_counter()
    corpus = load_corpus()
    plan = plan_query(question, corpus, filters, test_ids=test_ids, flex_identifiers=flex_identifiers)
    if plan.route not in ("EXACT_ID", "SEMANTIC"):
        result = blocked_result(plan)
        result["timings"]["totalMs"] = round((perf_counter() - started) * 1000, 3)
        return result
    with open_store(DatabaseSettings.from_environment()) as store:
        async with httpx.AsyncClient(timeout=EMBEDDING_TIMEOUT, trust_env=False) as client:
            return await retrieve_records(
                question, store, corpus, filters=filters, test_ids=test_ids, flex_identifiers=flex_identifiers,
                embed=partial(embed_texts, client=client), profile_loader=partial(get_model_profile, client),
                identity_check=lambda profile: verify_model_identity(profile, client),
            )


def main() -> int:
    parser = argparse.ArgumentParser(description="Retrieve up to five original FLEX source records; no generation.")
    parser.add_argument("question")
    parser.add_argument("--source-id", action="append", default=[])
    parser.add_argument("--investigation-id", action="append", default=[])
    parser.add_argument("--fuel")
    parser.add_argument("--test-id", action="append", default=[])
    parser.add_argument("--flex-identifier", action="append", default=[])
    args = parser.parse_args()
    try:
        result = asyncio.run(run_retrieval(
            args.question, RetrievalFilters(tuple(args.source_id), tuple(args.investigation_id), args.fuel),
            test_ids=args.test_id, flex_identifiers=args.flex_identifier,
        ))
    except (RagError, EmbeddingError) as error:
        print(f"Error [{error.code}]: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
