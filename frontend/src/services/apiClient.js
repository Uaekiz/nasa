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

async function request(path, { timeoutMs = 15000, ...options } = {}) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(`${API_BASE}${path}`, {
      ...options,
      headers: { Accept: "application/json", ...options.headers },
      signal: controller.signal,
    });
    const data = await response.json().catch(() => null);
    if (!response.ok) {
      throw new ApiError(data?.error?.message || `API isteği başarısız (HTTP ${response.status}).`, {
        code: data?.error?.code, requestId: data?.requestId, status: response.status,
      });
    }
    if (!data) throw new ApiError("API geçerli bir JSON yanıtı döndürmedi.");
    return data;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    throw new ApiError(error.name === "AbortError"
      ? "API yanıt süresi aşıldı. Yeniden deneyebilirsiniz."
      : "Backend API bağlantısı kurulamadı.");
  } finally {
    clearTimeout(timeout);
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

export function askAiAssistant({ question, investigationIds = [], experimentIds = [], language = "tr" }) {
  return post("/chat", { question, investigationIds, experimentIds, language }, { timeoutMs: 130000 });
}
