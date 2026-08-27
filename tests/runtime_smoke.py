#!/usr/bin/env python3
"""Exercise converted Vue, SvelteKit, and Next fixtures in a real browser."""

from __future__ import annotations

import argparse
import contextlib
import functools
import html
import http.server
import os
import re
import shutil
import signal
import socket
import subprocess
import time
import urllib.request
from pathlib import Path
from typing import Iterator, Optional

ROOT = Path(__file__).resolve().parents[1]
VUE_DIST = ROOT / "tests" / "fixtures" / "vue-vite" / "dist"
MUI_DIST = ROOT / "tests" / "fixtures" / "react-mui" / "dist"
SVELTE_BUILD = ROOT / "tests" / "fixtures" / "svelte-kit" / "build"
NEXT_ROOT = ROOT / "tests" / "fixtures" / "next-tailwind"
BROWSERS = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "google-chrome",
    "chromium",
    "chromium-browser",
)


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass


@contextlib.contextmanager
def static_server(directory: Path) -> Iterator[str]:
    handler = functools.partial(QuietHandler, directory=str(directory))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = __import__("threading").Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@contextlib.contextmanager
def next_server() -> Iterator[str]:
    port = free_port()
    command = ["npm", "run", "start", "--workspace", "next-fixture", "--", "--hostname", "127.0.0.1", "--port", str(port)]
    process = subprocess.Popen(
        command,
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
    )
    base = f"http://127.0.0.1:{port}"
    try:
        deadline = time.monotonic() + 30
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            if process.poll() is not None:
                output = process.stdout.read() if process.stdout else ""
                raise RuntimeError(f"Next server exited early ({process.returncode}):\n{output[-3000:]}")
            try:
                with urllib.request.urlopen(base, timeout=1) as response:
                    if response.status == 200:
                        break
            except Exception as error:  # server readiness probe
                last_error = error
                time.sleep(0.1)
        else:
            raise RuntimeError(f"Next server did not become ready: {last_error}")
        yield base
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=5)


def find_browser(explicit: Optional[str]) -> str:
    if explicit:
        return explicit
    for candidate in BROWSERS:
        if Path(candidate).is_file() or shutil.which(candidate):
            return candidate
    raise SystemExit("No Chrome/Chromium executable found; pass --browser")


def browser_dom(browser: str, url: str) -> tuple[str, str]:
    command = [
        browser,
        "--headless=new",
        "--disable-gpu",
        "--hide-scrollbars",
        "--no-first-run",
        "--no-default-browser-check",
        "--enable-logging=stderr",
        "--v=0",
        "--virtual-time-budget=4000",
        "--dump-dom",
        url,
    ]
    result = subprocess.run(command, capture_output=True, text=True, timeout=40)
    if result.returncode != 0:
        raise RuntimeError(result.stderr[-3000:])
    return result.stdout, result.stderr


def assert_runtime(browser: str, name: str, url: str, expected_text: str) -> None:
    dom, stderr = browser_dom(browser, f"{url}/?selftest=1")
    if 'data-selftest="passed"' not in dom or expected_text not in dom:
        detail_match = re.search(r'data-selftest-details="([^"]*)"', dom)
        details = html.unescape(detail_match.group(1)) if detail_match else "not provided"
        raise RuntimeError(f"{name} runtime smoke failed; details={details}\n{stderr[-1500:]}\n{dom[-3000:]}")
    console_lines = [line for line in stderr.splitlines() if ":CONSOLE:" in line]
    if console_lines:
        raise RuntimeError(f"{name} emitted browser console output:\n" + "\n".join(console_lines[-20:]))
    if "hydration failed" in stderr.lower() or "hydration mismatch" in stderr.lower():
        raise RuntimeError(f"{name} emitted a hydration error: {stderr[-3000:]}")
    print(f"{name} runtime interaction smoke passed")


def assert_external_interaction(browser: str, name: str, url: str, scenario: str) -> None:
    command = [
        "node",
        str(ROOT / "tests" / "cdp_probe.mjs"),
        "--browser",
        browser,
        "--url",
        url,
        "--scenario",
        scenario,
    ]
    result = subprocess.run(command, capture_output=True, text=True, timeout=40)
    if result.returncode != 0:
        raise RuntimeError(f"{name} external browser interaction failed:\n{result.stdout}\n{result.stderr[-3000:]}")
    print(result.stdout.strip())


def screenshot(browser: str, url: str, output: Path, *, width: int = 1180, height: int = 760) -> None:
    command = [
        browser,
        "--headless=new",
        "--disable-gpu",
        "--hide-scrollbars",
        "--no-first-run",
        "--no-default-browser-check",
        "--virtual-time-budget=2500",
        f"--window-size={width},{height}",
        f"--screenshot={output.resolve()}",
        url,
    ]
    result = subprocess.run(command, capture_output=True, text=True, timeout=40)
    if result.returncode != 0 or not output.is_file():
        raise RuntimeError(f"screenshot failed: {output}\n{result.stderr[-3000:]}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--browser")
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--output", type=Path, default=ROOT / "screenshots")
    args = parser.parse_args()
    browser = find_browser(args.browser)

    for directory in (MUI_DIST, VUE_DIST, SVELTE_BUILD):
        if not (directory / "index.html").is_file():
            raise SystemExit(f"missing production build: {directory}; run npm run build:fixtures")

    with static_server(MUI_DIST) as base:
        assert_runtime(browser, "React/MUI/Emotion", base, "社内LANを保存しました")
        assert_external_interaction(browser, "React/MUI/Emotion", base, "mui")
        if not args.check_only:
            args.output.mkdir(parents=True, exist_ok=True)
            screenshot(browser, base, args.output / "react-mui-windows-98.png")
            screenshot(browser, f"{base}/?dialog=1", args.output / "react-mui-windows-98-dialog.png")

    with static_server(VUE_DIST) as base:
        assert_runtime(browser, "Vue/Bootstrap", base, "接続プロファイルを保存しました")
        assert_external_interaction(browser, "Vue/Bootstrap", base, "vue")
        if not args.check_only:
            screenshot(browser, base, args.output / "vue-windows-xp.png")

    with static_server(SVELTE_BUILD) as base:
        assert_runtime(browser, "SvelteKit hydration", base, "D:\\Archiveへ自動保存します")
        assert_external_interaction(browser, "SvelteKit hydration", base, "svelte")
        if not args.check_only:
            screenshot(browser, base, args.output / "svelte-japanese-freeware-2000s.png")

    with next_server() as base:
        with urllib.request.urlopen(base, timeout=5) as response:
            server_html = response.read().decode("utf-8")
        if 'data-retro-theme="windows-7"' not in server_html or "システム設定" not in server_html:
            raise RuntimeError("Next initial server HTML is missing the stable theme root or server-rendered content")
        print("Next SSR initial HTML check passed")
        assert_runtime(browser, "Next/Radix hydration", base, "管理者プロファイルを保存しました")
        assert_external_interaction(browser, "Next/Radix hydration", base, "next")
        if not args.check_only:
            screenshot(browser, base, args.output / "next-windows-7.png")
            screenshot(browser, f"{base}/?dialog=1", args.output / "next-windows-7-dialog.png")
            screenshot(browser, base, args.output / "next-windows-7-narrow.png", width=520, height=820)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
