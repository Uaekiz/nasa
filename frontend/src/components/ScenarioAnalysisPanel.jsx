import { useEffect, useId, useRef, useState } from "react";
import { submitScenario } from "../services/apiClient";
import { formatNumber, formatDateTime } from "../services/format";
import {
  SCENARIO_FIELDS, MEASUREMENT_PHASES, scenarioParameters, sameScenario,
  validateScenarioParams, createScenarioSnapshot, validateScenarioResponse,
  createScenarioRequestGate, sourceDifferences, citationAnchor,
} from "../services/scenarioAnalysis";
import SourceCard from "./SourceCard";

const STATUS_LABELS = {
  COMPARED: "Compared", PARTIAL: "Partly comparable", NOT_COMPARABLE: "Not comparable",
  PHASE_UNSPECIFIED: "Measurement phase not specified", NO_SOURCE: "No matching source field",
  MATCH: "Same value", DIFFERENT: "Different value",
};
const PARAMETER_LABELS = Object.fromEntries(SCENARIO_FIELDS.map(([key, label]) => [key, label]));
const PARAMETER_UNITS = Object.fromEntries(SCENARIO_FIELDS.map(([key, , unit]) => [key, unit]));

function valueText(value) {
  if (value == null) return "Not specified";
  if (typeof value === "number") return formatNumber(value);
  return { CONCURRENT: "Concurrent", OPPOSED: "Opposed", UNSPECIFIED: "Not specified", INITIAL: "Initial measurement", FINAL: "Final measurement" }[value] || String(value);
}

function RawCell({ value }) {
  if (value === "") return <span>Blank source cell <code>""</code></span>;
  if (value == null) return <span>Field not supplied by this source</span>;
  return <code className="source-cell-raw">{typeof value === "string" ? JSON.stringify(value) : String(value)}</code>;
}

function Citations({ ids = [], prefix }) {
  function follow(event, id) {
    const target = document.getElementById(citationAnchor(prefix, id));
    if (!target) return;
    event.preventDefault();
    let parent = target;
    while (parent) {
      if (parent.tagName === "DETAILS") parent.open = true;
      parent = parent.parentElement;
    }
    target.scrollIntoView({ block: "start", behavior: "smooth" });
    target.querySelector("summary")?.focus({ preventScroll: true });
  }
  return ids.map((id) => <a className="scenario-citation-link" key={id} href={`#${citationAnchor(prefix, id)}`} onClick={(event) => follow(event, id)}>[{id}]</a>);
}

function SourceRecord({ source, prefix, primary }) {
  const differences = primary ? sourceDifferences(primary, source) : [];
  return <details className="scenario-source" id={source.citationId ? citationAnchor(prefix, source.citationId) : undefined}>
    <summary tabIndex={0}>{source.citationId && `[${source.citationId}] `}{source.investigationId} · Test {source.sourceTestId} · {source.sourceType} · Row {formatNumber(source.rowNumber)}</summary>
    {source.sheetName && <p>Worksheet: {source.sheetName}</p>}
    {source.sourceClass && <p>Source experiment class: {source.sourceClass.toLowerCase()}</p>}
    <SourceCard source={source} />
    <h5>Comparison with captured inputs</h5>
    {(source.comparisons || []).length === 0 && <p>No comparable scenario fields are provided by this source.</p>}
    {(source.comparisons || []).map((comparison) => <div className="measurement-item" key={comparison.parameter}>
      <strong>{PARAMETER_LABELS[comparison.parameter] || comparison.parameter}: {STATUS_LABELS[comparison.status] || comparison.status}</strong>
      <p>Captured input: {valueText(comparison.scenarioValue)}{PARAMETER_UNITS[comparison.parameter] ? ` ${PARAMETER_UNITS[comparison.parameter]}` : ""}</p>
      <p>Source field: {comparison.sourceField || "No matching field"} · Raw cell: <RawCell value={comparison.sourceValue} /></p>
      {comparison.status === "COMPARED" && <p>Difference (scenario − source): {formatNumber(comparison.difference)} {comparison.unit}</p>}
      {comparison.reason && <p>{comparison.reason}</p>}
    </div>)}
    {primary && <section className="scenario-source-differences" aria-label="Differences between source versions">
      <h5>Differences from the primary source version</h5>
      <p>The source versions remain separate. Only mapped or identically named fields can be compared.</p>
      {differences.length === 0 ? <p>No differences were identified in comparable fields. Different layouts may contain additional, unpaired fields below.</p>
        : <div className="nasa-table-wrapper"><table className="nasa-table"><thead><tr><th>Field</th><th>Primary source</th><th>This source version</th></tr></thead>
          <tbody>{differences.map((difference, index) => <tr key={`${difference.field}:${index}`}><th scope="row">{difference.field}</th><td>{difference.primaryField && <small>Original field: {difference.primaryField}<br /></small>}<RawCell value={difference.primaryValue} /></td><td>{difference.alternateField && <small>Original field: {difference.alternateField}<br /></small>}<RawCell value={difference.alternateValue} /></td></tr>)}</tbody></table></div>}
    </section>}
    <h5>Original source cells</h5>
    <div className="nasa-table-wrapper"><table className="nasa-table"><thead><tr><th scope="col">Original field</th><th scope="col">Original value</th></tr></thead>
      <tbody>{Object.entries(source.fields || {}).map(([name, value]) => <tr key={name}><th scope="row">{name}</th><td><RawCell value={value} /></td></tr>)}</tbody></table></div>
    {(source.alternateRecords || []).length > 0 && <section className="scenario-alternates" aria-label="Separate source versions">
      <h5>Other source versions of this test ({formatNumber(source.alternateRecords.length)})</h5>
      <p>CSV and workbook cells are shown independently; their values are not combined.</p>
      {source.alternateRecords.map((alternate) => <SourceRecord key={`${alternate.sourceId}:${alternate.sheetName}:${alternate.rowNumber}`} source={alternate} prefix={prefix} primary={source} />)}
    </section>}
  </details>;
}

export default function ScenarioAnalysisPanel({ params, onCaptureImage }) {
  const [phases, setPhases] = useState({ coMeasurementPhase: "UNSPECIFIED", co2MeasurementPhase: "UNSPECIFIED" });
  const [snapshot, setSnapshot] = useState(null);
  const [captureError, setCaptureError] = useState("");
  const [submission, setSubmission] = useState(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isCapturing, setIsCapturing] = useState(false);
  const [submitError, setSubmitError] = useState("");
  const gate = useRef(createScenarioRequestGate());
  const captureGeneration = useRef(0);
  const prefix = `scenario-${useId().replace(/[^a-zA-Z0-9_-]/g, "")}`;
  const currentParams = scenarioParameters(params, phases);
  const isStale = snapshot !== null && !sameScenario(snapshot.params, currentParams);
  const evidence = submission?.evidence;
  const narrative = evidence?.narrative;

  useEffect(() => {
    const currentGate = gate.current;
    currentGate.resume();
    return () => { captureGeneration.current += 1; currentGate.dispose(); };
  }, []);

  async function handleCaptureScenario() {
    gate.current.invalidate();
    const capture = ++captureGeneration.current;
    setIsSubmitting(false);
    setIsCapturing(true);
    setSnapshot(null);
    setSubmission(null);
    setSubmitError("");
    setCaptureError("");
    try {
      const capturedParams = { ...currentParams };
      validateScenarioParams(capturedParams);
      const capturedAt = new Date().toISOString();
      const imageDataUrl = await onCaptureImage();
      if (capture !== captureGeneration.current) return;
      setSnapshot(createScenarioSnapshot(capturedParams, imageDataUrl, capturedAt));
    } catch (error) {
      if (capture === captureGeneration.current) setCaptureError(error instanceof Error ? error.message : "The 3D image could not be captured.");
    } finally {
      if (capture === captureGeneration.current) setIsCapturing(false);
    }
  }

  async function handleSubmitScenario() {
    if (!snapshot || isStale || isSubmitting) return;
    const ticket = gate.current.begin();
    const submittedSnapshot = snapshot;
    setIsSubmitting(true);
    setSubmitError("");
    setSubmission(null);
    try {
      const response = await submitScenario(submittedSnapshot, { signal: ticket.signal });
      if (gate.current.accepts(ticket)) setSubmission(validateScenarioResponse(response, submittedSnapshot));
    } catch (error) {
      if (gate.current.accepts(ticket)) setSubmitError(error.message || "The captured scenario could not be submitted.");
    } finally {
      if (gate.current.accepts(ticket)) setIsSubmitting(false);
    }
  }

  return <section className="panel-card scenario-analysis-panel" aria-label="Source-backed scenario analysis">
    <div className="panel-card-header"><div><span className="section-eyebrow">SOURCE-BACKED SCENARIO ANALYSIS</span><h3>Review the current scenario</h3></div></div>
    <p>Capture the current inputs and 3D view, then request source-based comparisons for that saved scenario.</p>
    <div className="scenario-phases">
      {[["coMeasurementPhase", "CO measurement phase"], ["co2MeasurementPhase", "CO₂ measurement phase"]].map(([key, label]) => <label key={key}>{label}
        <select className="nasa-select" aria-label={label} value={phases[key]} onChange={(event) => setPhases((previous) => ({ ...previous, [key]: event.target.value }))}>
          {MEASUREMENT_PHASES.map(([value, text]) => <option key={value} value={value}>{text}</option>)}
        </select>
      </label>)}
    </div>
    <p>Select what the CO and CO₂ inputs represent. A phase left unspecified cannot be matched to an initial or final source measurement. Oxygen comparisons use the source's calibrated initial O₂ % by volume; original fields and units are shown for each comparison.</p>
    <button type="button" className="nasa-btn nasa-btn-primary nasa-btn-block" onClick={handleCaptureScenario} disabled={isCapturing}>
      {isCapturing ? "Capturing…" : snapshot ? "Capture the current scenario again" : "Capture scenario and image"}
    </button>
    {captureError && <p role="alert">{captureError}</p>}
    {snapshot && <>
      <p role="status">{isStale ? "Inputs changed. This capture and its analysis belong to the previous scenario." : "The current scenario inputs are captured."}</p>
      <section className="scenario-inputs" aria-label="Captured scenario inputs"><h4>Captured inputs</h4><p>Captured at: {formatDateTime(snapshot.capturedAt)}</p>
        <div className="nasa-table-wrapper"><table className="nasa-table"><thead><tr><th scope="col">Parameter</th><th scope="col">Captured value</th></tr></thead>
          <tbody>{SCENARIO_FIELDS.map(([key, label, unit]) => <tr key={key}><th scope="row">{label}</th><td>{valueText(snapshot.params[key])}{unit ? ` ${unit}` : ""}</td></tr>)}</tbody></table></div>
      </section>
      <section className="scenario-preview" aria-label="Captured 3D view"><h4>Captured 3D view</h4>
        <img src={snapshot.imageDataUrl} alt="Illustrative 3D view of the captured scenario" style={{ display: "block", width: "100%", borderRadius: 8 }} />
        <p>The screenshot stays in this browser. It is not sent to RAG or inspected by a vision model.</p>
        <a className="nasa-btn nasa-btn-xs" href={snapshot.imageDataUrl} download={`flamescope-scenario-${snapshot.capturedAt.replace(/[:.]/g, "-")}.png`}>Download image</a>
      </section>
      <button type="button" className="nasa-btn nasa-btn-primary nasa-btn-block" onClick={handleSubmitScenario} disabled={isSubmitting || isStale}>
        {isSubmitting ? "Reviewing captured inputs…" : "Analyze captured scenario"}
      </button>
      {isStale && <p>Capture the current inputs again before submitting a new analysis.</p>}
      {isSubmitting && <p role="status">The analysis uses the captured inputs{isStale ? "; the current inputs have changed" : ""}. You can capture again to cancel this request.</p>}
      {submitError && <p role="alert">{submitError}</p>}
      {submission && <section aria-label="Captured scenario analysis result">
        <p>Source search completed. Request ID: {submission.requestId}</p>
        {isStale && <p role="status">This result belongs to the previously captured scenario.</p>}
        <section className="scenario-assessment" aria-label="Scenario assessment"><h4>Scenario assessment</h4>
          {narrative ? <>
            <p>{narrative.message}</p>
            {narrative.modelUsed && <p>Check ordering model: {narrative.modelUsed}. Source observations and comparisons are deterministic.</p>}
            {narrative.fallbackReason && <p role="status">{narrative.fallbackReason}</p>}
            {(narrative.observations || []).map((point, index) => <p key={`observation-${index}`}>{point.text} <Citations ids={point.citationIds} prefix={prefix} /></p>)}
          </> : <p>No narrative was returned. Source records and deterministic comparisons remain available below.</p>}
          {evidence?.status === "INSUFFICIENT_EVIDENCE" && <p>No reviewed source record matches this material and experiment class.</p>}
        </section>
        {(narrative?.nextChecks || []).length > 0 && <section aria-label="Suggested next checks"><h4>Next checks</h4>
          {narrative.nextChecks.map((point, index) => <p key={`check-${index}`}>{point.text} <Citations ids={point.citationIds} prefix={prefix} /></p>)}
        </section>}
        <section className="scenario-coverage" aria-label="Source selection and parameter coverage"><h4>Source selection and coverage</h4>
          <p>Material-matched source rows: {formatNumber(evidence?.matchedRecordCount ?? 0)} · Experiment groups: {formatNumber(evidence?.matchedExperimentCount ?? 0)}</p>
          <p>Records are grouped by investigation and test ID, then ordered within each investigation by the mapped conditions. This ordering is not full experiment equivalence or statistical confidence.</p>
          {(evidence?.selectionDetails || []).map((selection) => <p key={selection.investigationId}>{selection.investigationId} · {selection.sourceClass?.toLowerCase()} · Ordering fields: {(selection.sortParameters || []).map((key) => PARAMETER_LABELS[key] || key).join(", ") || "Material name and source provenance"}</p>)}
          {(evidence?.parameterCoverage || []).length > 0 && <div className="nasa-table-wrapper"><table className="nasa-table"><thead><tr><th>Input</th><th>Coverage</th><th>Details</th></tr></thead>
            <tbody>{evidence.parameterCoverage.map((field) => <tr key={field.parameter}><th scope="row">{PARAMETER_LABELS[field.parameter] || field.parameter}</th><td>{STATUS_LABELS[field.status] || field.status}</td><td>{field.reason}</td></tr>)}</tbody></table></div>}
          {(evidence?.limitations || []).map((limitation, index) => <p key={index}>{limitation}</p>)}
        </section>
        <section aria-label="Scenario source records"><h4>Sources and original cells</h4>
          {(evidence?.sources || []).map((source) => <SourceRecord key={`${source.sourceId}:${source.sheetName}:${source.rowNumber}`} source={source} prefix={prefix} />)}
        </section>
      </section>}
    </>}
  </section>;
}
