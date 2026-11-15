"""Read hash-pinned original CSV/XLSX sources without normalizing their cells.

This module uses only the standard library so the backend importer can reuse it.
"""
import csv
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import re
import zipfile
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
CATALOG_PATH = ROOT / "rag-service/source_catalog.json"
EXAMPLE_QUESTIONS = {
    "PSI-69": ["Summarize FLEX test 70.", "Show both records for identifier 193F001."],
    "PSI-25": ["Show BASS-II test B1.", "Show BASS-II workbook test B1."],
    "PSI-100": ["Show SAFFIRE-III sample S1."],
    "PSI-101": ["Show SAME-R test 51a."],
}
NS = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}

PROFILES = {
    "PSI-69": {"name": "FLEX", "aliases": ["FLEX", "PSI-69"], "fuel": "Fuel",
        "identifier": "FLEX Identifier", "outcome": "Test end",
        "summary": ["Fuel", "Test end", "Burn time; s", "Burning rate; mm"],
        "fields": {"Fuel": r"\bfuels?\b", "Test end": r"\b(outcomes?|results?|test end|extinction|extinguish\w*|disruption|completion)\b",
            "Test Date": r"\b(dates?|when)\b", "Test GMT": r"\bgmt\b",
            "Ambient pressure; mmHg": r"\b(?:ambient )?pressure\b",
            "Droplet initial diameter; mm": r"\b(?:droplet )?initial diameter\b",
            "Visible flame extinction diameter; mm": r"\b(?:visible )?(?:flame )?extinction diameter\b",
            "Burning rate; mm": r"\b(?:burning|burn) rate\b", "Burn time; s": r"\b(?:burn|burning) (?:time|duration)\b",
            "FLEX Identifier": r"\b(?:flex )?identifiers?\b", "FLEX Test #": r"\btest (?:id|number|no\.?)\b"}},
    "PSI-25": {"name": "BASS-II", "aliases": ["BASS-II", "BASS II", "PSI-25"], "fuel": "Fuel Sample Material",
        "identifier": "Test #", "outcome": None,
        "summary": ["Fuel Sample Material", "Calibrated  initial O2 % by vol ", "Final CO (ppm)"],
        "fields": {"Fuel Sample Material": r"\b(?:fuel|material|sample material)\b", "PI": r"\b(?:pi|investigator)\b",
            "Date": r"\b(?:date|when)\b", "GMT": r"\bgmt\b", "Fan display": r"\bfan display\b",
            "Air display": r"\bair display\b", "Flow restrictor": r"\bflow restrictor\b",
            "Calibrated  initial O2 % by vol ": r"\binitial (?:oxygen|o2)\b",
            "Calibrated final O2 % by vol": r"\bfinal (?:oxygen|o2)\b",
            "Initial CO (ppm)": r"\binitial co\b", "Final CO (ppm)": r"\bfinal co\b"}},
    "PSI-100": {"name": "SAFFIRE-III", "aliases": ["SAFFIRE-III", "SAFFIRE III", "SAFFIRE-3", "PSI-100"], "fuel": "Material",
        "identifier": "Sample Number ", "outcome": None,
        "summary": ["Material", "Sample Thickness", "Sample Length", "Sample Width", "Air Flow ", "Direction"],
        "fields": {"Material": r"\b(?:fuel|material)\b", "Sample Thickness": r"\b(?:sample )?thickness\b",
            "Sample Length": r"\b(?:sample )?length\b", "Sample Width": r"\b(?:sample )?width\b",
            "Air Flow ": r"\b(?:air flow|airflow)\b", "Direction": r"\b(?:flow )?direction\b"}},
    "PSI-101": {"name": "SAME-R", "aliases": ["SAME-R", "SAME R", "PSI-101"], "fuel": "Sample Type",
        "identifier": "SAME Test #", "outcome": None,
        "summary": ["Sample Type", "Description", "Inlet velocity (cm/s)", "Net aging time (sec)"],
        "fields": {"Sample Type": r"\b(?:material|sample type|fuel)\b", "Description": r"\bdescription\b",
            "Date": r"\b(?:date|when)\b", "Inlet velocity (cm/s)": r"\binlet velocity\b",
            "Rt/R0": r"\brt/r0\b", "Duration (sec)": r"\bduration\b",
            "Primary aging time (sec)": r"\bprimary aging time\b", "Primary mixing time (sec)": r"\bprimary mixing time\b",
            "Net aging time (sec)": r"\bnet aging time\b"}},
}


def profile_for(record):
    profile = PROFILES[record["investigationId"]]
    if record["sourceType"] != "XLSX":
        return profile
    return {**profile, "fuel": "Material", "identifier": "Test no.",
        "summary": ["Material", "calibrated  initial O2 % by vol ", "Final CO (ppm)"],
        "fields": {**profile["fields"], "Material": r"\b(?:fuel|material|sample material)\b",
            "calibrated  initial O2 % by vol ": r"\binitial (?:oxygen|o2)\b",
            "calibrated final O2 % by vol": r"\bfinal (?:oxygen|o2)\b"}}


def field_value(record, field):
    header = profile_for(record).get(field)
    return record["fields"].get(header, "") if header else ""


def load_catalog(path=CATALOG_PATH):
    catalog = json.loads(Path(path).read_text(encoding="utf-8"))
    ids = [s["sourceId"] for s in catalog["sources"]]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate catalog sourceId")
    for source in catalog["sources"]:
        if source["provenance"]["status"] != "NASA_DOWNLOAD_HASH_MATCH":
            raise ValueError("Unverified sources cannot enter the published corpus")
    return catalog


def _record(source, row_number, fields, sheet=None, cells=None):
    result = {"investigationId": source["investigationId"], "sourceId": source["sourceId"],
        "sourceTestId": fields[source["sourceTestIdField"]], "sourceType": source["sourceType"],
        "sourceFile": source["sourceFile"], "rowNumber": row_number, "fields": fields}
    if sheet is not None:
        result.update(sheetName=sheet, originalCells=cells)
    lines = [f"{PROFILES[source['investigationId']]['name']} {source['sourceType']} test evidence.",
        f"Investigation: {source['investigationId']}", f"Source: {source['sourceFile']}",
        f"Source row (including the header): {row_number}"]
    if sheet is not None:
        lines.append(f"Worksheet: {sheet}; numeric cell text is original XLSX storage, not an inferred measurement/date.")
    lines += ["Original field names and JSON-quoted cell values:"]
    lines += [f"{h}: {json.dumps(v, ensure_ascii=False)}" for h, v in fields.items()]
    result["text"] = "\n".join(lines)
    return result


def read_source(source, *, root=ROOT):
    path = (root / source["sourceFile"]).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("Source path must stay inside the repository")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != source["sha256"]:
        raise ValueError(f"Source hash changed: {source['sourceId']}; review source version before import")
    if source["sourceId"] == "PSI-69:experimental-table:v1":
        spec = importlib.util.spec_from_file_location("original_flex_csv", ROOT / "rag-service/app/csv_loader.py")
        loader = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(loader)
        return loader.extract_records()
    records = []
    if source["sourceType"] == "CSV":
        reader = csv.reader(io.StringIO(raw.decode(source["encoding"], errors="strict"), newline=""), strict=True)
        headers = next(reader)
        if headers != source["headers"] or len(set(headers)) != len(headers):
            raise ValueError("Original CSV headers differ from the reviewed manifest")
        for number, row in enumerate(reader, 2):
            if not row or all(v == "" for v in row):
                continue
            if len(row) != len(headers):
                raise ValueError(f"Malformed CSV row {number}")
            fields = dict(zip(headers, row, strict=True))
            if not re.fullmatch(source["testIdPattern"], fields[source["sourceTestIdField"]]):
                raise ValueError(f"Unrecognized test row {number}; no experiment inferred")
            records.append(_record(source, number, fields))
    elif source["sourceType"] == "XLSX":
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            strings = ["".join(si.itertext()) for si in ET.fromstring(archive.read("xl/sharedStrings.xml"))]
            workbook = ET.fromstring(archive.read("xl/workbook.xml"))
            relationships = {r.attrib["Id"]: r.attrib["Target"] for r in ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))}
            for sheet in workbook.find("s:sheets", NS):
                name = sheet.attrib["name"]
                if name not in source["sheets"]:
                    raise ValueError("Unexpected workbook sheet")
                target = relationships[sheet.attrib["{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"]]
                rows = ET.fromstring(archive.read("xl/" + target)).find("s:sheetData", NS)
                headers = None
                for row in rows:
                    cells, by_column = {}, {}
                    for c in row:
                        address = c.attrib["r"]
                        v = c.find("s:v", NS)
                        value = v.text if v is not None else ""
                        if c.attrib.get("t") == "s": value = strings[int(value)]
                        elif c.attrib.get("t") == "inlineStr": value = "".join(c.find("s:is", NS).itertext())
                        cells[address] = {"value": value, "type": c.attrib.get("t", "n"), "style": c.attrib.get("s"),
                            "formula": c.findtext("s:f", default=None, namespaces=NS), "storedValue": v.text if v is not None else None}
                        by_column[re.sub(r"\d+", "", address)] = value
                    if int(row.attrib["r"]) == 1:
                        headers = [by_column.get(chr(65 + i), "") for i in range(16)]
                        if headers != source["sheetHeaders"][name]: raise ValueError("Workbook header drift")
                        continue
                    if not any(by_column.values()): continue
                    fields = dict(zip(headers, [by_column.get(chr(65+i), "") for i in range(16)], strict=True))
                    if not re.fullmatch(source["testIdPattern"], fields[source["sourceTestIdField"]]):
                        raise ValueError(f"Unrecognized workbook row: {name} {row.attrib['r']}")
                    records.append(_record(source, int(row.attrib["r"]), fields, name, cells))
    else:
        raise ValueError("Unsupported source type")
    if len(records) != source["expectedTestCount"]:
        raise ValueError(f"Expected {source['expectedTestCount']} rows for {source['sourceId']}, got {len(records)}")
    return records


def read_all_sources(catalog=None):
    catalog = catalog or load_catalog()
    return [record for source in catalog["sources"] for record in read_source(source)]
