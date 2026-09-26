"""M05 audit-corpus runner (V2 M05 remediation).

Executes every case of the audit's frozen synthetic corpus
(``m05_audit_corpus.json``, verbatim, every case NOT_RUN as delivered)
against the REAL production code of ``--code-root`` and writes a
SEPARATE result artifact keyed by case_id/family_id with the code SHA,
runner version and environment. The corpus file itself is never written.

Oracles are authored independently of the code under test: exact
Unicode strings and exact rule-id populations where the case supplies
them, otherwise the case's stated invariant implemented as an explicit
check. Matcher cases build entries with the dataclass constructor (the
matcher boundary); admission cases go through the public
``VocabularyStore.add_entry`` / ``import_json`` APIs (the admission
boundary) — the two are never mixed. Cases whose entries include a
dictionary skill run through the app's real ``_vocab_job_state``
composition (M05 snapshot → M10 SkillRegistry → M04 policy). App-level
stateful cases drive the real ``AppDelegate`` under the DECLARED
non-native shims (tests/v2/lifecycle/native_shims.py) with a scripted
M06 context service and supervisor — portable orchestration evidence,
never native AppKit/Accessibility/microphone/model evidence. Concurrent
cases serialize writer admission with an explicit turnstile, never
sleeps.

Status per case: ``pass`` | ``fail`` | ``declared_residual`` (a documented
limitation, never counted as a pass) | ``not_applicable`` (justified) |
``not_run`` (handler error — reported, never silently skipped).

Run:
    .venv/bin/python tests/v2/vocabulary/m05_corpus_runner.py \
        [--code-root DIR] [--label NAME] [--output PATH] [--only IDS]
Exit code: 0 when no case failed or errored, 1 otherwise.
"""

from __future__ import annotations

import argparse
import collections
import contextlib
import dataclasses
import hashlib
import io
import json
import os
import pathlib
import platform
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import traceback

RUNNER_VERSION = "m05-corpus-runner-1"
HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parents[2]
CORPUS = HERE / "m05_audit_corpus.json"

ap = argparse.ArgumentParser()
ap.add_argument("--code-root", default=str(REPO))
ap.add_argument("--label", default="current")
ap.add_argument("--output")
ap.add_argument("--only")
ap.add_argument("--quiet", action="store_true")
ARGS = ap.parse_args() if __name__ == "__main__" else ap.parse_args([])
CODE = pathlib.Path(ARGS.code_root).resolve()
sys.path.insert(0, str(CODE))
sys.path.insert(0, str(CODE / "tests" / "v2" / "lifecycle"))

from localflow.v2 import store as store_mod  # noqa: E402
from localflow.v2 import vocabulary as V  # noqa: E402
from localflow.v2 import vocabulary_store as VS  # noqa: E402
from localflow.v2.normalize import (  # noqa: E402
    ContextSnapshot,
    NormalizationPolicy,
    normalize,
)

# The contract's documented budget-omission reason (contracts/
# vocabulary.md "budget omissions with reason `budget_limit`"). The
# corpus text of BUDGET-99/100/101 names "term_limit"; that string is
# the HintSet FIELD holding the budget, not a documented reason — the
# oracle uses the contract (recorded per case as an oracle note).
BUDGET_REASON = "budget_limit"


class CaseError(Exception):
    pass


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)


# ---------------------------------------------------------------------------
# Construction helpers
# ---------------------------------------------------------------------------

def mk_entry(d):
    return V.VocabularyEntry(
        entry_id=d["entry_id"], canonical=d["canonical"],
        language=d.get("language"), kind=d.get("kind", "term"),
        matching_mode=d.get("matching_mode", "phrase"),
        scope_kind=d.get("scope_kind", "global"),
        scope_value=d.get("scope_value"),
        priority=d.get("priority", 0), pinned=d.get("pinned", False),
        usage_count=d.get("usage_count", 0),
        last_used_utc=d.get("last_used_utc"),
        origin=d.get("origin", "user"), enabled=d.get("enabled", True),
        approved=d.get("approved", False),
        verification=d.get("verification", "suggested"),
        revision=d.get("revision", 1),
        aliases=tuple(V.Alias(alias=a["alias"],
                              approved=a.get("approved", True),
                              language=a.get("language"))
                      for a in d.get("aliases", [])))


def scope_of(case):
    return V.ScopeContext(**(case.get("ScopeContext") or {}))


def ent(eid, canonical, aliases=(), **kw):
    kw.setdefault("approved", True)
    kw.setdefault("verification", "explicit" if kw["approved"]
                  else "suggested")
    return V.VocabularyEntry(entry_id=eid, canonical=canonical,
                             aliases=tuple(V.Alias(a) for a in aliases),
                             **kw)


def result_view(res):
    return {
        "text": res.text,
        "edits": [{"cls": e.cls, "input": e.input_text,
                   "output": e.output_text, "rule_id": e.rule_id,
                   "reason": e.reason,
                   "span": list(e.input_span.as_pair())}
                  for e in res.edits],
        "rejected": [{"cls": r.cls, "input": r.input_text,
                      "reason": r.reason, "rule_id": r.rule_id,
                      "span": [r.span.start, r.span.end]}
                     for r in res.rejected],
    }


def norm_direct(text, entries, scope=None, snippets=None):
    snap = V.VocabularySnapshot(entries, scope)
    ctx = ContextSnapshot(vocabulary=snap)
    if snippets is not None:
        ctx = dataclasses.replace(ctx, snippets=snippets)
    return normalize(text, NormalizationPolicy(), ctx)


def vocab_ids(view, classes=("vocabulary",)):
    return [e["rule_id"] for e in view["edits"] if e["cls"] in classes]


def new_store(td, name="v2.db", events=None):
    rec = events if events is not None else []

    def emit(n, **kw):
        rec.append({"event": n, **kw})
    st = store_mod.Store(pathlib.Path(td) / name, emit=emit)
    return st, VS.VocabularyStore(st), rec


def store_add(vs, d):
    """Public admission: add a corpus entry through add_entry with its
    stable id, per-alias approval as tuples."""
    return vs.add_entry(
        d["canonical"],
        [(a["alias"], a.get("approved", True)) for a in d["aliases"]],
        language=d.get("language"), kind=d.get("kind", "term"),
        scope_kind=d.get("scope_kind", "global"),
        scope_value=d.get("scope_value"), priority=d.get("priority", 0),
        pinned=d.get("pinned", False), origin=d.get("origin", "user"),
        enabled=d.get("enabled", True), approved=d.get("approved", False),
        verification=d.get("verification"), entry_id=d["entry_id"])


def raw_sql(path, sql, args=()):
    con = sqlite3.connect(path)
    try:
        return con.execute(sql, args).fetchall()
    finally:
        con.close()


class Turnstile:
    """Scripted writer admission (see scripts/v2/m05_remediation_repro.py):
    participating threads call ``Store.submit`` in the scripted order; a
    finished thread's remaining turns are skipped. The liveness timeout
    is counted and reported, never used as a race outcome."""

    def __init__(self, store, script):
        self.store = store
        self.real = store.submit
        self.script = list(script)
        self.cond = threading.Condition()
        self.done = set()
        self.participants = set(script)
        self.timeouts = 0
        store.submit = self.submit

    def submit(self, fn, *a, **kw):
        name = threading.current_thread().name
        if name not in self.participants:
            return self.real(fn, *a, **kw)
        with self.cond:
            while True:
                while self.script and self.script[0] in self.done:
                    self.script.pop(0)
                if not self.script or self.script[0] == name:
                    break
                if not self.cond.wait(10):
                    self.timeouts += 1
                    break
        try:
            return self.real(fn, *a, **kw)
        finally:
            with self.cond:
                if self.script and self.script[0] == name:
                    self.script.pop(0)
                self.cond.notify_all()

    def finished(self, name):
        with self.cond:
            self.done.add(name)
            self.cond.notify_all()

    def restore(self):
        self.store.submit = self.real


def run_threads(ts, fns):
    out = {}

    def wrap(name, fn):
        try:
            out[name] = ("ok", fn())
        except Exception as e:
            out[name] = ("error", type(e).__name__, str(e))
        finally:
            ts.finished(name)
    threads = [threading.Thread(target=wrap, args=(n, f), name=n)
               for n, f in fns.items()]
    for t in threads:
        t.start()
    for t in threads:
        t.join(60)
    return out


# ---------------------------------------------------------------------------
# App harness (declared non-native shims)
# ---------------------------------------------------------------------------

def _helpers():
    import m03_helpers as h  # noqa: E402  (installs the declared shims)
    return h


class FakeContext:
    def __init__(self):
        self.identity = None
        self.final = None
        self.on_finalize = None

    def capture_identity(self):
        return self.identity

    def begin(self, identity):
        return object()

    def abandon(self):
        pass

    def finalize(self, job_id=None, target_snapshot_id=None, **kw):
        if self.on_finalize is not None:
            self.on_finalize()
        return self.final


def _target(bundle, category="editor"):
    from localflow.v2 import ids
    from localflow.v2.context import snapshot as csnap
    return csnap.TargetSnapshot(target_snapshot_id=ids.new_id("tgt"),
                                app_bundle=bundle, app_name=bundle,
                                category=category)


def _final(tgt, workspace=None, site=None):
    from localflow.v2 import ids
    from localflow.v2.context import snapshot as csnap
    return csnap.ContextSnapshot(
        context_snapshot_id=ids.new_id("ctx"), stage="pre_decode",
        target=tgt, workspace=workspace, site_origin=site)


class AppRun:
    def __init__(self, td, text, cfg=None):
        h = _helpers()
        self.h = h
        self.a = h.App(td, cfg=cfg, start_coordinator=False)
        self.d = self.a.d
        self.fc = FakeContext()
        self.d._context = self.fc
        self.events = []
        real_emit = self.d.v2log.emit

        def emit(name, **kw):
            self.events.append({"event": name, **kw})
            return real_emit(name, **kw)
        self.d.v2log.emit = emit
        store_emit = self.d.store.emit

        def semit(name, **kw):
            self.events.append({"event": name, **kw})
            return store_emit(name, **kw)
        self.d.store.emit = semit
        outer = self

        class Sup(h.GateSup):
            def transcribe(self, **kw):
                if outer.on_transcribe is not None:
                    outer.on_transcribe()
                return super().transcribe(**kw)

            def clean(self, **kw):
                outer.clean_kwargs.append(kw)
                return super().clean(**kw)
        self.on_transcribe = None
        self.clean_kwargs = []
        self.sup = Sup(text=text)
        self.a.set_sup(self.sup)
        self.a.start_coordinator()

    def job(self, bundle, workspace=None, site=None, category="editor"):
        h = self.h
        self.fc.identity = _target(bundle, category) if bundle else None
        self.fc.final = _final(self.fc.identity, workspace, site) \
            if bundle else None
        h.AppHelper.calls.clear()
        n = len(self.clean_kwargs)
        self.a.dictate(blocks=10)
        ok = self.a.wait_call("_finishWithText_", 20)
        text, job = None, None
        for fn, args in list(h.AppHelper.calls):
            if getattr(fn, "__name__", "") == "_finishWithText_":
                text, job = args[0], args[1]
        self.a.drain()
        kw = self.clean_kwargs[n] if len(self.clean_kwargs) > n else {}
        return {"finished": ok, "text": text, "job": job,
                "cleanup_input": kw.get("raw_text"),
                "pairs": [tuple(p) for p in
                          (kw.get("vocabulary_pairs") or [])],
                "relevant": list(kw.get("relevant_vocabulary") or [])}

    def close(self):
        self.a.close()


def app_state_norm(case, text):
    """Matcher cases that include a dictionary SKILL: production
    composition through the app's _vocab_job_state (store admission of
    the entries with their stable ids, the M10 registry merge, the M04
    policy) — then the real engine."""
    with tempfile.TemporaryDirectory() as td:
        h = _helpers()
        a = h.App(td, start_coordinator=False)
        try:
            d = a.d
            for e in case["synthetic_vocabulary_entries"]:
                store_add(d._vocab, e)
            pol, ctx, _hs = d._vocab_job_state(
                scope_of(case), m10={"skill_records": (),
                                     "skill_records_rev": None,
                                     "norm_profile": None})
            return result_view(normalize(text, pol, ctx)), pol, ctx
        finally:
            a.close()


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

HANDLERS = {}


def handles(*families):
    def deco(fn):
        for f in families:
            HANDLERS[f] = fn
        return fn
    return deco


def ok(actual, **kw):
    return {"status": "pass", "actual": actual, **kw}


@handles("exact-positive", "clause-boundary", "edge-punctuation",
         "protected-alias", "five-scope-precedence", "scope-isolation",
         "same-scope-active-mask", "implicit-explicit-mask",
         "wrong-rule-scope-characterization", "approval-gate",
         "language-is-metadata", "substring-controls",
         "approved-common-word", "canonical-noop",
         "inactive-longer-alias", "active-longer-alias")
def h_text(case):
    ents = [mk_entry(e) for e in case["synthetic_vocabulary_entries"]]
    view = result_view(norm_direct(case["input"], ents, scope_of(case)))
    exp = case["expected_text"]
    check(view["text"] == exp,
          f"text {view['text']!r} != expected {exp!r}")
    want = case.get("expected_winning_rule_ids")
    got = vocab_ids(view)
    if want:
        check(got == want, f"winning rule ids {got} != {want}")
    else:
        check(not got, f"unexpected vocabulary edits {got}")
    if case["family_id"] == "canonical-noop":
        check(not view["edits"], "a canonical no-op must record no edit"
              " (so no record_hits increment)")
    return ok(view, disposition="exact_oracle")


@handles("left-overlap-noop")
def h_left_overlap(case):
    ents = [mk_entry(e) for e in case["synthetic_vocabulary_entries"]]
    p1 = result_view(norm_direct(case["input"], ents))
    check(p1["text"] == case["expected_text"],
          f"pass1 {p1['text']!r} != {case['expected_text']!r}")
    want = case.get("expected_winning_rule_ids")
    if want:
        check(vocab_ids(p1) == want, f"pass1 ids {vocab_ids(p1)} != {want}")
    out = {"pass1": p1}
    if case.get("steps"):
        p2 = result_view(norm_direct(p1["text"], ents))
        out["pass2"] = p2
        check(p2["text"] == p1["text"],
              f"pass2 drifted {p1['text']!r} -> {p2['text']!r}")
        check(not vocab_ids(p2), f"pass2 vocabulary edits {vocab_ids(p2)}")
    return ok(out, disposition="exact_oracle_two_pass")


@handles("literal-payload")
def h_literal(case):
    ents = [mk_entry(e) for e in case["synthetic_vocabulary_entries"]]
    res = norm_direct(case["input"], ents)
    view = result_view(res)
    check(view["text"] == case["expected_text"],
          f"text {view['text']!r} != {case['expected_text']!r}")
    zones = [(p.span.start, p.span.end) for p in res.protected
             if getattr(p, "kind", "") in ("literal_escape", "escape")
             or "escape" in str(getattr(p, "kind", ""))]
    for e in view["edits"]:
        if e["cls"] != "vocabulary":
            continue
        s, t = e["span"]
        check(not any(s < b and a < t for a, b in zones),
              f"vocabulary edit inside the protected payload: {e}")
    if "\nuse clod code" in case["input"]:
        check(any(e["cls"] == "vocabulary" for e in view["edits"]),
              "vocabulary outside the payload must still apply")
    return ok({**view, "protected_zones": zones},
              disposition="exact_oracle")


# Characterization authored from the retained M04 tokenizer contract
# (contracts/normalization.md; M04 addendum "paren/quote-attached words
# are not word tokens"): such tokens never form an alias phrase, and an
# em dash is its own non-word token — the alias does not span it.
TOKEN_CHARACTERIZATION = {"(clod code)": "(clod code)",
                          "clod — code": "clod — code",
                          "'clod code'": "'clod code'"}


@handles("tokenizer-residual")
def h_tokenizer(case):
    ents = [mk_entry(e) for e in case["synthetic_vocabulary_entries"]]
    view = result_view(norm_direct(case["input"], ents))
    want = TOKEN_CHARACTERIZATION[case["input"]]
    check(view["text"] == want,
          f"characterized {want!r}, observed {view['text']!r}")
    if case["input"] == "clod — code":
        # A spaced em dash is its own token between two clauses: not
        # matching across it is the intended behavior.
        return ok(view, disposition="characterization:dash_is_a_token")
    # Paren/quote-ATTACHED words are not word tokens (retained M04
    # tokenizer limitation): the alias never matches there. A known
    # limitation, never counted as a pass.
    return {"status": "declared_residual", "actual": view,
            "disposition": "residual:m04_attached_punctuation_tokens",
            "reason": "paren/quote-attached words are not word tokens"
                      " (M04 addendum, retained; not an M05 repair)"}


@handles("masked-longer-alias")
def h_masked_longer(case):
    """Adjudicated (addendum D-M1): a masked resolution is NOT a span
    reservation — the same rule the engine applies to an ambiguous
    same-span pair; the shorter approved rule still owns its word."""
    ents = [mk_entry(e) for e in case["synthetic_vocabulary_entries"]]
    view = result_view(norm_direct(case["input"], ents))
    snap = V.VocabularySnapshot(ents)
    check(any(c["alias"] == "clod code" for c in snap.conflicts),
          "the longer phrase must be recorded as a masked conflict")
    check(view["text"] == "Claude code" and vocab_ids(view) == ["E-CL"],
          f"adjudicated 'Claude code' via E-CL, got {view['text']!r}"
          f" {vocab_ids(view)}")
    return ok(view, disposition="adjudicated_policy:D-M1")


@handles("skill-command-ownership", "skill-term-composition",
         "skill-approval-scope")
def h_skill(case):
    view, pol, ctx = app_state_norm(case, case["input"])
    exp = case.get("expected_text")
    skill_edits = [e for e in view["edits"] if e["cls"] == "skill"]
    if case["family_id"] == "skill-approval-scope":
        check(view["text"] == case["input"],
              f"no skill rewrite expected, got {view['text']!r}")
        check(not skill_edits, f"applied skill edit {skill_edits}")
        return ok(view, disposition="invariant")
    check(view["text"] == exp, f"text {view['text']!r} != {exp!r}")
    if exp == case["input"]:
        check(not skill_edits, f"applied skill edit {skill_edits}")
        check(not vocab_ids(view), "no vocabulary edit expected")
    else:
        check(len(skill_edits) == 1, f"one skill edit, got {skill_edits}")
        check(skill_edits[0]["rule_id"] == "E-SK",
              "applied dictionary skill must retain approving provenance"
              f" (rule_id E-SK), got {skill_edits[0]['rule_id']!r}")
        check(not vocab_ids(view), "layer-5 term must not also apply")
    return ok(view, disposition="invariant+exact")


@handles("same-span-layer-composition")
def h_same_span(case):
    from localflow.v2 import snippets as sn
    out = {}
    if case["case_id"] == "SNIP-001":
        ents = [mk_entry(e) for e in case["synthetic_vocabulary_entries"]]
        for label, body in (("different_output", "Snippet output"),
                            ("equal_output", "VocabularyOutput")):
            snip = sn.Snippet(snippet_id="S-1", trigger="shared trigger",
                              name="shared", content=body)
            res = norm_direct("shared trigger", ents,
                              snippets=sn.SnippetSnapshot([snip]))
            view = result_view(res)
            check(view["text"] == body, f"{label}: {view['text']!r}")
            check([e["cls"] for e in view["edits"]] == ["snippet"],
                  f"{label}: snippet must own the span: {view['edits']}")
            lost = [r for r in view["rejected"] if r["cls"] == "vocabulary"]
            check(lost and lost[0]["reason"] == "lower_layer_same_span"
                  and lost[0]["span"] == view["edits"][0]["span"],
                  f"{label}: vocabulary must lose on the SAME span: {lost}")
            out[label] = view
        return ok(out, disposition="real_registry_same_span")
    # SNIP-002: a real snippet whose trigger covers exactly the
    # dictionary skill's "slash code review" span.
    for label, body, want in (
            ("different_output", "Review checklist", "slash code review"),
            ("equal_output", "/code-review", None)):
        snip = sn.Snippet(snippet_id="S-2", trigger="slash code review",
                          name="review", content=body)
        view, pol, ctx = app_state_norm(case, "slash code review")
        res = normalize("slash code review", pol, dataclasses.replace(
            ctx, snippets=sn.SnippetSnapshot([snip])))
        view = result_view(res)
        out[label] = view
        if want is not None:
            check(view["text"] == want,
                  f"{label}: {view['text']!r} != {want!r}")
        else:
            check(view["text"] in ("/code-review", "slash code review"),
                  f"{label}: {view['text']!r}")
        if label == "different_output":
            amb = [r for r in view["rejected"]
                   if r["reason"] == "ambiguous_same_span"]
            check({r["cls"] for r in amb} == {"skill", "snippet"},
                  f"both same-layer proposals rejected ambiguous: {amb}")
        else:
            # The corpus: identical output MAY coalesce, but the winning
            # provenance must be deterministic. M04's accepted same-span
            # rule treats the same text with different typed values
            # (skill name vs snippet id) as ambiguous — also a
            # deterministic outcome. Either is accepted; a coalesced
            # winner must carry its provenance, and repeated runs must
            # agree exactly.
            again = result_view(normalize("slash code review", pol,
                                          dataclasses.replace(
                                              ctx, snippets=sn.SnippetSnapshot(
                                                  [snip]))))
            check(again == view, "same-span outcome must be deterministic")
            if view["edits"]:
                check(len(view["edits"]) == 1
                      and view["edits"][0]["cls"] == "skill"
                      and view["edits"][0]["rule_id"] == "E-SK",
                      f"coalesced winner must carry provenance:"
                      f" {view['edits']}")
            else:
                amb = {r["cls"] for r in view["rejected"]
                       if r["reason"] == "ambiguous_same_span"}
                check(amb == {"skill", "snippet"},
                      f"uncoalesced pair must be rejected as ambiguous:"
                      f" {view['rejected']}")
    return ok(out, disposition="real_registry_same_span")


@handles("alias-admission")
def h_alias_admission(case):
    op = case["operation"]
    alias = op["alias"]
    out = {}
    for path in ("manual", "import"):
        with tempfile.TemporaryDirectory() as td:
            st, vs, _ = new_store(td)
            rev0 = vs.revision()
            try:
                if path == "manual":
                    vs.add_entry(op["canonical"], [alias], approved=True)
                else:
                    p = pathlib.Path(td) / "imp.json"
                    p.write_text(json.dumps({"entries": [{
                        "entry_id": "x", "canonical": op["canonical"],
                        "scope": ["global", None], "approved": True,
                        "enabled": True, "verification": "explicit",
                        "aliases": [{"alias": alias,
                                     "approved": True}]}]}),
                        encoding="utf-8")
                    vs.import_json(p)
                admitted = "accept"
            except Exception as e:
                admitted = f"reject:{type(e).__name__}"
            rows = [[a.alias for a in e.aliases] for e in vs.entries()]
            out[path] = {"admission": admitted, "rows": rows,
                         "revision_delta": vs.revision() - rev0}
            st.close()
    want = case["expected_admission"]
    for path, o in out.items():
        check(o["admission"].split(":")[0] == want,
              f"{path}: {o['admission']} != {want}")
        if want == "reject":
            check(not o["rows"] and o["revision_delta"] == 0,
                  f"{path}: rejected input mutated the store: {o}")
        else:
            check(o["rows"] == [[" ".join(alias.split())]],
                  f"{path}: stored alias {o['rows']}")
    check(out["manual"]["admission"].split(":")[0]
          == out["import"]["admission"].split(":")[0],
          "manual creation and import must agree")
    return ok(out, disposition="public_admission")


CANARIES = ("Claude", "clod")


@handles("strict-boolean-admission")
def h_strict_bool(case):
    with tempfile.TemporaryDirectory() as td:
        st, vs, events = new_store(td)
        rev0 = vs.revision()
        p = pathlib.Path(td) / "imp.json"
        p.write_text(json.dumps(case["import_document"]), encoding="utf-8")
        try:
            r = vs.import_json(p)
            admitted, msg = ("accept", json.dumps(r))
        except Exception as e:
            admitted, msg = (f"reject:{type(e).__name__}", str(e))
        rows = [(e.canonical, e.approved, e.enabled, e.pinned,
                 [a.approved for a in e.aliases]) for e in vs.entries()]
        hist = raw_sql(st.db_path, "SELECT count(*) FROM vocabulary_history")
        out = {"admission": admitted, "rows": rows,
               "revision_delta": vs.revision() - rev0,
               "history_rows": hist[0][0],
               "error_message_content_free": not any(
                   c in msg for c in CANARIES) if admitted != "accept"
               else None,
               "store_events": [e["event"] for e in events]}
        st.close()
    check(admitted.startswith("reject"),
          f"malformed boolean admitted: {rows}")
    check(not rows and out["revision_delta"] == 0
          and out["history_rows"] == 0, f"partial state change: {out}")
    check(out["error_message_content_free"],
          "rejection message carries dictionary content")
    return ok(out, disposition="public_admission")


@handles("ranking-tuples")
def h_ranking(case):
    ents = [mk_entry(e) for e in case["synthetic_vocabulary_entries"]]
    snap = V.VocabularySnapshot(ents, scope_of(case))
    hs = V.RelevantVocabularySelector(100).select(
        snap, now_utc="2026-09-25T00:00:00Z")
    order = [t.entry_id for t in hs.terms]
    check(order == case["expected_hint_membership"],
          f"order {order} != {case['expected_hint_membership']}")
    return ok({"order": order,
               "scores": [list(t.score) for t in hs.terms]},
              disposition="independent_rank_tuple")


def _alpha(i):
    s = ""
    n = i
    while True:
        s = chr(ord("a") + n % 26) + s
        n = n // 26 - 1
        if n < 0:
            return s


@handles("hint-budget")
def h_budget(case):
    if "generator" in case:
        n = case["generator"]["count"]
        limit = case["selector_limit"]
        ents = [ent(f"E-{i:04d}", f"Term{_alpha(i).capitalize()}")
                for i in range(n)]
        # Permuted insertion: the partition must not depend on order.
        ents = ents[1::2] + ents[0::2]
        hs = V.RelevantVocabularySelector(limit).select(
            V.VocabularySnapshot(ents), now_utc="2026-09-25T00:00:00Z")
        ids_all = sorted(e.entry_id for e in ents)
        sel = [t.entry_id for t in hs.terms]
        om = [o["entry_id"] for o in hs.omitted]
        # Independent oracle: every rank component ties, so the
        # contract's final tie-break (entry id ascending) decides.
        check(sel == ids_all[:limit], "selected must be the first ids")
        check(om == ids_all[limit:], "omitted must be the rest, in order")
        check(len(sel) == min(n, limit)
              and len(om) == max(0, n - limit), (len(sel), len(om)))
        check(not set(sel) & set(om) and set(sel) | set(om)
              == set(ids_all), "exact id partition")
        check(all(o["reason"] == BUDGET_REASON for o in hs.omitted),
              f"omission reasons {[o['reason'] for o in hs.omitted]}")
        return ok({"selected": len(sel), "omitted": len(om),
                   "reasons": sorted({o["reason"] for o in hs.omitted})},
                  disposition="independent_partition",
                  oracle_note="omission reason checked against the"
                              " contract's documented 'budget_limit' (the"
                              " corpus text says 'term_limit', the HintSet"
                              " field that carries the budget)")
    limit_present = "selector_limit" in case
    limit = case.get("selector_limit")
    try:
        sel = V.RelevantVocabularySelector(limit) if limit_present \
            else V.RelevantVocabularySelector()
        made = {"constructed": True, "max_terms": sel.max_terms}
    except Exception as e:
        made = {"constructed": False, "error": type(e).__name__}
    if limit_present:
        check(not made["constructed"],
              f"malformed limit {limit!r} accepted: {made}")
    else:
        check(made["constructed"] and made["max_terms"] == 100,
              f"absent limit must use the documented default 100: {made}")
    return ok(made, disposition="refusal_or_default")


@handles("suggested-context-policy", "masked-context-policy",
         "duplicate-hint-policy")
def h_hint_policy(case):
    """Adjudicated D3/D4 (addendum): offering is not rewrite authority —
    suggestions and conflict-masked canonicals may be OFFERED as context,
    duplicate canonicals keep separate slots; none of them may rewrite
    text or appear as a cleanup alias pair."""
    ents = [mk_entry(e) for e in case["synthetic_vocabulary_entries"]]
    snap = V.VocabularySnapshot(ents, scope_of(case))
    hs = V.RelevantVocabularySelector(100).select(snap)
    members = [t.entry_id for t in hs.terms]
    pairs = [(a, t.entry_id) for a, t in snap.match_items()]
    view = result_view(norm_direct("clod suggestedname", ents,
                                   scope_of(case)))
    fam = case["family_id"]
    if fam == "suggested-context-policy":
        check(members == case["expected_hint_membership"], members)
        check(not pairs, f"suggestion must not become a rewrite pair {pairs}")
        check(view["text"] == "clod suggestedname", view["text"])
    elif fam == "masked-context-policy":
        check(sorted(members) == ["E-CL", "E-X"], members)
        check(not any(a == "clod" for a, _ in pairs), pairs)
        check(view["text"].startswith("clod"), view["text"])
    else:
        check(members == ["E-W", "E-G"], members)
    return ok({"hint_members": members, "rewrite_pairs": pairs,
               "text": view["text"]},
              disposition="adjudicated_policy:D3/D4")


# ---- stateful ---------------------------------------------------------------

def _E(eid="E-CL", canonical="Claude", aliases=(("clod", True),), **kw):
    d = {"entry_id": eid, "canonical": canonical,
         "aliases": [{"alias": a, "approved": f} for a, f in aliases]}
    d.update(kw)
    return d


def _norm(snap, text="clod"):
    return result_view(normalize(text, NormalizationPolicy(),
                                 ContextSnapshot(vocabulary=snap)))


@handles("midflight-approval", "midflight-disable", "delete-active",
         "conflict-delete")
def h_midflight(case):
    fam = case["family_id"]
    with tempfile.TemporaryDirectory() as td:
        st, vs, _ = new_store(td)
        if fam == "midflight-approval":
            store_add(vs, _E(approved=False))
            a = vs.snapshot(None)
            vs.approve_entry("E-CL")
            ra, rb = _norm(a), _norm(vs.snapshot(None))
            check(ra["text"] == "clod", f"A rewrote {ra}")
            check(rb["text"] == "Claude" and vocab_ids(rb) == ["E-CL"], rb)
        elif fam == "midflight-disable":
            store_add(vs, _E(approved=True))
            a = vs.snapshot(None)
            vs.set_enabled("E-CL", False)
            ra, rb = _norm(a), _norm(vs.snapshot(None))
            check(ra["text"] == "Claude" and vocab_ids(ra) == ["E-CL"], ra)
            check(rb["text"] == "clod", rb)
        elif fam == "delete-active":
            store_add(vs, _E(approved=True))
            a = vs.snapshot(None)
            vs.delete_entry("E-CL")
            ra = _norm(a)
            n = vs.record_hits(vocab_ids(ra))
            rb = _norm(vs.snapshot(None))
            check(ra["text"] == "Claude" and vocab_ids(ra) == ["E-CL"], ra)
            check(n == 0, f"hit on a deleted row updated {n} rows")
            check(rb["text"] == "clod", rb)
            check(not raw_sql(st.db_path, "SELECT 1 FROM vocabulary_entries"
                              " WHERE entry_id='E-CL'"), "row resurrected")
        else:
            store_add(vs, _E(approved=True))
            store_add(vs, _E("E-X", "Cloud", approved=True))
            a = vs.snapshot(None)
            vs.delete_entry("E-X")
            ra, rb = _norm(a), _norm(vs.snapshot(None))
            check(ra["text"] == "clod", f"A must stay masked {ra}")
            check(rb["text"] == "Claude" and vocab_ids(rb) == ["E-CL"], rb)
        st.close()
    return ok({"A": ra, "B": rb}, disposition="stateful")


@handles("sequential-workspaces")
def h_seq_workspaces(case):
    with tempfile.TemporaryDirectory() as td:
        r = AppRun(td, "clod")
        try:
            v = r.d._vocab
            v.add_entry("GlobalName", ["clod"], approved=True)
            v.add_entry("XName", ["clod"], scope_kind="workspace",
                        scope_value="X", approved=True)
            v.add_entry("YName", ["clod"], scope_kind="workspace",
                        scope_value="Y", approved=True)
            got = [r.job("app.one", workspace="X")["text"],
                   r.job("app.one", workspace="Y")["text"],
                   r.job("app.one")["text"],
                   r.job("app.one", workspace="X")["text"]]
        finally:
            r.close()
    check(got == ["XName", "YName", "GlobalName", "XName"], got)
    return ok(got, disposition="portable_orchestration_shim")


@handles("sequential-profiles")
def h_seq_profiles(case):
    with tempfile.TemporaryDirectory() as td:
        r = AppRun(td, "clod")
        try:
            v = r.d._vocab
            v.add_entry("GlobalName", ["clod"], approved=True)
            v.add_entry("ProfileA", ["clod"], scope_kind="profile",
                        scope_value="pa", approved=True)
            v.add_entry("ProfileB", ["clod"], scope_kind="profile",
                        scope_value="pb", approved=True)
            styles = r.d._styles
            ra = styles.add_rule(name="a", scope_kind="app",
                                 scope_value="app.pa", profile_name="pa")
            styles.add_rule(name="b", scope_kind="app",
                            scope_value="app.pb", profile_name="pb")
            styles.add_rule(name="inherit", scope_kind="app",
                            scope_value="app.inherit")
            got = {"A": r.job("app.pa")["text"],
                   "B": r.job("app.pb")["text"],
                   "inherit_default": r.job("app.inherit")["text"],
                   "A_again": r.job("app.pa")["text"]}
            styles.delete_rule(ra)
            got["A_after_rule_deleted"] = r.job("app.pa")["text"]
        finally:
            r.close()
    check(got == {"A": "ProfileA", "B": "ProfileB",
                  "inherit_default": "GlobalName", "A_again": "ProfileA",
                  "A_after_rule_deleted": "GlobalName"}, got)
    return ok(got, disposition="portable_orchestration_shim")


FIVE = [("E-G", "GlobalName", "global", None),
        ("E-A", "AppName", "app", "test.app"),
        ("E-S", "SiteName", "site", "https://example.test"),
        ("E-P", "ProfileName", "profile", "coding"),
        ("E-W", "WorkspaceName", "workspace", "project-x")]


@handles("scope-removal")
def h_scope_removal(case):
    ents = [ent(i, c, ["clod"], scope_kind=k, scope_value=v)
            for i, c, k, v in FIVE] + [ent("E-U", "Unrelated", ["unrel"])]
    ctxs = [dict(app_bundle="test.app", site_origin="https://example.test",
                 profile="coding", workspace="project-x")]
    for drop in ("workspace", "profile", "site_origin", "app_bundle"):
        c = dict(ctxs[-1])
        c.pop(drop)
        ctxs.append(c)
    got, unrelated = [], []
    for c in ctxs:
        snap = V.VocabularySnapshot(ents, V.ScopeContext(**c))
        got.append(vocab_ids(_norm(snap)))
        unrelated.append(_norm(snap, "unrel")["text"])
    check(got == [["E-W"], ["E-P"], ["E-S"], ["E-A"], ["E-G"]], got)
    check(set(unrelated) == {"Unrelated"}, unrelated)
    return ok({"winners": got, "unrelated": unrelated},
              disposition="stateful")


def _mutation_attempts(snap, hs=None):
    tries = {
        "rebind_scope_ctx": lambda: setattr(
            snap, "scope_ctx", V.ScopeContext(workspace="x")),
        "rebind_match_index": lambda: setattr(snap, "match_index", {}),
        "rebind_entries": lambda: setattr(snap, "entries", ()),
        "rebind_revision": lambda: setattr(snap, "revision", "m05:x"),
        "rebind_skills": lambda: setattr(snap, "skills", {}),
        "match_index_item": lambda: snap.match_index.__setitem__("x", None),
        "skills_item": lambda: snap.skills.__setitem__("x", "y"),
        "conflict_item": lambda: snap.conflicts[0].__setitem__("alias", "z"),
        "conflict_entries": lambda: snap.conflicts[0]["entries"].append("z"),
        "entry_alias_rebind": lambda: object.__setattr__(
            snap.entries[0].aliases[0], "__bogus__", 1)
        if False else setattr(snap.entries[0], "canonical", "X"),
    }
    out = {}
    for label, fn in tries.items():
        try:
            fn()
            out[label] = "accepted"
        except Exception as e:
            out[label] = f"rejected:{type(e).__name__}"
    return out


@handles("snapshot-deep-mutation")
def h_snapshot_mutation(case):
    caller = [V.Alias("clod")]
    e_cl = V.VocabularyEntry(entry_id="E-CL", canonical="Claude",
                             aliases=caller, approved=True,
                             verification="explicit")
    ents = [e_cl, ent("E-X1", "Cloud", ["klaud"]),
            ent("E-X2", "Clown", ["klaud"]),
            ent("E-SK", "code-review", ["code review"], kind="skill")]
    snap = V.VocabularySnapshot(ents)
    rev = snap.revision
    ser = json.dumps(snap.to_json(), sort_keys=True, default=str)
    behave = _norm(snap, "ask clod and klod now")["text"]
    check(snap.conflicts, "the case needs a conflict")
    attempts = _mutation_attempts(snap)
    caller.append(V.Alias("klod"))
    rescoped = V.VocabularySnapshot(snap.entries,
                                    V.ScopeContext(workspace="x"))
    after = {
        "revision": snap.revision,
        "serialization_same": json.dumps(snap.to_json(), sort_keys=True,
                                         default=str) == ser,
        "behavior": _norm(snap, "ask clod and klod now")["text"],
        "rescoped_behavior": _norm(rescoped, "ask clod and klod now")[
            "text"],
        "skills": dict(snap.skills),
    }
    accepted = [k for k, v in attempts.items() if v == "accepted"]
    check(not accepted, f"accepted mutations {accepted}")
    check(after["revision"] == rev and after["serialization_same"],
          "revision/serialization changed")
    check(after["behavior"] == behave == after["rescoped_behavior"]
          == "ask Claude and klod now",
          f"caller alias mutation leaked: {after}")
    check(after["skills"] == {"code review": "code-review",
                              "code-review": "code-review"},
          after["skills"])
    return ok({"attempts": attempts, **after}, disposition="stateful")


@handles("hintset-deep-mutation")
def h_hintset_mutation(case):
    ents = [ent("E-A", "Alpha"), ent("E-B", "Beta"), ent("E-C", "Gamma")]
    snap = V.VocabularySnapshot(ents, V.ScopeContext(workspace="w"))
    hs = V.RelevantVocabularySelector(2).select(
        snap, now_utc="2026-09-25T00:00:00Z")
    hid = hs.hint_set_id
    b0 = json.dumps(hs.to_json(), sort_keys=True)
    tries = {
        "scope_item": lambda: hs.scope.__setitem__("workspace", "y"),
        "omitted_item": lambda: hs.omitted[0].__setitem__("reason", "x"),
        "to_json_scope": lambda: hs.to_json()["scope"].__setitem__(
            "workspace", "z"),
        "to_json_terms": lambda: hs.to_json()["terms"][0].__setitem__(
            "canonical", "z"),
        "to_json_omitted": lambda: hs.to_json()["omitted"][0].__setitem__(
            "reason", "z"),
        "term_score": lambda: setattr(hs.terms[0], "score", (9,)),
        "rebind_terms": lambda: setattr(hs, "terms", ()),
    }
    attempts = {}
    for label, fn in tries.items():
        try:
            fn()
            attempts[label] = "accepted_call"
        except Exception as e:
            attempts[label] = f"rejected:{type(e).__name__}"
    b1 = json.dumps(hs.to_json(), sort_keys=True)
    check(b1 == b0 and hs.hint_set_id == hid,
          f"frozen content changed under the same id: {attempts}")
    # Constructor-owned caller containers (direct construction).
    scope = {"workspace": "w"}
    omitted = [{"canonical": "Gamma", "entry_id": "E-C",
                "reason": BUDGET_REASON}]
    terms = list(hs.terms)
    try:
        hs2 = V.HintSet(hint_set_id=hs.hint_set_id,
                        selector_revision=hs.selector_revision,
                        vocabulary_revision=hs.vocabulary_revision,
                        scope=scope, terms=terms, omitted=omitted,
                        created_utc=hs.created_utc,
                        term_limit=hs.term_limit)
        c0 = json.dumps(hs2.to_json(), sort_keys=True)
        scope["workspace"] = "evil"
        omitted[0]["reason"] = "evil"
        terms.clear()
        direct = {"constructed": True,
                  "caller_mutation_leaked":
                      json.dumps(hs2.to_json(), sort_keys=True) != c0}
    except Exception as e:
        direct = {"constructed": False, "error": type(e).__name__}
    check(not direct.get("caller_mutation_leaked"),
          f"constructor did not own its inputs: {direct}")
    # Distinct identity-bearing state → distinct id.
    ids_ = {hs.hint_set_id}
    for other in (
            V.RelevantVocabularySelector(3).select(snap),
            V.RelevantVocabularySelector(2).select(
                V.VocabularySnapshot(ents, V.ScopeContext(workspace="v"))),
            V.RelevantVocabularySelector(2).select(
                V.VocabularySnapshot(ents[:2] + [ent("E-C", "Gamma",
                                                     priority=5)],
                                     V.ScopeContext(workspace="w")))):
        ids_.add(other.hint_set_id)
    check(len(ids_) == 4, "distinct identity-bearing state must get a"
          " distinct id")
    return ok({"attempts": attempts, "direct": direct},
              disposition="stateful")


@handles("usage-without-edit", "ranking-freshness")
def h_usage(case):
    with tempfile.TemporaryDirectory() as td:
        st, vs, _ = new_store(td)
        store_add(vs, _E("E-A", "Alpha", ()))
        store_add(vs, _E("E-B", "Beta", ()))
        srev0 = vs.revision()
        snap = vs.snapshot(None)
        sel = V.RelevantVocabularySelector(10)
        order0 = [t.entry_id for t in sel.select(snap).terms]
        for _ in range(25):
            vs.record_hits(["E-B"])
        live = {e.entry_id: e.usage_count for e in vs.entries()}
        snap_fresh = vs.snapshot(None)
        out = {"order_cached": [t.entry_id for t in sel.select(snap).terms],
               "order_fresh": [t.entry_id
                               for t in sel.select(snap_fresh).terms],
               "store_revision_unchanged": vs.revision() == srev0,
               "snapshot_revision_unchanged":
                   snap_fresh.revision == snap.revision,
               "live_usage": live, "order_before": order0}
        st.close()
    check(out["store_revision_unchanged"]
          and out["snapshot_revision_unchanged"],
          "usage must not be matching identity")
    check(out["live_usage"]["E-B"] == 25, out["live_usage"])
    check(out["order_cached"] == order0 == ["E-A", "E-B"],
          "a cached snapshot keeps its (deliberately stale) ranking")
    check(out["order_fresh"] == ["E-B", "E-A"],
          "a freshly constructed snapshot ranks by the live usage")
    return ok(out, disposition="characterization:D4_frozen_usage")


def _import(vs, td, doc, name):
    p = pathlib.Path(td) / name
    p.write_text(json.dumps(doc), encoding="utf-8")
    return vs.import_json(p)


@handles("import-twice")
def h_import_twice(case):
    doc = {"entries": [{"entry_id": "x", "canonical": "Claude",
                        "scope": ["global", None], "approved": True,
                        "enabled": True, "verification": "explicit",
                        "aliases": [{"alias": "zulu", "approved": True},
                                    {"alias": "alpha", "approved": True}]}]}
    with tempfile.TemporaryDirectory() as td:
        st, vs, _ = new_store(td)
        runs = []
        for i in range(3):
            r = _import(vs, td, doc, f"i{i}.json")
            e = vs.entries()[0]
            runs.append({"result": r, "revision": e.revision,
                         "store_revision": vs.revision(),
                         "history": len(vs.history(e.entry_id)),
                         "snapshot": vs.snapshot(None).revision})
        st.close()
    check(runs[0]["result"]["created"] == 1, runs[0])
    for r in runs[1:]:
        check(r["result"] == {"created": 0, "updated": 0, "unchanged": 1},
              f"repeat import reported {r['result']}")
        check((r["revision"], r["store_revision"], r["history"],
               r["snapshot"]) == (runs[0]["revision"],
                                  runs[0]["store_revision"],
                                  runs[0]["history"], runs[0]["snapshot"]),
              f"revision/history churn: {runs}")
    return ok(runs, disposition="stateful")


@handles("dismiss-reseed")
def h_dismiss(case):
    with tempfile.TemporaryDirectory() as td:
        st, vs, _ = new_store(td)
        vs.seed_suggested_coding_terms()
        claude = next(e for e in vs.entries() if e.canonical == "Claude")
        check(claude.scope_kind == "profile"
              and claude.scope_value == "coding" and not claude.approved,
              "seeded suggestion in its declared scope, unapproved")
        vs.set_enabled(claude.entry_id, False)
        vs.seed_suggested_coding_terms()
        st.close()
        st2 = store_mod.Store(pathlib.Path(td) / "v2.db")
        vs2 = VS.VocabularyStore(st2)
        vs2.seed_suggested_coding_terms()
        dismissed = [(e.entry_id, e.enabled) for e in vs2.entries()
                     if e.canonical == "Claude"]
        st2.close()
    with tempfile.TemporaryDirectory() as td:
        st, vs, _ = new_store(td)
        vs.seed_suggested_coding_terms()
        claude = next(e for e in vs.entries() if e.canonical == "Claude")
        vs.delete_entry(claude.entry_id)
        vs.seed_suggested_coding_terms()
        after_delete = [(e.entry_id != claude.entry_id, e.enabled)
                        for e in vs.entries() if e.canonical == "Claude"]
        st.close()
    check(dismissed == [(claude.entry_id, False)] or (
        len(dismissed) == 1 and dismissed[0][1] is False),
        f"disabled suggestion must stay dismissed: {dismissed}")
    check(after_delete == [(True, True)],
          "declared policy: a DELETED suggestion is re-seeded (delete is"
          f" not dismiss): {after_delete}")
    return ok({"dismissed": dismissed, "after_delete": after_delete},
              disposition="characterization:declared_policy")


def _collector(td):
    from localflow.v2 import training
    st = store_mod.Store(pathlib.Path(td) / "v2.db")
    events = []

    def rec(name, **kw):
        events.append({"event": name, **kw})
    consent = training.ConsentManager(st, rec)
    col = training.EvidenceCollector(st, rec, consent,
                                     lambda: {"live": "x"})
    consent.set("enabled")
    return st, col, events


def _start(col):
    from localflow.v2 import ids
    job = ids.new_id("job")
    return job, col.job_started(job, ids.new_id("fam"),
                                captured_at_utc=ids.now_utc_iso(),
                                timezone=None, utc_offset_minutes=None)


@handles("hint-evidence-failure")
def h_hint_failure(case):
    from localflow.v2 import capabilities
    out = {}
    for fail_at in ("write", "lease"):
        with tempfile.TemporaryDirectory() as td:
            st, col, events = _collector(td)
            job, ctx = _start(col)
            snap = V.VocabularySnapshot([ent("E-CL", "AUDIT_CANARY_CANON",
                                             ["audit canary alias"])])
            hs = V.RelevantVocabularySelector(10).select(snap)
            real_w, real_l = st.write_text_artifact, st.grant_lease

            def w(**kw):
                if kw.get("role") == "hint_set" and fail_at == "write":
                    raise OSError("synthetic write failure")
                return real_w(**kw)

            def lease(aid, holder, days=None):
                row = st.artifact(aid) if hasattr(st, "artifact") else None
                if (row or {}).get("role") == "hint_set" \
                        and fail_at == "lease":
                    raise OSError("synthetic lease failure")
                return real_l(aid, holder, days=days)
            st.write_text_artifact, st.grant_lease = w, lease
            col.on_hint_set(ctx, hs, capabilities.hint_disposition(None, hs))
            st.write_text_artifact, st.grant_lease = real_w, real_l
            col.on_asr_result(ctx, "audit canary alias", model_id="m",
                              model_revision=None, stage_duration_ms=0.0)
            col.on_cleanup_result(ctx, "audit canary alias")
            ex = col.finalize(ctx)
            env = st.latest_revision(ex)
            cb = env.get("context") or {}
            refs = [aid for aid in ((cb.get("artifact_ids") or {}).values())
                    if aid]
            valid_refs = all(st.artifact(a) is not None for a in refs)
            out[fail_at] = {
                "context_block": cb,
                "missing_reasons": env.get("missing_reasons"),
                "refs_valid": valid_refs,
                "events": [(e["event"], e.get("outcome"), e.get("detail"))
                           for e in events],
                "event_blob_canary_free": not any(
                    c in json.dumps(events, default=str)
                    for c in ("AUDIT_CANARY", "audit canary")),
                "dictation_evidence_present": env.get("recognition")
                is not None}
            st.close()
    for fail_at, o in out.items():
        cb = o["context_block"]
        check(cb, f"{fail_at}: the known hint set vanished from the"
              " envelope")
        check(cb.get("hint_set_id") and cb.get("offered_terms") == 1,
              f"{fail_at}: safe id/count metadata lost: {cb}")
        check("retention_write_failed" in json.dumps(cb)
              or o["missing_reasons"].get("hint_set_payload")
              == "retention_write_failed",
              f"{fail_at}: precise retention failure reason missing")
        check("hint_set" not in (cb.get("artifact_ids") or {}),
              f"{fail_at}: unretained artifact referenced")
        check(o["refs_valid"] and o["event_blob_canary_free"]
              and o["dictation_evidence_present"], o)
    return ok(out, disposition="fault_injection")


@handles("cross-job-refresh-failure")
def h_cross_job(case):
    with tempfile.TemporaryDirectory() as td:
        r = AppRun(td, "ask clod now")
        try:
            d = r.d
            d._vocab.add_entry("Claude", ["clod"], scope_kind="app",
                               scope_value="app.A", approved=True)
            d._vocab.add_entry("code-review", ["code review"],
                               kind="skill", scope_kind="app",
                               scope_value="app.A", approved=True)
            a = r.job("app.A")

            def boom():
                raise RuntimeError("injected")
            real = d._vocab.revision
            d._vocab.revision = boom
            b = r.job("app.B")
            b_policy_skills = dict(b["job"]["norm_policy"].registered_skills) \
                if b["job"].get("norm_policy") is not None else {}
            b_hint = b["job"].get("hint_set")
            d._vocab.revision = real
        finally:
            r.close()
    check(a["text"] == "ask Claude now", f"control A {a['text']!r}")
    check(b["finished"] and b["text"] == "ask clod now",
          f"B applied A's app-only rule: {b['text']!r}")
    check(not any(p[0] == "clod" for p in b["pairs"]),
          f"B cleanup got A's pair: {b['pairs']}")
    check("code review" not in b_policy_skills,
          f"B policy carries A's app skill: {b_policy_skills}")
    check(b_hint is None or all(t.canonical != "Claude"
                                for t in b_hint.terms),
          "B hint set offers A's app-only term")
    return ok({"A": a["text"], "B": b["text"], "B_pairs": b["pairs"],
               "B_skills": sorted(b_policy_skills)},
              disposition="portable_orchestration_shim")


@handles("selector-failure-scope-upgrade")
def h_selector_failure(case):
    with tempfile.TemporaryDirectory() as td:
        r = AppRun(td, "ask clod now")
        try:
            d = r.d
            d._vocab.add_entry("GlobalName", ["clod"], approved=True)
            d._vocab.add_entry("WorkspaceName", ["clod"],
                               scope_kind="workspace", scope_value="wsx",
                               approved=True)

            def boom(*a, **k):
                raise RuntimeError("injected selector failure")
            d._hint_selector.select = boom
            j = r.job("app.C", workspace="wsx")
        finally:
            r.close()
    check(j["finished"] and j["text"] == "ask WorkspaceName now",
          f"optional hint failure blocked the scope rebuild: {j['text']!r}")
    check(("clod", "WorkspaceName") in j["pairs"], j["pairs"])
    return ok({"text": j["text"], "pairs": j["pairs"]},
              disposition="portable_orchestration_shim")


def _race_scope(order):
    with tempfile.TemporaryDirectory() as td:
        st, vs, _ = new_store(td)
        store_add(vs, _E(approved=True))
        ts = Turnstile(st, order)
        res = run_threads(ts, {
            "A": lambda: vs.update_entry("E-CL", scope_kind="workspace",
                                         scope_value="X").revision,
            "B": lambda: vs.update_entry("E-CL", scope_value=None)
            .revision})
        ts.restore()
        st.sync()
        row = raw_sql(st.db_path, "SELECT scope_kind, scope_value, revision"
                      " FROM vocabulary_entries WHERE entry_id='E-CL'")
        hist = raw_sql(st.db_path, "SELECT revision, action FROM"
                       " vocabulary_history WHERE entry_id='E-CL' ORDER BY"
                       " history_id")
        try:
            vs.snapshot(None)
            snap_ok = True
        except Exception as e:
            snap_ok = type(e).__name__
        st.close()
    return {"callers": res, "row": row, "history": hist,
            "snapshot_ok": snap_ok, "timeouts": ts.timeouts}


@handles("concurrent-scope-update")
def h_concurrent_scope(case):
    out = {"AB": _race_scope(["A", "B", "A", "B"]),
           "BA": _race_scope(["B", "A", "B", "A"])}
    for k, o in out.items():
        kind, value, rev = o["row"][0]
        check(not (kind != "global" and value is None),
              f"{k}: invalid committed scope {o['row']}")
        revs = [r for r, _ in o["history"]]
        check(revs == sorted(set(revs)) and revs[-1] == rev,
              f"{k}: duplicate/misordered revisions {o['history']}")
        check(o["snapshot_ok"] is True, f"{k}: snapshot {o['snapshot_ok']}")
        check(o["timeouts"] == 0, f"{k}: turnstile liveness timeout")
    return ok(out, disposition="barrier_both_orders")


def _race_update_delete(order):
    with tempfile.TemporaryDirectory() as td:
        st, vs, _ = new_store(td)
        store_add(vs, _E(approved=True))
        ts = Turnstile(st, order)
        res = run_threads(ts, {
            "U": lambda: vs.update_entry(
                "E-CL", aliases=["clod", "klod"]).revision,
            "D": lambda: vs.delete_entry("E-CL")})
        ts.restore()
        st.sync()
        out = {"callers": res,
               "entry": raw_sql(st.db_path, "SELECT count(*) FROM"
                                " vocabulary_entries"),
               "aliases": raw_sql(st.db_path, "SELECT entry_id, alias FROM"
                                  " vocabulary_aliases"),
               "history": raw_sql(st.db_path, "SELECT revision, action"
                                  " FROM vocabulary_history ORDER BY"
                                  " history_id"),
               "timeouts": ts.timeouts}
        st.close()
    return out


@handles("update-delete-race")
def h_update_delete(case):
    out = {"read_delete_write": _race_update_delete(["U", "D", "D", "U"]),
           "delete_first": _race_update_delete(["D", "D", "U", "U"])}
    for k, o in out.items():
        check(o["entry"][0][0] == 0, f"{k}: entry survived delete {o}")
        check(not o["aliases"], f"{k}: orphan aliases {o['aliases']}")
        acts = [a for _, a in o["history"]]
        check("deleted" in acts and acts[-1] == "deleted",
              f"{k}: history continued after delete {o['history']}")
        revs = [r for r, _ in o["history"]]
        check(revs == sorted(set(revs)), f"{k}: revisions {revs}")
        u = o["callers"]["U"]
        check(u[0] == "ok" or u[1] == "KeyError",
              f"{k}: update outcome must be success-before-delete or an"
              f" explicit missing outcome, got {u}")
    return ok(out, disposition="barrier_both_orders")


class Field:
    def __init__(self, v=""):
        self.v = v

    def stringValue(self):
        return self.v

    def setStringValue_(self, v):
        self.v = v

    def titleOfSelectedItem(self):
        return self.v or "global"


def _panel(vs):
    _helpers()
    from localflow.v2 import dictionary_panel as dp
    ctl = dp.DictionaryPanelController.alloc().initWithVocabularyStore_(vs)
    for name in ("search", "phrase", "sandbox", "listing", "canonical",
                 "alias", "scope_value"):
        setattr(ctl, name, Field())
    ctl.scope_popup = Field("global")
    ctl.refresh()
    return ctl


@handles("panel-filter-selection")
def h_panel(case):
    out = {}
    for variant in ("clear_filter", "insert_before", "delete_selected"):
        with tempfile.TemporaryDirectory() as td:
            st, vs, _ = new_store(td)
            a = vs.add_entry("Alpha", ["alfa"], approved=False)
            b = vs.add_entry("Beta", ["beeta"], approved=False)
            ctl = _panel(vs)
            ctl.search.v = "beta"
            ctl.searchChanged_(None)
            ctl.phrase.v = "1"
            ctl.runSandbox_(None)
            if variant == "clear_filter":
                ctl.search.v = ""
                ctl.searchChanged_(None)
            elif variant == "insert_before":
                ctl.search.v = ""
                vs.add_entry("Aardvark", ["ardvark"], approved=False)
                ctl.refresh()
            else:
                vs.delete_entry(b)
                ctl.search.v = ""
                ctl.refresh()
            ctl.approveEntry_(None)
            out[variant] = {
                "approved": sorted(e.canonical for e in vs.entries()
                                   if e.approved),
                "message": ctl.sandbox.v}
            st.close()
    for variant, o in out.items():
        check("Alpha" not in o["approved"]
              and "Aardvark" not in o["approved"],
              f"{variant}: approval retargeted: {o}")
        if variant != "delete_selected":
            check(o["approved"] in (["Beta"], []),
                  f"{variant}: {o}")
        else:
            check(o["approved"] == [], f"{variant}: {o}")
    return ok(out, disposition="mocked_interface_controller")


@handles("alias-language-roundtrip")
def h_lang(case):
    with tempfile.TemporaryDirectory() as td:
        st, vs, _ = new_store(td)
        eid = vs.add_entry("Claude", ["clod"], language="en", approved=True)
        vs.update_entry(eid, language="es")
        e = vs.entry(eid)
        eff = [(a.alias, a.language or e.language) for a in e.aliases]
        st.close()
    with tempfile.TemporaryDirectory() as td:
        st, vs, _ = new_store(td)
        _import(vs, td, {"entries": [{
            "entry_id": "x", "canonical": "Claude", "language": "en",
            "scope": ["global", None], "approved": True, "enabled": True,
            "verification": "explicit",
            "aliases": [{"alias": "clod", "approved": True,
                         "language": "es"},
                        {"alias": "klod", "approved": True}]}]}, "l.json")
        exp = vs.export_json()["entries"][0]
        again = _import(vs, td, {"entries": [exp]}, "l2.json")
        st.close()
    langs = {a["alias"]: (a["language"] or exp["language"])
             for a in exp["aliases"]}
    check(eff == [("clod", "es")],
          f"inherited alias language drifted after a language-only"
          f" update: {eff}")
    check(langs == {"clod": "es", "klod": "en"},
          f"explicit alias override lost on import/export: {langs}")
    check(again == {"created": 0, "updated": 0, "unchanged": 1},
          f"export→reimport churn: {again}")
    return ok({"effective_after_update": eff, "exported": langs},
              disposition="stateful")


@handles("predecode-no-postanswer-leak")
def h_predecode(case):
    from localflow.v2 import capabilities
    with tempfile.TemporaryDirectory() as td:
        st, col, _ = _collector(td)
        vs = VS.VocabularyStore(st)
        vs.add_entry("Claude", ["clod"], approved=True)
        s1 = vs.snapshot(None)
        h1 = V.RelevantVocabularySelector(10).select(s1)
        b1 = json.dumps(h1.to_json(), sort_keys=True)
        job, ctx = _start(col)
        col.on_hint_set(ctx, h1, capabilities.hint_disposition(None, h1))
        col.on_asr_result(ctx, "ask clod now", model_id="m",
                          model_revision=None, stage_duration_ms=0.0)
        vs.add_entry("Qwen", ["q wen"], approved=True)
        vs.approve_entry(vs.entries()[0].entry_id)
        h2 = V.RelevantVocabularySelector(10).select(vs.snapshot(None))
        col.on_cleanup_result(ctx, "ask Claude now")
        ex = col.finalize(ctx)
        env = st.latest_revision(ex)
        aid = env["context"]["artifact_ids"]["hint_set"]
        stored = json.loads(st.artifact_payload(aid))
        st.close()
    check(env["context"]["hint_set_id"] == h1.hint_set_id
          != h2.hint_set_id, "envelope must keep H1")
    check(json.dumps(stored, sort_keys=True) == b1,
          "retained pre-decode bytes changed")
    check(env["context"]["disposition"]["accepted_terms"] == 0,
          "post-ASR repair relabeled as accepted hint")
    return ok({"h1": h1.hint_set_id, "h2": h2.hint_set_id},
              disposition="stateful")


@handles("historical-rule-reconstruction")
def h_reconstruct(case):
    """Clean reader over every retained artifact of the job: the applied
    rule's exact state is either reconstructable (keyed by rule id) or
    explicitly declared unsupported in the evidence — never inferred
    from a hash."""
    from localflow.v2 import capabilities
    with tempfile.TemporaryDirectory() as td:
        st, col, _ = _collector(td)
        vs = VS.VocabularyStore(st)
        eid = vs.add_entry("Zeta", ["zeeta", ("zed", False)],
                           scope_kind="workspace", scope_value="W1",
                           approved=True)
        vs.update_entry(eid, priority=2)
        for i in range(3):
            vs.add_entry(f"Pin{i}", [], pinned=True, approved=True)
        snap = vs.snapshot(V.ScopeContext(workspace="W1"))
        hs = V.RelevantVocabularySelector(1).select(snap)
        check(all(t.entry_id != eid for t in hs.terms),
              "the rule must be omitted from the budgeted HintSet")
        job, ctx = _start(col)
        col.on_hint_set(ctx, hs, capabilities.hint_disposition(None, hs))
        col.on_asr_result(ctx, "use zeeta", model_id="m",
                          model_revision=None, stage_duration_ms=0.0)
        pol = NormalizationPolicy()
        cctx = ContextSnapshot(vocabulary=snap)
        res = normalize("use zeeta", pol, cctx)
        col.on_normalization_result(ctx, res, source_text="use zeeta",
                                    policy=pol, context=cctx)
        col.on_cleanup_result(ctx, res.text)
        env = st.latest_revision(col.finalize(ctx))
        vs.update_entry(eid, aliases=[("zeeta", False)])
        vs.delete_entry(eid)
        st.sync()
        rows = raw_sql(st.db_path, "SELECT artifact_id FROM artifacts"
                       " WHERE job_id=? AND purged=0", (job,))
        docs = []
        for (aid,) in rows:
            try:
                docs.append(json.loads(st.artifact_payload(aid)))
            except Exception:
                pass
        st.close()

    def walk(o):
        if isinstance(o, dict):
            yield o
            for v in o.values():
                yield from walk(v)
        elif isinstance(o, list):
            for v in o:
                yield from walk(v)
    nodes = [n for d in docs + [env] for n in walk(d)]
    rule = next((n for n in nodes if n.get("entry_id") == eid
                 and "aliases" in n and "scope" in n), None)
    declared = "unsupported" in json.dumps(
        (env.get("normalization") or {}).get("vocabulary") or {})
    if rule is None:
        check(declared, "neither reconstructable nor declared unsupported")
        return ok({"reconstructed": None, "declared_unsupported": True},
                  disposition="explicit_unsupported")
    got = {"scope": rule["scope"], "approved": rule.get("approved"),
           "verification": rule.get("verification"),
           "revision": rule.get("revision"),
           "aliases": sorted((a["alias"], a["approved"])
                             for a in rule["aliases"])}
    check(got == {"scope": ["workspace", "W1"], "approved": True,
                  "verification": "explicit", "revision": 2,
                  "aliases": [("zed", False), ("zeeta", True)]},
          f"reconstructed state differs from the applied rule: {got}")
    check((env.get("normalization") or {}).get("vocabulary", {}).get(
        "revision") == snap.revision, "snapshot revision missing")
    return ok(got, disposition="reconstructed_from_retained_artifacts")


@handles("populated-torn-tables")
def h_torn(case):
    out = {}
    with tempfile.TemporaryDirectory() as td:
        seed = pathlib.Path(td) / "seed.db"
        st = store_mod.Store(seed)
        vs = VS.VocabularyStore(st)
        e1 = vs.add_entry("Claude", ["clod", ("klod", False)], approved=True)
        vs.add_entry("Cloud", ["clod"], approved=True)
        vs.update_entry(e1, priority=3)
        before = [(e.entry_id, e.canonical, e.revision, e.priority,
                   [(a.alias, a.approved) for a in e.aliases])
                  for e in vs.entries()]
        st.close()
        for label, sqls in (
                ("drop_aliases", ["DROP TABLE vocabulary_aliases"]),
                ("drop_history", ["DROP TABLE vocabulary_history"]),
                ("drop_entries", ["DROP TABLE vocabulary_entries"]),
                ("drop_unique_index",
                 ["DROP INDEX idx_vocabulary_canonical_scope"]),
                ("drop_meta", ["DROP TABLE vocabulary_meta"])):
            copy = pathlib.Path(td) / f"{label}.db"
            copy.write_bytes(seed.read_bytes())
            con = sqlite3.connect(copy)
            for sql in sqls:
                con.execute(sql)
            con.commit()
            con.close()
            events = []
            st2 = store_mod.Store(copy, backup_dir=pathlib.Path(td) / "bk",
                                  emit=lambda n, **kw: events.append(
                                      (n, kw.get("reason_code"))))
            vs2 = VS.VocabularyStore(st2)
            try:
                check_fn = getattr(vs2, "integrity_report", None)
                report = check_fn() if check_fn else None
            except Exception as ex:
                report = {"error": type(ex).__name__}
            after = [(e.entry_id, e.canonical, e.revision, e.priority,
                      [(a.alias, a.approved) for a in e.aliases])
                     for e in vs2.entries()]
            out[label] = {"events": events, "report": report,
                          "after": after}
            st2.close()
    survivors_exact = {
        "drop_history": True, "drop_unique_index": True, "drop_meta": True}
    for label, o in out.items():
        if label in survivors_exact:
            check(o["after"] == before, f"{label}: surviving data changed")
        if label == "drop_aliases":
            check([x[:4] for x in o["after"]] == [x[:4] for x in before],
                  "entries must survive alias-table loss")
            check(o["report"] and o["report"].get("entries_missing_aliases"),
                  "alias loss must be reported, never silent")
        if label == "drop_entries":
            check(o["report"] and (o["report"].get("vanished_entries")
                                   or o["report"].get("error")),
                  "a lost entries table must not read as a healthy empty"
                  " dictionary")
    return ok(out, disposition="characterization+integrity_signal")


@handles("concurrent-duplicate-privacy")
def h_dup_privacy(case):
    out = {}
    for order in (["A", "B", "A", "B"], ["B", "A", "B", "A"]):
        with tempfile.TemporaryDirectory() as td:
            st, vs, events = new_store(td)
            ts = Turnstile(st, order)
            res = run_threads(ts, {
                n: (lambda: vs.add_entry(
                    "AUDIT_CANARY_CANON", ["audit canary alias"],
                    scope_kind="workspace",
                    scope_value="AUDIT_CANARY_SCOPE", approved=True))
                for n in ("A", "B")})
            ts.restore()
            st.sync()
            n_rows = len(vs.entries())
            blob = json.dumps(events, default=str) + json.dumps(
                list(st.last_errors)) + json.dumps(res, default=str)
            out["".join(order[:2])] = {
                "callers": {k: v[:2] for k, v in res.items()},
                "rows": n_rows, "events": [e["event"] for e in events],
                "canary_free": not any(c in blob for c in (
                    "AUDIT_CANARY", "audit canary"))}
            st.close()
    for k, o in out.items():
        check(o["rows"] == 1, f"{k}: {o['rows']} entries remain")
        check(sorted(v[0] for v in o["callers"].values())
              == ["error", "ok"], f"{k}: {o['callers']}")
        check(o["canary_free"], f"{k}: canary in events/errors")
    return ok(out, disposition="barrier_both_orders")


@handles("lease-delete-barrier")
def h_lease_delete(case):
    from localflow.v2 import capabilities
    with tempfile.TemporaryDirectory() as td:
        st, col, events = _collector(td)
        job, ctx = _start(col)
        hs = V.RelevantVocabularySelector(10).select(
            V.VocabularySnapshot([ent("E-CL", "Claude", ["clod"])]))
        entered, release = threading.Event(), threading.Event()
        real_w = st.write_text_artifact

        def w(**kw):
            if kw.get("role") == "hint_set":
                entered.set()
                release.wait(30)
            return real_w(**kw)
        st.write_text_artifact = w
        t = threading.Thread(target=col.on_hint_set, args=(
            ctx, hs, capabilities.hint_disposition(None, hs)))
        t.start()
        check(entered.wait(30), "retention never reached publication")
        deleted = st.delete_everywhere("job", job)
        release.set()
        t.join(30)
        st.write_text_artifact = real_w
        try:
            ex = col.finalize(ctx)
        except Exception as e:
            ex = f"refused:{type(e).__name__}"
        st.sync()
        live = raw_sql(st.db_path, "SELECT artifact_id, role FROM artifacts"
                       " WHERE job_id=? AND purged=0", (job,))
        examples = raw_sql(st.db_path, "SELECT state FROM"
                           " training_examples WHERE job_id=?", (job,))
        st.close()
    check(not live, f"deleted job gained a live retained payload: {live}")
    check(all(s[0] == "deleted" for s in examples) or not examples,
          f"deleted evidence resurrected: {examples}")
    return ok({"deleted": str(deleted)[:120], "finalize": str(ex)[:80],
               "live_artifacts": live, "examples": examples},
              disposition="barrier")


@handles("approval-edit-race")
def h_approval_race(case):
    out = {}
    for label, order in (("approve_read_then_edit",
                          ["P", "L", "L", "L", "P", "P"]),
                         ("edit_then_approve",
                          ["L", "L", "L", "P", "P", "P"])):
        with tempfile.TemporaryDirectory() as td:
            st, vs, _ = new_store(td)
            store_add(vs, _E(approved=False, aliases=(("clod", False),)))
            ts = Turnstile(st, order)
            res = run_threads(ts, {
                "P": lambda: vs.approve_entry("E-CL").revision,
                "L": lambda: vs.update_entry(
                    "E-CL", aliases=[("clod", False),
                                     ("klod", False)]).revision})
            ts.restore()
            st.sync()
            out[label] = {
                "callers": {k: v[:2] for k, v in res.items()},
                "aliases": raw_sql(st.db_path, "SELECT alias, approved FROM"
                                   " vocabulary_aliases ORDER BY alias"),
                "entry": raw_sql(st.db_path, "SELECT approved, revision FROM"
                                 " vocabulary_entries"),
                "history": raw_sql(st.db_path, "SELECT revision, action FROM"
                                   " vocabulary_history ORDER BY history_id")}
            st.close()
    for label, o in out.items():
        check(any(a == "klod" for a, _ in o["aliases"]),
              f"{label}: newer alias silently lost {o['aliases']}")
        revs = [r for r, _ in o["history"]]
        check(revs == sorted(set(revs)), f"{label}: revisions {revs}")
        if o["callers"]["P"][0] == "ok" and o["entry"][0][0] == 1:
            last_p = [i for i, (_, a) in enumerate(o["history"])]
            # An approval that committed after the alias edit approves
            # the CURRENT alias set (no stale whole-list approval).
            if label == "edit_then_approve":
                check(all(f == 1 for _, f in o["aliases"]),
                      f"{label}: approval applied to a stale list"
                      f" {o['aliases']}")
    return ok(out, disposition="barrier_both_orders")


@handles("scope-upgrade-edit-barrier")
def h_upgrade_edit(case):
    with tempfile.TemporaryDirectory() as td:
        r = AppRun(td, "ask clod now")
        try:
            v = r.d._vocab
            v.add_entry("GlobalName", ["clod"], approved=True)
            wid = v.add_entry("WorkspaceName", ["clod"],
                              scope_kind="workspace", scope_value="wsx",
                              approved=True)
            fired = []

            def edit_at_finalize():
                if fired:
                    return
                fired.append(1)
                # Paused between hotkey-down capture and finalization:
                # live canonical/scope/approval edits land now.
                v.update_entry(wid, canonical="EditedName")
                v.add_entry("LateName", ["clod"], scope_kind="workspace",
                            scope_value="wsy", approved=True)
                v.set_enabled(wid, False)
            r.fc.on_finalize = edit_at_finalize
            a = r.job("app.C", workspace="wsx")
            r.fc.on_finalize = None
            b = r.job("app.C", workspace="wsx")
        finally:
            r.close()
    check(a["text"] == "ask WorkspaceName now",
          f"A must upgrade from its captured entries: {a['text']!r}")
    check(b["text"] == "ask GlobalName now",
          f"B must see the live store (workspace entry disabled):"
          f" {b['text']!r}")
    return ok({"A": a["text"], "B": b["text"]},
              disposition="portable_orchestration_shim")


@handles("retry-boundary")
def h_retry(case):
    with tempfile.TemporaryDirectory() as td:
        r = AppRun(td, "slash deploy now clod")
        try:
            d = r.d
            d._vocab.add_entry("WorkspaceName", ["clod"],
                               scope_kind="workspace", scope_value="wsx",
                               approved=True)
            d._vocab.add_entry("deploy-now", ["deploy now"], kind="skill",
                               scope_kind="workspace", scope_value="wsx",
                               approved=True)
            live = r.job("app.C", workspace="wsx")
            pol, ctx, source = d._retry_norm_state()
            retry = normalize("slash deploy now clod", pol, ctx)
            live_source = live["job"].get("norm_source") or (
                "job_snapshot" if live["job"].get("norm_policy")
                is not None else None)
        finally:
            r.close()
    check(live["text"] == "/deploy-now WorkspaceName",
          f"live job keeps its own snapshot: {live['text']!r}")
    check(live_source == "job_snapshot", live_source)
    check(source == "retry_unscoped_default"
          and retry.text == "slash deploy now clod",
          f"retry must be unscoped: {source} {retry.text!r}")
    return ok({"live": live["text"], "retry": retry.text,
               "retry_source": source}, disposition="real_helpers")


@handles("sandbox-no-side-effects")
def h_sandbox(case):
    with tempfile.TemporaryDirectory() as td:
        st, vs, events = new_store(td)
        e1 = vs.add_entry("Claude", ["clod"], approved=True)
        vs.add_entry("Qwen", ["q wen"], approved=False)
        vs.add_entry("WsName", ["ws term"], scope_kind="workspace",
                     scope_value="X", approved=False)

        def state():
            return (vs.revision(),
                    [(e.entry_id, e.approved, e.enabled, e.usage_count,
                      e.last_used_utc, e.revision) for e in vs.entries()],
                    raw_sql(st.db_path, "SELECT count(*) FROM artifacts"),
                    raw_sql(st.db_path, "SELECT count(*) FROM"
                            " vocabulary_history"))
        s0 = state()
        outs = []
        for text in ("ask clod now", "load q wen", "use ws term",
                     "nothing here"):
            for scope in (None, V.ScopeContext(workspace="X")):
                outs.append(V.sandbox_phrase(text, vs.snapshot(scope)))
        ctl = _panel(vs)
        ctl.phrase.v = "ask clod now"
        ctl.runSandbox_(None)
        s1 = state()
        st.close()
    check(s0 == s1, f"sandbox changed persistent state: {s0} → {s1}")
    check(outs[0]["output"] == "ask Claude now", outs[0]["output"])
    return ok({"runs": len(outs)}, disposition="stateful")


@handles("learning-approval-boundary")
def h_learning(case):
    from localflow.v2 import learning
    with tempfile.TemporaryDirectory() as td:
        st = store_mod.Store(pathlib.Path(td) / "v2.db")
        vs = VS.VocabularyStore(st)
        ls = learning.LearningService(st, vocabulary=vs)
        job, fam = st.create_job()
        raw_aid = st.write_text_artifact(
            job_id=job, stage="asr", role="raw_transcript",
            text="ship the clod code branch", retention_class="training")
        app_aid = st.write_text_artifact(
            job_id=job, stage="cleanup", role="applied_output",
            text="Ship the clod code branch", retention_class="training",
            parent_artifact_id=raw_aid)
        ex = st.upsert_example(job_id=job, family_id=fam)
        st.append_revision(ex, {
            "example_id": ex, "job_id": job, "family_id": fam,
            "artifact_ids": {"source_text": raw_aid,
                             "applied_output": app_aid},
            "outcome": {}, "annotations": [], "missing_reasons": {}})
        cand = ls.teach_correction(job, "Ship the Claude Code branch")
        cid = cand.get("candidate_id") or (cand.get("candidates") or [{}])[
            0].get("candidate_id")
        pending = [c for c in ls.candidates("pending")]
        snap0 = vs.snapshot(None)
        hs0 = V.RelevantVocabularySelector(100).select(snap0)
        text0 = _norm(snap0, "ship the clod code branch")["text"]
        res = ls.approve(cid) if cid else {"entry_id": None}
        eid = res.get("entry_id")
        e = vs.entry(eid) if eid else None
        snap1 = vs.snapshot(None)
        text1 = _norm(snap1, "ship the clod code branch")
        st.close()
    check(pending, "a pending candidate was minted")
    check(not snap0.entries and not hs0.terms
          and text0 == "ship the clod code branch",
          "a pending candidate must not act as a rule or a hint")
    check(e is not None and e.approved and e.enabled
          and e.scope_kind == pending[0].get("proposed_scope_kind",
                                             e.scope_kind),
          f"approved entry exact id/scope: {e}")
    check(text1["text"] != "ship the clod code branch"
          and set(vocab_ids(text1)) == {eid},
          f"approved rule applies with its own id: {text1}")
    return ok({"entry_id": eid, "scope": [e.scope_kind, e.scope_value],
               "applied": text1["text"]},
              disposition="m14_interface")


# ---- single-field mutation --------------------------------------------------

# Independent expectation table: which observable each field must move.
# (behavior = matching of the probe phrases; revision = snapshot
# identity; every public edit must version the entry and append history.)
MUTATIONS = {
    "canonical": ({"canonical": "Klaude"}, True),
    "alias": ({"aliases": [("klod", True)]}, True),
    "alias.approved": ({"aliases": [("clod", False)]}, True),
    "approved": ({"approved": False}, True),
    "scope_kind": ({"scope_kind": "profile"}, True),
    "scope_value": ({"scope_value": "Y"}, True),
    "kind": ({"kind": "skill"}, True),
    "language": ({"language": "es"}, False),
    "enabled": ({"enabled": False}, True),
    "priority": ({"priority": 7}, False),
    "pinned": ({"pinned": True}, False),
    "verification": ({"verification": "context_supported"}, False),
}


@handles("single-field-mutation")
def h_mutation(case):
    field = case["mutation_field"]
    change, behavior_moves = MUTATIONS[field]
    scoped = field in ("scope_kind", "scope_value")
    ctx = V.ScopeContext(workspace="X") if scoped else None
    with tempfile.TemporaryDirectory() as td:
        st, vs, _ = new_store(td)
        store_add(vs, _E(approved=True, **({"scope_kind": "workspace",
                                            "scope_value": "X"}
                                           if scoped else {})))
        e0 = vs.entry("E-CL")
        s0 = vs.snapshot(ctx)
        probe = "ask clod about claude and slash clod"
        b0 = _norm(s0, probe)
        pol0 = NormalizationPolicy(registered_skills=dict(s0.skills))
        b0s = normalize(probe, pol0, ContextSnapshot(vocabulary=s0)).text
        h0 = V.RelevantVocabularySelector(10).select(s0)
        r0 = vs.revision()
        vs.update_entry("E-CL", **change)
        e1 = vs.entry("E-CL")
        s1 = vs.snapshot(ctx)
        pol1 = NormalizationPolicy(registered_skills=dict(s1.skills))
        b1s = normalize(probe, pol1, ContextSnapshot(vocabulary=s1)).text
        h1 = V.RelevantVocabularySelector(10).select(s1)
        hist = vs.history("E-CL")
        detected = {
            "entry_revision": e1.revision == e0.revision + 1,
            "history_appended": len(hist) == 2
            and hist[-1]["revision"] == e1.revision,
            "store_revision": vs.revision() == r0 + 1,
            "snapshot_revision": s1.revision != s0.revision,
            "behavior": b1s != b0s,
            "hint_set_id": h1.hint_set_id != h0.hint_set_id,
        }
        st.close()
    survived = not any(detected.values())
    check(not survived, f"mutation of {field} survived every oracle")
    check(detected["entry_revision"] and detected["history_appended"]
          and detected["store_revision"] and detected["snapshot_revision"],
          f"{field}: versioning oracles {detected}")
    check(detected["behavior"] == behavior_moves,
          f"{field}: behavior moved={detected['behavior']}, expected"
          f" {behavior_moves} ({b0s!r} → {b1s!r})")
    return ok({"detected_by": detected, "before": b0s, "after": b1s},
              disposition="mutation_killed")


# ---- metamorphic ------------------------------------------------------------

def _two():
    return [ent("E-CL", "Claude", ["clod"]),
            ent("E-CC", "Claude Code", ["clod code"])]


@handles("metamorphic-relations")
def h_meta(case):
    rel = case["relation"]
    phrases = ["ask clod now", "use clod code today", "clod, code",
               "clod code.", "the cloud is grey"]
    base = _two()

    def outs(ents, scope=None):
        snap = V.VocabularySnapshot(ents, scope)
        return [_norm(snap, p)["text"] for p in phrases]
    detail = {}
    if rel == "scope narrowing":
        narrow = base + [ent("E-N", "Klaud", ["clod"], scope_kind="workspace",
                             scope_value="X")]
        detail = {"no_ws": (outs(base), outs(narrow)),
                  "ws_X": (outs(base, V.ScopeContext(workspace="X")),
                           outs(narrow, V.ScopeContext(workspace="X")))}
        check(detail["no_ws"][0] == detail["no_ws"][1], detail)
        check(detail["ws_X"][0] != detail["ws_X"][1]
              and "ask Klaud now" in detail["ws_X"][1], detail)
    elif rel == "scope removal":
        narrow = base + [ent("E-N", "Klaud", ["clod"], scope_kind="workspace",
                             scope_value="X")]
        check(outs(narrow) == outs(base), "removing scope restores broader")
    elif rel == "mid-flight freeze":
        with tempfile.TemporaryDirectory() as td:
            st, vs, _ = new_store(td)
            vs.add_entry("Claude", ["clod"], approved=True)
            a = vs.snapshot(None)
            ra = outs(list(a.entries))
            vs.add_entry("Claude Code", ["clod code"], approved=True)
            b = vs.snapshot(None)
            check(outs(list(a.entries)) == ra != outs(list(b.entries)),
                  "A frozen, B changed")
            st.close()
    elif rel == "approval transition":
        sug = [ent("E-CL", "Claude", ["clod"], approved=False)]
        on = [ent("E-CL", "Claude", ["clod"])]
        off = [ent("E-CL", "Claude", ["clod"], enabled=False)]
        check(outs(sug)[0] == "ask clod now" and outs(on)[0]
              == "ask Claude now" and outs(off)[0] == "ask clod now", "")
    elif rel == "canonical no-op":
        snap = V.VocabularySnapshot(base)
        for p in phrases + ["red clod code, then clod"]:
            o1 = _norm(snap, p)
            o2 = _norm(snap, o1["text"])
            check(o2["text"] == o1["text"] and not vocab_ids(o2),
                  f"second pass drifted for {p!r}: {o2}")
    elif rel == "punctuation wrapper":
        snap = V.VocabularySnapshot(base)
        for w in (",", ".", "!", "?", ":", ";"):
            o = _norm(snap, f"use clod code{w} then go")
            check(o["text"] == f"use Claude Code{w} then go", o)
            o = _norm(snap, f"use clod{w} code then go")
            check(o["text"] == f"use Claude{w} code then go"
                  and vocab_ids(o) == ["E-CL"], o)
        # The relation holds for EVERY occurrence in one dictation
        # (no occurrence may be silently skipped).
        many = "ask clod, clod; clod. clod! clod? clod: clod code, done"
        o = _norm(snap, many)
        check(o["text"] == "ask Claude, Claude; Claude. Claude! Claude?"
              " Claude: Claude Code, done"
              and vocab_ids(o) == ["E-CL"] * 6 + ["E-CC"], o)
    elif rel == "context isolation":
        g = [ent("E-U", "Unrelated", ["unrel"])]
        for ctx in (None, V.ScopeContext(workspace="A"),
                    V.ScopeContext(profile="B"),
                    V.ScopeContext(workspace="A", profile="B")):
            check(_norm(V.VocabularySnapshot(g + base, ctx),
                        "go unrel")["text"] == "go Unrelated", ctx)
    elif rel == "hint identity":
        sel = V.RelevantVocabularySelector(5)
        a = sel.select(V.VocabularySnapshot(base), now_utc="t1")
        b = sel.select(V.VocabularySnapshot(list(reversed(base))),
                       now_utc="t2")
        c = sel.select(V.VocabularySnapshot(
            [ent("E-CL", "Claude", ["clod"], priority=3), base[1]]))
        check(a.hint_set_id == b.hint_set_id and [t.entry_id for t in
                                                  a.terms]
              == [t.entry_id for t in b.terms], "equivalent → same id")
        check(c.hint_set_id != a.hint_set_id, "changed → new id")
    elif rel == "import idempotence":
        with tempfile.TemporaryDirectory() as td:
            st, vs, _ = new_store(td)
            doc = {"entries": [e.to_json() for e in base]}
            _import(vs, td, doc, "a.json")
            r1 = (vs.revision(), vs.snapshot(None).revision,
                  outs(list(vs.snapshot(None).entries)))
            again = _import(vs, td, doc, "b.json")
            r2 = (vs.revision(), vs.snapshot(None).revision,
                  outs(list(vs.snapshot(None).entries)))
            st.close()
        check(r1 == r2 and again["created"] == again["updated"] == 0,
              f"import twice ≠ once: {again}")
    elif rel == "input order determinism":
        det = _determinism()
        check(len({json.dumps(v, sort_keys=True) for v in det.values()})
              == 1, f"non-deterministic across seeds/orders: {det}")
        detail = {"variants": len(det)}
    else:
        raise CaseError(f"unknown relation {rel}")
    return ok(detail or {"relation": rel}, disposition="metamorphic")


_DET_SCRIPT = r"""
import json, sys, pathlib, tempfile
sys.path.insert(0, sys.argv[1])
from localflow.v2 import store as store_mod, vocabulary as V
from localflow.v2 import vocabulary_store as VS
from localflow.v2.normalize import ContextSnapshot, NormalizationPolicy, normalize
order = sys.argv[2]
specs = [("E-CL", "Claude", ["clod"]), ("E-CC", "Claude Code", ["clod code"]),
         ("E-Z", "Zed", ["zee"]), ("E-QW", "Qwen", ["q wen"])]
if order == "rev":
    specs = list(reversed(specs))
with tempfile.TemporaryDirectory() as td:
    st = store_mod.Store(pathlib.Path(td) / "v2.db")
    vs = VS.VocabularyStore(st)
    for eid, c, al in specs:
        vs.add_entry(c, al, approved=True, entry_id=eid)
    snap = vs.snapshot(V.ScopeContext(workspace="w"))
    hs = V.RelevantVocabularySelector(3).select(snap, now_utc="t")
    txt = normalize("clod code and zee and q wen", NormalizationPolicy(),
                    ContextSnapshot(vocabulary=snap)).text
    print(json.dumps({"rev": snap.revision, "hint": hs.hint_set_id,
                      "terms": [t.entry_id for t in hs.terms], "text": txt}))
    st.close()
"""


def _determinism():
    out = {}
    for seed in ("0", "1", "4242"):
        for order in ("fwd", "rev"):
            env = dict(os.environ, PYTHONHASHSEED=seed)
            p = subprocess.run([sys.executable, "-c", _DET_SCRIPT,
                                str(CODE), order], env=env,
                               capture_output=True, text=True, timeout=120)
            out[f"seed{seed}_{order}"] = json.loads(
                p.stdout.strip().splitlines()[-1]) if p.returncode == 0 \
                else {"error": p.stderr[-300:]}
    return out


# ---- privacy / honesty / cleanup -------------------------------------------

CANARY_STRINGS = ("AUDIT_CANARY_CANON", "audit canary alias",
                  "AUDIT_CANARY_SCOPE")


def _canary_free(blob):
    return not any(c in blob for c in CANARY_STRINGS)


@handles("operational-canaries")
def h_canary(case):
    stage = case["fault_stage"]
    ce = case["synthetic_vocabulary_entries"][0]
    detail = {}
    if stage in ("duplicate rejection", "import parse/type failure",
                 "store write failure"):
        with tempfile.TemporaryDirectory() as td:
            st, vs, events = new_store(td)
            errs = []
            if stage == "duplicate rejection":
                store_add(vs, {**ce, "approved": True})
                try:
                    store_add(vs, {**ce, "entry_id": "E-CAN2",
                                   "approved": True})
                except Exception as e:
                    errs.append(f"{type(e).__name__}:{e}")
            elif stage == "import parse/type failure":
                p = pathlib.Path(td) / "c.json"
                p.write_text(json.dumps({"entries": [{
                    "entry_id": "x", "canonical": ce["canonical"],
                    "scope": [ce["scope_kind"], ce["scope_value"]],
                    "approved": "false",
                    "aliases": [{"alias": "audit canary alias",
                                 "approved": True}]}]}), encoding="utf-8")
                try:
                    vs.import_json(p)
                except Exception as e:
                    errs.append(f"{type(e).__name__}:{e}")
            else:
                st.submit(lambda db: db.execute(
                    "CREATE TRIGGER t_fail BEFORE INSERT ON"
                    " vocabulary_aliases BEGIN SELECT RAISE(ABORT,"
                    " 'synthetic write failure'); END"))
                try:
                    store_add(vs, {**ce, "approved": True})
                except Exception as e:
                    errs.append(f"{type(e).__name__}:{e}")
            blob = json.dumps(events, default=str) + json.dumps(
                list(st.last_errors))
            detail = {"errors": [x.split(":")[0] for x in errs],
                      "events": [e["event"] for e in events],
                      "event_canary_free": _canary_free(blob),
                      "error_canary_free": _canary_free(" ".join(errs)),
                      "rows": len(vs.entries())}
            st.close()
        check(detail["errors"], "the fault must surface as an error")
        check(detail["event_canary_free"] and detail["error_canary_free"],
              f"canary leaked: {detail}")
        return ok(detail, disposition="fault_injection")
    if stage in ("hint artifact failure", "hint lease failure"):
        from localflow.v2 import capabilities
        with tempfile.TemporaryDirectory() as td:
            st, col, events = _collector(td)
            job, ctx = _start(col)
            hs = V.RelevantVocabularySelector(10).select(
                V.VocabularySnapshot([mk_entry({**ce, "approved": True})],
                                     scope_of(case)))
            real_w, real_l = st.write_text_artifact, st.grant_lease
            fail_write = stage == "hint artifact failure"

            def w(**kw):
                if kw.get("role") == "hint_set" and fail_write:
                    raise OSError("synthetic")
                return real_w(**kw)

            def lease(aid, holder, days=None):
                row = st.artifact(aid) if hasattr(st, "artifact") else None
                if (row or {}).get("role") == "hint_set" and not fail_write:
                    raise OSError("synthetic")
                return real_l(aid, holder, days=days)
            st.write_text_artifact, st.grant_lease = w, lease
            col.on_hint_set(ctx, hs, capabilities.hint_disposition(None, hs))
            st.write_text_artifact, st.grant_lease = real_w, real_l
            col.on_asr_result(ctx, "x", model_id="m", model_revision=None,
                              stage_duration_ms=0.0)
            env = st.latest_revision(col.finalize(ctx))
            blob = json.dumps(events, default=str) + json.dumps(env)
            detail = {"events": [(e["event"], e.get("outcome"))
                                 for e in events],
                      "canary_free": _canary_free(blob),
                      "reason": json.dumps(env.get("context"))}
            st.close()
        check(detail["canary_free"], "canary in events/envelope")
        check("retention_write_failed" in detail["reason"] or
              "retention_write_failed" in json.dumps(
                  env.get("missing_reasons")),
              f"imprecise reason: {detail['reason']}")
        return ok(detail, disposition="fault_injection")
    # App-level snapshot/selector failure: dictation preserved.
    with tempfile.TemporaryDirectory() as td:
        r = AppRun(td, "audit canary alias")
        try:
            d = r.d
            store_add(d._vocab, {**ce, "approved": True})
            if stage == "snapshot failure":
                def boom(*a, **k):
                    raise RuntimeError("synthetic snapshot failure")
                d._vocab.snapshot = boom
            else:
                def boom(*a, **k):
                    raise RuntimeError("synthetic selector failure")
                d._hint_selector.select = boom
            j = r.job("app.canary", workspace="AUDIT_CANARY_SCOPE")
            blob = json.dumps(r.events, default=str)
        finally:
            r.close()
    detail = {"finished": j["finished"], "text": j["text"],
              "events": sorted({e["event"] for e in r.events}),
              "canary_free": _canary_free(blob)}
    check(j["finished"] and j["text"], "dictation must be preserved")
    check(detail["canary_free"], "canary in operational events")
    reasons = [e.get("reason_code") for e in r.events
               if e["event"] == "vocabulary.refresh_failed"]
    check(reasons and all(reasons), "precise reason code expected")
    if stage == "selector failure":
        check(j["text"] == "AUDIT_CANARY_CANON",
              "a selector-only failure must keep the valid scoped rewrite")
    return ok(detail, disposition="portable_orchestration_shim")


def _qualified_manifest(cap, hs_runtime=None):
    m = cap.asr_capability_manifest("m", model_revision="rev1",
                                    runtime={"mlx": "1"})
    m = json.loads(json.dumps(m))
    cb = m["capabilities"]["contextual_biasing"]
    cb["supported"] = True
    cb["qualified_identity"] = {"adapter": m["adapter"], "model_id": "m",
                                "model_revision": "rev1",
                                "runtime": {"mlx": "1"}}
    cb["evidence"] = "synthetic qualification record (test only)"
    return m


@handles("hint-honesty")
def h_honesty(case):
    from localflow.v2 import capabilities as cap
    cond = case["condition"]
    ents = [mk_entry(e) for e in case["synthetic_vocabulary_entries"]]
    hs = V.RelevantVocabularySelector(5).select(V.VocabularySnapshot(ents))
    prod = cap.asr_capability_manifest("m", model_revision="rev1",
                                       runtime={"mlx": "1"})
    out = {}
    if cond in ("nonempty unqualified", "zero offered"):
        f = cap.asr_hint_request_fields(hs, prod, context_snapshot_id="c1")
        disp = cap.hint_disposition(prod, hs)
        out = {"fields": f, "disposition": disp}
        check(f is None and disp["accepted_terms"] == 0, out)
        if cond == "zero offered":
            check(not hs.terms and disp["ignored"] is False
                  and disp["ignored_reason"] is None, out)
        else:
            check(disp["ignored"] is True
                  and disp["ignored_reason"] == "disabled_until_qualified",
                  out)
        return ok(out, disposition="contract")
    if cond == "wrong context_snapshot_id":
        q = _qualified_manifest(cap)
        f = cap.asr_hint_request_fields(hs, q, context_snapshot_id="ctx-A")
        g = cap.asr_hint_request_fields(hs, q, context_snapshot_id=None)
        out = {"qualified_positive": f is not None,
               "carried_id": (f or {}).get("context_snapshot_id"),
               "absent_id": (g or {}).get("context_snapshot_id")}
        check(f is not None and f["context_snapshot_id"] == "ctx-A"
              and g is not None and g["context_snapshot_id"] is None,
              f"exact id propagation under a complete synthetic"
              f" qualification: {out}")
        return ok(out, disposition="future_boundary_contract")
    m = json.loads(json.dumps(prod))
    m["capabilities"]["contextual_biasing"]["supported"] = True
    if cond == "missing checkpoint":
        m["model_revision"] = None
    elif cond == "mismatched runtime":
        m = _qualified_manifest(cap)
        m["runtime"] = {"mlx": "2"}
    f = cap.asr_hint_request_fields(hs, m, context_snapshot_id="c1")
    disp = cap.hint_disposition(m, hs)
    out = {"fields_returned": f is not None, "disposition": disp}
    check(f is None and disp["accepted_terms"] == 0
          and disp["ignored"] is True,
          f"{cond}: an unqualified identity must not receive hints: {out}")
    return ok(out, disposition="future_boundary_contract")


@handles("cleanup-data-boundary")
def h_cleanup(case):
    cond = case["condition"]
    ents = case["synthetic_vocabulary_entries"]
    sc = case["ScopeContext"]
    with tempfile.TemporaryDirectory() as td:
        r = AppRun(td, "ask clod now")
        try:
            d = r.d
            for e in ents:
                store_add(d._vocab, {**e, "approved": True,
                                     "verification": "explicit"})
            styles = d._styles
            styles.add_rule(name="p", scope_kind="app",
                            scope_value=sc["app_bundle"],
                            profile_name=sc["profile"])
            if cond == "suggestions present as hint-only context":
                d._vocab.add_entry("SuggestedTerm", ["sug term"],
                                   scope_kind="workspace",
                                   scope_value=sc["workspace"],
                                   approved=False)
            if cond == "independent 40-item caps":
                for i in range(45):
                    d._vocab.add_entry(f"Cap{_alpha(i).capitalize()}",
                                       [f"cap {_alpha(i)}"],
                                       approved=True)
            if cond == "midflight dictionary edit":
                def edit():
                    d._vocab.add_entry("LiveOnly", ["live only"],
                                       approved=True)
                    wid = next(e.entry_id for e in d._vocab.entries()
                               if e.canonical == "WorkspaceName")
                    d._vocab.set_enabled(wid, False)
                r.on_transcribe = edit
            j = r.job(sc["app_bundle"], workspace=sc["workspace"],
                      site=sc["site_origin"])
            r.on_transcribe = None
            j2 = None
            if cond == "profile/workspace switch":
                j2 = r.job("app.other", workspace=None)
        finally:
            r.close()
    pairs = dict((a, c) for a, c in j["pairs"])
    out = {"text": j["text"], "pairs": j["pairs"],
           "relevant": j["relevant"]}
    check(len(j["pairs"]) <= 40 and len(j["relevant"]) <= 40, out)
    if cond == "approved scope winners only in alias pairs":
        check(j["text"] == "ask WorkspaceName now", out)
        check(pairs.get("clod") == "WorkspaceName", out)
    elif cond == "suggestions present as hint-only context":
        check("sug term" not in pairs, "suggestion must not be a pair")
        check("SuggestedTerm" in j["relevant"],
              "adjudicated D3: an in-scope suggestion may be OFFERED as"
              " hint-derived context")
    elif cond == "independent 40-item caps":
        check(len(j["pairs"]) == 40 and len(j["relevant"]) == 40, out)
    elif cond == "midflight dictionary edit":
        check(j["text"] == "ask WorkspaceName now"
              and pairs.get("clod") == "WorkspaceName"
              and "live only" not in pairs, out)
    else:
        out["second"] = {"text": j2["text"], "pairs": j2["pairs"]}
        check(j["text"] == "ask WorkspaceName now", out)
        check(j2["text"] == "ask GlobalName now"
              and dict(j2["pairs"]).get("clod") == "GlobalName", out)
    return ok(out, disposition="portable_orchestration_shim")


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def run_case(case):
    fn = HANDLERS.get(case["family_id"])
    if fn is None:
        return {"status": "not_run", "reason": "no handler"}
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            return fn(case)
    except AssertionError as e:
        return {"status": "fail", "reason": str(e)[:1500]}
    except Exception as e:
        return {"status": "fail", "reason": f"{type(e).__name__}: {e}"[:600],
                "trace_tail": traceback.format_exc().splitlines()[-5:]}


def code_sha():
    return subprocess.run(["git", "-C", str(CODE), "rev-parse", "HEAD"],
                          capture_output=True, text=True).stdout.strip()


def main():
    raw = CORPUS.read_bytes()
    corpus = json.loads(raw)
    only = set(ARGS.only.split(",")) if ARGS.only else None
    results = []
    for case in corpus["cases"]:
        if only and case["case_id"] not in only \
                and case["family_id"] not in only:
            continue
        t0 = time.monotonic()
        r = run_case(case)
        rec = {
            "case_id": case["case_id"], "family_id": case["family_id"],
            "category": case["category"], "role": case["role"],
            "policy_status": case["policy_status"],
            "finding_ids": case["finding_ids"],
            "expected_text": case.get("expected_text"),
            "expected_invariant": case.get("expected_invariant"),
            "status": r.get("status"), "disposition": r.get("disposition"),
            "reason": r.get("reason"), "oracle_note": r.get("oracle_note"),
            "actual": r.get("actual"), "trace_tail": r.get("trace_tail"),
            "seconds": round(time.monotonic() - t0, 3)}
        results.append(rec)
        if not ARGS.quiet:
            print(f"{rec['case_id']:<28} {rec['status']:<18}"
                  f" {(rec['reason'] or '')[:110]}", flush=True)
    counts = collections.Counter(r["status"] for r in results)

    def by(key):
        d = collections.defaultdict(collections.Counter)
        for r in results:
            d[r[key]][r["status"]] += 1
        return {k: dict(v) for k, v in sorted(d.items())}
    try:
        import native_shims
        shims = list(native_shims.SHIMMED)
    except Exception:
        shims = []
    out = {
        "schema_version": 1, "runner_version": RUNNER_VERSION,
        "label": ARGS.label, "code_root_sha": code_sha(),
        "code_root_modified": bool(subprocess.run(
            ["git", "-C", str(CODE), "status", "--porcelain",
             "--untracked-files=no"], capture_output=True,
            text=True).stdout.strip()),
        "corpus_file": "tests/v2/vocabulary/m05_audit_corpus.json",
        "corpus_sha256": hashlib.sha256(raw).hexdigest(),
        "corpus_execution_status_as_delivered":
            corpus.get("execution_status"),
        "environment": {"python": platform.python_version(),
                        "implementation": platform.python_implementation(),
                        "machine": platform.machine(),
                        "system": platform.system(),
                        "sqlite": sqlite3.sqlite_version,
                        "declared_non_native_shims": shims},
        "evaluated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "counts": dict(counts), "cases_run": len(results),
        "by_family": by("family_id"), "by_role": by("role"),
        "by_category": by("category"), "by_policy": by("policy_status"),
        "results": results,
    }
    text = json.dumps(out, indent=1, sort_keys=True, default=str,
                      ensure_ascii=False)
    if ARGS.output:
        pathlib.Path(ARGS.output).write_text(text + "\n", encoding="utf-8")
    print(f"cases {len(results)}: " + ", ".join(
        f"{k} {v}" for k, v in sorted(counts.items())), flush=True)
    bad = counts.get("fail", 0) + counts.get("not_run", 0)
    sys.stdout.flush()
    os._exit(1 if bad else 0)


if __name__ == "__main__":
    main()
