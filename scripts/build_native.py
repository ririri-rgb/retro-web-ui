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
from pathlib import PurePosixPath
import platform
import plistlib
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
from typing import Callable
import zipfile


ROOT = Path(__file__).resolve().parents[1]
VERSION = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
BUNDLE_IDENTIFIER = "io.github.ririri-rgb.retro-web-ui"
LINUX_GLIBC_CEILING = (2, 35)


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
        executable = applications[0] / "Contents" / "MacOS" / "retro-web-ui-gui"
        return applications[0], executable
    expected_names = {"retro-web-ui-gui.exe"} if system == "windows" else {"retro-web-ui-gui", "retro-web-ui-gui.bin"}
    executables = [item for item in output.rglob("*") if item.is_file() and item.name in expected_names]
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
        shutil.copytree(product, root / "Retro Web UI GUI.app", symlinks=True)
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
    shutil.copy2(ROOT / "distribution" / "INSTALL.md", root / "INSTALL.md")
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


def set_macos_bundle_metadata(bundle: Path) -> None:
    """Set stable application identity and version fields before final signing."""
    plist_path = bundle / "Contents" / "Info.plist"
    with plist_path.open("rb") as stream:
        document = plistlib.load(stream)
    document["CFBundleIdentifier"] = BUNDLE_IDENTIFIER
    document["CFBundleShortVersionString"] = VERSION
    document["CFBundleVersion"] = VERSION
    with plist_path.open("wb") as stream:
        plistlib.dump(document, stream, sort_keys=True)


def _safe_member_path(name: str) -> PurePosixPath:
    if not name or "\\" in name or name.startswith("/"):
        raise RuntimeError(f"Native archive has an unsafe member path: {name!r}")
    path = PurePosixPath(name.rstrip("/"))
    if not path.parts or any(part in {"", ".", ".."} or ":" in part for part in path.parts):
        raise RuntimeError(f"Native archive has an unsafe member path: {name!r}")
    return path


def validate_archive_layout(artifact: Path, system: str) -> None:
    """Fail closed on ambiguous or unsafe portable archive layouts."""
    expected_root = "retro-web-ui-gui" if system == "linux" else "Retro Web UI GUI"
    expected_executable = {
        "macos": f"{expected_root}/Retro Web UI GUI.app/Contents/MacOS/retro-web-ui-gui",
        "windows": f"{expected_root}/retro-web-ui-gui.exe",
        "linux": f"{expected_root}/retro-web-ui-gui",
    }[system]
    names: list[str] = []
    if artifact.suffix == ".zip":
        with zipfile.ZipFile(artifact) as archive:
            corrupt = archive.testzip()
            if corrupt:
                raise RuntimeError(f"Native ZIP integrity check failed at: {corrupt}")
            for item in archive.infolist():
                path = _safe_member_path(item.filename)
                mode = (item.external_attr >> 16) & 0xFFFF
                if stat.S_ISLNK(mode):
                    raise RuntimeError(f"Native ZIP must not contain symlinks: {item.filename}")
                if item.is_dir():
                    continue
                names.append(path.as_posix())
    else:
        with tarfile.open(artifact, "r:gz") as archive:
            for item in archive.getmembers():
                path = _safe_member_path(item.name)
                if item.issym() or item.islnk() or item.isdev() or item.isfifo():
                    raise RuntimeError(f"Native tar must contain regular files and directories only: {item.name}")
                if item.isdir():
                    continue
                if not item.isfile():
                    raise RuntimeError(f"Native tar contains an unsupported member type: {item.name}")
                names.append(path.as_posix())
    if len(names) != len(set(names)):
        raise RuntimeError("Native archive contains duplicate file paths.")
    if system in {"windows", "macos"} and len(names) != len({name.casefold() for name in names}):
        raise RuntimeError(f"{system} archive contains case-insensitive path collisions.")
    application_names = [name for name in names if not name.startswith("__MACOSX/")]
    roots = {PurePosixPath(name).parts[0] for name in application_names}
    if roots != {expected_root}:
        raise RuntimeError(f"Native archive must have exactly one application root: {sorted(roots)}")
    if application_names.count(expected_executable) != 1:
        raise RuntimeError(f"Native archive must contain exactly one launcher: {expected_executable}")
    if f"{expected_root}/INSTALL.md" not in application_names:
        raise RuntimeError("Native archive is missing its root INSTALL.md.")
    forbidden = [
        name for name in application_names
        if PurePosixPath(name).name == ".DS_Store" or PurePosixPath(name).name.startswith("._")
    ]
    if forbidden:
        raise RuntimeError(f"Native archive contains forbidden application metadata: {forbidden[:5]}")


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
            paths = {PurePosixPath(name.rstrip("/")).as_posix() for name in archive.namelist() if name and not name.endswith("/")}
    else:
        with tarfile.open(artifact, "r:gz") as archive:
            paths = {PurePosixPath(name.rstrip("/")).as_posix() for name in archive.getnames() if name and not name.endswith("/")}
    roots = {PurePosixPath(name).parts[0] for name in paths if not name.startswith("__MACOSX/")}
    if len(roots) != 1:
        raise RuntimeError(f"Cannot resolve native archive license root: {sorted(roots)}")
    root = next(iter(roots))
    missing = sorted(name for name in required if f"{root}/LICENSES/{name}" not in paths)
    if missing:
        raise RuntimeError(f"Native archive is missing required license files: {missing}")


def validate_archive_inventory(artifact: Path, system: str) -> None:
    """Reconcile the packaged component inventory with exact archive bytes."""
    root = "retro-web-ui-gui" if system == "linux" else "Retro Web UI GUI"
    product_prefix = f"{root}/Retro Web UI GUI.app/" if system == "macos" else f"{root}/"
    inventory_path = f"{root}/LICENSES/NATIVE_COMPONENTS.json"
    if artifact.suffix == ".zip":
        with zipfile.ZipFile(artifact) as archive:
            inventory = json.loads(archive.read(inventory_path))
            actual_files = {
                name[len(product_prefix):]: name
                for name in archive.namelist()
                if name.startswith(product_prefix)
                and not name.endswith("/")
                and not name.startswith(f"{root}/LICENSES/")
                and name != f"{root}/INSTALL.md"
            }
            read_file = archive.read
            _validate_inventory_entries(inventory, actual_files, read_file, system)
    else:
        with tarfile.open(artifact, "r:gz") as archive:
            source = archive.extractfile(inventory_path)
            if source is None:
                raise RuntimeError("Native archive component inventory is unreadable.")
            inventory = json.loads(source.read())
            actual_files = {
                item.name[len(product_prefix):]: item.name
                for item in archive.getmembers()
                if item.isfile()
                and item.name.startswith(product_prefix)
                and not item.name.startswith(f"{root}/LICENSES/")
                and item.name != f"{root}/INSTALL.md"
            }

            def read_file(name: str) -> bytes:
                stream = archive.extractfile(name)
                if stream is None:
                    raise RuntimeError(f"Native archive member is unreadable: {name}")
                return stream.read()

            _validate_inventory_entries(inventory, actual_files, read_file, system)


def _validate_inventory_entries(
    inventory: object,
    actual_files: dict[str, str],
    read_file: Callable[[str], bytes],
    system: str,
) -> None:
    if not isinstance(inventory, dict) or not isinstance(inventory.get("files"), list):
        raise RuntimeError("Native archive has a malformed component inventory.")
    expected_metadata = {
        "schemaVersion": 1,
        "application": "Retro Web UI GUI",
        "version": VERSION,
        "platform": system,
    }
    for key, value in expected_metadata.items():
        if inventory.get(key) != value:
            raise RuntimeError(f"Native component inventory {key} mismatch: {inventory.get(key)!r}")
    entries = inventory["files"]
    expected: dict[str, dict[str, object]] = {}
    for entry in entries:
        if not isinstance(entry, dict) or entry.get("type") != "file" or not isinstance(entry.get("path"), str):
            raise RuntimeError("Native component inventory must contain regular files only.")
        expected[str(entry["path"])] = entry
    if len(entries) != len(expected):
        raise RuntimeError("Native component inventory contains duplicate paths.")
    if set(expected) != set(actual_files):
        raise RuntimeError("Native component inventory paths do not match packaged product files.")
    for relative, entry in expected.items():
        data = read_file(actual_files[relative])
        if entry.get("bytes") != len(data) or entry.get("sha256") != hashlib.sha256(data).hexdigest():
            raise RuntimeError(f"Native component inventory digest mismatch: {relative}")


def linux_abi_versions(product: Path) -> dict[str, str | None]:
    """Record external GNU ABI requirements from ELF version-reference tables."""
    patterns = {
        "glibc": re.compile(rb"GLIBC_([0-9]+(?:\.[0-9]+)+)"),
        "glibcxx": re.compile(rb"GLIBCXX_([0-9]+(?:\.[0-9]+)+)"),
        "cxxabi": re.compile(rb"CXXABI_([0-9]+(?:\.[0-9]+)+)"),
    }
    found: dict[str, set[tuple[int, ...]]] = {key: set() for key in patterns}
    for path in product.rglob("*"):
        if not path.is_file():
            continue
        with path.open("rb") as stream:
            if stream.read(4) != b"\x7fELF":
                continue
        data = run(["readelf", "--version-info", "--wide", str(path)], timeout=60).stdout.encode("utf-8")
        for key, pattern in patterns.items():
            for match in pattern.findall(data):
                found[key].add(tuple(int(part) for part in match.decode("ascii").split(".")))
    return {
        key: ".".join(map(str, max(versions))) if versions else None
        for key, versions in found.items()
    }


def write_checksum_file(artifact: Path, digest: str) -> Path:
    """Write a portable sha256sum manifest with an explicit LF terminator."""
    checksum = artifact.with_name(artifact.name + ".sha256")
    checksum.write_bytes(f"{digest}  {artifact.name}\n".encode("ascii"))
    return checksum


def sign_and_verify_macos_bundle(product: Path) -> None:
    """Seal all bundled code and package data with a verified ad-hoc signature."""
    run(["codesign", "--force", "--deep", "--sign", "-", str(product)], timeout=300)
    run(["codesign", "--verify", "--deep", "--strict", "--verbose=2", str(product)], timeout=300)


def verify_macos_archive_signature(artifact: Path, destination: Path) -> None:
    """Re-extract the deliverable and verify the signature users receive."""
    destination.mkdir(parents=True, exist_ok=True)
    run(["ditto", "-x", "-k", str(artifact), str(destination)], timeout=300)
    applications = sorted(destination.rglob("*.app"))
    if len(applications) != 1:
        raise RuntimeError(f"Expected one archived macOS app bundle, found: {applications}")
    run(
        ["codesign", "--verify", "--deep", "--strict", "--verbose=2", str(applications[0])],
        timeout=300,
    )


def verify_delivered_archive(
    artifact: Path,
    destination: Path,
    system: str,
    *,
    app_server_smoke: bool = False,
) -> tuple[str, dict[str, object]]:
    """Extract and execute the exact archive that will be delivered to users."""
    destination.mkdir(parents=True, exist_ok=True)
    if system == "macos":
        run(["ditto", "-x", "-k", str(artifact), str(destination)], timeout=300)
    elif system == "windows":
        with zipfile.ZipFile(artifact) as archive:
            archive.extractall(destination)
    else:
        with tarfile.open(artifact, "r:gz") as archive:
            archive.extractall(destination, filter="data")
    root = destination / ("retro-web-ui-gui" if system == "linux" else "Retro Web UI GUI")
    executable = (
        root / "Retro Web UI GUI.app" / "Contents" / "MacOS" / "retro-web-ui-gui"
        if system == "macos"
        else root / ("retro-web-ui-gui.exe" if system == "windows" else "retro-web-ui-gui")
    )
    if not executable.is_file():
        raise RuntimeError(f"Delivered archive launcher is missing: {executable}")
    if system == "macos":
        run(["codesign", "--verify", "--deep", "--strict", "--verbose=2", str(root / "Retro Web UI GUI.app")], timeout=300)
    environment = dict(os.environ)
    environment["QT_QPA_PLATFORM"] = "offscreen"
    isolated_home = destination / "isolated-home"
    isolated_home.mkdir()
    environment["HOME"] = str(isolated_home)
    environment["XDG_CONFIG_HOME"] = str(isolated_home / ".config")
    for inherited in ("PYTHONHOME", "PYTHONPATH", "QT_PLUGIN_PATH", "QML2_IMPORT_PATH"):
        environment.pop(inherited, None)
    if system == "windows":
        environment["USERPROFILE"] = str(isolated_home)
        for name, relative in {
            "APPDATA": "AppData/Roaming",
            "LOCALAPPDATA": "AppData/Local",
            "TEMP": "Temp",
            "TMP": "Temp",
        }.items():
            location = isolated_home / relative
            location.mkdir(parents=True, exist_ok=True)
            environment[name] = str(location)
    version_output = run([str(executable), "--version"], env=environment, timeout=60).stdout.strip()
    expected_version = f"Retro Web UI GUI {VERSION}"
    if version_output != expected_version:
        raise RuntimeError(f"Delivered GUI version mismatch: expected {expected_version!r}, found {version_output!r}")
    smoke_args = [str(executable), "--smoke"]
    if app_server_smoke:
        smoke_args.append("--app-server-smoke")
    smoke_output = run(smoke_args, env=environment, timeout=180).stdout.strip().splitlines()
    try:
        smoke = json.loads(smoke_output[-1])
    except (IndexError, json.JSONDecodeError) as error:
        raise RuntimeError("Delivered GUI smoke did not return a valid JSON result.") from error
    required = {
        "status": "ok",
        "version": VERSION,
        "coreStatus": "ok",
        "manifestCompatible": True,
        "skillAvailable": True,
        "windowVisible": True,
    }
    mismatches = {key: {"expected": value, "actual": smoke.get(key)} for key, value in required.items() if smoke.get(key) != value}
    if app_server_smoke and smoke.get("appServer") != "ready":
        mismatches["appServer"] = {"expected": "ready", "actual": smoke.get("appServer")}
    if mismatches:
        raise RuntimeError(f"Delivered GUI smoke contract failed: {mismatches}")
    return version_output, smoke


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
    installed_version = getattr(retro_web_ui, "__version__", None)
    if installed_version != VERSION:
        raise RuntimeError(
            f"Native release build requires installed retro-web-ui {VERSION}; found {installed_version!r}. "
            "Reinstall the current checkout with: python -m pip install --force-reinstall '.[native]'"
        )
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
            "--output-filename=retro-web-ui-gui",
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
        if system == "macos":
            set_macos_bundle_metadata(product)
        abi_versions = linux_abi_versions(product) if system == "linux" else None
        if abi_versions and abi_versions.get("glibc"):
            required_glibc = tuple(int(part) for part in str(abi_versions["glibc"]).split("."))
            if required_glibc > LINUX_GLIBC_CEILING:
                raise RuntimeError(
                    f"Linux artifact requires GLIBC_{abi_versions['glibc']}; "
                    f"the supported build ceiling is GLIBC_{'.'.join(map(str, LINUX_GLIBC_CEILING))}."
                )
        extension = ".tar.gz" if system == "linux" else ".zip"
        staged_root, license_bundle = stage_product(product, work / "archive", system)
        if system == "macos":
            sign_and_verify_macos_bundle(staged_root / "Retro Web UI GUI.app")
        artifact = archive_product(
            staged_root,
            output / f"retro-web-ui-gui-{VERSION}-{system}-{machine}{extension}",
            system,
        )
        validate_archive_layout(artifact, system)
        validate_archive_licenses(artifact)
        validate_archive_inventory(artifact, system)
        version_output, smoke_result = verify_delivered_archive(
            artifact,
            work / "delivered-check",
            system,
            app_server_smoke=args.app_server_smoke,
        )
        digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
        write_checksum_file(artifact, digest)
        report = {
            "version": VERSION,
            "platform": system,
            "architecture": machine,
            "python": platform.python_version(),
            "artifact": artifact.name,
            "artifactBytes": artifact.stat().st_size,
            "installedBytes": sum(path.stat().st_size for path in staged_root.rglob("*") if path.is_file()),
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
            "signing": "ad-hoc-verified" if system == "macos" else "unsigned" if system == "windows" else "not-applicable",
            "versionOutput": version_output,
            "smoke": smoke_result,
        }
        if abi_versions is not None:
            report["linuxAbi"] = abi_versions
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
