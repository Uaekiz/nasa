import { useState } from "react";
import { NASA_PALETTE } from "../theme/nasaPalette";
import { EXPERIMENTS_DATA } from "../data/nasaPsiData";

/**
 * High-precision SVG Engineering & Telemetry Charts
 * Uses exclusively the NASA color palette (#07173F, #0042A6, #0960E1, #2E96F5, #E43700, #8E1100, #EAFE07, #FFFFFF).
 */
export default function TelemetryCharts({
  params,
  mitigationPlan,
  timelineData,
  onSelectPsiPoint,
}) {
  const [hoveredIdx, setHoveredIdx] = useState(null);
  const [hoveredPsiExp, setHoveredPsiExp] = useState(null);

  const { baseline, optimizedProbability, combinedPatch, recommendations } =
    mitigationPlan;

  // --- CHART 1: TIME-SERIES TELEMETRY & AI RISK PROJECTION ---
  const tsWidth = 580;
  const tsHeight = 250;
  const padL = 44;
  const padR = 22;
  const padT = 24;
  const padB = 34;
  const plotW = tsWidth - padL - padR;
  const plotH = tsHeight - padT - padB;

  const getX = (idx) =>
    padL + (idx / Math.max(1, timelineData.length - 1)) * plotW;
  const getY = (val) => padT + plotH - (Math.min(100, Math.max(0, val)) / 100) * plotH;

  const unmitigatedPath = timelineData
    .map((pt, i) => `${i === 0 ? "M" : "L"} ${getX(i).toFixed(1)} ${getY(pt.riskUnmitigated).toFixed(1)}`)
    .join(" ");

  const mitigatedPath = timelineData
    .map((pt, i) => `${i === 0 ? "M" : "L"} ${getX(i).toFixed(1)} ${getY(pt.riskMitigated).toFixed(1)}`)
    .join(" ");

  const nowIdx = timelineData.findIndex((pt) => pt.tSec === 0);
  const nowX = nowIdx >= 0 ? getX(nowIdx) : padL + plotW * 0.65;

  // --- CHART 2: O2 % vs AIRFLOW (cm/s) FLAMMABILITY PHASE DIAGRAM ---
  const phWidth = 580;
  const phHeight = 250;
  const flowMax = 40;
  const o2Min = 12;
  const o2Max = 38;

  const mapFlowX = (flow) =>
    padL + (Math.min(flowMax, Math.max(0, flow)) / flowMax) * plotW;
  const mapO2Y = (o2) =>
    padT +
    plotH -
    ((Math.min(o2Max, Math.max(o2Min, o2)) - o2Min) / (o2Max - o2Min)) * plotH;

  const currX = mapFlowX(params.airflowCmS);
  const currY = mapO2Y(params.oxygenPercent);

  const targetFlow = combinedPatch.airflowCmS ?? params.airflowCmS;
  const targetO2 = combinedPatch.oxygenPercent ?? params.oxygenPercent;
  const targetX = mapFlowX(targetFlow);
  const targetY = mapO2Y(targetO2);

  return (
    <div className="charts-grid-2col">
      {/* 1. REAL-TIME TELEMETRY & AI RISK TRAJECTORY CHART */}
      <div className="chart-panel">
        <div className="chart-panel-header">
          <div>
            <span className="section-eyebrow">
              TELEMETRİ ZAMAN SERİSİ & AI RİSK PROJEKSİYONU
            </span>
            <h4>
              Müdahalesiz Seyir vs. AI Önlemleri Sonrası Yangın İhtimali (%)
            </h4>
          </div>
          <div className="chart-legend-inline">
            <span className="legend-item">
              <i
                className="legend-swatch"
                style={{ background: NASA_PALETTE.rocketRed.hex }}
              />
              Müdahalesiz Risk (%)
            </span>
            <span className="legend-item">
              <i
                className="legend-swatch"
                style={{ background: NASA_PALETTE.blueYonder.hex }}
              />
              AI Önlemli Projeksiyon (%)
            </span>
            <span className="legend-item">
              <i
                className="legend-swatch"
                style={{ background: NASA_PALETTE.neonYellow.hex }}
              />
              Şimdi (t=0s)
            </span>
          </div>
        </div>

        <div className="svg-chart-container">
          <svg
            viewBox={`0 0 ${tsWidth} ${tsHeight}`}
            className="nasa-svg-chart"
            role="img"
            aria-label="Zaman serisi yangın riski ve telemetri grafiği"
          >
            {/* Critical Risk Danger Zone Band (>=75%) */}
            <rect
              x={padL}
              y={getY(100)}
              width={plotW}
              height={getY(75) - getY(100)}
              fill="rgba(142, 17, 0, 0.28)"
            />
            {/* Safe Operating Zone Band (<25%) */}
            <rect
              x={padL}
              y={getY(25)}
              width={plotW}
              height={getY(0) - getY(25)}
              fill="rgba(0, 66, 166, 0.22)"
            />

            {/* Horizontal Grid Lines & Y-Axis Labels */}
            {[0, 25, 50, 75, 100].map((val) => {
              const y = getY(val);
              return (
                <g key={val}>
                  <line
                    x1={padL}
                    y1={y}
                    x2={padL + plotW}
                    y2={y}
                    stroke={
                      val === 75
                        ? "rgba(228, 55, 0, 0.55)"
                        : "rgba(0, 66, 166, 0.45)"
                    }
                    strokeDasharray={val === 75 ? "4 4" : undefined}
                    strokeWidth="1"
                  />
                  <text
                    x={padL - 8}
                    y={y + 4}
                    textAnchor="end"
                    fill={NASA_PALETTE.white.hex}
                    fontSize="10"
                    fontFamily="monospace"
                  >
                    %{val}
                  </text>
                </g>
              );
            })}

            {/* "NOW (t=0)" Vertical Divider */}
            <line
              x1={nowX}
              y1={padT}
              x2={nowX}
              y2={padT + plotH}
              stroke={NASA_PALETTE.neonYellow.hex}
              strokeWidth="1.5"
              strokeDasharray="3 3"
            />
            <text
              x={nowX + 5}
              y={padT + 11}
              fill={NASA_PALETTE.neonYellow.hex}
              fontSize="9.5"
              fontFamily="monospace"
              fontWeight="700"
            >
              AI MÜDAHALE NOKTASI (t=0)
            </text>

            {/* Unmitigated Trajectory Line (#E43700 Rocket Red) */}
            <path
              d={unmitigatedPath}
              fill="none"
              stroke={NASA_PALETTE.rocketRed.hex}
              strokeWidth="2.6"
            />

            {/* AI-Mitigated Trajectory Line (#2E96F5 Blue Yonder) */}
            <path
              d={mitigatedPath}
              fill="none"
              stroke={NASA_PALETTE.blueYonder.hex}
              strokeWidth="2.6"
              strokeDasharray="5 3"
            />

            {/* Data Points & Interactive Hover Targets */}
            {timelineData.map((pt, i) => {
              const cx = getX(i);
              const cyUn = getY(pt.riskUnmitigated);
              const cyMit = getY(pt.riskMitigated);
              const isHovered = hoveredIdx === i;

              return (
                <g
                  key={pt.label}
                  onMouseEnter={() => setHoveredIdx(i)}
                  onMouseLeave={() => setHoveredIdx(null)}
                  style={{ cursor: "pointer" }}
                >
                  {i % 2 === 0 && (
                    <text
                      x={cx}
                      y={padT + plotH + 18}
                      textAnchor="middle"
                      fill={
                        pt.tSec === 0
                          ? NASA_PALETTE.neonYellow.hex
                          : NASA_PALETTE.white.hex
                      }
                      fontSize="9.5"
                      fontFamily="monospace"
                    >
                      {pt.label}
                    </text>
                  )}

                  <circle
                    cx={cx}
                    cy={cyUn}
                    r={isHovered ? 5 : 3}
                    fill={NASA_PALETTE.rocketRed.hex}
                    stroke={NASA_PALETTE.white.hex}
                    strokeWidth="1"
                  />

                  {pt.isForecast && (
                    <circle
                      cx={cx}
                      cy={cyMit}
                      r={isHovered ? 5 : 3.2}
                      fill={NASA_PALETTE.blueYonder.hex}
                      stroke={NASA_PALETTE.neonYellow.hex}
                      strokeWidth="1.2"
                    />
                  )}

                  {/* Invisible wider hit rect for smooth hover */}
                  <rect
                    x={cx - 12}
                    y={padT}
                    width="24"
                    height={plotH}
                    fill="transparent"
                  />
                </g>
              );
            })}
          </svg>

          {/* Interactive Telemetry Readout Strip below Chart 1 */}
          <div className="chart- readout-bar">
            {hoveredIdx !== null && timelineData[hoveredIdx] ? (
              <div className="chart-hover-details">
                <span>
                  Zaman: <strong>{timelineData[hoveredIdx].label}</strong>
                </span>
                <span style={{ color: NASA_PALETTE.rocketRed.hex }}>
                  Müdahalesiz Risk:{" "}
                  <strong>%{timelineData[hoveredIdx].riskUnmitigated}</strong>
                </span>
                <span style={{ color: NASA_PALETTE.blueYonder.hex }}>
                  AI Önlemli Risk:{" "}
                  <strong>%{timelineData[hoveredIdx].riskMitigated}</strong>
                </span>
                <span>
                  O₂: <strong>%{timelineData[hoveredIdx].oxygenPercent}</strong> | Akış:{" "}
                  <strong>{timelineData[hoveredIdx].airflowCmS} cm/s</strong> | CO:{" "}
                  <strong>{timelineData[hoveredIdx].coPpm} ppm</strong>
                </span>
              </div>
            ) : (
              <div className="chart-hover-details">
                <span>
                  Mevcut AI Risk: <strong>%{baseline.probability}</strong>
                </span>
                <span style={{ color: NASA_PALETTE.neonYellow.hex }}>
                  AI Önlemleri Sonrası Hedef:{" "}
                  <strong>%{optimizedProbability}</strong> (Δ -%
                  {mitigationPlan.totalReductionDelta})
                </span>
                <span>Detaylı telemetri için grafik noktalarının üzerine gelin.</span>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* 2. NASA PSI FLAMMABILITY BOUNDARY PHASE DIAGRAM (O2 % vs AIRFLOW cm/s) */}
      <div className="chart-panel">
        <div className="chart-panel-header">
          <div>
            <span className="section-eyebrow">
              NASA PSI YANICILIK FAZ DİYAGRAMI (O₂ % vs. HAVA AKIŞI cm/s)
            </span>
            <h4>
              Mikroçekim Sönme (Quenching), Yayılım ve AI Güvenli Hedef Vektörü
            </h4>
          </div>
          <div className="chart-legend-inline">
            <span className="legend-item">
              <i
                className="legend-swatch"
                style={{ background: NASA_PALETTE.neonYellow.hex }}
              />
              Aktif Nokta
            </span>
            <span className="legend-item">
              <i
                className="legend-swatch"
                style={{ background: NASA_PALETTE.blueYonder.hex }}
              />
              AI Güvenli Hedef
            </span>
            <span className="legend-item">
              <i
                className="legend-swatch"
                style={{ background: NASA_PALETTE.white.hex }}
              />
              NASA PSI Testleri
            </span>
          </div>
        </div>

        <div className="svg-chart-container">
          <svg
            viewBox={`0 0 ${phWidth} ${phHeight}`}
            className="nasa-svg-chart"
            role="img"
            aria-label="Oksijen ve hava akışı yanıcılık faz diyagramı"
          >
            <defs>
              <marker
                id="aiVectorArrow"
                viewBox="0 0 10 10"
                refX="7"
                refY="5"
                markerWidth="6"
                markerHeight="6"
                orient="auto-start-reverse"
              >
                <path
                  d="M 0 1 L 10 5 L 0 9 z"
                  fill={NASA_PALETTE.neonYellow.hex}
                />
              </marker>
            </defs>

            {/* Zone 1: Quenching / Safe Low-O2 & Ultra-Low Flow Envelope */}
            <rect
              x={padL}
              y={mapO2Y(18.0)}
              width={plotW}
              height={padT + plotH - mapO2Y(18.0)}
              fill="rgba(0, 66, 166, 0.28)"
            />
            <rect
              x={padL}
              y={padT}
              width={mapFlowX(2.0) - padL}
              height={plotH}
              fill="rgba(0, 66, 166, 0.28)"
            />

            {/* Zone 2: Hyperoxic Flashover Danger Envelope (O2 > 25%) */}
            <rect
              x={mapFlowX(2.0)}
              y={padT}
              width={plotW - (mapFlowX(2.0) - padL)}
              height={mapO2Y(25.0) - padT}
              fill="rgba(142, 17, 0, 0.34)"
            />

            {/* Zone 3: Sustained Microgravity Spread Bowl Curve */}
            <path
              d={`M ${mapFlowX(1.6)} ${mapO2Y(36)} Q ${mapFlowX(
                3.5
              )} ${mapO2Y(16.8)} ${mapFlowX(14)} ${mapO2Y(
                17.2
              )} T ${mapFlowX(38)} ${mapO2Y(22.5)}`}
              fill="none"
              stroke={NASA_PALETTE.rocketRed.hex}
              strokeWidth="2"
              strokeDasharray="6 3"
            />

            {/* Zone Labels inside Diagram */}
            <text
              x={mapFlowX(20)}
              y={mapO2Y(33.5)}
              fill={NASA_PALETTE.rocketRed.hex}
              fontSize="9.5"
              fontFamily="monospace"
              fontWeight="700"
            >
              HİPEROKSİK KRİTİK YAYILIM BÖLGESİ
            </text>
            <text
              x={mapFlowX(18)}
              y={mapO2Y(14.5)}
              fill={NASA_PALETTE.blueYonder.hex}
              fontSize="9.5"
              fontFamily="monospace"
              fontWeight="700"
            >
              OKSİJEN AÇLIĞI / SÖNME (QUENCHING &lt; LOI)
            </text>
            <text
              x={mapFlowX(32)}
              y={mapO2Y(18.8)}
              fill={NASA_PALETTE.neonBlue.hex}
              fontSize="9"
              fontFamily="monospace"
            >
              BLOWOFF SINIRI
            </text>

            {/* Grid Lines & Axes */}
            {[15, 20, 25, 30, 35].map((o2Val) => {
              const y = mapO2Y(o2Val);
              return (
                <g key={o2Val}>
                  <line
                    x1={padL}
                    y1={y}
                    x2={padL + plotW}
                    y2={y}
                    stroke="rgba(0, 66, 166, 0.4)"
                    strokeWidth="1"
                  />
                  <text
                    x={padL - 6}
                    y={y + 3}
                    textAnchor="end"
                    fill={NASA_PALETTE.white.hex}
                    fontSize="9.5"
                    fontFamily="monospace"
                  >
                    %{o2Val}
                  </text>
                </g>
              );
            })}

            {[0, 5, 10, 15, 20, 25, 30, 35, 40].map((fVal) => {
              const x = mapFlowX(fVal);
              return (
                <g key={fVal}>
                  <line
                    x1={x}
                    y1={padT}
                    x2={x}
                    y2={padT + plotH}
                    stroke="rgba(0, 66, 166, 0.35)"
                    strokeWidth="1"
                  />
                  <text
                    x={x}
                    y={padT + plotH + 18}
                    textAnchor="middle"
                    fill={NASA_PALETTE.white.hex}
                    fontSize="9.5"
                    fontFamily="monospace"
                  >
                    {fVal}
                  </text>
                </g>
              );
            })}

            <text
              x={padL + plotW / 2}
              y={phHeight - 3}
              textAnchor="middle"
              fill={NASA_PALETTE.blueYonder.hex}
              fontSize="10"
              fontFamily="monospace"
            >
              Havalandırma Akış Hızı (cm/s) →
            </text>

            {/* Plot Real NASA PSI Reference Runs */}
            {EXPERIMENTS_DATA.map((exp) => {
              const px = mapFlowX(exp.simulationParams.airflowCmS);
              const py = mapO2Y(exp.simulationParams.oxygenPercent);
              const isSelected = hoveredPsiExp?.experimentId === exp.experimentId;
              return (
                <g
                  key={exp.experimentId}
                  onMouseEnter={() => setHoveredPsiExp(exp)}
                  onMouseLeave={() => setHoveredPsiExp(null)}
                  onClick={() => onSelectPsiPoint && onSelectPsiPoint(exp)}
                  style={{ cursor: "pointer" }}
                >
                  <circle
                    cx={px}
                    cy={py}
                    r={isSelected ? 6 : 4}
                    fill={
                      exp.reportedOutcome.includes("EXTINCTION") ||
                      exp.reportedOutcome.includes("SELF_EXTINGUISHED") ||
                      exp.reportedOutcome.includes("INSIGNIFICANT")
                        ? NASA_PALETTE.blueYonder.hex
                        : NASA_PALETTE.white.hex
                    }
                    stroke={NASA_PALETTE.deepBlue.hex}
                    strokeWidth="1.5"
                  />
                  <text
                    x={px + 6}
                    y={py - 4}
                    fill="rgba(255, 255, 255, 0.82)"
                    fontSize="8.5"
                    fontFamily="monospace"
                  >
                    {exp.sourceTestId}
                  </text>
                </g>
              );
            })}

            {/* AI Mitigation Vector Arrow (Current -> Target Safe Operating Point) */}
            {(Math.abs(currX - targetX) > 4 || Math.abs(currY - targetY) > 4) && (
              <g>
                <line
                  x1={currX}
                  y1={currY}
                  x2={targetX}
                  y2={targetY}
                  stroke={NASA_PALETTE.neonYellow.hex}
                  strokeWidth="2"
                  strokeDasharray="4 3"
                  markerEnd="url(#aiVectorArrow)"
                />
                <circle
                  cx={targetX}
                  cy={targetY}
                  r="6"
                  fill={NASA_PALETTE.blueYonder.hex}
                  stroke={NASA_PALETTE.white.hex}
                  strokeWidth="2"
                />
                <text
                  x={targetX + 9}
                  y={targetY + 12}
                  fill={NASA_PALETTE.blueYonder.hex}
                  fontSize="9.5"
                  fontFamily="monospace"
                  fontWeight="700"
                >
                  AI HEDEF (%{optimizedProbability})
                </text>
              </g>
            )}

            {/* Current Operating Point Crosshair (#EAFE07 Neon Yellow) */}
            <g>
              <circle
                cx={currX}
                cy={currY}
                r="10"
                fill="none"
                stroke={NASA_PALETTE.neonYellow.hex}
                strokeWidth="1.5"
              />
              <circle
                cx={currX}
                cy={currY}
                r="4.5"
                fill={
                  baseline.probability >= 60
                    ? NASA_PALETTE.rocketRed.hex
                    : NASA_PALETTE.neonYellow.hex
                }
              />
              <line
                x1={currX - 14}
                y1={currY}
                x2={currX + 14}
                y2={currY}
                stroke={NASA_PALETTE.neonYellow.hex}
                strokeWidth="1.2"
              />
              <line
                x1={currX}
                y1={currY - 14}
                x2={currX}
                y2={currY + 14}
                stroke={NASA_PALETTE.neonYellow.hex}
                strokeWidth="1.2"
              />
              <text
                x={currX + 12}
                y={currY - 8}
                fill={NASA_PALETTE.neonYellow.hex}
                fontSize="10"
                fontFamily="monospace"
                fontWeight="700"
              >
                AKTİF (%{baseline.probability})
              </text>
            </g>
          </svg>

          <div className="chart-readout-bar">
            {hoveredPsiExp ? (
              <div className="chart-hover-details">
                <span style={{ color: NASA_PALETTE.neonYellow.hex }}>
                  <strong>
                    {hoveredPsiExp.investigationId} // Test {hoveredPsiExp.sourceTestId}
                  </strong>
                </span>
                <span>
                  Materyal: <strong>{hoveredPsiExp.fuel}</strong> | Sonuç:{" "}
                  <strong>{hoveredPsiExp.reportedOutcome}</strong>
                </span>
                <span>
                  Simülasyona yüklemek için noktaya tıklayın.
                </span>
              </div>
            ) : (
              <div className="chart-hover-details">
                <span>
                  Aktif Konum:{" "}
                  <strong>
                    {params.airflowCmS.toFixed(1)} cm/s, %{params.oxygenPercent.toFixed(1)} O₂
                  </strong>
                </span>
                <span style={{ color: NASA_PALETTE.blueYonder.hex }}>
                  AI Güvenli Hedef:{" "}
                  <strong>
                    {targetFlow.toFixed(1)} cm/s, %{targetO2.toFixed(1)} O₂
                  </strong>
                </span>
                <span>
                  Beyaz/Mavi noktalar gerçek NASA PSI deneylerini gösterir (tıklanabilir).
                </span>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* 3. FULL-WIDTH AI RISK ATTRIBUTION & COUNTERMEASURE STEP-DOWN BAR CHART */}
      <div className="chart-panel chart-panel-full">
        <div className="chart-panel-header">
          <div>
            <span className="section-eyebrow">
              YAPAY ZEKA RİSK FAKTÖRÜ DAĞILIMI & ÖNLEM ETKİ SİMÜLASYONU
            </span>
            <h4>
              Çevresel Telemetri Katkı Ağırlıkları ve Önerilen Müdahalelerin Kümülatif Risk Düşürme Etkisi
            </h4>
          </div>
        </div>

        <div className="attribution-and-waterfall-grid">
          {/* Left: Environmental Telemetry Factor Weights */}
          <div className="factor-list-box">
            <div className="subpanel-title">
              Çevresel Telemetri Faktör Ağırlıkları (Toplam %100)
            </div>
            {baseline.factorContributions.map((f) => (
              <div key={f.id} className="factor-row">
                <div className="factor-row-top">
                  <span className="factor-name">{f.label}</span>
                  <span className="factor-meta">
                    {f.value} — <strong>%{f.weightPercent}</strong>
                  </span>
                </div>
                <div className="factor-bar-track">
                  <div
                    className="factor-bar-fill"
                    style={{
                      width: `${f.weightPercent}%`,
                      background: f.color,
                    }}
                  />
                </div>
              </div>
            ))}
          </div>

          {/* Right: Step-by-Step Risk Reduction Waterfall */}
          <div className="waterfall-box">
            <div className="subpanel-title">
              AI Önlemleri Uygulandığında Kademeli Yangın İhtimali Düşüşü
            </div>

            <div className="waterfall-rows">
              <div className="waterfall-row">
                <span className="wf-label">1. Mevcut Telemetri Riski</span>
                <div className="wf-bar-track">
                  <div
                    className="wf-bar-fill"
                    style={{
                      width: `${baseline.probability}%`,
                      background: baseline.riskColor,
                    }}
                  />
                </div>
                <span className="wf-val">%{baseline.probability}</span>
              </div>

              {recommendations.slice(0, 3).map((rec, idx) => (
                <div key={rec.id} className="waterfall-row">
                  <span className="wf-label">
                    {idx + 2}. {rec.category}
                  </span>
                  <div className="wf-bar-track">
                    <div
                      className="wf-bar-fill"
                      style={{
                        width: `${rec.postActionProbability}%`,
                        background: NASA_PALETTE.neonBlue.hex,
                      }}
                    />
                  </div>
                  <span
                    className="wf-val"
                    style={{ color: NASA_PALETTE.neonYellow.hex }}
                  >
                    %{rec.postActionProbability} (-%{rec.riskReductionDelta})
                  </span>
                </div>
              ))}

              <div className="waterfall-row waterfall-row-final">
                <span className="wf-label">
                  ★ Tüm AI Önerileri Sonrası Hedef
                </span>
                <div className="wf-bar-track">
                  <div
                    className="wf-bar-fill"
                    style={{
                      width: `${optimizedProbability}%`,
                      background: NASA_PALETTE.blueYonder.hex,
                    }}
                  />
                </div>
                <span
                  className="wf-val"
                  style={{ color: NASA_PALETTE.blueYonder.hex }}
                >
                  %{optimizedProbability}
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
