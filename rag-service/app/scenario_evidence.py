"""Read-only comparisons of scenario inputs and reviewed independent source rows."""
import math
import re
from .rag_corpus import load_corpus
from .source_catalog import field_value, load_catalog, profile_for

SOURCE_CLASSES = {"PSI-69": "DROPLET", "PSI-25": "SOLID", "PSI-100": "SOLID", "PSI-101": "SMOKE"}
PARAMETERS = ("oxygenPercent", "pressureKpa", "airflowCmS", "gravityG", "temperatureC",
              "ignitionPowerW", "material", "flowDirection", "coPpm", "co2Percent")
NUMBER = r"[-+]?(?:\d+(?:\.\d+)?|\.\d+)"
MISSING = {"", "none", "n/a", "na", "-", "–", "—"}
SORT_PARAMETERS = {"PSI-100": ["flowDirection", "airflowCmS"], "PSI-25": ["oxygenPercent"],
                   "PSI-69": ["pressureKpa"], "PSI-101": ["airflowCmS"]}


def normalize(value):
    return " ".join(value.casefold().split())


def _header(fields, *names):
    wanted = {normalize(name) for name in names}
    return next((name for name in fields if normalize(name) in wanted), None)


def _base(parameter, params, header=None, raw=None, unit="", reason="No explicit source field with a compatible unit is available."):
    return {"parameter": parameter, "sourceField": header, "sourceValue": raw,
            "scenarioValue": params[parameter], "unit": unit, "status": "NOT_COMPARABLE",
            "difference": None, "normalizedSourceValue": None, "reason": reason}


def compare_conditions(record, params):
    if params is None:
        return []
    fields = record["fields"]
    items = {parameter: _base(parameter, params) for parameter in PARAMETERS}

    def numeric(parameter, names, unit, *, suffix="", factor=1, explanation=""):
        header = _header(fields, *names)
        if header is None:
            return
        raw = fields[header]
        item = items[parameter] = _base(parameter, params, header, raw, unit)
        if raw.strip().casefold() in MISSING:
            item["reason"] = "The source cell is blank or marked missing; it was not treated as zero."
            return
        pattern = NUMBER + (r"\s*" + re.escape(suffix) if suffix else "")
        if re.fullmatch(pattern, raw.strip(), re.I) is None:
            item["reason"] = "The cell is not an exact number in the expected source unit; its qualifier or text was preserved."
            return
        value = float(re.match(NUMBER, raw.strip()).group()) * factor
        if factor != 1:
            value = round(value, 6)  # Match the existing importer conversion precision.
        if (not math.isfinite(value) or (parameter == "pressureKpa" and value <= 0)
                or (parameter == "temperatureC" and value < -273.15)
                or (parameter not in {"pressureKpa", "temperatureC"} and value < 0)
                or (parameter in {"oxygenPercent", "co2Percent"} and value > 100)):
            item["reason"] = "The reported value is outside the comparable quantity range; the raw cell is retained."
            return
        item.update(normalizedSourceValue=value, difference=round(params[parameter] - value, 6),
                    status="COMPARED", reason=explanation or "Exact source value; difference is scenario minus source.")

    # A unit-labelled column is required. These mappings never create absent columns.
    numeric("pressureKpa", ("Ambient pressure; mmHg",), "kPa", factor=0.133322,
            explanation="Source mmHg × 0.133322 = kPa uses the existing importer conversion. Difference is scenario minus source.")
    numeric("pressureKpa", ("Pressure (kPa)", "Ambient pressure (kPa)", "Pressure; kPa"), "kPa")
    numeric("gravityG", ("Gravity (g)", "Gravity; g", "Gravitational acceleration (g)"), "g")
    numeric("temperatureC", ("Temperature (°C)", "Temperature; °C", "Temperature (C)"), "°C")
    numeric("ignitionPowerW", ("Ignition power (W)", "Ignition power; W"), "W")

    if record["investigationId"] == "PSI-100":
        numeric("airflowCmS", ("Air Flow ",), "cm/s", suffix="cm/s")
        header = _header(fields, "Direction")
        if header is not None:
            raw = fields[header]
            direction = raw.strip().upper()
            items["flowDirection"] = _base("flowDirection", params, header, raw)
            if direction in {"CONCURRENT", "OPPOSED"}:
                items["flowDirection"].update(status="MATCH" if direction == params["flowDirection"] else "DIFFERENT",
                    normalizedSourceValue=direction,
                    reason="Compared with the relative flow-direction label; no flame direction was inferred.")
    elif record["investigationId"] == "PSI-25":
        numeric("oxygenPercent", ("Calibrated  initial O2 % by vol ",), "percentage points",
                explanation="Scenario oxygen is compared with calibrated initial O2 % by volume. Difference is in percentage points.")
        items["airflowCmS"]["reason"] = "Fan display and Air display are instrument settings without physical speed units; no cm/s conversion was inferred."
        for parameter, phase_key, label, source_unit, output_unit in (
            ("coPpm", "coMeasurementPhase", "CO", "(ppm)", "ppm"),
            ("co2Percent", "co2MeasurementPhase", "CO2", "% by vol", "percentage points"),
        ):
            phase = params.get(phase_key, "UNSPECIFIED")
            if phase == "UNSPECIFIED":
                items[parameter]["reason"] = "Choose INITIAL or FINAL explicitly; the source has distinct initial and final gas readings and no phase was assumed."
                items[parameter]["availableSourceFields"] = [h for h in fields if normalize(h) in {
                    normalize(f"Initial {label} {source_unit}"), normalize(f"Final {label} {source_unit}")}]
            else:
                numeric(parameter, (f"{phase.title()} {label} {source_unit}",), output_unit,
                    explanation=f"Compared with the explicitly selected {phase.lower()} {label} measurement. Difference is scenario minus source.")
    elif record["investigationId"] == "PSI-101":
        numeric("airflowCmS", ("Inlet velocity (cm/s)",), "cm/s",
                explanation="Compared with the smoke/aging source's inlet velocity; this is not open-flame evidence.")
    elif record["investigationId"] == "PSI-69":
        items["oxygenPercent"]["reason"] = "The source labels an O mole fraction, not O2 % by volume. No unspecified composition-basis conversion was inferred."
        items["coPpm"]["reason"] = "The source labels a CO mole fraction rather than ppm; no unspecified concentration-basis conversion was inferred."

    header = profile_for(record)["fuel"]
    raw = fields.get(header, "")
    items["material"] = _base("material", params, header, raw,
        reason="Material-name selection does not establish specimen geometry, composition or experimental equivalence.")
    if normalize(raw) == normalize(params["material"]):
        items["material"].update(status="MATCH", normalizedSourceValue=raw,
                                 reason="Recorded material names match; specimen equivalence is not established.")
    return list(items.values())


def material_matches(record, requested):
    original = normalize(field_value(record, "fuel"))
    if requested == original:
        return True
    families = {"sibal fabric": r"\bsibal\b", "pmma film": r"(?=.*\bpmma\b)(?=.*\bfilm\b)",
                "nomex iii": r"\bnomex\s+iii\b"}
    return requested in families and bool(re.search(families[requested], original))


def _experiment_key(record):
    investigator = ""
    if record["investigationId"] == "PSI-25":
        investigator = normalize(record.get("sheetName") or record["fields"].get("PI", ""))
    return record["investigationId"], record["sourceTestId"].strip().casefold(), investigator


def _provenance(record):
    return record["sourceId"], record.get("sheetName", ""), record["rowNumber"]


def condition_order(record, params):
    comparisons = {item["parameter"]: item for item in compare_conditions(record, params)}
    order = []
    for parameter in SORT_PARAMETERS[record["investigationId"]]:
        item = comparisons.get(parameter, {})
        if parameter == "flowDirection":
            order.append({"MATCH": 0, "DIFFERENT": 1}.get(item.get("status"), 2))
        else:
            compared = item.get("status") == "COMPARED"
            order.extend((not compared, abs(item["difference"]) if compared else float("inf")))
    return tuple(order) + (_provenance(record),)


def _canonical_header(header):
    name = " ".join(re.sub(r"[,#().]", " ", normalize(header)).split())
    if name in {"fuel sample material", "material"}: return "material"
    if name in {"test", "test no"}: return "test identifier"
    if name in {"sample", "sample no"}: return "sample identifier"
    if name == "date" or name.startswith("actual date "): return "date (original storage)"
    return name


def record_differences(primary, alternate, citation):
    first = {_canonical_header(h): (h, v) for h, v in primary["fields"].items()}
    second = {_canonical_header(h): (h, v) for h, v in alternate["fields"].items()}
    differences = []
    for key in sorted(first.keys() | second.keys()):
        a, b = first.get(key, (None, None)), second.get(key, (None, None))
        if a[1] != b[1]:
            differences.append({"field": key, "primaryField": a[0], "alternateField": b[0],
                "primaryValue": a[1], "alternateValue": b[1], "alternateCitationId": citation})
    return differences


def parameter_coverage(sources, params):
    if params is None:
        return []
    versions = [version for source in sources for version in (source, *source["alternateRecords"])]
    coverage = []
    for parameter in PARAMETERS:
        items = [(source, next(c for c in source["comparisons"] if c["parameter"] == parameter)) for source in versions]
        usable = [(source, item) for source, item in items if item["status"] in {"COMPARED", "MATCH", "DIFFERENT"}]
        phase_key = {"coPpm": "coMeasurementPhase", "co2Percent": "co2MeasurementPhase"}.get(parameter)
        if not versions:
            status, reason = "NO_SOURCE", "No matching reviewed source record was selected."
        elif phase_key and params.get(phase_key, "UNSPECIFIED") == "UNSPECIFIED":
            status, reason = "PHASE_UNSPECIFIED", "Select INITIAL or FINAL to define the gas reading; no phase is assumed."
        elif usable:
            status = "COMPARED" if len(usable) == len(items) else "PARTIAL"
            reason = "Only explicit source fields and compatible units were compared; other records retain their own limitations."
        else:
            status, reason = "NOT_COMPARABLE", items[0][1]["reason"]
        coverage.append({"parameter": parameter, "scenarioValue": params[parameter], "status": status, "reason": reason,
            "sourceIds": sorted({s["sourceId"] for s, c in items if c["sourceField"] is not None}),
            "comparedSourceIds": sorted({s["sourceId"] for s, _ in usable})})
    return coverage


def find_scenario_evidence(material, params=None):
    corpus = load_corpus(mode="multi")
    requested = normalize(material)
    matches = [r for r in corpus.records if material_matches(r, requested)]
    keys = {_experiment_key(record) for record in matches}
    experiments = {}
    # Keep independently recorded versions even when their material wording differs.
    for record in corpus.records:
        if _experiment_key(record) in keys:
            experiments.setdefault(_experiment_key(record), []).append(record)
    groups = {}
    for records in experiments.values():
        records.sort(key=lambda r: (r["sourceType"] != "CSV", _provenance(r)))
        groups.setdefault(records[0]["investigationId"], []).append((records[0], records[1:]))
    for group in groups.values():
        group.sort(key=lambda item: condition_order(item[0], params))
    selected = []
    while len(selected) < 5:
        added = False
        for inv in sorted(groups):
            if groups[inv] and len(selected) < 5:
                selected.append(groups[inv].pop(0))
                added = True
        if not added: break
    catalog = {s["sourceId"]: s for s in load_catalog()["sources"]}

    def source_view(record, citation):
        metadata = catalog[record["sourceId"]]
        return {**{k: record.get(k) for k in ("investigationId", "sourceId", "sourceTestId", "sourceType", "sourceFile", "sheetName", "rowNumber", "fields")},
            "citationId": citation, "sourceClass": SOURCE_CLASSES[record["investigationId"]],
            "comparisons": compare_conditions(record, params), "title": metadata["title"],
            "documentUrl": metadata.get("documentUrl"), "originalUrl": metadata["provenance"].get("investigationUrl"),
            "doi": metadata.get("doi"), "materialNameMatched": material_matches(record, requested)}
    sources = []
    for index, (primary, alternatives) in enumerate(selected, 1):
        source = source_view(primary, f"S{index}")
        source["alternateRecords"] = [source_view(r, f"S{index}A{a}") for a, r in enumerate(alternatives, 1)]
        source["recordDifferences"] = [d for a, r in enumerate(alternatives, 1)
                                     for d in record_differences(primary, r, f"S{index}A{a}")]
        sources.append(source)
    return {"status": "EVIDENCE_FOUND" if sources else "INSUFFICIENT_EVIDENCE", "material": material,
        "selectionMethod": "WITHIN_INVESTIGATION_CONDITION_MATCH" if params is not None else "MATERIAL_NAME_MATCH",
        "matchedRecordCount": len(matches), "matchedExperimentCount": len(experiments), "returnedRecordCount": len(sources),
        "returnedSourceVersionCount": sum(1 + len(s["alternateRecords"]) for s in sources),
        "sources": sources, "parameterCoverage": parameter_coverage(sources, params), "scenarioInputs": params,
        "selectionDetails": [{"investigationId": inv, "sourceClass": SOURCE_CLASSES[inv], "sortParameters": SORT_PARAMETERS[inv],
            "method": "Material-name candidates, then the listed condition fields within this investigation; provenance breaks ties."}
            for inv in sorted({s["investigationId"] for s in sources})],
        "limitations": ["Material-name matching is not specimen equivalence.",
            "Solid-specimen, droplet and smoke/aging records remain separate evidence classes; none establishes another class's behaviour.",
            "Records are ordered within each investigation using only its listed condition fields; no cross-investigation similarity or confidence score is calculated.",
            "CSV and workbook versions are independent; raw cells, unavailable columns and disagreements are shown separately.",
            "No measured or predicted fire probability, flame behaviour or safe operating range is derived from these comparisons.",
            "The screenshot is a local representative preview. It is not sent to or inspected by a vision model."]}
