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

  // Compute AI Fire Risk, Factor Contributions, and Ranked Risk-Reduction Recommendations
  const mitigationPlan = useMemo(
    () => generateMitigationRecommendations(params),
    [params]
  );

  // Compute Time-Series Telemetry & Forecast Trajectory
  const timelineData = useMemo(
    () => generateTelemetryTimeline(params),
    [params]
  );

  const { baseline, recommendations, combinedPatch, optimizedProbability, totalReductionDelta } =
    mitigationPlan;

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
      `AI Önerisi Uygulandı: "${rec.title}" — Yangın İhtimali %${baseline.probability} → %${rec.postActionProbability} (-%${rec.riskReductionDelta}) seviyesine düşürüldü.`
    );
  };

  const handleApplyAllRecommendations = () => {
    if (!recommendations.length) return;
    setPreviousParamsSnapshot({ ...params });
    setParams((prev) => ({ ...prev, ...combinedPatch }));
    setActivePresetId("ai-optimized");
    setAppliedBanner(
      `Tüm AI Önlemleri Devreye Alındı — Yangın Çıkma İhtimali %${baseline.probability} → %${optimizedProbability} (-%${totalReductionDelta}) güvenli zarfına çekildi.`
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
      {/* 1. TOP MISSION TELEMETRY HEADER BAR */}
      <header className="mission-header">
        <div className="brand-cluster">
          <div className="nasa-insignia-box">
            <span className="insignia-dot" />
            <span className="insignia-code">NASA // PSI</span>
          </div>
          <div>
            <div className="brand-title-row">
              <h1>FLAMESCOPE</h1>
              <span className="version-tag">TELEMETRY & AI FIRE SAFETY v1.0</span>
            </div>
            <p className="brand-subtitle">
              Açık Telemetri Verileriyle Yapay Zeka Destekli Yangın Olasılığı Hesaplama, Simülasyon ve Önleyici Karar Destek Sistemi
            </p>
          </div>
        </div>

        <div className="header-right-cluster">
          <div className="status-indicators">
            <span className="status-chip">
              <i className="pulse-dot" />
              AI RİSK MOTORU: AKTİF
            </span>
            <span className="status-chip">
              PSI VERİ TABANI: 9 ARAŞTIRMA / 671 TEST
            </span>
            <span className="status-chip">
              API:{" "}
              {backendStatus.status === "UP"
                ? "SPRING BOOT BAĞLI"
                : "YEREL TELEMETRİ MODU"}
            </span>
          </div>

          <nav className="main-nav-tabs" aria-label="Ana Modüller">
            <button
              type="button"
              className={`nav-tab-btn ${
                activeTab === "dashboard" ? "active" : ""
              }`}
              onClick={() => setActiveTab("dashboard")}
            >
              01 // Komuta, Grafik & Simülasyon
            </button>
            <button
              type="button"
              className={`nav-tab-btn ${
                activeTab === "explorer" ? "active" : ""
              }`}
              onClick={() => setActiveTab("explorer")}
            >
              02 // NASA PSI Telemetri & Karşılaştırma
            </button>
            <button
              type="button"
              className={`nav-tab-btn ${
                activeTab === "assistant" ? "active" : ""
              }`}
              onClick={() => setActiveTab("assistant")}
            >
              03 // AI Bilimsel Asistan (RAG)
            </button>
          </nav>
        </div>
      </header>

      {/* 2. MISSION SCENARIO PRESET SELECTOR BAR */}
      <section className="preset-ribbon" aria-label="Görev ve Ortam Senaryoları">
        <div className="preset-ribbon-label">
          <span>GÖREV / ORTAM TELEMETRİ PROFİLİ:</span>
        </div>
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

      {/* NOTIFICATION BANNER WHEN AI COUNTERMEASURES OR PSI EXPERIMENTS ARE LOADED */}
      {appliedBanner && (
        <div className="ai-action-banner" role="status">
          <div className="ai-banner-text">
            <span className="ai-banner-icon">★</span>
            <strong>{appliedBanner}</strong>
          </div>
          <div className="ai-banner-actions">
            {previousParamsSnapshot && (
              <button
                type="button"
                className="nasa-btn nasa-btn-xs"
                onClick={handleUndoOptimization}
              >
                ↺ Önceki Telemetriye Dön
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

      {/* 3. MAIN WORKSPACE CONTENT */}
      <main className="mission-main">
        {activeTab === "dashboard" && (
          <>
            {/* TOP KPI TELEMETRY STRIP (5 CARDS) */}
            <section className="kpi-telemetry-grid" aria-label="Temel Telemetri Göstergeleri">
              {/* KPI 1: AI Fire Outbreak Probability */}
              <div
                className="kpi-card kpi-card-primary"
                style={{ borderColor: baseline.riskColor }}
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
                          ? NASA_PALETTE.electricBlue.hex
                          : NASA_PALETTE.deepBlue.hex,
                      color:
                        baseline.probability >= 50 && baseline.probability < 75
                          ? NASA_PALETTE.neonYellow.hex
                          : NASA_PALETTE.white.hex,
                      borderColor: baseline.riskColor,
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
                        baseline.probability >= 75
                          ? NASA_PALETTE.rocketRed.hex
                          : baseline.probability >= 50
                          ? NASA_PALETTE.neonYellow.hex
                          : NASA_PALETTE.white.hex,
                    }}
                  >
                    %{baseline.probability.toFixed(1)}
                  </span>
                  {totalReductionDelta > 0.5 && (
                    <span className="kpi-delta-tag">
                      AI Önlemiyle: <strong>%{optimizedProbability}</strong> (-%
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
                <div className="kpi-subtext">
                  Model Güven Skoru: %{baseline.confidence} (NASA PSI Kalibreli)
                </div>
              </div>

              {/* KPI 2: Oxygen & Partial Pressure */}
              <div className="kpi-card">
                <div className="kpi-top-row">
                  <span className="kpi-label">OKSİJEN & KISMİ BASINÇ</span>
                  <span className="kpi-unit-tag">VOL % // kPa</span>
                </div>
                <div className="kpi-main-value-row">
                  <span className="kpi-big-number">
                    %{params.oxygenPercent.toFixed(1)}
                  </span>
                  <span className="kpi-secondary-readout">
                    ppO₂: {baseline.metrics.partialPressureO2Kpa} kPa
                  </span>
                </div>
                <div className="kpi-subtext">
                  Materyal Tutuşma Sınırı (LOI):{" "}
                  <strong style={{ color: NASA_PALETTE.neonYellow.hex }}>
                    %{baseline.metrics.effectiveLoi} O₂
                  </strong>{" "}
                  ({params.pressureKpa.toFixed(1)} kPa Toplam)
                </div>
              </div>

              {/* KPI 3: Ventilation Airflow & Gravity Convection */}
              <div className="kpi-card">
                <div className="kpi-top-row">
                  <span className="kpi-label">HAVA AKIŞ HIZI & ÇEKİM</span>
                  <span className="kpi-unit-tag">ECLSS FAN // G</span>
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
                  Etkin Konveksiyon: <strong>{baseline.metrics.effectiveVelocityCmS} cm/s</strong>{" "}
                  ({params.flowDirection === "CONCURRENT" ? "Aynı Yönlü" : "Ters Yönlü"})
                </div>
              </div>

              {/* KPI 4: Predicted Flame Spread & Gas Telemetry */}
              <div className="kpi-card">
                <div className="kpi-top-row">
                  <span className="kpi-label">YAYILIM HIZI & GAZ TELEMETRİSİ</span>
                  <span className="kpi-unit-tag">SAFFIRE // SAME-R</span>
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
                          : NASA_PALETTE.blueYonder.hex,
                    }}
                  >
                    CO: {params.coPpm} ppm
                  </span>
                </div>
                <div className="kpi-subtext">
                  CO₂: %{params.co2Percent.toFixed(2)} | Kabin: {params.temperatureC.toFixed(1)}°C | Güç:{" "}
                  {params.ignitionPowerW}W
                </div>
              </div>
            </section>

            {/* MAIN WORKSPACE GRID: LEFT = SIMULATION + TELEMETRY SLIDERS, RIGHT = AI RECOMMENDATIONS */}
            <section className="workspace-split-grid">
              {/* LEFT COLUMN: 2D Physics Simulation + Interactive Environmental Telemetry Controls */}
              <div className="sim-and-controls-col">
                <FlameSimulationCanvas
                  params={params}
                  riskEvaluation={baseline}
                  onUpdateParams={handleUpdateParams}
                  onApplyAllRecommendations={handleApplyAllRecommendations}
                  hasRecommendations={recommendations.length > 0}
                />

                {/* Interactive Environmental Parameter Sliders */}
                <div className="panel-card telemetry-controls-card">
                  <div className="panel-card-header">
                    <div>
                      <span className="section-eyebrow">
                        ÇEVRE KOŞULLARI VE TELEMETRİ GİRİŞ PARAMETRELERİ
                      </span>
                      <h3>
                        Canlı Çevresel Telemetri Simülasyon Kontrolleri
                      </h3>
                    </div>
                    {previousParamsSnapshot && (
                      <button
                        type="button"
                        className="nasa-btn nasa-btn-xs"
                        onClick={handleUndoOptimization}
                      >
                        ↺ Değişiklikleri Geri Al
                      </button>
                    )}
                  </div>

                  <div className="sliders-grid">
                    {/* Slider 1: Oxygen Concentration */}
                    <div className="slider-control-box">
                      <div className="slider-header">
                        <label htmlFor="slider-o2">Oksijen Oranı (O₂ % vol)</label>
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
                      <div className="slider-scale-hints">
                        <span>%12 (Hipoksik)</span>
                        <span>%21 (ISS)</span>
                        <span>%34 (Lunar EVA)</span>
                      </div>
                    </div>

                    {/* Slider 2: Ventilation Airflow Velocity */}
                    <div className="slider-control-box">
                      <div className="slider-header">
                        <label htmlFor="slider-flow">
                          Havalandırma Hızı (cm/s)
                        </label>
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
                      <div className="slider-scale-hints">
                        <span>0 (Sönme/Quench)</span>
                        <span>10 (BASS-II)</span>
                        <span>20 (SAFFIRE)</span>
                        <span>35+ (Blowoff)</span>
                      </div>
                    </div>

                    {/* Slider 3: Ambient Cabin Pressure */}
                    <div className="slider-control-box">
                      <div className="slider-header">
                        <label htmlFor="slider-pressure">
                          Kabin Basıncı (kPa)
                        </label>
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
                      <div className="slider-scale-hints">
                        <span>56.5 kPa (Ay)</span>
                        <span>70 kPa (Mars)</span>
                        <span>101.3 kPa (ISS/Dünya)</span>
                      </div>
                    </div>

                    {/* Slider 4: Gravity Level */}
                    <div className="slider-control-box">
                      <div className="slider-header">
                        <label htmlFor="slider-gravity">
                          Yerçekimi İvmesi (g)
                        </label>
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
                      <div className="slider-scale-hints">
                        <span>0.00g (ISS)</span>
                        <span>0.16g (Ay)</span>
                        <span>0.38g (Mars)</span>
                        <span>1.00g (Dünya)</span>
                      </div>
                    </div>

                    {/* Slider 5: Ignition / Thermal Power */}
                    <div className="slider-control-box">
                      <div className="slider-header">
                        <label htmlFor="slider-power">
                          Termal / Ateşleme Gücü (W)
                        </label>
                        <span className="slider-readout">
                          {params.ignitionPowerW} W
                        </span>
                      </div>
                      <input
                        id="slider-power"
                        type="range"
                        min="20"
                        max="220"
                        step="5"
                        value={params.ignitionPowerW}
                        onChange={(e) =>
                          handleUpdateParams({
                            ignitionPowerW: parseInt(e.target.value, 10),
                          })
                        }
                        className="nasa-range"
                      />
                      <div className="slider-scale-hints">
                        <span>40W (Düşük)</span>
                        <span>80W (SAFFIRE-II)</span>
                        <span>182W (SAFFIRE-I)</span>
                      </div>
                    </div>

                    {/* Slider 6: CO Pyrolysis Telemetry */}
                    <div className="slider-control-box">
                      <div className="slider-header">
                        <label htmlFor="slider-co">
                          CO Gaz Telemetrisi (ppm)
                        </label>
                        <span className="slider-readout">
                          {params.coPpm} ppm
                        </span>
                      </div>
                      <input
                        id="slider-co"
                        type="range"
                        min="0"
                        max="160"
                        step="1"
                        value={params.coPpm}
                        onChange={(e) =>
                          handleUpdateParams({
                            coPpm: parseInt(e.target.value, 10),
                          })
                        }
                        className="nasa-range"
                      />
                      <div className="slider-scale-hints">
                        <span>0 ppm (Temiz)</span>
                        <span>25 ppm (Eşik)</span>
                        <span>131 ppm (BASS-II B8)</span>
                      </div>
                    </div>

                    {/* Select 7: Fuel / Sample Material */}
                    <div className="slider-control-box">
                      <div className="slider-header">
                        <label htmlFor="select-material">
                          Numune / Kabin Materyali
                        </label>
                        <span className="slider-readout">
                          LOI: %{MATERIALS_CATALOG[params.material]?.loi}
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
                            {m.label} — LOI: %{m.loi}
                          </option>
                        ))}
                      </select>
                    </div>

                    {/* Select 8: Airflow Direction */}
                    <div className="slider-control-box">
                      <div className="slider-header">
                        <label>Akış Yönü (Flow Geometry)</label>
                        <span className="slider-readout">
                          {params.flowDirection}
                        </span>
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
                          ⇉ Concurrent (Aynı Yönlü)
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
                          ⇇ Opposed (Ters Yönlü)
                        </button>
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              {/* RIGHT COLUMN: AI FIRE RISK MITIGATION & RECOMMENDATIONS ENGINE */}
              <aside className="ai-recommendations-col" aria-label="Yapay Zeka Yangın Önleme Önerileri">
                <div className="panel-card ai-panel-card">
                  <div className="ai-panel-header">
                    <div>
                      <span className="section-eyebrow">
                        YAPAY ZEKA KARAR DESTEK & RİSK DÜŞÜRME SİSTEMİ
                      </span>
                      <h3>
                        Yangın İhtimalini Düşürmek İçin Önerilen Müdahaleler
                      </h3>
                    </div>
                  </div>

                  {/* Summary Target Box */}
                  <div className="ai-optimization-summary">
                    <div className="opt-col">
                      <span className="opt-label">MEVCUT OLASILIK</span>
                      <strong
                        className="opt-value"
                        style={{ color: baseline.riskColor }}
                      >
                        %{baseline.probability}
                      </strong>
                    </div>
                    <div className="opt-arrow">→</div>
                    <div className="opt-col">
                      <span className="opt-label">ÖNERİ SONRASI HEDEF</span>
                      <strong
                        className="opt-value"
                        style={{ color: NASA_PALETTE.blueYonder.hex }}
                      >
                        %{optimizedProbability}
                      </strong>
                    </div>
                    <div className="opt-col opt-col-delta">
                      <span className="opt-label">TOPLAM DÜŞÜŞ</span>
                      <strong
                        className="opt-value"
                        style={{ color: NASA_PALETTE.neonYellow.hex }}
                      >
                        -%{totalReductionDelta}
                      </strong>
                    </div>
                  </div>

                  {recommendations.length > 0 && (
                    <button
                      type="button"
                      className="nasa-btn nasa-btn-yellow nasa-btn-block"
                      onClick={handleApplyAllRecommendations}
                    >
                      ★ Tüm AI Önerilerini Uygula ve Riski %{optimizedProbability}{" "}
                      Seviyesine İndir
                    </button>
                  )}

                  {/* Individual Ranked Recommendation Cards */}
                  <div className="recommendations-list">
                    {recommendations.length === 0 ? (
                      <div className="safe-state-box">
                        <div className="safe-state-title">
                          ✓ OPTİMUM GÜVENLİK ZARFINDA (QUENCHING / SAFE ZONE)
                        </div>
                        <p>
                          Mevcut çevre koşulları (%{params.oxygenPercent.toFixed(1)} O₂,{" "}
                          {params.airflowCmS.toFixed(1)} cm/s akış, {params.material})
                          mikroçekim tutuşma sınırının altındadır. Ek müdahale gerekmemektedir.
                        </p>
                      </div>
                    ) : (
                      recommendations.map((rec, index) => (
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
                              -%{rec.riskReductionDelta} RİSK DÜŞÜŞÜ
                            </span>
                          </div>

                          <div className="rec-category">{rec.category}</div>
                          <h4 className="rec-title">{rec.title}</h4>
                          <p className="rec-rationale">{rec.rationale}</p>

                          <div className="rec-card-footer">
                            <span className="rec-psi-ref">
                              Kanıt: <strong>{rec.psiReference}</strong>
                            </span>
                            <button
                              type="button"
                              className="nasa-btn nasa-btn-xs nasa-btn-apply"
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

            {/* BOTTOM SECTION: INTERACTIVE ENGINEERING & TELEMETRY CHARTS */}
            <section className="charts-section" aria-label="Mühendislik Grafikleri ve Faz Diyagramı">
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

      {/* 4. FOOTER & OFFICIAL NASA COLOR PALETTE SPEC BAR */}
      <footer className="mission-footer">
        <div className="palette-spec-strip">
          <span className="palette-strip-title">
            NASA TASARIM SİSTEMİ RENK PALETİ:
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
        <div className="footer-meta-row">
          <span>
            FLAMESCOPE // NASA Space Apps Challenge — Physical Sciences Informatics (PSI) Open Telemetry
          </span>
          <span>
            Veri Kaynakları: PSI-25 (BASS-II), PSI-98/99/100 (SAFFIRE I-III), PSI-68/69 (FLEX), PSI-101/102 (SAME-R)
          </span>
        </div>
      </footer>
    </div>
  );
}
