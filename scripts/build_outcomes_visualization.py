#!/usr/bin/env python3
"""Inject the compact research dataset into the inline visualization fragment."""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path


ORGANIZATION_DISPLAY_ALIASES = {
    "Ulsan National Institute of Science and Technology": "UNIST",
}


OLYMPIAD_SOURCE_PATTERN = re.compile(
    r"(?:imo-official|ioinformatics|ipho-unofficial|icho-official|scoreboard\.bc-pf|ibo-info)",
    re.IGNORECASE,
)


def split_values(value: object) -> list[str]:
    return [item for item in str(value or "").split(";") if item]


def compact_sources(
    row: dict[str, object],
    location: dict[str, object],
    affiliations: list[dict[str, object]],
    audit_evidence: list[dict[str, object]],
) -> list[dict[str, str]]:
    sources: list[dict[str, str]] = []
    seen: set[str] = set()

    def add(url: object, kind: str, label: str, icon: str) -> None:
        value = str(url or "").strip()
        key = value.rstrip("/").casefold()
        if not value.startswith(("http://", "https://")) or key in seen:
            return
        seen.add(key)
        sources.append({"url": value, "kind": kind, "label": label, "icon": icon})

    add(row.get("linkedin_url"), "profile", "Accepted LinkedIn profile", "user-round")
    add(
        row.get("profile_url"),
        "outcome" if row.get("organization") else "evidence",
        "Reviewed destination or identity source",
        "briefcase-business" if row.get("organization") else "file-search-2",
    )

    olympiad_sources = [
        evidence.get("source_url")
        for evidence in audit_evidence
        if evidence.get("claim_type") == "olympiad_participation"
        and evidence.get("review_status") == "accepted"
    ]
    olympiad_sources.extend(
        url for url in split_values(row.get("evidence_urls")) if OLYMPIAD_SOURCE_PATTERN.search(url)
    )
    if olympiad_sources:
        add(olympiad_sources[0], "olympiad", "Official Olympiad result", "medal")

    alma = next(
        (item for item in affiliations if item.get("selected_as_alma_mater")), None
    )
    if alma:
        add(alma.get("evidence_url"), "education", "Alma mater source", "graduation-cap")
    add(location.get("evidence_url"), "location", "Current country source", "map-pin")

    for evidence in audit_evidence:
        if evidence.get("review_status") not in {"accepted", "supporting"}:
            continue
        add(evidence.get("source_url"), "evidence", "Additional reviewed evidence", "file-search-2")
        if len(sources) >= 5:
            break
    return sources[:5]


def compact_person(
    row: dict[str, object],
    location: dict[str, object] | None = None,
    affiliations: list[dict[str, object]] | None = None,
    audit_evidence: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    location = location or {}
    affiliations = affiliations or []
    audit_evidence = audit_evidence or []
    organization = str(row["organization"])
    alma = next(
        (item for item in affiliations if item.get("selected_as_alma_mater")), {}
    )
    history_terms = list(
        dict.fromkeys(
            value
            for item in affiliations
            for value in (str(item.get("organization") or ""), str(item.get("role") or ""))
            if value
        )
    )
    return {
        "id": row["person_id"],
        "name": row["name"],
        "aliases": [value for value in str(row.get("aliases", "")).split(";") if value],
        "olympiads": [value for value in str(row["olympiads"]).split(";") if value],
        "firstYear": int(row["first_year"]),
        "lastYear": int(row.get("last_year") or row["first_year"]),
        "awards": [value for value in str(row.get("awards", "")).split(";") if value],
        "confidence": row["confidence"],
        "organization": ORGANIZATION_DISPLAY_ALIASES.get(organization, organization),
        "role": row["role"],
        "organizationCategory": row["organization_category"],
        "roleCategory": row["role_category"],
        "destinationStatus": row.get("destination_status", ""),
        "almaMater": alma.get("organization", ""),
        "almaMaterRole": alma.get("role", ""),
        "historyTerms": history_terms,
        "countryCode": location.get("country_code", ""),
        "country": location.get("country_name", ""),
        "location": location.get("location_label", ""),
        "locationConfidence": location.get("confidence", ""),
        "profile": row["profile_url"],
        "linkedin": row["linkedin_url"],
        "sources": compact_sources(row, location, affiliations, audit_evidence),
        "scope": row["research_scope"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", default="data/researched_people.json")
    parser.add_argument("--locations", default="data/person_locations.json")
    parser.add_argument("--affiliations", default="data/person_affiliations.json")
    parser.add_argument("--audit-evidence", default="data/audit/evidence.json")
    parser.add_argument(
        "--template",
        default="visualization/olympiad-outcomes-template.html",
    )
    parser.add_argument(
        "--out",
        default="docs/index.html",
    )
    args = parser.parse_args()

    rows = json.loads(Path(args.data).read_text(encoding="utf-8"))
    locations = {
        row["person_id"]: row
        for row in json.loads(Path(args.locations).read_text(encoding="utf-8"))
    }
    affiliations_by_person: dict[str, list[dict[str, object]]] = defaultdict(list)
    for affiliation in json.loads(Path(args.affiliations).read_text(encoding="utf-8")):
        affiliations_by_person[affiliation["person_id"]].append(affiliation)
    evidence_by_person: dict[str, list[dict[str, object]]] = defaultdict(list)
    for evidence in json.loads(Path(args.audit_evidence).read_text(encoding="utf-8")):
        evidence_by_person[evidence["person_id"]].append(evidence)
    compact = [
        compact_person(
            row,
            locations.get(row["person_id"]),
            affiliations_by_person.get(row["person_id"]),
            evidence_by_person.get(row["person_id"]),
        )
        for row in rows
    ]
    template = Path(args.template).read_text(encoding="utf-8")
    marker = "/*__DATA__*/[]"
    if marker not in template:
        raise RuntimeError(f"Visualization data marker not found in {args.template}")
    payload = json.dumps(compact, ensure_ascii=False, separators=(",", ":"))
    output = template.replace(marker, payload, 1)
    output_path = Path(args.out)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(output, encoding="utf-8")
    print(f"Wrote {len(compact)} people to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
