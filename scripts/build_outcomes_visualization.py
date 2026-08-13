#!/usr/bin/env python3
"""Inject the compact research dataset into the inline visualization fragment."""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

try:
    from scripts.organization_names import (
        canonicalize_organization,
        display_organization,
        organization_aliases_for,
    )
    from scripts.organization_sectors import organization_metadata
except ModuleNotFoundError:  # Direct script execution adds scripts/ to sys.path.
    from organization_names import (
        canonicalize_organization,
        display_organization,
        organization_aliases_for,
    )
    from organization_sectors import organization_metadata


OLYMPIAD_SOURCE_PATTERN = re.compile(
    r"(?:imo-official|ioinformatics|ipho-unofficial|icho-official|scoreboard\.bc-pf|ibo-info)",
    re.IGNORECASE,
)


def split_values(value: object) -> list[str]:
    return [item for item in str(value or "").split(";") if item]


def selected_alma_maters(
    affiliations: list[dict[str, object]],
) -> list[dict[str, object]]:
    selected: dict[str, dict[str, object]] = {}
    for item in affiliations:
        if not item.get("selected_as_alma_mater"):
            continue
        organization = canonicalize_organization(item.get("organization"))
        key = organization.casefold()
        if organization and key not in selected:
            selected[key] = item
    return sorted(
        selected.values(),
        key=lambda item: (
            alma_degree_rank(item.get("role")),
            int(str(item.get("start_year") or "0"))
            if str(item.get("start_year") or "").isdigit()
            else 9999,
            int(str(item.get("end_year") or "0"))
            if str(item.get("end_year") or "").isdigit()
            else 9999,
            canonicalize_organization(item.get("organization")).casefold(),
        ),
    )


def alma_degree_rank(role: object) -> int:
    value = str(role or "").casefold()
    if re.search(r"\b(?:associate|bachelor|bsc|bs\b|beng|undergraduate|medical student|бакалавр)", value):
        return 1
    if re.search(r"\b(?:master|msc|ms\b|meng|mba|mph|specialist|магистр|специалист)", value):
        return 2
    if re.search(r"\b(?:ph\.?d|doctor|graduate student)", value):
        return 3
    return 4


def preferred_alma_source(
    alma: dict[str, object], affiliations: list[dict[str, object]]
) -> dict[str, object]:
    organization = canonicalize_organization(alma.get("organization"))
    candidates = [
        item
        for item in affiliations
        if canonicalize_organization(item.get("organization")) == organization
        and str(item.get("affiliation_type") or "").casefold() == "education"
        and str(item.get("evidence_url") or "").startswith(("http://", "https://"))
    ]
    if not candidates:
        return alma

    def source_rank(item: dict[str, object]) -> tuple[int, int, int, str]:
        evidence_kind = str(item.get("evidence_kind") or "").casefold()
        source_quality = 0
        if evidence_kind.startswith("official_"):
            source_quality = 4
        elif evidence_kind in {
            "institutional_profile",
            "publication_affiliation",
            "research_group_biography",
        }:
            source_quality = 3
        elif evidence_kind.startswith("accepted_orcid") or evidence_kind.startswith(
            "accepted_openalex"
        ):
            source_quality = 2
        elif evidence_kind != "accepted_linkedin_profile":
            source_quality = 1
        confidence = {"confirmed": 2, "probable": 1}.get(
            str(item.get("confidence") or "").casefold(), 0
        )
        url = str(item.get("evidence_url") or "")
        return source_quality, confidence, int("linkedin.com" not in url.casefold()), url

    return max(candidates, key=source_rank)


def compact_sources(
    row: dict[str, object],
    location: dict[str, object],
    affiliations: list[dict[str, object]],
    audit_evidence: list[dict[str, object]],
) -> list[dict[str, str]]:
    sources: list[dict[str, str]] = []
    seen: set[str] = set()
    unpublished_urls = {
        "https://stats.ioinformatics.org/results/kaz",
    }

    def add(url: object, kind: str, label: str, icon: str) -> None:
        value = str(url or "").strip()
        key = value.rstrip("/").casefold()
        if (
            not value.startswith(("http://", "https://"))
            or key in seen
            or key in unpublished_urls
            or (kind != "olympiad" and OLYMPIAD_SOURCE_PATTERN.search(value))
        ):
            return
        seen.add(key)
        sources.append({"url": value, "kind": kind, "label": label, "icon": icon})

    add(row.get("linkedin_url"), "profile", "Accepted LinkedIn profile", "user-round")
    destination_evidence = [
        evidence
        for evidence in audit_evidence
        if evidence.get("review_status") == "accepted"
        and evidence.get("supports_final_outcome")
        and evidence.get("claim_type")
        in {"destination_source_review", "career_outcome"}
    ]
    destination_evidence.sort(
        key=lambda evidence: (
            evidence.get("claim_type") != "destination_source_review",
            str(evidence.get("source_url") or ""),
        )
    )
    if row.get("organization") and destination_evidence:
        add(
            destination_evidence[0].get("source_url"),
            "outcome",
            "Reviewed destination source",
            "briefcase-business",
        )
    else:
        add(
            row.get("profile_url"),
            "outcome" if row.get("organization") else "evidence",
            (
                "Reviewed destination source"
                if row.get("organization")
                else "Reviewed identity source"
            ),
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
    if OLYMPIAD_SOURCE_PATTERN.search(str(row.get("profile_url") or "")):
        olympiad_sources.append(row.get("profile_url"))

    def olympiad_source_rank(url: object) -> tuple[int, int, str]:
        value = str(url or "")
        if re.search(r"/(?:contestant|participant|profile)[_/]", value, re.IGNORECASE):
            source_rank = 0
        elif re.search(r"(?:team_|country|individual)", value, re.IGNORECASE):
            source_rank = 1
        else:
            source_rank = 2
        return source_rank, int(not value.casefold().startswith("https://")), value.casefold()

    if olympiad_sources:
        best_olympiad_source = min(
            dict.fromkeys(str(url) for url in olympiad_sources if url),
            key=olympiad_source_rank,
        )
        add(best_olympiad_source, "olympiad", "Official Olympiad result", "medal")

    for alma in selected_alma_maters(affiliations):
        source = preferred_alma_source(alma, affiliations)
        add(source.get("evidence_url"), "education", "Alma mater source", "graduation-cap")
    location_label = (
        "Historical outcome country source"
        if location.get("evidence_kind") == "historical_outcome_location"
        else "Outcome country source"
    )
    add(location.get("evidence_url"), "location", location_label, "map-pin")

    for evidence in audit_evidence:
        if evidence.get("review_status") not in {"accepted", "supporting"}:
            continue
        if evidence.get("claim_type") == "olympiad_participation":
            continue
        add(evidence.get("source_url"), "evidence", "Additional reviewed evidence", "file-search-2")
        if len(sources) >= 5:
            break
    return sources[:5]


def explicit_destinations(
    row: dict[str, object], affiliations: list[dict[str, object]]
) -> list[dict[str, str]]:
    """Return the primary destination plus source-explicit concurrent roles."""
    primary_organization = canonicalize_organization(row.get("organization"))
    if not primary_organization:
        return []

    primary_metadata = organization_metadata(
        primary_organization, row.get("organization_category", "")
    )
    destinations = [
        {
            "organization": display_organization(primary_organization),
            "role": str(row.get("role") or ""),
            "organizationType": primary_metadata["organization_type"],
            "sector": primary_metadata["sector"],
        }
    ]
    if primary_metadata["organization_type"] == "education":
        return destinations

    destination_review_text = " ".join(
        str(item.get("evidence_text") or "")
        for item in affiliations
        if str(item.get("evidence_kind") or "").casefold()
        == "destination_source_review"
    )
    if not re.search(r"\b(?:both|concurrent(?:ly)?)\b", destination_review_text, re.I):
        return destinations

    normalized_review_text = destination_review_text.casefold()
    seen = {primary_organization.casefold()}
    for item in affiliations:
        is_current = item.get("is_current") is True or str(
            item.get("is_current") or ""
        ).casefold() == "true"
        if (
            str(item.get("affiliation_type") or "").casefold() != "employment"
            or not is_current
        ):
            continue
        organization = canonicalize_organization(item.get("organization"))
        key = organization.casefold()
        display_name = display_organization(organization)
        if (
            not organization
            or key in seen
            or (
                key not in normalized_review_text
                and display_name.casefold() not in normalized_review_text
            )
        ):
            continue
        metadata = organization_metadata(organization, "employment")
        destinations.append(
            {
                "organization": display_name,
                "role": str(item.get("role") or ""),
                "organizationType": metadata["organization_type"],
                "sector": metadata["sector"],
            }
        )
        seen.add(key)
    return destinations


def compact_person(
    row: dict[str, object],
    location: dict[str, object] | None = None,
    affiliations: list[dict[str, object]] | None = None,
    audit_evidence: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    location = location or {}
    affiliations = affiliations or []
    audit_evidence = audit_evidence or []
    organization = canonicalize_organization(row["organization"])
    organization_classification = organization_metadata(
        organization, row.get("organization_category", "")
    )
    destinations = explicit_destinations(row, affiliations)
    alma_rows = selected_alma_maters(affiliations)
    alma_maters = [
        {
            "organization": display_organization(
                canonicalize_organization(item.get("organization"))
            ),
            "role": str(item.get("role") or ""),
        }
        for item in alma_rows
    ]
    history_terms: list[str] = []
    for item in affiliations:
        affiliation_organization = canonicalize_organization(item.get("organization"))
        history_terms.extend(
            value
            for value in (
                affiliation_organization,
                display_organization(affiliation_organization),
                *organization_aliases_for(affiliation_organization),
                str(item.get("role") or ""),
            )
            if value
        )
    history_terms.extend(organization_aliases_for(organization))
    history_terms = list(dict.fromkeys(history_terms))
    return {
        "id": row["person_id"],
        "name": row["name"],
        "aliases": [value for value in str(row.get("aliases", "")).split(";") if value],
        "olympiads": [value for value in str(row["olympiads"]).split(";") if value],
        "firstYear": int(row["first_year"]),
        "lastYear": int(row.get("last_year") or row["first_year"]),
        "awards": [value for value in str(row.get("awards", "")).split(";") if value],
        "confidence": row["confidence"],
        "organization": display_organization(organization),
        "role": row["role"],
        "destinations": destinations,
        "organizationCategory": row["organization_category"],
        "organizationType": organization_classification["organization_type"],
        "sector": organization_classification["sector"],
        "roleCategory": row["role_category"],
        "destinationStatus": row.get("destination_status", ""),
        "almaMater": "; ".join(item["organization"] for item in alma_maters),
        "almaMaterRole": "; ".join(
            f'{item["organization"]}: {item["role"]}'
            for item in alma_maters
            if item["role"]
        ),
        "almaMaters": alma_maters,
        "historyTerms": history_terms,
        "countryCode": location.get("country_code", ""),
        "country": location.get("country_name", ""),
        "location": location.get("location_label", ""),
        "locationConfidence": location.get("confidence", ""),
        "locationEvidenceKind": location.get("evidence_kind", ""),
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
