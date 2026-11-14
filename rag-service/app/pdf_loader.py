import argparse
import json
import sys
from pathlib import Path
from typing import BinaryIO
from zipfile import BadZipFile, ZipFile, is_zipfile

from pypdf import PdfReader
from pypdf.errors import PyPdfError

# Resolve paths relative to the service directory.
BASE_DIR = Path(__file__).resolve().parent.parent
PDF_PATH = BASE_DIR / "data" / "documents" / "bass_ii_summary.pdf"
OUTPUT_PATH = BASE_DIR / "data" / "processed" / "bass_ii_pages.json"


class PdfIngestionError(ValueError):
    """The input cannot be used for PDF text ingestion."""


def resolve_service_path(path: str | Path) -> Path:
    """Resolve relative paths against the service, regardless of the caller's cwd."""
    path = Path(path).expanduser()
    if not path.is_absolute():
        path = BASE_DIR / path
    return path.resolve()


def _validate_pdf_content(stream: BinaryIO, path: Path) -> None:
    """Check the file signature and identify renamed Excel workbooks."""
    header = stream.read(1024)
    if b"%PDF-" not in header:
        if is_zipfile(stream):
            try:
                with ZipFile(stream) as archive:
                    entries = set(archive.namelist())
            except BadZipFile as error:
                raise PdfIngestionError(f"Invalid ZIP file; expected a PDF: {path}") from error
            if {"[Content_Types].xml", "xl/workbook.xml"} <= entries:
                raise PdfIngestionError(
                    f"Expected a PDF, but the file is an Excel workbook (XLSX/ZIP): {path}. "
                    "Preserve it with an .xlsx extension and supply the genuine report PDF. "
                    "Renaming a workbook does not convert it to PDF."
                )
            raise PdfIngestionError(f"Expected a PDF, but the file is a ZIP archive: {path}")
        raise PdfIngestionError(f"Invalid file type: no PDF header found in {path}")
    stream.seek(0)


def extract_pages(pdf_path: str | Path = PDF_PATH) -> list[dict]:
    """Extract the supplied BASS-II report, keeping each PDF page separate."""
    pdf_path = resolve_service_path(pdf_path)
    if not pdf_path.is_file():
        raise FileNotFoundError(f"PDF file not found: {pdf_path}. Supply the genuine report PDF.")

    try:
        with pdf_path.open("rb") as stream:
            _validate_pdf_content(stream, pdf_path)
            try:
                reader = PdfReader(stream)
                if reader.is_encrypted:
                    raise PdfIngestionError(f"Encrypted PDFs are not supported: {pdf_path}")
                if not reader.pages:
                    raise PdfIngestionError(f"PDF contains no pages: {pdf_path}")
                pages = []
                # PDF viewer pages are one-based; printed labels are not inferred.
                for page_number, page in enumerate(reader.pages, start=1):
                    try:
                        text = page.extract_text(
                            extraction_mode="layout",
                            layout_mode_space_vertically=True,
                            layout_mode_strip_rotated=False,
                        ) or ""
                    except (PyPdfError, ValueError) as error:
                        raise PdfIngestionError(
                            f"Cannot extract PDF page {page_number} from {pdf_path}: {error}"
                        ) from error
                    pages.append({
                        "sourceId": "PSI-25:summary-report:v1",
                        "investigationId": "PSI-25",
                        "title": "BASS-II Summary Report",
                        "pdfPage": page_number,
                        # Keep indentation, columns, headers, footnotes, and blank lines.
                        "text": text,
                    })
            except PyPdfError as error:
                raise PdfIngestionError(f"Cannot read PDF {pdf_path}: {error}") from error
    except OSError as error:
        raise OSError(f"Cannot read PDF file {pdf_path}: {error}") from error

    return pages


def save_pages(pages: list[dict], output_path: str | Path = OUTPUT_PATH) -> bool:
    """Save UTF-8 JSON, reusing identical output and refusing to replace other files."""
    output_path = resolve_service_path(output_path)
    content = (json.dumps(pages, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        # Exclusive creation protects existing JSON, workbooks, and source PDFs.
        with output_path.open("xb") as stream:
            stream.write(content)
    except FileExistsError:
        if output_path.is_file() and output_path.read_bytes() == content:
            return False
        raise FileExistsError(
            f"Output already exists with different contents: {output_path}. "
            "Choose a new --output path; the existing file was not changed."
        ) from None
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Extract BASS-II report pages into UTF-8 JSON.")
    parser.add_argument("--pdf", type=Path, default=PDF_PATH, help="Genuine BASS-II report PDF.")
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH, help="Page JSON destination.")
    args = parser.parse_args(argv)

    try:
        pages = extract_pages(args.pdf)
        created = save_pages(pages, args.output)
    except (PdfIngestionError, OSError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    non_empty_pages = sum(bool(page["text"].strip()) for page in pages)
    print(f"Total PDF pages: {len(pages)}")
    print(f"Pages containing extracted text: {non_empty_pages}")
    print(
        f"{'Saved to' if created else 'Identical output already exists at'}: "
        f"{resolve_service_path(args.output)}"
    )
    empty_pages = [str(page["pdfPage"]) for page in pages if not page["text"].strip()]
    if empty_pages:
        print("Warning: No text on PDF pages: " + ", ".join(empty_pages) + ". OCR is not performed.")
    print("Review wide tables and rotated text against the PDF; layout extraction can misalign columns.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
