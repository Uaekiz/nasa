import { useEffect, useState } from "react";
import {
  fetchInvestigations,
  fetchExperiments,
  compareExperiments,
} from "../services/apiClient";
import { evaluateFireRisk } from "../services/fireRiskEngine";
import { NASA_PALETTE } from "../theme/nasaPalette";

export default function ExperimentExplorer({ onLoadExperimentIntoSim }) {
  const [investigations, setInvestigations] = useState([]);
  const [selectedInv, setSelectedInv] = useState("");
  const [selectedFuel, setSelectedFuel] = useState("");
  const [experimentsPage, setExperimentsPage] = useState({
    items: [],
    totalElements: 0,
  });
  const [compareIds, setCompareIds] = useState([
    "PSI-25:run-0008",
    "PSI-25:run-0014",
    "PSI-98:run-0001",
  ]);
  const [comparisonResult, setComparisonResult] = useState(null);
  const [activeDetailExp, setActiveDetailExp] = useState(null);

  useEffect(() => {
    fetchInvestigations().then(setInvestigations);
  }, []);

  useEffect(() => {
    fetchExperiments({
      investigationId: selectedInv,
      fuel: selectedFuel,
      page: 0,
      size: 50,
    }).then((res) => {
      setExperimentsPage(res);
      setActiveDetailExp((prev) => prev || res.items[0] || null);
    });
  }, [selectedInv, selectedFuel]);

  useEffect(() => {
    let cancelled = false;
    compareExperiments(compareIds).then((res) => {
      if (!cancelled) {
        setComparisonResult(compareIds.length >= 2 ? res : null);
      }
    });
    return () => {
      cancelled = true;
    };
  }, [compareIds]);

  const toggleCompareId = (id) => {
    setCompareIds((prev) => {
      if (prev.includes(id)) {
        return prev.filter((item) => item !== id);
      }
      if (prev.length >= 3) {
        return [...prev.slice(1), id];
      }
      return [...prev, id];
    });
  };

  const uniqueFuels = [
    "PMMA Film",
    "SIBAL Fabric",
    "Silicone",
    "Nomex III",
    "Methanol",
    "Kapton",
  ];

  return (
    <div className="explorer-container">
      {/* 1. Investigation Catalog Strip */}
      <div className="panel-card">
        <div className="panel-card-header">
          <div>
            <span className="section-eyebrow">
              NASA PHYSICAL SCIENCES INFORMATICS (PSI) KATALOĞU
            </span>
            <h3>Açık Telemetri Araştırma Paketleri (9 Araştırma / 671 Deney Kaydı)</h3>
          </div>
          <div className="filter-controls-row">
            <select
              className="nasa-select"
              value={selectedInv}
              onChange={(e) => setSelectedInv(e.target.value)}
            >
              <option value="">Tüm Araştırmalar (PSI-25 .. PSI-102)</option>
              {investigations.map((inv) => (
                <option key={inv.investigationId} value={inv.investigationId}>
                  {inv.investigationId} — {inv.shortName || inv.name}
                </option>
              ))}
            </select>

            <select
              className="nasa-select"
              value={selectedFuel}
              onChange={(e) => setSelectedFuel(e.target.value)}
            >
              <option value="">Tüm Materyal / Yakıt Türleri</option>
              {uniqueFuels.map((f) => (
                <option key={f} value={f}>
                  {f}
                </option>
              ))}
            </select>

            {(selectedInv || selectedFuel) && (
              <button
                type="button"
                className="nasa-btn nasa-btn-xs"
                onClick={() => {
                  setSelectedInv("");
                  setSelectedFuel("");
                }}
              >
                Filtreleri Temizle
              </button>
            )}
          </div>
        </div>

        <div className="investigation-pills-grid">
          {investigations.map((inv) => {
            const isActive = selectedInv === inv.investigationId;
            return (
              <button
                type="button"
                key={inv.investigationId}
                className={`inv-pill-card ${isActive ? "active" : ""}`}
                onClick={() =>
                  setSelectedInv(isActive ? "" : inv.investigationId)
                }
              >
                <div className="inv-pill-top">
                  <span className="inv-id-badge">{inv.investigationId}</span>
                  <span className="inv-run-count">{inv.totalRunsInCsv} kayıt</span>
                </div>
                <div className="inv-pill-name">{inv.shortName || inv.name}</div>
                <div className="inv-pill-facility">{inv.facility}</div>
              </button>
            );
          })}
        </div>
      </div>

      {/* 2. Experiments Table + Measurement Qualifier Inspector */}
      <div className="explorer-split-grid">
        <div className="panel-card">
          <div className="panel-card-header">
            <div>
              <span className="section-eyebrow">
                DENEY TELEMETRİ MATRİSİ (GET /api/v1/experiments)
              </span>
              <h4>
                Doğrulanmış NASA PSI Deneyleri ({experimentsPage.totalElements} Gösteriliyor)
              </h4>
            </div>
            <span className="compare-counter-badge">
              Karşılaştırma Seçimi: {compareIds.length}/3
            </span>
          </div>

          <div className="nasa-table-wrapper">
            <table className="nasa-table">
              <thead>
                <tr>
                  <th>Karşılaştır</th>
                  <th>Deney Kimliği</th>
                  <th>Test #</th>
                  <th>Yakıt / Materyal</th>
                  <th>O₂ (% vol)</th>
                  <th>Akış (cm/s)</th>
                  <th>AI Risk</th>
                  <th>Raporlanan Sonuç</th>
                  <th>İşlem</th>
                </tr>
              </thead>
              <tbody>
                {experimentsPage.items.map((exp) => {
                  const risk = evaluateFireRisk(exp.simulationParams);
                  const isCompared = compareIds.includes(exp.experimentId);
                  const isInspected =
                    activeDetailExp?.experimentId === exp.experimentId;

                  const o2Cond = exp.conditions?.find(
                    (c) => c.name === "oxygenInitial"
                  );
                  const flowCond = exp.conditions?.find(
                    (c) => c.name === "airflow"
                  );

                  return (
                    <tr
                      key={exp.experimentId}
                      className={isInspected ? "row-selected" : ""}
                      onClick={() => setActiveDetailExp(exp)}
                    >
                      <td onClick={(e) => e.stopPropagation()}>
                        <input
                          type="checkbox"
                          checked={isCompared}
                          onChange={() => toggleCompareId(exp.experimentId)}
                          aria-label={`${exp.experimentId} karşılaştırmaya ekle`}
                        />
                      </td>
                      <td className="mono-cell">{exp.experimentId}</td>
                      <td className="mono-cell">
                        <strong>{exp.sourceTestId}</strong>
                      </td>
                      <td>
                        <div>{exp.fuel}</div>
                        <small className="cell-subtext">{exp.materialRaw}</small>
                      </td>
                      <td className="mono-cell">
                        {o2Cond ? o2Cond.rawValue : exp.simulationParams.oxygenPercent}%
                        {o2Cond && o2Cond.qualifier !== "EXACT" && (
                          <span className="qualifier-tag">{o2Cond.qualifier}</span>
                        )}
                      </td>
                      <td className="mono-cell">
                        {flowCond ? flowCond.rawValue : exp.simulationParams.airflowCmS}
                        {flowCond && flowCond.qualifier !== "EXACT" && (
                          <span className="qualifier-tag">{flowCond.qualifier}</span>
                        )}
                      </td>
                      <td className="mono-cell">
                        <span
                          className="risk-pill-mini"
                          style={{
                            borderColor: risk.riskColor,
                            color:
                              risk.probability >= 75
                                ? NASA_PALETTE.white.hex
                                : NASA_PALETTE.deepBlue.hex,
                            background:
                              risk.probability >= 75
                                ? NASA_PALETTE.rocketRed.hex
                                : risk.probability >= 50
                                ? NASA_PALETTE.neonYellow.hex
                                : "#EEF4FF",
                          }}
                        >
                          %{risk.probability}
                        </span>
                      </td>
                      <td>
                        <span className="outcome-tag">{exp.reportedOutcome}</span>
                      </td>
                      <td onClick={(e) => e.stopPropagation()}>
                        <button
                          type="button"
                          className="nasa-btn nasa-btn-primary nasa-btn-xs"
                          onClick={() => onLoadExperimentIntoSim(exp)}
                        >
                          Simülasyona Yükle →
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>

        {/* Right: Single Experiment Normalized Measurement & RawValue Inspector */}
        {activeDetailExp && (
          <div className="panel-card detail-inspector-card">
            <div className="panel-card-header">
              <div>
                <span className="section-eyebrow">
                  DENEY DETAYI & ÖLÇÜM DOĞRULAMA (BÖLÜM 4 SÖZLEŞME ŞEMASI)
                </span>
                <h4>
                  {activeDetailExp.experimentId} (Test {activeDetailExp.sourceTestId})
                </h4>
              </div>
              <button
                type="button"
                className="nasa-btn nasa-btn-yellow nasa-btn-sm"
                onClick={() => onLoadExperimentIntoSim(activeDetailExp)}
              >
                ★ Bu Deneyi Simülatörde Çalıştır
              </button>
            </div>

            <div className="detail-meta-grid">
              <div>
                <span className="meta-label">Araştırma:</span>
                <strong>{activeDetailExp.investigationId}</strong>
              </div>
              <div>
                <span className="meta-label">Baş Araştırmacı (PI):</span>
                <strong>{activeDetailExp.pi}</strong>
              </div>
              <div>
                <span className="meta-label">Tarih:</span>
                <strong>
                  {activeDetailExp.date || `${activeDetailExp.dateRaw} (Yıl Yok)`}
                </strong>
              </div>
              <div>
                <span className="meta-label">Numune:</span>
                <strong>{activeDetailExp.materialRaw}</strong>
              </div>
            </div>

            <div className="subpanel-title">
              Normalize Koşullar & Ölçümler (rawValue & qualifier Korunumu)
            </div>
            <div className="measurements-list">
              {[
                ...(activeDetailExp.conditions || []),
                ...(activeDetailExp.measurements || []),
              ].map((m, idx) => (
                <div key={`${m.name}-${idx}`} className="measurement-item">
                  <div className="measurement-top">
                    <span className="measurement-name">{m.name}</span>
                    <span className="qualifier-badge">{m.qualifier}</span>
                    <span className="quality-badge">{m.qualityStatus}</span>
                  </div>
                  <div className="measurement-values">
                    <span>
                      Normalize:{" "}
                      <strong>
                        {m.value !== null && m.value !== undefined
                          ? `${m.value} ${m.unit || ""}`
                          : m.startValue !== undefined
                          ? `${m.startValue} → ${m.endValue} ${m.unit || ""}`
                          : `null (${m.missingReason || "CHANGING"})`}
                      </strong>
                    </span>
                    <span>
                      Kaynak (rawValue): <code>&quot;{m.rawValue}&quot;</code>
                    </span>
                  </div>
                </div>
              ))}
            </div>

            {activeDetailExp.reportedFindings?.length > 0 && (
              <div className="findings-box">
                <div className="subpanel-title">Bilimsel Bulgular</div>
                {activeDetailExp.reportedFindings.map((f, i) => (
                  <p key={i}>{f}</p>
                ))}
              </div>
            )}

            {activeDetailExp.warnings?.length > 0 && (
              <div className="warnings-box">
                {activeDetailExp.warnings.map((w, i) => (
                  <div key={i} className="warning-line">
                    <strong>[{w.code}]</strong> {w.message}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* 3. Side-by-Side Comparison Module (POST /api/v1/comparisons) */}
      {comparisonResult && comparisonResult.status !== "INSUFFICIENT_DATA" && (
        <div className="panel-card">
          <div className="panel-card-header">
            <div>
              <span className="section-eyebrow">
                YAN YANA DENEY KARŞILAŞTIRMA MATRİSİ (POST /api/v1/comparisons)
              </span>
              <h4>
                Seçilen Deneyler: {comparisonResult.experimentIds.join(" vs. ")}
              </h4>
            </div>
            <span
              className={`status-tag ${
                comparisonResult.status === "COMPARABLE"
                  ? "status-comparable"
                  : "status-limited"
              }`}
            >
              KARŞILAŞTIRMA DURUMU: {comparisonResult.status}
            </span>
          </div>

          <div className="comparison-series-grid">
            {comparisonResult.series.map((s) => {
              const maxVal = Math.max(
                1,
                ...s.points.map((p) => Number(p.value) || 0)
              );
              return (
                <div key={s.metric} className="series-card">
                  <div className="series-card-title">{s.label}</div>
                  {s.points.map((pt) => {
                    const pct = Math.min(100, ((pt.value || 0) / maxVal) * 100);
                    return (
                      <div key={pt.experimentId} className="series-bar-row">
                        <div className="series-bar-meta">
                          <span>
                            {pt.experimentId} ({pt.sourceTestId})
                          </span>
                          <strong>
                            {pt.value} {s.unit}
                          </strong>
                        </div>
                        <div className="series-bar-track">
                          <div
                            className="series-bar-fill"
                            style={{
                              width: `${pct}%`,
                              background:
                                s.metric === "aiFireRisk"
                                  ? NASA_PALETTE.rocketRed.hex
                                  : NASA_PALETTE.blueYonder.hex,
                            }}
                          />
                        </div>
                      </div>
                    );
                  })}
                </div>
              );
            })}
          </div>

          <div className="nasa-table-wrapper" style={{ marginTop: "14px" }}>
            <table className="nasa-table">
              <thead>
                <tr>
                  <th>Karşılaştırılan Alan</th>
                  {comparisonResult.experimentIds.map((id) => (
                    <th key={id} className="mono-cell">
                      {id}
                    </th>
                  ))}
                  <th>Mühendislik Notu</th>
                </tr>
              </thead>
              <tbody>
                {comparisonResult.differences.map((diff) => (
                  <tr key={diff.field}>
                    <td>
                      <strong>{diff.field}</strong>
                    </td>
                    {diff.values.map((v) => (
                      <td key={v.experimentId} className="mono-cell">
                        {v.value}
                      </td>
                    ))}
                    <td className="cell-subtext">{diff.note}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
