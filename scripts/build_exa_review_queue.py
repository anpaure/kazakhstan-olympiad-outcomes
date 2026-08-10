#!/usr/bin/env python3
"""Build an auditable manual-review queue from Exa LinkedIn search results."""

from __future__ import annotations

import argparse
import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

try:
    from scripts.organization_names import canonicalize_organization
except ModuleNotFoundError:  # Direct script execution adds scripts/ to sys.path.
    from organization_names import canonicalize_organization


DEFAULT_PEOPLE = Path("data/researched_people.csv")
DEFAULT_EXA_AUDIT = Path("data/exa_linkedin_search_audit.json")
DEFAULT_REJECTIONS = Path("data/rejected_identity_candidates.csv")
DEFAULT_IDENTITY_DECISIONS = Path("data/exa_identity_review_decisions.csv")
DEFAULT_OUTCOME_DECISIONS = Path("data/exa_outcome_review_decisions.csv")
DEFAULT_CSV = Path("data/exa_linkedin_review_queue.csv")
DEFAULT_JSON = Path("data/exa_linkedin_review_queue.json")

OLYMPIAD_PATTERNS = {
    "IMO": re.compile(r"\bIMO\b|International Mathematical Olympiad", re.IGNORECASE),
    "IOI": re.compile(r"\bIOI\b|International Olympiad in Informatics", re.IGNORECASE),
    "IPhO": re.compile(r"\bIPhO\b|International Physics Olympiad", re.IGNORECASE),
    "IBO": re.compile(r"\bIBO\b|International Biology Olympiad", re.IGNORECASE),
    "IChO": re.compile(r"\bIChO\b|International Chemistry Olympiad", re.IGNORECASE),
}
AWARD_PATTERN = re.compile(
    r"\b(gold|silver|bronze|medal|medalist|honou?rable mention|participant)\b",
    re.IGNORECASE,
)
CURRENT_PATTERN = re.compile(
    r"\(Current\)|\bPresent\b|\bIncoming\b|\bcurrently\b|\bcurrent employer\b",
    re.IGNORECASE,
)
CURRENT_AFFILIATION_PATTERN = re.compile(
    r"#{3,4}\s+(?P<role>[^#|]{2,180}?)\s+-\s+"
    r"(?:\[(?P<link_org>[^\]]+)\]\([^)]+\)|(?P<plain_org>[^#|]{2,140}?))"
    r"\s+\(Current\)",
    re.IGNORECASE,
)

CSV_FIELDS = [
    "person_id",
    "name",
    "olympiads",
    "years",
    "current_confidence",
    "current_organization",
    "current_role",
    "current_linkedin_url",
    "candidate_current_organization",
    "candidate_current_role",
    "outcome_alignment",
    "outcome_review_status",
    "outcome_review_reason",
    "outcome_review_evidence_url",
    "review_status",
    "review_tier",
    "priority_score",
    "expected_olympiad_bridge",
    "year_overlap",
    "award_language",
    "current_affiliation_language",
    "identity_review_reason",
    "identity_review_evidence_url",
    "search_request_id",
    "query",
    "search_cost_usd",
    "result_rank",
    "candidate_title",
    "candidate_url",
    "result_kind",
    "highlights",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def clean_text(value: object) -> str:
    text = "" if value is None else str(value)
    return re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()


def evidence_text(value: str) -> str:
    value = re.sub(r"\]\([^)]*\)", "]", value)
    return re.sub(r"https?://\S+", "", value)


def canonical_url(value: str) -> str:
    parsed = urlparse(clean_text(value))
    host = (parsed.hostname or "").casefold()
    if host == "linkedin.com" or host.endswith(".linkedin.com"):
        host = "linkedin.com"
    path_parts = [part for part in parsed.path.split("/") if part]
    if host == "linkedin.com" and len(path_parts) >= 2 and path_parts[0].casefold() == "in":
        path_parts = path_parts[:2]
    path = "/" + "/".join(path_parts) if path_parts else ""
    path = path.casefold()
    return f"{host}{path}" if host else path


def clean_affiliation_fragment(value: str) -> str:
    value = re.sub(r"\s*\.{3}\s*", " ", value)
    return clean_text(value).strip(" -–—:;,.#")


def extract_current_affiliation(text: str) -> tuple[str, str]:
    match = CURRENT_AFFILIATION_PATTERN.search(text)
    if not match:
        return "", ""
    role = clean_affiliation_fragment(match.group("role"))
    organization = clean_affiliation_fragment(
        match.group("link_org") or match.group("plain_org") or ""
    )
    return organization, role


def normalize_organization(value: str) -> str:
    canonical = canonicalize_organization(value)
    normalized = re.sub(r"[^a-z0-9]+", " ", canonical.casefold()).strip()
    normalized = re.sub(
        r"\b(?:inc|llc|ltd|limited|corp|corporation|company|jsc)\b", "", normalized
    )
    normalized = clean_text(normalized)
    return normalized


def classify_outcome_alignment(current: str, candidate: str) -> str:
    if not candidate:
        return "no_current_affiliation_extracted"
    if not current:
        return "missing_published_outcome"
    current_key = normalize_organization(current)
    candidate_key = normalize_organization(candidate)
    if current_key == candidate_key:
        return "organization_match"
    if min(len(current_key), len(candidate_key)) >= 5 and (
        current_key in candidate_key or candidate_key in current_key
    ):
        return "organization_match"
    return "organization_change"


def load_people(path: Path) -> dict[str, dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return {row["person_id"]: row for row in csv.DictReader(handle)}


def load_searches(path: Path) -> list[dict[str, object]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    searches = payload.get("searches", [])
    return [search for search in searches if isinstance(search, dict)]


def load_rejections(path: Path) -> set[tuple[str, str]]:
    if not path.exists():
        return set()
    with path.open(newline="", encoding="utf-8") as handle:
        return {
            (clean_text(row.get("person_id")), canonical_url(row.get("evidence_url", "")))
            for row in csv.DictReader(handle)
        }


def load_outcome_decisions(path: Path) -> dict[tuple[str, str], dict[str, str]]:
    if not path.exists():
        return {}
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    decisions = {}
    for row in rows:
        key = (
            clean_text(row.get("person_id")),
            canonical_url(row.get("candidate_url", "")),
        )
        if key in decisions:
            raise ValueError(f"Duplicate Exa outcome decision: {key[0]} {key[1]}")
        decisions[key] = row
    return decisions


def load_identity_decisions(path: Path) -> dict[tuple[str, str], dict[str, str]]:
    if not path.exists():
        return {}
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    decisions = {}
    for row in rows:
        key = (
            clean_text(row.get("person_id")),
            canonical_url(row.get("candidate_url", "")),
        )
        if key in decisions:
            raise ValueError(f"Duplicate Exa identity decision: {key[0]} {key[1]}")
        decisions[key] = row
    return decisions


def expected_olympiad_bridge(olympiads: str, text: str) -> bool:
    expected = [item.strip() for item in olympiads.split(";") if item.strip()]
    return any(pattern.search(text) for code in expected if (pattern := OLYMPIAD_PATTERNS.get(code)))


def has_year_overlap(years: str, text: str) -> bool:
    expected_years = set(re.findall(r"\b(?:19|20)\d{2}\b", years))
    result_years = set(re.findall(r"\b(?:19|20)\d{2}\b", text))
    return bool(expected_years & result_years)


def classify_candidate(
    person: dict[str, str],
    search: dict[str, object],
    result: dict[str, object],
) -> dict[str, object]:
    highlights = " | ".join(
        clean_text(item) for item in result.get("highlights", []) if clean_text(item)
    )
    visible_evidence = evidence_text(highlights)
    olympiads = clean_text(person.get("olympiads"))
    years = clean_text(person.get("years"))
    bridge = expected_olympiad_bridge(olympiads, visible_evidence)
    year_overlap = has_year_overlap(years, visible_evidence)
    award_language = bool(AWARD_PATTERN.search(visible_evidence))
    current_language = bool(CURRENT_PATTERN.search(visible_evidence))
    candidate_organization, candidate_role = extract_current_affiliation(highlights)
    exact_name = bool(result.get("exact_name_in_title"))
    result_kind = clean_text(result.get("result_kind"))

    if exact_name and bridge and (year_overlap or award_language):
        review_tier = "explicit_bridge"
    elif exact_name and bridge:
        review_tier = "olympiad_context"
    else:
        review_tier = "exact_name_only"

    confidence = clean_text(person.get("confidence"))
    score = 0
    score += 40 if exact_name else 0
    score += 10 if result_kind == "profile" else 0
    score += 30 if bridge else 0
    score += 10 if year_overlap else 0
    score += 5 if award_language else 0
    score += 8 if current_language else 0
    score += {"unmatched": 12, "probable": 7}.get(confidence, 0)
    rank = int(result.get("rank", 99) or 99)
    score += max(0, 6 - rank)

    return {
        "person_id": clean_text(person.get("person_id")),
        "name": clean_text(person.get("name")),
        "olympiads": olympiads,
        "years": years,
        "current_confidence": confidence,
        "current_organization": clean_text(person.get("organization")),
        "current_role": clean_text(person.get("role")),
        "current_linkedin_url": clean_text(person.get("linkedin_url")),
        "candidate_current_organization": candidate_organization,
        "candidate_current_role": candidate_role,
        "outcome_alignment": classify_outcome_alignment(
            clean_text(person.get("organization")), candidate_organization
        ),
        "outcome_review_status": "",
        "outcome_review_reason": "",
        "outcome_review_evidence_url": "",
        "review_status": "unreviewed",
        "review_tier": review_tier,
        "priority_score": score,
        "expected_olympiad_bridge": bridge,
        "year_overlap": year_overlap,
        "award_language": award_language,
        "current_affiliation_language": current_language,
        "identity_review_reason": "",
        "identity_review_evidence_url": "",
        "search_request_id": clean_text(search.get("request_id")),
        "query": clean_text(search.get("query")),
        "search_cost_usd": search.get("cost_usd", 0.0),
        "result_rank": rank,
        "candidate_title": clean_text(result.get("title")),
        "candidate_url": clean_text(result.get("url")),
        "result_kind": result_kind,
        "highlights": highlights,
    }


def build_queue(
    people: dict[str, dict[str, str]],
    searches: list[dict[str, object]],
    rejections: set[tuple[str, str]] | None = None,
    identity_decisions: dict[tuple[str, str], dict[str, str]] | None = None,
    outcome_decisions: dict[tuple[str, str], dict[str, str]] | None = None,
) -> list[dict[str, object]]:
    rejections = rejections or set()
    identity_decisions = identity_decisions or {}
    outcome_decisions = outcome_decisions or {}
    rows = []
    for search in searches:
        person_id = clean_text(search.get("person_id"))
        person = people.get(person_id)
        if not person:
            continue
        for result in search.get("results", []):
            if not isinstance(result, dict):
                continue
            if not result.get("exact_name_in_title") or result.get("result_kind") != "profile":
                continue
            row = classify_candidate(person, search, result)
            candidate_key = canonical_url(str(row["candidate_url"]))
            selected_keys = {
                canonical_url(person.get("linkedin_url", "")),
                canonical_url(person.get("profile_url", "")),
            }
            selected_keys.discard("")
            if (person_id, candidate_key) in rejections:
                row["review_status"] = "rejected"
            elif candidate_key in selected_keys:
                row["review_status"] = "selected"
            else:
                identity_decision = identity_decisions.get((person_id, candidate_key))
                if identity_decision:
                    row["review_status"] = clean_text(identity_decision.get("decision"))
                    row["identity_review_reason"] = clean_text(
                        identity_decision.get("reason")
                    )
                    row["identity_review_evidence_url"] = clean_text(
                        identity_decision.get("review_evidence_url")
                    )
            outcome_decision = outcome_decisions.get((person_id, candidate_key))
            if outcome_decision:
                row["outcome_review_status"] = clean_text(
                    outcome_decision.get("decision")
                )
                row["outcome_review_reason"] = clean_text(
                    outcome_decision.get("reason")
                )
                row["outcome_review_evidence_url"] = clean_text(
                    outcome_decision.get("review_evidence_url")
                )
            elif row["review_tier"] != "explicit_bridge":
                row["outcome_review_status"] = "not_applicable"
            elif row["review_status"] == "rejected":
                row["outcome_review_status"] = "identity_rejected"
            elif row["review_status"] == "supporting":
                row["outcome_review_status"] = "supporting_identity_only"
            elif row["review_status"] == "deferred":
                row["outcome_review_status"] = "identity_deferred"
            elif row["review_status"] != "selected":
                row["outcome_review_status"] = "identity_review_needed"
            elif row["outcome_alignment"] == "organization_match":
                row["outcome_review_status"] = "integrated"
            elif row["outcome_alignment"] == "no_current_affiliation_extracted":
                row["outcome_review_status"] = "selected_no_current_extracted"
            else:
                row["outcome_review_status"] = "outcome_review_needed"
            rows.append(row)

    confidence_order = {"unmatched": 0, "probable": 1, "confirmed": 2}
    tier_order = {"explicit_bridge": 0, "olympiad_context": 1, "exact_name_only": 2}
    status_order = {
        "unreviewed": 0,
        "selected": 1,
        "supporting": 2,
        "deferred": 3,
        "rejected": 4,
    }
    rows.sort(
        key=lambda row: (
            status_order.get(str(row["review_status"]), 3),
            confidence_order.get(str(row["current_confidence"]), 3),
            tier_order.get(str(row["review_tier"]), 3),
            -int(row["priority_score"]),
            str(row["name"]).casefold(),
            int(row["result_rank"]),
        )
    )
    return rows


def write_outputs(
    rows: list[dict[str, object]],
    csv_path: Path,
    json_path: Path,
    people_count: int,
    search_count: int,
) -> dict[str, object]:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    csv_tmp = csv_path.with_suffix(csv_path.suffix + ".tmp")
    with csv_tmp.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    csv_tmp.replace(csv_path)

    explicit_rows = [row for row in rows if row["review_tier"] == "explicit_bridge"]
    explicit_outcome_changes = [
        row for row in explicit_rows if row["outcome_alignment"] == "organization_change"
    ]
    explicit_outcome_review_needed = [
        row
        for row in explicit_rows
        if row["outcome_review_status"] in {"identity_review_needed", "outcome_review_needed"}
    ]
    unreviewed_rows = [row for row in rows if row["review_status"] == "unreviewed"]
    unresolved_unreviewed = [
        row
        for row in unreviewed_rows
        if row["current_confidence"] in {"unmatched", "probable"}
    ]
    summary = {
        "generated_at": utc_now(),
        "canonical_people": people_count,
        "exa_searches": search_count,
        "exact_name_profile_results": len(rows),
        "people_with_exact_name_profile": len({row["person_id"] for row in rows}),
        "explicit_bridge_results": len(explicit_rows),
        "people_with_explicit_bridge": len({row["person_id"] for row in explicit_rows}),
        "explicit_bridge_outcome_change_results": len(explicit_outcome_changes),
        "people_with_explicit_bridge_outcome_change": len(
            {row["person_id"] for row in explicit_outcome_changes}
        ),
        "explicit_bridge_outcome_review_needed_results": len(
            explicit_outcome_review_needed
        ),
        "unmatched_people_with_explicit_bridge": len(
            {
                row["person_id"]
                for row in explicit_rows
                if row["current_confidence"] == "unmatched"
            }
        ),
        "probable_people_with_explicit_bridge": len(
            {
                row["person_id"]
                for row in explicit_rows
                if row["current_confidence"] == "probable"
            }
        ),
        "selected_result_rows": sum(row["review_status"] == "selected" for row in rows),
        "supporting_result_rows": sum(
            row["review_status"] == "supporting" for row in rows
        ),
        "deferred_result_rows": sum(row["review_status"] == "deferred" for row in rows),
        "rejected_result_rows": sum(row["review_status"] == "rejected" for row in rows),
        "unreviewed_result_rows": len(unreviewed_rows),
        "unresolved_people_with_unreviewed_results": len(
            {row["person_id"] for row in unresolved_unreviewed}
        ),
        "rows": rows,
    }
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_tmp = json_path.with_suffix(json_path.suffix + ".tmp")
    json_tmp.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    json_tmp.replace(json_path)
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--people", type=Path, default=DEFAULT_PEOPLE)
    parser.add_argument("--exa-audit", type=Path, default=DEFAULT_EXA_AUDIT)
    parser.add_argument("--rejections", type=Path, default=DEFAULT_REJECTIONS)
    parser.add_argument(
        "--identity-decisions", type=Path, default=DEFAULT_IDENTITY_DECISIONS
    )
    parser.add_argument(
        "--outcome-decisions", type=Path, default=DEFAULT_OUTCOME_DECISIONS
    )
    parser.add_argument("--output-csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_JSON)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    people = load_people(args.people)
    searches = load_searches(args.exa_audit)
    rejections = load_rejections(args.rejections)
    identity_decisions = load_identity_decisions(args.identity_decisions)
    outcome_decisions = load_outcome_decisions(args.outcome_decisions)
    rows = build_queue(
        people, searches, rejections, identity_decisions, outcome_decisions
    )
    summary = write_outputs(rows, args.output_csv, args.output_json, len(people), len(searches))
    print(json.dumps({key: value for key, value in summary.items() if key != "rows"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
