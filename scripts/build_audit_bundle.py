#!/usr/bin/env python3
"""Build normalized, source-linked audit tables for the research dataset."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urlparse

try:
    from scripts.organization_names import canonicalize_organization
except ModuleNotFoundError:  # Direct script execution adds scripts/ to sys.path.
    from organization_names import canonicalize_organization


AUDIT_PEOPLE_FIELDS = [
    "person_id",
    "name",
    "aliases",
    "olympiads",
    "years",
    "awards",
    "research_scope",
    "outcome_status",
    "organization",
    "role",
    "affiliation_type",
    "start_year",
    "end_year",
    "country_code",
    "organization_category",
    "role_category",
    "destination_status",
    "destination_note",
    "alma_mater",
    "alma_mater_source_url",
    "outcome_country_code",
    "outcome_country_name",
    "outcome_location_label",
    "outcome_country_source_url",
    "review_method",
    "traceability_status",
    "participation_evidence_count",
    "outcome_evidence_count",
    "candidate_evidence_count",
    "rejected_evidence_count",
    "evidence_total",
    "primary_profile_url",
    "linkedin_url",
    "audit_summary",
]

AUDIT_AFFILIATION_FIELDS = [
    "affiliation_id",
    "evidence_id",
    "source_id",
    "person_id",
    "name",
    "organization",
    "role",
    "affiliation_type",
    "start_year",
    "end_year",
    "is_current",
    "selected_as_alma_mater",
    "evidence_url",
    "evidence_kind",
    "confidence",
    "evidence_text",
]

AUDIT_LOCATION_FIELDS = [
    "location_id",
    "evidence_id",
    "source_id",
    "person_id",
    "name",
    "country_code",
    "country_name",
    "location_label",
    "evidence_url",
    "evidence_kind",
    "confidence",
    "review_reason",
]

AUDIT_ORGANIZATION_ALIAS_FIELDS = [
    "organization_alias_id",
    "alias",
    "canonical_name",
    "display_name",
    "merge_type",
    "rationale",
    "evidence_url",
]


def alma_mater_sort_key(row: dict[str, str]) -> tuple[int, int, str]:
    role = row.get("role", "").casefold()
    if re.search(r"\b(?:associate|bachelor|bsc|bs\b|beng|undergraduate|medical student)", role):
        degree_rank = 1
    elif re.search(r"\b(?:master|msc|ms\b|meng|mba|mph)", role):
        degree_rank = 2
    elif re.search(r"\b(?:ph\.?d|doctor|graduate student)", role):
        degree_rank = 3
    else:
        degree_rank = 4
    start_year = (
        int(row.get("start_year", "0"))
        if row.get("start_year", "").isdigit()
        else 9999
    )
    return degree_rank, start_year, row.get("organization", "").casefold()

AUDIT_ORGANIZATION_SECTOR_FIELDS = [
    "organization_sector_id",
    "canonical_name",
    "organization_type",
    "sector",
    "rationale",
]

AUDIT_DESTINATION_REVIEW_FIELDS = [
    "destination_review_id",
    "evidence_id",
    "source_id",
    "person_id",
    "name",
    "organization",
    "role",
    "affiliation_type",
    "start_year",
    "end_year",
    "evidence_url",
    "reviewed_at",
    "review_reason",
]

EVIDENCE_FIELDS = [
    "evidence_id",
    "person_id",
    "person_name",
    "claim_type",
    "claim_summary",
    "olympiad",
    "year",
    "award",
    "organization",
    "role",
    "source_id",
    "source_url",
    "secondary_url",
    "source_host",
    "source_kind",
    "provenance",
    "source_adapter",
    "external_record_id",
    "review_status",
    "confidence",
    "supports_final_outcome",
    "evidence_text",
    "review_note",
]

SOURCE_FIELDS = [
    "source_id",
    "source_url",
    "source_host",
    "source_kind",
    "evidence_rows",
    "people_count",
    "accepted_rows",
    "supporting_rows",
    "candidate_rows",
    "superseded_rows",
    "rejected_rows",
    "provenances",
    "source_adapters",
]

PARTICIPATION_FIELDS = [
    "participation_id",
    "evidence_id",
    "person_id",
    "canonical_name",
    "recorded_name",
    "olympiad",
    "country",
    "country_code",
    "year",
    "award",
    "rank",
    "score",
    "person_url",
    "source_url",
    "source_type",
]

REJECTION_FIELDS = [
    "person_id",
    "person_name",
    "source_id",
    "evidence_url",
    "reason",
    "review_evidence_url",
]


def clean_text(value: object) -> str:
    text = "" if value is None else str(value)
    return re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()


def normalize_name(value: str) -> str:
    value = clean_text(value).casefold()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", value)).strip()


def normalize_url(value: str) -> str:
    return clean_text(value).rstrip("/")


def stable_id(prefix: str, *parts: object, length: int = 16) -> str:
    payload = "|".join(clean_text(part) for part in parts)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:length]
    return f"{prefix}-{digest}"


def source_id_for(url: str) -> str:
    return stable_id("src", normalize_url(url), length=12)


def source_kind_for(url: str, hint: str = "") -> str:
    hint = clean_text(hint).casefold()
    host = urlparse(url).netloc.casefold().removeprefix("www.")
    path = urlparse(url).path.casefold()
    if path.endswith(".pdf") or hint == "pdf":
        return "pdf"
    if "linkedin.com" in host:
        return "linkedin"
    if host in {"orcid.org", "openalex.org", "github.com", "codeforces.com", "wikidata.org", "cphof.org"}:
        return "structured_profile"
    if hint in {"json", "html", "api"}:
        return hint
    return "web_page"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_rows(path: Path, rows: list[dict[str, object]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows({field: row.get(field, "") for field in fields} for row in rows)
    path.with_suffix(".json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def aliases_to_people(people: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    people_by_alias: dict[str, dict[str, str]] = {}
    for person in people:
        aliases = [person.get("canonical_name", "")]
        aliases.extend(clean_text(person.get("aliases")).split(";"))
        for alias in aliases:
            key = normalize_name(alias)
            if not key:
                continue
            existing = people_by_alias.get(key)
            if existing and existing["person_id"] != person["person_id"]:
                raise ValueError(f"ambiguous canonical alias: {alias}")
            people_by_alias[key] = person
    return people_by_alias


def build_participations(
    participants: list[dict[str, str]], people: list[dict[str, str]]
) -> list[dict[str, object]]:
    people_by_alias = aliases_to_people(people)
    output: list[dict[str, object]] = []
    for row in participants:
        person = people_by_alias.get(normalize_name(row.get("name", "")))
        if not person:
            raise ValueError(f"participant is not mapped to a person: {row.get('name')}")
        participation_id = stable_id(
            "part",
            person["person_id"],
            row.get("olympiad"),
            row.get("year"),
            row.get("name"),
            row.get("source_url"),
        )
        output.append(
            {
                "participation_id": participation_id,
                "evidence_id": "",
                "person_id": person["person_id"],
                "canonical_name": person["canonical_name"],
                "recorded_name": row.get("name", ""),
                "olympiad": row.get("olympiad", ""),
                "country": row.get("country", ""),
                "country_code": row.get("country_code", ""),
                "year": row.get("year", ""),
                "award": row.get("award", ""),
                "rank": row.get("rank", ""),
                "score": row.get("score", ""),
                "person_url": row.get("person_url", ""),
                "source_url": row.get("source_url", ""),
                "source_type": row.get("source_type", ""),
            }
        )
    return output


def add_evidence(
    rows: list[dict[str, object]],
    seen: set[str],
    *,
    person_id: str,
    person_name: str,
    claim_type: str,
    claim_summary: str,
    source_url: str,
    provenance: str,
    source_adapter: str,
    review_status: str,
    confidence: str,
    supports_final_outcome: bool,
    secondary_url: str = "",
    source_kind_hint: str = "",
    external_record_id: str = "",
    olympiad: str = "",
    year: str = "",
    award: str = "",
    organization: str = "",
    role: str = "",
    evidence_text: str = "",
    review_note: str = "",
) -> str:
    source_url = clean_text(source_url)
    if not source_url:
        return ""
    source_id = source_id_for(source_url)
    evidence_id = stable_id(
        "ev",
        person_id,
        claim_type,
        source_id,
        external_record_id,
        claim_summary,
    )
    if evidence_id in seen:
        return evidence_id
    seen.add(evidence_id)
    rows.append(
        {
            "evidence_id": evidence_id,
            "person_id": person_id,
            "person_name": person_name,
            "claim_type": claim_type,
            "claim_summary": claim_summary,
            "olympiad": olympiad,
            "year": year,
            "award": award,
            "organization": organization,
            "role": role,
            "source_id": source_id,
            "source_url": source_url,
            "secondary_url": clean_text(secondary_url),
            "source_host": urlparse(source_url).netloc.casefold().removeprefix("www."),
            "source_kind": source_kind_for(source_url, source_kind_hint),
            "provenance": provenance,
            "source_adapter": source_adapter,
            "external_record_id": external_record_id,
            "review_status": review_status,
            "confidence": confidence,
            "supports_final_outcome": supports_final_outcome,
            "evidence_text": clean_text(evidence_text),
            "review_note": clean_text(review_note),
        }
    )
    return evidence_id


def build_evidence(
    participations: list[dict[str, object]],
    researched: list[dict[str, str]],
    identities: list[dict[str, str]],
    affiliations: list[dict[str, str]],
    verified: list[dict[str, str]],
    rejections: list[dict[str, str]],
    destination_reviews: list[dict[str, str]] | None = None,
) -> list[dict[str, object]]:
    final_by_person = {row["person_id"]: row for row in researched}
    verified_by_person = {row["person_id"]: row for row in verified}
    destination_review_by_person = {
        row["person_id"]: row for row in destination_reviews or []
    }
    rejection_by_key = {
        (row["person_id"], normalize_url(row.get("evidence_url", ""))): row
        for row in rejections
    }
    rows: list[dict[str, object]] = []
    seen: set[str] = set()

    for row in participations:
        source_url = clean_text(row.get("person_url")) or clean_text(row.get("source_url"))
        archive_url = clean_text(row.get("source_url"))
        award = clean_text(row.get("award")) or "Participant"
        summary = f"{row['olympiad']} {row['year']}: {award}"
        row["evidence_id"] = add_evidence(
            rows,
            seen,
            person_id=str(row["person_id"]),
            person_name=str(row["canonical_name"]),
            claim_type="olympiad_participation",
            claim_summary=summary,
            source_url=source_url,
            secondary_url=archive_url if normalize_url(archive_url) != normalize_url(source_url) else "",
            source_kind_hint=str(row.get("source_type", "")),
            provenance="participant_registry",
            source_adapter=str(row["olympiad"]),
            external_record_id=str(row["participation_id"]),
            review_status="accepted",
            confidence="confirmed",
            supports_final_outcome=False,
            olympiad=str(row["olympiad"]),
            year=str(row["year"]),
            award=str(row.get("award", "")),
            evidence_text=f"Recorded name: {row['recorded_name']}",
        )

    for row in verified:
        person_id = row["person_id"]
        name = clean_text(row.get("name")) or final_by_person[person_id]["name"]
        confidence = clean_text(row.get("confidence")) or "confirmed"
        basis = row.get("verification_basis", "")
        has_outcome = bool(
            canonicalize_organization(row.get("organization"))
            and clean_text(row.get("role"))
            and clean_text(row.get("affiliation_type"))
        )
        identity_source_url = (
            row.get("olympiad_evidence_url", "")
            if has_outcome
            else row.get("career_evidence_url", "")
            or row.get("olympiad_evidence_url", "")
        )
        identity_secondary_url = (
            ""
            if has_outcome
            else row.get("olympiad_evidence_url", "")
        )
        destination_review = destination_review_by_person.get(person_id)
        destination_superseded = bool(
            destination_review
            and (
                canonicalize_organization(row.get("organization"))
                != canonicalize_organization(destination_review.get("organization"))
                or clean_text(row.get("role"))
                != clean_text(destination_review.get("role"))
                or clean_text(row.get("affiliation_type"))
                != clean_text(destination_review.get("affiliation_type"))
                or clean_text(row.get("start_year"))
                != clean_text(destination_review.get("start_year"))
                or clean_text(row.get("end_year"))
                != clean_text(destination_review.get("end_year"))
            )
        )
        add_evidence(
            rows,
            seen,
            person_id=person_id,
            person_name=name,
            claim_type="olympiad_identity_bridge",
            claim_summary=f"Reviewed Olympiad identity evidence for {name}",
            source_url=identity_source_url,
            secondary_url=identity_secondary_url,
            provenance="manual_review",
            source_adapter="manual",
            review_status="accepted",
            confidence=confidence,
            supports_final_outcome=has_outcome,
            evidence_text=basis,
            review_note=basis,
        )
        if has_outcome:
            add_evidence(
                rows,
                seen,
                person_id=person_id,
                person_name=name,
                claim_type="career_outcome",
                claim_summary=f"{row.get('role') or 'Affiliation'} at {row.get('organization')}",
                source_url=row.get("career_evidence_url", ""),
                provenance="manual_review",
                source_adapter="manual",
                review_status="superseded" if destination_superseded else "accepted",
                confidence=confidence,
                supports_final_outcome=not destination_superseded,
                organization=row.get("organization", ""),
                role=row.get("role", ""),
                evidence_text=basis,
                review_note=basis,
            )
        add_evidence(
            rows,
            seen,
            person_id=person_id,
            person_name=name,
            claim_type="public_profile",
            claim_summary=f"Public LinkedIn profile for {name}",
            source_url=row.get("linkedin_url", ""),
            provenance="manual_review",
            source_adapter="linkedin",
            review_status="supporting",
            confidence=confidence,
            supports_final_outcome=has_outcome,
            review_note=basis,
        )

    for row in identities:
        person_id = row["person_id"]
        if person_id not in final_by_person:
            continue
        final = final_by_person[person_id]
        source_url = clean_text(row.get("evidence_url")) or clean_text(row.get("profile_url"))
        rejection = rejection_by_key.get((person_id, normalize_url(source_url)))
        final_urls = {
            normalize_url(url)
            for url in clean_text(final.get("evidence_urls")).split(";")
            if clean_text(url)
        }
        final_urls.update(
            normalize_url(final.get(field, ""))
            for field in ("profile_url", "linkedin_url")
            if clean_text(final.get(field, ""))
        )
        selected = (
            person_id not in verified_by_person
            and normalize_url(row.get("profile_url", "")) == normalize_url(final.get("profile_url", ""))
            and bool(normalize_url(final.get("profile_url", "")))
        )
        supports_destination = final.get("destination_status") != "none"
        if rejection:
            status = "rejected"
        elif selected:
            status = "accepted"
        elif (
            normalize_url(source_url) in final_urls
            and row.get("confidence") in {"probable", "confirmed"}
        ):
            status = "supporting"
        else:
            status = "candidate"
        add_evidence(
            rows,
            seen,
            person_id=person_id,
            person_name=final["name"],
            claim_type="identity_candidate",
            claim_summary=f"Identity candidate from {row.get('source')}: {row.get('matched_name') or final['name']}",
            source_url=source_url,
            provenance="structured_identity",
            source_adapter=row.get("source", ""),
            external_record_id=row.get("source_id", ""),
            review_status=status,
            confidence=row.get("confidence", "candidate"),
            supports_final_outcome=(selected or status == "supporting")
            and supports_destination,
            organization=row.get("organization", ""),
            role=row.get("role", ""),
            evidence_text=row.get("evidence_text", ""),
            review_note=(
                rejection.get("reason", "") if rejection else row.get("score_reasons", "")
            ),
        )

    for row in affiliations:
        person_id = row["person_id"]
        if person_id not in final_by_person:
            continue
        final = final_by_person[person_id]
        source_url = clean_text(row.get("evidence_url"))
        rejection = rejection_by_key.get((person_id, normalize_url(source_url)))
        final_urls = {
            normalize_url(url)
            for url in clean_text(final.get("evidence_urls")).split(";")
            if clean_text(url)
        }
        final_urls.update(
            normalize_url(final.get(field, ""))
            for field in ("profile_url", "linkedin_url")
            if clean_text(final.get(field, ""))
        )
        selected = (
            person_id not in verified_by_person
            and canonicalize_organization(row.get("organization"))
            == clean_text(final.get("organization"))
            and clean_text(row.get("role")) == clean_text(final.get("role"))
            and clean_text(row.get("affiliation_type")) == clean_text(final.get("affiliation_type"))
            and final.get("confidence") != "unmatched"
        )
        supports_destination = final.get("destination_status") != "none"
        if rejection:
            status = "rejected"
        elif selected:
            status = "accepted"
        elif (
            normalize_url(source_url) in final_urls
            and row.get("confidence") in {"probable", "confirmed"}
        ):
            status = "supporting"
        else:
            status = "candidate"
        add_evidence(
            rows,
            seen,
            person_id=person_id,
            person_name=final["name"],
            claim_type="affiliation_candidate",
            claim_summary=f"{row.get('role') or 'Affiliation'} at {row.get('organization')}",
            source_url=source_url,
            provenance="structured_affiliation",
            source_adapter=row.get("source", ""),
            review_status=status,
            confidence=row.get("confidence", "candidate"),
            supports_final_outcome=(selected or status == "supporting")
            and supports_destination,
            organization=row.get("organization", ""),
            role=row.get("role", ""),
            evidence_text=row.get("evidence_text", ""),
            review_note=rejection.get("reason", "") if rejection else "",
        )

    for row in rejections:
        person_id = row["person_id"]
        final = final_by_person[person_id]
        add_evidence(
            rows,
            seen,
            person_id=person_id,
            person_name=final["name"],
            claim_type="identity_review",
            claim_summary=f"Rejected identity candidate for {final['name']}",
            source_url=row.get("evidence_url", ""),
            secondary_url=row.get("review_evidence_url", ""),
            provenance="review_rejection",
            source_adapter="manual",
            review_status="rejected",
            confidence="unmatched",
            supports_final_outcome=False,
            evidence_text=row.get("reason", ""),
            review_note=row.get("reason", ""),
        )

    return sorted(
        rows,
        key=lambda row: (
            str(row["person_id"]),
            str(row["claim_type"]),
            str(row["source_url"]),
            str(row["evidence_id"]),
        ),
    )


def build_audit_people(
    researched: list[dict[str, str]],
    verified: list[dict[str, str]],
    evidence: list[dict[str, object]],
    locations: list[dict[str, str]] | None = None,
    affiliation_history: list[dict[str, str]] | None = None,
) -> list[dict[str, object]]:
    verified_ids = {row["person_id"] for row in verified}
    evidence_by_person: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in evidence:
        evidence_by_person[str(row["person_id"])].append(row)
    locations_by_person = {
        row["person_id"]: row for row in locations or [] if row.get("person_id")
    }
    alma_by_person: dict[str, list[dict[str, str]]] = defaultdict(list)
    for alma_row in affiliation_history or []:
        if alma_row.get("selected_as_alma_mater", "").casefold() == "true":
            alma_by_person[alma_row["person_id"]].append(alma_row)

    output: list[dict[str, object]] = []
    for row in researched:
        person_evidence = evidence_by_person[row["person_id"]]
        participation_count = sum(
            item["claim_type"] == "olympiad_participation" for item in person_evidence
        )
        outcome_count = sum(
            bool(item["supports_final_outcome"])
            and item["review_status"] in {"accepted", "supporting"}
            for item in person_evidence
        )
        candidate_count = sum(
            item["review_status"] == "candidate" for item in person_evidence
        )
        rejected_count = sum(
            item["review_status"] == "rejected" for item in person_evidence
        )
        if (
            row["confidence"] in {"probable", "confirmed"}
            and row.get("destination_status") == "none"
        ):
            identity_count = sum(
                item["claim_type"]
                in {"olympiad_identity_bridge", "identity_candidate"}
                and item["review_status"] == "accepted"
                for item in person_evidence
            )
            traceability = (
                "identity_verified"
                if participation_count and identity_count
                else "incomplete"
            )
        elif row["confidence"] in {"probable", "confirmed"}:
            traceability = "complete" if participation_count and outcome_count else "incomplete"
        elif candidate_count:
            traceability = "review_required"
        else:
            traceability = "participation_only"
        location = locations_by_person.get(row["person_id"], {})
        alma_rows = sorted(
            alma_by_person.get(row["person_id"], []),
            key=alma_mater_sort_key,
        )
        output.append(
            {
                "person_id": row["person_id"],
                "name": row["name"],
                "aliases": row["aliases"],
                "olympiads": row["olympiads"],
                "years": row["years"],
                "awards": row["awards"],
                "research_scope": row["research_scope"],
                "outcome_status": row["confidence"],
                "organization": row["organization"],
                "role": row["role"],
                "affiliation_type": row["affiliation_type"],
                "start_year": row["start_year"],
                "end_year": row["end_year"],
                "country_code": row["country_code"],
                "organization_category": row["organization_category"],
                "role_category": row["role_category"],
                "destination_status": row.get("destination_status", ""),
                "destination_note": row.get("destination_note", ""),
                "alma_mater": "; ".join(
                    dict.fromkeys(item.get("organization", "") for item in alma_rows)
                ),
                "alma_mater_source_url": "; ".join(
                    dict.fromkeys(item.get("evidence_url", "") for item in alma_rows)
                ),
                "outcome_country_code": location.get("country_code", ""),
                "outcome_country_name": location.get("country_name", ""),
                "outcome_location_label": location.get("location_label", ""),
                "outcome_country_source_url": location.get("evidence_url", ""),
                "review_method": (
                    "manual_review"
                    if row["person_id"] in verified_ids
                    else "structured_sources"
                    if row["confidence"] != "unmatched"
                    else "unmatched"
                ),
                "traceability_status": traceability,
                "participation_evidence_count": participation_count,
                "outcome_evidence_count": outcome_count,
                "candidate_evidence_count": candidate_count,
                "rejected_evidence_count": rejected_count,
                "evidence_total": len(person_evidence),
                "primary_profile_url": row["profile_url"],
                "linkedin_url": row["linkedin_url"],
                "audit_summary": row["verification_basis"],
            }
        )
    return output


def append_affiliation_history_evidence(
    evidence: list[dict[str, object]],
    researched: list[dict[str, str]],
    affiliation_history: list[dict[str, str]],
) -> list[dict[str, object]]:
    final_by_person = {row["person_id"]: row for row in researched}
    seen = {str(row["evidence_id"]) for row in evidence}
    audit_rows: list[dict[str, object]] = []
    for row in affiliation_history:
        person_id = row["person_id"]
        final = final_by_person[person_id]
        claim_type = (
            "education_history"
            if row.get("affiliation_type") == "education"
            else "employment_history"
        )
        claim_summary = f"{row.get('role') or 'Affiliation'} at {row.get('organization')}"
        evidence_id = add_evidence(
            evidence,
            seen,
            person_id=person_id,
            person_name=final["name"],
            claim_type=claim_type,
            claim_summary=claim_summary,
            source_url=row.get("evidence_url", ""),
            provenance="accepted_affiliation_history",
            source_adapter=row.get("evidence_kind", ""),
            review_status="supporting",
            confidence=row.get("confidence", "probable"),
            supports_final_outcome=(
                clean_text(row.get("organization")) == clean_text(final.get("organization"))
                and clean_text(row.get("role")) == clean_text(final.get("role"))
                and bool(clean_text(final.get("organization")))
            ),
            organization=row.get("organization", ""),
            role=row.get("role", ""),
            evidence_text=row.get("evidence_text", ""),
        )
        source_url = row.get("evidence_url", "")
        audit_rows.append(
            {
                "affiliation_id": stable_id(
                    "aff",
                    person_id,
                    row.get("affiliation_type", ""),
                    row.get("organization", ""),
                    row.get("role", ""),
                    row.get("start_year", ""),
                    row.get("end_year", ""),
                    normalize_url(source_url),
                ),
                "evidence_id": evidence_id,
                "source_id": source_id_for(source_url),
                **row,
            }
        )
    return audit_rows


def append_destination_review_evidence(
    evidence: list[dict[str, object]],
    researched: list[dict[str, str]],
    destination_reviews: list[dict[str, str]],
) -> list[dict[str, object]]:
    final_by_person = {row["person_id"]: row for row in researched}
    seen = {str(row["evidence_id"]) for row in evidence}
    output: list[dict[str, object]] = []
    for review in destination_reviews:
        person_id = clean_text(review.get("person_id"))
        final = final_by_person.get(person_id)
        if not final:
            raise ValueError(f"destination review has unknown person: {person_id}")
        expected = {
            "organization": canonicalize_organization(review.get("organization")),
            "role": clean_text(review.get("role")),
            "affiliation_type": clean_text(review.get("affiliation_type")),
            "start_year": clean_text(review.get("start_year")),
            "end_year": clean_text(review.get("end_year")),
        }
        mismatches = [
            field
            for field, value in expected.items()
            if clean_text(final.get(field)) != value
        ]
        if mismatches:
            raise ValueError(
                f"destination review was not published for {person_id}: "
                + ", ".join(mismatches)
            )
        source_url = clean_text(review.get("evidence_url"))
        summary = f"{expected['role'] or 'Affiliation'} at {expected['organization']}"
        evidence_id = add_evidence(
            evidence,
            seen,
            person_id=person_id,
            person_name=final["name"],
            claim_type="destination_source_review",
            claim_summary=summary,
            source_url=source_url,
            provenance="manual_destination_reconciliation",
            source_adapter="destination_review",
            review_status="accepted",
            confidence=final.get("confidence", "confirmed"),
            supports_final_outcome=True,
            organization=expected["organization"],
            role=expected["role"],
            evidence_text=review.get("review_reason", ""),
            review_note=review.get("review_reason", ""),
        )
        normalized_review = dict(review)
        normalized_review["organization"] = expected["organization"]
        output.append(
            {
                "destination_review_id": stable_id(
                    "dest-review", person_id, source_url, review.get("reviewed_at", "")
                ),
                "evidence_id": evidence_id,
                "source_id": source_id_for(source_url),
                **{
                    field: normalized_review.get(field, "")
                    for field in AUDIT_DESTINATION_REVIEW_FIELDS[3:]
                },
            }
        )
    return sorted(output, key=lambda row: clean_text(row.get("name")).casefold())


def append_location_evidence(
    evidence: list[dict[str, object]],
    researched: list[dict[str, str]],
    locations: list[dict[str, str]],
) -> list[dict[str, object]]:
    final_by_person = {row["person_id"]: row for row in researched}
    seen = {str(row["evidence_id"]) for row in evidence}
    audit_rows: list[dict[str, object]] = []
    for row in locations:
        person_id = row["person_id"]
        final = final_by_person[person_id]
        source_url = row.get("evidence_url", "")
        claim_summary = f"Outcome country: {row.get('country_name')}"
        evidence_id = add_evidence(
            evidence,
            seen,
            person_id=person_id,
            person_name=final["name"],
            claim_type="outcome_country",
            claim_summary=claim_summary,
            source_url=source_url,
            provenance="accepted_location_evidence",
            source_adapter=row.get("evidence_kind", ""),
            review_status="supporting",
            confidence=row.get("confidence", "probable"),
            supports_final_outcome=False,
            evidence_text=row.get("review_reason", ""),
        )
        audit_rows.append(
            {
                "location_id": stable_id(
                    "loc", person_id, row.get("country_code", ""), normalize_url(source_url)
                ),
                "evidence_id": evidence_id,
                "source_id": source_id_for(source_url),
                **row,
            }
        )
    return audit_rows


def build_sources(evidence: list[dict[str, object]]) -> list[dict[str, object]]:
    by_source: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in evidence:
        by_source[str(row["source_id"])].append(row)
    output: list[dict[str, object]] = []
    for source_id, rows in by_source.items():
        first = rows[0]
        statuses = Counter(str(row["review_status"]) for row in rows)
        output.append(
            {
                "source_id": source_id,
                "source_url": first["source_url"],
                "source_host": first["source_host"],
                "source_kind": first["source_kind"],
                "evidence_rows": len(rows),
                "people_count": len({str(row["person_id"]) for row in rows}),
                "accepted_rows": statuses["accepted"],
                "supporting_rows": statuses["supporting"],
                "candidate_rows": statuses["candidate"],
                "superseded_rows": statuses["superseded"],
                "rejected_rows": statuses["rejected"],
                "provenances": ";".join(sorted({str(row["provenance"]) for row in rows})),
                "source_adapters": ";".join(sorted({str(row["source_adapter"]) for row in rows})),
            }
        )
    return sorted(output, key=lambda row: str(row["source_url"]))


def build_audit_rejections(
    rejections: list[dict[str, str]], researched: list[dict[str, str]]
) -> list[dict[str, object]]:
    names = {row["person_id"]: row["name"] for row in researched}
    return [
        {
            "person_id": row["person_id"],
            "person_name": names[row["person_id"]],
            "source_id": source_id_for(row["evidence_url"]),
            "evidence_url": row["evidence_url"],
            "reason": row["reason"],
            "review_evidence_url": row.get("review_evidence_url", ""),
        }
        for row in rejections
    ]


def build_audit_organization_aliases(
    aliases: list[dict[str, str]],
) -> list[dict[str, object]]:
    return sorted(
        [
            {
                "organization_alias_id": stable_id(
                    "org", row.get("alias", ""), row.get("canonical_name", "")
                ),
                "alias": clean_text(row.get("alias")),
                "canonical_name": clean_text(row.get("canonical_name")),
                "display_name": clean_text(row.get("display_name")),
                "merge_type": clean_text(row.get("merge_type")),
                "rationale": clean_text(row.get("rationale")),
                "evidence_url": clean_text(row.get("evidence_url")),
            }
            for row in aliases
        ],
        key=lambda row: (
            clean_text(row.get("canonical_name")).casefold(),
            clean_text(row.get("alias")).casefold(),
        ),
    )


def build_audit_organization_sectors(
    sectors: list[dict[str, str]],
) -> list[dict[str, object]]:
    return sorted(
        [
            {
                "organization_sector_id": stable_id(
                    "sector", row.get("canonical_name", "")
                ),
                **row,
            }
            for row in sectors
        ],
        key=lambda row: clean_text(row.get("canonical_name")).casefold(),
    )


def build_bundle(
    participants: list[dict[str, str]],
    people: list[dict[str, str]],
    researched: list[dict[str, str]],
    identities: list[dict[str, str]],
    affiliations: list[dict[str, str]],
    verified: list[dict[str, str]],
    rejections: list[dict[str, str]],
    locations: list[dict[str, str]] | None = None,
    affiliation_history: list[dict[str, str]] | None = None,
    organization_aliases: list[dict[str, str]] | None = None,
    organization_sectors: list[dict[str, str]] | None = None,
    destination_reviews: list[dict[str, str]] | None = None,
) -> dict[str, object]:
    participations = build_participations(participants, people)
    evidence = build_evidence(
        participations,
        researched,
        identities,
        affiliations,
        verified,
        rejections,
        destination_reviews,
    )
    audit_affiliations = append_affiliation_history_evidence(
        evidence, researched, affiliation_history or []
    )
    audit_locations = append_location_evidence(evidence, researched, locations or [])
    audit_destination_reviews = append_destination_review_evidence(
        evidence, researched, destination_reviews or []
    )
    audit_people = build_audit_people(
        researched, verified, evidence, locations, affiliation_history
    )
    sources = build_sources(evidence)
    audit_rejections = build_audit_rejections(rejections, researched)
    audit_organization_aliases = build_audit_organization_aliases(
        organization_aliases or []
    )
    audit_organization_sectors = build_audit_organization_sectors(
        organization_sectors or []
    )
    manifest = {
        "schema_version": 6,
        "primary_key": {
            "people": "person_id",
            "affiliations": "affiliation_id",
            "locations": "location_id",
            "organization_aliases": "organization_alias_id",
            "organization_sectors": "organization_sector_id",
            "destination_reviews": "destination_review_id",
            "evidence": "evidence_id",
            "sources": "source_id",
        },
        "joins": [
            "people.person_id = evidence.person_id",
            "evidence.source_id = sources.source_id",
            "participations.evidence_id = evidence.evidence_id",
            "affiliations.evidence_id = evidence.evidence_id",
            "affiliations.source_id = sources.source_id",
            "locations.evidence_id = evidence.evidence_id",
            "locations.source_id = sources.source_id",
            "destination_reviews.evidence_id = evidence.evidence_id",
            "destination_reviews.source_id = sources.source_id",
        ],
        "review_statuses": ["accepted", "supporting", "candidate", "superseded", "rejected"],
        "counts": {
            "people": len(audit_people),
            "participations": len(participations),
            "affiliations": len(audit_affiliations),
            "locations": len(audit_locations),
            "organization_aliases": len(audit_organization_aliases),
            "organization_sectors": len(audit_organization_sectors),
            "destination_reviews": len(audit_destination_reviews),
            "evidence_rows": len(evidence),
            "sources": len(sources),
            "rejections": len(audit_rejections),
            "complete_outcomes": sum(
                row["traceability_status"] == "complete" for row in audit_people
            ),
            "resolved_destinations": sum(
                bool(clean_text(row.get("organization"))) for row in researched
            ),
            "verified_identities": sum(
                row.get("confidence") in {"probable", "confirmed"}
                for row in researched
            ),
            "confirmed_identities": sum(
                row.get("confidence") == "confirmed" for row in researched
            ),
            "probable_identities": sum(
                row.get("confidence") == "probable" for row in researched
            ),
            "identity_only_people": sum(
                row.get("confidence") in {"probable", "confirmed"}
                and row.get("destination_status") == "none"
                for row in researched
            ),
            "candidate_only_people": sum(
                row.get("confidence") == "candidate" for row in researched
            ),
            "unmatched_people": sum(
                row.get("confidence") == "unmatched" for row in researched
            ),
        },
    }
    return {
        "people": audit_people,
        "participations": participations,
        "affiliations": audit_affiliations,
        "locations": audit_locations,
        "organization_aliases": audit_organization_aliases,
        "organization_sectors": audit_organization_sectors,
        "destination_reviews": audit_destination_reviews,
        "evidence": evidence,
        "sources": sources,
        "rejections": audit_rejections,
        "manifest": manifest,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--participants-csv", default="data/kazakhstan_participants.csv")
    parser.add_argument("--people-csv", default="data/people.csv")
    parser.add_argument("--researched-csv", default="data/researched_people.csv")
    parser.add_argument("--identity-csv", default="data/identity_candidates.csv")
    parser.add_argument("--affiliation-csv", default="data/affiliation_candidates.csv")
    parser.add_argument("--verified-csv", default="data/verified_evidence.csv")
    parser.add_argument("--rejections-csv", default="data/rejected_identity_candidates.csv")
    parser.add_argument("--locations-csv", default="data/person_locations.csv")
    parser.add_argument("--affiliation-history-csv", default="data/person_affiliations.csv")
    parser.add_argument("--organization-aliases-csv", default="data/organization_aliases.csv")
    parser.add_argument("--organization-sectors-csv", default="data/organization_sectors.csv")
    parser.add_argument("--destination-reviews-csv", default="data/destination_reviews.csv")
    parser.add_argument("--out-dir", default="data/audit")
    args = parser.parse_args()

    bundle = build_bundle(
        read_csv(Path(args.participants_csv)),
        read_csv(Path(args.people_csv)),
        read_csv(Path(args.researched_csv)),
        read_csv(Path(args.identity_csv)),
        read_csv(Path(args.affiliation_csv)),
        read_csv(Path(args.verified_csv)),
        read_csv(Path(args.rejections_csv)),
        read_csv(Path(args.locations_csv)),
        read_csv(Path(args.affiliation_history_csv)),
        read_csv(Path(args.organization_aliases_csv)),
        read_csv(Path(args.organization_sectors_csv)),
        read_csv(Path(args.destination_reviews_csv)),
    )
    output_dir = Path(args.out_dir)
    write_rows(output_dir / "people.csv", bundle["people"], AUDIT_PEOPLE_FIELDS)
    write_rows(
        output_dir / "participations.csv", bundle["participations"], PARTICIPATION_FIELDS
    )
    write_rows(
        output_dir / "affiliations.csv", bundle["affiliations"], AUDIT_AFFILIATION_FIELDS
    )
    write_rows(output_dir / "locations.csv", bundle["locations"], AUDIT_LOCATION_FIELDS)
    write_rows(
        output_dir / "organization_aliases.csv",
        bundle["organization_aliases"],
        AUDIT_ORGANIZATION_ALIAS_FIELDS,
    )
    write_rows(
        output_dir / "organization_sectors.csv",
        bundle["organization_sectors"],
        AUDIT_ORGANIZATION_SECTOR_FIELDS,
    )
    write_rows(
        output_dir / "destination_reviews.csv",
        bundle["destination_reviews"],
        AUDIT_DESTINATION_REVIEW_FIELDS,
    )
    write_rows(output_dir / "evidence.csv", bundle["evidence"], EVIDENCE_FIELDS)
    write_rows(output_dir / "sources.csv", bundle["sources"], SOURCE_FIELDS)
    write_rows(output_dir / "rejections.csv", bundle["rejections"], REJECTION_FIELDS)
    (output_dir / "manifest.json").write_text(
        json.dumps(bundle["manifest"], ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(bundle["manifest"]["counts"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
