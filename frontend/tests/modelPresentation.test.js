import assert from "node:assert/strict";
import { test } from "node:test";
import { MISSION_PRESETS } from "../src/data/nasaPsiData.js";
import { evaluateFireRisk, generateMitigationRecommendations, generateTelemetryTimeline } from "../src/services/fireRiskEngine.js";

// Captured from the working model before the presentation-only cleanup.
// This guards the requested distinction: relabel a demonstration, retain its
// numerical behavior for the existing scene and charts.
const BEFORE = [
  ["iss-nominal", 95.5, 1.2, 94.3, [21.3, 8.5, 0, 15.4, 3.25, 155]],
  ["lunar-artemis", 99.2, 2.6, 96.6, [19.2, 23.2, 16.8, 17.5, 12, 197]],
  ["cygnus-saffire", 99.2, 2, 97.2, [21.9, 20, 0, 16.1, 3.48, 209]],
  ["bass2-quenching", 10.8, 1.2, 9.6, [15.2, 1.8, 0, 16.8, 0, 18]],
  ["mars-transit", 92.3, 1.6, 90.7, [18.6, 28.5, 25.9, 16.8, 4.64, 160]],
];

test("English presentation keeps every preset's existing model calculations", () => {
  for (const [id, score, variant, delta, metrics] of BEFORE) {
    const preset = MISSION_PRESETS.find((item) => item.id === id);
    const evaluation = evaluateFireRisk(preset.params);
    const plan = generateMitigationRecommendations(preset.params);
    assert.equal(evaluation.probability, score, id);
    assert.deepEqual(Object.values(evaluation.metrics), metrics, id);
    assert.equal(plan.optimizedProbability, variant, id);
    assert.equal(plan.totalReductionDelta, delta, id);
    assert.equal(Object.hasOwn(evaluation, "confidence"), false);
    assert.match(evaluation.riskLabelTr, /MODEL SCORE/);
    assert.match(evaluation.regimeDescription, /Illustrative/);
  }
});

test("example curves retain numerical points and identify an arbitrary reference", () => {
  const timeline = generateTelemetryTimeline(MISSION_PRESETS[1].params);
  assert.equal(timeline.length, 16);
  assert.deepEqual(timeline.map((point) => point.tSec), [-100, -90, -80, -70, -60, -50, -40, -30, -20, -10, 0, 10, 20, 30, 40, 50]);
  assert.equal(timeline[10].label, "REFERENCE");
  for (const point of timeline) {
    assert.ok(Number.isFinite(point.riskUnmitigated));
    assert.ok(Number.isFinite(point.riskMitigated));
    assert.ok(point.riskUnmitigated >= 0 && point.riskUnmitigated <= 100);
  }
});

test("retained chart variants do not claim source-supported mitigations", () => {
  const plan = generateMitigationRecommendations(MISSION_PRESETS[1].params);
  assert.ok(plan.recommendations.length > 0);
  for (const variant of plan.recommendations) {
    assert.equal(variant.psiReference, null);
    assert.match(variant.rationale, /Illustrative model variant only/);
    assert.ok(Number.isFinite(variant.riskReductionDelta));
  }
});
