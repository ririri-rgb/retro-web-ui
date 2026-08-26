#!/usr/bin/env python3
"""Build a reproducible Skill zip and SHA-256 file."""

from __future__ import annotations

import argparse
import hashlib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "retro-web-ui"
FIXED_TIME = (2026, 1, 1, 0, 0, 0)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "dist")
    args = parser.parse_args()
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    args.output.mkdir(parents=True, exist_ok=True)
    archive = args.output / f"retro-web-ui-{version}.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as target:
        for path in sorted(SKILL.rglob("*")):
            relative_parts = path.relative_to(SKILL).parts
            if not path.is_file() or "__pycache__" in relative_parts or any(part.startswith(".") for part in relative_parts):
                continue
            relative = Path("retro-web-ui") / path.relative_to(SKILL)
            info = zipfile.ZipInfo(relative.as_posix(), FIXED_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (0o755 if path.suffix == ".py" else 0o644) << 16
            target.writestr(info, path.read_bytes())
    value = hashlib.sha256(archive.read_bytes()).hexdigest()
    checksum = archive.with_suffix(".zip.sha256")
    checksum.write_text(f"{value}  {archive.name}\n", encoding="utf-8")
    print(archive)
    print(checksum)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
