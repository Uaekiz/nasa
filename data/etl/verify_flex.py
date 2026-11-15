"""Check the already running backend and imported FLEX rows. Does not start services.

--check-reimport explicitly re-runs the importer and checks persistent identities.
"""
import argparse
from collections import Counter
import hashlib
import json
import os
from urllib.error import HTTPError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

import psycopg

import load_experiments as etl


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-base", default=os.getenv("PYROSPHERE_API_BASE", "http://localhost:8080/api/v1"))
    parser.add_argument("--check-reimport", action="store_true")
    args = parser.parse_args()
    manifest, records = etl.prepare_flex()
    source_id = records[0]["sourceId"]

    def api(path, body=None, status=200):
        request = Request(args.api_base.rstrip("/") + path,
                          data=None if body is None else json.dumps(body).encode(),
                          headers={"Content-Type": "application/json"})
        try:
            with urlopen(request, timeout=15) as response:
                assert response.status == status
                return json.load(response)
        except HTTPError as error:
            assert error.code == status, (error.code, error.read())
            return json.load(error)

    with psycopg.connect(**etl.DB_CONFIG, autocommit=True, connect_timeout=5) as conn:
        def snapshot():
            return conn.execute("""
                SELECT experiment_id, investigation_id, source_id, source_test_id,
                       source_row_number, row_fingerprint
                FROM core.experiments ORDER BY experiment_id
            """).fetchall(), conn.execute("SELECT * FROM core.experiment_id_sequence ORDER BY investigation_id").fetchall()

        before = snapshot()
        if args.check_reimport:
            stats = etl.import_flex(conn, manifest, records)
            assert stats == {"created": 0, "updated": 274, "rows": 274}, stats
            assert before == snapshot(), "Reimport changed experiment identities or sequences"
            print("Reimport: created=0, updated=274; all identities, counts and experiment sequences unchanged")

        db_rows = conn.execute("""
            SELECT experiment_id, source_row_number, raw_row FROM core.experiments
            WHERE source_id = %s ORDER BY source_row_number
        """, (source_id,)).fetchall()
        assert len(db_rows) == 274
        by_test = {}
        for (experiment_id, row_number, raw_row), record in zip(db_rows, records, strict=True):
            assert row_number == record["rowNumber"]
            assert raw_row == list(record["fields"].values())
            by_test[record["sourceTestId"]] = experiment_id
        print("Database: 274 FLEX experiments; all original row numbers and cells match CSV")

        all_items = []
        for page_number in range(14):
            page = api("/experiments?" + urlencode({"investigationId": "PSI-69", "page": page_number, "size": 20}))
            assert (page["totalElements"], page["totalPages"], page["page"]) == (274, 14, page_number)
            all_items.extend(page["items"])
        ids = [item["experimentId"] for item in all_items]
        assert len(set(ids)) == 274 and ids == sorted(ids)
        assert all("measurements" not in item and "simulationParams" not in item for item in all_items)
        assert api("/experiments?investigationId=PSI-69&page=14")["items"] == []
        counts = Counter(r["fields"]["Fuel"] for r in records)
        for fuel, count in counts.items():
            filtered = api("/experiments?" + urlencode({"investigationId": "PSI-69", "fuel": fuel}))
            assert filtered["totalElements"] == count
            assert all(item["fuel"] == fuel for item in filtered["items"])
        assert api("/experiments?fuel=not-a-source-fuel")["totalElements"] == 0
        assert api("/experiments?unsupported=1", status=400)["error"]["code"] == "VALIDATION_ERROR"
        assert api("/experiments?size=101", status=400)["error"]["code"] == "VALIDATION_ERROR"
        print(f"API: 14 pages / 274 unique summaries, fuel filters {dict(counts)}, empty/invalid filters checked")

        samples = [r for r in records if r["sourceTestId"] in {"1", "9", "24", "40", "274"}
                   or r["fields"]["Burn time; s"].startswith("~")]
        for record in samples:
            detail = api("/experiments/" + quote(by_test[record["sourceTestId"]], safe=""))
            assert detail["sourceTestId"] == record["sourceTestId"]
            assert detail["reportedFindings"][0]["rawValue"] == record["fields"]["Test end"]
            values = detail["conditions"] + detail["measurements"]
            for measurement, spec in zip(values, etl.DATASETS["PSI-69"]["conditions"] + etl.DATASETS["PSI-69"]["measurements"], strict=True):
                assert measurement["rawValue"] == record["fields"][spec["header"]]
                assert measurement["sourceId"] == source_id
                if measurement["qualityStatus"] == "MISSING":
                    assert measurement["value"] is None
                if measurement["name"] == "Burning rate":
                    assert measurement["unit"] == "mm" and measurement["qualityStatus"] != "VERIFIED"
        print(f"API details: {len(samples)} samples (missing dates/cells, en dash, approximate times, first/last rows) match source cells")

        selected = [by_test["1"], by_test["24"], by_test["40"]]
        comparison = api("/comparisons", {"experimentIds": selected})
        assert comparison["experimentIds"] == selected
        assert comparison["warnings"]
        assert all(series["metric"] != "Burning rate" for series in comparison["series"])
        for series in comparison["series"]:
            for point in series["points"]:
                assert point["experimentId"] in selected and point["sourceId"] == source_id
                value = conn.execute("""SELECT value FROM core.experiment_measurements
                    WHERE experiment_id = %s AND name = %s AND quality_status = 'VERIFIED'
                """, (point["experimentId"], series["metric"])).fetchone()[0]
                assert value == point["value"]
        api("/comparisons", {"experimentIds": [selected[0]]}, status=400)
        print("API comparison: actual metric/point fields and SQL values match; ambiguous burning rates excluded")

        source = api("/sources/" + quote(source_id, safe=""))
        assert source["sourceId"] == source_id and source["sourceType"] == "CSV"
        url = args.api_base.split("/api/v1")[0] + source["documentUrl"]
        with urlopen(url, timeout=15) as response:
            assert hashlib.sha256(response.read()).hexdigest() == manifest["investigations"][0]["sources"][0]["provenance"]["sha256"]
        print("Source endpoint: original CSV download SHA-256 matches backend/RAG manifest")


if __name__ == "__main__":
    main()
