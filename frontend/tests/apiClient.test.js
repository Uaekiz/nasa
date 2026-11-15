/* global global */
import assert from "node:assert/strict";
import { afterEach, test } from "node:test";
import { fetchInvestigations, fetchExperiments, fetchExperiment, fetchSource, fetchChatCapabilities, compareExperiments, askAiAssistant, sourceDocumentUrl, submitScenario } from "../src/services/apiClient.js";
import { comparisonRows, measurementText, loadedChatScopes } from "../src/services/experimentData.js";

const originalFetch = global.fetch;
afterEach(() => { global.fetch = originalFetch; });
const response = (body, status = 200) => new Response(JSON.stringify(body), { status });

test("empty backend results remain empty", async () => {
  global.fetch = async () => response({ items: [], totalElements: 0, totalPages: 0 });
  assert.deepEqual(await fetchInvestigations(), []);
  assert.equal((await fetchExperiments()).totalElements, 0);
});

test("every API operation propagates errors instead of supplying local experiments or model text", async () => {
  global.fetch = async () => response({ requestId: "actual-request", error: { code: "RAG_UNAVAILABLE", message: "Unavailable" } }, 503);
  for (const operation of [fetchInvestigations, fetchChatCapabilities, fetchExperiments, () => fetchExperiment("id"), () => fetchSource("source"), () => compareExperiments(["a", "b"]), () => askAiAssistant({ question: "test" })]) {
    await assert.rejects(operation, { code: "RAG_UNAVAILABLE", requestId: "actual-request", status: 503 });
  }
  global.fetch = async () => { throw new TypeError("network"); };
  await assert.rejects(() => askAiAssistant({ question: "test" }), /backend API/i);
});

test("summary filters, detail/source identifiers, and comparison/chat payloads follow DTOs", async () => {
  const calls = [];
  global.fetch = async (url, options) => { calls.push({ url, options }); return response({ items: [] }); };
  await fetchExperiments({ investigationId: "PSI-69", fuel: "Heptane", page: 2, size: 20 });
  assert.equal(calls[0].url, "/api/v1/experiments?page=2&size=20&investigationId=PSI-69&fuel=Heptane");
  await fetchExperiment("PSI-69:run-0001");
  assert.equal(calls[1].url, "/api/v1/experiments/PSI-69%3Arun-0001");
  await fetchSource("PSI-69:experimental-table:v1");
  assert.equal(calls[2].url, "/api/v1/sources/PSI-69%3Aexperimental-table%3Av1");
  await compareExperiments(["a", "b"]);
  assert.deepEqual(JSON.parse(calls[3].options.body), { experimentIds: ["a", "b"] });
  await askAiAssistant({ question: "test", activeTelemetryParams: { fake: 42 } });
  assert.deepEqual(JSON.parse(calls[4].options.body), { question: "test", investigationIds: [], experimentIds: [], language: "en" });
});

test("measurement rendering preserves nulls, ranges, qualifiers and review status", () => {
  assert.equal(measurementText({ qualityStatus: "VERIFIED", qualifier: "RANGE", minValue: 1, maxValue: 3, unit: "s", value: null, startValue: null }), "1 – 3 s");
  assert.equal(measurementText({ qualityStatus: "VERIFIED", qualifier: "APPROXIMATE", value: 6, unit: "s" }), "~6 s");
  assert.match(measurementText({ qualityStatus: "MISSING", value: null, startValue: null }), /Missing/);
  assert.match(measurementText({ qualityStatus: "REQUIRES_REVIEW", value: .52, unit: "mm" }), /review/);
});

test("scenario transport keeps capture local, preserves all params and supports cancellation", async () => {
  const params = { oxygenPercent: 21, pressureKpa: 101.3, airflowCmS: 8.5, gravityG: 0, temperatureC: 22,
    ignitionPowerW: 10, material: "PMMA Film", flowDirection: "CONCURRENT", coPpm: 5, co2Percent: 0.1,
    coMeasurementPhase: "UNSPECIFIED", co2MeasurementPhase: "FINAL" };
  let call;
  global.fetch = async (url, options) => { call = { url, options }; return response({ status: "EVIDENCE_RETRIEVED" }); };
  await submitScenario({ capturedAt: "2026-11-15T12:00:00Z", params, imageDataUrl: "data:image/png;base64,LOCAL_ONLY" });
  assert.equal(call.url, "/api/v1/scenario-analyses");
  assert.deepEqual(JSON.parse(call.options.body), { capturedAt: "2026-11-15T12:00:00Z", params });
  assert.equal(call.options.headers["Accept-Language"], "en");
  assert.ok(!call.options.body.includes("LOCAL_ONLY"));
  global.fetch = async (_, { signal }) => new Promise((resolve, reject) => {
    signal.addEventListener("abort", () => reject(new DOMException("Cancelled", "AbortError")), { once: true });
  });
  const controller = new AbortController();
  const rejected = assert.rejects(submitScenario({ capturedAt: "now", params }, { signal: controller.signal }), { name: "AbortError" });
  controller.abort();
  await rejected;
});

test("sparse series align to experiment IDs without filling absent points with zero", () => {
  const rows = comparisonRows({ metric: "Burn time", points: [{ experimentId: "b", value: 0, sourceId: "s" }] }, ["a", "b", "c"]);
  assert.equal(rows[0].point, undefined);
  assert.equal(rows[1].point.value, 0);
  assert.equal(rows[2].point, undefined);
});

test("source URLs use backend file links and preserve PDF page references", () => {
  assert.equal(sourceDocumentUrl({ documentUrl: "/files/source.pdf" }, 4), "http://localhost/files/source.pdf#page=4");
  assert.equal(sourceDocumentUrl({ documentUrl: null }), null);
});

test("chat options require both loaded backend experiments and a ready English RAG source", () => {
  const backend = [{ investigationId: "PSI-69" }, { investigationId: "PSI-25" }];
  const capabilities = { status: "READY", language: "en", items: [
    { investigationId: "PSI-69", sourceIds: ["flex"] },
    { investigationId: "PSI-25", sourceIds: [] },
    { investigationId: "PSI-100", sourceIds: ["saffire"] },
  ] };
  assert.deepEqual(loadedChatScopes(backend, capabilities).map((i) => i.investigationId), ["PSI-69"]);
  assert.deepEqual(loadedChatScopes(backend, { ...capabilities, status: "BUILDING" }), []);
  assert.deepEqual(loadedChatScopes(backend, null), []);
});
