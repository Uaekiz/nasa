#!/usr/bin/env python3
"""Pyrosphere ETL: NASA experimental CSV tables -> PostgreSQL (core schema).

Work packages 1.1 (source inventory) and 1.3 (numeric transfer).

Design rules implemented here:
  * experimentId is persistent: <investigationId>:run-0001. A new identifier is
    allocated only when a new row_fingerprint is seen. Re-running the script
    updates the existing experiment instead of inserting duplicates.
  * Every source cell keeps its original text in raw_value.
  * "11 to 3"          -> qualifier CHANGING, start_value/end_value
  * ">500", "<0.5"     -> GREATER_THAN / LESS_THAN
  * "1.5 - 5"          -> RANGE, min_value/max_value
  * "~ 21.5"           -> APPROXIMATE
  * "", "n/a", "none"  -> value null, quality_status MISSING
  * multi-value or unit-ambiguous cells -> REQUIRES_REVIEW (never coerced).
  * Unit conversions keep original_value/original_unit/conversion_method.

Run:
    python data/etl/load_experiments.py --investigation PSI-69
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import sys
from datetime import date, datetime
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb as Json

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = ROOT / "data" / "manifest.json"
SOURCE_MANIFEST = ROOT / "rag-service" / "source_manifest.json"

DB_CONFIG = {
    "host": os.getenv("PYROSPHERE_DB_HOST", "localhost"),
    "port": int(os.getenv("PYROSPHERE_DB_PORT", "5433")),
    "dbname": os.getenv("PYROSPHERE_DB_NAME", "pyrosphere"),
    "user": os.getenv("PYROSPHERE_DB_USER", "pyrosphere"),
    "password": os.getenv("PYROSPHERE_DB_PASSWORD", "pyrosphere_dev"),
}

NUMBER = r"[-+]?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][-+]?\d+)?"
CHANGING_RE = re.compile(rf"^({NUMBER})\s*(?:to|->)\s*({NUMBER})$", re.IGNORECASE)
RANGE_RE = re.compile(rf"^({NUMBER})\s*-\s*({NUMBER})$")
GREATER_RE = re.compile(rf"^>\s*({NUMBER})$")
LESS_RE = re.compile(rf"^<\s*({NUMBER})$")
APPROX_RE = re.compile(rf"^~\s*({NUMBER})$")
EXACT_RE = re.compile(rf"^({NUMBER})$")
# "0.33 cm", "30 cm/s", "420 s", "182 W" -> numeric value + source unit.
UNIT_SUFFIX_RE = re.compile(rf"^({NUMBER})\s*(cm/s|cm|mm|s|W|w|ppm|%|frames?)$", re.IGNORECASE)

MISSING_TOKENS = {"", "n/a", "na", "n.a.", "none", "null", "-", "--", "–", "—", "?", "missing"}

VERIFIED = "VERIFIED"
REQUIRES_REVIEW = "REQUIRES_REVIEW"
MISSING = "MISSING"


def clean(value) -> str:
    """Normalize a raw CSV cell without losing its scientific content."""
    if value is None:
        return ""
    text = str(value).replace("\ufeff", "").replace("\u200b", "").replace("\xa0", " ")
    return " ".join(text.split())


def normalized_header(value) -> str:
    return clean(value).lower()


def cell_is_missing(raw: str) -> bool:
    return raw.lower() in MISSING_TOKENS


def parse_cell(raw: str) -> dict:
    """Apply the qualifier rules from the API contract to one raw cell."""
    text = clean(raw)
    result = {
        "value": None,
        "qualifier": "UNKNOWN",
        "start_value": None,
        "end_value": None,
        "min_value": None,
        "max_value": None,
        "raw_value": raw,
        "missing_reason": None,
        "quality_status": VERIFIED,
    }

    if cell_is_missing(text):
        result["quality_status"] = MISSING
        result["missing_reason"] = "EMPTY_CELL" if text == "" else "SOURCE_MARKED_MISSING"
        result["qualifier"] = "UNKNOWN"
        return result

    match = CHANGING_RE.match(text)
    if match:
        result.update(
            qualifier="CHANGING",
            start_value=float(match.group(1)),
            end_value=float(match.group(2)),
        )
        return result

    match = RANGE_RE.match(text)
    if match:
        low, high = float(match.group(1)), float(match.group(2))
        result.update(qualifier="RANGE", min_value=min(low, high), max_value=max(low, high))
        return result

    match = GREATER_RE.match(text)
    if match:
        result.update(qualifier="GREATER_THAN", value=float(match.group(1)))
        return result

    match = LESS_RE.match(text)
    if match:
        result.update(qualifier="LESS_THAN", value=float(match.group(1)))
        return result

    match = APPROX_RE.match(text)
    if match:
        result.update(qualifier="APPROXIMATE", value=float(match.group(1)))
        return result

    match = EXACT_RE.match(text)
    if match:
        result.update(qualifier="EXACT", value=float(match.group(1)))
        return result

    match = UNIT_SUFFIX_RE.match(text)
    if match:
        result.update(qualifier="EXACT", value=float(match.group(1)), source_unit_text=match.group(2))
        return result

    # Qualitative or multi-value cell: keep it, but never invent a number.
    result["quality_status"] = REQUIRES_REVIEW
    result["qualifier"] = "UNKNOWN"
    return result


def convert_measurement(parsed: dict, transform: str | None) -> dict:
    """Apply a documented unit conversion while preserving the original value."""
    if transform not in ("mmHg_to_kPa", "cm_to_mm"):
        return parsed

    def convert_one(number):
        if number is None:
            return None
        return round(number * 0.133322, 6) if transform == "mmHg_to_kPa" else round(number * 10.0, 6)

    source_unit = "mmHg" if transform == "mmHg_to_kPa" else "cm"
    target_unit = "kPa" if transform == "mmHg_to_kPa" else "mm"
    method = "value_mmHg * 0.133322 = kPa" if transform == "mmHg_to_kPa" else "value_cm * 10 = mm"

    parsed["original_unit"] = source_unit
    parsed["conversion_method"] = method
    if parsed["value"] is not None:
        parsed["original_value"] = parsed["value"]
        parsed["value"] = convert_one(parsed["value"])
    if parsed["start_value"] is not None:
        parsed["start_value"] = convert_one(parsed["start_value"])
    if parsed["end_value"] is not None:
        parsed["end_value"] = convert_one(parsed["end_value"])
    if parsed["min_value"] is not None:
        parsed["min_value"] = convert_one(parsed["min_value"])
    if parsed["max_value"] is not None:
        parsed["max_value"] = convert_one(parsed["max_value"])
    parsed["unit"] = target_unit
    return parsed


def column(name: str, header: str, unit: str | None = None, transform: str | None = None,
           suspicious: bool = False) -> dict:
    return {
        "name": name,
        "header": header,
        "unit": unit,
        "transform": transform,
        "suspicious": suspicious,
    }


DATASETS = {
    "PSI-69": {
        "source_id": "PSI-69:experimental-table:v1",
        "test_header": "FLEX Test #",
        "identifier_header": "FLEX Identifier",
        "date_header": "Test Date",
        "time_header": "Test GMT",
        "fuel_header": "Fuel",
        "conditions": [
            column("Ambient pressure", "Ambient pressure; mmHg", "kPa", "mmHg_to_kPa"),
            column("O initial ambient composition", "O initial ambient composition; mole fraction", "mol/mol"),
            column("N initial ambient composition", "N initial ambient composition; mole fraction", "mol/mol"),
            column("CO initial ambient composition", "CO initial ambient composition; mole fraction", "mol/mol"),
            column("He initial ambient composition", "He initial ambient composition; mole fraction", "mol/mol"),
            column("Droplet initial diameter", "Droplet initial diameter; mm", "mm"),
        ],
        "measurements": [
            column("Visible flame extinction diameter", "Visible flame extinction diameter; mm", "mm"),
            column("Burning rate", "Burning rate; mm", "mm", suspicious=True),
            column("Burn time", "Burn time; s", "s"),
        ],
        "findings": ["Test end"],
        "outcome_header": "Test end",
    },
}

DATASETS.update({
    "PSI-25": {
        "source_id": "PSI-25:experimental-table:v1", "test_header": "Test #", "identifier_header": "Test #",
        "date_header": "Date", "time_header": "GMT", "fuel_header": "Fuel Sample Material", "outcome_header": None,
        "conditions": [column("Flow restrictor", "Flow restrictor", suspicious=True),
            column("Fan display", "Fan display", suspicious=True), column("Air display", "Air display", suspicious=True),
            column("Radiometer gain", "Radiometer gain   (1000   250   50   10)", suspicious=True),
            column("Initial O2", "Calibrated  initial O2 % by vol", "% by vol"),
            column("Initial CO2", "Initial CO2 % by vol", "% by vol"), column("Initial CO", "Initial CO (ppm)", "ppm")],
        "measurements": [column("Total frames shot", "Total Frames Shot", "frames"),
            column("Final O2", "Calibrated final O2 % by vol", "% by vol"),
            column("Final CO2", "Final CO2 % by vol", "% by vol"), column("Final CO", "Final CO (ppm)", "ppm")],
        "findings": ["PI", "Sample #", "Fuel Sample Material"],
    },
    "PSI-100": {
        "source_id": "PSI-100:experimental-table:v1", "test_header": "Sample Number", "identifier_header": "Sample Number",
        "date_header": None, "time_header": None, "fuel_header": "Material", "outcome_header": None,
        "conditions": [column("Sample thickness", "Sample Thickness", "mm", "cm_to_mm"),
            column("Sample length", "Sample Length", "mm", "cm_to_mm"), column("Sample width", "Sample Width", "mm", "cm_to_mm"),
            column("Air flow", "Air Flow", "cm/s")],
        "measurements": [], "findings": ["Material", "Direction", "Camera 1", "Camera 2"],
    },
    "PSI-101": {
        "source_id": "PSI-101:experimental-table:v1", "test_header": "SAME Test #", "identifier_header": "SAME Test #",
        "date_header": "Date", "time_header": None, "fuel_header": "Sample Type", "outcome_header": None,
        "conditions": [column("Inlet velocity", "Inlet velocity (cm/s)", "cm/s"), column("Rt/R0", "Rt/R0", "1"),
            column("Duration", "Duration (sec)", "s"), column("Primary aging time", "Primary aging time (sec)", "s"),
            column("Primary mixing time", "Primary mixing time (sec)", "s")],
        "measurements": [column("Net aging time", "Net aging time (sec)", "s")], "findings": ["Sample Type", "Description"],
    },
})


def source_reader():
    spec = importlib.util.spec_from_file_location("reviewed_sources", ROOT / "rag-service/app/source_catalog.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def prepare_verified(investigation_ids, manifest_path=DEFAULT_MANIFEST):
    reader = source_reader()
    catalog = reader.load_catalog()
    backend = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    selected, records_by_source = [], {}
    for investigation in backend["investigations"]:
        if investigation["investigationId"] not in investigation_ids:
            continue
        sources = []
        for source in catalog["sources"]:
            if source["investigationId"] != investigation["investigationId"]:
                continue
            records = reader.read_source(source)
            public_file = ROOT / "data/public-docs" / Path(source["documentUrl"].replace("%20", " ")).name
            if hashlib.sha256(public_file.read_bytes()).hexdigest() != source["sha256"]:
                raise ValueError("Public source file differs from pinned original")
            records_by_source[source["sourceId"]] = records
            sources.append({"sourceId": source["sourceId"], "title": source["title"], "sourceType": source["sourceType"],
                "doi": source["doi"], "originalUrl": source["provenance"]["investigationUrl"],
                "documentUrl": source["documentUrl"], "relativePath": source["sourceFile"], "rowCount": len(records),
                "etlEnabled": True, "primary": source["primary"],
                "provenance": {**source["provenance"], "sha256": source["sha256"], "encoding": source["encoding"],
                    "headers": source.get("headers"), "sheetHeaders": source.get("sheetHeaders"), "coverage": source["coverage"]}})
        selected.append({**investigation, "sources": sources})
    if set(investigation_ids) != {i["investigationId"] for i in selected}:
        raise ValueError("Requested investigation is not in the reviewed catalog")
    return {"investigations": selected}, records_by_source


def save_source_row(cur, experiment_id, record):
    cur.execute("""INSERT INTO core.experiment_source_rows
        (source_id, sheet_name, row_number, experiment_id, source_test_id, headers, raw_cells, original_cells)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (source_id, sheet_name, row_number) DO UPDATE SET
            raw_cells=EXCLUDED.raw_cells, original_cells=EXCLUDED.original_cells, headers=EXCLUDED.headers
        WHERE core.experiment_source_rows.experiment_id=EXCLUDED.experiment_id
    """, (record["sourceId"], record.get("sheetName", ""), record["rowNumber"], experiment_id,
        record["sourceTestId"], list(record["fields"]), Json(list(record["fields"].values())),
        Json(record["originalCells"]) if "originalCells" in record else None))
    if cur.rowcount != 1:
        raise ValueError("Source-row experiment mapping changed; transaction rolled back")


def import_verified(conn, manifest, records_by_source):
    results = {}
    with conn.transaction():
        with conn.cursor() as cur:
            for inv in sorted(i["investigationId"] for i in manifest["investigations"]):
                cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (inv + ":experimental-table:v1",))
            upsert_manifest(cur, manifest)
            cur.execute((ROOT / "backend/src/main/resources/db/migration/V3__source_rows.sql").read_text(encoding="utf-8"))
        for investigation in manifest["investigations"]:
            inv = investigation["investigationId"]
            primary = next(s for s in investigation["sources"] if s["primary"])
            results[inv] = load_dataset(conn, inv, primary, DATASETS[inv], records=records_by_source[primary["sourceId"]], preserve_source_rows=True)
            with conn.cursor() as cur:
                cur.execute("SELECT count(*) FROM core.experiments WHERE source_id = %s", (primary["sourceId"],))
                if cur.fetchone()[0] != primary["rowCount"]:
                    raise ValueError("Unexpected primary-source experiment count")
                for source in investigation["sources"]:
                    if source["primary"]: continue
                    for record in records_by_source[source["sourceId"]]:
                        cur.execute("SELECT experiment_id, raw_row FROM core.experiments WHERE source_id=%s AND source_test_id=%s",
                            (primary["sourceId"], record["sourceTestId"]))
                        matches = cur.fetchall()
                        # BASS workbook PI is its worksheet name, not an inferred file-wide label.
                        if len(matches) != 1 or matches[0][1][0] != record["sheetName"]:
                            raise ValueError("Workbook test ID / investigator mapping is ambiguous")
                        experiment_id = matches[0][0]
                        save_source_row(cur, experiment_id, record)
                        cur.execute("""INSERT INTO core.reported_findings
                            (experiment_id,name,value,raw_value,source_id,display_order) VALUES (%s,%s,%s,%s,%s,100)
                        """, (experiment_id, f"Workbook [{record['sheetName']}] Material", record["fields"]["Material"],
                            record["fields"]["Material"], source["sourceId"]))
    return results


def index_headers(header: list[str]) -> dict[str, int]:
    return {normalized_header(name): position for position, name in enumerate(header) if clean(name)}


def cell(row: list[str], index: dict[str, int], header: str | None) -> str:
    if not header:
        return ""
    position = index.get(normalized_header(header))
    if position is None or position >= len(row):
        return ""
    return row[position]


def parse_date_value(raw: str) -> date | None:
    text = clean(raw)
    if not text:
        return None
    for pattern in ("%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d", "%d-%b-%Y"):
        try:
            parsed = datetime.strptime(text, pattern)
            if parsed.year == 1900:  # "%d-%b" supplies 1900; the source has no year.
                return None
            return parsed.date()
        except ValueError:
            continue
    return None


def row_fingerprint(investigation_id: str, source_id: str, row_number: int,
                    source_test_id: str, raw_values: list[str]) -> str:
    payload = "|".join([
        investigation_id,
        source_id,
        str(row_number),
        source_test_id,
        *[clean(value) for value in raw_values],
    ])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def upsert_manifest(cur, manifest: dict) -> None:
    for investigation in manifest["investigations"]:
        cur.execute(
            """
            INSERT INTO core.investigations
                (investigation_id, name, description, available_data_types)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (investigation_id) DO UPDATE SET
                name = EXCLUDED.name,
                description = EXCLUDED.description,
                available_data_types = EXCLUDED.available_data_types,
                updated_at = now()
            """,
            (
                investigation["investigationId"],
                investigation["name"],
                investigation.get("description"),
                investigation.get("availableDataTypes", []),
            ),
        )
        for source in investigation.get("sources", []):
            cur.execute(
                """
                INSERT INTO core.sources
                    (source_id, investigation_id, title, source_type, doi, original_url,
                     document_url, local_path, metadata)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (source_id) DO UPDATE SET
                    title = EXCLUDED.title,
                    source_type = EXCLUDED.source_type,
                    doi = EXCLUDED.doi,
                    original_url = EXCLUDED.original_url,
                    document_url = EXCLUDED.document_url,
                    local_path = EXCLUDED.local_path,
                    metadata = EXCLUDED.metadata
                """,
                (
                    source["sourceId"],
                    investigation["investigationId"],
                    source["title"],
                    source["sourceType"],
                    source.get("doi"),
                    source.get("originalUrl"),
                    source.get("documentUrl"),
                    source.get("relativePath"),
                    Json({"etlEnabled": source.get("etlEnabled", False),
                          "rowCount": source.get("rowCount"),
                          "notes": source.get("notes", []),
                          **source.get("provenance", {})}),
                ),
            )


def next_experiment_id(cur, investigation_id: str) -> str:
    cur.execute(
        """
        INSERT INTO core.experiment_id_sequence AS seq (investigation_id, last_value)
        VALUES (%s, COALESCE((
            SELECT max(substring(experiment_id from ':run-([0-9]+)$')::integer)
            FROM core.experiments WHERE investigation_id = %s
        ), 0))
        ON CONFLICT (investigation_id) DO UPDATE
        SET last_value = GREATEST(seq.last_value, EXCLUDED.last_value)
        """,
        (investigation_id, investigation_id),
    )
    cur.execute(
        "SELECT last_value FROM core.experiment_id_sequence WHERE investigation_id = %s FOR UPDATE",
        (investigation_id,),
    )
    last_value = cur.fetchone()[0] + 1
    cur.execute(
        "UPDATE core.experiment_id_sequence SET last_value = %s WHERE investigation_id = %s",
        (last_value, investigation_id),
    )
    return f"{investigation_id}:run-{last_value:04d}"


def ensure_experiment(cur, investigation_id: str, source_id: str, source_test_id: str,
                      identifier: str | None, fuel: str | None, experiment_date: date | None,
                      date_raw: str | None, test_time: str | None, reported_outcome: str | None,
                      source_row_number: int, fingerprint: str, raw_row: list[str]) -> str:
    """Return the persistent experimentId for this source row (upsert semantics)."""
    cur.execute("SELECT experiment_id FROM core.experiments WHERE row_fingerprint = %s", (fingerprint,))
    existing = cur.fetchone()

    if existing is None:
        # Never allocate another identity for an existing location in this source version.
        # The byte hash preflight rejects changed files; this also catches legacy drift.
        cur.execute("""
            SELECT experiment_id, source_test_id FROM core.experiments
            WHERE source_id = %s AND source_row_number = %s
        """, (source_id, source_row_number))
        previous = cur.fetchall()
        if previous:
            raise ValueError(
                f"Source identity conflict at {source_id}, row {source_row_number}: {previous}. "
                "Review the existing mapping; no new experimentId was allocated."
            )

    if existing:
        experiment_id = existing[0]
        cur.execute(
            """
            UPDATE core.experiments SET
                source_id = %s, source_test_id = %s, experiment_identifier = %s, fuel = %s,
                experiment_date = %s, date_raw = %s, test_time = %s, reported_outcome = %s,
                source_row_number = %s, raw_row = %s, updated_at = now()
            WHERE experiment_id = %s
            """,
            (source_id, source_test_id, identifier, fuel, experiment_date, date_raw,
             test_time, reported_outcome, source_row_number, Json(raw_row), experiment_id),
        )
    else:
        experiment_id = next_experiment_id(cur, investigation_id)
        cur.execute(
            """
            INSERT INTO core.experiments
                (experiment_id, investigation_id, source_id, source_test_id, experiment_identifier,
                 fuel, experiment_date, date_raw, test_time, reported_outcome, source_row_number,
                 row_fingerprint, raw_row)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (experiment_id, investigation_id, source_id, source_test_id, identifier,
             fuel, experiment_date, date_raw, test_time, reported_outcome, source_row_number,
             fingerprint, Json(raw_row)),
        )

    cur.execute("DELETE FROM core.experiment_measurements WHERE experiment_id = %s", (experiment_id,))
    cur.execute("DELETE FROM core.reported_findings WHERE experiment_id = %s", (experiment_id,))
    cur.execute("DELETE FROM core.experiment_warnings WHERE experiment_id = %s", (experiment_id,))
    return experiment_id


def insert_measurement(cur, experiment_id: str, category: str, spec: dict, parsed: dict,
                       source_id: str, display_order: int) -> None:
    cur.execute(
        """
        INSERT INTO core.experiment_measurements
            (experiment_id, category, name, value, unit, qualifier, start_value, end_value,
             min_value, max_value, raw_value, missing_reason, quality_status, source_id,
             original_value, original_unit, conversion_method, display_order)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            experiment_id,
            category,
            spec["name"],
            parsed.get("value"),
            parsed.get("unit", spec.get("unit")),
            parsed["qualifier"],
            parsed.get("start_value"),
            parsed.get("end_value"),
            parsed.get("min_value"),
            parsed.get("max_value"),
            parsed.get("raw_value"),
            parsed.get("missing_reason"),
            parsed["quality_status"],
            source_id,
            parsed.get("original_value"),
            parsed.get("original_unit"),
            parsed.get("conversion_method"),
            display_order,
        ),
    )


def load_dataset(conn, investigation_id: str, source: dict, dataset: dict,
                 *, records: list[dict], preserve_source_rows=False) -> dict:
    """Load validated records inside the caller's transaction; never commit here."""
    header = list(records[0]["fields"])
    rows = [(record["rowNumber"], list(record["fields"].values())) for record in records]
    index = index_headers(header)

    required = [dataset.get("test_header"), dataset.get("fuel_header")]
    required += [spec["header"] for spec in dataset["conditions"] + dataset["measurements"]]
    missing = [name for name in required if name and normalized_header(name) not in index]
    if missing:
        raise RuntimeError(f"{source['relativePath']}: missing columns: {missing}")

    created = updated = 0
    with conn.cursor() as cur:
        for row_number, row in rows:
            source_test_id = clean(cell(row, index, dataset["test_header"]))
            if not source_test_id:
                # Footnote / template / "pre-test visualization" rows are not experiments.
                continue

            raw_values = [clean(value) for value in row]
            fingerprint = row_fingerprint(
                investigation_id, source["sourceId"], row_number, source_test_id, raw_values
            )
            cur.execute("SELECT 1 FROM core.experiments WHERE row_fingerprint = %s", (fingerprint,))
            is_new = cur.fetchone() is None

            date_raw = clean(cell(row, index, dataset["date_header"])) or None
            fuel = clean(cell(row, index, dataset["fuel_header"])) or None
            identifier = clean(cell(row, index, dataset["identifier_header"])) or None
            test_time = clean(cell(row, index, dataset["time_header"])) or None
            outcome_raw = clean(cell(row, index, dataset["outcome_header"]))
            if outcome_raw.upper() in {"DISRUPTION", "EXTINCTION", "COMPLETION"}:
                reported_outcome = outcome_raw.upper()
            else:
                reported_outcome = outcome_raw[:64] or None

            experiment_id = ensure_experiment(
                cur,
                investigation_id=investigation_id,
                source_id=source["sourceId"],
                source_test_id=source_test_id,
                identifier=identifier,
                fuel=fuel,
                experiment_date=parse_date_value(date_raw or ""),
                date_raw=date_raw,
                test_time=test_time,
                reported_outcome=reported_outcome,
                source_row_number=row_number,
                fingerprint=fingerprint,
                raw_row=row,
            )

            warnings: dict[tuple[str, str], None] = {}
            if preserve_source_rows:
                save_source_row(cur, experiment_id, next(record for record in records if record["rowNumber"] == row_number))
            order = 0
            verified_numeric = 0

            for category, specs in (("CONDITION", dataset["conditions"]),
                                    ("MEASUREMENT", dataset["measurements"])):
                for spec in specs:
                    raw_value = cell(row, index, spec["header"])
                    parsed = convert_measurement(parse_cell(raw_value), spec.get("transform"))
                    if spec.get("suspicious") and parsed["quality_status"] != MISSING:
                        parsed["quality_status"] = REQUIRES_REVIEW
                        code = "BURNING_RATE_UNIT_AMBIGUOUS" if spec["name"] == "Burning rate" else "DISPLAY_UNIT_UNSPECIFIED"
                        warnings[(code, f"{spec['header']}: source unit/interpretation requires review; no rate or airflow conversion was inferred.")] = None
                    if parsed.get("value") is not None and parsed["value"] < 0 and spec.get("unit") in {"ppm", "% by vol", "s", "frames"}:
                        parsed["quality_status"] = REQUIRES_REVIEW
                        warnings[("NEGATIVE_REPORTED_VALUE", f"{spec['header']}: negative source reading preserved; excluded from verified comparisons.")] = None
                    if parsed["quality_status"] == REQUIRES_REVIEW:
                        warnings[("VALUE_REQUIRES_REVIEW",
                                  f"{spec['name']}: '{clean(raw_value)}' tek bir dogrulanmis sayiya "
                                  "cevrilemedi; ham deger korunuyor.")] = None
                    if category == "MEASUREMENT" and parsed["quality_status"] == VERIFIED and (
                            parsed["value"] is not None or parsed["start_value"] is not None
                            or parsed["min_value"] is not None):
                        verified_numeric += 1
                    insert_measurement(cur, experiment_id, category, spec, parsed,
                                       source["sourceId"], order)
                    order += 1

            if not dataset["measurements"]:
                warnings[("NO_NUMERIC_MEASUREMENTS",
                          "Bu kaynakta sayisal yanma olcumu yok; yalnizca kosullar ve nitel bulgular aktarildi.")] = None
            elif verified_numeric == 0:
                warnings[("NO_VERIFIED_MEASUREMENTS",
                          "Dogrulanmis sayisal olcum bulunmuyor; karsilastirma sinirli kalir.")] = None

            finding_order = 0
            for finding_header in dataset["findings"]:
                finding_raw = cell(row, index, finding_header)
                if not clean(finding_raw):
                    continue
                cur.execute(
                    """
                    INSERT INTO core.reported_findings
                        (experiment_id, name, value, raw_value, source_id, display_order)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (experiment_id, finding_header, clean(finding_raw), finding_raw,
                     source["sourceId"], finding_order),
                )
                finding_order += 1

            for code, message in warnings:
                cur.execute(
                    """
                    INSERT INTO core.experiment_warnings (experiment_id, code, message)
                    VALUES (%s, %s, %s)
                    """,
                    (experiment_id, code, message),
                )

            if is_new:
                created += 1
            else:
                updated += 1

    return {"created": created, "updated": updated, "rows": len(rows)}



def report(conn) -> None:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT investigation_id, count(*) FROM core.experiments
            GROUP BY investigation_id ORDER BY investigation_id
        """)
        print("\ncore.experiments (investigation bazinda):")
        for investigation_id, count in cur.fetchall():
            print(f"  {investigation_id}: {count}")

        cur.execute("SELECT count(*) FROM core.investigations")
        print(f"core.investigations: {cur.fetchone()[0]}")
        cur.execute("SELECT count(*) FROM core.sources")
        print(f"core.sources: {cur.fetchone()[0]}")
        cur.execute("SELECT count(*) FROM core.experiments")
        print(f"core.experiments: {cur.fetchone()[0]}")
        cur.execute("""
            SELECT category, quality_status, count(*)
            FROM core.experiment_measurements
            GROUP BY category, quality_status ORDER BY category, quality_status
        """)
        print("core.experiment_measurements:")
        for category, status, count in cur.fetchall():
            print(f"  {category}/{status}: {count}")
        cur.execute("SELECT count(*) FROM core.experiment_measurements")
        print(f"core.experiment_measurements (toplam): {cur.fetchone()[0]}")
        cur.execute("SELECT count(*) FROM core.reported_findings")
        print(f"core.reported_findings: {cur.fetchone()[0]}")
        cur.execute("SELECT count(*) FROM core.experiment_warnings")
        print(f"core.experiment_warnings: {cur.fetchone()[0]}")

def prepare_flex(manifest_path: Path = DEFAULT_MANIFEST,
                 source_manifest_path: Path = SOURCE_MANIFEST) -> tuple[dict, list[dict]]:
    """Reuse RAG's strict, read-only CSV extraction, without touching its index/output."""
    spec = importlib.util.spec_from_file_location("flex_csv_source", ROOT / "rag-service/app/csv_loader.py")
    loader = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loader)
    records = loader.extract_records(source_manifest_path, repository_dir=ROOT)
    provenance = json.loads(source_manifest_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    investigation = next(item for item in manifest["investigations"] if item["investigationId"] == "PSI-69")
    source = next(item for item in investigation["sources"] if item["sourceId"] == DATASETS["PSI-69"]["source_id"])
    if (provenance["sourceId"] != source["sourceId"] or provenance["expectedTestCount"] != 274
            or len(records) != 274 or source["rowCount"] != 274):
        raise ValueError("FLEX source identity/count differs between backend and RAG manifests.")
    if source["relativePath"] != provenance["sourceFile"]:
        raise ValueError("FLEX source path differs between backend and RAG manifests.")
    # The existing backend file endpoint must serve the identical original bytes.
    public_file = ROOT / "data/public-docs" / Path(provenance["sourceFile"]).name
    if hashlib.sha256(public_file.read_bytes()).hexdigest() != provenance["sha256"]:
        raise ValueError("The public FLEX source file differs from the manifested CSV.")
    source["provenance"] = {
        "sha256": provenance["sha256"], "encoding": provenance["encoding"],
        "headers": list(records[0]["fields"]), "rowNumberIncludesHeader": True,
    }
    return {"investigations": [{**investigation, "sources": [source]}]}, records


def import_flex(conn, manifest: dict, records: list[dict]) -> dict:
    """One transaction covers catalog, identities, measurements, findings and warnings."""
    with conn.transaction():
        with conn.cursor() as cur:
            # Serialize imports before looking up fingerprints or allocating IDs.
            cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (DATASETS["PSI-69"]["source_id"],))
            upsert_manifest(cur, manifest)
        source = manifest["investigations"][0]["sources"][0]
        stats = load_dataset(conn, "PSI-69", source, DATASETS["PSI-69"], records=records)
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM core.experiments WHERE investigation_id = 'PSI-69'")
            if cur.fetchone()[0] != 274:
                raise ValueError("Expected exactly 274 FLEX experiments; transaction rolled back.")
        return stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Explicit reviewed NASA sources -> PostgreSQL core import (no RAG writes)")
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--investigation", action="append", choices=sorted(DATASETS))
    selection.add_argument("--all-verified", action="store_true")
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--dry-run", action="store_true", help="Validate source files and counts without database writes")
    args = parser.parse_args(argv)

    manifest_path = Path(args.manifest)
    if not manifest_path.is_absolute():
        manifest_path = ROOT / manifest_path
    try:
        manifest, records = prepare_verified(list(DATASETS) if args.all_verified else args.investigation, manifest_path)
        print("Validated sources:", {key: len(value) for key, value in records.items()})
        if args.dry_run:
            return 0
        with psycopg.connect(**DB_CONFIG, connect_timeout=10, autocommit=True) as connection:
            stats = import_verified(connection, manifest, records)
            print("Committed:", stats)
            report(connection)
    except (ValueError, OSError, psycopg.Error) as error:
        print(f"Import failed; no partial import committed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())


