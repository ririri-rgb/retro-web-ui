# Retro Web UI

[English](README.md) | [日本語](README.ja.md) | 简体中文

这是一个桌面 GUI、CLI 与 Codex Skill，可在保留现有 Web 应用功能的同时，将其界面转换为 Windows 98、Windows XP、Windows 7 或 2000 年代日本 Windows 免费软件风格。它不只是替换配色，还会根据界面含义进行结构转换，例如将 card 改为 group box、toggle 改为 checkbox、settings sidebar 改为 property sheet。

## 桌面 GUI

本项目提供一个 Windows XP 风格的 PySide6 桌面 GUI，作为安全的 orchestration 层。
用户可以选择 repository/application 与四种主题，检查 Core/CLI 的分析和 behavior baseline，然后使用本人现有的 ChatGPT 登录启动 Codex App Server session。
GUI 可显示 agent event、command/file/permission approval、interrupt/reconnect、verification、Git diff 以及 Before/After 证据。它不会要求或保存 OpenAI API key，也不会在 GUI 中重复实现 semantic conversion engine。

v2.1.0 新增了本地 Project/Session workspace。它不复制 source，而是登记 canonical project path；同时保存每次转换的独立 lifecycle、带 hash 的 baseline/Core/Git evidence、重启后的中断状态和 session 比较结果。恢复的 Codex thread 只用于 review，不会自动继续 turn，也不会回滚 source。missing/changed artifact 会被明确显示，historical evidence 也不会被标记为当前 working tree。该 workspace 已包含在 v2.1.4 native archive 中。

![Retro Web UI desktop GUI](screenshots/gui/desktop-xp.png)

可从 [v2.1.4 release](https://github.com/ririri-rgb/retro-web-ui/releases/tag/v2.1.4) 下载适用于 macOS arm64、Windows x86_64 和 Linux x86_64 的 native archive。归档中包含 Python 和 Qt，但不包含 Codex。macOS 版本带有已验证的 ad-hoc 签名，但未经 notarization；Windows 版本未签名。v2.1.4 Linux 版本在 Ubuntu 22.04 上构建，并通过 GLIBC 2.35 兼容性门禁；运行时还需要常规桌面显示环境。启动前请验证 SHA-256。

从 checkout 启动：

```bash
python3 -m venv .venv-gui
.venv-gui/bin/python -m pip install '.[gui]'
.venv-gui/bin/retro-web-ui-gui
```

Windows 请使用 `.venv-gui\Scripts\retro-web-ui-gui.exe`。Codex 必须已安装，并已通过 ChatGPT 登录。GUI 不会要求 API key，而是通过本地 stdio 使用 `codex app-server`。已发布的 `v1.1.0` 是 GUI 出现之前保持不变的 CLI + Skill baseline。详情请参阅 [Desktop GUI architecture](docs/gui-architecture.md)、[GUI engineering report](docs/gui-validation-report.md)、[Phase C workspace validation report](docs/gui-workspace-validation-report.md)，以及包含各操作系统解压、签名边界、Codex 诊断和卸载步骤的 [Desktop distribution guide](docs/distribution.md)。

转换前界面与四种主题的实际渲染结果可在[英文 README](README.md)开头查看。五张截图使用完全相同的 HTML 和 JavaScript。此外，项目还在 pinned TodoMVC、React/Vite、React/MUI/Emotion、Vue/Bootstrap、SvelteKit、Next App Router/Radix/Tailwind，以及 pinned `naive-ui-admin` 的 login surface 上，对 semantic 转换进行了边界明确的验证。

当前 main 会在真实浏览器中验证 client rendering、static prerender 后的 hydration、request-time SSR 后的 hydration、controlled form、library modal/dialog、body portal、Escape、focus return、routing、live region，以及 desktop/narrow screenshot。这并不代表支持各生态系统中的所有组件；已验证的 fixture/surface 边界记录在 [Compatibility evidence](docs/compatibility.md) 中。

## 安装

向 Codex 的 `$skill-installer` 提供 GitHub 上固定版本的 Skill directory：

```text
$skill-installer install https://github.com/ririri-rgb/retro-web-ui/tree/v2.1.4/skills/retro-web-ui
```

也可以 clone tagged release，并复制到 user scope：

```bash
git clone --branch v2.1.4 --depth 1 https://github.com/ririri-rgb/retro-web-ui.git
mkdir -p "$HOME/.agents/skills"
cp -R retro-web-ui/skills/retro-web-ui "$HOME/.agents/skills/"
```

如果只想在单个 repository 中使用，请复制到 `.agents/skills/retro-web-ui/`。Skill 本体与 CLI runtime 只需要 Python 3.9 或更高版本，不依赖第三方 runtime package。`v2.1.4` 是当前 desktop + CLI + Skill release，并继续保留 standalone Skill 结构和 `v1.0.0` legacy helper entry point。

从 checkout 将 CLI 安装到虚拟环境：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install .
.venv/bin/retro-web-ui info --json
```

CLI 提供 `analyze`、`doctor`、`behavior snapshot/compare`、`theme`、`audit` 和 `verify`。如果 monorepo 中存在多个候选项，它会要求明确指定 `--app`；它不会自动安装依赖、执行 target script 或进行 semantic conversion。含义转换、framework-specific 修复，以及 runtime/visual 判断仍由 Skill/Codex 负责。

```bash
python3 -m venv .venv
npm ci
npm run build:fixtures
npm audit --omit=dev --audit-level=moderate
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python tests/visual_smoke.py --check-only
.venv/bin/python tests/runtime_smoke.py --check-only
```

## 使用示例

```text
Use $retro-web-ui to convert this app to Windows XP style while preserving its behavior.
```

```text
使用 $retro-web-ui 将这个应用转换为 2000 年代日本 Windows 免费软件风格。不要改变 API、身份验证、路由、表单提交、validation 或保存格式。
```

Skill 会检查随附 CLI 的 manifest compatibility，分析目标 repository 和 app 候选项，并为 behavior signal 建立 hash baseline。Codex 根据 framework 使用 namespaced CSS 和 markup 完成符合含义的修改后，会依次执行 CLI structured verify、现有 build/test、interactive flow、visual 检查和 Git diff review。

## 重要限制

- 本项目不声称能够完全自动转换所有 Web 应用。涉及含义的结构转换需要 Codex 阅读目标代码后完成。
- CLI 本身不是 semantic converter；静态检查 clean 也不能证明 behavior 或 theme fidelity。
- closed Shadow DOM、仅使用 Canvas/WebGL 的 UI、cross-origin iframe，以及没有 source 的生成 bundle 无法安全转换。
- Next/Radix、MUI/Emotion、Bootstrap 和 Naive UI 的代表性案例已经验证，但 SSR hydration、portal、virtualized list、component library 和 CSS-in-JS 仍需针对目标应用进行 runtime 验证。
- 不包含 Microsoft 的 font、icon、bitmap、wallpaper、sound 等专有资源。
- v2.1.4 native archive 未进行 Developer ID notarization 或 Authenticode signing，也不提供自动更新。请验证 checksum，并使用操作系统明确的本地应用许可流程。
- GUI 不会推测或安装目标应用所需的 browser/runtime。Before/After 显示的是来自用户已授权现有 runtime 的 evidence。

已验证范围与未验证范围记录在 [Compatibility evidence](docs/compatibility.md)；v1 已执行验证记录在 [Validation report](docs/validation-report.md)；v1.0.0 review 结论依据记录在 [Final validation report](docs/final-validation-report.md)；v1.1.0 CLI + Skill 依据记录在 [CLI + Skill validation report](docs/cli-validation-report.md)；v2 GUI 记录在 [GUI engineering report](docs/gui-validation-report.md)；v2.0.1 distribution hardening 记录在 [Distribution validation report](docs/distribution-validation-report.md)。完整使用方法、troubleshooting 和 license 信息请参阅[英文 README](README.md)。
