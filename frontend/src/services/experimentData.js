import { formatNumber } from "./format.js";

export function measurementText(m) {
  const unit = m.unit ? ` ${m.unit}` : "";
  if (m.qualityStatus === "MISSING") return `Missing (${m.missingReason || "MISSING"})`;
  if (m.qualityStatus !== "VERIFIED") return "Unit/value review required";
  if (m.qualifier === "CHANGING" && m.startValue != null && m.endValue != null) {
    return `${formatNumber(m.startValue)} → ${formatNumber(m.endValue)}${unit}`;
  }
  if (m.qualifier === "RANGE" && m.minValue != null && m.maxValue != null) {
    return `${formatNumber(m.minValue)} – ${formatNumber(m.maxValue)}${unit}`;
  }
  const prefix = { APPROXIMATE: "~", GREATER_THAN: ">", LESS_THAN: "<" }[m.qualifier] || "";
  return m.value != null ? `${prefix}${formatNumber(m.value)}${unit}` : "No normalized value";
}

export function experimentDate({ date, dateRaw }) {
  if (date) return date;
  const raw = dateRaw?.trim();
  if (!raw) return "Not reported in source";
  return /\b\d{4}\b/.test(raw) ? `${raw} (original date format)` : `${raw} (year not provided in source)`;
}

export function comparisonRows(series, experimentIds) {
  return experimentIds.map((experimentId) => ({
    experimentId,
    point: series.points.find((point) => point.experimentId === experimentId),
  }));
}

export function loadedChatScopes(investigations = [], capabilities) {
  if (capabilities?.status !== "READY" || capabilities.language !== "en") return [];
  return (capabilities.items || []).filter((item) =>
    Array.isArray(item.sourceIds) && item.sourceIds.length > 0
    && investigations.some((investigation) => investigation.investigationId === item.investigationId));
}
