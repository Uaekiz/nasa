// A read-only view of one ExperimentDetail. No simulation state or risk model.
export function experimentViewModel(detail) {
  const sources = new Set((detail.sources || []).map((source) => source.sourceId));
  const conditions = detail.conditions || [];
  const findings = detail.reportedFindings || [];
  const parameters = [], missing = [];
  const trusted = (field) => field && sources.has(field.sourceId);
  const exact = (name, unit, allowZero = false) => conditions.find((field) => field.name === name && trusted(field)
    && field.qualityStatus === "VERIFIED" && field.qualifier === "EXACT"
    && field.unit === unit && Number.isFinite(field.value) && (allowZero ? field.value >= 0 : field.value > 0));
  const add = (field, label = field.name) => parameters.push({
    label, value: field.value, unit: field.unit || "", rawValue: field.rawValue, sourceId: field.sourceId,
  });
  const material = findings.find((field) => trusted(field) && ["Fuel Sample Material", "Material", "Sample Type"].includes(field.name));
  if (material) add(material);
  const model = { kind: "unknown", dimensions: null, diameter: null, width: null, flow: null, parameters, missing,
    geometryNote: "Kaynakta numune geometrisi ve boyutları tanımlanmıyor. İşaret yalnızca numune konumunu temsil eder; ölçekli değildir." };

  if (detail.investigationId === "PSI-69") {
    model.kind = "droplet";
    const diameter = exact("Droplet initial diameter", "mm");
    if (diameter) { model.diameter = diameter.value; add(diameter); }
    else missing.push("Doğrulanmış kesin başlangıç damlacık çapı");
    model.geometryNote = diameter
      ? "Küre, kaynakta verilen başlangıç damlacık çapını gösterir; gerçek damlacık şekli veya alev geometrisi ölçümü değildir."
      : "Damlacık simgesi ölçekli değildir; eksik çap yerine varsayılan deney değeri kullanılmadı.";
  } else {
    const length = exact("Sample length", "mm"), width = exact("Sample width", "mm"), thickness = exact("Sample thickness", "mm");
    [length, width, thickness].filter(Boolean).forEach((field) => add(field));
    if (length && width && thickness) {
      model.kind = "box";
      model.dimensions = [length.value, thickness.value, width.value];
      model.geometryNote = "Boyut zarfı, kaynaktaki uzunluk × kalınlık × genişlik oranlarını korur. Doku ve yanma davranışı modellenmez.";
    } else if (detail.investigationId === "PSI-25" && material) {
      // Only explicitly labelled, exact widths/thicknesses in the CSV description
      // are interpreted. Unlabelled inch fractions are never assumed diameters.
      const text = material.rawValue || "";
      const dimension = (word) => {
        const match = text.match(new RegExp(`(^|[\\s,])(\\d+(?:\\.\\d+)?)\\s*(mm|cm|micron)\\s+${word}\\b`, "i"));
        if (!match || /[~<>]|approx|about|\d\s*[-–]\s*\d/i.test(text)) return null;
        return { value: Number(match[2]) * { mm: 1, cm: 10, micron: 0.001 }[match[3].toLowerCase()], raw: match[0].trim() };
      };
      const w = dimension("wide"), t = dimension("thick");
      if (w) {
        model.kind = t ? "cross-section" : "width";
        model.width = w.value;
        model.dimensions = t ? [w.value, t.value] : null;
        model.geometryNote = t
          ? "Yalnızca açıkça yazılmış genişlik ve kalınlığın kesiti gösteriliyor. Kaynakta olmayan uzunluk veya hacim üretilmedi."
          : "Yalnızca açıkça yazılmış genişlik çizgisi gösteriliyor; diğer boyutlar tamamlanmadı.";
      } else {
        model.kind = /\brod\b/i.test(text) ? "rod" : /\bfilm\b/i.test(text) ? "film" : "solid";
        model.geometryNote = "Malzeme tanımına ait ölçekli olmayan numune simgesi. Kaynak metnindeki etiketsiz boyutlar eksen veya çap olarak yorumlanmadı.";
      }
      missing.push("Tam ve açıkça tanımlanmış numune boyutları (eksik eksenler çizilmedi)");
    } else missing.push("Doğrulanmış numune geometrisi ve tam boyutları");
  }

  const speed = exact("Air flow", "cm/s", true) || exact("Inlet velocity", "cm/s", true);
  const direction = findings.find((field) => field.name === "Direction" && trusted(field));
  if (speed) add(speed);
  else missing.push("Doğrulanmış fiziksel hava akış hızı (gösterge değeri hız değildir)");
  if (direction) add(direction);
  const sign = { concurrent: 1, opposed: -1 }[direction?.value?.trim().toLowerCase()];
  if (speed && speed.value > 0 && sign) model.flow = { speed: speed.value, unit: speed.unit, sign, direction: direction.value.trim() };
  else if (speed?.value === 0) missing.push("Kaynakta akış hızı sıfır; hareketli akış oku çizilmedi");
  else missing.push("Kaynakta tanımlanmış akış yönü; yön bilinmeden akış oku çizilmedi");
  missing.push("Alevin 3B şekli, rengi, sıcaklığı ve zamana bağlı davranışı; alev animasyonu gösterilmiyor");
  if (detail.investigationId === "PSI-101") model.studyNote = "SAME-R kaydı açık alev deneyi olarak yorumlanmadı. Süre ve yaşlandırma alanlarından yanma zaman çizelgesi çıkarılmaz.";
  if (detail.investigationId === "PSI-100") model.studyNote = "SAFFIRE-III kaynağı yalnızca numune ve koşulları içerir. Yanma ölçümü veya sonuç tahmini eklenmedi.";
  return model;
}
