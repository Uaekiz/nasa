import { test } from "node:test";
import assert from "node:assert/strict";
import { formatNumber, formatDateTime, investigationDescription, warningText } from "../src/services/format.js";
import { measurementText, experimentDate } from "../src/services/experimentData.js";

test("normalized values use en-US grouping and decimal points without zero-filling missing data", () => {
  assert.equal(formatNumber(1234.567), "1,234.567");
  assert.equal(formatNumber(0), "0");
  for (const value of [null, undefined, NaN, Infinity, "1234.5"]) assert.equal(formatNumber(value), "Not reported");
  assert.equal(measurementText({ value: 1234.5, qualifier: "APPROXIMATE", qualityStatus: "VERIFIED", unit: "s" }), "~1,234.5 s");
  assert.equal(experimentDate({ dateRaw: "22-Jul" }), "22-Jul (year not provided in source)");
  assert.equal(formatDateTime("invalid"), "Not reported");
  assert.match(formatDateTime("2026-11-15T12:00:00Z"), /Nov 15, 2026/);
});

test("English descriptions and stored application warnings do not rewrite original source strings", () => {
  assert.match(investigationDescription({ investigationId: "PSI-101" }), /SAME-R/);
  assert.match(warningText({ code: "BURNING_RATE_UNIT_AMBIGUOUS", message: "original application message" }), /No mm\/s conversion/);
  const raw = "100 micron PMMA film   2 cm wide";
  assert.equal(warningText({ code: "ORIGINAL_SOURCE_NOTE", message: raw }), raw);
});
