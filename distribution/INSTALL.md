# Retro Web UI GUI portable installation

This archive contains the desktop GUI, Python runtime, Qt runtime, bundled
Retro Web UI Core/CLI, Skill instructions, and licenses. Codex is deliberately
not bundled. The GUI uses the current user's existing Codex installation and
ChatGPT sign-in; it never asks for an OpenAI API key.

Before opening the archive, download its adjacent `.sha256` file from the same
GitHub release and compare the SHA-256 value.

## macOS arm64

1. Verify with `shasum -a 256 retro-web-ui-gui-*-macos-arm64.zip`.
2. Open the ZIP and move `Retro Web UI GUI.app` to `Applications` or another
   user-writable folder.
3. Open the app. This portable build has a verified ad-hoc signature but is not
   Developer ID notarized. After verifying the checksum, use Finder's Open
   command or macOS Privacy & Security if macOS requests an explicit decision.

Do not remove quarantine metadata or disable Gatekeeper. To uninstall, quit the
app and delete `Retro Web UI GUI.app` and the downloaded archive.

## Windows x86_64

1. In PowerShell, run
   `Get-FileHash retro-web-ui-gui-*-windows-x86_64.zip -Algorithm SHA256`.
2. Use Explorer's **Extract All** and keep the entire `Retro Web UI GUI` folder
   together.
3. Run `Retro Web UI GUI\retro-web-ui-gui.exe`.

This portable build is not Authenticode-signed. Do not disable SmartScreen or
Defender; proceed only after the checksum matches the release manifest and the
OS information is understood. To uninstall, quit the app and delete the whole
extracted folder and downloaded ZIP. No installer, service, updater, Start menu
entry, or registry configuration is created by this archive.

## Linux x86_64

1. Verify with `sha256sum retro-web-ui-gui-*-linux-x86_64.tar.gz`.
2. Extract with `tar -xzf retro-web-ui-gui-*-linux-x86_64.tar.gz`.
3. Run `./retro-web-ui-gui/retro-web-ui-gui` from a normal desktop session.

The portable build requires glibc 2.35 or newer, a compatible libstdc++, and
the normal X11 or Wayland desktop libraries used by Qt, including EGL support.
To uninstall, quit the app and delete the extracted directory and downloaded
archive. It does not install a desktop entry, service, or updater.

## Codex prerequisite and recovery

Install the current Codex release using OpenAI's official instructions, sign in
with ChatGPT, and confirm both commands work in a terminal:

```text
codex --version
codex app-server --help
```

The GUI checks Codex automatically at launch. If Codex is missing or signed
out, local project analysis remains available; install/sign in to Codex and use
**Reconnect**. Authentication remains owned by Codex and is not copied into the
application archive or logs. Desktop launches do not always inherit a terminal
`PATH`, so the GUI also checks bounded common Codex application/npm locations.
It rejects relative, current-directory, and selected-project launchers rather
than executing a repository-local `codex` file.

The bundled Skill is supplied to the GUI's Codex session. It is not installed
globally into Codex. To use `$retro-web-ui` outside the GUI, install the Skill
separately from the matching tagged repository directory.
