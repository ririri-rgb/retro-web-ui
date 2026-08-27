#!/usr/bin/env python3
"""Build reproducible CLI wheel/sdist artifacts and SHA-256 files."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import os
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_DATE_EPOCH = "1767225600"  # 2026-01-01T00:00:00Z


def normalized_sdist(source_path: Path) -> bytes:
    """Normalize setuptools tar/gzip metadata without changing archive content."""

    output = io.BytesIO()
    with tarfile.open(source_path, "r:gz") as source:
        with gzip.GzipFile(fileobj=output, mode="wb", filename="", compresslevel=9, mtime=int(SOURCE_DATE_EPOCH)) as compressed:
            with tarfile.open(fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT) as target:
                for member in sorted(source.getmembers(), key=lambda item: item.name):
                    normalized = tarfile.TarInfo(member.name)
                    normalized.mode = member.mode
                    normalized.type = member.type
                    normalized.linkname = member.linkname
                    normalized.size = member.size if member.isfile() else 0
                    normalized.mtime = int(SOURCE_DATE_EPOCH)
                    normalized.uid = 0
                    normalized.gid = 0
                    normalized.uname = ""
                    normalized.gname = ""
                    extracted = source.extractfile(member) if member.isfile() else None
                    target.addfile(normalized, extracted)
    return output.getvalue()


def write_artifact(output: Path, content: bytes, force: bool) -> str:
    if output.exists():
        if output.read_bytes() == content:
            return "current"
        if not force:
            raise RuntimeError(f"refusing to overwrite different artifact: {output}; pass --force after review")
    output.write_bytes(content)
    return "written"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "dist")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    environment = os.environ.copy()
    environment["SOURCE_DATE_EPOCH"] = SOURCE_DATE_EPOCH
    environment["PYTHONHASHSEED"] = "0"
    with tempfile.TemporaryDirectory(prefix="retro-web-ui-cli-") as temp:
        command = [sys.executable, "-m", "build", "--no-isolation", "--outdir", temp, str(ROOT)]
        completed = subprocess.run(command, cwd=ROOT, env=environment)
        if completed.returncode:
            return completed.returncode
        artifacts = sorted(path for path in Path(temp).iterdir() if path.suffix == ".whl" or path.name.endswith(".tar.gz"))
        if len(artifacts) != 2:
            print(f"expected one wheel and one sdist, found: {[path.name for path in artifacts]}", file=sys.stderr)
            return 2
        for source in artifacts:
            target = args.output / source.name
            content = normalized_sdist(source) if source.name.endswith(".tar.gz") else source.read_bytes()
            action = write_artifact(target, content, args.force)
            digest = hashlib.sha256(target.read_bytes()).hexdigest()
            checksum = target.with_name(target.name + ".sha256")
            checksum_content = f"{digest}  {target.name}\n".encode("utf-8")
            write_artifact(checksum, checksum_content, args.force)
            print(f"{action}: {target}")
            print(f"sha256: {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
