from __future__ import annotations

import hashlib
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
CLI = SCRIPTS / "retro_web_ui.py"


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
        self.assertIn("request-time-ssr", {item["name"] for item in next_result["rendering_models"]})
        self.assertIn("client-islands", {item["name"] for item in next_result["rendering_models"]})
        self.assertIn("portals-or-overlays", {item["name"] for item in next_result["component_architecture"]})
        self.assertIn("static-generation-or-prerender", {item["name"] for item in svelte["rendering_models"]})

    def test_mui_emotion_portal_and_controlled_architecture(self):
        result = inspect_project.detect(FIXTURES / "react-mui")
        styling = {item["name"] for item in result["styling"]}
        architecture = {item["name"] for item in result["component_architecture"]}
        self.assertTrue({"mui", "emotion"}.issubset(styling))
        self.assertTrue({"portals-or-overlays", "controlled-or-two-way-binding"}.issubset(architecture))

    def test_naive_ui_scoped_async_route_and_virtualized_architecture(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "package.json").write_text(
                json.dumps({
                    "dependencies": {
                        "vue": "3.5.0",
                        "naive-ui": "2.0.0",
                        "vue-router": "4.0.0",
                        "vue-virtual-scroller": "2.0.0",
                    }
                }),
                encoding="utf-8",
            )
            (root / "App.vue").write_text(
                "<script setup>const Page = defineAsyncComponent(() => import('./Page.vue'))</script>"
                "<template><RouterView /><NDialog /><input v-model=\"name\"></template>"
                "<style scoped>.panel { display: block }</style>",
                encoding="utf-8",
            )
            result = inspect_project.detect(root)
            styling = {item["name"] for item in result["styling"]}
            rendering = {item["name"] for item in result["rendering_models"]}
            architecture = {item["name"] for item in result["component_architecture"]}
            self.assertTrue({"naive-ui", "scoped-css"}.issubset(styling))
            self.assertIn("async-loaded-ui", rendering)
            self.assertTrue({"controlled-or-two-way-binding", "route-driven-ui", "virtualized-ui"}.issubset(architecture))

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

    def test_package_manager_metadata_supports_bun_without_installing_it(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "package.json").write_text(
                json.dumps({"packageManager": "bun@1.2.0", "scripts": {"build": "vite build"}, "dependencies": {"vite": "8.0.0"}}),
                encoding="utf-8",
            )
            result = inspect_project.detect(root)
            self.assertEqual(result["package_manager"], None)
            self.assertEqual(result["packages"][0]["package_manager"], "bun")
            self.assertEqual(result["verification_commands"]["build"][0]["command"], "bun run build")

    def test_symlinked_source_outside_target_is_not_scanned(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            target = root / "target"
            target.mkdir()
            outside = root / "outside.jsx"
            outside.write_text("import React from 'react'; export default () => <main/>;", encoding="utf-8")
            try:
                (target / "App.jsx").symlink_to(outside)
            except OSError as error:
                self.skipTest(f"symlink unavailable: {error}")
            result = inspect_project.detect(target)
            self.assertNotIn("react", {item["name"] for item in result["frameworks"]})
            self.assertEqual(behavior_guard.snapshot(target)["files"], {})


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
    def compare_source(self, before_source: str, after_source: str, suffix: str = ".tsx"):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "app"
            target.mkdir()
            source = target / f"App{suffix}"
            source.write_text(before_source, encoding="utf-8")
            before = behavior_guard.snapshot(target)
            source.write_text(after_source, encoding="utf-8")
            return behavior_guard.compare(before, behavior_guard.snapshot(target))

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

    def test_multiline_framework_event_bindings_are_protected(self):
        cases = [
            ("<button onClick={() => {\n save();\n}}>Save</button>", "<button>Save</button>", ".tsx"),
            ('<button @click="\n save()\n">Save</button>', "<button>Save</button>", ".vue"),
            ("<button on:click|preventDefault={\n save\n}>Save</button>", "<button>Save</button>", ".svelte"),
            ("<button onclick={save}>Save</button>", "<button>Save</button>", ".svelte"),
            ('<button (click)="save()">Save</button>', "<button>Save</button>", ".html"),
            ('<button onclick="save()">Save</button>', "<button>Save</button>", ".html"),
            ("button.onclick = save;", "button.textContent = 'Save';", ".ts"),
        ]
        for before, after, suffix in cases:
            with self.subTest(before=before):
                result = self.compare_source(before, after, suffix)
                self.assertEqual(result["status"], "review-required")
                self.assertGreater(result["removed_signal_count"], 0)

    def test_unquoted_route_and_form_contract_are_protected(self):
        before = "<a href=/admin/delete>Delete</a><form action=/wipe><input name=role value=user></form>"
        after = "<a>Delete</a><form><input name=role value=admin></form>"
        result = self.compare_source(before, after, ".html")
        changed = {item["signal"] for item in result["protected_signal_changes"]}
        self.assertIn("routing", changed)
        self.assertIn("form-contract", changed)

    def test_state_transition_alias_timer_accessibility_and_selector_are_protected(self):
        before = """
        let submit = saveDraft;
        const save = () => setOpen(true);
        setTimeout(save, 200);
        <button aria-pressed={open} data-testid="save" onClick={save}>Save</button>
        """
        after = """
        let submit = deleteAccount;
        const save = () => setOpen(false);
        <button onClick={save}>Save</button>
        """
        result = self.compare_source(before, after)
        changed = {item["signal"] for item in result["protected_signal_changes"]}
        self.assertTrue({"behavior-alias", "state-transition", "timer-subscription", "accessibility-contract", "test-selector"}.issubset(changed))

    def test_history_api_change_is_protected(self):
        result = self.compare_source(
            "history.pushState({}, '', '/safe');",
            "history.pushState({}, '', '/delete');",
            ".js",
        )
        self.assertEqual(result["status"], "review-required")

    def test_auth_words_in_comments_are_ignored(self):
        result = self.compare_source(
            "export const value = 1;",
            "// login layout only\nexport const value = 1;",
            ".js",
        )
        self.assertEqual(result["status"], "unchanged")

    def test_auth_words_in_url_and_header_strings_are_protected(self):
        result = self.compare_source(
            "fetch('https://example.test/login', { headers: { Authorization: 'Bearer one' } });",
            "fetch('https://example.test/public');",
            ".js",
        )
        changed = {item["signal"] for item in result["protected_signal_changes"]}
        self.assertIn("auth", changed)
        self.assertIn("network", changed)


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


class UnifiedCLITests(unittest.TestCase):
    def run_cli(self, *arguments: str):
        result = subprocess.run(
            [sys.executable, str(CLI), *arguments],
            capture_output=True,
            text=True,
        )
        document = json.loads(result.stdout)
        return result, document

    def test_info_has_stable_envelope_and_matching_manifest(self):
        result, document = self.run_cli("info", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(document["schema_version"], 1)
        self.assertEqual(document["tool"]["name"], "retro-web-ui")
        self.assertEqual(document["tool"]["version"], "1.1.0")
        self.assertTrue(document["result"]["manifest_compatible"])
        self.assertEqual(len(document["result"]["theme_bundle_sha256"]), 4)

    def test_manifest_mismatch_is_contract_error(self):
        with tempfile.TemporaryDirectory() as temp:
            manifest = json.loads((SKILL / "manifest.json").read_text(encoding="utf-8"))
            manifest["required_cli_api"]["max"] = 0
            path = Path(temp) / "manifest.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            result, document = self.run_cli("info", "--manifest", str(path), "--json")
            self.assertEqual(result.returncode, 3)
            self.assertEqual(document["status"], "incompatible")
            self.assertIn("CLI_API_MISMATCH", {item["code"] for item in document["diagnostics"]})

    def test_monorepo_requires_selection_and_preserves_manager_argv(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "package.json").write_text(
                json.dumps({"name": "workspace", "private": True, "packageManager": "pnpm@9.1.0", "workspaces": ["apps/*"]}),
                encoding="utf-8",
            )
            for name in ("admin", "public"):
                app = root / "apps" / name
                app.mkdir(parents=True)
                (app / "package.json").write_text(
                    json.dumps({"name": name, "scripts": {"build": "vite build"}, "dependencies": {"react": "19.0.0", "vite": "8.0.0"}}),
                    encoding="utf-8",
                )
                (app / "App.jsx").write_text("export default function App(){return <main/>}", encoding="utf-8")
            vanilla = root / "apps" / "vanilla"
            vanilla.mkdir(parents=True)
            (vanilla / "package.json").write_text(json.dumps({"name": "vanilla"}), encoding="utf-8")
            (vanilla / "index.html").write_text("<main>Vanilla</main>", encoding="utf-8")
            ambiguous, ambiguous_document = self.run_cli("analyze", str(root), "--json")
            self.assertEqual(ambiguous.returncode, 1)
            self.assertEqual(ambiguous_document["status"], "review_required")
            self.assertIn("APP_SELECTION_REQUIRED", {item["code"] for item in ambiguous_document["diagnostics"]})
            candidate_paths = {item["path"] for item in ambiguous_document["result"]["selection"]["candidates"]}
            self.assertEqual(candidate_paths, {"apps/admin", "apps/public", "apps/vanilla"})
            selected, selected_document = self.run_cli("analyze", str(root), "--app", "apps/admin", "--json")
            self.assertEqual(selected.returncode, 0, selected.stderr)
            selection = selected_document["result"]["selection"]
            self.assertEqual(selection["selected"]["path"], "apps/admin")
            plan = selected_document["result"]["verification_plan"]
            self.assertEqual(plan[0]["argv"], ["pnpm", "build"])

    def test_invalid_app_is_structured_error(self):
        result, document = self.run_cli("analyze", str(FIXTURES / "react-vite"), "--app", "missing", "--json")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(document["status"], "error")
        self.assertEqual(document["diagnostics"][0]["code"], "APP_NOT_FOUND")

    def test_usage_error_is_json_when_requested(self):
        result, document = self.run_cli("theme", "bundle", "not-a-theme", "--json")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(document["status"], "error")
        self.assertEqual(document["diagnostics"][0]["code"], "USAGE_ERROR")

    def test_human_input_error_has_no_traceback(self):
        result = subprocess.run(
            [sys.executable, str(CLI), "analyze", "/definitely/not/a/retro-web-ui-target"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("TARGET_NOT_DIRECTORY", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_behavior_artifact_is_explicit_idempotent_and_non_overwriting(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            target = root / "app"
            target.mkdir()
            source = target / "App.jsx"
            source.write_text("<button onClick={save}>Save</button>", encoding="utf-8")
            output = root / "baseline.json"
            first, first_document = self.run_cli("behavior", "snapshot", str(target), "--output", str(output), "--json")
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(first_document["result"]["action"], "written")
            original = output.read_text(encoding="utf-8")
            second, second_document = self.run_cli("behavior", "snapshot", str(target), "--output", str(output), "--json")
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(second_document["result"]["action"], "current")
            source.write_text("<button>Save</button>", encoding="utf-8")
            refused, refused_document = self.run_cli("behavior", "snapshot", str(target), "--output", str(output), "--json")
            self.assertEqual(refused.returncode, 2)
            self.assertEqual(refused_document["diagnostics"][0]["code"], "OUTPUT_EXISTS")
            self.assertEqual(output.read_text(encoding="utf-8"), original)
            replaced, replaced_document = self.run_cli(
                "behavior", "snapshot", str(target), "--output", str(output), "--force", "--json"
            )
            self.assertEqual(replaced.returncode, 0, replaced.stderr)
            self.assertTrue(replaced_document["result"]["changed"])
            self.assertEqual(
                replaced_document["result"]["replaced_sha256"],
                hashlib.sha256(original.encode("utf-8")).hexdigest(),
            )
            self.assertNotEqual(output.read_text(encoding="utf-8"), original)

    def test_behavior_output_inside_target_requires_explicit_permission(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp)
            (target / "index.html").write_text("<button onclick=save()>Save</button>", encoding="utf-8")
            result, document = self.run_cli(
                "behavior", "snapshot", str(target), "--output", str(target / "baseline.json"), "--json"
            )
            self.assertEqual(result.returncode, 2)
            self.assertEqual(document["diagnostics"][0]["code"], "OUTPUT_INSIDE_TARGET")

    def test_behavior_output_symlink_is_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            target = root / "app"
            target.mkdir()
            (target / "app.js").write_text("button.onclick = save;", encoding="utf-8")
            destination = root / "destination.json"
            destination.write_text("user data", encoding="utf-8")
            link = root / "baseline.json"
            try:
                link.symlink_to(destination)
            except OSError as error:
                self.skipTest(f"symlink unavailable: {error}")
            result, document = self.run_cli("behavior", "snapshot", str(target), "--output", str(link), "--force", "--json")
            self.assertEqual(result.returncode, 2)
            self.assertEqual(document["diagnostics"][0]["code"], "OUTPUT_IS_SYMLINK")
            self.assertEqual(destination.read_text(encoding="utf-8"), "user data")

    def test_behavior_compare_uses_review_exit_code(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            target = root / "app"
            target.mkdir()
            source = target / "app.js"
            source.write_text("button.onclick = save;", encoding="utf-8")
            baseline = root / "baseline.json"
            snapshot, _ = self.run_cli("behavior", "snapshot", str(target), "--output", str(baseline), "--json")
            self.assertEqual(snapshot.returncode, 0)
            source.write_text("button.textContent = 'Save';", encoding="utf-8")
            result, document = self.run_cli("behavior", "compare", str(baseline), str(target), "--json")
            self.assertEqual(result.returncode, 1)
            self.assertEqual(document["status"], "review_required")

    def test_theme_bundle_and_check_share_deterministic_content(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "theme.css"
            written, written_document = self.run_cli("theme", "bundle", "windows-7", "--output", str(output), "--json")
            self.assertEqual(written.returncode, 0, written.stderr)
            self.assertEqual(written_document["result"]["action"], "written")
            checked, checked_document = self.run_cli("theme", "bundle", "windows-7", "--output", str(output), "--check", "--json")
            self.assertEqual(checked.returncode, 0, checked.stderr)
            self.assertTrue(checked_document["result"]["current"])

    def test_verify_never_runs_discovered_target_scripts(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            marker = root / "executed"
            (root / "package.json").write_text(
                json.dumps({"scripts": {"build": f"touch {marker.name}"}, "dependencies": {"react": "19.0.0"}}),
                encoding="utf-8",
            )
            (root / "App.jsx").write_text("export default function App(){return <main/>}", encoding="utf-8")
            result, document = self.run_cli("verify", str(root), "--json")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(marker.exists())
            self.assertFalse(document["result"]["target_commands_executed"])
            self.assertEqual(document["result"]["analysis"]["verification_plan"][0]["execution"], "not-run")


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

    def test_repository_markdown_links_resolve(self):
        import re
        markdown_files = [ROOT / "README.md", ROOT / "README.ja.md", ROOT / "THIRD_PARTY_NOTICES.md"]
        markdown_files.extend(sorted((ROOT / "docs").glob("*.md")))
        markdown_files.extend(sorted((ROOT / "docs" / "releases").glob("*.md")))
        for path in markdown_files:
            text = path.read_text(encoding="utf-8")
            for target in re.findall(r"\[[^]]*\]\(([^)]+)\)", text):
                clean = target.split("#", 1)[0]
                if not clean or "://" in clean or clean.startswith(("mailto:", "#")):
                    continue
                with self.subTest(path=path.relative_to(ROOT), target=target):
                    self.assertTrue((path.parent / clean).exists(), target)

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
            self.assertIn("retro-web-ui/manifest.json", names)
            self.assertIn("retro-web-ui/scripts/retro_web_ui.py", names)
            self.assertIn("retro-web-ui/core/__init__.py", names)
            self.assertFalse(any(Path(name).name.startswith(".") for name in names))

    def test_development_versions_are_aligned(self):
        manifest = json.loads((SKILL / "manifest.json").read_text(encoding="utf-8"))
        contracts = (SCRIPTS / "contracts.py").read_text(encoding="utf-8")
        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        self.assertEqual((ROOT / "VERSION").read_text(encoding="utf-8").strip(), "1.1.0")
        self.assertEqual(manifest["skill_version"], "1.1.0")
        self.assertIn('TOOL_VERSION = "1.1.0"', contracts)
        self.assertIn('version = "1.1.0"', pyproject)


if __name__ == "__main__":
    unittest.main()
