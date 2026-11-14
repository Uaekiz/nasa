import { useEffect, useMemo, useState } from "react";
import {
  MISSION_PRESETS,
  MATERIALS_CATALOG,
} from "./data/nasaPsiData";
import {
  generateMitigationRecommendations,
  generateTelemetryTimeline,
} from "./services/fireRiskEngine";
import { checkBackendHealth } from "./services/apiClient";
import { PALETTE_LIST, NASA_PALETTE } from "./theme/nasaPalette";
import FlameSimulationCanvas from "./components/FlameSimulationCanvas";
import TelemetryCharts from "./components/TelemetryCharts";
import ExperimentExplorer from "./components/ExperimentExplorer";
import AiAssistantPanel from "./components/AiAssistantPanel";
import "./App.css";

export default function App() {
  const [activeTab, setActiveTab] = useState("dashboard");
  const [activePresetId, setActivePresetId] = useState("lunar-artemis");
  const [params, setParams] = useState(MISSION_PRESETS[1].params);
  const [previousParamsSnapshot, setPreviousParamsSnapshot] = useState(null);
  const [appliedBanner, setAppliedBanner] = useState(null);
  const [backendStatus, setBackendStatus] = useState({
    status: "CHECKING",
    mode: "LOCAL_PSI_TELEMETRY",
  });

  useEffect(() => {
    checkBackendHealth().then(setBackendStatus);
  }, []);

  const mitigationPlan = useMemo(
    () => generateMitigationRecommendations(params),
    [params]
  );

  const timelineData = useMemo(
    () => generateTelemetryTimeline(params),
    [params]
  );

  const {
    baseline,
    recommendations,
    combinedPatch,
    optimizedProbability,
    totalReductionDelta,
  } = mitigationPlan;

  const handleSelectPreset = (preset) => {
    setActivePresetId(preset.id);
    setPreviousParamsSnapshot(null);
    setAppliedBanner(null);
    setParams({ ...preset.params });
  };

  const handleUpdateParams = (patch) => {
    setActivePresetId("custom");
    setAppliedBanner(null);
    setParams((prev) => ({ ...prev, ...patch }));
  };

  const handleApplySingleRecommendation = (rec) => {
    setPreviousParamsSnapshot({ ...params });
    setParams((prev) => ({ ...prev, ...rec.patch }));
    setActivePresetId("ai-optimized");
    setAppliedBanner(
      `Öneri Uygulandı: ${rec.title} (Risk: %${baseline.probability} → %${rec.postActionProbability})`
    );
  };

  const handleApplyAllRecommendations = () => {
    if (!recommendations.length) return;
    setPreviousParamsSnapshot({ ...params });
    setParams((prev) => ({ ...prev, ...combinedPatch }));
    setActivePresetId("ai-optimized");
    setAppliedBanner(
      `Tüm AI Önlemleri Uygulandı — Yangın İhtimali %${baseline.probability} → %${optimizedProbability} (-%${totalReductionDelta}) seviyesine düşürüldü.`
    );
  };

  const handleUndoOptimization = () => {
    if (!previousParamsSnapshot) return;
    setParams(previousParamsSnapshot);
    setPreviousParamsSnapshot(null);
    setAppliedBanner(null);
  };

  const handleLoadExperimentIntoSim = (exp) => {
    if (!exp?.simulationParams) return;
    setPreviousParamsSnapshot({ ...params });
    setParams({ ...exp.simulationParams });
    setActivePresetId(exp.experimentId);
    setAppliedBanner(
      `NASA PSI Deneyi Yüklendi: ${exp.experimentId} (Test ${exp.sourceTestId} — ${exp.materialRaw})`
    );
    setActiveTab("dashboard");
  };

  return (
    <div className="nasa-app-shell">
      {/* 1. CLEAN PROFESSIONAL HEADER */}
      <header className="mission-header">
        <div className="brand-cluster">
          <div className="nasa-insignia-box">
            <span className="insignia-dot" />
            <span>NASA // PSI</span>
          </div>
          <div>
            <div className="brand-title-row">
              <h1>FLAMESCOPE</h1>
              <span className="version-tag">AI FIRE SAFETY</span>
            </div>
            <p className="brand-subtitle">
              Açık Telemetri Tabanlı Yangın Olasılığı Hesaplama ve Önleyici Karar Destek Sistemi
            </p>
          </div>
        </div>

        <nav className="main-nav-tabs" aria-label="Ana Modüller">
          <button
            type="button"
            className={`nav-tab-btn ${
              activeTab === "dashboard" ? "active" : ""
            }`}
            onClick={() => setActiveTab("dashboard")}
          >
            Simülasyon & Analiz
          </button>
          <button
            type="button"
            className={`nav-tab-btn ${
              activeTab === "explorer" ? "active" : ""
            }`}
            onClick={() => setActiveTab("explorer")}
          >
            NASA PSI Veri Tabanı
          </button>
          <button
            type="button"
            className={`nav-tab-btn ${
              activeTab === "assistant" ? "active" : ""
            }`}
            onClick={() => setActiveTab("assistant")}
          >
            AI Bilimsel Asistan
          </button>
        </nav>
      </header>

      {/* 2. SCENARIO PRESET BAR */}
      <section className="preset-ribbon" aria-label="Ortam Senaryoları">
        <span className="preset-ribbon-label">ORTAM PROFİLİ:</span>
        <div className="preset-buttons-scroll">
          {MISSION_PRESETS.map((preset) => (
            <button
              type="button"
              key={preset.id}
              className={`preset-chip-btn ${
                activePresetId === preset.id ? "active" : ""
              }`}
              onClick={() => handleSelectPreset(preset)}
            >
              <span className="preset-chip-name">{preset.name}</span>
              <span className="preset-chip-badge">{preset.badge}</span>
            </button>
          ))}
        </div>
      </section>

      {/* FEEDBACK BANNER */}
      {appliedBanner && (
        <div className="ai-action-banner" role="status">
          <div className="ai-banner-text">
            <span className="ai-banner-icon">●</span>
            <strong>{appliedBanner}</strong>
          </div>
          <div className="ai-banner-actions">
            {previousParamsSnapshot && (
              <button
                type="button"
                className="nasa-btn nasa-btn-xs"
                onClick={handleUndoOptimization}
              >
                ↺ Geri Al
              </button>
            )}
            <button
              type="button"
              className="nasa-btn nasa-btn-xs"
              onClick={() => setAppliedBanner(null)}
            >
              ✕
            </button>
          </div>
        </div>
      )}

      {/* 3. MAIN WORKSPACE */}
      <main className="mission-main">
        {activeTab === "dashboard" && (
          <>
            {/* CLEAN 4-CARD KPI STRIP */}
            <section className="kpi-telemetry-grid">
              <div
                className="kpi-card kpi-card-primary"
                style={{ borderTopColor: baseline.riskColor }}
              >
                <div className="kpi-top-row">
                  <span className="kpi-label">AI YANGIN ÇIKMA İHTİMALİ</span>
                  <span
                    className="kpi-status-badge"
                    style={{
                      background:
                        baseline.probability >= 75
                          ? NASA_PALETTE.rocketRed.hex
                          : baseline.probability >= 50
                          ? NASA_PALETTE.neonYellow.hex
                          : NASA_PALETTE.blueYonder.hex,
                      color:
                        baseline.probability >= 50 && baseline.probability < 75
                          ? NASA_PALETTE.deepBlue.hex
                          : NASA_PALETTE.white.hex,
                    }}
                  >
                    {baseline.riskLabelTr}
                  </span>
                </div>
                <div className="kpi-main-value-row">
                  <span
                    className="kpi-big-number"
                    style={{
                      color:
                        baseline.probability >= 60
                          ? NASA_PALETTE.rocketRed.hex
                          : NASA_PALETTE.deepBlue.hex,
                    }}
                  >
                    %{baseline.probability.toFixed(1)}
                  </span>
                  {totalReductionDelta > 0.5 && (
                    <span className="kpi-delta-tag">
                      Hedef: <strong>%{optimizedProbability}</strong> (-%
                      {totalReductionDelta})
                    </span>
                  )}
                </div>
                <div className="kpi-progress-bar">
                  <div
                    className="kpi-progress-fill"
                    style={{
                      width: `${baseline.probability}%`,
                      background: baseline.riskColor,
                    }}
                  />
                </div>
              </div>

              <div className="kpi-card">
                <div className="kpi-top-row">
                  <span className="kpi-label">OKSİJEN & BASINÇ</span>
                  <span className="kpi-unit-tag">LOI: %{baseline.metrics.effectiveLoi}</span>
                </div>
                <div className="kpi-main-value-row">
                  <span className="kpi-big-number">
                    %{params.oxygenPercent.toFixed(1)}
                  </span>
                  <span className="kpi-secondary-readout">
                    {params.pressureKpa.toFixed(1)} kPa
                  </span>
                </div>
                <div className="kpi-subtext">
                  O₂ Kısmi Basıncı: <strong>{baseline.metrics.partialPressureO2Kpa} kPa</strong>
                </div>
              </div>

              <div className="kpi-card">
                <div className="kpi-top-row">
                  <span className="kpi-label">HAVA AKIŞI & ÇEKİM</span>
                  <span className="kpi-unit-tag">{params.flowDirection}</span>
                </div>
                <div className="kpi-main-value-row">
                  <span className="kpi-big-number">
                    {params.airflowCmS.toFixed(1)}{" "}
                    <small className="unit-inline">cm/s</small>
                  </span>
                  <span className="kpi-secondary-readout">
                    {params.gravityG.toFixed(2)}g
                  </span>
                </div>
                <div className="kpi-subtext">
                  Etkin Konveksiyon: <strong>{baseline.metrics.effectiveVelocityCmS} cm/s</strong>
                </div>
              </div>

              <div className="kpi-card">
                <div className="kpi-top-row">
                  <span className="kpi-label">YAYILIM HIZI & CO</span>
                  <span className="kpi-unit-tag">{params.material}</span>
                </div>
                <div className="kpi-main-value-row">
                  <span className="kpi-big-number">
                    {baseline.metrics.predictedSpreadRateMmS}{" "}
                    <small className="unit-inline">mm/s</small>
                  </span>
                  <span
                    className="kpi-secondary-readout"
                    style={{
                      color:
                        params.coPpm > 40
                          ? NASA_PALETTE.rocketRed.hex
                          : NASA_PALETTE.neonBlue.hex,
                    }}
                  >
                    {params.coPpm} ppm CO
                  </span>
                </div>
                <div className="kpi-subtext">
                  Termal Güç: <strong>{params.ignitionPowerW} W</strong> | Kabin:{" "}
                  <strong>{params.temperatureC.toFixed(0)}°C</strong>
                </div>
              </div>
            </section>

            {/* MAIN GRID: LEFT = 3D THREE.JS SIMULATION + COMPACT CONTROLS, RIGHT = AI RECOMMENDATIONS */}
            <section className="workspace-split-grid">
              <div className="sim-and-controls-col">
                <FlameSimulationCanvas
                  params={params}
                  riskEvaluation={baseline}
                  onApplyAllRecommendations={handleApplyAllRecommendations}
                  hasRecommendations={recommendations.length > 0}
                />

                {/* STREAMLINED ENVIRONMENTAL TELEMETRY CONTROLS */}
                <div className="panel-card">
                  <div className="panel-card-header">
                    <div>
                      <span className="section-eyebrow">
                        ÇEVRE KOŞULLARI PARAMETRELERİ
                      </span>
                      <h3>Canlı Telemetri Kontrolleri</h3>
                    </div>
                    {previousParamsSnapshot && (
                      <button
                        type="button"
                        className="nasa-btn nasa-btn-xs"
                        onClick={handleUndoOptimization}
                      >
                        ↺ Varsayılana Dön
                      </button>
                    )}
                  </div>

                  <div className="sliders-grid">
                    <div className="slider-control-box">
                      <div className="slider-header">
                        <label htmlFor="slider-o2">Oksijen Oranı (O₂)</label>
                        <span className="slider-readout">
                          %{params.oxygenPercent.toFixed(1)}
                        </span>
                      </div>
                      <input
                        id="slider-o2"
                        type="range"
                        min="12"
                        max="38"
                        step="0.2"
                        value={params.oxygenPercent}
                        onChange={(e) =>
                          handleUpdateParams({
                            oxygenPercent: parseFloat(e.target.value),
                          })
                        }
                        className="nasa-range"
                      />
                    </div>

                    <div className="slider-control-box">
                      <div className="slider-header">
                        <label htmlFor="slider-flow">Hava Akış Hızı</label>
                        <span className="slider-readout">
                          {params.airflowCmS.toFixed(1)} cm/s
                        </span>
                      </div>
                      <input
                        id="slider-flow"
                        type="range"
                        min="0"
                        max="40"
                        step="0.5"
                        value={params.airflowCmS}
                        onChange={(e) =>
                          handleUpdateParams({
                            airflowCmS: parseFloat(e.target.value),
                          })
                        }
                        className="nasa-range"
                      />
                    </div>

                    <div className="slider-control-box">
                      <div className="slider-header">
                        <label htmlFor="slider-pressure">Kabin Basıncı</label>
                        <span className="slider-readout">
                          {params.pressureKpa.toFixed(1)} kPa
                        </span>
                      </div>
                      <input
                        id="slider-pressure"
                        type="range"
                        min="35"
                        max="140"
                        step="1"
                        value={params.pressureKpa}
                        onChange={(e) =>
                          handleUpdateParams({
                            pressureKpa: parseFloat(e.target.value),
                          })
                        }
                        className="nasa-range"
                      />
                    </div>

                    <div className="slider-control-box">
                      <div className="slider-header">
                        <label htmlFor="slider-gravity">Yerçekimi İvmesi</label>
                        <span className="slider-readout">
                          {params.gravityG.toFixed(2)} g
                        </span>
                      </div>
                      <input
                        id="slider-gravity"
                        type="range"
                        min="0"
                        max="1"
                        step="0.02"
                        value={params.gravityG}
                        onChange={(e) =>
                          handleUpdateParams({
                            gravityG: parseFloat(e.target.value),
                          })
                        }
                        className="nasa-range"
                      />
                    </div>

                    <div className="slider-control-box">
                      <div className="slider-header">
                        <label htmlFor="select-material">Numune Materyali</label>
                        <span className="slider-readout">
                          LOI %{MATERIALS_CATALOG[params.material]?.loi}
                        </span>
                      </div>
                      <select
                        id="select-material"
                        className="nasa-select nasa-select-full"
                        value={params.material}
                        onChange={(e) =>
                          handleUpdateParams({ material: e.target.value })
                        }
                      >
                        {Object.values(MATERIALS_CATALOG).map((m) => (
                          <option key={m.id} value={m.id}>
                            {m.label}
                          </option>
                        ))}
                      </select>
                    </div>

                    <div className="slider-control-box">
                      <div className="slider-header">
                        <label>Havalandırma Akış Yönü</label>
                      </div>
                      <div className="direction-toggle-group">
                        <button
                          type="button"
                          className={`nasa-btn nasa-btn-sm ${
                            params.flowDirection === "CONCURRENT" ? "active" : ""
                          }`}
                          onClick={() =>
                            handleUpdateParams({ flowDirection: "CONCURRENT" })
                          }
                        >
                          ⇉ Aynı Yönlü
                        </button>
                        <button
                          type="button"
                          className={`nasa-btn nasa-btn-sm ${
                            params.flowDirection === "OPPOSED" ? "active" : ""
                          }`}
                          onClick={() =>
                            handleUpdateParams({ flowDirection: "OPPOSED" })
                          }
                        >
                          ⇇ Ters Yönlü
                        </button>
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              {/* RIGHT COLUMN: AI RECOMMENDATIONS TO REDUCE FIRE PROBABILITY */}
              <aside className="ai-recommendations-col">
                <div className="panel-card ai-panel-card">
                  <div className="panel-card-header">
                    <div>
                      <span className="section-eyebrow">
                        YAPAY ZEKA KARAR DESTEK ÖNERİLERİ
                      </span>
                      <h3>Yangın İhtimalini Düşürme Protokolleri</h3>
                    </div>
                  </div>

                  <div className="ai-optimization-summary">
                    <div className="opt-col">
                      <span className="opt-label">MEVCUT RİSK</span>
                      <strong
                        className="opt-value"
                        style={{
                          color:
                            baseline.probability >= 60
                              ? NASA_PALETTE.rocketRed.hex
                              : NASA_PALETTE.deepBlue.hex,
                        }}
                      >
                        %{baseline.probability}
                      </strong>
                    </div>
                    <div className="opt-arrow">→</div>
                    <div className="opt-col">
                      <span className="opt-label">AI HEDEF</span>
                      <strong
                        className="opt-value"
                        style={{ color: NASA_PALETTE.neonBlue.hex }}
                      >
                        %{optimizedProbability}
                      </strong>
                    </div>
                    <div className="opt-col opt-col-delta">
                      <span className="opt-label">NET KAZANÇ</span>
                      <strong className="opt-value opt-delta-pill">
                        -%{totalReductionDelta}
                      </strong>
                    </div>
                  </div>

                  {recommendations.length > 0 && (
                    <button
                      type="button"
                      className="nasa-btn nasa-btn-primary nasa-btn-block"
                      onClick={handleApplyAllRecommendations}
                    >
                      Tüm AI Önerilerini Uygula (Risk: %{baseline.probability} → %
                      {optimizedProbability})
                    </button>
                  )}

                  <div className="recommendations-list">
                    {recommendations.length === 0 ? (
                      <div className="safe-state-box">
                        <div className="safe-state-title">
                          ✓ GÜVENLİ SÖNME ZARFINDA (SAFE ZONE)
                        </div>
                        <p>
                          Mevcut çevre koşulları mikroçekim tutuşma sınırının altındadır.
                        </p>
                      </div>
                    ) : (
                      recommendations.slice(0, 4).map((rec, index) => (
                        <div key={rec.id} className="rec-card">
                          <div className="rec-card-top">
                            <span
                              className={`rec-priority-badge ${
                                rec.priority.includes("KRİTİK")
                                  ? "priority-critical"
                                  : "priority-high"
                              }`}
                            >
                              0{index + 1} // {rec.priority}
                            </span>
                            <span className="rec-delta-badge">
                              -%{rec.riskReductionDelta} Risk
                            </span>
                          </div>

                          <h4 className="rec-title">{rec.title}</h4>
                          <p className="rec-rationale">{rec.rationale}</p>

                          <div className="rec-card-footer">
                            <span className="rec-psi-ref">
                              Referans: <strong>{rec.psiReference}</strong>
                            </span>
                            <button
                              type="button"
                              className="nasa-btn nasa-btn-xs"
                              onClick={() => handleApplySingleRecommendation(rec)}
                            >
                              Uygula (→ %{rec.postActionProbability})
                            </button>
                          </div>
                        </div>
                      ))
                    )}
                  </div>
                </div>
              </aside>
            </section>

            {/* ECHARTS ANALYTICS SECTION */}
            <section className="charts-section">
              <TelemetryCharts
                params={params}
                mitigationPlan={mitigationPlan}
                timelineData={timelineData}
                onSelectPsiPoint={handleLoadExperimentIntoSim}
              />
            </section>
          </>
        )}

        {activeTab === "explorer" && (
          <ExperimentExplorer
            onLoadExperimentIntoSim={handleLoadExperimentIntoSim}
          />
        )}

        {activeTab === "assistant" && (
          <AiAssistantPanel
            params={params}
            mitigationPlan={mitigationPlan}
          />
        )}
      </main>

      {/* 4. CLEAN FOOTER WITH NASA PALETTE ACCENT BAR */}
      <footer className="mission-footer">
        <div className="palette-spec-strip">
          <span className="palette-strip-title">
            NASA RENK PALETİ & SİSTEM DURUMU (
            {backendStatus.status === "UP" ? "API BAĞLI" : "PSI YEREL VERİ"}):
          </span>
          <div className="palette-swatches-row">
            {PALETTE_LIST.map((c) => (
              <div key={c.hex} className="palette-chip" title={c.role}>
                <span
                  className="palette-color-dot"
                  style={{ background: c.hex }}
                />
                <span className="palette-chip-name">{c.name}</span>
                <code className="palette-chip-hex">{c.hex}</code>
              </div>
            ))}
          </div>
        </div>
      </footer>
    </div>
  );
}
