#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Build the single-file app from src/viewer.template.html.

The page's Content-Security-Policy allows only the exact inline <script> and
<style> blocks it ships with, pinned by SHA-256 hash. This script computes
those hashes and writes the final file.

Usage:
    python3 scripts/build.py           # write coder-agreement-viewer.html
    python3 scripts/build.py --check   # fail if the committed file is stale
"""
import base64
import hashlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "viewer.template.html"
OUT = ROOT / "coder-agreement-viewer.html"


def csp_hash(body: str) -> str:
    digest = hashlib.sha256(body.encode("utf-8")).digest()
    return "'sha256-" + base64.b64encode(digest).decode() + "'"


def build() -> str:
    src = SRC.read_text(encoding="utf-8")
    scripts = re.findall(r"<script>(.*?)</script>", src, re.S)
    styles = re.findall(r"<style>(.*?)</style>", src, re.S)
    if len(scripts) != 1 or len(styles) != 1:
        sys.exit("expected exactly one inline <script> and one <style> in the template")
    csp = "; ".join([
        "default-src 'none'",
        "script-src " + csp_hash(scripts[0]),
        "style-src " + csp_hash(styles[0]),
        "img-src 'none'",
        "font-src 'none'",
        "connect-src 'none'",
        "media-src 'none'",
        "object-src 'none'",
        "frame-src 'none'",
        "worker-src 'none'",
        "manifest-src 'none'",
        "base-uri 'none'",
        "form-action 'none'",
    ])
    if src.count("__CSP__") != 1:
        sys.exit("expected exactly one __CSP__ placeholder in the template")
    return src.replace("__CSP__", csp)


def main() -> None:
    html = build()
    if "--check" in sys.argv[1:]:
        current = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
        if current != html:
            sys.exit(f"{OUT.name} is out of date; run: python3 scripts/build.py")
        print(f"{OUT.name} is up to date")
        return
    OUT.write_text(html, encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)} ({len(html.encode('utf-8'))} bytes)")


if __name__ == "__main__":
    main()
