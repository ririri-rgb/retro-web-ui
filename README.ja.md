# Retro Web UI

[English](README.md)

既存Webアプリの機能を維持しながら、UIを Windows 98 / Windows XP / Windows 7 / 2000年代の日本製Windowsフリーソフト風へ変換するCLI + Codex Skillです。単なる配色変更ではなく、card→group box、toggle→checkbox、settings sidebar→property sheet等を意味に応じて再構成します。

変換前と4テーマの実描画結果は[英語README](README.md)冒頭で比較できます。5枚は同一HTML・同一JavaScriptを使っています。さらに、pinned TodoMVC、React/Vite、React/MUI/Emotion、Vue/Bootstrap、SvelteKit、Next App Router/Radix/Tailwind、およびpinned `naive-ui-admin`のlogin surfaceで、範囲を区別しながらsemantic変換を検証しています。

現在のmainでは、client rendering、static prerender後のhydration、request-time SSR後のhydration、controlled form、library modal/dialog、body portal、Escape、focus return、routing、live region、desktop/narrow screenshotまで実ブラウザで確認します。これは各ecosystem全体への対応保証ではなく、実証したfixture/surfaceの境界を[Compatibility evidence](docs/compatibility.md)へ明記しています。

## インストール

Codexの`$skill-installer`へ、versionを固定したGitHub上のSkill directoryを指定します。

```text
$skill-installer install https://github.com/ririri-rgb/retro-web-ui/tree/v1.1.0/skills/retro-web-ui
```

またはtagged releaseをcloneして、user scopeへコピーします。

```bash
git clone --branch v1.1.0 --depth 1 https://github.com/ririri-rgb/retro-web-ui.git
mkdir -p "$HOME/.agents/skills"
cp -R retro-web-ui/skills/retro-web-ui "$HOME/.agents/skills/"
```

リポジトリ限定で使う場合は `.agents/skills/retro-web-ui/` へコピーします。Skill本体とCLI runtimeはPython 3.9以上だけで動作し、第三者runtime packageは不要です。`v1.1.0`が現在の安定版CLI + Skillで、standalone Skill構成と`v1.0.0`のlegacy helper entry pointを維持しています。

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

実証範囲・未検証範囲は[Compatibility evidence](docs/compatibility.md)、v1実行済み検証は[Validation report](docs/validation-report.md)、v1.0.0 review判断の根拠は[Final validation report](docs/final-validation-report.md)、v1.1.0 CLI + Skillの根拠は[CLI + Skill validation report](docs/cli-validation-report.md)に分けて記録しています。完全な使用方法、troubleshooting、licenseは[英語README](README.md)を参照してください。
