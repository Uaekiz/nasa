import { useCallback, useState } from "react";
import { fetchInvestigations, fetchExperiments, fetchExperiment, compareExperiments } from "../services/apiClient";
import { comparisonRows, measurementText, experimentDate } from "../services/experimentData";
import useApiResource from "../hooks/useApiResource";
import SourceCard from "./SourceCard";
import ExperimentSourceView from "./ExperimentSourceView";

function Warnings({ warnings = [] }) {
  return warnings.length > 0 && <div className="warnings-box">{warnings.map((warning, index) => (
    <p key={`${warning.code}-${index}`}><strong>{warning.code}</strong>: {warning.message}</p>
  ))}</div>;
}

function ErrorMessage({ error, retry }) {
  return <div role="alert" className="warnings-box">
    {error.code && `${error.code}: `}{error.message}
    {error.requestId && <small> İstek: {error.requestId}</small>}
    <button type="button" className="nasa-btn nasa-btn-xs" onClick={retry}>Yeniden dene</button>
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
        <div><span className="section-eyebrow">NASA PSI ARAŞTIRMALARI</span><h3>Backend deney kataloğu</h3></div>
        <form className="filter-controls-row" onSubmit={(event) => { event.preventDefault(); changeFilters({ fuel: fuelInput.trim() }); }}>
          <select className="nasa-select" aria-label="Araştırma filtresi" value={filters.investigationId}
            onChange={(event) => changeFilters({ investigationId: event.target.value })}>
            <option value="">Tüm araştırmalar</option>
            {(catalog.data || []).map((inv) => <option key={inv.investigationId} value={inv.investigationId}>{inv.investigationId} · {inv.name}</option>)}
          </select>
          <input className="nasa-input" aria-label="Yakıt filtresi" placeholder="Yakıt adı (tam eşleşme)" value={fuelInput} onChange={(event) => setFuelInput(event.target.value)} />
          <button className="nasa-btn" type="submit">Filtrele</button>
          <button className="nasa-btn" type="button" onClick={() => { setFuelInput(""); changeFilters({ investigationId: "", fuel: "" }); }}>Temizle</button>
        </form>
      </div>
      {catalog.loading && <p role="status">Araştırmalar yükleniyor…</p>}
      {catalog.error && <ErrorMessage error={catalog.error} retry={reload} />}
      {catalog.data?.length === 0 && <p>Araştırma kataloğu boş.</p>}
      <div className="investigation-pills-grid">{(catalog.data || []).map((inv) => (
        <button type="button" key={inv.investigationId} className={`inv-pill-card ${filters.investigationId === inv.investigationId ? "active" : ""}`}
          onClick={() => changeFilters({ investigationId: inv.investigationId })}>
          <span className="inv-id-badge">{inv.investigationId}</span><div className="inv-pill-name">{inv.name}</div><p>{inv.description}</p>
        </button>
      ))}</div>
    </div>

    <div className="explorer-split-grid">
      <div className="panel-card">
        <div className="panel-card-header"><h4>Deney ve numune kayıtları{page && ` (${page.totalElements} kayıt)`}</h4><span>Karşılaştırma: {compareIds.length}/3</span></div>
        {list.loading && <p role="status">Deneyler yükleniyor…</p>}
        {list.error && <ErrorMessage error={list.error} retry={reload} />}
        {page?.items.length === 0 && <p role="status">Bu filtrelere uygun backend deney kaydı yok.</p>}
        {page?.items.length > 0 && <div className="nasa-table-wrapper"><table className="nasa-table">
          <thead><tr><th>Karşılaştır</th><th>Deney kimliği</th><th>Kaynak test #</th><th>Yakıt</th><th>Tarih</th><th>Raporlanan sonuç</th><th>İşlem</th></tr></thead>
          <tbody>{page.items.map((exp) => <tr key={exp.experimentId} className={detailId === exp.experimentId ? "row-selected" : ""}>
            <td><input type="checkbox" checked={compareIds.includes(exp.experimentId)} disabled={compareIds.length >= 3 && !compareIds.includes(exp.experimentId)}
              onChange={() => toggleComparison(exp.experimentId)} aria-label={`${exp.experimentId} karşılaştır`} /></td>
            <td className="mono-cell">{exp.experimentId}</td><td>{exp.sourceTestId}</td><td>{exp.fuel || "Belirtilmemiş"}</td>
            <td>{experimentDate(exp)}</td><td>{exp.reportedOutcome || "Belirtilmemiş"}</td>
            <td><button className="nasa-btn nasa-btn-xs" onClick={() => setDetailId(exp.experimentId)}>Detay</button></td>
          </tr>)}</tbody>
        </table></div>}
        {page && <div className="filter-controls-row">
          <button className="nasa-btn nasa-btn-xs" disabled={page.page === 0} onClick={() => { setFilters({ ...filters, page: page.page - 1 }); setDetailId(null); }}>Önceki</button>
          <span>Sayfa {page.totalPages ? page.page + 1 : 0} / {page.totalPages}</span>
          <button className="nasa-btn nasa-btn-xs" disabled={page.page + 1 >= page.totalPages} onClick={() => { setFilters({ ...filters, page: page.page + 1 }); setDetailId(null); }}>Sonraki</button>
        </div>}
      </div>

      <div className="panel-card detail-inspector-card">
        {!detailId && <p>Koşulları, ölçümleri ve kaynak hücrelerini görmek için deney detayı açın.</p>}
        {detail.loading && <p role="status">Deney detayı yükleniyor…</p>}
        {detail.error && <ErrorMessage error={detail.error} retry={reload} />}
        {experiment && <>
          <h4>{experiment.experimentId} · Test {experiment.sourceTestId}</h4>
          <p>{experiment.experimentIdentifier} · {experiment.fuel} · {experimentDate(experiment)}</p>
          <p>Raporlanan sonuç: {experiment.reportedOutcome || "Belirtilmemiş"}</p>
          <ExperimentSourceView key={experiment.experimentId} experiment={experiment} />
          <div className="subpanel-title">Koşullar ve ölçümler</div>
          {experiment.measurements.length === 0 && <p>Bu kaynakta sayısal sonuç ölçümü yok; gösterilenler numune/koşul bilgileri ve kaynakta verilen nitel alanlardır.</p>}
          {[...experiment.conditions, ...experiment.measurements].map((measurement, index) => <div key={`${measurement.name}:${index}`} className="measurement-item">
            <div className="measurement-top"><strong>{measurement.name}</strong><span className="qualifier-badge">{measurement.qualifier}</span><span className="quality-badge">{measurement.qualityStatus}</span></div>
            <div className="measurement-values"><span>{measurementText(measurement)}</span><span>Kaynak hücre: <code>{JSON.stringify(measurement.rawValue)}</code></span></div>
          </div>)}
          {experiment.reportedFindings.length > 0 && <div className="findings-box"><h4>Raporlanan bulgular</h4>{experiment.reportedFindings.map((finding, index) => <p key={index}>
            <strong>{finding.name}:</strong> {finding.value} <span> · Ham değer: <code>{JSON.stringify(finding.rawValue)}</code> · {finding.sourceId}</span>
          </p>)}</div>}
          <Warnings warnings={experiment.warnings} />
          {experiment.sources.map((source) => <SourceCard key={source.sourceId} source={source} />)}
        </>}
      </div>
    </div>

    <div className="panel-card">
      <h4>Deney karşılaştırması</h4>
      <div className="filter-controls-row">{compareIds.map((id) => <button className="nasa-btn nasa-btn-xs" key={id} onClick={() => toggleComparison(id)}>{id} ×</button>)}</div>
      {compareIds.length < 2 && <p>Karşılaştırma için 2 veya 3 deney seçin.</p>}
      {comparison.loading && <p role="status">Karşılaştırma yükleniyor…</p>}
      {comparison.error && <ErrorMessage error={comparison.error} retry={reload} />}
      {result && <>
        <p>Durum: <strong>{result.status}</strong></p>
        {result.status === "INSUFFICIENT_DATA" && <p>Sayısal karşılaştırma için yeterli doğrulanmış ölçüm yok.</p>}
        <div className="comparison-series-grid">{result.series.map((series) => {
          const max = Math.max(1, ...series.points.filter((point) => Number.isFinite(point.value)).map((point) => Math.abs(point.value)));
          return <div key={`${series.metric}:${series.unit}`} className="series-card">
            <h4>{series.metric} {series.unit && `(${series.unit})`}</h4>
            {comparisonRows(series, result.experimentIds).map(({ experimentId, point }) => <div className="series-bar-row" key={experimentId}>
              <div className="series-bar-meta"><span>{experimentId}</span><strong>{point ? `${point.value} ${series.unit || ""}` : "Doğrulanmış değer yok"}</strong></div>
              {point && <><div className="series-bar-track"><div className="series-bar-fill" style={{ width: `${Math.abs(point.value) / max * 100}%` }} /></div><small>{point.sourceId}</small></>}
            </div>)}
          </div>;
        })}</div>
        <div className="nasa-table-wrapper"><table className="nasa-table"><thead><tr><th>Alan</th>{result.experimentIds.map((id) => <th key={id}>{id}</th>)}<th>Not</th></tr></thead>
          <tbody>{result.differences.map((difference) => <tr key={difference.field}><td>{difference.field}</td>{result.experimentIds.map((id) => <td key={id}>{difference.values.find((value) => value.experimentId === id)?.value ?? "Eksik / hariç"}</td>)}<td>{difference.note}</td></tr>)}</tbody>
        </table></div>
        <Warnings warnings={result.warnings} />
        {result.sources.map((source) => <SourceCard key={source.sourceId} source={source} />)}
      </>}
    </div>
  </div>;
}
