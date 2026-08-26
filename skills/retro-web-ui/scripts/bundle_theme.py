#!/usr/bin/env python3
"""Create a deterministic, namespaced CSS bundle for one retro theme."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

THEMES = ("windows-98", "windows-xp", "windows-7", "japanese-freeware-2000s")


def build(theme: str) -> str:
    asset_dir = Path(__file__).resolve().parent.parent / "assets" / "theme-kit"
    parts = []
    for name in ("retro-base.css", f"{theme}.css"):
        content = (asset_dir / name).read_text(encoding="utf-8").rstrip() + "\n"
        parts.append(f"/* source: {name} */\n{content}")
    body = "\n".join(parts)
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]
    return f"/* retro-web-ui theme={theme} source-sha256={digest}; MIT; no proprietary assets */\n{body}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("theme", choices=THEMES)
    parser.add_argument("--output", "-o", type=Path, help="write bundle to this file; otherwise print to stdout")
    parser.add_argument("--check", action="store_true", help="fail if output does not already match")
    parser.add_argument("--force", action="store_true", help="replace a different existing output after reviewing it")
    args = parser.parse_args()
    content = build(args.theme)
    if not args.output:
        if args.check:
            parser.error("--check requires --output")
        print(content, end="")
        return 0
    output = args.output.resolve()
    if args.check and args.force:
        parser.error("--check and --force cannot be combined")
    if args.check:
        try:
            existing = output.read_text(encoding="utf-8")
        except OSError:
            print(f"missing bundle: {output}")
            return 1
        if existing != content:
            print(f"stale bundle: {output}")
            return 1
        print(f"bundle is current: {output}")
        return 0
    if output.exists():
        try:
            existing = output.read_text(encoding="utf-8")
        except OSError as error:
            print(f"cannot read existing output: {output}: {error}")
            return 2
        if existing == content:
            print(f"bundle is already current: {output}")
            return 0
        if not args.force:
            print(f"refusing to overwrite different existing file: {output}; review it, then pass --force")
            return 2
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(content, encoding="utf-8")
    print(f"wrote {args.theme} bundle: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
