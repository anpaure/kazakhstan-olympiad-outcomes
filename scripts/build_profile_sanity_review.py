#!/usr/bin/env python3
"""Build reproducible profile-review and LinkedIn reconciliation audit tables."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

try:
    from scripts.build_affiliation_history import extract_affiliations
    from scripts.build_exa_review_queue import canonical_url
    from scripts.organization_names import canonicalize_organization
except ModuleNotFoundError:  # Direct script execution adds scripts/ to sys.path.
    from build_affiliation_history import extract_affiliations
    from build_exa_review_queue import canonical_url
    from organization_names import canonicalize_organization


SAMPLE_SEED = "20260812-round4"
ERA_CUTOFF_YEAR = 2005
SAMPLE_PER_STRATUM = 12
REVIEWED_AT = "2026-08-13"
DATA_AS_OF_YEAR = 2026
DEFAULT_REVIEW_DECISIONS = Path("data/profile_sanity_review_decisions.csv")

SAMPLE_FIELDS = [
    "sample_seed",
    "stratum",
    "sample_rank",
    "sample_hash",
    "review_fingerprint",
    "person_id",
    "name",
    "olympiads",
    "years",
    "outcome_status",
    "organization",
    "role",
    "destination_status",
    "outcome_country_name",
    "outcome_location_label",
    "alma_mater",
    "primary_profile_url",
    "linkedin_url",
    "participation_source_urls",
    "identity_source_urls",
    "destination_source_urls",
    "location_source_url",
    "alma_mater_source_urls",
    "profile_hydration_status",
    "profile_current_affiliations",
    "linkedin_destination_alignment",
    "participation_check",
    "destination_check",
    "country_check",
    "alma_mater_check",
    "manual_review_status",
    "review_depth",
    "reviewed_at",
    "review_note",
]

RECONCILIATION_FIELDS = [
    "person_id",
    "name",
    "linkedin_url",
    "profile_hydration_status",
    "profile_current_organizations",
    "profile_current_roles",
    "published_destination",
    "published_role",
    "organization_alignment",
    "role_alignment",
    "alignment_status",
    "review_decision",
    "review_reason",
    "review_reference_url",
]

FINDING_FIELDS = [
    "finding_id",
    "affected_person_ids",
    "affected_names",
    "review_scope",
    "severity",
    "issue",
    "root_cause",
    "correction",
    "prevention",
    "evidence_urls",
    "status",
    "reviewed_at",
]

REVIEW_DECISION_FIELDS = [
    "sample_seed",
    "person_id",
    "review_fingerprint",
    "review_depth",
    "review_status",
    "reviewed_at",
    "review_note",
]

REVIEW_FINGERPRINT_FIELDS = [
    "person_id",
    "name",
    "olympiads",
    "years",
    "outcome_status",
    "organization",
    "role",
    "destination_status",
    "outcome_country_name",
    "outcome_location_label",
    "alma_mater",
    "primary_profile_url",
    "linkedin_url",
    "participation_source_urls",
    "identity_source_urls",
    "destination_source_urls",
    "location_source_url",
    "alma_mater_source_urls",
    "profile_hydration_status",
    "profile_current_affiliations",
    "linkedin_destination_alignment",
]


def clean_text(value: object) -> str:
    return " ".join(str(value or "").replace("\xa0", " ").split())


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def write_rows(path: Path, rows: list[dict[str, object]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    path.with_suffix(".json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def joined(values: list[str] | set[str]) -> str:
    return ";".join(sorted({clean_text(value) for value in values if clean_text(value)}))


def sample_hash(seed: str, stratum: str, person_id: str) -> str:
    return hashlib.sha256(f"{seed}:{stratum}:{person_id}".encode()).hexdigest()


def review_fingerprint(row: dict[str, object]) -> str:
    payload = "\x1f".join(clean_text(row.get(field)) for field in REVIEW_FINGERPRINT_FIELDS)
    return hashlib.sha256(payload.encode()).hexdigest()[:20]


def load_review_decisions(path: Path) -> dict[tuple[str, str], dict[str, str]]:
    if not path.exists():
        return {}
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != REVIEW_DECISION_FIELDS:
            raise ValueError(
                f"Unexpected profile review decision fields: {reader.fieldnames!r}"
            )
        rows = list(reader)
    decisions: dict[tuple[str, str], dict[str, str]] = {}
    for index, raw in enumerate(rows, start=2):
        row = {field: clean_text(raw.get(field)) for field in REVIEW_DECISION_FIELDS}
        key = (row["sample_seed"], row["person_id"])
        if not all(row.values()) or key in decisions:
            raise ValueError(f"Incomplete or duplicate profile review decision at row {index}")
        if row["review_status"] not in {"pass", "pass_after_correction"}:
            raise ValueError(f"Invalid profile review status at row {index}")
        if row["review_depth"] not in {"standard", "deep"}:
            raise ValueError(f"Invalid profile review depth at row {index}")
        decisions[key] = row
    return decisions


def select_sample(
    people: list[dict[str, str]],
    seed: str = SAMPLE_SEED,
    cutoff_year: int = ERA_CUTOFF_YEAR,
    per_stratum: int = SAMPLE_PER_STRATUM,
    excluded_person_ids: set[str] | None = None,
) -> list[dict[str, object]]:
    excluded_person_ids = excluded_person_ids or set()
    selected: list[dict[str, object]] = []
    for confidence in ("probable", "confirmed"):
        for era, predicate in (
            ("older", lambda year: year <= cutoff_year),
            ("newer", lambda year: year > cutoff_year),
        ):
            stratum = f"{confidence}_{era}"
            cohort = [
                row
                for row in people
                if row.get("confidence") == confidence
                and row.get("person_id") not in excluded_person_ids
                and row.get("first_year", "").isdigit()
                and predicate(int(row["first_year"]))
            ]
            ranked = sorted(
                cohort,
                key=lambda row: sample_hash(seed, stratum, row["person_id"]),
            )
            if len(ranked) < per_stratum:
                raise ValueError(
                    f"{stratum} contains {len(ranked)} people; need {per_stratum}"
                )
            for rank, row in enumerate(ranked[:per_stratum], start=1):
                selected.append(
                    {
                        "person": row,
                        "stratum": stratum,
                        "sample_rank": rank,
                        "sample_hash": sample_hash(seed, stratum, row["person_id"])[
                            :16
                        ],
                    }
                )
    return selected


def parsed_current_affiliations(profile: dict[str, object]) -> list[dict[str, object]]:
    if profile.get("status") not in {
        "success",
        "search_cache",
        "manual_public_profile",
    }:
        return []
    rows = []
    for row in extract_affiliations(str(profile.get("text") or "")):
        end_year = clean_text(row.get("end_year"))
        active_bounded_education = (
            row.get("affiliation_type") == "education"
            and end_year.isdigit()
            and int(end_year) >= DATA_AS_OF_YEAR
        )
        if (row.get("is_current") or active_bounded_education) and clean_text(
            row.get("organization")
        ):
            rows.append(row)
    deduplicated: dict[tuple[str, str, str], dict[str, object]] = {}
    for row in rows:
        organization = canonicalize_organization(clean_text(row.get("organization")))
        key = (
            organization,
            clean_text(row.get("role")),
            clean_text(row.get("affiliation_type")),
        )
        deduplicated[key] = {**row, "organization": organization}
    return sorted(
        deduplicated.values(),
        key=lambda row: (
            clean_text(row.get("organization")).casefold(),
            clean_text(row.get("role")).casefold(),
        ),
    )


def parsed_historical_affiliations(profile: dict[str, object]) -> list[dict[str, object]]:
    if profile.get("status") not in {
        "success",
        "search_cache",
        "manual_public_profile",
    }:
        return []
    output = []
    for row in extract_affiliations(str(profile.get("text") or "")):
        if row.get("is_current") or not clean_text(row.get("organization")):
            continue
        output.append(
            {
                **row,
                "organization": canonicalize_organization(row.get("organization")),
            }
        )
    return output


ROLE_TRANSLATIONS = {
    "генеральный директор": "chief executive officer director",
    "директор": "director",
    "директор по информационным технологиям": "director information technology",
    "директор по продажам": "sales director",
    "исполнительный директор": "chief implementation officer executive director",
    "основатель": "founder",
    "специалист по маркетингу": "marketing specialist",
    "учитель биологии": "biology teacher",
}
ROLE_TOKEN_ALIASES = {
    "ceo": {"chief", "executive", "officer"},
    "cio": {"chief", "information", "officer"},
    "cfo": {"chief", "financial", "officer"},
    "cto": {"chief", "technology", "officer"},
    "owner": {"founder", "entrepreneur"},
}
ROLE_STOP_WORDS = {
    "a",
    "an",
    "and",
    "at",
    "for",
    "in",
    "of",
    "on",
    "the",
    "current",
    "junior",
    "senior",
}


def role_tokens(value: object) -> set[str]:
    text = clean_text(value).casefold()
    text = ROLE_TRANSLATIONS.get(text, text)
    tokens = set(re.findall(r"[a-z0-9]+", text)) - ROLE_STOP_WORDS
    for token in list(tokens):
        tokens.update(ROLE_TOKEN_ALIASES.get(token, set()))
    return tokens


def roles_compatible(
    published_role: str,
    profile_role: str,
    published_type: str = "",
    profile_type: str = "",
) -> bool:
    published = clean_text(published_role)
    profile = clean_text(profile_role)
    if not published or not profile:
        return True
    if published.casefold() in profile.casefold() or profile.casefold() in published.casefold():
        return True
    left = role_tokens(published)
    right = role_tokens(profile)
    if left and right and (
        len(left & right) >= 2
        or len(left & right) / min(len(left), len(right)) >= 0.5
    ):
        return True
    if published_type == profile_type == "education":
        degree_terms = {"bachelor", "doctoral", "doctor", "phd", "student", "undergraduate"}
        if left & degree_terms and right & degree_terms:
            return True
    return False


def build_reconciliation(
    people: list[dict[str, str]],
    profiles: list[dict[str, object]],
    destination_reviews: list[dict[str, str]],
    outcome_decisions: list[dict[str, str]],
    evidence: list[dict[str, str]] | None = None,
) -> list[dict[str, object]]:
    people_by_id = {row["person_id"]: row for row in people}
    reviews_by_id = {row["person_id"]: row for row in destination_reviews}
    decisions_by_key = {
        (row["person_id"], canonical_url(row.get("candidate_url", ""))): row
        for row in outcome_decisions
    }
    outcome_evidence_by_id: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in evidence or []:
        if (
            row.get("supports_final_outcome") == "True"
            and row.get("review_status") in {"accepted", "supporting"}
            and row.get("claim_type") != "public_profile"
            and clean_text(row.get("source_url"))
        ):
            outcome_evidence_by_id[row["person_id"]].append(row)
    output: list[dict[str, object]] = []

    for profile in sorted(profiles, key=lambda row: clean_text(row.get("name")).casefold()):
        person_id = clean_text(profile.get("person_id"))
        person = people_by_id[person_id]
        current = parsed_current_affiliations(profile)
        historical = parsed_historical_affiliations(profile)
        current_organizations = {
            clean_text(row.get("organization")) for row in current if row.get("organization")
        }
        final_organization = canonicalize_organization(person.get("organization", ""))
        matching_current = [
            row
            for row in current
            if clean_text(row.get("organization")) == final_organization
        ]
        role_matches = [
            row
            for row in matching_current
            if roles_compatible(
                person.get("role", ""),
                clean_text(row.get("role")),
                person.get("affiliation_type", ""),
                clean_text(row.get("affiliation_type")),
            )
        ]
        profile_key = canonical_url(clean_text(profile.get("linkedin_url")))
        destination_review = reviews_by_id.get(person_id)
        outcome_decision = decisions_by_key.get((person_id, profile_key))
        profile_status = clean_text(profile.get("status"))
        bounded_destination_rows = [
            row
            for row in historical
            if clean_text(row.get("organization")) == final_organization
            and clean_text(row.get("end_year")).isdigit()
            and int(clean_text(row.get("end_year"))) <= DATA_AS_OF_YEAR
        ]
        matching_bounded_destination_rows = [
            row
            for row in bounded_destination_rows
            if clean_text(person.get("end_year"))
            and clean_text(row.get("end_year")) == clean_text(person.get("end_year"))
            and roles_compatible(
                person.get("role", ""),
                clean_text(row.get("role")),
                person.get("affiliation_type", ""),
                clean_text(row.get("affiliation_type")),
            )
        ]

        fallback_evidence = sorted(
            outcome_evidence_by_id.get(person_id, []),
            key=lambda row: (
                row.get("review_status") == "accepted",
                row.get("claim_type") in {"destination_source_review", "career_outcome"},
                row.get("claim_type") == "olympiad_identity_bridge",
            ),
            reverse=True,
        )
        fallback = fallback_evidence[0] if fallback_evidence else {}
        if profile_status == "error":
            organization_alignment = "not_checked"
            role_alignment = "not_checked"
            alignment = "profile_retrieval_unavailable"
        elif not current and matching_bounded_destination_rows:
            organization_alignment = "matched"
            role_alignment = "matched"
            alignment = "matched_historical_profile"
        elif not current and bounded_destination_rows and destination_review:
            organization_alignment = "reconciled"
            role_alignment = "reconciled"
            alignment = "reconciled_destination_review"
        elif not current and bounded_destination_rows and outcome_decision:
            organization_alignment = "reconciled"
            role_alignment = "reconciled"
            alignment = "reconciled_source_precedence"
        elif not current and bounded_destination_rows:
            organization_alignment = "unreconciled"
            role_alignment = "unreconciled"
            alignment = "unreconciled_bounded_profile_destination"
        elif not current:
            organization_alignment = "not_parsed"
            role_alignment = "not_parsed"
            alignment = "no_current_affiliation_parsed"
        elif matching_current and role_matches:
            organization_alignment = "matched"
            role_alignment = "matched"
            alignment = "matched_current_profile"
        elif matching_current and destination_review:
            organization_alignment = "matched"
            role_alignment = "reconciled"
            alignment = "reconciled_destination_review"
        elif matching_current and outcome_decision:
            organization_alignment = "matched"
            role_alignment = "reconciled"
            alignment = "reconciled_source_precedence"
        elif matching_current:
            organization_alignment = "matched"
            role_alignment = "unreconciled"
            alignment = "unreconciled_role"
        elif destination_review:
            organization_alignment = "reconciled"
            role_alignment = "reconciled"
            alignment = "reconciled_destination_review"
        elif outcome_decision:
            organization_alignment = "reconciled"
            role_alignment = "reconciled"
            alignment = "reconciled_source_precedence"
        else:
            organization_alignment = "unreconciled"
            role_alignment = "unreconciled"
            alignment = "unreconciled_organization"

        review_row = destination_review or outcome_decision or {}
        if profile_status == "error" and not review_row and fallback:
            review_row = fallback
        output.append(
            {
                "person_id": person_id,
                "name": person["name"],
                "linkedin_url": clean_text(profile.get("linkedin_url")),
                "profile_hydration_status": profile_status,
                "profile_current_organizations": joined(current_organizations),
                "profile_current_roles": joined(
                    {
                        clean_text(row.get("role"))
                        for row in current
                        if clean_text(row.get("role"))
                    }
                ),
                "published_destination": final_organization,
                "published_role": person.get("role", ""),
                "organization_alignment": organization_alignment,
                "role_alignment": role_alignment,
                "alignment_status": alignment,
                "review_decision": (
                    "destination_source_review"
                    if destination_review
                    else outcome_decision.get("decision", "")
                    if outcome_decision
                    else "verified_fallback_source"
                    if profile_status == "error" and fallback
                    else ""
                ),
                "review_reason": review_row.get("review_reason", "")
                or review_row.get("reason", "")
                or (
                    f"Exa profile retrieval is unavailable; the published outcome is "
                    f"retained from {review_row.get('claim_type', 'separate reviewed')} "
                    "evidence."
                    if profile_status == "error" and review_row
                    else ""
                ),
                "review_reference_url": review_row.get("evidence_url", "")
                or review_row.get("review_evidence_url", "")
                or review_row.get("source_url", ""),
            }
        )
    return output


def build_sample_rows(
    selected: list[dict[str, object]],
    audit_people: list[dict[str, str]],
    evidence: list[dict[str, str]],
    affiliations: list[dict[str, str]],
    profiles: list[dict[str, object]],
    reconciliation: list[dict[str, object]],
    seed: str,
    review_decisions: dict[tuple[str, str], dict[str, str]] | None = None,
) -> list[dict[str, object]]:
    audit_people_by_id = {row["person_id"]: row for row in audit_people}
    profiles_by_id = {clean_text(row.get("person_id")): row for row in profiles}
    reconciliation_by_id = {row["person_id"]: row for row in reconciliation}
    evidence_by_id: dict[str, list[dict[str, str]]] = defaultdict(list)
    affiliations_by_id: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in evidence:
        evidence_by_id[row["person_id"]].append(row)
    for row in affiliations:
        affiliations_by_id[row["person_id"]].append(row)

    output: list[dict[str, object]] = []
    for selection in selected:
        person = selection["person"]
        person_id = person["person_id"]
        audit_person = audit_people_by_id[person_id]
        person_evidence = evidence_by_id[person_id]
        participation_urls = joined(
            [
                row["source_url"]
                for row in person_evidence
                if row["claim_type"] == "olympiad_participation"
            ]
        )
        identity_urls = joined(
            [
                row["source_url"]
                for row in person_evidence
                if row["claim_type"]
                in {"olympiad_identity_bridge", "identity_candidate", "public_profile"}
                and row["review_status"] in {"accepted", "supporting"}
            ]
        )
        destination_urls = joined(
            [
                row["source_url"]
                for row in person_evidence
                if row["claim_type"] in {"career_outcome", "destination_source_review"}
                and row["supports_final_outcome"] == "True"
            ]
        )
        alma_urls = joined(
            [
                row["evidence_url"]
                for row in affiliations_by_id[person_id]
                if row["selected_as_alma_mater"].casefold() == "true"
            ]
        )
        profile = profiles_by_id.get(person_id, {})
        reconciliation_row = reconciliation_by_id.get(person_id, {})
        current = parsed_current_affiliations(profile) if profile else []
        current_summary = joined(
            {
                " :: ".join(
                    value
                    for value in (
                        clean_text(row.get("organization")),
                        clean_text(row.get("role")),
                        clean_text(row.get("affiliation_type")),
                    )
                    if value
                )
                for row in current
            }
        )
        has_destination = bool(clean_text(audit_person.get("organization")))
        has_country = bool(clean_text(audit_person.get("outcome_country_name")))
        has_alma = bool(clean_text(audit_person.get("alma_mater")))
        row: dict[str, object] = {
                "sample_seed": seed,
                "stratum": selection["stratum"],
                "sample_rank": selection["sample_rank"],
                "sample_hash": selection["sample_hash"],
                "person_id": person_id,
                "name": audit_person["name"],
                "olympiads": audit_person["olympiads"],
                "years": audit_person["years"],
                "outcome_status": audit_person["outcome_status"],
                "organization": audit_person["organization"],
                "role": audit_person["role"],
                "destination_status": audit_person["destination_status"],
                "outcome_country_name": audit_person["outcome_country_name"],
                "outcome_location_label": audit_person["outcome_location_label"],
                "alma_mater": audit_person["alma_mater"],
                "primary_profile_url": audit_person["primary_profile_url"],
                "linkedin_url": audit_person["linkedin_url"],
                "participation_source_urls": participation_urls,
                "identity_source_urls": identity_urls,
                "destination_source_urls": destination_urls,
                "location_source_url": audit_person["outcome_country_source_url"],
                "alma_mater_source_urls": alma_urls,
                "profile_hydration_status": clean_text(profile.get("status"))
                if profile
                else "not_applicable",
                "profile_current_affiliations": current_summary,
                "linkedin_destination_alignment": reconciliation_row.get(
                    "alignment_status", "not_applicable"
                ),
                "participation_check": "pass" if participation_urls else "fail",
                "destination_check": (
                    "pass" if has_destination and destination_urls else "not_available"
                ),
                "country_check": (
                    "pass"
                    if has_country and audit_person["outcome_country_source_url"]
                    else "unknown_retained"
                ),
                "alma_mater_check": (
                    "pass" if has_alma and alma_urls else "not_available"
                ),
                "manual_review_status": "pending",
                "review_depth": "",
                "reviewed_at": "",
                "review_note": (
                    "No current fingerprinted manual review decision matches this "
                    "generated profile record."
                ),
        }
        row["review_fingerprint"] = review_fingerprint(row)
        decision = (review_decisions or {}).get((seed, person_id), {})
        if decision.get("review_fingerprint") == row["review_fingerprint"]:
            row["manual_review_status"] = decision["review_status"]
            row["review_depth"] = decision["review_depth"]
            row["reviewed_at"] = decision["reviewed_at"]
            row["review_note"] = decision["review_note"]
        elif decision:
            row["review_note"] = (
                "The stored manual review decision is stale because the profile "
                "fingerprint changed."
            )
        output.append(row)
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--audit-dir", default="data/audit")
    parser.add_argument("--seed", default=SAMPLE_SEED)
    parser.add_argument("--cutoff-year", type=int, default=ERA_CUTOFF_YEAR)
    parser.add_argument("--sample-per-stratum", type=int, default=SAMPLE_PER_STRATUM)
    parser.add_argument(
        "--review-decisions", type=Path, default=DEFAULT_REVIEW_DECISIONS
    )
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    audit_dir = Path(args.audit_dir)
    researched = read_csv(data_dir / "researched_people.csv")
    audit_people = read_csv(audit_dir / "people.csv")
    evidence = read_csv(audit_dir / "evidence.csv")
    affiliations = read_csv(audit_dir / "affiliations.csv")
    profile_document = read_json(data_dir / "exa_linkedin_profile_audit.json")
    profiles = profile_document["profiles"]
    destination_reviews = read_csv(data_dir / "destination_reviews.csv")
    outcome_decisions = read_csv(data_dir / "exa_outcome_review_decisions.csv")
    findings = read_csv(data_dir / "profile_sanity_review_findings.csv")
    review_decisions = load_review_decisions(args.review_decisions)
    previously_reviewed_ids = {
        person_id
        for (decision_seed, person_id) in review_decisions
        if decision_seed != args.seed
    }

    reconciliation = build_reconciliation(
        researched, profiles, destination_reviews, outcome_decisions, evidence
    )
    selected = select_sample(
        researched,
        args.seed,
        args.cutoff_year,
        args.sample_per_stratum,
        previously_reviewed_ids,
    )
    sample_rows = build_sample_rows(
        selected,
        audit_people,
        evidence,
        affiliations,
        profiles,
        reconciliation,
        args.seed,
        review_decisions,
    )

    write_rows(audit_dir / "profile_sanity_review.csv", sample_rows, SAMPLE_FIELDS)
    write_rows(
        audit_dir / "linkedin_destination_reconciliation.csv",
        reconciliation,
        RECONCILIATION_FIELDS,
    )
    write_rows(
        audit_dir / "profile_sanity_review_findings.csv", findings, FINDING_FIELDS
    )

    manifest = {
        "schema_version": 1,
        "reviewed_at": REVIEWED_AT,
        "sample_seed": args.seed,
        "era_cutoff_year": args.cutoff_year,
        "sample_per_stratum": args.sample_per_stratum,
        "sample_method": (
            "Within each confidence/era stratum, sort by SHA-256 of "
            "seed:stratum:person_id and take the first rows after excluding "
            "people signed in earlier review rounds."
        ),
        "excluded_previously_reviewed": len(previously_reviewed_ids),
        "sample_population": len(
            [
                row
                for row in researched
                if row.get("confidence") in {"probable", "confirmed"}
                and row.get("person_id") not in previously_reviewed_ids
            ]
        ),
        "sample_size": len(sample_rows),
        "sample_strata": dict(Counter(row["stratum"] for row in sample_rows)),
        "sample_review_statuses": dict(
            Counter(row["manual_review_status"] for row in sample_rows)
        ),
        "deep_reviewed_profiles": sum(
            row["review_depth"] == "deep" for row in sample_rows
        ),
        "cumulative_signed_profiles": len(
            {
                person_id
                for (decision_seed, person_id), decision in review_decisions.items()
                if decision_seed == args.seed
                or decision.get("review_status") in {"pass", "pass_after_correction"}
            }
        ),
        "accepted_linkedin_profiles": len(reconciliation),
        "linkedin_alignment_statuses": dict(
            Counter(row["alignment_status"] for row in reconciliation)
        ),
        "unreconciled_linkedin_profiles": sum(
            row["alignment_status"].startswith("unreconciled")
            for row in reconciliation
        ),
        "root_cause_findings": len(findings),
        "unresolved_findings": sum(row.get("status") != "resolved" for row in findings),
    }
    (audit_dir / "profile_sanity_review_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
