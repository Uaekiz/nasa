export const SCENARIO_FIELDS = [
  ["oxygenPercent", "Oxygen", "%"], ["pressureKpa", "Pressure", "kPa"],
  ["airflowCmS", "Airflow", "cm/s"], ["gravityG", "Gravity", "g"],
  ["temperatureC", "Temperature", "°C"], ["ignitionPowerW", "Igniter power", "W"],
  ["material", "Material", ""], ["flowDirection", "Flow direction", ""],
  ["coPpm", "CO", "ppm"], ["co2Percent", "CO₂", "%"],
  ["coMeasurementPhase", "CO measurement phase", ""], ["co2MeasurementPhase", "CO₂ measurement phase", ""],
];

export const MEASUREMENT_PHASES = [
  ["UNSPECIFIED", "Not specified"], ["INITIAL", "Initial measurement"], ["FINAL", "Final measurement"],
];
const PHASE_KEYS = ["coMeasurementPhase", "co2MeasurementPhase"];

export function scenarioParameters(params, phases = {}) {
  return { ...params,
    coMeasurementPhase: phases.coMeasurementPhase ?? params.coMeasurementPhase ?? "UNSPECIFIED",
    co2MeasurementPhase: phases.co2MeasurementPhase ?? params.co2MeasurementPhase ?? "UNSPECIFIED",
  };
}

export function sameScenario(left, right) {
  if (!left || !right) return false;
  const a = scenarioParameters(left), b = scenarioParameters(right), keys = Object.keys(a);
  return keys.length === Object.keys(b).length && keys.every((key) => Object.hasOwn(b, key) && Object.is(a[key], b[key]));
}

export function validateScenarioParams(params) {
  const limits = {
    oxygenPercent: [0, 100], pressureKpa: [0, Infinity], airflowCmS: [0, Infinity],
    gravityG: [0, Infinity], temperatureC: [-273.15, Infinity], ignitionPowerW: [0, Infinity],
    coPpm: [0, Infinity], co2Percent: [0, 100],
  };
  for (const [name, [min, max]] of Object.entries(limits)) {
    const value = params[name];
    if (!Number.isFinite(value) || value < min || value > max || (name === "pressureKpa" && value === 0)) {
      throw new Error(`${SCENARIO_FIELDS.find(([key]) => key === name)[1]} must be a finite value within the supported input range.`);
    }
  }
  if (typeof params.material !== "string" || !params.material.trim() || params.material.length > 120) throw new Error("Select a valid material.");
  if (!["CONCURRENT", "OPPOSED"].includes(params.flowDirection)) throw new Error("Select a valid flow direction.");
  for (const key of PHASE_KEYS) if (!MEASUREMENT_PHASES.some(([phase]) => phase === params[key])) throw new Error("Select a valid CO and CO₂ measurement phase.");
}

export function createScenarioSnapshot(params, imageDataUrl, capturedAt = new Date().toISOString()) {
  const captured = scenarioParameters(params);
  validateScenarioParams(captured);
  if (typeof imageDataUrl !== "string" || !/^data:image\/png;base64,.+/.test(imageDataUrl)) throw new Error("The 3D canvas did not provide a PNG image. Check WebGL and capture again.");
  return { capturedAt, params: { ...captured }, imageDataUrl };
}

export function validateScenarioResponse(response, snapshot) {
  if (!response || typeof response.requestId !== "string" || !response.requestId
    || !response.evidence || typeof response.evidence !== "object"
    || !sameScenario(response.params, snapshot.params)
    || Date.parse(response.capturedAt) !== Date.parse(snapshot.capturedAt)) {
    throw new Error("The analysis response does not match the captured scenario. Capture and submit again.");
  }
  return response;
}

// Abort is advisory; the ticket also rejects late completions if ignored by IO.
export function createScenarioRequestGate() {
  let epoch = 0, controller = null, disposed = false;
  const invalidate = () => { epoch += 1; controller?.abort(); controller = null; };
  return {
    begin() {
      if (disposed) throw new Error("The scenario panel has closed.");
      invalidate(); controller = new AbortController();
      return { epoch, signal: controller.signal };
    },
    accepts(ticket) { return !disposed && ticket.epoch === epoch && !ticket.signal.aborted; },
    invalidate,
    resume() { disposed = false; },
    dispose() { invalidate(); disposed = true; },
  };
}

export function sourceDifferences(primary, alternate) {
  if (Array.isArray(primary.recordDifferences)) return primary.recordDifferences.filter((item) => item.alternateCitationId === alternate.citationId);
  // Never pair different CSV/XLSX headers without an explicit backend mapping.
  return Object.entries(primary.fields || {})
    .filter(([field, value]) => Object.hasOwn(alternate.fields || {}, field) && alternate.fields[field] !== value)
    .map(([field, primaryValue]) => ({ field, primaryValue, alternateValue: alternate.fields[field], alternateCitationId: alternate.citationId }));
}

export function citationAnchor(prefix, citationId) {
  return `${prefix}-source-${String(citationId).replace(/[^a-zA-Z0-9_-]/g, "-")}`;
}
