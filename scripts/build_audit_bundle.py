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
) -> list[dict[str, object]]:
    final_by_person = {row["person_id"]: row for row in researched}
    verified_by_person = {row["person_id"]: row for row in verified}
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
        add_evidence(
            rows,
            seen,
            person_id=person_id,
            person_name=name,
            claim_type="olympiad_identity_bridge",
            claim_summary=f"Reviewed Olympiad identity evidence for {name}",
            source_url=row.get("olympiad_evidence_url", ""),
            provenance="manual_review",
            source_adapter="manual",
            review_status="accepted",
            confidence=confidence,
            supports_final_outcome=True,
            evidence_text=basis,
            review_note=basis,
        )
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
            review_status="accepted",
            confidence=confidence,
            supports_final_outcome=True,
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
            supports_final_outcome=True,
            review_note=basis,
        )

    for row in identities:
        person_id = row["person_id"]
        final = final_by_person[person_id]
        source_url = clean_text(row.get("evidence_url")) or clean_text(row.get("profile_url"))
        rejection = rejection_by_key.get((person_id, normalize_url(source_url)))
        selected = (
            person_id not in verified_by_person
            and normalize_url(row.get("profile_url", "")) == normalize_url(final.get("profile_url", ""))
            and bool(normalize_url(final.get("profile_url", "")))
        )
        if rejection:
            status = "rejected"
        elif person_id in verified_by_person:
            status = "superseded"
        elif selected:
            status = "accepted"
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
            supports_final_outcome=selected,
            organization=row.get("organization", ""),
            role=row.get("role", ""),
            evidence_text=row.get("evidence_text", ""),
            review_note=(
                rejection.get("reason", "") if rejection else row.get("score_reasons", "")
            ),
        )

    for row in affiliations:
        person_id = row["person_id"]
        final = final_by_person[person_id]
        source_url = clean_text(row.get("evidence_url"))
        rejection = rejection_by_key.get((person_id, normalize_url(source_url)))
        selected = (
            person_id not in verified_by_person
            and clean_text(row.get("organization")) == clean_text(final.get("organization"))
            and clean_text(row.get("role")) == clean_text(final.get("role"))
            and clean_text(row.get("affiliation_type")) == clean_text(final.get("affiliation_type"))
            and final.get("confidence") != "unmatched"
        )
        if rejection:
            status = "rejected"
        elif person_id in verified_by_person:
            status = "superseded"
        elif selected:
            status = "accepted"
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
            supports_final_outcome=selected,
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
) -> list[dict[str, object]]:
    verified_ids = {row["person_id"] for row in verified}
    evidence_by_person: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in evidence:
        evidence_by_person[str(row["person_id"])].append(row)

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
        if row["confidence"] in {"probable", "confirmed"}:
            traceability = "complete" if participation_count and outcome_count else "incomplete"
        elif candidate_count:
            traceability = "review_required"
        else:
            traceability = "participation_only"
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


def build_bundle(
    participants: list[dict[str, str]],
    people: list[dict[str, str]],
    researched: list[dict[str, str]],
    identities: list[dict[str, str]],
    affiliations: list[dict[str, str]],
    verified: list[dict[str, str]],
    rejections: list[dict[str, str]],
) -> dict[str, object]:
    participations = build_participations(participants, people)
    evidence = build_evidence(
        participations, researched, identities, affiliations, verified, rejections
    )
    audit_people = build_audit_people(researched, verified, evidence)
    sources = build_sources(evidence)
    audit_rejections = build_audit_rejections(rejections, researched)
    manifest = {
        "schema_version": 1,
        "primary_key": {"people": "person_id", "evidence": "evidence_id", "sources": "source_id"},
        "joins": [
            "people.person_id = evidence.person_id",
            "evidence.source_id = sources.source_id",
            "participations.evidence_id = evidence.evidence_id",
        ],
        "review_statuses": ["accepted", "supporting", "candidate", "superseded", "rejected"],
        "counts": {
            "people": len(audit_people),
            "participations": len(participations),
            "evidence_rows": len(evidence),
            "sources": len(sources),
            "rejections": len(audit_rejections),
            "complete_outcomes": sum(
                row["traceability_status"] == "complete" for row in audit_people
            ),
        },
    }
    return {
        "people": audit_people,
        "participations": participations,
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
    )
    output_dir = Path(args.out_dir)
    write_rows(output_dir / "people.csv", bundle["people"], AUDIT_PEOPLE_FIELDS)
    write_rows(
        output_dir / "participations.csv", bundle["participations"], PARTICIPATION_FIELDS
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
