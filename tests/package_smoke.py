#!/usr/bin/env python3
"""Install a built CLI wheel in a temporary venv and validate its public interface."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def artifact_map(directory: Path) -> dict[str, str]:
    return {
        path.name: digest(path)
        for path in sorted(directory.iterdir())
        if path.suffix == ".whl" or path.name.endswith(".tar.gz")
    }


def run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifacts", type=Path)
    parser.add_argument("--compare", type=Path)
    args = parser.parse_args()
    wheels = sorted(args.artifacts.glob("*.whl"))
    if len(wheels) != 1:
        print(f"expected one wheel in {args.artifacts}, found {len(wheels)}", file=sys.stderr)
        return 2
    if args.compare and artifact_map(args.artifacts) != artifact_map(args.compare):
        print("separate builds are not byte-identical", file=sys.stderr)
        return 1
    with tempfile.TemporaryDirectory(prefix="retro-web-ui-clean-") as temp:
        environment = Path(temp) / "venv"
        created = run([sys.executable, "-m", "venv", str(environment)])
        if created.returncode:
            print(created.stdout + created.stderr, file=sys.stderr)
            return created.returncode
        python = environment / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
        cli = environment / ("Scripts/retro-web-ui.exe" if sys.platform == "win32" else "bin/retro-web-ui")
        gui = environment / ("Scripts/retro-web-ui-gui.exe" if sys.platform == "win32" else "bin/retro-web-ui-gui")
        installed = run([str(python), "-m", "pip", "install", "--no-index", "--no-deps", str(wheels[0])])
        if installed.returncode:
            print(installed.stdout + installed.stderr, file=sys.stderr)
            return installed.returncode
        info = run([str(cli), "info", "--json"])
        if info.returncode:
            print(info.stdout + info.stderr, file=sys.stderr)
            return info.returncode
        document = json.loads(info.stdout)
        if document["status"] != "ok" or not document["result"]["manifest_compatible"]:
            print(info.stdout, file=sys.stderr)
            return 1
        analyzed = run([str(cli), "analyze", str(ROOT / "tests" / "fixtures" / "static-html"), "--json"])
        if analyzed.returncode:
            print(analyzed.stdout + analyzed.stderr, file=sys.stderr)
            return analyzed.returncode
        imported = run([
            str(python),
            "-c",
            "from retro_web_ui.core import THEMES, build; assert len(THEMES) == 4 and 'retro-web-ui theme=windows-98' in build('windows-98')",
        ])
        if imported.returncode:
            print(imported.stdout + imported.stderr, file=sys.stderr)
            return imported.returncode
        gui_imported = run([
            str(python), "-c", "import retro_web_ui_gui; assert retro_web_ui_gui.__version__",
        ])
        gui_version = run([str(gui), "--version"])
        if gui_imported.returncode or gui_version.returncode or "Retro Web UI GUI" not in gui_version.stdout:
            print(gui_imported.stdout + gui_imported.stderr + gui_version.stdout + gui_version.stderr, file=sys.stderr)
            return 1
    print("clean wheel install, CLI/GUI entry points, manifest, analysis, and shared core passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
