# Retro Web UI

[English](README.md)

既存Webアプリの機能を維持しながら、UIを Windows 98 / Windows XP / Windows 7 / 2000年代の日本製Windowsフリーソフト風へ変換するデスクトップGUI + CLI + Codex Skillです。単なる配色変更ではなく、card→group box、toggle→checkbox、settings sidebar→property sheet等を意味に応じて再構成します。

## デスクトップGUI

Windows XP風のPySide6デスクトップGUIを安全なorchestration層として提供します。
repository/applicationと4テーマを選択し、Core/CLIによる解析とbehavior baselineを確認したうえで、
ユーザー本人のChatGPT sign-inを再利用するCodex App Server sessionを開始できます。
GUI内でagent event、command/file/permission approval、interrupt/reconnect、verification、Git diff、
Before/Afterを確認できます。OpenAI API keyの入力・保存は行わず、semantic conversion engineをGUIへ再実装していません。

v2.1.0では、localなProject/Session workspaceを追加しました。sourceをcopyせずcanonical
project pathを登録し、変換ごとのlifecycle、hash付きbaseline/Core/Git evidence、再起動後の中断状態、
session比較を保持します。復元したCodex threadはreview用に読み込むだけで、turnの自動再開やsource rollbackでは
ありません。missing/changed artifactは明示し、historical evidenceを現在のworking treeとして表示しません。
このworkspaceはv2.1.4 native archiveに含まれます。

![Retro Web UI desktop GUI](screenshots/gui/desktop-xp.png)

[v2.1.4 release](https://github.com/ririri-rgb/retro-web-ui/releases/tag/v2.1.4)から
macOS arm64 / Windows x86_64 / Linux x86_64用native archiveを取得できます。PythonとQtは同梱しますが、Codexは同梱しません。
macOS版は検証済みad-hoc署名ですがnotarizeされておらず、Windows版はunsignedです。v2.1.4 Linux版はUbuntu 22.04でbuildし、GLIBC 2.35以下をgateとします。通常のdesktop display stackも必要です。起動前にSHA-256を確認してください。

checkoutから起動する場合:

```bash
python3 -m venv .venv-gui
.venv-gui/bin/python -m pip install '.[gui]'
.venv-gui/bin/retro-web-ui-gui
```

Windowsでは`.venv-gui\Scripts\retro-web-ui-gui.exe`を使います。Codexが既にinstallされ、
ChatGPTでsign in済みである必要があります。GUIはAPI keyを要求せず、local stdioの`codex app-server`を使います。
公開済み`v1.1.0`はimmutableなGUI以前のCLI + Skill baselineです。詳細は
[Desktop GUI architecture](docs/gui-architecture.md)、[GUI engineering report](docs/gui-validation-report.md)、
[Phase C workspace validation report](docs/gui-workspace-validation-report.md)、OS別の展開・署名境界・Codex診断・uninstallをまとめた[Desktop distribution guide](docs/distribution.md)を参照してください。

変換前と4テーマの実描画結果は[英語README](README.md)冒頭で比較できます。5枚は同一HTML・同一JavaScriptを使っています。さらに、pinned TodoMVC、React/Vite、React/MUI/Emotion、Vue/Bootstrap、SvelteKit、Next App Router/Radix/Tailwind、およびpinned `naive-ui-admin`のlogin surfaceで、範囲を区別しながらsemantic変換を検証しています。

現在のmainでは、client rendering、static prerender後のhydration、request-time SSR後のhydration、controlled form、library modal/dialog、body portal、Escape、focus return、routing、live region、desktop/narrow screenshotまで実ブラウザで確認します。これは各ecosystem全体への対応保証ではなく、実証したfixture/surfaceの境界を[Compatibility evidence](docs/compatibility.md)へ明記しています。

## インストール

Codexの`$skill-installer`へ、versionを固定したGitHub上のSkill directoryを指定します。

```text
$skill-installer install https://github.com/ririri-rgb/retro-web-ui/tree/v2.1.4/skills/retro-web-ui
```

またはtagged releaseをcloneして、user scopeへコピーします。

```bash
git clone --branch v2.1.4 --depth 1 https://github.com/ririri-rgb/retro-web-ui.git
mkdir -p "$HOME/.agents/skills"
cp -R retro-web-ui/skills/retro-web-ui "$HOME/.agents/skills/"
```

リポジトリ限定で使う場合は `.agents/skills/retro-web-ui/` へコピーします。Skill本体とCLI runtimeはPython 3.9以上だけで動作し、第三者runtime packageは不要です。`v2.1.4`は現在のdesktop + CLI + Skill releaseで、standalone Skill構成と`v1.0.0`のlegacy helper entry pointを維持しています。

CLIをcheckoutから仮想環境へ導入する場合:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install .
.venv/bin/retro-web-ui info --json
```

CLIは`analyze`、`doctor`、`behavior snapshot/compare`、`theme`、`audit`、`verify`を提供します。monorepoで候補が複数なら`--app`を要求し、依存導入・target script実行・semantic conversionは自動実行しません。意味変換、framework固有修復、runtime/visual判断はSkill/Codex側に残します。

```bash
python3 -m venv .venv
npm ci
npm run build:fixtures
npm audit --omit=dev --audit-level=moderate
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python tests/visual_smoke.py --check-only
.venv/bin/python tests/runtime_smoke.py --check-only
```

## 利用例

```text
Use $retro-web-ui to convert this app to Windows XP style while preserving its behavior.
```

```text
このアプリを2000年代の日本製Windowsフリーソフト風にして。API、認証、ルーティング、フォーム送信、validation、保存形式は変えないで。
```

Skillは同梱CLIのmanifest整合を確認し、対象repositoryとapp候補を解析し、behavior signalのhash baselineを取ります。Codexがframeworkに合わせてnamespaced CSSとmarkupを意味に沿って変更した後、CLIのstructured verify、既存build/test、interactive flow、visual、git diffを順に検証します。

## 重要な制限

- 全Webアプリの完全自動変換を主張しません。意味を伴う構造変換はCodexが対象コードを読んで行います。
- CLI単体はsemantic converterではなく、静的にcleanでもbehaviorやtheme fidelityの証明にはなりません。
- closed Shadow DOM、Canvas/WebGLのみのUI、cross-origin iframe、sourceのない生成bundleは安全な変換対象外です。
- Next/Radix、MUI/Emotion、Bootstrap、Naive UIの代表ケースは検証済みですが、SSR hydration、portal、virtualized list、component library、CSS-in-JSは対象アプリごとのruntime検証が必要です。
- Microsoftのfont、icon、bitmap、wallpaper、sound等は同梱していません。
- v2.1.4 native archiveはDeveloper ID notarization / Authenticode signingを行っておらず、自動更新もありません。checksumを確認し、OSの明示的なlocal-app許可手順を使ってください。
- GUIはtarget appのbrowser/runtimeを推測installしません。Before/Afterはユーザーが許可した既存runtimeから得たevidenceを表示します。

実証範囲・未検証範囲は[Compatibility evidence](docs/compatibility.md)、v1実行済み検証は[Validation report](docs/validation-report.md)、v1.0.0 review判断の根拠は[Final validation report](docs/final-validation-report.md)、v1.1.0 CLI + Skillの根拠は[CLI + Skill validation report](docs/cli-validation-report.md)、v2 GUIは[GUI engineering report](docs/gui-validation-report.md)、v2.0.1配布hardeningは[Distribution validation report](docs/distribution-validation-report.md)に分けて記録しています。完全な使用方法、troubleshooting、licenseは[英語README](README.md)を参照してください。
