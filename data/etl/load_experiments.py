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
    data/etl/.venv/Scripts/python.exe data/etl/load_experiments.py
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sys
from datetime import date, datetime
from pathlib import Path

import psycopg2
from psycopg2.extras import Json

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = ROOT / "data" / "manifest.json"

DB_CONFIG = {
    "host": os.getenv("PYROSPHERE_DB_HOST", "localhost"),
    "port": int(os.getenv("PYROSPHERE_DB_PORT", "5432")),
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

MISSING_TOKENS = {"", "n/a", "na", "n.a.", "none", "null", "-", "--", "?", "missing"}

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
    "PSI-25": {
        "source_id": "PSI-25:experimental-table:v1",
        "test_header": "Test #",
        "identifier_header": "Test #",
        "date_header": "Date",
        "time_header": "GMT",
        "fuel_header": "Fuel Sample Material",
        "conditions": [
            column("Sample number", "Sample #"),
            column("Flow restrictor", "Flow restrictor"),
            column("Fan display", "Fan display"),
            column("Air display", "Air display"),
            column("Radiometer gain", "Radiometer gain   (1000   250   50   10)"),
        ],
        "measurements": [
            column("Total frames shot", "Total Frames Shot", "frames"),
            column("Initial O2", "Calibrated  initial O2 % by vol", "% by vol"),
            column("Final O2", "Calibrated final O2 % by vol", "% by vol"),
            column("Initial CO2", "Initial CO2 % by vol", "% by vol"),
            column("Final CO2", "Final CO2 % by vol", "% by vol"),
            column("Initial CO", "Initial CO (ppm)", "ppm"),
            column("Final CO", "Final CO (ppm)", "ppm"),
        ],
        "findings": ["PI"],
        "outcome_header": None,
    },
    "PSI-101": {
        "source_id": "PSI-101:experimental-table:v1",
        "test_header": "SAME Test #",
        "identifier_header": "SAME Test #",
        "date_header": "Date",
        "time_header": None,
        "fuel_header": "Sample Type",
        "conditions": [
            column("Inlet velocity", "Inlet velocity (cm/s)", "cm/s"),
            column("Rt/R0", "Rt/R0"),
            column("Duration", "Duration (sec)", "s"),
            column("Primary aging time", "Primary aging time (sec)", "s"),
            column("Primary mixing time", "Primary mixing time (sec)", "s"),
        ],
        "measurements": [
            column("Net aging time", "Net aging time (sec)", "s"),
        ],
        "findings": ["Description"],
        "outcome_header": None,
    },
    "PSI-100": {
        "source_id": "PSI-100:experimental-table:v1",
        "test_header": "Sample Number",
        "identifier_header": "Sample Number",
        "date_header": None,
        "time_header": None,
        "fuel_header": "Material",
        "conditions": [
            column("Sample thickness", "Sample Thickness", "mm", "cm_to_mm"),
            column("Sample length", "Sample Length", "mm", "cm_to_mm"),
            column("Sample width", "Sample Width", "mm", "cm_to_mm"),
            column("Air flow", "Air Flow", "cm/s"),
        ],
        "measurements": [],
        "findings": ["Direction"],
        "outcome_header": None,
    },
}


def read_csv_rows(path: Path) -> tuple[list[str], list[tuple[int, list[str]]]]:
    with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as handle:
        reader = csv.reader(handle)
        try:
            header = next(reader)
        except StopIteration:
            return [], []
        rows = [(number, row) for number, row in enumerate(reader, start=2) if any(clean(c) for c in row)]
    return header, rows


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
    for pattern in ("%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d", "%d-%b-%Y", "%d-%b"):
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
                          "notes": source.get("notes", [])}),
                ),
            )


def next_experiment_id(cur, investigation_id: str) -> str:
    cur.execute(
        """
        INSERT INTO core.experiment_id_sequence (investigation_id, last_value)
        VALUES (%s, 0)
        ON CONFLICT (investigation_id) DO NOTHING
        """,
        (investigation_id,),
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


def load_dataset(conn, investigation_id: str, source: dict, dataset: dict) -> dict:
    path = ROOT / source["relativePath"]
    header, rows = read_csv_rows(path)
    index = index_headers(header)

    required = [dataset.get("test_header"), dataset.get("fuel_header")]
    required += [spec["header"] for spec in dataset["conditions"] + dataset["measurements"]]
    missing = [name for name in required if name and normalized_header(name) not in index]
    if missing:
        raise RuntimeError(f"{path.name}: beklenen sutunlar bulunamadi: {missing}")

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
            order = 0
            verified_numeric = 0

            for category, specs in (("CONDITION", dataset["conditions"]),
                                    ("MEASUREMENT", dataset["measurements"])):
                for spec in specs:
                    raw_value = cell(row, index, spec["header"])
                    parsed = convert_measurement(parse_cell(raw_value), spec.get("transform"))
                    if spec.get("suspicious") and parsed["quality_status"] != MISSING:
                        parsed["quality_status"] = REQUIRES_REVIEW
                        warnings[("BURNING_RATE_UNIT_AMBIGUOUS",
                                  "Burning rate basligindaki birim (mm) belirsiz; deger REQUIRES_REVIEW, "
                                  "varsayilan sayisal karsilastirmaya katilmaz.")] = None
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

    conn.commit()
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

def main() -> int:
    parser = argparse.ArgumentParser(description="Pyrosphere CSV -> PostgreSQL ETL")
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    args = parser.parse_args()

    manifest_path = Path(args.manifest)
    if not manifest_path.is_absolute():
        manifest_path = ROOT / manifest_path
    with manifest_path.open("r", encoding="utf-8") as handle:
        manifest = json.load(handle)

    investigations = {item["investigationId"]: item for item in manifest["investigations"]}
    connection = psycopg2.connect(**DB_CONFIG)
    try:
        with connection.cursor() as cur:
            upsert_manifest(cur, manifest)
        connection.commit()

        for investigation_id in manifest["etl"]["order"]:
            investigation = investigations[investigation_id]
            source = next(
                (item for item in investigation["sources"] if item.get("etlEnabled")),
                None,
            )
            if source is None:
                print(f"! {investigation_id}: etlEnabled kaynak yok, atlandi")
                continue
            dataset = DATASETS[investigation_id]
            print(f"-> {investigation_id} ({investigation['name']}), kaynak: {source['relativePath']}")
            stats = load_dataset(connection, investigation_id, source, dataset)
            print(f"   yeni: {stats['created']}, guncellenen: {stats['updated']}, veri satiri: {stats['rows']}")

        report(connection)
    finally:
        connection.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())


