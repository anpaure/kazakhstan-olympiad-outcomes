#!/usr/bin/env python3
"""Search LinkedIn profiles for Olympiad competitors through the Exa API.

The API key is read only from EXA_API_KEY and is never written to output. Results
are checkpointed after every person in both nested JSON and flat CSV form so a
reviewer can reproduce every identity decision from the query and source URL.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests


EXA_SEARCH_URL = "https://api.exa.ai/search"
DEFAULT_INPUT = Path("data/researched_people.csv")
DEFAULT_JSON_OUTPUT = Path("data/exa_linkedin_search_audit.json")
DEFAULT_CSV_OUTPUT = Path("data/exa_linkedin_search_audit.csv")
DEFAULT_CONFIDENCES = {"unmatched", "probable"}
DEFAULT_SCOPES = {"career", "early_career_or_university"}

CSV_FIELDS = [
    "person_id",
    "name",
    "olympiads",
    "years",
    "prior_confidence",
    "query",
    "search_status",
    "error",
    "request_id",
    "cost_usd",
    "result_rank",
    "title",
    "url",
    "result_kind",
    "exact_name_in_title",
    "published_date",
    "author",
    "highlights",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def clean_text(value: object) -> str:
    text = "" if value is None else str(value)
    return re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()


def normalize_name(value: str) -> str:
    value = value.casefold()
    value = "".join(character if character.isalnum() else " " for character in value)
    return re.sub(r"\s+", " ", value).strip()


def exact_name_in_title(name: str, title: str) -> bool:
    normalized_name = normalize_name(name)
    normalized_title = normalize_name(title)
    if not normalized_name:
        return False
    if f" {normalized_name} " in f" {normalized_title} ":
        return True

    name_tokens = [token for token in normalized_name.split() if len(token) > 1]
    if len(name_tokens) < 2:
        return False
    title_counts = Counter(normalized_title.split())
    return not (Counter(name_tokens) - title_counts)


def linkedin_result_kind(url: str) -> str:
    parsed = urlparse(url)
    host = parsed.netloc.casefold().split(":", 1)[0]
    if host != "linkedin.com" and not host.endswith(".linkedin.com"):
        return "non_linkedin"
    path = parsed.path.rstrip("/")
    if path.startswith("/in/"):
        return "profile"
    if path.startswith("/company/"):
        return "company"
    if path.startswith("/posts/") or path.startswith("/pulse/"):
        return "post"
    return "other_linkedin"


def identity_names(person: dict[str, str]) -> list[str]:
    canonical_name = clean_text(person.get("name") or person.get("canonical_name"))
    names = [canonical_name]
    names.extend(clean_text(alias) for alias in str(person.get("aliases") or "").split(";"))

    distinct_names = []
    seen = set()
    for name in names:
        normalized = normalize_name(name)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        distinct_names.append(name)
    return distinct_names


def build_query(person: dict[str, str]) -> str:
    names = identity_names(person)
    name_query = " OR ".join(f'"{name}"' for name in names)
    if len(names) > 1:
        name_query = f"({name_query})"
    olympiads = clean_text(person.get("olympiads"))
    years = clean_text(person.get("years"))
    return (
        f"{name_query} Kazakhstan {olympiads} Olympiad {years} "
        "current employer university role"
    ).strip()


def load_people(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def select_people(
    people: list[dict[str, str]],
    person_ids: set[str] | None = None,
    names: set[str] | None = None,
    confidences: set[str] | None = None,
    scopes: set[str] | None = None,
    limit: int | None = None,
    include_all: bool = False,
) -> list[dict[str, str]]:
    person_ids = person_ids or set()
    normalized_names = {normalize_name(name) for name in names or set()}
    explicit_selection = bool(person_ids or normalized_names)
    confidences = confidences or DEFAULT_CONFIDENCES
    scopes = scopes or DEFAULT_SCOPES

    selected = []
    for person in people:
        person_id = clean_text(person.get("person_id"))
        name = clean_text(person.get("name") or person.get("canonical_name"))
        if explicit_selection:
            if person_id not in person_ids and normalize_name(name) not in normalized_names:
                continue
        elif not include_all and (
            clean_text(person.get("confidence")) not in confidences
            or clean_text(person.get("research_scope")) not in scopes
        ):
            continue
        selected.append(person)

    selected.sort(
        key=lambda row: (
            int(clean_text(row.get("first_year")) or 9999),
            clean_text(row.get("name") or row.get("canonical_name")).casefold(),
        )
    )
    return selected[:limit] if limit is not None else selected


class ExaClient:
    def __init__(self, api_key: str, timeout: float = 45.0, retries: int = 3):
        self.api_key = api_key
        self.timeout = timeout
        self.retries = retries

    def search_linkedin(self, query: str, num_results: int) -> dict[str, object]:
        payload = {
            "query": query,
            "includeDomains": ["linkedin.com"],
            "category": "people",
            "type": "auto",
            "numResults": num_results,
            "contents": {
                "highlights": {
                    "maxCharacters": 1800,
                }
            },
        }
        for attempt in range(self.retries):
            response = requests.post(
                EXA_SEARCH_URL,
                headers={
                    "x-api-key": self.api_key,
                    "Content-Type": "application/json",
                    "User-Agent": "iso-futures/0.1",
                },
                json=payload,
                timeout=self.timeout,
            )
            if response.status_code != 429 and response.status_code < 500:
                response.raise_for_status()
                return response.json()
            if attempt + 1 < self.retries:
                time.sleep(2**attempt)
        response.raise_for_status()
        raise RuntimeError("Exa search failed without an HTTP error")


def normalize_result(
    result: dict[str, object], rank: int, names: list[str]
) -> dict[str, object]:
    title = clean_text(result.get("title"))
    url = clean_text(result.get("url"))
    highlights = [clean_text(item) for item in result.get("highlights", []) if clean_text(item)]
    scores = result.get("highlightScores", [])
    return {
        "rank": rank,
        "title": title,
        "url": url,
        "published_date": clean_text(result.get("publishedDate")),
        "author": clean_text(result.get("author")),
        "result_kind": linkedin_result_kind(url),
        "exact_name_in_title": any(exact_name_in_title(name, title) for name in names),
        "highlights": highlights,
        "highlight_scores": scores if isinstance(scores, list) else [],
    }


def search_person(
    client: ExaClient,
    person: dict[str, str],
    num_results: int,
) -> dict[str, object]:
    name = clean_text(person.get("name") or person.get("canonical_name"))
    names = identity_names(person)
    query = build_query(person)
    base = {
        "person_id": clean_text(person.get("person_id")),
        "name": name,
        "olympiads": clean_text(person.get("olympiads")),
        "years": clean_text(person.get("years")),
        "prior_confidence": clean_text(person.get("confidence")),
        "query": query,
        "searched_at": utc_now(),
    }
    try:
        response = client.search_linkedin(query, num_results)
    except (requests.RequestException, ValueError) as exc:
        return {
            **base,
            "status": "error",
            "error": clean_text(exc),
            "request_id": "",
            "cost_usd": 0.0,
            "results": [],
        }

    cost = response.get("costDollars", {})
    cost_total = cost.get("total", 0.0) if isinstance(cost, dict) else 0.0
    raw_results = response.get("results", [])
    results = [
        normalize_result(result, rank, names)
        for rank, result in enumerate(raw_results, start=1)
        if isinstance(result, dict)
    ]
    return {
        **base,
        "status": "ok",
        "error": "",
        "request_id": clean_text(response.get("requestId")),
        "cost_usd": float(cost_total or 0.0),
        "results": results,
    }


def load_existing(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    searches = data.get("searches", []) if isinstance(data, dict) else data
    return [item for item in searches if isinstance(item, dict)]


def should_search(
    previous: dict[str, object] | None,
    refresh: bool = False,
    retry_errors: bool = False,
) -> bool:
    if refresh or previous is None:
        return True
    return bool(retry_errors and previous.get("status") == "error")


def flat_rows(searches: list[dict[str, object]]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for search in searches:
        common = {
            "person_id": search.get("person_id", ""),
            "name": search.get("name", ""),
            "olympiads": search.get("olympiads", ""),
            "years": search.get("years", ""),
            "prior_confidence": search.get("prior_confidence", ""),
            "query": search.get("query", ""),
            "search_status": search.get("status", ""),
            "error": search.get("error", ""),
            "request_id": search.get("request_id", ""),
            "cost_usd": search.get("cost_usd", 0.0),
        }
        results = search.get("results", [])
        if not isinstance(results, list) or not results:
            rows.append({**common})
            continue
        for result in results:
            if not isinstance(result, dict):
                continue
            rows.append(
                {
                    **common,
                    "result_rank": result.get("rank", ""),
                    "title": result.get("title", ""),
                    "url": result.get("url", ""),
                    "result_kind": result.get("result_kind", ""),
                    "exact_name_in_title": result.get("exact_name_in_title", False),
                    "published_date": result.get("published_date", ""),
                    "author": result.get("author", ""),
                    "highlights": " | ".join(result.get("highlights", [])),
                }
            )
    return rows


def write_outputs(
    searches: list[dict[str, object]],
    json_path: Path,
    csv_path: Path,
    input_path: Path,
    input_people_count: int,
) -> None:
    searches.sort(key=lambda item: (clean_text(item.get("name")).casefold(), clean_text(item.get("person_id"))))
    searched_people_count = len(
        {clean_text(item.get("person_id")) for item in searches if clean_text(item.get("person_id"))}
    )
    successful_search_count = sum(item.get("status") == "ok" for item in searches)
    error_search_count = sum(item.get("status") == "error" for item in searches)
    payload = {
        "provider": "Exa",
        "endpoint": EXA_SEARCH_URL,
        "generated_at": utc_now(),
        "input_path": str(input_path),
        "input_people_count": input_people_count,
        "searched_people_count": searched_people_count,
        "successful_search_count": successful_search_count,
        "error_search_count": error_search_count,
        "coverage_percent": round(
            100 * searched_people_count / input_people_count if input_people_count else 0.0,
            2,
        ),
        "search_count": len(searches),
        "total_cost_usd": round(sum(float(item.get("cost_usd", 0.0) or 0.0) for item in searches), 6),
        "key_persisted": False,
        "searches": searches,
    }
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_tmp = json_path.with_suffix(json_path.suffix + ".tmp")
    json_tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    json_tmp.replace(json_path)

    csv_path.parent.mkdir(parents=True, exist_ok=True)
    csv_tmp = csv_path.with_suffix(csv_path.suffix + ".tmp")
    with csv_tmp.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(flat_rows(searches))
    csv_tmp.replace(csv_path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--output-csv", type=Path, default=DEFAULT_CSV_OUTPUT)
    parser.add_argument("--person-id", action="append", default=[])
    parser.add_argument("--name", action="append", default=[])
    parser.add_argument("--confidence", action="append", default=[])
    parser.add_argument("--scope", action="append", default=[])
    parser.add_argument(
        "--all",
        dest="all_people",
        action="store_true",
        help="select every person in the input; completed searches are still resumed",
    )
    parser.add_argument("--limit", type=int)
    parser.add_argument("--num-results", type=int, default=5)
    parser.add_argument("--delay", type=float, default=0.25)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--retry-errors", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    api_key = os.getenv("EXA_API_KEY")
    if not api_key:
        print("EXA_API_KEY is required and must be supplied through the environment.", file=sys.stderr)
        return 2
    if args.all_people and (args.person_id or args.name or args.confidence or args.scope):
        raise SystemExit(
            "--all cannot be combined with --person-id, --name, --confidence, or --scope"
        )
    if args.limit is not None and args.limit < 1:
        raise SystemExit("--limit must be at least 1")
    if not 1 <= args.num_results <= 100:
        raise SystemExit("--num-results must be between 1 and 100")

    people = load_people(args.input)
    selected = select_people(
        people,
        person_ids=set(args.person_id),
        names=set(args.name),
        confidences=set(args.confidence) or None,
        scopes=set(args.scope) or None,
        limit=args.limit,
        include_all=args.all_people,
    )
    if not selected:
        print("No people matched the requested selection.", file=sys.stderr)
        return 1

    existing = load_existing(args.output_json)
    valid_person_ids = {
        clean_text(person.get("person_id"))
        for person in people
        if clean_text(person.get("person_id"))
    }
    existing = [
        item
        for item in existing
        if clean_text(item.get("person_id")) in valid_person_ids
    ]
    by_person = {clean_text(item.get("person_id")): item for item in existing}
    client = ExaClient(api_key)
    searched = 0
    for person in selected:
        person_id = clean_text(person.get("person_id"))
        previous = by_person.get(person_id)
        if not should_search(previous, refresh=args.refresh, retry_errors=args.retry_errors):
            print(f"skip {person_id}: already searched", file=sys.stderr)
            continue

        result = search_person(client, person, args.num_results)
        by_person[person_id] = result
        searched += 1
        print(
            f"searched {person_id} {result['name']}: "
            f"{result['status']} ({len(result['results'])} results)",
            file=sys.stderr,
        )
        write_outputs(
            list(by_person.values()),
            args.output_json,
            args.output_csv,
            args.input,
            len(people),
        )
        if args.delay > 0:
            time.sleep(args.delay)

    write_outputs(
        list(by_person.values()),
        args.output_json,
        args.output_csv,
        args.input,
        len(people),
    )
    total_cost = sum(float(item.get("cost_usd", 0.0) or 0.0) for item in by_person.values())
    searched_people_count = len(
        {clean_text(item.get("person_id")) for item in by_person.values() if clean_text(item.get("person_id"))}
    )
    print(
        json.dumps(
            {
                "selected": len(selected),
                "searched_this_run": searched,
                "audit_searches": len(by_person),
                "input_people": len(people),
                "searched_people": searched_people_count,
                "coverage_percent": round(
                    100 * searched_people_count / len(people) if people else 0.0,
                    2,
                ),
                "total_audit_cost_usd": round(total_cost, 6),
                "output_json": str(args.output_json),
                "output_csv": str(args.output_csv),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
