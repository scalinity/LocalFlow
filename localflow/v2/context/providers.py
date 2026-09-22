"""Context providers (V2 M06, Spec S12): what reads the destination.

All macOS access is isolated behind two injectable call sites —
``SystemAXHost`` (Accessibility reads; a short messaging timeout bounds
unresponsive apps) and the frontmost-app accessor (NSWorkspace). Tests
inject fakes that interpret synthetic AX trees
(``tests/v2/context/fixtures_context_targets.json``), so every filtering
rule is testable without a live destination.

Absolute sensitive-field rules (S12): secure fields and denied apps are
never read for content; an unclassifiable field gets plain dictation
without nearby text; browser origins drop query/fragment; placeholder
values are metadata, never text; no arbitrary filesystem read ever runs
(a document locator is a recorded string, not an open()).
"""

from __future__ import annotations

import re
import time
from typing import Optional
from urllib.parse import urlsplit

from .snapshot import (
    FIELD_NONE,
    FIELD_SECURE,
    FIELD_TEXT,
    FIELD_UNCLASSIFIABLE,
    OMISSION_DENIED,
    OMISSION_MESSAGING,
    OMISSION_NOT_EXPOSED,
    OMISSION_PERMISSION,
    OMISSION_SECURE,
    OMISSION_UNCLASSIFIABLE,
    FieldContext,
    classify_field,
)

# Bounded reads: the nearby-text window and the identifier budget.
NEARBY_CHARS = 600
IDENTIFIER_LIMIT = 64

CATEGORY_BROWSER = "browser"
CATEGORY_IDE = "ide"
CATEGORY_TERMINAL = "terminal"
CATEGORY_EDITOR = "editor"
CATEGORY_MESSAGING = "messaging"
CATEGORY_MAIL = "mail"
CATEGORY_UNKNOWN = "unknown"

BROWSER_BUNDLES = {
    "com.apple.Safari", "com.google.Chrome", "com.google.Chrome.canary",
    "com.google.Chrome.dev", "com.microsoft.edgemac", "com.brave.Browser",
    "company.thebrowser.Browser", "org.mozilla.firefox",
}
IDE_BUNDLES = {
    "com.microsoft.VSCode", "com.microsoft.VSCodeInsiders",
    "com.apple.dt.Xcode", "com.jetbrains.intellij",
    "com.jetbrains.pycharm", "com.jetbrains.datagrip",
    "com.todesktop.230313mzl4w4u92",   # Cursor
    "dev.zed.Zed", "com.sublimetext.4",
}
TERMINAL_BUNDLES = {
    "com.apple.Terminal", "com.googlecode.iterm2",
    "com.mitchellh.ghostty", "dev.warp.Warp-Stable",
    "com.todesktop.1935169459", "com.microsoft.VSCode",  # integrated terminal
}
EDITOR_BUNDLES = {"com.apple.TextEdit", "com.apple.Notes"}
MESSAGING_BUNDLES = {"com.apple.iChat", "com.tinyspeck.slackmacgap"}
MAIL_BUNDLES = {"com.apple.mail"}

# URL-ish token in a window title (fallback provenance only; domains are
# never invented from arbitrary text — this matches host[.tld] shapes).
_TITLE_DOMAIN_RE = re.compile(
    r"\b([a-z0-9-]+(?:\.[a-z0-9-]+)+)\b", re.IGNORECASE)

# File extensions that would otherwise pass the alphabetic-TLD rule —
# a filename in a title is never a site origin.
_NON_ORIGIN_TLDS = frozenset({
    "app", "aspx", "avi", "css", "csv", "dmg", "exe", "gif", "go",
    "gz", "htm", "html", "ini", "java", "jpeg", "jpg", "js", "json",
    "local", "lock", "md", "mov", "mp3", "mp4", "pdf", "php", "pkg",
    "png", "py", "rb", "rs", "so", "svg", "tar", "toml", "ts", "tsv",
    "txt", "webp", "xml", "yaml", "yml", "zip",
})


def categorize(bundle: Optional[str]) -> str:
    if bundle in BROWSER_BUNDLES:
        return CATEGORY_BROWSER
    if bundle in IDE_BUNDLES:
        return CATEGORY_IDE
    if bundle in TERMINAL_BUNDLES:
        return CATEGORY_TERMINAL
    if bundle in EDITOR_BUNDLES:
        return CATEGORY_EDITOR
    if bundle in MESSAGING_BUNDLES:
        return CATEGORY_MESSAGING
    if bundle in MAIL_BUNDLES:
        return CATEGORY_MAIL
    return CATEGORY_UNKNOWN


class SystemAXHost:
    """Accessibility reads with a per-call messaging timeout so an
    unresponsive application can never stall the dictation path. One
    systemwide element is created lazily and reused (guarded —
    overlapping collections may share the host)."""

    def __init__(self, messaging_timeout: float = 0.2):
        self.messaging_timeout = messaging_timeout
        self._system_el = None
        self._system_lock = __import__("threading").Lock()

    def is_trusted(self) -> bool:
        import ApplicationServices as AS
        return bool(AS.AXIsProcessTrusted())

    def _system(self):
        import ApplicationServices as AS
        with self._system_lock:
            if self._system_el is None:
                el = AS.AXUIElementCreateSystemWide()
                AS.AXUIElementSetMessagingTimeout(el, self.messaging_timeout)
                self._system_el = el
            return self._system_el

    def focused_element(self):
        import ApplicationServices as AS
        err, el = AS.AXUIElementCopyAttributeValue(
            self._system(), "AXFocusedUIElement", None)
        if err == 0 and el is not None:
            AS.AXUIElementSetMessagingTimeout(
                el, self.messaging_timeout)
            return el
        return None

    def attribute(self, el, name):
        import ApplicationServices as AS
        try:
            err, val = AS.AXUIElementCopyAttributeValue(el, name, None)
        except Exception:
            return None
        return val if err == 0 else None

    def focused_window(self, el) -> Optional[object]:
        return self.attribute(el, "AXFocusedWindow")

    def window_title(self, win) -> Optional[str]:
        t = self.attribute(win, "AXTitle")
        return str(t) if t else None

    def string_for_range(self, el, start: int, length: int) -> Optional[str]:
        import ApplicationServices as AS
        from CoreFoundation import CFRange
        try:
            err, val = AS.AXUIElementCopyParameterizedAttributeValue(
                el, "AXStringForRange", CFRange(start, length), None)
        except Exception:
            return None
        return str(val) if err == 0 and val is not None else None

    def number_of_characters(self, el) -> Optional[int]:
        n = self.attribute(el, "AXNumberOfCharacters")
        try:
            return int(n)
        except (TypeError, ValueError):
            return None


def system_frontmost() -> Optional[dict]:
    """Frontmost app via NSWorkspace — no Accessibility grant needed."""
    try:
        from AppKit import NSWorkspace
        app = NSWorkspace.sharedWorkspace().frontmostApplication()
        if app is None:
            return None
        return {"bundle": app.bundleIdentifier(),
                "name": app.localizedName(), "pid": app.processIdentifier()}
    except Exception:
        return None


class ProviderResult:
    """One provider's outcome: a value, an omission reason, provenance
    and the measured duration (for coverage/skip reporting)."""

    def __init__(self, name, value=None, reason=None, provenance=None,
                 duration_ms=None):
        self.name = name
        self.value = value
        self.reason = reason
        self.provenance = provenance
        self.duration_ms = duration_ms


def read_field(host, denied: bool) -> ProviderResult:
    """Focused-field provider: classify FIRST, then read bounded content
    only for classifiable text fields (S12 ordering is a hard rule)."""
    t0 = time.monotonic()
    name = "focused_field"
    if denied:
        return ProviderResult(name, reason=OMISSION_DENIED,
                              duration_ms=_ms(t0))
    if not host.is_trusted():
        return ProviderResult(name, reason=OMISSION_PERMISSION,
                              duration_ms=_ms(t0))
    el = host.focused_element()
    if el is None:
        # Either no focused element or the AX messaging failed — the
        # host cannot distinguish cheaply, so the honest generic reason.
        return ProviderResult(name, reason=OMISSION_MESSAGING,
                              duration_ms=_ms(t0))
    role = host.attribute(el, "AXRole")
    subrole = host.attribute(el, "AXSubrole")
    cls = classify_field(
        role if isinstance(role, str) else None,
        subrole if isinstance(subrole, str) else None)
    if cls == FIELD_SECURE:
        # Absolute rule: no content attribute of a secure field is ever
        # read — not its value, selection, placeholder or ranges.
        return ProviderResult(
            name, value=FieldContext(
                role=role if isinstance(role, str) else None,
                subrole=subrole if isinstance(subrole, str) else None,
                classification=FIELD_SECURE),
            reason=OMISSION_SECURE, duration_ms=_ms(t0))
    if cls != FIELD_TEXT:
        return ProviderResult(
            name, value=FieldContext(
                role=role if isinstance(role, str) else None,
                subrole=subrole if isinstance(subrole, str) else None,
                classification=cls),
            reason=(None if cls == FIELD_NONE
                    else OMISSION_UNCLASSIFIABLE),
            duration_ms=_ms(t0))
    # Classifiable text field: bounded reads only.
    placeholder = host.attribute(el, "AXPlaceholderValue")
    selected = host.attribute(el, "AXSelectedText")
    rng = host.attribute(el, "AXSelectedTextRange")
    doc = host.attribute(el, "AXDocument")
    total = host.number_of_characters(el)
    selected_text = str(selected) if isinstance(selected, str) else None
    loc, length = _as_range(rng)
    preceding = following = None
    if total is not None and loc is not None:
        p_start = max(0, loc - NEARBY_CHARS)
        preceding = host.string_for_range(el, p_start, loc - p_start)
        f_start = (loc + (length or 0))
        if f_start < total:
            following = host.string_for_range(
                el, f_start, min(NEARBY_CHARS, total - f_start))
    return ProviderResult(
        name,
        value=FieldContext(
            role=role if isinstance(role, str) else None,
            subrole=subrole if isinstance(subrole, str) else None,
            classification=FIELD_TEXT,
            selected_text=selected_text,
            selected_range=(loc, loc + (length or 0))
            if loc is not None else None,
            preceding_text=preceding, following_text=following,
            placeholder=str(placeholder)
            if isinstance(placeholder, str) else None,
            document_url=str(doc) if isinstance(doc, str) else None),
        duration_ms=_ms(t0))


def read_site_origin(host, category: str, window_title: Optional[str],
                     denied: bool = False) -> ProviderResult:
    """Browser-origin provider: AXURL where the browser exposes it,
    stripped to origin (query/fragment dropped by construction); a
    plausible domain token in the window title is the marked fallback.
    Never a guess from arbitrary text. A denied app is never read —
    not even probed (S12 absolute)."""
    t0 = time.monotonic()
    name = "site_origin"
    if denied:
        return ProviderResult(name, reason=OMISSION_DENIED,
                              duration_ms=_ms(t0))
    if category != CATEGORY_BROWSER:
        return ProviderResult(name, reason=OMISSION_NOT_EXPOSED,
                              duration_ms=_ms(t0))
    if not host.is_trusted():
        return ProviderResult(name, reason=OMISSION_PERMISSION,
                              duration_ms=_ms(t0))
    el = host.focused_element()
    url = None
    if el is not None:
        url = host.attribute(el, "AXURL")
    origin = _url_origin(url if isinstance(url, str) else None)
    if origin is not None:
        return ProviderResult(name, value=origin, provenance="ax_url",
                              duration_ms=_ms(t0))
    if window_title:
        m = _TITLE_DOMAIN_RE.search(window_title)
        if m and _plausible_host(m.group(1)):
            # Titles expose hostnames at best; the scheme is not
            # knowable from a title token, so the recorded fallback
            # origin is https-schemed with explicit provenance marking
            # it heuristic (consumers see origin_source).
            return ProviderResult(
                name, value=f"https://{m.group(1)}",
                provenance="window_title", duration_ms=_ms(t0))
    return ProviderResult(name, reason=OMISSION_NOT_EXPOSED,
                          duration_ms=_ms(t0))


def read_workspace(host, category: str, window_title: Optional[str],
                   document_url: Optional[str],
                   denied: bool = False) -> ProviderResult:
    """Opaque workspace identifier: the focused document's directory
    name where AX exposes a file locator (never an http URL), else the
    IDE title's project segment. A locator string is recorded; nothing
    on disk is ever opened. A denied app is never read."""
    t0 = time.monotonic()
    name = "workspace"
    if denied:
        return ProviderResult(name, reason=OMISSION_DENIED,
                              duration_ms=_ms(t0))
    if document_url and is_path_document(document_url):
        ws = _workspace_from_path(document_url)
        if ws:
            return ProviderResult(name, value=ws, provenance="document",
                                  duration_ms=_ms(t0))
    if category == CATEGORY_IDE and window_title:
        seg = _ide_title_project(window_title)
        if seg:
            return ProviderResult(name, value=seg,
                                  provenance="window_title",
                                  duration_ms=_ms(t0))
    return ProviderResult(name, reason=OMISSION_NOT_EXPOSED,
                          duration_ms=_ms(t0))


_IDENTIFIER_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_WORD_SPLIT_RE = re.compile(
    r"[A-Z]+(?![a-z])|[A-Z][a-z0-9]*|[a-z0-9]+|_")


def extract_identifiers(field: Optional[FieldContext],
                        limit: int = IDENTIFIER_LIMIT) -> dict[str, str]:
    """Spoken form → canonical identifier map, derived only from the
    bounded nearby window of a classifiable text field (S12 "visible
    file/symbol names"; a full symbol provider would need an IDE
    extension — not shipped here)."""
    if field is None or field.classification != FIELD_TEXT:
        return {}
    text = field.nearby_text() or ""
    out: dict[str, str] = {}
    for tok in _IDENTIFIER_RE.findall(text):
        if not ("_" in tok[1:] or _has_case_transition(tok)):
            continue          # plain words are not identifiers
        spoken = _spoken_form(tok)
        if not spoken or spoken in out:
            continue
        out[spoken] = tok
        if len(out) >= limit:
            break
    return out


def _has_case_transition(tok: str) -> bool:
    return any(a.islower() and b.isupper()
               for a, b in zip(tok, tok[1:]))


def _spoken_form(tok: str) -> str:
    words = [w for w in _WORD_SPLIT_RE.findall(tok) if w and w != "_"]
    if not words:
        return ""
    return " ".join(w.lower() for w in words)


def is_path_document(url_or_path: Optional[str]) -> bool:
    """Only file URLs (or scheme-less absolute paths) are document
    locators — an http(s) page URL is a web address, not a filesystem
    workspace (review fix: 'https://host/u/0' must never yield a
    workspace or force path_context)."""
    if not url_or_path:
        return False
    return url_or_path.startswith("file://") or (
        "://" not in url_or_path and url_or_path.startswith("/"))


def _workspace_from_path(url_or_path: str) -> Optional[str]:
    if not is_path_document(url_or_path):
        return None
    path = url_or_path
    if path.startswith("file://"):
        sp = urlsplit(path)
        path = sp.path
    parts = [p for p in path.split("/") if p]
    # The workspace is the containing directory (the project), not the
    # file itself: /Users/x/Notes/checklist.txt -> "Notes".
    if len(parts) < 2:
        return None
    return parts[-2] or None


_IDE_TITLE_SPLIT = re.compile(r"\s+[—–-]\s+")


def _ide_title_project(title: str) -> Optional[str]:
    # "main.py — myproject — Visual Studio Code" → "myproject"
    parts = _IDE_TITLE_SPLIT.split(title.strip())
    if len(parts) >= 2:
        seg = parts[-2].strip()
        if seg:
            return seg
    return None


def _url_origin(url: Optional[str]) -> Optional[str]:
    if not url or "://" not in url:
        return None
    try:
        sp = urlsplit(url)
    except ValueError:
        return None
    if not sp.netloc:
        return None
    origin = f"{sp.scheme}://{sp.netloc}"
    # Query and fragment are dropped by construction (S12).
    return origin


def _as_range(rng) -> tuple[Optional[int], Optional[int]]:
    """AX value shapes: CFRange-like (loc, len) tuple/dict, or an
    AXValue-ref whose description reads 'loc=len'; accept the common
    shapes without importing AX types."""
    if rng is None:
        return None, None
    if isinstance(rng, tuple) and len(rng) == 2:
        try:
            return int(rng[0]), int(rng[1])
        except (TypeError, ValueError):
            return None, None
    loc = getattr(rng, "location", None)
    ln = getattr(rng, "length", None)
    if loc is not None and ln is not None:
        try:
            return int(loc), int(ln)
        except (TypeError, ValueError):
            return None, None
    if isinstance(rng, dict) and "location" in rng:
        try:
            return int(rng["location"]), int(rng.get("length", 0))
        except (TypeError, ValueError):
            return None, None
    m = re.match(r"^NSRange\s*=\s*\{(\d+),\s*(\d+)\}", str(rng))
    if m:
        return int(m.group(1)), int(m.group(2))
    return None, None


def _ms(t0: float) -> float:
    return round((time.monotonic() - t0) * 1000.0, 3)


def _plausible_host(host: str) -> bool:
    """A title token is treated as a hostname only when it looks like
    one: every label non-empty and non-numeric, the TLD alphabetic with
    2+ chars and not a file extension — '16.4', 'index.html' and 'e.g'
    never become origins."""
    labels = host.split(".")
    if len(labels) < 2:
        return False
    tld = labels[-1]
    if not (tld.isalpha() and len(tld) >= 2):
        return False
    if tld in _NON_ORIGIN_TLDS:
        return False
    if any(lab.isdigit() for lab in labels[:-1]):
        return False
    return all(lab and not lab.startswith("-") and not lab.endswith("-")
               for lab in labels)


__all__ = [
    "SystemAXHost", "system_frontmost", "categorize",
    "read_field", "read_site_origin", "read_workspace",
    "extract_identifiers", "is_path_document",
    "CATEGORY_BROWSER", "CATEGORY_IDE", "CATEGORY_TERMINAL",
    "CATEGORY_UNKNOWN", "NEARBY_CHARS", "IDENTIFIER_LIMIT",
    "OMISSION_SECURE", "OMISSION_DENIED", "OMISSION_UNCLASSIFIABLE",
    "OMISSION_PERMISSION", "OMISSION_MESSAGING", "OMISSION_NOT_EXPOSED",
]
