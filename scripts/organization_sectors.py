#!/usr/bin/env python3
"""Load reviewed organization types and sectors for destination reporting."""

from __future__ import annotations

import csv
from functools import lru_cache
from pathlib import Path

try:
    from scripts.organization_names import canonicalize_organization, clean_organization
except ModuleNotFoundError:  # Direct script execution adds scripts/ to sys.path.
    from organization_names import canonicalize_organization, clean_organization


DEFAULT_SECTORS = Path(__file__).resolve().parents[1] / "data/organization_sectors.csv"
ORGANIZATION_TYPES = {"company", "government", "nonprofit", "independent"}
SECTORS = {
    "Consulting & Professional Services",
    "Consumer & Media",
    "Education & Research",
    "Energy & Natural Resources",
    "Environment & Nonprofit",
    "Finance & Insurance",
    "Government & Public Sector",
    "Healthcare & Life Sciences",
    "Independent & Other",
    "Industrial & Manufacturing",
    "Technology & Software",
    "Transportation & Infrastructure",
}


@lru_cache(maxsize=None)
def load_organization_sectors(
    path: Path = DEFAULT_SECTORS,
) -> dict[str, dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    metadata: dict[str, dict[str, str]] = {}
    for index, row in enumerate(rows, start=2):
        canonical_name = canonicalize_organization(row.get("canonical_name"))
        organization_type = clean_organization(row.get("organization_type")).casefold()
        sector = clean_organization(row.get("sector"))
        rationale = clean_organization(row.get("rationale"))
        if not canonical_name or not organization_type or not sector or not rationale:
            raise ValueError(f"Incomplete organization sector row {index}")
        if clean_organization(row.get("canonical_name")) != canonical_name:
            raise ValueError(
                f"Organization sector row {index} is not canonical: "
                f"{row.get('canonical_name')!r}"
            )
        if organization_type not in ORGANIZATION_TYPES:
            raise ValueError(
                f"Unsupported organization type at row {index}: {organization_type!r}"
            )
        if sector not in SECTORS:
            raise ValueError(f"Unsupported sector at row {index}: {sector!r}")
        key = canonical_name.casefold()
        if key in metadata:
            raise ValueError(f"Duplicate organization sector: {canonical_name}")
        metadata[key] = {
            "canonical_name": canonical_name,
            "organization_type": organization_type,
            "sector": sector,
            "rationale": rationale,
        }
    return metadata


def organization_metadata(
    organization: object,
    organization_category: object = "",
) -> dict[str, str]:
    canonical_name = canonicalize_organization(organization)
    if not canonical_name:
        return {
            "canonical_name": "",
            "organization_type": "",
            "sector": "",
            "rationale": "",
        }
    category = clean_organization(organization_category).casefold()
    if category in {"academia", "education"}:
        return {
            "canonical_name": canonical_name,
            "organization_type": "education",
            "sector": "Education & Research",
            "rationale": "Destination is classified as an educational or research institution.",
        }
    return load_organization_sectors().get(
        canonical_name.casefold(),
        {
            "canonical_name": canonical_name,
            "organization_type": "",
            "sector": "",
            "rationale": "",
        },
    )
