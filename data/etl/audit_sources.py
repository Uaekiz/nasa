"""Reproduce local row/field comparisons. Remote hash verification is pinned in the catalog."""
from collections import Counter
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("catalog", ROOT / "rag-service/app/source_catalog.py")
catalog_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(catalog_module)


def audit():
    catalog = catalog_module.load_catalog()
    records = catalog_module.read_all_sources(catalog)
    csv_rows = {r["sourceTestId"]: r for r in records if r["sourceId"] == "PSI-25:experimental-table:v1"}
    workbook = [r for r in records if r["sourceType"] == "XLSX"]
    differences, examples = Counter(), []
    mapping = {"Test #": "Test no.", "Sample #": "Sample no.", "Fuel Sample Material": "Material",
        "Fan display": "Fan display", "Air display": "Air display", "Flow restrictor": "Flow restrictor",
        "Radiometer gain   (1000   250   50   10)": "Radiometer gain   (1000, 250, 50, 10)",
        "Total Frames Shot": "total frames shot", "Calibrated  initial O2 % by vol ": "calibrated  initial O2 % by vol ",
        "Calibrated final O2 % by vol": "calibrated final O2 % by vol", "Initial CO2 % by vol": "Initial CO2 % by vol",
        "Final CO2 % by vol": "Final CO2 % by vol", "Initial CO (ppm)": "Initial CO (ppm)", "Final CO (ppm)": "Final CO (ppm)"}
    assert len(csv_rows) == len(workbook) == 129
    for record in workbook:
        csv = csv_rows[record["sourceTestId"]]
        assert csv["fields"]["PI"] == record["sheetName"]
        for left, right in mapping.items():
            a, b = csv["fields"][left], record["fields"][right]
            if a != b:
                differences[left] += 1
                if len(examples) < 18:
                    examples.append({"testId": record["sourceTestId"], "sheet": record["sheetName"],
                        "workbookRow": record["rowNumber"], "csvRow": csv["rowNumber"],
                        "csvHeader": left, "workbookHeader": right, "csvCell": a, "workbookCell": b})
    return {"sources": [{"sourceId": s["sourceId"], "sha256": s["sha256"], "provenance": s["provenance"],
        "rowCount": s["expectedTestCount"], "coverage": s["coverage"]} for s in catalog["sources"]],
        "bassOverlap": {"csvRows": 129, "workbookRows": 129, "matchingTestIdAndInvestigator": 129,
            "workbookRowsPerSheet": dict(Counter(r["sheetName"] for r in workbook)),
            "differentRawCellsPerField": dict(differences), "examples": examples,
            "decision": "Preserve independent source rows; link only by verified test ID and PI. Do not create duplicate experiments or overwrite CSV cells with workbook cells.",
            "dateDifference": "CSV dates are text; workbook dates are numeric Excel cells with their original styles. Workbook raw serial values are preserved separately."},
        "saffireIII": {"rowCount": 2, "verifiedOriginalBytes": 239,
            "decision": "This is the complete downloaded NASA experimental-table file, with two sample/condition rows. It is not a complete measured-results dataset. No burn times, outcomes, or burn rates are present."}}


if __name__ == "__main__":
    report = audit()
    target = ROOT / "docs/local-source-audit.json"
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"rows": sum(s["rowCount"] for s in report["sources"]), "overlap": report["bassOverlap"]["matchingTestIdAndInvestigator"],
        "differences": report["bassOverlap"]["differentRawCellsPerField"]}))
