import { useCallback, useState } from "react";
import { fetchInvestigations, fetchExperiments, fetchExperiment, compareExperiments } from "../services/apiClient";
import { comparisonRows, measurementText, experimentDate } from "../services/experimentData";
import useApiResource from "../hooks/useApiResource";
import SourceCard from "./SourceCard";
import ExperimentSourceView from "./ExperimentSourceView";
import { formatNumber, investigationDescription, warningText } from "../services/format";

function Warnings({ warnings = [] }) {
  return warnings.length > 0 && <div className="warnings-box">{warnings.map((warning, index) => (
    <p key={`${warning.code}-${index}`}><strong>{warning.code}</strong>: {warningText(warning)}</p>
  ))}</div>;
}

function ErrorMessage({ error, retry }) {
  return <div role="alert" className="warnings-box">
    {error.code && `${error.code}: `}{error.message}
    {error.requestId && <small> Request: {error.requestId}</small>}
    <button type="button" className="nasa-btn nasa-btn-xs" onClick={retry}>Retry</button>
  </div>;
}

export default function ExperimentExplorer() {
  const [filters, setFilters] = useState({ investigationId: "", fuel: "", page: 0, size: 20 });
  const [fuelInput, setFuelInput] = useState("");
  const [retry, setRetry] = useState(0);
  const [detailId, setDetailId] = useState(null);
  const [compareIds, setCompareIds] = useState([]);
  const loadCatalog = useCallback(() => fetchInvestigations(), []);
  const catalog = useApiResource(loadCatalog, `catalog:${retry}`);
  const loadPage = useCallback(() => fetchExperiments(filters), [filters]);
  const list = useApiResource(loadPage, `${JSON.stringify(filters)}:${retry}`);
  const loadDetail = useCallback(() => fetchExperiment(detailId), [detailId]);
  const detail = useApiResource(loadDetail, detailId ? `${detailId}:${retry}` : null);
  const loadComparison = useCallback(() => compareExperiments(compareIds), [compareIds]);
  const comparison = useApiResource(loadComparison, compareIds.length >= 2 ? `${compareIds.join(",")}:${retry}` : null);
  const page = list.data;
  const experiment = detail.data;
  const result = comparison.data;
  const reload = () => setRetry((value) => value + 1);

  function changeFilters(patch) {
    setFilters((previous) => ({ ...previous, ...patch, page: 0 }));
    setDetailId(null);
  }

  function toggleComparison(id) {
    setCompareIds((previous) => previous.includes(id)
      ? previous.filter((item) => item !== id)
      : previous.length < 3 ? [...previous, id] : previous);
  }

  return <div className="explorer-container">
    <div className="panel-card">
      <div className="panel-card-header">
        <div><span className="section-eyebrow">NASA PSI INVESTIGATIONS</span><h3>Experiment catalog</h3></div>
        <form className="filter-controls-row" onSubmit={(event) => { event.preventDefault(); changeFilters({ fuel: fuelInput.trim() }); }}>
          <select className="nasa-select" aria-label="Investigation filter" value={filters.investigationId}
            onChange={(event) => changeFilters({ investigationId: event.target.value })}>
            <option value="">All investigations</option>
            {(catalog.data || []).map((inv) => <option key={inv.investigationId} value={inv.investigationId}>{inv.investigationId} · {inv.name}</option>)}
          </select>
          <input className="nasa-input" aria-label="Fuel filter" placeholder="Fuel name (exact match)" value={fuelInput} onChange={(event) => setFuelInput(event.target.value)} />
          <button className="nasa-btn" type="submit">Filter</button>
          <button className="nasa-btn" type="button" onClick={() => { setFuelInput(""); changeFilters({ investigationId: "", fuel: "" }); }}>Clear</button>
        </form>
      </div>
      {catalog.loading && <p role="status">Loading investigations…</p>}
      {catalog.error && <ErrorMessage error={catalog.error} retry={reload} />}
      {catalog.data?.length === 0 && <p>The investigation catalog is empty.</p>}
      <div className="investigation-pills-grid">{(catalog.data || []).map((inv) => (
        <button type="button" key={inv.investigationId} className={`inv-pill-card ${filters.investigationId === inv.investigationId ? "active" : ""}`}
          onClick={() => changeFilters({ investigationId: inv.investigationId })}>
          <span className="inv-id-badge">{inv.investigationId}</span><div className="inv-pill-name">{inv.name}</div><p>{investigationDescription(inv)}</p>
        </button>
      ))}</div>
    </div>

    <div className="explorer-split-grid">
      <div className="panel-card">
        <div className="panel-card-header"><h4>Experiment and specimen records{page && ` (${formatNumber(page.totalElements)} records)`}</h4><span>Comparison: {formatNumber(compareIds.length)}/3</span></div>
        {list.loading && <p role="status">Loading experiments…</p>}
        {list.error && <ErrorMessage error={list.error} retry={reload} />}
        {page?.items.length === 0 && <p role="status">No experiment records match these filters.</p>}
        {page?.items.length > 0 && <div className="nasa-table-wrapper"><table className="nasa-table">
          <thead><tr><th>Compare</th><th>Experiment ID</th><th>Source test #</th><th>Fuel</th><th>Date</th><th>Reported outcome</th><th>Action</th></tr></thead>
          <tbody>{page.items.map((exp) => <tr key={exp.experimentId} className={detailId === exp.experimentId ? "row-selected" : ""}>
            <td><input type="checkbox" checked={compareIds.includes(exp.experimentId)} disabled={compareIds.length >= 3 && !compareIds.includes(exp.experimentId)}
              onChange={() => toggleComparison(exp.experimentId)} aria-label={`${exp.experimentId} compare`} /></td>
            <td className="mono-cell">{exp.experimentId}</td><td>{exp.sourceTestId}</td><td>{exp.fuel || "Not reported"}</td>
            <td>{experimentDate(exp)}</td><td>{exp.reportedOutcome || "Not reported"}</td>
            <td><button className="nasa-btn nasa-btn-xs" onClick={() => setDetailId(exp.experimentId)}>Details</button></td>
          </tr>)}</tbody>
        </table></div>}
        {page && <div className="filter-controls-row">
          <button className="nasa-btn nasa-btn-xs" disabled={page.page === 0} onClick={() => { setFilters({ ...filters, page: page.page - 1 }); setDetailId(null); }}>Previous</button>
          <span>Page {formatNumber(page.totalPages ? page.page + 1 : 0)} / {formatNumber(page.totalPages)}</span>
          <button className="nasa-btn nasa-btn-xs" disabled={page.page + 1 >= page.totalPages} onClick={() => { setFilters({ ...filters, page: page.page + 1 }); setDetailId(null); }}>Next</button>
        </div>}
      </div>

      <div className="panel-card detail-inspector-card">
        {!detailId && <p>Open an experiment to review its conditions, measurements and original source cells.</p>}
        {detail.loading && <p role="status">Loading experiment details…</p>}
        {detail.error && <ErrorMessage error={detail.error} retry={reload} />}
        {experiment && <>
          <h4>{experiment.experimentId} · Test {experiment.sourceTestId}</h4>
          <p>{experiment.experimentIdentifier} · {experiment.fuel} · {experimentDate(experiment)}</p>
          <p>Reported outcome: {experiment.reportedOutcome || "Not reported"}</p>
          <ExperimentSourceView key={experiment.experimentId} experiment={experiment} />
          <div className="subpanel-title">Conditions and measurements</div>
          {experiment.measurements.length === 0 && <p>This source has no numerical outcome measurements. The entries below are specimen conditions and qualitative source fields.</p>}
          {[...experiment.conditions, ...experiment.measurements].map((measurement, index) => <div key={`${measurement.name}:${index}`} className="measurement-item">
            <div className="measurement-top"><strong>{measurement.name}</strong><span className="qualifier-badge">{measurement.qualifier}</span><span className="quality-badge">{measurement.qualityStatus}</span></div>
            <div className="measurement-values"><span>{measurementText(measurement)}</span><span>Source cell: <code>{JSON.stringify(measurement.rawValue)}</code></span></div>
          </div>)}
          {experiment.reportedFindings.length > 0 && <div className="findings-box"><h4>Reported findings</h4>{experiment.reportedFindings.map((finding, index) => <p key={index}>
            <strong>{finding.name}:</strong> {finding.value} <span> · Raw value: <code>{JSON.stringify(finding.rawValue)}</code> · {finding.sourceId}</span>
          </p>)}</div>}
          <Warnings warnings={experiment.warnings} />
          {experiment.sources.map((source) => <SourceCard key={source.sourceId} source={source} />)}
        </>}
      </div>
    </div>

    <div className="panel-card">
      <h4>Experiment comparison</h4>
      <div className="filter-controls-row">{compareIds.map((id) => <button className="nasa-btn nasa-btn-xs" key={id} onClick={() => toggleComparison(id)}>{id} ×</button>)}</div>
      {compareIds.length < 2 && <p>Select 2 or 3 experiments to compare.</p>}
      {comparison.loading && <p role="status">Loading comparison…</p>}
      {comparison.error && <ErrorMessage error={comparison.error} retry={reload} />}
      {result && <>
        <p>Status: <strong>{result.status}</strong></p>
        {result.status === "INSUFFICIENT_DATA" && <p>There are not enough verified measurements for a numerical comparison.</p>}
        <div className="comparison-series-grid">{result.series.map((series) => {
          const max = Math.max(1, ...series.points.filter((point) => Number.isFinite(point.value)).map((point) => Math.abs(point.value)));
          return <div key={`${series.metric}:${series.unit}`} className="series-card">
            <h4>{series.metric} {series.unit && `(${series.unit})`}</h4>
            {comparisonRows(series, result.experimentIds).map(({ experimentId, point }) => <div className="series-bar-row" key={experimentId}>
              <div className="series-bar-meta"><span>{experimentId}</span><strong>{point ? `${formatNumber(point.value)} ${series.unit || ""}` : "No verified value"}</strong></div>
              {point && <><div className="series-bar-track"><div className="series-bar-fill" style={{ width: `${Math.abs(point.value) / max * 100}%` }} /></div><small>{point.sourceId}</small></>}
            </div>)}
          </div>;
        })}</div>
        <div className="nasa-table-wrapper"><table className="nasa-table"><thead><tr><th>Field</th>{result.experimentIds.map((id) => <th key={id}>{id}</th>)}<th>Note</th></tr></thead>
          <tbody>{result.differences.map((difference) => <tr key={difference.field}><td>{difference.field}</td>{result.experimentIds.map((id) => {
            const value = difference.values.find((entry) => entry.experimentId === id)?.value;
            return <td key={id}>{value == null ? "Missing / excluded" : formatNumber(value)}</td>;
          })}<td>{difference.note?.replace("Tüm doğrulanmış değerler eşit.", "All verified values are equal.").replace("Fark (max - min)", "Difference (max - min)")}</td></tr>)}</tbody>
        </table></div>
        <Warnings warnings={result.warnings} />
        {result.sources.map((source) => <SourceCard key={source.sourceId} source={source} />)}
      </>}
    </div>
  </div>;
}
