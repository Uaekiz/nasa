import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from zipfile import ZipFile

from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from app.pdf_loader import (
    BASE_DIR,
    PDF_PATH,
    PdfIngestionError,
    extract_pages,
    resolve_service_path,
    save_pages,
)


def write_synthetic_pdf(path: Path, *, encrypted: bool = False, empty: bool = False) -> None:
    """Build a small test fixture; it is not a NASA report or scientific evidence."""
    writer = PdfWriter()
    if not empty:
        font = DictionaryObject({
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
            NameObject("/Encoding"): NameObject("/WinAnsiEncoding"),
        })
        page = writer.add_blank_page(width=612, height=792)
        page[NameObject("/Resources")] = DictionaryObject({
            NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})
        })
        contents = DecodedStreamObject()
        contents.set_data(
            b"BT /F1 12 Tf 1 0 0 1 60 740 Tm (Synthetic table) Tj "
            b"1 0 0 1 60 710 Tm (Test ID) Tj "
            b"1 0 0 1 240 710 Tm (Condition) Tj "
            b"1 0 0 1 60 690 Tm (SYNTHETIC-001) Tj "
            b"1 0 0 1 240 690 Tm (caf\xe9) Tj "
            b"1 0 0 1 100 650 Tm (Synthetic footnote) Tj ET"
        )
        page[NameObject("/Contents")] = writer._add_object(contents)
        writer.add_blank_page(width=612, height=792)
    if encrypted:
        writer.encrypt("synthetic-test-password", algorithm="RC4-128")
    writer.write(path)


class PdfLoaderTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.pdf = self.directory / "synthetic.pdf"
        self.output = self.directory / "pages.json"

    def test_extracts_layout_metadata_and_empty_page_without_changing_source(self):
        write_synthetic_pdf(self.pdf)
        before = hashlib.sha256(self.pdf.read_bytes()).digest()
        pages = extract_pages(self.pdf)
        self.assertEqual([page["pdfPage"] for page in pages], [1, 2])
        for page in pages:
            self.assertEqual(set(page), {"sourceId", "investigationId", "title", "pdfPage", "text"})
            self.assertEqual(page["sourceId"], "PSI-25:summary-report:v1")
            self.assertEqual(page["investigationId"], "PSI-25")
            self.assertEqual(page["title"], "BASS-II Summary Report")
        self.assertRegex(pages[0]["text"], r"Test ID {2,}Condition")
        self.assertRegex(pages[0]["text"], r"SYNTHETIC-001 {2,}caf\u00e9")
        self.assertIn("Synthetic table", pages[0]["text"])
        self.assertRegex(pages[0]["text"], r"\n +Synthetic footnote")
        self.assertFalse(pages[1]["text"].strip())
        self.assertEqual(hashlib.sha256(self.pdf.read_bytes()).digest(), before)

    def test_accepts_pdf_content_independently_of_extension(self):
        path = self.directory / "synthetic.bin"
        write_synthetic_pdf(path)
        self.assertEqual(len(extract_pages(path)), 2)

    def test_missing_pdf_has_clear_error(self):
        with self.assertRaisesRegex(FileNotFoundError, "PDF file not found:.*synthetic.pdf"):
            extract_pages(self.pdf)

    def test_rejects_workbook_renamed_as_pdf_without_modifying_it(self):
        with ZipFile(self.pdf, "w") as archive:
            archive.writestr("[Content_Types].xml", "<Types/>")
            archive.writestr("xl/workbook.xml", "<workbook/>")
            archive.writestr("xl/worksheets/sheet1.xml", "<worksheet/>")
        before = self.pdf.read_bytes()
        with self.assertRaisesRegex(PdfIngestionError, "Excel workbook.*XLSX/ZIP"):
            extract_pages(self.pdf)
        self.assertEqual(self.pdf.read_bytes(), before)

    def test_rejects_generic_zip(self):
        with ZipFile(self.pdf, "w") as archive:
            archive.writestr("synthetic.txt", "This is not a PDF.")
        with self.assertRaisesRegex(PdfIngestionError, "ZIP archive"):
            extract_pages(self.pdf)

    def test_rejects_non_pdf_and_empty_files(self):
        for content in (b"This is not a PDF.", b""):
            with self.subTest(content=content):
                self.pdf.write_bytes(content)
                with self.assertRaisesRegex(PdfIngestionError, "no PDF header found"):
                    extract_pages(self.pdf)

    def test_pdf_header_alone_is_not_sufficient(self):
        self.pdf.write_bytes(b"%PDF-1.7\nThis is truncated.\n")
        with self.assertRaisesRegex(PdfIngestionError, "Cannot read PDF"):
            extract_pages(self.pdf)

    def test_rejects_encrypted_pdf(self):
        write_synthetic_pdf(self.pdf, encrypted=True)
        with self.assertRaisesRegex(PdfIngestionError, "Encrypted PDFs are not supported"):
            extract_pages(self.pdf)

    def test_rejects_pdf_without_pages(self):
        write_synthetic_pdf(self.pdf, empty=True)
        with self.assertRaisesRegex(PdfIngestionError, "PDF contains no pages"):
            extract_pages(self.pdf)

    def test_json_is_utf8_and_identical_output_is_reused(self):
        write_synthetic_pdf(self.pdf)
        pages = extract_pages(self.pdf)
        self.assertTrue(save_pages(pages, self.output))
        original = self.output.read_bytes()
        self.assertIn("caf\u00e9".encode("utf-8"), original)
        self.assertEqual(json.loads(original), pages)
        modified = self.output.stat().st_mtime_ns
        self.assertFalse(save_pages(pages, self.output))
        self.assertEqual(self.output.read_bytes(), original)
        self.assertEqual(self.output.stat().st_mtime_ns, modified)

    def test_existing_output_and_pdf_cannot_be_overwritten(self):
        write_synthetic_pdf(self.pdf)
        pages = extract_pages(self.pdf)
        self.output.write_bytes(b"Existing output must survive.")
        for path in (self.output, self.pdf):
            with self.subTest(path=path):
                before = path.read_bytes()
                with self.assertRaisesRegex(FileExistsError, "existing file was not changed"):
                    save_pages(pages, path)
                self.assertEqual(path.read_bytes(), before)

    def test_relative_paths_are_based_on_service_directory(self):
        self.assertEqual(resolve_service_path("data/documents/bass_ii_summary.pdf"), PDF_PATH)
        self.assertEqual(resolve_service_path("data/processed/pages.json"),
                         BASE_DIR / "data" / "processed" / "pages.json")

    def run_loader(self, *arguments):
        return subprocess.run(
            [sys.executable, "-X", "utf8", str(BASE_DIR / "app" / "pdf_loader.py"),
             *map(str, arguments)],
            cwd=self.directory,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=20,
        )

    def test_cli_runs_from_other_directory_and_reports_blank_pages(self):
        write_synthetic_pdf(self.pdf)
        result = self.run_loader("--pdf", self.pdf, "--output", self.output)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(json.loads(self.output.read_text(encoding="utf-8"))), 2)
        self.assertIn("No text on PDF pages: 2", result.stdout)
        self.assertIn("OCR is not performed", result.stdout)
        self.assertIn("Review wide tables", result.stdout)

    def test_cli_invalid_input_creates_no_output(self):
        self.pdf.write_bytes(b"Not a PDF.")
        result = self.run_loader("--pdf", self.pdf, "--output", self.output)
        self.assertEqual(result.returncode, 1)
        self.assertIn("Error: Invalid file type", result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertFalse(self.output.exists())

    def test_cli_existing_output_is_preserved(self):
        write_synthetic_pdf(self.pdf)
        self.output.write_bytes(b"Existing output must survive.")
        result = self.run_loader("--pdf", self.pdf, "--output", self.output)
        self.assertEqual(result.returncode, 1)
        self.assertIn("Choose a new --output path", result.stderr)
        self.assertEqual(self.output.read_bytes(), b"Existing output must survive.")


if __name__ == "__main__":
    unittest.main()
