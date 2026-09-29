"""Desktop companion — the committed page build (static checks).

The page LocalFlow shows is built from ``frontend/`` and committed into
``localflow/v2/ui/companion/web/`` so the app runs without Node. These
checks keep that build honest:

- it matches its sources (``BUILD.json`` records a hash of every file the
  bundle is made from; this recomputes it the same way);
- it loads nothing from outside the bundle (relative assets only, no
  inline script, no remote URL in the document);
- the browser-preview fixtures never reach it;
- the bundled third-party notices travel with it;
- the native scheme handler serves only files inside the build folder.

Run: .venv/bin/python tests/v2/ui/test_companion_build.py
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve()
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT))

FRONTEND = ROOT / "frontend"
WEB = ROOT / "localflow" / "v2" / "ui" / "companion" / "web"
SOURCE_FILES = ("index.html", "package.json", "package-lock.json",
                "svelte.config.js", "tsconfig.json", "vite.config.ts")


def source_hash() -> str:
    files = [FRONTEND / f for f in SOURCE_FILES] + [
        p for p in (FRONTEND / "src").rglob("*") if p.is_file()]
    rels = sorted(p.relative_to(FRONTEND).as_posix() for p in files)
    h = hashlib.sha256()
    for rel in rels:
        h.update(rel.encode())
        h.update(b"\0")
        h.update((FRONTEND / rel).read_bytes())
        h.update(b"\0")
    return h.hexdigest()


def test_build_matches_sources():
    record = json.loads((WEB / "BUILD.json").read_text())
    got = source_hash()
    assert record["source_sha256"] == got, (
        "the committed build is stale: run `npm run build` in frontend/"
        f" (recorded {record['source_sha256'][:12]}, sources {got[:12]})")
    print("ok  committed build matches frontend/ sources")


def test_document_loads_only_its_own_assets():
    html = (WEB / "index.html").read_text()
    scripts = re.findall(r"<script\b([^>]*)>(.*?)</script>", html, re.S)
    assert scripts, "no script"
    for attrs, body in scripts:
        assert body.strip() == "", "inline script in the document"
        src = re.search(r'src="([^"]+)"', attrs).group(1)
        assert src.startswith("./assets/") and src.endswith(".js"), src
    for href in re.findall(r'href="([^"]+)"', html):
        assert href.startswith("./assets/"), href
    assert not re.search(r"https?://", html), "remote URL in the document"
    for css in WEB.glob("assets/*.css"):
        text = css.read_text()
        assert not re.search(r"url\(\s*['\"]?https?:", text), css.name
        assert "@import" not in text, css.name
    print("ok  the document loads only its own bundled assets")


def test_preview_fixtures_never_ship():
    for js in WEB.glob("assets/*.js"):
        text = js.read_text()
        for marker in ("connectPreview", "synthetic.json", "__preview__"):
            assert marker not in text, f"{marker} in {js.name}"
    print("ok  browser-preview fixtures are not in the production bundle")


def test_notices_travel_with_the_bundle():
    text = (WEB / "THIRD_PARTY_NOTICES.txt").read_text()
    for name in ("svelte", "@lucide/svelte", "esm-env", "clsx"):
        assert text.count(f"{name} ") >= 1, name
    assert "ISC" in text and "MIT" in text
    print("ok  third-party notices ship beside the bundle")


def test_scheme_handler_serves_only_the_build():
    from localflow.v2.ui.companion import host
    assert host.resolve_asset("/index.html") == (WEB / "index.html").resolve()
    for bad in ("/../host.py", "/assets/../../host.py", "/.git/config",
                "/assets/.hidden", "//etc/passwd", "/assets", "/nope.js"):
        assert host.resolve_asset(bad) is None, bad
    js = next(WEB.glob("assets/*.js"))
    assert host.content_type(js) == "text/javascript"
    assert "connect-src 'none'" in host.CSP and \
        "default-src 'self'" in host.CSP and "unsafe" not in host.CSP
    print("ok  the scheme handler serves the build folder only, under a"
          " strict CSP")


if __name__ == "__main__":
    for test in (test_build_matches_sources,
                 test_document_loads_only_its_own_assets,
                 test_preview_fixtures_never_ship,
                 test_notices_travel_with_the_bundle,
                 test_scheme_handler_serves_only_the_build):
        test()
