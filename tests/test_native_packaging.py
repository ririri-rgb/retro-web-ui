from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from scripts.build_native import archive_product, find_product, stage_product, validate_archive_licenses


class NativePackagingTests(unittest.TestCase):
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
