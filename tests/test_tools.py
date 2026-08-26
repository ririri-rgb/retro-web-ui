from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "retro-web-ui"
SCRIPTS = SKILL / "scripts"
FIXTURES = ROOT / "tests" / "fixtures"


def load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


inspect_project = load("inspect_project")
bundle_theme = load("bundle_theme")
behavior_guard = load("behavior_guard")
audit_ui = load("audit_ui")


class ProjectDetectionTests(unittest.TestCase):
    def test_static_html(self):
        result = inspect_project.detect(FIXTURES / "static-html")
        self.assertEqual(result["frameworks"][0]["name"], "static-html-or-vanilla")

    def test_react_tailwind_and_commands(self):
        result = inspect_project.detect(FIXTURES / "react-vite")
        names = {item["name"] for item in result["frameworks"]}
        styling = {item["name"] for item in result["styling"]}
        self.assertTrue({"react", "vite"}.issubset(names))
        self.assertIn("tailwind", styling)
        self.assertIn("build", result["verification_commands"])
        self.assertEqual(result["verification_commands"]["build"][0]["cwd"], ".")

    def test_vue_bootstrap(self):
        result = inspect_project.detect(FIXTURES / "vue-vite")
        self.assertIn("vue", {item["name"] for item in result["frameworks"]})
        self.assertIn("bootstrap", {item["name"] for item in result["styling"]})

    def test_meta_frameworks(self):
        svelte = inspect_project.detect(FIXTURES / "svelte-kit")
        next_result = inspect_project.detect(FIXTURES / "next-tailwind")
        self.assertIn("sveltekit", {item["name"] for item in svelte["frameworks"]})
        self.assertIn("next", {item["name"] for item in next_result["frameworks"]})
        self.assertIn("radix-shadcn", {item["name"] for item in next_result["styling"]})

    def test_bootstrap_binding_risk(self):
        result = inspect_project.detect(FIXTURES / "bootstrap-dashboard")
        self.assertIn("bootstrap-js-bindings", {item["name"] for item in result["risk_signals"]})

    def test_mixed_monorepo_commands_keep_manager_and_cwd(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "package.json").write_text('{"name":"root","scripts":{"build":"root-build"}}', encoding="utf-8")
            (root / "package-lock.json").write_text('{}', encoding="utf-8")
            child = root / "packages" / "child"
            child.mkdir(parents=True)
            (child / "package.json").write_text('{"name":"child","scripts":{"build":"child-build"}}', encoding="utf-8")
            (child / "yarn.lock").write_text("# fixture", encoding="utf-8")
            result = inspect_project.detect(root)
            commands = {(item["cwd"], item["command"]) for item in result["verification_commands"]["build"]}
            self.assertEqual(commands, {(".", "npm run build"), ("packages/child", "yarn build")})


class ThemeBundleTests(unittest.TestCase):
    def test_all_themes_are_scoped_and_structurally_distinct(self):
        bundles = {theme: bundle_theme.build(theme) for theme in bundle_theme.THEMES}
        self.assertEqual(len(set(bundles.values())), 4)
        for theme, content in bundles.items():
            self.assertIn(f'[data-retro-theme="{theme}"]', content)
            self.assertIn(".retro-window", content)
            self.assertIn(")[hidden]", content.replace(" ", ""))
            self.assertNotIn("data:image", content)
        self.assertIn("inset -1px -1px", bundles["windows-98"])
        self.assertIn("#e68b2c", bundles["windows-xp"])
        self.assertIn(".retro-command-link", bundles["windows-7"])
        self.assertIn(".retro-log", bundles["japanese-freeware-2000s"])

    def test_deterministic_write_and_check(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "theme.css"
            expected = bundle_theme.build("windows-7")
            output.write_text(expected, encoding="utf-8")
            self.assertEqual(output.read_text(encoding="utf-8"), expected)

    def test_cli_refuses_unreviewed_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "theme.css"
            output.write_text("user content", encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(SCRIPTS / "bundle_theme.py"), "windows-98", "--output", str(output)],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 2)
            self.assertEqual(output.read_text(encoding="utf-8"), "user content")


class BehaviorGuardTests(unittest.TestCase):
    def test_css_only_change_does_not_change_signals(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "app"
            shutil.copytree(FIXTURES / "static-html", target)
            before = behavior_guard.snapshot(target)
            (target / "retro.css").write_text("body { color: red; }", encoding="utf-8")
            result = behavior_guard.compare(before, behavior_guard.snapshot(target))
            self.assertEqual(result["status"], "unchanged")

    def test_import_before_unchanged_handler_does_not_change_signal(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "app"
            shutil.copytree(FIXTURES / "static-html", target)
            before = behavior_guard.snapshot(target)
            app = target / "app.js"
            app.write_text("import './retro.css';\n" + app.read_text(encoding="utf-8"), encoding="utf-8")
            result = behavior_guard.compare(before, behavior_guard.snapshot(target))
            self.assertEqual(result["status"], "unchanged")

    def test_class_after_unchanged_jsx_handler_does_not_change_signal(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "app"
            shutil.copytree(FIXTURES / "react-vite", target)
            before = behavior_guard.snapshot(target)
            app = target / "src" / "App.jsx"
            app.write_text(app.read_text(encoding="utf-8").replace('type="button" onClick=', 'type="button" className="retro-button" onClick='), encoding="utf-8")
            result = behavior_guard.compare(before, behavior_guard.snapshot(target))
            self.assertEqual(result["status"], "unchanged")

    def test_removed_handler_requires_review(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "app"
            shutil.copytree(FIXTURES / "static-html", target)
            before = behavior_guard.snapshot(target)
            (target / "app.js").write_text("console.log('visual only');", encoding="utf-8")
            result = behavior_guard.compare(before, behavior_guard.snapshot(target))
            self.assertEqual(result["status"], "review-required")
            self.assertGreater(result["removed_signal_count"], 0)

    def test_snapshot_contains_no_literal_storage_value(self):
        data = json.dumps(behavior_guard.snapshot(FIXTURES / "static-html"))
        self.assertNotIn("last-item", data)

    def test_incompatible_baseline_algorithm_is_rejected(self):
        before = behavior_guard.snapshot(FIXTURES / "static-html")
        before["signal_algorithm"] = "sha256-normalized-window-v1"
        result = behavior_guard.compare(before, behavior_guard.snapshot(FIXTURES / "static-html"))
        self.assertEqual(result["status"], "incompatible-baseline")


class AuditTests(unittest.TestCase):
    def test_integrated_fixture_has_no_high_findings(self):
        result = audit_ui.audit(FIXTURES / "static-html", "windows-98")
        self.assertFalse(any(item["severity"] == "high" for item in result["findings"]))

    def test_direct_theme_kit_import_is_recognized(self):
        result = audit_ui.audit(FIXTURES / "react-vite", "japanese-freeware-2000s")
        self.assertFalse(any(item["severity"] == "high" for item in result["findings"]))

    def test_modern_residue_is_reported(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "index.html").write_text('<main data-retro-theme="windows-7" class="card"></main>', encoding="utf-8")
            (root / "theme.css").write_text('/* retro-web-ui theme=windows-7 */ .card{border-radius:24px}', encoding="utf-8")
            result = audit_ui.audit(root, "windows-7")
            checks = {item["check"] for item in result["findings"]}
            self.assertIn("large-radius", checks)
            self.assertIn("modern-card-name", checks)


class RepositoryTests(unittest.TestCase):
    def test_distributable_skill_contains_license(self):
        self.assertEqual((SKILL / "LICENSE").read_text(encoding="utf-8"), (ROOT / "LICENSE").read_text(encoding="utf-8"))

    def test_skill_has_no_placeholders(self):
        for path in SKILL.rglob("*"):
            if path.is_file() and path.suffix in {".md", ".yaml", ".py", ".css"}:
                self.assertNotIn("TODO", path.read_text(encoding="utf-8"))

    def test_skill_links_resolve(self):
        skill_text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        import re
        for target in re.findall(r"\[[^]]+\]\(([^)]+)\)", skill_text):
            if "://" not in target and not target.endswith("/"):
                self.assertTrue((SKILL / target).exists(), target)

    def test_repository_validator(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "quick_validate_compat.py"), str(SKILL)],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_release_archive_excludes_hidden_metadata(self):
        with tempfile.TemporaryDirectory() as temp:
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "package_skill.py"), "--output", temp],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            archive = next(Path(temp).glob("*.zip"))
            with zipfile.ZipFile(archive) as source:
                names = source.namelist()
            self.assertIn("retro-web-ui/LICENSE", names)
            self.assertFalse(any(Path(name).name.startswith(".") for name in names))


if __name__ == "__main__":
    unittest.main()
