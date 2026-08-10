#!/usr/bin/env python3
"""Build auditable employment and education history from accepted evidence."""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import defaultdict
from pathlib import Path

try:
    from scripts.build_exa_review_queue import canonical_url
    from scripts.destination_reviews import load_destination_reviews
    from scripts.hydrate_linkedin_profiles_with_exa import profile_search_records
    from scripts.build_research_dataset import (
        CONFIDENCE_RANK,
        affiliation_supported_by_identity,
        identity_sort_key,
        identity_urls,
    )
    from scripts.organization_names import canonicalize_organization
except ModuleNotFoundError:  # Direct script execution adds scripts/ to sys.path.
    from build_exa_review_queue import canonical_url
    from destination_reviews import load_destination_reviews
    from hydrate_linkedin_profiles_with_exa import profile_search_records
    from build_research_dataset import (
        CONFIDENCE_RANK,
        affiliation_supported_by_identity,
        identity_sort_key,
        identity_urls,
    )
    from organization_names import canonicalize_organization


DEFAULT_PEOPLE = Path("data/researched_people.json")
DEFAULT_EXA_AUDIT = Path("data/exa_linkedin_search_audit.json")
DEFAULT_EXA_PROFILES = Path("data/exa_linkedin_profile_audit.json")
DEFAULT_IDENTITIES = Path("data/identity_candidates.json")
DEFAULT_AFFILIATIONS = Path("data/affiliation_candidates.json")
DEFAULT_VERIFIED = Path("data/verified_evidence.csv")
DEFAULT_MANUAL_AFFILIATIONS = Path("data/manual_affiliations.csv")
DEFAULT_DESTINATION_REVIEWS = Path("data/destination_reviews.csv")
DEFAULT_REJECTIONS = Path("data/rejected_identity_candidates.csv")
DEFAULT_CSV = Path("data/person_affiliations.csv")
DEFAULT_JSON = Path("data/person_affiliations.json")

OUTPUT_FIELDS = [
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

HEADING_PATTERN = re.compile(r"(?P<marker>#{2,4})\s+")
MARKDOWN_LINK_PATTERN = re.compile(r"\[([^\]]+)\]\([^)]+\)")
LINKED_EXPERIENCE_PATTERN = re.compile(
    r"^(?P<role>.{2,120}?)\s+-\s+\[(?P<organization>[^\]]{2,140})\]\([^)]+\)",
    re.IGNORECASE,
)
PLAIN_EXPERIENCE_PATTERN = re.compile(
    r"^(?P<role>.{2,120}?)\s+-\s+(?P<organization>.{2,140}?)"
    r"(?=\s+\(Current\)|\s+(?:(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+)?(?:19|20)\d{2}\s*-|\s+\.{3}|$)",
    re.IGNORECASE,
)
LINKED_EDUCATION_PATTERN = re.compile(
    r"^(?P<role>.{2,140}?)\s+at\s+\[(?P<organization>[^\]]{2,160})\]\([^)]+\)",
    re.IGNORECASE,
)
PLAIN_EDUCATION_PATTERN = re.compile(
    r"^(?P<role>(?:bachelor|b\.?\s*sc\.?|bs\b|b\.?\s*a\.?|master|m\.?\s*sc\.?|ms\b|m\.?\s*a\.?|ph\.?d|doctor|degree|diploma).{0,140}?)"
    r"\s+at\s+(?P<organization>.{2,160}?)"
    r"(?=\s+(?:(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+)?(?:19|20)\d{2}\s*-|\s+\.{3}|$)",
    re.IGNORECASE,
)
LINK_ONLY_PATTERN = re.compile(r"^\[(?P<organization>[^\]]{2,160})\]\([^)]+\)")
DATE_RANGE_PATTERN = re.compile(
    r"(?:(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+)?"
    r"(?P<start>(?:19|20)\d{2})\s*-\s*"
    r"(?:(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+)?"
    r"(?P<end>Present|(?:19|20)\d{2})",
    re.IGNORECASE,
)
ROLE_STOP_PATTERN = re.compile(
    r"\s+(?:\(Current\)|(?:(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+)?(?:19|20)\d{2}\s*-|\.{3}).*$",
    re.IGNORECASE,
)
EXCLUDED_ROLE_PATTERN = re.compile(
    r"\b(?:medal|award|issued by|certification|license)\b",
    re.IGNORECASE,
)
EDUCATION_TERMS = re.compile(
    r"\b(?:bachelor|b\.?\s*sc\.?|bs\b|b\.?\s*a\.?|master|m\.?\s*sc\.?|ms\b|m\.?\s*a\.?|ph\.?d|doctor|student|graduate|degree|diploma|school|education)\b",
    re.IGNORECASE,
)
EMPLOYMENT_ROLE_TERMS = re.compile(
    r"\b(?:researcher|research assistant|fellow|scientist|engineer|professor|lecturer|teacher)\b",
    re.IGNORECASE,
)
INSTITUTION_TERMS = re.compile(
    r"\b(?:university|institute|school|college|academy|universität|universitesi|université|университет)\b",
    re.IGNORECASE,
)
DATE_DURATION_PATTERN = re.compile(r"^(?:19|20)\d{2}\s*\(")
LEADING_YEAR_RANGE_PATTERN = re.compile(
    r"^(?:19|20)\d{2}\s*[-–]\s*(?:19|20)\d{2}\s*,\s*"
)
MONTH_DURATION_PATTERN = re.compile(
    r"^(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+"
    r"(?:19|20)\d{2}(?:\s*\(|\b)",
    re.IGNORECASE,
)
INCOMPLETE_INSTITUTION_PATTERN = re.compile(
    r"\b(?:university|institute|school|college)\s+(?:of|for|at)$",
    re.IGNORECASE,
)
ONE_OFF_ROLE_PATTERN = re.compile(
    r"\b(?:(?:19|20)\d{2}\s+participant|summer school|summer intern(?:ship)?)\b",
    re.IGNORECASE,
)


def clean_text(value: object) -> str:
    text = "" if value is None else str(value)
    return re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()


def strip_markdown(value: str) -> str:
    return clean_text(MARKDOWN_LINK_PATTERN.sub(r"\1", value)).strip(" .,-")


def years_from_text(value: str) -> tuple[str, str, bool]:
    match = DATE_RANGE_PATTERN.search(value)
    if not match:
        return "", "", "(Current)" in value
    end = match.group("end")
    return (
        match.group("start"),
        "" if end.casefold() == "present" else end,
        end.casefold() == "present" or "(Current)" in value,
    )


def valid_affiliation(organization: str, role: str) -> bool:
    if not organization or len(organization) > 160 or len(role) > 160:
        return False
    if re.fullmatch(r"(?:19|20)\d{2}", organization):
        return False
    if DATE_DURATION_PATTERN.match(organization):
        return False
    if MONTH_DURATION_PATTERN.match(organization):
        return False
    if INCOMPLETE_INSTITUTION_PATTERN.search(organization):
        return False
    if EXCLUDED_ROLE_PATTERN.search(f"{role} {organization}"):
        return False
    if "..." in organization or "http" in organization.casefold():
        return False
    if any(character in organization for character in "[]{}<>"):
        return False
    return organization.casefold() not in {"bronze medal", "silver medal", "gold medal"}


def make_entry(
    organization: str,
    role: str,
    affiliation_type: str,
    segment: str,
) -> dict[str, object] | None:
    organization = LEADING_YEAR_RANGE_PATTERN.sub("", strip_markdown(organization))
    role = strip_markdown(role)
    role = clean_text(ROLE_STOP_PATTERN.sub("", role)).strip(" .,-")
    if affiliation_type == "education" and "olympiad" in organization.casefold():
        return None
    if not valid_affiliation(organization, role):
        return None
    organization = canonicalize_organization(organization)
    start_year, end_year, is_current = years_from_text(segment)
    if is_current and start_year and ONE_OFF_ROLE_PATTERN.search(role):
        end_year = start_year
        is_current = False
    return {
        "organization": organization,
        "role": role,
        "affiliation_type": affiliation_type,
        "start_year": start_year,
        "end_year": end_year,
        "is_current": is_current,
        "evidence_text": clean_text(segment)[:500].rstrip(),
    }


def parse_experience(segment: str, organization: str = "") -> dict[str, object] | None:
    if organization:
        role = ROLE_STOP_PATTERN.sub("", segment)
        affiliation_type = (
            "education"
            if EDUCATION_TERMS.search(role) and not EMPLOYMENT_ROLE_TERMS.search(role)
            else "employment"
        )
        return make_entry(organization, role, affiliation_type, segment)
    match = LINKED_EXPERIENCE_PATTERN.match(segment) or PLAIN_EXPERIENCE_PATTERN.match(segment)
    if not match:
        return None
    role = strip_markdown(match.group("role"))
    parsed_organization = strip_markdown(match.group("organization"))
    if DATE_DURATION_PATTERN.match(parsed_organization):
        embedded = re.match(r"^(?P<role>.+?)\s+at\s+(?P<organization>.+)$", role, re.IGNORECASE)
        if not embedded:
            return None
        embedded_organization = strip_markdown(embedded.group("organization"))
        if not (
            EDUCATION_TERMS.search(embedded.group("role"))
            or INSTITUTION_TERMS.search(embedded_organization)
        ):
            return None
        return make_entry(
            embedded_organization,
            embedded.group("role"),
            "education",
            segment,
        )
    affiliation_type = (
        "education"
        if EDUCATION_TERMS.search(role) and not EMPLOYMENT_ROLE_TERMS.search(role)
        else "employment"
    )
    return make_entry(
        parsed_organization,
        role,
        affiliation_type,
        segment,
    )


def parse_education(segment: str) -> dict[str, object] | None:
    match = LINKED_EDUCATION_PATTERN.match(segment) or PLAIN_EDUCATION_PATTERN.match(segment)
    if match:
        if not EDUCATION_TERMS.search(match.group("role")):
            return None
        return make_entry(
            match.group("organization"),
            match.group("role"),
            "education",
            segment,
        )
    match = LINK_ONLY_PATTERN.match(segment)
    if not match:
        return None
    role = segment[match.end() :]
    role = ROLE_STOP_PATTERN.sub("", role)
    return make_entry(
        match.group("organization"),
        role if EDUCATION_TERMS.search(role) else "",
        "education",
        segment,
    )


def extract_affiliations(highlights: str) -> list[dict[str, object]]:
    text = str(highlights or "").replace("\xa0", " ")
    headings = list(HEADING_PATTERN.finditer(text))
    entries: list[dict[str, object]] = []
    section = ""
    grouped_organization = ""
    grouped_type = ""

    for index, heading in enumerate(headings):
        level = len(heading.group("marker"))
        end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
        raw_segment = text[heading.end() : end]
        segment = clean_text(raw_segment)
        if not segment:
            continue
        heading_title = clean_text(
            next((line for line in raw_segment.splitlines() if clean_text(line)), segment)
        )
        if level == 2:
            label = segment.casefold()
            section = "experience" if label.startswith("experience") else (
                "education" if label.startswith("education") else "ignore"
            )
            grouped_organization = ""
            grouped_type = ""
            continue
        if section == "ignore":
            continue

        entry = None
        next_level = (
            len(headings[index + 1].group("marker"))
            if index + 1 < len(headings)
            else 0
        )
        if level == 3 and section == "education":
            organization_match = LINK_ONLY_PATTERN.match(segment)
            if organization_match and next_level == 4:
                grouped_organization = strip_markdown(
                    organization_match.group("organization")
                )
                grouped_type = "education"
            else:
                grouped_organization = ""
                grouped_type = ""
                entry = parse_education(segment)
        elif level == 3 and section == "experience":
            entry = parse_experience(segment)
            if not entry:
                employer_match = LINK_ONLY_PATTERN.match(segment)
                grouped_organization = (
                    strip_markdown(employer_match.group("organization"))
                    if employer_match
                    else ""
                )
                grouped_type = "employment" if grouped_organization else ""
            else:
                grouped_organization = ""
                grouped_type = ""
        elif level == 4 and grouped_organization:
            entry = (
                make_entry(
                    grouped_organization,
                    heading_title,
                    "education",
                    segment,
                )
                if grouped_type == "education"
                else parse_experience(segment, grouped_organization)
            )
        elif level == 3:
            employer_match = LINK_ONLY_PATTERN.match(segment)
            if employer_match and next_level == 4:
                grouped_organization = strip_markdown(
                    employer_match.group("organization")
                )
                grouped_type = ""
            else:
                grouped_organization = ""
                grouped_type = ""
                entry = parse_education(segment)
                if not entry and ("(Current)" in segment or DATE_RANGE_PATTERN.search(segment)):
                    entry = parse_experience(segment)

        if entry:
            entries.append(entry)

    return entries


def load_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def is_linkedin(url: str) -> bool:
    return "linkedin.com/in/" in clean_text(url).casefold()


def rejected_urls(rows: list[dict[str, str]]) -> set[tuple[str, str]]:
    return {
        (clean_text(row.get("person_id")), canonical_url(clean_text(row.get("evidence_url"))))
        for row in rows
        if clean_text(row.get("person_id")) and clean_text(row.get("evidence_url"))
    }


def normalized_type(value: str, role: str = "") -> str:
    value = clean_text(value).casefold()
    if value in {"education", "qualification"}:
        role_text = clean_text(role).casefold()
        if re.search(r"\b(?:research(?:er| author)?|professor|lecturer|engineer)\b", role_text) and not EDUCATION_TERMS.search(role_text):
            return "employment"
        return "education"
    return "employment"


def row_key(row: dict[str, object]) -> tuple[str, ...]:
    return (
        clean_text(row.get("person_id")),
        normalized_type(
            clean_text(row.get("affiliation_type")), clean_text(row.get("role"))
        ),
        clean_text(row.get("organization")).casefold(),
        clean_text(row.get("role")).casefold(),
        clean_text(row.get("start_year")),
        clean_text(row.get("end_year")),
        canonical_url(clean_text(row.get("evidence_url"))),
    )


def education_score(
    row: dict[str, object],
    destination_organization: str,
    destination_is_education: bool,
    as_of_year: int,
) -> tuple[int, int, int, int, int]:
    role = clean_text(row.get("role")).casefold()
    organization = clean_text(row.get("organization")).casefold()
    end_text = clean_text(row.get("end_year"))
    end_year = int(end_text) if end_text.isdigit() else 0
    start_text = clean_text(row.get("start_year"))
    start_year = int(start_text) if start_text.isdigit() else 0
    completed = int(bool(end_year and end_year <= as_of_year))
    different_from_current_school = int(
        not destination_is_education
        or not destination_organization
        or organization != destination_organization.casefold()
    )
    degree_rank = 0
    if re.search(r"\b(?:ph\.?d|doctor)", role):
        degree_rank = 4
    elif re.search(r"\b(?:master|msc|ms\b)", role):
        degree_rank = 3
    elif re.search(r"\b(?:bachelor|bsc|bs\b|undergraduate)", role):
        degree_rank = 2
    elif "school" not in organization:
        degree_rank = 1
    return (
        different_from_current_school,
        degree_rank,
        completed,
        end_year,
        start_year,
    )


def build_rows(
    people: list[dict[str, object]],
    searches: list[dict[str, object]],
    identities: list[dict[str, str]],
    affiliations: list[dict[str, str]],
    verified: list[dict[str, str]],
    manual_affiliations: list[dict[str, str]],
    rejections: list[dict[str, str]],
    as_of_year: int,
    destination_reviews: list[dict[str, str]] | None = None,
) -> list[dict[str, object]]:
    people_by_id = {
        clean_text(person.get("person_id")): person
        for person in people
        if clean_text(person.get("confidence")) in {"probable", "confirmed"}
    }
    accepted_profiles: dict[str, set[str]] = defaultdict(set)
    for person_id, person in people_by_id.items():
        for field in ("linkedin_url", "profile_url"):
            url = clean_text(person.get(field))
            if is_linkedin(url):
                accepted_profiles[canonical_url(url)].add(person_id)

    result_texts: dict[str, set[str]] = defaultdict(set)
    for search in searches:
        for result in search.get("results", []):
            url_key = canonical_url(clean_text(result.get("url")))
            if url_key not in accepted_profiles:
                continue
            text = "\n".join(str(item) for item in result.get("highlights", []) if item)
            if clean_text(text):
                result_texts[url_key].add(text)

    rows: list[dict[str, object]] = []
    for url_key, person_ids in accepted_profiles.items():
        for highlights in sorted(result_texts.get(url_key, set()), key=len, reverse=True):
            for parsed in extract_affiliations(highlights):
                for person_id in person_ids:
                    person = people_by_id[person_id]
                    rows.append(
                        {
                            "person_id": person_id,
                            "name": clean_text(person.get("name")),
                            **parsed,
                            "selected_as_alma_mater": False,
                            "evidence_url": clean_text(person.get("linkedin_url"))
                            or clean_text(person.get("profile_url")),
                            "evidence_kind": "accepted_linkedin_profile",
                            "confidence": "probable",
                        }
                    )

    rejected = rejected_urls(rejections)
    identities_by_person: dict[str, list[dict[str, str]]] = defaultdict(list)
    for identity in identities:
        person_id = clean_text(identity.get("person_id"))
        if person_id not in people_by_id:
            continue
        candidate_urls = {
            canonical_url(clean_text(identity.get("profile_url"))),
            canonical_url(clean_text(identity.get("evidence_url"))),
        }
        if any((person_id, url) in rejected for url in candidate_urls if url):
            continue
        identities_by_person[person_id].append(identity)

    for affiliation in affiliations:
        person_id = clean_text(affiliation.get("person_id"))
        if person_id not in people_by_id:
            continue
        if CONFIDENCE_RANK.get(clean_text(affiliation.get("confidence")), 0) < 1:
            continue
        raw_type = clean_text(affiliation.get("affiliation_type")).casefold()
        if raw_type in {"distinction", "other"}:
            continue
        url_key = canonical_url(clean_text(affiliation.get("evidence_url")))
        if (person_id, url_key) in rejected:
            continue
        identity_rows = identities_by_person.get(person_id, [])
        best_identity = max(identity_rows, key=identity_sort_key, default=None)
        if not best_identity or not affiliation_supported_by_identity(
            affiliation, best_identity, identity_rows
        ):
            continue
        organization = clean_text(affiliation.get("organization"))
        role = clean_text(affiliation.get("role"))
        affiliation_type = normalized_type(raw_type, role)
        if affiliation_type == "education" and "olympiad" in organization.casefold():
            continue
        if not valid_affiliation(organization, role):
            continue
        organization = canonicalize_organization(organization)
        person = people_by_id[person_id]
        end_year = clean_text(affiliation.get("end_year"))
        rows.append(
            {
                "person_id": person_id,
                "name": clean_text(person.get("name")),
                "organization": organization,
                "role": role,
                "affiliation_type": affiliation_type,
                "start_year": clean_text(affiliation.get("start_year")),
                "end_year": end_year,
                "is_current": not bool(end_year),
                "selected_as_alma_mater": False,
                "evidence_url": clean_text(affiliation.get("evidence_url")),
                "evidence_kind": f"accepted_{clean_text(affiliation.get('source')) or 'structured'}",
                "confidence": clean_text(affiliation.get("confidence")),
                "evidence_text": clean_text(affiliation.get("evidence_text"))[:500].rstrip(),
            }
        )

    for manual in verified:
        person_id = clean_text(manual.get("person_id"))
        if person_id not in people_by_id:
            continue
        affiliation_type = normalized_type(
            clean_text(manual.get("affiliation_type")), clean_text(manual.get("role"))
        )
        if affiliation_type not in {"employment", "education"}:
            continue
        end_year = clean_text(manual.get("end_year"))
        rows.append(
            {
                "person_id": person_id,
                "name": clean_text(people_by_id[person_id].get("name")),
                "organization": canonicalize_organization(manual.get("organization")),
                "role": clean_text(manual.get("role")),
                "affiliation_type": affiliation_type,
                "start_year": clean_text(manual.get("start_year")),
                "end_year": end_year,
                "is_current": not bool(end_year),
                "selected_as_alma_mater": False,
                "evidence_url": clean_text(manual.get("career_evidence_url")),
                "evidence_kind": "manual_review",
                "confidence": clean_text(manual.get("confidence")) or "confirmed",
                "evidence_text": clean_text(manual.get("verification_basis"))[:500].rstrip(),
            }
        )

    for manual in manual_affiliations:
        person_id = clean_text(manual.get("person_id"))
        if person_id not in people_by_id:
            continue
        role = clean_text(manual.get("role"))
        affiliation_type = normalized_type(
            clean_text(manual.get("affiliation_type")), role
        )
        organization = canonicalize_organization(manual.get("organization"))
        evidence_url = clean_text(manual.get("evidence_url"))
        if (
            affiliation_type not in {"employment", "education"}
            or not valid_affiliation(organization, role)
            or not evidence_url
        ):
            continue
        end_year = clean_text(manual.get("end_year"))
        current_value = clean_text(manual.get("is_current")).casefold()
        is_current = current_value == "true" if current_value else not bool(end_year)
        rows.append(
            {
                "person_id": person_id,
                "name": clean_text(people_by_id[person_id].get("name")),
                "organization": organization,
                "role": role,
                "affiliation_type": affiliation_type,
                "start_year": clean_text(manual.get("start_year")),
                "end_year": end_year,
                "is_current": is_current,
                "selected_as_alma_mater": False,
                "evidence_url": evidence_url,
                "evidence_kind": clean_text(manual.get("evidence_kind"))
                or "manual_profile_transcription",
                "confidence": clean_text(manual.get("confidence")) or "confirmed",
                "evidence_text": clean_text(manual.get("evidence_text"))[:500].rstrip(),
            }
        )

    for review in destination_reviews or []:
        person_id = clean_text(review.get("person_id"))
        if person_id not in people_by_id:
            continue
        organization = canonicalize_organization(review.get("organization"))
        role = clean_text(review.get("role"))
        affiliation_type = normalized_type(
            clean_text(review.get("affiliation_type")), role
        )
        evidence_url = clean_text(review.get("evidence_url"))
        if (
            affiliation_type not in {"employment", "education"}
            or not valid_affiliation(organization, role)
            or not evidence_url
        ):
            continue
        end_year = clean_text(review.get("end_year"))
        is_current = not end_year or (
            affiliation_type == "education"
            and end_year.isdigit()
            and int(end_year) >= as_of_year
        )
        rows.append(
            {
                "person_id": person_id,
                "name": clean_text(people_by_id[person_id].get("name")),
                "organization": organization,
                "role": role,
                "affiliation_type": affiliation_type,
                "start_year": clean_text(review.get("start_year")),
                "end_year": end_year,
                "is_current": is_current,
                "selected_as_alma_mater": False,
                "evidence_url": evidence_url,
                "evidence_kind": "destination_source_review",
                "confidence": clean_text(people_by_id[person_id].get("confidence"))
                or "confirmed",
                "evidence_text": clean_text(review.get("review_reason"))[:500].rstrip(),
            }
        )

    deduplicated: dict[tuple[str, ...], dict[str, object]] = {}
    for row in rows:
        if not clean_text(row.get("organization")) or not clean_text(row.get("evidence_url")):
            continue
        key = row_key(row)
        existing = deduplicated.get(key)
        row_is_review = row.get("evidence_kind") == "destination_source_review"
        existing_is_review = bool(
            existing
            and existing.get("evidence_kind") == "destination_source_review"
        )
        if (
            not existing
            or (row_is_review and not existing_is_review)
            or (
                row_is_review == existing_is_review
                and len(clean_text(row.get("evidence_text")))
                > len(clean_text(existing.get("evidence_text")))
            )
        ):
            deduplicated[key] = row
    rows = list(deduplicated.values())

    education_by_person: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        if row["affiliation_type"] == "education":
            education_by_person[clean_text(row.get("person_id"))].append(row)
    for person_id, education_rows in education_by_person.items():
        person = people_by_id[person_id]
        selected = max(
            education_rows,
            key=lambda row: education_score(
                row,
                clean_text(person.get("organization")),
                clean_text(person.get("affiliation_type")) == "education",
                as_of_year,
            ),
        )
        selected["selected_as_alma_mater"] = True

    return sorted(
        rows,
        key=lambda row: (
            clean_text(row.get("name")).casefold(),
            clean_text(row.get("affiliation_type")),
            not bool(row.get("is_current")),
            clean_text(row.get("organization")).casefold(),
            clean_text(row.get("role")).casefold(),
        ),
    )


def write_outputs(
    rows: list[dict[str, object]], csv_path: Path, json_path: Path
) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    field: (
                        str(row.get(field)).lower()
                        if isinstance(row.get(field), bool)
                        else row.get(field, "")
                    )
                    for field in OUTPUT_FIELDS
                }
            )
    json_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--people", type=Path, default=DEFAULT_PEOPLE)
    parser.add_argument("--exa-audit", type=Path, default=DEFAULT_EXA_AUDIT)
    parser.add_argument("--exa-profiles", type=Path, default=DEFAULT_EXA_PROFILES)
    parser.add_argument("--identities", type=Path, default=DEFAULT_IDENTITIES)
    parser.add_argument("--affiliations", type=Path, default=DEFAULT_AFFILIATIONS)
    parser.add_argument("--verified", type=Path, default=DEFAULT_VERIFIED)
    parser.add_argument(
        "--manual-affiliations",
        type=Path,
        default=DEFAULT_MANUAL_AFFILIATIONS,
    )
    parser.add_argument(
        "--destination-reviews",
        type=Path,
        default=DEFAULT_DESTINATION_REVIEWS,
    )
    parser.add_argument("--rejections", type=Path, default=DEFAULT_REJECTIONS)
    parser.add_argument("--output-csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--as-of-year", type=int, default=2026)
    args = parser.parse_args()

    audit = json.loads(args.exa_audit.read_text(encoding="utf-8"))
    profile_audit = (
        json.loads(args.exa_profiles.read_text(encoding="utf-8"))
        if args.exa_profiles.exists()
        else {"profiles": []}
    )
    rows = build_rows(
        json.loads(args.people.read_text(encoding="utf-8")),
        audit.get("searches", [])
        + profile_search_records(profile_audit.get("profiles", [])),
        json.loads(args.identities.read_text(encoding="utf-8")),
        json.loads(args.affiliations.read_text(encoding="utf-8")),
        load_csv(args.verified),
        load_csv(args.manual_affiliations),
        load_csv(args.rejections),
        args.as_of_year,
        load_destination_reviews(args.destination_reviews),
    )
    write_outputs(rows, args.output_csv, args.output_json)
    print(
        json.dumps(
            {
                "affiliations": len(rows),
                "people": len({row["person_id"] for row in rows}),
                "employment": sum(row["affiliation_type"] == "employment" for row in rows),
                "education": sum(row["affiliation_type"] == "education" for row in rows),
                "alma_maters": sum(bool(row["selected_as_alma_mater"]) for row in rows),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
