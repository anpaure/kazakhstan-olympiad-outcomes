#!/usr/bin/env python3
"""Merge reviewed Exa namesake rejections into the identity rejection ledger."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path


DEFAULT_BASE = Path("data/rejected_identity_candidates.csv")
DEFAULT_REJECTIONS = Path("data/exa_identity_rejections.csv")


def normalized_url(value: str) -> str:
    return value.strip().rstrip("/").casefold()


def merge_rows(
    base: list[dict[str, str]], additions: list[dict[str, str]]
) -> tuple[list[dict[str, str]], int]:
    keys = {
        (row.get("person_id", "").strip(), normalized_url(row.get("evidence_url", "")))
        for row in base
    }
    merged = list(base)
    added = 0
    for row in additions:
        key = (
            row.get("person_id", "").strip(),
            normalized_url(row.get("evidence_url", "")),
        )
        if not all(key):
            raise ValueError("Exa rejection rows require person_id and evidence_url")
        if key in keys:
            continue
        merged.append(row)
        keys.add(key)
        added += 1
    return merged, added


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, default=DEFAULT_BASE)
    parser.add_argument("--additions", type=Path, default=DEFAULT_REJECTIONS)
    args = parser.parse_args()

    with args.base.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fields = list(reader.fieldnames or [])
        base = list(reader)
    with args.additions.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        addition_fields = list(reader.fieldnames or [])
        additions = list(reader)
    if fields != addition_fields:
        raise ValueError("Exa rejection fields must match the rejection ledger")

    merged, added = merge_rows(base, additions)
    output_tmp = args.base.with_suffix(args.base.suffix + ".tmp")
    with output_tmp.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(merged)
    output_tmp.replace(args.base)
    print(f"Merged {added} new Exa namesake rejections from {len(additions)} reviews")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
