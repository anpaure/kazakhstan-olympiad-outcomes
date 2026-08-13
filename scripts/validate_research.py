#!/usr/bin/env python3
"""Validate the canonical registry and assembled research dataset."""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

try:
    from scripts.build_affiliation_history import (
        NON_CHRONOLOGICAL_DIRECTORY_SOURCES,
        extract_affiliations,
        valid_affiliation,
    )
    from scripts.build_exa_review_queue import canonical_url
    from scripts.build_profile_sanity_review import (
        ERA_CUTOFF_YEAR,
        SAMPLE_PER_STRATUM,
        SAMPLE_SEED,
        build_reconciliation,
        load_review_decisions,
        select_sample,
    )
    from scripts.build_research_dataset import (
        identity_urls,
        linkedin_profile_slug,
        preferred_manual_profile_url,
    )
    from scripts.build_location_evidence import (
        COUNTRY_NAMES,
        TRUSTED_OVERRIDE_KINDS,
        load_overrides,
        load_organization_locations,
    )
    from scripts.destination_reviews import load_destination_reviews
    from scripts.organization_names import (
        canonicalize_organization,
        display_organization,
        load_organization_aliases,
        organization_audit_key,
        organization_key,
    )
    from scripts.organization_sectors import (
        load_organization_sectors,
        organization_metadata,
    )
except ModuleNotFoundError:  # Direct script execution adds scripts/ to sys.path.
    from build_affiliation_history import (
        NON_CHRONOLOGICAL_DIRECTORY_SOURCES,
        extract_affiliations,
        valid_affiliation,
    )
    from build_exa_review_queue import canonical_url
    from build_profile_sanity_review import (
        ERA_CUTOFF_YEAR,
        SAMPLE_PER_STRATUM,
        SAMPLE_SEED,
        build_reconciliation,
        load_review_decisions,
        select_sample,
    )
    from build_research_dataset import (
        identity_urls,
        linkedin_profile_slug,
        preferred_manual_profile_url,
    )
    from build_location_evidence import (
        COUNTRY_NAMES,
        TRUSTED_OVERRIDE_KINDS,
        load_overrides,
        load_organization_locations,
    )
    from destination_reviews import load_destination_reviews
    from organization_names import (
        canonicalize_organization,
        display_organization,
        load_organization_aliases,
        organization_audit_key,
        organization_key,
    )
    from organization_sectors import load_organization_sectors, organization_metadata


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_DIR = ROOT / "data"
CONFIDENCE_LEVELS = {"unmatched", "candidate", "probable", "confirmed"}
OLYMPIADS = {"IMO", "IOI", "IPhO", "IBO", "IChO"}
AUDIT_REVIEW_STATUSES = {
    "accepted",
    "supporting",
    "candidate",
    "superseded",
    "rejected",
}
DATA_AS_OF_YEAR = 2026
STRUCTURED_RESEARCH_AFFILIATION_KINDS = {
    "accepted_openalex",
    "accepted_openalex_orcid",
    "accepted_orcid",
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def split_values(value: str) -> set[str]:
    return {item.strip() for item in value.split(";") if item.strip()}


def structured_alma_timeline_conflicts(
    affiliations: list[dict[str, str]], minimum_overlap_years: int = 2
) -> list[tuple[str, str, str, str]]:
    """Find structured alma rows that contradict a separately trusted degree."""

    by_person: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in affiliations:
        by_person[row.get("person_id", "")].append(row)

    conflicts: set[tuple[str, str, str, str]] = set()
    for person_id, rows in by_person.items():
        structured_rows = [
            row
            for row in rows
            if row.get("evidence_kind") in STRUCTURED_RESEARCH_AFFILIATION_KINDS
            and row.get("affiliation_type") == "education"
            and row.get("selected_as_alma_mater", "").casefold() == "true"
            and row.get("start_year", "").isdigit()
            and row.get("end_year", "").isdigit()
        ]
        trusted_rows = [
            row
            for row in rows
            if row.get("evidence_kind") not in STRUCTURED_RESEARCH_AFFILIATION_KINDS
            and row.get("affiliation_type") == "education"
            and row.get("selected_as_alma_mater", "").casefold() == "true"
            and row.get("start_year", "").isdigit()
            and row.get("end_year", "").isdigit()
        ]
        trusted_organizations = {
            canonicalize_organization(row.get("organization", ""))
            for row in trusted_rows
        }
        for structured in structured_rows:
            structured_organization = canonicalize_organization(
                structured.get("organization", "")
            )
            if structured_organization in trusted_organizations:
                continue
            structured_start = int(structured["start_year"])
            structured_end = int(structured["end_year"])
            for trusted in trusted_rows:
                trusted_organization = canonicalize_organization(
                    trusted.get("organization", "")
                )
                if structured_organization == trusted_organization:
                    continue
                overlap = (
                    min(structured_end, int(trusted["end_year"]))
                    - max(structured_start, int(trusted["start_year"]))
                    + 1
                )
                if overlap >= minimum_overlap_years:
                    conflicts.add(
                        (
                            person_id,
                            structured.get("evidence_url", "").strip().rstrip("/"),
                            structured_organization,
                            trusted_organization,
                        )
                    )
    return sorted(conflicts)


def stale_employment_superseded_by_active_education(
    outcome: dict[str, str],
    affiliations: list[dict[str, str]],
    as_of_year: int = DATA_AS_OF_YEAR,
) -> bool:
    if (
        outcome.get("affiliation_type", "").strip() != "employment"
        or outcome.get("end_year", "").strip()
    ):
        return False
    organization = canonicalize_organization(outcome.get("organization", ""))
    matching_employment = [
        row
        for row in affiliations
        if row.get("affiliation_type") == "employment"
        and canonicalize_organization(row.get("organization", "")) == organization
        and row.get("evidence_kind") == "accepted_linkedin_profile"
    ]
    ended_employment = any(
        row.get("end_year", "").isdigit()
        and int(row["end_year"]) < as_of_year
        for row in matching_employment
    )
    ongoing_employment = any(
        row.get("is_current", "").strip().casefold() == "true"
        for row in matching_employment
    )
    active_education = any(
        row.get("affiliation_type") == "education"
        and row.get("evidence_kind") == "accepted_linkedin_profile"
        and row.get("end_year", "").isdigit()
        and int(row["end_year"]) >= as_of_year
        for row in affiliations
    )
    return ended_employment and not ongoing_employment and active_education


def validate(data_dir: Path) -> tuple[list[str], dict[str, int]]:
    errors: list[str] = []
    required = {
        "participants": data_dir / "kazakhstan_participants.csv",
        "people": data_dir / "people.csv",
        "researched": data_dir / "researched_people.csv",
        "verified": data_dir / "verified_evidence.csv",
        "manual_affiliations": data_dir / "manual_affiliations.csv",
        "destination_reviews": data_dir / "destination_reviews.csv",
        "person_merges": data_dir / "person_merges.csv",
        "exa_outcomes": data_dir / "exa_outcome_integrations.csv",
        "exa_outcome_decisions": data_dir / "exa_outcome_review_decisions.csv",
        "exa_profiles": data_dir / "exa_linkedin_profile_audit.json",
        "identity_candidates": data_dir / "identity_candidates.csv",
        "locations": data_dir / "person_locations.csv",
        "location_overrides": data_dir / "location_overrides.csv",
        "affiliations": data_dir / "person_affiliations.csv",
        "organization_aliases": data_dir / "organization_aliases.csv",
        "organization_locations": data_dir / "organization_locations.csv",
        "organization_sectors": data_dir / "organization_sectors.csv",
        "rejections": data_dir / "rejected_identity_candidates.csv",
        "audit_people": data_dir / "audit" / "people.csv",
        "audit_participations": data_dir / "audit" / "participations.csv",
        "audit_affiliations": data_dir / "audit" / "affiliations.csv",
        "audit_locations": data_dir / "audit" / "locations.csv",
        "audit_organization_aliases": data_dir / "audit" / "organization_aliases.csv",
        "audit_organization_sectors": data_dir / "audit" / "organization_sectors.csv",
        "audit_destination_reviews": data_dir / "audit" / "destination_reviews.csv",
        "audit_evidence": data_dir / "audit" / "evidence.csv",
        "audit_sources": data_dir / "audit" / "sources.csv",
        "audit_rejections": data_dir / "audit" / "rejections.csv",
        "audit_manifest": data_dir / "audit" / "manifest.json",
        "profile_sanity_review": data_dir / "audit" / "profile_sanity_review.csv",
        "profile_review_decisions": data_dir / "profile_sanity_review_decisions.csv",
        "linkedin_reconciliation": data_dir
        / "audit"
        / "linkedin_destination_reconciliation.csv",
        "profile_review_findings": data_dir
        / "audit"
        / "profile_sanity_review_findings.csv",
        "profile_review_manifest": data_dir
        / "audit"
        / "profile_sanity_review_manifest.json",
    }
    missing = [str(path) for path in required.values() if not path.exists()]
    if missing:
        return [f"missing required file: {path}" for path in missing], {}

    participants = read_csv(required["participants"])
    people = read_csv(required["people"])
    researched = read_csv(required["researched"])
    verified = read_csv(required["verified"])
    manual_affiliations = read_csv(required["manual_affiliations"])
    destination_reviews = read_csv(required["destination_reviews"])
    person_merges = read_csv(required["person_merges"])
    exa_outcomes = read_csv(required["exa_outcomes"])
    exa_outcome_decisions = read_csv(required["exa_outcome_decisions"])
    exa_profiles = json.loads(required["exa_profiles"].read_text(encoding="utf-8"))
    identity_candidates = read_csv(required["identity_candidates"])
    locations = read_csv(required["locations"])
    location_overrides = load_overrides(required["location_overrides"])
    affiliations = read_csv(required["affiliations"])
    organization_aliases = read_csv(required["organization_aliases"])
    organization_locations = load_organization_locations(
        required["organization_locations"]
    )
    organization_sectors = read_csv(required["organization_sectors"])
    rejections = read_csv(required["rejections"])
    audit_people = read_csv(required["audit_people"])
    audit_participations = read_csv(required["audit_participations"])
    audit_affiliations = read_csv(required["audit_affiliations"])
    audit_locations = read_csv(required["audit_locations"])
    audit_organization_aliases = read_csv(required["audit_organization_aliases"])
    audit_organization_sectors = read_csv(required["audit_organization_sectors"])
    audit_destination_reviews = read_csv(required["audit_destination_reviews"])
    audit_evidence = read_csv(required["audit_evidence"])
    audit_sources = read_csv(required["audit_sources"])
    audit_rejections = read_csv(required["audit_rejections"])
    audit_manifest = json.loads(required["audit_manifest"].read_text(encoding="utf-8"))
    profile_sanity_review = read_csv(required["profile_sanity_review"])
    profile_review_decisions = load_review_decisions(
        required["profile_review_decisions"]
    )
    linkedin_reconciliation = read_csv(required["linkedin_reconciliation"])
    profile_review_findings = read_csv(required["profile_review_findings"])
    profile_review_manifest = json.loads(
        required["profile_review_manifest"].read_text(encoding="utf-8")
    )

    def duplicate_ids(rows: list[dict[str, str]], label: str) -> None:
        counts = Counter(row.get("person_id", "") for row in rows)
        duplicates = sorted(key for key, count in counts.items() if key and count > 1)
        if duplicates:
            errors.append(f"{label} contains duplicate person IDs: {', '.join(duplicates[:8])}")

    duplicate_ids(people, "people.csv")
    duplicate_ids(researched, "researched_people.csv")
    duplicate_ids(verified, "verified_evidence.csv")
    duplicate_ids(destination_reviews, "destination_reviews.csv")
    duplicate_ids(exa_outcomes, "exa_outcome_integrations.csv")
    duplicate_ids(locations, "person_locations.csv")

    participant_rows = sum(int(row.get("participant_rows") or 0) for row in people)
    if participant_rows != len(participants):
        errors.append(
            f"registry accounts for {participant_rows} participant rows, expected {len(participants)}"
        )

    invalid_participant_olympiads = sorted(
        {row.get("olympiad", "") for row in participants} - OLYMPIADS
    )
    if invalid_participant_olympiads:
        errors.append(
            "participant file contains unsupported olympiads: "
            + ", ".join(invalid_participant_olympiads)
        )
    broken_ioi_person_urls = sorted(
        {
            row.get("person_url", "").strip()
            for row in participants
            if "/results/people/" in row.get("person_url", "")
        }
    )
    if broken_ioi_person_urls:
        errors.append(
            "participant file contains noncanonical IOI person URLs: "
            + ", ".join(broken_ioi_person_urls[:8])
        )

    people_by_id = {row["person_id"]: row for row in people}
    researched_by_id = {row["person_id"]: row for row in researched}
    verified_by_id = {row["person_id"]: row for row in verified}
    destination_reviews_by_id = {
        row["person_id"]: row for row in destination_reviews
    }
    exa_outcomes_by_id = {row["person_id"]: row for row in exa_outcomes}
    exa_outcome_decisions_by_profile = {
        (
            row.get("person_id", "").strip(),
            canonical_url(row.get("candidate_url", "")),
        ): row
        for row in exa_outcome_decisions
    }
    affiliations_by_person: dict[str, list[dict[str, str]]] = {}
    for row in affiliations:
        affiliations_by_person.setdefault(row.get("person_id", ""), []).append(row)
    identity_candidates_by_source = {
        (row.get("person_id", ""), canonical_url(url))
        for row in identity_candidates
        if row.get("confidence") in {"probable", "confirmed"}
        for url in identity_urls(row)
        if canonical_url(url)
    }
    audit_people_by_id = {row["person_id"]: row for row in audit_people}
    audit_evidence_by_id = {row["evidence_id"]: row for row in audit_evidence}
    participant_profile_urls_by_person: dict[str, set[str]] = defaultdict(set)
    for row in audit_participations:
        person_url = row.get("person_url", "").strip().rstrip("/")
        if person_url:
            participant_profile_urls_by_person[row["person_id"]].add(person_url)

    direct_imo_url_pattern = re.compile(
        r"^https?://www\.imo-official\.org/results/contestant/\d+/?$",
        re.IGNORECASE,
    )
    for row in verified:
        evidence_url = row.get("olympiad_evidence_url", "").strip().rstrip("/")
        if not direct_imo_url_pattern.match(evidence_url):
            continue
        canonical_urls = participant_profile_urls_by_person.get(row["person_id"], set())
        if evidence_url not in canonical_urls:
            errors.append(
                f"manual IMO contestant URL disagrees with participant registry for "
                f"{row['person_id']}"
            )
    audit_sources_by_id = {row["source_id"]: row for row in audit_sources}

    def duplicate_field(rows: list[dict[str, str]], field: str, label: str) -> None:
        counts = Counter(row.get(field, "") for row in rows)
        duplicates = sorted(key for key, count in counts.items() if key and count > 1)
        if duplicates:
            errors.append(f"{label} contains duplicate {field} values: {', '.join(duplicates[:8])}")

    duplicate_field(audit_people, "person_id", "audit/people.csv")
    duplicate_field(
        audit_participations, "participation_id", "audit/participations.csv"
    )
    duplicate_field(audit_affiliations, "affiliation_id", "audit/affiliations.csv")
    duplicate_field(audit_locations, "location_id", "audit/locations.csv")
    duplicate_field(
        audit_organization_aliases,
        "organization_alias_id",
        "audit/organization_aliases.csv",
    )
    duplicate_field(
        audit_organization_sectors,
        "organization_sector_id",
        "audit/organization_sectors.csv",
    )
    duplicate_field(
        audit_destination_reviews,
        "destination_review_id",
        "audit/destination_reviews.csv",
    )
    duplicate_field(audit_evidence, "evidence_id", "audit/evidence.csv")
    duplicate_field(audit_sources, "source_id", "audit/sources.csv")

    rejection_keys = [
        (
            row.get("person_id", "").strip(),
            row.get("evidence_url", "").strip().rstrip("/"),
        )
        for row in rejections
    ]
    duplicate_rejections = sorted(
        key for key, count in Counter(rejection_keys).items() if all(key) and count > 1
    )
    if duplicate_rejections:
        errors.append(
            "rejected identity candidates contain duplicate keys: "
            + ", ".join(f"{person_id} {url}" for person_id, url in duplicate_rejections[:8])
        )

    unknown_rejections = sorted(
        {person_id for person_id, _ in rejection_keys if person_id} - set(people_by_id)
    )
    if unknown_rejections:
        errors.append(
            "rejected identity candidates have unknown people: "
            + ", ".join(unknown_rejections[:8])
        )
    for index, row in enumerate(rejections, start=2):
        if not row.get("person_id", "").strip():
            errors.append(f"rejected identity row {index} has no person ID")
        if not row.get("evidence_url", "").strip():
            errors.append(f"rejected identity row {index} has no evidence URL")
        if not row.get("reason", "").strip():
            errors.append(f"rejected identity row {index} has no reason")

    if set(people_by_id) != set(researched_by_id):
        missing_research = sorted(set(people_by_id) - set(researched_by_id))
        unknown_research = sorted(set(researched_by_id) - set(people_by_id))
        if missing_research:
            errors.append(f"research dataset is missing {len(missing_research)} registry people")
        if unknown_research:
            errors.append(f"research dataset has {len(unknown_research)} unknown people")

    unknown_verified = sorted(set(verified_by_id) - set(people_by_id))
    if unknown_verified:
        errors.append(f"verified evidence has unknown people: {', '.join(unknown_verified)}")

    unknown_manual_affiliations = sorted(
        {
            row.get("person_id", "")
            for row in manual_affiliations
            if row.get("person_id")
        }
        - set(people_by_id)
    )
    if unknown_manual_affiliations:
        errors.append(
            "manual affiliation history has unknown people: "
            + ", ".join(unknown_manual_affiliations[:8])
        )

    try:
        load_destination_reviews(required["destination_reviews"])
    except ValueError as error:
        errors.append(f"destination review registry is invalid: {error}")
    unknown_destination_reviews = sorted(
        set(destination_reviews_by_id) - set(people_by_id)
    )
    if unknown_destination_reviews:
        errors.append(
            "destination reviews have unknown people: "
            + ", ".join(unknown_destination_reviews[:8])
        )
    for person_id, review in destination_reviews_by_id.items():
        final = researched_by_id.get(person_id)
        if not final:
            continue
        if review.get("name", "").strip() != final.get("name", "").strip():
            errors.append(f"destination review name disagrees for {person_id}")
        expected_fields = {
            "organization": canonicalize_organization(review.get("organization", "")),
            "role": review.get("role", "").strip(),
            "affiliation_type": review.get("affiliation_type", "").strip(),
            "start_year": review.get("start_year", "").strip(),
            "end_year": review.get("end_year", "").strip(),
        }
        for field, expected in expected_fields.items():
            if final.get(field, "").strip() != expected:
                errors.append(
                    f"destination review {field} was not published for {person_id}"
                )
        evidence_url = review.get("evidence_url", "").strip()
        accepted_urls = split_values(final.get("evidence_urls", "")) | {
            final.get("profile_url", "").strip(),
            final.get("linkedin_url", "").strip(),
        }
        if evidence_url not in accepted_urls:
            errors.append(
                f"destination review source is not linked from the final row for {person_id}"
            )
        matching_history = any(
            row.get("organization", "").strip() == expected_fields["organization"]
            and row.get("role", "").strip() == expected_fields["role"]
            and row.get("affiliation_type", "").strip()
            == expected_fields["affiliation_type"]
            and (
                not expected_fields["start_year"]
                or row.get("start_year", "").strip() == expected_fields["start_year"]
            )
            and (
                not expected_fields["end_year"]
                or row.get("end_year", "").strip() == expected_fields["end_year"]
            )
            and row.get("evidence_url", "").strip().rstrip("/")
            == evidence_url.rstrip("/")
            and row.get("evidence_kind", "").strip()
            == "destination_source_review"
            for row in affiliations_by_person.get(person_id, [])
        )
        if not matching_history:
            errors.append(
                f"destination review is missing from affiliation history for {person_id}"
            )

    for person_id, outcome in exa_outcomes_by_id.items():
        if person_id in destination_reviews_by_id:
            continue
        if stale_employment_superseded_by_active_education(
            outcome, affiliations_by_person.get(person_id, [])
        ):
            errors.append(
                f"ended LinkedIn employment supersedes an active education destination "
                f"without review for {person_id}"
            )

    merge_ids = [row.get("canonical_person_id", "") for row in person_merges]
    if len({person_id for person_id in merge_ids if person_id}) != len(
        [person_id for person_id in merge_ids if person_id]
    ):
        errors.append("person merge registry contains duplicate canonical person IDs")
    for index, row in enumerate(person_merges, start=2):
        person_id = row.get("canonical_person_id", "")
        person = people_by_id.get(person_id)
        aliases = split_values(row.get("aliases", ""))
        if not person:
            errors.append(f"person merge row {index} has unknown canonical person ID")
            continue
        if person.get("canonical_name") != row.get("canonical_name"):
            errors.append(f"person merge row {index} canonical name was not published")
        if not aliases or not aliases <= split_values(person.get("aliases", "")):
            errors.append(f"person merge row {index} aliases were not merged")
        if not row.get("reason", "").strip():
            errors.append(f"person merge row {index} has no rationale")
        if not row.get("evidence_url", "").startswith(("http://", "https://")):
            errors.append(f"person merge row {index} has no direct HTTP(S) source")

    unknown_exa_outcomes = sorted(set(exa_outcomes_by_id) - set(people_by_id))
    if unknown_exa_outcomes:
        errors.append(
            "Exa outcome integrations have unknown people: "
            + ", ".join(unknown_exa_outcomes)
        )

    unknown_locations = sorted(
        {row.get("person_id", "") for row in locations if row.get("person_id")} - set(people_by_id)
    )
    if unknown_locations:
        errors.append("location evidence has unknown people: " + ", ".join(unknown_locations[:8]))
    unknown_affiliations = sorted(set(affiliations_by_person) - set(people_by_id))
    if unknown_affiliations:
        errors.append(
            "affiliation history has unknown people: " + ", ".join(unknown_affiliations[:8])
        )

    manual_affiliation_keys = []
    for index, row in enumerate(manual_affiliations, start=2):
        person_id = row.get("person_id", "")
        affiliation_type = row.get("affiliation_type", "").casefold()
        organization = canonicalize_organization(row.get("organization", ""))
        evidence_url = row.get("evidence_url", "")
        if affiliation_type not in {"employment", "education"}:
            errors.append(
                f"manual affiliation row {index} has invalid type: {affiliation_type!r}"
            )
        if not organization:
            errors.append(f"manual affiliation row {index} has no organization")
        if not evidence_url.startswith(("http://", "https://")):
            errors.append(f"manual affiliation row {index} has no direct HTTP(S) source")
        if row.get("confidence", "") not in {"probable", "confirmed"}:
            errors.append(f"manual affiliation row {index} has invalid confidence")
        manual_affiliation_keys.append(
            (
                person_id,
                affiliation_type,
                organization.casefold(),
                row.get("role", "").casefold(),
                row.get("start_year", ""),
                row.get("end_year", ""),
                evidence_url.rstrip("/").casefold(),
            )
        )
    duplicate_manual_affiliations = [
        key
        for key, count in Counter(manual_affiliation_keys).items()
        if key[0] and count > 1
    ]
    if duplicate_manual_affiliations:
        errors.append("manual affiliation history contains duplicate sourced records")

    locations_by_person = {row.get("person_id", ""): row for row in locations}
    for row in locations:
        person_id = row.get("person_id", "")
        code = row.get("country_code", "")
        if code not in COUNTRY_NAMES:
            errors.append(f"location evidence has invalid country code for {person_id}: {code!r}")
        if row.get("country_name", "") != COUNTRY_NAMES.get(code, ""):
            errors.append(f"location country name disagrees with code for {person_id}")
        if not row.get("evidence_url", "").startswith(("http://", "https://")):
            errors.append(f"location evidence has no direct HTTP(S) source for {person_id}")
        if row.get("evidence_kind") in {
            "manual_public_profile_location",
            "public_profile_location",
        }:
            errors.append(
                f"LinkedIn header location lacks active-affiliation corroboration for {person_id}"
            )
        final = researched_by_id.get(person_id, {})
        accepted_urls = split_values(final.get("evidence_urls", "")) | {
            final.get("profile_url", ""),
            final.get("linkedin_url", ""),
        }
        accepted_urls.update(
            affiliation.get("evidence_url", "")
            for affiliation in affiliations_by_person.get(person_id, [])
            if affiliation.get("evidence_url", "")
        )
        organization_location = organization_locations.get(
            organization_key(
                canonicalize_organization(final.get("organization", ""))
            )
        )
        is_destination_organization_location = (
            final.get("destination_status") in {"current_education", "latest_employment"}
            and organization_location
            and row.get("evidence_url") == organization_location.get("evidence_url")
            and row.get("country_code") == organization_location.get("country_code")
        )
        reviewed_override = location_overrides.get(person_id, {})
        is_reviewed_override = (
            reviewed_override.get("evidence_kind") in TRUSTED_OVERRIDE_KINDS
            and all(
                row.get(field, "") == reviewed_override.get(field, "")
                for field in (
                    "country_code",
                    "country_name",
                    "location_label",
                    "evidence_url",
                    "evidence_kind",
                )
            )
        )
        if (
            row.get("evidence_url", "") not in accepted_urls
            and not is_destination_organization_location
            and not is_reviewed_override
        ):
            errors.append(f"location source is not linked to accepted evidence for {person_id}")

    for person_id, final in researched_by_id.items():
        if (
            final.get("confidence") not in {"probable", "confirmed"}
            or final.get("destination_status") != "current_education"
        ):
            continue
        organization = canonicalize_organization(final.get("organization", ""))
        expected = organization_locations.get(organization_key(organization))
        if not expected:
            errors.append(
                f"current education destination lacks an organization location: "
                f"{person_id} {organization}"
            )
            continue
        actual = locations_by_person.get(person_id)
        if not actual:
            errors.append(
                f"current education destination lacks country evidence: {person_id}"
            )
            continue
        if actual.get("country_code") != expected.get("country_code"):
            errors.append(
                f"current education country conflicts with institution location for "
                f"{person_id}: {actual.get('country_code')} vs {expected.get('country_code')}"
            )

    affiliation_keys = [
        (
            row.get("person_id", ""),
            row.get("affiliation_type", ""),
            row.get("organization", "").casefold(),
            row.get("role", "").casefold(),
            row.get("start_year", ""),
            row.get("end_year", ""),
            row.get("evidence_url", "").rstrip("/").casefold(),
        )
        for row in affiliations
    ]
    duplicate_affiliations = [
        key for key, count in Counter(affiliation_keys).items() if key[0] and count > 1
    ]
    if duplicate_affiliations:
        errors.append("affiliation history contains duplicate sourced records")
    missing_manual_affiliations = sorted(set(manual_affiliation_keys) - set(affiliation_keys))
    if missing_manual_affiliations:
        errors.append(
            f"{len(missing_manual_affiliations)} manual affiliation rows were not published"
        )
    alma_counts = Counter(
        (
            row.get("person_id", ""),
            row.get("organization", "").casefold(),
        )
        for row in affiliations
        if row.get("selected_as_alma_mater", "").casefold() == "true"
    )
    duplicate_alma = sorted(key for key, count in alma_counts.items() if count > 1)
    if duplicate_alma:
        errors.append(
            "people have duplicate selected alma-mater organizations: "
            + ", ".join(
                f"{person_id}/{organization}"
                for person_id, organization in duplicate_alma[:8]
            )
        )
    people_with_alma = {
        row.get("person_id", "")
        for row in affiliations
        if row.get("selected_as_alma_mater", "").casefold() == "true"
    }
    accepted_linkedin_people = {
        row.get("person_id", "")
        for row in researched
        if row.get("confidence", "") in {"probable", "confirmed"}
        and "linkedin.com/in/" in row.get("linkedin_url", "").casefold()
    }
    missing_linkedin_alma = sorted(accepted_linkedin_people - people_with_alma)
    if missing_linkedin_alma:
        errors.append(
            "accepted LinkedIn profiles have no selected alma mater: "
            + ", ".join(missing_linkedin_alma[:8])
        )
    current_students_without_alma = sorted(
        person_id
        for person_id, row in researched_by_id.items()
        if row.get("destination_status") == "current_education"
        and person_id not in people_with_alma
    )
    if current_students_without_alma:
        errors.append(
            "current education destinations have no selected alma mater: "
            + ", ".join(current_students_without_alma[:8])
        )
    structured_affiliation_kinds = {
        "accepted_codeforces",
        "accepted_cphof",
        "accepted_cphof_codeforces",
        "accepted_github",
        "accepted_openalex",
        "accepted_openalex_orcid",
        "accepted_orcid",
    }
    for row in affiliations:
        person_id = row.get("person_id", "")
        if not row.get("organization", ""):
            errors.append(f"affiliation history has no organization for {person_id}")
        if not row.get("evidence_url", "").startswith(("http://", "https://")):
            errors.append(f"affiliation history has no direct HTTP(S) source for {person_id}")
        if (
            row.get("evidence_kind") == "accepted_orcid"
            and row.get("affiliation_type") == "employment"
            and row.get("is_current", "").casefold() == "true"
            and not row.get("role")
            and not row.get("start_year")
            and not row.get("end_year")
        ):
            errors.append(
                f"undated roleless ORCID employment is marked current for {person_id}"
            )
        if (
            row.get("evidence_kind", "").removeprefix("accepted_")
            in NON_CHRONOLOGICAL_DIRECTORY_SOURCES
            and row.get("is_current", "").casefold() == "true"
            and not row.get("role")
            and not row.get("start_year")
            and not row.get("end_year")
        ):
            errors.append(
                f"undated directory organization is marked current for {person_id}"
            )
        if (
            row.get("evidence_kind") in structured_affiliation_kinds
            and (
                person_id,
                canonical_url(row.get("evidence_url", "")),
            )
            not in identity_candidates_by_source
        ):
            errors.append(
                f"structured affiliation lacks a probable identity bridge for {person_id}: "
                f"{row.get('evidence_url', '')}"
            )
        if (
            row.get("selected_as_alma_mater", "").casefold() == "true"
            and row.get("affiliation_type") != "education"
        ):
            errors.append(f"selected alma mater is not education for {person_id}")
        organization = row.get("organization", "")
        if organization and not valid_affiliation(organization, row.get("role", "")):
            errors.append(
                f"affiliation history has malformed organization for {person_id}: "
                f"{organization}"
            )
        if row.get("selected_as_alma_mater", "").casefold() == "true":
            metadata = organization_metadata(organization)
            if metadata.get("sector") and metadata.get("sector") != "Education & Research":
                errors.append(
                    f"selected alma mater is classified outside education for {person_id}: "
                    f"{organization}"
                )
        if organization and canonicalize_organization(organization) != organization:
            errors.append(
                f"affiliation history retains noncanonical organization for {person_id}: "
                f"{organization}"
            )

    for person_id, source_url, structured_organization, trusted_organization in (
        structured_alma_timeline_conflicts(affiliations)
    ):
        errors.append(
            "structured alma timeline conflicts with trusted education for "
            f"{person_id}: {structured_organization} versus {trusted_organization} "
            f"({source_url})"
        )

    for person_id, review in destination_reviews_by_id.items():
        review_organization = canonicalize_organization(review.get("organization", ""))
        review_type = review.get("affiliation_type", "")
        contradictory_current = [
            row
            for row in affiliations_by_person.get(person_id, [])
            if row.get("is_current", "").casefold() == "true"
            and canonicalize_organization(row.get("organization", ""))
            == review_organization
            and row.get("affiliation_type") == review_type
            and row.get("evidence_kind") != "destination_source_review"
            and (
                row.get("evidence_kind") == "manual_review"
                or not row.get("role")
                or "alumn" in row.get("role", "").casefold()
            )
        ]
        if contradictory_current:
            errors.append(
                f"weaker current affiliation contradicts destination review for {person_id}"
            )

    try:
        load_organization_aliases()
    except ValueError as error:
        errors.append(f"organization alias registry is invalid: {error}")
    organization_values = {
        row.get("organization", "").strip()
        for row in affiliations + researched
        if row.get("organization", "").strip()
    }
    organizations_by_audit_key: dict[str, set[str]] = defaultdict(set)
    organizations_by_display: dict[str, set[str]] = defaultdict(set)
    for organization in organization_values:
        canonical = canonicalize_organization(organization)
        audit_key = organization_audit_key(canonical)
        if audit_key:
            organizations_by_audit_key[audit_key].add(canonical)
        organizations_by_display[display_organization(canonical).casefold()].add(
            canonical
        )
    duplicate_organization_clusters = sorted(
        tuple(sorted(values))
        for values in organizations_by_audit_key.values()
        if len(values) > 1
    )
    if duplicate_organization_clusters:
        errors.append(
            "canonical organization names retain low-risk duplicate variants: "
            + "; ".join(
                " / ".join(sorted(values))
                for values in duplicate_organization_clusters[:8]
            )
        )
    display_collisions = sorted(
        tuple(sorted(values))
        for values in organizations_by_display.values()
        if len(values) > 1
    )
    if display_collisions:
        errors.append(
            "canonical organizations have colliding display names: "
            + "; ".join(
                " / ".join(sorted(values)) for values in display_collisions[:8]
            )
        )
    alias_chains = sorted(
        {
            (
                row.get("canonical_name", ""),
                canonicalize_organization(row.get("canonical_name", "")),
            )
            for row in organization_aliases
            if row.get("canonical_name", "")
            and canonicalize_organization(row.get("canonical_name", ""))
            != row.get("canonical_name", "")
        }
    )
    if alias_chains:
        errors.append(
            "organization alias registry contains canonical-name chains: "
            + "; ".join(f"{source} -> {target}" for source, target in alias_chains[:8])
        )
    if len(audit_organization_aliases) != len(organization_aliases):
        errors.append("audit organization aliases do not match the source registry")
    source_alias_rows = {
        tuple(row.get(field, "") or "" for field in (
            "alias",
            "canonical_name",
            "display_name",
            "merge_type",
            "rationale",
            "evidence_url",
        ))
        for row in organization_aliases
    }
    audit_alias_rows = {
        tuple(row.get(field, "") or "" for field in (
            "alias",
            "canonical_name",
            "display_name",
            "merge_type",
            "rationale",
            "evidence_url",
        ))
        for row in audit_organization_aliases
    }
    if source_alias_rows != audit_alias_rows:
        errors.append("audit organization aliases differ from the source registry")
    invalid_alias_sources = sorted(
        row.get("evidence_url", "")
        for row in organization_aliases
        if row.get("evidence_url", "")
        and not row.get("evidence_url", "").startswith(("http://", "https://"))
    )
    if invalid_alias_sources:
        errors.append(
            "organization aliases contain invalid evidence URLs: "
            + ", ".join(invalid_alias_sources[:8])
        )

    try:
        load_organization_sectors(required["organization_sectors"])
    except ValueError as error:
        errors.append(f"organization sector registry is invalid: {error}")
    if len(audit_organization_sectors) != len(organization_sectors):
        errors.append("audit organization sectors do not match the source registry")
    sector_fields = (
        "canonical_name",
        "organization_type",
        "sector",
        "rationale",
    )
    source_sector_rows = {
        tuple(row.get(field, "") for field in sector_fields)
        for row in organization_sectors
    }
    audit_sector_rows = {
        tuple(row.get(field, "") for field in sector_fields)
        for row in audit_organization_sectors
    }
    if source_sector_rows != audit_sector_rows:
        errors.append("audit organization sectors differ from the source registry")
    if len(audit_destination_reviews) != len(destination_reviews):
        errors.append("audit destination reviews do not match the source registry")
    destination_review_fields = (
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
    )
    source_destination_reviews = {
        tuple(
            canonicalize_organization(row.get(field, ""))
            if field == "organization"
            else row.get(field, "")
            for field in destination_review_fields
        )
        for row in destination_reviews
    }
    audit_destination_review_rows = {
        tuple(row.get(field, "") for field in destination_review_fields)
        for row in audit_destination_reviews
    }
    if source_destination_reviews != audit_destination_review_rows:
        errors.append("audit destination reviews differ from the source registry")
    for row in audit_destination_reviews:
        evidence = audit_evidence_by_id.get(row.get("evidence_id", ""))
        source = audit_sources_by_id.get(row.get("source_id", ""))
        if not evidence or evidence.get("claim_type") != "destination_source_review":
            errors.append(
                f"destination review {row.get('destination_review_id')} has no review evidence"
            )
        elif evidence.get("supports_final_outcome") != "True":
            errors.append(
                f"destination review {row.get('destination_review_id')} does not support the final outcome"
            )
        if not source or source.get("source_url", "").strip() != row.get(
            "evidence_url", ""
        ).strip():
            errors.append(
                f"destination review {row.get('destination_review_id')} has no matching source"
            )
    for person_id, row in researched_by_id.items():
        organization = row.get("organization", "")
        if not organization:
            continue
        metadata = organization_metadata(
            organization, row.get("organization_category", "")
        )
        if not metadata.get("organization_type") or not metadata.get("sector"):
            errors.append(
                f"{person_id} has an unclassified destination organization: {organization}"
            )

    accepted_linkedin = {
        row["person_id"]: row.get("linkedin_url", "")
        for row in researched
        if row.get("confidence") in {"probable", "confirmed"}
        and row.get("linkedin_url", "")
    }
    hydrated_profiles = {
        row.get("person_id", ""): row
        for row in exa_profiles.get("profiles", [])
        if row.get("person_id")
    }
    if set(hydrated_profiles) != set(accepted_linkedin):
        missing_profiles = sorted(set(accepted_linkedin) - set(hydrated_profiles))
        unknown_profiles = sorted(set(hydrated_profiles) - set(accepted_linkedin))
        if missing_profiles:
            errors.append(
                f"Exa profile audit is missing {len(missing_profiles)} accepted LinkedIn profiles"
            )
        if unknown_profiles:
            errors.append(
                f"Exa profile audit has {len(unknown_profiles)} unaccepted profiles"
            )
    if exa_profiles.get("key_persisted") is not False:
        errors.append("Exa profile audit does not declare key_persisted=false")
    if exa_profiles.get("accepted_linkedin_count") != len(accepted_linkedin):
        errors.append("Exa profile audit accepted count is stale")
    if exa_profiles.get("profile_count") != len(hydrated_profiles):
        errors.append("Exa profile audit profile count is stale")
    for person_id, profile in hydrated_profiles.items():
        if canonical_url(profile.get("linkedin_url", "")) != canonical_url(
            accepted_linkedin.get(person_id, "")
        ):
            errors.append(f"Exa profile URL disagrees for {person_id}")
        status = profile.get("status")
        if status not in {"success", "search_cache", "manual_public_profile", "error"}:
            errors.append(f"Exa profile audit has invalid status for {person_id}")
        if status in {"success", "search_cache", "manual_public_profile"} and not profile.get(
            "text", ""
        ).strip():
            errors.append(f"Exa profile audit has empty successful content for {person_id}")
        if status not in {"success", "search_cache", "manual_public_profile"}:
            continue
        current_profile_organizations = {
            canonicalize_organization(row.get("organization", ""))
            for row in extract_affiliations(profile.get("text", ""))
            if row.get("is_current") and row.get("organization")
        }
        current_profile_organizations.discard("")
        if not current_profile_organizations:
            continue
        final_organization = canonicalize_organization(
            researched_by_id.get(person_id, {}).get("organization", "")
        )
        profile_key = canonical_url(profile.get("linkedin_url", ""))
        explicitly_reviewed = (
            person_id in destination_reviews_by_id
            or (person_id, profile_key) in exa_outcome_decisions_by_profile
        )
        if final_organization not in current_profile_organizations and not explicitly_reviewed:
            errors.append(
                f"accepted LinkedIn current organization is not reconciled for {person_id}: "
                + ", ".join(sorted(current_profile_organizations))
            )

    for index, decision in enumerate(exa_outcome_decisions, start=2):
        person_id = decision.get("person_id", "").strip()
        candidate_url = decision.get("candidate_url", "").strip()
        review_url = decision.get("review_evidence_url", "").strip()
        if person_id not in researched_by_id:
            errors.append(f"Exa outcome decision row {index} has an unknown person")
        if not candidate_url.startswith(("http://", "https://")):
            errors.append(f"Exa outcome decision row {index} has no candidate URL")
        if not decision.get("decision", "").strip() or not decision.get("reason", "").strip():
            errors.append(f"Exa outcome decision row {index} is incomplete")
        if not review_url.startswith(("http://", "https://")):
            errors.append(f"Exa outcome decision row {index} has no review source")

    expected_reconciliation = build_reconciliation(
        researched,
        exa_profiles.get("profiles", []),
        destination_reviews,
        exa_outcome_decisions,
        audit_evidence,
    )
    if linkedin_reconciliation != [
        {key: str(value) for key, value in row.items()}
        for row in expected_reconciliation
    ]:
        errors.append("LinkedIn destination reconciliation is stale")
    if len(linkedin_reconciliation) != len(accepted_linkedin):
        errors.append("LinkedIn destination reconciliation does not cover every profile")
    if any(
        row.get("alignment_status", "").startswith("unreconciled")
        for row in linkedin_reconciliation
    ):
        errors.append("LinkedIn destination reconciliation contains unresolved mismatches")
    if any(
        row.get("profile_hydration_status") == "error"
        and (
            not row.get("review_decision", "").strip()
            or not row.get("review_reference_url", "").startswith(("http://", "https://"))
        )
        for row in linkedin_reconciliation
    ):
        errors.append("LinkedIn retrieval errors lack an auditable fallback source")

    previously_reviewed_ids = {
        person_id
        for (decision_seed, person_id) in profile_review_decisions
        if decision_seed != SAMPLE_SEED
    }
    expected_sample = select_sample(
        researched,
        SAMPLE_SEED,
        ERA_CUTOFF_YEAR,
        SAMPLE_PER_STRATUM,
        previously_reviewed_ids,
    )
    expected_sample_keys = [
        (
            str(row["stratum"]),
            str(row["sample_rank"]),
            str(row["sample_hash"]),
            str(row["person"]["person_id"]),
        )
        for row in expected_sample
    ]
    actual_sample_keys = [
        (
            row.get("stratum", ""),
            row.get("sample_rank", ""),
            row.get("sample_hash", ""),
            row.get("person_id", ""),
        )
        for row in profile_sanity_review
    ]
    if actual_sample_keys != expected_sample_keys:
        errors.append("profile sanity sample is not reproducible from its declared seed")
    if any(
        row.get("participation_check") != "pass"
        or row.get("manual_review_status") not in {"pass", "pass_after_correction"}
        or row.get("review_depth") not in {"standard", "deep"}
        or not row.get("review_fingerprint", "").strip()
        for row in profile_sanity_review
    ):
        errors.append("profile sanity sample contains an unresolved review failure")
    if any(row.get("status") != "resolved" for row in profile_review_findings):
        errors.append("profile sanity root-cause ledger contains unresolved findings")
    expected_review_manifest = {
        "sample_seed": SAMPLE_SEED,
        "era_cutoff_year": ERA_CUTOFF_YEAR,
        "sample_per_stratum": SAMPLE_PER_STRATUM,
        "excluded_previously_reviewed": len(previously_reviewed_ids),
        "sample_population": len(
            [
                row
                for row in researched
                if row.get("confidence") in {"probable", "confirmed"}
                and row.get("person_id") not in previously_reviewed_ids
            ]
        ),
        "sample_size": len(profile_sanity_review),
        "cumulative_signed_profiles": len(
            {
                person_id
                for (_, person_id), decision in profile_review_decisions.items()
                if decision.get("review_status") in {"pass", "pass_after_correction"}
            }
        ),
        "accepted_linkedin_profiles": len(linkedin_reconciliation),
        "unreconciled_linkedin_profiles": 0,
        "root_cause_findings": len(profile_review_findings),
        "unresolved_findings": 0,
    }
    for field, expected_value in expected_review_manifest.items():
        if profile_review_manifest.get(field) != expected_value:
            errors.append(f"profile sanity review manifest has stale {field}")

    for person_id, expected in exa_outcomes_by_id.items():
        merged = verified_by_id.get(person_id)
        final = researched_by_id.get(person_id)
        if merged is None:
            errors.append(f"Exa outcome integration was not merged for {person_id}")
            continue
        for field in expected:
            expected_value = expected.get(field, "").strip()
            if merged.get(field, "").strip() != expected_value:
                errors.append(
                    f"Exa outcome integration {field} was not merged for {person_id}"
                )
        final_field_map = {
            "organization": "organization",
            "role": "role",
            "affiliation_type": "affiliation_type",
            "start_year": "start_year",
            "end_year": "end_year",
            "linkedin_url": "linkedin_url",
            "confidence": "confidence",
            "verification_basis": "verification_basis",
        }
        for expected_field, final_field in final_field_map.items():
            if person_id in destination_reviews_by_id:
                continue
            if (
                final is not None
                and final.get("destination_status") == "history_only"
                and expected_field
                in {"organization", "role", "affiliation_type", "start_year", "end_year"}
            ):
                continue
            expected_value = expected.get(expected_field, "").strip()
            if expected_field == "organization":
                expected_value = canonicalize_organization(expected_value)
            if final is not None and final.get(final_field, "").strip() != expected_value:
                errors.append(
                    f"Exa outcome integration {expected_field} was not published for {person_id}"
                )
        expected_profile_url = preferred_manual_profile_url(
            expected.get("career_evidence_url", ""), expected.get("linkedin_url", "")
        )
        if final is not None and final.get("profile_url", "").strip() != expected_profile_url:
            errors.append(
                f"Exa outcome integration primary profile was not published for {person_id}"
            )
        final_urls = split_values(final.get("evidence_urls", "")) if final else set()
        for field in ("olympiad_evidence_url", "career_evidence_url"):
            expected_url = expected.get(field, "").strip()
            if expected_url and expected_url not in final_urls:
                errors.append(
                    f"Exa outcome integration {field} is not traceable for {person_id}"
                )

    if set(audit_people_by_id) != set(people_by_id):
        errors.append("audit people do not match the canonical people registry")
    if len(audit_participations) != len(participants):
        errors.append(
            f"audit participations contain {len(audit_participations)} rows, "
            f"expected {len(participants)}"
        )
    if len(audit_affiliations) != len(affiliations):
        errors.append(
            f"audit affiliations contain {len(audit_affiliations)} rows, "
            f"expected {len(affiliations)}"
        )
    if len(audit_locations) != len(locations):
        errors.append(
            f"audit locations contain {len(audit_locations)} rows, expected {len(locations)}"
        )

    for person_id, final_row in researched_by_id.items():
        audit_row = audit_people_by_id.get(person_id)
        if not audit_row:
            continue
        for audit_field, final_field in [
            ("name", "name"),
            ("outcome_status", "confidence"),
            ("organization", "organization"),
            ("role", "role"),
        ]:
            if audit_row.get(audit_field, "").strip() != final_row.get(final_field, "").strip():
                errors.append(
                    f"audit {audit_field} does not match final {final_field} for {person_id}"
                )

    evidence_by_person: dict[str, list[dict[str, str]]] = {}
    for row in audit_evidence:
        evidence_by_person.setdefault(row.get("person_id", ""), []).append(row)
        person_id = row.get("person_id", "")
        source_id = row.get("source_id", "")
        source_url = row.get("source_url", "").strip()
        if person_id not in people_by_id:
            errors.append(f"audit evidence {row.get('evidence_id')} has unknown person {person_id}")
        if source_id not in audit_sources_by_id:
            errors.append(f"audit evidence {row.get('evidence_id')} has unknown source {source_id}")
        elif audit_sources_by_id[source_id].get("source_url", "").strip() != source_url:
            errors.append(f"audit evidence {row.get('evidence_id')} disagrees with its source URL")
        if not source_url.startswith(("http://", "https://")):
            errors.append(f"audit evidence {row.get('evidence_id')} has no direct HTTP(S) source")
        if row.get("review_status") not in AUDIT_REVIEW_STATUSES:
            errors.append(
                f"audit evidence {row.get('evidence_id')} has invalid review status: "
                f"{row.get('review_status')!r}"
            )

    for row in audit_participations:
        person_id = row.get("person_id", "")
        evidence = audit_evidence_by_id.get(row.get("evidence_id", ""))
        if person_id not in people_by_id:
            errors.append(
                f"audit participation {row.get('participation_id')} has unknown person {person_id}"
            )
        if not evidence:
            errors.append(
                f"audit participation {row.get('participation_id')} has no evidence row"
            )
        elif evidence.get("claim_type") != "olympiad_participation":
            errors.append(
                f"audit participation {row.get('participation_id')} links to non-participation evidence"
            )

    for row in audit_affiliations:
        person_id = row.get("person_id", "")
        evidence = audit_evidence_by_id.get(row.get("evidence_id", ""))
        source = audit_sources_by_id.get(row.get("source_id", ""))
        if person_id not in people_by_id:
            errors.append(
                f"audit affiliation {row.get('affiliation_id')} has unknown person {person_id}"
            )
        if not evidence:
            errors.append(
                f"audit affiliation {row.get('affiliation_id')} has no evidence row"
            )
        elif evidence.get("person_id") != person_id:
            errors.append(
                f"audit affiliation {row.get('affiliation_id')} disagrees with its evidence person"
            )
        if not source:
            errors.append(
                f"audit affiliation {row.get('affiliation_id')} has no source row"
            )
        elif source.get("source_url", "").strip() != row.get("evidence_url", "").strip():
            errors.append(
                f"audit affiliation {row.get('affiliation_id')} disagrees with its source URL"
            )

    for row in audit_locations:
        person_id = row.get("person_id", "")
        evidence = audit_evidence_by_id.get(row.get("evidence_id", ""))
        source = audit_sources_by_id.get(row.get("source_id", ""))
        if person_id not in people_by_id:
            errors.append(
                f"audit location {row.get('location_id')} has unknown person {person_id}"
            )
        if not evidence or evidence.get("claim_type") != "outcome_country":
            errors.append(
                f"audit location {row.get('location_id')} has no outcome-country evidence"
            )
        if not source:
            errors.append(f"audit location {row.get('location_id')} has no source row")
        elif source.get("source_url", "").strip() != row.get("evidence_url", "").strip():
            errors.append(
                f"audit location {row.get('location_id')} disagrees with its source URL"
            )

    rejected_keys = {
        (row.get("person_id", ""), row.get("evidence_url", "").strip().rstrip("/"))
        for row in rejections
    }
    if len(audit_rejections) != len(rejections):
        errors.append("normalized audit rejections do not match the review ledger")
    for row in audit_rejections:
        if row.get("person_id") not in people_by_id:
            errors.append(f"normalized rejection has unknown person: {row.get('person_id')}")
        if row.get("source_id") not in audit_sources_by_id:
            errors.append(f"normalized rejection has unknown source: {row.get('source_id')}")
    for row in audit_evidence:
        key = (row.get("person_id", ""), row.get("source_url", "").strip().rstrip("/"))
        if (
            key in rejected_keys
            and row.get("supports_final_outcome") == "True"
            and row.get("review_status") in {"accepted", "supporting"}
        ):
            errors.append(f"rejected source supports a final outcome: {key[0]} {key[1]}")

    for person_id, final_row in researched_by_id.items():
        person_evidence = evidence_by_person.get(person_id, [])
        participation_evidence = [
            row
            for row in person_evidence
            if row.get("claim_type") == "olympiad_participation"
            and row.get("review_status") == "accepted"
        ]
        if not participation_evidence:
            errors.append(f"{person_id} has no accepted participation evidence")
        if final_row.get("confidence") in {"probable", "confirmed"}:
            audit_row = audit_people_by_id.get(person_id, {})
            if final_row.get("destination_status") == "none":
                identity_evidence = [
                    row
                    for row in person_evidence
                    if row.get("claim_type")
                    in {"olympiad_identity_bridge", "identity_candidate"}
                    and row.get("review_status") == "accepted"
                ]
                if not identity_evidence:
                    errors.append(
                        f"{person_id} has no accepted source-linked identity evidence"
                    )
                if audit_row.get("traceability_status") != "identity_verified":
                    errors.append(
                        f"{person_id} has no destination without verified identity traceability"
                    )
            else:
                outcome_evidence = [
                    row
                    for row in person_evidence
                    if row.get("supports_final_outcome") == "True"
                    and row.get("review_status") in {"accepted", "supporting"}
                ]
                if not outcome_evidence:
                    errors.append(
                        f"{person_id} has no accepted source-linked outcome evidence"
                    )
                if audit_row.get("traceability_status") != "complete":
                    errors.append(
                        f"{person_id} is high confidence without complete audit traceability"
                    )

    manifest_counts = audit_manifest.get("counts", {})
    expected_manifest_counts = {
        "people": len(audit_people),
        "participations": len(audit_participations),
        "affiliations": len(audit_affiliations),
        "locations": len(audit_locations),
        "organization_aliases": len(audit_organization_aliases),
        "organization_sectors": len(audit_organization_sectors),
        "destination_reviews": len(audit_destination_reviews),
        "evidence_rows": len(audit_evidence),
        "sources": len(audit_sources),
        "rejections": len(audit_rejections),
        "complete_outcomes": sum(
            row.get("traceability_status") == "complete" for row in audit_people
        ),
        "resolved_destinations": sum(
            bool(row.get("organization", "").strip()) for row in researched
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
    }
    if manifest_counts != expected_manifest_counts:
        errors.append("audit manifest counts do not match the normalized audit tables")

    for person_id, row in researched_by_id.items():
        if not row.get("name"):
            errors.append(f"{person_id} has no canonical name")
        confidence = row.get("confidence", "")
        if confidence not in CONFIDENCE_LEVELS:
            errors.append(f"{person_id} has invalid confidence: {confidence!r}")
        olympiads = split_values(row.get("olympiads", ""))
        if not olympiads or not olympiads <= OLYMPIADS:
            errors.append(f"{person_id} has invalid olympiad membership: {sorted(olympiads)}")
        if confidence in {"probable", "confirmed"}:
            if int(row.get("evidence_count") or 0) < 1:
                errors.append(f"{person_id} is {confidence} without an evidence URL")
            if "timeline_conflict" in row.get("verification_basis", ""):
                errors.append(f"{person_id} is {confidence} despite a timeline conflict")
        organization = row.get("organization", "")
        if organization and canonicalize_organization(organization) != organization:
            errors.append(
                f"{person_id} retains noncanonical destination organization: {organization}"
            )
        destination_status = row.get("destination_status", "")
        if destination_status not in {
            "none",
            "history_only",
            "latest_employment",
            "current_education",
        }:
            errors.append(f"{person_id} has invalid destination status: {destination_status!r}")
        if destination_status in {"none", "history_only"} and (
            row.get("organization") or row.get("role")
        ):
            errors.append(f"{person_id} has a destination despite {destination_status} status")
        if destination_status in {"latest_employment", "current_education"} and not row.get(
            "organization"
        ):
            errors.append(f"{person_id} has {destination_status} status without an organization")
        if destination_status in {"latest_employment", "current_education"} and not row.get(
            "role"
        ):
            errors.append(f"{person_id} has {destination_status} status without a role")
        if destination_status == "current_education" and row.get("affiliation_type") != "education":
            errors.append(f"{person_id} has current education status without education type")
        if (
            destination_status == "current_education"
            and not row.get("start_year")
            and not row.get("end_year")
        ):
            same_organization_completed_degrees = [
                affiliation
                for affiliation in affiliations_by_person.get(person_id, [])
                if affiliation.get("affiliation_type") == "education"
                and canonicalize_organization(affiliation.get("organization", ""))
                == canonicalize_organization(row.get("organization", ""))
                and affiliation.get("end_year", "").isdigit()
                and int(affiliation["end_year"]) < DATA_AS_OF_YEAR
                and affiliation.get("selected_as_alma_mater", "").casefold() == "true"
            ]
            if same_organization_completed_degrees:
                errors.append(
                    f"{person_id} uses an undated current-student summary over a "
                    "completed same-institution degree"
                )
        if destination_status == "latest_employment" and re.search(
            r"\b(?:ph\.?\s*d|doctoral)\s+researcher\b",
            row.get("role", ""),
            re.IGNORECASE,
        ):
            errors.append(
                f"{person_id} publishes an active doctoral researcher as employment"
            )
        if re.search(
            r"\balumn(?:us|a|i)\b",
            row.get("role", ""),
            re.IGNORECASE,
        ):
            errors.append(f"{person_id} publishes alumni status as a destination role")
        if row.get("role", "").casefold() == "research author":
            errors.append(f"{person_id} publishes authorship as a destination")
        final_urls = {
            url.strip().rstrip("/")
            for url in row.get("evidence_urls", "").split(";")
            if url.strip()
        }
        leaked_rejections = [
            url
            for rejected_person_id, url in rejection_keys
            if rejected_person_id == person_id and url in final_urls
        ]
        if leaked_rejections:
            errors.append(
                f"{person_id} retains rejected evidence: {', '.join(leaked_rejections[:3])}"
            )

    for person_id, verified_row in verified_by_id.items():
        final_row = researched_by_id.get(person_id)
        if final_row is None:
            continue
        manual_organization = canonicalize_organization(
            verified_row.get("organization", "")
        )
        manual_role = verified_row.get("role", "").strip()
        manual_type = verified_row.get("affiliation_type", "").strip()
        manual_dates = any(
            verified_row.get(field, "").strip()
            for field in ("start_year", "end_year")
        )
        if not manual_organization and (manual_role or manual_type or manual_dates):
            errors.append(
                f"identity-only manual evidence has partial outcome fields for {person_id}"
            )
        expected_profile_url = preferred_manual_profile_url(
            verified_row.get("career_evidence_url", ""),
            verified_row.get("linkedin_url", ""),
        )
        if final_row.get("profile_url", "").strip() != expected_profile_url:
            errors.append(f"manual primary profile source was not preserved for {person_id}")
        career_slug = linkedin_profile_slug(
            verified_row.get("career_evidence_url", "")
        )
        own_slug = linkedin_profile_slug(verified_row.get("linkedin_url", ""))
        if career_slug and own_slug and career_slug != own_slug:
            final_slug = linkedin_profile_slug(final_row.get("profile_url", ""))
            if final_slug != own_slug:
                errors.append(
                    f"third-party LinkedIn source replaced own profile for {person_id}"
                )
        expected_confidence = verified_row.get("confidence", "").strip() or "confirmed"
        if expected_confidence not in {"probable", "confirmed"}:
            errors.append(
                f"manual evidence for {person_id} has invalid confidence: "
                f"{expected_confidence!r}"
            )
        elif final_row.get("confidence") != expected_confidence:
            errors.append(
                f"manual evidence for {person_id} did not preserve "
                f"{expected_confidence} confidence"
            )
        if person_id in destination_reviews_by_id:
            history_rows = affiliations_by_person.get(person_id, [])
            preserved_in_history = any(
                row.get("organization", "").strip()
                == canonicalize_organization(verified_row.get("organization", ""))
                and row.get("role", "").strip()
                == verified_row.get("role", "").strip()
                and row.get("evidence_url", "").strip().rstrip("/")
                == verified_row.get("career_evidence_url", "").strip().rstrip("/")
                for row in history_rows
            )
            if not preserved_in_history:
                errors.append(
                    f"superseded manual evidence was not preserved for {person_id}"
                )
            continue
        if final_row.get("destination_status") == "history_only":
            history_rows = affiliations_by_person.get(person_id, [])
            preserved_in_history = any(
                row.get("organization", "").strip()
                == canonicalize_organization(verified_row.get("organization", ""))
                and row.get("role", "").strip() == verified_row.get("role", "").strip()
                and row.get("evidence_url", "").strip().rstrip("/")
                == verified_row.get("career_evidence_url", "").strip().rstrip("/")
                for row in history_rows
            )
            if not preserved_in_history:
                errors.append(f"manual history evidence was not preserved for {person_id}")
            continue
        for field in ("organization", "role"):
            expected = verified_row.get(field, "").strip()
            if field == "organization":
                expected = canonicalize_organization(expected)
            if expected and final_row.get(field, "").strip() != expected:
                errors.append(f"manual {field} was not preserved for {person_id}")

    recent_high_confidence = [
        row["person_id"]
        for row in researched
        if row.get("research_scope") == "recent_competitor"
        and row.get("confidence") in {"probable", "confirmed"}
        and row["person_id"] not in verified_by_id
    ]
    if recent_high_confidence:
        errors.append(
            "recent competitors were career-profiled without manual evidence: "
            + ", ".join(recent_high_confidence[:8])
        )

    confidence_counts = Counter(row.get("confidence", "") for row in researched)
    high_confidence_people = (
        confidence_counts["probable"] + confidence_counts["confirmed"]
    )
    summary = {
        "participant_rows": len(participants),
        "canonical_people": len(people),
        "researched_people": high_confidence_people,
        "candidate_only_people": confidence_counts["candidate"],
        "high_confidence_people": high_confidence_people,
        "manually_verified_people": len(verified),
        "integrated_exa_outcomes": len(exa_outcomes),
        "rejected_identity_candidates": len(rejections),
        "audit_evidence_rows": len(audit_evidence),
        "audit_sources": len(audit_sources),
        "organization_sectors": len(organization_sectors),
        "destination_reviews": len(destination_reviews),
        "profile_sanity_sample": len(profile_sanity_review),
        "linkedin_profiles_reconciled": len(linkedin_reconciliation),
        "profile_review_findings": len(profile_review_findings),
    }
    return errors, summary


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate participant conservation, identity confidence, and manual overrides."
    )
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    args = parser.parse_args()

    errors, summary = validate(args.data_dir)
    if errors:
        print("Validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print("Research dataset validation passed")
    for label, value in summary.items():
        print(f"- {label.replace('_', ' ')}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
