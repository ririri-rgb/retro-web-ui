from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from scripts.build_native import (
    archive_product,
    find_product,
    sign_and_verify_macos_bundle,
    stage_product,
    validate_archive_licenses,
    write_checksum_file,
)


class NativePackagingTests(unittest.TestCase):
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
                validate_archive_licenses(artifact)

                self.assertIn("LGPL-3.0-only.txt", license_bundle)
                inventory = json.loads((staged / "LICENSES" / "NATIVE_COMPONENTS.json").read_text(encoding="utf-8"))
                self.assertEqual(inventory["platform"], system)
                self.assertEqual(
                    {entry["path"] for entry in inventory["files"]},
                    {"QtCore.dll", executable_name},
                )


if __name__ == "__main__":
    unittest.main()
