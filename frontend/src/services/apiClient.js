const API_BASE = (import.meta.env?.VITE_API_BASE_URL || "/api/v1").replace(/\/$/, "");

export class ApiError extends Error {
  constructor(message, { code, requestId, status } = {}) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.requestId = requestId;
    this.status = status;
  }
}

async function request(path, { timeoutMs = 15000, signal: externalSignal, ...options } = {}) {
  const controller = new AbortController();
  let timedOut = false;
  const abort = () => controller.abort();
  externalSignal?.addEventListener("abort", abort, { once: true });
  const timeout = setTimeout(() => { timedOut = true; controller.abort(); }, timeoutMs);
  try {
    if (externalSignal?.aborted) throw new DOMException("Request cancelled.", "AbortError");
    const response = await fetch(`${API_BASE}${path}`, {
      ...options,
      headers: { Accept: "application/json", "Accept-Language": "en", ...options.headers },
      signal: controller.signal,
    });
    const data = await response.json().catch(() => null);
    if (!response.ok) {
      const message = data?.error?.message;
      const englishErrors = {
        RAG_UNAVAILABLE: "The RAG service is unavailable. You can retry.", RAG_TIMEOUT: "The RAG service timed out. You can retry.",
        VALIDATION_ERROR: "The request contains invalid or missing fields.", NOT_FOUND: "The requested record or source was not found.",
        INTERNAL_ERROR: "An unexpected server error occurred.",
      };
      throw new ApiError(message && !/[çğıöşüİÇĞÖŞÜ]/.test(message) ? message : englishErrors[data?.error?.code] || `API request failed (HTTP ${response.status}).`, {
        code: data?.error?.code, requestId: data?.requestId, status: response.status,
      });
    }
    if (!data) throw new ApiError("The API did not return valid JSON.");
    return data;
  } catch (error) {
    if (externalSignal?.aborted && !timedOut) throw new DOMException("Request cancelled.", "AbortError");
    if (error instanceof ApiError) throw error;
    throw new ApiError(error.name === "AbortError"
      ? "The API request timed out. You can retry."
      : "Could not connect to the backend API.", { code: timedOut ? "API_TIMEOUT" : "API_UNAVAILABLE" });
  } finally {
    clearTimeout(timeout);
    externalSignal?.removeEventListener("abort", abort);
  }
}

function post(path, body, options) {
  return request(path, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body), ...options,
  });
}

export async function checkBackendHealth() {
  try { return await request("/health"); }
  catch { return { status: "OFFLINE" }; }
}

export async function fetchInvestigations() {
  return (await request("/investigations")).items;
}

export function fetchChatCapabilities() {
  return request("/chat/capabilities");
}

export function fetchExperiments({ investigationId = "", fuel = "", page = 0, size = 20 } = {}) {
  const params = new URLSearchParams({ page: String(page), size: String(size) });
  if (investigationId) params.set("investigationId", investigationId);
  if (fuel) params.set("fuel", fuel);
  return request(`/experiments?${params}`);
}

export function fetchExperiment(experimentId) {
  return request(`/experiments/${encodeURIComponent(experimentId)}`);
}

export function fetchSource(sourceId) {
  return request(`/sources/${encodeURIComponent(sourceId)}`);
}

// /files belongs to the backend origin even when API_BASE is cross-origin.
export function sourceDocumentUrl(source, pdfPage) {
  if (!source.documentUrl) return null;
  const backend = new URL(API_BASE, globalThis.location?.origin || "http://localhost");
  const url = new URL(source.documentUrl, backend.origin);
  if (!["http:", "https:"].includes(url.protocol)) return null;
  if (pdfPage != null && source.documentUrl.toLowerCase().includes(".pdf")) url.hash = `page=${pdfPage}`;
  return url.href;
}

export function compareExperiments(experimentIds) {
  return post("/comparisons", { experimentIds });
}

export function askAiAssistant({ question, investigationIds = [], experimentIds = [], language = "en" }) {
  return post("/chat", { question, investigationIds, experimentIds, language }, { timeoutMs: 130000 });
}
export function submitScenario({ capturedAt, params }, { signal } = {}) {
  return post(
    "/scenario-analyses",
    { capturedAt, params },
    { timeoutMs: 130000, signal }
  );
}
