#!/usr/bin/env python3
"""Inject the compact research dataset into the inline visualization fragment."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


ORGANIZATION_DISPLAY_ALIASES = {
    "Ulsan National Institute of Science and Technology": "UNIST",
}


def compact_person(row: dict[str, object]) -> dict[str, object]:
    organization = str(row["organization"])
    return {
        "id": row["person_id"],
        "name": row["name"],
        "olympiads": [value for value in str(row["olympiads"]).split(";") if value],
        "firstYear": int(row["first_year"]),
        "confidence": row["confidence"],
        "organization": ORGANIZATION_DISPLAY_ALIASES.get(organization, organization),
        "role": row["role"],
        "organizationCategory": row["organization_category"],
        "roleCategory": row["role_category"],
        "profile": row["profile_url"],
        "linkedin": row["linkedin_url"],
        "scope": row["research_scope"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", default="data/researched_people.json")
    parser.add_argument(
        "--template",
        default="visualization/olympiad-outcomes-template.html",
    )
    parser.add_argument(
        "--out",
        default="docs/index.html",
    )
    args = parser.parse_args()

    rows = json.loads(Path(args.data).read_text(encoding="utf-8"))
    compact = [compact_person(row) for row in rows]
    template = Path(args.template).read_text(encoding="utf-8")
    marker = "/*__DATA__*/[]"
    if marker not in template:
        raise RuntimeError(f"Visualization data marker not found in {args.template}")
    payload = json.dumps(compact, ensure_ascii=False, separators=(",", ":"))
    output = template.replace(marker, payload, 1)
    output_path = Path(args.out)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(output, encoding="utf-8")
    print(f"Wrote {len(compact)} people to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
