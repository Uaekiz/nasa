"""Connect read-only retrieval to constrained local generation and the v1 answer envelope."""

import asyncio
from time import perf_counter

from .rag_config import RagError
from . import ollama_client
from .answer_evidence import assess_coverage, build_sources, generation_input, render_validated_answer
from .retrieval import ANALYSIS_PATTERN, RetrievalFilters, run_retrieval


async def retrieve_for_answer(question: str, filters: RetrievalFilters) -> dict:
    # The existing module uses synchronous psycopg. Keep it off the ASGI event loop.
    # Each worker owns its async Ollama client and database connection; no indexing.
    return await asyncio.to_thread(lambda: asyncio.run(run_retrieval(question, filters)))


async def answer_question(request) -> dict:
    started = perf_counter()
    response = {
        "requestId": str(request.requestId), "answer": "", "status": "INSUFFICIENT_EVIDENCE",
        "modelTier": "NONE", "modelUsed": None, "sources": [], "warnings": [],
        "timings": {"retrievalMs": 0.0, "generationMs": 0.0, "ragTotalMs": 0.0},
    }
    if not request.question.strip():
        raise RagError("INVALID_QUESTION", "Provide a nonempty English question.")
    if request.analysisContext is not None:
        response["warnings"].append({"code": "ANALYSIS_CONTEXT_NOT_USED", "message": "Backend analysisContext validation is not implemented. No supplied calculation was treated as verified evidence."})
    if request.experimentIds:
        response["answer"] = "Backend experimentId mapping is unavailable for the FLEX source rows. The requested experiment filter cannot be applied."
        response["warnings"].append({"code": "EXPERIMENT_MAPPING_UNAVAILABLE", "message": "No experiment filter was ignored and no backend experiment IDs were inferred from FLEX test numbers."})
        if ANALYSIS_PATTERN.search(request.question):
            response["warnings"].append({"code": "STRUCTURED_ANALYSIS_REQUIRED", "message": "Numeric aggregation requires verified structured analysis."})
    else:
        retrieval_started = perf_counter()
        result = await retrieve_for_answer(request.question, RetrievalFilters(investigation_ids=tuple(request.investigationIds)))
        response["timings"]["retrievalMs"] = round((perf_counter() - retrieval_started) * 1000, 3)
        coverage = assess_coverage(request.question, result)
        if coverage.status == "INSUFFICIENT_EVIDENCE":
            response["answer"] = coverage.reason
            code = "STRUCTURED_ANALYSIS_REQUIRED" if result["route"] == "STRUCTURED_ANALYSIS_REQUIRED" else "QUESTION_NOT_COVERED"
            response["warnings"].append({"code": code, "message": coverage.reason})
        else:
            records = [match["record"] for match in result["matches"]]
            response["sources"] = build_sources(records)
            generation_started = perf_counter()
            prompt, schema = generation_input(request.question, records, coverage.required_fields)
            content = await ollama_client.generate_answer(prompt, response_schema=schema, num_predict=1024)
            text, warnings = render_validated_answer(content, records, coverage.required_fields)
            response["timings"]["generationMs"] = round((perf_counter() - generation_started) * 1000, 3)
            response.update(answer=text, status=coverage.status, modelTier="SLM", modelUsed=ollama_client.OLLAMA_MODEL)
            response["warnings"].extend(warnings)
            if result["route"] == "SEMANTIC":
                response["answer"] = "Retrieved examples from the requested scope:\n" + response["answer"]
                response["warnings"].append({"code": "RETRIEVAL_SUBSET", "message": "These are up to five matching examples, not an exhaustive result or a scientific confidence estimate."})
            elif coverage.status == "PARTIAL":
                response["warnings"].append({"code": "PARTIAL_COVERAGE", "message": "Some requested IDs, records, or field values are not covered by the returned source rows."})
    response["timings"]["ragTotalMs"] = round((perf_counter() - started) * 1000, 3)
    return response
