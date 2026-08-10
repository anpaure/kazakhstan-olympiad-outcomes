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
    from scripts.hydrate_linkedin_profiles_with_exa import profile_search_records
    from scripts.organization_names import (
        canonicalize_organization,
        organization_audit_key,
        organization_key,
    )
except ModuleNotFoundError:  # Direct script execution adds scripts/ to sys.path.
    from build_exa_review_queue import canonical_url
    from hydrate_linkedin_profiles_with_exa import profile_search_records
    from organization_names import (
        canonicalize_organization,
        organization_audit_key,
        organization_key,
    )


DEFAULT_PEOPLE = Path("data/researched_people.json")
DEFAULT_EXA_AUDIT = Path("data/exa_linkedin_search_audit.json")
DEFAULT_EXA_PROFILES = Path("data/exa_linkedin_profile_audit.json")
DEFAULT_OVERRIDES = Path("data/location_overrides.csv")
DEFAULT_ORGANIZATION_LOCATIONS = Path("data/organization_locations.csv")
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
    "HU": "Hungary",
    "ID": "Indonesia",
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
    "RO": "Romania",
    "RS": "Serbia",
    "RU": "Russia",
    "SA": "Saudi Arabia",
    "SE": "Sweden",
    "SG": "Singapore",
    "TR": "Türkiye",
    "TW": "Taiwan",
    "AE": "United Arab Emirates",
    "US": "United States",
    "UZ": "Uzbekistan",
    "VN": "Vietnam",
    "KG": "Kyrgyzstan",
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
    "hungary": "HU",
    "indonesia": "ID",
    "india": "IN",
    "ireland": "IE",
    "israel": "IL",
    "italy": "IT",
    "japan": "JP",
    "kazakhstan": "KZ",
    "kazakhstant": "KZ",
    "luxembourg": "LU",
    "netherlands": "NL",
    "norway": "NO",
    "poland": "PL",
    "portugal": "PT",
    "qatar": "QA",
    "romania": "RO",
    "serbia": "RS",
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
    "taiwan": "TW",
    "united arab emirates": "AE",
    "united kingdom": "GB",
    "united states": "US",
    "united states of america": "US",
    "uzbekistan": "UZ",
    "vietnam": "VN",
    "kyrgyzstan": "KG",
    "бельгия": "BE",
    "казахстан": "KZ",
    "киргизия": "KG",
    "россия": "RU",
    "саудовская аравия": "SA",
    "соединенные штаты": "US",
    "швейцарская конфедерация": "CH",
    "южная корея": "KR",
}

CITY_COUNTRIES = {
    "abu dhabi": "AE",
    "al khobar": "SA",
    "almaty": "KZ",
    "amsterdam": "NL",
    "astana": "KZ",
    "atyrau": "KZ",
    "aktobe": "KZ",
    "berlin": "DE",
    "belgrade": "RS",
    "boston": "US",
    "cambridge, massachusetts": "US",
    "constanța": "RO",
    "daejeon": "KR",
    "debrecen": "HU",
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
    "palo alto, ca": "US",
    "taipei": "TW",
    "tashkent": "UZ",
    "toronto, on": "CA",
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
STRUCTURED_CURRENT_ROLE_PATTERN = re.compile(
    r"^###\s+(?P<header>[^\n]+?)\s+\(Current\)\s*$\n"
    r"(?P<body>.*?)(?=^###\s|\Z)",
    re.IGNORECASE | re.MULTILINE | re.DOTALL,
)
COMPACT_CURRENT_ROLE_PATTERN = re.compile(
    r"###\s+(?P<header>(?:(?!\s+#{3,4}\s).){1,300}?)\s+\(Current\)"
    r"(?P<body>(?:(?!\s+#{3,4}\s).){0,1200})",
    re.IGNORECASE,
)
ROLE_LOCATION_PATTERN = re.compile(
    r"\bin\s+(?P<location>[^#]{2,100}?)(?=\s*\.{3}|\s+Department:|\s+#{3,4}|$)",
    re.IGNORECASE,
)
MARKDOWN_LINK_PATTERN = re.compile(r"\[([^\]]+)\]\([^)]+\)")
EMPLOYER_DESCRIPTION_PATTERN = re.compile(
    r"\b(?:employees?|founded|headquartered|workforce|revenue|funding|research output)\b",
    re.IGNORECASE,
)
TRUSTED_OVERRIDE_KINDS = {
    "active_affiliation_profile_location",
    "affiliation_country",
    "career_source_location",
    "current_role_location",
}
PRIORITY_OVERRIDE_KINDS = {"current_role_location"}

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


def clean_location_label(value: object) -> str:
    location = re.sub(r"\s+,", ",", clean_text(value)).strip(" .,-")
    location = re.sub(r"\bKazakhstant\b", "Kazakhstan", location, flags=re.IGNORECASE)
    return re.sub(r",\s*US$", ", United States", location, flags=re.IGNORECASE)


def country_from_location(location: str) -> str:
    normalized = clean_text(location).casefold()
    for alias, code in sorted(COUNTRY_ALIASES.items(), key=lambda item: -len(item[0])):
        if re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", normalized):
            return code
    for city, code in sorted(CITY_COUNTRIES.items(), key=lambda item: -len(item[0])):
        if city in normalized:
            return code
    return ""


def extract_profile_location(highlights: str) -> dict[str, str] | None:
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
    return None


def role_heading_parts(header: str) -> tuple[str, str]:
    heading = clean_text(header)
    role = heading
    organization = ""
    links = list(MARKDOWN_LINK_PATTERN.finditer(heading))
    if links:
        organization_match = links[-1]
        organization = organization_match.group(1)
        role = heading[: organization_match.start()].removesuffix(" - ")
    elif " - " in heading:
        role, organization_text = heading.rsplit(" - ", 1)
        organization = organization_text
    role = MARKDOWN_LINK_PATTERN.sub(r"\1", role)
    organization = MARKDOWN_LINK_PATTERN.sub(r"\1", organization)
    return clean_text(role), clean_text(organization)


def structured_role_location(body: str) -> tuple[str, str]:
    date_line = next(
        (
            clean_text(raw_line)
            for raw_line in body.replace("\r\n", "\n").splitlines()
            if clean_text(raw_line)
        ),
        "",
    )
    match = re.search(r"\s(?:in|в)\s+(?P<location>.+)$", date_line, re.IGNORECASE)
    if not match:
        return "", ""
    prefix = date_line[: match.start()].casefold()
    if not re.search(r"\bpresent\b|настоящ|\b20\d{2}\b", prefix):
        return "", ""
    location = clean_location_label(match.group("location"))
    code = country_from_location(location)
    if code:
        return location, code
    return "", ""


def compact_role_location(body: str) -> tuple[str, str]:
    description_match = EMPLOYER_DESCRIPTION_PATTERN.search(body)
    role_metadata = body[: description_match.start()] if description_match else body
    role_metadata = role_metadata[:360]
    current_match = ROLE_LOCATION_PATTERN.search(role_metadata)
    if not current_match:
        return "", ""
    prefix = role_metadata[: current_match.start()].casefold()
    present_at = prefix.rfind("present")
    if present_at < 0:
        return "", ""
    gap = prefix[present_at + len("present") :]
    gap = re.sub(r"\b(?:and|months?|years?)\b|\d+", "", gap)
    if re.search(r"\w", gap):
        return "", ""
    location = clean_location_label(current_match.group("location"))
    if ". " in location:
        return "", ""
    code = country_from_location(location)
    if code:
        return location, code
    return "", ""


def extract_current_roles(highlights: str) -> list[dict[str, str]]:
    source_text = str(highlights or "").replace("\xa0", " ")
    roles: list[dict[str, str]] = []
    for match in STRUCTURED_CURRENT_ROLE_PATTERN.finditer(source_text):
        role, organization = role_heading_parts(match.group("header"))
        location, code = structured_role_location(match.group("body"))
        roles.append(
            {
                "role": role,
                "organization": organization,
                "location_label": location,
                "country_code": code,
                "structured": "true",
            }
        )
    if roles:
        return roles

    compact_text = clean_text(source_text)
    for match in COMPACT_CURRENT_ROLE_PATTERN.finditer(compact_text):
        role, organization = role_heading_parts(match.group("header"))
        location, code = compact_role_location(match.group("body"))
        roles.append(
            {
                "role": role,
                "organization": organization,
                "location_label": location,
                "country_code": code,
                "structured": "false",
            }
        )
    return roles


def role_key(value: object) -> str:
    text = clean_text(value).casefold()
    text = re.sub(r"\bsde\b", "software development engineer", text)
    return " ".join(re.findall(r"\w+", text))


def current_role_match_score(
    current_role: dict[str, str], destination_organization: str, destination_role: str
) -> int:
    organization = canonicalize_organization(current_role.get("organization"))
    expected_organization = canonicalize_organization(destination_organization)
    if organization and expected_organization:
        if organization_audit_key(organization) == organization_audit_key(
            expected_organization
        ):
            return 5

    actual_role = role_key(current_role.get("role"))
    expected_role = role_key(destination_role)
    if actual_role and expected_role:
        if actual_role == expected_role:
            return 4
        if min(len(actual_role), len(expected_role)) >= 8 and (
            actual_role in expected_role or expected_role in actual_role
        ):
            return 3
        ignored = {"a", "and", "at", "for", "in", "of", "the"}
        actual_tokens = set(actual_role.split()) - ignored
        expected_tokens = set(expected_role.split()) - ignored
        overlap = actual_tokens & expected_tokens
        if (
            len(overlap) >= 2
            and len(overlap) / min(len(actual_tokens), len(expected_tokens)) >= 0.6
        ):
            return 2
    return 0


def current_employment_location(
    person: dict[str, object], candidates: list[dict[str, object]]
) -> dict[str, str] | None:
    if clean_text(person.get("destination_status")) != "latest_employment":
        return None

    organization = canonicalize_organization(person.get("organization"))
    destination_role = clean_text(person.get("role"))
    ranked_locations: list[tuple[int, int, int, dict[str, str]]] = []
    ranked_headers: list[tuple[int, dict[str, str]]] = []
    for candidate in candidates:
        text = "\n\n".join(
            str(item).strip()
            for item in candidate.get("highlights", [])
            if str(item).strip()
        )
        if not text:
            continue
        header = extract_profile_location(text)
        if header:
            ranked_headers.append((len(text), header))
        for current_role in extract_current_roles(text):
            if not current_role.get("country_code"):
                continue
            score = current_role_match_score(
                current_role, organization, destination_role
            )
            if not score:
                continue
            ranked_locations.append(
                (
                    score,
                    1 if current_role.get("structured") == "true" else 0,
                    len(text),
                    current_role,
                )
            )

    if not ranked_locations:
        return None
    _, _, _, selected = max(ranked_locations, key=lambda item: item[:3])
    code = selected["country_code"]
    header = max(ranked_headers, key=lambda item: item[0])[1] if ranked_headers else None
    reason = (
        f"Country follows the location attached to the accepted current role at "
        f"{organization}."
    )
    if header and header.get("country_code") == code:
        reason += " The public profile header independently agrees."
    elif header:
        reason += (
            f" The profile header points to {header['country_name']}, but it conflicts "
            "with the active-role location and is not used."
        )
    confidence = (
        "confirmed"
        if clean_text(person.get("confidence")) == "confirmed"
        else "probable"
    )
    return {
        "country_code": code,
        "country_name": COUNTRY_NAMES[code],
        "location_label": selected["location_label"],
        "evidence_kind": "current_role_location",
        "confidence": confidence,
        "review_reason": reason,
    }


def extract_location(highlights: str) -> dict[str, str] | None:
    for current_role in extract_current_roles(highlights):
        code = current_role.get("country_code")
        if not code:
            continue
        return {
            "country_code": code,
            "country_name": COUNTRY_NAMES[code],
            "location_label": current_role["location_label"],
            "evidence_kind": "current_role_location",
            "confidence": "probable",
            "review_reason": "Country is derived from the location attached to the accepted current role.",
        }

    return extract_profile_location(highlights)


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


def load_organization_locations(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    locations: dict[str, dict[str, str]] = {}
    for row in rows:
        organization = canonicalize_organization(row.get("canonical_name"))
        key = organization_key(organization)
        if not key:
            raise ValueError("Organization location is missing canonical_name")
        if key in locations:
            raise ValueError(f"Duplicate organization location: {organization}")
        code = clean_text(row.get("country_code")).upper()
        if code not in COUNTRY_NAMES:
            raise ValueError(
                f"Unsupported organization location country code for {organization}: {code}"
            )
        evidence_url = clean_text(row.get("evidence_url"))
        if not evidence_url.startswith(("http://", "https://")):
            raise ValueError(
                f"Organization location has an invalid evidence URL for {organization}"
            )
        locations[key] = {
            "organization": organization,
            "country_code": code,
            "country_name": COUNTRY_NAMES[code],
            "location_label": clean_text(row.get("location_label"))
            or COUNTRY_NAMES[code],
            "evidence_url": evidence_url,
            "rationale": clean_text(row.get("rationale")),
        }
    return locations


def current_education_location(
    person: dict[str, object],
    organization_locations: dict[str, dict[str, str]],
) -> dict[str, str] | None:
    if (
        clean_text(person.get("destination_status")) != "current_education"
        or clean_text(person.get("affiliation_type")) != "education"
    ):
        return None
    organization = canonicalize_organization(person.get("organization"))
    location = organization_locations.get(organization_key(organization))
    if not location:
        return None
    confidence = (
        "confirmed"
        if clean_text(person.get("confidence")) == "confirmed"
        else "probable"
    )
    rationale = clean_text(location.get("rationale"))
    reason = (
        f"Country follows the accepted active student affiliation at {organization}; "
        "the linked official institution source establishes the campus location."
    )
    if rationale:
        reason = f"{reason} {rationale}"
    return {
        "country_code": location["country_code"],
        "country_name": location["country_name"],
        "location_label": location["location_label"],
        "evidence_url": location["evidence_url"],
        "evidence_kind": "current_education_location",
        "confidence": confidence,
        "review_reason": reason,
    }


def build_rows(
    people: list[dict[str, object]],
    searches: list[dict[str, object]],
    overrides: dict[str, dict[str, str]],
    organization_locations: dict[str, dict[str, str]] | None = None,
) -> list[dict[str, str]]:
    organization_locations = organization_locations or {}
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

        override = overrides.get(person_id)
        # A reviewed role location overrides conflicting automated extraction.
        if override and override.get("evidence_kind") in PRIORITY_OVERRIDE_KINDS:
            row = dict(override)
            row["name"] = clean_text(person.get("name"))
            output.append(row)
            continue

        education_location = current_education_location(
            person, organization_locations
        )
        if education_location:
            output.append(
                {
                    "person_id": person_id,
                    "name": clean_text(person.get("name")),
                    **education_location,
                }
            )
            continue

        evidence_url = clean_text(person.get("linkedin_url"))
        candidates = results_by_url.get(canonical_url(evidence_url), [])
        employment_location = current_employment_location(person, candidates)
        if employment_location:
            output.append(
                {
                    "person_id": person_id,
                    "name": clean_text(person.get("name")),
                    **employment_location,
                    "evidence_url": evidence_url,
                }
            )
            continue

        if override and override.get("evidence_kind") in TRUSTED_OVERRIDE_KINDS:
            row = dict(override)
            row["name"] = clean_text(person.get("name"))
            output.append(row)
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
    parser.add_argument("--exa-profiles", type=Path, default=DEFAULT_EXA_PROFILES)
    parser.add_argument("--overrides", type=Path, default=DEFAULT_OVERRIDES)
    parser.add_argument(
        "--organization-locations",
        type=Path,
        default=DEFAULT_ORGANIZATION_LOCATIONS,
    )
    parser.add_argument("--output-csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_JSON)
    args = parser.parse_args()

    people = json.loads(args.people.read_text(encoding="utf-8"))
    audit = json.loads(args.exa_audit.read_text(encoding="utf-8"))
    profile_audit = (
        json.loads(args.exa_profiles.read_text(encoding="utf-8"))
        if args.exa_profiles.exists()
        else {"profiles": []}
    )
    searches = audit.get("searches", []) + profile_search_records(
        profile_audit.get("profiles", [])
    )
    rows = build_rows(
        people,
        searches,
        load_overrides(args.overrides),
        load_organization_locations(args.organization_locations),
    )
    write_outputs(rows, args.output_csv, args.output_json)
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["country_code"]] = counts.get(row["country_code"], 0) + 1
    print(json.dumps({"people_with_country": len(rows), "countries": counts}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
