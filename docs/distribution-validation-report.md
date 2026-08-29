# v2.0.1 distribution hardening validation report

Date: 2026-08-30

Candidate commit: `b1ef3a3f8eb38a4a2faee7550dfc6ddd5be4842b` for product code,
with test-only isolation at `39663c16b16e1e1e03404c3e9cb8be01d9992468`

Status: ready for release review; no release or tag was created

This report supplements the [desktop GUI engineering report](gui-validation-report.md).
It covers installation and distribution failures found by replaying the public
v2.0.0 artifacts and then exercising the hardened v2.0.1 candidate exactly as an
end user receives it. The public `v2.0.0` release, its tag, and `main` remain at
`7f7e3007ea3230ed65b748ea9b6527fa71794045` and were not rewritten.

## Architecture and scope

The application architecture remains:

```text
PySide6/Qt Widgets -> DesktopController -> ConversionWorkflow
                                      |-> CoreFacade -> canonical CLI/Core
                                      `-> CodexBridge -> codex app-server
                                                       -> user's Codex + bundled Skill
```

The hardening work does not add a GUI-owned semantic engine. `CoreFacade`
continues to consume versioned CLI/Core contracts for analysis, application
selection, behavior artifacts, themes, audit, and deterministic verification.
`CodexBridge` owns discovery, local stdio JSONL, initialization, account/model
readiness, threads/turns, events, approvals, interruption, recovery, and
shutdown. The App Server uses the user's existing Codex/ChatGPT authentication;
the application does not ask for or persist an API key.

## Public baseline replay

The public v2.0.0 macOS, Windows, and Linux archives and adjacent checksum
manifests were downloaded, hashed, and extracted independently. The macOS
archive was also launched on a physical Apple-silicon host and used with the
host's existing ChatGPT-signed-in Codex.

That replay exposed distribution-relevant defects which a build-tree smoke did
not reveal:

- Linux v2.0.0 required GLIBC 2.38 and therefore could not run on Ubuntu 22.04.
- the frozen doctor path could mistake a bundled runtime library for a runnable
  Python interpreter;
- raw streaming deltas made the activity list difficult to review;
- deterministic evidence could hide missing browser/runtime review behind a
  `Complete` result;
- first launch did not immediately establish Codex readiness;
- final archives did not yet enforce a uniform extraction, inventory, ABI, and
  post-archive startup contract.

The baseline replay is evidence for these failures, not a modification of the
published release.

## Generalized corrections

| Failure | Owning layer | Generalized correction | Regression evidence |
| --- | --- | --- | --- |
| frozen runtime library looked executable | Core/packaging boundary | report `runtime_kind` and `runnable`; use bundled Core in process | doctor/Core tests and final archive smoke |
| delta event flood | Codex integration/GUI | suppress raw fragments; retain authoritative completed events with a 500-event bound | fake event stream and real streamed turn |
| missing runtime review could become `Complete` | workflow/integration | require a turn-matched structured final assessment and merge it conservatively with deterministic status | malformed/missing/foreign-turn tests and real candidate conversion |
| no first-launch readiness | GUI state | automatically perform Codex discovery/account/model readiness at launch | widget/controller tests and physical Finder launch |
| archive checks differed by OS | packaging | normalize root/launcher/notices, reject unsafe entries, re-extract, execute, and reconcile inventory/checksum | three native jobs and independent artifact replay |
| Linux runner leaked a new ABI floor | platform/packaging | build on Ubuntu 22.04; record GLIBC/GLIBCXX/CXXABI; fail above GLIBC 2.35 | Linux native report and ABI gate |
| post-sign inventory changed the macOS seal | macOS packaging | create inventory before signing and place the post-sign report outside the app | strict local and CI `codesign` replay |
| Finder launch lacked a useful `PATH` | Codex integration/platform | bounded absolute discovery of ChatGPT/Codex and common platform installs | physical Finder launch plus macOS/Windows/Linux discovery tests |
| repository-local `codex` could shadow the launcher | Codex integration/security | reject relative, current-directory, and selected-project launchers; pin one validated absolute path for startup | unsafe PATH/CWD, no-spawn, and platform fallback tests |
| fake transport tests depended on host Codex | test infrastructure | use an explicit harmless absolute executable except in discovery-specific tests | final three-OS standard CI |

## Candidate artifacts

Artifacts were downloaded from [native run 33256977484](https://github.com/ririri-rgb/retro-web-ui/actions/runs/33256977484),
their adjacent manifests were checked independently, and every archive passed
the root, traversal, collision, symlink/special-file, notice, license, inventory,
version, and isolated-startup validators.

| Platform | Compressed bytes | Expanded bytes | SHA-256 | Signing / ABI |
| --- | ---: | ---: | --- | --- |
| macOS arm64 | 28,838,942 | 82,570,032 | `25c47b6d8e1e45d51ab30a38222de2ce69c97de687ce8cc08098dcc7f8cae3d0` | strict ad-hoc signature verified; bundle ID `io.github.ririri-rgb.retro-web-ui` |
| Windows x86_64 | 29,899,294 | 75,621,430 | `8a0b959206c9acec70604db3de329f56a719844ff813dd03bc3785c5d6b44e30` | unsigned |
| Linux x86_64 | 58,793,819 | 153,852,098 | `a3c31fbcfb1a36a9c29607e0fef3e32106d599ca055cb00c27396b8a55f29984` | GLIBC 2.35, GLIBCXX 3.4.29, CXXABI 1.3.13 |

All three final archives reported version 2.0.1, loaded the bundled Core and
Skill, passed manifest compatibility, detected Codex CLI `0.150.0-alpha.8`,
initialized App Server, and created a visible offscreen Qt window in native CI.
Codex itself is an external prerequisite and is not bundled.

## Installed macOS and real conversion replay

The downloaded macOS ZIP was extracted outside the repository. The final app
passed `codesign --verify --deep --strict`, reported version 2.0.1 and the stable
bundle identifier, and started from Finder-style desktop context. With a
sanitized terminal-minimal `PATH`, the bridge found the Codex executable
embedded in the installed ChatGPT application, reused the existing ChatGPT
sign-in, initialized App Server, and displayed the advertised models without an
API key or copied credential.

From that final app, a user selected a fresh Git-backed static Settings Center,
analyzed it, chose Windows XP, selected GPT-5.6-Terra with Medium reasoning, and
started a real App Server/Skill conversion. The turn changed only `index.html`
and `styles.css`; `app.js` remained unchanged. The GUI displayed the completed
event stream, full diff, deterministic verification, behavior review, semantic
assessment, and the final classification `complete_with_review_items`.

The canonical CLI was replayed independently against a fresh external behavior
baseline. Static audit was clean, zero protected signals were removed, and two
added form/accessibility signals correctly kept the result at `review_required`.
The GUI's Before/After tab explicitly said that screenshots were unavailable
instead of fabricating visual evidence.

An independent browser replay then:

- switched General and Notifications and observed the matching `hidden` state;
- filled the display name and checkbox, submitted, and observed
  `Settings saved.` in the live status region;
- reset the form to its original values;
- confirmed labels and standard control roles in the accessibility tree;
- inspected the normal and 520 px-wide Windows XP layouts;
- observed zero browser console warnings or errors.

This extra browser replay resolves the tested static target's interaction and
visual review item, while the GUI classification remains correctly conservative
because those checks were not available inside the original turn.

The previous v2.0.0 engineering evidence still supplies the heterogeneous real
OSS loop: pinned MIT TodoMVC was selected from a monorepo, converted through the
GUI/App Server/Skill workflow, approved and built, kept generated JavaScript
byte-identical, preserved behavior signals and the active hash route, and passed
browser review. The distribution patch does not change that semantic engine;
the full standard regression protects it.

## Automated validation

- [CI run 33257139469](https://github.com/ririri-rgb/retro-web-ui/actions/runs/33257139469)
  passed Python-minimum, three-OS CLI portability/reproducibility/clean install,
  three-OS GUI portability/state/bridge tests, fixture builds, production
  dependency audit, browser interaction/render smoke, and diff hygiene.
- Local final discovery suite: 108 tests passed; five PySide presentation tests
  were intentionally skipped in the source environment without PySide.
- All four themes, Skill validation, Core import, CLI JSON contracts, behavior
  guard, fixtures, wheel/sdist reproducibility, and clean-install checks passed.
- Production dependency audit reported zero vulnerabilities. A low-severity
  cookie advisory remains only in a development SvelteKit fixture dependency,
  has no available fix in that fixture line, and is not packaged in the desktop
  application.

## Security review

- Authentication and credentials remain owned by Codex; credential-, token-,
  device-code-, login-URL-, and JWT-shaped values are redacted from diagnostics.
- Launcher discovery is absolute, executable, bounded, selected-root aware, and
  fails closed; startup uses the same resolved path that discovery approved.
- The selected application is the only agent write root. Canonical path and
  symlink checks prevent an application outside the selected repository, and
  unrelated dirty work is never reverted.
- Commands use argv without a shell. Agent command/file/permission requests are
  presented with operation, working directory, reason/scope, and risk; Deny is
  the default.
- Archives reject traversal, absolute paths, collisions, links, and special
  files, then reconcile every packaged component against a hashed inventory and
  required notices. Codex, credentials, caches, and secrets are not bundled.

## Performance and storage

On the physical Apple-silicon validation host, the final frozen executable's
`--version` cold process completed in 0.14 seconds. After launch and automatic
App Server readiness, an observed idle sample used about 148 MiB RSS for the Qt
GUI and 86 MiB RSS for the separately managed Codex App Server process; both
processes exited after the GUI closed. These are point measurements, not a
cross-platform benchmark. The 500-event UI bound prevents unbounded activity
growth. Exact archive and expanded sizes are recorded above.

The prior engineering measurements remain representative for the same
architecture: roughly 529 ms to construct/process the first offscreen GUI event,
roughly 76 ms for App Server initialize and 81 ms for account/model readiness
with an existing login. Agent conversion duration is target/model dependent and
is not presented as deterministic performance.

## Cross-platform evidence and limitations

| Platform | Candidate evidence | Remaining boundary |
| --- | --- | --- |
| macOS arm64 | final ZIP download/hash/extract, strict signature, physical desktop startup, existing ChatGPT auth, real App Server turn/conversion, browser review | ad-hoc signature only; no Developer ID/notarization/Gatekeeper acceptance claim |
| Windows x86_64 | host-native build, final ZIP re-extract/startup, Core/Skill/App Server smoke, full Windows tests, safe npm/app fallback contracts | unsigned; no physical Explorer/SmartScreen or assistive-technology session |
| Linux x86_64 | Ubuntu 22.04 build, final tar re-extract/offscreen startup, Core/Skill/App Server smoke, ABI ceiling and full Linux tests | no physical X11/Wayland session; compatible EGL/libstdc++/desktop stack required |

GUI limitations remain archive installation rather than DMG/MSI/AppImage,
unsigned/unnotarized OS reputation, no automatic target-server discovery or
screenshot capture, and unverified physical Windows/Linux desktop UX. Skill
limitations remain separate: behavior hashes are review signals rather than
semantic proof, and portals, hydration, virtualized UI, dependency CSS, canvas,
closed Shadow DOM, and application-specific flows still require target-aware
runtime review.

## Saturation and release recommendation

The final loop covered a public-download failure replay, three final native
archives, physical macOS installation, real authenticated App Server conversion,
independent deterministic and browser review, and the existing real-OSS
regression baseline. New failures converged into their owning Core, bridge, GUI,
packaging, platform, or test layers and gained non-project-specific regression
coverage. The remaining gaps are explicitly bounded signing, physical-platform,
installer, and target-specific runtime issues rather than unresolved
cross-cutting ownership defects.

**Release recommendation: Ready for GUI release review.** Recommended version:
`v2.0.1`, because the candidate is a backward-compatible security,
classification, startup, and distribution-hardening patch over v2.0.0 rather
than a new product boundary. Before publication, a maintainer still needs to
approve the final report/version, decide whether unsigned/unnotarized archives
meet release policy, create the immutable tag, let the tag workflow rebuild the
artifacts, and verify the public downloads. This report does not perform any of
those publication actions.
