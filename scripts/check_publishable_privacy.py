#!/usr/bin/env python3
"""Scan publishable files and optionally reachable Git history without echoing secrets."""

from __future__ import annotations

import argparse
import io
import json
import re
import subprocess
import zipfile
from pathlib import Path

PATTERNS = {
    "local_home_path": re.compile(
        rb"/(?:Users|home)/[A-Za-z0-9_.-]+/|[A-Za-z]:\\+Users\\+[A-Za-z0-9_.-]+\\+"
    ),
    "inline_api_secret": re.compile(
        rb"(?i)[\"']?(?:exa_api_key|ga4_api_secret|api_secret|x-api-key)[\"']?"
        rb"\s*[:=]\s*[\"'][A-Za-z0-9_+/=-]{16,}[\"']"
    ),
    "private_key": re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "github_token": re.compile(rb"\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{50,})\b"),
}


def findings(data: bytes) -> list[dict[str, object]]:
    payloads = [("", data)]
    if data.startswith(b"PK\x03\x04"):
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                payloads.extend(
                    (name, archive.read(name))
                    for name in archive.namelist()
                    if name.endswith((".xml", ".rels"))
                )
        except zipfile.BadZipFile:
            pass
    result = []
    for member, payload in payloads:
        for kind, pattern in PATTERNS.items():
            for match in pattern.finditer(payload):
                result.append({
                    "kind": kind,
                    "member": member,
                    "line": payload[:match.start()].count(b"\n") + 1,
                })
    return result


def git(root: Path, *args: str) -> bytes:
    return subprocess.check_output(["git", "-C", str(root), *args])


def scan(root: Path, history: bool = False) -> dict[str, object]:
    errors = []
    files = git(root, "ls-files", "--cached", "--others", "--exclude-standard", "-z")
    paths = sorted(set(name.decode() for name in files.split(b"\0") if name))
    file_count = 0
    for name in paths:
        path = root / name
        if path.is_file():
            file_count += 1
            errors.extend({"file": name, **item} for item in findings(path.read_bytes()))

    objects = 0
    if history:
        object_names = git(root, "rev-list", "--objects", "--all").decode().splitlines()
        process = subprocess.Popen(
            ["git", "-C", str(root), "cat-file", "--batch"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        )
        try:
            for entry in object_names:
                object_id, _, name = entry.partition(" ")
                process.stdin.write((object_id + "\n").encode())
                process.stdin.flush()
                header = process.stdout.readline().decode().split()
                if len(header) != 3 or not header[2].isdigit():
                    raise ValueError("Unable to read a reachable Git object")
                payload = process.stdout.read(int(header[2]))
                if len(payload) != int(header[2]) or process.stdout.read(1) != b"\n":
                    raise ValueError("Incomplete Git object read")
                if header[1] not in {"blob", "commit", "tag"}:
                    continue
                objects += 1
                errors.extend(
                    {"object": object_id, "file": name, **item}
                    for item in findings(payload)
                )
        finally:
            process.stdin.close()
            process.stdout.close()
            return_code = process.wait()
        if return_code:
            raise RuntimeError("Git history scan did not complete")
    return {
        "publishable_files": file_count,
        "history_objects": objects,
        "history_scanned": history,
        "findings": errors,
        "limitations": "Pattern scan for local home paths and common credential formats; not proof that every possible secret or personal detail is absent.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--history", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    report = scan(args.root, args.history)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return int(bool(report["findings"]))


if __name__ == "__main__":
    raise SystemExit(main())
