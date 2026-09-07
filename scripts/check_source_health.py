#!/usr/bin/env python3
"""Check existing evidence URLs and retain retrieval results for manual review."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup


def check(url: str, cache_dir: Path, host_locks: dict) -> dict:
    host = urlparse(url).hostname or ""
    row = {"source_url": url, "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    if host == "linkedin.com" or host.endswith(".linkedin.com"):
        return {**row, "status": "use_exa_profile_audit"}
    with host_locks[host]:
        try:
            with requests.get(url, timeout=(8, 15), stream=True,
                              headers={"User-Agent": "ISO-Futures-Source-Review/1.0"}) as response:
                row.update(http_status=response.status_code, resolved_url=response.url,
                           content_type=response.headers.get("Content-Type", ""))
                if response.status_code in {401, 403, 429, 999}:
                    return {**row, "status": "access_restricted"}
                if response.status_code in {404, 410}:
                    return {**row, "status": "not_found"}
                if not response.ok:
                    return {**row, "status": "http_error"}
                if "pdf" in row["content_type"].lower():
                    return {**row, "status": "reachable_pdf"}
                data = bytearray()
                start = time.monotonic()
                for chunk in response.iter_content(16384):
                    data.extend(chunk)
                    if len(data) >= 1_048_576 or time.monotonic() - start > 20:
                        break
                encoding = response.encoding if "charset=" in row["content_type"].lower() else None
                soup = BeautifulSoup(bytes(data), "html.parser", from_encoding=encoding)
                for tag in soup(["script", "style", "noscript"]):
                    tag.decompose()
                title = soup.title.get_text(" ", strip=True) if soup.title else ""
                text = soup.get_text(" ", strip=True)
                digest = hashlib.sha256(url.encode()).hexdigest()[:20]
                (cache_dir / f"{digest}.txt").write_text(text, encoding="utf-8")
                row.update(title=title, text_characters=len(text), text_cache=f"{digest}.txt")
                if any(fragment in title.lower() for fragment in ("just a moment", "access denied", "captcha", "not found", "404")):
                    return {**row, "status": "review_response"}
                if len(text) < 200:
                    return {**row, "status": "content_unavailable"}
                return {**row, "status": "reachable"}
        except requests.RequestException as error:
            return {**row, "status": "network_error", "error_type": type(error).__name__}
        finally:
            time.sleep(0.1)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources", type=Path, default=Path("data/audit/sources.csv"))
    parser.add_argument("--out-dir", type=Path, default=Path("output/revalidation/source_health"))
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    with args.sources.open(newline="") as handle:
        sources = list(csv.DictReader(handle))
    args.out_dir.mkdir(parents=True, exist_ok=True)
    cache_dir = args.out_dir / "text"
    cache_dir.mkdir(exist_ok=True)
    host_locks = {urlparse(row["source_url"]).hostname: threading.Semaphore(2) for row in sources}
    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(check, row["source_url"], cache_dir, host_locks): row for row in sources}
        for future in as_completed(futures):
            source = futures[future]
            result = future.result()
            result.update(source_id=source["source_id"], accepted_rows=int(source["accepted_rows"]),
                          supporting_rows=int(source["supporting_rows"]))
            results.append(result)
            if len(results) % 100 == 0 or len(results) == len(sources):
                counts = dict(Counter(row["status"] for row in results))
                print(json.dumps({"checked": len(results), "total": len(sources), "statuses": counts}), flush=True)
                (args.out_dir / "results.json").write_text(json.dumps(sorted(results, key=lambda row: row["source_url"]), indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
