# PyroSphere RAG service

This independent, English-only FastAPI service uses local Ollama. No external
model API or API key is required. The current ingestion path starts with the
existing NASA structured datasets; PDF ingestion is not a prerequisite. The
answer API uses the existing READY FLEX index and local qwen2.5 to report
verified source fields. Producing evidence JSON alone does not build an index.

The shared contract is in `../impotant_doc/FlameScope_API_Sozlesmesi_v1.md`.
The existing API field names are preserved. The product is English-only; language
selection is not implemented.

## Environment and API

Use the existing Python 3.14 virtual environment. `requirements.txt` records the
direct dependencies already installed during validation; this change requires
no additional packages. The commands below run from `C:\NASA\nasa` in PowerShell.

```powershell
& .\rag-service\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir .\rag-service --port 8000
```

- `GET /rag/v1/health` returns `{"status":"UP"}`.
- `POST /rag/v1/answer` reports cited FLEX test fields when the question is
  covered, and `INSUFFICIENT_EVIDENCE` for unsupported requests. Request and
  response field names are preserved. See [answer behavior and live checks](docs/answers.md).
- `app/ollama_client.py` uses `OLLAMA_BASE_URL` (default
  `http://localhost:11434`) and `OLLAMA_MODEL` (default `qwen2.5:3b`).

## PSI-69 FLEX CSV ingestion

The first structured source is
`../databases/Flex-1/PSI-69_Experimental table_FLEX.csv`. It has 15 original
headers and 274 test rows (CSV rows 2-275, including the header as row 1).
Strict UTF-8 decoding fails on byte `0x96`; Windows-1252 (`cp1252`) decodes the
source and preserves its en dash markers. No encoding replacement is used.

Run from the repository root with the existing virtual environment:

```powershell
& .\rag-service\.venv\Scripts\python.exe .\rag-service\app\csv_loader.py
```

The script also works when launched by absolute path from another working
directory. It reads the source without modifying it and writes a UTF-8 JSON
array to `rag-service/data/processed/flex_psi69_evidence.json`. The existing
ignore rule excludes generated output from Git. No new dependency is required.

Each record contains `investigationId`, `sourceId`, `sourceTestId`, `sourceType`,
`sourceFile`, `rowNumber`, `fields`, and `text`:

- `investigationId` is `PSI-69`; `sourceType` is `CSV`.
- `sourceTestId` is the original `FLEX Test #` cell string. `FLEX Identifier`
  remains in `fields`; it is not assumed to be unique.
- `sourceFile` is the repository-relative filename using forward slashes.
- `rowNumber` is the one-based logical CSV record number, counting the header
  and any blank rows. A quoted multiline cell belongs to one CSV record. In the
  current source every record occupies one physical line.
- `fields` retains original header names, their order, and decoded cell strings,
  including spaces, empty strings, zeros, dashes, and approximate values.
- `text` gives English provenance followed by every original field name and its
  JSON-quoted cell value. A blank cell appears as `""`; it is not replaced by zero,
  a scientific interpretation, or an inferred missing-value category.

`source_manifest.json` declares the local source ID
`PSI-69:experimental-table:v1`, filename, encoding, SHA-256, test ID column,
and reviewed test count. This is a RAG staging source ID, to be reconciled with
the backend's manifest before integration. `v1` identifies the local source
version, not a NASA publication edition. No `experimentId` is generated or inferred.

All 274 source rows have a numeric `FLEX Test #` and a nonempty `FLEX Identifier`.
The loader uses these observed markers to recognize tests. Completely empty rows
are skipped while retaining row positions. Unexpected note-like rows, missing
test markers, duplicate headers, malformed rows, source hash changes, and count
mismatches fail for review. It does not silently turn notes into tests or drop
ambiguous rows. Repeated identifiers are retained as separate source rows.

The output is a complete snapshot, never an append. Its evidence provenance key
is `(sourceId, rowNumber)`; this is not a backend experiment identity. Rerunning
unchanged ingestion reuses identical JSON without changing its timestamp or
duplicating records. Different existing output is preserved. After reviewing a
changed source version, update the manifest and use a new output filename:

```powershell
& .\rag-service\.venv\Scripts\python.exe .\rag-service\app\csv_loader.py --output data/processed/flex_psi69_evidence_review.json
```

All output paths must resolve inside `rag-service/data/processed/` and end in
`.json`; relative paths resolve from `rag-service/`. Original datasets are never
destinations. Manifest or source errors produce English messages and exit code 1.

Data limitations remain explicit:

- `Burning rate; mm` is preserved literally. Its unit is ambiguous; no `mm/s`,
  other rate unit, normalized measurement, or conversion is inferred.
- Empty cells, en dash markers, and `~6`/`~9` burn times remain literal strings.
  Missing-value categories and exact durations are not inferred.
- Dates and GMT cells remain original strings, including mixed year formats and
  a missing GMT value. No timestamp or timezone conversion is performed.
- Gas composition headers (`O`, `N`, `CO`, and `He`) are kept exactly as supplied;
  chemical formula subscripts and alternate units are not inferred.
- `FLEX Identifier` value `193F001` appears twice. Both rows are retained.
- This step preserves source evidence; it does not establish scientific validity,
  parse XLSX sources or establish scientific interpretations.

Validation compares every generated record with its CSV row, including all cells,
original headings, row provenance, and text. Representative checks cover the
first and last tests, blanks, en dashes, approximate times, and the repeated
identifier. API compatibility tests retain the health response and answer envelope.

## Local embedding client and live smoke test

`app/embedding_client.py` provides `await embed_texts(text_or_list)`, using httpx
and Ollama's `POST /api/embed`. `OLLAMA_BASE_URL` retains its existing default
`http://localhost:11434`. `OLLAMA_EMBEDDING_MODEL` selects the embedding model
and defaults to `qwen3-embedding:0.6b`; it is independent of the chat model's
`OLLAMA_MODEL` setting. No new dependency or external API key is required.

One string or a list of 1-8 nonempty strings is accepted. Input text is sent
unchanged and `truncate` is always `false`. Ollama therefore rejects context
overflow rather than silently truncating input. The client validates exactly
one vector per input, nonempty vectors of consistent dimensions, numeric finite
values (excluding booleans), and a returned model name. It preserves input order
and converts returned numeric components to Python floats without normalization.
Dimensions are observed from the response, not hardcoded. See the official
[Ollama embedding API contract](https://docs.ollama.com/api/embed).

Results contain the returned model, vectors, measured client elapsed time in
milliseconds, and optional Ollama generation/load durations converted from
nanoseconds. Returned timing metadata is also validated. The connection timeout
is five seconds; other HTTP phase timeouts are 120 seconds to allow model loading.
Local requests bypass environment proxies. No retry, automatic model download,
alternate model, text rewriting, or vector persistence is performed.

Failures raise `EmbeddingError` with an English message and a code distinguishing
`MODEL_UNAVAILABLE`, `OLLAMA_UNAVAILABLE`, `EMBEDDING_TIMEOUT`,
`EMBEDDING_REQUEST_FAILED`, and `INVALID_EMBEDDING_RESPONSE`. Invalid input and
empty model configuration are rejected before any network request.

Run the explicit live smoke test from the service directory:

```powershell
Push-Location .\rag-service
try { & .\.venv\Scripts\python.exe -m app.embedding_smoke }
finally { Pop-Location }
```

The smoke test reads the existing evidence and source manifest, validates the
selected provenance, and submits only the first and last FLEX evidence texts
plus the English query `Which FLEX tests used methanol and ended in disruption?`
in a single three-input batch. For the current evidence these are original
source tests `1` and `274`, CSV rows `2` and `275`. Their existing source ID,
filename, row number, and text are unchanged; no backend experiment IDs are
assigned. The JSON summary reports dimensions, elapsed time, server timing when
available, and the two source descriptors. Vectors remain in memory and are not
printed or written to disk. A failure prints an English error and exits with
code 1. This checks connectivity and response validity, not retrieval quality.

Live validation on November 14, 2026 used `qwen3-embedding:0.6b` and returned
three finite vectors, each with 1,024 dimensions. Client elapsed time was
31,433.657 ms; Ollama reported 30,861.32512 ms total and 14,819.052636 ms for
model loading. These are measurements from one request, including model loading.
The evidence JSON, manifest, source CSV, and answer endpoint were unchanged.

The regular unit tests use mock HTTP responses; they never contact Ollama.
For PostgreSQL persistence, resumable bulk indexing and the independent retrieval
CLI, see [FLEX persistence and retrieval](docs/pgvector.md). These tools are
separate from this smoke test. The answer API reuses retrieval without indexing
records per request.

## Optional PDF source status

On November 14, 2026, a content-signature search under `C:\NASA` found no genuine
BASS-II Summary Report PDF. The only PDF was the unrelated project delivery guide
under `impotant_doc/`. No NASA datasets were changed.

`data/documents/bass_ii_workbook.xlsx` is already preserved with the correct
extension. Its ZIP entries identify an Excel workbook. Its SHA-256 matches
`../databases/BASS-2/BASS-II Test Matrix by PI Final.xlsx`:

```text
1a3b283dd0adec861793bbc4a454aab64d398cd32d6f37d7a1ad0f642879e686
```

Do not rename or convert this workbook into a substitute report. Supply the
genuine report as `data/documents/bass_ii_summary.pdf`, or pass its path with
`--pdf`. Check an existing destination before copying; the loader never moves,
renames, converts, or modifies a source file. Verify the document identity and
edition manually: a valid PDF signature alone does not establish that it is
the BASS-II report.

## Optional PDF ingestion

The existing PDF loader is retained but is unused by the structured-data path.
The missing PDF does not block CSV ingestion.

```powershell
& .\rag-service\.venv\Scripts\python.exe .\rag-service\app\pdf_loader.py
# Alternative input or a new output path:
& .\rag-service\.venv\Scripts\python.exe .\rag-service\app\pdf_loader.py --pdf C:\path\to\genuine-report.pdf --output data/processed/bass_ii_pages_review.json
```

The script can also be launched by absolute path from any working directory.
All relative `--pdf` and `--output` paths resolve from `rag-service/`, not from
the terminal's directory. Default output is `data/processed/bass_ii_pages.json`.

The loader validates content before parsing. Missing files, renamed XLSX/ZIP
files, invalid or unreadable PDFs, encrypted PDFs, and PDFs without pages fail
with an English error and a nonzero exit code. Invalid input produces no JSON.
Existing output is checked byte for byte: identical output is reused; different
contents are never overwritten. Choose a new output path when re-extracting
with changed input or settings.

Output is a UTF-8 JSON array with one record per PDF page, including empty pages:

```json
{
  "sourceId": "PSI-25:summary-report:v1",
  "investigationId": "PSI-25",
  "title": "BASS-II Summary Report",
  "pdfPage": 1,
  "text": "Extracted page text"
}
```

These are the existing report-specific identifiers, not newly inferred metadata.
The contract treats `v1` as an internal source version. Confirm source identity
and edition against the team's manifest before indexing. `pdfPage` is the
one-based PDF viewer position. Printed page numbers, table labels, experiment
identifiers, and scientific facts are not inferred or added.

Layout extraction retains page boundaries, whitespace, table headers, footnotes,
and surrounding text. Rotated text is included where supported; pypdf can warn
about degraded layout. Wide tables, merged cells, symbols, and column order
still require visual comparison with the original. This is text extraction,
not structured table parsing or OCR. Blank or image-only pages remain in the
JSON and trigger a warning; nonempty text alone does not establish completeness.

Once the report is available, search the entire extracted text for Table 7.1 and
GMT190-T20. Check the matching pages and their neighbors in the original PDF,
including headers, units, continuation rows, and footnotes. For the expected
edition, PDF page 104 may show Table 7.1 and printed page 96; neither mapping has
been verified, and neither is hardcoded. Do not treat a test ID match as proof
that a wide table's column associations are correct.

Source documents, generated JSON, virtual environments, caches, and local
environment files are ignored only within this service. The existing workbook
remains on disk.

## Validation and next step

Run the standard-library tests without installing a test framework:

```powershell
Push-Location .\rag-service
try { & .\.venv\Scripts\python.exe -m unittest discover -s tests -v }
finally { Pop-Location }
```

Fixture files are explicitly synthetic PDFs, CSVs, and ZIPs created in temporary
directories; they are not NASA evidence. CSV integration tests also compare the
actual PSI-69 dataset with generated records. Tests cover content validation,
source and row/page provenance, raw cell preservation, UTF-8 output, source and
destination preservation, working-directory independence, repeatability, and
the health response and compatible answer fields. Answer tests also cover
question coverage, source citations, exact cell validation, filters and technical errors.

The READY index contains 274 FLEX records. The next step is to agree on backend
experiment-ID mapping and a verified structured-analysis handoff. The backend
retains authority over experiment IDs and numerical calculations. Larger-model
routing and streaming are not implemented.
