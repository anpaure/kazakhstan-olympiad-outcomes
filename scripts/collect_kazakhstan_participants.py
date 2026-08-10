#!/usr/bin/env python3
"""Collect Kazakhstan participants from major international olympiads.

The collector uses Exa for source discovery/audit when requested, then parses
stable result archives directly so repeated runs produce comparable data.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import html as html_lib
import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from io import BytesIO
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin, urlsplit

import requests
from bs4 import BeautifulSoup


COUNTRY = "Kazakhstan"
COUNTRY_CODE = "KAZ"
DEFAULT_TIMEOUT_SECONDS = 30

OFFICIAL_SOURCE_URLS = {
    "IMO": "https://www.imo-official.org/results/individual/country/KAZ/",
    "IOI": "https://stats.ioinformatics.org/results/KAZ",
    "IPhO": "https://ipho-unofficial.org/countries/KAZ/individual",
    "IChO": "https://www.icho-official.org/results/country_info.php?country=Kazakhstan",
    "IBO": "https://www.ibo-info.org/en/info/results-reports.html",
}

SCOREBOARD_SOURCE_URLS = {
    "IBO": "https://scoreboard.bc-pf.org/en/results/biology/international_biology_olympiad",
    "IChO": "https://scoreboard.bc-pf.org/en/results/chemistry/international-chemistry-olympiad",
}

EXA_SOURCE_QUERIES = {
    "IMO": 'Kazakhstan IMO individual results contestants official KAZ "International Mathematical Olympiad"',
    "IOI": 'Kazakhstan IOI results contestants official KAZ "International Olympiad in Informatics"',
    "IPhO": 'Kazakhstan IPhO individual results contestants KAZ "International Physics Olympiad"',
    "IBO": 'Kazakhstan IBO final results contestants KAZ "International Biology Olympiad"',
    "IChO": 'Kazakhstan IChO country individual results contestants "International Chemistry Olympiad"',
}

EXA_DOMAINS = {
    "IMO": ["imo-official.org"],
    "IOI": ["stats.ioinformatics.org"],
    "IPhO": ["ipho-unofficial.org"],
    "IBO": ["scoreboard.bc-pf.org", "ibo-info.org"],
    "IChO": ["scoreboard.bc-pf.org", "icho-official.org"],
}

# These official result PDFs are image-only or list surnames without given
# names. The rows below were audited against the same year's official result
# sheet and, where needed, adjacent official result sheets/final reports.
IBO_LEGACY_PDF_ROWS: dict[int, list[tuple[str, str]]] = {
    1994: [
        ("Saken Sherhandy", ""),
        ("Nourbol Silliedev", ""),
        ("Akram Mahmudov", ""),
        ("Bakhytjan Bakhaotdinov", ""),
    ],
    1995: [
        ("Saken Sherhanov", "Bronze"),
        ("Nurbol Sihimbayev", "Bronze"),
        ("Bakitkan Bahautdinov", ""),
        ("Ekrem Mahmudov", ""),
    ],
    1996: [
        ("Saken Serhanov", "Gold"),
        ("Nurbol Sihimbayev", "Gold"),
        ("Azamat Abilkhanov", "Bronze"),
    ],
    1998: [
        ("Mirat Sadikov", "Bronze"),
        ("Andrey Jigalov", "Bronze"),
        ("Abzal Daribaev", "Bronze"),
        ("Nurlan Algashev", ""),
    ],
    1999: [
        ("Nurbol Kisembaev", "Bronze"),
        ("Anton Nesveldin", "Bronze"),
        ("Kuanysh Yergaliyev", ""),
        ("Nurlan Algashev", ""),
    ],
    2009: [
        ("Talap Kossybakov", ""),
        ("Nazym Nurlanovna Bashkenova", ""),
        ("Roman Langolf", ""),
        ("Ruslan Vladimirovich Kalizhan", ""),
    ],
}

IBO_COUNTRY_PATTERN = re.compile(
    r"(?<![A-Za-z])(?:kazakhstan|kazakhistan|kazachstan|kazakistan)(?![A-Za-z])",
    flags=re.IGNORECASE,
)
IBO_CODE_PATTERN = re.compile(r"\bKAZ(?:[- ]?[A-Z]?\d+)\b", flags=re.IGNORECASE)


@dataclass(frozen=True)
class Participant:
    olympiad: str
    country: str
    country_code: str
    year: int
    name: str
    award: str = ""
    rank: str = ""
    score: str = ""
    person_url: str = ""
    source_url: str = ""
    source_type: str = "html"


def clean_text(value: object) -> str:
    if value is None:
        return ""
    if hasattr(value, "get_text"):
        text = value.get_text(" ", strip=True)
    else:
        text = str(value)
    text = text.replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def extract_year(text: str) -> int | None:
    match = re.search(r"\b(19\d{2}|20\d{2})\b", clean_text(text))
    if not match:
        return None
    return int(match.group(1))


def stable_cache_name(url: str, suffix: str) -> str:
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
    return f"{digest}{suffix}"


def fetch_bytes(url: str, cache_dir: Path, refresh: bool = False) -> bytes:
    suffix = ".pdf" if ".pdf" in url.lower() else ".html"
    cache_path = cache_dir / stable_cache_name(url, suffix)
    if cache_path.exists() and not refresh:
        return cache_path.read_bytes()

    response = requests.get(
        url,
        timeout=DEFAULT_TIMEOUT_SECONDS,
        headers={"User-Agent": "Mozilla/5.0 (compatible; iso-futures/0.1; +participant research)"},
    )
    response.raise_for_status()
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_bytes(response.content)
    return response.content


def fetch_html(url: str, cache_dir: Path, refresh: bool = False) -> str:
    content = fetch_bytes(url, cache_dir, refresh)
    return content.decode("utf-8", errors="replace")


class ExaClient:
    def __init__(self, api_key: str):
        self.api_key = api_key

    def search(self, query: str, domains: list[str], num_results: int = 5) -> dict:
        payload: dict[str, object] = {
            "query": query,
            "numResults": num_results,
            "type": "auto",
        }
        if domains:
            payload["includeDomains"] = domains

        response = requests.post(
            "https://api.exa.ai/search",
            headers={
                "x-api-key": self.api_key,
                "Content-Type": "application/json",
                "User-Agent": "iso-futures/0.1",
            },
            json=payload,
            timeout=DEFAULT_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return response.json()


def run_exa_source_discovery(olympiads: list[str], out_dir: Path) -> None:
    api_key = os.getenv("EXA_API_KEY")
    if not api_key:
        print("EXA_API_KEY is not set; skipping Exa source discovery.", file=sys.stderr)
        return

    client = ExaClient(api_key)
    hits: dict[str, object] = {}
    for olympiad in olympiads:
        if olympiad not in EXA_SOURCE_QUERIES:
            continue
        try:
            hits[olympiad] = client.search(
                EXA_SOURCE_QUERIES[olympiad],
                EXA_DOMAINS.get(olympiad, []),
            )
        except requests.RequestException as exc:
            hits[olympiad] = {"error": str(exc)}

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "exa_source_hits.json").write_text(
        json.dumps(hits, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def table_with_headers(soup: BeautifulSoup, required: Iterable[str]):
    required_lower = [item.lower() for item in required]
    for table in soup.find_all("table"):
        headers = [clean_text(th).lower() for th in table.find_all("th")]
        if all(any(req in header for header in headers) for req in required_lower):
            return table
    return None


def absolute_link(source_url: str, tag) -> str:
    link = tag.find("a", href=True) if tag is not None else None
    return urljoin(source_url, link["href"]) if link else ""


def parse_simple_country_table(
    olympiad: str,
    html: str,
    source_url: str,
    source_type: str = "html",
) -> list[Participant]:
    soup = BeautifulSoup(html, "html.parser")
    table = table_with_headers(soup, ["Year", "Contestant", "Award"])
    if table is None:
        return []

    headers = [clean_text(th).lower() for th in table.find_all("th")]
    year_i = find_header_index(headers, "year", 0)
    name_i = find_header_index(headers, "contestant", 1)
    rank_i = find_header_index(headers, "rank", 2)
    award_i = find_header_index(headers, "award", len(headers) - 1)

    participants: list[Participant] = []
    for row in table.find_all("tr"):
        cells = row.find_all("td")
        if not cells:
            continue
        values = [clean_text(cell) for cell in cells]
        if max(year_i, name_i, award_i) >= len(values):
            continue
        year = extract_year(values[year_i])
        name = values[name_i]
        if year is None or not name:
            continue
        rank = values[rank_i] if rank_i < len(values) else ""
        award = values[award_i] if award_i < len(values) else ""
        participants.append(
            Participant(
                olympiad=olympiad,
                country=COUNTRY,
                country_code=COUNTRY_CODE,
                year=year,
                name=name,
                award=award,
                rank=rank,
                person_url=absolute_link(source_url, cells[name_i]),
                source_url=source_url,
                source_type=source_type,
            )
        )
    return participants


def parse_next_data(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    script = soup.find("script", id="__NEXT_DATA__")
    if script is None or script.string is None:
        return {}
    raw = html_lib.unescape(script.string)
    return json.loads(raw)


def scoreboard_years(index_html: str) -> list[int]:
    data = parse_next_data(index_html)
    years = data.get("props", {}).get("pageProps", {}).get("years", [])
    parsed: list[int] = []
    for item in years:
        year = item.get("year") if isinstance(item, dict) else item
        if isinstance(year, int):
            parsed.append(year)
        elif isinstance(year, str) and year.isdigit():
            parsed.append(int(year))
    return sorted(set(parsed), reverse=True)


def collect_scoreboard(
    olympiad: str,
    index_url: str,
    cache_dir: Path,
    refresh: bool,
) -> tuple[list[Participant], set[int]]:
    index_html = fetch_html(index_url, cache_dir, refresh)
    years = scoreboard_years(index_html)
    participants: list[Participant] = []
    for year in years:
        year_url = f"{index_url.rstrip('/')}/{year}"
        year_html = fetch_html(year_url, cache_dir, refresh)
        participants.extend(parse_scoreboard_year(olympiad, year_html, year_url))
    return participants, set(years)


def parse_scoreboard_year(olympiad: str, html: str, source_url: str) -> list[Participant]:
    data = parse_next_data(html)
    page_props = data.get("props", {}).get("pageProps", {})
    year_value = page_props.get("year", {})
    year = year_value.get("year") if isinstance(year_value, dict) else year_value
    if isinstance(year, str) and year.isdigit():
        year = int(year)
    if not isinstance(year, int):
        year = extract_year(source_url)
    if year is None:
        return []

    participants: list[Participant] = []
    rank = 0
    for grade in page_props.get("grades", []):
        for item in grade.get("participants", []):
            rank += 1
            if item.get("country") not in {"KZ", "KAZ"}:
                continue
            name = clean_text(item.get("nameEn"))
            if not name:
                continue
            medal = clean_text(item.get("medal"))
            award = "" if medal.lower() in {"", "none"} else medal.title()
            student_id = item.get("student")
            participants.append(
                Participant(
                    olympiad=olympiad,
                    country=COUNTRY,
                    country_code=COUNTRY_CODE,
                    year=year,
                    name=name,
                    award=award,
                    rank=str(rank),
                    score=format_score(item.get("sum")),
                    person_url=f"https://scoreboard.bc-pf.org/en/profile/{student_id}" if student_id else "",
                    source_url=source_url,
                    source_type="scoreboard",
                )
            )
    return participants


def format_score(score: object) -> str:
    if isinstance(score, int):
        return str(score)
    if isinstance(score, float):
        return f"{score:.3f}".rstrip("0").rstrip(".")
    return clean_text(score)


def find_header_index(headers: list[str], needle: str, default: int) -> int:
    for i, header in enumerate(headers):
        if needle.lower() in header:
            return i
    return default


def parse_imo(html: str, source_url: str) -> list[Participant]:
    soup = BeautifulSoup(html, "html.parser")
    data_script = soup.select_one("script[data-results-individual-country-contestants]")
    if data_script is not None:
        try:
            records = json.loads(data_script.get_text(strip=True))
        except json.JSONDecodeError:
            records = []

        award_names = {
            "gold": "Gold medal",
            "silver": "Silver medal",
            "bronze": "Bronze medal",
            "hm": "Honourable mention",
        }
        participants: list[Participant] = []
        for record in records if isinstance(records, list) else []:
            if not isinstance(record, dict):
                continue
            year = extract_year(record.get("year"))
            name = clean_text(" ".join(filter(None, [record.get("name"), record.get("surname")])))
            if year is None or not name:
                continue
            rank = record.get("rank")
            if rank is None:
                rank = record.get("scoreRank")
            slug = record.get("slug") or record.get("contestantId")
            participants.append(
                Participant(
                    olympiad="IMO",
                    country=COUNTRY,
                    country_code=COUNTRY_CODE,
                    year=year,
                    name=name,
                    award=award_names.get(clean_text(record.get("award")).lower(), ""),
                    rank=clean_text(rank),
                    score=clean_text(record.get("total")),
                    person_url=urljoin(source_url, f"/results/contestant/{slug}/") if slug else "",
                    source_url=source_url,
                )
            )
        if participants:
            return participants

    table = table_with_headers(soup, ["Year", "Contestant", "Award"])
    if table is None:
        return []

    participants: list[Participant] = []
    for row in table.select("tbody tr"):
        cells = row.find_all("td")
        if len(cells) < 6:
            continue
        values = [clean_text(cell) for cell in cells]
        year = extract_year(values[0])
        name = values[1]
        if year is None or not name:
            continue
        participants.append(
            Participant(
                olympiad="IMO",
                country=COUNTRY,
                country_code=COUNTRY_CODE,
                year=year,
                name=name,
                award=values[-1] if values else "",
                rank=values[-3] if len(values) >= 3 else "",
                score=values[-4] if len(values) >= 4 else "",
                person_url=absolute_link(source_url, cells[1]),
                source_url=source_url,
            )
        )
    return participants


def parse_ioi(html: str, source_url: str) -> list[Participant]:
    soup = BeautifulSoup(html, "html.parser")
    table = table_with_headers(soup, ["Year", "Contestant", "Award"])
    if table is None:
        return []

    participants: list[Participant] = []
    current_year: int | None = None
    for row in table.find_all("tr"):
        cells = row.find_all("td")
        if not cells:
            continue

        first_year = extract_year(clean_text(cells[0]))
        first_link = cells[0].find("a", href=re.compile(r"olympiads/\d{4}"))
        if first_year is not None and first_link:
            current_year = first_year
            offset = 1
        else:
            offset = 0

        if current_year is None or len(cells) <= offset:
            continue

        contestant_cell = cells[offset]
        person_link = contestant_cell.find("a", href=re.compile(r"people/\d+"))
        if not person_link:
            continue

        name = clean_text(contestant_cell)
        if not name:
            continue

        trailing_cells = cells[offset + 2 :]
        trailing_values = [clean_text(cell) for cell in trailing_cells]
        participants.append(
            Participant(
                olympiad="IOI",
                country=COUNTRY,
                country_code=COUNTRY_CODE,
                year=current_year,
                name=name,
                award=trailing_values[-1] if trailing_values else "",
                rank=trailing_values[-3] if len(trailing_values) >= 3 else "",
                score=trailing_values[-5] if len(trailing_values) >= 5 else "",
                person_url=urljoin(
                    source_url,
                    f"/{str(person_link['href']).lstrip('/')}",
                ),
                source_url=source_url,
            )
        )
    return participants


def extract_ibo_links(results_html: str, source_url: str) -> list[tuple[int, str, str]]:
    soup = BeautifulSoup(results_html, "html.parser")
    links_by_year: dict[int, tuple[int, str, str]] = {}
    for link in soup.find_all("a", href=True):
        href = link["href"]
        if "results-reports/results/" not in href or not href.lower().endswith(".pdf"):
            continue
        title = clean_text(link)
        candidate = " ".join([title, href])
        year = extract_year(candidate)
        if year is None:
            continue
        if href.lstrip("/").startswith("files/"):
            parsed_source = urlsplit(source_url)
            absolute = f"{parsed_source.scheme}://{parsed_source.netloc}/{href.lstrip('/')}"
        else:
            absolute = urljoin(source_url, href)
        current = links_by_year.get(year)
        should_replace = current is None or "amended" in candidate.lower()
        if should_replace:
            links_by_year[year] = (year, title or Path(href).name, absolute)
    return [links_by_year[year] for year in sorted(links_by_year, reverse=True)]


def parse_ibo_pdf(pdf_content: bytes, source_url: str, year: int) -> list[Participant]:
    if year in IBO_LEGACY_PDF_ROWS:
        return [
            Participant(
                olympiad="IBO",
                country=COUNTRY,
                country_code=COUNTRY_CODE,
                year=year,
                name=name,
                award=award,
                source_url=source_url,
                source_type="pdf_audited",
            )
            for name, award in IBO_LEGACY_PDF_ROWS[year]
        ]

    try:
        import pdfplumber
    except ImportError:
        print("pdfplumber is not installed; skipping IBO PDFs.", file=sys.stderr)
        return []

    participants: list[Participant] = []
    seen: set[tuple[int, str]] = set()
    with pdfplumber.open(BytesIO(pdf_content)) as pdf:
        for page in pdf.pages:
            for row in extract_pdf_rows(page):
                parsed = parse_ibo_row(row, source_url, year)
                if parsed is None:
                    continue
                key = (parsed.year, parsed.name.lower())
                if key in seen:
                    continue
                seen.add(key)
                participants.append(parsed)
    return participants


def extract_pdf_rows(page) -> list[list[str]]:
    rows: list[list[str]] = []
    try:
        for table in page.extract_tables() or []:
            for row in table or []:
                values = [clean_text(cell) for cell in row if clean_text(cell)]
                if values:
                    rows.append(values)
    except Exception:
        pass

    try:
        text = page.extract_text() or ""
    except Exception:
        text = ""
    for line in text.splitlines():
        line = clean_text(line)
        if line:
            rows.append([line])
    return rows


def parse_ibo_row(row: list[str], source_url: str, year: int) -> Participant | None:
    joined = clean_text(" | ".join(row))
    if not IBO_CODE_PATTERN.search(joined) and not IBO_COUNTRY_PATTERN.search(joined):
        return None

    award = extract_award(joined)
    rank = row[0] if row and re.fullmatch(r"\d+", row[0]) else ""
    score = ""

    name = extract_ibo_name_from_cells(row)
    if not name:
        name = extract_ibo_name_from_line(joined)
    if not name:
        return None
    name = " ".join(token.capitalize() if token.isupper() else token for token in name.split())

    return Participant(
        olympiad="IBO",
        country=COUNTRY,
        country_code=COUNTRY_CODE,
        year=year,
        name=name,
        award=award,
        rank=rank,
        score=score,
        source_url=source_url,
        source_type="pdf",
    )


def extract_award(text: str) -> str:
    for award in ["Gold", "Silver", "Bronze", "Certificate of Merit", "Merit", "Participant"]:
        if re.search(rf"\b{re.escape(award)}\b", text, flags=re.IGNORECASE):
            return award
    if re.search(r"(?:^|[\s|])B(?:$|[\s|])", text, flags=re.IGNORECASE):
        return "Bronze"
    return ""


def extract_ibo_name_from_cells(row: list[str]) -> str:
    for i, cell in enumerate(row):
        if IBO_CODE_PATTERN.fullmatch(cell):
            for candidate in row[i + 1 : i + 4]:
                if looks_like_name(candidate):
                    return candidate

    for i, cell in enumerate(row):
        if IBO_COUNTRY_PATTERN.search(cell):
            for candidate in row[i + 1 : i + 5]:
                if IBO_CODE_PATTERN.fullmatch(candidate):
                    continue
                if looks_like_name(candidate):
                    return candidate
    return ""


def extract_ibo_name_from_line(line: str) -> str:
    country_match = IBO_COUNTRY_PATTERN.search(line)
    code_match = IBO_CODE_PATTERN.search(line)
    if code_match:
        end = country_match.start() if country_match and country_match.start() > code_match.end() else len(line)
        after = line[code_match.end() : end].replace("|", " ").strip()
        candidate = words_until_numeric(after)
        if looks_like_name(candidate):
            return candidate

    if country_match:
        after = line[country_match.end() :].replace("|", " ").strip()
        after = IBO_CODE_PATTERN.sub("", after, count=1).strip()
        candidate = words_until_numeric(after)
        if looks_like_name(candidate):
            return candidate

        before = line[: country_match.start()].replace("|", " ").strip()
        before = re.sub(r"^(?:\W*\d+(?:[.,]\d+)?)+\s*", "", before)
        before = IBO_CODE_PATTERN.sub("", before, count=1).strip()
        candidate = words_until_numeric(before)
        if looks_like_name(candidate):
            return candidate
    return ""


def words_until_numeric(text: str) -> str:
    words: list[str] = []
    for token in text.split():
        if re.search(r"\d", token):
            break
        if token.lower() in {"gold", "silver", "bronze", "participant", "b", "s", "g"}:
            break
        if IBO_COUNTRY_PATTERN.fullmatch(token.strip(",;:|")):
            break
        words.append(token.strip(",;:"))
        if len(words) >= 5:
            break
    return clean_text(" ".join(words))


def looks_like_name(candidate: str) -> bool:
    candidate = clean_text(candidate)
    if not candidate or len(candidate) > 80:
        return False
    if IBO_COUNTRY_PATTERN.search(candidate):
        return False
    if IBO_CODE_PATTERN.search(candidate):
        return False
    if extract_award(candidate):
        return False
    if re.search(r"\d", candidate):
        return False
    return bool(re.search(r"[A-Za-z]", candidate)) and len(candidate.split()) >= 2


def dedupe_participants(participants: Iterable[Participant]) -> list[Participant]:
    deduped: dict[tuple[str, int, str], Participant] = {}
    for participant in participants:
        key = (
            participant.olympiad,
            participant.year,
            re.sub(r"\s+", " ", participant.name.lower()).strip(),
        )
        if key not in deduped:
            deduped[key] = participant
    return sorted(deduped.values(), key=lambda p: (p.olympiad, -p.year, p.name))


def collect(
    olympiads: list[str],
    cache_dir: Path,
    refresh: bool,
    include_ibo_pdfs: bool,
) -> list[Participant]:
    all_participants: list[Participant] = []

    for olympiad in olympiads:
        if olympiad not in OFFICIAL_SOURCE_URLS and olympiad not in SCOREBOARD_SOURCE_URLS:
            print(f"Unknown olympiad {olympiad}; skipping.", file=sys.stderr)
            continue

        if olympiad == "IMO":
            source_url = OFFICIAL_SOURCE_URLS[olympiad]
            print(f"Collecting {olympiad} from {source_url}", file=sys.stderr)
            all_participants.extend(parse_imo(fetch_html(source_url, cache_dir, refresh), source_url))
        elif olympiad == "IOI":
            source_url = OFFICIAL_SOURCE_URLS[olympiad]
            print(f"Collecting {olympiad} from {source_url}", file=sys.stderr)
            all_participants.extend(parse_ioi(fetch_html(source_url, cache_dir, refresh), source_url))
        elif olympiad in {"IPhO", "IChO"}:
            scoreboard_seen_years: set[int] = set()
            if olympiad in SCOREBOARD_SOURCE_URLS:
                scoreboard_url = SCOREBOARD_SOURCE_URLS[olympiad]
                print(f"Collecting {olympiad} scoreboard data from {scoreboard_url}", file=sys.stderr)
                scoreboard_participants, scoreboard_seen_years = collect_scoreboard(
                    olympiad,
                    scoreboard_url,
                    cache_dir,
                    refresh,
                )
                all_participants.extend(scoreboard_participants)

            source_url = OFFICIAL_SOURCE_URLS[olympiad]
            print(f"Collecting {olympiad} official backfill from {source_url}", file=sys.stderr)
            official = parse_simple_country_table(
                olympiad,
                fetch_html(source_url, cache_dir, refresh),
                source_url,
            )
            all_participants.extend(
                participant for participant in official if participant.year not in scoreboard_seen_years
            )
        elif olympiad == "IBO":
            scoreboard_url = SCOREBOARD_SOURCE_URLS[olympiad]
            print(f"Collecting {olympiad} scoreboard data from {scoreboard_url}", file=sys.stderr)
            scoreboard_participants, scoreboard_seen_years = collect_scoreboard(
                olympiad,
                scoreboard_url,
                cache_dir,
                refresh,
            )
            all_participants.extend(scoreboard_participants)

            if include_ibo_pdfs:
                source_url = OFFICIAL_SOURCE_URLS[olympiad]
                print(f"Collecting {olympiad} official PDF backfill from {source_url}", file=sys.stderr)
                results_html = fetch_html(source_url, cache_dir, refresh)
                for year, title, pdf_url in extract_ibo_links(results_html, source_url):
                    if year in scoreboard_seen_years:
                        continue
                    print(f"  IBO {year}: {title}", file=sys.stderr)
                    try:
                        pdf_content = fetch_bytes(pdf_url, cache_dir, refresh)
                    except requests.RequestException as exc:
                        print(f"    skipping unavailable PDF: {exc}", file=sys.stderr)
                        continue
                    all_participants.extend(parse_ibo_pdf(pdf_content, pdf_url, year))

    return dedupe_participants(all_participants)


def write_outputs(participants: list[Participant], csv_path: Path, json_path: Path) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(asdict(participants[0]).keys()) if participants else list(Participant.__dataclass_fields__.keys())

    with csv_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        for participant in participants:
            writer.writerow(asdict(participant))

    json_path.write_text(
        json.dumps([asdict(participant) for participant in participants], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--olympiads",
        nargs="+",
        default=["IMO", "IOI", "IPhO", "IBO", "IChO"],
        help="Olympiads to collect. Choices: IMO IOI IPhO IBO IChO",
    )
    parser.add_argument("--skip-ibo", action="store_true", help="Skip IBO collection.")
    parser.add_argument(
        "--include-ibo-pdfs",
        action="store_true",
        help="Backfill IBO years missing from Scoreboard by parsing official result PDFs.",
    )
    parser.add_argument("--refresh", action="store_true", help="Refresh cached source pages and PDFs.")
    parser.add_argument("--use-exa", action="store_true", help="Run Exa source discovery before parsing.")
    parser.add_argument("--out-csv", default="data/kazakhstan_participants.csv")
    parser.add_argument("--out-json", default="data/kazakhstan_participants.json")
    parser.add_argument("--cache-dir", default="data/cache")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    olympiads = [item.strip() for item in args.olympiads]
    if args.skip_ibo:
        olympiads = [item for item in olympiads if item != "IBO"]

    out_csv = Path(args.out_csv)
    out_json = Path(args.out_json)
    cache_dir = Path(args.cache_dir)

    if args.use_exa:
        run_exa_source_discovery(olympiads, out_csv.parent)

    participants = collect(olympiads, cache_dir, args.refresh, args.include_ibo_pdfs)
    write_outputs(participants, out_csv, out_json)

    counts: dict[str, int] = {}
    for participant in participants:
        counts[participant.olympiad] = counts.get(participant.olympiad, 0) + 1

    print(f"Wrote {len(participants)} participant records to {out_csv} and {out_json}")
    print(json.dumps(counts, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
