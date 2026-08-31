# Release engineering and immutable-publication policy

Date established: 2026-08-31

This policy separates a successfully published historical release from a future
release that GitHub itself makes immutable. Publication is not certification.

## v2.1.0 historical closure

Final classification:

> **RELEASED — Verified Provenance & Operational Immutability Accepted**

This is a closed historical classification. It must not be rewritten as
`RELEASED — GitHub-Enforced Immutable`.

### Accepted evidence

- Software validation: **PASSED**. Fresh candidate, `main`, tag, CI, native
  packaging, archive integrity, startup, workspace recovery, privacy, Core, CLI,
  and Skill evidence all passed for commit
  `10cf6adde75b802d2061f80c7beaff1e4be96eaa`.
- Artifact validation: **PASSED**. All 15 public assets were downloaded and their
  byte counts, SHA-256 digests, checksum sidecars, native reports, candidate
  commit, and three-platform lifecycle evidence were verified.
- Provenance validation: **PASSED**. Annotated tag object
  `1312bac841d43f3f002fbdade8bb33aae96b78ef` peels directly to the accepted
  commit; the public Release uses `v2.1.0`; `main` and the release candidate were
  the same commit at publication.
- Publication workflow: **PASSED**. Main CI run
  [33345427687](https://github.com/ririri-rgb/retro-web-ui/actions/runs/33345427687),
  tag CI run
  [33345449842](https://github.com/ririri-rgb/retro-web-ui/actions/runs/33345449842),
  native run
  [33345427612](https://github.com/ririri-rgb/retro-web-ui/actions/runs/33345427612),
  and release run
  [33345450190](https://github.com/ririri-rgb/retro-web-ui/actions/runs/33345450190)
  completed successfully.

### Historical platform limitation

At closure, GitHub reported repository immutable releases as
`enabled: false`, `enforced_by_owner: false`, and Release ID `379448443` as
`immutable: false`. GitHub-enforced immutability therefore was not enabled when
v2.1.0 was published. This is a repository-policy limitation, not a software,
artifact, checksum, or provenance failure.

Operational immutability is accepted for v2.1.0 under these exact promises:

- never move, delete, or recreate the `v2.1.0` tag;
- never edit, replace, add, or delete v2.1.0 Release assets or checksums;
- never delete and recreate the v2.1.0 GitHub Release;
- never rerun its historical write-capable release workflow;
- use a new version and new tag for every correction.

Enabling GitHub immutable releases later protects future releases only. It does
not retroactively convert v2.1.0. Destroying and recreating a correct historical
release merely to obtain a different platform flag is prohibited because that
would break the accepted provenance and operational-immutability record.

### Accepted public artifact digests

| Asset | SHA-256 |
| --- | --- |
| `native-report-linux-x86_64.json` | `b44882225188c3b150c894b5b0c053b8613b3678e255c34046c1a84ba72e6e11` |
| `native-report-macos-arm64.json` | `3238f647d3d4c7e5c2205210f61dc30eb2a022186cec915af154b5676045c587` |
| `native-report-windows-x86_64.json` | `b17df714cd088697c345875082287de51c55b73cd8e66ea0012da08365fae145` |
| `retro-web-ui-2.1.0.zip` | `02204064f76abcbe96c5abf4429d01c1c68fe4002b5aaeec00cef11ebf59851c` |
| `retro-web-ui-2.1.0.zip.sha256` | `e265429b638bc1fd902126ac03e12d869c9720e5a41d00538d8eb33407bab29b` |
| `retro-web-ui-gui-2.1.0-linux-x86_64.tar.gz` | `08ccc4d0b27585c62a8b9c1e913fe47a5a08e110cdea3115ea4e13a1a73737a1` |
| `retro-web-ui-gui-2.1.0-linux-x86_64.tar.gz.sha256` | `c5cb2a16dcf3af70d556ba1847042d912d278bcb559eb4149a1c401d8ea34824` |
| `retro-web-ui-gui-2.1.0-macos-arm64.zip` | `095f21dd8c4914ad116e1911b4a3b95e48a70ead0c5dd07fce8668517585d8d8` |
| `retro-web-ui-gui-2.1.0-macos-arm64.zip.sha256` | `7aadd0c9ad32d7cf0f97ad3d17c8f097eaf82ac133d30e7ea3e396255aea25b4` |
| `retro-web-ui-gui-2.1.0-windows-x86_64.zip` | `e60a6f8a7667187b1d0cc6f256337b10533cc106bb3d21f44f2033f993ff3d52` |
| `retro-web-ui-gui-2.1.0-windows-x86_64.zip.sha256` | `ae3ebb59b3e0597ee3eb1642d6c85ed2a94438026cbbbd9c7a62fdcb6bffec74` |
| `retro_web_ui_skill-2.1.0-py3-none-any.whl` | `af431bf909c2d760652433700fbe9b7e21009e280b8e23ba457cced5cfa87926` |
| `retro_web_ui_skill-2.1.0-py3-none-any.whl.sha256` | `f1239b8b151991df64640e6e6cc2f565a5af7ecba36a505ee48d28f8c104026c` |
| `retro_web_ui_skill-2.1.0.tar.gz` | `0cdcc21e6eb671ca63d3b2edaa987a041314e803f3475567c70d1f00355d271a` |
| `retro_web_ui_skill-2.1.0.tar.gz.sha256` | `8b6f166c360b7473c91866e1734575e125672e5e7cbb6526b4d682917fd0d2d7` |

## Future release state model

Only these states may be used:

1. **RELEASE CANDIDATE** — preflight passed, the annotated tag and default
   branch resolve to the exact candidate commit, no Release exists for the tag,
   and the local 15-asset manifest is complete.
2. **PUBLISHED — PENDING RELEASE VERIFICATION** — the verified draft was made
   public, but public bytes, checksums, release attestation, and GitHub's
   immutable flag have not all passed yet. This state is not release success.
3. **RELEASED — GitHub-Enforced Immutable** — every post-publication check passed
   and the Release API returned the literal JSON boolean `immutable: true`.

Any failure after publication leaves the release in the second state. Operators
must preserve evidence and diagnose it; they must not mutate or recreate that
release. A correction requires a new version.

## Required administrator preflight

Complete these controls before creating the next release tag:

1. Enable immutable releases in repository or organization settings. The
   authoritative preflight is
   `GET /repos/{owner}/{repo}/immutable-releases`; only HTTP 200 with the literal
   boolean `enabled: true` is accepted. The response must also expose
   `enforced_by_owner` as a boolean. That field distinguishes owner-level policy
   from repository-level enablement; GitHub's documented repository-enabled
   response may legitimately report `enforced_by_owner: false`.
2. Store a fine-grained personal access token or GitHub App installation token
   with repository **Administration: read** access as the protected `release`
   environment secret `IMMUTABLE_RELEASE_ADMIN_TOKEN`. The built-in
   `GITHUB_TOKEN` cannot receive repository Administration permission and must
   not be treated as proof that the setting was checked.
3. Configure the `release` Actions environment with required reviewers and
   deployment-branch/tag restrictions. Protect `main` and restrict release-tag
   creation to authorized maintainers.
4. Run **Future release preflight** manually for the proposed version while
   `main` is still untagged. Preserve its evidence, review it, and only then
   create the annotated tag with exactly one
   `Release-Preflight-Run: <workflow-run-id>` trailer. The tag-triggered workflow
   resolves that Actions run and requires the protected preflight workflow path,
   a successful conclusion, and the exact source commit. It then downloads that
   run's protected evidence artifact and rechecks its run ID, repository,
   version/tag, default branch, and commit before repeating the setting check and
   starting native builds. Missing, expired, stale, or mismatched preflight
   evidence fails closed.
5. Disable or tightly restrict reruns of historical release workflows. Workflow
   changes on `main` cannot remove write capability from the workflow file
   already stored in an old tag.

The workflow fails closed on absent credentials, HTTP permission errors,
unavailable APIs, non-JSON or malformed responses, missing/non-boolean fields,
`enabled: false`, `immutable: false`, lightweight or mismatched tags, default
branch mismatch, existing Release collision, or any unexpected asset.

## Immutable publication protocol

The ordering is mandatory:

1. before tag creation, use the protected manual preflight to establish the
   default-branch commit, proposed version/tag absence, absent prior Release,
   and immutable-setting prerequisite;
2. after the annotated tag is created, bind its preflight-run trailer to the
   successful manual run, repeat the immutable-setting check, and establish the
   tag object, peeled tag commit, default-branch commit, version, and notes;
3. run all software, native, security, archive, startup, and workspace gates;
4. generate the exact asset allowlist and bind every native report to version,
   candidate commit, clean tree, artifact name, byte count, and SHA-256;
5. create a **draft** through GitHub's create-only REST operation, upload the
   exact assets, and compare the complete draft API representation to the
   manifest; HTTP 422 or any existing Release is a rejection, never an update;
6. repeat draft and tag/source identity verification immediately before
   publishing the draft once; publication PATCHes only the exact Release ID
   returned by the create-only operation, never a tag lookup that could select
   a concurrently replaced Release;
7. download every asset through its public unauthenticated URL and verify bytes
   and checksum sidecars;
8. verify the GitHub release attestation with `gh release verify`, then parse
   its verified DSSE statement and require the expected tag and every expected
   asset digest;
9. fetch the Release API again and require the literal boolean
   `immutable: true`;
10. emit the machine-readable certification record and only then use
   **RELEASED — GitHub-Enforced Immutable**.

Per-tag workflow concurrency uses `cancel-in-progress: false`. An existing
Release causes rejection rather than update. Draft creation is an atomic
create-only API call; no update-capable upload action is used. All reusable
GitHub Actions in the future release path are pinned by full commit SHA.

## Authoritative GitHub references

- [Immutable releases concept](https://docs.github.com/en/code-security/concepts/supply-chain-security/immutable-releases)
- [Prevent release changes](https://docs.github.com/en/code-security/how-tos/secure-your-supply-chain/establish-provenance-and-integrity/prevent-release-changes)
- [Check whether immutable releases are enabled](https://docs.github.com/en/rest/repos/repos#check-if-immutable-releases-are-enabled-for-a-repository)
- [Verify release integrity](https://docs.github.com/en/code-security/how-tos/secure-your-supply-chain/secure-your-dependencies/verify-release-integrity)
- [GitHub Actions `GITHUB_TOKEN` permissions](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#defining-access-for-the-github_token-scopes)
- [Granting additional permissions](https://docs.github.com/en/actions/tutorials/authenticate-with-github_token#granting-additional-permissions)
