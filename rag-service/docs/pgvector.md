# FLEX persistence and retrieval

This path uses PostgreSQL plus pgvector and leaves `/rag/v1/answer` unchanged.
It performs no generation, PDF ingestion, numerical comparisons, or backend
experiment identity assignment. The existing CSV, manifest, evidence JSON, and
embedding client are inputs and are not rewritten.

## Database setup

Follow [the local PostgreSQL setup guide](local-database-setup.md) for the detected
Windows PostgreSQL 18 instance. It includes the exact hidden-password login,
create-only provisioning SQL, matching pgvector build/install commands, and
application configuration command. It does not replace or reset the server.

Normal operations require database `pyrosphere_rag`, role `pyrosphere_rag_app`,
and the marked application-owned schema `rag` by default. An administrator
provisions missing objects; indexing/retrieval reject an administrator or a
different database. Existing role passwords and attributes are never changed
by the provisioning script. The application role does not need database CREATE
or role-management privileges.

`RAG_DATABASE_URL` is a psycopg/libpq URI beginning with `postgresql://`, read
from the environment or ignored `rag-service/.env`. It is not a JDBC or
SQLAlchemy `postgresql+psycopg://` URL. Process environment variables take
precedence. Passwords are URL-encoded by the interactive configuration helper,
which preserves unrelated settings and refuses to replace a different existing
connection. `.env.example` contains no real credentials. Previously supported
`pyrosphere_rag*` schema names remain accepted for compatibility; no old schema
or index is migrated or removed automatically.

## Index and recover

```powershell
& .\.venv\Scripts\python.exe -m app.indexing --batch-size 8
# Run the same command again to verify reuse or recover an interrupted run.
& .\.venv\Scripts\python.exe -m app.indexing --batch-size 8
```

Before indexing, all 274 staged records are compared with the existing CSV
loader's output and the manifest's source hash. Every actual test remains one
evidence unit. The primary key includes `(sourceId, rowNumber)`, never a FLEX
Identifier or an invented backend experiment ID. Source tests 70 and 73 both
have FLEX Identifier `193F001` and remain distinct.

The schema has `index_state` and `evidence_records`. It stores the complete
original record as JSONB, exact provenance/filter columns, content and text
SHA-256 hashes, and a dimension-constrained pgvector column. JSON object key
order is not meaningful in PostgreSQL JSONB; original header order remains in
the unchanged evidence text and source JSON. Empty strings, en dashes,
qualifiers, dates, and `Burning rate; mm` remain unchanged; no unit conversion
or chemical formula correction occurs.

The index configuration pins the embedding tag, installed model digest,
dimensions, document formatting, query instruction, and schema version. A
different configuration is rejected before data writes. Create a new approved
RAG schema for an incompatible index; the tool does not drop an old one.
Source snapshot changes are staged as a new BUILDING snapshot, reusing unchanged
text embeddings. Only stale records in this RAG-owned snapshot are pruned when
the complete replacement is verified.

Batches of 1-8 records use the existing embedding client with `truncate=false`.
Each batch commits atomically. A process interruption or embedding error leaves
previous batches committed and the index BUILDING. Rerunning reuses matching
text hashes under the same pinned model, embeds only missing/changed text, and
publishes READY only after every stored record matches the full snapshot.
An unchanged READY rerun makes no embedding calls and does not duplicate rows.

Session advisory locks prevent concurrent writers and prevent retrieval during
index writes. A BUILDING, stale, incompatible, or incomplete index cannot be
queried. Database statements have 30-second timeouts, locks five seconds, and
connections five seconds; these are separate from Ollama inference timeouts.

The indexing summary reports the stored record count, newly embedded records,
reused embeddings, pinned identity, total indexing time, and cumulative
embedding/model-load time. Indexing timings are not query timings.

## Retrieve original evidence

```powershell
& .\.venv\Scripts\python.exe -m app.retrieval 'Show FLEX test 70.'
& .\.venv\Scripts\python.exe -m app.retrieval 'Show FLEX Identifier 193F001.'
& .\.venv\Scripts\python.exe -m app.retrieval 'Show the source record.' --test-id 24
& .\.venv\Scripts\python.exe -m app.retrieval 'Find FLEX droplet tests reported as extinction.' --source-id 'PSI-69:experimental-table:v1' --investigation-id PSI-69 --fuel Methanol
& .\.venv\Scripts\python.exe -m app.retrieval 'Describe flame spread on solid cotton fabric in microgravity.'
& .\.venv\Scripts\python.exe -m app.retrieval 'Which FLEX test has the highest burning rate?'
```

`app.retrieval.retrieve_records()` is also callable with an open store and a
validated corpus. Exact source test IDs and known/explicit FLEX Identifiers use
deterministic SQL lookup, with no query embedding or similarity fallback.
Exact IDs that are absent or excluded by filters return no matches. Multiple
rows with a shared FLEX Identifier are retained. The natural-language ID parser
handles forms such as `test #70` and `tests 70 and 73`; `--test-id` and
`--flex-identifier` provide explicit selectors when wording is ambiguous.

Semantic retrieval uses the same model tag, digest, dimensions and pinned
configuration as stored vectors. Following the [Qwen3 model card](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B#transformers-usage),
queries use `Instruct: {one-sentence task}\nQuery:{question}` and document texts
remain unprefixed. Other model families are rejected until their formatting is
implemented explicitly.

Source, investigation, and fuel restrictions are applied inside a materialized
candidate relation before exact cosine ranking. For this small corpus, no HNSW
or IVFFlat approximation is needed. An explicit extinction request also limits
the original `Test end` field to `Extinction` before ranking. This is a filter on
reported source text, not an inferred outcome. See [pgvector filtering](https://github.com/pgvector/pgvector#filtering).
At most five results contain the full original source record, deterministic
tie order, and cosine distance. Distance is a ranking measure, not scientific
confidence. Every returned record is checked against the original CSV snapshot.

Nearest matches are always `CANDIDATES_ONLY` with `sufficientEvidence=false`.
Exact lookups use `EXACT_MATCH`, also without claiming that a broader question
has been answered. Unsupported solid/fabric/other-investigation topics return
`INSUFFICIENT_EVIDENCE` without forcing liquid-droplet neighbors into an answer.
Totals, numeric comparisons, extrema, and exhaustive-list requests return
`STRUCTURED_ANALYSIS_REQUIRED` without a similarity call. Those require verified
backend SQL; no calculations or scientific answers are implemented here.
The English intent/scope rules are conservative heuristics, not a general
scientific question classifier. Unknown semantic topics still produce only
unverified candidates. The answer API applies an additional conservative coverage
check and validates generated field values against source cells; see
[answer behavior](answers.md). Retrieval itself never marks candidates sufficient.

## Live checks and timing

```powershell
& .\.venv\Scripts\python.exe -m app.retrieval_checks --cold
```

This checks exact test 70, both `193F001` records, filtered semantic extinction
retrieval, an unsupported solid-fabric question, and a blocked maximum question.
It compares all returned values to the CSV. It does not call the answer model.

`--cold` explicitly unloads only the embedding model using an empty `/api/embed`
request with `keep_alive=0`, then verifies absence through `/api/ps`. It never
claims a cold timing if unloading cannot be verified. Two identical semantic
requests are measured separately, with model residency checked before each.
The report includes query embedding, model loading, SQL search, and total query
time. Cold/warm labels refer to model residency, not filesystem/database cache
state. Without `--cold`, the report labels the observed state rather than
assuming the first query is cold. This is a small functional check, not a
performance benchmark.

## Tests

```powershell
& .\.venv\Scripts\python.exe -m unittest discover -s tests -v
# Optional: use the configured RAG database for disposable-schema SQL tests.
# Set RAG_TEST_DATABASE_URL for the application role and RAG_TEST_ADMIN_DATABASE_URL
# for test-schema provisioning locally, then run:
& .\.venv\Scripts\python.exe -m unittest discover -s tests -p test_pgvector_integration.py -v
```

Regular tests mock embeddings and persistence. Live SQL tests are skipped unless
both explicit test connection variables are set. An administrative connection
only provisions and removes a new, uniquely named `rag_test_*` schema. All
indexing and retrieval in that schema use the dedicated application connection.
The tests use explicitly synthetic vectors and remove only their own new test
schema after checking ownership/marker. They do not rebuild the real index or
contact Ollama. They cover durable interrupted-run recovery, reuse, incompatible
configurations, source values, filter ordering and duplicate IDs.

If database credentials, connectivity or pgvector are missing, no bulk embedding
work is started. Live indexed counts, retrieval examples and cold/warm timings
must be reported as blocked, separately from successful unit tests and the
validated count of 274 source records.
