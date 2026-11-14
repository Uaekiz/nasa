import { useEffect, useRef, useState } from "react";
import * as echarts from "echarts";
import { NASA_PALETTE } from "../theme/nasaPalette";
import { EXPERIMENTS_DATA } from "../data/nasaPsiData";

/**
 * Reusable ECharts wrapper hook/component with ResizeObserver cleanup.
 */
function EChartContainer({ option, onPointClick, height = 290 }) {
  const chartDomRef = useRef(null);
  const instanceRef = useRef(null);

  useEffect(() => {
    const dom = chartDomRef.current;
    if (!dom) return;

    const chart = echarts.init(dom, null, { renderer: "canvas" });
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
  onSelectPsiPoint,
}) {
  const [rightChartMode, setRightChartMode] = useState("phase"); // "phase" | "factors"
  const { baseline, optimizedProbability, combinedPatch, recommendations } =
    mitigationPlan;

  // 1. ECharts Option: Time-Series Telemetry & AI Risk Forecast
  const timelineOption = {
    backgroundColor: "transparent",
    tooltip: {
      trigger: "axis",
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
          `<strong>Zaman: ${pt.label}</strong>`,
          `<span style="color:${NASA_PALETTE.rocketRed.hex}">●</span> Müdahalesiz Risk: <b>%${pt.riskUnmitigated}</b>`,
          `<span style="color:${NASA_PALETTE.blueYonder.hex}">●</span> AI Önlemli Risk: <b>%${pt.riskMitigated}</b>`,
          `O₂: <b>%${pt.oxygenPercent}</b> | Akış: <b>${pt.airflowCmS} cm/s</b> | CO: <b>${pt.coPpm} ppm</b>`,
        ].join("<br/>");
      },
    },
    legend: {
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
      left: 44,
      right: 20,
      top: 36,
      bottom: 28,
    },
    xAxis: {
      type: "category",
      boundaryGap: false,
      data: timelineData.map((d) => d.label),
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
      axisLabel: {
        formatter: "%{value}",
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
        name: "Müdahalesiz Risk (%)",
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
            formatter: "AI Müdahale (t=0)",
            color: NASA_PALETTE.electricBlue.hex,
            fontWeight: 700,
            fontSize: 10.5,
          },
          lineStyle: {
            color: NASA_PALETTE.electricBlue.hex,
            type: "dashed",
            width: 1.5,
          },
          data: [{ xAxis: "ŞİMDİ" }],
        },
      },
      {
        name: "AI Önlemli Projeksiyon (%)",
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

  // 2A. ECharts Option: NASA PSI Flammability Phase Diagram (O2 % vs Airflow cm/s)
  const targetFlow = combinedPatch.airflowCmS ?? params.airflowCmS;
  const targetO2 = combinedPatch.oxygenPercent ?? params.oxygenPercent;

  const psiScatterData = EXPERIMENTS_DATA.map((exp) => ({
    name: `${exp.investigationId} (${exp.sourceTestId})`,
    value: [
      exp.simulationParams.airflowCmS,
      exp.simulationParams.oxygenPercent,
      exp.fuel,
      exp.reportedOutcome,
      exp.experimentId,
    ],
  }));

  const phaseDiagramOption = {
    backgroundColor: "transparent",
    tooltip: {
      trigger: "item",
      backgroundColor: NASA_PALETTE.deepBlue.hex,
      borderColor: NASA_PALETTE.electricBlue.hex,
      textStyle: { color: NASA_PALETTE.white.hex, fontSize: 12 },
      formatter: (p) => {
        if (p.seriesName === "NASA PSI Deneyleri") {
          const [flow, o2, fuel, outcome] = p.value;
          return [
            `<strong>${p.name}</strong>`,
            `Materyal: <b>${fuel}</b>`,
            `Koşul: <b>${flow} cm/s</b> | <b>%${o2} O₂</b>`,
            `Sonuç: <b>${outcome}</b>`,
            `<span style="color:${NASA_PALETTE.neonYellow.hex}">Simülasyona yüklemek için tıklayın</span>`,
          ].join("<br/>");
        }
        return `<strong>${p.seriesName}</strong><br/>Akış: <b>${p.value[0]} cm/s</b> | O₂: <b>%${p.value[1]}</b>`;
      },
    },
    legend: {
      top: 0,
      right: 8,
      textStyle: {
        color: NASA_PALETTE.deepBlue.hex,
        fontSize: 11.5,
        fontWeight: 600,
      },
    },
    grid: {
      left: 46,
      right: 22,
      top: 36,
      bottom: 34,
    },
    xAxis: {
      type: "value",
      name: "Akış Hızı (cm/s)",
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
      axisLabel: { color: NASA_PALETTE.deepBlue.hex, fontFamily: "monospace" },
      splitLine: { lineStyle: { color: "#E2E8F0", type: "dashed" } },
    },
    yAxis: {
      type: "value",
      name: "O₂ (% vol)",
      min: 12,
      max: 38,
      nameTextStyle: {
        color: NASA_PALETTE.deepBlue.hex,
        fontWeight: 600,
        fontSize: 11,
      },
      axisLabel: {
        formatter: "%{value}",
        color: NASA_PALETTE.deepBlue.hex,
        fontFamily: "monospace",
      },
      splitLine: { lineStyle: { color: "#E2E8F0", type: "dashed" } },
    },
    series: [
      {
        name: "NASA PSI Deneyleri",
        type: "scatter",
        symbolSize: 10,
        data: psiScatterData,
        itemStyle: {
          color: NASA_PALETTE.electricBlue.hex,
          borderColor: NASA_PALETTE.white.hex,
          borderWidth: 1.5,
        },
        markArea: {
          silent: true,
          data: [
            [
              {
                name: "Sönme (Quenching) Zarfı",
                yAxis: 12,
                itemStyle: { color: "rgba(46, 150, 245, 0.10)" },
                label: {
                  color: NASA_PALETTE.electricBlue.hex,
                  fontSize: 10,
                  position: "insideBottomRight",
                },
              },
              { yAxis: 17.5 },
            ],
            [
              {
                name: "Hiperoksik Kritik Bölge",
                yAxis: 25,
                itemStyle: { color: "rgba(228, 55, 0, 0.09)" },
                label: {
                  color: NASA_PALETTE.martianRed.hex,
                  fontSize: 10,
                  position: "insideTopRight",
                },
              },
              { yAxis: 38 },
            ],
          ],
        },
      },
      {
        name: "Aktif Telemetri Noktası",
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
        name: "AI Güvenli Hedef",
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
    "Mevcut Yangın İhtimali",
    ...recommendations.slice(0, 3).map((r) => r.category),
    "Tüm AI Önerileri Sonrası",
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
      axisPointer: { type: "shadow" },
      backgroundColor: NASA_PALETTE.deepBlue.hex,
      textStyle: { color: NASA_PALETTE.white.hex, fontSize: 12 },
      formatter: (items) => {
        const it = items[0];
        return `<strong>${it.name}</strong><br/>Yangın İhtimali: <b>%${it.value}</b>`;
      },
    },
    grid: {
      left: 165,
      right: 36,
      top: 18,
      bottom: 28,
    },
    xAxis: {
      type: "value",
      min: 0,
      max: 100,
      axisLabel: {
        formatter: "%{value}",
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
      },
    },
    series: [
      {
        name: "Yangın İhtimali (%)",
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
          formatter: "%{c}",
          color: NASA_PALETTE.deepBlue.hex,
          fontWeight: 700,
          fontFamily: "monospace",
        },
      },
    ],
  };

  const handleScatterClick = (chartEvent) => {
    if (chartEvent?.seriesName === "NASA PSI Deneyleri") {
      const expId = chartEvent.value?.[4];
      const found = EXPERIMENTS_DATA.find((e) => e.experimentId === expId);
      if (found && onSelectPsiPoint) {
        onSelectPsiPoint(found);
      }
    }
  };

  return (
    <div className="charts-grid-2col">
      {/* CHART 1: ECHARTS TIME-SERIES TELEMETRY & AI RISK TRAJECTORY */}
      <div className="chart-panel">
        <div className="chart-panel-header">
          <div>
            <span className="section-eyebrow">
              ECHARTS // ZAMAN SERİSİ TELEMETRİ PROJEKSİYONU
            </span>
            <h4>Müdahalesiz Seyir vs. AI Önlemleri Sonrası Yangın İhtimali</h4>
          </div>
          <span className="chart-badge-pill">
            Hedef Kazanç: -%{mitigationPlan.totalReductionDelta}
          </span>
        </div>

        <EChartContainer option={timelineOption} height={275} />
      </div>

      {/* CHART 2: ECHARTS PHASE DIAGRAM OR MITIGATION WATERFALL */}
      <div className="chart-panel">
        <div className="chart-panel-header">
          <div>
            <span className="section-eyebrow">
              ECHARTS // YANICILIK ZARFI & ÖNLEM ETKİ ANALİZİ
            </span>
            <h4>
              {rightChartMode === "phase"
                ? "NASA PSI Yanıcılık Faz Haritası (O₂ % vs. Hava Akışı)"
                : "AI Önlemlerinin Kademeli Risk Düşürme Etkisi"}
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
              Faz Haritası
            </button>
            <button
              type="button"
              className={`nasa-btn nasa-btn-xs ${
                rightChartMode === "factors" ? "active" : ""
              }`}
              onClick={() => setRightChartMode("factors")}
            >
              Önlem Etkisi
            </button>
          </div>
        </div>

        {rightChartMode === "phase" ? (
          <EChartContainer
            option={phaseDiagramOption}
            onPointClick={handleScatterClick}
            height={275}
          />
        ) : (
          <EChartContainer option={mitigationBarOption} height={275} />
        )}
      </div>
    </div>
  );
}
