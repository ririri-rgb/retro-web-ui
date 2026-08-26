#!/usr/bin/env python3
"""Find likely modern-style residue and theme integration problems."""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path

THEMES = ("windows-98", "windows-xp", "windows-7", "japanese-freeware-2000s")
EXCLUDED = {".git", "node_modules", "dist", "build", ".next", ".nuxt", ".svelte-kit", "coverage", "vendor"}
SOURCE_EXTENSIONS = {".html", ".htm", ".css", ".scss", ".sass", ".less", ".jsx", ".tsx", ".vue", ".svelte", ".astro"}
CHECKS = {
    "large-radius": re.compile(r"border-radius\s*:\s*(?:[1-9]\d|[2-9]rem|999)"),
    "pill-utility": re.compile(r"(?:rounded-full|rounded-\[999|border-radius\s*:\s*999)"),
    "oversized-type": re.compile(r"(?:font-size\s*:\s*(?:3[2-9]|[4-9]\d)px|text-(?:4xl|5xl|6xl|7xl|8xl|9xl))"),
    "oversized-spacing": re.compile(r"(?:padding\s*:\s*(?:3[2-9]|[4-9]\d)px|\bp-(?:10|12|14|16|20|24)\b)"),
    "backdrop-blur": re.compile(r"(?:backdrop-filter\s*:|backdrop-blur)"),
    "floating-shadow": re.compile(r"(?:box-shadow\s*:[^;]*(?:20px|30px|40px)|shadow-2xl)"),
    "modern-card-name": re.compile(r"(?:class(?:Name)?\s*=\s*[\"'][^\"']*\b(?:card|pill|chip|fab)\b)", re.I),
}


def audit(root: Path, theme: str) -> dict:
    findings = []
    theme_marker = f'data-retro-theme="{theme}"'
    marker_seen = False
    css_bundle_seen = False
    for current, dirs, names in os.walk(root):
        dirs[:] = [d for d in dirs if d not in EXCLUDED]
        for name in names:
            path = Path(current) / name
            if path.suffix.lower() not in SOURCE_EXTENSIONS or path.stat().st_size > 2_000_000:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if theme_marker in text or f"data-retro-theme={{'{theme}'}}" in text or f'data-retro-theme="{theme}"' in text:
                marker_seen = True
            if (
                f"retro-web-ui theme={theme}" in text
                or f'[data-retro-theme="{theme}"]' in text
                or f"assets/theme-kit/{theme}.css" in text
            ):
                css_bundle_seen = True
            if "assets/theme-kit" in path.as_posix():
                continue
            for check, pattern in CHECKS.items():
                matches = list(pattern.finditer(text))
                if matches:
                    findings.append({
                        "file": path.relative_to(root).as_posix(),
                        "check": check,
                        "count": len(matches),
                        "severity": "review",
                    })
    if not marker_seen:
        findings.insert(0, {"file": ".", "check": "missing-theme-root", "count": 1, "severity": "high"})
    if not css_bundle_seen:
        findings.insert(0, {"file": ".", "check": "missing-theme-css", "count": 1, "severity": "high"})
    return {
        "theme": theme,
        "status": "review-required" if findings else "clean",
        "findings": findings,
        "limitations": [
            "Static patterns can be false positives and do not inspect computed styles.",
            "Excluded dependencies and generated build output can retain modern styles that this source audit cannot see.",
            "A clean report does not establish theme fidelity, accessibility, or behavior preservation.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--theme", choices=THEMES, required=True)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--strict", action="store_true", help="exit nonzero on any finding")
    args = parser.parse_args()
    result = audit(args.root.resolve(), args.theme)
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"{result['theme']}: {result['status']}")
        for item in result["findings"]:
            print(f"{item['severity']}: {item['file']}: {item['check']} ({item['count']})")
    if any(item["severity"] == "high" for item in result["findings"]):
        return 2
    if args.strict and result["findings"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
