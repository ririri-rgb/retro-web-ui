#!/usr/bin/env python3
"""Build, exercise, and archive one host-native Retro Web UI GUI artifact.

The build uses Nuitka directly with the compiler and core package-data options
recorded in ``deployment/pysidedeploy.spec``. Direct invocation gives CI an
explicit temporary output directory while preserving ``pyside6-deploy`` as the
documented configuration and dry-run route.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile


ROOT = Path(__file__).resolve().parents[1]
VERSION = (ROOT / "VERSION").read_text(encoding="utf-8").strip()


def run(
    argv: list[str],
    *,
    cwd: Path = ROOT,
    env: dict[str, str] | None = None,
    timeout: float = 1200,
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        argv,
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if completed.returncode:
        detail = (completed.stdout + "\n" + completed.stderr)[-20_000:]
        raise RuntimeError(f"Command failed ({completed.returncode}): {argv!r}\n{detail}")
    return completed


def platform_id() -> tuple[str, str]:
    system = platform.system().lower()
    names = {"darwin": "macos", "windows": "windows", "linux": "linux"}
    if system not in names:
        raise RuntimeError(f"Unsupported native build host: {platform.system()}")
    machine = platform.machine().lower().replace("amd64", "x86_64").replace("aarch64", "arm64")
    return names[system], machine


def draw_icon(path: Path, size: int) -> None:
    from PIL import Image, ImageDraw

    image = Image.new("RGBA", (size, size), "#008080")
    painter = ImageDraw.Draw(image)
    scale = size / 64
    border = max(1, round(2 * scale))
    painter.rectangle(
        (round(8 * scale), round(10 * scale), round(56 * scale), round(52 * scale)),
        fill="#ece9d8",
        outline="#0b1b49",
        width=border,
    )
    painter.rectangle((round(10 * scale), round(12 * scale), round(54 * scale), round(23 * scale)), fill="#0755d5")
    painter.rectangle((round(14 * scale), round(29 * scale), round(39 * scale), round(36 * scale)), fill="#ffffff", outline="#808080")
    painter.rectangle((round(37 * scale), round(40 * scale), round(51 * scale), round(47 * scale)), fill="#d4d0c8", outline="#808080")
    file_format = {".ico": "ICO", ".icns": "ICNS"}.get(path.suffix.lower(), "PNG")
    save_options = {"sizes": [(16, 16), (32, 32), (64, 64), (128, 128), (256, 256)]} if file_format == "ICO" else {}
    image.save(path, format=file_format, **save_options)


def make_icon(directory: Path, system: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    if system == "macos":
        output = directory / "retro-web-ui.icns"
        draw_icon(output, 1024)
        return output
    output = directory / ("retro-web-ui.ico" if system == "windows" else "retro-web-ui.png")
    draw_icon(output, 256)
    return output


def find_product(output: Path, system: str) -> tuple[Path, Path]:
    if system == "macos":
        applications = sorted(output.rglob("*.app"))
        if len(applications) != 1:
            raise RuntimeError(f"Expected one macOS app bundle, found: {applications}")
        executable = applications[0] / "Contents" / "MacOS" / "launcher"
        return applications[0], executable
    suffix = ".exe" if system == "windows" else ".bin"
    executables = [
        item
        for item in output.rglob(f"*{suffix}")
        if item.is_file() and item.name.startswith("launcher")
    ]
    if len(executables) != 1:
        raise RuntimeError(f"Expected one native executable, found: {executables}")
    return executables[0].parent, executables[0]


def component_inventory(product: Path) -> list[dict[str, object]]:
    inventory: list[dict[str, object]] = []
    for path in sorted(product.rglob("*")):
        relative = path.relative_to(product).as_posix()
        if path.is_symlink():
            inventory.append({"path": relative, "type": "symlink", "target": os.readlink(path)})
        elif path.is_file():
            inventory.append(
                {
                    "path": relative,
                    "type": "file",
                    "bytes": path.stat().st_size,
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                }
            )
    return inventory


def stage_product(product: Path, directory: Path, system: str) -> tuple[Path, list[str]]:
    root = directory / ("retro-web-ui-gui" if system == "linux" else "Retro Web UI GUI")
    root.mkdir(parents=True)
    if system == "macos":
        shutil.copytree(product, root / product.name, symlinks=True)
    else:
        for path in product.iterdir():
            target = root / path.name
            if path.is_dir() and not path.is_symlink():
                shutil.copytree(path, target, symlinks=True)
            elif path.is_symlink():
                target.symlink_to(os.readlink(path))
            else:
                shutil.copy2(path, target)

    licenses = root / "LICENSES"
    shutil.copytree(ROOT / "distribution" / "licenses", licenses)
    shutil.copy2(ROOT / "LICENSE", licenses / "PROJECT-LICENSE.txt")
    shutil.copy2(ROOT / "THIRD_PARTY_NOTICES.md", licenses / "THIRD_PARTY_NOTICES.md")
    inventory = {
        "schemaVersion": 1,
        "application": "Retro Web UI GUI",
        "version": VERSION,
        "platform": system,
        "files": component_inventory(product),
    }
    (licenses / "NATIVE_COMPONENTS.json").write_text(
        json.dumps(inventory, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return root, sorted(path.name for path in licenses.iterdir() if path.is_file())


def archive_product(staged_root: Path, destination: Path, system: str) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if system == "macos":
        run(["ditto", "-c", "-k", "--sequesterRsrc", "--keepParent", str(staged_root), str(destination)])
    elif system == "windows":
        with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for path in sorted(staged_root.rglob("*")):
                if path.is_file():
                    archive.write(path, staged_root.name / path.relative_to(staged_root))
    else:
        with tarfile.open(destination, "w:gz", format=tarfile.PAX_FORMAT) as archive:
            archive.add(staged_root, arcname=staged_root.name, recursive=True)
    return destination


def validate_archive_licenses(artifact: Path) -> None:
    required = {
        "PROJECT-LICENSE.txt",
        "THIRD_PARTY_NOTICES.md",
        "NATIVE-DISTRIBUTION-NOTICE.md",
        "NATIVE_COMPONENTS.json",
        "GPL-3.0-only.txt",
        "LGPL-3.0-only.txt",
        "PYTHON-3.12-LICENSE.txt",
        "OPENSSL-LICENSE.txt",
        "XZ-UTILS-COPYING.txt",
        "MPDECIMAL-LICENSE.txt",
    }
    if artifact.suffix == ".zip":
        with zipfile.ZipFile(artifact) as archive:
            names = {Path(name).name for name in archive.namelist() if "/LICENSES/" in name}
    else:
        with tarfile.open(artifact, "r:gz") as archive:
            names = {Path(name).name for name in archive.getnames() if "/LICENSES/" in name}
    missing = sorted(required - names)
    if missing:
        raise RuntimeError(f"Native archive is missing required license files: {missing}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "dist" / "native")
    parser.add_argument("--app-server-smoke", action="store_true")
    parser.add_argument("--keep-build", action="store_true")
    args = parser.parse_args()
    if sys.version_info[:2] != (3, 12):
        raise RuntimeError(
            f"Native release builds require CPython 3.12; current interpreter is {platform.python_version()}."
        )
    import retro_web_ui

    package_root = Path(retro_web_ui.__file__).resolve().parent
    if package_root == (ROOT / "skills" / "retro-web-ui").resolve():
        raise RuntimeError(
            "Native release builds require a regular wheel install, not an editable source mapping. "
            "Create a clean environment and run: python -m pip install '.[native]'"
        )
    system, machine = platform_id()
    output = args.output.resolve()
    work = Path(tempfile.mkdtemp(prefix=f"retro-web-ui-native-{system}-"))
    try:
        icon = make_icon(work / "icons", system)
        build = work / "build"
        command = [
            sys.executable,
            "-m",
            "nuitka",
            str(ROOT / "retro_web_ui_gui" / "launcher.py"),
            "--standalone",
            "--enable-plugin=pyside6",
            "--include-module=PySide6.QtCore",
            "--include-module=PySide6.QtGui",
            "--include-module=PySide6.QtWidgets",
            f"--output-dir={build}",
            "--noinclude-qt-translations",
            "--include-package=retro_web_ui",
            "--include-package-data=retro_web_ui",
            "--include-distribution-metadata=retro-web-ui-skill",
            "--assume-yes-for-downloads",
            "--static-libpython=no",
        ]
        if system == "macos":
            command.extend([
                "--macos-create-app-bundle",
                "--macos-app-name=Retro Web UI GUI",
                f"--macos-app-version={VERSION}",
                f"--macos-app-icon={icon}",
            ])
        elif system == "windows":
            command.extend(["--windows-console-mode=attach", f"--windows-icon-from-ico={icon}"])
        build_environment = dict(os.environ)
        build_environment["XDG_CACHE_HOME"] = str(work / "cache")
        build_environment["NUITKA_CACHE_DIR"] = str(work / "cache" / "nuitka")
        run(command, cwd=work, env=build_environment, timeout=1800)
        product, executable = find_product(build, system)
        environment = dict(os.environ)
        environment.setdefault("QT_QPA_PLATFORM", "offscreen")
        version_output = run([str(executable), "--version"], env=environment, timeout=60).stdout.strip()
        smoke_args = [str(executable), "--smoke"]
        if args.app_server_smoke:
            smoke_args.append("--app-server-smoke")
        smoke = run(smoke_args, env=environment, timeout=120)
        smoke_result = json.loads(smoke.stdout.strip().splitlines()[-1])
        extension = ".tar.gz" if system == "linux" else ".zip"
        staged_root, license_bundle = stage_product(product, work / "archive", system)
        artifact = archive_product(
            staged_root,
            output / f"retro-web-ui-gui-{VERSION}-{system}-{machine}{extension}",
            system,
        )
        validate_archive_licenses(artifact)
        digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
        checksum = artifact.with_name(artifact.name + ".sha256")
        checksum.write_text(f"{digest}  {artifact.name}\n", encoding="utf-8")
        report = {
            "version": VERSION,
            "platform": system,
            "architecture": machine,
            "python": platform.python_version(),
            "artifact": artifact.name,
            "artifactBytes": artifact.stat().st_size,
            "installedBytes": sum(path.stat().st_size for path in product.rglob("*") if path.is_file()),
            "sha256": digest,
            "bundledPythonQt": True,
            "systemDependencies": (
                ["macOS system frameworks"]
                if system == "macos"
                else ["Windows system runtime"]
                if system == "windows"
                else ["glibc", "libstdc++", "libEGL", "Linux desktop display stack"]
            ),
            "codexBundled": False,
            "licenseBundle": license_bundle,
            "signing": "ad-hoc" if system == "macos" else "unsigned" if system == "windows" else "not-applicable",
            "versionOutput": version_output,
            "smoke": smoke_result,
        }
        report_path = output / f"native-report-{system}-{machine}.json"
        report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    finally:
        if args.keep_build:
            print(f"Native build retained at {work}", file=sys.stderr)
        else:
            shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
