import { useEffect, useRef, useState } from "react";
import * as echarts from "echarts";
import { NASA_PALETTE } from "../theme/nasaPalette";
import { formatNumber } from "../services/format";

/**
 * Reusable ECharts wrapper hook/component with ResizeObserver cleanup.
 */
function EChartContainer({ option, onPointClick, height = 290 }) {
  const chartDomRef = useRef(null);
  const instanceRef = useRef(null);

  useEffect(() => {
    const dom = chartDomRef.current;
    if (!dom) return;

    const chart = echarts.init(dom, null, { renderer: "canvas", locale: "EN" });
    instanceRef.current = chart;

    const resizeObserver = new ResizeObserver(() => {
      chart.resize();
    });
    resizeObserver.observe(dom);

    return () => {
      resizeObserver.disconnect();
      chart.dispose();
      instanceRef.current = null;
    };
  }, []);

  useEffect(() => {
    const chart = instanceRef.current;
    if (!chart || !option) return;
    chart.setOption(option, { notMerge: true });
  }, [option]);

  useEffect(() => {
    const chart = instanceRef.current;
    if (!chart || !onPointClick) return;
    const handler = (params) => {
      onPointClick(params);
    };
    chart.on("click", handler);
    return () => {
      chart.off("click", handler);
    };
  }, [onPointClick]);

  return (
    <div
      ref={chartDomRef}
      style={{ width: "100%", height: `${height}px` }}
      className="echart-canvas-box"
    />
  );
}

export default function TelemetryCharts({
  params,
  mitigationPlan,
  timelineData,
}) {
  const [rightChartMode, setRightChartMode] = useState("phase"); // "phase" | "factors"
  const { baseline, optimizedProbability, combinedPatch, recommendations } =
    mitigationPlan;

  // 1. ECharts Option: Time-Series Telemetry & AI Risk Forecast
  const timelineOption = {
    backgroundColor: "transparent",
    tooltip: {
      trigger: "axis",
      confine: true,
      backgroundColor: NASA_PALETTE.deepBlue.hex,
      borderColor: NASA_PALETTE.electricBlue.hex,
      textStyle: {
        color: NASA_PALETTE.white.hex,
        fontSize: 12,
        fontFamily: "Inter, sans-serif",
      },
      formatter: (items) => {
        if (!items?.length) return "";
        const idx = items[0].dataIndex;
        const pt = timelineData[idx];
        return [
          `<strong>Example time: ${pt.label}</strong>`,
          `<span style="color:${NASA_PALETTE.rocketRed.hex}">●</span> Base example score: <b>${formatNumber(pt.riskUnmitigated)} / 100</b>`,
          `<span style="color:${NASA_PALETTE.blueYonder.hex}">●</span> Variant example score: <b>${formatNumber(pt.riskMitigated)} / 100</b>`,
          `O₂: <b>${formatNumber(pt.oxygenPercent)}%</b> | Airflow: <b>${formatNumber(pt.airflowCmS)} cm/s</b> | CO: <b>${formatNumber(pt.coPpm)} ppm</b>`,
        ].join("<br/>");
      },
    },
    legend: {
      type: "scroll",
      top: 0,
      right: 8,
      itemWidth: 14,
      itemHeight: 8,
      textStyle: {
        color: NASA_PALETTE.deepBlue.hex,
        fontSize: 11.5,
        fontWeight: 600,
      },
    },
    grid: {
      left: 58,
      right: 20,
      top: 36,
      bottom: 45,
    },
    xAxis: {
      type: "category",
      boundaryGap: false,
      data: timelineData.map((d) => d.label),
      name: "Example time (s)",
      nameLocation: "middle",
      nameGap: 22,
      axisLine: { lineStyle: { color: "#CBD5E1" } },
      axisLabel: {
        color: NASA_PALETTE.deepBlue.hex,
        fontSize: 11,
        fontFamily: "monospace",
      },
    },
    yAxis: {
      type: "value",
      min: 0,
      max: 100,
      name: "Score (0–100)",
      nameLocation: "middle",
      nameGap: 38,
      axisLabel: {
        formatter: (value) => formatNumber(value),
        color: NASA_PALETTE.deepBlue.hex,
        fontSize: 11,
        fontFamily: "monospace",
      },
      splitLine: {
        lineStyle: { color: "#E2E8F0", type: "dashed" },
      },
    },
    series: [
      {
        name: "Base example score",
        type: "line",
        smooth: 0.3,
        symbol: "circle",
        symbolSize: 6,
        data: timelineData.map((d) => d.riskUnmitigated),
        itemStyle: { color: NASA_PALETTE.rocketRed.hex },
        lineStyle: { width: 3, color: NASA_PALETTE.rocketRed.hex },
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: "rgba(228, 55, 0, 0.22)" },
            { offset: 1, color: "rgba(228, 55, 0, 0.01)" },
          ]),
        },
        markLine: {
          symbol: ["none", "none"],
          label: {
            formatter: "Reference input (t=0)",
            color: NASA_PALETTE.electricBlue.hex,
            fontWeight: 700,
            fontSize: 10.5,
          },
          lineStyle: {
            color: NASA_PALETTE.electricBlue.hex,
            type: "dashed",
            width: 1.5,
          },
          data: [{ xAxis: "REFERENCE" }],
        },
      },
      {
        name: "Variant example score",
        type: "line",
        smooth: 0.3,
        symbol: "circle",
        symbolSize: 6,
        data: timelineData.map((d) => d.riskMitigated),
        itemStyle: { color: NASA_PALETTE.neonBlue.hex },
        lineStyle: {
          width: 3,
          type: "dashed",
          color: NASA_PALETTE.neonBlue.hex,
        },
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: "rgba(9, 96, 225, 0.16)" },
            { offset: 1, color: "rgba(46, 150, 245, 0.01)" },
          ]),
        },
      },
    ],
  };

  // 2A. Simulation inputs and the heuristic model target; no source experiment points.
  const targetFlow = combinedPatch.airflowCmS ?? params.airflowCmS;
  const targetO2 = combinedPatch.oxygenPercent ?? params.oxygenPercent;

  const phaseDiagramOption = {
    backgroundColor: "transparent",
    tooltip: {
      trigger: "item",
      confine: true,
      backgroundColor: NASA_PALETTE.deepBlue.hex,
      borderColor: NASA_PALETTE.electricBlue.hex,
      textStyle: { color: NASA_PALETTE.white.hex, fontSize: 12 },
      formatter: (p) => {
        return `<strong>${p.seriesName}</strong><br/>Airflow: <b>${formatNumber(p.value[0])} cm/s</b> | O₂: <b>${formatNumber(p.value[1])}%</b>`;
      },
    },
    legend: {
      type: "scroll",
      top: 0,
      right: 8,
      textStyle: {
        color: NASA_PALETTE.deepBlue.hex,
        fontSize: 11.5,
        fontWeight: 600,
      },
    },
    grid: {
      left: 62,
      right: 22,
      top: 36,
      bottom: 34,
    },
    xAxis: {
      type: "value",
      name: "Airflow (cm/s)",
      nameLocation: "middle",
      nameGap: 22,
      min: 0,
      max: 40,
      nameTextStyle: {
        color: NASA_PALETTE.deepBlue.hex,
        fontWeight: 600,
        fontSize: 11,
      },
      axisLine: { lineStyle: { color: "#CBD5E1" } },
      axisLabel: { formatter: (value) => formatNumber(value), color: NASA_PALETTE.deepBlue.hex, fontFamily: "monospace" },
      splitLine: { lineStyle: { color: "#E2E8F0", type: "dashed" } },
    },
    yAxis: {
      type: "value",
      name: "O₂ (%)",
      nameLocation: "middle",
      nameGap: 42,
      min: 12,
      max: 38,
      nameTextStyle: {
        color: NASA_PALETTE.deepBlue.hex,
        fontWeight: 600,
        fontSize: 11,
      },
      axisLabel: {
        formatter: (value) => `${formatNumber(value)}%`,
        color: NASA_PALETTE.deepBlue.hex,
        fontFamily: "monospace",
      },
      splitLine: { lineStyle: { color: "#E2E8F0", type: "dashed" } },
    },
    series: [
      {
        name: "Current inputs",
        type: "effectScatter",
        symbolSize: 15,
        rippleEffect: { brushType: "stroke", scale: 3.2 },
        data: [[params.airflowCmS, params.oxygenPercent]],
        itemStyle: {
          color:
            baseline.probability >= 55
              ? NASA_PALETTE.rocketRed.hex
              : NASA_PALETTE.neonBlue.hex,
        },
      },
      {
        name: "Model variant input",
        type: "scatter",
        symbol: "diamond",
        symbolSize: 15,
        data: [[targetFlow, targetO2]],
        itemStyle: {
          color: NASA_PALETTE.blueYonder.hex,
          borderColor: NASA_PALETTE.deepBlue.hex,
          borderWidth: 1.5,
        },
      },
    ],
  };

  // 2B. ECharts Option: Risk Factor Weights & Step-Down Mitigation Bar Chart
  const factorCategories = [
    "Current model score",
    ...recommendations.slice(0, 3).map((r) => r.category),
    "Combined model variant",
  ];
  const factorValues = [
    baseline.probability,
    ...recommendations.slice(0, 3).map((r) => r.postActionProbability),
    optimizedProbability,
  ];

  const mitigationBarOption = {
    backgroundColor: "transparent",
    tooltip: {
      trigger: "axis",
      confine: true,
      axisPointer: { type: "shadow" },
      backgroundColor: NASA_PALETTE.deepBlue.hex,
      textStyle: { color: NASA_PALETTE.white.hex, fontSize: 12 },
      formatter: (items) => {
        const it = items[0];
        return `<strong>${it.name}</strong><br/>Illustrative score: <b>${formatNumber(it.value)} / 100</b>`;
      },
    },
    grid: {
      left: 165,
      right: 36,
      top: 18,
      bottom: 45,
    },
    xAxis: {
      type: "value",
      min: 0,
      max: 100,
      name: "Score (0–100)",
      nameLocation: "middle",
      nameGap: 24,
      axisLabel: {
        formatter: (value) => formatNumber(value),
        color: NASA_PALETTE.deepBlue.hex,
        fontFamily: "monospace",
      },
      splitLine: { lineStyle: { color: "#E2E8F0", type: "dashed" } },
    },
    yAxis: {
      type: "category",
      inverse: true,
      data: factorCategories,
      axisLine: { lineStyle: { color: "#CBD5E1" } },
      axisLabel: {
        color: NASA_PALETTE.deepBlue.hex,
        fontSize: 11,
        fontWeight: 600,
        width: 145,
        overflow: "break",
      },
    },
    series: [
      {
        name: "Illustrative score (0–100)",
        type: "bar",
        barWidth: 18,
        data: factorValues.map((val, idx) => ({
          value: val,
          itemStyle: {
            borderRadius: [0, 4, 4, 0],
            color:
              idx === 0
                ? baseline.riskColor
                : idx === factorValues.length - 1
                ? NASA_PALETTE.blueYonder.hex
                : NASA_PALETTE.neonBlue.hex,
          },
        })),
        label: {
          show: true,
          position: "right",
          formatter: ({ value }) => formatNumber(value),
          color: NASA_PALETTE.deepBlue.hex,
          fontWeight: 700,
          fontFamily: "monospace",
        },
      },
    ],
  };

  return (
    <div className="charts-grid-2col">
      {/* CHART 1: ECHARTS TIME-SERIES TELEMETRY & AI RISK TRAJECTORY */}
      <div className="chart-panel">
        <div className="chart-panel-header">
          <div>
            <span className="section-eyebrow">
              ILLUSTRATIVE MODEL // EXAMPLE CURVES
            </span>
            <h4>Example model score curves</h4>
          </div>
          <span className="chart-badge-pill">
            Variant difference: {formatNumber(mitigationPlan.totalReductionDelta)} points
          </span>
        </div>

        <EChartContainer option={timelineOption} height={275} />
        <p className="chart-context-note">Both curves are generated by the local example model on an arbitrary time axis. They are not sensor history, a recorded intervention, or a validated future forecast. Scores use a 0–100 scale; differences are points.</p>
      </div>

      {/* CHART 2: ECHARTS PHASE DIAGRAM OR MITIGATION WATERFALL */}
      <div className="chart-panel">
        <div className="chart-panel-header">
          <div>
            <span className="section-eyebrow">
              ILLUSTRATIVE INPUTS & MODEL VARIANTS
            </span>
            <h4>
              {rightChartMode === "phase"
                ? "Scenario inputs (oxygen and airflow)"
                : "Illustrative variant scores"}
            </h4>
          </div>

          <div className="camera-view-group">
            <button
              type="button"
              className={`nasa-btn nasa-btn-xs ${
                rightChartMode === "phase" ? "active" : ""
              }`}
              onClick={() => setRightChartMode("phase")}
            >
              Inputs
            </button>
            <button
              type="button"
              className={`nasa-btn nasa-btn-xs ${
                rightChartMode === "factors" ? "active" : ""
              }`}
              onClick={() => setRightChartMode("factors")}
            >
              Model variants
            </button>
          </div>
        </div>

        {rightChartMode === "phase" ? (
          <EChartContainer
            option={phaseDiagramOption}
            height={275}
          />
        ) : (
          <EChartContainer option={mitigationBarOption} height={275} />
        )}
        <p className="chart-context-note">The variant uses existing model parameter changes for illustration. No preferred operating condition, measured improvement, or safety threshold is established.</p>
      </div>
    </div>
  );
}
