#!/usr/bin/env python3
"""Independently check exported tables, public-page data, and workbook contents."""

from __future__ import annotations

import argparse
import csv
import json
import posixpath
import re
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
NS = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
TABLE_SHEETS = {
    "People": "people", "Evidence": "evidence", "Sources": "sources",
    "Participations": "participations", "Rejections": "rejections",
    "Affiliations": "affiliations", "Locations": "locations",
    "Organizations": "organization_aliases", "Sectors": "organization_sectors",
    "Destination Reviews": "destination_reviews", "Profile Review": "profile_sanity_review",
    "LinkedIn Reconciliation": "linkedin_destination_reconciliation",
    "Root Causes": "profile_sanity_review_findings",
}


def normalized(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value).lower()
    text = str(value).replace("\r\n", "\n")
    if text.lower() in {"true", "false"}:
        return text.lower()
    return text


def workbook_cells(path: Path) -> dict[str, dict[str, str]]:
    result = {}
    with zipfile.ZipFile(path) as archive:
        strings = []
        if "xl/sharedStrings.xml" in archive.namelist():
            for item in ET.fromstring(archive.read("xl/sharedStrings.xml")):
                strings.append("".join(item.itertext()))
        relationships = {
            item.attrib["Id"]: posixpath.normpath("xl/" + item.attrib["Target"])
            if not item.attrib["Target"].startswith("/") else item.attrib["Target"].lstrip("/")
            for item in ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        }
        for sheet in ET.fromstring(archive.read("xl/workbook.xml")).findall("s:sheets/s:sheet", NS):
            cells = {}
            document = ET.fromstring(archive.read(relationships[sheet.attrib[f"{{{REL}}}id"]]))
            for cell in document.findall(".//s:sheetData/s:row/s:c", NS):
                value = cell.findtext("s:v", default="", namespaces=NS)
                kind = cell.get("t")
                if kind == "s":
                    value = strings[int(value)]
                elif kind == "inlineStr":
                    value = "".join(cell.find("s:is", NS).itertext())
                elif kind == "b":
                    value = "true" if value == "1" else "false"
                cells[cell.attrib["r"]] = value
            result[sheet.attrib["name"]] = cells
    return result


def column_name(index: int) -> str:
    result = ""
    while index:
        index, digit = divmod(index - 1, 26)
        result = chr(65 + digit) + result
    return result


def embedded_people(html: str) -> list[dict]:
    marker = re.search(r"\bconst people\s*=\s*", html)
    if marker is None:
        raise ValueError("Public page has no people dataset")
    return json.JSONDecoder().raw_decode(html[marker.end():])[0]


def validate(root: Path) -> dict:
    errors = []
    mirrors = 0
    for path in sorted((root / "data").rglob("*.csv")):
        if "cache" in path.parts or not path.with_suffix(".json").exists():
            continue
        payload = json.loads(path.with_suffix(".json").read_text())
        if isinstance(payload, dict) and "profiles" in payload:
            payload = [{k: "\n".join(line.rstrip() for line in v.splitlines()) if isinstance(v, str) else v
                        for k, v in row.items()} for row in payload["profiles"]]
        elif isinstance(payload, dict) and "searches" in payload and path.name == "exa_linkedin_search_audit.csv":
            import sys
            sys.path.insert(0, str(root))
            from scripts.search_linkedin_with_exa import flat_rows
            payload = flat_rows(payload["searches"])
        if not isinstance(payload, list) or (payload and not isinstance(payload[0], dict)):
            continue
        with path.open(newline="") as handle:
            reader = csv.DictReader(handle)
            fields = reader.fieldnames
            rows = list(reader)
        csv_rows = Counter(tuple(normalized(row.get(field)) for field in fields) for row in rows)
        json_rows = Counter(tuple(normalized(row.get(field)) for field in fields) for row in payload)
        if csv_rows != json_rows:
            errors.append({"kind": "csv_json_mismatch", "file": str(path.relative_to(root)),
                           "csv_only_rows": sum((csv_rows - json_rows).values()),
                           "json_only_rows": sum((json_rows - csv_rows).values())})
        mirrors += 1

    workbook = workbook_cells(root / "docs/kazakhstan_olympiad_outcomes_audit.xlsx")
    manifest = json.loads((root / "data/audit/manifest.json").read_text())["counts"]
    summary_cells = {"B4": "people", "B5": "complete_outcomes", "B6": "confirmed_identities",
                     "B7": "probable_identities", "B8": "evidence_rows", "B9": "sources",
                     "B10": "participations", "E4": "affiliations", "E5": "locations",
                     "E6": "organization_sectors", "E7": "destination_reviews"}
    for address, metric in summary_cells.items():
        if normalized(workbook.get("README", {}).get(address)) != normalized(manifest[metric]):
            errors.append({"kind": "workbook_summary_mismatch", "cell": address, "metric": metric})
    checked_cells = 0
    for name, stem in TABLE_SHEETS.items():
        with (root / f"data/audit/{stem}.csv").open(newline="") as handle:
            rows = list(csv.reader(handle))
        cells = workbook.get(name, {})
        mismatch = []
        expected = {}
        for row_index, row in enumerate(rows, 1):
            for column, value in enumerate(row, 1):
                address = f"{column_name(column)}{row_index}"
                expected[address] = normalized(value)
                if expected[address] != normalized(cells.get(address)):
                    mismatch.append(address)
                checked_cells += 1
        extra = [address for address, value in cells.items() if normalized(value) and address not in expected]
        if mismatch or extra:
            errors.append({"kind": "workbook_mismatch", "sheet": name,
                           "count": len(mismatch), "cells": mismatch[:15], "extra_cells": extra[:15]})

    # Compare the exported public records with the complete current builder output.
    import sys
    sys.path.insert(0, str(root))
    from scripts.build_outcomes_visualization import compact_person, restrict_public_links
    people = json.loads((root / "data/researched_people.json").read_text())
    locations = {row["person_id"]: row for row in json.loads((root / "data/person_locations.json").read_text())}
    affiliations, evidence = defaultdict(list), defaultdict(list)
    for row in json.loads((root / "data/person_affiliations.json").read_text()):
        affiliations[row["person_id"]].append(row)
    for row in json.loads((root / "data/audit/evidence.json").read_text()):
        evidence[row["person_id"]].append(row)
    html = (root / "docs/index.html").read_text()
    published = embedded_people(html)
    with (root / "data/concurrent_destinations.csv").open(newline="") as handle:
        concurrent = list(csv.DictReader(handle))
    expected = [compact_person(row, locations.get(row["person_id"]), affiliations[row["person_id"]],
                               evidence[row["person_id"]], concurrent) for row in people]
    expected = restrict_public_links(expected, set(json.loads((root / "data/published_links.json").read_text())))
    if published != expected:
        errors.append({"kind": "public_data_mismatch"})
    if len({person['id'] for person in published}) != len(published):
        errors.append({"kind": "duplicate_public_person"})
    for person in published:
        if sum(source.get("kind") == "olympiad" for source in person["sources"]) > 1:
            errors.append({"kind": "duplicate_olympiad_source", "person_id": person["id"]})
    return {"csv_json_pairs": mirrors, "workbook_sheets": len(TABLE_SHEETS),
            "workbook_cells": checked_cells, "published_people": len(published), "errors": errors}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    report = validate(args.root)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return int(bool(report["errors"]))


if __name__ == "__main__":
    raise SystemExit(main())
