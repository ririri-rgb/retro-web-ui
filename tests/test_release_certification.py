from __future__ import annotations

import hashlib
import io
import json
import os
import subprocess
import tempfile
import unittest
import urllib.error
import zipfile
from base64 import b64encode
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from scripts import release_certification as certification


COMMIT = "a" * 40
TAG_OBJECT = "b" * 40
REPO = "owner/project"
TAG = "v3.4.5"


def digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


class FakeAPI:
    def __init__(self, responses):
        self.responses = responses
        self.downloads = {}

    def get(self, path, *, expected=(200,)):
        status, payload = self.responses[path]
        if status not in expected:
            raise certification.CertificationError(f"unexpected HTTP {status}")
        return status, payload

    def download(self, path, *, maximum_bytes=1024 * 1024):
        return self.downloads[path]


def identity_responses(commit: str = COMMIT, message: str = "Release tag"):
    return {
        f"/repos/{REPO}/git/ref/tags/{TAG}": (200, {"object": {"type": "tag", "sha": TAG_OBJECT}}),
        f"/repos/{REPO}/git/tags/{TAG_OBJECT}": (200, {"message": message, "object": {"type": "commit", "sha": commit}}),
        f"/repos/{REPO}": (200, {"default_branch": "main"}),
        f"/repos/{REPO}/git/ref/heads/main": (200, {"object": {"type": "commit", "sha": commit}}),
    }


class ReleaseFixture:
    def __init__(self, root: Path):
        self.root = root
        self.files = {}
        version = "3.4.5"
        for name in (
            f"retro-web-ui-{version}.zip",
            f"retro_web_ui_skill-{version}-py3-none-any.whl",
            f"retro_web_ui_skill-{version}.tar.gz",
        ):
            self.payload(name, f"payload:{name}".encode())
        architectures = {"linux": "x86_64", "macos": "arm64", "windows": "x86_64"}
        for platform, architecture in architectures.items():
            extension = "tar.gz" if platform == "linux" else "zip"
            artifact = f"retro-web-ui-gui-{version}-{platform}-{architecture}.{extension}"
            content = f"native:{platform}".encode()
            self.payload(artifact, content)
            report = {
                "version": version,
                "candidateCommit": COMMIT,
                "candidateClean": True,
                "platform": platform,
                "artifact": artifact,
                "artifactBytes": len(content),
                "sha256": digest(content),
                "codexBundled": False,
                "smoke": {
                    "status": "ok",
                    "appServer": "ready",
                    "coreStatus": "ok",
                    "manifestCompatible": True,
                    "skillAvailable": True,
                    "windowVisible": True,
                    "version": version,
                },
                "workspaceLifecycle": {
                    "create": {
                        "phase": "created",
                        "artifactIntegrity": "available",
                        "artifactSha256": "c" * 64,
                    },
                    "restore": {
                        "phase": "restored",
                        "artifactIntegrity": "available",
                        "artifactSha256": "c" * 64,
                        "projectAvailability": "available",
                        "privacyScan": "clean",
                        "projectHistoryCount": 1,
                        "sessionHistoryCount": 1,
                    },
                },
            }
            report_name = f"native-report-{platform}-{architecture}.json"
            path = root / "native" / report_name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(report), encoding="utf-8")
            self.files[report_name] = path

    def payload(self, name: str, content: bytes):
        directory = self.root / ("native" if name.startswith("retro-web-ui-gui") else "")
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / name
        path.write_bytes(content)
        checksum = directory / f"{name}.sha256"
        checksum.write_text(f"{digest(content)}  {name}\n", encoding="utf-8")
        self.files[name] = path
        self.files[checksum.name] = checksum


class ImmutableSemanticsTests(unittest.TestCase):
    def test_repository_setting_accepts_only_literal_enabled_true(self):
        certification.validate_immutable_setting({"enabled": True, "enforced_by_owner": False})
        for payload in (
            {"enabled": False, "enforced_by_owner": False},
            {"enabled": "true", "enforced_by_owner": False},
            {"enabled": True},
            {},
            [],
            "malformed",
        ):
            with self.subTest(payload=payload):
                with self.assertRaises(certification.CertificationError):
                    certification.validate_immutable_setting(payload)

    def test_release_accepts_only_literal_immutable_true(self):
        certification.validate_release_immutable({"immutable": True})
        for payload in ({"immutable": False}, {"immutable": "true"}, {}):
            with self.subTest(payload=payload):
                with self.assertRaises(certification.CertificationError):
                    certification.validate_release_immutable(payload)

    def test_setting_permission_disabled_and_unavailable_diagnostics_are_actionable(self):
        cases = (
            (401, "Administration: read"),
            (403, "Administration: read"),
            (404, "not enabled"),
            (503, "unavailable"),
        )
        for status, message in cases:
            with self.subTest(status=status):
                with self.assertRaisesRegex(certification.CertificationError, message):
                    certification.validate_immutable_preflight_response(status, {})

    def test_permission_failure_is_not_interpreted_as_disabled_or_success(self):
        error = urllib.error.HTTPError("https://api.github.test", 403, "forbidden", {}, io.BytesIO(b'{"message":"forbidden"}'))
        with mock.patch("urllib.request.urlopen", side_effect=error):
            with self.assertRaisesRegex(certification.CertificationError, "HTTP 403"):
                certification.GitHubAPI("token").get("/repos/owner/project/immutable-releases")

    def test_unavailable_api_fails_closed(self):
        with mock.patch("urllib.request.urlopen", side_effect=urllib.error.URLError("offline")):
            with self.assertRaisesRegex(certification.CertificationError, "unavailable"):
                certification.GitHubAPI("token").get("/repos/owner/project/immutable-releases")

    def test_malformed_api_json_fails_closed(self):
        response = mock.MagicMock()
        response.__enter__.return_value = response
        response.status = 200
        response.read.return_value = b"not-json"
        with mock.patch("urllib.request.urlopen", return_value=response):
            with self.assertRaisesRegex(certification.CertificationError, "malformed JSON"):
                certification.GitHubAPI("token").get("/repos/owner/project/immutable-releases")


class IdentityTests(unittest.TestCase):
    def test_annotated_tag_default_branch_and_expected_commit_must_match(self):
        result = certification.verify_tag_identity(FakeAPI(identity_responses()), REPO, TAG, COMMIT)
        self.assertEqual(result["tagCommit"], COMMIT)
        mismatch = identity_responses("d" * 40)
        with self.assertRaisesRegex(certification.CertificationError, "not expected commit"):
            certification.verify_tag_identity(FakeAPI(mismatch), REPO, TAG, COMMIT)

    def test_lightweight_tag_is_rejected(self):
        responses = identity_responses()
        responses[f"/repos/{REPO}/git/ref/tags/{TAG}"] = (200, {"object": {"type": "commit", "sha": COMMIT}})
        with self.assertRaisesRegex(certification.CertificationError, "annotated"):
            certification.resolve_tag_commit(FakeAPI(responses), REPO, TAG)


class ManifestTests(unittest.TestCase):
    def test_exact_fifteen_asset_manifest_binds_native_evidence(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = ReleaseFixture(Path(temporary))
            manifest = certification.build_manifest(Path(temporary), "3.4.5", COMMIT)
            self.assertEqual(manifest["state"], certification.STATE_CANDIDATE)
            self.assertEqual(len(manifest["assets"]), 15)
            self.assertEqual({item["name"] for item in manifest["assets"]}, set(fixture.files))

    def test_missing_extra_and_changed_checksum_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture = ReleaseFixture(root)
            (root / "unexpected.bin").write_bytes(b"x")
            with self.assertRaisesRegex(certification.CertificationError, "unexpected"):
                certification.build_manifest(root, "3.4.5", COMMIT)
            (root / "unexpected.bin").unlink()
            fixture.files["retro-web-ui-3.4.5.zip.sha256"].write_text("0" * 64 + "  retro-web-ui-3.4.5.zip\n")
            with self.assertRaisesRegex(certification.CertificationError, "checksum digest mismatch"):
                certification.build_manifest(root, "3.4.5", COMMIT)

    def test_native_report_commit_and_privacy_are_fail_closed(self):
        for field, value, message in (
            ("candidateCommit", "d" * 40, "commit mismatch"),
            ("candidateClean", False, "not clean"),
        ):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                fixture = ReleaseFixture(root)
                report_path = fixture.files["native-report-linux-x86_64.json"]
                report = json.loads(report_path.read_text())
                report[field] = value
                report_path.write_text(json.dumps(report))
                with self.assertRaisesRegex(certification.CertificationError, message):
                    certification.build_manifest(root, "3.4.5", COMMIT)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture = ReleaseFixture(root)
            report_path = fixture.files["native-report-windows-x86_64.json"]
            report = json.loads(report_path.read_text())
            report["workspaceLifecycle"]["restore"]["privacyScan"] = "unavailable"
            report_path.write_text(json.dumps(report))
            with self.assertRaisesRegex(certification.CertificationError, "privacy scan failed"):
                certification.build_manifest(root, "3.4.5", COMMIT)

    def test_remote_asset_digest_field_must_exist_and_match(self):
        manifest = {
            "assets": [{"name": "artifact.zip", "size": 4, "sha256": digest(b"data")}],
        }
        release = {"assets": [{"name": "artifact.zip", "size": 4, "digest": f"sha256:{digest(b'data')}"}]}
        certification.validate_remote_assets(release, manifest)
        del release["assets"][0]["digest"]
        with self.assertRaisesRegex(certification.CertificationError, "digest"):
            certification.validate_remote_assets(release, manifest)

    def test_verified_provenance_must_bind_tag_and_every_asset_digest(self):
        manifest = {"assets": [{"name": "artifact.zip", "size": 4, "sha256": digest(b"data")}]}
        statement = {
            "predicate": {"tag": TAG},
            "subject": [{"name": "artifact.zip", "digest": {"sha256": digest(b"data")}}],
        }
        provenance = {
            "attestation": {"bundle": {"dsseEnvelope": {"payload": b64encode(json.dumps(statement).encode()).decode()}}},
            "verificationResult": {
                "mediaType": certification.VERIFICATION_RESULT_MEDIA_TYPE,
                "statement": statement,
                "signature": {"certificate": {"issuer": "GitHub"}},
                "verifiedTimestamps": [{"type": "Tlog", "uri": "https://rekor.example", "timestamp": "2026-01-01T00:00:00Z"}],
            },
        }
        certification.validate_provenance(provenance, manifest, TAG)
        provenance["attestation"]["bundle"]["dsseEnvelope"]["payload"] = b64encode(
            json.dumps({"predicate": {"tag": "v9.9.9"}, "subject": statement["subject"]}).encode()
        ).decode()
        with self.assertRaisesRegex(certification.CertificationError, "tag does not match"):
            certification.validate_provenance(provenance, manifest, TAG)

    def test_provenance_requires_structured_successful_verification_result(self):
        manifest = {"assets": [{"name": "artifact.zip", "size": 4, "sha256": digest(b"data")}]}
        statement = {
            "predicate": {"tag": TAG},
            "subject": [{"name": "artifact.zip", "digest": {"sha256": digest(b"data")}}],
        }
        encoded_statement = b64encode(json.dumps(statement).encode()).decode()
        base = {"attestation": {"bundle": {"dsseEnvelope": {"payload": encoded_statement}}}}
        invalid_results = (
            {},
            {"verified": False},
            {"mediaType": certification.VERIFICATION_RESULT_MEDIA_TYPE, "statement": statement, "signature": {}, "verifiedTimestamps": []},
        )
        for result in invalid_results:
            with self.subTest(result=result):
                with self.assertRaises(certification.CertificationError):
                    certification.validate_provenance({**base, "verificationResult": result}, manifest, TAG)

    def test_tag_triggered_preflight_is_bound_to_successful_manual_run(self):
        run_id = 123456
        artifact_id = 789
        responses = identity_responses(message=f"Retro Web UI {TAG}\n\nRelease-Preflight-Run: {run_id}")
        responses[f"/repos/{REPO}/actions/runs/{run_id}"] = (
            200,
            {
                "id": run_id,
                "path": f"{certification.PREFLIGHT_WORKFLOW_PATH}@main",
                "event": "workflow_dispatch",
                "status": "completed",
                "conclusion": "success",
                "head_sha": COMMIT,
                "head_branch": "main",
            },
        )
        responses[f"/repos/{REPO}/actions/runs/{run_id}/artifacts"] = (
            200,
            {"artifacts": [{"id": artifact_id, "name": f"release-preflight-{TAG}", "expired": False}]},
        )
        evidence = {
            "state": certification.STATE_CANDIDATE,
            "phase": "protected-pre-tag-preflight",
            "repository": REPO,
            "tag": TAG,
            "expectedCommit": COMMIT,
            "defaultBranch": "main",
            "defaultBranchCommit": COMMIT,
            "workflowRunId": run_id,
        }
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w") as bundle:
            bundle.writestr("release-preflight.json", json.dumps(evidence))
        fake = FakeAPI(responses)
        fake.downloads[f"/repos/{REPO}/actions/artifacts/{artifact_id}/zip"] = archive.getvalue()
        result = certification.verify_preflight_run(fake, REPO, TAG, COMMIT)
        self.assertEqual(result["preflightRunId"], run_id)
        responses[f"/repos/{REPO}/actions/runs/{run_id}"][1]["path"] = certification.PREFLIGHT_WORKFLOW_PATH
        certification.verify_preflight_run(fake, REPO, TAG, COMMIT)
        responses[f"/repos/{REPO}/actions/runs/{run_id}"][1]["path"] = f"{certification.PREFLIGHT_WORKFLOW_PATH}@feature"
        with self.assertRaisesRegex(certification.CertificationError, "wrong workflow or ref"):
            certification.verify_preflight_run(fake, REPO, TAG, COMMIT)
        responses[f"/repos/{REPO}/actions/runs/{run_id}"][1]["path"] = f"{certification.PREFLIGHT_WORKFLOW_PATH}@main"
        evidence["tag"] = "v9.9.9"
        changed = io.BytesIO()
        with zipfile.ZipFile(changed, "w") as bundle:
            bundle.writestr("release-preflight.json", json.dumps(evidence))
        fake.downloads[f"/repos/{REPO}/actions/artifacts/{artifact_id}/zip"] = changed.getvalue()
        with self.assertRaisesRegex(certification.CertificationError, "version or tag"):
            certification.verify_preflight_run(fake, REPO, TAG, COMMIT)
        for message in ("Release tag", "Release-Preflight-Run: 123\nRelease-Preflight-Run: 456"):
            with self.subTest(message=message):
                with self.assertRaisesRegex(certification.CertificationError, "exactly one"):
                    certification.verify_preflight_run(FakeAPI(identity_responses(message=message)), REPO, TAG, COMMIT)

    def test_create_only_draft_collision_never_uploads_or_updates(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            ReleaseFixture(root)
            manifest_value = certification.build_manifest(root, "3.4.5", COMMIT)
            manifest_path = root.parent / f"manifest-{root.name}.json"
            body_path = root.parent / f"notes-{root.name}.md"
            manifest_path.write_text(json.dumps(manifest_value), encoding="utf-8")
            body_path.write_text("notes", encoding="utf-8")
            fake = FakeAPI({**identity_responses(), f"/repos/{REPO}/releases/tags/{TAG}": (404, {})})
            fake.post_json = mock.Mock(return_value=(422, {"message": "already_exists"}))
            fake.upload = mock.Mock()
            args = SimpleNamespace(
                repo=REPO,
                tag=TAG,
                expected_commit=COMMIT,
                manifest=manifest_path,
                root=root,
                body=body_path,
                token_env="GITHUB_TOKEN",
            )
            try:
                with mock.patch.dict(os.environ, {"GITHUB_TOKEN": "test"}), mock.patch.object(certification, "GitHubAPI", return_value=fake):
                    with self.assertRaisesRegex(certification.CertificationError, "create-only"):
                        certification.command_create_draft(args)
                fake.upload.assert_not_called()
            finally:
                manifest_path.unlink(missing_ok=True)
                body_path.unlink(missing_ok=True)

    def test_created_draft_identity_is_verified_before_any_upload(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            ReleaseFixture(root)
            manifest_value = certification.build_manifest(root, "3.4.5", COMMIT)
            manifest_path = root.parent / f"manifest-{root.name}.json"
            body_path = root.parent / f"notes-{root.name}.md"
            manifest_path.write_text(json.dumps(manifest_value), encoding="utf-8")
            body_path.write_text("notes", encoding="utf-8")
            created_id = 123
            responses = {
                **identity_responses(),
                f"/repos/{REPO}/releases/tags/{TAG}": (404, {}),
                f"/repos/{REPO}/releases/{created_id}": (
                    200,
                    {"id": created_id, "tag_name": "v9.9.9", "draft": True, "prerelease": False, "assets": [], "upload_url": "https://uploads.github.com/example{?name}"},
                ),
            }
            fake = FakeAPI(responses)
            fake.post_json = mock.Mock(return_value=(201, {"id": created_id, "upload_url": "https://uploads.github.com/example{?name}"}))
            fake.upload = mock.Mock()
            args = SimpleNamespace(repo=REPO, tag=TAG, expected_commit=COMMIT, manifest=manifest_path, root=root, body=body_path, token_env="GITHUB_TOKEN")
            try:
                with mock.patch.dict(os.environ, {"GITHUB_TOKEN": "test"}), mock.patch.object(certification, "GitHubAPI", return_value=fake):
                    with self.assertRaisesRegex(certification.CertificationError, "tag does not match"):
                        certification.command_create_draft(args)
                fake.upload.assert_not_called()
            finally:
                manifest_path.unlink(missing_ok=True)
                body_path.unlink(missing_ok=True)

    def test_publish_targets_only_the_exact_created_release_id(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest_path = root / "manifest.json"
            creation_path = root / "creation.json"
            manifest = {
                "schemaVersion": 1,
                "state": certification.STATE_CANDIDATE,
                "tag": TAG,
                "expectedCommit": COMMIT,
                "assets": [{"name": "artifact.zip", "size": 4, "sha256": digest(b"data")}],
            }
            manifest_path.write_text(json.dumps(manifest))
            creation_path.write_text(json.dumps({"draftCreated": True, "tag": TAG, "expectedCommit": COMMIT, "releaseId": 123}))
            replacement = {
                "id": 999,
                "tag_name": TAG,
                "draft": True,
                "prerelease": False,
                "assets": [{"name": "artifact.zip", "size": 4, "digest": f"sha256:{digest(b'data')}"}],
            }
            fake = FakeAPI({**identity_responses(), f"/repos/{REPO}/releases/123": (200, replacement)})
            fake.patch_json = mock.Mock()
            args = SimpleNamespace(
                repo=REPO,
                tag=TAG,
                expected_commit=COMMIT,
                manifest=manifest_path,
                draft_creation=creation_path,
                token_env="GITHUB_TOKEN",
            )
            with mock.patch.dict(os.environ, {"GITHUB_TOKEN": "test"}), mock.patch.object(certification, "GitHubAPI", return_value=fake):
                with self.assertRaisesRegex(certification.CertificationError, "ID response"):
                    certification.command_publish_draft(args)
            fake.patch_json.assert_not_called()


class PolicyRegressionTests(unittest.TestCase):
    def test_release_metadata_recovers_remote_annotated_tag_after_checkout_peels_local_ref(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            remote = root / "remote.git"
            source = root / "source"
            checkout = root / "checkout"
            subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
            subprocess.run(["git", "init", "-b", "main", str(source)], check=True, capture_output=True)
            subprocess.run(["git", "-C", str(source), "config", "user.name", "Release Test"], check=True)
            subprocess.run(["git", "-C", str(source), "config", "user.email", "release@example.invalid"], check=True)
            (source / "VERSION").write_text("3.4.5\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(source), "add", "VERSION"], check=True)
            subprocess.run(["git", "-C", str(source), "commit", "-m", "release source"], check=True, capture_output=True)
            subprocess.run(["git", "-C", str(source), "tag", "-a", TAG, "-m", "annotated release"], check=True)
            subprocess.run(["git", "-C", str(source), "remote", "add", "origin", str(remote)], check=True)
            subprocess.run(["git", "-C", str(source), "push", "origin", "main", TAG], check=True, capture_output=True)
            subprocess.run(["git", "clone", str(remote), str(checkout)], check=True, capture_output=True)

            expected_commit = subprocess.check_output(
                ["git", "-C", str(source), "rev-parse", f"{TAG}^{{commit}}"], text=True
            ).strip()
            subprocess.run(["git", "-C", str(checkout), "update-ref", f"refs/tags/{TAG}", expected_commit], check=True)
            local_type = subprocess.check_output(
                ["git", "-C", str(checkout), "cat-file", "-t", f"refs/tags/{TAG}"], text=True
            ).strip()
            self.assertEqual(local_type, "commit")

            verified_ref = f"refs/retro-release-tags/{TAG}"
            subprocess.run(
                ["git", "-C", str(checkout), "fetch", "--force", "--no-tags", "origin", f"refs/tags/{TAG}:{verified_ref}"],
                check=True,
                capture_output=True,
            )
            verified_type = subprocess.check_output(
                ["git", "-C", str(checkout), "cat-file", "-t", verified_ref], text=True
            ).strip()
            verified_commit = subprocess.check_output(
                ["git", "-C", str(checkout), "rev-parse", f"{verified_ref}^{{commit}}"], text=True
            ).strip()
            self.assertEqual(verified_type, "tag")
            self.assertEqual(verified_commit, expected_commit)

        workflow = (Path(__file__).parents[1] / ".github" / "workflows" / "release.yml").read_text()
        self.assertIn('remote_tag_ref="refs/retro-release-tags/${GITHUB_REF_NAME}"', workflow)
        self.assertIn('"refs/tags/${GITHUB_REF_NAME}:${remote_tag_ref}"', workflow)

    def test_workflow_orders_future_release_certification_and_forbids_overwrite(self):
        workflow = (Path(__file__).parents[1] / ".github" / "workflows" / "release.yml").read_text()
        ordered = [
            "immutable-preflight:",
            "Create draft through create-only API and upload exact assets",
            "Verify the complete draft before publication",
            "Publish the verified draft",
            "Re-download and verify every public asset and checksum",
            "Verify GitHub release provenance",
            "Certify GitHub-enforced immutability",
        ]
        positions = [workflow.index(value) for value in ordered]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("cancel-in-progress: false", workflow)
        self.assertIn("IMMUTABLE_RELEASE_ADMIN_TOKEN", workflow)
        self.assertIn("actions: read", workflow[workflow.index("immutable-preflight:"):workflow.index("native:")])
        self.assertIn("verify_preflight_run", (Path(__file__).parents[1] / "scripts" / "release_certification.py").read_text())
        self.assertIn("environment: release", workflow[workflow.index("immutable-preflight:"):workflow.index("native:")])
        self.assertIn("create-draft", workflow)
        self.assertIn("publish-draft", workflow)
        self.assertNotIn("softprops/action-gh-release", workflow)
        self.assertNotIn("gh release edit", workflow)
        self.assertNotIn("gh release delete", workflow)
        self.assertNotRegex(workflow, r"actions/(?:checkout|setup-python|setup-node|download-artifact|upload-artifact)@v\d")

    def test_protected_manual_pre_tag_preflight_exists(self):
        workflow = (Path(__file__).parents[1] / ".github" / "workflows" / "release-preflight.yml").read_text()
        self.assertIn("workflow_dispatch:", workflow)
        self.assertIn("environment: release", workflow)
        self.assertIn("repository-preflight", workflow)
        self.assertIn("--workflow-run-id", workflow)
        self.assertIn("ref: main", workflow)
        self.assertIn("IMMUTABLE_RELEASE_ADMIN_TOKEN", workflow)

    def test_v2_1_0_is_closed_as_historical_operational_immutability(self):
        policy = (Path(__file__).parents[1] / "docs" / "release-engineering.md").read_text()
        self.assertIn("RELEASED — Verified Provenance & Operational Immutability Accepted", policy)
        self.assertIn("`immutable: false`", policy)
        self.assertIn("repository-policy limitation, not a software", policy)
        self.assertIn("never rerun its historical write-capable release workflow", policy)
        self.assertNotIn("v2.1.0 was GitHub-enforced immutable", policy)


if __name__ == "__main__":
    unittest.main()
