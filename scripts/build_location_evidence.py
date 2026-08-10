#!/usr/bin/env python3
"""Build sourced current-country evidence for accepted alumni outcomes."""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path

try:
    from scripts.build_exa_review_queue import canonical_url
except ModuleNotFoundError:  # Direct script execution adds scripts/ to sys.path.
    from build_exa_review_queue import canonical_url


DEFAULT_PEOPLE = Path("data/researched_people.json")
DEFAULT_EXA_AUDIT = Path("data/exa_linkedin_search_audit.json")
DEFAULT_OVERRIDES = Path("data/location_overrides.csv")
DEFAULT_CSV = Path("data/person_locations.csv")
DEFAULT_JSON = Path("data/person_locations.json")

COUNTRY_NAMES = {
    "AT": "Austria",
    "AU": "Australia",
    "BE": "Belgium",
    "CA": "Canada",
    "CH": "Switzerland",
    "CN": "China",
    "CZ": "Czechia",
    "DE": "Germany",
    "DK": "Denmark",
    "ES": "Spain",
    "FI": "Finland",
    "FR": "France",
    "GB": "United Kingdom",
    "HK": "Hong Kong",
    "IE": "Ireland",
    "IL": "Israel",
    "IN": "India",
    "IT": "Italy",
    "JP": "Japan",
    "KR": "South Korea",
    "KZ": "Kazakhstan",
    "LU": "Luxembourg",
    "NL": "Netherlands",
    "NO": "Norway",
    "PL": "Poland",
    "PT": "Portugal",
    "QA": "Qatar",
    "RU": "Russia",
    "SA": "Saudi Arabia",
    "SE": "Sweden",
    "SG": "Singapore",
    "TR": "Türkiye",
    "AE": "United Arab Emirates",
    "US": "United States",
}

COUNTRY_ALIASES = {
    "australia": "AU",
    "austria": "AT",
    "belgium": "BE",
    "canada": "CA",
    "china": "CN",
    "czech republic": "CZ",
    "czechia": "CZ",
    "denmark": "DK",
    "finland": "FI",
    "france": "FR",
    "germany": "DE",
    "hong kong": "HK",
    "india": "IN",
    "ireland": "IE",
    "israel": "IL",
    "italy": "IT",
    "japan": "JP",
    "kazakhstan": "KZ",
    "luxembourg": "LU",
    "netherlands": "NL",
    "norway": "NO",
    "poland": "PL",
    "portugal": "PT",
    "qatar": "QA",
    "russia": "RU",
    "russian federation": "RU",
    "saudi arabia": "SA",
    "singapore": "SG",
    "south korea": "KR",
    "spain": "ES",
    "sweden": "SE",
    "switzerland": "CH",
    "turkey": "TR",
    "türkiye": "TR",
    "united arab emirates": "AE",
    "united kingdom": "GB",
    "united states": "US",
    "united states of america": "US",
    "казахстан": "KZ",
    "россия": "RU",
    "саудовская аравия": "SA",
    "соединенные штаты": "US",
    "южная корея": "KR",
}

CITY_COUNTRIES = {
    "abu dhabi": "AE",
    "al khobar": "SA",
    "almaty": "KZ",
    "astana": "KZ",
    "atyrau": "KZ",
    "aktobe": "KZ",
    "berlin": "DE",
    "boston": "US",
    "cambridge, massachusetts": "US",
    "daejeon": "KR",
    "dubai": "AE",
    "helsinki": "FI",
    "hillsboro, oregon": "US",
    "hong kong": "HK",
    "hwaseong": "KR",
    "karlsruhe": "DE",
    "london": "GB",
    "los angeles": "US",
    "luxembourg": "LU",
    "moscow": "RU",
    "mountain view": "US",
    "new york": "US",
    "novosibirsk": "RU",
    "riyadh": "SA",
    "san francisco": "US",
    "seattle": "US",
    "seoul": "KR",
    "singapore": "SG",
    "warsaw": "PL",
    "zurich": "CH",
    "алматы": "KZ",
    "астана": "KZ",
    "атырау": "KZ",
    "эр-рияд": "SA",
}

PROFILE_COUNTRY_CODE_PATTERN = re.compile(
    r"(?P<label>[^#\n]{2,100}?)\s+\((?P<code>[A-Z]{2})\)"
    r"(?=\s+(?:\d[\d,+]*\s+(?:connections|followers)|\.{3}))"
)
CURRENT_ROLE_BLOCK_PATTERN = re.compile(
    r"\(Current\)(?P<body>(?:(?!#{3,4}).){0,360})",
    re.IGNORECASE,
)
ROLE_LOCATION_PATTERN = re.compile(
    r"\bin\s+(?P<location>[^#]{2,100}?)(?=\s*\.{3}|\s+Department:|\s+#{3,4}|$)",
    re.IGNORECASE,
)
EMPLOYER_DESCRIPTION_PATTERN = re.compile(
    r"\b(?:employees?|founded|headquartered|workforce|revenue|funding|research output)\b",
    re.IGNORECASE,
)

OUTPUT_FIELDS = [
    "person_id",
    "name",
    "country_code",
    "country_name",
    "location_label",
    "evidence_url",
    "evidence_kind",
    "confidence",
    "review_reason",
]


def clean_text(value: object) -> str:
    text = "" if value is None else str(value)
    return re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()


def country_from_location(location: str) -> str:
    normalized = clean_text(location).casefold()
    for alias, code in sorted(COUNTRY_ALIASES.items(), key=lambda item: -len(item[0])):
        if re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", normalized):
            return code
    for city, code in sorted(CITY_COUNTRIES.items(), key=lambda item: -len(item[0])):
        if city in normalized:
            return code
    return ""


def extract_location(highlights: str) -> dict[str, str] | None:
    text = clean_text(highlights)
    header = text.split("## Experience", 1)[0][:600]
    for match in PROFILE_COUNTRY_CODE_PATTERN.finditer(header):
        raw_code = match.group("code")
        code = "GB" if raw_code == "UK" else raw_code
        if code not in COUNTRY_NAMES:
            continue
        return {
            "country_code": code,
            "country_name": COUNTRY_NAMES[code],
            "location_label": COUNTRY_NAMES[code],
            "evidence_kind": "public_profile_location",
            "confidence": "confirmed",
            "review_reason": "Country code is exposed in the accepted public profile location.",
        }

    for block_match in CURRENT_ROLE_BLOCK_PATTERN.finditer(text):
        body = block_match.group("body")
        description_match = EMPLOYER_DESCRIPTION_PATTERN.search(body)
        role_metadata = body[: description_match.start()] if description_match else body
        for current_match in ROLE_LOCATION_PATTERN.finditer(role_metadata):
            location = clean_text(current_match.group("location")).strip(" .,-")
            if ". " in location:
                continue
            code = country_from_location(location)
            if code:
                return {
                    "country_code": code,
                    "country_name": COUNTRY_NAMES[code],
                    "location_label": location,
                    "evidence_kind": "current_role_location",
                    "confidence": "probable",
                    "review_reason": "Country is derived from the location attached to the accepted current role.",
                }
    return None


def load_overrides(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    overrides: dict[str, dict[str, str]] = {}
    for row in rows:
        person_id = clean_text(row.get("person_id"))
        if not person_id:
            raise ValueError("Location override is missing person_id")
        if person_id in overrides:
            raise ValueError(f"Duplicate location override person_id: {person_id}")
        code = clean_text(row.get("country_code")).upper()
        if code not in COUNTRY_NAMES:
            raise ValueError(f"Unsupported location country code for {person_id}: {code}")
        normalized = {field: clean_text(row.get(field)) for field in OUTPUT_FIELDS}
        normalized["country_code"] = code
        normalized["country_name"] = COUNTRY_NAMES[code]
        overrides[person_id] = normalized
    return overrides


def build_rows(
    people: list[dict[str, object]],
    searches: list[dict[str, object]],
    overrides: dict[str, dict[str, str]],
) -> list[dict[str, str]]:
    results_by_url: dict[str, list[dict[str, object]]] = {}
    for search in searches:
        for result in search.get("results", []):
            url_key = canonical_url(clean_text(result.get("url")))
            if url_key:
                results_by_url.setdefault(url_key, []).append(result)

    output = []
    for person in people:
        if clean_text(person.get("confidence")) not in {"probable", "confirmed"}:
            continue
        person_id = clean_text(person.get("person_id"))
        if person_id in overrides:
            row = dict(overrides[person_id])
            row["name"] = clean_text(person.get("name"))
            output.append(row)
            continue

        evidence_url = clean_text(person.get("linkedin_url"))
        candidates = results_by_url.get(canonical_url(evidence_url), [])
        location = next(
            (
                extracted
                for result in candidates
                if (extracted := extract_location(" ".join(result.get("highlights", []))))
            ),
            None,
        )
        if location:
            output.append(
                {
                    "person_id": person_id,
                    "name": clean_text(person.get("name")),
                    **location,
                    "evidence_url": evidence_url,
                }
            )
            continue

        fallback_code = clean_text(person.get("country_code")).upper()
        fallback_url = clean_text(person.get("profile_url"))
        if fallback_code in COUNTRY_NAMES and fallback_url:
            output.append(
                {
                    "person_id": person_id,
                    "name": clean_text(person.get("name")),
                    "country_code": fallback_code,
                    "country_name": COUNTRY_NAMES[fallback_code],
                    "location_label": COUNTRY_NAMES[fallback_code],
                    "evidence_url": fallback_url,
                    "evidence_kind": "affiliation_country",
                    "confidence": "probable",
                    "review_reason": "Country comes from the accepted structured affiliation record.",
                }
            )

    return sorted(output, key=lambda row: (row["name"].casefold(), row["person_id"]))


def write_outputs(rows: list[dict[str, str]], csv_path: Path, json_path: Path) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    json_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--people", type=Path, default=DEFAULT_PEOPLE)
    parser.add_argument("--exa-audit", type=Path, default=DEFAULT_EXA_AUDIT)
    parser.add_argument("--overrides", type=Path, default=DEFAULT_OVERRIDES)
    parser.add_argument("--output-csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_JSON)
    args = parser.parse_args()

    people = json.loads(args.people.read_text(encoding="utf-8"))
    audit = json.loads(args.exa_audit.read_text(encoding="utf-8"))
    rows = build_rows(people, audit.get("searches", []), load_overrides(args.overrides))
    write_outputs(rows, args.output_csv, args.output_json)
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["country_code"]] = counts.get(row["country_code"], 0) + 1
    print(json.dumps({"people_with_country": len(rows), "countries": counts}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
