export function measurementText(m) {
  const unit = m.unit ? ` ${m.unit}` : "";
  if (m.qualityStatus === "MISSING") return `Eksik (${m.missingReason || "MISSING"})`;
  if (m.qualityStatus !== "VERIFIED") return "Birim/değer incelemesi gerekiyor";
  if (m.qualifier === "CHANGING" && m.startValue != null && m.endValue != null) {
    return `${m.startValue} → ${m.endValue}${unit}`;
  }
  if (m.qualifier === "RANGE" && m.minValue != null && m.maxValue != null) {
    return `${m.minValue} – ${m.maxValue}${unit}`;
  }
  const prefix = { APPROXIMATE: "~", GREATER_THAN: ">", LESS_THAN: "<" }[m.qualifier] || "";
  return m.value != null ? `${prefix}${m.value}${unit}` : "Normalize değer yok";
}

export function experimentDate({ date, dateRaw }) {
  if (date) return date;
  const raw = dateRaw?.trim();
  if (!raw) return "Kaynakta belirtilmemiş";
  return /\b\d{4}\b/.test(raw) ? `${raw} (kaynak tarih biçimi)` : `${raw} (yıl kaynakta yok)`;
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
