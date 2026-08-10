#!/usr/bin/env python3
"""Load reviewed corrections that reconcile final outcomes with cited sources."""

from __future__ import annotations

import csv
from functools import lru_cache
from pathlib import Path

try:
    from scripts.organization_names import canonicalize_organization
except ModuleNotFoundError:  # Direct script execution adds scripts/ to sys.path.
    from organization_names import canonicalize_organization


DEFAULT_DESTINATION_REVIEWS = (
    Path(__file__).resolve().parents[1] / "data/destination_reviews.csv"
)
DESTINATION_REVIEW_FIELDS = [
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


def clean_text(value: object) -> str:
    return " ".join(str(value or "").replace("\xa0", " ").split())


@lru_cache(maxsize=None)
def load_destination_reviews(
    path: str | Path = DEFAULT_DESTINATION_REVIEWS,
) -> list[dict[str, str]]:
    review_path = Path(path)
    with review_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != DESTINATION_REVIEW_FIELDS:
            raise ValueError(
                f"Unexpected destination review fields: {reader.fieldnames!r}"
            )
        rows = list(reader)

    seen_people: set[str] = set()
    output: list[dict[str, str]] = []
    for index, raw in enumerate(rows, start=2):
        row = {field: clean_text(raw.get(field)) for field in DESTINATION_REVIEW_FIELDS}
        person_id = row["person_id"]
        if not person_id or person_id in seen_people:
            raise ValueError(
                f"Missing or duplicate person ID in destination review row {index}"
            )
        seen_people.add(person_id)
        row["organization"] = canonicalize_organization(row["organization"])
        if not row["name"] or not row["organization"] or not row["affiliation_type"]:
            raise ValueError(f"Incomplete destination review row {index}")
        if row["affiliation_type"] not in {"employment", "education"}:
            raise ValueError(
                f"Invalid affiliation type in destination review row {index}: "
                f"{row['affiliation_type']!r}"
            )
        if not row["evidence_url"].startswith(("http://", "https://")):
            raise ValueError(f"Missing source URL in destination review row {index}")
        if not row["reviewed_at"] or not row["review_reason"]:
            raise ValueError(f"Incomplete review metadata in row {index}")
        output.append(row)
    return output


def destination_reviews_by_person(
    path: str | Path = DEFAULT_DESTINATION_REVIEWS,
) -> dict[str, dict[str, str]]:
    return {row["person_id"]: row for row in load_destination_reviews(path)}
