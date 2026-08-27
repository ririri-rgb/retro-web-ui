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
# Attribute values cover ordinary quoted HTML/template values and JSX/Svelte
# braced expressions with one nested brace level. They intentionally stop well
# before an entire source file can become one signal.
_DOUBLE_QUOTED = r'"(?:\\.|[^"\\]){0,1200}"'
_SINGLE_QUOTED = r"'(?:\\.|[^'\\]){0,1200}'"
_BRACED = r"\{(?:[^{}\"']|" + _DOUBLE_QUOTED + "|" + _SINGLE_QUOTED + r"|\{[^{}]{0,800}\}){0,1600}\}"
_UNQUOTED = r"[^\s>]{1,500}"
_ATTRIBUTE_VALUE = rf"(?:{_BRACED}|{_DOUBLE_QUOTED}|{_SINGLE_QUOTED}|{_UNQUOTED})"
_CALL = r"\((?:[^()\"']|" + _DOUBLE_QUOTED + "|" + _SINGLE_QUOTED + r"|\([^()]{0,800}\)){0,2000}\)"

SIGNALS = {
    "event-binding": re.compile(
        rf"(?:(?:on[A-Za-z][\w:-]*(?:\|[\w-]+)*|@[a-z][\w:-]*(?:\.[\w-]+)*|v-on:[\w:-]+(?:\.[\w-]+)*|on:[a-z][\w:-]*(?:\|[\w-]+)*|\([a-z][\w:-]*\))\s*=\s*{_ATTRIBUTE_VALUE}|(?:[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*)\.on[a-z]+\s*=\s*{_ATTRIBUTE_VALUE}|(?:addEventListener|removeEventListener)\s*{_CALL})",
        re.I,
    ),
    "network": re.compile(rf"(?:\bfetch\s*{_CALL}|\baxios(?:\.[a-z]+)?\s*{_CALL}|\bXMLHttpRequest\b|\bWebSocket\s*{_CALL}|\bEventSource\s*{_CALL})", re.I),
    "auth": re.compile(r"(?:\bauth(?:enticate|orize)?\b|\bsignIn\b|\bsignOut\b|\blogin\b|\blogout\b|\bBearer\b|\bAuthorization\b)", re.I),
    "routing": re.compile(
        rf"(?:\buseRouter\s*\(\s*\)|\bnavigate\s*{_CALL}|\brouter\.(?:push|replace|go)\s*{_CALL}|\bhistory\.(?:pushState|replaceState)\s*{_CALL}|\b(?:window\.)?location(?:\.href)?\s*=\s*(?:{_BRACED}|{_DOUBLE_QUOTED}|{_SINGLE_QUOTED})|\b(?:href|to|action)\s*=\s*{_ATTRIBUTE_VALUE})",
        re.I,
    ),
    "storage": re.compile(rf"(?:(?:\blocalStorage|\bsessionStorage)(?:\.[A-Za-z]+\s*{_CALL})?|\bindexedDB(?:\.[A-Za-z]+\s*{_CALL})?|\bcaches\.(?:open|match)\s*{_CALL})"),
    "state": re.compile(rf"(?:\buseState\s*{_CALL}|\buseReducer\s*{_CALL}|\bcreateStore\s*{_CALL}|\bwritable\s*{_CALL}|\bref\s*{_CALL}|\breactive\s*{_CALL})"),
    "state-transition": re.compile(rf"\bset[A-Z][A-Za-z0-9_$]*\s*{_CALL}"),
    "behavior-alias": re.compile(r"\b(?:const|let|var)\s+(?:handle[A-Z]\w*|on[A-Z]\w*|submit\w*|save\w*|delete\w*|toggle\w*|open\w*|close\w*|navigate\w*)\s*=\s*(?:[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*|(?:async\s*)?(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>|function\b)", re.I),
    "form-contract": re.compile(
        rf"\b(?:name|type|method|pattern|formaction|value|min|max|step|autocomplete|checked|disabled|readonly|required)\s*(?:=\s*{_ATTRIBUTE_VALUE})?",
        re.I,
    ),
    "framework-binding": re.compile(
        rf"\b(?:v-model(?::[\w-]+)?(?:\.[\w-]+)*|bind:[\w-]+|ngModel|formControlName|data-bs-(?:toggle|target|dismiss))\s*(?:=\s*{_ATTRIBUTE_VALUE})?",
        re.I,
    ),
    "timer-subscription": re.compile(rf"\b(?:setTimeout|clearTimeout|setInterval|clearInterval|requestAnimationFrame|cancelAnimationFrame|subscribe|unsubscribe)\s*{_CALL}"),
    "accessibility-contract": re.compile(rf"\b(?:aria-[\w-]+|role|for)\s*=\s*{_ATTRIBUTE_VALUE}", re.I),
    "test-selector": re.compile(rf"\b(?:data-testid|data-test|data-cy)\s*=\s*{_ATTRIBUTE_VALUE}", re.I),
}
SIGNAL_ALGORITHM = "sha256-normalized-signal-expression-v4"


def without_comments(text: str) -> str:
    """Blank JS/CSS/HTML comments while preserving offsets and newlines."""

    result = list(text)
    index = 0
    quote: str | None = None
    while index < len(text):
        char = text[index]
        if quote:
            if char == "\\":
                index += 2
                continue
            if char == quote:
                quote = None
            index += 1
            continue
        if char in {'"', "'", "`"}:
            quote = char
            index += 1
            continue
        closing = None
        if text.startswith("//", index):
            closing = text.find("\n", index + 2)
            closing = len(text) if closing == -1 else closing
        elif text.startswith("/*", index):
            found = text.find("*/", index + 2)
            closing = len(text) if found == -1 else found + 2
        elif text.startswith("<!--", index):
            found = text.find("-->", index + 4)
            closing = len(text) if found == -1 else found + 3
        if closing is None:
            index += 1
            continue
        for position in range(index, closing):
            if result[position] not in "\r\n":
                result[position] = " "
        index = closing
    return "".join(result)


def files(root: Path) -> Iterable[Path]:
    for current, dirs, names in os.walk(root):
        current_path = Path(current)
        dirs[:] = [d for d in dirs if d not in EXCLUDED and not (current_path / d).is_symlink()]
        for name in names:
            path = current_path / name
            if not path.is_symlink() and path.suffix.lower() in EXTENSIONS and path.stat().st_size <= 2_000_000:
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
            scan_text = without_comments(text) if name == "auth" else text
            values = sorted(digest(f"{name}:{normalized_window(scan_text, match.start(), match.end())}") for match in pattern.finditer(scan_text))
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
            "Dynamic aliases, arbitrary handler-body semantics, generated code, and runtime-only wiring may be missed.",
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
