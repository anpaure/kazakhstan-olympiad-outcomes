#!/usr/bin/env python3
"""Retrieve accepted LinkedIn profile URLs directly through the Exa API.

Search results can miss an already-reviewed profile URL. This pass hydrates those
exact URLs so employment, education, and location extraction do not depend on
whether a name search happened to return the accepted profile.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

try:
    from scripts.build_exa_review_queue import canonical_url
except ModuleNotFoundError:  # Direct script execution adds scripts/ to sys.path.
    from build_exa_review_queue import canonical_url


EXA_CONTENTS_URL = "https://api.exa.ai/contents"
EXA_SEARCH_URL = "https://api.exa.ai/search"
DEFAULT_INPUT = Path("data/researched_people.csv")
DEFAULT_SEARCH_AUDIT = Path("data/exa_linkedin_search_audit.json")
DEFAULT_MANUAL_PROFILES = Path("data/manual_linkedin_profiles.csv")
DEFAULT_JSON_OUTPUT = Path("data/exa_linkedin_profile_audit.json")
DEFAULT_CSV_OUTPUT = Path("data/exa_linkedin_profile_audit.csv")
MANUAL_PROFILE_STATUS = "manual_public_profile"

CSV_FIELDS = [
    "person_id",
    "name",
    "linkedin_url",
    "status",
    "error",
    "request_id",
    "retrieved_at",
    "title",
    "resolved_url",
    "content_characters",
    "source_endpoint",
    "text",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def clean_text(value: object) -> str:
    text = "" if value is None else str(value)
    return re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()


def csv_value(value: object) -> object:
    if not isinstance(value, str):
        return value
    return "\n".join(line.rstrip() for line in value.splitlines())


def load_people(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def select_profiles(
    people: list[dict[str, str]],
    person_ids: set[str] | None = None,
    names: set[str] | None = None,
    limit: int | None = None,
) -> list[dict[str, str]]:
    person_ids = person_ids or set()
    normalized_names = {clean_text(name).casefold() for name in names or set()}
    explicit = bool(person_ids or normalized_names)
    selected = []
    for person in people:
        person_id = clean_text(person.get("person_id"))
        name = clean_text(person.get("name") or person.get("canonical_name"))
        linkedin_url = clean_text(person.get("linkedin_url"))
        if not linkedin_url or "linkedin.com/in/" not in linkedin_url.casefold():
            continue
        if clean_text(person.get("confidence")) not in {"probable", "confirmed"}:
            continue
        if explicit and person_id not in person_ids and name.casefold() not in normalized_names:
            continue
        selected.append(
            {
                "person_id": person_id,
                "name": name,
                "linkedin_url": linkedin_url,
            }
        )
    selected.sort(key=lambda row: (row["name"].casefold(), row["person_id"]))
    return selected[:limit] if limit is not None else selected


class ExaContentsClient:
    def __init__(self, api_key: str, timeout: float = 90.0, retries: int = 3):
        self.api_key = api_key
        self.timeout = timeout
        self.retries = retries

    def retrieve(self, urls: list[str], max_characters: int) -> dict[str, object]:
        payload = {
            "ids": urls,
            "text": {"maxCharacters": max_characters},
        }
        for attempt in range(self.retries):
            response = requests.post(
                EXA_CONTENTS_URL,
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
        raise RuntimeError("Exa contents request failed without an HTTP error")


def error_text(value: object) -> str:
    if isinstance(value, dict):
        return clean_text(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return clean_text(value)


def normalize_batch(
    selected: list[dict[str, str]],
    response: dict[str, object],
    retrieved_at: str,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    request_id = clean_text(response.get("requestId"))
    results_by_url: dict[str, dict[str, object]] = {}
    for result in response.get("results", []):
        if not isinstance(result, dict):
            continue
        for field in ("id", "url"):
            key = canonical_url(clean_text(result.get(field)))
            if key:
                results_by_url[key] = result
    statuses_by_url = {
        canonical_url(clean_text(status.get("id"))): status
        for status in response.get("statuses", [])
        if isinstance(status, dict) and canonical_url(clean_text(status.get("id")))
    }

    profiles: list[dict[str, object]] = []
    for person in selected:
        linkedin_url = person["linkedin_url"]
        key = canonical_url(linkedin_url)
        result = results_by_url.get(key)
        status = statuses_by_url.get(key, {})
        successful = bool(result) and clean_text(status.get("status") or "success") == "success"
        text = str(result.get("text") or "") if result else ""
        profiles.append(
            {
                **person,
                "status": "success" if successful else "error",
                "error": "" if successful else error_text(status.get("error") or "No Exa result returned"),
                "request_id": request_id,
                "retrieved_at": retrieved_at,
                "title": clean_text(result.get("title")) if result else "",
                "resolved_url": clean_text(result.get("url")) if result else "",
                "content_characters": len(text),
                "source_endpoint": EXA_CONTENTS_URL,
                "text": text,
            }
        )

    cost = response.get("costDollars", {})
    request_cost = cost.get("total", 0.0) if isinstance(cost, dict) else 0.0
    request = {
        "request_id": request_id,
        "retrieved_at": retrieved_at,
        "requested_profile_count": len(selected),
        "cost_usd": float(request_cost or 0.0),
    }
    return profiles, request


def profile_search_records(profiles: list[dict[str, object]]) -> list[dict[str, object]]:
    records = []
    for profile in profiles:
        if clean_text(profile.get("status")) not in {
            "success",
            "search_cache",
            MANUAL_PROFILE_STATUS,
        }:
            continue
        text = str(profile.get("text") or "")
        url = clean_text(profile.get("resolved_url") or profile.get("linkedin_url"))
        if not text or not url:
            continue
        records.append(
            {
                "person_id": clean_text(profile.get("person_id")),
                "results": [
                    {
                        "url": url,
                        "title": clean_text(profile.get("title")),
                        "highlights": [text],
                    }
                ],
            }
        )
    return records


def cached_profiles_from_search(
    selected: list[dict[str, str]], searches: list[dict[str, object]]
) -> list[dict[str, object]]:
    results_by_url: dict[str, tuple[dict[str, object], dict[str, object]]] = {}
    for search in searches:
        for result in search.get("results", []):
            if not isinstance(result, dict):
                continue
            key = canonical_url(clean_text(result.get("url")))
            if key:
                results_by_url[key] = (search, result)

    profiles = []
    for person in selected:
        match = results_by_url.get(canonical_url(person["linkedin_url"]))
        if not match:
            continue
        search, result = match
        text = "\n\n".join(
            str(item).strip()
            for item in result.get("highlights", [])
            if str(item).strip()
        )
        if not text:
            continue
        profiles.append(
            {
                **person,
                "status": "search_cache",
                "error": "",
                "request_id": clean_text(search.get("request_id")),
                "retrieved_at": clean_text(search.get("searched_at")),
                "title": clean_text(result.get("title")),
                "resolved_url": clean_text(result.get("url")),
                "content_characters": len(text),
                "source_endpoint": EXA_SEARCH_URL,
                "text": text,
            }
        )
    return profiles


def normalize_manual_profiles(rows: list[dict[str, str]]) -> list[dict[str, object]]:
    profiles = []
    for row in rows:
        person_id = clean_text(row.get("person_id"))
        linkedin_url = clean_text(row.get("linkedin_url"))
        text = str(row.get("text") or "").strip()
        if not person_id or not linkedin_url or not text:
            continue
        profiles.append(
            {
                "person_id": person_id,
                "name": clean_text(row.get("name")),
                "linkedin_url": linkedin_url,
                "status": MANUAL_PROFILE_STATUS,
                "error": "",
                "request_id": "",
                "retrieved_at": clean_text(row.get("reviewed_at")),
                "title": clean_text(row.get("title")),
                "resolved_url": linkedin_url,
                "content_characters": len(text),
                "source_endpoint": clean_text(row.get("evidence_url")) or linkedin_url,
                "text": text,
            }
        )
    return profiles


def load_manual_profiles(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return normalize_manual_profiles(list(csv.DictReader(handle)))


def load_existing(path: Path) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    if not path.exists():
        return [], []
    payload = json.loads(path.read_text(encoding="utf-8"))
    return (
        [row for row in payload.get("profiles", []) if isinstance(row, dict)],
        [row for row in payload.get("requests", []) if isinstance(row, dict)],
    )


def write_outputs(
    profiles: list[dict[str, object]],
    requests_log: list[dict[str, object]],
    json_path: Path,
    csv_path: Path,
    input_path: Path,
    input_people_count: int,
    accepted_linkedin_count: int,
) -> None:
    for profile in profiles:
        if not clean_text(profile.get("source_endpoint")):
            status = clean_text(profile.get("status"))
            if status == "search_cache":
                profile["source_endpoint"] = EXA_SEARCH_URL
            elif status == MANUAL_PROFILE_STATUS:
                profile["source_endpoint"] = clean_text(
                    profile.get("resolved_url") or profile.get("linkedin_url")
                )
            else:
                profile["source_endpoint"] = EXA_CONTENTS_URL
    profiles.sort(key=lambda row: (clean_text(row.get("name")).casefold(), clean_text(row.get("person_id"))))
    payload = {
        "provider": "Exa with reviewed public-profile supplements",
        "endpoint": EXA_CONTENTS_URL,
        "fallback_endpoint": EXA_SEARCH_URL,
        "generated_at": utc_now(),
        "input_path": str(input_path),
        "input_people_count": input_people_count,
        "accepted_linkedin_count": accepted_linkedin_count,
        "profile_count": len(profiles),
        "successful_profile_count": sum(row.get("status") == "success" for row in profiles),
        "cached_search_profile_count": sum(
            row.get("status") == "search_cache" for row in profiles
        ),
        "manual_public_profile_count": sum(
            row.get("status") == MANUAL_PROFILE_STATUS for row in profiles
        ),
        "error_profile_count": sum(row.get("status") == "error" for row in profiles),
        "total_cost_usd": round(
            sum(float(row.get("cost_usd", 0.0) or 0.0) for row in requests_log), 6
        ),
        "key_persisted": False,
        "requests": requests_log,
        "profiles": profiles,
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
        writer.writerows(
            {
                field: csv_value(profile.get(field, ""))
                for field in CSV_FIELDS
            }
            for profile in profiles
        )
    csv_tmp.replace(csv_path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--search-audit", type=Path, default=DEFAULT_SEARCH_AUDIT)
    parser.add_argument("--manual-profiles", type=Path, default=DEFAULT_MANUAL_PROFILES)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--output-csv", type=Path, default=DEFAULT_CSV_OUTPUT)
    parser.add_argument("--person-id", action="append", default=[])
    parser.add_argument("--name", action="append", default=[])
    parser.add_argument("--limit", type=int)
    parser.add_argument("--batch-size", type=int, default=25)
    parser.add_argument("--max-characters", type=int, default=24000)
    parser.add_argument("--delay", type=float, default=0.25)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--retry-errors", action="store_true")
    parser.add_argument(
        "--from-search-cache",
        action="store_true",
        help="Fill missing accepted profiles from the existing Exa search audit.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    api_key = os.getenv("EXA_API_KEY")
    if not api_key and not args.from_search_cache:
        print("EXA_API_KEY is required and must be supplied through the environment.", file=sys.stderr)
        return 2
    if args.limit is not None and args.limit < 1:
        raise SystemExit("--limit must be at least 1")
    if not 1 <= args.batch_size <= 100:
        raise SystemExit("--batch-size must be between 1 and 100")
    if args.max_characters < 1000:
        raise SystemExit("--max-characters must be at least 1000")

    people = load_people(args.input)
    all_profiles = select_profiles(people)
    selected = select_profiles(
        people,
        person_ids=set(args.person_id),
        names=set(args.name),
        limit=args.limit,
    )
    if not selected:
        print("No accepted LinkedIn profiles matched the requested selection.", file=sys.stderr)
        return 1

    existing_profiles, requests_log = load_existing(args.output_json)
    accepted_person_ids = {row["person_id"] for row in all_profiles}
    existing_profiles = [
        row
        for row in existing_profiles
        if clean_text(row.get("person_id")) in accepted_person_ids
    ]
    by_person = {clean_text(row.get("person_id")): row for row in existing_profiles}
    accepted_by_person = {row["person_id"]: row for row in all_profiles}
    for profile in load_manual_profiles(args.manual_profiles):
        person_id = clean_text(profile.get("person_id"))
        accepted = accepted_by_person.get(person_id)
        if not accepted:
            continue
        if canonical_url(clean_text(profile.get("linkedin_url"))) != canonical_url(
            accepted["linkedin_url"]
        ):
            raise SystemExit(
                f"Manual public profile URL disagrees with accepted LinkedIn URL for {person_id}"
            )
        previous = by_person.get(person_id)
        if previous is None or clean_text(previous.get("status")) in {
            "error",
            MANUAL_PROFILE_STATUS,
        }:
            by_person[person_id] = profile

    if args.from_search_cache:
        searches_payload = json.loads(args.search_audit.read_text(encoding="utf-8"))
        searches = [
            row for row in searches_payload.get("searches", []) if isinstance(row, dict)
        ]
        cache_selected = [
            person
            for person in selected
            if args.refresh
            or by_person.get(person["person_id"], {}).get("status") in {None, "error"}
        ]
        cached_profiles = cached_profiles_from_search(cache_selected, searches)
        for profile in cached_profiles:
            by_person[clean_text(profile.get("person_id"))] = profile
        write_outputs(
            list(by_person.values()),
            requests_log,
            args.output_json,
            args.output_csv,
            args.input,
            len(people),
            len(all_profiles),
        )
        print(
            json.dumps(
                {
                    "accepted_linkedin_profiles": len(all_profiles),
                    "selected": len(selected),
                    "cached_profiles_added": len(cached_profiles),
                    "output_json": str(args.output_json),
                    "output_csv": str(args.output_csv),
                },
                indent=2,
            )
        )
        return 0

    pending = []
    for person in selected:
        previous = by_person.get(person["person_id"])
        if args.refresh or previous is None or previous.get("status") == "search_cache" or (
            args.retry_errors and previous.get("status") == "error"
        ):
            pending.append(person)

    client = ExaContentsClient(api_key)
    for index in range(0, len(pending), args.batch_size):
        batch = pending[index : index + args.batch_size]
        retrieved_at = utc_now()
        try:
            response = client.retrieve(
                [row["linkedin_url"] for row in batch], args.max_characters
            )
            profiles, request = normalize_batch(batch, response, retrieved_at)
        except (requests.RequestException, ValueError) as exc:
            profiles = [
                {
                    **person,
                    "status": "error",
                    "error": clean_text(exc),
                    "request_id": "",
                    "retrieved_at": retrieved_at,
                    "title": "",
                    "resolved_url": "",
                    "content_characters": 0,
                    "source_endpoint": EXA_CONTENTS_URL,
                    "text": "",
                }
                for person in batch
            ]
            request = {
                "request_id": "",
                "retrieved_at": retrieved_at,
                "requested_profile_count": len(batch),
                "cost_usd": 0.0,
                "error": clean_text(exc),
            }
        for profile in profiles:
            by_person[clean_text(profile.get("person_id"))] = profile
        requests_log.append(request)
        write_outputs(
            list(by_person.values()),
            requests_log,
            args.output_json,
            args.output_csv,
            args.input,
            len(people),
            len(all_profiles),
        )
        print(
            f"retrieved batch {index // args.batch_size + 1}: "
            f"{sum(row['status'] == 'success' for row in profiles)}/{len(batch)} successful",
            file=sys.stderr,
        )
        if args.delay > 0 and index + args.batch_size < len(pending):
            time.sleep(args.delay)

    write_outputs(
        list(by_person.values()),
        requests_log,
        args.output_json,
        args.output_csv,
        args.input,
        len(people),
        len(all_profiles),
    )
    final_profiles = list(by_person.values())
    print(
        json.dumps(
            {
                "accepted_linkedin_profiles": len(all_profiles),
                "selected": len(selected),
                "retrieved_this_run": len(pending),
                "successful_profiles": sum(row.get("status") == "success" for row in final_profiles),
                "error_profiles": sum(row.get("status") == "error" for row in final_profiles),
                "output_json": str(args.output_json),
                "output_csv": str(args.output_csv),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
