#!/usr/bin/env python3
"""Merge reviewed Exa outcome updates into the manual evidence ledger."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path


DEFAULT_BASE = Path("data/verified_evidence.csv")
DEFAULT_UPDATES = Path("data/exa_outcome_integrations.csv")


def read_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError(f"Missing CSV header: {path}")
        return list(reader.fieldnames), list(reader)


def merge_rows(
    base: list[dict[str, str]], updates: list[dict[str, str]]
) -> tuple[list[dict[str, str]], int, int]:
    update_by_id: dict[str, dict[str, str]] = {}
    for row in updates:
        person_id = row.get("person_id", "").strip()
        if not person_id:
            raise ValueError("Exa integration row is missing person_id")
        if person_id in update_by_id:
            raise ValueError(f"Duplicate Exa integration person_id: {person_id}")
        update_by_id[person_id] = row

    merged = []
    updated = 0
    seen = set()
    for row in base:
        person_id = row.get("person_id", "").strip()
        if person_id in update_by_id:
            merged.append(update_by_id[person_id])
            seen.add(person_id)
            updated += 1
        else:
            merged.append(row)

    appended = 0
    for row in updates:
        person_id = row["person_id"].strip()
        if person_id not in seen and not any(
            existing.get("person_id", "").strip() == person_id for existing in base
        ):
            merged.append(row)
            appended += 1
    return merged, updated, appended


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, default=DEFAULT_BASE)
    parser.add_argument("--updates", type=Path, default=DEFAULT_UPDATES)
    args = parser.parse_args()

    fields, base = read_rows(args.base)
    update_fields, updates = read_rows(args.updates)
    if update_fields != fields:
        raise ValueError("Integration CSV fields must match verified_evidence.csv")
    merged, updated, appended = merge_rows(base, updates)

    output_tmp = args.base.with_suffix(args.base.suffix + ".tmp")
    with output_tmp.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(merged)
    output_tmp.replace(args.base)
    print(
        f"Merged {len(updates)} reviewed Exa outcomes: "
        f"{updated} updated, {appended} appended"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
