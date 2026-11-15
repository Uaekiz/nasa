import assert from "node:assert/strict";
import { test } from "node:test";
import {
  scenarioParameters, sameScenario, validateScenarioParams, createScenarioSnapshot,
  validateScenarioResponse, createScenarioRequestGate, sourceDifferences, citationAnchor,
} from "../src/services/scenarioAnalysis.js";

const params = () => ({
  oxygenPercent: 21, pressureKpa: 101.3, airflowCmS: 8.5, gravityG: 0,
  temperatureC: 23, ignitionPowerW: 10, material: "PMMA Film", flowDirection: "CONCURRENT",
  coPpm: 0, co2Percent: 0.04,
});
const image = "data:image/png;base64,iVBORw0KGgo=";
const capturedAt = "2026-11-15T12:00:00.000Z";

test("capture preserves a separate input snapshot and leaves unspecified gas phases explicit", () => {
  const current = params();
  const captured = createScenarioSnapshot(current, image, capturedAt);
  current.oxygenPercent = 30;
  assert.equal(captured.params.oxygenPercent, 21);
  assert.equal(captured.params.coPpm, 0);
  assert.equal(captured.params.coMeasurementPhase, "UNSPECIFIED");
  assert.equal(captured.params.co2MeasurementPhase, "UNSPECIFIED");
  assert.equal(captured.imageDataUrl, image);
  assert.equal(captured.capturedAt, capturedAt);
  assert.equal(sameScenario(captured.params, current), false);
});

test("changing any captured parameter or gas phase marks the analysis stale", () => {
  const current = scenarioParameters(params(), { coMeasurementPhase: "INITIAL" });
  const saved = { ...current };
  assert.ok(sameScenario(saved, current));
  for (const [key, value] of [["gravityG", 0.5], ["material", "Methanol"], ["temperatureC", 24], ["coMeasurementPhase", "FINAL"], ["co2MeasurementPhase", "FINAL"]]) {
    assert.equal(sameScenario(saved, { ...current, [key]: value }), false, key);
  }
  assert.equal(sameScenario(saved, { ...current, unexpectedInput: 5 }), false);
  assert.ok(sameScenario(params(), scenarioParameters(params()))); // Backward-compatible unspecified phases.
});

test("invalid numeric inputs, enum values and unusable canvas captures are shown as errors", () => {
  for (const patch of [
    { oxygenPercent: NaN }, { pressureKpa: 0 }, { airflowCmS: Infinity }, { gravityG: -1 },
    { temperatureC: -274 }, { ignitionPowerW: -5 }, { coPpm: null }, { co2Percent: 101 },
    { flowDirection: "UNKNOWN" }, { material: " " }, { coMeasurementPhase: "AVERAGE" },
  ]) assert.throws(() => validateScenarioParams(scenarioParameters({ ...params(), ...patch })), Error);
  for (const bad of [undefined, "data:,", "", "data:image/png;base64,", "http://example/image.png"]) {
    assert.throws(() => createScenarioSnapshot(params(), bad), /PNG/);
  }
});

test("recapture and repeated submissions abort and reject older completions even if IO ignores cancellation", async () => {
  const gate = createScenarioRequestGate();
  let shown = null;
  let finishOld;
  const old = gate.begin();
  const pending = new Promise((resolve) => { finishOld = resolve; }).then((response) => {
    if (gate.accepts(old)) shown = response;
  });
  gate.invalidate(); // Capture a new image/inputs.
  assert.ok(old.signal.aborted);
  const newer = gate.begin();
  if (gate.accepts(newer)) shown = "new scenario result";
  finishOld("old scenario result");
  await pending;
  assert.equal(shown, "new scenario result");
  assert.equal(gate.accepts(old), false);
  const retry = gate.begin();
  assert.ok(newer.signal.aborted);
  assert.ok(gate.accepts(retry));
});

test("unmount invalidates pending work and a StrictMode effect resume cannot revive it", () => {
  const gate = createScenarioRequestGate();
  const pending = gate.begin();
  gate.dispose();
  assert.ok(pending.signal.aborted);
  assert.equal(gate.accepts(pending), false);
  assert.throws(() => gate.begin(), /closed/);
  gate.resume();
  assert.equal(gate.accepts(pending), false);
  assert.ok(gate.accepts(gate.begin()));
});

test("response must echo the submitted capture, including selected measurement semantics", () => {
  const snapshot = createScenarioSnapshot(scenarioParameters(params(), { coMeasurementPhase: "FINAL" }), image, capturedAt);
  const valid = { requestId: "actual-request", capturedAt, params: snapshot.params, evidence: { sources: [] } };
  assert.equal(validateScenarioResponse(valid, snapshot), valid);
  for (const patch of [
    { params: { ...snapshot.params, coMeasurementPhase: "INITIAL" } },
    { params: { ...snapshot.params, pressureKpa: 80 } },
    { capturedAt: "2026-11-15T12:00:01.000Z" }, { requestId: "" }, { evidence: null },
  ]) assert.throws(() => validateScenarioResponse({ ...valid, ...patch }, snapshot), /does not match/);
});

test("source versions retain raw differences without pairing unrelated headers or treating blank as zero", () => {
  const primary = { fields: { "CO (ppm)": "0", Material: "PMMA", "CSV-only": "x" } };
  const alternate = { citationId: "S1A1", fields: { "CO (ppm)": "", Material: "pmma", "Workbook-only": "x" } };
  const differences = sourceDifferences(primary, alternate);
  assert.equal(differences.length, 2);
  assert.deepEqual(differences[0], { field: "CO (ppm)", primaryValue: "0", alternateValue: "", alternateCitationId: "S1A1" });
  assert.ok(!differences.some((item) => /only/.test(item.field)));
  const mapped = { ...primary, recordDifferences: [
    { field: "Material", primaryValue: "PMMA", alternateValue: "pmma", alternateCitationId: "S1A1" },
    { field: "CO", primaryValue: "0", alternateValue: "4", alternateCitationId: "S1A2" },
  ] };
  assert.deepEqual(sourceDifferences(mapped, alternate), [mapped.recordDifferences[0]]);
  assert.notEqual(citationAnchor("panel", "S1"), citationAnchor("panel", "S1A1"));
});
