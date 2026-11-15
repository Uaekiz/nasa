# FLEX answer endpoint

The examples below describe legacy FLEX scope. The current multi-source mode,
natural source sentences and explicit rejected-model fallback are documented in
[the current report](../../docs/source-narrative-and-3d.md).

`POST /rag/v1/answer` now calls `app.retrieval.run_retrieval` against the existing
READY PostgreSQL/pgvector index. It never runs ingestion, embeds source rows, or
writes index tables. Query embeddings are used only for semantic retrieval.
Synchronous database work runs in a worker thread so it does not block ASGI's
event loop. `GET /rag/v1/health` still returns `{"status":"UP"}`.

## Run and check

Use the existing virtual environment and ignored local `.env`. No dependency,
credential, provisioning or source-manifest change is needed. From the repository
root, start the service in a terminal:

```powershell
& .\rag-service\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir .\rag-service --port 8000
```

An already running process must reload the edited modules before it serves the
new behavior. For a check while another server occupies port 8000, run
`python -m app.multi_checks` from `rag-service`. This calls ASGI in-process with
the real database and Ollama without starting another server.

In a second terminal:

```powershell
Push-Location .\rag-service
try {
    & .\.venv\Scripts\python.exe -m app.answer_checks --base-url http://127.0.0.1:8000
    & .\.venv\Scripts\python.exe -m unittest discover -s tests -v
}
finally { Pop-Location }
```

The explicit live checker submits nine HTTP requests: test 70, both `193F001`
records, Methanol extinction examples, unsupported fabric, numeric maximum,
unmapped experiment filter, another investigation, unsupported cause and a repeat
of test 70. It compares cited rows and rendered values against the corpus, which
is validated against every original CSV cell. It checks database count, stored
content hashes, vector hashes and update timestamps before and after. Reports
use unique filenames under ignored `data/processed/flex_answer_validation_*.json`.
No index is built or model unloaded. The repeat is measured separately; the first
request is not assumed to be cold. These are functional checks, not benchmarks.

## Request and response compatibility

The request retains `requestId`, `question`, `investigationIds`, `experimentIds`,
and `analysisContext`; language selection is not introduced. An example:

```json
{
  "requestId": "00000000-0000-4000-8000-000000000070",
  "question": "Summarize FLEX test 70.",
  "investigationIds": ["PSI-69"],
  "experimentIds": [],
  "analysisContext": null
}
```

Successful HTTP 200 responses keep `requestId`, `answer`, `status`, `modelTier`,
`modelUsed`, `sources`, `warnings` and `timings`. Covered exact lookups use
`ANSWERED`, or `PARTIAL` if IDs, rows or requested values are missing. Valid
semantic examples use `PARTIAL` and `RETRIEVAL_SUBSET`; they are not exhaustive.
Unsupported questions use `INSUFFICIENT_EVIDENCE`, model tier `NONE`, null model
and no generated text. Numeric aggregates, comparisons and extrema retain
`STRUCTURED_ANALYSIS_REQUIRED`; no nearest-row arithmetic is performed.

Investigation filters reach the existing SQL retrieval filters. Fuel names in
the question are resolved by the existing planner before ranking. Combined-fuel
conditions are rejected explicitly rather than silently dropping them. Exact test
numbers and FLEX Identifiers use deterministic lookup without query embeddings.
`193F001` returns test 70, CSV row 71, and test 73, CSV row 74. They are separate
evidence records. Up to five records are returned; a truncated exact lookup
cannot claim full coverage.

There is no backend experiment-ID mapping. Any nonempty `experimentIds` produces
`INSUFFICIENT_EVIDENCE` with `EXPERIMENT_MAPPING_UNAVAILABLE`, without running an
unfiltered search or inventing IDs. `analysisContext` is not yet validated and
receives `ANALYSIS_CONTEXT_NOT_USED` when supplied; it cannot authorize numbers.

## Evidence and generation boundary

Retrieval continues to return `sufficientEvidence=false`. A separate coverage
check admits original-field questions and test summaries, or matching semantic
examples. It rejects unknown attributes, unimplemented conditions, causal
explanations, predictions and safety recommendations. Exact ID presence and
eligible row count are checked; semantic outcome/fuel constraints are checked
against returned cells. No similarity threshold is treated as scientific
confidence. These English rules are deliberately conservative and can reject
valid paraphrases. They do not constitute general scientific entailment.

For covered requests the existing local chat client uses `OLLAMA_MODEL`
(default `qwen2.5:3b`) and `POST /api/chat`. It supplies the question and every
retrieved row's original fields. It requests a JSON object containing required
field/value pairs for every citation, using Ollama's documented
[structured output schema](https://docs.ollama.com/capabilities/structured-outputs).
Generation is non-streaming, temperature zero, with an 8,192-token context and
1,024 output-token limit. There is no alternate model, download or retry.

The service rejects missing/extra citation IDs, duplicate JSON keys, missing or
extra fields and every cell string that differs from its cited original.
It then renders short English sentences from original values and explicit source
unit mappings, citing every factual sentence. Free model
prose is not accepted. This extractive format checks factual cell agreement,
including numbers, rather than attempting to validate unrestricted prose after
generation. Rejected model output is replaced by a direct cited rendering of the
original cells, explicitly labelled with `MODEL_OUTPUT_REJECTED`, `PARTIAL`,
`modelTier: NONE` and `modelUsed: null`; no successful model prose is claimed.

Original empty strings are explained as missing in natural language; nonempty
missing markers are quoted and `~` qualifiers remain unchanged. Missing selected cells yield `PARTIAL` and a
`SOURCE_MISSING_VALUE` warning. `Burning rate; mm` retains that literal heading
and gets `AMBIGUOUS_SOURCE_UNIT`; `mm/s` is not inferred. Gas headings, mixed
dates and source precision are not scientifically normalized.

Citation objects are built exclusively from retrieved records. Every `[S1]`
maps to its actual source ID, investigation, CSV filename and one-based row
(including the header). Contract fields for PDF page, printed page, table,
chunk, sheet and backend experiment ID are null. Optional `sourceTestId` and
repository-relative `sourceFile` make CSV provenance explicit. No absolute
local path or model-authored provenance is returned. Source registry mapping
to backend-accessible document URLs remains an integration task.

This validates agreement with the provided CSV, not NASA scientific validity,
measurement accuracy, mechanisms, generalization, or safety. No claim requires
trusting a similarity score or a model-created scientific explanation.

## Errors and timings

Technical failures use the shared contract's error envelope, with the echoed
request ID, `error.code`, English `message` and `details` codes:

- HTTP 400 `VALIDATION_ERROR`: invalid request or question/filter.
- HTTP 503 `RAG_UNAVAILABLE`: database, index or source-validation failure.
- HTTP 503 `MODEL_UNAVAILABLE`: unreachable/rejected Ollama requests or invalid
  embedding responses. Invalid chat content or generated-value/citation failures
  use the explicit source-only fallback described above.
- HTTP 504 `RAG_TIMEOUT`: database, embedding, chat or total request timeout.
- HTTP 500 `INTERNAL_ERROR`: unexpected service failure.

The endpoint has a 120-second total deadline; PostgreSQL retains its existing
five-second connection/lock and 30-second statement limits. A cancelled request
does not return a background worker's result; an already running retrieval
worker may finish within its own transport/database limits. No retries occur.
Exception messages returned to clients never include connection strings or
passwords. Health remains a liveness check rather than a readiness assertion.

Normal responses measure wall-clock `retrievalMs` (corpus validation, connection,
query embedding if needed and SQL), `generationMs` (chat, validation and rendering),
and `ragTotalMs` (the complete service operation). Skipped stages are zero.
Model loading is included when it occurs. Client/backend network time is excluded
from `ragTotalMs`. Error responses retain the contract's error-only envelope.

The next integration step is backend experiment/source mapping, followed by a
validated structured-analysis handoff for numeric questions. Larger-model
routing, streaming, PDF ingestion and index changes are outside this endpoint work.
