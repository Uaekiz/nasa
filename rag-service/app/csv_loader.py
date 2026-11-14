"""Stage PSI-69 FLEX CSV rows as evidence without normalizing scientific values."""

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import sys


BASE_DIR = Path(__file__).resolve().parent.parent
REPOSITORY_DIR = BASE_DIR.parent
MANIFEST_PATH = BASE_DIR / "source_manifest.json"
PROCESSED_DIR = BASE_DIR / "data" / "processed"
OUTPUT_PATH = PROCESSED_DIR / "flex_psi69_evidence.json"


class CsvIngestionError(ValueError):
    """The source or its manifest cannot be ingested without losing provenance."""


def extract_records(
    manifest_path: Path = MANIFEST_PATH,
    *,
    repository_dir: Path = REPOSITORY_DIR,
) -> list[dict]:
    """Read the manifested source and preserve all original headers and cell strings."""
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise CsvIngestionError(f"Cannot read the source manifest: {manifest_path}") from error
    required = (
        "sourceId", "investigationId", "sourceType", "sourceFile", "encoding",
        "sha256", "sourceTestIdField",
    )
    if not isinstance(manifest, dict) or any(
        not isinstance(manifest.get(key), str) or not manifest[key].strip() for key in required
    ):
        raise CsvIngestionError("The source manifest must contain all required string fields.")
    if manifest["investigationId"] != "PSI-69" or manifest["sourceType"] != "CSV":
        raise CsvIngestionError("This loader supports only the PSI-69 FLEX CSV source.")
    expected_count = manifest.get("expectedTestCount")
    if type(expected_count) is not int or expected_count < 1:
        raise CsvIngestionError("The source manifest must specify a positive expectedTestCount.")

    repository_dir = repository_dir.resolve()
    source_path = (repository_dir / manifest["sourceFile"]).resolve()
    if not source_path.is_relative_to(repository_dir / "databases"):
        raise CsvIngestionError("The source CSV must be inside the repository's databases directory.")
    try:
        original_bytes = source_path.read_bytes()
    except OSError as error:
        raise CsvIngestionError(
            f"Cannot read source CSV: {source_path} ({type(error).__name__})."
        ) from error
    if hashlib.sha256(original_bytes).hexdigest() != manifest["sha256"]:
        raise CsvIngestionError(
            "Source CSV SHA-256 differs from the manifest. Review the source version, "
            "sourceId, and expected test count before ingesting changed data."
        )
    try:
        source_text = original_bytes.decode(manifest["encoding"], errors="strict")
    except (UnicodeError, LookupError) as error:
        raise CsvIngestionError(
            f"Cannot decode the source CSV using {manifest['encoding']}; no replacement text was used."
        ) from error

    reader = csv.reader(io.StringIO(source_text, newline=""), strict=True)
    records = []
    try:
        headers = next(reader, None)
        if not headers or any(not header.strip() for header in headers):
            raise CsvIngestionError("The source CSV must have nonempty original column headers.")
        if len(set(headers)) != len(headers):
            raise CsvIngestionError("Duplicate CSV headers would lose field values; review the source.")
        id_field = manifest["sourceTestIdField"]
        if id_field != "FLEX Test #" or not {id_field, "FLEX Identifier"} <= set(headers):
            raise CsvIngestionError("The source CSV must contain FLEX Test # and FLEX Identifier.")

        # Count logical CSV records, including the header and any blank rows.
        for row_number, row in enumerate(reader, start=2):
            if not row or all(value == "" for value in row):
                continue
            if len(row) != len(headers):
                raise CsvIngestionError(
                    f"CSV row {row_number} has {len(row)} cells; expected {len(headers)}."
                )
            fields = dict(zip(headers, row, strict=True))
            test_id = fields[id_field]
            # These are the observed test markers, not generated backend identifiers.
            if not (
                test_id.strip().isascii()
                and test_id.strip().isdecimal()
                and fields["FLEX Identifier"].strip()
            ):
                raise CsvIngestionError(
                    f"CSV row {row_number} is not a recognized FLEX test row. "
                    "Review notes or missing test identifiers before ingestion."
                )
            source_file = source_path.relative_to(repository_dir).as_posix()
            text_lines = [
                "FLEX CSV test evidence.",
                f"Investigation: {manifest['investigationId']}",
                f"Source: {source_file}",
                f"CSV row (including the header): {row_number}",
                "Original field names and JSON-quoted cell values:",
            ]
            text_lines.extend(
                f"{header}: {json.dumps(value, ensure_ascii=False)}"
                for header, value in fields.items()
            )
            records.append({
                "investigationId": manifest["investigationId"],
                "sourceId": manifest["sourceId"],
                "sourceTestId": test_id,
                "sourceType": "CSV",
                "sourceFile": source_file,
                "rowNumber": row_number,
                "fields": fields,
                "text": "\n".join(text_lines),
            })
    except csv.Error as error:
        raise CsvIngestionError(
            f"Malformed CSV near physical line {reader.line_num}: {error}"
        ) from error
    if len(records) != expected_count:
        raise CsvIngestionError(
            f"Extracted {len(records)} test records; the manifest expects {expected_count}. "
            "Review the source before saving evidence."
        )
    return records


def save_records(
    records: list[dict],
    output_path: str | Path = OUTPUT_PATH,
    *,
    output_root: Path = PROCESSED_DIR,
) -> bool:
    """Write a separate UTF-8 JSON snapshot; never append or replace different output."""
    output_path = Path(output_path)
    if not output_path.is_absolute():
        output_path = BASE_DIR / output_path
    output_path = output_path.resolve()
    if not output_path.is_relative_to(output_root.resolve()) or output_path.suffix.lower() != ".json":
        raise CsvIngestionError("Output must be a JSON file inside rag-service/data/processed/.")
    content = (json.dumps(records, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with output_path.open("xb") as stream:
                stream.write(content)
        except FileExistsError:
            if output_path.is_file() and output_path.read_bytes() == content:
                return False
            raise CsvIngestionError(
                f"Output already exists with different contents: {output_path}. "
                "Choose a new --output path; the existing file was not changed."
            ) from None
    except OSError as error:
        raise CsvIngestionError(
            f"Cannot write evidence JSON: {output_path} ({type(error).__name__})."
        ) from error
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Stage PSI-69 FLEX CSV tests as raw evidence.")
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH, help="New evidence JSON path.")
    args = parser.parse_args(argv)
    try:
        records = extract_records()
        created = save_records(records, args.output)
    except CsvIngestionError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    output_path = args.output if args.output.is_absolute() else BASE_DIR / args.output
    print(f"Extracted test records: {len(records)}")
    print(f"{'Saved to' if created else 'Identical output already exists at'}: {output_path.resolve()}")
    print("Original headers and cell strings were preserved; no experimentId values were assigned.")
    print("The source header 'Burning rate; mm' remains ambiguous; no rate unit was inferred.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
