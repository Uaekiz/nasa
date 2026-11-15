"""Verify all reviewed sources against the existing backend; never starts a server."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

import psycopg
import load_experiments as etl


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-base", default="http://localhost:8080/api/v1")
    parser.add_argument("--check-reimport", action="store_true")
    args = parser.parse_args()
    manifest, records = etl.prepare_verified(list(etl.DATASETS))

    def api(path, body=None):
        request = Request(args.api_base + path, data=None if body is None else json.dumps(body).encode(), headers={"Content-Type": "application/json"})
        with urlopen(request, timeout=15) as response: return json.load(response)

    report = {"checkedAt": "2026-11-15", "investigations": {}}
    with psycopg.connect(**etl.DB_CONFIG, autocommit=True, connect_timeout=5) as conn:
        def snapshot():
            return {"identities": conn.execute("SELECT experiment_id,source_id,source_test_id,source_row_number,row_fingerprint FROM core.experiments ORDER BY experiment_id").fetchall(),
                "sequences": conn.execute("SELECT * FROM core.experiment_id_sequence ORDER BY investigation_id").fetchall(),
                "counts": [conn.execute(f"SELECT count(*) FROM core.{table}").fetchone()[0] for table in
                    ("investigations", "sources", "experiments", "experiment_source_rows", "experiment_measurements", "reported_findings", "experiment_warnings")]}
        before = snapshot()
        baseline = json.loads((etl.ROOT / "rag-service/.local/nasa-provenance/backend_flex_before.json").read_text(encoding="utf-8"))
        current_flex = conn.execute("SELECT experiment_id,source_test_id,row_fingerprint FROM core.experiments WHERE investigation_id='PSI-69' ORDER BY experiment_id").fetchall()
        assert json.loads(json.dumps(current_flex)) == baseline, "Existing FLEX identities changed"
        if args.check_reimport:
            stats = etl.import_verified(conn, manifest, records)
            assert all(s["created"] == 0 for s in stats.values())
            assert before == snapshot(), "Repeat import changed counts/identities/sequences"
            report["reimport"] = stats
            print("Reimport: zero new experiments; all counts/identities/sequences unchanged", flush=True)
        raw_rows = conn.execute("SELECT source_id,sheet_name,row_number,headers,raw_cells,original_cells FROM core.experiment_source_rows").fetchall()
        stored = {(r[0],r[1],r[2]): r for r in raw_rows}
        assert len(stored) == 643
        for rows in records.values():
            for record in rows:
                raw = stored[(record["sourceId"],record.get("sheetName", ""),record["rowNumber"])]
                assert raw[3] == list(record["fields"]) and raw[4] == list(record["fields"].values())
                assert raw[5] == record.get("originalCells")
        assert api("/experiments")["totalElements"] == 514
        assert {i["investigationId"] for i in api("/investigations")["items"]} == set(etl.DATASETS)
        for inv in manifest["investigations"]:
            inv_id = inv["investigationId"]
            source = next(s for s in inv["sources"] if s["primary"])
            source_records = records[source["sourceId"]]
            found = []
            pages = (len(source_records) + 19) // 20
            for page in range(pages):
                result = api("/experiments?" + urlencode({"investigationId": inv_id, "page": page, "size": 20}))
                assert result["totalElements"] == len(source_records)
                assert result["totalPages"] == pages
                assert all(item["investigationId"] == inv_id for item in result["items"])
                found += result["items"]
            assert len({r["experimentId"] for r in found}) == len(source_records)
            fuel_header = etl.DATASETS[inv_id]["fuel_header"]
            fuels = Counter(etl.clean(r["fields"][fuel_header]) for r in source_records)
            fuel = next(iter(fuels))
            filtered = api("/experiments?" + urlencode({"investigationId": inv_id, "fuel": fuel}))
            assert filtered["totalElements"] == fuels[fuel] and all(r["fuel"] == fuel for r in filtered["items"])
            details = []
            for record in (source_records[0],source_records[-1]):
                experiment_id = next(r["experimentId"] for r in found if r["sourceTestId"] == record["sourceTestId"])
                detail = api("/experiments/" + quote(experiment_id, safe=""))
                assert detail["investigationId"] == inv_id
                for measurement,spec in zip(detail["conditions"]+detail["measurements"], etl.DATASETS[inv_id]["conditions"]+etl.DATASETS[inv_id]["measurements"], strict=True):
                    header = next(h for h in record["fields"] if etl.normalized_header(h) == etl.normalized_header(spec["header"]))
                    assert measurement["rawValue"] == record["fields"][header]
                if inv_id == "PSI-100":
                    assert not detail["measurements"] and detail["reportedOutcome"] is None
                if inv_id == "PSI-101": assert detail["date"] is None and detail["dateRaw"]
                if inv_id == "PSI-25": assert any(s["sourceId"] == "PSI-25:test-matrix:v1" for s in detail["sources"])
                details.append(experiment_id)
            ids = [r["experimentId"] for r in found[:2]]
            comparison = api("/comparisons", {"experimentIds": ids})
            if inv_id == "PSI-100": assert comparison["status"] == "INSUFFICIENT_DATA" and not comparison["series"]
            for series in comparison["series"]:
                for point in series["points"]:
                    row = conn.execute("SELECT value,quality_status,qualifier FROM core.experiment_measurements WHERE experiment_id=%s AND name=%s",
                        (point["experimentId"],series["metric"])).fetchone()
                    assert row[0] == point["value"] and row[1] == "VERIFIED"
                    assert row[2] in {"EXACT", "APPROXIMATE"}
                    assert point["experimentId"] in ids and point["sourceId"] == source["sourceId"]
            for item in inv["sources"]:
                metadata = api("/sources/" + quote(item["sourceId"], safe=""))
                with urlopen(args.api_base.split("/api/v1")[0]+metadata["documentUrl"], timeout=15) as response:
                    assert hashlib.sha256(response.read()).hexdigest() == item["provenance"]["sha256"]
            report["investigations"][inv_id] = {"experiments": len(found), "sources": len(inv["sources"]), "pages": pages,
                "detailSamples": details, "comparisonStatus": comparison["status"], "filtersIsolated": True, "sourceFilesHashMatch": True}
            print(inv_id, report["investigations"][inv_id], flush=True)
        report["rawSourceRows"] = 643
        report["flexIdentityBaselineUnchanged"] = True
        (etl.ROOT/"docs/multi-backend-checks.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
        print("PASS: 514 experiments; 643 independent source rows; all source/field/filter/comparison checks passed")


if __name__ == "__main__": main()
