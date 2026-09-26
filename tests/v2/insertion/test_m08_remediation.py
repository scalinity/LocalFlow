"""M08 remediation regressions (2026-09-26 read-only audit at 180278e).

One or more cases per production finding M08-AUDIT-01..19, each driven
through the REAL insertion service, validation, selection capture,
observer and — where the finding lives there — the real coordinator and
store, over the independent world in ``m08_world.py`` (UTF-16 host
units, separate owner pids, equal-title windows, its own read/effect
logs). Every assertion is checked against the WORLD's record of what
was read and written, never only against a result object. Each case
pairs its adversarial schedule with a positive control, so "refuse
everything" cannot pass.

The same file runs on the audited base (where each case is expected to
fail on the defect it names) and on the repaired code. Configuration
the base does not accept (e.g. a deny list reaching the service) is
passed through a signature-tolerant factory and the dropped parameter
is reported — on the base, that absence IS the defect.

Run: .venv/bin/python tests/v2/context/run_isolated.py \
         tests/v2/insertion/test_m08_remediation.py [--json OUT] [-k NAME]
"""

from __future__ import annotations

import inspect
import json
import pathlib
import sys
import tempfile
import threading
import time
import traceback

HERE = pathlib.Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[3]))
sys.path.insert(0, str(HERE.parent))

from m08_world import (Keyboard, Pasteboard, Win, standard_world,  # noqa: E402
                      u16, wait_for)

from localflow.v2 import ids, store as store_mod  # noqa: E402
from localflow.v2.context.providers import categorize  # noqa: E402
from localflow.v2.context.snapshot import (ContextSnapshot,  # noqa: E402
                                           FieldContext, TargetSnapshot)
from localflow.v2.insertion import service as service_mod  # noqa: E402
from localflow.v2.insertion import observation as observation_mod  # noqa: E402
from localflow.v2.insertion.selection import capture_selection  # noqa: E402
from localflow.v2.insertion.service import InsertionService  # noqa: E402

CASES = []


def case(finding):
    def deco(fn):
        fn.finding = finding
        CASES.append(fn)
        return fn
    return deco


class Rec:
    def __init__(self):
        self.events = []

    def __call__(self, event, level="INFO", **kw):
        self.events.append((event, level, kw))


class Env:
    """A temporary store plus the standard world and a real service."""

    def __init__(self, *, window=0.0, settle=0.15, text_f1="",
                 sel_f1=None, role="AXTextArea", **service_kw):
        self.tmp = tempfile.TemporaryDirectory()
        root = pathlib.Path(self.tmp.name)
        self.store = store_mod.Store(root / "v2.db",
                                     backup_dir=root / "backups")
        self.w, self.pb, self.kb = standard_world(
            text_f1=text_f1, sel_f1=sel_f1, role=role)
        self.rec = Rec()
        kw = dict(host=self.w, pasteboard=self.pb, keyboard=self.kb,
                  store=self.store, emit=self.rec, restore_clipboard=True,
                  observation_window_sec=window, settle_sec=settle)
        params = inspect.signature(InsertionService.__init__).parameters
        self.dropped = sorted(k for k in service_kw if k not in params)
        kw.update({k: v for k, v in service_kw.items() if k in params})
        self.svc = InsertionService(**kw)

    def close(self):
        try:
            self.store.sync()
            self.store.close()
        finally:
            self.tmp.cleanup()

    def run(self, text, job, timeout=10.0, on_observation=None,
            injected_fault=False):
        box, done = {}, threading.Event()

        def on_done(r):
            box["r"] = r
            done.set()

        self.svc.submit(text, job, on_done, on_observation=on_observation)
        assert done.wait(timeout), "transaction did not finish"
        r = box["r"]
        if not injected_fault and \
                (r.reason_code or "").startswith("transaction_error:"):
            # A fault before any effect is a harness/code error — never
            # evidence that an effect was (correctly) avoided.
            raise RuntimeError(f"transaction error: {r.reason_code}")
        return r

    def rows(self, sql, *args):
        return self.store.submit(
            lambda conn: conn.execute(sql, args).fetchall())


def snap(w, app="A", fid="F1", *, sel=None, sel_text=None, title=True,
         window=True, pre=None, fol=None, category=None, denied=False,
         stage="pre_decode"):
    """A ContextSnapshot of (app, field) as M06/M11 would have recorded
    it: host-unit selection, the field's own window element, the title."""
    a = w.apps[app]
    f = w.fields[fid]
    target = TargetSnapshot(
        target_snapshot_id=ids.new_id("tgt"), app_bundle=a["bundle"],
        app_name=app, app_pid=a["pid"], denied=denied,
        category=category or categorize(a["bundle"]),
        captured_at_utc=ids.now_utc_iso())
    field = FieldContext(
        role=f.role, subrole=f.subrole, classification="text",
        selected_text=sel_text, selected_range=None,
        selected_range_utf16=sel, preceding_text=pre, following_text=fol)
    return ContextSnapshot(
        context_snapshot_id=ids.new_id("ctx"), stage=stage, target=target,
        field=field,
        window_title=w.windows[f.window]["title"] if title else None,
        window_element=Win(f.window) if window else None,
        captured_at_utc=ids.now_utc_iso())


def job(jid="job-m08", s=None, *, consent=True, **kw):
    j = {"job_id": jid, "attempt": 1, "observation_consent": consent}
    if s is not None:
        j["context_snapshot"] = s
    j.update(kw)
    return j


class after_validation:
    """Run ``fn(job)`` immediately after the service's validate_target
    returns — the exact check-to-use boundary (a barrier, not a sleep)."""

    def __init__(self, fn):
        self.fn = fn

    def __enter__(self):
        self._real = service_mod.validate_target
        real, fn = self._real, self.fn

        def wrapped(host, snapshot, job, **kw):
            out = real(host, snapshot, job, **kw)
            fn(job)
            return out
        service_mod.validate_target = wrapped
        return self

    def __exit__(self, *exc):
        service_mod.validate_target = self._real


def reads_on(w, fids, since=0):
    return [r for r in w.reads if r[2] in fids and r[0] > since]


def writes_on(w, fids, since=0):
    return [e for e in w.effects
            if e[2] in fids and e[0] > since
            and e[1] in ("ax_set_text", "ax_set_range", "paste_consumed",
                         "ax_set_noop")]


# ---- M08-AUDIT-01: validation binds the element used for the write --------

@case("M08-AUDIT-01")
def test_a01_write_after_validation_goes_only_to_validated_field():
    """A/W1/F1 validates; before the effect the focus moves to app B's
    settable field. Nothing may be written to B, and the result must not
    carry A's verification over B's effect."""
    env = Env()
    w = env.w
    s = snap(w)

    def switch(_job):
        w.focus("B", "FB")
    with after_validation(switch):
        r = env.run("dictated", job(s=s))
    assert writes_on(w, {"FB", "F2"}) == [], \
        f"foreign write: {writes_on(w, {'FB', 'F2'})}"
    assert w.text("FB") == "CANARY_B_SELECTION", w.text("FB")
    assert r.state == "target_changed", (r.state, r.reason_code)
    env.close()
    # Positive control: unchanged destination inserts once, confirmed.
    env = Env()
    r = env.run("dictated", job(s=snap(env.w)))
    assert env.w.text("F1") == "dictated", env.w.text("F1")
    assert r.state == "confirmed", (r.state, r.reason_code)
    env.close()


@case("M08-AUDIT-01")
def test_a01_same_app_other_window_after_validation():
    """Same application, another window with an equal title: a move from
    W1/F1 to W2/F2 after validation must not write F2."""
    env = Env()
    w = env.w
    w.fields["F2"].text = ""
    w.fields["F2"].sel = (0, 0)
    s = snap(w)
    with after_validation(lambda _j: w.focus("A", "F2")):
        r = env.run("dictated", job(s=s))
    assert writes_on(w, {"F2"}) == [], writes_on(w, {"F2"})
    assert w.text("F2") == "", w.text("F2")
    assert r.state == "target_changed", (r.state, r.reason_code)
    env.close()


@case("M08-AUDIT-01")
def test_a01_clipboard_post_bound_to_validated_field():
    """Clipboard method: after validation the system focus moves to B.
    The ⌘V would land in B — it must not be posted."""
    env = Env()
    w = env.w
    w.fields["F1"].settable = False
    s = snap(w)
    with after_validation(lambda _j: w.focus("B", "FB")):
        r = env.run("dictated", job(s=s))
    assert writes_on(w, {"FB"}) == [], writes_on(w, {"FB"})
    assert env.kb.posts == 0, f"{env.kb.posts} paste(s) posted into B"
    assert r.state == "target_changed", (r.state, r.reason_code)
    env.close()


# ---- M08-AUDIT-02: M11 capture reads only the authorized app's element ----

@case("M08-AUDIT-02")
def test_a02_capture_never_reads_other_apps_element():
    """Allowed A is authorized; the system focus then points at denied
    B's field. The capture must not read B's content at all (a read that
    is later discarded still fails)."""
    w, pb, kb = standard_world(text_f1="keep old words here",
                               sel_f1=(5, 14))
    w.fields["FB"].sel = (0, 18)                # CANARY_B_SELECTION
    w.system_focus = "FB"                      # focus drift after authz
    cap, reason = capture_selection(w, denied_apps=("com.example.b",))
    assert reads_on(w, {"FB"}) == [], \
        f"B content read: {reads_on(w, {'FB'})}"
    if cap is not None:
        assert "CANARY" not in cap["source"], cap["source"]
    # Positive control: A's own selection is captured.
    w2, _pb, _kb = standard_world(text_f1="keep old words here",
                                  sel_f1=(5, 14))
    cap2, reason2 = capture_selection(w2, denied_apps=("com.example.b",))
    assert cap2 is not None and cap2["source"] == "old words", \
        (cap2, reason2)


@case("M08-AUDIT-02")
def test_a02_capture_flank_reads_stay_on_one_element():
    """The selection is read from A/F1; before the surrounding-text reads
    the global focus changes to B. No B content may be acquired."""
    w, pb, kb = standard_world(text_f1="keep old words here",
                               sel_f1=(5, 14))
    fired = []

    def drift(world, el, *a):
        if not fired:
            fired.append(1)
            world.system_focus = "FB"
            world.front_app = "B"
    # The first surrounding read happens after the selected text is read.
    w.on("number_of_characters", drift, nth=1)
    capture_selection(w, denied_apps=())
    assert reads_on(w, {"FB"}) == [], reads_on(w, {"FB"})


# ---- M08-AUDIT-03: destination-content readers obey the deny policy -------

DENY_A = ("com.example.a",)


@case("M08-AUDIT-03")
def test_a03_denied_app_insert_reads_no_destination_content():
    """A is denied (identity-only snapshot). Plain insertion may still
    happen, but validation and readback must not read A's content."""
    env = Env(text_f1="CANARY_DENIED ", denied_apps=DENY_A)
    w = env.w
    t = TargetSnapshot(target_snapshot_id="tgt-d", app_bundle="com.example.a",
                       app_name="A", app_pid=101, denied=True,
                       category="unknown", captured_at_utc="")
    r = env.run("hello", {"job_id": "job-den", "attempt": 1,
                          "target": t, "observation_consent": True})
    reads = reads_on(w, {"F1"})
    assert reads == [], f"denied-app content reads: {reads}" + \
        (f" (service ignored {env.dropped})" if env.dropped else "")
    assert "hello" in w.text("F1"), "plain insertion stays available"
    assert r.state != "confirmed", r.state
    env.close()


@case("M08-AUDIT-03")
def test_a03_denied_app_undo_and_repaste_read_nothing():
    env = Env(text_f1="", denied_apps=DENY_A)
    w = env.w
    t = TargetSnapshot(target_snapshot_id="tgt-d", app_bundle="com.example.a",
                       app_name="A", app_pid=101, denied=True,
                       category="unknown", captured_at_utc="")
    env.run("hello", {"job_id": "job-den", "attempt": 1, "target": t,
                      "observation_consent": True})
    w.fields["F1"].text = "CANARY_DENIED hello"
    mark = w.seq
    env.svc.undo_last()
    env.svc.paste_again()
    env.svc.paste_text("hello", job_id="job-den")
    time.sleep(0.4)
    reads = reads_on(w, {"F1"}, since=mark)
    assert reads == [], f"denied-app reads by undo/repaste: {reads}"
    env.close()


@case("M08-AUDIT-03")
def test_a03_unclassifiable_field_reads_nothing():
    """An allowed app whose focused element cannot be classified as a
    text field: plain dictation without any content read."""
    env = Env(text_f1="CANARY_UNKNOWN", role="AXGroup")
    w = env.w
    s = snap(w)
    r = env.run("hi", job(s=s))
    assert reads_on(w, {"F1"}) == [], reads_on(w, {"F1"})
    assert r.state != "confirmed", r.state
    env.close()


# ---- M08-AUDIT-04: missing proof never keeps destructive authority -------

@case("M08-AUDIT-04")
def test_a04_plain_replacement_needs_live_selection():
    """A recorded non-empty selection; the live selected range is
    unreadable. Replacement authority must not survive — nothing is
    overwritten."""
    env = Env(text_f1="say old wording now", sel_f1=(4, 15))
    w = env.w
    s = snap(w, sel=(4, 15), sel_text="old wording")
    real_attr = w.attribute

    def attr(el, name):
        if name == "AXSelectedTextRange" and getattr(el, "fid", "") == "F1":
            w._read("attribute", "F1", name)
            return None
        return real_attr(el, name)
    w.attribute = attr
    r = env.run("new", job(s=s))
    assert w.text("F1") == "say old wording now", w.text("F1")
    assert r.state in ("target_changed", "saved_not_inserted"), r.state
    env.close()


@case("M08-AUDIT-04")
def test_a04_strict_needs_native_window_element():
    """Strict accept with matching title/role/range/text but the live
    AXWindow unavailable: the title alone is not window proof."""
    env = Env(text_f1="say old wording now", sel_f1=(4, 15))
    w = env.w
    s = snap(w, sel=(4, 15), sel_text="old wording", pre="say ",
             fol=" now")
    real_attr = w.attribute
    w.attribute = lambda el, name: (None if name == "AXWindow"
                                    else real_attr(el, name))
    r = env.run("new wording", job(s=s, strict_replacement=True))
    assert w.text("F1") == "say old wording now", w.text("F1")
    assert r.state == "target_changed", r.state
    env.close()


@case("M08-AUDIT-04")
def test_a04_strict_needs_recorded_surroundings():
    """Strict accept whose capture recorded no surrounding text on
    either side: the surroundings proof is missing, not passed."""
    env = Env(text_f1="say old wording now", sel_f1=(4, 15))
    w = env.w
    s = snap(w, sel=(4, 15), sel_text="old wording", pre=None, fol=None)
    r = env.run("new wording", job(s=s, strict_replacement=True))
    assert w.text("F1") == "say old wording now", w.text("F1")
    assert r.state == "target_changed", r.state
    env.close()
    # Positive control: every proof present -> one exact replacement.
    env = Env(text_f1="say old wording now", sel_f1=(4, 15))
    s = snap(env.w, sel=(4, 15), sel_text="old wording", pre="say ",
             fol=" now")
    r = env.run("new wording", job(s=s, strict_replacement=True))
    assert env.w.text("F1") == "say new wording now", env.w.text("F1")
    assert r.state == "confirmed", (r.state, r.reason_code, r.verification)
    env.close()


# ---- M08-AUDIT-05: native UTF-16 ranges end to end ----------------------

@case("M08-AUDIT-05")
def test_a05_astral_owned_range_in_host_units():
    """A😀B with the caret at its end (4 UTF-16 units); inserting X😀Y
    (3 code points, 4 units) owns [4, 8) — never a mixed-unit [4, 7)."""
    env = Env(text_f1="A😀B", sel_f1=(4, 4))
    w = env.w
    r = env.run("X😀Y", job(s=snap(w)))
    assert w.text("F1") == "A😀BX😀Y", w.text("F1")
    assert (r.owned_start, r.owned_end) == (4, 8), \
        (r.owned_start, r.owned_end)
    assert r.state == "confirmed", (r.state, r.readback)
    env.close()


@case("M08-AUDIT-05")
def test_a05_astral_undo_restores_exactly():
    """Replace a selection containing an astral character, then undo:
    the exact previous text returns, in host units."""
    env = Env(text_f1="pre 😀x post", sel_f1=(4, 7))
    w = env.w
    s = snap(w, sel=(4, 7), sel_text="😀x", pre="pre ", fol=" post")
    r = env.run("Y😀Z", job(s=s))
    assert w.text("F1") == "pre Y😀Z post", w.text("F1")
    out = env.svc.undo_last()
    assert out and out.get("outcome") == "undone", out
    assert w.text("F1") == "pre 😀x post", w.text("F1")
    env.close()


# ---- M08-AUDIT-06: confirmation needs attributable change ---------------

@case("M08-AUDIT-06")
def test_a06_ax_noop_over_identical_text_is_not_confirmed():
    """The field already holds 'hello' at the caret; the AX setter
    acknowledges but changes nothing. No effect happened."""
    env = Env(text_f1="hello", sel_f1=(0, 0))
    w = env.w
    w.fields["F1"].set_behavior = "noop"
    r = env.run("hello", job(s=snap(w)))
    assert w.text("F1") == "hello"
    assert r.state != "confirmed", (r.state, r.readback)
    env.close()


@case("M08-AUDIT-06")
def test_a06_missing_preread_cannot_confirm():
    """Clipboard method, the pre-write read fails, and the target never
    consumes the paste — a later equal read proves nothing."""
    env = Env(text_f1="hello", sel_f1=(0, 0))
    w = env.w
    w.fields["F1"].settable = False
    env.kb.mode = "drop"
    real = w.string_for_range
    n = []

    def sfr(el, start, length):
        n.append(1)
        if len(n) == 1:
            w._read("string_for_range", el.fid, "AXStringForRange")
            return None
        return real(el, start, length)
    w.string_for_range = sfr
    r = env.run("hello", job(s=snap(w)))
    assert w.text("F1") == "hello"
    assert r.state != "confirmed", (r.state, r.readback)
    env.close()


@case("M08-AUDIT-06")
def test_a06_no_recorded_destination_is_never_confirmed():
    """No snapshot at all (context off / identity failed): the validator
    records no destination — insert on faith, posted_unverified."""
    env = Env()
    r = env.run("faith", {"job_id": "job-ns", "attempt": 1,
                          "observation_consent": True})
    assert env.w.text("F1") == "faith"
    assert r.state == "posted_unverified", r.state
    env.close()


# ---- M08-AUDIT-07: an unchanged prefix is not a consumed paste ----------

@case("M08-AUDIT-07")
def test_a07_unchanged_prefix_keeps_ownership():
    """Field 'hel', request 'hello', the target consumes only after the
    settle bound. The unchanged prefix must not trigger restore — the
    late consumer must paste LocalFlow's text, not the user's clipboard."""
    env = Env(text_f1="hel", sel_f1=(0, 0), settle=0.12)
    w = env.w
    w.fields["F1"].settable = False
    env.pb.user_copy("CANARY_OLD_CLIPBOARD")
    env.kb.mode = "gate"
    r = env.run("hello", job(s=snap(w)))
    env.kb.release()
    assert wait_for(lambda: any(e[1] == "paste_consumed"
                                for e in w.effects), 3)
    assert "CANARY_OLD_CLIPBOARD" not in w.text("F1"), w.text("F1")
    assert w.text("F1") == "hellohel", w.text("F1")
    assert r.state != "confirmed", r.state
    env.close()
    # Positive control: a genuinely truncated paste changed the field.
    env = Env(text_f1="", settle=0.12)
    env.w.fields["F1"].settable = False
    env.pb.user_copy("CANARY_OLD_CLIPBOARD")
    env.kb.truncate = 3
    r = env.run("hello", job(s=snap(env.w)))
    assert env.w.text("F1") == "hel"
    assert r.readback == "partial" and r.state == "posted_unverified", \
        (r.readback, r.state)
    assert env.pb.plain() == "CANARY_OLD_CLIPBOARD", env.pb.plain()
    env.close()


@case("M08-AUDIT-07")
def test_a07_next_job_never_changes_a_pending_payload():
    """ONE is posted and unconsumed past settle (ownership kept); TWO is
    queued. TWO must not replace ONE's payload under the late consumer,
    and neither job may be pasted twice."""
    env = Env(text_f1="", settle=0.1)
    w = env.w
    w.fields["F1"].settable = False
    env.pb.user_copy("CANARY_OLD_CLIPBOARD")
    env.kb.mode = "gate"
    r1 = env.run("ONE ", job("job-one", snap(w)))
    r2 = env.run("TWO ", job("job-two", snap(w)))
    env.kb.release()
    wait_for(lambda: sum(1 for e in w.effects
                         if e[1] == "paste_consumed") >= env.kb.posts, 3)
    time.sleep(0.2)
    txt = w.text("F1")
    assert "CANARY_OLD_CLIPBOARD" not in txt, txt
    assert txt.count("TWO") <= 1 and txt.count("ONE") <= 1, txt
    assert "ONE" in txt, f"the late consumer lost ONE's payload: {txt!r}"
    env.close()


# ---- M08-AUDIT-08: undo is bound to the original field --------------------

@case("M08-AUDIT-08")
def test_a08_undo_never_writes_another_window():
    env = Env(text_f1="")
    w = env.w
    r = env.run("red", job(s=snap(w)))
    assert w.text("F1") == "red"
    w.fields["F2"].text = "red"
    w.fields["F2"].sel = (3, 3)
    w.focus("A", "F2")
    mark = w.seq
    out = env.svc.undo_last()
    assert writes_on(w, {"F2"}, mark) == [], writes_on(w, {"F2"}, mark)
    assert w.text("F2") == "red", w.text("F2")
    assert out.get("outcome") != "undone", out
    env.close()
    # Positive control: the original field, still focused -> undone.
    env = Env(text_f1="")
    env.run("red", job(s=snap(env.w)))
    out = env.svc.undo_last()
    assert out.get("outcome") == "undone" and env.w.text("F1") == "", \
        (out, env.w.text("F1"))
    env.close()


# ---- M08-AUDIT-09: clipboard replacement keeps the replaced text ----------

@case("M08-AUDIT-09")
def test_a09_clipboard_replacement_undo_restores_selection():
    env = Env(text_f1="say old wording now", sel_f1=(4, 15))
    w = env.w
    w.fields["F1"].settable = False
    w.fields["F1"].range_settable = False
    s = snap(w, sel=(4, 15), sel_text="old wording")
    r = env.run("new wording", job(s=s))
    assert w.text("F1") == "say new wording now", w.text("F1")
    w.fields["F1"].settable = True
    w.fields["F1"].range_settable = True
    out = env.svc.undo_last()
    assert w.text("F1") == "say old wording now", (w.text("F1"), out)
    env.close()


# ---- M08-AUDIT-10: observation never follows focus to another field ------

def observed(env, text, *, consent=True, s=None, jid="job-obs"):
    box = {}
    r = env.run(text, job(jid, s if s is not None else snap(env.w),
                          consent=consent),
                on_observation=lambda info: box.__setitem__(
                    "obs", info["observer"]))
    return r, box.get("obs")


@case("M08-AUDIT-10")
def test_a10_observer_stops_before_reading_another_field():
    env = Env(window=1.5, text_f1="")
    w = env.w
    r, obs = observed(env, "owned")
    assert r.state == "confirmed" and obs is not None, (r.state, obs)
    w.fields["F2"].text = "CANARY_FOREIGN_FIELD"
    mark = w.seq
    w.focus("A", "F2")
    obs.join(5)
    assert reads_on(w, {"F2"}, mark) == [], reads_on(w, {"F2"}, mark)
    assert obs.edited is False, "a foreign field is not our edit"
    env.close()


@case("M08-AUDIT-10")
def test_a10_secure_subrole_transition_stops_before_read():
    env = Env(window=1.5, text_f1="", role="AXTextField")
    w = env.w
    r, obs = observed(env, "owned")
    assert obs is not None
    time.sleep(0.1)
    mark = w.seq
    w.fields["F1"].subrole = "AXSecureTextField"
    obs.join(5)
    late = [x for x in reads_on(w, {"F1"}, mark)]
    assert late == [] or obs.stop_reason == "secure_field_transition", late
    assert obs.stop_reason == "secure_field_transition", obs.stop_reason
    assert late == [], f"content read after the secure transition: {late}"
    env.close()


# ---- M08-AUDIT-11: re-anchoring needs unique bounded provenance ----------

def artifact_text(env, aid):
    row = env.rows("SELECT content_text FROM artifacts WHERE artifact_id=?",
                   aid)
    return row[0][0] if row else None


@case("M08-AUDIT-11")
def test_a11_duplicate_occurrence_is_ambiguous():
    """'red ' precedes our inserted 'red'; the user deletes OUR
    occurrence. The remaining equal text is not our region."""
    env = Env(window=1.5, text_f1="red ", sel_f1=(4, 4))
    w = env.w
    r, obs = observed(env, "red")
    assert obs is not None and w.text("F1") == "red red"
    time.sleep(0.15)
    w.user_replace("F1", 4, 7, "")
    obs.join(5)
    assert not (obs.stop_reason == "window_elapsed" and obs.reanchors), \
        f"re-anchored onto the pre-existing occurrence ({obs.stop_reason})"
    env.close()


@case("M08-AUDIT-11")
def test_a11_read_failure_is_not_an_edit():
    """The field length stays readable but the ranged string reads fail
    once the range has shifted: the re-anchor search saw nothing — that
    is 'unavailable', never an owned-region edit."""
    env = Env(window=1.5, text_f1="")
    w = env.w
    r, obs = observed(env, "stable text")
    assert obs is not None
    time.sleep(0.1)
    real = w.string_for_range

    def failing(el, start, length):
        w._read("string_for_range", el.fid, "AXStringForRange")
        return None
    w.user_type("F1", 0, "x")            # shift: forces a search
    w.string_for_range = failing
    obs.join(5)
    w.string_for_range = real
    assert obs.edited is False, "a failed read was attributed as an edit"
    assert obs.after_artifact is None
    env.close()


@case("M08-AUDIT-11")
def test_a11_changed_length_edit_keeps_only_owned_region():
    """'cat' inserted before a neighbour canary; the user replaces it
    with a longer word. The after-text is exactly the new word or
    nothing — never a truncated or neighbour-including region."""
    for new in ("tiger", "ox"):
        env = Env(window=1.5, text_f1=" CANARY_OUTSIDE", sel_f1=(0, 0))
        w = env.w
        r, obs = observed(env, "cat")
        assert obs is not None and w.text("F1") == "cat CANARY_OUTSIDE"
        time.sleep(0.15)
        w.user_replace("F1", 0, 3, new)
        obs.join(5)
        after = artifact_text(env, obs.after_artifact) \
            if obs.after_artifact else None
        assert after in (None, new), f"after-text {after!r} for {new!r}"
        env.close()


# ---- M08-AUDIT-12: no passive observation without capture consent ------

@case("M08-AUDIT-12")
def test_a12_consent_off_capture_writes_no_observation_content():
    env = Env(window=1.2, text_f1="")
    w = env.w
    r, obs = observed(env, "private words", consent=False)
    if obs is not None:
        time.sleep(0.2)
        w.user_replace("F1", 0, 7, "PUBLIC")
        obs.join(5)
    env.store.sync()
    arts = env.rows("SELECT role FROM artifacts WHERE role LIKE"
                    " 'observation_%'")
    rows = env.rows("SELECT observation_id FROM insertion_observations")
    assert arts == [] and rows == [], (arts, rows)
    env.close()
    # Positive control: consent at capture -> the window runs.
    env = Env(window=0.6, text_f1="")
    r, obs = observed(env, "private words", consent=True)
    assert obs is not None, "a consented capture on a certified surface"
    obs.join(5)
    env.close()


# ---- M08-AUDIT-15: cancellation before an avoidable effect ----------------

@case("M08-AUDIT-15")
def test_a15_cancel_after_validation_prevents_ax_write():
    env = Env()
    w = env.w
    j = job(s=snap(w))
    with after_validation(lambda jj: jj.__setitem__("cancelled", True)):
        r = env.run("must not land", j)
    assert w.text("F1") == "", w.text("F1")
    assert r.state == "saved_not_inserted", r.state
    env.close()


@case("M08-AUDIT-15")
def test_a15_cancel_after_publish_prevents_post():
    env = Env()
    w = env.w
    w.fields["F1"].settable = False
    env.pb.user_copy("CANARY_USER_ORIGINAL")
    j = job(s=snap(w))
    env.svc._on_post_begin = lambda: j.__setitem__("cancelled", True)
    r = env.run("must not land", j)
    assert env.kb.posts == 0, "a paste was posted after cancellation"
    assert w.text("F1") == ""
    assert env.pb.plain() == "CANARY_USER_ORIGINAL", env.pb.plain()
    env.close()
    # Control: cancellation after the witnessed effect keeps the truth.
    env = Env()
    j = job(s=snap(env.w))
    r = env.run("landed", j)
    j["cancelled"] = True
    assert env.w.text("F1") == "landed" and r.state == "confirmed"
    env.close()


# ---- M08-AUDIT-16: a late exception keeps the physical facts --------------

@case("M08-AUDIT-16")
def test_a16_exception_after_ax_write_keeps_effect_facts():
    env = Env()
    w = env.w
    wrote = []
    w.on("set_attribute", lambda world, el, name: wrote.append(name))
    real = w.number_of_characters

    def boom(el):
        if wrote:
            raise RuntimeError("controlled readback fault")
        return real(el)
    w.number_of_characters = boom
    r = env.run("landed", job(s=snap(w)), injected_fault=True)
    assert w.text("F1") == "landed"
    assert r.method == "ax_replacement", (r.state, r.method, r.reason_code)
    assert r.state == "posted_unverified", (r.state, r.reason_code)
    rows = env.rows("SELECT insertion_id, method FROM insertions")
    assert rows and rows[0][0] == r.insertion_id, (rows, r.insertion_id)
    env.close()


@case("M08-AUDIT-16")
def test_a16_exception_during_restore_keeps_post():
    env = Env(settle=0.1)
    w = env.w
    w.fields["F1"].settable = False
    env.pb.user_copy("CANARY_USER_ORIGINAL")

    def boom(_pb):
        raise RuntimeError("controlled restore fault")
    env.pb.on("clear_and_write_items", boom)
    r = env.run("landed", job(s=snap(w)), injected_fault=True)
    assert w.text("F1") == "landed"
    assert r.method == "clipboard_transaction", (r.method, r.reason_code)
    assert r.state in ("posted_unverified", "confirmed"), r.state
    env.close()


# ---- M08-AUDIT-19: clipboard snapshot and acknowledgments ---------------

@case("M08-AUDIT-19")
def test_a19_capture_is_one_generation_or_a_conflict():
    """A user copy lands between the generation read and the flavour
    reads. The capture must be consistent, or the transaction must not
    publish over the newer copy."""
    env = Env()
    w = env.w
    w.fields["F1"].settable = False
    env.pb.user_copy(items=[[("public.utf8-plain-text", b"OLD"),
                             ("public.rtf", b"{\\rtf1 OLD}")]])
    fired = []

    def copy_mid(pb):
        if not fired:
            fired.append(1)
            pb.user_copy("CANARY_USER_COPY")
    env.pb.on("data_for_type", copy_mid, nth=1)
    r = env.run("dictated", job(s=snap(w)))
    ops = [o[1] for o in env.pb.ops]
    published_after_copy = "write_text" in ops[ops.index("user_copy", 1):] \
        if ops.count("user_copy") > 1 else False
    disclosed = r.clipboard.get("unsupported_types", [])
    assert not (published_after_copy and env.pb.plain() != "CANARY_USER_COPY"
                ), f"user copy lost: board={env.pb.plain()!r} ops={ops}"
    assert "public.rtf" not in disclosed, \
        f"a flavour from another generation reported: {disclosed}"
    env.close()


@case("M08-AUDIT-19")
def test_a19_copy_after_publish_is_never_pasted():
    """A user copy lands after LocalFlow published and before the paste
    post (corpus F10-C01): posting now would paste THEIR content."""
    env = Env()
    w = env.w
    w.fields["F1"].settable = False
    env.pb.user_copy("CANARY_OLD_CLIPBOARD")
    env.svc._on_post_begin = lambda: env.pb.user_copy("CANARY_USER_COPY")
    r = env.run("dictated", job(s=snap(w)))
    assert "CANARY_USER_COPY" not in w.text("F1"), w.text("F1")
    assert env.pb.plain() == "CANARY_USER_COPY", env.pb.plain()
    assert r.state in ("saved_not_inserted", "posted_unverified"), r.state
    env.close()


@case("M08-AUDIT-01/D15")
def test_terminal_cr_and_separators_are_not_pasted():
    """A terminal destination: a bare CR (or a Unicode line separator,
    or a control character) executes like a newline — copy offer only
    (corpus F16-C05, policy D15). A single plain line still inserts."""
    for text in ("ls\rrm -rf x", "one two", "a\x1b[0m"):
        env = Env()
        w = env.w
        w.apps["A"]["bundle"] = "com.apple.Terminal"
        r = env.run(text, job(s=snap(w, category="terminal")))
        assert w.text("F1") == "", (text, w.text("F1"))
        assert env.kb.posts == 0 and r.state == "saved_not_inserted", \
            (text, r.state, r.reason_code)
        env.close()
    env = Env()
    env.w.apps["A"]["bundle"] = "com.apple.Terminal"
    r = env.run("git status", job(s=snap(env.w, category="terminal")))
    assert env.w.text("F1") == "git status", env.w.text("F1")
    env.close()


@case("M08-AUDIT-11")
def test_a11_edit_after_window_deadline_is_not_attributed():
    """The window's deadline has passed when the next tick sees the
    owned text changed (corpus F20-C04): deadline exhaustion is never
    edit evidence."""
    env = Env(window=0.6, text_f1="")
    w = env.w
    r, obs = observed(env, "owned words")
    assert obs is not None
    time.sleep(0.75)                  # after the deadline, before a tick
    w.user_replace("F1", 0, 5, "OWNED")
    obs.join(5)
    assert obs.edited is False, (obs.stop_reason, obs.edited)
    assert obs.after_artifact is None
    env.close()


@case("M08-AUDIT-19")
def test_a19_refused_publication_is_not_posted():
    env = Env()
    w = env.w
    w.fields["F1"].settable = False
    env.pb.user_copy("CANARY_USER_ORIGINAL")
    env.pb.write_ack = False
    r = env.run("dictated", job(s=snap(w)))
    assert env.kb.posts == 0, "posted a paste after a refused publication"
    assert r.state not in ("confirmed", "posted_unverified"), r.state
    env.close()


# ---- app-level cases: the real AppDelegate over the world ----------------

class AppEnv:
    """The shared M04/M06 harness (real AppDelegate, real store, real
    coordinator thread) with the app's OWN InsertionService — built by
    ``configure`` from the app's configuration — pointed at the world.
    Context collection is off (no live NSWorkspace/Accessibility); a
    test attaches the destination snapshot to the job itself."""

    def __init__(self, *, consent=False, cfg=None, window=1.5,
                 text_f1="", asr="hello app"):
        sys.path.insert(0, str(HERE.parents[1] / "normalization"))
        import test_normalization_pipeline as tnp
        import localflow.app as app_mod
        self.app_mod = app_mod
        c = {"outcome_observation_sec": window}
        c.update(cfg or {})
        # The shared harness swaps in a synchronous stub after
        # configure(); keep the service configure() really built (with
        # the app's own parameters) instead.
        stub = tnp.StubInsertionService
        tnp.StubInsertionService = lambda d: d._insertion
        try:
            self.h = tnp.Harness([1.0], cfg=c,
                                 supervisor=tnp.RecordingSupervisor(asr))
        finally:
            tnp.StubInsertionService = stub
        d = self.d = self.h.d
        d._context = None
        # Point the app-built service at the world before its first
        # transaction; it has never touched the system hosts.
        self.svc = d._insertion
        assert isinstance(self.svc, InsertionService), type(self.svc)
        self.w, self.pb, self.kb = standard_world(text_f1=text_f1)
        self.svc.host, self.svc.pasteboard = self.w, self.pb
        self.svc.keyboard = self.kb
        self.svc._settle_sec = 0.1
        if consent:
            d.consent.set("enabled", note="m08 remediation test")

    def dictate(self, *, snapshot=True):
        """press → coordinator → _finishWithText_ with the destination
        snapshot attached; callbacks run inline. Returns the job."""
        app_mod = self.app_mod
        self.h.press_release()
        fn, args = self.h.run_coordinator()
        text, job = args
        if snapshot:
            s = snap(self.w)
            job["context_snapshot"] = s
            job["target"] = s.target
        real = app_mod.AppHelper.callAfter
        app_mod.AppHelper.callAfter = lambda f, *a: f(*a)
        try:
            self.d._finishWithText_(text, job)
            assert wait_for(lambda: job not in self.d._active_jobs, 10), \
                "insertion never settled the job"
        finally:
            app_mod.AppHelper.callAfter = real
        return job

    def close(self):
        self.h.close()


class inline_after:
    def __init__(self, app_mod):
        self.m = app_mod

    def __enter__(self):
        self._real = self.m.AppHelper.callAfter
        self.m.AppHelper.callAfter = lambda f, *a: f(*a)

    def __exit__(self, *exc):
        self.m.AppHelper.callAfter = self._real


@case("M08-AUDIT-12")
def test_a12_app_capture_consent_gates_observation():
    """Through the coordinator: collection OFF at push-to-talk -> no
    observation row or artifact; ON -> the window runs."""
    a = AppEnv(consent=False, window=0.8)
    job = a.dictate()
    time.sleep(0.2)
    a.w.user_replace("F1", 0, 3, "HEY")
    time.sleep(1.0)
    a.d.store.sync()
    rows = a.d.store.submit(lambda c: c.execute(
        "SELECT COUNT(*) FROM insertion_observations").fetchone()[0])
    arts = a.d.store.submit(lambda c: c.execute(
        "SELECT COUNT(*) FROM artifacts WHERE role LIKE"
        " 'observation_%'").fetchone()[0])
    a.close()
    assert rows == 0 and arts == 0, (rows, arts)
    b = AppEnv(consent=True, window=0.6)
    b.dictate()
    ok = wait_for(lambda: b.d.store.submit(lambda c: c.execute(
        "SELECT COUNT(*) FROM insertion_observations").fetchone()[0]) >= 1,
        3)
    b.close()
    assert ok, "a consented capture on a certified surface observes"


@case("M08-AUDIT-03")
def test_a03_app_passes_its_deny_policy_to_the_service():
    """The app's validated deny list reaches M08's readers: a dictation
    into a denied app reads none of its content."""
    a = AppEnv(consent=True, cfg={"context_denied_apps": ["COM.Example.A "]})
    a.w.fields["F1"].text = "CANARY_DENIED "
    a.w.fields["F1"].sel = (0, 0)
    a.dictate()
    time.sleep(0.3)
    reads = reads_on(a.w, {"F1"})
    a.close()
    assert reads == [], f"denied-app reads through the app: {reads[:4]}"


@case("M08-AUDIT-13")
def test_a13_deletion_revokes_repaste_undo_and_observer():
    """A confirmed, observed insertion; then delete-everywhere through
    the real store and listener. Paste Again, Undo and the running
    observer must neither read nor write the field again."""
    a = AppEnv(consent=True, window=3.0)
    job = a.dictate()
    assert a.w.text("F1") == "hello app", a.w.text("F1")
    a.d.store.delete_everywhere("job", job["job_id"])
    mark = a.w.seq
    with inline_after(a.app_mod):
        a.d.pasteLastResultAgain_(None)
        a.d.undoLastInsertion_(None)
    time.sleep(1.4)                       # > two observer ticks
    late_reads = reads_on(a.w, {"F1"}, mark)
    late_writes = writes_on(a.w, {"F1"}, mark)
    text = a.w.text("F1")
    a.close()
    assert late_writes == [] and text == "hello app", (late_writes, text)
    assert late_reads == [], f"reads after deletion: {late_reads[:4]}"


@case("M08-AUDIT-14")
def test_a14_duplicate_completion_retires_once():
    a = AppEnv(consent=False)
    job = a.dictate()
    pending = a.d._pending
    from localflow.v2.insertion import InsertionResult
    dup = InsertionResult(insertion_id="ins-dup", job_id=job["job_id"],
                          state="confirmed", method="ax_replacement")
    with inline_after(a.app_mod):
        a.d._insertionDone_(dup, job)
    after = a.d._pending
    a.close()
    assert after == pending, f"_pending {pending} -> {after}"


@case("M08-AUDIT-14")
def test_a14_same_operation_submitted_twice_writes_once():
    env = Env()
    w = env.w
    j = job(s=snap(w))
    done = []
    gate = threading.Event()
    env.svc.undo_last(on_done=lambda _o: gate.wait(5))   # hold the queue
    env.svc.submit("once", j, lambda r: done.append(r))
    env.svc.submit("once", j, lambda r: done.append(r))
    gate.set()
    wait_for(lambda: len(done) >= 2, 5)
    txt = w.text("F1")
    env.close()
    assert txt == "once", f"one operation, effects: {txt!r}"


@case("M08-AUDIT-14")
def test_a14_two_repastes_reconcile_serially():
    """The previous result is absent; two Paste Again requests arrive
    while the queue is busy. Serialized reconciliation pastes once."""
    env = Env()
    w = env.w
    env.run("hello", job(s=snap(w)))
    w.user_replace("F1", 0, 5, "")
    gate = threading.Event()
    env.svc.undo_last(on_done=lambda _o: gate.wait(5))   # hold the queue
    time.sleep(0.05)
    env.svc.paste_again()
    env.svc.paste_again()
    gate.set()
    wait_for(lambda: env.kb.posts + sum(
        1 for e in w.effects if e[1] == "ax_set_text") >= 2, 2)
    time.sleep(0.6)
    txt = w.text("F1")
    env.close()
    assert txt == "hello", f"two repastes produced {txt!r}"


@case("M08-AUDIT-17")
def test_a17_recovery_and_history_repaste_do_no_ax_on_caller():
    """Recovery's Paste Again and History's Paste Again called on the
    UI thread with a slow Accessibility reader: the callback returns
    promptly and no AX read runs on the calling thread."""
    a = AppEnv(consent=False)
    job = a.dictate()
    a.w.user_replace("F1", 0, u16(a.w.text("F1")), "")
    caller = threading.current_thread().name
    seen = []

    def slow(world, *args):
        seen.append(threading.current_thread().name)
        time.sleep(0.25)
    a.w.on("number_of_characters", slow)
    a.w.on("string_for_range", slow)
    t0 = time.monotonic()
    with inline_after(a.app_mod):
        a.d.pasteLastResultAgain_(None)
        dt_recovery = time.monotonic() - t0
        t1 = time.monotonic()
        a.d.hubPasteText("history text", job_id=job["job_id"])
        dt_history = time.monotonic() - t1
    time.sleep(0.8)
    a.close()
    on_caller = [t for t in seen if t == caller]
    assert on_caller == [], f"{len(on_caller)} AX read(s) on the UI thread"
    assert dt_recovery < 0.1 and dt_history < 0.1, (dt_recovery, dt_history)


@case("M08-AUDIT-18")
def test_a18_close_in_subscription_gap_delivers_once():
    """The observer closes after the app looked at it but before the
    app's close subscription is installed. Exactly one final
    observation callback must still reach the evidence collector."""
    a = AppEnv(consent=True, window=5.0)
    base = observation_mod.OutcomeObserver

    class GapObserver(base):
        def __init__(self, *args, **kw):
            super().__init__(*args, **kw)
            self._gap_fired = False
            self.signals = observation_mod.StopSignals()

        def _gap(self):
            # Only the APP's subscription (from _observationStarted_) is
            # the gap under test; the close lands just before it.
            caller = sys._getframe(2).f_code.co_name
            if not self._gap_fired and caller == "_observationStarted_":
                self._gap_fired = True
                self.signals.note_session_locked()
                self._thread.join(3)

        def __setattr__(self, name, value):
            if name == "on_closed" and value is not None:
                self._gap()
            super().__setattr__(name, value)

        def subscribe_close(self, fn):
            self._gap()
            return super().subscribe_close(fn)

    calls = []
    a.d.collector.on_observation_closed = \
        lambda ctx, result, obs: calls.append(obs)
    service_mod.OutcomeObserver = GapObserver
    try:
        a.dictate()
        wait_for(lambda: calls, 3)
        time.sleep(0.3)
    finally:
        service_mod.OutcomeObserver = base
    a.close()
    assert len(calls) == 1, f"final observation callbacks: {len(calls)}"


def code_stamp():
    """Which code actually ran: the root's HEAD, whether any TRACKED file
    differs from it (untracked files — e.g. this suite copied into a
    frozen base worktree — do not count), and the imported package's
    location relative to that root."""
    import subprocess
    import localflow
    root = HERE.parents[3]

    def git(*a):
        try:
            return subprocess.run(["git", "-C", str(root), *a],
                                  capture_output=True, text=True,
                                  timeout=10).stdout.strip()
        except Exception:
            return None
    origin = pathlib.Path(localflow.__file__).resolve()
    try:
        rel = origin.relative_to(root.resolve()).as_posix()
    except ValueError:
        rel = None
    dirty = git("status", "--porcelain", "--untracked-files=no")
    return {"code_root_sha": git("rev-parse", "HEAD"),
            "tracked_files_modified": bool(dirty) if dirty is not None
            else None,
            "localflow_imported_from_root": rel,
            "python": sys.version.split()[0]}


def main(argv):
    out_json = None
    only = None
    if "--json" in argv:
        out_json = argv[argv.index("--json") + 1]
    if "-k" in argv:
        only = argv[argv.index("-k") + 1]
    results = []
    for fn in CASES:
        if only and only not in fn.__name__:
            continue
        t0 = time.monotonic()
        try:
            fn()
            status, detail = "pass", None
            print(f"ok  {fn.finding} {fn.__name__}")
        except AssertionError as e:
            status, detail = "fail", str(e)[:400]
            print(f"FAIL {fn.finding} {fn.__name__}: {detail}")
        except Exception as e:
            status = "error"
            detail = f"{type(e).__name__}: {e}"[:400]
            print(f"ERROR {fn.finding} {fn.__name__}: {detail}")
            traceback.print_exc()
        results.append({"case": fn.__name__, "finding": fn.finding,
                        "status": status, "detail": detail,
                        "seconds": round(time.monotonic() - t0, 3)})
    passed = sum(r["status"] == "pass" for r in results)
    print(f"{passed}/{len(results)} m08 remediation cases passed")
    if out_json:
        pathlib.Path(out_json).write_text(json.dumps({
            "suite": "tests/v2/insertion/test_m08_remediation.py",
            **code_stamp(),
            "results": results, "passed": passed, "total": len(results),
        }, indent=2) + "\n")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
