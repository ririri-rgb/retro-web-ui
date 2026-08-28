from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from scripts.build_native import archive_product, stage_product, validate_archive_licenses


class NativePackagingTests(unittest.TestCase):
    def test_windows_and_linux_archives_include_license_bundle_and_inventory(self) -> None:
        for system, extension in (("windows", ".zip"), ("linux", ".tar.gz")):
            with self.subTest(system=system), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                product = root / "launcher.dist"
                product.mkdir()
                (product / ("launcher.exe" if system == "windows" else "launcher.bin")).write_bytes(b"native")
                (product / "QtCore.dll").write_bytes(b"qt")

                staged, license_bundle = stage_product(product, root / "stage", system)
                artifact = archive_product(staged, root / f"candidate{extension}", system)
                validate_archive_licenses(artifact)

                self.assertIn("LGPL-3.0-only.txt", license_bundle)
                inventory = json.loads((staged / "LICENSES" / "NATIVE_COMPONENTS.json").read_text(encoding="utf-8"))
                self.assertEqual(inventory["platform"], system)
                self.assertEqual(
                    {entry["path"] for entry in inventory["files"]},
                    {"QtCore.dll", "launcher.exe"} if system == "windows" else {"QtCore.dll", "launcher.bin"},
                )


if __name__ == "__main__":
    unittest.main()
