# Retro Web UI

[English](README.md)

既存Webアプリの機能を維持しながら、UIを Windows 98 / Windows XP / Windows 7 / 2000年代の日本製Windowsフリーソフト風へ変換するCodex Skillです。単なる配色変更ではなく、card→group box、toggle→checkbox、settings sidebar→property sheet等を意味に応じて再構成します。

変換前と4テーマの実描画結果は[英語README](README.md)冒頭で比較できます。5枚は同一HTML・同一JavaScriptを使っています。さらに、pinned TodoMVC、React/Vite、React/MUI/Emotion、Vue/Bootstrap、SvelteKit、Next App Router/Radix/Tailwind、およびpinned `naive-ui-admin`のlogin surfaceで、範囲を区別しながらsemantic変換を検証しています。

現在のmainでは、client rendering、static prerender後のhydration、request-time SSR後のhydration、controlled form、library modal/dialog、body portal、Escape、focus return、routing、live region、desktop/narrow screenshotまで実ブラウザで確認します。これは各ecosystem全体への対応保証ではなく、実証したfixture/surfaceの境界を[Compatibility evidence](docs/compatibility.md)へ明記しています。

## インストール

Codexの`$skill-installer`へ、versionを固定したGitHub上のSkill directoryを指定します。

```text
$skill-installer install https://github.com/ririri-rgb/retro-web-ui/tree/v0.1.0/skills/retro-web-ui
```

またはtagged releaseをcloneして、user scopeへコピーします。

```bash
git clone --branch v0.1.0 --depth 1 https://github.com/ririri-rgb/retro-web-ui.git
mkdir -p "$HOME/.agents/skills"
cp -R retro-web-ui/skills/retro-web-ui "$HOME/.agents/skills/"
```

リポジトリ限定で使う場合は `.agents/skills/retro-web-ui/` へコピーします。Skill本体とhelperはPython 3.9以上だけで動作し、第三者Python packageは不要です。repositoryの検証は `python3 -m venv .venv` で作成した仮想環境から実行します。framework regression harnessは、dependency-free external browser driverのためNode.js 22以上も使用します。`v0.1.0`はstandalone Skillとして公開し、universal Plugins Directory向けpackage化は今回のrelease stabilization scopeには含めません。

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

Skillは対象repositoryを検出し、behavior signalのhash baselineを取り、frameworkに合わせてnamespaced CSSを導入し、必要なmarkupだけを意味に沿って変更します。その後、既存build/test、behavior比較、interactive flow、visual、git diffを順に検証します。

## 重要な制限

- 全Webアプリの完全自動変換を主張しません。意味を伴う構造変換はCodexが対象コードを読んで行います。
- closed Shadow DOM、Canvas/WebGLのみのUI、cross-origin iframe、sourceのない生成bundleは安全な変換対象外です。
- Next/Radix、MUI/Emotion、Bootstrap、Naive UIの代表ケースは検証済みですが、SSR hydration、portal、virtualized list、component library、CSS-in-JSは対象アプリごとのruntime検証が必要です。
- Microsoftのfont、icon、bitmap、wallpaper、sound等は同梱していません。

実証範囲・未検証範囲は[Compatibility evidence](docs/compatibility.md)、実行済み検証は[Validation report](docs/validation-report.md)、v1 review判断の根拠は[Final validation report](docs/final-validation-report.md)に分けて記録しています。完全な使用方法、troubleshooting、licenseは[英語README](README.md)を参照してください。
