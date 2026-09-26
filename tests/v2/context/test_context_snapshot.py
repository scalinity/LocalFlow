"""EV-08 / M06: target/context snapshots over synthetic AX trees.

Drives the real providers and collector through a fake AX host that
interprets ``fixtures_context_targets.json`` (8 destination classes x 4
E10 conditions + adversarial trees). Covers: identity/scope
distinguishability (AC03), secure fields retaining no content (AC01),
unclassifiable fields degrading to plain dictation, permission
unavailable, denied apps, the bounded deadline (AC02), stale-window
invalidation, hostile nearby text as data (AC04), mid-sentence
continuation, placeholder handling and browser-origin lifecycle.

Run: .venv/bin/python tests/v2/context/test_context_snapshot.py
"""

import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

from localflow.v2.context import ContextCollector  # noqa: E402
from localflow.v2.context.snapshot import (  # noqa: E402
    FIELD_SECURE,
    FIELD_TEXT,
)
from localflow.v2 import vocabulary as vocab  # noqa: E402

FIXTURES = json.loads(
    (pathlib.Path(__file__).parent / "fixtures_context_targets.json")
    .read_text(encoding="utf-8"))
SCENARIOS = {s["id"]: s for s in FIXTURES["scenarios"]}
ADVERSARIAL = {s["id"]: s for s in FIXTURES["adversarial"]}

# Explicit scheduling slack for deadline-tight assertions (the wait is
# bounded by the deadline; compose + thread wakeup add a few ms).
DEADLINE_SLACK_MS = 60.0

CONTENT_ATTRS = ("AXPlaceholderValue", "AXSelectedText",
                 "AXStringForRange", "AXValue")


class FakeAXHost:
    """Interprets one fixture tree through the real host protocol and
    records the attribute-read order (for classify-before-read)."""

    def __init__(self, scenario):
        self.scenario = scenario
        self.tree = scenario.get("tree", {})
        self.trusted = bool(scenario.get("host_trusted", True))
        self.reads: list[tuple[str, str]] = []

    def is_trusted(self):
        return self.trusted

    def focused_element(self):
        f = self.tree.get("focused")
        if f is None:
            return None
        sleep_ms = self.tree.get("sleep_ms", 0)
        if sleep_ms:
            time.sleep(sleep_ms / 1000.0)
        return ("focused", f)

    def attribute(self, el, name):
        _, f = el
        self.reads.append(("focused", name))
        if name == "AXRole":
            return f.get("role")
        if name == "AXSubrole":
            return f.get("subrole")
        if name == "AXURL":
            return f.get("url")
        if name == "AXPlaceholderValue":
            return f.get("placeholder")
        if name == "AXSelectedText":
            loc, ln = self._range(f)
            if loc is None or not ln:
                return None
            v = f.get("value") or ""
            return v[loc:loc + ln]
        if name == "AXSelectedTextRange":
            loc, ln = self._range(f)
            return None if loc is None else (loc, ln)
        if name == "AXDocument":
            return f.get("document")
        if name == "AXNumberOfCharacters":
            return len(f.get("value") or "")
        return None

    def focused_window(self, el):
        return ("window", self.tree)

    def window_title(self, win):
        self.reads.append(("window", "AXTitle"))
        return self.tree.get("window_title")

    def string_for_range(self, el, start, length):
        _, f = el
        self.reads.append(("focused", "AXStringForRange"))
        v = f.get("value") or ""
        return v[start:start + length]

    def number_of_characters(self, el):
        _, f = el
        self.reads.append(("focused", "AXNumberOfCharacters"))
        return len(f.get("value") or "")

    @staticmethod
    def _range(f):
        r = f.get("selected_text_range")
        if not r:
            return None, None
        return int(r[0]), int(r[1])

    # ---- job-owned typed protocol (M06 remediation) -------------------
    # The fixture's one application owns its tree: the focused element
    # belongs to the scenario's frontmost pid, identities are the fixture
    # objects themselves (a new tree = a new window/field).

    def _owner(self):
        return self.tree.get("owner_pid",
                             (self.scenario.get("frontmost") or {}).get("pid"))

    def focused_element_for(self, pid):
        if pid != self._owner():
            return None
        return self.focused_element()

    def element_pid(self, el):
        return self._owner()

    def element_token(self, el):
        return ("field", id(el[1]))

    def window_of(self, el):
        return ("window", self.tree)

    def window_token(self, win):
        return ("window", id(win[1]))

    def read(self, el, name):
        if el[0] == "window":
            if name == "AXTitle":
                self.reads.append(("window", "AXTitle"))
                t = self.tree.get("window_title")
                return (t, 0) if t is not None else (None, -25212)
            return None, -25205
        value = self.attribute(el, name)
        return (value, 0) if value is not None else (None, -25205)

    def read_range(self, el, name="AXSelectedTextRange"):
        value, err = self.read(el, name)
        return (tuple(value) if value is not None else None), err


class Recorder:
    """Content-free event sink for trace assertions."""

    def __init__(self):
        self.events = []

    def __call__(self, event, level="INFO", **kw):
        self.events.append((event, json.dumps(kw, default=str)))
        return True

    def blob(self):
        return "\n".join(f"{e} {d}" for e, d in self.events)


def run(scenario, *, denied_apps=(), deadline_ms=75.0,
        settle_sec=0.15, frontmost_override=None):
    host = FakeAXHost(scenario)
    sink = Recorder()
    coll = ContextCollector(
        enabled=True, deadline_ms=deadline_ms,
        denied_apps=denied_apps, emit=sink, host=host,
        frontmost=lambda: frontmost_override
        or scenario["frontmost"])
    target = coll.capture_identity()
    handle = coll.begin(target)
    if settle_sec:
        time.sleep(settle_sec)
    snap = coll.finalize(handle)
    return coll, host, sink, target, snap


def test_identity_and_scope_distinguishable():
    """AC03: app, browser-site and field identity are distinguishable —
    the eight destination classes produce distinct scope tuples and
    field classifications (E10 matrix core)."""
    seen_scopes = set()
    for s in FIXTURES["scenarios"]:
        _, _, _, target, snap = run(s)
        exp = s["expect"]
        assert snap is not None
        assert snap.target.app_bundle == s["frontmost"]["bundle"]
        assert snap.target.category == exp["category"], s["id"]
        assert snap.site_origin == exp.get("site_origin"), s["id"]
        assert snap.field is not None \
            and snap.field.classification == exp["classification"], s["id"]
        sc = snap.to_scope_context()
        assert sc.app_bundle == s["frontmost"]["bundle"]
        assert sc.site_origin == exp.get("site_origin")
        assert sc.workspace == exp.get("workspace"), s["id"]
        assert snap.path_context == exp.get("path_context", False), s["id"]
        # The hotkey-down identity scope is app-only; the finalized
        # scope can be wider (origin/workspace) — never narrower.
        assert target.to_scope_context().site_origin is None
        seen_scopes.add((sc.app_bundle, sc.site_origin, sc.workspace))
    # The scope key set distinguishes at least: plain app, browser
    # sites, IDE workspaces and the TextEdit document workspace.
    assert len({k for k in seen_scopes if k[1]}) >= 2, seen_scopes
    assert any(k[2] for k in seen_scopes), seen_scopes
    print(f"ok  identity/scope distinguishable across 8 destination"
          f" classes ({len(seen_scopes)} distinct scope keys)")


def test_ac01_secure_field_retains_no_content():
    s = ADVERSARIAL["LF-CTX-A1"]
    _, host, sink, _, snap = run(s)
    assert snap.field.classification == FIELD_SECURE
    # Classification happened on role/subrole alone; no content
    # attribute of the secure field was ever read.
    read_names = [a for _, a in host.reads]
    for attr in CONTENT_ATTRS:
        assert attr not in read_names, read_names
    # Nothing retained anywhere in the traces carries the canary value.
    for blob in (json.dumps(snap.to_json()), sink.blob()):
        assert "CANARY-SECRET" not in blob
    assert snap.omission_reason("focused_field") == "secure_field"
    # The identity itself is still recorded (destination known, content
    # not). Policy D1 (M06 remediation, contracts/context.md): a secure
    # element answers AXRole/AXSubrole only — its AXURL is not asked, so
    # the origin comes from the window title or is honestly absent
    # ("Sign in — Safari" names no host); the title itself is allowed
    # destination metadata.
    assert "AXURL" not in read_names, read_names
    assert snap.site_origin is None
    assert snap.window_title == "Sign in — Safari"
    print("ok  AC01: secure field classified before read; no retained"
          " content in snapshot, events or reads")


def test_classify_before_content_read():
    s = SCENARIOS["LF-CTX-002"]
    _, host, _, _, snap = run(s)
    names = [a for _, a in host.reads if a != "AXTitle"]
    first_content = next((i for i, a in enumerate(names)
                          if a in CONTENT_ATTRS), None)
    assert first_content is not None
    assert names.index("AXRole") < first_content
    assert names.index("AXSubrole") < first_content
    print("ok  field inspected (role/subrole) before any content"
          " collection (S12 ordering)")


def test_unclassifiable_field_plain_dictation():
    s = ADVERSARIAL["LF-CTX-A2"]
    _, host, sink, _, snap = run(s)
    assert snap.field.classification == "unclassifiable"
    assert snap.omission_reason("focused_field") == "unclassifiable_field"
    assert snap.field.selected_text is None \
        and snap.field.preceding_text is None
    assert "CANARY-CANVAS" not in json.dumps(snap.to_json())
    assert "CANARY-CANVAS" not in sink.blob()
    # Identity still resolves: plain dictation WITH destination app.
    assert snap.target.app_bundle == "com.example.canvasapp"
    print("ok  unclassifiable field: no nearby text, identity kept")


def test_permission_unavailable_degrades():
    s = ADVERSARIAL["LF-CTX-A3"]
    _, _, _, target, snap = run(s)
    assert target is not None and target.app_bundle  # NSWorkspace works
    assert snap.omission_reason("focused_field") == "permission_unavailable"
    assert snap.field is None or snap.field.preceding_text is None
    assert "CANARY-NO-AX" not in json.dumps(snap.to_json())
    assert snap.partial
    print("ok  AX permission unavailable: identity-only partial"
          " snapshot, no content")


def test_denied_app_never_read():
    s = ADVERSARIAL["LF-CTX-A4"]
    _, host, sink, _, snap = run(s, denied_apps=["com.example.secretbank"])
    assert snap.target.denied is True
    for f in ("focused_field", "site_origin", "workspace"):
        assert snap.omission_reason(f) == "denied_app", f
    # Not even role/subrole of the denied app's field was read.
    assert host.reads == [], host.reads
    assert "CANARY-DENIED" not in json.dumps(snap.to_json())
    assert "CANARY-DENIED" not in sink.blob()
    print("ok  denied app: identity records the denial; zero field"
          " reads")


def test_denied_browser_never_read():
    """Review critical: a denied app that is a BROWSER — the origin
    provider's leak class. Zero host reads, no origin, no window title,
    and the canary URL never reaches snapshot, events or envelope."""
    s = ADVERSARIAL["LF-CTX-A9"]
    _, host, sink, _, snap = run(
        s, denied_apps=["com.apple.Safari"])
    assert snap.target.denied is True
    assert snap.target.category == "browser"
    assert host.reads == [], host.reads
    assert snap.site_origin is None
    assert snap.window_title is None
    for f in ("focused_field", "site_origin", "workspace"):
        assert snap.omission_reason(f) == "denied_app", f
    block = snap.to_envelope_block()
    assert block["denied_app"] is True
    assert block["site_origin_resolved"] is False
    for blob in (json.dumps(snap.to_json()), sink.blob(),
                 json.dumps(block)):
        assert "health.example.com" not in blob
        assert "CANARY-999" not in blob
    print("ok  denied browser (review critical): origin provider never"
          " reads; no leak into snapshot, events or envelope")


def test_no_focused_element():
    s = ADVERSARIAL["LF-CTX-A5"]
    _, _, _, _, snap = run(s)
    assert snap.omission_reason("focused_field") == "ax_messaging_failed"
    assert snap.target.app_bundle == "com.apple.TextEdit"
    print("ok  no focused element: honest omission, identity kept")


def test_ac02_timeout_partial_snapshot():
    """A timed-out provider yields a partial snapshot within the
    deadline and never stalls the caller (M06-AC02)."""
    s = ADVERSARIAL["LF-CTX-A8"]
    host = FakeAXHost(s)
    coll = ContextCollector(enabled=True, deadline_ms=75.0, emit=Recorder(),
                            host=host, frontmost=lambda: s["frontmost"])
    t = coll.capture_identity()
    handle = coll.begin(t)
    t0 = time.monotonic()
    snap = coll.finalize(handle)    # no settle: the field is slow
    waited = (time.monotonic() - t0) * 1000.0
    assert snap.partial
    assert snap.omission_reason("focused_field") == "deadline"
    # Deadline + bounded scheduling slack only (explicit constant, not
    # a loose wall-clock bound).
    assert waited < 75.0 + DEADLINE_SLACK_MS, waited
    # The late provider eventually lands — as the downstream revision,
    # never merged into the pre-decode snapshot (AC05 mechanism).
    time.sleep(0.30)
    late = coll.take_downstream(handle)
    assert late is not None and late.stage == "downstream"
    assert late.context_snapshot_id != snap.context_snapshot_id
    assert late.field is not None and late.field.preceding_text == \
        "slow content", late.field
    assert snap.field is None       # the pre-decode snapshot never grew
    # Composed once: a second take returns None (no duplicate ids).
    assert coll.take_downstream(handle) is None
    print(f"ok  AC02: deadline cut at {waited:.1f} ms with partial"
          " snapshot; late result became a one-shot downstream"
          " revision")


def test_finalize_idempotent_and_reusable():
    s = SCENARIOS["LF-CTX-010"]
    coll = ContextCollector(enabled=True, emit=Recorder(),
                            host=FakeAXHost(s),
                            frontmost=lambda: s["frontmost"])
    handle = coll.begin(coll.capture_identity())
    snap = coll.finalize(handle)
    again = coll.finalize(handle)
    assert again is snap           # same object, no re-composition
    print("ok  finalize is idempotent per job")


def test_ac03_stale_window_invalidates():
    """A captured snapshot stops matching the frontmost app after a
    focus change; the metadata cache invalidates with it."""
    s = SCENARIOS["LF-CTX-009"]
    holder = {"fm": s["frontmost"]}
    host = FakeAXHost(s)
    sink = Recorder()
    coll = ContextCollector(enabled=True, deadline_ms=75.0, emit=sink,
                            host=host, frontmost=lambda: holder["fm"])
    t1 = coll.capture_identity()
    h1 = coll.begin(t1)
    time.sleep(0.15)
    snap = coll.finalize(h1)
    assert snap.same_destination(holder["fm"]) is True
    new_front = {"bundle": "com.apple.iChat", "name": "Messages",
                 "pid": 999}
    assert snap.same_destination(new_front) is False
    # Replacement authority check is the consumer-facing half M08 will
    # call before writing; a stale snapshot must answer False.
    # Cache invalidation: the next identity under a different pid drops
    # the cached origin/workspace.
    n_before = len([e for e, _ in sink.events
                    if e == "context.cache_invalidated"])
    holder["fm"] = new_front
    t2 = coll.capture_identity()
    assert t2.app_pid == 999 and t2.app_bundle == "com.apple.iChat"
    n_after = len([e for e, _ in sink.events
                   if e == "context.cache_invalidated"])
    assert n_after == n_before + 1
    print("ok  AC03: focus change invalidates cache and snapshot"
          " destination match")


def test_cache_reuse_same_window():
    s = SCENARIOS["LF-CTX-009"]
    coll, host, _, _, snap1 = run(s)
    # Second dictation, same frontmost + same window: origin/workspace
    # come from the cache (no second AXURL read).
    reads_before = len(host.reads)
    t2 = coll.capture_identity()
    h2 = coll.begin(t2)
    time.sleep(0.15)
    snap2 = coll.finalize(h2)
    assert snap2.site_origin == snap1.site_origin
    row = {p["name"]: p for p in snap2.providers}["site_origin"]
    assert row["status"] == "ok" and row.get("cached") is True, row
    new_url_reads = [a for _, a in host.reads[reads_before:]
                     if a == "AXURL"]
    assert not new_url_reads, new_url_reads
    print("ok  short-lived cache reuses origin/workspace while the"
          " window signature holds")


def test_ac04_hostile_nearby_text_is_data():
    for sid in ("LF-CTX-004", "LF-CTX-012", "LF-CTX-028"):
        s = SCENARIOS[sid]
        _, _, _, _, snap = run(s)
        assert snap.field.classification == FIELD_TEXT
        nearby = snap.field.nearby_text() or ""
        assert s["expect"]["hostile_nearby"] in nearby, sid
        # The snapshot carries it as plain data fields; there is no
        # instruction surface — nothing in the snapshot object is
        # executable or routed to a model prompt (pipeline half is
        # asserted in test_context_pipeline.py).
        blob = json.dumps(snap.to_json())
        assert "instructions" not in json.dumps(
            snap.to_envelope_block())
        assert isinstance(nearby, str)
    print("ok  AC04: prompt-like nearby text captured as data only")


def test_mid_sentence_continuation():
    for sid, frag in (("LF-CTX-002", "Hey, did you see the"),
                      ("LF-CTX-010", "Hi team, here is the"),
                      ("LF-CTX-022", "cd ~/Documents/Tools/LocalFlow && ")):
        s = SCENARIOS[sid]
        _, _, _, _, snap = run(s)
        assert snap.field.preceding_text == frag, sid
        assert snap.field.selected_text is None
    print("ok  mid-sentence continuation captured as preceding text")


def test_placeholder_never_becomes_text():
    s = SCENARIOS["LF-CTX-009"]
    _, _, _, _, snap = run(s)
    assert snap.field.placeholder == "Reply to Claude…"
    # The placeholder is metadata, distinct from field text: it is not
    # part of preceding/following/nearby and never prependable.
    assert snap.field.preceding_text in (None, "")
    assert "Reply to Claude" not in (snap.field.nearby_text() or "")
    print("ok  placeholder recorded as metadata, never as text")


def test_selected_text_and_range():
    for sid, sel in (("LF-CTX-003", "six"),
                     ("LF-CTX-011", "Q3"),
                     ("LF-CTX-023", "release-branch-v2")):
        s = SCENARIOS[sid]
        _, _, _, _, snap = run(s)
        assert snap.field.selected_text == sel, sid
        assert snap.field.selected_range is not None
        loc, end = snap.field.selected_range
        v = s["tree"]["focused"]["value"]
        assert v[loc:end] == sel
    print("ok  selected text + half-open range match the tree")


def test_browser_origin_lifecycle():
    # Query and fragment are dropped; origin changes invalidate scope.
    s = SCENARIOS["LF-CTX-009"]
    _, _, _, _, snap = run(s)
    assert snap.site_origin == "https://mail.google.com"
    assert snap.origin_source == "ax_url"
    assert "?" not in snap.site_origin and "#" not in snap.site_origin
    # A different site in the same browser is a different scope key.
    s2 = SCENARIOS["LF-CTX-017"]
    _, _, _, _, snap2 = run(s2)
    assert snap2.site_origin == "https://claude.ai"
    assert snap.scope_key() != snap2.scope_key()
    # Title fallback + honest not-exposed (A6/A7).
    _, _, _, _, a7 = run(ADVERSARIAL["LF-CTX-A7"])
    assert a7.site_origin == "https://docs.example.com"
    assert a7.origin_source == "window_title"
    _, _, _, _, a6 = run(ADVERSARIAL["LF-CTX-A6"])
    assert a6.site_origin is None
    assert a6.omission_reason("site_origin") == "not_exposed"
    print("ok  browser origin: query/fragment stripped, title fallback"
          " marked, honest not-exposed")


def test_identifiers_bounded_and_workspace_scoped():
    s = SCENARIOS["LF-CTX-026"]
    _, _, _, _, snap = run(s)
    ids = snap.identifiers
    assert len(ids) >= s["expect"]["identifiers_min"], ids
    assert ids.get("user id") == "user_id", ids
    # Bounded: never more than the configured limit.
    assert len(ids) <= 64
    # Non-code destinations yield no identifiers.
    s2 = SCENARIOS["LF-CTX-002"]
    _, _, _, _, snap2 = run(s2)
    assert snap2.identifiers == {}
    # Workspace resolution provenance.
    assert snap.workspace == "localflow"
    _, _, _, _, xcode = run(SCENARIOS["LF-CTX-029"])
    assert xcode.workspace == "LocalFlow"   # from AXDocument
    print("ok  identifiers extracted only from code-adjacent nearby"
          " text; workspace from title/document")


def test_scope_context_drives_vocabulary_snapshot():
    """The M05 ScopeContext adapter: the same entry set matches only
    under the finalized destination scope (the M05 sandbox/live gap M06
    closes)."""
    entries = [
        vocab.VocabularyEntry(
            entry_id="vocab-g1", canonical="MLX", approved=True,
            aliases=(vocab.Alias("mlx"),)),
        vocab.VocabularyEntry(
            entry_id="vocab-s1", canonical="Qwen", approved=True,
            scope_kind="site", scope_value="https://claude.ai",
            aliases=(vocab.Alias("q wen"),)),
        vocab.VocabularyEntry(
            entry_id="vocab-w1", canonical="Servo", approved=True,
            scope_kind="workspace", scope_value="localflow",
            aliases=(vocab.Alias("survo"),)),
    ]
    s = SCENARIOS["LF-CTX-026"]          # VS Code, workspace localflow
    _, _, _, _, snap = run(s)
    scoped = vocab.VocabularySnapshot(entries, snap.to_scope_context())
    assert "mlx" in scoped.match_index
    assert "survo" in scoped.match_index          # workspace matches
    assert "q wen" not in scoped.match_index      # site does not
    s2 = SCENARIOS["LF-CTX-018"]          # claude.ai prompt field
    _, _, _, _, snap2 = run(s2)
    scoped2 = vocab.VocabularySnapshot(entries, snap2.to_scope_context())
    assert "q wen" in scoped2.match_index
    assert "survo" not in scoped2.match_index
    print("ok  finalized scope feeds the M05 snapshot (site/workspace"
          " entries live)")


def test_context_disabled():
    coll = ContextCollector(enabled=False, emit=Recorder(),
                            host=FakeAXHost(SCENARIOS["LF-CTX-002"]),
                            frontmost=lambda: {"bundle": "x", "pid": 1})
    assert coll.capture_identity() is None
    assert coll.begin(None) is None and coll.finalize(None) is None
    print("ok  context disabled: no identity, no snapshot, no reads")


def test_stale_finalize_refused_and_abandoned():
    """Review critical: a failed identity capture can never finalize the
    PREVIOUS job's snapshot; a finalize naming a foreign target is
    refused outright. (Remediation: every call names the job's own
    handle — a job whose identity failed has none, so nothing of the
    previous job is reachable; there is no global collection to
    abandon.)"""
    s1 = SCENARIOS["LF-CTX-010"]
    holder = {"fm": s1["frontmost"]}
    coll = ContextCollector(enabled=True, emit=Recorder(),
                            host=FakeAXHost(s1),
                            frontmost=lambda: holder["fm"])
    t1 = coll.capture_identity()
    h1 = coll.begin(t1)
    time.sleep(0.1)
    snap1 = coll.finalize(h1)
    assert snap1 is not None
    # Job 2: identity capture fails (no frontmost) → no handle, so its
    # finalize returns None, never snap1.
    holder["fm"] = None
    t2 = coll.capture_identity()
    assert t2 is None and coll.begin(t2) is None
    assert coll.finalize(coll.begin(t2)) is None
    # A finalize that names a different target id is refused even with
    # an active collection.
    t2_holder = {"fm": SCENARIOS["LF-CTX-002"]["frontmost"]}
    coll2 = ContextCollector(enabled=True, emit=Recorder(),
                             host=FakeAXHost(SCENARIOS["LF-CTX-002"]),
                             frontmost=lambda: t2_holder["fm"])
    t2 = coll2.capture_identity()
    h2 = coll2.begin(t2)
    time.sleep(0.1)
    assert coll2.finalize(h2, target_snapshot_id="tgt-foreign") is None
    assert coll2.finalize(
        h2, target_snapshot_id=t2.target_snapshot_id) is not None
    # The older job's handle still finalizes ITS OWN snapshot.
    assert coll.finalize(h1) is snap1
    print("ok  per-job ownership: abandoned/stale collections never"
          " finalize into the wrong job")


def test_provider_exception_recorded_not_deadline():
    """A raising provider is omitted with provider_failed and an event —
    never mislabeled as a deadline cut."""

    class BoomHost(FakeAXHost):
        def attribute(self, el, name):
            # A read every text field performs (the selected text is
            # only read for a non-empty in-budget selection).
            if name == "AXPlaceholderValue":
                raise RuntimeError("synthetic provider crash")
            return super().attribute(el, name)

    s = SCENARIOS["LF-CTX-002"]
    sink = Recorder()
    coll = ContextCollector(enabled=True, emit=sink, host=BoomHost(s),
                            frontmost=lambda: s["frontmost"])
    t = coll.capture_identity()
    h = coll.begin(t)
    time.sleep(0.1)
    snap = coll.finalize(h)
    assert snap.omission_reason("focused_field") == "provider_failed"
    assert any(e == "context.provider_failed" for e, _ in sink.events)
    print("ok  provider exception: provider_failed omission + event,"
          " never a fake deadline reason")


def test_destination_changed_skips_content_reads():
    """Frontmost changed between PTT start and collection: no content is
    read at all (another app's field is never attributed to this
    target)."""
    s = SCENARIOS["LF-CTX-002"]
    holder = {"fm": s["frontmost"]}
    host = FakeAXHost(s)
    coll = ContextCollector(enabled=True, emit=Recorder(), host=host,
                            frontmost=lambda: holder["fm"])
    t = coll.capture_identity()
    holder["fm"] = {"bundle": "com.apple.Terminal", "name": "Terminal",
                    "pid": 4242}       # cmd-tab away mid-dictation
    h = coll.begin(t)
    time.sleep(0.1)
    snap = coll.finalize(h)
    assert host.reads == [], host.reads
    for f in ("focused_field", "site_origin", "workspace"):
        assert snap.omission_reason(f) == "destination_changed", f
    assert snap.partial
    print("ok  destination drift mid-collection: zero content reads,"
          " explicit destination_changed omissions")


def test_same_pid_window_change_invalidates_cache():
    """The cache sentinel: same app, different window/tab → the cached
    origin is NOT reused and the URL is re-read."""
    s = SCENARIOS["LF-CTX-009"]
    host = FakeAXHost(s)
    coll = ContextCollector(enabled=True, emit=Recorder(), host=host,
                            frontmost=lambda: s["frontmost"])
    t1 = coll.capture_identity()
    h1 = coll.begin(t1)
    time.sleep(0.05)
    snap1 = coll.finalize(h1)
    reads_before = len(host.reads)
    # Same pid, new tab (different window title + URL).
    s2 = SCENARIOS["LF-CTX-017"]
    host.tree = s2["tree"]
    t2 = coll.capture_identity()
    h2 = coll.begin(t2)
    time.sleep(0.05)
    snap2 = coll.finalize(h2)
    assert snap2.site_origin == "https://claude.ai" != snap1.site_origin
    assert any(a == "AXURL"
               for _, a in host.reads[reads_before:]), host.reads
    print("ok  same-app window change re-reads origin (cache sentinel"
          " holds)")


def test_no_window_title_branch():
    s = SCENARIOS["LF-CTX-002"]
    tree = dict(s["tree"])
    tree.pop("window_title", None)
    scenario = {**s, "tree": tree}
    _, _, _, _, snap = run(scenario)
    assert snap.window_title is None
    assert snap.field.preceding_text == "Hey, did you see the"
    print("ok  window-title-unavailable branch composes cleanly")


def test_same_destination_pidless_fallback():
    s = SCENARIOS["LF-CTX-002"]
    fm = {"bundle": "com.apple.iChat", "name": "Messages", "pid": None}
    _, _, _, _, snap = run(s, frontmost_override=fm)
    assert snap.same_destination(fm) is True
    other = {"bundle": "com.apple.Terminal", "pid": None}
    assert snap.same_destination(other) is False
    print("ok  same_destination falls back to bundle when pid is"
          " unknown")


def test_title_fallback_rejects_non_hosts():
    from localflow.v2.context.providers import _plausible_host
    for junk in ("16.4", "index.html", "e.g", "v1.2.3", "file.tar.gz"):
        assert not _plausible_host(junk), junk
    for real in ("docs.example.com", "github.com", "sub.domain.co.uk"):
        assert _plausible_host(real), real
    print("ok  title fallback: filenames/versions never become origins")


def main():
    test_identity_and_scope_distinguishable()
    test_ac01_secure_field_retains_no_content()
    test_classify_before_content_read()
    test_unclassifiable_field_plain_dictation()
    test_permission_unavailable_degrades()
    test_denied_app_never_read()
    test_denied_browser_never_read()
    test_no_focused_element()
    test_ac02_timeout_partial_snapshot()
    test_finalize_idempotent_and_reusable()
    test_ac03_stale_window_invalidates()
    test_cache_reuse_same_window()
    test_same_pid_window_change_invalidates_cache()
    test_ac04_hostile_nearby_text_is_data()
    test_mid_sentence_continuation()
    test_placeholder_never_becomes_text()
    test_selected_text_and_range()
    test_browser_origin_lifecycle()
    test_title_fallback_rejects_non_hosts()
    test_identifiers_bounded_and_workspace_scoped()
    test_scope_context_drives_vocabulary_snapshot()
    test_context_disabled()
    test_stale_finalize_refused_and_abandoned()
    test_provider_exception_recorded_not_deadline()
    test_destination_changed_skips_content_reads()
    test_no_window_title_branch()
    test_same_destination_pidless_fallback()
    print("all context snapshot tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
