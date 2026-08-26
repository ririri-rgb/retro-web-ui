#!/usr/bin/env python3
"""Snapshot and compare hashed behavior signals around a UI-only conversion."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from collections import Counter
from pathlib import Path
from typing import Iterable

EXCLUDED = {".git", "node_modules", "dist", "build", ".next", ".nuxt", ".svelte-kit", "coverage", "vendor"}
EXTENSIONS = {".html", ".htm", ".js", ".mjs", ".cjs", ".ts", ".jsx", ".tsx", ".vue", ".svelte", ".astro"}
SIGNALS = {
    "event-binding": re.compile(r"(?:(?:on[A-Z][A-Za-z]+|@[a-z][\w:-]*|v-on:[\w:-]+|on:[a-z][\w:-]*)\s*=\s*(?:\{[^}\n]{0,400}\}|[\"'][^\"'\n]{0,400}[\"'])|(?:addEventListener|removeEventListener)\s*\([^;\n]{0,500}\))"),
    "network": re.compile(r"(?:\bfetch\s*\([^;\n]{0,700}\)|\baxios(?:\.[a-z]+)?\s*\([^;\n]{0,700}\)|\bXMLHttpRequest\b|\bWebSocket\s*\([^;\n]{0,400}\)|\bEventSource\s*\([^;\n]{0,400}\))"),
    "auth": re.compile(r"(?:\bauth(?:enticate|orize)?\b|\bsignIn\b|\bsignOut\b|\blogin\b|\blogout\b|\bBearer\b|\bAuthorization\b)", re.I),
    "routing": re.compile(r"(?:\buseRouter\s*\(\s*\)|\bnavigate\s*\([^;\n]{0,400}\)|\brouter\.(?:push|replace|go)\s*\([^;\n]{0,400}\)|\b(?:href|to|action)\s*=\s*(?:\{[^}\n]{0,400}\}|[\"'][^\"'\n]{0,400}[\"']))"),
    "storage": re.compile(r"(?:(?:\blocalStorage|\bsessionStorage)(?:\.[A-Za-z]+\s*\([^;\n]{0,500}\))?|\bindexedDB(?:\.[A-Za-z]+\s*\([^;\n]{0,500}\))?|\bcaches\.(?:open|match)\s*\([^;\n]{0,500}\))"),
    "state": re.compile(r"(?:\buseState\s*\([^;\n]{0,300}\)|\buseReducer\s*\([^;\n]{0,500}\)|\bcreateStore\s*\([^;\n]{0,500}\)|\bwritable\s*\([^;\n]{0,300}\)|\bref\s*\([^;\n]{0,300}\)|\breactive\s*\([^;\n]{0,500}\))"),
    "form-contract": re.compile(r"(?:\b(?:name|type|method|pattern|formaction)\s*=\s*(?:\{[^}\n]{0,400}\}|[\"'][^\"'\n]{0,400}[\"'])|\brequired(?:\s*=\s*(?:\{[^}\n]{0,80}\}|[\"'][^\"'\n]{0,80}[\"']))?)", re.I),
    "framework-binding": re.compile(r"(?:\b(?:v-model(?::[\w-]+)?|bind:[\w-]+|ngModel|formControlName|data-bs-(?:toggle|target|dismiss))\s*(?:=\s*(?:\{[^}\n]{0,400}\}|[\"'][^\"'\n]{0,400}[\"']))?)"),
}
SIGNAL_ALGORITHM = "sha256-normalized-signal-expression-v3"


def files(root: Path) -> Iterable[Path]:
    for current, dirs, names in os.walk(root):
        dirs[:] = [d for d in dirs if d not in EXCLUDED]
        for name in names:
            path = Path(current) / name
            if path.suffix.lower() in EXTENSIONS and path.stat().st_size <= 2_000_000:
                yield path


def normalized_window(text: str, start: int, end: int) -> str:
    # Patterns include the protected expression itself and exclude neighboring UI markup.
    value = text[start:end]
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:20]


def snapshot(root: Path) -> dict:
    file_entries = {}
    totals: Counter[str] = Counter()
    for path in files(root):
        try:
            raw = path.read_bytes()
            text = raw.decode("utf-8", errors="ignore")
        except OSError:
            continue
        signals: dict[str, list[str]] = {}
        for name, pattern in SIGNALS.items():
            values = sorted(digest(f"{name}:{normalized_window(text, match.start(), match.end())}") for match in pattern.finditer(text))
            if values:
                signals[name] = values
                totals[name] += len(values)
        if signals:
            file_entries[path.relative_to(root).as_posix()] = {
                "sha256": hashlib.sha256(raw).hexdigest(),
                "signals": signals,
            }
    return {
        "schema_version": 1,
        "root": str(root.resolve()),
        "signal_algorithm": SIGNAL_ALGORITHM,
        "files": file_entries,
        "totals": dict(sorted(totals.items())),
        "limitations": [
            "Hashes detect changed local source patterns but do not prove semantic equivalence.",
            "Dynamic aliases, generated code, and runtime-only wiring may be missed.",
            "No source excerpts or literal values are stored.",
        ],
    }


def compare(before: dict, after: dict) -> dict:
    before_algorithm = before.get("signal_algorithm")
    after_algorithm = after.get("signal_algorithm")
    if before_algorithm != after_algorithm:
        return {
            "status": "incompatible-baseline",
            "protected_signal_changes": [],
            "removed_signal_count": 0,
            "message": f"Baseline algorithm {before_algorithm!r} does not match current algorithm {after_algorithm!r}; create a new baseline.",
        }
    changes = []
    before_files = before.get("files", {})
    after_files = after.get("files", {})
    for path in sorted(set(before_files) | set(after_files)):
        old = before_files.get(path, {"signals": {}})
        new = after_files.get(path, {"signals": {}})
        for signal in sorted(set(old["signals"]) | set(new["signals"])):
            old_values = Counter(old["signals"].get(signal, []))
            new_values = Counter(new["signals"].get(signal, []))
            removed = sum((old_values - new_values).values())
            added = sum((new_values - old_values).values())
            if removed or added:
                changes.append({"file": path, "signal": signal, "removed": removed, "added": added})
    removals = sum(item["removed"] for item in changes)
    return {
        "status": "review-required" if changes else "unchanged",
        "protected_signal_changes": changes,
        "removed_signal_count": removals,
        "message": "Inspect every change; added signals can also alter behavior." if changes else "No protected source signal changed.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    snap = sub.add_parser("snapshot", help="write a baseline")
    snap.add_argument("root", type=Path)
    snap.add_argument("--output", "-o", type=Path, required=True)
    check = sub.add_parser("compare", help="compare baseline with current source")
    check.add_argument("baseline", type=Path)
    check.add_argument("root", type=Path)
    check.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if args.command == "snapshot":
        root = args.root.resolve()
        if not root.is_dir():
            parser.error(f"not a directory: {root}")
        result = snapshot(root)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"wrote behavior baseline with {len(result['files'])} signal-bearing files: {args.output}")
        return 0
    before = json.loads(args.baseline.read_text(encoding="utf-8"))
    result = compare(before, snapshot(args.root.resolve()))
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(result["status"])
        for item in result["protected_signal_changes"]:
            print(f"{item['file']}: {item['signal']} -{item['removed']} +{item['added']}")
        print(result["message"])
    if result["status"] == "incompatible-baseline":
        return 3
    return 2 if result["protected_signal_changes"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
