# FLAMESCOPE frontend

Run from the repository root with the existing dependencies:

```powershell
npm.cmd --prefix frontend run dev
```

The Vite proxy forwards `/api` and `/files` to the existing Spring Boot backend
on port 8080. The backend calls the Python RAG service on port 8000. Start or
restart each service in its own terminal; do not start another copy on an
occupied port. See [setup and verification notes](../docs/flamescope-completion.md).

The interface and deterministic scenario text use English. Normalized values
use `en-US` formatting; original source headers/cells remain verbatim. The
FLAMESCOPE mark and favicon are local SVG assets. No external image service or
new frontend dependency is required.

Capture saves the current inputs and a PNG locally. Only `capturedAt` and
`params` are submitted; the image is not sent to RAG or a vision model. CO/CO2
phase selectors define whether those inputs correspond to initial or final
source readings. Changing inputs marks a saved analysis stale.

```powershell
npm.cmd --prefix frontend test
npm.cmd --prefix frontend run lint
npm.cmd --prefix frontend run build
```

`node tests/flamescope-workflow-browser.mjs` (from `frontend`) is an optional
isolated Edge integration check. It requires the real-DB MockMvc fixture export
and RAG chat fixture described in the completion notes. It starts only its own
hidden test browser, and uses `FRONTEND_URL` for an already running frontend.
