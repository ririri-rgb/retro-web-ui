from __future__ import annotations

import hashlib
import json
import plistlib
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

from scripts.build_native import (
    archive_product,
    BUNDLE_IDENTIFIER,
    VERSION,
    find_product,
    linux_abi_versions,
    set_macos_bundle_metadata,
    sign_and_verify_macos_bundle,
    stage_product,
    validate_archive_layout,
    validate_archive_licenses,
    validate_archive_inventory,
    verify_delivered_archive,
    verify_macos_archive_signature,
    write_component_inventory,
    write_checksum_file,
)


class NativePackagingTests(unittest.TestCase):
    def test_macos_metadata_has_stable_identity_and_aligned_versions(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            bundle = Path(temporary) / "Retro Web UI GUI.app"
            plist = bundle / "Contents" / "Info.plist"
            plist.parent.mkdir(parents=True)
            with plist.open("wb") as stream:
                plistlib.dump({"CFBundleIdentifier": "Retro Web UI GUI"}, stream)

            set_macos_bundle_metadata(bundle)

            with plist.open("rb") as stream:
                document = plistlib.load(stream)
            self.assertEqual(document["CFBundleIdentifier"], BUNDLE_IDENTIFIER)
            self.assertEqual(document["CFBundleShortVersionString"], document["CFBundleVersion"])

    def test_macos_bundle_is_resealed_and_strictly_verified(self) -> None:
        bundle = Path("/tmp/Retro Web UI GUI.app")
        with mock.patch("scripts.build_native.run") as runner:
            sign_and_verify_macos_bundle(bundle)

        self.assertEqual(
            [call.args[0] for call in runner.call_args_list],
            [
                ["codesign", "--force", "--deep", "--sign", "-", str(bundle)],
                ["codesign", "--verify", "--deep", "--strict", "--verbose=2", str(bundle)],
            ],
        )

    def test_macos_inventory_can_be_refreshed_after_signing_mutates_executable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            application = root / "Retro Web UI GUI.app"
            executable = application / "Contents" / "MacOS" / "retro-web-ui-gui"
            executable.parent.mkdir(parents=True)
            executable.write_bytes(b"unsigned")
            inventory_path = root / "NATIVE_COMPONENTS.json"

            write_component_inventory(application, inventory_path, "macos")
            executable.write_bytes(b"signed")
            write_component_inventory(application, inventory_path, "macos")

            inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
            launcher = next(entry for entry in inventory["files"] if entry["path"] == "Contents/MacOS/retro-web-ui-gui")
            self.assertEqual(launcher["bytes"], len(b"signed"))
            self.assertEqual(
                launcher["sha256"],
                hashlib.sha256(b"signed").hexdigest(),
            )

    def test_macos_archive_is_reextracted_before_signature_verification(self) -> None:
        artifact = Path("/tmp/retro-web-ui-gui-2.0.0-macos-arm64.zip")
        destination = Path("/tmp/signature-check")
        application = destination / "Retro Web UI GUI" / "Retro Web UI GUI.app"
        with (
            mock.patch("scripts.build_native.run") as runner,
            mock.patch.object(Path, "mkdir"),
            mock.patch.object(Path, "rglob", return_value=[application]),
        ):
            verify_macos_archive_signature(artifact, destination)

        self.assertEqual(
            [call.args[0] for call in runner.call_args_list],
            [
                ["ditto", "-x", "-k", str(artifact), str(destination)],
                ["codesign", "--verify", "--deep", "--strict", "--verbose=2", str(application)],
            ],
        )

    def test_checksum_manifest_uses_portable_lf_line_ending(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            artifact = Path(temporary) / "retro-web-ui-gui-2.0.0-windows-x86_64.zip"
            artifact.write_bytes(b"native")
            checksum = write_checksum_file(artifact, "a" * 64)

            self.assertEqual(
                checksum.read_bytes(),
                ("a" * 64 + "  retro-web-ui-gui-2.0.0-windows-x86_64.zip\n").encode("ascii"),
            )
            self.assertNotIn(b"\r", checksum.read_bytes())

    def test_windows_and_linux_archives_include_license_bundle_and_inventory(self) -> None:
        for system, extension in (("windows", ".zip"), ("linux", ".tar.gz")):
            with self.subTest(system=system), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                product = root / "launcher.dist"
                product.mkdir()
                executable_name = "retro-web-ui-gui.exe" if system == "windows" else "retro-web-ui-gui"
                (product / executable_name).write_bytes(b"native")
                (product / "QtCore.dll").write_bytes(b"qt")
                found_product, found_executable = find_product(root, system)
                self.assertEqual(found_product, product)
                self.assertEqual(found_executable, product / executable_name)

                staged, license_bundle = stage_product(product, root / "stage", system)
                artifact = archive_product(staged, root / f"candidate{extension}", system)
                validate_archive_layout(artifact, system)
                validate_archive_licenses(artifact)
                validate_archive_inventory(artifact, system)

                self.assertIn("LGPL-3.0-only.txt", license_bundle)
                self.assertTrue((staged / "INSTALL.md").is_file())
                inventory = json.loads((staged / "LICENSES" / "NATIVE_COMPONENTS.json").read_text(encoding="utf-8"))
                self.assertEqual(inventory["platform"], system)
                self.assertEqual(
                    {entry["path"] for entry in inventory["files"]},
                    {"QtCore.dll", executable_name},
                )

    def test_archive_layout_rejects_traversal_and_case_insensitive_collisions(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            traversal = root / "traversal.zip"
            with __import__("zipfile").ZipFile(traversal, "w") as archive:
                archive.writestr("../outside", b"bad")
            with self.assertRaisesRegex(RuntimeError, "unsafe member path"):
                validate_archive_layout(traversal, "windows")

            for system in ("windows", "macos"):
                with self.subTest(system=system):
                    collision = root / f"collision-{system}.zip"
                    with __import__("zipfile").ZipFile(collision, "w") as archive:
                        archive.writestr("Retro Web UI GUI/INSTALL.md", b"install")
                        archive.writestr("Retro Web UI GUI/Readme.txt", b"one")
                        archive.writestr("Retro Web UI GUI/README.TXT", b"two")
                    with self.assertRaisesRegex(RuntimeError, "case-insensitive"):
                        validate_archive_layout(collision, system)

    def test_macos_archive_allows_ditto_metadata_only_outside_application_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            artifact = Path(temporary) / "mac.zip"
            with __import__("zipfile").ZipFile(artifact, "w") as archive:
                archive.writestr("Retro Web UI GUI/INSTALL.md", b"install")
                archive.writestr(
                    "Retro Web UI GUI/Retro Web UI GUI.app/Contents/MacOS/retro-web-ui-gui",
                    b"exe",
                )
                archive.writestr("__MACOSX/Retro Web UI GUI/._INSTALL.md", b"metadata")
            validate_archive_layout(artifact, "macos")

    def test_exact_delivered_archive_is_extracted_and_smoked(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact = root / "windows.zip"
            with __import__("zipfile").ZipFile(artifact, "w") as archive:
                archive.writestr("Retro Web UI GUI/retro-web-ui-gui.exe", b"native")
            responses = [
                SimpleNamespace(stdout=f"Retro Web UI GUI {VERSION}\n"),
                SimpleNamespace(stdout=json.dumps({
                    "status": "ok", "version": VERSION, "coreStatus": "ok",
                    "manifestCompatible": True, "skillAvailable": True,
                    "windowVisible": True, "appServer": "ready",
                }) + "\n"),
                SimpleNamespace(stdout=json.dumps({
                    "phase": "created", "state": "running", "artifactSha256": "abc",
                }) + "\n"),
                SimpleNamespace(stdout=json.dumps({
                    "phase": "restored", "state": "transport_lost",
                    "projectAvailability": "available", "artifactIntegrity": "available",
                    "artifactSha256": "abc", "privacyScan": "clean", "windowVisible": True,
                    "projectHistoryCount": 1, "sessionHistoryCount": 1,
                    "workspaceRoot": str(root / "extracted" / "isolated-home" / "AppData" / "Local" / "Retro Web UI"),
                }) + "\n"),
            ]
            with mock.patch("scripts.build_native.run", side_effect=responses) as runner:
                version, smoke, lifecycle = verify_delivered_archive(
                    artifact, root / "extracted", "windows", app_server_smoke=True
                )
            self.assertEqual(version, f"Retro Web UI GUI {VERSION}")
            self.assertEqual(smoke["appServer"], "ready")
            self.assertEqual(lifecycle["restore"]["privacyScan"], "clean")
            self.assertIn("--app-server-smoke", runner.call_args_list[1].args[0])
            self.assertIn("--workspace-lifecycle-smoke", runner.call_args_list[2].args[0])

    def test_linux_abi_versions_are_derived_from_bundled_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            product = Path(temporary)
            (product / "binary").write_bytes(b"\x7fELFfake")
            (product / "documentation.txt").write_text("GLIBC_9.99", encoding="utf-8")
            table = SimpleNamespace(stdout="GLIBC_2.17 GLIBC_2.35 GLIBCXX_3.4.29 CXXABI_1.3.13")
            with mock.patch("scripts.build_native.run", return_value=table) as reader:
                self.assertEqual(linux_abi_versions(product), {
                    "glibc": "2.35", "glibcxx": "3.4.29", "cxxabi": "1.3.13",
                })
            self.assertEqual(reader.call_args.args[0][:3], ["readelf", "--version-info", "--wide"])


if __name__ == "__main__":
    unittest.main()
