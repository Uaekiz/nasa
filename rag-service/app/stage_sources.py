"""Explicitly stage the entire reviewed multi-source catalog; never replace differing evidence."""
import json
from pathlib import Path
from .source_catalog import ROOT, load_catalog, read_all_sources


def main():
    catalog = load_catalog()
    records = read_all_sources(catalog)
    target = ROOT / "rag-service" / catalog["evidenceFile"]
    content = (json.dumps(records, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    if target.exists():
        if target.read_bytes() != content:
            raise ValueError("The staged snapshot differs. Review versions and use a new evidenceFile; existing output was preserved.")
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as handle:
            handle.write(content)
    print(f"Validated/staged {len(records)} source rows across {len(catalog['sources'])} sources: {target}")


if __name__ == "__main__":
    main()
