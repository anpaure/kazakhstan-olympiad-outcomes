#!/usr/bin/env python3
"""Canonical organization names shared by research and presentation layers."""

from __future__ import annotations

import csv
import re
import unicodedata
from collections import defaultdict
from functools import lru_cache
from pathlib import Path


DEFAULT_ALIASES = Path(__file__).resolve().parents[1] / "data/organization_aliases.csv"
ZERO_WIDTH = dict.fromkeys(map(ord, "\u200b\u200c\u200d\ufeff"), None)


def clean_organization(value: object) -> str:
    text = "" if value is None else str(value)
    text = unicodedata.normalize("NFKC", text).translate(ZERO_WIDTH)
    return re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip(" ,")


def organization_key(value: object) -> str:
    text = clean_organization(value).casefold()
    return re.sub(r"[^\w]+", " ", text, flags=re.UNICODE).strip()


@lru_cache(maxsize=None)
def load_organization_aliases(
    path: str | Path = DEFAULT_ALIASES,
) -> tuple[dict[str, str], dict[str, str], dict[str, tuple[str, ...]]]:
    alias_path = Path(path)
    with alias_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    alias_to_canonical: dict[str, str] = {}
    display_by_canonical: dict[str, str] = {}
    aliases_by_canonical: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        if None in row:
            raise ValueError(f"Organization alias row has extra CSV columns: {row}")
        if not clean_organization(row.get("merge_type")):
            raise ValueError(f"Organization alias row is missing merge_type: {row}")
        alias = clean_organization(row.get("alias"))
        canonical = clean_organization(row.get("canonical_name"))
        display = clean_organization(row.get("display_name")) or canonical
        if not alias or not canonical:
            raise ValueError(f"Organization alias row is incomplete: {row}")
        alias_key = organization_key(alias)
        previous = alias_to_canonical.get(alias_key)
        if previous and previous != canonical:
            raise ValueError(
                f"Conflicting organization alias {alias!r}: {previous!r} vs {canonical!r}"
            )
        alias_to_canonical[alias_key] = canonical
        canonical_key = organization_key(canonical)
        alias_to_canonical.setdefault(canonical_key, canonical)
        previous_display = display_by_canonical.get(canonical_key)
        if previous_display and previous_display != display:
            raise ValueError(
                f"Conflicting display name for {canonical!r}: "
                f"{previous_display!r} vs {display!r}"
            )
        display_by_canonical[canonical_key] = display
        if alias not in aliases_by_canonical[canonical_key]:
            aliases_by_canonical[canonical_key].append(alias)

    return (
        alias_to_canonical,
        display_by_canonical,
        {
            key: tuple(values)
            for key, values in aliases_by_canonical.items()
        },
    )


def canonicalize_organization(value: object) -> str:
    cleaned = clean_organization(value)
    if not cleaned:
        return ""
    aliases, _, _ = load_organization_aliases()
    return aliases.get(organization_key(cleaned), cleaned)


def display_organization(value: object) -> str:
    canonical = canonicalize_organization(value)
    if not canonical:
        return ""
    _, displays, _ = load_organization_aliases()
    return displays.get(organization_key(canonical), canonical)


def organization_aliases_for(value: object) -> tuple[str, ...]:
    canonical = canonicalize_organization(value)
    if not canonical:
        return ()
    _, _, aliases = load_organization_aliases()
    return aliases.get(organization_key(canonical), ())
