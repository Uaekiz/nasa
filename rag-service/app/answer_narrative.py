"""Compose English sentences from original cells, never from free model prose.

Each sentence carries its source citation. Labels/units are explicit header
mappings; unknown terms remain source entries rather than invented definitions.
"""
import re

from .source_catalog import PROFILES
from .rag_config import RagError

MISSING = {"", "none", "n/a", "na", "-", "–", "—"}
FIELD_LABELS = {
    "burn time; s": ("burn time", "s"),
    "burning rate; mm": ("burning rate", ""),
    "ambient pressure; mmhg": ("ambient pressure", "mmHg"),
    "droplet initial diameter; mm": ("initial droplet diameter", "mm"),
    "visible flame extinction diameter; mm": ("visible flame extinction diameter", "mm"),
    "calibrated initial o2 % by vol": ("calibrated initial O2 reading", "% by vol"),
    "calibrated final o2 % by vol": ("calibrated final O2 reading", "% by vol"),
    "initial co2 % by vol": ("initial CO2 reading", "% by vol"),
    "final co2 % by vol": ("final CO2 reading", "% by vol"),
    "initial co (ppm)": ("initial CO reading", "ppm"),
    "final co (ppm)": ("final CO reading", "ppm"),
    "inlet velocity (cm/s)": ("inlet velocity", "cm/s"),
    "rt/r0": ("Rt/R0 value", ""),
    "duration (sec)": ("duration", "sec"),
    "primary aging time (sec)": ("primary aging time", "sec"),
    "primary mixing time (sec)": ("primary mixing time", "sec"),
    "net aging time (sec)": ("net aging time", "sec"),
    "sample thickness": ("sample thickness", ""),
    "sample length": ("sample length", ""),
    "sample width": ("sample width", ""),
    "air flow": ("air flow", ""),
    "total frames shot": ("total frames shot", "frames"),
}


def normalized(header):
    return " ".join(header.casefold().split())


def missing(value):
    return value.strip().casefold() in MISSING


def measured_text(value, unit):
    # This only appends a unit explicitly present in the source heading.
    # No parsing, arithmetic, qualifier reduction or unit conversion happens here.
    return value + (f" {unit}" if unit else "")


def label(record):
    name = PROFILES[record["investigationId"]]["name"]
    entity = "sample" if record["investigationId"] == "PSI-100" else "test"
    result = f"{name} {entity} {record['sourceTestId']}"
    if record["investigationId"] == "PSI-69":
        result += f" (FLEX Identifier {record['fields']['FLEX Identifier']})"
    if record.get("sheetName"):
        result += f" in the workbook’s {record['sheetName']} worksheet, row {record['rowNumber']}"
    return result


def source_sentences(record, headers, citation):
    fields = record["fields"]
    if any(header not in fields for header in headers):
        raise RagError("INVALID_EVIDENCE", "A narrative field is absent from its cited source.")
    selected = {normalized(h): h for h in headers}
    used = set()
    sentences = []

    def add(text, *keys):
        sentences.append(f"{text} [{citation}]")
        used.update(keys)

    material_key = next((h for h in headers if normalized(h) in {"fuel", "fuel sample material", "material", "sample type"}), None)
    if material_key and not missing(fields[material_key]):
        value = fields[material_key]
        if normalized(material_key) == "fuel":
            add(f"{label(record)} used {value}.", material_key)
        else:
            kind = "sample type" if normalized(material_key) == "sample type" else "material"
            add(f"{label(record)} lists the {kind} as “{value}”.", material_key)
    else:
        add(f"The source entry is {label(record)}.")

    # Group related source fields without computing a result or interpreting an outcome.
    end, burn = selected.get("test end"), selected.get("burn time; s")
    if end and burn and not missing(fields[end]) and not missing(fields[burn]):
        add(f"The recorded outcome was {fields[end]}, and the reported burn time was {measured_text(fields[burn], 's')}.", end, burn)
    dims = [selected.get(h) for h in ("sample thickness", "sample length", "sample width")]
    if all(dims) and all(not missing(fields[h]) for h in dims):
        add(f"The sample is listed as {fields[dims[0]]} thick, {fields[dims[1]]} long and {fields[dims[2]]} wide.", *dims)
    speed, direction = selected.get("air flow"), selected.get("direction")
    if speed and direction and not missing(fields[speed]) and not missing(fields[direction]):
        add(f"The table records an air flow of {fields[speed]} and labels the direction “{fields[direction]}”.", speed, direction)
    inlet, aging = selected.get("inlet velocity (cm/s)"), selected.get("net aging time (sec)")
    if inlet and aging and not missing(fields[inlet]) and not missing(fields[aging]):
        add(f"The recorded inlet velocity was {measured_text(fields[inlet], 'cm/s')}, with a net aging time of {measured_text(fields[aging], 'sec')}.", inlet, aging)

    for header in headers:
        if header in used:
            continue
        value, key = fields[header], normalized(header)
        noun, unit = FIELD_LABELS.get(key, (header.strip(), ""))
        if missing(value):
            if value:
                add(f"The source marks the {noun} entry as “{value}”; it does not provide a usable value for that field.", header)
            else:
                add(f"The source does not give a {noun} value for this entry; the cell is blank.", header)
        elif key == "burning rate; mm":
            add(f"The “Burning rate; mm” column records {value}; its rate unit is ambiguous, so the value is left uninterpreted.", header)
        elif key == "test end":
            add(f"The recorded outcome was {value}.", header)
        elif key in {"date", "test date"}:
            year_note = "; no year is given in the source" if re.fullmatch(r"\d{1,2}-[A-Za-z]{3}", value.strip()) else ""
            add(f"The date is recorded as {value}{year_note}.", header)
        elif key == "description":
            add(f"The source description reads “{value}”.", header)
        elif key in {"fan display", "air display"}:
            add(f"The {noun} is recorded as “{value}”; no physical airflow speed is inferred from this display entry.", header)
        elif key in FIELD_LABELS:
            add(f"The {noun} was recorded as {measured_text(value, unit)}.", header)
        elif "initial ambient composition; mole fraction" in key:
            species = header.split()[0]
            add(f"The initial ambient {species} mole fraction was recorded as {value}.", header)
        elif key == "flex identifier" and record["investigationId"] == "PSI-69":
            # It is already included verbatim in the cited entry label.
            used.add(header)
        else:
            add(f"The source records “{header.strip()}” as “{value}”.", header)
    if record["investigationId"] == "PSI-100":
        add("This source lists sample conditions, but does not provide burn time, burning rate or a measured outcome.")
    if set(headers) - used:
        raise RagError("INVALID_EVIDENCE", "Not every authorized field was rendered.")
    return sentences


def render_source_answer(records, required_fields):
    paragraphs, warnings = [], []
    has_missing = has_ambiguous = False
    for index, record in enumerate(records, 1):
        headers = required_fields[f"S{index}"] if isinstance(required_fields, dict) else required_fields
        paragraphs.append(" ".join(source_sentences(record, headers, f"S{index}")))
        has_missing |= any(missing(record["fields"][h]) for h in headers)
        has_ambiguous |= "Burning rate; mm" in headers
    answer = "\n\n".join(paragraphs)
    if set(re.findall(r"\[(S\d+)\]", answer)) != {f"S{i}" for i in range(1, len(records) + 1)}:
        raise RagError("INVALID_EVIDENCE", "Narrative citations do not match the original records.")
    if has_missing:
        warnings.append({"code": "SOURCE_MISSING_VALUE", "message": "Missing source fields are described explicitly; no missing measurement was inferred."})
    if has_ambiguous:
        warnings.append({"code": "AMBIGUOUS_SOURCE_UNIT", "message": "The unit in 'Burning rate; mm' remains ambiguous and was not reinterpreted."})
    if any(r["investigationId"] == "PSI-100" for r in records):
        warnings.append({"code": "CONDITIONS_ONLY_SOURCE", "message": "The SAFFIRE-III source provides sample conditions, not measured burning behaviour."})
    if any(r["sourceType"] == "XLSX" for r in records):
        warnings.append({"code": "INDEPENDENT_WORKBOOK_SOURCE", "message": "Workbook entries retain their own worksheet/row citations and do not replace CSV values."})
    return answer, warnings
