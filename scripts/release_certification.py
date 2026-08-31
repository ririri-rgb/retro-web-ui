#!/usr/bin/env python3
"""Fail-closed GitHub immutable-release preflight and certification.

The commands in this module deliberately distinguish publication from release
certification.  A public GitHub release is not certified until its tag identity,
complete asset set, public bytes, and GitHub immutable flag all match the local
manifest.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import os
import re
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from typing import Any, Mapping, Sequence


API_ROOT = "https://api.github.com"
API_VERSION = "2022-11-28"
SEMVER = re.compile(r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)")
SHA = re.compile(r"[0-9a-f]{40}")
DIGEST = re.compile(r"[0-9a-f]{64}")
PLATFORMS = {"linux", "macos", "windows"}
PREFLIGHT_RUN = re.compile(r"(?m)^Release-Preflight-Run: ([1-9]\d*)$")
PREFLIGHT_WORKFLOW_PATH = ".github/workflows/release-preflight.yml"
VERIFICATION_RESULT_MEDIA_TYPE = "application/vnd.dev.sigstore.verificationresult+json;version=0.1"
STATE_CANDIDATE = "RELEASE CANDIDATE"
STATE_PENDING = "PUBLISHED — PENDING RELEASE VERIFICATION"
STATE_RELEASED = "RELEASED — GitHub-Enforced Immutable"


class CertificationError(RuntimeError):
    """An expected invariant was absent or contradicted."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise CertificationError(message)


def require_bool(payload: Mapping[str, Any], key: str, context: str) -> bool:
    value = payload.get(key)
    require(type(value) is bool, f"{context}: {key!r} must be a JSON boolean")
    return value


def validate_immutable_setting(payload: Any) -> None:
    require(isinstance(payload, dict), "immutable-release preflight returned malformed JSON")
    enabled = require_bool(payload, "enabled", "immutable-release preflight")
    require_bool(payload, "enforced_by_owner", "immutable-release preflight")
    require(enabled, "immutable releases are disabled for this repository")


def validate_immutable_preflight_response(status: int, payload: Any) -> None:
    if status in (401, 403):
        raise CertificationError(
            f"immutable-release preflight returned HTTP {status}; the dedicated credential is unavailable or lacks repository Administration: read"
        )
    if status == 404:
        raise CertificationError("immutable-release preflight returned HTTP 404; immutable releases are not enabled for this repository")
    require(status == 200, f"immutable-release preflight endpoint is unavailable (HTTP {status})")
    validate_immutable_setting(payload)


def validate_release_immutable(payload: Mapping[str, Any]) -> None:
    immutable = require_bool(payload, "immutable", "published release")
    require(immutable, "published release is not GitHub-enforced immutable")


def sha256(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


class GitHubAPI:
    def __init__(self, token: str | None):
        self.token = token

    def request(
        self,
        method: str,
        path: str,
        *,
        expected: Sequence[int],
        data: bytes | None = None,
        content_type: str | None = None,
    ) -> tuple[int, Any]:
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "retro-web-ui-release-certification",
            "X-GitHub-Api-Version": API_VERSION,
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if content_type:
            headers["Content-Type"] = content_type
        url = path if path.startswith("https://") else f"{API_ROOT}{path}"
        request = urllib.request.Request(url, headers=headers, data=data, method=method)
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                status = response.status
                body = response.read()
        except urllib.error.HTTPError as error:
            status = error.code
            body = error.read()
        except (OSError, TimeoutError) as error:
            raise CertificationError(f"GitHub API unavailable for {path}: {error}") from error
        require(status in expected, f"GitHub API {path} returned HTTP {status}; expected {list(expected)}")
        if not body:
            return status, None
        try:
            return status, json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise CertificationError(f"GitHub API {path} returned malformed JSON") from error

    def get(self, path: str, *, expected: Sequence[int] = (200,)) -> tuple[int, Any]:
        return self.request("GET", path, expected=expected)

    def post_json(self, path: str, payload: Mapping[str, Any], *, expected: Sequence[int]) -> tuple[int, Any]:
        data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        return self.request("POST", path, expected=expected, data=data, content_type="application/json")

    def patch_json(self, path: str, payload: Mapping[str, Any], *, expected: Sequence[int]) -> tuple[int, Any]:
        data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        return self.request("PATCH", path, expected=expected, data=data, content_type="application/json")

    def upload(self, url: str, content: bytes) -> Any:
        require(url.startswith("https://uploads.github.com/"), "release upload URL is missing or not the GitHub uploads endpoint")
        _, payload = self.request("POST", url, expected=(201,), data=content, content_type="application/octet-stream")
        return payload

    def download(self, path: str, *, maximum_bytes: int = 1024 * 1024) -> bytes:
        require(path.startswith("/repos/"), "GitHub artifact download path is malformed")
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "retro-web-ui-release-certification",
            "X-GitHub-Api-Version": API_VERSION,
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        request = urllib.request.Request(f"{API_ROOT}{path}", headers=headers, method="GET")
        opener = urllib.request.build_opener(CredentialSafeRedirectHandler())
        try:
            with opener.open(request, timeout=120) as response:
                require(response.status == 200, f"GitHub artifact download returned HTTP {response.status}")
                content = response.read(maximum_bytes + 1)
        except (urllib.error.URLError, OSError, TimeoutError) as error:
            raise CertificationError(f"GitHub artifact download failed for {path}: {error}") from error
        require(len(content) <= maximum_bytes, "GitHub preflight artifact exceeds the size limit")
        return content


class CredentialSafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Follow GitHub downloads without forwarding credentials across hosts."""

    def redirect_request(self, request, fp, code, message, headers, new_url):
        redirected = super().redirect_request(request, fp, code, message, headers, new_url)
        if redirected is None:
            return None
        source = urllib.parse.urlsplit(request.full_url)
        destination = urllib.parse.urlsplit(redirected.full_url)
        if destination.scheme != "https":
            raise CertificationError("GitHub artifact download redirect must use HTTPS")
        if source.hostname != destination.hostname:
            redirected.remove_header("Authorization")
            redirected.remove_header("Proxy-Authorization")
        return redirected


def encoded(value: str) -> str:
    return urllib.parse.quote(value, safe="")


def require_sha(value: Any, context: str) -> str:
    require(isinstance(value, str) and SHA.fullmatch(value) is not None, f"{context}: expected a 40-character commit SHA")
    return value


def resolve_annotated_tag(api: GitHubAPI, repo: str, tag: str) -> dict[str, Any]:
    _, reference = api.get(f"/repos/{repo}/git/ref/tags/{encoded(tag)}")
    require(isinstance(reference, dict), "tag reference response is malformed")
    obj = reference.get("object")
    require(isinstance(obj, dict), "tag reference has no object")
    require(obj.get("type") == "tag", "release tag must be annotated; lightweight tags are rejected")
    tag_object_sha = require_sha(obj.get("sha"), "tag object")
    _, tag_object = api.get(f"/repos/{repo}/git/tags/{tag_object_sha}")
    require(isinstance(tag_object, dict), "annotated tag response is malformed")
    peeled = tag_object.get("object")
    require(isinstance(peeled, dict), "annotated tag has no target object")
    require(peeled.get("type") == "commit", "annotated tag must point directly to a commit")
    message = tag_object.get("message")
    require(isinstance(message, str) and message, "annotated tag message is missing or malformed")
    return {
        "tagObject": tag_object_sha,
        "tagCommit": require_sha(peeled.get("sha"), "annotated tag target"),
        "tagMessage": message,
    }


def resolve_tag_commit(api: GitHubAPI, repo: str, tag: str) -> str:
    return resolve_annotated_tag(api, repo, tag)["tagCommit"]


def default_branch_commit(api: GitHubAPI, repo: str) -> tuple[str, str]:
    _, repository = api.get(f"/repos/{repo}")
    require(isinstance(repository, dict), "repository response is malformed")
    branch = repository.get("default_branch")
    require(isinstance(branch, str) and branch, "repository default_branch is missing or malformed")
    _, reference = api.get(f"/repos/{repo}/git/ref/heads/{encoded(branch)}")
    require(isinstance(reference, dict) and isinstance(reference.get("object"), dict), "default branch reference is malformed")
    return branch, require_sha(reference["object"].get("sha"), "default branch")


def verify_tag_identity(api: GitHubAPI, repo: str, tag: str, expected_commit: str) -> dict[str, str]:
    require(SHA.fullmatch(expected_commit) is not None, "expected commit must be a full lowercase SHA")
    tag_identity = resolve_annotated_tag(api, repo, tag)
    tag_commit = tag_identity["tagCommit"]
    branch, branch_commit = default_branch_commit(api, repo)
    require(tag_commit == expected_commit, f"tag {tag} targets {tag_commit}, not expected commit {expected_commit}")
    require(branch_commit == expected_commit, f"default branch {branch} is {branch_commit}, not expected commit {expected_commit}")
    return {
        "tagObject": tag_identity["tagObject"],
        "tagCommit": tag_commit,
        "defaultBranch": branch,
        "defaultBranchCommit": branch_commit,
    }


def verify_preflight_run(api: GitHubAPI, repo: str, tag: str, expected_commit: str) -> dict[str, Any]:
    tag_identity = resolve_annotated_tag(api, repo, tag)
    matches = PREFLIGHT_RUN.findall(tag_identity["tagMessage"])
    require(len(matches) == 1, "annotated tag must bind exactly one Release-Preflight-Run ID")
    run_id = int(matches[0])
    _, run = api.get(f"/repos/{repo}/actions/runs/{run_id}")
    require(isinstance(run, dict) and run.get("id") == run_id, "release preflight workflow run response is malformed or mismatched")
    workflow_path = run.get("path")
    require(
        workflow_path in {PREFLIGHT_WORKFLOW_PATH, f"{PREFLIGHT_WORKFLOW_PATH}@main"},
        "release preflight evidence came from the wrong workflow or ref",
    )
    require(run.get("event") == "workflow_dispatch", "release preflight evidence was not manually dispatched")
    require(run.get("status") == "completed" and run.get("conclusion") == "success", "release preflight workflow did not complete successfully")
    require(run.get("head_sha") == expected_commit, "release preflight workflow commit does not match the tag target")
    require(run.get("head_branch") == "main", "release preflight workflow did not run on main")
    _, artifact_payload = api.get(f"/repos/{repo}/actions/runs/{run_id}/artifacts")
    artifacts = artifact_payload.get("artifacts") if isinstance(artifact_payload, dict) else None
    require(isinstance(artifacts, list), "release preflight artifact response is malformed")
    expected_name = f"release-preflight-{tag}"
    matches = [artifact for artifact in artifacts if isinstance(artifact, dict) and artifact.get("name") == expected_name]
    require(len(matches) == 1, "release preflight evidence artifact is missing or duplicated")
    artifact = matches[0]
    require(artifact.get("expired") is False, "release preflight evidence artifact has expired")
    artifact_id = artifact.get("id")
    require(isinstance(artifact_id, int), "release preflight evidence artifact ID is malformed")
    archive = api.download(f"/repos/{repo}/actions/artifacts/{artifact_id}/zip")
    try:
        with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
            members = bundle.infolist()
            require(len(members) == 1 and members[0].filename == "release-preflight.json", "release preflight evidence archive has an unexpected manifest")
            member = members[0]
            require(not member.is_dir() and member.file_size <= 256 * 1024, "release preflight evidence entry is malformed or oversized")
            require((member.external_attr >> 16) & 0o170000 != 0o120000, "release preflight evidence must not be a symlink")
            evidence = json.loads(bundle.read(member).decode("utf-8"))
    except (zipfile.BadZipFile, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CertificationError("release preflight evidence artifact is malformed") from error
    require(isinstance(evidence, dict), "release preflight evidence record is malformed")
    require(evidence.get("state") == STATE_CANDIDATE and evidence.get("phase") == "protected-pre-tag-preflight", "release preflight evidence state is invalid")
    require(evidence.get("repository") == repo, "release preflight evidence repository does not match")
    require(evidence.get("tag") == tag, "release preflight evidence version or tag does not match")
    require(evidence.get("expectedCommit") == expected_commit, "release preflight evidence commit does not match")
    require(evidence.get("defaultBranch") == "main" and evidence.get("defaultBranchCommit") == expected_commit, "release preflight evidence default branch does not match")
    require(evidence.get("workflowRunId") == run_id, "release preflight evidence run ID does not match")
    return {"preflightRunId": run_id, "preflightWorkflow": PREFLIGHT_WORKFLOW_PATH}


def parse_checksum(path: Path, payload_name: str) -> str:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as error:
        raise CertificationError(f"checksum is not UTF-8: {path.name}") from error
    match = re.fullmatch(r"([0-9a-f]{64})  ([^\r\n]+)\n?", text)
    require(match is not None, f"checksum has malformed content: {path.name}")
    require(match.group(2) == payload_name, f"checksum {path.name} names {match.group(2)!r}, expected {payload_name!r}")
    return match.group(1)


def validate_native_report(report_path: Path, files: Mapping[str, Path], version: str, expected_commit: str) -> None:
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CertificationError(f"native report is malformed: {report_path.name}") from error
    require(isinstance(report, dict), f"native report is not an object: {report_path.name}")
    platform = report.get("platform")
    require(platform in PLATFORMS, f"native report has invalid platform: {report_path.name}")
    require(report.get("version") == version, f"native report version mismatch: {report_path.name}")
    require(report.get("candidateCommit") == expected_commit, f"native report commit mismatch: {report_path.name}")
    require(report.get("candidateClean") is True, f"native report candidate is not clean: {report_path.name}")
    require(report.get("codexBundled") is False, f"native report must record codexBundled=false: {report_path.name}")
    artifact_name = report.get("artifact")
    require(isinstance(artifact_name, str) and artifact_name in files, f"native report artifact is missing: {report_path.name}")
    artifact = files[artifact_name]
    require(report.get("artifactBytes") == artifact.stat().st_size, f"native report byte count mismatch: {report_path.name}")
    require(report.get("sha256") == sha256(artifact), f"native report digest mismatch: {report_path.name}")
    require(artifact.with_name(artifact.name + ".sha256").name in files, f"native artifact checksum is missing: {artifact.name}")
    smoke = report.get("smoke")
    require(isinstance(smoke, dict), f"native smoke evidence is missing: {report_path.name}")
    expected_smoke = {
        "status": "ok",
        "appServer": "ready",
        "coreStatus": "ok",
        "manifestCompatible": True,
        "skillAvailable": True,
        "windowVisible": True,
        "version": version,
    }
    for key, expected in expected_smoke.items():
        require(smoke.get(key) == expected, f"native smoke {key} mismatch: {report_path.name}")
    lifecycle = report.get("workspaceLifecycle")
    require(isinstance(lifecycle, dict), f"workspace lifecycle evidence is missing: {report_path.name}")
    created, restored = lifecycle.get("create"), lifecycle.get("restore")
    require(isinstance(created, dict) and isinstance(restored, dict), f"workspace lifecycle is malformed: {report_path.name}")
    require(created.get("phase") == "created", f"workspace create evidence failed: {report_path.name}")
    require(created.get("artifactIntegrity") == "available", f"workspace create artifact is unavailable: {report_path.name}")
    require(restored.get("phase") == "restored", f"workspace restore evidence failed: {report_path.name}")
    require(restored.get("artifactIntegrity") == "available", f"workspace restored artifact is unavailable: {report_path.name}")
    require(restored.get("projectAvailability") == "available", f"workspace project is unavailable: {report_path.name}")
    require(restored.get("privacyScan") == "clean", f"workspace privacy scan failed: {report_path.name}")
    require(isinstance(restored.get("projectHistoryCount"), int) and restored["projectHistoryCount"] >= 1, f"workspace project history is missing: {report_path.name}")
    require(isinstance(restored.get("sessionHistoryCount"), int) and restored["sessionHistoryCount"] >= 1, f"workspace session history is missing: {report_path.name}")
    require(created.get("artifactSha256") == restored.get("artifactSha256"), f"workspace artifact changed after restart: {report_path.name}")


def build_manifest(root: Path, version: str, expected_commit: str) -> dict[str, Any]:
    require(SEMVER.fullmatch(version) is not None, "version must be canonical MAJOR.MINOR.PATCH")
    require(SHA.fullmatch(expected_commit) is not None, "expected commit must be a full lowercase SHA")
    require(root.is_dir(), f"asset root does not exist: {root}")
    paths = sorted(path for path in root.rglob("*") if path.is_file())
    files: dict[str, Path] = {}
    for path in paths:
        require(path.name not in files, f"duplicate asset basename: {path.name}")
        files[path.name] = path

    skill = f"retro-web-ui-{version}.zip"
    wheel = f"retro_web_ui_skill-{version}-py3-none-any.whl"
    sdist = f"retro_web_ui_skill-{version}.tar.gz"
    expected = {skill, wheel, sdist, f"{skill}.sha256", f"{wheel}.sha256", f"{sdist}.sha256"}
    reports: dict[str, Path] = {}
    native_payloads: dict[str, str] = {}
    for name, path in files.items():
        report_match = re.fullmatch(r"native-report-(linux|macos|windows)-([A-Za-z0-9_]+)\.json", name)
        native_match = re.fullmatch(rf"retro-web-ui-gui-{re.escape(version)}-(linux|macos|windows)-([A-Za-z0-9_]+)\.(?:zip|tar\.gz)", name)
        if report_match:
            platform = report_match.group(1)
            require(platform not in reports, f"multiple native reports for {platform}")
            reports[platform] = path
            expected.add(name)
        elif native_match:
            platform = native_match.group(1)
            require(platform not in native_payloads, f"multiple native payloads for {platform}")
            native_payloads[platform] = name
            expected.update({name, f"{name}.sha256"})
    require(set(reports) == PLATFORMS, f"native reports must cover {sorted(PLATFORMS)}; found {sorted(reports)}")
    require(set(native_payloads) == PLATFORMS, f"native payloads must cover {sorted(PLATFORMS)}; found {sorted(native_payloads)}")
    require(set(files) == expected, f"release asset set mismatch; missing={sorted(expected - set(files))}, unexpected={sorted(set(files) - expected)}")

    for payload_name in sorted(name for name in expected if not name.endswith((".sha256", ".json"))):
        digest = sha256(files[payload_name])
        sidecar = files[f"{payload_name}.sha256"]
        require(parse_checksum(sidecar, payload_name) == digest, f"checksum digest mismatch: {sidecar.name}")
    for platform, report in reports.items():
        validate_native_report(report, files, version, expected_commit)
        data = json.loads(report.read_text(encoding="utf-8"))
        require(data["artifact"] == native_payloads[platform], f"native report/payload platform mismatch: {report.name}")

    assets = [
        {"name": name, "size": files[name].stat().st_size, "sha256": sha256(files[name])}
        for name in sorted(expected)
    ]
    return {
        "schemaVersion": 1,
        "state": STATE_CANDIDATE,
        "version": version,
        "tag": f"v{version}",
        "expectedCommit": expected_commit,
        "assets": assets,
    }


def load_manifest(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CertificationError(f"manifest is unavailable or malformed: {path}") from error
    require(isinstance(value, dict) and value.get("schemaVersion") == 1, "manifest schema is missing or unsupported")
    require(value.get("state") == STATE_CANDIDATE, "manifest is not a release candidate record")
    require(isinstance(value.get("assets"), list) and value["assets"], "manifest asset list is missing")
    return value


def expected_assets(manifest: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    for asset in manifest["assets"]:
        require(isinstance(asset, dict), "manifest asset entry is malformed")
        name, size, digest = asset.get("name"), asset.get("size"), asset.get("sha256")
        require(isinstance(name, str) and name and name not in result, "manifest asset name is missing or duplicated")
        require(isinstance(size, int) and size >= 0, f"manifest asset size is malformed: {name}")
        require(isinstance(digest, str) and DIGEST.fullmatch(digest) is not None, f"manifest asset digest is malformed: {name}")
        result[name] = asset
    return result


def validate_local_assets(root: Path, manifest: Mapping[str, Any]) -> dict[str, Path]:
    wanted = expected_assets(manifest)
    paths: dict[str, Path] = {}
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        require(not path.is_symlink(), f"release asset must not be a symlink: {path.name}")
        require(path.name not in paths, f"duplicate release asset basename: {path.name}")
        paths[path.name] = path
    require(set(paths) == set(wanted), f"local release asset set mismatch; missing={sorted(set(wanted) - set(paths))}, unexpected={sorted(set(paths) - set(wanted))}")
    for name, expected in wanted.items():
        require(paths[name].stat().st_size == expected["size"], f"local asset size changed after manifest: {name}")
        require(sha256(paths[name]) == expected["sha256"], f"local asset digest changed after manifest: {name}")
    return paths


def validate_release_statement(statement: Any, manifest: Mapping[str, Any], tag: str, context: str) -> None:
    require(isinstance(statement, dict), f"{context} statement is malformed")
    predicate = statement.get("predicate")
    require(isinstance(predicate, dict) and predicate.get("tag") == tag, f"{context} tag does not match")
    subjects = statement.get("subject")
    require(isinstance(subjects, list), f"{context} subjects are missing")
    attested: set[tuple[str, str]] = set()
    for subject in subjects:
        if not isinstance(subject, dict) or not isinstance(subject.get("digest"), dict):
            continue
        name, value = subject.get("name"), subject["digest"].get("sha256")
        if isinstance(name, str) and isinstance(value, str):
            attested.add((name, value))
    for name, expected in expected_assets(manifest).items():
        require((name, expected["sha256"]) in attested, f"{context} does not bind expected asset: {name}")


def validate_provenance(provenance: Any, manifest: Mapping[str, Any], tag: str) -> None:
    require(isinstance(provenance, dict), "release provenance verification output is not an object")
    attestation = provenance.get("attestation")
    verification_result = provenance.get("verificationResult")
    require(isinstance(attestation, dict) and attestation, "release provenance attestation is missing")
    require(isinstance(verification_result, dict), "release provenance verificationResult is missing")
    require(
        verification_result.get("mediaType") == VERIFICATION_RESULT_MEDIA_TYPE,
        "release provenance verificationResult mediaType is missing or unsupported",
    )
    require(isinstance(verification_result.get("signature"), dict) and verification_result["signature"], "release provenance verified signature is missing")
    timestamps = verification_result.get("verifiedTimestamps")
    require(isinstance(timestamps, list) and timestamps, "release provenance has no verified timestamp")
    bundle = attestation.get("bundle")
    envelope = bundle.get("dsseEnvelope") if isinstance(bundle, dict) else None
    payload = envelope.get("payload") if isinstance(envelope, dict) else None
    require(isinstance(payload, str) and payload, "release provenance DSSE payload is missing")
    try:
        statement = json.loads(base64.b64decode(payload, validate=True))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CertificationError("release provenance DSSE payload is malformed") from error
    validate_release_statement(statement, manifest, tag, "release provenance DSSE")
    validate_release_statement(verification_result.get("statement"), manifest, tag, "verified release provenance")


def validate_remote_assets(release: Mapping[str, Any], manifest: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    wanted = expected_assets(manifest)
    raw_assets = release.get("assets")
    require(isinstance(raw_assets, list), "release assets field is missing or malformed")
    actual: dict[str, Mapping[str, Any]] = {}
    for asset in raw_assets:
        require(isinstance(asset, dict), "release asset entry is malformed")
        name = asset.get("name")
        require(isinstance(name, str) and name and name not in actual, "release asset name is missing or duplicated")
        actual[name] = asset
    require(set(actual) == set(wanted), f"remote asset set mismatch; missing={sorted(set(wanted) - set(actual))}, unexpected={sorted(set(actual) - set(wanted))}")
    for name, expected in wanted.items():
        asset = actual[name]
        require(asset.get("size") == expected["size"], f"remote asset size mismatch: {name}")
        require(asset.get("digest") == f"sha256:{expected['sha256']}", f"remote asset digest missing or mismatched: {name}")
    return actual


def get_release(api: GitHubAPI, repo: str, tag: str) -> Mapping[str, Any]:
    _, release = api.get(f"/repos/{repo}/releases/tags/{encoded(tag)}")
    require(isinstance(release, dict), "release response is malformed")
    require(release.get("tag_name") == tag, "release tag_name does not match requested tag")
    return release


def get_release_by_id(api: GitHubAPI, repo: str, release_id: int) -> Mapping[str, Any]:
    _, release = api.get(f"/repos/{repo}/releases/{release_id}")
    require(isinstance(release, dict) and release.get("id") == release_id, "release ID response is malformed or mismatched")
    return release


def load_creation_record(path: Path, tag: str, expected_commit: str) -> Mapping[str, Any]:
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CertificationError("draft creation record is unavailable or malformed") from error
    require(isinstance(record, dict) and record.get("draftCreated") is True, "draft creation record is malformed")
    require(record.get("tag") == tag and record.get("expectedCommit") == expected_commit, "draft creation record tag or commit mismatch")
    require(isinstance(record.get("releaseId"), int), "draft creation record has no release ID")
    return record


def verify_release_shape(release: Mapping[str, Any], manifest: Mapping[str, Any], *, draft: bool) -> None:
    require(require_bool(release, "draft", "release") is draft, f"release draft state must be {str(draft).lower()}")
    require(require_bool(release, "prerelease", "release") is False, "release must not be a prerelease")
    require(release.get("tag_name") == manifest.get("tag"), "release tag does not match manifest")


def download_public_asset(url: str, destination: Path) -> None:
    require(url.startswith("https://github.com/"), "asset browser_download_url is missing or not a GitHub HTTPS URL")
    request = urllib.request.Request(url, headers={"User-Agent": "retro-web-ui-release-certification"})
    try:
        with urllib.request.urlopen(request, timeout=120) as response, destination.open("wb") as target:
            require(response.status == 200, f"public asset download returned HTTP {response.status}")
            while block := response.read(1024 * 1024):
                target.write(block)
    except (urllib.error.URLError, OSError, TimeoutError) as error:
        raise CertificationError(f"public asset download failed for {destination.name}: {error}") from error


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def token_from_env(name: str) -> str:
    token = os.environ.get(name)
    require(isinstance(token, str) and token.strip() != "", f"required token environment variable {name} is unavailable")
    return token


def require_release_tag(tag: str) -> None:
    require(tag.startswith("v") and SEMVER.fullmatch(tag[1:]) is not None, "release tag must be canonical vMAJOR.MINOR.PATCH")


def require_immutable_preflight(api: GitHubAPI, repo: str) -> None:
    status, setting = api.get(f"/repos/{repo}/immutable-releases", expected=(200, 401, 403, 404))
    validate_immutable_preflight_response(status, setting)


def command_repository_preflight(args: argparse.Namespace) -> dict[str, Any]:
    require_release_tag(args.tag)
    require(SHA.fullmatch(args.expected_commit) is not None, "expected commit must be a full lowercase SHA")
    require_immutable_preflight(GitHubAPI(token_from_env(args.admin_token_env)), args.repo)
    api = GitHubAPI(token_from_env(args.token_env))
    release_status, _ = api.get(f"/repos/{args.repo}/releases/tags/{encoded(args.tag)}", expected=(200, 404))
    require(release_status == 404, f"release {args.tag} already exists; use a new version and tag")
    tag_status, _ = api.get(f"/repos/{args.repo}/git/ref/tags/{encoded(args.tag)}", expected=(200, 404))
    require(tag_status == 404, f"tag {args.tag} already exists; use a new version")
    branch, branch_commit = default_branch_commit(api, args.repo)
    require(branch_commit == args.expected_commit, f"default branch {branch} is {branch_commit}, not expected commit {args.expected_commit}")
    return {
        "state": STATE_CANDIDATE,
        "phase": "protected-pre-tag-preflight",
        "repository": args.repo,
        "tag": args.tag,
        "expectedCommit": args.expected_commit,
        "defaultBranch": branch,
        "defaultBranchCommit": branch_commit,
        "workflowRunId": args.workflow_run_id,
    }


def command_preflight(args: argparse.Namespace) -> dict[str, Any]:
    require_release_tag(args.tag)
    require_immutable_preflight(GitHubAPI(token_from_env(args.admin_token_env)), args.repo)
    api = GitHubAPI(token_from_env(args.token_env))
    status, _ = api.get(f"/repos/{args.repo}/releases/tags/{encoded(args.tag)}", expected=(200, 404))
    require(status == 404, f"release {args.tag} already exists; use a new version and tag")
    identity = verify_tag_identity(api, args.repo, args.tag, args.expected_commit)
    preflight = verify_preflight_run(api, args.repo, args.tag, args.expected_commit)
    return {"state": STATE_CANDIDATE, "repository": args.repo, "tag": args.tag, "expectedCommit": args.expected_commit, **identity, **preflight}


def command_create_draft(args: argparse.Namespace) -> dict[str, Any]:
    manifest = load_manifest(args.manifest)
    require(manifest.get("tag") == args.tag and manifest.get("expectedCommit") == args.expected_commit, "manifest tag or commit does not match command")
    paths = validate_local_assets(args.root, manifest)
    api = GitHubAPI(token_from_env(args.token_env))
    identity = verify_tag_identity(api, args.repo, args.tag, args.expected_commit)
    status, _ = api.get(f"/repos/{args.repo}/releases/tags/{encoded(args.tag)}", expected=(200, 404))
    require(status == 404, f"release {args.tag} already exists; create-only publication refuses to update it")
    try:
        body = args.body.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise CertificationError(f"release notes are unavailable or malformed: {args.body}") from error
    status, release = api.post_json(
        f"/repos/{args.repo}/releases",
        {
            "tag_name": args.tag,
            "target_commitish": args.expected_commit,
            "name": args.tag,
            "body": body,
            "draft": True,
            "prerelease": False,
            "make_latest": "false",
        },
        expected=(201, 422),
    )
    require(status == 201, f"create-only draft creation returned HTTP {status}; a concurrent Release or invalid request was not updated")
    require(isinstance(release, dict) and isinstance(release.get("id"), int), "created draft response is malformed")
    release_id = release["id"]
    created = get_release_by_id(api, args.repo, release_id)
    verify_release_shape(created, manifest, draft=True)
    require(created.get("assets") == [], "newly created draft unexpectedly already contains assets")
    upload_template = created.get("upload_url")
    require(isinstance(upload_template, str), "created draft has no upload URL")
    upload_base = upload_template.partition("{")[0]
    for name in sorted(paths):
        query = urllib.parse.urlencode({"name": name})
        uploaded = api.upload(f"{upload_base}?{query}", paths[name].read_bytes())
        require(isinstance(uploaded, dict) and uploaded.get("name") == name, f"GitHub upload response mismatch: {name}")
    return {
        "state": STATE_CANDIDATE,
        "draftCreated": True,
        "tag": args.tag,
        "expectedCommit": args.expected_commit,
        "releaseId": release_id,
        "assetsUploaded": len(paths),
        **identity,
    }


def command_verify_draft(args: argparse.Namespace) -> dict[str, Any]:
    manifest = load_manifest(args.manifest)
    require(manifest.get("tag") == args.tag and manifest.get("expectedCommit") == args.expected_commit, "manifest tag or commit does not match command")
    creation = load_creation_record(args.draft_creation, args.tag, args.expected_commit)
    api = GitHubAPI(token_from_env(args.token_env))
    identity = verify_tag_identity(api, args.repo, args.tag, args.expected_commit)
    release = get_release_by_id(api, args.repo, creation["releaseId"])
    verify_release_shape(release, manifest, draft=True)
    validate_remote_assets(release, manifest)
    return {"state": STATE_CANDIDATE, "draftVerified": True, "releaseId": release.get("id"), **identity}


def command_publish_draft(args: argparse.Namespace) -> dict[str, Any]:
    manifest = load_manifest(args.manifest)
    require(manifest.get("tag") == args.tag and manifest.get("expectedCommit") == args.expected_commit, "manifest tag or commit does not match command")
    creation = load_creation_record(args.draft_creation, args.tag, args.expected_commit)
    api = GitHubAPI(token_from_env(args.token_env))
    identity = verify_tag_identity(api, args.repo, args.tag, args.expected_commit)
    release = get_release_by_id(api, args.repo, creation["releaseId"])
    verify_release_shape(release, manifest, draft=True)
    validate_remote_assets(release, manifest)
    _, published = api.patch_json(
        f"/repos/{args.repo}/releases/{creation['releaseId']}",
        {"draft": False, "make_latest": "true"},
        expected=(200,),
    )
    require(isinstance(published, dict) and published.get("id") == creation["releaseId"], "published release ID changed")
    verify_release_shape(published, manifest, draft=False)
    return {
        "state": STATE_PENDING,
        "repository": args.repo,
        "tag": args.tag,
        "expectedCommit": args.expected_commit,
        "releaseId": creation["releaseId"],
        **identity,
    }


def command_verify_public(args: argparse.Namespace) -> dict[str, Any]:
    manifest = load_manifest(args.manifest)
    require(manifest.get("tag") == args.tag and manifest.get("expectedCommit") == args.expected_commit, "manifest tag or commit does not match command")
    creation = load_creation_record(args.draft_creation, args.tag, args.expected_commit)
    api = GitHubAPI(token_from_env(args.token_env))
    identity = verify_tag_identity(api, args.repo, args.tag, args.expected_commit)
    release = get_release(api, args.repo, args.tag)
    require(release.get("id") == creation["releaseId"], "public release ID does not match the create-only draft")
    verify_release_shape(release, manifest, draft=False)
    actual = validate_remote_assets(release, manifest)
    wanted = expected_assets(manifest)
    with tempfile.TemporaryDirectory(prefix="retro-release-public-") as temporary:
        root = Path(temporary)
        for name, expected in wanted.items():
            url = actual[name].get("browser_download_url")
            require(isinstance(url, str), f"public download URL is missing: {name}")
            downloaded = root / name
            download_public_asset(url, downloaded)
            require(downloaded.stat().st_size == expected["size"], f"public asset size mismatch: {name}")
            require(sha256(downloaded) == expected["sha256"], f"public asset digest mismatch: {name}")
        for name in wanted:
            if name.endswith(".sha256"):
                payload_name = name.removesuffix(".sha256")
                require(parse_checksum(root / name, payload_name) == wanted[payload_name]["sha256"], f"public checksum mismatch: {name}")
    return {
        "schemaVersion": 1,
        "state": STATE_PENDING,
        "repository": args.repo,
        "tag": args.tag,
        "expectedCommit": args.expected_commit,
        "releaseId": release.get("id"),
        "publicAssetsVerified": len(wanted),
        "manifestSha256": sha256(args.manifest),
        **identity,
    }


def command_certify(args: argparse.Namespace) -> dict[str, Any]:
    manifest = load_manifest(args.manifest)
    require(manifest.get("tag") == args.tag and manifest.get("expectedCommit") == args.expected_commit, "manifest tag or commit does not match command")
    try:
        public_record = json.loads(args.public_verification.read_text(encoding="utf-8"))
        provenance = json.loads(args.provenance.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CertificationError("public-byte or provenance verification record is unavailable or malformed") from error
    require(isinstance(public_record, dict), "public verification record is malformed")
    require(public_record.get("state") == STATE_PENDING, "public verification record is not pending final certification")
    require(public_record.get("tag") == args.tag and public_record.get("expectedCommit") == args.expected_commit, "public verification record tag or commit mismatch")
    require(public_record.get("publicAssetsVerified") == len(expected_assets(manifest)), "public verification asset count mismatch")
    require(public_record.get("manifestSha256") == sha256(args.manifest), "manifest changed after public-byte verification")
    validate_provenance(provenance, manifest, args.tag)
    api = GitHubAPI(token_from_env(args.token_env))
    identity = verify_tag_identity(api, args.repo, args.tag, args.expected_commit)
    release = get_release(api, args.repo, args.tag)
    require(release.get("id") == public_record.get("releaseId"), "final release ID does not match public-byte verification")
    verify_release_shape(release, manifest, draft=False)
    validate_remote_assets(release, manifest)
    validate_release_immutable(release)
    return {
        "schemaVersion": 1,
        "state": STATE_RELEASED,
        "repository": args.repo,
        "tag": args.tag,
        "expectedCommit": args.expected_commit,
        "releaseId": release.get("id"),
        "immutable": True,
        "publicAssetsVerified": public_record["publicAssetsVerified"],
        "provenanceVerified": True,
        **identity,
    }


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    commands = value.add_subparsers(dest="command", required=True)
    for name in ("repository-preflight", "preflight"):
        preflight = commands.add_parser(name)
        preflight.add_argument("--repo", required=True)
        preflight.add_argument("--tag", required=True)
        preflight.add_argument("--expected-commit", required=True)
        preflight.add_argument("--admin-token-env", default="IMMUTABLE_RELEASE_ADMIN_TOKEN")
        preflight.add_argument("--token-env", default="GITHUB_TOKEN")
        if name == "repository-preflight":
            preflight.add_argument("--workflow-run-id", required=True, type=int)

    manifest = commands.add_parser("manifest")
    manifest.add_argument("--root", type=Path, required=True)
    manifest.add_argument("--version", required=True)
    manifest.add_argument("--expected-commit", required=True)
    manifest.add_argument("--output", type=Path, required=True)

    create = commands.add_parser("create-draft")
    create.add_argument("--repo", required=True)
    create.add_argument("--tag", required=True)
    create.add_argument("--expected-commit", required=True)
    create.add_argument("--manifest", type=Path, required=True)
    create.add_argument("--root", type=Path, required=True)
    create.add_argument("--body", type=Path, required=True)
    create.add_argument("--output", type=Path, required=True)
    create.add_argument("--token-env", default="GITHUB_TOKEN")

    for name in ("verify-draft", "publish-draft", "verify-public", "certify"):
        command = commands.add_parser(name)
        command.add_argument("--repo", required=True)
        command.add_argument("--tag", required=True)
        command.add_argument("--expected-commit", required=True)
        command.add_argument("--manifest", type=Path, required=True)
        command.add_argument("--token-env", default="GITHUB_TOKEN")
        if name == "certify":
            command.add_argument("--output", type=Path, required=True)
            command.add_argument("--public-verification", type=Path, required=True)
            command.add_argument("--provenance", type=Path, required=True)
        elif name == "verify-public":
            command.add_argument("--output", type=Path, required=True)
            command.add_argument("--draft-creation", type=Path, required=True)
        elif name in ("verify-draft", "publish-draft"):
            command.add_argument("--draft-creation", type=Path, required=True)
            if name == "publish-draft":
                command.add_argument("--output", type=Path, required=True)
    return value


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "repository-preflight":
            result = command_repository_preflight(args)
        elif args.command == "preflight":
            result = command_preflight(args)
        elif args.command == "manifest":
            result = build_manifest(args.root, args.version, args.expected_commit)
            write_json(args.output, result)
        elif args.command == "create-draft":
            result = command_create_draft(args)
            write_json(args.output, result)
        elif args.command == "verify-draft":
            result = command_verify_draft(args)
        elif args.command == "publish-draft":
            result = command_publish_draft(args)
            write_json(args.output, result)
        elif args.command == "verify-public":
            result = command_verify_public(args)
            write_json(args.output, result)
        else:
            result = command_certify(args)
            write_json(args.output, result)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except CertificationError as error:
        print(f"release certification blocked: {error}", file=os.sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
