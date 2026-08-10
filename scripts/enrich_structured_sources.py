#!/usr/bin/env python3
"""Enrich olympiad alumni from structured public professional sources.

The output is deliberately candidate-oriented. A name-only match is retained as
``candidate`` but is not suitable for visualization until another independent
signal raises it to ``probable`` or ``confirmed``.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, replace
from difflib import SequenceMatcher
from io import StringIO
from pathlib import Path
from typing import Iterable
from urllib.parse import quote, unquote, urljoin

import requests
from bs4 import BeautifulSoup


DEFAULT_TIMEOUT_SECONDS = 60
USER_AGENT = "iso-futures/0.2 (public olympiad alumni research)"
KAZAKHSTAN_TERMS = {
    "kazakhstan",
    "kazakh",
    "almaty",
    "astana",
    "nur sultan",
    "nursultan",
    "karaganda",
    "shymkent",
    "kz",
    "nazarbayev university",
    "eurasian national university",
    "al farabi",
    "kbtU".casefold(),
}
OLYMPIAD_TERMS = {
    "olympiad",
    "imo",
    "ioi",
    "ipho",
    "ibo",
    "icho",
    "international mathematical olympiad",
    "international olympiad in informatics",
    "international physics olympiad",
    "international biology olympiad",
    "international chemistry olympiad",
}
FIELD_TERMS = {
    "IMO": {"mathematics", "statistics", "computer science", "economics", "engineering"},
    "IOI": {"computer science", "software", "artificial intelligence", "engineering", "mathematics"},
    "IPhO": {"physics", "astronomy", "engineering", "materials science", "optics", "photonics"},
    "IBO": {"biology", "biochemistry", "medicine", "neuroscience", "genetics", "agriculture"},
    "IChO": {"chemistry", "materials science", "chemical engineering", "medicine", "pharmacy"},
}


@dataclass(frozen=True)
class PersonSeed:
    person_id: str
    canonical_name: str
    aliases: tuple[str, ...]
    olympiads: tuple[str, ...]
    years: tuple[int, ...]
    first_year: int
    last_year: int
    research_scope: str


@dataclass(frozen=True)
class IdentityCandidate:
    person_id: str
    canonical_name: str
    aliases: str
    olympiads: str
    first_year: int
    source: str
    source_id: str
    profile_url: str
    matched_name: str
    score: float
    confidence: str
    score_reasons: str
    location: str
    organization: str
    role: str
    evidence_text: str
    evidence_url: str
    outbound_urls: str


@dataclass(frozen=True)
class AffiliationCandidate:
    person_id: str
    canonical_name: str
    organization: str
    role: str
    department: str
    affiliation_type: str
    start_year: str
    end_year: str
    country_code: str
    source: str
    evidence_url: str
    confidence: str
    evidence_text: str


class RateLimitExhausted(RuntimeError):
    def __init__(self, source: str, retry_after: str):
        super().__init__(f"{source} rate limit exhausted; retry after {retry_after} seconds")
        self.source = source
        self.retry_after = retry_after


def clean_text(value: object) -> str:
    text = "" if value is None else str(value)
    return re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()


def normalize_text(value: str) -> str:
    value = value.casefold()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def token_key(value: str) -> str:
    return " ".join(sorted(normalize_text(value).split()))


def stable_cache_name(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:20] + ".json"


def load_people(path: Path, scopes: set[str]) -> list[PersonSeed]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    people: list[PersonSeed] = []
    for row in rows:
        if scopes and row["research_scope"] not in scopes:
            continue
        people.append(
            PersonSeed(
                person_id=row["person_id"],
                canonical_name=row["canonical_name"],
                aliases=tuple(item for item in row["aliases"].split(";") if item),
                olympiads=tuple(item for item in row["olympiads"].split(";") if item),
                years=tuple(int(item) for item in row["years"].split(";") if item),
                first_year=int(row["first_year"]),
                last_year=int(row["last_year"]),
                research_scope=row["research_scope"],
            )
        )
    return people


def fetch_json(
    url: str,
    cache_path: Path,
    *,
    params: dict[str, object] | None = None,
    headers: dict[str, str] | None = None,
    refresh: bool = False,
) -> object:
    if cache_path.exists() and not refresh:
        return json.loads(cache_path.read_text(encoding="utf-8"))
    response = requests.get(
        url,
        params=params,
        headers={"User-Agent": USER_AGENT, **(headers or {})},
        timeout=DEFAULT_TIMEOUT_SECONDS,
    )
    if response.status_code == 429:
        raise RateLimitExhausted(url, response.headers.get("retry-after", "unknown"))
    response.raise_for_status()
    data = response.json()
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data


def fetch_text(
    url: str,
    cache_path: Path,
    *,
    params: dict[str, object] | None = None,
    headers: dict[str, str] | None = None,
    refresh: bool = False,
) -> str:
    if cache_path.exists() and not refresh:
        return cache_path.read_text(encoding="utf-8", errors="replace")
    response = requests.get(
        url,
        params=params,
        headers={"User-Agent": USER_AGENT, **(headers or {})},
        timeout=DEFAULT_TIMEOUT_SECONDS,
    )
    if response.status_code == 429:
        raise RateLimitExhausted(url, response.headers.get("retry-after", "unknown"))
    response.raise_for_status()
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(response.text, encoding="utf-8")
    return response.text


def name_match_score(person: PersonSeed, candidate_name: str) -> tuple[float, str]:
    candidate_normalized = normalize_text(candidate_name)
    candidate_tokens = token_key(candidate_name)
    aliases = [normalize_text(alias) for alias in person.aliases]
    alias_tokens = [token_key(alias) for alias in person.aliases]
    if candidate_normalized in aliases:
        return 0.5, "exact_name"
    if candidate_tokens and candidate_tokens in alias_tokens:
        return 0.48, "name_tokens_reordered"
    best = max(
        (SequenceMatcher(None, candidate_tokens, alias).ratio() for alias in alias_tokens),
        default=0.0,
    )
    if best >= 0.94:
        return 0.4, "near_exact_name"
    if best >= 0.88:
        return 0.32, "similar_name"
    return 0.0, ""


def context_contains(text: str, terms: Iterable[str]) -> bool:
    normalized = normalize_text(text)
    padded = f" {normalized} "
    for term in terms:
        normalized_term = normalize_text(term)
        if not normalized_term:
            continue
        if " " not in normalized_term and len(normalized_term) <= 4:
            if f" {normalized_term} " in padded:
                return True
        elif normalized_term in normalized:
            return True
    return False


def confidence_for(score: float, reasons: list[str]) -> str:
    reason_set = set(reasons)
    if "timeline_conflict" in reason_set and "direct_olympiad_evidence" not in reason_set:
        return "candidate"
    if reason_set & {"ambiguous_same_name_source", "wikidata_name_only"} and not any(
        reason in reasons
        for reason in {
            "cross_source_handle",
            "cross_source_organization",
            "linked_profile",
            "direct_olympiad_evidence",
        }
    ):
        return "candidate"
    if "direct_olympiad_evidence" in reason_set:
        return "confirmed"
    if (
        reason_set & {"exact_name", "name_tokens_reordered", "near_exact_name"}
        and "kazakhstan_context" in reason_set
        and reason_set & {"cross_source_handle", "cross_source_organization", "linked_profile"}
    ):
        return "confirmed"
    if score >= 0.65 and any(
        reason in reasons
        for reason in {
            "kazakhstan_context",
            "field_alignment",
            "cross_source_handle",
            "self_asserted_orcid_affiliation",
        }
    ):
        return "probable"
    return "candidate"


def identity(
    person: PersonSeed,
    *,
    source: str,
    source_id: str,
    profile_url: str,
    matched_name: str,
    score: float,
    reasons: list[str],
    location: str = "",
    organization: str = "",
    role: str = "",
    evidence_text: str = "",
    evidence_url: str = "",
    outbound_urls: Iterable[str] = (),
) -> IdentityCandidate:
    score = round(min(score, 1.0), 3)
    return IdentityCandidate(
        person_id=person.person_id,
        canonical_name=person.canonical_name,
        aliases=";".join(person.aliases),
        olympiads=";".join(person.olympiads),
        first_year=person.first_year,
        source=source,
        source_id=source_id,
        profile_url=profile_url,
        matched_name=matched_name,
        score=score,
        confidence=confidence_for(score, reasons),
        score_reasons=";".join(dict.fromkeys(reasons)),
        location=location,
        organization=organization,
        role=role,
        evidence_text=clean_text(evidence_text),
        evidence_url=evidence_url or profile_url,
        outbound_urls=";".join(sorted({url for url in outbound_urls if url})),
    )


def codeforces_enrich(
    people: list[PersonSeed], cache_dir: Path, refresh: bool
) -> tuple[list[IdentityCandidate], list[AffiliationCandidate], dict[str, object]]:
    cache_path = cache_dir / "codeforces" / "rated_users.json"
    payload = fetch_json(
        "https://codeforces.com/api/user.ratedList",
        cache_path,
        params={"activeOnly": "false", "includeRetired": "true"},
        refresh=refresh,
    )
    if not isinstance(payload, dict) or payload.get("status") != "OK":
        raise RuntimeError(f"Codeforces API failed: {payload}")
    users = payload.get("result", [])
    by_name: dict[str, list[dict[str, object]]] = {}
    for user in users:
        full_name = clean_text(" ".join(filter(None, [user.get("firstName"), user.get("lastName")])))
        if not full_name:
            continue
        by_name.setdefault(token_key(full_name), []).append(user)

    identities: list[IdentityCandidate] = []
    affiliations: list[AffiliationCandidate] = []
    matched_people: set[str] = set()
    for person in people:
        seen_handles: set[str] = set()
        for alias in person.aliases:
            for user in by_name.get(token_key(alias), []):
                handle = clean_text(user.get("handle"))
                if not handle or handle in seen_handles:
                    continue
                seen_handles.add(handle)
                full_name = clean_text(" ".join(filter(None, [user.get("firstName"), user.get("lastName")])))
                name_score, name_reason = name_match_score(person, full_name)
                if name_score < 0.4:
                    continue
                reasons = [name_reason]
                score = name_score
                country = clean_text(user.get("country"))
                city = clean_text(user.get("city"))
                organization = clean_text(user.get("organization"))
                context = " ".join([country, city, organization])
                if country.casefold() == "kazakhstan" or context_contains(context, KAZAKHSTAN_TERMS):
                    score += 0.22
                    reasons.append("kazakhstan_context")
                if organization:
                    score += 0.03
                    reasons.append("organization_present")
                profile_url = f"https://codeforces.com/profile/{quote(handle)}"
                evidence = "; ".join(
                    item
                    for item in [
                        f"handle={handle}",
                        f"country={country}" if country else "",
                        f"city={city}" if city else "",
                        f"organization={organization}" if organization else "",
                    ]
                    if item
                )
                candidate = identity(
                    person,
                    source="codeforces",
                    source_id=handle,
                    profile_url=profile_url,
                    matched_name=full_name,
                    score=score,
                    reasons=reasons,
                    location="; ".join(item for item in [city, country] if item),
                    organization=organization,
                    evidence_text=evidence,
                )
                identities.append(candidate)
                matched_people.add(person.person_id)
                if organization:
                    affiliations.append(
                        AffiliationCandidate(
                            person_id=person.person_id,
                            canonical_name=person.canonical_name,
                            organization=organization,
                            role="",
                            department="",
                            affiliation_type="organization",
                            start_year="",
                            end_year="",
                            country_code="KZ" if country.casefold() == "kazakhstan" else "",
                            source="codeforces",
                            evidence_url=profile_url,
                            confidence=candidate.confidence,
                            evidence_text=evidence,
                        )
                    )
    return identities, affiliations, {
        "rated_users": len(users),
        "named_users": sum(len(items) for items in by_name.values()),
        "matched_people": len(matched_people),
        "identity_candidates": len(identities),
    }


def cphof_codeforces_user(
    handle: str, cache_dir: Path, refresh: bool
) -> dict[str, object] | None:
    cache_path = cache_dir / "cphof" / "codeforces" / stable_cache_name(handle)
    payload = fetch_json(
        "https://codeforces.com/api/user.info",
        cache_path,
        params={"handles": handle},
        refresh=refresh,
    )
    if not isinstance(payload, dict) or payload.get("status") != "OK":
        return None
    results = payload.get("result") or []
    return results[0] if results and isinstance(results[0], dict) else None


def cphof_enrich(
    people: list[PersonSeed], cache_dir: Path, refresh: bool, sleep_seconds: float
) -> tuple[list[IdentityCandidate], list[AffiliationCandidate], dict[str, object]]:
    identities: list[IdentityCandidate] = []
    affiliations: list[AffiliationCandidate] = []
    matched_people: set[str] = set()
    errors: list[str] = []
    profile_pages = 0
    alias_searches = 0

    for index, person in enumerate(people, start=1):
        if "IOI" not in person.olympiads:
            continue
        profiles: dict[str, str] = {}
        for alias in person.aliases:
            alias_searches += 1
            cache_path = cache_dir / "cphof" / "search" / stable_cache_name(alias).replace(
                ".json", ".html"
            )
            try:
                html = fetch_text(
                    "https://cphof.org/search",
                    cache_path,
                    params={"query": alias},
                    refresh=refresh,
                )
            except Exception as exc:
                errors.append(f"search {alias}: {exc}")
                continue
            soup = BeautifulSoup(html, "html.parser")
            content = soup.select_one("#content-wrapper") or soup
            for anchor in content.select('a[href^="/profile/"]'):
                href = clean_text(anchor.get("href"))
                matched_name = clean_text(anchor.get_text(" ", strip=True))
                name_score, _ = name_match_score(person, matched_name)
                if href and name_score >= 0.32:
                    profiles[href] = matched_name
            if sleep_seconds > 0:
                time.sleep(sleep_seconds)

        for href, search_name in profiles.items():
            profile_id = unquote(href.split("/profile/", 1)[-1])
            profile_url = urljoin("https://cphof.org", href)
            cache_path = cache_dir / "cphof" / "profiles" / stable_cache_name(profile_id).replace(
                ".json", ".html"
            )
            try:
                html = fetch_text(profile_url, cache_path, refresh=refresh)
            except Exception as exc:
                errors.append(f"profile {profile_id}: {exc}")
                continue
            profile_pages += 1
            soup = BeautifulSoup(html, "html.parser")
            content = soup.select_one("#content-wrapper") or soup
            heading = content.find("h3")
            matched_name = clean_text(heading.get_text(" ", strip=True) if heading else search_name)
            name_score, name_reason = name_match_score(person, matched_name)
            if name_score < 0.32:
                continue

            country_kz = content.select_one('a[href="/country/KAZ"]') is not None
            has_ioi = bool(
                content.select_one('a[href="/contest/ioi"]')
                or content.select_one('a[href*="stats.ioinformatics.org/people/"]')
            )
            if not has_ioi:
                continue

            external_urls = list(
                dict.fromkeys(
                    clean_text(anchor.get("href"))
                    for anchor in content.select('a[href^="http"]')
                    if clean_text(anchor.get("href"))
                )
            )
            codeforces_urls = [
                url for url in external_urls if "codeforces.com/profile/" in url.casefold()
            ]
            handles = [unquote(url.rstrip("/").split("/")[-1]) for url in codeforces_urls]
            universities = list(
                dict.fromkeys(
                    clean_text(anchor.get_text(" ", strip=True))
                    for anchor in content.select('a[href^="/university/"]')
                    if clean_text(anchor.get_text(" ", strip=True))
                )
            )

            codeforces_user: dict[str, object] | None = None
            for handle in handles:
                try:
                    codeforces_user = cphof_codeforces_user(handle, cache_dir, refresh)
                except Exception as exc:
                    errors.append(f"Codeforces {handle}: {exc}")
                if codeforces_user:
                    break
            organization = clean_text(
                (codeforces_user or {}).get("organization")
            ) or next(iter(universities), "")
            cf_country = clean_text((codeforces_user or {}).get("country"))
            cf_city = clean_text((codeforces_user or {}).get("city"))
            location = "; ".join(
                item for item in [cf_city, cf_country or ("Kazakhstan" if country_kz else "")] if item
            )

            reasons = [name_reason]
            score = name_score
            if country_kz or cf_country.casefold() == "kazakhstan":
                score += 0.22
                reasons.append("kazakhstan_context")
            if has_ioi and (country_kz or cf_country.casefold() == "kazakhstan"):
                score += 0.32
                reasons.append("direct_olympiad_evidence")
            if external_urls:
                score += 0.03
                reasons.append("outbound_profile_links")
            evidence = "; ".join(
                item
                for item in [
                    f"profile={profile_id}",
                    "country=Kazakhstan" if country_kz else "",
                    "contest=IOI",
                    f"codeforces={', '.join(handles)}" if handles else "",
                    f"universities={', '.join(universities)}" if universities else "",
                    f"organization={organization}" if organization else "",
                ]
                if item
            )
            candidate = identity(
                person,
                source="cphof",
                source_id=profile_id,
                profile_url=profile_url,
                matched_name=matched_name,
                score=score,
                reasons=reasons,
                location=location,
                organization=organization,
                evidence_text=evidence,
                outbound_urls=external_urls,
            )
            identities.append(candidate)
            matched_people.add(person.person_id)

            if organization and codeforces_user:
                affiliations.append(
                    AffiliationCandidate(
                        person_id=person.person_id,
                        canonical_name=person.canonical_name,
                        organization=organization,
                        role="",
                        department="",
                        affiliation_type="organization",
                        start_year="",
                        end_year="",
                        country_code="KZ" if cf_country.casefold() == "kazakhstan" else "",
                        source="cphof_codeforces",
                        evidence_url=next(iter(codeforces_urls), profile_url),
                        confidence=candidate.confidence,
                        evidence_text=evidence,
                    )
                )
            for university in universities:
                affiliations.append(
                    AffiliationCandidate(
                        person_id=person.person_id,
                        canonical_name=person.canonical_name,
                        organization=university,
                        role="",
                        department="",
                        affiliation_type="education",
                        start_year="",
                        end_year="",
                        country_code="",
                        source="cphof",
                        evidence_url=profile_url,
                        confidence=candidate.confidence,
                        evidence_text=evidence,
                    )
                )
            if sleep_seconds > 0:
                time.sleep(sleep_seconds)

        if index % 50 == 0:
            print(f"CPHOF checked {index}/{len(people)} people", file=sys.stderr)

    return identities, affiliations, {
        "people_searched": sum(1 for person in people if "IOI" in person.olympiads),
        "alias_searches": alias_searches,
        "profile_pages": profile_pages,
        "matched_people": len(matched_people),
        "identity_candidates": len(identities),
        "errors": errors,
    }


GITHUB_NODE_FIELDS = """
nodes {
  ... on User {
    login
    name
    company
    location
    bio
    websiteUrl
    url
    createdAt
    socialAccounts(first: 10) { nodes { provider url } }
  }
}
"""


def github_graphql(query: str, cache_path: Path, refresh: bool) -> dict[str, object]:
    if cache_path.exists() and not refresh:
        return json.loads(cache_path.read_text(encoding="utf-8"))
    process = subprocess.run(
        ["gh", "api", "graphql", "-f", f"query={query}"],
        check=False,
        capture_output=True,
        text=True,
        timeout=DEFAULT_TIMEOUT_SECONDS,
    )
    if process.returncode != 0:
        raise RuntimeError(process.stderr.strip() or process.stdout.strip())
    data = json.loads(process.stdout)
    if data.get("errors"):
        raise RuntimeError(json.dumps(data["errors"], ensure_ascii=False))
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data


def github_enrich(
    people: list[PersonSeed], cache_dir: Path, refresh: bool, batch_size: int
) -> tuple[list[IdentityCandidate], list[AffiliationCandidate], dict[str, object]]:
    search_items: list[tuple[PersonSeed, str]] = [
        (person, alias) for person in people for alias in person.aliases
    ]
    raw_results: dict[str, list[dict[str, object]]] = {person.person_id: [] for person in people}
    errors: list[str] = []
    for batch_index in range(0, len(search_items), batch_size):
        batch = search_items[batch_index : batch_index + batch_size]
        fields: list[str] = []
        field_map: dict[str, str] = {}
        for offset, (person, alias) in enumerate(batch):
            field = f"q{offset}"
            search_query = f'"{alias}" in:fullname'
            fields.append(
                f"{field}: search(query: {json.dumps(search_query)}, type: USER, first: 5) "
                + "{ " + GITHUB_NODE_FIELDS + " }"
            )
            field_map[field] = person.person_id
        query = "query {\n" + "\n".join(fields) + "\n}"
        cache_path = cache_dir / "github" / stable_cache_name(query)
        try:
            payload = github_graphql(query, cache_path, refresh)
            for field, result in payload.get("data", {}).items():
                person_id = field_map[field]
                raw_results[person_id].extend(result.get("nodes", []))
        except Exception as exc:
            errors.append(f"batch {batch_index // batch_size}: {exc}")
        if batch_index and batch_index % (batch_size * 5) == 0:
            print(f"GitHub searched {min(batch_index + batch_size, len(search_items))} aliases", file=sys.stderr)
        time.sleep(0.25)

    people_by_id = {person.person_id: person for person in people}
    identities: list[IdentityCandidate] = []
    affiliations: list[AffiliationCandidate] = []
    matched_people: set[str] = set()
    for person_id, nodes in raw_results.items():
        person = people_by_id[person_id]
        seen_logins: set[str] = set()
        for node in nodes:
            login = clean_text(node.get("login"))
            if not login or login in seen_logins:
                continue
            seen_logins.add(login)
            matched_name = clean_text(node.get("name"))
            name_score, name_reason = name_match_score(person, matched_name)
            if name_score < 0.4:
                continue
            company = clean_text(node.get("company"))
            location = clean_text(node.get("location"))
            bio = clean_text(node.get("bio"))
            website = clean_text(node.get("websiteUrl"))
            social_urls = [
                clean_text(item.get("url"))
                for item in node.get("socialAccounts", {}).get("nodes", [])
                if clean_text(item.get("url"))
            ]
            reasons = [name_reason]
            score = name_score
            context = " ".join([company, location, bio, website])
            if context_contains(context, KAZAKHSTAN_TERMS):
                score += 0.22
                reasons.append("kazakhstan_context")
            if context_contains(context, OLYMPIAD_TERMS):
                score += 0.32
                reasons.append("direct_olympiad_evidence")
            if website or social_urls:
                score += 0.03
                reasons.append("outbound_profile_links")
            profile_url = clean_text(node.get("url")) or f"https://github.com/{quote(login)}"
            evidence = "; ".join(
                item
                for item in [
                    f"login={login}",
                    f"company={company}" if company else "",
                    f"location={location}" if location else "",
                    f"bio={bio}" if bio else "",
                    f"website={website}" if website else "",
                ]
                if item
            )
            candidate = identity(
                person,
                source="github",
                source_id=login,
                profile_url=profile_url,
                matched_name=matched_name,
                score=score,
                reasons=reasons,
                location=location,
                organization=company,
                role=bio,
                evidence_text=evidence,
                outbound_urls=[website, *social_urls],
            )
            identities.append(candidate)
            matched_people.add(person_id)
            if company:
                affiliations.append(
                    AffiliationCandidate(
                        person_id=person_id,
                        canonical_name=person.canonical_name,
                        organization=company,
                        role=bio,
                        department="",
                        affiliation_type="company_or_organization",
                        start_year="",
                        end_year="",
                        country_code="KZ" if context_contains(location, KAZAKHSTAN_TERMS) else "",
                        source="github",
                        evidence_url=profile_url,
                        confidence=candidate.confidence,
                        evidence_text=evidence,
                    )
                )
    return identities, affiliations, {
        "aliases_searched": len(search_items),
        "matched_people": len(matched_people),
        "identity_candidates": len(identities),
        "errors": errors,
    }


def field_alignment(person: PersonSeed, author: dict[str, object]) -> bool:
    expected = set().union(*(FIELD_TERMS.get(olympiad, set()) for olympiad in person.olympiads))
    topic_text: list[str] = []
    for topic in author.get("topics") or []:
        topic_text.append(clean_text(topic.get("display_name")))
        for level in ["subfield", "field", "domain"]:
            topic_text.append(clean_text((topic.get(level) or {}).get("display_name")))
    normalized = normalize_text(" ".join(topic_text))
    return any(normalize_text(term) in normalized for term in expected)


def orcid_affiliation_rows(
    person: PersonSeed,
    record: dict[str, object],
    confidence: str,
    orcid_url: str,
    source: str = "orcid",
) -> list[AffiliationCandidate]:
    rows: list[AffiliationCandidate] = []
    activities = record.get("activities-summary") or {}
    sections = [
        ("educations", "education-summary", "education"),
        ("employments", "employment-summary", "employment"),
        ("qualifications", "qualification-summary", "qualification"),
        ("distinctions", "distinction-summary", "distinction"),
    ]
    for section_name, summary_name, affiliation_type in sections:
        section = activities.get(section_name) or {}
        for group in section.get("affiliation-group") or []:
            for item in group.get("summaries") or []:
                summary = item.get(summary_name) or {}
                organization = clean_text((summary.get("organization") or {}).get("name"))
                if not organization:
                    continue
                address = (summary.get("organization") or {}).get("address") or {}
                start_year = clean_text(((summary.get("start-date") or {}).get("year") or {}).get("value"))
                end_year = clean_text(((summary.get("end-date") or {}).get("year") or {}).get("value"))
                role = clean_text(summary.get("role-title"))
                department = clean_text(summary.get("department-name"))
                evidence = "; ".join(
                    item
                    for item in [organization, role, department, start_year, end_year]
                    if item
                )
                rows.append(
                    AffiliationCandidate(
                        person_id=person.person_id,
                        canonical_name=person.canonical_name,
                        organization=organization,
                        role=role,
                        department=department,
                        affiliation_type=affiliation_type,
                        start_year=start_year,
                        end_year=end_year,
                        country_code=clean_text(address.get("country")),
                        source=source,
                        evidence_url=orcid_url,
                        confidence=confidence,
                        evidence_text=evidence,
                    )
                )
    return rows


def orcid_signals(record: dict[str, object]) -> tuple[list[str], list[str], str, str]:
    reasons: list[str] = []
    outbound_urls: list[str] = []
    person = record.get("person") or {}
    for item in ((person.get("researcher-urls") or {}).get("researcher-url") or []):
        url = clean_text((item.get("url") or {}).get("value"))
        if url:
            outbound_urls.append(url)
    record_text = json.dumps(record, ensure_ascii=False)
    if context_contains(record_text, KAZAKHSTAN_TERMS):
        reasons.append("kazakhstan_context")
    if context_contains(record_text, OLYMPIAD_TERMS):
        reasons.append("direct_olympiad_evidence")
    affiliations: list[tuple[str, str, str]] = []
    activities = record.get("activities-summary") or {}
    for section_name, summary_name in [
        ("employments", "employment-summary"),
        ("educations", "education-summary"),
    ]:
        for group in (activities.get(section_name) or {}).get("affiliation-group") or []:
            for item in group.get("summaries") or []:
                summary = item.get(summary_name) or {}
                org = clean_text((summary.get("organization") or {}).get("name"))
                role = clean_text(summary.get("role-title"))
                year = clean_text(((summary.get("start-date") or {}).get("year") or {}).get("value"))
                if org:
                    affiliations.append((year, org, role))
    latest = max(affiliations, key=lambda item: item[0] or "0000", default=("", "", ""))
    return reasons, outbound_urls, latest[1], latest[2]


def orcid_affiliation_years(record: dict[str, object]) -> list[int]:
    years: list[int] = []
    activities = record.get("activities-summary") or {}
    for section_name, summary_name in [
        ("employments", "employment-summary"),
        ("educations", "education-summary"),
        ("qualifications", "qualification-summary"),
        ("distinctions", "distinction-summary"),
    ]:
        for group in (activities.get(section_name) or {}).get("affiliation-group") or []:
            for item in group.get("summaries") or []:
                summary = item.get(summary_name) or {}
                for date_name in ["start-date", "end-date"]:
                    value = clean_text(((summary.get(date_name) or {}).get("year") or {}).get("value"))
                    if value.isdigit():
                        years.append(int(value))
    return years


def orcid_field_alignment(person: PersonSeed, record: dict[str, object]) -> bool:
    expected = set().union(*(FIELD_TERMS.get(olympiad, set()) for olympiad in person.olympiads))
    activities = record.get("activities-summary") or {}
    fragments: list[str] = []
    for group in (activities.get("works") or {}).get("group") or []:
        for summary in group.get("work-summary") or []:
            fragments.append(
                clean_text((((summary.get("title") or {}).get("title") or {}).get("value")))
            )
            fragments.append(clean_text((summary.get("journal-title") or {}).get("value")))
    normalized = normalize_text(" ".join(fragments))
    return any(normalize_text(term) in normalized for term in expected)


def orcid_search_enrich(
    people: list[PersonSeed], cache_dir: Path, refresh: bool, sleep_seconds: float
) -> tuple[list[IdentityCandidate], list[AffiliationCandidate], dict[str, object]]:
    identities: list[IdentityCandidate] = []
    affiliations: list[AffiliationCandidate] = []
    matched_people: set[str] = set()
    errors: list[str] = []
    records_read: set[str] = set()
    searches = 0
    for index, person in enumerate(people, start=1):
        found_rows: dict[str, dict[str, str]] = {}
        for alias in person.aliases:
            searches += 1
            query = f'given-and-family-names:"{alias}"'
            cache_path = cache_dir / "orcid_search" / stable_cache_name(query).replace(".json", ".csv")
            try:
                text = fetch_text(
                    "https://pub.orcid.org/v3.0/csv-search/",
                    cache_path,
                    params={
                        "q": query,
                        "fl": (
                            "orcid,given-names,family-name,"
                            "current-institution-affiliation-name,"
                            "past-institution-affiliation-name"
                        ),
                    },
                    headers={"Accept": "text/csv"},
                    refresh=refresh,
                )
                for row in csv.DictReader(StringIO(text)):
                    orcid_id = clean_text(row.get("orcid"))
                    if orcid_id:
                        found_rows[orcid_id] = row
            except Exception as exc:
                errors.append(f"{person.canonical_name}: {exc}")
            if sleep_seconds > 0:
                time.sleep(sleep_seconds)

        for orcid_id, search_row in found_rows.items():
            matched_name = clean_text(
                " ".join(
                    filter(
                        None,
                        [search_row.get("given-names"), search_row.get("family-name")],
                    )
                )
            )
            name_score, name_reason = name_match_score(person, matched_name)
            if name_score < 0.4:
                continue
            orcid_url = f"https://orcid.org/{orcid_id}"
            record_cache = cache_dir / "orcid" / f"{orcid_id}.json"
            try:
                record = fetch_json(
                    f"https://pub.orcid.org/v3.0/{orcid_id}/record",
                    record_cache,
                    headers={"Accept": "application/json"},
                    refresh=refresh,
                )
            except Exception as exc:
                errors.append(f"ORCID {orcid_id}: {exc}")
                continue
            if not isinstance(record, dict):
                continue
            records_read.add(orcid_id)
            reasons = [name_reason, "self_asserted_orcid_affiliation"]
            score = name_score + 0.07
            signal_reasons, outbound_urls, organization, role = orcid_signals(record)
            if "kazakhstan_context" in signal_reasons:
                score += 0.2
                reasons.append("kazakhstan_context")
            if "direct_olympiad_evidence" in signal_reasons:
                score += 0.3
                reasons.append("direct_olympiad_evidence")
            if orcid_field_alignment(person, record):
                score += 0.1
                reasons.append("field_alignment")
            years = orcid_affiliation_years(record)
            if years and min(years) < person.first_year - 4:
                score -= 0.4
                reasons.append("timeline_conflict")
            elif years and max(years) >= person.first_year + 1:
                score += 0.03
                reasons.append("plausible_timeline")
            current_affiliation = clean_text(
                search_row.get("current-institution-affiliation-name")
            )
            past_affiliation = clean_text(search_row.get("past-institution-affiliation-name"))
            organization = organization or current_affiliation
            evidence = "; ".join(
                item
                for item in [
                    f"orcid={orcid_id}",
                    f"current_affiliation={current_affiliation}" if current_affiliation else "",
                    f"past_affiliation={past_affiliation}" if past_affiliation else "",
                    f"role={role}" if role else "",
                ]
                if item
            )
            candidate = identity(
                person,
                source="orcid",
                source_id=orcid_id,
                profile_url=orcid_url,
                matched_name=matched_name,
                score=score,
                reasons=reasons,
                organization=organization,
                role=role,
                evidence_text=evidence,
                outbound_urls=outbound_urls,
            )
            identities.append(candidate)
            matched_people.add(person.person_id)
            affiliations.extend(
                orcid_affiliation_rows(person, record, candidate.confidence, orcid_url)
            )

        if index % 25 == 0:
            print(f"ORCID searched {index}/{len(people)} people", file=sys.stderr)
    return identities, affiliations, {
        "people_searched": len(people),
        "alias_searches": searches,
        "matched_people": len(matched_people),
        "identity_candidates": len(identities),
        "records_read": len(records_read),
        "errors": errors,
    }


WIKIDATA_CONTEXT_PROPERTIES = {
    "P27",  # country of citizenship
    "P31",  # instance of
    "P69",  # educated at
    "P106",  # occupation
    "P108",  # employer
    "P1416",  # affiliation
    "P19",  # place of birth
    "P551",  # residence
    "P1344",  # participant in
}


def batched(values: list[str], size: int) -> Iterable[list[str]]:
    for index in range(0, len(values), size):
        yield values[index : index + size]


def wikidata_get_entities(
    ids: list[str], cache_dir: Path, refresh: bool, *, props: str
) -> dict[str, dict[str, object]]:
    if not ids:
        return {}
    cache_key = f"{props}:" + "|".join(sorted(ids))
    cache_path = cache_dir / "wikidata" / "entities" / stable_cache_name(cache_key)
    payload = fetch_json(
        "https://www.wikidata.org/w/api.php",
        cache_path,
        params={
            "action": "wbgetentities",
            "ids": "|".join(ids),
            "props": props,
            "languages": "en|ru|kk",
            "format": "json",
        },
        refresh=refresh,
    )
    if not isinstance(payload, dict):
        return {}
    return {
        entity_id: entity
        for entity_id, entity in (payload.get("entities") or {}).items()
        if isinstance(entity, dict) and "missing" not in entity
    }


def wikidata_snak_value(snak: dict[str, object]) -> object | None:
    return ((snak.get("datavalue") or {}).get("value"))


def wikidata_claims(entity: dict[str, object], property_id: str) -> list[dict[str, object]]:
    return [
        statement
        for statement in (entity.get("claims") or {}).get(property_id, [])
        if isinstance(statement, dict) and statement.get("rank") != "deprecated"
    ]


def wikidata_item_id(statement: dict[str, object]) -> str:
    value = wikidata_snak_value(statement.get("mainsnak") or {})
    if isinstance(value, dict):
        return clean_text(value.get("id"))
    return ""


def wikidata_string_values(entity: dict[str, object], property_id: str) -> list[str]:
    values: list[str] = []
    for statement in wikidata_claims(entity, property_id):
        value = wikidata_snak_value(statement.get("mainsnak") or {})
        if isinstance(value, str) and clean_text(value):
            values.append(clean_text(value))
    return list(dict.fromkeys(values))


def wikidata_time_year(snak: dict[str, object]) -> int | None:
    value = wikidata_snak_value(snak)
    if not isinstance(value, dict):
        return None
    match = re.match(r"^[+-](\d{4,})-", clean_text(value.get("time")))
    if not match:
        return None
    year = int(match.group(1))
    return year if 0 < year < 3000 else None


def wikidata_qualifier_year(statement: dict[str, object], property_id: str) -> str:
    qualifiers = (statement.get("qualifiers") or {}).get(property_id, [])
    years = [wikidata_time_year(snak) for snak in qualifiers if isinstance(snak, dict)]
    valid = [year for year in years if year is not None]
    return str(min(valid)) if valid else ""


def wikidata_claim_rows(
    entity: dict[str, object], property_id: str
) -> list[tuple[str, str, str]]:
    rows: list[tuple[str, str, str]] = []
    for statement in wikidata_claims(entity, property_id):
        item_id = wikidata_item_id(statement)
        if item_id:
            rows.append(
                (
                    item_id,
                    wikidata_qualifier_year(statement, "P580"),
                    wikidata_qualifier_year(statement, "P582"),
                )
            )
    return rows


def wikidata_label(entity: dict[str, object], fallback: str = "") -> str:
    labels = entity.get("labels") or {}
    for language in ("en", "ru", "kk"):
        value = clean_text((labels.get(language) or {}).get("value"))
        if value:
            return value
    return fallback


def wikidata_description(entity: dict[str, object]) -> str:
    descriptions = entity.get("descriptions") or {}
    for language in ("en", "ru", "kk"):
        value = clean_text((descriptions.get(language) or {}).get("value"))
        if value:
            return value
    return ""


def wikidata_preferred_claim(
    rows: list[tuple[str, str, str]], labels: dict[str, str]
) -> tuple[str, str, str]:
    if not rows:
        return "", "", ""

    def sort_key(row: tuple[str, str, str]) -> tuple[int, int, str]:
        _, _, end_year = row
        return (0 if not end_year else 1, -int(end_year or 0), labels.get(row[0], row[0]))

    return sorted(rows, key=sort_key)[0]


def wikidata_enrich(
    people: list[PersonSeed],
    cache_dir: Path,
    refresh: bool,
    batch_size: int,
    sleep_seconds: float,
) -> tuple[list[IdentityCandidate], list[AffiliationCandidate], dict[str, object]]:
    alias_index: dict[str, list[PersonSeed]] = {}
    aliases: set[str] = set()
    for person in people:
        for alias in person.aliases:
            normalized = normalize_text(alias)
            if not normalized:
                continue
            aliases.add(alias)
            alias_index.setdefault(normalized, []).append(person)

    matches: dict[str, dict[str, str]] = {person.person_id: {} for person in people}
    errors: list[str] = []
    batches_attempted = 0
    rate_limit_retry_after = ""
    for alias_batch in batched(sorted(aliases), max(1, batch_size)):
        batches_attempted += 1
        values = " ".join(
            f"{json.dumps(alias, ensure_ascii=False)}@{language}"
            for alias in alias_batch
            for language in ("en", "ru", "kk")
        )
        query = (
            "SELECT DISTINCT ?item ?name WHERE { "
            f"VALUES ?name {{ {values} }} "
            "?item (rdfs:label|skos:altLabel) ?name . "
            "}"
        )
        cache_path = cache_dir / "wikidata" / "search" / stable_cache_name(query)
        try:
            payload = fetch_json(
                "https://query.wikidata.org/sparql",
                cache_path,
                params={"query": query, "format": "json"},
                headers={"Accept": "application/sparql-results+json"},
                refresh=refresh,
            )
        except RateLimitExhausted as exc:
            rate_limit_retry_after = exc.retry_after
            errors.append(str(exc))
            break
        except Exception as exc:
            errors.append(f"search batch {batches_attempted}: {exc}")
            continue
        bindings = (
            ((payload.get("results") or {}).get("bindings") or [])
            if isinstance(payload, dict)
            else []
        )
        for binding in bindings:
            item_url = clean_text((binding.get("item") or {}).get("value"))
            matched_name = clean_text((binding.get("name") or {}).get("value"))
            item_id = item_url.rstrip("/").split("/")[-1]
            if not item_id.startswith("Q") or not matched_name:
                continue
            for person in alias_index.get(normalize_text(matched_name), []):
                matches[person.person_id][item_id] = matched_name
        if sleep_seconds > 0:
            time.sleep(sleep_seconds)

    candidate_ids = sorted({item_id for values in matches.values() for item_id in values})
    entities: dict[str, dict[str, object]] = {}
    for id_batch in batched(candidate_ids, 50):
        try:
            entities.update(
                wikidata_get_entities(
                    id_batch,
                    cache_dir,
                    refresh,
                    props="labels|descriptions|claims|sitelinks",
                )
            )
        except Exception as exc:
            errors.append(f"entity batch {id_batch[0]}: {exc}")

    linked_ids: set[str] = set()
    for entity in entities.values():
        for property_id in WIKIDATA_CONTEXT_PROPERTIES:
            linked_ids.update(
                item_id
                for item_id, _, _ in wikidata_claim_rows(entity, property_id)
                if item_id
            )
    label_entities = dict(entities)
    for id_batch in batched(sorted(linked_ids - set(entities)), 50):
        try:
            label_entities.update(
                wikidata_get_entities(id_batch, cache_dir, refresh, props="labels")
            )
        except Exception as exc:
            errors.append(f"label batch {id_batch[0]}: {exc}")
    labels = {
        entity_id: wikidata_label(entity, entity_id)
        for entity_id, entity in label_entities.items()
    }

    people_by_id = {person.person_id: person for person in people}
    identities: list[IdentityCandidate] = []
    affiliations: list[AffiliationCandidate] = []
    matched_people: set[str] = set()
    for person_id, person_matches in matches.items():
        person = people_by_id[person_id]
        for item_id, matched_name in person_matches.items():
            entity = entities.get(item_id)
            if entity is None:
                continue
            name_score, name_reason = name_match_score(person, matched_name)
            if name_score < 0.4:
                continue

            claim_rows = {
                property_id: wikidata_claim_rows(entity, property_id)
                for property_id in WIKIDATA_CONTEXT_PROPERTIES
            }
            claim_labels = {
                property_id: [labels.get(item, item) for item, _, _ in rows]
                for property_id, rows in claim_rows.items()
            }
            description = wikidata_description(entity)
            context = " ".join(
                [description]
                + [label for values in claim_labels.values() for label in values]
            )
            reasons = [name_reason, "wikidata_name_only"]
            score = name_score
            if context_contains(context, KAZAKHSTAN_TERMS):
                score += 0.22
                reasons.append("kazakhstan_context")
            if context_contains(context, OLYMPIAD_TERMS):
                score += 0.32
                reasons.append("direct_olympiad_evidence")
            expected_fields = set().union(
                *(FIELD_TERMS.get(olympiad, set()) for olympiad in person.olympiads)
            )
            if any(context_contains(context, {field}) for field in expected_fields):
                score += 0.1
                reasons.append("field_alignment")

            birth_years = [
                wikidata_time_year(statement.get("mainsnak") or {})
                for statement in wikidata_claims(entity, "P569")
            ]
            birth_year = next((year for year in birth_years if year is not None), None)
            if birth_year is not None:
                if birth_year < person.first_year - 25 or birth_year > person.first_year - 10:
                    score -= 0.4
                    reasons.append("timeline_conflict")
                else:
                    score += 0.03
                    reasons.append("plausible_timeline")

            official_urls = wikidata_string_values(entity, "P856")
            orcid_ids = wikidata_string_values(entity, "P496")
            outbound_urls = list(official_urls)
            outbound_urls.extend(f"https://orcid.org/{orcid_id}" for orcid_id in orcid_ids)
            enwiki = clean_text(((entity.get("sitelinks") or {}).get("enwiki") or {}).get("title"))
            if enwiki:
                outbound_urls.append(
                    "https://en.wikipedia.org/wiki/" + quote(enwiki.replace(" ", "_"))
                )
            if outbound_urls:
                score += 0.03
                reasons.append("outbound_profile_links")

            employer_rows = claim_rows.get("P108", [])
            affiliation_rows = claim_rows.get("P1416", [])
            education_rows = claim_rows.get("P69", [])
            organization_row = wikidata_preferred_claim(employer_rows, labels)
            if not organization_row[0]:
                organization_row = wikidata_preferred_claim(affiliation_rows, labels)
            if not organization_row[0]:
                organization_row = wikidata_preferred_claim(education_rows, labels)
            organization = labels.get(organization_row[0], "")
            role = next(iter(claim_labels.get("P106", [])), "")
            location = "; ".join(
                dict.fromkeys(
                    claim_labels.get("P551", [])
                    + claim_labels.get("P19", [])
                    + claim_labels.get("P27", [])
                )
            )
            profile_url = f"https://www.wikidata.org/wiki/{item_id}"
            evidence = "; ".join(
                item
                for item in [
                    f"description={description}" if description else "",
                    f"occupation={', '.join(claim_labels.get('P106', []))}"
                    if claim_labels.get("P106")
                    else "",
                    f"employer={', '.join(claim_labels.get('P108', []))}"
                    if claim_labels.get("P108")
                    else "",
                    f"education={', '.join(claim_labels.get('P69', []))}"
                    if claim_labels.get("P69")
                    else "",
                    f"citizenship={', '.join(claim_labels.get('P27', []))}"
                    if claim_labels.get("P27")
                    else "",
                    f"orcid={', '.join(orcid_ids)}" if orcid_ids else "",
                ]
                if item
            )
            candidate = identity(
                person,
                source="wikidata",
                source_id=item_id,
                profile_url=profile_url,
                matched_name=matched_name,
                score=score,
                reasons=reasons,
                location=location,
                organization=organization,
                role=role,
                evidence_text=evidence,
                outbound_urls=outbound_urls,
            )
            identities.append(candidate)
            matched_people.add(person_id)

            for property_id, affiliation_type in [
                ("P108", "employment"),
                ("P1416", "affiliation"),
                ("P69", "education"),
            ]:
                for organization_id, start_year, end_year in claim_rows.get(property_id, []):
                    organization_name = labels.get(organization_id, organization_id)
                    affiliations.append(
                        AffiliationCandidate(
                            person_id=person_id,
                            canonical_name=person.canonical_name,
                            organization=organization_name,
                            role=role if affiliation_type != "education" else "",
                            department="",
                            affiliation_type=affiliation_type,
                            start_year=start_year,
                            end_year=end_year,
                            country_code=(
                                "KZ"
                                if context_contains(organization_name, KAZAKHSTAN_TERMS)
                                else ""
                            ),
                            source="wikidata",
                            evidence_url=profile_url,
                            confidence=candidate.confidence,
                            evidence_text=evidence,
                        )
                    )

    return identities, affiliations, {
        "people_searched": len(people),
        "aliases_searched": len(aliases),
        "search_batches_attempted": batches_attempted,
        "entities_loaded": len(entities),
        "matched_people": len(matched_people),
        "identity_candidates": len(identities),
        "rate_limit_retry_after_seconds": rate_limit_retry_after,
        "errors": errors,
    }


def openalex_enrich(
    people: list[PersonSeed], cache_dir: Path, refresh: bool, sleep_seconds: float
) -> tuple[list[IdentityCandidate], list[AffiliationCandidate], dict[str, object]]:
    identities: list[IdentityCandidate] = []
    affiliations: list[AffiliationCandidate] = []
    matched_people: set[str] = set()
    errors: list[str] = []
    api_key = os.getenv("OPENALEX_API_KEY", "")
    attempted = 0
    rate_limit_retry_after = ""
    rate_limit_exhausted = False
    uncached_skipped_after_rate_limit = 0
    for index, person in enumerate(people, start=1):
        params: dict[str, object] = {"search": person.canonical_name, "per-page": 5}
        if api_key:
            params["api_key"] = api_key
        cache_key = "openalex:" + person.canonical_name
        cache_path = cache_dir / "openalex" / stable_cache_name(cache_key)
        if rate_limit_exhausted and not cache_path.exists():
            uncached_skipped_after_rate_limit += 1
            continue
        attempted += 1
        try:
            payload = fetch_json(
                "https://api.openalex.org/authors",
                cache_path,
                params=params,
                refresh=refresh and not rate_limit_exhausted,
            )
            results = payload.get("results", []) if isinstance(payload, dict) else []
        except RateLimitExhausted as exc:
            rate_limit_retry_after = exc.retry_after
            errors.append(f"{person.canonical_name}: {exc}")
            rate_limit_exhausted = True
            continue
        except Exception as exc:
            errors.append(f"{person.canonical_name}: {exc}")
            continue

        retained: list[tuple[float, dict[str, object], list[str]]] = []
        for author in results:
            matched_name = clean_text(author.get("display_name"))
            name_score, name_reason = name_match_score(person, matched_name)
            if name_score < 0.32:
                continue
            score = name_score
            reasons = [name_reason]
            author_affiliations = author.get("affiliations") or []
            if any(
                clean_text((item.get("institution") or {}).get("country_code")) == "KZ"
                for item in author_affiliations
            ):
                score += 0.2
                reasons.append("kazakhstan_context")
            if field_alignment(person, author):
                score += 0.1
                reasons.append("field_alignment")
            if author.get("orcid"):
                score += 0.05
                reasons.append("orcid_present")
            affiliation_years = [
                year
                for item in author_affiliations
                for year in (item.get("years") or [])
                if isinstance(year, int)
            ]
            if affiliation_years and min(affiliation_years) < person.first_year - 4:
                score -= 0.4
                reasons.append("timeline_conflict")
            elif affiliation_years and max(affiliation_years) >= person.first_year + 1:
                score += 0.03
                reasons.append("plausible_timeline")
            retained.append((score, author, reasons))

        for base_score, author, reasons in sorted(retained, key=lambda item: item[0], reverse=True)[:3]:
            author_id = clean_text(author.get("id"))
            author_url = author_id
            orcid_url = clean_text(author.get("orcid"))
            orcid_record: dict[str, object] | None = None
            outbound_urls: list[str] = []
            organization = clean_text(
                ((author.get("last_known_institutions") or [{}])[0] or {}).get("display_name")
            )
            role = "Research author"
            score = base_score
            if orcid_url and base_score >= 0.5:
                orcid_id = orcid_url.rstrip("/").split("/")[-1]
                orcid_cache = cache_dir / "orcid" / f"{orcid_id}.json"
                try:
                    record = fetch_json(
                        f"https://pub.orcid.org/v3.0/{orcid_id}/record",
                        orcid_cache,
                        headers={"Accept": "application/json"},
                        refresh=refresh,
                    )
                    if isinstance(record, dict):
                        orcid_record = record
                        orcid_reasons, orcid_urls, orcid_org, orcid_role = orcid_signals(record)
                        outbound_urls.extend(orcid_urls)
                        if orcid_reasons:
                            reasons.extend(orcid_reasons)
                            if "direct_olympiad_evidence" in orcid_reasons:
                                score += 0.3
                            if "kazakhstan_context" in orcid_reasons and "kazakhstan_context" not in reasons[:-1]:
                                score += 0.1
                        reasons.append("self_asserted_orcid_affiliation")
                        score += 0.07
                        orcid_years = orcid_affiliation_years(record)
                        if orcid_years and min(orcid_years) < person.first_year - 4:
                            score -= 0.4
                            reasons.append("timeline_conflict")
                        organization = orcid_org or organization
                        role = orcid_role or role
                except Exception as exc:
                    errors.append(f"ORCID {orcid_id}: {exc}")

            institution_names = [
                clean_text((item.get("institution") or {}).get("display_name"))
                for item in author.get("affiliations") or []
                if clean_text((item.get("institution") or {}).get("display_name"))
            ]
            topic_names = [
                clean_text(item.get("display_name"))
                for item in author.get("topics") or []
                if clean_text(item.get("display_name"))
            ][:5]
            evidence = "; ".join(
                item
                for item in [
                    f"works={author.get('works_count', 0)}",
                    f"citations={author.get('cited_by_count', 0)}",
                    f"institutions={', '.join(institution_names)}" if institution_names else "",
                    f"topics={', '.join(topic_names)}" if topic_names else "",
                    f"orcid={orcid_url}" if orcid_url else "",
                ]
                if item
            )
            candidate = identity(
                person,
                source="openalex",
                source_id=author_id.rsplit("/", 1)[-1],
                profile_url=author_url,
                matched_name=clean_text(author.get("display_name")),
                score=score,
                reasons=reasons,
                organization=organization,
                role=role,
                evidence_text=evidence,
                outbound_urls=[orcid_url, *outbound_urls],
            )
            identities.append(candidate)
            matched_people.add(person.person_id)

            for item in author.get("affiliations") or []:
                institution = item.get("institution") or {}
                institution_name = clean_text(institution.get("display_name"))
                if not institution_name:
                    continue
                years = sorted(year for year in item.get("years") or [] if isinstance(year, int))
                affiliations.append(
                    AffiliationCandidate(
                        person_id=person.person_id,
                        canonical_name=person.canonical_name,
                        organization=institution_name,
                        role="Research author",
                        department="",
                        affiliation_type=clean_text(institution.get("type")) or "institution",
                        start_year=str(min(years)) if years else "",
                        end_year=str(max(years)) if years else "",
                        country_code=clean_text(institution.get("country_code")),
                        source="openalex",
                        evidence_url=author_url,
                        confidence=candidate.confidence,
                        evidence_text=evidence,
                    )
                )
            if orcid_record:
                affiliations.extend(
                    orcid_affiliation_rows(
                        person,
                        orcid_record,
                        candidate.confidence,
                        orcid_url,
                        source="openalex_orcid",
                    )
                )

        if index % 25 == 0:
            print(f"OpenAlex searched {index}/{len(people)} people", file=sys.stderr)
        if sleep_seconds > 0:
            time.sleep(sleep_seconds)
    return identities, affiliations, {
        "people_searched": len(people),
        "people_attempted": attempted,
        "matched_people": len(matched_people),
        "identity_candidates": len(identities),
        "orcid_records": len(list((cache_dir / "orcid").glob("*.json"))) if (cache_dir / "orcid").exists() else 0,
        "rate_limit_retry_after_seconds": rate_limit_retry_after,
        "uncached_skipped_after_rate_limit": uncached_skipped_after_rate_limit,
        "errors": errors,
    }


def dedupe_identities(items: Iterable[IdentityCandidate]) -> list[IdentityCandidate]:
    best: dict[tuple[str, str, str], IdentityCandidate] = {}
    for item in items:
        key = item.person_id, item.source, item.source_id
        current = best.get(key)
        if current is None or item.score > current.score:
            best[key] = item
    return sorted(best.values(), key=lambda item: (item.person_id, -item.score, item.source, item.source_id))


def with_score_adjustment(
    item: IdentityCandidate, delta: float, reason: str
) -> IdentityCandidate:
    reasons = [value for value in item.score_reasons.split(";") if value]
    if reason not in reasons:
        reasons.append(reason)
    score = round(max(0.0, min(1.0, item.score + delta)), 3)
    return replace(
        item,
        score=score,
        confidence=confidence_for(score, reasons),
        score_reasons=";".join(reasons),
    )


def reconcile_identities(items: list[IdentityCandidate]) -> list[IdentityCandidate]:
    reconciled = list(items)
    by_person: dict[str, list[int]] = {}
    for index, item in enumerate(reconciled):
        by_person.setdefault(item.person_id, []).append(index)

    for indexes in by_person.values():
        for position, left_index in enumerate(indexes):
            left = reconciled[left_index]
            for right_index in indexes[position + 1 :]:
                right = reconciled[right_index]
                can_cross_validate = "wikidata" not in {left.source, right.source}
                if (
                    can_cross_validate
                    and left.source != right.source
                    and left.source_id.casefold() == right.source_id.casefold()
                ):
                    reconciled[left_index] = with_score_adjustment(
                        reconciled[left_index], 0.2, "cross_source_handle"
                    )
                    reconciled[right_index] = with_score_adjustment(
                        reconciled[right_index], 0.2, "cross_source_handle"
                    )
                left_org = normalize_text(left.organization)
                right_org = normalize_text(right.organization)
                if (
                    can_cross_validate
                    and left.source != right.source
                    and len(left_org) >= 4
                    and left_org == right_org
                ):
                    reconciled[left_index] = with_score_adjustment(
                        reconciled[left_index], 0.15, "cross_source_organization"
                    )
                    reconciled[right_index] = with_score_adjustment(
                        reconciled[right_index], 0.15, "cross_source_organization"
                    )
                left_urls = {url.rstrip("/") for url in left.outbound_urls.split(";") if url}
                right_urls = {url.rstrip("/") for url in right.outbound_urls.split(";") if url}
                if can_cross_validate and (
                    right.profile_url.rstrip("/") in left_urls
                    or left.profile_url.rstrip("/") in right_urls
                ):
                    reconciled[left_index] = with_score_adjustment(
                        reconciled[left_index], 0.2, "linked_profile"
                    )
                    reconciled[right_index] = with_score_adjustment(
                        reconciled[right_index], 0.2, "linked_profile"
                    )

        by_source: dict[str, list[int]] = {}
        for index in indexes:
            by_source.setdefault(reconciled[index].source, []).append(index)
        for source_indexes in by_source.values():
            if len(source_indexes) < 2:
                continue
            ranked = sorted(source_indexes, key=lambda index: reconciled[index].score, reverse=True)
            top = reconciled[ranked[0]]
            second = reconciled[ranked[1]]
            top_reasons = set(top.score_reasons.split(";"))
            has_cross_source_proof = bool(
                top_reasons
                & {"cross_source_handle", "cross_source_organization", "linked_profile", "direct_olympiad_evidence"}
            )
            if top.score - second.score < 0.1 and not has_cross_source_proof:
                for index in ranked:
                    reconciled[index] = with_score_adjustment(
                        reconciled[index], -0.15, "ambiguous_same_name_source"
                    )

    return sorted(
        reconciled,
        key=lambda item: (item.person_id, -item.score, item.source, item.source_id),
    )


def reconcile_affiliation_confidence(
    affiliations: list[AffiliationCandidate], identities: list[IdentityCandidate]
) -> list[AffiliationCandidate]:
    confidence_rank = {"candidate": 0, "probable": 1, "confirmed": 2}
    url_confidence: dict[tuple[str, str], str] = {}
    identities_by_source: dict[tuple[str, str], list[IdentityCandidate]] = {}
    for item in identities:
        identities_by_source.setdefault((item.person_id, item.source), []).append(item)
        urls = {
            item.profile_url.rstrip("/"),
            item.evidence_url.rstrip("/"),
            *(url.rstrip("/") for url in item.outbound_urls.split(";") if url),
        }
        for url in urls:
            if not url:
                continue
            key = item.person_id, url
            current = url_confidence.get(key, "candidate")
            if confidence_rank[item.confidence] > confidence_rank[current]:
                url_confidence[key] = item.confidence
    reconciled: list[AffiliationCandidate] = []
    for item in affiliations:
        identity_source = "openalex" if item.source == "openalex_orcid" else item.source
        evidence_key = item.person_id, item.evidence_url.rstrip("/")
        confidence = url_confidence.get(evidence_key, item.confidence)
        source_identities = identities_by_source.get((item.person_id, identity_source), [])
        if evidence_key not in url_confidence and len(source_identities) == 1:
            confidence = source_identities[0].confidence
        reconciled.append(replace(item, confidence=confidence))
    return reconciled


def dedupe_affiliations(items: Iterable[AffiliationCandidate]) -> list[AffiliationCandidate]:
    best: dict[tuple[str, str, str, str, str, str], AffiliationCandidate] = {}
    rank = {"candidate": 0, "probable": 1, "confirmed": 2}
    for item in items:
        key = (
            item.person_id,
            normalize_text(item.organization),
            normalize_text(item.role),
            item.start_year,
            item.end_year,
            item.source,
        )
        current = best.get(key)
        if current is None or rank[item.confidence] > rank[current.confidence]:
            best[key] = item
    return sorted(best.values(), key=lambda item: (item.person_id, item.start_year, item.organization.casefold()))


def write_dataclasses(items: list[object], csv_path: Path, json_path: Path, fieldnames: list[str]) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for item in items:
            writer.writerow(asdict(item))
    json_path.write_text(
        json.dumps([asdict(item) for item in items], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--people-csv", default="data/people.csv")
    parser.add_argument(
        "--sources",
        nargs="+",
        choices=["codeforces", "cphof", "github", "orcid", "openalex", "wikidata"],
        default=["codeforces", "cphof", "github", "orcid", "openalex", "wikidata"],
    )
    parser.add_argument(
        "--scopes",
        nargs="+",
        choices=["career", "early_career_or_university", "recent_competitor"],
        default=["career"],
    )
    parser.add_argument("--max-people", type=int, default=0)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--cache-dir", default="data/cache/enrichment")
    parser.add_argument("--github-batch-size", type=int, default=15)
    parser.add_argument("--cphof-sleep", type=float, default=0.12)
    parser.add_argument("--orcid-sleep", type=float, default=0.12)
    parser.add_argument("--openalex-sleep", type=float, default=0.12)
    parser.add_argument("--wikidata-batch-size", type=int, default=40)
    parser.add_argument("--wikidata-sleep", type=float, default=0.2)
    parser.add_argument("--identity-csv", default="data/identity_candidates.csv")
    parser.add_argument("--identity-json", default="data/identity_candidates.json")
    parser.add_argument("--affiliation-csv", default="data/affiliation_candidates.csv")
    parser.add_argument("--affiliation-json", default="data/affiliation_candidates.json")
    parser.add_argument("--audit-json", default="data/enrichment_audit.json")
    args = parser.parse_args()

    people = load_people(Path(args.people_csv), set(args.scopes))
    if args.max_people > 0:
        people = people[: args.max_people]
    cache_dir = Path(args.cache_dir)
    identities: list[IdentityCandidate] = []
    affiliations: list[AffiliationCandidate] = []
    audit: dict[str, object] = {
        "people_loaded": len(people),
        "scopes": args.scopes,
        "sources": args.sources,
    }

    if "codeforces" in args.sources:
        print("Collecting Codeforces identities", file=sys.stderr)
        source_identities, source_affiliations, source_audit = codeforces_enrich(
            people, cache_dir, args.refresh
        )
        identities.extend(source_identities)
        affiliations.extend(source_affiliations)
        audit["codeforces"] = source_audit

    if "cphof" in args.sources:
        print("Collecting CPHOF identities", file=sys.stderr)
        source_identities, source_affiliations, source_audit = cphof_enrich(
            people, cache_dir, args.refresh, args.cphof_sleep
        )
        identities.extend(source_identities)
        affiliations.extend(source_affiliations)
        audit["cphof"] = source_audit

    if "github" in args.sources:
        print("Collecting GitHub identities", file=sys.stderr)
        source_identities, source_affiliations, source_audit = github_enrich(
            people, cache_dir, args.refresh, args.github_batch_size
        )
        identities.extend(source_identities)
        affiliations.extend(source_affiliations)
        audit["github"] = source_audit

    if "openalex" in args.sources:
        print("Collecting OpenAlex and ORCID identities", file=sys.stderr)
        source_identities, source_affiliations, source_audit = openalex_enrich(
            people, cache_dir, args.refresh, args.openalex_sleep
        )
        identities.extend(source_identities)
        affiliations.extend(source_affiliations)
        audit["openalex"] = source_audit

    if "orcid" in args.sources:
        print("Collecting direct ORCID identities", file=sys.stderr)
        source_identities, source_affiliations, source_audit = orcid_search_enrich(
            people, cache_dir, args.refresh, args.orcid_sleep
        )
        identities.extend(source_identities)
        affiliations.extend(source_affiliations)
        audit["orcid"] = source_audit

    if "wikidata" in args.sources:
        print("Collecting Wikidata identities", file=sys.stderr)
        source_identities, source_affiliations, source_audit = wikidata_enrich(
            people,
            cache_dir,
            args.refresh,
            args.wikidata_batch_size,
            args.wikidata_sleep,
        )
        identities.extend(source_identities)
        affiliations.extend(source_affiliations)
        audit["wikidata"] = source_audit

    identities = reconcile_identities(dedupe_identities(identities))
    affiliations = dedupe_affiliations(
        reconcile_affiliation_confidence(affiliations, identities)
    )
    write_dataclasses(
        identities,
        Path(args.identity_csv),
        Path(args.identity_json),
        list(IdentityCandidate.__dataclass_fields__),
    )
    write_dataclasses(
        affiliations,
        Path(args.affiliation_csv),
        Path(args.affiliation_json),
        list(AffiliationCandidate.__dataclass_fields__),
    )
    confidence_counts = {
        level: sum(1 for item in identities if item.confidence == level)
        for level in ["confirmed", "probable", "candidate"]
    }
    audit["output"] = {
        "identity_candidates": len(identities),
        "affiliation_candidates": len(affiliations),
        "matched_people": len({item.person_id for item in identities}),
        "confidence_counts": confidence_counts,
    }
    Path(args.audit_json).write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(audit["output"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
