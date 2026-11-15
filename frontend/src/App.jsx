import { useEffect, useMemo, useRef, useState } from "react";
import { MISSION_PRESETS, MATERIALS_CATALOG } from "./data/nasaPsiData";
import { generateMitigationRecommendations, generateTelemetryTimeline } from "./services/fireRiskEngine";
import { checkBackendHealth } from "./services/apiClient";
import { formatNumber } from "./services/format";
import FlameSimulationCanvas from "./components/FlameSimulationCanvas";
import TelemetryCharts from "./components/TelemetryCharts";
import ExperimentExplorer from "./components/ExperimentExplorer";
import AiAssistantPanel from "./components/AiAssistantPanel";
import ScenarioAnalysisPanel from "./components/ScenarioAnalysisPanel";
import "./App.css";
import "./brand.css";

const number = (value, digits = 1) => formatNumber(value, {
  minimumFractionDigits: digits, maximumFractionDigits: digits,
});

const SLIDERS = [
  { key: "oxygenPercent", id: "slider-o2", label: "Oxygen concentration (O₂)", unit: "%", min: 12, max: 38, step: 0.2, digits: 1 },
  { key: "airflowCmS", id: "slider-flow", label: "Airflow speed", unit: "cm/s", min: 0, max: 40, step: 0.5, digits: 1 },
  { key: "pressureKpa", id: "slider-pressure", label: "Pressure", unit: "kPa", min: 35, max: 140, step: 1, digits: 1 },
  { key: "gravityG", id: "slider-gravity", label: "Gravity", unit: "g", min: 0, max: 1, step: 0.02, digits: 2 },
  { key: "temperatureC", id: "slider-temperature", label: "Temperature", unit: "°C", min: -20, max: 100, step: 0.5, digits: 1 },
  { key: "ignitionPowerW", id: "slider-power", label: "Ignition power", unit: "W", min: 0, max: 250, step: 1, digits: 0 },
  { key: "coPpm", id: "slider-co", label: "CO concentration", unit: "ppm", min: 0, max: 250, step: 1, digits: 0 },
  { key: "co2Percent", id: "slider-co2", label: "CO₂ concentration", unit: "%", min: 0, max: 5, step: 0.01, digits: 2 },
];

export default function App() {
  const [activeTab, setActiveTab] = useState("dashboard");
  const [activePresetId, setActivePresetId] = useState("lunar-artemis");
  const [params, setParams] = useState(MISSION_PRESETS[1].params);
  const [backendStatus, setBackendStatus] = useState({ status: "CHECKING" });
  const simulationCaptureRef = useRef(null);

  useEffect(() => {
    let active = true;
    checkBackendHealth().then((status) => { if (active) setBackendStatus(status); });
    return () => { active = false; };
  }, []);

  // Retain the existing illustrative calculations used by the scene and charts.
  // The generated patches are chart variants, never actions applied to inputs.
  const mitigationPlan = useMemo(() => generateMitigationRecommendations(params), [params]);
  const timelineData = useMemo(() => generateTelemetryTimeline(params), [params]);
  const { baseline } = mitigationPlan;

  function selectPreset(preset) {
    setActivePresetId(preset.id);
    setParams({ ...preset.params });
  }

  function updateParams(patch) {
    setActivePresetId("custom");
    setParams((previous) => ({ ...previous, ...patch }));
  }

  function captureSimulationImage() {
    if (!simulationCaptureRef.current) throw new Error("The 3D scene is not ready yet.");
    return simulationCaptureRef.current();
  }

  const apiLabel = backendStatus.status === "UP" ? "Backend API reachable"
    : backendStatus.status === "CHECKING" ? "Checking backend API" : "Backend API unavailable";

  return <div className="nasa-app-shell">
    <header className="mission-header">
      <div className="brand-cluster"><img
  src="/nasa.jpeg"
  className="flamescope-logo"
  alt="FLAMESCOPE logo"
/>
        <div>
          <div className="brand-title-row"><h1>FLAMESCOPE</h1></div>
          
          <span className={`backend-status backend-status-${backendStatus.status.toLowerCase()}`} role="status"
            title="Checks the backend health endpoint only; RAG and model availability are not implied.">{apiLabel}</span>
        </div>
      </div>
      <nav className="main-nav-tabs" aria-label="Main navigation">
        <button type="button" className={`nav-tab-btn ${activeTab === "dashboard" ? "active" : ""}`} onClick={() => setActiveTab("dashboard")}>Scenario workspace</button>
        <button type="button" className={`nav-tab-btn ${activeTab === "explorer" ? "active" : ""}`} onClick={() => setActiveTab("explorer")}>NASA PSI Catalog</button>
        <button type="button" className={`nav-tab-btn ${activeTab === "assistant" ? "active" : ""}`} onClick={() => setActiveTab("assistant")}>Source assistant</button>
      </nav>
    </header>

    {activeTab === "dashboard" && <section className="preset-ribbon" aria-label="Illustrative scenario presets">
      <span className="preset-ribbon-label">INPUT PRESET:</span>
      <div className="preset-buttons-scroll">{MISSION_PRESETS.map((preset) => <button type="button" key={preset.id}
        title={preset.description} className={`preset-chip-btn ${activePresetId === preset.id ? "active" : ""}`} onClick={() => selectPreset(preset)}>
        <span className="preset-chip-name">{preset.name}</span><span className="preset-chip-badge">{preset.badge}</span>
      </button>)}</div>
    </section>}

    <main className="mission-main">
      {activeTab === "dashboard" && <>
        <p className="simulation-notice" role="note">Illustrative simulation: inputs, geometry, colors, curves and scores are model examples, not recorded experiment measurements or validated fire predictions. Open NASA PSI experiments for source records.</p>
        <section className="kpi-telemetry-grid" aria-label="Current illustrative scenario">
          <div className="kpi-card kpi-card-primary" style={{ borderTopColor: baseline.riskColor }}>
            <div className="kpi-top-row"><span className="kpi-label">ILLUSTRATIVE SCORE</span><span className="kpi-status-badge" style={{ background: baseline.riskColor, color: baseline.riskLevel === "HIGH" ? "#07173f" : "#ffffff" }}>{baseline.riskLabelTr}</span></div>
            <div className="kpi-main-value-row"><span className="kpi-big-number">{number(baseline.probability)} / 100</span></div>
            <div className="kpi-progress-bar"><div className="kpi-progress-fill" style={{ width: `${baseline.probability}%`, background: baseline.riskColor }} /></div>
            <p className="kpi-subtext">A unitless model score; no fire probability or safety threshold is established.</p>
          </div>
          <div className="kpi-card">
            <div className="kpi-top-row"><span className="kpi-label">OXYGEN & PRESSURE</span><span className="kpi-unit-tag">Scenario inputs</span></div>
            <div className="kpi-main-value-row"><span className="kpi-big-number">{number(params.oxygenPercent)}%</span><span className="kpi-secondary-readout">{number(params.pressureKpa)} kPa</span></div>
            <p className="kpi-subtext">Values entered for this scenario, not live sensor readings.</p>
          </div>
          <div className="kpi-card">
            <div className="kpi-top-row"><span className="kpi-label">AIRFLOW & GRAVITY</span><span className="kpi-unit-tag">{params.flowDirection === "CONCURRENT" ? "Concurrent" : "Opposed"}</span></div>
            <div className="kpi-main-value-row"><span className="kpi-big-number">{number(params.airflowCmS)} <small className="unit-inline">cm/s</small></span><span className="kpi-secondary-readout">{number(params.gravityG, 2)} g</span></div>
            <p className="kpi-subtext">The scene illustrates these inputs without predicting measured behavior.</p>
          </div>
          <div className="kpi-card">
            <div className="kpi-top-row"><span className="kpi-label">TEMPERATURE & POWER</span><span className="kpi-unit-tag">{params.material}</span></div>
            <div className="kpi-main-value-row"><span className="kpi-big-number">{number(params.temperatureC)} <small className="unit-inline">°C</small></span><span className="kpi-secondary-readout">{number(params.ignitionPowerW, 0)} W</span></div>
            <p className="kpi-subtext">CO: {number(params.coPpm, 0)} ppm · CO₂: {number(params.co2Percent, 2)}%</p>
          </div>
        </section>

        <section className="workspace-split-grid">
          <div className="sim-and-controls-col">
            <FlameSimulationCanvas params={params} riskEvaluation={baseline} captureRef={simulationCaptureRef} />
            <div className="panel-card">
              <div className="panel-card-header"><div><span className="section-eyebrow">SCENARIO INPUTS</span><h3>Adjust the illustrative scenario</h3></div></div>
              <div className="sliders-grid">
                {SLIDERS.map(({ key, id, label, unit, min, max, step, digits }) => <div className="slider-control-box" key={key}>
                  <div className="slider-header"><label htmlFor={id}>{label}</label><span className="slider-readout">{number(params[key], digits)} {unit}</span></div>
                  <input id={id} className="nasa-range" type="range" min={min} max={max} step={step} value={params[key]}
                    onChange={(event) => updateParams({ [key]: Number(event.target.value) })} />
                </div>)}
                <div className="slider-control-box">
                  <div className="slider-header"><label htmlFor="select-material">Sample material</label></div>
                  <select id="select-material" className="nasa-select nasa-select-full" value={params.material} onChange={(event) => updateParams({ material: event.target.value })}>
                    {Object.values(MATERIALS_CATALOG).map((material) => <option key={material.id} value={material.id}>{material.label}</option>)}
                  </select>
                </div>
                <div className="slider-control-box">
                  <div className="slider-header"><span>Airflow direction</span></div>
                  <div className="direction-toggle-group" role="group" aria-label="Scenario airflow direction">
                    <button type="button" className={`nasa-btn nasa-btn-sm ${params.flowDirection === "CONCURRENT" ? "active" : ""}`} onClick={() => updateParams({ flowDirection: "CONCURRENT" })}>⇉ Concurrent</button>
                    <button type="button" className={`nasa-btn nasa-btn-sm ${params.flowDirection === "OPPOSED" ? "active" : ""}`} onClick={() => updateParams({ flowDirection: "OPPOSED" })}>⇇ Opposed</button>
                  </div>
                </div>
              </div>
            </div>
          </div>
          <aside className="ai-recommendations-col"><ScenarioAnalysisPanel params={params} onCaptureImage={captureSimulationImage} /></aside>
        </section>
        <section className="charts-section"><TelemetryCharts params={params} mitigationPlan={mitigationPlan} timelineData={timelineData} /></section>
      </>}
      {activeTab === "explorer" && <ExperimentExplorer />}
      {activeTab === "assistant" && <AiAssistantPanel />}
    </main>

    <footer className="flamescope-footer">
  <strong>NASA Space Apps Challenge</strong>
  <span>
    Flame in Freefall — Fire Safety in Microgravity
  </span>
</footer>
  </div>;
}
