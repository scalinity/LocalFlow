"""M05 remediation: reproductions of M05-AUDIT-01..20 against a code root.

Every probe drives REAL production code — ``VocabularySnapshot`` /
``normalize`` / ``RelevantVocabularySelector`` / ``VocabularyStore`` /
``SkillRegistry`` / ``EvidenceCollector`` / the Dictionary panel
controller / ``capabilities`` / the M05 benchmark, and the app's
hotkey-down → release → finalize → coordinator path — with SYNTHETIC
authored terms only (the audit's own examples: clod→Claude, "red status
page", …). Only APIs that exist on the audited base are used, so the same
script runs unchanged against the base and the repaired tree
(``--code-root``).

App-level probes run the real ``AppDelegate`` under the DECLARED
non-native shims of tests/v2/lifecycle/native_shims.py with a scripted
supervisor and a scripted M06 context service (``FakeContext``): a result
is a portable orchestration observation, never native AppKit, Accessibility,
microphone or model evidence. The panel probes drive the controller's
Python logic with recorded stand-in text fields — a mocked-interface
signal, not AppKit certification.

Concurrency probes serialize writer admission with an explicit turnstile
(a scripted order of ``Store.submit`` calls per thread) — never sleeps.

``reproduced: true`` means the defect's failure mechanism was observed on
that code root; ``false`` means the probe ran and did not observe it.

Usage:
    .venv/bin/python scripts/v2/m05_remediation_repro.py \
        [--code-root DIR] [--output PATH] [--only a01,a02]
Exit code is always 0 (a reproduction is an observation, not a failure).
"""

import argparse
import contextlib
import io
import json
import os
import pathlib
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import traceback

HERE = pathlib.Path(__file__).resolve().parent.parent.parent

ap = argparse.ArgumentParser()
ap.add_argument("--code-root", default=str(HERE))
ap.add_argument("--output")
ap.add_argument("--only")
ARGS = ap.parse_args()
CODE = pathlib.Path(ARGS.code_root).resolve()
LIFECYCLE = CODE / "tests" / "v2" / "lifecycle"
sys.path.insert(0, str(CODE))
sys.path.insert(0, str(LIFECYCLE))

from localflow.v2 import store as store_mod  # noqa: E402
from localflow.v2 import vocabulary as V  # noqa: E402
from localflow.v2 import vocabulary_store as VS  # noqa: E402
from localflow.v2.normalize import (  # noqa: E402
    ContextSnapshot,
    NormalizationPolicy,
    normalize,
)

PROBES = {}


def probe(name):
    def deco(fn):
        PROBES[name] = fn
        return fn
    return deco


# ---------------------------------------------------------------------------
# Pure-domain helpers
# ---------------------------------------------------------------------------

def E(eid, canonical, aliases=(), **kw):
    """A synthetic entry through the dataclass constructor (probes of the
    PUBLIC admission boundary use the store/import APIs instead)."""
    kw.setdefault("approved", True)
    kw.setdefault("verification", "explicit" if kw["approved"]
                  else "suggested")
    return V.VocabularyEntry(
        entry_id=eid, canonical=canonical,
        aliases=tuple(V.Alias(a) if isinstance(a, str) else a
                      for a in aliases), **kw)


def run(text, entries, scope=None, policy=None):
    snap = V.VocabularySnapshot(entries, scope)
    res = normalize(text, policy or NormalizationPolicy(),
                    ContextSnapshot(vocabulary=snap))
    return {
        "input": text, "output": res.text,
        "vocab_edits": [
            {"input": e.input_text, "output": e.output_text,
             "rule_id": e.rule_id, "span": list(e.input_span.as_pair())}
            for e in res.edits if e.cls == "vocabulary"],
        "other_edits": [(e.cls, e.input_text, e.output_text)
                        for e in res.edits if e.cls != "vocabulary"],
    }


def new_store(td, name="v2.db", events=None):
    rec = events if events is not None else []

    def emit(name_, **kw):
        rec.append({"event": name_, **{k: v for k, v in kw.items()}})
    st = store_mod.Store(pathlib.Path(td) / name, emit=emit)
    return st, VS.VocabularyStore(st), rec


class Turnstile:
    """Scripted writer admission: participating threads may call
    ``Store.submit`` only when the head of ``script`` names them (a
    finished thread's remaining turns are skipped). Deterministic
    interleaving without sleeps; the condition wait has a liveness
    timeout that is REPORTED, never used as a race outcome."""

    def __init__(self, store, script):
        self.store = store
        self.real = store.submit
        self.script = list(script)
        self.cond = threading.Condition()
        self.done = set()
        self.participants = set(script)
        self.timeouts = 0
        self.log = []
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
                self.log.append(name)
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
    """Run name→callable in named threads under the turnstile; returns
    name→("ok", value) | ("error", type name)."""
    out = {}

    def wrap(name, fn):
        try:
            out[name] = ("ok", fn())
        except Exception as e:
            out[name] = ("error", type(e).__name__)
        finally:
            ts.finished(name)
    threads = [threading.Thread(target=wrap, args=(n, f), name=n)
               for n, f in fns.items()]
    for t in threads:
        t.start()
    for t in threads:
        t.join(60)
    return out


def raw(db_path, sql, args=()):
    con = sqlite3.connect(db_path)
    try:
        return con.execute(sql, args).fetchall()
    finally:
        con.close()


# ---------------------------------------------------------------------------
# App harness (declared non-native shims)
# ---------------------------------------------------------------------------

def _helpers():
    import m03_helpers as h  # noqa: E402  (installs the declared shims)
    return h


class FakeContext:
    """Scripted M06 context service: the identity captured at hotkey-down
    and the snapshot finalize returns (real ``context.snapshot`` value
    objects)."""

    def __init__(self):
        self.identity = None
        self.final = None

    def capture_identity(self):
        return self.identity

    def begin(self, identity):
        return object()

    def abandon(self):
        pass

    def finalize(self, job_id=None, target_snapshot_id=None, **kw):
        return self.final


def _target(bundle):
    from localflow.v2 import ids
    from localflow.v2.context import snapshot as csnap
    return csnap.TargetSnapshot(target_snapshot_id=ids.new_id("tgt"),
                                app_bundle=bundle, app_name=bundle,
                                category="editor")


def _final(tgt, workspace=None, site=None):
    from localflow.v2 import ids
    from localflow.v2.context import snapshot as csnap
    return csnap.ContextSnapshot(
        context_snapshot_id=ids.new_id("ctx"), stage="pre_decode",
        target=tgt, workspace=workspace, site_origin=site)


class AppRun:
    """One real AppDelegate on temp roots with the scripted context and a
    recording supervisor (the cleanup kwargs are what M07 would get)."""

    def __init__(self, td, text):
        h = _helpers()
        self.h = h
        self.a = h.App(td, start_coordinator=False)
        self.d = self.a.d
        self.fc = FakeContext()
        self.d._context = self.fc
        self.events = []
        real_emit = self.d.v2log.emit

        def emit(name, **kw):
            self.events.append({"event": name, **kw})
            return real_emit(name, **kw)
        self.d.v2log.emit = emit
        outer = self

        class Sup(h.GateSup):
            def clean(self, **kw):
                outer.clean_kwargs.append(kw)
                return super().clean(**kw)
        self.clean_kwargs = []
        self.sup = Sup(text=text)
        self.a.set_sup(self.sup)
        self.a.start_coordinator()

    def job(self, bundle, workspace=None, site=None):
        """Dictate one job: hotkey-down identity ``bundle``; finalize
        widens to workspace/site. Returns the inserted text, the cleanup
        input and its vocabulary payloads."""
        h = self.h
        self.fc.identity = _target(bundle) if bundle else None
        self.fc.final = _final(self.fc.identity, workspace, site) \
            if bundle else None
        h.AppHelper.calls.clear()
        n = len(self.clean_kwargs)
        self.a.dictate(blocks=10)
        ok = self.a.wait_call("_finishWithText_", 20)
        text = None
        for fn, args in list(h.AppHelper.calls):
            if getattr(fn, "__name__", "") == "_finishWithText_":
                text = args[0]
        self.a.drain()
        kw = self.clean_kwargs[n] if len(self.clean_kwargs) > n else {}
        return {"finished": ok, "inserted_text": text,
                "cleanup_input": kw.get("raw_text"),
                "cleanup_vocabulary_pairs": [
                    list(p) for p in (kw.get("vocabulary_pairs") or [])],
                "cleanup_relevant_vocabulary":
                    list(kw.get("relevant_vocabulary") or [])}

    def close(self):
        self.a.close()


# ---------------------------------------------------------------------------
# 01 — a multiword alias can consume a clause delimiter
# ---------------------------------------------------------------------------

SEPARATORS = [(",", "clod, code"), (".", "clod. code"), (":", "clod: code"),
              (";", "clod; code"), ("!", "clod! code"), ("?", "clod? code"),
              ("LF", "clod\ncode"), ("CR", "clod\rcode"),
              ("CRLF", "clod\r\ncode"), ("VT", "clod\x0bcode"),
              ("FF", "clod\x0ccode"), ("NEL", "clod\x85code"),
              ("LS", "clod code"), ("PS", "clod code")]


@probe("a01")
def a01():
    ents = [E("E-CC", "Claude Code", ["clod code"])]
    neg = {name: run(t, ents) for name, t in SEPARATORS}
    pos = {t: run(t, ents) for t in ("clod code,", "use clod code today",
                                     "clod code", "clod\tcode",
                                     "clod  code")}
    want = {"clod code,": "Claude Code,",
            "use clod code today": "use Claude Code today",
            "clod code": "Claude Code", "clod\tcode": "Claude Code",
            "clod  code": "Claude Code"}
    crossed = {n: r["output"] for n, r in neg.items()
               if r["output"] != dict(SEPARATORS)[n] or r["vocab_edits"]}
    return {"negatives": neg, "positives": pos,
            "positives_hold": all(pos[t]["output"] == w
                                  for t, w in want.items()),
            "crossed_separators": crossed,
            "reproduced": bool(crossed)}


# ---------------------------------------------------------------------------
# 02 — a failed refresh reuses another job's scoped dictionary; a failed
# hint selection blocks the scope upgrade
# ---------------------------------------------------------------------------

@probe("a02")
def a02():
    out = {}
    with tempfile.TemporaryDirectory() as td:
        r = AppRun(td, "ask clod now")
        try:
            d = r.d
            d._vocab.add_entry("Claude", ["clod"], scope_kind="app",
                               scope_value="app.A", approved=True)
            out["job_a_app_A"] = r.job("app.A")

            def boom():
                raise RuntimeError("injected revision read failure")
            real_rev = d._vocab.revision
            d._vocab.revision = boom
            out["job_b_app_B_refresh_failed"] = r.job("app.B")
            d._vocab.revision = real_rev
            out["job_c_app_B_after_recovery"] = r.job("app.B")
            out["refresh_failed_events"] = [
                e.get("outcome") for e in r.events
                if e["event"] == "vocabulary.refresh_failed"]
        finally:
            r.close()
    with tempfile.TemporaryDirectory() as td:
        r = AppRun(td, "ask clod now")
        try:
            d = r.d
            d._vocab.add_entry("GlobalName", ["clod"], approved=True)
            d._vocab.add_entry("WorkspaceName", ["clod"],
                               scope_kind="workspace", scope_value="wsx",
                               approved=True)
            out["control_workspace_upgrade"] = r.job("app.C",
                                                     workspace="wsx")

            def sel_boom(*a, **k):
                raise RuntimeError("injected selector failure")
            d._hint_selector.select = sel_boom
            out["selector_failed_workspace_upgrade"] = r.job(
                "app.C", workspace="wsx")
        finally:
            r.close()
    leak = out["job_b_app_B_refresh_failed"]["inserted_text"] \
        == "ask Claude now" or any(
            p[0] == "clod" for p in
            out["job_b_app_B_refresh_failed"]["cleanup_vocabulary_pairs"])
    gated = out["selector_failed_workspace_upgrade"]["inserted_text"] \
        != "ask WorkspaceName now"
    out.update({"cross_job_leak": leak,
                "selector_failure_blocked_upgrade": gated,
                "control_holds": out["control_workspace_upgrade"][
                    "inserted_text"] == "ask WorkspaceName now",
                "reproduced": leak or gated,
                "wiring": "real AppDelegate startDictation/finishDictation"
                          " → _vocab_job_state → _finalize_job_context →"
                          " coordinator _worker (declared shims)"})
    return out


@probe("a02b")
def a02b():
    """Narrowed sibling of 02: a live job whose hotkey-down capture
    failed falls back to the app's cached (previous job's) context."""
    out = {}
    with tempfile.TemporaryDirectory() as td:
        r = AppRun(td, "ask clod now")
        try:
            d = r.d
            d._vocab.add_entry("Claude", ["clod"], scope_kind="app",
                               scope_value="app.A", approved=True)
            out["job_a_app_A"] = r.job("app.A")
            real = d._m10_freeze

            def boom(*a, **k):
                raise RuntimeError("injected hotkey-down capture failure")
            d._m10_freeze = boom
            out["job_b_capture_failed"] = r.job("app.B")
            d._m10_freeze = real
        finally:
            r.close()
    leak = out["job_b_capture_failed"]["inserted_text"] == "ask Claude now"
    out["reproduced"] = leak
    return out


# ---------------------------------------------------------------------------
# 03 — canonical no-op shield is order dependent
# ---------------------------------------------------------------------------

@probe("a03")
def a03():
    ents = [E("E-A", "Status Page"), E("E-B", "Orange", ["red status"])]
    p1 = run("red status page", ents)
    p2 = run(p1["output"], ents)
    pos = run("red status", ents)
    # Right-overlap control: the claim starts FIRST.
    ents_r = [E("E-A", "Status Page"), E("E-C", "PageView", ["page view"])]
    r1 = run("status page view", ents_r)
    r2 = run(r1["output"], ents_r)
    drift = p2["output"] != p1["output"] or bool(p2["vocab_edits"])
    return {"left_overlap": {"pass1": p1, "pass2": p2},
            "positive_red_status": pos,
            "right_overlap_control": {"pass1": r1, "pass2": r2},
            "second_pass_drift": drift, "reproduced": drift}


# ---------------------------------------------------------------------------
# 04 — snapshot not deeply immutable
# ---------------------------------------------------------------------------

@probe("a04")
def a04():
    caller_aliases = [V.Alias("clod")]
    entry = V.VocabularyEntry(entry_id="E-CL", canonical="Claude",
                              aliases=caller_aliases, approved=True,
                              verification="explicit")
    others = [E("E-X1", "Cloud", ["klaud"]), E("E-X2", "Clown", ["klaud"]),
              E("E-SK", "code-review", ["code review"], kind="skill")]
    snap = V.VocabularySnapshot([entry] + others)
    rev0 = snap.revision
    json0 = json.dumps(snap.to_json(), sort_keys=True)
    out0 = run("ask klod now", list(snap.entries))["output"]
    attempts = {}
    caller_aliases.append(V.Alias("klod"))
    rescoped = V.VocabularySnapshot(snap.entries, V.ScopeContext(
        workspace="x"))
    after = normalize("ask klod now", NormalizationPolicy(),
                      ContextSnapshot(vocabulary=rescoped)).text
    attempts["caller_alias_list_append"] = {
        "entry_aliases_type": type(entry.aliases).__name__,
        "rescoped_output": after, "before": out0}
    for label, fn in (
            ("rebind_scope_ctx", lambda: setattr(
                snap, "scope_ctx", V.ScopeContext(workspace="x"))),
            ("rebind_match_index", lambda: setattr(snap, "match_index", {})),
            ("rebind_revision", lambda: setattr(snap, "revision", "m05:x")),
            ("mutate_conflict_dict", lambda: snap.conflicts[0].__setitem__(
                "alias", "zzz")),
            ("mutate_to_json_skills", lambda: snap.to_json()["skills"]
             .__setitem__("zzz", "x"))):
        try:
            fn()
            attempts[label] = "accepted"
        except Exception as e:
            attempts[label] = f"rejected:{type(e).__name__}"
    json1 = json.dumps(snap.to_json(), sort_keys=True, default=str)
    mutated = [k for k, v in attempts.items()
               if (isinstance(v, str) and v == "accepted"
                   and k != "mutate_to_json_skills")]
    alias_leak = after != out0
    return {"revision_before": rev0, "revision_after": snap.revision,
            "serialization_changed": json0 != json1,
            "attempts": attempts, "accepted_mutations": mutated,
            "caller_alias_mutation_changed_rescope": alias_leak,
            "reproduced": bool(mutated) or alias_leak}


# ---------------------------------------------------------------------------
# 05 — HintSet content mutable under the same id
# ---------------------------------------------------------------------------

@probe("a05")
def a05():
    ents = [E("E-A", "Alpha"), E("E-B", "Beta"), E("E-C", "Gamma")]
    snap = V.VocabularySnapshot(ents, V.ScopeContext(workspace="w"))
    hs = V.RelevantVocabularySelector(2).select(
        snap, now_utc="2026-09-25T00:00:00Z")
    id0 = hs.hint_set_id
    b0 = json.dumps(hs.to_json(), sort_keys=True)
    attempts = {}
    for label, fn in (
            ("scope_item", lambda: hs.scope.__setitem__("workspace", "y")),
            ("omitted_reason", lambda: hs.omitted[0].__setitem__(
                "reason", "other")),
            ("to_json_scope", lambda: hs.to_json()["scope"].__setitem__(
                "app_bundle", "z")),
            ("rebind_terms", lambda: setattr(hs, "terms", ()))):
        try:
            fn()
            attempts[label] = "accepted"
        except Exception as e:
            attempts[label] = f"rejected:{type(e).__name__}"
    b1 = json.dumps(hs.to_json(), sort_keys=True)
    changed_same_id = b1 != b0 and hs.hint_set_id == id0
    return {"id": id0, "bytes_changed_same_id": changed_same_id,
            "attempts": attempts, "after": json.loads(b1),
            "reproduced": changed_same_id}


# ---------------------------------------------------------------------------
# 06 — read-modify-write outside the writer transaction
# ---------------------------------------------------------------------------

def _history(db, eid):
    return raw(db, "SELECT revision, action FROM vocabulary_history"
               " WHERE entry_id=? ORDER BY history_id", (eid,))


@probe("a06")
def a06():
    out = {}
    # (1) A: workspace/X, B: scope_value=None — A.read, B.read, A.write,
    # B.write.
    with tempfile.TemporaryDirectory() as td:
        st, vs, _ = new_store(td)
        eid = vs.add_entry("Claude", ["clod"], approved=True)
        ts = Turnstile(st, ["A", "B", "A", "B"])
        res = run_threads(ts, {
            "A": lambda: vs.update_entry(eid, scope_kind="workspace",
                                         scope_value="X").revision,
            "B": lambda: vs.update_entry(eid, scope_value=None).revision})
        ts.restore()
        st.sync()
        row = raw(st.db_path, "SELECT scope_kind, scope_value, revision"
                  " FROM vocabulary_entries WHERE entry_id=?", (eid,))
        try:
            vs.snapshot(None)
            snap_ok = True
        except Exception as e:
            snap_ok = f"snapshot_failed:{type(e).__name__}"
        out["scope_race"] = {"callers": res, "row": row,
                             "history": _history(st.db_path, eid),
                             "snapshot_builds": snap_ok,
                             "turnstile_timeouts": ts.timeouts}
        st.close()
    # (2) two independent edits from revision 1.
    with tempfile.TemporaryDirectory() as td:
        st, vs, _ = new_store(td)
        eid = vs.add_entry("Claude", ["clod"], approved=True)
        ts = Turnstile(st, ["A", "B", "A", "B"])
        res = run_threads(ts, {
            "A": lambda: vs.update_entry(eid, priority=5).revision,
            "B": lambda: vs.update_entry(eid, pinned=True).revision})
        ts.restore()
        st.sync()
        out["independent_edits"] = {"callers": res,
                                    "history": _history(st.db_path, eid),
                                    "turnstile_timeouts": ts.timeouts}
        st.close()
    # (3) update read → delete commits → update write.
    with tempfile.TemporaryDirectory() as td:
        st, vs, _ = new_store(td)
        eid = vs.add_entry("Claude", ["clod"], approved=True)
        ts = Turnstile(st, ["U", "D", "D", "U"])
        res = run_threads(ts, {
            "U": lambda: vs.update_entry(eid, aliases=["clod", "klod"])
            .revision,
            "D": lambda: vs.delete_entry(eid)})
        ts.restore()
        st.sync()
        out["update_delete_race"] = {
            "callers": res,
            "entry_rows": raw(st.db_path, "SELECT count(*) FROM"
                              " vocabulary_entries WHERE entry_id=?",
                              (eid,)),
            "alias_rows": raw(st.db_path, "SELECT alias FROM"
                              " vocabulary_aliases WHERE entry_id=?",
                              (eid,)),
            "history": _history(st.db_path, eid),
            "turnstile_timeouts": ts.timeouts}
        st.close()
    # (4) approve_entry's stale alias list vs a concurrent alias edit.
    with tempfile.TemporaryDirectory() as td:
        st, vs, _ = new_store(td)
        eid = vs.add_entry("Claude", ["clod"], approved=False)
        ts = Turnstile(st, ["P", "L", "L", "L", "P"])
        res = run_threads(ts, {
            "P": lambda: vs.approve_entry(eid).revision,
            "L": lambda: vs.update_entry(
                eid, aliases=[("clod", False), ("klod", False)]).revision})
        ts.restore()
        st.sync()
        out["approve_alias_race"] = {
            "callers": res,
            "aliases": raw(st.db_path, "SELECT alias, approved FROM"
                           " vocabulary_aliases WHERE entry_id=? ORDER BY"
                           " alias", (eid,)),
            "history": _history(st.db_path, eid),
            "turnstile_timeouts": ts.timeouts}
        st.close()
    s = out["scope_race"]
    invalid = bool(s["row"]) and s["row"][0][0] != "global" \
        and s["row"][0][1] is None
    revs = [r for r, a in out["independent_edits"]["history"]
            if a == "updated"]
    dup = len(revs) != len(set(revs))
    u = out["update_delete_race"]
    orphan = (u["entry_rows"][0][0] == 0 and bool(u["alias_rows"])) or \
        any(a == "updated" for _, a in u["history"][
            [a for _, a in u["history"]].index("deleted"):]) \
        if any(a == "deleted" for _, a in u["history"]) else False
    lost_alias = not any(a == "klod" for a, _ in
                         out["approve_alias_race"]["aliases"])
    out.update({"invalid_scope_committed": invalid,
                "duplicate_next_revision": dup,
                "orphan_after_delete": orphan,
                "approve_lost_concurrent_alias": lost_alias,
                "reproduced": invalid or dup or orphan or lost_alias})
    return out


# ---------------------------------------------------------------------------
# 07 — malformed booleans coerced into approval
# ---------------------------------------------------------------------------

def _import_doc(vs, td, doc, name="imp.json"):
    p = pathlib.Path(td) / name
    p.write_text(json.dumps(doc), encoding="utf-8")
    try:
        return ("ok", vs.import_json(p))
    except Exception as e:
        return ("error", type(e).__name__)


@probe("a07")
def a07():
    cells = {}
    bad_values = ["false", "true", 0, 1, None, [], {}]
    for field in ("approved", "enabled", "pinned", "alias.approved"):
        for v in bad_values:
            ent = {"entry_id": "x", "canonical": "Claude",
                   "scope": ["global", None], "approved": True,
                   "enabled": True, "pinned": False,
                   "aliases": [{"alias": "clod", "approved": True}]}
            if field == "alias.approved":
                ent["aliases"][0]["approved"] = v
            else:
                ent[field] = v
            with tempfile.TemporaryDirectory() as td:
                st, vs, _ = new_store(td)
                rev0 = vs.revision()
                status = _import_doc(vs, td, {"entries": [ent]})
                rows = [(e.approved, e.enabled, e.pinned,
                         [a.approved for a in e.aliases])
                        for e in vs.entries()]
                out_text = normalize(
                    "ask clod now", NormalizationPolicy(),
                    ContextSnapshot(vocabulary=vs.snapshot(None))).text
                cells[f"{field}={json.dumps(v)}"] = {
                    "import": status[0], "stored": rows,
                    "store_revision_changed": vs.revision() != rev0,
                    "output": out_text}
                st.close()
    # Public update API with a string.
    with tempfile.TemporaryDirectory() as td:
        st, vs, _ = new_store(td)
        eid = vs.add_entry("Claude", ["clod"], approved=False)
        try:
            e = vs.update_entry(eid, approved="false")
            upd = {"accepted": True, "approved_stored": e.approved}
        except Exception as ex:
            upd = {"accepted": False, "error": type(ex).__name__}
        st.close()
    string_false_approved = cells['approved="false"']["stored"] and \
        cells['approved="false"']["stored"][0][0] is True
    accepted = [k for k, v in cells.items() if v["import"] == "ok"]
    return {"import_cells": cells, "update_api_string_false": upd,
            "malformed_accepted": accepted,
            "string_false_became_approval": bool(string_false_approved),
            "reproduced": bool(accepted) or upd.get("accepted", False)}


# ---------------------------------------------------------------------------
# 08 — panel selection retargets approval after filter/refresh
# ---------------------------------------------------------------------------

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
    _helpers()  # declared shims before importing the AppKit panel
    from localflow.v2 import dictionary_panel as dp
    ctl = dp.DictionaryPanelController.alloc().initWithVocabularyStore_(vs)
    for name in ("search", "phrase", "sandbox", "listing", "canonical",
                 "alias", "scope_value"):
        setattr(ctl, name, Field())
    ctl.scope_popup = Field("global")
    ctl.refresh()
    return ctl


@probe("a08")
def a08():
    with tempfile.TemporaryDirectory() as td:
        st, vs, _ = new_store(td)
        a = vs.add_entry("Alpha", ["alfa"], approved=False)
        b = vs.add_entry("Beta", ["beeta"], approved=False)
        ctl = _panel(vs)
        ctl.search.v = "beta"
        ctl.searchChanged_(None)
        ctl.phrase.v = "1"
        ctl.runSandbox_(None)
        selected_msg = ctl.sandbox.v
        ctl.search.v = ""
        ctl.searchChanged_(None)
        ctl.approveEntry_(None)
        result = {e.canonical: e.approved for e in vs.entries()}
        st.close()
    wrong = result.get("Alpha") is True
    return {"selected_message": selected_msg, "approved_after": result,
            "entry_ids": {"Alpha": a, "Beta": b},
            "approved_wrong_entry": wrong, "reproduced": wrong,
            "wiring": "DictionaryPanelController Python logic under the"
                      " declared shims with recorded stand-in fields"}


# ---------------------------------------------------------------------------
# 09 — dictionary skill edits lose the approving entry id
# ---------------------------------------------------------------------------

@probe("a09")
def a09():
    from localflow.v2.developer import skills as sk
    ents = [E("E-SK", "code-review", ["code review"], kind="skill")]
    snap = V.VocabularySnapshot(ents)
    snap_prov = getattr(snap, "skill_provenance", None)
    reg = sk.SkillRegistry((), dict(snap.skills),
                           **({"dictionary_provenance": dict(snap_prov)}
                              if snap_prov is not None else {}))
    # First-pass aware: when the code root exposes the provenance channel
    # (registry -> policy), the probe uses it exactly as the app does;
    # the audited base has neither attribute nor parameter.
    prov = getattr(reg, "policy_provenance", None)
    pol = NormalizationPolicy(registered_skills=dict(reg.policy_skills),
                              **({"skill_provenance": dict(prov)}
                                 if prov is not None else {}))
    res = normalize("slash code review", pol,
                    ContextSnapshot(vocabulary=snap))
    edits = [{"cls": e.cls, "output": e.output_text, "rule_id": e.rule_id,
              "reason": e.reason} for e in res.edits]
    app = {}
    with tempfile.TemporaryDirectory() as td:
        r = AppRun(td, "slash code review")
        try:
            r.d._vocab.add_entry("code-review", ["code review"],
                                 kind="skill", approved=True)
            j = r.job("app.X")
            pol2, ctx2, _ = r.d._vocab_job_state(
                V.ScopeContext(app_bundle="app.X"),
                m10={"skill_records": (), "skill_records_rev": None,
                     "norm_profile": None})
            res2 = normalize("slash code review", pol2, ctx2)
            app = {"inserted_text": j["inserted_text"],
                   "edits": [{"cls": e.cls, "rule_id": e.rule_id}
                             for e in res2.edits]}
        finally:
            r.close()
    lost = any(e["cls"] == "skill" and not e["rule_id"] for e in edits)
    app_lost = any(e["cls"] == "skill" and not e["rule_id"]
                   for e in app.get("edits", []))
    return {"text": res.text, "edits": edits, "app_path": app,
            "registry": reg.to_json(), "skill_rule_id_missing": lost,
            "app_skill_rule_id_missing": app_lost,
            "provenance_channel": prov is not None,
            "reproduced": lost or app_lost}


# ---------------------------------------------------------------------------
# 10 / 11 / 12 — import idempotence, duplicate identities, language
# ---------------------------------------------------------------------------

@probe("a10")
def a10():
    doc = {"entries": [{"entry_id": "x", "canonical": "Claude",
                        "scope": ["global", None], "approved": True,
                        "enabled": True, "verification": "explicit",
                        "aliases": [{"alias": "zulu", "approved": True},
                                    {"alias": "alpha", "approved": True}]}]}
    with tempfile.TemporaryDirectory() as td:
        st, vs, _ = new_store(td)
        runs = []
        for i in range(3):
            status = _import_doc(vs, td, doc, f"i{i}.json")
            e = vs.entries()[0]
            runs.append({"result": status, "entry_revision": e.revision,
                         "store_revision": vs.revision(),
                         "snapshot_revision": vs.snapshot(None).revision,
                         "history": len(vs.history(e.entry_id))})
        st.close()
    churn = any(r["result"][0] == "ok" and r["result"][1].get("updated")
                for r in runs[1:])
    return {"runs": runs, "repeat_import_churn": churn, "reproduced": churn}


@probe("a11")
def a11():
    out = {}
    for label, entries in (
            ("duplicate_new_same_case", [("Claude", "clod"),
                                         ("Claude", "klod")]),
            ("duplicate_new_case_variant", [("Claude", "clod"),
                                            ("CLAUDE", "klod")]),
            ("unicode_case_pair", [("Éclair", "eclair"),
                                   ("éclair", "ekler")])):
        doc = {"entries": [
            {"entry_id": f"x{i}", "canonical": c, "scope": ["global", None],
             "approved": True, "enabled": True, "verification": "explicit",
             "aliases": [{"alias": a, "approved": True}]}
            for i, (c, a) in enumerate(entries)]}
        with tempfile.TemporaryDirectory() as td:
            st, vs, _ = new_store(td)
            rev0 = vs.revision()
            status = _import_doc(vs, td, doc)
            out[label] = {"result": status,
                          "rows_after": [(e.canonical,
                                          [a.alias for a in e.aliases])
                                         for e in vs.entries()],
                          "store_revision_delta": vs.revision() - rev0}
            st.close()
    d = out["duplicate_new_same_case"]
    partial = d["result"][0] == "error" and bool(d["rows_after"])
    return {"cases": out, "partial_commit_behind_error": partial,
            "reproduced": partial}


@probe("a12")
def a12():
    out = {}
    with tempfile.TemporaryDirectory() as td:
        st, vs, _ = new_store(td)
        eid = vs.add_entry("Claude", ["clod"], language="en", approved=True)
        before = [(a.alias, a.language) for a in vs.entry(eid).aliases]
        vs.update_entry(eid, language="es")
        e = vs.entry(eid)
        out["language_only_update"] = {
            "entry_language": e.language, "aliases_before": before,
            "aliases_after": [(a.alias, a.language) for a in e.aliases]}
        st.close()
    with tempfile.TemporaryDirectory() as td:
        st, vs, _ = new_store(td)
        doc = {"entries": [{"entry_id": "x", "canonical": "Claude",
                            "language": "en", "scope": ["global", None],
                            "approved": True, "enabled": True,
                            "verification": "explicit",
                            "aliases": [{"alias": "clod", "approved": True,
                                         "language": "es"}]}]}
        _import_doc(vs, td, doc)
        exp = vs.export_json()["entries"][0]["aliases"]
        out["explicit_alias_language_import"] = {"exported_aliases": exp}
        st.close()
    drift = out["language_only_update"]["aliases_after"][0][1] == "en"
    lost = out["explicit_alias_language_import"]["exported_aliases"][0][
        "language"] != "es"
    return {**out, "inherited_alias_language_drift": drift,
            "explicit_alias_override_lost": lost,
            "reproduced": drift or lost}


# ---------------------------------------------------------------------------
# 13 — sandbox / preview diverge from live behavior
# ---------------------------------------------------------------------------

@probe("a13")
def a13():
    out = {}
    with tempfile.TemporaryDirectory() as td:
        st, vs, _ = new_store(td)
        vs.add_entry("WorkspaceName", ["clod"], scope_kind="workspace",
                     scope_value="X", approved=True)
        ctl = _panel(vs)
        ctl.phrase.v = "ask clod now"
        ctl.runSandbox_(None)
        panel_text = ctl.sandbox.v
        # Ask the panel for the entry's scope through its own controls
        # (a panel that ignores them keeps testing global only).
        ctl.scope_popup.v = "workspace"
        ctl.scope_value.v = "X"
        ctl.runSandbox_(None)
        chosen_text = ctl.sandbox.v
        scoped = V.sandbox_phrase("ask clod now",
                                  vs.snapshot(V.ScopeContext(workspace="X")))
        out["panel_scope"] = {
            "panel_output_line": panel_text.splitlines()[0]
            if panel_text else None,
            "panel_mentions_scope": "workspace" in (panel_text or ""),
            "panel_labels_tested_scope": "scope:" in (panel_text or ""),
            "panel_chosen_scope_output_line":
                chosen_text.splitlines()[0] if chosen_text else None,
            "scoped_sandbox_output": scoped["output"]}
        st.close()
    # Suggestions inside protected regions vs post-approval engine.
    sugg = {}
    for text in ('say " clod code " now', "```text\nclod code\n```",
                 "write the phrase clod code"):
        ents = [E("E-U", "Claude Code", ["clod code"], approved=False)]
        s = V.sandbox_phrase(text, V.VocabularySnapshot(ents))
        approved = run(text, [E("E-U", "Claude Code", ["clod code"])])
        sugg[text] = {"suggested": [x["text"] for x in s["suggestions"]],
                      "after_approval_vocab_edits": approved["vocab_edits"]}
    out["suggestions_vs_engine"] = sugg
    # Preview: inactive contenders reported as masks.
    prev = {}
    cand = E("E-NEW", "Claude", ["clod"])
    for label, other in (
            ("disabled_same_scope", E("E-OLD", "Cloud", ["clod"],
                                      enabled=False)),
            ("unapproved_same_scope", E("E-OLD", "Cloud", ["clod"],
                                        approved=False)),
            ("active_same_scope", E("E-OLD", "Cloud", ["clod"])),
            ("term_vs_skill_same_scope", E("E-OLD", "code-review", ["clod"],
                                           kind="skill"))):
        p = V.preview_entry_conflicts(cand, [other])
        committed = run("ask clod now", [cand, other])
        prev[label] = {"preview": p, "committed_output":
                       committed["output"]}
    out["preview_vs_committed"] = prev
    misleading_preview = any(
        any(c["kind"] == "same_scope_mask" and "active" not in c
            for c in v["preview"]) and v["committed_output"] != "ask clod now"
        for v in prev.values())
    misleading_suggestion = any(v["suggested"] and
                                not v["after_approval_vocab_edits"]
                                for v in sugg.values())
    ps = out["panel_scope"]
    panel_global = not (
        (ps["panel_labels_tested_scope"] or ps["panel_mentions_scope"])
        and ps["panel_chosen_scope_output_line"]
        == "→ ask WorkspaceName now")
    out.update({"panel_tests_global_only_unlabeled": panel_global,
                "suggestion_claims_protected_rewrite": misleading_suggestion,
                "preview_reports_inactive_mask": misleading_preview,
                "reproduced": panel_global or misleading_suggestion
                or misleading_preview})
    return out


# ---------------------------------------------------------------------------
# 14 — hint retention failure recorded as ordinary non-capture
# ---------------------------------------------------------------------------

@probe("a14")
def a14():
    from localflow.v2 import capabilities, ids, training
    out = {}
    for fail_at in ("write", "lease"):
        with tempfile.TemporaryDirectory() as td:
            st = store_mod.Store(pathlib.Path(td) / "v2.db")
            events = []

            def rec(name, **kw):
                events.append({"event": name, **kw})
            consent = training.ConsentManager(st, rec)
            col = training.EvidenceCollector(st, rec, consent,
                                             lambda: {"live": "x"})
            consent.set("enabled")
            ctx = col.job_started(ids.new_id("job"), ids.new_id("fam"),
                                  captured_at_utc=ids.now_utc_iso(),
                                  timezone=None, utc_offset_minutes=None)
            snap = V.VocabularySnapshot([E("E-CL", "Claude", ["clod"])])
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
            col.on_asr_result(ctx, "ask clod now", model_id="m",
                              model_revision=None, stage_duration_ms=0.0)
            ex = col.finalize(ctx)
            env = st.latest_revision(ex)
            cblock = env.get("context") or {}
            out[fail_at] = {
                "context_block": cblock,
                "missing_reasons": env.get("missing_reasons"),
                "events": [(e["event"], e.get("outcome"))
                           for e in events
                           if e["event"] == "training.capture_failed"]}
            st.close()
    generic = any(
        (v["context_block"] or {}).get("hint_set_missing_reason")
        in (None, "not_captured_at_stage")
        and "retention_write_failed" not in json.dumps(v)
        for v in out.values())
    return {"injections": out, "generic_non_capture": generic,
            "reproduced": generic}


# ---------------------------------------------------------------------------
# 15 — historical approving-rule reconstruction (test gap)
# ---------------------------------------------------------------------------

@probe("a15")
def a15():
    """Clean reader over EVERY retained artifact of the job (never the
    live dictionary tables): can the deleted applied rule's alias,
    alias approval, scope, verification and entry revision be read back
    structurally (keyed by its rule id), not by substring?"""
    from localflow.v2 import capabilities, ids, training
    with tempfile.TemporaryDirectory() as td:
        st = store_mod.Store(pathlib.Path(td) / "v2.db")
        vs = VS.VocabularyStore(st)
        consent = training.ConsentManager(st, lambda *a, **k: None)
        col = training.EvidenceCollector(st, lambda *a, **k: None, consent,
                                         lambda: {"live": "x"})
        consent.set("enabled")
        eid = vs.add_entry("Zeta", ["zeeta"], scope_kind="workspace",
                           scope_value="W1", approved=True)
        vs.update_entry(eid, priority=2)           # entry revision 2
        for i in range(3):
            vs.add_entry(f"Pin{i}", [], pinned=True, approved=True)
        snap = vs.snapshot(V.ScopeContext(workspace="W1"))
        hs = V.RelevantVocabularySelector(1).select(snap)
        job_id = ids.new_id("job")
        ctx = col.job_started(job_id, ids.new_id("fam"),
                              captured_at_utc=ids.now_utc_iso(),
                              timezone=None, utc_offset_minutes=None)
        col.on_hint_set(ctx, hs, capabilities.hint_disposition(None, hs))
        col.on_asr_result(ctx, "use zeeta", model_id="m",
                          model_revision=None, stage_duration_ms=0.0)
        pol = NormalizationPolicy()
        cctx = ContextSnapshot(vocabulary=snap)
        res = normalize("use zeeta", pol, cctx)
        col.on_normalization_result(ctx, res, source_text="use zeeta",
                                    policy=pol, context=cctx)
        col.on_cleanup_result(ctx, res.text)
        ex = col.finalize(ctx)
        env = st.latest_revision(ex)
        vs.update_entry(eid, aliases=[("zeeta", False)])
        vs.delete_entry(eid)
        st.sync()
        rows = raw(st.db_path, "SELECT artifact_id, role FROM artifacts"
                   " WHERE job_id=? AND purged=0", (job_id,))
        payloads = {}
        for aid, role in rows:
            try:
                payloads[role] = json.loads(st.artifact_payload(aid))
            except Exception:
                payloads[role] = None
        st.close()

    def walk(o):
        if isinstance(o, dict):
            yield o
            for v in o.values():
                yield from walk(v)
        elif isinstance(o, list):
            for v in o:
                yield from walk(v)
    docs = [d for p in list(payloads.values()) + [env]
            for d in walk(p)]
    keyed = [d for d in docs if eid in (d.get("rule_id"), d.get("entry_id"))]
    edit = next((d for d in keyed if d.get("rule_id") == eid
                 and "input_text" in d), None)
    found = {
        "rule_id_in_ledger": edit is not None,
        "alias_occurrence": edit.get("input_text") if edit else None,
        "verification": edit.get("reason") if edit else None,
        "scope_kind_value": next(
            (d.get("scope") for d in keyed if d.get("scope")), None),
        "alias_approval": next(
            (d.get("aliases") for d in keyed if "aliases" in d), None),
        "entry_revision": next(
            (d.get("revision") for d in keyed
             if isinstance(d.get("revision"), int)), None),
        "snapshot_revision_in_envelope":
            (env.get("normalization") or {}).get("vocabulary", {}).get(
                "revision") == snap.revision,
        "hint_set_terms_contain_rule": any(
            t.get("entry_id") == eid for t in hs.to_json()["terms"]),
    }
    missing = [k for k in ("scope_kind_value", "alias_approval",
                           "entry_revision") if not found[k]]
    return {"retained_roles": sorted(payloads), "recovered": found,
            "unrecoverable": missing, "reproduced": bool(missing),
            "note": "test gap: exact scope / alias approval / entry"
                    " revision of a deleted applied rule from retained"
                    " artifacts alone"}


# ---------------------------------------------------------------------------
# 16 — benchmark accepts identity matcher / wrong-scope selector
# ---------------------------------------------------------------------------

# A scripted clock (1 µs per reading) removes machine speed from the
# verdict: with every timing gate trivially met, the exit code can only
# reflect the benchmark's WORK-validity checks.
_FAKE_CLOCK = (
    "import time\n"
    "_t = [0.0]\n"
    "def _mono():\n"
    "    _t[0] += 1e-6\n"
    "    return _t[0]\n"
    "time.monotonic = _mono\n")

_BENCH_PATCH = {
    "unmodified_control": "",
    "identity_matcher": (
        "import localflow.v2.normalize.syntax as s\n"
        "s.grammar_vocabulary = lambda host: iter(())\n"),
    "wrong_scope_selector": (
        "import localflow.v2.vocabulary as V\n"
        "real = V.RelevantVocabularySelector.select\n"
        "def sel(self, snap, scope_ctx=None, **kw):\n"
        "    return real(self, V.VocabularySnapshot(snap.entries, None),"
        " None, **kw)\n"
        "V.RelevantVocabularySelector.select = sel\n"),
    "skip_every_fourth_edit": (
        "import localflow.v2.normalize.syntax as s\n"
        "real = s.grammar_vocabulary\n"
        "def g(host):\n"
        "    for i, p in enumerate(real(host)):\n"
        "        if i % 4 != 3:\n"
        "            yield p\n"
        "s.grammar_vocabulary = g\n"),
}


@probe("a16")
def a16():
    out = {}
    bench = CODE / "scripts" / "v2" / "benchmark_m05.py"
    for label, patch in _BENCH_PATCH.items():
        code = (f"import sys, runpy\nsys.path.insert(0, {str(CODE)!r})\n"
                + _FAKE_CLOCK + patch + f"sys.argv=[{str(bench)!r}]\n"
                f"runpy.run_path({str(bench)!r}, run_name='__main__')\n")
        t0 = time.monotonic()
        p = subprocess.run([sys.executable, "-c", code], cwd=str(CODE),
                           capture_output=True, text=True, timeout=3600)
        out[label] = {"exit": p.returncode,
                      "seconds": round(time.monotonic() - t0, 1),
                      "stdout_tail": p.stdout.strip().splitlines()[-10:],
                      "stderr_tail": p.stderr.strip().splitlines()[-3:]}
    accepted = [k for k, v in out.items()
                if k != "unmodified_control" and v["exit"] == 0]
    return {"mutations": out, "clock": "scripted (timing neutralized)",
            "accepted_invalid_work": accepted,
            "control_exit": out["unmodified_control"]["exit"],
            "reproduced": bool(accepted)}


# ---------------------------------------------------------------------------
# 17 — the inherited suites stay green over the reproduced defects
# ---------------------------------------------------------------------------

@probe("a17")
def a17():
    out = {}
    for rel in ("tests/v2/vocabulary/test_vocabulary_matching.py",
                "tests/v2/vocabulary/test_vocabulary_store.py",
                "tests/v2/vocabulary/test_hint_selection.py"):
        p = subprocess.run([sys.executable, str(CODE / rel)], cwd=str(CODE),
                           capture_output=True, text=True, timeout=600)
        out[rel] = {"exit": p.returncode,
                    "ok_lines": sum(1 for ln in p.stdout.splitlines()
                                    if ln.startswith("ok"))}
    green = all(v["exit"] == 0 for v in out.values())
    pinned = {}
    for rel in ("tests/v2/vocabulary/test_m05_remediation.py",
                "tests/v2/vocabulary/test_m05_remediation_app.py"):
        if not (CODE / rel).exists():
            pinned[rel] = "absent"
            continue
        p = subprocess.run([sys.executable,
                            str(CODE / "tests/v2/lifecycle/run_with_shims.py"),
                            str(CODE / rel)], cwd=str(CODE),
                           capture_output=True, text=True, timeout=1800)
        pinned[rel] = {"exit": p.returncode,
                       "ok_lines": sum(1 for ln in p.stdout.splitlines()
                                       if ln.startswith("ok"))}
    gap_closed = all(isinstance(v, dict) and v["exit"] == 0
                     for v in pinned.values())
    return {"inherited_suites": out, "all_green": green,
            "regression_suites": pinned, "gap_closed": gap_closed,
            "reproduced": green and not gap_closed,
            "note": "test gap: the inherited portable suites are green on"
                    " this code root; a01/a02/a03/a06/a07 show whether"
                    " defects coexist with that green (base) or not"}


# ---------------------------------------------------------------------------
# 18 — torn-table repair over a POPULATED dictionary (test gap)
# ---------------------------------------------------------------------------

@probe("a18")
def a18():
    """Populated torn M05 tables under the current schema-11 repair path,
    then the app's startup seeding over the repaired store."""
    out = {}
    with tempfile.TemporaryDirectory() as td:
        seed = pathlib.Path(td) / "seed.db"
        st = store_mod.Store(seed)
        vs = VS.VocabularyStore(st)
        e1 = vs.add_entry("Claude", ["clod", ("klod", False)], approved=True)
        vs.add_entry("Cloud", ["clod"], approved=True)       # conflict
        vs.update_entry(e1, priority=3)
        before = [(e.entry_id, e.canonical, e.revision,
                   [(a.alias, a.approved) for a in e.aliases])
                  for e in vs.entries()]
        rev_before = vs.revision()
        st.close()
        for label, sqls in (
                ("drop_aliases", ["DROP TABLE vocabulary_aliases"]),
                ("drop_history", ["DROP TABLE vocabulary_history"]),
                ("drop_entries", ["DROP TABLE vocabulary_entries"]),
                ("drop_unique_index",
                 ["DROP INDEX idx_vocabulary_canonical_scope"]),
                ("drop_index_then_duplicate",
                 ["DROP INDEX idx_vocabulary_canonical_scope",
                  "INSERT INTO vocabulary_entries(entry_id, canonical,"
                  " scope_kind, created_at_utc, updated_at_utc)"
                  " VALUES('vocab-dup','claude','global','t','t')"]),
                ("drop_meta", ["DROP TABLE vocabulary_meta"])):
            copy = pathlib.Path(td) / f"{label}.db"
            copy.write_bytes(seed.read_bytes())
            con = sqlite3.connect(copy)
            for sql in sqls:
                con.execute(sql)
            con.commit()
            con.close()
            events = []
            try:
                st2 = store_mod.Store(
                    copy, backup_dir=pathlib.Path(td) / f"bk-{label}",
                    emit=lambda n, **kw: events.append(
                        (n, kw.get("reason_code"))))
            except Exception as ex:
                out[label] = {"opened": False, "error": type(ex).__name__,
                              "events": events}
                continue
            try:
                vs2 = VS.VocabularyStore(st2)
                after = [(e.entry_id, e.canonical, e.revision,
                          [(a.alias, a.approved) for a in e.aliases])
                         for e in vs2.entries()]
                orphans = raw(copy, "SELECT count(*) FROM"
                              " vocabulary_aliases WHERE entry_id NOT IN"
                              " (SELECT entry_id FROM vocabulary_entries)")
                # The app's startup seeding (legacy + suggestions).
                try:
                    seeded = vs2.seed_suggested_coding_terms()
                except Exception as ex:
                    seeded = f"refused:{type(ex).__name__}"
                out[label] = {
                    "opened": True, "events": events,
                    "entries_after": after,
                    "entries_preserved": [x[:3] for x in after]
                    == [x[:3] for x in before],
                    "aliases_preserved": after == before,
                    "orphan_alias_rows": orphans[0][0],
                    "store_revision_after": vs2.revision(),
                    "startup_seeding": seeded,
                    "integrity_report": (
                        vs2.integrity_report()
                        if hasattr(vs2, "integrity_report") else None),
                    "vocabulary_integrity_signal": any(
                        n.startswith("vocabulary.") for n, _ in events)
                    or bool(hasattr(vs2, "integrity_report") and any(
                        vs2.integrity_report().values()))}
            finally:
                st2.close()
    silent_loss = out.get("drop_entries", {}).get("opened") and \
        not out["drop_entries"].get("vocabulary_integrity_signal") and \
        out["drop_entries"].get("orphan_alias_rows", 0) > 0
    return {"before": before, "store_revision_before": rev_before,
            "cohorts": out, "entries_table_loss_silent": bool(silent_loss),
            "reproduced": bool(silent_loss),
            "note": "test gap: characterization of repair over populated"
                    " M05 tables (the inherited test used an empty store)"}


# ---------------------------------------------------------------------------
# 19 — qualified-adapter shape vs identity (test gap)
# ---------------------------------------------------------------------------

@probe("a19")
def a19():
    from localflow.v2 import capabilities as cap
    hs = V.RelevantVocabularySelector(5).select(
        V.VocabularySnapshot([E("E-CL", "Claude", ["clod"])]))
    out = {}
    base = cap.asr_capability_manifest("m", model_revision="rev1",
                                       runtime={"mlx": "1"})
    out["production_unqualified"] = {
        "fields": cap.asr_hint_request_fields(hs, base),
        "disposition": cap.hint_disposition(base, hs)}
    for label, mutate in (
            ("supported_flag_only", lambda m: None),
            ("missing_checkpoint", lambda m: m.update(model_revision=None)),
            ("mismatched_runtime", lambda m: m["runtime"].update(mlx="2"))):
        m = json.loads(json.dumps(base))
        m["capabilities"]["contextual_biasing"]["supported"] = True
        mutate(m)
        f = cap.asr_hint_request_fields(hs, m, context_snapshot_id="ctx-1")
        out[label] = {"fields_returned": f is not None,
                      "disposition_ignored":
                          cap.hint_disposition(m, hs)["ignored"]}
    flag_bypass = any(out[k]["fields_returned"] for k in
                      ("supported_flag_only", "missing_checkpoint",
                       "mismatched_runtime"))
    return {**out, "boolean_bypasses_identity": flag_bypass,
            "reproduced": flag_bypass}


# ---------------------------------------------------------------------------
# 20 — active descriptions still pre-M06/pre-M07
# ---------------------------------------------------------------------------

@probe("a20")
def a20():
    hits = {}
    for rel, needles in (
            ("docs/v2/contracts/vocabulary.md",
             ("`profile` stays unfed until a writing-profile subsystem"
              " exists (M10)", "Pre-M06 the live app filters with no"
              " destination context")),
            ("tests/v2/vocabulary/test_hint_selection.py",
             ("cleanup deferred to M07 (not a consumer yet)",)),
            ("docs/v2/contracts/asr_hints.md",
             ("not a consumer yet", "deferred to M07"))):
        p = CODE / rel
        text = p.read_text(encoding="utf-8") if p.exists() else ""
        flat = " ".join(text.split())
        hits[rel] = [n for n in needles if " ".join(n.split()) in flat]
    stale = any(hits.values())
    return {"stale_statements_found": hits, "reproduced": stale}


def main():
    names = sorted(PROBES)
    if ARGS.only:
        names = [n for n in names if n in ARGS.only.split(",")]
    out = {"schema_version": 1, "tool": "scripts/v2/m05_remediation_repro.py",
           "code_root_sha": subprocess.run(
               ["git", "-C", str(CODE), "rev-parse", "HEAD"],
               capture_output=True, text=True).stdout.strip(),
           "working_tree_modified": bool(subprocess.run(
               ["git", "-C", str(CODE), "status", "--porcelain",
                "--untracked-files=no"], capture_output=True,
               text=True).stdout.strip()),
           "python": sys.version.split()[0],
           "sqlite": sqlite3.sqlite_version,
           "evaluated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                          time.gmtime()),
           "findings": {}}
    for n in names:
        t0 = time.monotonic()
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                res = PROBES[n]()
        except Exception as e:
            res = {"probe_error": type(e).__name__,
                   "trace_tail": traceback.format_exc().splitlines()[-6:]}
        res["seconds"] = round(time.monotonic() - t0, 2)
        out["findings"][n] = res
        print(f"{n}: reproduced={res.get('reproduced')}"
              f" ({res['seconds']}s)", flush=True)
    try:
        import native_shims
        out["native_shims"] = list(native_shims.SHIMMED)
    except Exception:
        out["native_shims"] = []
    text = json.dumps(out, indent=1, sort_keys=True, default=str,
                      ensure_ascii=False)
    if ARGS.output:
        pathlib.Path(ARGS.output).write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
    os._exit(0)  # coordinator daemon threads of app probes


if __name__ == "__main__":
    main()
