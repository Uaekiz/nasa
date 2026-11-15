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
    geometryNote: "The source does not define specimen geometry or dimensions. The marker indicates a sample location only and is not to scale." };

  if (detail.investigationId === "PSI-69") {
    model.kind = "droplet";
    const diameter = exact("Droplet initial diameter", "mm");
    if (diameter) { model.diameter = diameter.value; add(diameter); }
    else missing.push("Verified exact initial droplet diameter");
    model.geometryNote = diameter
      ? "The sphere represents the reported initial droplet diameter, not a measured droplet shape or flame geometry."
      : "The droplet symbol is not to scale. No default experimental diameter replaces the missing value.";
  } else {
    const length = exact("Sample length", "mm"), width = exact("Sample width", "mm"), thickness = exact("Sample thickness", "mm");
    [length, width, thickness].filter(Boolean).forEach((field) => add(field));
    if (length && width && thickness) {
      model.kind = "box";
      model.dimensions = [length.value, thickness.value, width.value];
      model.geometryNote = "The dimensional envelope preserves the reported length × thickness × width proportions. Texture and burning behavior are not modeled.";
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
          ? "Only the explicitly labeled width and thickness cross-section is shown. No unreported length or volume is generated."
          : "Only the explicitly labeled width is drawn as a line; other dimensions are not filled in.";
      } else {
        model.kind = /\brod\b/i.test(text) ? "rod" : /\bfilm\b/i.test(text) ? "film" : "solid";
        model.geometryNote = "An unscaled symbol represents the described specimen. Unlabeled dimensions are not interpreted as an axis or diameter.";
      }
      missing.push("Complete, explicitly labeled specimen dimensions (missing axes are not drawn)");
    } else missing.push("Verified specimen geometry and complete dimensions");
  }

  const speed = exact("Air flow", "cm/s", true) || exact("Inlet velocity", "cm/s", true);
  const direction = findings.find((field) => field.name === "Direction" && trusted(field));
  if (speed) add(speed);
  else missing.push("Verified physical airflow speed (display settings are not speed measurements)");
  if (direction) add(direction);
  const sign = { concurrent: 1, opposed: -1 }[direction?.value?.trim().toLowerCase()];
  if (speed && speed.value > 0 && sign) model.flow = { speed: speed.value, unit: speed.unit, sign, direction: direction.value.trim() };
  else if (speed?.value === 0) missing.push("The source reports zero airflow; no flow arrow is drawn");
  else missing.push("A source-defined flow direction; no arrow is drawn when direction is unknown");
  missing.push("3D flame shape, color, temperature and behavior over time; no flame animation is shown");
  if (detail.investigationId === "PSI-101") model.studyNote = "The SAME-R record is not treated as an open-flame experiment. Duration and aging fields do not establish a combustion timeline.";
  if (detail.investigationId === "PSI-100") model.studyNote = "The SAFFIRE-III source provides only specimen and condition fields. No burning measurement or predicted outcome is added.";
  return model;
}
