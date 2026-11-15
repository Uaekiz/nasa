# FLAMESCOPE completion and verification

This update builds on the user's uncommitted scenario workflow. Existing source
chat, the experiment catalog, scenario capture and the Spring Boot → RAG path
are retained. No commit, push, merge, deployment, database reset, migration,
source-data edit, index rebuild, `.env` edit or new dependency was made.

The application now uses English throughout its navigation, controls, charts,
tooltips, loading/errors, source-view explanations and deterministic Python
scenario text. Normalized numbers use `en-US`. Original NASA/PSI source names,
headers and cell values remain unchanged, including missing cells and partial
dates such as `22-Jul` with no year.

## UI and model presentation

The header and favicon use a local, original flame-and-inspection-lens SVG at
`frontend/public/flamescope-mark.svg`. The NASA // PSI brand badge and bottom
palette strip are removed. NASA/PSI identifiers remain in catalog data and
citations. A compact FLAMESCOPE footer explains source data versus illustrative
simulation. The header checks only the backend health endpoint and says so;
it does not infer RAG or model availability.

The old demo recommendation box, apply-all buttons, undo handler and associated
state are removed. Presets, sliders, Three.js scene, camera controls, pause,
capture and image download remain. Temperature, power, CO and CO2 inputs are
also exposed. The retained calculation engine still feeds the scene and charts.

Scores are labelled as illustrative 0–100 model scores, with differences in
points. Gas percentages keep their real percentage units. Time curves are
example model curves, not sensor history or a validated forecast; the chart
reference line is explicitly arbitrary. Fixed `confidence: 94.6` and
unsupported NASA-physics/AI-intervention/safe-region claims are removed. All
five original presets retain the same metrics, variant ordering/patches,
score differences and 16-point timelines. A separate before/after calculation
snapshot and three regression tests check this numerical preservation.

Responsive grid children can shrink, long source tables scroll inside their
own panels, and text wraps without expanding the page. The desktop scenario
panel scrolls independently so a detailed result does not leave a large empty
column or push all charts below it. Mobile uses normal page scrolling. Mobile screenshots and
a strict width check confirm 390 px viewport / 390 px document width.

## Scenario workflow

The panel order is captured inputs → local image → one assessment → next checks
→ coverage → sources. The assessment is outside the source details loop.
The image is a preview only and is not submitted to RAG or inspected by a model.

CO and CO2 have separate initial/final/unspecified selectors. No phase is
assumed. All ten original parameters are validated by both backend and RAG,
retained in the response and accounted for in `parameterCoverage`.

Source records are grouped by investigation, test and BASS-II investigator.
Each research uses named ordering fields; the old “last numeric comparison”
ordering defect is removed. CSV primary records and independently cited XLSX
alternatives stay separate. Raw differences, extra columns and missing cells
are visible; storage/wording differences are not silently reconciled.
Citation links open and scroll to their own source cards. Document and
provenance URLs come from the reviewed catalog and backend source endpoint.

The request gate combines cancellation and a version ticket. Recapture,
resubmit, navigation/unmount and late responses cannot replace a newer capture.
Changed inputs or measurement phases mark results as belonging to the old
scenario. Canvas errors, invalid inputs, no source, API failures and timeouts
remain explicit. The capture stays available after an API error for retry.

## Evidence scope and remaining limitations

| Input/source | Behavior |
|---|---|
| BASS-II oxygen | Calibrated initial O2 % by volume; delta in percentage points |
| BASS-II CO/CO2 | Only the explicitly selected initial/final source column; missing/negative/qualified readings stay uncomparable |
| SAFFIRE-III | Exact airflow and relative direction; source contains sample conditions, not burning outcomes |
| FLEX | Droplet evidence stays separate; pressure mmHg × 0.133322 → kPa matches the existing importer precision |
| FLEX composition | O mole fraction is not silently O2 by volume; CO mole fraction is not silently ppm on an unspecified basis |
| SAME-R | Smoke/aging inlet velocity, not open-flame evidence |
| Gravity, temperature, ignition power | Validated and retained. No explicit unit-labelled columns exist in the current reviewed files, so they remain NOT_COMPARABLE |
| Fan/Air display | Instrument settings; never converted into cm/s |

Generic mappings accept explicit unit-labelled pressure/gravity/temperature/
power fields if such fields exist; they do not create missing columns. No
source values, geometry, flame behavior, risk percentages or safety advice are
invented. Review checks identify evidence gaps and next inspection steps.

All observations and higher/lower/equal/different relations are deterministic.
The optional model only orders an exact set of supplied check IDs. Its role is
shown explicitly. A model failure preserves source records, comparisons and
the default check order with `modelUsed: null` and a visible fallback reason.

The actual configured Ollama call was unavailable during this run. A real
in-process ASGI request using the original reviewed files returned HTTP 200,
five PMMA source groups and `DETERMINISTIC`, with `OLLAMA_UNAVAILABLE` and no
claimed model success. No model was installed, downloaded or replaced.

## Verification

| Check | Result |
|---|---|
| Frontend unit tests | 25 passed |
| Frontend ESLint | Passed |
| Frontend production build | Passed; existing large-bundle warning remains (~1.99 MB before gzip) |
| Backend full normal Maven lifecycle | 15 passed |
| RAG full suite | 149 tests: 144 passed, 5 optional privileged-environment tests skipped |
| New Python scenario cases | 19 included above: grouping, sorting, units, directions, phases, validation, citations and model fallback |
| Frontend scenario cases | Snapshot/stale state, abort and ignored-abort late completions, unmount/StrictMode, echo validation and separate raw source versions |
| Actual browser capture | PNG capture, 12 saved fields, input-change marker, recapture, local-only image, logo/footer and zero uncaught exceptions |
| Integrated isolated browser scenarios | Single assessment, source variants/differences, citations, phases, stale/late/unmount handling, API errors/timeouts, mobile layout and WebGL failure passed |
| Catalog/chat browser regression | Actual MockMvc/DB fixtures: four filters, SAME-R partial date, FLEX detail, source endpoint, comparison and paging; actual READY-index scope and source-chat fallback fixture passed |
| Protected state | Source files, manifests, `.env`, all 514 experiment identities and both persisted RAG indexes unchanged |

The standard application ports were not responding during this run. Browser
checks used a temporary Vite dev preview on an unused port 5175 and a separate
hidden Edge test browser. API fixtures came from real-DB MockMvc responses and
the actual in-process ASGI code; scenario requests ran against original source
files with an explicitly rejected ordering-model fixture. These are isolated
integration checks, not a claim that all three live HTTP services were running
together. Existing service processes were not stopped. The temporary test
preview is closed after validation.

Protected counts remain FLEX 274, BASS-II 129, SAFFIRE-III 2 and SAME-R 109
(514 total). The legacy FLEX index still has 274 records; the multi-source
index retains 643 independent source rows. A file/identity/vector/state hash
snapshot was compared after checks.

Local outputs (ignored build/test artifacts):

- `backend/target/flamescope-backend-tests.log`, `flamescope-browser-api.json`
- `backend/target/flamescope-workflow-browser.log`, `flamescope-real-scenario.json`
- `backend/target/flamescope-preservation-before.json`
- `backend/target/brand-desktop.png`, `brand-mobile-header.png`, `brand-mobile-footer.png`, `flamescope-scenario-mobile.png`
- `rag-service/.local/nasa-provenance/scenario-all-tests.log`

## Run or restart

Reload/restart backend and RAG to load the new controller, validation and
comparison code. Vite development mode reloads frontend changes automatically;
start the frontend if it is not running. Use separate terminals and first close
any existing instance yourself; do not run a second copy on an occupied port.
No database restart, migration, import or reindex command is needed.

From the repository root, frontend:

```powershell
npm.cmd --prefix frontend run dev
```

Backend, using the installed Maven distribution that passed validation (the
local wrapper may fail on this machine):

```powershell
$mavenBin = Get-ChildItem "$env:USERPROFILE/.m2/wrapper/dists/apache-maven-3.10.0" -Recurse -Filter mvn.cmd | Select-Object -First 1 -ExpandProperty FullName
Push-Location backend
& $mavenBin "-Dmaven.repo.local=$env:USERPROFILE/.m2/repository" '-Daether.syncContext.named.factory=rwlock-local' spring-boot:run
Pop-Location
```

RAG with the existing configuration and local models:

```powershell
Push-Location rag-service
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
Pop-Location
```

The existing `.env` selects the multi-source index. Do not rebuild or replace
it for this update. Restore access to the configured local Ollama service if
model ordering is desired; deterministic comparisons do not require its
success, but do require a running RAG service.

## Repeat checks

```powershell
npm.cmd --prefix frontend test
npm.cmd --prefix frontend run lint
npm.cmd --prefix frontend run build
Push-Location backend
& $mavenBin "-Dmaven.repo.local=$env:USERPROFILE/.m2/repository" '-Daether.syncContext.named.factory=rwlock-local' '-Ddebug=false' '-Dlogging.level.root=WARN' -o -e test
Pop-Location
Push-Location rag-service
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
Pop-Location
```

The backend test run exports `flamescope-browser-api.json`. Export the chat
fixture from real READY-index capabilities and a source-answer ASGI response
with explicit generation rejection. The adapter uses the existing Python
environment and original corpus, without starting a server. From the repo root,
with the database and a frontend running:

```powershell
.\rag-service\.venv\Scripts\python.exe frontend/tests/scenario-fixture.py --export-chat
Push-Location frontend
$env:FRONTEND_URL='http://127.0.0.1:5173'
node tests/flamescope-workflow-browser.mjs
Pop-Location
```

For the HTTP workflow after starting all services, capture a scenario, choose
gas phases, submit and open citations/alternative source versions. Confirm that
a parameter change marks the result stale. Live model check ordering remains
an environment-dependent follow-up; it is not reported as verified here.
