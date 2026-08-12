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
NON_CHRONOLOGICAL_DIRECTORY_SOURCES = {
    "codeforces",
    "cphof",
    "cphof_codeforces",
}

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
    r"^(?P<role>(?:associate|bachelors?|b\.?\s*sc\.?|b\.?\s*s\.?|bs\b|b\.?\s*a\.?|b\.?\s*eng\.?|beng\b|masters?|m\.?\s*sc\.?|m\.?\s*s\.?|ms\b|m\.?\s*a\.?|m\.?\s*eng\.?|meng\b|ph\.?d|doctor|specialist|degree|diploma|бакалавр|магистр|специалист).{0,140}?)"
    r"\s+at\s+(?P<organization>.{2,160}?)"
    r"(?=\s+(?:(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+)?(?:19|20)\d{2}\s*-|\s+\.{3}|$)",
    re.IGNORECASE,
)
SECTION_EDUCATION_PATTERN = re.compile(
    r"^(?P<role>.{2,140}?)\s+at\s+(?P<organization>.{2,160}?)"
    r"(?=\s+(?:(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+)?(?:19|20)\d{2}\s*-|\s+\.{3}|$)",
    re.IGNORECASE,
)
LINK_ONLY_PATTERN = re.compile(
    r"^(?:at\s+)?\[(?P<organization>[^\]]{2,160})\]\([^)]+\)",
    re.IGNORECASE,
)
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
    r"\b(?:associate|bachelors?|b\.?\s*sc\.?|b\.?\s*s\.?|bs\b|b\.?\s*a\.?|b\.?\s*eng\.?|beng\b|masters?|m\.?\s*sc\.?|m\.?\s*s\.?|ms\b|m\.?\s*a\.?|m\.?\s*eng\.?|meng\b|ph\.?d|doctor|specialist|student|candidate|undergraduate|postgraduate|graduate|magistrant|degree|diploma|school|education|бакалавр|магистр|магистрант|специалист)\b",
    re.IGNORECASE,
)
POSTSECONDARY_ROLE_PATTERN = re.compile(
    r"\b(?:bachelors?|b\.?\s*sc\.?|b\.?\s*s\.?|bs\b|b\.?\s*a\.?|b\.?\s*eng\.?|beng\b|"
    r"masters?|m\.?\s*sc\.?|m\.?\s*s\.?|ms\b|m\.?\s*a\.?|m\.?\s*eng\.?|meng\b|mba\b|mph\b|"
    r"ph\.?d|doctor(?:ate)?|specialist|undergraduate|graduate (?:student|studies)|medical student|magistrant|бакалавр|магистр|магистрант|специалист)\b",
    re.IGNORECASE,
)
POSTSECONDARY_INSTITUTION_PATTERN = re.compile(
    r"\b(?:university|college|polytechnic|institute of technology|technical institute|"
    r"institute of science and technology|école polytechnique|"
    r"institute of physics and technology|"
    r"school of (?:economics|engineering|medicine|business)|école normale|graduate school)\b",
    re.IGNORECASE,
)
SECONDARY_INSTITUTION_PATTERN = re.compile(
    r"\b(?:high school|secondary school|international school|lyceum|gymnasium|intellectual schools?|"
    r"physics and mathematics school|boarding school|berufskolleg|haileybury)\b|\b(?:rfms|fizmat|bil)\b",
    re.IGNORECASE,
)
NON_ALMA_ROLE_PATTERN = re.compile(
    r"\b(?:research|teaching) assistants?\b|\bstudent researchers?\b|\binstructors?\b|\b(?:acting )?deans?\b|"
    r"\b(?:intern|fellow|visiting|exchange (?:student|program|semester|study|studies)|"
    r"summer (?:research )?(?:school|semester)|certificate|"
    r"short course|participant|director|manager|founder|co-?founder|chief|officer|partner|"
    r"analyst|consultant|developer|architect|president|head|lead|owner|advisor|"
    r"adviser|administrator|coordinator|research author)\b",
    re.IGNORECASE,
)
EMPLOYMENT_ROLE_TERMS = re.compile(
    r"\b(?:researcher|research assistant|teaching assistant|fellow|scientist|engineer|professor|lecturer|teacher)\b",
    re.IGNORECASE,
)
STRONG_EMPLOYMENT_ROLE_TERMS = re.compile(
    r"\b(?:director|manager|founder|co-?founder|chief|officer|partner|analyst|"
    r"consultant|developer|architect|president|head|lead|owner|"
    r"advisor|adviser|administrator|coordinator|(?:senior\s+)?specialist\s+of)\b",
    re.IGNORECASE,
)
SPECIALIST_ROLE_PATTERN = re.compile(
    r"\b(?:specialist|специалист)\b", re.IGNORECASE
)
SPECIALIST_DEGREE_PATTERN = re.compile(
    r"^\s*(?:"
    r"specialist(?:\s+degree)?(?=$|[\s,;(])"
    r"(?!\s+(?:of|at|for|with|in)\b)"
    r"|специалист\s*[,;(]"
    r")",
    re.IGNORECASE,
)
ASSOCIATE_EMPLOYMENT_PATTERN = re.compile(
    r"\b(?:postdoctoral(?:\s+research)?|senior)\s+associate\b",
    re.IGNORECASE,
)
ASSOCIATE_ROLE_PATTERN = re.compile(r"\bassociate\b", re.IGNORECASE)
ASSOCIATE_DEGREE_PATTERN = re.compile(
    r"^\s*associate(?:'s)?(?:\s+degree|\s+of\b|(?=\s*[,;(]|$))",
    re.IGNORECASE,
)
INSTITUTION_TERMS = re.compile(
    r"\b(?:university|institute|school|college|academy|universität|universitesi|université|университет)\b",
    re.IGNORECASE,
)
DATE_DURATION_PATTERN = re.compile(r"^(?:19|20)\d{2}\s*\(")
DATE_RANGE_FRAGMENT_PATTERN = re.compile(
    r"\b(?:19|20)\d{2}\s*[-–]\s*(?:19|20)\d{2}\b"
)
DEGREE_SENTENCE_ORGANIZATION_PATTERN = re.compile(
    r"^(?:associate|bachelors?|b\.?\s*sc\.?|b\.?\s*s\.?|bs\b|b\.?\s*a\.?|"
    r"b\.?\s*eng\.?|beng\b|masters?|m\.?\s*sc\.?|m\.?\s*s\.?|ms\b|"
    r"m\.?\s*a\.?|m\.?\s*eng\.?|meng\b|ph\.?d|doctor|specialist)\b.*\bat\b",
    re.IGNORECASE,
)
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
STUDENT_EDUCATION_ROLE_PATTERN = re.compile(
    r"(?:\b(?:bachelors?|masters?|ph\.?\s*d|doctoral|doctorate|undergraduate|"
    r"postgraduate|graduate|magistrant|магистрант)\b.*\b(?:student|candidate)\b|"
    r"\b(?:student|candidate)\b.*\b(?:bachelors?|masters?|ph\.?\s*d|doctoral|"
    r"doctorate|undergraduate|postgraduate|graduate|magistrant|магистрант)\b|"
    r"\b(?:ph\.?\s*d|doctoral)\s+researcher\b)",
    re.IGNORECASE,
)


def clean_text(value: object) -> str:
    text = "" if value is None else str(value)
    text = text.replace("\u00e2\u0080\u0099", "'")
    return re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()


def is_strong_employment_role(role: object) -> bool:
    role_text = clean_text(role)
    if STRONG_EMPLOYMENT_ROLE_TERMS.search(role_text):
        return True
    if ASSOCIATE_EMPLOYMENT_PATTERN.search(role_text):
        return True
    if ASSOCIATE_ROLE_PATTERN.search(role_text) and not ASSOCIATE_DEGREE_PATTERN.match(
        role_text
    ):
        return True
    return bool(
        SPECIALIST_ROLE_PATTERN.search(role_text)
        and not SPECIALIST_DEGREE_PATTERN.match(role_text)
    )


def is_student_education_role(role: object) -> bool:
    role_text = clean_text(role)
    if not role_text or is_strong_employment_role(role_text):
        return False
    if re.search(r"\bstudent researchers?\b", role_text, re.IGNORECASE):
        return False
    if STUDENT_EDUCATION_ROLE_PATTERN.search(role_text):
        return True
    return bool(
        re.fullmatch(
            r"(?:(?:full|part)[ -]?time\s+)?(?:student|undergraduate|postgraduate|"
            r"graduate student|doctoral student|ph\.?\s*d (?:student|candidate)|"
            r"magistrant(?: student)?|магистрант)",
            role_text,
            re.IGNORECASE,
        )
    )


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
    if DATE_RANGE_FRAGMENT_PATTERN.search(organization):
        return False
    if DEGREE_SENTENCE_ORGANIZATION_PATTERN.search(organization):
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
            if is_student_education_role(role)
            or (
                EDUCATION_TERMS.search(role)
                and not EMPLOYMENT_ROLE_TERMS.search(role)
                and not is_strong_employment_role(role)
            )
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
        if is_student_education_role(role)
        or (
            EDUCATION_TERMS.search(role)
            and not EMPLOYMENT_ROLE_TERMS.search(role)
            and not is_strong_employment_role(role)
        )
        else "employment"
    )
    return make_entry(
        parsed_organization,
        role,
        affiliation_type,
        segment,
    )


def parse_education(
    segment: str,
    *,
    trusted_section: bool = False,
    heading_title: str = "",
) -> dict[str, object] | None:
    match = (
        LINKED_EDUCATION_PATTERN.match(segment)
        or PLAIN_EDUCATION_PATTERN.match(segment)
        or (SECTION_EDUCATION_PATTERN.match(segment) if trusted_section else None)
    )
    if match:
        if not trusted_section and not EDUCATION_TERMS.search(match.group("role")):
            return None
        return make_entry(
            match.group("organization"),
            match.group("role"),
            "education",
            segment,
        )
    match = LINK_ONLY_PATTERN.match(segment)
    if match:
        heading_match = LINK_ONLY_PATTERN.match(heading_title)
        role = (
            heading_title[heading_match.end() :]
            if trusted_section and heading_match
            else segment[match.end() :]
        )
        role = ROLE_STOP_PATTERN.sub("", role)
        return make_entry(
            match.group("organization"),
            role if EDUCATION_TERMS.search(role) else "",
            "education",
            segment,
        )
    if trusted_section and heading_title:
        organization = strip_markdown(heading_title)
        canonical = canonicalize_organization(organization)
        if (
            POSTSECONDARY_INSTITUTION_PATTERN.search(canonical)
            or SECONDARY_INSTITUTION_PATTERN.search(canonical)
            or INSTITUTION_TERMS.search(canonical)
        ):
            return make_entry(canonical, "", "education", segment)
    return None


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
                entry = parse_education(
                    segment,
                    trusted_section=True,
                    heading_title=heading_title,
                )
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
    if is_student_education_role(role):
        return "education"
    if value in {"education", "qualification"}:
        role_text = clean_text(role).casefold()
        if is_strong_employment_role(role_text) or (
            EMPLOYMENT_ROLE_TERMS.search(role_text)
            and not EDUCATION_TERMS.search(role_text)
        ):
            return "employment"
        return "education"
    return "employment"


def is_current_affiliation(
    end_year: str, affiliation_type: str, as_of_year: int
) -> bool:
    """Treat education through its stated graduation year as current."""
    return not end_year or (
        affiliation_type == "education"
        and end_year.isdigit()
        and int(end_year) >= as_of_year
    )


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


def logical_row_key(row: dict[str, object]) -> tuple[str, ...]:
    return (
        clean_text(row.get("person_id")),
        normalized_type(
            clean_text(row.get("affiliation_type")), clean_text(row.get("role"))
        ),
        clean_text(row.get("organization")).casefold(),
        clean_text(row.get("role")).casefold(),
        canonical_url(clean_text(row.get("evidence_url"))),
    )


def evidence_explicitly_supports_dates(row: dict[str, object]) -> bool:
    start_year = clean_text(row.get("start_year"))
    end_year = clean_text(row.get("end_year"))
    if not start_year.isdigit():
        return False
    heading_context = clean_text(row.get("evidence_text"))[:320]
    if end_year.isdigit():
        return bool(
            re.search(
                rf"\b{re.escape(start_year)}\s*[-–]\s*{re.escape(end_year)}\b",
                heading_context,
            )
        )
    return bool(
        re.search(
            rf"\b{re.escape(start_year)}\s*[-–]\s*(?:present|current)\b",
            heading_context,
            re.IGNORECASE,
        )
    )


def date_ranges_overlap(
    left: dict[str, object], right: dict[str, object]
) -> bool:
    left_start = clean_text(left.get("start_year"))
    right_start = clean_text(right.get("start_year"))
    if not left_start.isdigit() or not right_start.isdigit():
        return False
    left_end = clean_text(left.get("end_year"))
    right_end = clean_text(right.get("end_year"))
    left_end_value = int(left_end) if left_end.isdigit() else 9999
    right_end_value = int(right_end) if right_end.isdigit() else 9999
    return max(int(left_start), int(right_start)) <= min(
        left_end_value, right_end_value
    )


def merge_undated_duplicates(
    rows: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Fold source-snippet duplicates into a dated record from the same source."""
    grouped: dict[tuple[str, ...], list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[logical_row_key(row)].append(row)

    merged: list[dict[str, object]] = []
    confidence_priority = {"candidate": 1, "probable": 2, "confirmed": 3}

    for group in grouped.values():
        dated = [
            row
            for row in group
            if clean_text(row.get("start_year")) or clean_text(row.get("end_year"))
        ]
        undated = [row for row in group if row not in dated]
        if (
            dated
            and logical_row_key(dated[0])[1] == "education"
            and POSTSECONDARY_ROLE_PATTERN.search(clean_text(dated[0].get("role")))
        ):
            explicit_profile_rows = [
                row
                for row in dated
                if clean_text(row.get("evidence_kind"))
                == "accepted_linkedin_profile"
                and evidence_explicitly_supports_dates(row)
            ]
            if explicit_profile_rows:
                dated = [
                    row
                    for row in dated
                    if clean_text(row.get("evidence_kind"))
                    != "accepted_linkedin_profile"
                    or evidence_explicitly_supports_dates(row)
                    or not any(
                        date_ranges_overlap(row, explicit)
                        for explicit in explicit_profile_rows
                    )
                ]
        reviewed_open_historical_starts = {
            clean_text(row.get("start_year"))
            for row in dated
            if clean_text(row.get("start_year"))
            and not clean_text(row.get("end_year"))
            and not bool(row.get("is_current"))
            and clean_text(row.get("evidence_kind")) != "manual_review"
        }
        dated = [
            row
            for row in dated
            if not (
                clean_text(row.get("start_year"))
                in reviewed_open_historical_starts
                and clean_text(row.get("end_year"))
                and clean_text(row.get("evidence_kind")) == "manual_review"
            )
        ]
        if not dated:
            merged.extend(undated)
            continue
        if not undated:
            merged.extend(dated)
            continue

        target = max(
            dated,
            key=lambda row: (
                not clean_text(row.get("end_year")),
                int(clean_text(row.get("start_year")))
                if clean_text(row.get("start_year")).isdigit()
                else 0,
                int(clean_text(row.get("end_year")))
                if clean_text(row.get("end_year")).isdigit()
                else 0,
            ),
        )
        for row in undated:
            target_kind = clean_text(target.get("evidence_kind"))
            row_kind = clean_text(row.get("evidence_kind"))
            if row_kind == "destination_source_review" and (
                target_kind != "destination_source_review"
                or len(clean_text(row.get("evidence_text")))
                > len(clean_text(target.get("evidence_text")))
            ):
                for field in ("evidence_kind", "evidence_text"):
                    target[field] = row.get(field, "")
            elif (
                row_kind == target_kind
                and len(clean_text(row.get("evidence_text")))
                > len(clean_text(target.get("evidence_text")))
            ):
                target["evidence_text"] = row.get("evidence_text", "")
            if confidence_priority.get(clean_text(row.get("confidence")), 0) > (
                confidence_priority.get(clean_text(target.get("confidence")), 0)
            ):
                target["confidence"] = row.get("confidence", "")
        merged.extend(dated)

    return merged


def apply_destination_review_precedence(
    rows: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Demote weaker open rows superseded by a destination review."""
    reviewed_organizations = {
        (
            clean_text(row.get("person_id")),
            normalized_type(
                clean_text(row.get("affiliation_type")), clean_text(row.get("role"))
            ),
            clean_text(row.get("organization")).casefold(),
        )
        for row in rows
        if clean_text(row.get("evidence_kind")) == "destination_source_review"
    }
    for row in rows:
        key = (
            clean_text(row.get("person_id")),
            normalized_type(
                clean_text(row.get("affiliation_type")), clean_text(row.get("role"))
            ),
            clean_text(row.get("organization")).casefold(),
        )
        if (
            key in reviewed_organizations
            and bool(row.get("is_current"))
            and clean_text(row.get("evidence_kind"))
            != "destination_source_review"
            and (
                clean_text(row.get("evidence_kind")) == "manual_review"
                or not clean_text(row.get("role"))
                or "alumn" in clean_text(row.get("role")).casefold()
            )
        ):
            row["is_current"] = False
    return rows


def education_score(
    row: dict[str, object],
    destination_organization: str,
    destination_is_education: bool,
    as_of_year: int,
) -> tuple[int, int, int, int, int, int]:
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
    elif re.search(r"\b(?:master|msc|ms\b|specialist|магистр|специалист)", role):
        degree_rank = 3
    elif re.search(r"\b(?:bachelor|bsc|bs\b|beng\b|b\.?\s*eng\.?|undergraduate|бакалавр)", role):
        degree_rank = 2
    elif "school" not in organization:
        degree_rank = 1
    degree_levels = sum(
        bool(pattern.search(role))
        for pattern in (
            re.compile(r"\b(?:bachelor|bsc|bs\b|beng\b|b\.?\s*eng\.?|undergraduate|бакалавр)"),
            re.compile(r"\b(?:master|msc|ms\b|specialist|магистр|специалист)"),
            re.compile(r"\b(?:ph\.?d|doctor)"),
        )
    )
    return (
        different_from_current_school,
        degree_rank,
        degree_levels,
        completed,
        end_year,
        start_year,
    )


def is_postsecondary_education(row: dict[str, object]) -> bool:
    role = clean_text(row.get("role"))
    organization = clean_text(row.get("organization"))
    evidence_text = clean_text(row.get("evidence_text"))
    if is_strong_employment_role(role):
        return False
    if NON_ALMA_ROLE_PATTERN.search(role):
        return False
    role_is_degree = bool(
        ASSOCIATE_DEGREE_PATTERN.match(role)
        or POSTSECONDARY_ROLE_PATTERN.search(role)
    )
    generic_graduate_role = bool(
        re.fullmatch(r"(?:graduate|postgraduate) student", role, re.IGNORECASE)
    )
    experience_style_role = evidence_text.casefold().startswith(
        f"{role.casefold()} - "
    )
    if (
        generic_graduate_role
        and experience_style_role
        and not POSTSECONDARY_INSTITUTION_PATTERN.search(organization)
    ):
        return False
    if not role_is_degree and NON_ALMA_ROLE_PATTERN.search(evidence_text):
        return False
    if role_is_degree:
        return True
    if SECONDARY_INSTITUTION_PATTERN.search(organization):
        return False
    return bool(POSTSECONDARY_INSTITUTION_PATTERN.search(organization))


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
    all_people_by_id = {
        clean_text(person.get("person_id")): person
        for person in people
        if clean_text(person.get("person_id"))
    }
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
        search_person_id = clean_text(search.get("person_id"))
        for result in search.get("results", []):
            url_key = canonical_url(clean_text(result.get("url")))
            if url_key not in accepted_profiles:
                continue
            if (
                search_person_id
                and search_person_id not in accepted_profiles[url_key]
            ):
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
        start_year = clean_text(affiliation.get("start_year"))
        end_year = clean_text(affiliation.get("end_year"))
        is_current = is_current_affiliation(end_year, affiliation_type, as_of_year)
        source = clean_text(affiliation.get("source"))
        if (
            source in NON_CHRONOLOGICAL_DIRECTORY_SOURCES
            and not role
            and not start_year
            and not end_year
        ):
            is_current = False
        if (
            source == "orcid"
            and affiliation_type == "employment"
            and not role
            and not start_year
            and not end_year
        ):
            is_current = False
        rows.append(
            {
                "person_id": person_id,
                "name": clean_text(person.get("name")),
                "organization": organization,
                "role": role,
                "affiliation_type": affiliation_type,
                "start_year": start_year,
                "end_year": end_year,
                "is_current": is_current,
                "selected_as_alma_mater": False,
                "evidence_url": clean_text(affiliation.get("evidence_url")),
                "evidence_kind": f"accepted_{source or 'structured'}",
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
                "is_current": is_current_affiliation(
                    end_year, affiliation_type, as_of_year
                ),
                "selected_as_alma_mater": False,
                "evidence_url": clean_text(manual.get("career_evidence_url")),
                "evidence_kind": "manual_review",
                "confidence": clean_text(manual.get("confidence")) or "confirmed",
                "evidence_text": clean_text(manual.get("verification_basis"))[:500].rstrip(),
            }
        )

    for manual in manual_affiliations:
        person_id = clean_text(manual.get("person_id"))
        if person_id not in all_people_by_id:
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
        is_current = (
            current_value == "true"
            if current_value
            else is_current_affiliation(end_year, affiliation_type, as_of_year)
        )
        rows.append(
            {
                "person_id": person_id,
                "name": clean_text(all_people_by_id[person_id].get("name")),
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
        is_current = is_current_affiliation(end_year, affiliation_type, as_of_year)
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
    rows = apply_destination_review_precedence(
        merge_undated_duplicates(list(deduplicated.values()))
    )

    education_by_person: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        if row["affiliation_type"] == "education":
            education_by_person[clean_text(row.get("person_id"))].append(row)
    for person_id, education_rows in education_by_person.items():
        person = all_people_by_id[person_id]
        postsecondary_rows = [
            row for row in education_rows if is_postsecondary_education(row)
        ]
        if not postsecondary_rows:
            secondary_rows = [
                row
                for row in education_rows
                if SECONDARY_INSTITUTION_PATTERN.search(
                    clean_text(row.get("organization"))
                )
                and not is_strong_employment_role(row.get("role"))
                and not NON_ALMA_ROLE_PATTERN.search(
                    f"{clean_text(row.get('role'))} {clean_text(row.get('evidence_text'))}"
                )
            ]
            if not secondary_rows:
                continue
            selected = max(
                secondary_rows,
                key=lambda row: education_score(
                    row,
                    clean_text(person.get("organization")),
                    clean_text(person.get("affiliation_type")) == "education",
                    as_of_year,
                ),
            )
            selected["selected_as_alma_mater"] = True
            continue
        candidates = postsecondary_rows
        selected_by_organization: dict[str, dict[str, object]] = {}
        for row in candidates:
            organization_key = clean_text(row.get("organization")).casefold()
            existing = selected_by_organization.get(organization_key)
            score = education_score(
                row,
                clean_text(person.get("organization")),
                clean_text(person.get("affiliation_type")) == "education",
                as_of_year,
            )
            if existing is None or score > education_score(
                existing,
                clean_text(person.get("organization")),
                clean_text(person.get("affiliation_type")) == "education",
                as_of_year,
            ):
                selected_by_organization[organization_key] = row
        for selected in selected_by_organization.values():
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
