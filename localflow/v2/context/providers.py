"""Context providers (V2 M06, Spec S12): what reads the destination.

All macOS access is isolated behind two injectable call sites —
``SystemAXHost`` (Accessibility reads; a short messaging timeout bounds
unresponsive apps) and the frontmost-app accessor (NSWorkspace). Tests
inject fakes that interpret synthetic AX trees
(``tests/v2/context/fixtures_context_targets.json``), so every filtering
rule is testable without a live destination.

Ownership: every content read goes to ONE element obtained from the
target application's own element (``focused_element_for(pid)``) and
verified to belong to the target process — never to whatever the
system-wide focus points at by the time a provider runs.

Absolute sensitive-field rules (S12): secure fields and denied apps are
never read for content; an unclassifiable field — including one whose
classification read FAILED — gets plain dictation without nearby text;
browser origins drop userinfo/path/query/fragment; placeholder values
are metadata, never text; no arbitrary filesystem read ever runs (a
document locator is a recorded string, not an open()).

Units: the Accessibility API counts UTF-16 code units. Ranges are
decoded from (and boxed into) native ``AXValue`` CFRanges here; retained
code-point offsets are derived only where exact (contracts/artifacts.md).
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
    OMISSION_CLASSIFICATION_FAILED,
    OMISSION_DENIED,
    OMISSION_MESSAGING,
    OMISSION_NOT_EXPOSED,
    OMISSION_PERMISSION,
    OMISSION_SECURE,
    OMISSION_SELECTION_UNAVAILABLE,
    OMISSION_UNCLASSIFIABLE,
    FieldContext,
    classify_field,
)

# Bounded reads: the nearby window per side (UTF-16 units requested),
# the identifier budget, and per-value budgets. A selection above its
# budget is not read at all; an over-budget metadata string is omitted
# rather than truncated (a cut title would no longer identify its
# window, a cut locator would name another file).
NEARBY_CHARS = 600
IDENTIFIER_LIMIT = 64
SELECTION_LIMIT = 4096
PLACEHOLDER_LIMIT = 200
DOCUMENT_LIMIT = 2048
TITLE_LIMIT = 512

# AXError codes that mean "this element does not have that attribute"
# (an honest absence) versus a read that failed.
AX_OK = 0
AX_ERR_UNSUPPORTED = -25205
AX_ERR_NO_VALUE = -25212
AX_ERR_API_DISABLED = -25211
AX_ERR_FAILURE = -25200
_ABSENT = frozenset({AX_ERR_UNSUPPORTED, AX_ERR_NO_VALUE})

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
# a filename in a title is never a site origin (compared case-blind).
_NON_ORIGIN_TLDS = frozenset({
    "app", "aspx", "avi", "css", "csv", "dmg", "exe", "gif", "go",
    "gz", "htm", "html", "ini", "java", "jpeg", "jpg", "js", "json",
    "local", "lock", "md", "mov", "mp3", "mp4", "pdf", "php", "pkg",
    "png", "py", "rb", "rs", "so", "svg", "tar", "toml", "ts", "tsv",
    "txt", "webp", "xml", "yaml", "yml", "zip",
})

_LONE_SURROGATE = re.compile("[\ud800-\udfff]")


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


def ax_range(value) -> Optional[tuple[int, int]]:
    """(location, length) from a native AXValue CFRange (decoded with
    AXValueGetValue — its description is not parsed), a (loc, len)
    tuple/list, an object with location/length, or a dict. None when
    the value is not a well-formed non-negative range."""
    if value is None:
        return None
    pair = None
    if type(value).__name__ == "AXValueRef":
        try:
            import ApplicationServices as AS
            ok, cf = AS.AXValueGetValue(value, AS.kAXValueCFRangeType, None)
        except Exception:
            return None
        pair = tuple(cf) if ok else None
    elif isinstance(value, (tuple, list)) and len(value) == 2:
        pair = tuple(value)
    elif isinstance(value, dict) and "location" in value:
        pair = (value["location"], value.get("length", 0))
    elif hasattr(value, "location") and hasattr(value, "length"):
        pair = (value.location, value.length)
    if pair is None:
        return None
    try:
        loc, ln = int(pair[0]), int(pair[1])
    except (TypeError, ValueError):
        return None
    if loc < 0 or ln < 0:
        return None
    return loc, ln


def ax_box_range(start: int, length: int):
    """A native AXValue CFRange for a parameterized attribute call."""
    import ApplicationServices as AS
    return AS.AXValueCreate(AS.kAXValueCFRangeType, (int(start), int(length)))


def utf16_len(s: str) -> int:
    return len(s.encode("utf-16-le", "surrogatepass")) // 2


def _utf16_clip(s: str, units: int) -> str:
    """At most ``units`` UTF-16 units of ``s``; a surrogate pair cut by
    the boundary is dropped, never kept half."""
    if utf16_len(s) > units:
        b = s.encode("utf-16-le", "surrogatepass")[:units * 2]
        s = b.decode("utf-16-le", "surrogatepass")
    return _LONE_SURROGATE.sub("", s)


class SystemAXHost:
    """Accessibility reads with a per-call messaging timeout so an
    unresponsive application can never stall the dictation path.

    Elements are obtained from the TARGET application's own element
    (``AXUIElementCreateApplication(pid)``), never from the system-wide
    focused element: a read can only ever reach the process the capture
    is about. Reads return ``(value, AXError)`` so callers can tell an
    attribute the element lacks from a read that failed."""

    def __init__(self, messaging_timeout: float = 0.2):
        self.messaging_timeout = messaging_timeout

    def is_trusted(self) -> bool:
        import ApplicationServices as AS
        return bool(AS.AXIsProcessTrusted())

    def _app(self, pid):
        import ApplicationServices as AS
        app = AS.AXUIElementCreateApplication(int(pid))
        AS.AXUIElementSetMessagingTimeout(app, self.messaging_timeout)
        return app

    def focused_element_for(self, pid):
        """The focused element WITHIN application ``pid`` (or None)."""
        if pid is None:
            return None
        value, err = self.read(self._app(pid), "AXFocusedUIElement")
        if err != AX_OK or value is None:
            return None
        import ApplicationServices as AS
        AS.AXUIElementSetMessagingTimeout(value, self.messaging_timeout)
        return value

    def element_pid(self, el) -> Optional[int]:
        import ApplicationServices as AS
        try:
            err, pid = AS.AXUIElementGetPid(el, None)
        except Exception:
            return None
        return int(pid) if err == AX_OK else None

    def element_token(self, el):
        """An opaque identity for cache keys: AXUIElementRefs compare
        with CFEqual, so a later fetch of the same element is equal."""
        return el

    def window_of(self, el):
        """The window that contains ``el`` (AXWindow); else the owning
        application's focused window. ``el`` is already ownership-
        verified by the caller, so its application is the target."""
        win, err = self.read(el, "AXWindow")
        if err == AX_OK and win is not None:
            return win
        pid = self.element_pid(el)
        if pid is None:
            return None
        win, err = self.read(self._app(pid), "AXFocusedWindow")
        return win if err == AX_OK else None

    def window_token(self, win):
        return win

    def read(self, el, name):
        import ApplicationServices as AS
        try:
            err, val = AS.AXUIElementCopyAttributeValue(el, name, None)
        except Exception:
            return None, AX_ERR_FAILURE
        return (val if err == AX_OK else None), err

    def attribute(self, el, name):
        return self.read(el, name)[0]

    def read_range(self, el, name="AXSelectedTextRange"):
        value, err = self.read(el, name)
        return (ax_range(value) if err == AX_OK else None), err

    def string_for_range(self, el, start: int, length: int) -> Optional[str]:
        import ApplicationServices as AS
        try:
            err, val = AS.AXUIElementCopyParameterizedAttributeValue(
                el, "AXStringForRange", ax_box_range(start, length), None)
        except Exception:
            return None
        return str(val) if err == AX_OK and val is not None else None

    def number_of_characters(self, el) -> Optional[int]:
        n, err = self.read(el, "AXNumberOfCharacters")
        try:
            return int(n) if err == AX_OK else None
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
    and the measured duration (for coverage/skip reporting). ``notes``
    are content-free sub-omissions ({field, reason}) of a provider whose
    main value resolved (e.g. a selection that was not retained);
    ``cached`` marks a value reused rather than read this capture."""

    def __init__(self, name, value=None, reason=None, provenance=None,
                 duration_ms=None, notes=(), cached=False):
        self.name = name
        self.value = value
        self.reason = reason
        self.provenance = provenance
        self.duration_ms = duration_ms
        self.notes = tuple(notes)
        self.cached = cached          # reused from the identity-keyed cache


def _str(value, limit) -> Optional[str]:
    if not isinstance(value, str):
        return None
    value = _LONE_SURROGATE.sub("", value)
    return value if len(value) <= limit else None


def classify_element(host, el) -> tuple[str, Optional[str],
                                        Optional[str], Optional[str]]:
    """(classification, role, subrole, failure reason) from AXRole and
    AXSubrole ONLY. A read that failed — rather than an attribute the
    element lacks — can never promote a field to text."""
    role, rerr = host.read(el, "AXRole")
    role = role if isinstance(role, str) else None
    if rerr != AX_OK and rerr not in _ABSENT:
        return FIELD_UNCLASSIFIABLE, None, None, \
            OMISSION_CLASSIFICATION_FAILED
    subrole, serr = host.read(el, "AXSubrole")
    subrole = subrole if isinstance(subrole, str) else None
    cls = classify_field(role, subrole)
    if cls == FIELD_TEXT and serr != AX_OK and serr not in _ABSENT:
        return FIELD_UNCLASSIFIABLE, role, None, \
            OMISSION_CLASSIFICATION_FAILED
    return cls, role, subrole, None


def read_field(host, denied: bool, el=None) -> ProviderResult:
    """Focused-field provider over ONE ownership-verified element:
    classify FIRST, then read bounded content only for classifiable
    text fields (S12 ordering is a hard rule)."""
    t0 = time.monotonic()
    name = "focused_field"
    if denied:
        return ProviderResult(name, reason=OMISSION_DENIED,
                              duration_ms=_ms(t0))
    if not host.is_trusted():
        return ProviderResult(name, reason=OMISSION_PERMISSION,
                              duration_ms=_ms(t0))
    if el is None:
        # No focused element in the target, or the lookup failed — the
        # host cannot distinguish cheaply, so the honest generic reason.
        return ProviderResult(name, reason=OMISSION_MESSAGING,
                              duration_ms=_ms(t0))
    cls, role, subrole, failed = classify_element(host, el)
    if cls == FIELD_SECURE:
        # Absolute rule: no content attribute of a secure field is ever
        # read — not its value, selection, placeholder or ranges.
        return ProviderResult(
            name, value=FieldContext(role=role, subrole=subrole,
                                     classification=FIELD_SECURE),
            reason=OMISSION_SECURE, duration_ms=_ms(t0))
    if cls != FIELD_TEXT:
        return ProviderResult(
            name, value=FieldContext(role=role, subrole=subrole,
                                     classification=cls),
            reason=(failed or (None if cls == FIELD_NONE
                               else OMISSION_UNCLASSIFIABLE)),
            duration_ms=_ms(t0))
    # Classifiable text field: bounded reads only. The range comes
    # first so a selection's size is known before its text is read.
    placeholder = _str(host.read(el, "AXPlaceholderValue")[0],
                       PLACEHOLDER_LIMIT)
    document = _str(host.read(el, "AXDocument")[0], DOCUMENT_LIMIT)
    # Validated whatever the host returns: a negative or malformed range
    # is no range (no selection, no flank read).
    rng = ax_range(host.read_range(el)[0])
    total = host.number_of_characters(el)
    if rng is not None and total is not None and rng[0] + rng[1] > total:
        rng = None                  # inconsistent with the field length
    notes = []
    selected_text = preceding = following = None
    cp_range = utf16_range = None
    if rng is not None:
        loc, length = rng
        utf16_range = (loc, loc + length)
        if length > SELECTION_LIMIT:
            notes.append({"field": "selected_text",
                          "reason": OMISSION_SELECTION_UNAVAILABLE})
        elif length:
            sel = host.read(el, "AXSelectedText")[0]
            if isinstance(sel, str) and utf16_len(sel) == length \
                    and not _LONE_SURROGATE.search(sel):
                selected_text = sel
            else:
                notes.append({"field": "selected_text",
                              "reason": OMISSION_SELECTION_UNAVAILABLE})
        p_start = max(0, loc - NEARBY_CHARS)
        preceding = _flank(host, el, p_start, loc - p_start)
        if total is not None and loc + length < total:
            following = _flank(host, el, loc + length,
                               min(NEARBY_CHARS, total - loc - length))
        # Code-point offsets are exact only when the whole prefix was
        # read (the selection starts inside the bounded window) and the
        # read kept every unit of it.
        if p_start == 0 and preceding is not None \
                and utf16_len(preceding) == loc \
                and (length == 0 or selected_text is not None):
            start = len(preceding)
            cp_range = (start, start + len(selected_text or ""))
    return ProviderResult(
        name,
        value=FieldContext(
            role=role, subrole=subrole, classification=FIELD_TEXT,
            selected_text=selected_text, selected_range=cp_range,
            preceding_text=preceding, following_text=following,
            placeholder=placeholder, document_url=document,
            selected_range_utf16=utf16_range),
        duration_ms=_ms(t0), notes=notes)


def _flank(host, el, start: int, length: int) -> Optional[str]:
    """One bounded nearby read: never more than requested, whatever the
    host returns."""
    if length <= 0:
        return ""
    s = host.string_for_range(el, start, length)
    if not isinstance(s, str):
        return None
    return _utf16_clip(s, length)


def read_site_origin(host, category: str, window_title: Optional[str],
                     denied: bool = False, el=None) -> ProviderResult:
    """Browser-origin provider: AXURL of the ownership-verified element
    (when one is given — a secure/unclassifiable element is not asked),
    reduced to scheme://host[:port]; a plausible host in the window
    title is the marked heuristic fallback. Never a guess from arbitrary
    text. A denied app is never read — not even probed (S12 absolute)."""
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
    url = host.read(el, "AXURL")[0] if el is not None else None
    origin = _url_origin(url if isinstance(url, str) else None)
    if origin is not None:
        return ProviderResult(name, value=origin, provenance="ax_url",
                              duration_ms=_ms(t0))
    host_token = _title_host(window_title)
    if host_token:
        # Titles expose hostnames at best; the scheme is not knowable
        # from a title token, so the recorded fallback origin is
        # https-schemed with provenance marking it heuristic — evidence,
        # never site-scope authority (ContextSnapshot.scope_site_origin).
        return ProviderResult(
            name, value=f"https://{host_token}",
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
    extension — not shipped here). Scans lazily and stops at the cap."""
    if field is None or field.classification != FIELD_TEXT:
        return {}
    text = field.nearby_text() or ""
    out: dict[str, str] = {}
    for m in _IDENTIFIER_RE.finditer(text):
        tok = m.group(0)
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
    """scheme://host[:port] rebuilt from validated parts — userinfo,
    path, query and fragment are dropped by construction; only web
    schemes with a real host (and a valid port) yield an origin."""
    if not url or "://" not in url:
        return None
    try:
        sp = urlsplit(url)
        port = sp.port
    except ValueError:
        return None
    scheme = sp.scheme.lower()
    if scheme not in ("http", "https") or not sp.hostname:
        return None
    # The host as written (after any userinfo, before any port): its
    # case is preserved — M05's comparison canonicalization already owns
    # case-insensitive equivalence; validation runs on the lowered form.
    hostport = sp.netloc.rsplit("@", 1)[-1]
    if hostport.startswith("["):                 # IPv6 literal
        host = hostport[:hostport.index("]") + 1]
    else:
        host = hostport.rsplit(":", 1)[0] if sp.port is not None \
            or hostport.endswith(":") else hostport
        if not host.isascii():
            try:
                host = host.encode("idna").decode("ascii")
            except UnicodeError:
                return None
        if not re.fullmatch(r"[a-z0-9.-]+", host.lower()):
            return None
    return f"{scheme}://{host}" + (f":{port}" if port is not None else "")


def _title_host(title: Optional[str]) -> Optional[str]:
    """The first plausible hostname in a title that is not part of an
    e-mail address or a path (an author@host byline, a/b/host.txt)."""
    if not title:
        return None
    for m in _TITLE_DOMAIN_RE.finditer(title):
        before = title[m.start() - 1] if m.start() else ""
        after = title[m.end()] if m.end() < len(title) else ""
        if before in ("@", "/", ".", ":") or after in ("@", "/"):
            continue
        if _plausible_host(m.group(1)):
            return m.group(1)
    return None


def _ms(t0: float) -> float:
    return round((time.monotonic() - t0) * 1000.0, 3)


def _plausible_host(host: str) -> bool:
    """A title token is treated as a hostname only when it looks like
    one: every label non-empty and non-numeric, the TLD alphabetic with
    2+ chars and not a file extension (in any case) — '16.4',
    'index.html', 'foo.com.TXT' and 'e.g' never become origins."""
    labels = host.split(".")
    if len(labels) < 2:
        return False
    tld = labels[-1]
    if not (tld.isalpha() and len(tld) >= 2):
        return False
    if tld.lower() in _NON_ORIGIN_TLDS:
        return False
    if any(lab.isdigit() for lab in labels[:-1]):
        return False
    return all(lab and not lab.startswith("-") and not lab.endswith("-")
               for lab in labels)


__all__ = [
    "SystemAXHost", "system_frontmost", "categorize",
    "read_field", "read_site_origin", "read_workspace",
    "classify_element", "extract_identifiers", "is_path_document",
    "ax_range", "ax_box_range", "utf16_len",
    "CATEGORY_BROWSER", "CATEGORY_IDE", "CATEGORY_TERMINAL",
    "CATEGORY_UNKNOWN", "NEARBY_CHARS", "IDENTIFIER_LIMIT",
    "SELECTION_LIMIT",
    "OMISSION_SECURE", "OMISSION_DENIED", "OMISSION_UNCLASSIFIABLE",
    "OMISSION_PERMISSION", "OMISSION_MESSAGING", "OMISSION_NOT_EXPOSED",
]
