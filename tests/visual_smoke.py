#!/usr/bin/env python3
"""Render the self-contained showcase with an installed Chromium browser."""

from __future__ import annotations

import argparse
import contextlib
import functools
import http.server
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]
SHOWCASE = ROOT / "skills" / "retro-web-ui" / "assets" / "showcase"
THEMES = ("modern", "windows-98", "windows-xp", "windows-7", "japanese-freeware-2000s")
NARROW_CASES = ("windows-7", "japanese-freeware-2000s")
BROWSERS = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "google-chrome",
    "chromium",
    "chromium-browser",
)
REACT_DIST = ROOT / "tests" / "fixtures" / "react-vite" / "dist"


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass


@contextlib.contextmanager
def running_server(directory: Path):
    handler = functools.partial(QuietHandler, directory=str(directory))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address[1]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def find_browser(explicit: Optional[str]) -> str:
    if explicit:
        return explicit
    for candidate in BROWSERS:
        if Path(candidate).is_file() or shutil.which(candidate):
            return candidate
    raise SystemExit("No Chrome/Chromium executable found; pass --browser")


def run_browser(argv: list[str], *, timeout: int = 30, attempts: int = 2) -> subprocess.CompletedProcess[str]:
    """Run a bounded browser command, retrying only a transient startup timeout."""
    for attempt in range(1, attempts + 1):
        try:
            return subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            if attempt == attempts:
                raise
            print(f"browser command timed out after {timeout}s; retrying ({attempt + 1}/{attempts})")
    raise AssertionError("browser retry loop exhausted without returning or raising")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--browser")
    parser.add_argument("--output", type=Path, default=ROOT / "screenshots")
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    browser = find_browser(args.browser)
    common = [browser, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run", "--no-default-browser-check"]
    desktop = common + ["--window-size=1180,760"]
    with running_server(SHOWCASE.parent) as port:
        base = f"http://127.0.0.1:{port}/showcase/index.html"
        smoke = run_browser(desktop + ["--dump-dom", f"{base}?theme=windows-98&selftest=1"])
        if smoke.returncode != 0 or 'data-selftest="passed"' not in smoke.stdout:
            print(smoke.stderr[-2000:])
            print("showcase interaction smoke test failed")
            return 1
        print("showcase interaction smoke test passed")
        if not (REACT_DIST / "index.html").is_file():
            print("React production fixture is missing; run npm run build:fixtures first")
            return 1
        with running_server(REACT_DIST) as react_port:
            react = run_browser(
                desktop
                + ["--virtual-time-budget=2000", "--dump-dom", f"http://127.0.0.1:{react_port}/?selftest=1"],
            )
        if react.returncode != 0 or 'data-selftest="passed"' not in react.stdout or "稼働中" not in react.stdout:
            print(react.stderr[-2000:])
            print("React production fixture interaction smoke test failed")
            return 1
        print("React production fixture interaction smoke test passed")
        if args.check_only:
            return 0
        args.output.mkdir(parents=True, exist_ok=True)
        for theme in THEMES:
            output = (args.output / f"showcase-{theme}.png").resolve()
            result = run_browser(desktop + [f"--screenshot={output}", f"{base}?theme={theme}"])
            if result.returncode != 0 or not output.exists():
                print(result.stderr[-2000:])
                print(f"screenshot failed: {theme}")
                return 1
            print(f"rendered {theme}: {output}")
        for theme in NARROW_CASES:
            output = (args.output / f"showcase-{theme}-narrow.png").resolve()
            result = run_browser(common + ["--window-size=640,900", f"--screenshot={output}", f"{base}?theme={theme}"])
            if result.returncode != 0 or not output.exists():
                print(result.stderr[-2000:])
                print(f"narrow screenshot failed: {theme}")
                return 1
            print(f"rendered {theme} narrow: {output}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
