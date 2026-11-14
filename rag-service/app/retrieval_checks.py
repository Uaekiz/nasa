"""Explicit live checks, including separately measured cold and warm query requests."""

import argparse
import asyncio
from functools import partial
import json
import sys

import httpx

from .rag_config import DatabaseSettings, RagError
from .rag_corpus import load_corpus, verify_match
from .model_profile import get_model_profile, verify_model_identity
from .embedding_client import EMBEDDING_TIMEOUT, EmbeddingError, embed_texts
from .retrieval import RetrievalFilters, retrieve_records
from .vector_store import open_store


async def is_loaded(client: httpx.AsyncClient, model: str) -> bool:
    try:
        response = await client.get("/api/ps")
        response.raise_for_status()
        models = response.json()["models"]
        if not isinstance(models, list):
            raise ValueError("Invalid running-model list.")
        return any(item.get("name") == model for item in models)
    except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError) as error:
        raise RagError("COLD_CHECK_UNAVAILABLE", "Cannot verify whether the embedding model is loaded.") from error


async def unload_for_cold_check(client: httpx.AsyncClient, model: str):
    if not await is_loaded(client, model):
        return
    try:
        # Empty input is a model lifecycle operation, not an evidence embedding.
        response = await client.post("/api/embed", json={
            "model": model, "input": [], "truncate": False, "keep_alive": 0,
        })
        response.raise_for_status()
    except httpx.HTTPError as error:
        raise RagError("COLD_CHECK_UNAVAILABLE", "Ollama could not unload the embedding model for the cold check.") from error
    for _ in range(10):
        if not await is_loaded(client, model):
            return
        await asyncio.sleep(0.2)
    raise RagError("COLD_CHECK_UNAVAILABLE", "The model is still loaded; a cold timing cannot be claimed.")


def compact(result: dict) -> dict:
    return {
        "status": result["status"], "route": result["route"],
        "sufficientEvidence": result["sufficientEvidence"], "timings": result["timings"],
        "matches": [{
            "sourceId": match["record"]["sourceId"], "sourceTestId": match["record"]["sourceTestId"],
            "sourceFile": match["record"]["sourceFile"], "rowNumber": match["record"]["rowNumber"],
            "cosineDistance": match["cosineDistance"], "originalFields": match["record"]["fields"],
        } for match in result["matches"]],
    }


async def run_checks(*, cold: bool = False) -> dict:
    corpus = load_corpus()
    settings = DatabaseSettings.from_environment()
    # A missing or incomplete database blocks live checks before model lifecycle changes.
    with open_store(settings) as store:
        with store.lock(shared=True):
            state = store.ready(corpus)
        from .ollama_client import OLLAMA_BASE_URL
        async with httpx.AsyncClient(base_url=OLLAMA_BASE_URL, timeout=EMBEDDING_TIMEOUT, trust_env=False) as client:
            profile = await get_model_profile(client)
            store.assert_configuration(state, profile)

            async def retrieve(question, **kwargs):
                result = await retrieve_records(
                    question, store, corpus, embed=partial(embed_texts, client=client),
                    profile_loader=partial(get_model_profile, client),
                    identity_check=lambda pinned: verify_model_identity(pinned, client), **kwargs,
                )
                for match in result["matches"]:
                    verify_match(match["record"], corpus)
                return result

            exact = await retrieve("Show FLEX test 70.")
            if [match["record"]["sourceTestId"] for match in exact["matches"]] != ["70"]:
                raise RagError("CHECK_FAILED", "Exact source test lookup did not return test 70.")
            duplicate = await retrieve("Show FLEX Identifier 193F001.")
            if {match["record"]["sourceTestId"] for match in duplicate["matches"]} != {"70", "73"}:
                raise RagError("CHECK_FAILED", "Repeated FLEX Identifier rows were not both retained.")
            if cold:
                await unload_for_cold_check(client, profile.model)
            first_was_loaded = await is_loaded(client, profile.model)
            filters = RetrievalFilters((corpus.manifest["sourceId"],), ("PSI-69",), "Methanol")
            question = "Find FLEX droplet tests reported as extinction."
            first = await retrieve(question, filters=filters)
            second_was_loaded = await is_loaded(client, profile.model)
            warm = await retrieve(question, filters=filters)
            for result in (first, warm):
                if len(result["matches"]) != 5 or result["sufficientEvidence"]:
                    raise RagError("CHECK_FAILED", "Semantic matches must be five review candidates, not sufficient evidence.")
                if any(
                    match["record"]["fields"]["Fuel"] != "Methanol"
                    or match["record"]["fields"]["Test end"] != "Extinction"
                    for match in result["matches"]
                ):
                    raise RagError("CHECK_FAILED", "A semantic result violated the fuel or reported-outcome filter.")
            unsupported = await retrieve("Describe flame spread on solid cotton fabric in microgravity.")
            if unsupported["status"] != "INSUFFICIENT_EVIDENCE" or unsupported["matches"]:
                raise RagError("CHECK_FAILED", "Unsupported fabric questions must not be treated as supported evidence.")
            numeric = await retrieve("Which FLEX test has the highest burning rate?")
            if numeric["status"] != "STRUCTURED_ANALYSIS_REQUIRED" or numeric["matches"]:
                raise RagError("CHECK_FAILED", "An extrema question was incorrectly routed to similarity search.")
            return {
                "model": profile.model, "modelDigest": profile.digest, "dimensions": profile.dimensions,
                "indexedRecordCount": len(corpus.records), "allReturnedValuesCheckedAgainstCsv": True,
                "exactId": compact(exact), "repeatedFlexIdentifier": compact(duplicate),
                "semanticQuestion": question, "semanticFilters": {"fuel": "Methanol", "investigationId": "PSI-69"},
                "firstQueryTemperature": "COLD_MODEL" if not first_was_loaded else "WARM_MODEL",
                "firstSemanticQuery": compact(first),
                "secondQueryTemperature": "WARM_MODEL" if second_was_loaded else "COLD_MODEL",
                "secondSemanticQuery": compact(warm),
                "unsupportedFabric": compact(unsupported), "numericQuestion": compact(numeric),
            }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run live pgvector retrieval checks against original FLEX values.")
    parser.add_argument("--cold", action="store_true", help="Unload only the embedding model before the first semantic query.")
    args = parser.parse_args()
    try:
        result = asyncio.run(run_checks(cold=args.cold))
    except (RagError, EmbeddingError) as error:
        print(f"Error [{error.code}]: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
