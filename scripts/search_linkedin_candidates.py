#!/usr/bin/env python3
"""Search for public LinkedIn candidates for olympiad participants.

This script intentionally searches public SERP snippets instead of scraping
LinkedIn profile pages. LinkedIn search results have many same-name false
positives, so output rows are candidate matches with scores, not identities
that should be treated as confirmed.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
import time
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable
from urllib.parse import quote_plus, urlparse

import requests


DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_USER_AGENT = "Mozilla/5.0 (compatible; iso-futures/0.1; +linkedin candidate research)"
LINKEDIN_HOST_RE = re.compile(r"(^|\.)linkedin\.com$", re.IGNORECASE)
NAME_STOPWORDS = {"bin", "ibn", "uly", "kyzy"}
KAZAKHSTAN_TERMS = {
    "kazakhstan",
    "kazakh",
    "almaty",
    "astana",
    "nur-sultan",
    "nursultan",
    "kz",
}
OLYMPIAD_TERMS = {
    "imo",
    "ioi",
    "ipho",
    "ibo",
    "icho",
    "olympiad",
    "olympiade",
    "international mathematical olympiad",
    "international olympiad in informatics",
    "international physics olympiad",
    "international biology olympiad",
    "international chemistry olympiad",
}


@dataclass(frozen=True)
class PersonSeed:
    person_key: str
    name: str
    olympiads: str
    years: str
    awards: str
    participant_rows: int


@dataclass(frozen=True)
class LinkedinCandidate:
    person_key: str
    name: str
    olympiads: str
    years: str
    query: str
    engine: str
    result_rank: int
    candidate_url: str
    candidate_title: str
    candidate_snippet: str
    score: float
    score_reasons: str
    search_url: str


def clean_text(value: object) -> str:
    text = "" if value is None else str(value)
    text = text.replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def normalize_text(value: str) -> str:
    value = value.casefold()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def name_tokens(name: str) -> list[str]:
    tokens = normalize_text(name).split()
    return [token for token in tokens if len(token) > 1 and token not in NAME_STOPWORDS]


def stable_cache_name(value: str, suffix: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:20]
    return f"{digest}{suffix}"


def load_people(input_csv: Path) -> list[PersonSeed]:
    people: dict[str, dict[str, object]] = {}
    with input_csv.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            name = clean_text(row.get("name"))
            if not name:
                continue
            person_key = normalize_text(name)
            entry = people.setdefault(
                person_key,
                {
                    "name": name,
                    "olympiads": set(),
                    "years": set(),
                    "awards": set(),
                    "rows": 0,
                },
            )
            entry["rows"] = int(entry["rows"]) + 1
            for field, target in [
                ("olympiad", "olympiads"),
                ("year", "years"),
                ("award", "awards"),
            ]:
                value = clean_text(row.get(field))
                if value:
                    entry[target].add(value)

    seeds: list[PersonSeed] = []
    for person_key, entry in people.items():
        years = sorted(entry["years"], reverse=True)
        olympiads = sorted(entry["olympiads"])
        awards = sorted(entry["awards"])
        seeds.append(
            PersonSeed(
                person_key=person_key,
                name=str(entry["name"]),
                olympiads=";".join(olympiads),
                years=";".join(years),
                awards=";".join(awards),
                participant_rows=int(entry["rows"]),
            )
        )
    return sorted(seeds, key=lambda item: (item.name.casefold(), item.person_key))


def build_query(person: PersonSeed, include_olympiad_terms: bool = True) -> str:
    parts = [f'site:linkedin.com/in "{person.name}"', "Kazakhstan"]
    if include_olympiad_terms:
        parts.extend(person.olympiads.split(";"))
        parts.append("olympiad")
    return " ".join(part for part in parts if part)


def bing_rss_search(query: str, cache_dir: Path, refresh: bool = False) -> tuple[str, list[dict[str, str]]]:
    search_url = f"https://www.bing.com/search?format=rss&setlang=en-US&cc=US&q={quote_plus(query)}"
    cache_path = cache_dir / stable_cache_name(search_url, ".xml")
    if cache_path.exists() and not refresh:
        text = cache_path.read_text(encoding="utf-8", errors="replace")
    else:
        response = requests.get(
            search_url,
            timeout=DEFAULT_TIMEOUT_SECONDS,
            headers={"User-Agent": DEFAULT_USER_AGENT},
        )
        response.raise_for_status()
        text = response.text
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(text, encoding="utf-8")

    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise RuntimeError(f"Bing RSS returned non-XML content: {exc}") from exc

    results: list[dict[str, str]] = []
    for item in root.findall("./channel/item"):
        results.append(
            {
                "title": clean_text(item.findtext("title")),
                "url": clean_text(item.findtext("link")),
                "snippet": clean_text(item.findtext("description")),
            }
        )
    return search_url, results


def is_linkedin_candidate(url: str, include_directory: bool) -> bool:
    parsed = urlparse(url)
    host = parsed.netloc.split("@")[-1].split(":")[0]
    if not LINKEDIN_HOST_RE.search(host):
        return False
    path = parsed.path.rstrip("/")
    if path.startswith("/in/"):
        return True
    return include_directory and path.startswith("/pub/dir/")


def score_candidate(person: PersonSeed, url: str, title: str, snippet: str) -> tuple[float, list[str]]:
    tokens = name_tokens(person.name)
    haystack = normalize_text(" ".join([url, title, snippet]))
    slug = normalize_text(urlparse(url).path)
    reasons: list[str] = []
    score = 0.0

    matched_tokens = [token for token in tokens if token in haystack]
    if tokens and len(matched_tokens) == len(tokens):
        score += 0.45
        reasons.append("all_name_tokens")
    elif tokens and len(matched_tokens) >= max(1, len(tokens) - 1):
        score += 0.30
        reasons.append("most_name_tokens")

    slug_matches = [token for token in tokens if token in slug]
    if tokens and len(slug_matches) == len(tokens):
        score += 0.20
        reasons.append("url_slug_matches_name")
    elif slug_matches:
        score += 0.08
        reasons.append("url_slug_partial_name")

    if "/in/" in urlparse(url).path:
        score += 0.08
        reasons.append("profile_url")
    elif "/pub/dir/" in urlparse(url).path:
        score += 0.03
        reasons.append("directory_url")

    if any(term in haystack for term in KAZAKHSTAN_TERMS):
        score += 0.15
        reasons.append("kazakhstan_context")

    olympiad_context = person.olympiads.casefold().split(";") + list(OLYMPIAD_TERMS)
    if any(term and term in haystack for term in olympiad_context):
        score += 0.12
        reasons.append("olympiad_context")

    return round(min(score, 1.0), 3), reasons


def search_people(
    people: Iterable[PersonSeed],
    cache_dir: Path,
    engine: str,
    refresh: bool,
    sleep_seconds: float,
    include_directory: bool,
    limit_per_person: int,
) -> tuple[list[LinkedinCandidate], list[dict[str, object]]]:
    candidates: list[LinkedinCandidate] = []
    audit: list[dict[str, object]] = []

    for index, person in enumerate(people, start=1):
        query = build_query(person)
        if engine != "bing-rss":
            raise ValueError(f"Unsupported engine: {engine}")

        try:
            search_url, results = bing_rss_search(query, cache_dir, refresh)
            linkedin_results = [
                (rank, result)
                for rank, result in enumerate(results, start=1)
                if is_linkedin_candidate(result["url"], include_directory)
            ]
            accepted = 0
            seen_urls: set[str] = set()
            for rank, result in linkedin_results:
                url = result["url"]
                if url in seen_urls:
                    continue
                seen_urls.add(url)
                score, reasons = score_candidate(person, url, result["title"], result["snippet"])
                if not any(reason in reasons for reason in {"all_name_tokens", "most_name_tokens"}):
                    continue
                candidates.append(
                    LinkedinCandidate(
                        person_key=person.person_key,
                        name=person.name,
                        olympiads=person.olympiads,
                        years=person.years,
                        query=query,
                        engine=engine,
                        result_rank=rank,
                        candidate_url=url,
                        candidate_title=result["title"],
                        candidate_snippet=result["snippet"],
                        score=score,
                        score_reasons=";".join(reasons),
                        search_url=search_url,
                    )
                )
                accepted += 1
                if accepted >= limit_per_person:
                    break

            audit.append(
                {
                    "person_key": person.person_key,
                    "name": person.name,
                    "query": query,
                    "engine": engine,
                    "search_url": search_url,
                    "raw_result_count": len(results),
                    "linkedin_result_count": len(linkedin_results),
                    "accepted_count": accepted,
                    "status": "ok",
                }
            )
        except Exception as exc:
            audit.append(
                {
                    "person_key": person.person_key,
                    "name": person.name,
                    "query": query,
                    "engine": engine,
                    "raw_result_count": 0,
                    "linkedin_result_count": 0,
                    "accepted_count": 0,
                    "status": "error",
                    "error": str(exc),
                }
            )

        if index % 25 == 0:
            print(f"Searched {index} people; candidates so far: {len(candidates)}", file=sys.stderr)
        if sleep_seconds > 0:
            time.sleep(sleep_seconds)

    return candidates, audit


def write_candidates(candidates: list[LinkedinCandidate], out_csv: Path, out_json: Path) -> None:
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(LinkedinCandidate.__dataclass_fields__.keys())
    with out_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for candidate in candidates:
            writer.writerow(asdict(candidate))
    out_json.write_text(
        json.dumps([asdict(candidate) for candidate in candidates], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def write_audit(audit: list[dict[str, object]], out_json: Path, out_csv: Path) -> None:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    fieldnames = [
        "person_key",
        "name",
        "query",
        "engine",
        "search_url",
        "raw_result_count",
        "linkedin_result_count",
        "accepted_count",
        "status",
        "error",
    ]
    with out_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in audit:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-csv", default="data/kazakhstan_participants.csv")
    parser.add_argument("--out-csv", default="data/linkedin_candidates.csv")
    parser.add_argument("--out-json", default="data/linkedin_candidates.json")
    parser.add_argument("--audit-json", default="data/linkedin_search_audit.json")
    parser.add_argument("--audit-csv", default="data/linkedin_search_audit.csv")
    parser.add_argument("--cache-dir", default="data/cache/linkedin_search")
    parser.add_argument("--engine", default="bing-rss", choices=["bing-rss"])
    parser.add_argument("--refresh", action="store_true", help="Refresh cached SERP responses.")
    parser.add_argument("--sleep", type=float, default=0.5, help="Seconds to pause between searches.")
    parser.add_argument("--max-people", type=int, default=0, help="Limit people searched; 0 means all.")
    parser.add_argument("--limit-per-person", type=int, default=5)
    parser.add_argument(
        "--include-directory",
        action="store_true",
        help="Also keep LinkedIn /pub/dir directory pages. Default keeps /in profile pages only.",
    )
    args = parser.parse_args()

    input_csv = Path(args.input_csv)
    people = load_people(input_csv)
    if args.max_people > 0:
        people = people[: args.max_people]

    print(f"Loaded {len(people)} unique people from {input_csv}")
    candidates, audit = search_people(
        people=people,
        cache_dir=Path(args.cache_dir),
        engine=args.engine,
        refresh=args.refresh,
        sleep_seconds=args.sleep,
        include_directory=args.include_directory,
        limit_per_person=args.limit_per_person,
    )
    write_candidates(candidates, Path(args.out_csv), Path(args.out_json))
    write_audit(audit, Path(args.audit_json), Path(args.audit_csv))

    searched = len(audit)
    ok = sum(1 for item in audit if item.get("status") == "ok")
    errors = searched - ok
    matched_people = len({candidate.person_key for candidate in candidates})
    print(f"Wrote {len(candidates)} candidate rows to {args.out_csv} and {args.out_json}")
    print(f"Wrote search audit to {args.audit_json} and {args.audit_csv}")
    print(
        json.dumps(
            {
                "people_searched": searched,
                "searches_ok": ok,
                "search_errors": errors,
                "matched_people": matched_people,
                "candidate_rows": len(candidates),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
