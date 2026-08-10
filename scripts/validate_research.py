#!/usr/bin/env python3
"""Validate the canonical registry and assembled research dataset."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path


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


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def split_values(value: str) -> set[str]:
    return {item.strip() for item in value.split(";") if item.strip()}


def validate(data_dir: Path) -> tuple[list[str], dict[str, int]]:
    errors: list[str] = []
    required = {
        "participants": data_dir / "kazakhstan_participants.csv",
        "people": data_dir / "people.csv",
        "researched": data_dir / "researched_people.csv",
        "verified": data_dir / "verified_evidence.csv",
        "rejections": data_dir / "rejected_identity_candidates.csv",
        "audit_people": data_dir / "audit" / "people.csv",
        "audit_participations": data_dir / "audit" / "participations.csv",
        "audit_evidence": data_dir / "audit" / "evidence.csv",
        "audit_sources": data_dir / "audit" / "sources.csv",
        "audit_rejections": data_dir / "audit" / "rejections.csv",
        "audit_manifest": data_dir / "audit" / "manifest.json",
    }
    missing = [str(path) for path in required.values() if not path.exists()]
    if missing:
        return [f"missing required file: {path}" for path in missing], {}

    participants = read_csv(required["participants"])
    people = read_csv(required["people"])
    researched = read_csv(required["researched"])
    verified = read_csv(required["verified"])
    rejections = read_csv(required["rejections"])
    audit_people = read_csv(required["audit_people"])
    audit_participations = read_csv(required["audit_participations"])
    audit_evidence = read_csv(required["audit_evidence"])
    audit_sources = read_csv(required["audit_sources"])
    audit_rejections = read_csv(required["audit_rejections"])
    audit_manifest = json.loads(required["audit_manifest"].read_text(encoding="utf-8"))

    def duplicate_ids(rows: list[dict[str, str]], label: str) -> None:
        counts = Counter(row.get("person_id", "") for row in rows)
        duplicates = sorted(key for key, count in counts.items() if key and count > 1)
        if duplicates:
            errors.append(f"{label} contains duplicate person IDs: {', '.join(duplicates[:8])}")

    duplicate_ids(people, "people.csv")
    duplicate_ids(researched, "researched_people.csv")
    duplicate_ids(verified, "verified_evidence.csv")

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

    people_by_id = {row["person_id"]: row for row in people}
    researched_by_id = {row["person_id"]: row for row in researched}
    verified_by_id = {row["person_id"]: row for row in verified}
    audit_people_by_id = {row["person_id"]: row for row in audit_people}
    audit_evidence_by_id = {row["evidence_id"]: row for row in audit_evidence}
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

    if set(audit_people_by_id) != set(people_by_id):
        errors.append("audit people do not match the canonical people registry")
    if len(audit_participations) != len(participants):
        errors.append(
            f"audit participations contain {len(audit_participations)} rows, "
            f"expected {len(participants)}"
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
            outcome_evidence = [
                row
                for row in person_evidence
                if row.get("supports_final_outcome") == "True"
                and row.get("review_status") in {"accepted", "supporting"}
            ]
            if not outcome_evidence:
                errors.append(f"{person_id} has no accepted source-linked outcome evidence")
            audit_row = audit_people_by_id.get(person_id, {})
            if audit_row.get("traceability_status") != "complete":
                errors.append(f"{person_id} is high confidence without complete audit traceability")

    manifest_counts = audit_manifest.get("counts", {})
    expected_manifest_counts = {
        "people": len(audit_people),
        "participations": len(audit_participations),
        "evidence_rows": len(audit_evidence),
        "sources": len(audit_sources),
        "rejections": len(audit_rejections),
        "complete_outcomes": sum(
            row.get("traceability_status") == "complete" for row in audit_people
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
        for field in ("organization", "role"):
            expected = verified_row.get(field, "").strip()
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
        "rejected_identity_candidates": len(rejections),
        "audit_evidence_rows": len(audit_evidence),
        "audit_sources": len(audit_sources),
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
