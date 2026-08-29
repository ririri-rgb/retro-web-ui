# Desktop distribution and clean-install guide

This document separates what is packaged, what was actually exercised, and
what remains an operating-system or signing boundary. The native application
is portable: there is no installer, background service, auto-updater, hosted
backend, or application-owned credential store.

## Choose and verify an artifact

Download the archive and its adjacent `.sha256` file from the same GitHub
release. Match both operating system and architecture:

| Platform | Archive | Current scope |
| --- | --- | --- |
| Apple silicon macOS | `retro-web-ui-gui-<version>-macos-arm64.zip` | arm64 only |
| 64-bit Windows | `retro-web-ui-gui-<version>-windows-x86_64.zip` | x86_64 only |
| 64-bit Linux | `retro-web-ui-gui-<version>-linux-x86_64.tar.gz` | x86_64 only |

Verify before extraction:

```bash
# macOS
shasum -a 256 retro-web-ui-gui-<version>-macos-arm64.zip

# Linux
sha256sum retro-web-ui-gui-<version>-linux-x86_64.tar.gz
```

```powershell
# Windows PowerShell
Get-FileHash retro-web-ui-gui-<version>-windows-x86_64.zip -Algorithm SHA256
```

The printed digest must exactly match the first field of the downloaded
`.sha256` file. Do not bypass an OS warning for an artifact with a mismatched
checksum.

## macOS arm64

Extract the ZIP and move `Retro Web UI GUI.app` to `Applications` or another
user-writable directory. The credential-free release lane applies and strictly
verifies an ad-hoc code signature before and after archiving. This is an
integrity check, not Apple Developer ID signing, notarization, stapling, or a
Gatekeeper acceptance claim.

After verifying the checksum, open the app using Finder's **Open** command or
the normal Privacy & Security decision shown by macOS. Do not remove quarantine
metadata and do not disable Gatekeeper. The ZIP intentionally retains
`__MACOSX`/AppleDouble records required to preserve the final bundle's resource
signature; the build gate re-extracts the deliverable and verifies the signature
and executable rather than assuming a visually cleaner ZIP is safer.

To uninstall, quit the application and delete the `.app`, extracted folder if
one remains, and downloaded ZIP. The portable app creates no service or updater.

## Windows x86_64

Use Explorer's **Extract All**, keep the entire `Retro Web UI GUI` folder
together, and run:

```text
Retro Web UI GUI\retro-web-ui-gui.exe
```

Sibling DLLs and Qt directories are part of the application and must not be
moved away from the executable. The current credential-free build is not
Authenticode-signed. Windows SmartScreen wording and reputation vary by policy,
network, and download provenance. Do not disable SmartScreen or Defender;
continue only after the checksum matches and the OS information is understood.

To uninstall, quit the application and delete the complete extracted folder
and downloaded ZIP. There is no MSI/MSIX installer, registry configuration,
Start menu entry, desktop shortcut, service, or updater to remove.

## Linux x86_64

Extract and launch from a regular desktop session:

```bash
tar -xzf retro-web-ui-gui-<version>-linux-x86_64.tar.gz
./retro-web-ui-gui/retro-web-ui-gui
```

The 2.0.1 candidate is built on Ubuntu 22.04 and rejects an artifact whose
bundled binaries require a glibc newer than 2.35. A compatible libstdc++ and
the normal Qt X11 or Wayland desktop libraries—including EGL support—remain
system dependencies. Offscreen CI startup does not prove every physical X11 or
Wayland session. The public v2.0.0 archive was built on a newer runner and was
measured to require GLIBC 2.38; it is not compatible with Ubuntu 22.04.

To uninstall, quit the application and delete the extracted directory and
downloaded archive. The tarball does not install a `.desktop` entry, system
package, service, or updater.

## Codex and ChatGPT sign-in

Codex is an external prerequisite. Install it using the current
[official Codex documentation](https://developers.openai.com/codex/), sign in
with ChatGPT, and verify:

```text
codex --version
codex app-server --help
```

At first launch, the GUI automatically checks the launcher, starts the local
App Server, reads the existing account state, and discovers models/config. It
does not request an API key or copy credentials. App Server traffic is local
stdio JSONL; authentication remains owned by Codex.

If the GUI reports **Codex unavailable**, confirm that `codex --version` works
from a new terminal. The bridge accepts absolute entries from `PATH` and checks
bounded common install locations, including the ChatGPT/Codex application
resources on macOS and npm's `%APPDATA%\npm\codex.cmd` on Windows. Empty,
current-directory, relative, and selected-project launcher paths are rejected;
an untrusted repository-local `codex` file is never used as App Server. If the
GUI reports an App Server startup error, run `codex app-server --help`, update
Codex if necessary, and choose **Reconnect**. Local project analysis remains
available while Codex is absent or signed out.

The native archive contains the matching Skill files so the GUI can explicitly
supply them to its Codex turn. It does not install the Skill into a global Codex
directory. Install the tagged `skills/retro-web-ui` directory separately when
using `$retro-web-ui` outside the desktop application.

## Build-time distribution gates

Each native job now validates the exact archive users receive:

- one normalized application root and one expected launcher;
- no traversal, absolute paths, ambiguous Windows case collisions, or archive
  symlinks/special files;
- exact root `INSTALL.md` and required license/notice bundle;
- re-extraction into a fresh directory;
- exact `Retro Web UI GUI <version>` output;
- offscreen GUI/Core/manifest/Skill smoke;
- real App Server initialization against an externally installed Codex in CI;
- SHA-256 output and a machine-readable native report;
- final strict code-signature verification on macOS;
- recorded GLIBC/GLIBCXX/CXXABI requirements and a GLIBC 2.35 ceiling on Linux.

These gates cover archive integrity and isolated startup. They do not turn CI
into evidence for physical Windows SmartScreen, macOS quarantine/notarization,
or every Linux desktop configuration.

## Evidence levels and known boundaries

| Evidence | macOS arm64 | Windows x86_64 | Linux x86_64 |
| --- | --- | --- | --- |
| Public v2.0.0 archive/checksum inspected | yes | yes | yes |
| Public archive independently extracted | yes | yes | yes |
| Public GUI launch | physical desktop from archive | build-tree native CI only | build-tree offscreen CI only |
| Real Codex/App Server from public archive | yes | no; build-tree CI only | no; build-tree CI only |
| Real Codex conversion from public archive | yes | not physically exercised | not physically exercised |
| OS signing/reputation acceptance | ad-hoc only; not notarized | unsigned; no physical SmartScreen evidence | not applicable |
| Physical desktop coverage | current macOS host | unavailable | X11/Wayland unavailable |

The v2.0.1 candidate adds final-archive re-extraction and startup on all three
host-native CI platforms, a GLIBC 2.35 ceiling, strict post-extraction macOS
signature verification, physical macOS Finder launch, existing ChatGPT
authentication reuse, and a real final-archive conversion plus browser replay.
See the [v2.0.1 distribution hardening validation report](distribution-validation-report.md)
for exact artifact hashes, sizes, CI runs, failure classification, and the
remaining release-policy boundaries.

The remaining signing and physical-machine gaps are explicit release-policy or
credential/hardware boundaries. They must not be described as validated merely
because an archive built or an offscreen smoke passed.
