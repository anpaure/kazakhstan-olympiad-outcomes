#!/usr/bin/env python3
"""Build a canonical people registry from olympiad participant rows."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
from pathlib import Path


MANUAL_ALIAS_GROUPS = [
    ("Saken Sherhandy", "Saken Sherhanov", "Saken Serhanov"),
    ("Nourbol Silliedev", "Nurbol Sihimbayev"),
    ("Akram Mahmudov", "Ekrem Mahmudov"),
    ("Bakhytjan Bakhaotdinov", "Bakitkan Bahautdinov"),
]

CANONICAL_NAME_OVERRIDES = {
    "kemel nurdaulet": "Nurdaulet Kemel",
}

DEFAULT_MANUAL_MERGES = Path("data/person_merges.csv")


@dataclass(frozen=True)
class Person:
    person_id: str
    canonical_name: str
    aliases: str
    olympiads: str
    years: str
    first_year: int
    last_year: int
    estimated_birth_year_min: int
    estimated_birth_year_max: int
    awards: str
    participant_rows: int
    research_scope: str
    source_urls: str


class UnionFind:
    def __init__(self, values: list[str]):
        self.parent = {value: value for value in values}

    def find(self, value: str) -> str:
        parent = self.parent[value]
        if parent != value:
            self.parent[value] = self.find(parent)
        return self.parent[value]

    def union(self, left: str, right: str) -> None:
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root != right_root:
            self.parent[right_root] = left_root


def clean_text(value: object) -> str:
    text = "" if value is None else str(value)
    return re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()


def normalize_name(value: str) -> str:
    value = unicodedata.normalize("NFKD", value.casefold())
    value = "".join(
        character if character.isalnum() else " "
        for character in value
        if not unicodedata.combining(character)
    )
    return re.sub(r"\s+", " ", value).strip()


def token_key(value: str) -> str:
    return " ".join(sorted(normalize_name(value).split()))


def load_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def load_manual_merges(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    merges: list[dict[str, object]] = []
    claimed_aliases: dict[str, str] = {}
    for index, row in enumerate(load_rows(path), start=2):
        person_id = clean_text(row.get("canonical_person_id"))
        canonical_name = clean_text(row.get("canonical_name"))
        aliases = tuple(
            dict.fromkeys(
                clean_text(alias)
                for alias in clean_text(row.get("aliases")).split(";")
                if clean_text(alias)
            )
        )
        reason = clean_text(row.get("reason"))
        evidence_url = clean_text(row.get("evidence_url"))
        if not person_id or not canonical_name or len(aliases) < 2 or not reason:
            raise ValueError(f"Incomplete manual person merge at row {index}")
        if canonical_name not in aliases:
            raise ValueError(
                f"Canonical name is not an alias in manual person merge row {index}"
            )
        if not evidence_url.startswith(("http://", "https://")):
            raise ValueError(f"Manual person merge row {index} has no direct source URL")
        for alias in aliases:
            key = normalize_name(alias)
            prior = claimed_aliases.get(key)
            if prior and prior != person_id:
                raise ValueError(f"Manual person alias belongs to multiple people: {alias}")
            claimed_aliases[key] = person_id
        merges.append(
            {
                "canonical_person_id": person_id,
                "canonical_name": canonical_name,
                "aliases": aliases,
                "reason": reason,
                "evidence_url": evidence_url,
            }
        )
    return merges


def load_existing_person_ids(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    ids_by_name: dict[str, str] = {}
    for row in load_rows(path):
        person_id = clean_text(row.get("person_id"))
        if not person_id:
            continue
        names = [clean_text(row.get("canonical_name") or row.get("name"))]
        names.extend(clean_text(row.get("aliases")).split(";"))
        for name in names:
            key = token_key(name)
            if key:
                ids_by_name.setdefault(key, person_id)
    return ids_by_name


def should_merge(
    left: str,
    right: str,
    metadata: dict[str, dict[str, object]],
) -> bool:
    left_meta = metadata[left]
    right_meta = metadata[right]
    shared_olympiads = left_meta["olympiads"] & right_meta["olympiads"]
    if not shared_olympiads:
        return False

    left_years = left_meta["years"]
    right_years = right_meta["years"]
    year_gap = min(abs(left_year - right_year) for left_year in left_years for right_year in right_years)
    if year_gap > 2:
        return False

    left_normalized = normalize_name(left)
    right_normalized = normalize_name(right)
    if left_normalized == right_normalized:
        return True

    left_tokens = token_key(left)
    right_tokens = token_key(right)
    if left_tokens == right_tokens:
        return True

    left_token_set = set(left_tokens.split())
    right_token_set = set(right_tokens.split())
    if min(len(left_token_set), len(right_token_set)) >= 2 and (
        left_token_set <= right_token_set or right_token_set <= left_token_set
    ):
        return True

    return SequenceMatcher(None, left_tokens, right_tokens).ratio() >= 0.84


def canonical_alias(aliases: list[str], row_counts: Counter[str], latest_year: dict[str, int]) -> str:
    def rank(name: str) -> tuple[int, int, int, str]:
        all_title_case = int(all(token[:1].isupper() and token[1:].islower() for token in name.split()))
        return row_counts[name], all_title_case, latest_year[name], name.casefold()

    candidate = max(aliases, key=rank)
    return CANONICAL_NAME_OVERRIDES.get(normalize_name(candidate), candidate)


def person_id_for(aliases: list[str]) -> str:
    identity = "|".join(sorted(normalize_name(alias) for alias in aliases))
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:12]
    return f"kaz-{digest}"


def build_registry(
    rows: list[dict[str, str]],
    existing_person_ids: dict[str, str] | None = None,
    manual_merges: list[dict[str, object]] | None = None,
) -> tuple[list[Person], list[dict[str, object]]]:
    existing_person_ids = existing_person_ids or {}
    manual_merges = manual_merges or []
    metadata: dict[str, dict[str, object]] = defaultdict(
        lambda: {"olympiads": set(), "years": set(), "rows": []}
    )
    row_counts: Counter[str] = Counter()
    latest_year: dict[str, int] = {}

    for row in rows:
        name = clean_text(row.get("name"))
        if not name:
            continue
        year = int(row["year"])
        metadata[name]["olympiads"].add(clean_text(row.get("olympiad")))
        metadata[name]["years"].add(year)
        metadata[name]["rows"].append(row)
        row_counts[name] += 1
        latest_year[name] = max(latest_year.get(name, year), year)

    names = sorted(metadata, key=str.casefold)
    union_find = UnionFind(names)
    merge_evidence: list[dict[str, object]] = []
    for index, left in enumerate(names):
        for right in names[index + 1 :]:
            if not should_merge(left, right, metadata):
                continue
            ratio = SequenceMatcher(None, token_key(left), token_key(right)).ratio()
            shared = sorted(metadata[left]["olympiads"] & metadata[right]["olympiads"])
            union_find.union(left, right)
            merge_evidence.append(
                {
                    "left": left,
                    "right": right,
                    "token_similarity": round(ratio, 3),
                    "shared_olympiads": shared,
                    "left_years": sorted(metadata[left]["years"]),
                    "right_years": sorted(metadata[right]["years"]),
                }
            )

    for alias_group in MANUAL_ALIAS_GROUPS:
        present = [alias for alias in alias_group if alias in metadata]
        for left, right in zip(present, present[1:]):
            if union_find.find(left) == union_find.find(right):
                continue
            union_find.union(left, right)
            merge_evidence.append(
                {
                    "left": left,
                    "right": right,
                    "token_similarity": round(
                        SequenceMatcher(None, token_key(left), token_key(right)).ratio(),
                        3,
                    ),
                    "shared_olympiads": sorted(
                        metadata[left]["olympiads"] & metadata[right]["olympiads"]
                    ),
                    "left_years": sorted(metadata[left]["years"]),
                    "right_years": sorted(metadata[right]["years"]),
                    "reason": "manual_transliteration",
                }
            )

    for merge in manual_merges:
        present = [alias for alias in merge["aliases"] if alias in metadata]
        if len(present) == 1:
            recorded = present[0]
            merge_evidence.append(
                {
                    "left": recorded,
                    "right": merge["canonical_name"],
                    "token_similarity": round(
                        SequenceMatcher(
                            None,
                            token_key(recorded),
                            token_key(str(merge["canonical_name"])),
                        ).ratio(),
                        3,
                    ),
                    "shared_olympiads": sorted(metadata[recorded]["olympiads"]),
                    "left_years": sorted(metadata[recorded]["years"]),
                    "right_years": [],
                    "reason": "reviewed_alias_augmentation",
                    "review_reason": merge["reason"],
                    "evidence_url": merge["evidence_url"],
                    "canonical_person_id": merge["canonical_person_id"],
                }
            )
        for left, right in zip(present, present[1:]):
            if union_find.find(left) == union_find.find(right):
                continue
            union_find.union(left, right)
            merge_evidence.append(
                {
                    "left": left,
                    "right": right,
                    "token_similarity": round(
                        SequenceMatcher(None, token_key(left), token_key(right)).ratio(),
                        3,
                    ),
                    "shared_olympiads": sorted(
                        metadata[left]["olympiads"] & metadata[right]["olympiads"]
                    ),
                    "left_years": sorted(metadata[left]["years"]),
                    "right_years": sorted(metadata[right]["years"]),
                    "reason": "reviewed_cross_olympiad_merge",
                    "review_reason": merge["reason"],
                    "evidence_url": merge["evidence_url"],
                    "canonical_person_id": merge["canonical_person_id"],
                }
            )

    groups: dict[str, list[str]] = defaultdict(list)
    for name in names:
        groups[union_find.find(name)].append(name)

    people: list[Person] = []
    for aliases in groups.values():
        aliases = sorted(aliases, key=str.casefold)
        reviewed_merges = [
            merge
            for merge in manual_merges
            if set(merge["aliases"]) & set(aliases)
        ]
        if len(reviewed_merges) > 1:
            raise ValueError(f"Multiple reviewed merges match aliases: {aliases}")
        prior_ids = {
            existing_person_ids[key]
            for alias in aliases
            if (key := token_key(alias)) in existing_person_ids
        }
        reviewed_merge = reviewed_merges[0] if reviewed_merges else None
        person_id = (
            str(reviewed_merge["canonical_person_id"])
            if reviewed_merge
            else next(iter(prior_ids))
            if len(prior_ids) == 1
            else person_id_for(aliases)
        )
        group_rows = [row for alias in aliases for row in metadata[alias]["rows"]]
        years = sorted({int(row["year"]) for row in group_rows})
        olympiads = sorted({clean_text(row.get("olympiad")) for row in group_rows if row.get("olympiad")})
        awards = sorted({clean_text(row.get("award")) for row in group_rows if clean_text(row.get("award"))})
        source_urls = sorted(
            {clean_text(row.get("source_url")) for row in group_rows if clean_text(row.get("source_url"))}
        )
        first_year = min(years)
        last_year = max(years)
        if first_year <= 2018:
            research_scope = "career"
        elif first_year <= 2022:
            research_scope = "early_career_or_university"
        else:
            research_scope = "recent_competitor"

        published_aliases = sorted(
            set(aliases)
            | (set(reviewed_merge["aliases"]) if reviewed_merge else set()),
            key=str.casefold,
        )
        people.append(
            Person(
                person_id=person_id,
                canonical_name=(
                    str(reviewed_merge["canonical_name"])
                    if reviewed_merge
                    else canonical_alias(aliases, row_counts, latest_year)
                ),
                aliases=";".join(published_aliases),
                olympiads=";".join(olympiads),
                years=";".join(str(year) for year in years),
                first_year=first_year,
                last_year=last_year,
                estimated_birth_year_min=first_year - 19,
                estimated_birth_year_max=first_year - 15,
                awards=";".join(awards),
                participant_rows=len(group_rows),
                research_scope=research_scope,
                source_urls=";".join(source_urls),
            )
        )

    people.sort(key=lambda person: (person.first_year, person.canonical_name.casefold()))
    return people, merge_evidence


def write_outputs(
    people: list[Person],
    merge_evidence: list[dict[str, object]],
    csv_path: Path,
    json_path: Path,
    merge_path: Path,
) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(Person.__dataclass_fields__)
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for person in people:
            writer.writerow(asdict(person))
    json_path.write_text(
        json.dumps([asdict(person) for person in people], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    merge_path.write_text(json.dumps(merge_evidence, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-csv", default="data/kazakhstan_participants.csv")
    parser.add_argument("--out-csv", default="data/people.csv")
    parser.add_argument("--out-json", default="data/people.json")
    parser.add_argument("--merge-audit", default="data/people_merge_audit.json")
    parser.add_argument("--manual-merges", default=str(DEFAULT_MANUAL_MERGES))
    parser.add_argument(
        "--existing-people-csv",
        default="data/researched_people.csv",
        help="Previous people output used only to preserve stable person IDs.",
    )
    args = parser.parse_args()

    rows = load_rows(Path(args.input_csv))
    existing_person_ids = load_existing_person_ids(Path(args.existing_people_csv))
    people, merge_evidence = build_registry(
        rows,
        existing_person_ids,
        load_manual_merges(Path(args.manual_merges)),
    )
    write_outputs(
        people,
        merge_evidence,
        Path(args.out_csv),
        Path(args.out_json),
        Path(args.merge_audit),
    )
    scope_counts = Counter(person.research_scope for person in people)
    print(
        json.dumps(
            {
                "participant_rows": len(rows),
                "canonical_people": len(people),
                "merged_alias_pairs": len(merge_evidence),
                "research_scopes": dict(sorted(scope_counts.items())),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
