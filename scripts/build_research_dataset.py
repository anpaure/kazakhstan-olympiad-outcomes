#!/usr/bin/env python3
"""Assemble one research-ready row per olympiad alumnus."""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path

try:
    from scripts.destination_reviews import load_destination_reviews
    from scripts.organization_names import canonicalize_organization
except ModuleNotFoundError:  # Direct script execution adds scripts/ to sys.path.
    from destination_reviews import load_destination_reviews
    from organization_names import canonicalize_organization


CONFIDENCE_RANK = {"unmatched": -1, "candidate": 0, "probable": 1, "confirmed": 2}
SOURCE_RANK = {
    "verified": 10,
    "cphof": 9,
    "orcid": 9,
    "github": 8,
    "cphof_codeforces": 8,
    "openalex_orcid": 7,
    "openalex": 6,
    "codeforces": 3,
}


@dataclass(frozen=True)
class ResearchedPerson:
    person_id: str
    name: str
    aliases: str
    olympiads: str
    years: str
    first_year: int
    last_year: int
    awards: str
    research_scope: str
    confidence: str
    identity_score: str
    identity_source: str
    profile_url: str
    linkedin_url: str
    organization: str
    role: str
    affiliation_type: str
    organization_category: str
    role_category: str
    destination_status: str
    destination_note: str
    start_year: str
    end_year: str
    country_code: str
    evidence_urls: str
    evidence_count: int
    sources: str
    verification_basis: str


def clean_text(value: object) -> str:
    text = "" if value is None else str(value)
    return re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def is_linkedin_profile(url: str) -> bool:
    return bool(
        re.match(
            r"^https?://(?:[a-z0-9-]+\.)?linkedin\.com/in/[^/?#]+/?(?:[?#].*)?$",
            clean_text(url),
            re.IGNORECASE,
        )
    )


def identity_sort_key(row: dict[str, str]) -> tuple[int, float, int]:
    return (
        CONFIDENCE_RANK.get(row.get("confidence", "candidate"), 0),
        float(row.get("score") or 0),
        SOURCE_RANK.get(row.get("source", ""), 0),
    )


def affiliation_sort_key(row: dict[str, str]) -> tuple[int, int, int, int, int]:
    affiliation_type = clean_text(row.get("affiliation_type")).casefold()
    type_rank = {
        "employment": 60,
        "company_or_organization": 55,
        "company": 55,
        "facility": 45,
        "education": 40,
        "qualification": 35,
        "organization": 25,
        "institution": 25,
        "distinction": 10,
    }.get(affiliation_type, 20)
    start_year = int(row["start_year"]) if clean_text(row.get("start_year")).isdigit() else 0
    active = int(not clean_text(row.get("end_year")))
    role_present = int(bool(clean_text(row.get("role"))))
    return (
        CONFIDENCE_RANK.get(row.get("confidence", "candidate"), 0),
        type_rank,
        SOURCE_RANK.get(row.get("source", ""), 0),
        active + role_present,
        start_year,
    )


def organization_category(organization: str, affiliation_type: str) -> str:
    normalized_organization = canonicalize_organization(organization).casefold()
    word_text = re.sub(r"[^\w]+", " ", normalized_organization).replace("_", " ")
    text = f" {clean_text(word_text)} "
    affiliation_type = clean_text(affiliation_type).casefold()
    if affiliation_type == "education":
        return "Education"
    if any(
        term in text
        for term in [
            " university ",
            " universities ",
            " institute ",
            " institutes ",
            " school ",
            " schools ",
            " academy ",
            " academies ",
            " college ",
            " lyceum ",
            " lyceums ",
            " gymnasium ",
            " education ",
            " akadem",
            " universität",
            " universidade",
            " olympiad team ",
            " olympic training ",
            " physics battles ",
        ]
    ) or normalized_organization in {
        "almaty ktl",
        "beyond curriculum pf",
        "binus international",
        "harbour.space",
        "hits",
        "hkust",
        "kaist",
        "mit",
        "nis medeu (nis phm almaty)",
        "qazcho",
        "rfms",
        "unist",
    }:
        return "Academia"
    if any(
        term in text
        for term in [
            "bank of canada",
            "national bank",
            "ministry",
            "government",
            "national laboratory",
            "security council",
        ]
    ):
        return "Government"
    if not clean_text(organization):
        return "Unknown"
    return "Industry"


def role_category(role: str, organization: str, affiliation_type: str) -> str:
    text = (
        f" {clean_text(role).casefold()} "
        f"{canonicalize_organization(organization).casefold()} "
    )
    affiliation_type = clean_text(affiliation_type).casefold()
    if any(term in text for term in ["student", "candidate", "bachelor", "master", "phd graduate"]):
        return "Student"
    if any(term in text for term in ["software", "developer", "machine learning", " ai ", "computer science"]):
        return "Software & AI"
    if any(term in text for term in ["economist", "finance", "bank", "quantitative"]):
        return "Economics & Finance"
    if any(term in text for term in ["professor", "research", "scientist", "postdoc", "phd"]):
        return "Research & Academia"
    if any(term in text for term in ["engineer", "engineering"]):
        return "Engineering"
    if any(
        term in text
        for term in [
            "head",
            "manager",
            "founder",
            "director",
            "principal",
            "coordinator",
            "deputy secretary",
        ]
    ):
        return "Leadership"
    if affiliation_type == "education":
        return "Student"
    return "Other"


def normalize_destination(
    organization: str,
    role: str,
    affiliation_type: str,
    start_year: str,
    end_year: str,
    as_of_year: int = 2026,
) -> tuple[str, str, str, str, str, str, str]:
    organization = canonicalize_organization(organization)
    role = clean_text(role)
    affiliation_type = clean_text(affiliation_type)
    start_year = clean_text(start_year)
    end_year = clean_text(end_year)
    if not organization:
        return "", "", "", "none", "No reviewed destination is available.", "", ""

    if role.casefold() == "research author":
        return (
            "",
            "",
            "",
            "history_only",
            "Publication authorship is retained in history but is not treated as a job.",
            "",
            "",
        )

    if not role and organization_category(organization, affiliation_type) in {
        "Academia",
        "Education",
    }:
        return (
            "",
            "",
            "",
            "history_only",
            "An undated academic organization without a student or staff role is retained only in history.",
            "",
            "",
        )

    if affiliation_type.casefold() == "education":
        role_text = role.casefold()
        active_student = bool(
            re.search(r"\b(?:student|ph\.?d candidate|doctoral candidate|incoming)\b", role_text)
        )
        end_is_current = not end_year or (
            end_year.isdigit() and int(end_year) >= as_of_year
        )
        if active_student and end_is_current:
            return (
                organization,
                role,
                "education",
                "current_education",
                "The latest reviewed destination is an active student affiliation.",
                start_year,
                end_year,
            )

        staff_role = bool(
            re.search(
                r"\b(?:researcher|scientist|professor|lecturer|teacher|engineer|faculty|postdoc)\b",
                role_text,
            )
        )
        if staff_role and not re.search(r"\b(?:student|candidate)\b", role_text):
            return (
                organization,
                role,
                "employment",
                "latest_employment",
                "A university staff role is treated as employment, not education.",
                start_year,
                end_year,
            )

        return (
            "",
            "",
            "",
            "history_only",
            "Completed or undated education is retained as alma-mater/history evidence, not as a destination.",
            "",
            "",
        )

    return (
        organization,
        role,
        affiliation_type,
        "latest_employment",
        "One reviewed latest employment or organizational role is used as the destination.",
        start_year,
        end_year,
    )


def best_linkedin(rows: list[dict[str, str]], minimum_confidence: str) -> str:
    minimum_rank = CONFIDENCE_RANK[minimum_confidence]
    for row in sorted(rows, key=identity_sort_key, reverse=True):
        if CONFIDENCE_RANK.get(row.get("confidence", "candidate"), 0) < minimum_rank:
            continue
        for url in clean_text(row.get("outbound_urls")).split(";"):
            if is_linkedin_profile(url):
                return url
        if is_linkedin_profile(clean_text(row.get("profile_url"))):
            return clean_text(row.get("profile_url"))
    return ""


def identity_urls(row: dict[str, str]) -> set[str]:
    urls = {
        clean_text(row.get("profile_url")).rstrip("/"),
        clean_text(row.get("evidence_url")).rstrip("/"),
    }
    urls.update(
        clean_text(url).rstrip("/")
        for url in clean_text(row.get("outbound_urls")).split(";")
        if clean_text(url)
    )
    return {url for url in urls if url}


def rejected_candidate(
    row: dict[str, str], rejected_urls: set[tuple[str, str]]
) -> bool:
    person_id = clean_text(row.get("person_id"))
    candidate_urls = {
        clean_text(row.get("profile_url")).rstrip("/"),
        clean_text(row.get("evidence_url")).rstrip("/"),
    }
    return any(
        (person_id, url) in rejected_urls for url in candidate_urls if url
    )


def affiliation_supported_by_identity(
    affiliation: dict[str, str],
    best_identity: dict[str, str],
    identity_rows: list[dict[str, str]],
) -> bool:
    evidence_url = clean_text(affiliation.get("evidence_url")).rstrip("/")
    if evidence_url and evidence_url in identity_urls(best_identity):
        return True

    support_reasons = {
        "kazakhstan_context",
        "direct_olympiad_evidence",
    }
    for identity_row in identity_rows:
        if evidence_url and evidence_url not in identity_urls(identity_row):
            continue
        reasons = {
            reason
            for reason in clean_text(identity_row.get("score_reasons")).split(";")
            if reason
        }
        if reasons & support_reasons:
            return True
    return False


def build_rows(
    people: list[dict[str, str]],
    identities: list[dict[str, str]],
    affiliations: list[dict[str, str]],
    verified: list[dict[str, str]],
    rejections: list[dict[str, str]] | None = None,
    destination_reviews: list[dict[str, str]] | None = None,
) -> list[ResearchedPerson]:
    rejected_urls = {
        (
            clean_text(row.get("person_id")),
            clean_text(row.get("evidence_url")).rstrip("/"),
        )
        for row in rejections or []
        if clean_text(row.get("person_id")) and clean_text(row.get("evidence_url"))
    }
    identities_by_person: dict[str, list[dict[str, str]]] = defaultdict(list)
    affiliations_by_person: dict[str, list[dict[str, str]]] = defaultdict(list)
    verified_by_person = {row["person_id"]: row for row in verified}
    destination_review_by_person: dict[str, dict[str, str]] = {}
    for review in destination_reviews or []:
        person_id = clean_text(review.get("person_id"))
        if person_id in destination_review_by_person:
            raise ValueError(f"duplicate destination review for {person_id}")
        destination_review_by_person[person_id] = review
    for row in identities:
        if rejected_candidate(row, rejected_urls):
            continue
        identities_by_person[row["person_id"]].append(row)
    for row in affiliations:
        if rejected_candidate(row, rejected_urls):
            continue
        affiliations_by_person[row["person_id"]].append(row)

    output: list[ResearchedPerson] = []
    for person in people:
        person_id = person["person_id"]
        identity_rows = identities_by_person.get(person_id, [])
        affiliation_rows = affiliations_by_person.get(person_id, [])
        manual = verified_by_person.get(person_id)
        best_identity = max(identity_rows, key=identity_sort_key, default=None)
        eligible_affiliations = affiliation_rows
        if best_identity and CONFIDENCE_RANK.get(best_identity["confidence"], 0) >= 1:
            eligible_affiliations = [
                row
                for row in affiliation_rows
                if CONFIDENCE_RANK.get(row.get("confidence", "candidate"), 0) >= 1
                and affiliation_supported_by_identity(row, best_identity, identity_rows)
            ]
        best_affiliation = max(
            eligible_affiliations, key=affiliation_sort_key, default=None
        )
        display_name = person["canonical_name"]

        if manual:
            display_name = clean_text(manual.get("name")) or display_name
            confidence = clean_text(manual.get("confidence")) or "confirmed"
            identity_score = "1.0"
            identity_source = "verified"
            profile_url = manual["career_evidence_url"]
            linkedin_url = manual["linkedin_url"]
            organization = manual["organization"]
            role = manual["role"]
            affiliation_type = manual["affiliation_type"]
            start_year = manual["start_year"]
            end_year = manual["end_year"]
            country_code = ""
            verification_basis = manual["verification_basis"]
            manual_urls = [
                manual["olympiad_evidence_url"],
                manual["career_evidence_url"],
                manual["linkedin_url"],
            ]
        else:
            confidence = best_identity["confidence"] if best_identity else "unmatched"
            if best_affiliation:
                confidence = min(
                    [confidence, best_affiliation["confidence"]],
                    key=lambda value: CONFIDENCE_RANK.get(value, 0),
                )
            identity_score = best_identity["score"] if best_identity else ""
            identity_source = best_identity["source"] if best_identity else ""
            profile_url = best_identity["profile_url"] if best_identity else ""
            linkedin_url = best_linkedin(identity_rows, confidence) if best_identity else ""
            organization = best_affiliation["organization"] if best_affiliation else (
                best_identity["organization"] if best_identity else ""
            )
            role = best_affiliation["role"] if best_affiliation else (
                best_identity["role"] if best_identity else ""
            )
            affiliation_type = best_affiliation["affiliation_type"] if best_affiliation else ""
            start_year = best_affiliation["start_year"] if best_affiliation else ""
            end_year = best_affiliation["end_year"] if best_affiliation else ""
            country_code = best_affiliation["country_code"] if best_affiliation else ""
            verification_parts = [
                best_identity["evidence_text"] if best_identity else "",
                best_affiliation["evidence_text"] if best_affiliation else "",
            ]
            verification_basis = "; ".join(
                dict.fromkeys(part for part in verification_parts if clean_text(part))
            )
            manual_urls = []

        destination_review = destination_review_by_person.get(person_id)
        if destination_review:
            organization = destination_review["organization"]
            role = destination_review["role"]
            affiliation_type = destination_review["affiliation_type"]
            start_year = destination_review["start_year"]
            end_year = destination_review["end_year"]
            review_url = clean_text(destination_review.get("evidence_url"))
            if review_url:
                profile_url = review_url
                if is_linkedin_profile(review_url):
                    linkedin_url = review_url
                manual_urls.append(review_url)
            review_reason = clean_text(destination_review.get("review_reason"))
            if review_reason:
                verification_basis = "; ".join(
                    part
                    for part in [verification_basis, f"Destination review: {review_reason}"]
                    if part
                )

        (
            organization,
            role,
            affiliation_type,
            destination_status,
            destination_note,
            start_year,
            end_year,
        ) = normalize_destination(
            organization,
            role,
            affiliation_type,
            start_year,
            end_year,
        )
        if not organization:
            country_code = ""

        urls = {
            clean_text(url)
            for url in manual_urls
            + [row.get("evidence_url", "") for row in identity_rows]
            + [row.get("evidence_url", "") for row in affiliation_rows]
            if clean_text(url)
        }
        sources = {row["source"] for row in identity_rows if row.get("source")}
        if manual:
            sources.add("verified")
        output.append(
            ResearchedPerson(
                person_id=person_id,
                name=display_name,
                aliases=person["aliases"],
                olympiads=person["olympiads"],
                years=person["years"],
                first_year=int(person["first_year"]),
                last_year=int(person["last_year"]),
                awards=person["awards"],
                research_scope=person["research_scope"],
                confidence=confidence,
                identity_score=identity_score,
                identity_source=identity_source,
                profile_url=profile_url,
                linkedin_url=linkedin_url,
                organization=organization,
                role=role,
                affiliation_type=affiliation_type,
                organization_category=organization_category(organization, affiliation_type),
                role_category=role_category(role, organization, affiliation_type),
                destination_status=destination_status,
                destination_note=destination_note,
                start_year=start_year,
                end_year=end_year,
                country_code=country_code,
                evidence_urls=";".join(sorted(urls)),
                evidence_count=len(urls),
                sources=";".join(sorted(sources)),
                verification_basis=verification_basis,
            )
        )
    return output


def write_outputs(rows: list[ResearchedPerson], csv_path: Path, json_path: Path) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(ResearchedPerson.__dataclass_fields__)
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))
    json_path.write_text(
        json.dumps([asdict(row) for row in rows], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--people-csv", default="data/people.csv")
    parser.add_argument("--identity-csv", default="data/identity_candidates.csv")
    parser.add_argument("--affiliation-csv", default="data/affiliation_candidates.csv")
    parser.add_argument("--verified-csv", default="data/verified_evidence.csv")
    parser.add_argument(
        "--rejections-csv", default="data/rejected_identity_candidates.csv"
    )
    parser.add_argument(
        "--destination-reviews-csv", default="data/destination_reviews.csv"
    )
    parser.add_argument("--out-csv", default="data/researched_people.csv")
    parser.add_argument("--out-json", default="data/researched_people.json")
    args = parser.parse_args()

    rows = build_rows(
        load_csv(Path(args.people_csv)),
        load_csv(Path(args.identity_csv)),
        load_csv(Path(args.affiliation_csv)),
        load_csv(Path(args.verified_csv)),
        load_csv(Path(args.rejections_csv)),
        load_destination_reviews(Path(args.destination_reviews_csv)),
    )
    write_outputs(rows, Path(args.out_csv), Path(args.out_json))
    confidence_counts = Counter(row.confidence for row in rows)
    researched = [
        row for row in rows if row.confidence in {"probable", "confirmed"}
    ]
    print(
        json.dumps(
            {
                "people": len(rows),
                "researched_people": len(researched),
                "candidate_only_people": confidence_counts["candidate"],
                "with_organization": sum(bool(row.organization) for row in researched),
                "with_linkedin": sum(bool(row.linkedin_url) for row in researched),
                "confidence": dict(sorted(confidence_counts.items())),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
