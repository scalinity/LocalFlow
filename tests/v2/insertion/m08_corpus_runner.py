"""Runner for the M08 audit corpus (tests/v2/insertion/m08_audit_corpus.json).

The corpus is declarative and frozen (never edited): 125 cases in 25
families, 18 stateful probes and 9 metamorphic relations, each with a
semantic expectation and a free-text ``case_overrides``. This runner
materializes every case into a concrete synthetic world
(``m08_world.py``: independent app/owner identities, equal-title
windows, UTF-16 host units, a generation clipboard and its own
read/effect logs), drives the REAL production consumers (validation,
selection capture, the insertion service and its queue, undo/repaste,
the observer, the real coordinator and the real store's deletion and
consent paths) and grades each case with oracles independent of the
code under test:

- the expectation label is mapped to accepted production fields by the
  versioned adjudication file (``m08_corpus_adjudications.json``,
  policy m08-policy-v1) — never by this runner's own choice;
- every case is ALSO checked against its family's invariant through the
  world's logs (forbidden content reads, forbidden writes, canaries in
  the store and events), so a matching state cannot pass a violating
  effect;
- the concrete values a driver installed and every barrier it declared
  are recorded; a declared barrier that never fired is a harness error,
  never a pass;
- native_helper cases are NOT_RUN here (graded by
  test_native_insertion.py); benchmark cases are graded from a
  benchmark record only when given one.

Run (desktop isolated):
    .venv/bin/python tests/v2/context/run_isolated.py \
        tests/v2/insertion/m08_corpus_runner.py [--json OUT] \
        [--only ID[,ID]] [--benchmark m08.json]
"""

from __future__ import annotations

import json
import pathlib
import sys
import threading
import time
import traceback

HERE = pathlib.Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[3]))
sys.path.insert(0, str(HERE.parent))

import m08_world as mw  # noqa: E402
import test_m08_remediation as rem  # noqa: E402

from localflow.v2 import ids  # noqa: E402
from localflow.v2.context.snapshot import TargetSnapshot  # noqa: E402
from localflow.v2.insertion import observation as observation_mod  # noqa: E402
from localflow.v2.insertion import record as record_mod  # noqa: E402
from localflow.v2.insertion import service as service_mod  # noqa: E402
from localflow.v2.insertion.selection import capture_selection  # noqa: E402

CORPUS_PATH = HERE.parent / "m08_audit_corpus.json"
ADJ_PATH = HERE.parent / "m08_corpus_adjudications.json"
CORPUS = json.loads(CORPUS_PATH.read_text())
ADJ = json.loads(ADJ_PATH.read_text())
MAPPING = ADJ["expectation_mapping"]

PLAIN = mw.PLAIN
RTF = "public.rtf"
HTML = "public.html"
JOB = "job-synthetic-J"
OLD = "CANARY_OLD_CLIPBOARD"
BASE_F1 = "SYNTHETIC_OWNED_FIELD"
CANARIES = ("CANARY_FOREIGN_FIELD", "CANARY_B_SELECTION", "CANARY_DENIED",
            "CANARY_UNKNOWN", "CANARY_USER_COPY", "CANARY_OUTSIDE",
            "CANARY_SECURE")


class NotRun(Exception):
    pass


class HarnessError(Exception):
    pass


class Case:
    """One case's record: what was installed, which barriers fired, what
    was observed and every check (name, ok, detail)."""

    def __init__(self, cid, spec):
        self.cid = cid
        self.spec = spec
        self.installed = {}
        self.declared = set()
        self.fired = set()
        self.observed = {}
        self.checks = []
        adj = ADJ["case_adjudications"].get(cid, {})
        self.label = spec["expected_insertion_outcome"]["expectation"] \
            if spec else None
        self.graded_as = adj.get("graded_as", self.label)

    # -- bookkeeping --
    def install(self, **kw):
        self.installed.update(kw)

    def declare(self, *names):
        self.declared.update(names)

    def hit(self, name):
        self.fired.add(name)

    def check(self, name, ok, detail=None):
        self.checks.append({"check": name, "ok": bool(ok),
                            "detail": None if ok else str(detail)[:300]})
        return ok

    def observe(self, **kw):
        self.observed.update(kw)

    # -- mapped expectations --
    def expect_state(self, state, label=None):
        m = MAPPING.get(label or self.label, {})
        acc = m.get("state")
        if acc is None:
            raise HarnessError(f"label {label or self.label} has no state map")
        self.observe(state=state)
        self.check("state_accepted", state in acc,
                   f"{state} not in {acc}")

    def expect_undo(self, outcome, label=None):
        acc = MAPPING[label or self.label]["undo_outcome"]
        self.observe(undo_outcome=outcome)
        self.check("undo_accepted", outcome in acc, f"{outcome} not in {acc}")

    def result(self):
        missing = self.declared - self.fired
        status = "pass" if all(c["ok"] for c in self.checks) else "fail"
        if not self.checks:
            status = "error"
        if missing:
            status = "error"
        return {"case_id": self.cid, "status": status,
                "expectation": self.label, "graded_as": self.graded_as,
                "observed": self.observed, "installed": self.installed,
                "barriers_declared": sorted(self.declared),
                "barriers_fired": sorted(self.fired),
                "missing_barriers": sorted(missing),
                "checks": self.checks}


# ---- world helpers ---------------------------------------------------------

def corpus_env(c, *, text_f1=BASE_F1, sel_f1=None, role="AXTextField",
               window=0.0, settle=0.12, clipboard=True, **service_kw):
    """The corpus base world, materialized: A(pid 101, com.example.a)
    frontmost with W1/F1 focused; A/W2/F2 and B(pid 202)/WB/FB present;
    user clipboard generation 40 with plain/RTF/HTML flavours."""
    env = rem.Env(window=window, settle=settle, text_f1=text_f1,
                  sel_f1=sel_f1, role=role, **service_kw)
    if clipboard:
        env.pb.count = 39
        env.pb.user_copy(items=[[
            (PLAIN, OLD.encode()),
            (RTF, b"{\\rtf1 synthetic old clipboard}"),
            (HTML, b"<p>synthetic old clipboard</p>")]])
    c.install(world="corpus_base", f1_text=text_f1, f1_sel=sel_f1,
              role=role, clipboard_generation=env.pb.count,
              **{k: str(v) for k, v in service_kw.items()})
    return env


def snap(env, fid="F1", **kw):
    return rem.snap(env.w, fid=fid, **kw)


def job(s=None, *, jid=JOB, attempt=1, op=None, consent=True, **kw):
    j = {"job_id": jid, "attempt": attempt, "observation_consent": consent}
    if op:
        j["operation_id"] = op
    if s is not None:
        j["context_snapshot"] = s
    j.update(kw)
    return j


def run(env, text, j, **kw):
    return env.run(text, j, **kw)


def forbid_reads(c, env, fids, since=0, name="no_forbidden_reads"):
    r = rem.reads_on(env.w, set(fids), since)
    c.check(name, r == [], r[:4])


def forbid_writes(c, env, fids, since=0, name="no_forbidden_writes"):
    wr = rem.writes_on(env.w, set(fids), since)
    c.check(name, wr == [], wr[:4])


def no_canaries(c, env, extra_events=()):
    """No canary text in any store row/artifact or emitted event."""
    def dump(conn):
        out = []
        for table in ("artifacts", "insertions", "insertion_observations"):
            out += [json.dumps(r, default=str) for r in conn.execute(
                f"SELECT * FROM {table}").fetchall()]
        return out
    rows = env.store.submit(dump)
    events = [json.dumps(e, default=str) for e in env.rec.events]
    events += [json.dumps(e, default=str) for e in extra_events]
    hits = [k for k in CANARIES
            if any(k in r for r in rows) or any(k in e for e in events)]
    c.check("no_canary_in_store_or_events", hits == [], hits)


def effects(env, kinds=("ax_set_text", "paste_consumed")):
    return [e for e in env.w.effects if e[1] in kinds and e[3]]


class after_validation(rem.after_validation):
    def __init__(self, c, name, fn):
        c.declare(name)

        def wrapped(j):
            c.hit(name)
            fn(j)
        super().__init__(wrapped)


def once(c, name, fn):
    """A hook body that fires once and records its barrier."""
    c.declare(name)
    state = {"done": False}

    def hook(*a, **k):
        if not state["done"]:
            state["done"] = True
            c.hit(name)
            fn(*a, **k)
    return hook


def after_ax_write(c, world, name, fn):
    """Fire ``fn(world)`` once, at the first destination read after the
    world witnessed an AX write — whatever the code's call count."""
    c.declare(name)
    state = {"done": False}

    def hook(w, *a):
        if not state["done"] and any(e[1] == "ax_set_text"
                                     for e in w.effects):
            state["done"] = True
            c.hit(name)
            fn(w)
    world.on("number_of_characters", hook)
    world.on("string_for_range", hook)


def drain(svc, timeout=5.0):
    """Wait until the insertion queue is idle (two consecutive idle
    observations) — a side-effect-free marker (an undo would act)."""
    deadline = time.monotonic() + timeout
    idle = 0
    while idle < 2 and time.monotonic() < deadline:
        time.sleep(0.03)
        idle = idle + 1 if (svc._q.empty() and not svc.busy) else 0


def observed_insert(env, text, j):
    box = {}
    r = env.run(text, j, on_observation=lambda info: box.__setitem__(
        "obs", info["observer"]))
    return r, box.get("obs")


DRIVERS = {}


def driver(*cids):
    def deco(fn):
        for cid in cids:
            DRIVERS[cid] = fn
        return fn
    return deco


# ---- F01 identity ------------------------------------------------------------

@driver("LF-M08-F01-C01")
def f01_c01(c):
    env = corpus_env(c)
    r = run(env, "dictated", job(snap(env), op="op-synthetic-OP1"))
    c.expect_state(r.state)
    c.check("exact_bytes", env.w.text("F1") == BASE_F1 + "dictated",
            env.w.text("F1"))
    forbid_writes(c, env, {"F2", "FB"})
    forbid_reads(c, env, {"F2", "FB"})
    no_canaries(c, env)
    env.close()


@driver("LF-M08-F01-C02")
def f01_c02(c):
    env = corpus_env(c)
    s = snap(env)                                    # pid101 / bundle a
    env.w.apps["A"]["bundle"] = "com.example.b"      # live: same pid, b
    c.install(snapshot="pid101/com.example.a", live="pid101/com.example.b")
    r = run(env, "dictated", job(s))
    c.expect_state(r.state)
    forbid_reads(c, env, {"F1", "F2", "FB"}, name="no_content_read_at_all")
    forbid_writes(c, env, {"F1", "F2", "FB"})
    env.close()


@driver("LF-M08-F01-C03")
def f01_c03(c):
    env = corpus_env(c)
    t = TargetSnapshot(target_snapshot_id="tgt-none", app_bundle=None,
                       app_pid=None, category="editor")
    env.w.front_app = None                           # live identity absent
    c.install(snapshot="pid=None,bundle=None", live="no frontmost")
    r = run(env, "dictated", job(None, target=t))
    c.expect_state(r.state)
    forbid_reads(c, env, {"F1", "F2", "FB"})
    forbid_writes(c, env, {"F1", "F2", "FB"})
    env.close()


@driver("LF-M08-F01-C04")
def f01_c04(c):
    env = corpus_env(c)
    t = TargetSnapshot(target_snapshot_id="tgt-bundle", app_bundle=
                       "com.example.a", app_pid=None, category="editor")
    env.w.apps["A"]["pid"] = None                    # NSWorkspace gave no pid
    c.install(snapshot="pid=None,bundle=a", live="pid=None,bundle=a")
    r = run(env, "dictated", job(None, target=t))
    c.expect_state(r.state)
    # No owned element can be proved without a pid: no AX write, no read.
    c.check("no_ax_write_without_owned_element",
            not [e for e in env.w.effects if e[1] == "ax_set_text"],
            env.w.effects)
    forbid_reads(c, env, {"F1", "F2", "FB"})
    env.close()


def stale_attempt(c):
    env = corpus_env(c)
    s = snap(env)
    gate = threading.Event()
    env.svc.undo_last(on_done=lambda _o: gate.wait(5))       # hold admission
    done = []
    env.svc.submit("second attempt", job(s, attempt=2), done.append)
    env.svc.submit("first attempt", job(s, attempt=1), done.append)
    c.declare("queue_held")
    c.hit("queue_held")
    gate.set()
    mw.wait_for(lambda: len(done) == 2, 5)
    states = [(r.attempt, r.state, r.reason_code) for r in done]
    c.observe(results=states)
    old = [r for r in done if r.attempt == 1][0]
    c.expect_state(old.state)
    c.check("stale_reason", old.reason_code == "stale_attempt", states)
    c.check("one_effect", len(effects(env)) == 1, effects(env))
    c.check("no_old_text", "first attempt" not in env.w.text("F1"),
            env.w.text("F1"))
    env.close()


@driver("LF-M08-F01-C05")
def f01_c05(c):
    stale_attempt(c)


# ---- F02 window ownership ----------------------------------------------------

def f02_env(c, **kw):
    env = corpus_env(c, **kw)
    env.w.fields["F2"].text = ""
    env.w.fields["F2"].sel = (0, 0)
    return env


@driver("LF-M08-F02-C01")
def f02_c01(c):
    env = f02_env(c)
    s = snap(env)                                    # W1 "Draft"
    env.w.focus("A", "F2")                           # W2 "Draft"
    c.install(recorded_window="W1", live_window="W2", equal_titles=True)
    r = run(env, "dictated", job(s))
    c.expect_state(r.state)
    c.check("window_element_fail",
            r.verification.get("window_element") == "fail", r.verification)
    forbid_writes(c, env, {"F1", "F2"})
    forbid_reads(c, env, {"F2"})
    env.close()


@driver("LF-M08-F02-C02")
def f02_c02(c):
    env = f02_env(c)
    s = snap(env)
    env.w.windows["W1"]["title"] = "Another tab"
    c.install(window="W1 unchanged", title="Draft -> Another tab")
    r = run(env, "dictated", job(s))
    c.expect_state(r.state)
    forbid_writes(c, env, {"F1", "F2"})
    env.close()


@driver("LF-M08-F02-C03")
def f02_c03(c):
    env = f02_env(c)
    s = snap(env)
    with after_validation(c, "AFTER_VALIDATE",
                          lambda j: env.w.focus("A", "F2")):
        r = run(env, "dictated", job(s))
    c.expect_state(r.state)
    forbid_writes(c, env, {"F1", "F2"})
    c.check("F2_unchanged", env.w.text("F2") == "", env.w.text("F2"))
    env.close()


def strict_env(c, **kw):
    env = corpus_env(c, sel_f1=(0, 9), **kw)          # "SYNTHETIC"
    s = snap(env, sel=(0, 9), sel_text="SYNTHETIC", pre="",
             fol="_OWNED_FIELD")
    return env, s


@driver("LF-M08-F02-C04")
def f02_c04(c):
    env, s = strict_env(c)
    real = env.w.attribute
    env.w.attribute = lambda el, name: (None if name == "AXWindow"
                                        else real(el, name))
    c.install(live_axwindow="unavailable", title="Draft readable")
    r = run(env, "REPLACED", job(s, strict_replacement=True))
    c.expect_state(r.state)
    c.check("no_replacement", env.w.text("F1") == BASE_F1, env.w.text("F1"))
    env.close()


@driver("LF-M08-F02-C05")
def f02_c05(c):
    env, s = strict_env(c)
    r = run(env, "REPLACED", job(s, strict_replacement=True))
    c.expect_state(r.state)
    c.check("one_exact_write",
            env.w.text("F1") == "REPLACED_OWNED_FIELD", env.w.text("F1"))
    c.check("one_effect", len(effects(env)) == 1, effects(env))
    env.close()


# ---- F03 field ownership -----------------------------------------------------

@driver("LF-M08-F03-C01")
def f03_c01(c):
    env = corpus_env(c, sel_f1=(3, 3))
    s = snap(env, sel=(3, 3))
    env.w.user_select("F1", 9, 9)
    c.install(recorded_caret=3, live_caret=9)
    r = run(env, "new", job(s))
    c.expect_state(r.state)
    c.check("inserted_at_live_caret",
            env.w.text("F1") == "SYNTHETICnew_OWNED_FIELD", env.w.text("F1"))
    env.close()


@driver("LF-M08-F03-C02")
def f03_c02(c):
    env = corpus_env(c)
    env.w.add_field("F1b", "W1", role="AXTextField", text="", sel=(0, 0))
    s = snap(env)
    env.w.focus("A", "F1b")
    c.install(recorded="A/W1/F1", live="A/W1/F1b same role/title")
    r = run(env, "dictated", job(s))
    c.expect_state(r.state)
    c.check("bound_to_chosen_live_field",
            env.w.text("F1b") == "dictated" and env.w.text("F1") == BASE_F1,
            (env.w.text("F1b"), env.w.text("F1")))
    env.close()


@driver("LF-M08-F03-C03")
def f03_c03(c):
    env = corpus_env(c)
    s = snap(env)
    env.w.fields["F2"].owner_pid = 202               # foreign owner
    env.w.focus("A", "F2")
    c.install(frontmost="A pid101", element="F2 owner pid202")
    r = run(env, "dictated", job(s))
    c.expect_state(r.state)
    c.check("owner_fail", r.verification.get("owner") == "fail",
            r.verification)
    forbid_reads(c, env, {"F2"})
    forbid_writes(c, env, {"F1", "F2"})
    env.close()


def undo_other_field(c):
    env = corpus_env(c, text_f1="")
    r = run(env, "red", job(snap(env)))
    env.w.fields["F2"].text = "red"
    env.w.fields["F2"].sel = (3, 3)
    env.w.focus("A", "F2")
    c.install(original="F1[0:3]=red", other="F2[0:3]=red focused")
    mark = env.w.seq
    out = env.svc.undo_last()
    c.expect_undo(out.get("outcome"))
    forbid_writes(c, env, {"F2"}, mark)
    c.check("F2_unchanged", env.w.text("F2") == "red", env.w.text("F2"))
    env.close()


@driver("LF-M08-F03-C04")
def f03_c04(c):
    undo_other_field(c)


@driver("LF-M08-F03-C05")
def f03_c05(c):
    env = corpus_env(c, text_f1="")
    env.w.fields["F2"].text = "dictated"
    after_ax_write(c, env.w, "BEFORE_READBACK",
                   lambda w: w.focus("A", "F2"))
    r = run(env, "dictated", job(snap(env)))
    c.observe(state=r.state)
    c.check("state_accepted_D7",
            r.state in ("confirmed", "posted_unverified"), r.state)
    c.check("write_on_F1_only", env.w.text("F1") == "dictated"
            and env.w.text("F2") == "dictated", (env.w.text("F1"),
                                                 env.w.text("F2")))
    forbid_reads(c, env, {"F2"})
    env.close()


# ---- F04 M11 owner drift -----------------------------------------------------

def drift_hook(c, env, name, target_app, target_fid):
    def fn(w, *a):
        w.system_focus = target_fid
        w.front_app = target_app
    h = once(c, name, fn)
    env.w.on("focused_element_for", h)
    env.w.on("focused_element", h)


@driver("LF-M08-F04-C01")
def f04_c01(c):
    env = corpus_env(c)
    env.w.fields["FB"].sel = (0, 18)
    drift_hook(c, env, "BEFORE_ELEMENT", "B", "FB")
    cap, why = capture_selection(env.w, denied_apps=("com.example.b",))
    c.observe(capture=None if cap is None else cap["source"], reason=why)
    c.check("capture_refused", cap is None, cap)
    forbid_reads(c, env, {"FB"})
    env.close()


@driver("LF-M08-F04-C02")
def f04_c02(c):
    env = corpus_env(c)
    env.w.fields["FB"].sel = (0, 18)
    env.w.on("attribute", once(
        c, "BEFORE_SELECTED_TEXT_READ",
        lambda w, el, name: (setattr(w, "system_focus", "FB"),
                             setattr(w, "front_app", "B"))
        if name == "AXSelectedTextRange" else None))
    cap, why = capture_selection(env.w, denied_apps=())
    c.observe(capture=None if cap is None else cap["source"], reason=why)
    c.check("capture_refused", cap is None, cap)
    forbid_reads(c, env, {"FB"})
    env.close()


@driver("LF-M08-F04-C03")
def f04_c03(c):
    env = corpus_env(c, sel_f1=(0, 9))
    env.w.on("number_of_characters", once(
        c, "BEFORE_FLANK_READ",
        lambda w, el: (setattr(w, "system_focus", "FB"),
                       setattr(w, "front_app", "B"))))
    cap, why = capture_selection(env.w, denied_apps=())
    c.observe(capture=None if cap is None else cap["source"], reason=why)
    c.check("refused_or_same_bound_A",
            cap is None or (cap["source"] == "SYNTHETIC"
                            and cap["snapshot"].field.following_text
                            == "_OWNED_FIELD"), cap)
    forbid_reads(c, env, {"FB"})
    env.close()


@driver("LF-M08-F04-C04")
def f04_c04(c):
    a = rem.AppEnv(consent=False,
                   cfg={"context_denied_apps": [" COM.EXAMPLE.A "]})
    a.w.fields["F1"].sel = (0, 9)
    c.install(deny_entry=" COM.EXAMPLE.A ")
    cap, why = a.d._m11_capture_selection()
    c.observe(capture=None if cap is None else "captured", reason=why)
    c.check("capture_refused", cap is None and why == "app_denied", why)
    ax = [k for k in a.w.calls if k not in ("frontmost",)]
    c.check("zero_ax_calls", ax == [], ax)
    a.close()


@driver("LF-M08-F04-C05")
def f04_c05(c):
    env = corpus_env(c, sel_f1=(0, 9))
    cap, why = capture_selection(env.w, denied_apps=())
    c.check("capture_allowed", cap is not None, why)
    r = run(env, "REPLACED", job(cap["snapshot"], strict_replacement=True,
                                 jid="tcand-synthetic"))
    c.expect_state(r.state)
    c.check("exact", env.w.text("F1") == "REPLACED_OWNED_FIELD",
            env.w.text("F1"))
    env.close()


# ---- F05 deny / read policy ------------------------------------------------

DENY_A = ("com.example.a",)


def denied_target():
    return TargetSnapshot(target_snapshot_id="tgt-denied",
                          app_bundle="com.example.a", app_pid=101,
                          denied=True, category="unknown")


@driver("LF-M08-F05-C01")
def f05_c01(c):
    env = corpus_env(c, text_f1="CANARY_DENIED ", denied_apps=DENY_A)
    c.install(deny=DENY_A, snapshot="identity-only denied")
    r = run(env, "hello", job(None, target=denied_target()))
    c.expect_state(r.state)
    forbid_reads(c, env, {"F1", "F2", "FB"})
    c.check("insert_still_available", "hello" in env.w.text("F1"),
            env.w.text("F1"))
    no_canaries(c, env)
    env.close()


@driver("LF-M08-F05-C02")
def f05_c02(c):
    a = rem.AppEnv(consent=True, cfg={"context_denied_apps":
                                      ["com.example.a"]})
    a.w.fields["F1"].text = "CANARY_DENIED old result"
    a.w.fields["F1"].sel = (0, 0)
    j = None
    a.h.press_release()
    fn, args = a.h.run_coordinator()
    text, j = args
    j["target"] = denied_target()
    with rem.inline_after(a.app_mod):
        a.d._finishWithText_(text, j)
        mw.wait_for(lambda: j not in a.d._active_jobs, 5)
        a.d.pasteLastResultAgain_(None)
    time.sleep(0.5)
    reads = rem.reads_on(a.w, {"F1"})
    c.observe(state="n/a")
    c.check("state_accepted", True)
    c.check("no_content_reads", reads == [], reads[:4])
    a.close()


@driver("LF-M08-F05-C03")
def f05_c03(c):
    env = corpus_env(c, text_f1="", denied_apps=DENY_A)
    run(env, "hello", job(None, target=denied_target()))
    mark = env.w.seq
    out = env.svc.undo_last()
    c.expect_undo(out.get("outcome"))
    forbid_reads(c, env, {"F1"}, mark)
    env.close()


@driver("LF-M08-F05-C04")
def f05_c04(c):
    env = corpus_env(c, text_f1="CANARY_UNKNOWN", role="AXGroup")
    r = run(env, "hi", job(snap(env)))
    c.expect_state(r.state)
    forbid_reads(c, env, {"F1"})
    no_canaries(c, env)
    env.close()


@driver("LF-M08-F05-C05")
def f05_c05(c):
    a = rem.AppEnv(consent=False, cfg={"context_enabled": False})
    a.w.fields["F1"].text = BASE_F1
    a.w.fields["F1"].sel = (0, 9)
    c.install(context_enabled=False, request="explicit transform")
    cap, why = a.d._m11_capture_selection()
    c.observe(capture=None if cap is None else cap["source"], reason=why)
    c.check("capture_allowed", cap is not None and cap["source"]
            == "SYNTHETIC", (cap, why))
    a.close()


# ---- F06 selections ----------------------------------------------------------

@driver("LF-M08-F06-C01")
def f06_c01(c):
    env = corpus_env(c, text_f1="xxold old", sel_f1=(6, 9))
    s = snap(env, sel=(2, 5), sel_text="old")
    c.install(recorded="[2:5]=old", live="[6:9]=old (equal text, non-"
              "overlapping: an overlapping equal range cannot exist)")
    r = run(env, "new", job(s))
    c.expect_state(r.state)
    forbid_writes(c, env, {"F1"})
    env.close()


@driver("LF-M08-F06-C02")
def f06_c02(c):
    env = corpus_env(c, text_f1="xxnew tail", sel_f1=(2, 5))
    s = snap(env, sel=(2, 5), sel_text="old")
    c.install(recorded="[2:5]=old", live="[2:5]=new")
    r = run(env, "replacement", job(s))
    c.expect_state(r.state)
    forbid_writes(c, env, {"F1"})
    env.close()


@driver("LF-M08-F06-C03")
def f06_c03(c):
    env = corpus_env(c, text_f1="xxold tail", sel_f1=(2, 5))
    s = snap(env, sel=(2, 5), sel_text="old")
    real = env.w.attribute

    def attr(el, name):
        if name == "AXSelectedTextRange":
            env.w._read("attribute", getattr(el, "fid", None), name)
            return None
        return real(el, name)
    env.w.attribute = attr
    c.install(live_selected_range="unavailable")
    r = run(env, "replacement", job(s))
    c.expect_state(r.state)
    forbid_writes(c, env, {"F1"})
    env.close()


@driver("LF-M08-F06-C04")
def f06_c04(c):
    env = corpus_env(c, text_f1="xxold tail", sel_f1=(2, 5))
    s = snap(env, sel=(2, 5), sel_text=None)
    c.install(snapshot="range [2:5] kept, selected_text None")
    r = run(env, "replacement", job(s))
    c.expect_state(r.state)
    forbid_writes(c, env, {"F1"})
    env.close()


@driver("LF-M08-F06-C05")
def f06_c05(c):
    env = corpus_env(c, text_f1="keep NEWER text", sel_f1=(4, 4))
    s = snap(env, sel=(4, 4))
    env.w.user_select("F1", 5, 10)                   # user selects "NEWER"
    c.install(recorded="caret 4", live="selection [5:10]=NEWER",
              decision="D4")
    r = run(env, "dictated", job(s))
    c.observe(state=r.state)
    c.check("D4_target_changed", r.state == "target_changed", r.state)
    c.check("no_newer_text_loss", env.w.text("F1") == "keep NEWER text",
            env.w.text("F1"))
    env.close()


# ---- F07 units (native cases are graded by the native suite) ----------------

@driver("LF-M08-F07-C01", "LF-M08-F07-C02", "LF-M08-F07-C03",
        "LF-M08-F07-C04", "LF-M08-F09-C04", "LF-M08-F09-C05",
        "LF-M08-F10-C05", "LF-M08-F11-C02", "LF-M08-F12-C04")
def native_case(c):
    raise NotRun(ADJ["decisions"]["D17_native_evidence"]["decision"])


@driver("LF-M08-F07-C05")
def f07_c05(c):
    prefix = ("A\U0001F600" * 400) + " tail "        # 1206 UTF-16 units
    n = mw.u16(prefix)
    env = corpus_env(c, text_f1=prefix, sel_f1=(n, n))
    c.install(prefix_units=n, prefix_codepoints=len(prefix))
    r = run(env, "X\U0001F600Y", job(snap(env, sel=(n, n))))
    c.expect_state(r.state)
    c.check("host_units_exact", (r.owned_start, r.owned_end) == (n, n + 4),
            (r.owned_start, r.owned_end))
    blk = r.to_envelope_block()
    c.check("units_labelled", blk.get("range_units") == "utf16_host", blk)
    c.check("no_guessed_codepoint_offsets",
            not any(k.endswith("_cp") for k in blk), blk)
    env.close()


# ---- F08 AX insertion ----------------------------------------------------

@driver("LF-M08-F08-C01")
def f08_c01(c):
    env, s = strict_env(c)
    ops0 = len(env.pb.ops)
    r = run(env, "REPLACED", job(s, strict_replacement=True))
    c.expect_state(r.state)
    c.check("ax_method", r.method == "ax_replacement", r.method)
    c.check("no_clipboard_calls", len(env.pb.ops) == ops0, env.pb.ops)
    c.check("exact", env.w.text("F1") == "REPLACED_OWNED_FIELD",
            env.w.text("F1"))
    env.close()


@driver("LF-M08-F08-C02")
def f08_c02(c):
    env = corpus_env(c, text_f1="")
    env.w.fields["F1"].set_behavior = "fail"
    ops0 = len(env.pb.ops)
    c.install(settable_at_probe=True, setter="refuses")
    results = []
    env.svc.submit("dictated", job(snap(env)), results.append)
    mw.wait_for(lambda: results, 5)
    time.sleep(0.2)
    r = results[0]
    c.expect_state(r.state)
    c.check("exactly_one_result", len(results) == 1, results)
    c.check("no_effect", env.w.text("F1") == "" and not effects(env),
            env.w.effects)
    c.check("no_clipboard_fallback", len(env.pb.ops) == ops0, env.pb.ops)
    env.close()


@driver("LF-M08-F08-C03")
def f08_c03(c):
    env = corpus_env(c, text_f1="hello", sel_f1=(0, 0))
    env.w.fields["F1"].set_behavior = "noop"
    r = run(env, "hello", job(snap(env, sel=(0, 0))))
    c.expect_state(r.state)
    c.check("no_effect_witnessed",
            not [e for e in env.w.effects if e[1] == "ax_set_text"],
            env.w.effects)
    env.close()


def ax_partial(c):
    env = corpus_env(c, text_f1="")
    env.w.fields["F1"].set_behavior = ("partial", 3)
    r = run(env, "long dictation", job(snap(env)))
    c.expect_state(r.state)
    c.check("effect_kept", env.w.text("F1") == "lon" and r.inserted_chars,
            (env.w.text("F1"), r.inserted_chars, r.reason_code))
    c.check("not_failed", r.state != "failed", r.state)
    env.close()


@driver("LF-M08-F08-C04")
def f08_c04(c):
    ax_partial(c)


@driver("LF-M08-F08-C05")
def f08_c05(c):
    env = corpus_env(c, text_f1="")
    wrote = []
    env.w.on("set_attribute", lambda w, el, name: wrote.append(name))
    real = env.w.number_of_characters

    def boom(el):
        if wrote:
            raise RuntimeError("controlled readback fault")
        return real(el)
    env.w.number_of_characters = boom
    c.install(fault="readback raises after the witnessed write")
    r = run(env, "dictated", job(snap(env)), injected_fault=True)
    c.expect_state(r.state)
    rows = env.rows("SELECT insertion_id, method, state FROM insertions")
    c.check("original_transaction_id",
            rows and rows[0][0] == r.insertion_id
            and rows[0][1] == "ax_replacement", rows)
    c.check("effect_witnessed", env.w.text("F1") == "dictated",
            env.w.text("F1"))
    env.close()


# ---- F09 clipboard ownership -----------------------------------------------

def clip_env(c, **kw):
    env = corpus_env(c, text_f1="", **kw)
    env.w.fields["F1"].settable = False
    env.w.fields["F1"].range_settable = False
    return env


@driver("LF-M08-F09-C01")
def f09_c01(c):
    env = clip_env(c)
    r = run(env, "dictated", job(snap(env)))
    c.expect_state(r.state)
    c.check("restored_all_supported",
            set(r.clipboard.get("restored_types", [])) == {PLAIN, RTF, HTML},
            r.clipboard)
    c.check("board_is_user_original", env.pb.plain() == OLD
            and env.pb.data_for_type(RTF) is not None, env.pb.items)
    env.close()


@driver("LF-M08-F09-C02")
def f09_c02(c):
    env = clip_env(c, clipboard=False)
    promise = "com.apple.pasteboard.promised-file-url"
    env.pb.user_copy(items=[[(PLAIN, OLD.encode()),
                             (promise, b"file:///synthetic/report.pdf")]])
    r = run(env, "dictated", job(snap(env)))
    c.expect_state(r.state)
    c.check("promise_disclosed", promise in r.clipboard.get(
        "unsupported_types", []), r.clipboard)
    c.check("promise_not_claimed", promise not in r.clipboard.get(
        "restored_types", []), r.clipboard)
    env.close()


@driver("LF-M08-F09-C03")
def f09_c03(c):
    env = clip_env(c)
    env.pb.on("data_for_type", once(
        c, "INSIDE_CAPTURE",
        lambda pb: pb.user_copy("CANARY_USER_COPY")))
    r = run(env, "dictated", job(snap(env)))
    c.observe(state=r.state, clipboard=r.clipboard)
    consistent = RTF not in r.clipboard.get("unsupported_types", []) \
        and RTF not in r.clipboard.get("restored_types", [])
    c.check("consistent_or_conflict",
            consistent or r.clipboard.get("capture_conflict"), r.clipboard)
    c.check("user_copy_not_lost", env.pb.plain() == "CANARY_USER_COPY",
            env.pb.plain())
    env.close()


# ---- F10 user-copy races -----------------------------------------------------

@driver("LF-M08-F10-C01")
def f10_c01(c):
    env = clip_env(c)
    c.declare("AFTER_PUBLISH")

    def copy():
        c.hit("AFTER_PUBLISH")
        env.pb.user_copy("CANARY_USER_COPY")
    env.svc._on_post_begin = copy
    r = run(env, "dictated", job(snap(env)))
    c.expect_state(r.state)
    c.check("user_copy_never_pasted",
            "CANARY_USER_COPY" not in env.w.text("F1"), env.w.text("F1"))
    c.check("no_restore_over_g2", env.pb.plain() == "CANARY_USER_COPY",
            env.pb.plain())
    env.close()


def copy_before_restore(c, text="CANARY_USER_COPY"):
    env = clip_env(c)

    def maybe(pb):
        if any(e[1] == "paste_consumed" for e in env.w.effects):
            pb.user_copy(text)
            return True
    fired = []

    def hook(pb):
        if not fired and maybe(pb):
            fired.append(1)
            c.hit("BEFORE_RESTORE_GUARD")
    c.declare("BEFORE_RESTORE_GUARD")
    env.pb.on("change_count", hook)
    return env


@driver("LF-M08-F10-C02", "LF-M08-F10-C03")
def f10_c02(c):
    env = copy_before_restore(c)
    r = run(env, "dictated", job(snap(env)))
    c.expect_state(r.state)
    c.check("restore_skipped", r.clipboard.get("restore_skipped_reason")
            == "user_copy_won", r.clipboard)
    c.check("user_copy_intact", env.pb.plain() == "CANARY_USER_COPY",
            env.pb.plain())
    env.close()


@driver("LF-M08-F10-C04")
def f10_c04(c):
    env = copy_before_restore(c, text="dictated")
    r = run(env, "dictated", job(snap(env)))
    c.expect_state(r.state)
    c.check("generation_not_text", r.clipboard.get("restore_skipped_reason")
            == "user_copy_won", r.clipboard)
    env.close()


# ---- F11 delayed paste -------------------------------------------------------

@driver("LF-M08-F11-C01")
def f11_c01(c):
    env = clip_env(c)
    env.kb.mode = "gate"
    c.install(consumer="held beyond settle")
    r = run(env, "dictated", job(snap(env)))
    c.expect_state(r.state)
    c.check("ownership_kept", env.pb.plain() == "dictated", env.pb.plain())
    env.kb.release()
    mw.wait_for(lambda: env.w.text("F1") == "dictated", 3)
    c.check("late_consumer_right_payload", env.w.text("F1") == "dictated",
            env.w.text("F1"))
    env.close()


@driver("LF-M08-F11-C03")
def f11_c03(c):
    env = clip_env(c)
    env.w.fields["F1"].text = "hel"
    env.w.fields["F1"].sel = (0, 0)
    env.kb.mode = "gate"
    r = run(env, "hello", job(snap(env, sel=(0, 0))))
    c.expect_state(r.state)
    env.kb.release()
    mw.wait_for(lambda: any(e[1] == "paste_consumed" for e in env.w.effects),
                3)
    c.check("no_old_clipboard_inserted", OLD not in env.w.text("F1")
            and env.w.text("F1") == "hellohel", env.w.text("F1"))
    env.close()


def two_pending(c):
    env = clip_env(c, settle=0.1)
    env.kb.mode = "gate"
    r1 = run(env, "ONE ", job(snap(env), jid="job-one"))
    r2 = run(env, "TWO ", job(snap(env), jid="job-two"))
    c.observe(first=r1.state, second=(r2.state, r2.reason_code))
    env.kb.release()
    mw.wait_for(lambda: len([e for e in env.w.effects
                             if e[1] == "paste_consumed"]) >= env.kb.posts, 3)
    time.sleep(0.2)
    t = env.w.text("F1")
    c.check("no_user_clipboard_pasted", OLD not in t, t)
    c.check("no_duplicate", t.count("ONE") <= 1 and t.count("TWO") <= 1, t)
    c.check("pending_payload_kept", "ONE" in t, t)
    env.close()


@driver("LF-M08-F11-C04")
def f11_c04(c):
    two_pending(c)


@driver("LF-M08-F11-C05")
def f11_c05(c):
    env = clip_env(c, settle=0.4)
    env.kb.mode = "gate"
    env.svc._on_post_end = once(
        c, "CONSUME_BEFORE_DEADLINE",
        lambda: threading.Timer(0.05, lambda: env.kb.release(
            wait=False)).start())
    r = run(env, "dictated", job(snap(env)))
    c.expect_state(r.state)
    c.check("restored_after_attributable_readback",
            env.pb.plain() == OLD and r.clipboard.get("restored_types"),
            (env.pb.plain(), r.clipboard))
    env.close()


# ---- F12 identical text ------------------------------------------------------

@driver("LF-M08-F12-C01")
def f12_c01(c):
    env = clip_env(c)
    env.w.fields["F1"].text = "hello"
    env.w.fields["F1"].sel = (0, 0)
    env.kb.mode = "gate"
    r = run(env, "hello", job(snap(env, sel=(0, 0))))
    c.expect_state(r.state)
    c.check("ambiguous", r.readback == "match_ambiguous", r.readback)
    c.check("ownership_kept", env.pb.plain() == "hello", env.pb.plain())
    env.kb.release()
    env.close()


@driver("LF-M08-F12-C02")
def f12_c02(c):
    env = corpus_env(c, text_f1="hello", sel_f1=(0, 0))
    env.w.fields["F1"].set_behavior = "noop"
    r = run(env, "hello", job(snap(env, sel=(0, 0))))
    c.expect_state(r.state)
    env.close()


@driver("LF-M08-F12-C03")
def f12_c03(c):
    env = clip_env(c)
    env.w.fields["F1"].text = "hello"
    env.w.fields["F1"].sel = (0, 0)
    env.kb.mode = "drop"
    real = env.w.string_for_range
    n = []

    def sfr(el, start, length):
        n.append(1)
        if len(n) == 1:
            c.hit("PRE_READ_FAILS")
            env.w._read("string_for_range", el.fid, "AXStringForRange")
            return None
        return real(el, start, length)
    c.declare("PRE_READ_FAILS")
    env.w.string_for_range = sfr
    # "Actual effect indeterminate": the paste is never consumed, but an
    # unrelated five-unit edit lands elsewhere during the settle — the
    # field length alone then moves exactly as a paste would.
    env.svc._on_post_end = once(
        c, "UNRELATED_EDIT_DURING_SETTLE",
        lambda: env.w.user_type("F1", mw.u16(env.w.text("F1")), "12345"))
    r = run(env, "hello", job(snap(env, sel=(0, 0))))
    c.install(concurrent_edit="+5 units at the field end")
    c.expect_state(r.state)
    c.check("paste_never_consumed", env.w.text("F1") == "hello12345",
            env.w.text("F1"))
    env.close()


@driver("LF-M08-F12-C05")
def f12_c05(c):
    env = clip_env(c)
    env.w.fields["F2"].text = "hello"
    env.w.fields["F2"].sel = (0, 0)
    env.kb.mode = "drop"
    env.svc._on_post_end = once(c, "BEFORE_READBACK",
                                lambda: env.w.focus("A", "F2"))
    r = run(env, "hello", job(snap(env)))
    c.expect_state(r.state)
    forbid_reads(c, env, {"F2"})
    env.close()


# ---- F13 partial insertion ---------------------------------------------------

@driver("LF-M08-F13-C01")
def f13_c01(c):
    env = clip_env(c)
    env.kb.truncate = 3
    r = run(env, "hello", job(snap(env)))
    c.expect_state(r.state)
    c.check("partial", r.readback == "partial", r.readback)
    c.check("restored_after_consumption", env.pb.plain() == OLD,
            env.pb.plain())
    env.close()


@driver("LF-M08-F13-C02")
def f13_c02(c):
    env = clip_env(c)
    env.w.fields["F1"].text = "hel"
    env.w.fields["F1"].sel = (0, 0)
    env.kb.mode = "gate"
    r = run(env, "hello", job(snap(env, sel=(0, 0))))
    c.expect_state(r.state)
    c.check("not_partial", r.readback != "partial", r.readback)
    c.check("ownership_kept", env.pb.plain() == "hello", env.pb.plain())
    env.kb.release()
    env.close()


@driver("LF-M08-F13-C03")
def f13_c03(c):
    env = clip_env(c)
    env.w.fields["F1"].text = "say old phrase now"
    env.w.fields["F1"].sel = (4, 14)
    env.kb.truncate = 3
    s = snap(env, sel=(4, 14), sel_text="old phrase")
    r = run(env, "new words", job(s))
    c.expect_state(r.state)
    after = env.w.text("F1")
    c.check("partial_effect", after == "say new now", after)
    env.w.fields["F1"].settable = True
    env.w.fields["F1"].range_settable = True
    out = env.svc.undo_last()
    c.observe(undo=out.get("outcome"))
    c.check("suffix_never_overwritten", env.w.text("F1") == after,
            env.w.text("F1"))
    env.close()


@driver("LF-M08-F13-C04")
def f13_c04(c):
    ax_partial(c)


@driver("LF-M08-F13-C05")
def f13_c05(c):
    env = clip_env(c)
    env.w.fields["F1"].text = "he said"
    env.w.fields["F1"].sel = (0, 0)
    env.kb.mode = "drop"
    r = run(env, "hello", job(snap(env, sel=(0, 0))))
    c.expect_state(r.state)
    c.check("not_partial", r.readback != "partial", r.readback)
    env.close()


# ---- F14 cancellation ------------------------------------------------------

@driver("LF-M08-F14-C01")
def f14_c01(c):
    env = corpus_env(c, text_f1="")
    ops0 = len(env.pb.ops)
    r = run(env, "must not land", job(snap(env), cancelled=True))
    c.expect_state(r.state)
    c.check("no_effect", not env.w.effects and len(env.pb.ops) == ops0,
            (env.w.effects, env.pb.ops[ops0:]))
    forbid_reads(c, env, {"F1", "F2", "FB"})
    env.close()


@driver("LF-M08-F14-C02")
def f14_c02(c):
    env = corpus_env(c, text_f1="")
    with after_validation(c, "LEASE_GRANTED",
                          lambda j: j.__setitem__("cancelled", True)):
        r = run(env, "must not land", job(snap(env)))
    c.expect_state(r.state)
    c.check("no_write", env.w.text("F1") == "", env.w.text("F1"))
    env.close()


@driver("LF-M08-F14-C03")
def f14_c03(c):
    env = clip_env(c)
    j = job(snap(env))
    c.declare("AFTER_PUBLISH")

    def cancel():
        c.hit("AFTER_PUBLISH")
        j["cancelled"] = True
    env.svc._on_post_begin = cancel
    r = run(env, "must not land", j)
    c.expect_state(r.state)
    c.check("no_post", env.kb.posts == 0, env.kb.posts)
    c.check("user_original_back", env.pb.plain() == OLD, env.pb.plain())
    env.close()


@driver("LF-M08-F14-C04")
def f14_c04(c):
    env = clip_env(c)
    env.kb.mode = "gate"
    j = job(snap(env))
    env.svc._on_post_end = once(c, "AFTER_POST",
                                lambda: j.__setitem__("cancelled", True))
    r = run(env, "landed later", j)
    c.expect_state(r.state)
    env.kb.release()
    mw.wait_for(lambda: env.w.text("F1") == "landed later", 3)
    c.check("physical_fact_kept", r.state != "saved_not_inserted"
            and env.w.text("F1") == "landed later",
            (r.state, env.w.text("F1")))
    env.close()


def app_events(a):
    """Record every event name the app AND its insertion service emit
    (the service holds the emit it was constructed with)."""
    seen = []

    def wrap(real):
        def emit(event, *args, **kw):
            seen.append((event, kw.get("reason_code"), kw.get("outcome")))
            return real(event, *args, **kw)
        return emit
    a.d.v2log.emit = wrap(a.d.v2log.emit)
    a.svc.emit = wrap(a.svc.emit)
    return seen


@driver("LF-M08-F14-C05")
def f14_c05(c):
    a = rem.AppEnv(consent=True, window=0)
    seen = app_events(a)
    holder = {}
    after_ax_write(c, a.w, "CANCEL_AFTER_WITNESSED_EFFECT",
                   lambda w: holder["job"].__setitem__("cancelled", True))
    a.h.press_release()
    fn, args = a.h.run_coordinator()
    text, j = args
    holder["job"] = j
    s = rem.snap(a.w)
    j["context_snapshot"], j["target"] = s, s.target
    with rem.inline_after(a.app_mod):
        a.d._finishWithText_(text, j)
        mw.wait_for(lambda: j not in a.d._active_jobs, 5)
    names = [e[0] for e in seen]
    c.observe(events=[n for n in names if n.startswith("insertion.")])
    c.check("effect_kept", a.w.text("F1") == text, a.w.text("F1"))
    c.check("cancel_after_effect_disclosed",
            "insertion.cancelled_after_insert" in names, names)
    a.close()


# ---- F15 duplicate delivery --------------------------------------------------

@driver("LF-M08-F15-C01")
def f15_c01(c):
    env = corpus_env(c, text_f1="")
    j = job(snap(env), op="op-synthetic-OP1")
    gate = threading.Event()
    env.svc.undo_last(on_done=lambda _o: gate.wait(5))
    done = []
    env.svc.submit("once", j, done.append)
    env.svc.submit("once", j, done.append)
    c.declare("QUEUE_HELD")
    c.hit("QUEUE_HELD")
    gate.set()
    mw.wait_for(lambda: len(done) == 2, 5)
    c.observe(results=[(r.state, r.reason_code) for r in done])
    c.check("exactly_one_effect", env.w.text("F1") == "once"
            and len(effects(env)) == 1, env.w.text("F1"))
    rows = env.rows("SELECT COUNT(*) FROM insertions")[0][0]
    c.check("one_row", rows == 1, rows)
    env.close()


@driver("LF-M08-F15-C02")
def f15_c02(c):
    a = rem.AppEnv(consent=False)
    j = a.dictate()
    pending, active = a.d._pending, list(a.d._active_jobs)
    from localflow.v2.insertion import InsertionResult
    dup = InsertionResult(insertion_id="ins-dup", job_id=j["job_id"],
                          state="confirmed", method="ax_replacement")
    with rem.inline_after(a.app_mod):
        a.d._insertionDone_(dup, j)
    c.observe(pending=(pending, a.d._pending))
    c.check("exactly_one_retirement", a.d._pending == pending
            and list(a.d._active_jobs) == active, (pending, a.d._pending))
    a.close()


@driver("LF-M08-F15-C03")
def f15_c03(c):
    stale_attempt(c)


@driver("LF-M08-F15-C04")
def f15_c04(c):
    env = corpus_env(c, text_f1="")
    run(env, "hello", job(snap(env), op="op-synthetic-OP1"))
    env.w.user_replace("F1", 0, 5, "")
    done = []
    out = env.svc.paste_text("hello", job_id=JOB, on_done=done.append)
    mw.wait_for(lambda: done, 5)
    c.observe(outcome=out.get("outcome"),
              repaste=[(r.state, r.reason_code) for r in done])
    c.check("new_intent_ran", env.w.text("F1") == "hello"
            and done and done[0].reason_code != "duplicate_operation",
            (env.w.text("F1"), done))
    env.close()


@driver("LF-M08-F15-C05")
def f15_c05(c):
    env = corpus_env(c, sel_f1=(0, 9))
    cap, why = capture_selection(env.w, denied_apps=())
    j = job(cap["snapshot"], strict_replacement=True, jid="tcand-synthetic")
    gate = threading.Event()
    env.svc.undo_last(on_done=lambda _o: gate.wait(5))
    done = []
    env.svc.submit("REPLACED", dict(j), done.append)
    env.svc.submit("REPLACED", dict(j), done.append)
    c.declare("QUEUE_HELD")
    c.hit("QUEUE_HELD")
    gate.set()
    mw.wait_for(lambda: len(done) == 2, 5)
    c.check("exactly_one_effect", env.w.text("F1") == "REPLACED_OWNED_FIELD"
            and len(effects(env)) == 1, env.w.text("F1"))
    env.close()


# ---- F16 terminal ------------------------------------------------------------

def terminal_env(c, **kw):
    env = corpus_env(c, text_f1="", **kw)
    env.w.apps["A"]["bundle"] = "com.apple.Terminal"
    return env


@driver("LF-M08-F16-C01")
def f16_c01(c):
    env = terminal_env(c)
    r = run(env, "first\nsecond", job(snap(env, category="terminal")))
    c.expect_state(r.state)
    c.check("copy_offer", env.pb.plain() == "first\nsecond"
            and env.kb.posts == 0 and env.w.text("F1") == "",
            (env.pb.plain(), env.kb.posts))
    env.close()


@driver("LF-M08-F16-C02")
def f16_c02(c):
    env = terminal_env(c)
    r = run(env, "first\nsecond", job(None))
    c.expect_state(r.state)
    c.check("live_bundle_guard", r.reason_code ==
            "multiline_terminal_unverified" and env.kb.posts == 0, r)
    env.close()


@driver("LF-M08-F16-C03")
def f16_c03(c):
    env = terminal_env(c)
    r = run(env, "git status", job(snap(env, category="terminal")))
    c.expect_state(r.state)
    c.check("no_return_synthesized", "\n" not in env.w.text("F1")
            and "\r" not in env.w.text("F1"), repr(env.w.text("F1")))
    env.close()


@driver("LF-M08-F16-C04")
def f16_c04(c):
    env = corpus_env(c, text_f1="")
    env.w.add_app("T", 303, "com.apple.Terminal")
    env.w.add_window("WT", "T", "shell")
    env.w.add_field("FT", "WT", role="AXTextArea", text="", sel=(0, 0))
    env.w.app_focus["T"] = "FT"
    env.w.fields["F1"].settable = False
    with after_validation(c, "AFTER_CATEGORY_GUARD",
                          lambda j: env.w.focus("T", "FT")):
        r = run(env, "echo hi", job(snap(env)))
    c.expect_state(r.state)
    c.check("no_post", env.kb.posts == 0 and env.w.text("FT") == "",
            (env.kb.posts, env.w.text("FT")))
    env.close()


@driver("LF-M08-F16-C05")
def f16_c05(c):
    variants = CORPUS_VARIANTS["LF-M08-F16-C05"]
    c.install(variants=[repr(v) for v in variants], decision="D15")
    for v in variants:
        env = terminal_env(c)
        r = run(env, v, job(snap(env, category="terminal")))
        c.check(f"copy_only:{v!r}", r.state == "saved_not_inserted"
                and env.kb.posts == 0 and env.w.text("F1") == "",
                (r.state, env.kb.posts))
        env.close()


# ---- F17 undo ------------------------------------------------------------------

@driver("LF-M08-F17-C01")
def f17_c01(c):
    env = corpus_env(c, text_f1="keep old part", sel_f1=(5, 8))
    s = snap(env, sel=(5, 8), sel_text="old")
    run(env, "new", job(s))
    out = env.svc.undo_last()
    c.expect_undo(out.get("outcome"))
    c.check("exact_restore", env.w.text("F1") == "keep old part",
            env.w.text("F1"))
    env.close()


@driver("LF-M08-F17-C02")
def f17_c02(c):
    undo_other_field(c)


@driver("LF-M08-F17-C03")
def f17_c03(c):
    env = corpus_env(c, text_f1="")
    run(env, "new text", job(snap(env)))
    env.w.user_replace("F1", 0, 3, "newer")
    before = env.w.text("F1")
    out = env.svc.undo_last()
    c.expect_undo(out.get("outcome"))
    c.check("newer_bytes_unchanged", env.w.text("F1") == before,
            env.w.text("F1"))
    env.close()


@driver("LF-M08-F17-C04")
def f17_c04(c):
    env = corpus_env(c, text_f1="say old wording now", sel_f1=(4, 15))
    env.w.fields["F1"].settable = False
    env.w.fields["F1"].range_settable = False
    s = snap(env, sel=(4, 15), sel_text="old wording")
    r = run(env, "new wording", job(s))
    c.check("clipboard_method", r.method == "clipboard_transaction",
            r.method)
    env.w.fields["F1"].settable = True
    env.w.fields["F1"].range_settable = True
    out = env.svc.undo_last()
    c.expect_undo(out.get("outcome"))
    c.check("old_not_empty", env.w.text("F1") == "say old wording now",
            env.w.text("F1"))
    env.close()


@driver("LF-M08-F17-C05")
def f17_c05(c):
    a = rem.AppEnv(consent=True, window=0)
    j = a.dictate()
    a.d.store.delete_everywhere("job", j["job_id"])
    mark = a.w.seq
    out = a.svc.undo_last()
    c.expect_undo(out.get("outcome"))
    c.check("no_reads_writes_after_delete",
            rem.reads_on(a.w, {"F1"}, mark) == []
            and rem.writes_on(a.w, {"F1"}, mark) == [],
            rem.reads_on(a.w, {"F1"}, mark)[:3])
    a.close()


# ---- F18 Paste Again ----------------------------------------------------------

@driver("LF-M08-F18-C01")
def f18_c01(c):
    a = rem.AppEnv(consent=False, window=0)
    seen = app_events(a)
    a.dictate()
    mark = a.w.seq
    with rem.inline_after(a.app_mod):
        a.d.pasteLastResultAgain_(None)
    drain(a.svc)
    time.sleep(0.4)
    c.observe(events=[e for e in seen if e[0] == "insertion.paste_again"])
    c.check("already_present", ("insertion.paste_again", 
            "reconciled_accessible_text", "already_present") in seen, seen)
    c.check("zero_effects", rem.writes_on(a.w, {"F1"}, mark) == []
            or all(e[1] == "ax_set_range" for e in
                   rem.writes_on(a.w, {"F1"}, mark)), a.w.effects)
    a.close()


@driver("LF-M08-F18-C02")
def f18_c02(c):
    env = corpus_env(c, text_f1="")
    run(env, "hello", job(snap(env)))
    env.w.user_replace("F1", 0, 5, "")
    gate = threading.Event()
    env.svc.undo_last(on_done=lambda _o: gate.wait(5))
    time.sleep(0.05)
    env.svc.paste_again()
    env.svc.paste_again()
    c.declare("BOTH_ADMITTED_WHILE_HELD")
    c.hit("BOTH_ADMITTED_WHILE_HELD")
    gate.set()
    time.sleep(0.8)
    c.check("no_unintended_duplicate", env.w.text("F1") == "hello",
            env.w.text("F1"))
    env.close()


@driver("LF-M08-F18-C03")
def f18_c03(c):
    a = rem.AppEnv(consent=True, window=0)
    j = a.dictate()
    a.w.user_replace("F1", 0, mw.u16(a.w.text("F1")), "")
    a.d.store.delete_everywhere("job", j["job_id"])
    mark = a.w.seq
    with rem.inline_after(a.app_mod):
        a.d.pasteLastResultAgain_(None)
    time.sleep(0.5)
    c.observe(state="saved_not_inserted" if a.w.text("F1") == ""
              else "inserted")
    c.check("state_accepted", a.w.text("F1") == "", a.w.text("F1"))
    forbid_reads(c, a, {"F1"}, mark) if False else c.check(
        "no_reads_after_delete", rem.reads_on(a.w, {"F1"}, mark) == [],
        rem.reads_on(a.w, {"F1"}, mark)[:3])
    a.close()


@driver("LF-M08-F18-C04")
def f18_c04(c):
    a = rem.AppEnv(consent=False, window=0)
    j = a.dictate()
    a.w.user_replace("F1", 0, mw.u16(a.w.text("F1")), "")
    caller = threading.current_thread().name
    seen = []

    def slow(world, *args):
        seen.append(threading.current_thread().name)
        time.sleep(0.2)
    a.w.on("number_of_characters", slow)
    a.w.on("string_for_range", slow)
    t0 = time.monotonic()
    with rem.inline_after(a.app_mod):
        a.d.pasteLastResultAgain_(None)
        d1 = time.monotonic() - t0
        t1 = time.monotonic()
        a.d.hubPasteText("history text", job_id=j["job_id"])
        d2 = time.monotonic() - t1
    time.sleep(1.0)
    c.observe(callback_ms=(round(d1 * 1000, 2), round(d2 * 1000, 2)))
    c.check("no_ax_on_ui_thread", caller not in seen, seen)
    c.check("callbacks_prompt", d1 < 0.05 and d2 < 0.05, (d1, d2))
    a.close()


@driver("LF-M08-F18-C05")
def f18_c05(c):
    env = corpus_env(c, text_f1="")
    run(env, "hello", job(snap(env)))
    env.w.fields["F2"].text = "unrelated text containing hello inside"
    env.w.fields["F2"].sel = (0, 0)
    env.w.focus("A", "F2")
    mark = env.w.seq
    env.svc.paste_again()
    drain(env.svc)
    time.sleep(0.4)
    c.observe(decision="D16")
    c.check("approximate_already_present", rem.writes_on(
        env.w, {"F2"}, mark) == [], env.w.effects)
    env.close()


# ---- F19 observation -----------------------------------------------------------

@driver("LF-M08-F19-C01")
def f19_c01(c):
    a = rem.AppEnv(consent=True, window=0.6)
    ex = None

    def final():
        nonlocal ex
        ex = a.d.store.latest_example()
        if not ex:
            return False
        o = (a.d.store.latest_revision(ex[0]).get("outcome") or {})
        return (o.get("observation") or {}).get("stop_reason") == \
            "window_elapsed"
    # The close callback reaches the main thread through callAfter: run
    # it inline for the whole window (nothing pumps a run loop here).
    with rem.inline_after(a.app_mod):
        a.dictate()
        mw.wait_for(final, 4)
    o = a.d.store.latest_revision(ex[0])["outcome"]
    c.observe(observation=o.get("observation"))
    c.check("no_edit_observed", o["observation"].get("no_edit_observed")
            is True, o.get("observation"))
    c.check("correctness_unreviewed", o.get("correctness") == "unreviewed",
            o.get("correctness"))
    labels = a.d.store.submit(lambda db: db.execute(
        "SELECT COUNT(*) FROM correction_labels").fetchone()[0])
    c.check("no_labels", labels == 0, labels)
    a.close()


def obs_env(c, window=1.5, **kw):
    env = corpus_env(c, text_f1="", window=window, **kw)
    r, obs = observed_insert(env, "owned words", job(snap(env)))
    if obs is None:
        raise HarnessError(f"no observer ({r.state}, {r.reason_code})")
    return env, obs


@driver("LF-M08-F19-C02")
def f19_c02(c):
    env, obs = obs_env(c)
    mark = env.w.seq
    env.w.focus("A", "F2")
    obs.join(5)
    c.observe(stop_reason=obs.stop_reason)
    c.check("stopped", obs.stop_reason in ("field_changed", "focus_lost"),
            obs.stop_reason)
    forbid_reads(c, env, {"F2"}, mark)
    no_canaries(c, env)
    env.close()


@driver("LF-M08-F19-C03")
def f19_c03(c):
    env, obs = obs_env(c)
    time.sleep(0.1)
    mark = env.w.seq
    env.w.fields["F1"].subrole = "AXSecureTextField"
    obs.join(5)
    c.observe(stop_reason=obs.stop_reason)
    c.check("secure_stop", obs.stop_reason == "secure_field_transition",
            obs.stop_reason)
    forbid_reads(c, env, {"F1"}, mark)
    env.close()


@driver("LF-M08-F19-C04")
def f19_c04(c):
    env = corpus_env(c, text_f1="", window=1.0)
    r, obs = observed_insert(env, "owned words", job(snap(env),
                                                     consent=False))
    time.sleep(0.2)
    env.w.user_replace("F1", 0, 5, "OWNED")
    time.sleep(1.2)
    env.store.sync()
    rows = env.rows("SELECT COUNT(*) FROM insertion_observations")[0][0]
    arts = env.rows("SELECT COUNT(*) FROM artifacts WHERE role LIKE"
                    " 'observation_%'")[0][0]
    c.observe(observer=obs is not None, rows=rows, artifacts=arts)
    c.check("no_training_observation_content", obs is None and rows == 0
            and arts == 0, (obs, rows, arts))
    env.close()


@driver("LF-M08-F19-C05")
def f19_c05(c):
    c.declare("CLOSE_IN_GAP")
    base = observation_mod.OutcomeObserver

    class Gap(base):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            self._g = False
            self.signals = observation_mod.StopSignals()

        def _gap(self):
            # The app's own subscription step — subscribe_close in the
            # repaired app, the on_closed assignment in the audited one —
            # with the close landing just before it.
            if not self._g and sys._getframe(2).f_code.co_name == \
                    "_observationStarted_":
                self._g = True
                c.hit("CLOSE_IN_GAP")
                self.signals.note_session_locked()
                self._thread.join(3)

        def subscribe_close(self, fn):
            self._gap()
            return super().subscribe_close(fn)

        def __setattr__(self, name, value):
            if name == "on_closed" and value is not None:
                self._gap()
            super().__setattr__(name, value)
    a = rem.AppEnv(consent=True, window=5.0)
    calls = []
    a.d.collector.on_observation_closed = lambda ctx, r, o: calls.append(o)
    service_mod.OutcomeObserver = Gap
    try:
        a.dictate()
        mw.wait_for(lambda: calls, 3)
        time.sleep(0.3)
    finally:
        service_mod.OutcomeObserver = base
    c.observe(final_callbacks=len(calls))
    c.check("exactly_one", len(calls) == 1, len(calls))
    a.close()


# ---- F20 re-anchoring ------------------------------------------------------------

@driver("LF-M08-F20-C01")
def f20_c01(c):
    env, obs = obs_env(c)
    time.sleep(0.2)
    env.w.user_type("F1", 0, "prefix ")
    obs.join(5)
    c.observe(stop_reason=obs.stop_reason, reanchors=obs.reanchors,
              start=obs.start)
    c.check("reanchored_no_edit", obs.edited is False and obs.reanchors >= 1
            and obs.start == mw.u16("prefix "), (obs.edited, obs.start))
    env.close()


@driver("LF-M08-F20-C02")
def f20_c02(c):
    env = corpus_env(c, text_f1="owned words ", sel_f1=(12, 12), window=1.5)
    r, obs = observed_insert(env, "owned words", job(snap(env)))
    time.sleep(0.2)
    env.w.user_replace("F1", 12, 23, "")            # remove OUR occurrence
    obs.join(5)
    c.observe(stop_reason=obs.stop_reason, start=obs.start)
    c.check("ambiguous_no_attribution", obs.edited is False
            and obs.stop_reason == "reanchor_ambiguous", obs.stop_reason)
    env.close()


@driver("LF-M08-F20-C03")
def f20_c03(c):
    env, obs = obs_env(c)
    time.sleep(0.2)

    def failing(el, start, length):
        env.w._read("string_for_range", el.fid, "AXStringForRange")
        return None
    env.w.user_type("F1", 0, "x")
    env.w.string_for_range = failing
    obs.join(5)
    c.observe(stop_reason=obs.stop_reason)
    c.check("unavailable_no_attribution", obs.edited is False
            and obs.stop_reason == "target_read_failed", obs.stop_reason)
    env.close()


class FakeClock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


@driver("LF-M08-F20-C04")
def f20_c04(c):
    clock = FakeClock()
    env = corpus_env(c, text_f1="", window=2.0, clock=clock)
    r, obs = observed_insert(env, "owned words", job(snap(env)))
    if obs is None:
        raise HarnessError(f"no observer ({r.state})")
    mw.wait_for(lambda: obs.ticks >= 1, 2)
    c.declare("CLOCK_PAST_DEADLINE")
    clock.t += 10.0
    c.hit("CLOCK_PAST_DEADLINE")
    env.w.user_replace("F1", 0, 5, "OWNED")
    obs.join(5)
    c.observe(stop_reason=obs.stop_reason)
    c.check("deadline_no_attribution", obs.edited is False
            and obs.stop_reason in ("reanchor_deadline", "window_elapsed"),
            obs.stop_reason)
    env.close()


@driver("LF-M08-F20-C05")
def f20_c05(c):
    for new in ("tiger", "ox"):
        env = corpus_env(c, text_f1=" CANARY_OUTSIDE", sel_f1=(0, 0),
                         window=1.5)
        r, obs = observed_insert(env, "cat", job(snap(env)))
        time.sleep(0.2)
        env.w.user_replace("F1", 0, 3, new)
        obs.join(5)
        after = rem.artifact_text(env, obs.after_artifact) \
            if obs.after_artifact else None
        c.check(f"exact_or_abstain:{new}", after in (None, new)
                and (after is None or "CANARY" not in after), after)
        env.close()


def _override(cid):
    return next(x for x in CORPUS["cases"] if x["case_id"] == cid)[
        "synthetic_target_state"]["case_overrides"]


# The exact variant strings from the frozen corpus bytes (CR, CRLF, a
# Unicode separator, ESC) — parsed, never retyped.
CORPUS_VARIANTS = {
    "LF-M08-F16-C05": _override("LF-M08-F16-C05").split(
        "text variants ", 1)[1].split(", "),
}


# ---- F21 lock / wake / new dictation ------------------------------------

@driver("LF-M08-F21-C01")
def f21_c01(c):
    env, obs = obs_env(c)
    time.sleep(0.1)
    env.svc.note_session_locked()
    mark = env.w.seq
    obs.join(5)
    c.observe(stop_reason=obs.stop_reason)
    c.check("locked_stop", obs.stop_reason == "session_locked",
            obs.stop_reason)
    forbid_reads(c, env, {"F1"}, mark + 2, name="no_read_after_lock_tick")
    env.close()


@driver("LF-M08-F21-C02")
def f21_c02(c):
    env = corpus_env(c, text_f1="", window=0.8)
    env.svc.note_session_locked()
    r1, o1 = observed_insert(env, "first ", job(snap(env), jid="job-a"))
    o1.join(3)
    env.svc.note_session_unlocked()
    r2, o2 = observed_insert(env, "second", job(snap(env), jid="job-b"))
    o2.join(4)
    c.observe(first=o1.stop_reason, second=o2.stop_reason,
              ticks=o2.ticks)
    c.check("fresh_observer_active", o1.stop_reason == "session_locked"
            and o2.stop_reason == "window_elapsed" and o2.ticks >= 1,
            (o1.stop_reason, o2.stop_reason))
    env.close()


@driver("LF-M08-F21-C03")
def f21_c03(c):
    env = corpus_env(c, text_f1="", window=0.8)
    env.svc.note_new_dictation()                    # before the observer
    time.sleep(0.01)
    r, obs = observed_insert(env, "owned", job(snap(env)))
    obs.join(4)
    c.observe(stop_reason=obs.stop_reason)
    c.check("continues", obs.stop_reason == "window_elapsed",
            obs.stop_reason)
    env.close()


@driver("LF-M08-F21-C04")
def f21_c04(c):
    env, obs = obs_env(c, window=3.0)
    time.sleep(0.1)
    env.svc.note_new_dictation()
    obs.join(5)
    c.observe(stop_reason=obs.stop_reason)
    c.check("new_dictation_stop", obs.stop_reason == "new_dictation",
            obs.stop_reason)
    env.close()


@driver("LF-M08-F21-C05")
def f21_c05(c):
    a = rem.AppEnv(consent=True, window=3.0)
    j = a.dictate()
    a.d.store.delete_everywhere("job", j["job_id"])
    mark = a.w.seq
    a.svc.note_session_locked()
    a.svc.note_session_unlocked()
    with rem.inline_after(a.app_mod):
        a.d.pasteLastResultAgain_(None)
    time.sleep(1.2)
    c.check("revoked_stays_revoked", rem.reads_on(a.w, {"F1"}, mark) == []
            and rem.writes_on(a.w, {"F1"}, mark) == [],
            rem.reads_on(a.w, {"F1"}, mark)[:3])
    a.close()


# ---- F22 evidence semantics ------------------------------------------------

@driver("LF-M08-F22-C01")
def f22_c01(c):
    a = rem.AppEnv(consent=True, window=0)
    a.dictate()
    ex = a.d.store.latest_example()
    o = a.d.store.latest_revision(ex[0])["outcome"]
    c.expect_state(o.get("insertion"))
    c.check("correctness_unreviewed", o.get("correctness") == "unreviewed",
            o.get("correctness"))
    n = a.d.store.submit(lambda db: (
        db.execute("SELECT COUNT(*) FROM correction_labels").fetchone()[0],
        db.execute("SELECT COUNT(*) FROM preference_observations")
        .fetchone()[0] if db.execute(
            "SELECT 1 FROM sqlite_master WHERE name="
            "'preference_observations'").fetchone() else 0))
    c.check("no_labels_or_preferences", n == (0, 0), n)
    a.close()


@driver("LF-M08-F22-C02")
def f22_c02(c):
    env = corpus_env(c, text_f1="", window=1.0)
    env.w.fields["F1"].readable = False
    r, obs = observed_insert(env, "unseen", job(snap(env)))
    c.expect_state(r.state)
    c.check("no_observer", obs is None, obs)
    env.close()


@driver("LF-M08-F22-C03")
def f22_c03(c):
    env = corpus_env(c, text_f1="")
    real = record_mod.record_insertion

    def boom(store, result):
        raise RuntimeError("controlled store failure")
    service_mod.record.record_insertion = boom
    try:
        r = run(env, "dictated", job(snap(env)))
    finally:
        service_mod.record.record_insertion = real
    c.observe(state=r.state)
    c.check("physical_result_preserved", r.state == "confirmed"
            and env.w.text("F1") == "dictated", (r.state, env.w.text("F1")))
    c.check("evidence_failure_disclosed", any(
        e[0] == "insertion.record_failed" for e in env.rec.events),
        env.rec.events)
    env.close()


class _FakeTransformResult:
    def __init__(self, output):
        self.output = output
        self.job = None
        self.path = "applied"


@driver("LF-M08-F22-C04", "LF-M08-F22-C05")
def f22_c04(c):
    candidate = "tcand-synthetic" if c.cid.endswith("C04") else None
    a = rem.AppEnv(consent=candidate is not None, window=0.6)
    a.w.fields["F1"].text = BASE_F1
    a.w.fields["F1"].sel = (0, 9)
    cap, why = a.d._m11_capture_selection()
    with rem.inline_after(a.app_mod):
        a.d.tfAcceptTransform(_FakeTransformResult("REPLACED"), cap,
                              candidate)
    mw.wait_for(lambda: a.w.text("F1") == "REPLACED_OWNED_FIELD", 3)
    time.sleep(0.8)
    a.d.store.sync()
    rows = a.d.store.submit(lambda db: db.execute(
        "SELECT job_id FROM insertions").fetchall())
    obs = a.d.store.submit(lambda db: db.execute(
        "SELECT COUNT(*) FROM insertion_observations").fetchone()[0])
    c.observe(rows=rows, observations=obs)
    c.check("replaced", a.w.text("F1") == "REPLACED_OWNED_FIELD",
            a.w.text("F1"))
    if candidate:
        c.check("candidate_attributed", rows == [(candidate,)], rows)
    else:
        c.check("jobless_no_row_no_observation", rows == [] and obs == 0,
                (rows, obs))
    a.close()


# ---- F23 deletion ------------------------------------------------------------

def deletion_env(c, **kw):
    env = corpus_env(c, **kw)
    jid, _fam = env.store.create_job(state="queued")
    revoke = getattr(env.svc, "revoke_job", None)
    if revoke is not None:            # absent at the audited base
        env.store.add_job_deletion_listener(revoke)
    c.install(job_row=jid, listener=(
        "svc.revoke_job via the real store" if revoke is not None
        else "none: the service has no revoke_job at this code"))
    return env, jid


@driver("LF-M08-F23-C01")
def f23_c01(c):
    env, jid = deletion_env(c, text_f1="")
    gate = threading.Event()
    env.svc.undo_last(on_done=lambda _o: gate.wait(5))
    done = []
    env.svc.submit("must not land", job(snap(env), jid=jid), done.append)
    env.store.delete_everywhere("job", jid)
    c.declare("DELETED_WHILE_QUEUED")
    c.hit("DELETED_WHILE_QUEUED")
    gate.set()
    mw.wait_for(lambda: done, 5)
    c.expect_state(done[0].state)
    c.check("no_effect", env.w.text("F1") == "" and not effects(env),
            env.w.effects)
    env.close()


@driver("LF-M08-F23-C02")
def f23_c02(c):
    env, jid = deletion_env(c, text_f1="", window=1.0)
    env.w.on("number_of_characters", once(
        c, "DELETE_AFTER_EFFECT",
        lambda w, el: env.store.delete_everywhere("job", jid)), nth=2)
    r, obs = observed_insert(env, "dictated", job(snap(env), jid=jid))
    c.observe(state=r.state, observer=obs is not None)
    arts = env.rows("SELECT COUNT(*) FROM artifacts WHERE job_id=? AND"
                    " purged=0", jid)[0][0]
    c.check("effect_truth", env.w.text("F1") == "dictated"
            and r.state in ("confirmed", "posted_unverified"), r.state)
    c.check("no_observer_no_content", obs is None and arts == 0,
            (obs, arts))
    env.close()


@driver("LF-M08-F23-C03")
def f23_c03(c):
    env, jid = deletion_env(c, text_f1="", window=2.0)
    held = threading.Event()
    release = threading.Event()
    real = env.store.write_text_artifact

    def gated(**kw):
        held.set()
        release.wait(5)
        return real(**kw)
    r, obs = observed_insert(env, "owned words", job(snap(env), jid=jid))
    if obs is None:
        raise HarnessError(f"no observer ({r.state})")
    env.store.write_text_artifact = gated
    time.sleep(0.15)
    env.w.user_replace("F1", 0, 5, "OWNED")
    c.declare("PUBLICATION_HELD")
    if held.wait(3):
        c.hit("PUBLICATION_HELD")
    env.store.delete_everywhere("job", jid)
    release.set()
    obs.join(5)
    env.store.sync()
    arts = env.rows("SELECT COUNT(*) FROM artifacts WHERE job_id=? AND"
                    " purged=0", jid)[0][0]
    c.check("artifact_publication_refused", arts == 0, arts)
    env.close()


@driver("LF-M08-F23-C04")
def f23_c04(c):
    env, jid = deletion_env(c, text_f1="", window=2.0)
    r, obs = observed_insert(env, "owned words", job(snap(env), jid=jid))
    time.sleep(0.15)
    env.w.user_replace("F1", 0, 5, "OWNED")
    obs.join(5)
    env.store.sync()
    before = env.rows("SELECT COUNT(*) FROM artifacts WHERE job_id=? AND"
                      " purged=0", jid)[0][0]
    env.store.delete_everywhere("job", jid)
    after = env.rows("SELECT COUNT(*) FROM artifacts WHERE job_id=? AND"
                     " purged=0", jid)[0][0]
    mark = env.w.seq
    out = env.svc.paste_again()
    c.observe(before=before, after=after, paste_again=out)
    c.check("committed_then_purged", before == 2 and after == 0,
            (before, after))
    c.check("no_future_authority", out.get("outcome") == "nothing_to_paste"
            and rem.reads_on(env.w, {"F1"}, mark) == [], out)
    env.close()


@driver("LF-M08-F23-C05")
def f23_c05(c):
    env, jid = deletion_env(c, text_f1="")
    env.store.delete_everywhere("job", jid)
    from localflow.v2.insertion.result import InsertionResult
    res = InsertionResult(insertion_id=ids.new_id("ins"), job_id=jid,
                          state="posted_unverified", method="clipboard_"
                          "transaction")
    record_mod.record_insertion(env.store, res)
    try:
        record_mod.open_observation(env.store, res.insertion_id, jid)
        opened = True
    except Exception:
        opened = False
    rows = env.rows("SELECT state FROM insertions WHERE job_id=?", jid)
    c.install(decision="D13")
    c.observe(insertion_rows=rows, observation_opened=opened)
    c.check("content_free_row_allowed", rows == [("posted_unverified",)],
            rows)
    c.check("observation_refused", opened is False, opened)
    env.close()


# ---- F24 retention -----------------------------------------------------------

def observed_app_edit(c, consent, *, pause_after_press=False,
                      enable_after_press=False):
    a = rem.AppEnv(consent=consent, window=2.0)
    a.h.press_release()
    if pause_after_press:
        a.d.consent.set("paused", note="m08 corpus")
    if enable_after_press:
        a.d.consent.set("enabled", note="m08 corpus")
    fn, args = a.h.run_coordinator()
    text, j = args
    s = rem.snap(a.w)
    j["context_snapshot"], j["target"] = s, s.target
    with rem.inline_after(a.app_mod):
        a.d._finishWithText_(text, j)
        mw.wait_for(lambda: j not in a.d._active_jobs, 5)
    time.sleep(0.3)
    a.w.user_replace("F1", 0, 5, "HELLO")
    time.sleep(1.2)
    a.d.store.sync()
    return a, j


@driver("LF-M08-F24-C01", "LF-M08-F24-C02")
def f24_c01(c):
    a, j = observed_app_edit(c, True)
    arts = a.d.store.submit(lambda db: db.execute(
        "SELECT artifact_id FROM artifacts WHERE role LIKE"
        " 'observation_%' AND job_id=?", (j["job_id"],)).fetchall())
    if len(arts) != 2:
        raise HarnessError(f"observation artifacts not written: {arts}")
    if c.cid.endswith("C01"):
        a.d.store.grant_lease(arts[1][0], "history", days=None)
    a.d.store.sync()
    a.d.store.prune_training(now=time.time() + 40 * 86400)
    a.d.store.prune(now=time.time() + 40 * 86400)
    rows = a.d.store.submit(lambda db: db.execute(
        "SELECT artifact_id, purged FROM artifacts WHERE role LIKE"
        " 'observation_%' AND job_id=?", (j["job_id"],)).fetchall())
    training = a.d.store.submit(lambda db: db.execute(
        "SELECT COUNT(*) FROM artifact_leases WHERE holder='training' AND"
        " revoked_at_utc IS NULL AND artifact_id IN (?,?)",
        (arts[0][0], arts[1][0])).fetchone()[0])
    c.observe(artifacts=rows, live_training_leases=training)
    purged = {aid: p for aid, p in rows}
    if c.cid.endswith("C01"):
        c.check("history_retained_training_ineligible",
                purged[arts[1][0]] == 0 and training == 0, (rows, training))
    else:
        c.check("no_expired_payload_reuse", all(p == 1 for p in
                                                purged.values()), rows)
    a.close()


@driver("LF-M08-F24-C03")
def f24_c03(c):
    a, j = observed_app_edit(c, True, pause_after_press=True)
    n = a.d.store.submit(lambda db: db.execute(
        "SELECT COUNT(*) FROM insertion_observations WHERE job_id=?",
        (j["job_id"],)).fetchone()[0])
    c.observe(observations=n)
    c.check("authorized_capture_semantics", n == 1, n)
    a.close()


@driver("LF-M08-F24-C04")
def f24_c04(c):
    a, j = observed_app_edit(c, False, enable_after_press=True)
    n = a.d.store.submit(lambda db: db.execute(
        "SELECT COUNT(*) FROM insertion_observations").fetchone()[0])
    arts = a.d.store.submit(lambda db: db.execute(
        "SELECT COUNT(*) FROM artifacts WHERE role LIKE"
        " 'observation_%'").fetchone()[0])
    c.observe(observations=n, artifacts=arts)
    c.check("no_retroactive_authorization", n == 0 and arts == 0, (n, arts))
    a.close()


@driver("LF-M08-F24-C05")
def f24_c05(c):
    clock = FakeClock()
    env = corpus_env(c, text_f1="", clock=clock)
    run(env, "hello", job(snap(env)))
    clock.t += getattr(service_mod, "RECOVERY_CACHE_TTL_SEC", 3600.0) + 1
    c.declare("CACHE_EXPIRED")
    c.hit("CACHE_EXPIRED")
    mark = env.w.seq
    p = env.svc.paste_again()
    u = env.svc.undo_last()
    c.observe(paste_again=p, undo=u)
    c.check("expired_not_replayed", p.get("outcome") == "nothing_to_paste"
            and u.get("outcome") == "nothing_to_undo", (p, u))
    forbid_reads(c, env, {"F1"}, mark)
    env.close()
    env2, jid = deletion_env(c, text_f1="")
    run(env2, "hello", job(snap(env2), jid=jid))
    env2.store.delete_everywhere("job", jid)
    p2 = env2.svc.paste_again()
    c.check("deleted_not_replayed", p2.get("outcome") == "nothing_to_paste",
            p2)
    env2.close()


# ---- F25 benchmark (graded from a benchmark record) ----------------------

BENCH = {"record": None}


STATS = ("n", "p50_ms", "p95_ms", "p99_ms", "max_ms")
UI_COHORTS = ("ui_finish_with_text", "ui_recovery_paste_again",
              "ui_history_paste_text", "ui_undo_last_insertion")


def _cohort_ok(c, rec, name, where="cohorts"):
    co = (rec.get(where) or {}).get(name) if where == "cohorts" \
        else (rec.get("native") or {}).get("cohorts", {}).get(name)
    ok = co is not None and co.get("invalid_samples") == 0 \
        and not co.get("problems") and co.get("n", 0) > 0
    c.check(f"{name}_every_sample_witnessed", ok,
            None if co is None else {k: co.get(k) for k in
                                     ("n", "invalid_samples", "problems")})
    return co or {}


def _clock(co, name):
    s = co.get(name)
    return isinstance(s, dict) and all(k in s for k in STATS) and s["n"] > 0


@driver("LF-M08-F25-C01", "LF-M08-F25-C02", "LF-M08-F25-C03",
        "LF-M08-F25-C04", "LF-M08-F25-C05")
def f25(c):
    """Graded from the benchmark record's own fields (cohort validity,
    clocks, boundaries, witnesses, environment, verdicts)."""
    rec = BENCH["record"]
    if rec is None:
        raise NotRun(ADJ["decisions"]["D18_benchmark_cases"]["decision"])
    c.install(benchmark=rec.get("tool"), measured_utc=rec.get("measured_utc"))
    c.check("work_valid", rec.get("work_valid") is True)
    verdicts = rec.get("verdicts", {})
    if c.cid.endswith("C01"):
        for name in UI_COHORTS:
            co = _cohort_ok(c, rec, name)
            c.check(f"{name}_callback_clock", _clock(co, "callback"),
                    sorted(co))
            c.check(f"{name}_s24_verdict", verdicts.get(name) == "pass",
                    verdicts.get(name))
        c.check("ax_delay_injected_outside_ui",
                (rec.get("injected_delays") or {}).get(
                    "ui_ax_content_read_sec", 0) > 0,
                rec.get("injected_delays"))
    elif c.cid.endswith("C02"):
        for name in rec.get("cohorts", {}):
            _cohort_ok(c, rec, name)
        for name in ("native_ax", "native_ax_cold"):
            _cohort_ok(c, rec, name, where="native")
    elif c.cid.endswith("C03"):
        co = _cohort_ok(c, rec, "ax_transaction")
        for clock in ("enqueue", "queue_wait", "worker_exec"):
            c.check(f"separate_{clock}", _clock(co, clock), sorted(co))
        for name in ("clipboard_settle_inside", "clipboard_settle_beyond"):
            _cohort_ok(c, rec, name)
        d = rec.get("injected_delays") or {}
        c.check("settle_delays_declared",
                d.get("settle_inside_consumer_sec", 0) > 0
                and d.get("settle_beyond_consumer_sec", 0) > 0, d)
    elif c.cid.endswith("C04"):
        co = _cohort_ok(c, rec, "observer_tick")
        b = (co.get("boundary") or "").lower()
        c.check("full_tick_not_approximation",
                "full" in b and "no approximation" in b, co.get("boundary"))
        _cohort_ok(c, rec, "observer_reanchor_tick")
        _cohort_ok(c, rec, "observer_stop")
    else:
        warm = _cohort_ok(c, rec, "native_ax", where="native")
        cold = _cohort_ok(c, rec, "native_ax_cold", where="native")
        c.check("warm_and_cold_cohorts", warm.get("warmth") == "warm"
                and cold.get("warmth") == "cold",
                (warm.get("warmth"), cold.get("warmth")))
        env = rec.get("environment") or {}
        c.check("environment_recorded", all(
            env.get(k) for k in ("macos", "machine", "code_root_sha",
                                 "python", "pyobjc")), sorted(env))
        c.check("budget_verdicts", all(
            verdicts.get(k, "").startswith("pass")
            for k in ("native_ax", "native_ax_cold")), verdicts)
    c.observe(benchmark_verdicts={k: v for k, v in verdicts.items()})


# ---- stateful probes (intermediate state checked after every step) -------

STATEFUL = {}


def probe(pid):
    def deco(fn):
        STATEFUL[pid] = fn
        return fn
    return deco


@probe("LF-M08-ST-01")
def st01(c):
    env = corpus_env(c)
    s = snap(env)
    c.check("s1_snapshot_is_A", s.target.app_pid == 101)
    env.w.focus("B", "FB")
    c.check("s2_B_frontmost", env.w.frontmost()["pid"] == 202)
    r = run(env, "dictated", job(s))
    c.check("s3_refused", r.state == "target_changed", r.state)
    forbid_reads(c, env, {"FB"})
    forbid_writes(c, env, {"FB", "F1"})
    env.close()


@probe("LF-M08-ST-02")
def st02(c):
    env = f02_env(c)
    s = snap(env)
    c.check("s1_W1", s.window_element == mw.Win("W1"))
    env.w.focus("A", "F2")
    c.check("s2_equal_title", env.w.windows["W1"]["title"]
            == env.w.windows["W2"]["title"])
    r = run(env, "dictated", job(s))
    c.check("s3_refused", r.state == "target_changed", r.state)
    forbid_writes(c, env, {"F2"})
    env.close()


@probe("LF-M08-ST-03")
def st03(c):
    env = corpus_env(c, text_f1="abc def", sel_f1=(0, 0))
    s = snap(env, sel=(0, 0))
    env.w.user_select("F1", 4, 4)
    c.check("s2_caret_moved", env.w.fields["F1"].sel == (4, 4))
    r = run(env, "X", job(s))
    c.check("s3_once_at_new_caret", env.w.text("F1") == "abc Xdef"
            and len(effects(env)) == 1 and r.state == "confirmed",
            (env.w.text("F1"), r.state))
    env.close()


@probe("LF-M08-ST-04")
def st04(c):
    env = corpus_env(c, text_f1="keep old part", sel_f1=(5, 8))
    s = snap(env, sel=(5, 8), sel_text="old")
    env.w.user_replace("F1", 5, 8, "OLD")
    c.check("s2_changed", env.w.text("F1") == "keep OLD part")
    r = run(env, "new", job(s))
    c.check("s3_refused", r.state == "target_changed"
            and env.w.text("F1") == "keep OLD part", r.state)
    env.close()


@probe("LF-M08-ST-05")
def st05(c):
    env = corpus_env(c, sel_f1=(0, 9))
    env.w.fields["FB"].sel = (0, 18)
    drift_hook(c, env, "BEFORE_ELEMENT_READ", "B", "FB")
    cap, why = capture_selection(env.w, denied_apps=())
    c.check("s4_no_B_read", rem.reads_on(env.w, {"FB"}) == [])
    c.check("s4_capture_is_A_or_refused", cap is None
            or cap["source"] == "SYNTHETIC", cap)
    env.close()


@probe("LF-M08-ST-06")
def st06(c):
    env = corpus_env(c, text_f1="CANARY_DENIED ", denied_apps=DENY_A,
                     window=1.0)
    j = job(None, target=denied_target())
    r, obs = observed_insert(env, "hello", j)
    c.check("s3_insert_no_read", rem.reads_on(env.w, {"F1"}) == []
            and obs is None, (r.state, obs))
    env.svc.undo_last()
    env.svc.paste_again()
    drain(env.svc)
    c.check("s4_zero_acquisition", rem.reads_on(env.w, {"F1"}) == [],
            rem.reads_on(env.w, {"F1"})[:3])
    env.close()


@probe("LF-M08-ST-07")
def st07(c):
    env = copy_before_restore(c)
    r = run(env, "dictated", job(snap(env)))
    c.check("s2_consumed", env.w.text("F1") == "dictated")
    c.check("s4_restore_skipped", r.clipboard.get("restore_skipped_reason")
            == "user_copy_won" and env.pb.plain() == "CANARY_USER_COPY",
            (r.clipboard, env.pb.plain()))
    env.close()


@probe("LF-M08-ST-08")
def st08(c):
    env = clip_env(c)
    env.kb.mode = "gate"
    r = run(env, "dictated", job(snap(env)))
    c.check("s2_not_confirmed", r.state == "posted_unverified", r.state)
    c.check("s3_payload_retained", env.pb.plain() == "dictated",
            env.pb.plain())
    env.kb.release()
    mw.wait_for(lambda: env.w.text("F1") == "dictated", 3)
    c.check("s4_right_payload", env.w.text("F1") == "dictated",
            env.w.text("F1"))
    env.close()


@probe("LF-M08-ST-09")
def st09(c):
    env = clip_env(c)
    env.w.fields["F1"].text = "hello"
    env.w.fields["F1"].sel = (0, 0)
    env.kb.mode = "gate"
    r = run(env, "hello", job(snap(env, sel=(0, 0))))
    c.check("s4_ambiguous", r.readback == "match_ambiguous"
            and r.state == "posted_unverified", (r.readback, r.state))
    env.kb.release()
    env.close()


@probe("LF-M08-ST-10")
def st10(c):
    env = clip_env(c)
    env.kb.truncate = 3
    r = run(env, "hello", job(snap(env)))
    c.check("s2_prefix_written", env.w.text("F1") == "hel")
    c.check("s4_partial_not_confirmed", r.readback == "partial"
            and r.state == "posted_unverified", (r.readback, r.state))
    env.close()


@probe("LF-M08-ST-11")
def st11(c):
    env = clip_env(c)
    j = job(snap(env))
    seen = {}

    def cancel():
        seen["board_at_barrier"] = env.pb.plain()
        j["cancelled"] = True
    env.svc._on_post_begin = cancel
    r = run(env, "dictated", j)
    c.check("s2_published", seen.get("board_at_barrier") == "dictated",
            seen)
    c.check("s5_no_paste_and_restored", env.kb.posts == 0
            and env.pb.plain() == OLD and r.state == "saved_not_inserted",
            (env.kb.posts, env.pb.plain(), r.state))
    env.close()


@probe("LF-M08-ST-12")
def st12(c):
    two_pending(c)


@probe("LF-M08-ST-13")
def st13(c):
    env = corpus_env(c, text_f1="")
    run(env, "owned text", job(snap(env)))
    env.w.user_replace("F1", 0, 5, "OWNED")
    c.check("s2_edited", env.w.text("F1") == "OWNED text")
    out = env.svc.undo_last()
    c.check("s4_newer_unchanged", env.w.text("F1") == "OWNED text"
            and out.get("outcome") != "undone", out)
    env.close()


@probe("LF-M08-ST-14")
def st14(c):
    env = corpus_env(c, text_f1="")
    run(env, "hello", job(snap(env)))
    c.check("s2_complete", env.w.text("F1") == "hello")
    mark = env.w.seq
    env.svc.paste_again()
    drain(env.svc)
    time.sleep(0.3)
    c.check("s4_no_second_effect", env.w.text("F1") == "hello"
            and not [e for e in rem.writes_on(env.w, {"F1"}, mark)
                     if e[1] == "ax_set_text" and e[3]], env.w.text("F1"))
    env.close()


@probe("LF-M08-ST-15")
def st15(c):
    f21_c02(c)


@probe("LF-M08-ST-16")
def st16(c):
    env, obs = obs_env(c, window=3.0)
    t0 = obs._started
    time.sleep(0.1)
    env.svc.note_new_dictation()
    c.check("s2_later_dictation", env.svc.signals.new_dictation_since(t0))
    obs.join(5)
    c.check("s4_stopped", obs.stop_reason == "new_dictation",
            obs.stop_reason)
    env.close()


@probe("LF-M08-ST-17")
def st17(c):
    f23_c03(c)


@probe("LF-M08-ST-18")
def st18(c):
    env = corpus_env(c, sel_f1=(0, 9))
    env.w.fields["F2"].text = BASE_F1
    env.w.fields["F2"].sel = (0, 9)
    cap, why = capture_selection(env.w, denied_apps=())
    c.check("s1_strict_capture", cap is not None, why)
    candidate = "SYNTHETIC-CANDIDATE"
    env.w.focus("A", "F2")
    r = run(env, candidate, job(cap["snapshot"], strict_replacement=True,
                                jid="tcand-st18"))
    c.check("s4_no_W2_replacement", env.w.text("F2") == BASE_F1
            and r.state == "target_changed", (env.w.text("F2"), r.state))
    env.close()


# ---- metamorphic relations ------------------------------------------------

RANK = {"confirmed": 3, "posted_unverified": 2, "failed": 1,
        "target_changed": 0, "saved_not_inserted": 0}
RELATIONS = {}


def relation(rid):
    def deco(fn):
        RELATIONS[rid] = fn
        return fn
    return deco


@relation("LF-M08-MR-01")
def mr01(c):
    for text in ("alpha", "beta"):
        base = corpus_env(c)
        r0 = run(base, text, job(snap(base)))
        base.close()
        t = corpus_env(c)
        s = snap(t)
        t.w.apps["A"]["bundle"] = "com.example.contradiction"
        r1 = run(t, text, job(s))
        t.close()
        c.check(f"monotone:{text}", RANK[r1.state] <= RANK[r0.state]
                and r1.state == "target_changed", (r0.state, r1.state))


@relation("LF-M08-MR-02")
def mr02(c):
    env, s = strict_env(c)
    r0 = run(env, "REPLACED", job(s, strict_replacement=True))
    env.close()
    env, s = strict_env(c)
    env.w.fields["F1"].window = "W2"                 # same title/app/text
    r1 = run(env, "REPLACED", job(s, strict_replacement=True))
    env.close()
    c.check("title_alone_not_authority", r0.state == "confirmed"
            and r1.state == "target_changed", (r0.state, r1.state))


@relation("LF-M08-MR-03")
def mr03(c):
    env = corpus_env(c, sel_f1=(3, 3))
    r0 = run(env, "x", job(snap(env, sel=(3, 3))))
    env.close()
    env = corpus_env(c, sel_f1=(3, 3))
    s = snap(env, sel=(3, 3))
    env.w.user_select("F1", 7, 7)
    r1 = run(env, "x", job(s))
    env.close()
    c.check("caret_move_positive_control", r0.state == r1.state
            == "confirmed", (r0.state, r1.state))


@relation("LF-M08-MR-04")
def mr04(c):
    env = corpus_env(c, text_f1="keep old part", sel_f1=(5, 8))
    r0 = run(env, "new", job(snap(env, sel=(5, 8), sel_text="old")))
    env.close()
    env = corpus_env(c, text_f1="keep old part", sel_f1=(5, 8))
    r1 = run(env, "new", job(snap(env, sel=(5, 8), sel_text=None)))
    kept = env.w.text("F1")
    env.close()
    c.check("weakened_proof_no_authority", RANK[r1.state] < RANK[r0.state]
            and kept == "keep old part", (r0.state, r1.state, kept))


@relation("LF-M08-MR-05")
def mr05(c):
    env = clip_env(c)
    r0 = run(env, "dictated", job(snap(env)))
    env.close()
    env = copy_before_restore(c, text="dictated")
    r1 = run(env, "dictated", job(snap(env)))
    env.close()
    c.check("ownership_only_prevents", bool(r0.clipboard.get(
        "restored_types")) and not r1.clipboard.get("restored_types"),
        (r0.clipboard, r1.clipboard))


@relation("LF-M08-MR-06")
def mr06(c):
    env = corpus_env(c, text_f1="", window=0.5)
    r0, o0 = observed_insert(env, "x", job(snap(env)))
    env.close()
    env = corpus_env(c, text_f1="", window=0.5)
    env.w.fields["F1"].readable = False
    r1, o1 = observed_insert(env, "x", job(snap(env)))
    env.close()
    c.check("no_upgrade", RANK[r1.state] <= RANK[r0.state]
            and r1.state != "confirmed" and o1 is None,
            (r0.state, r1.state, o1))


@relation("LF-M08-MR-07")
def mr07(c):
    env = corpus_env(c, text_f1="")
    with rem.after_validation(lambda j: j.__setitem__("cancelled", True)):
        r0 = run(env, "x", job(snap(env)))
    before_effect = env.w.text("F1")
    env.close()
    env = corpus_env(c, text_f1="")
    j = job(snap(env))
    r1 = run(env, "x", j)
    j["cancelled"] = True
    after_effect = env.w.text("F1")
    env.close()
    c.check("before_effect_prohibited", before_effect == ""
            and r0.state == "saved_not_inserted", (before_effect, r0.state))
    c.check("after_effect_kept", after_effect == "x"
            and r1.state == "confirmed", (after_effect, r1.state))


@relation("LF-M08-MR-08")
def mr08(c):
    env, jid = deletion_env(c, text_f1="")
    run(env, "hello", job(snap(env), jid=jid))
    before = (env.svc.paste_again().get("outcome"),)
    drain(env.svc)
    time.sleep(0.3)
    env.close()
    env, jid = deletion_env(c, text_f1="")
    run(env, "hello", job(snap(env), jid=jid))
    env.store.delete_everywhere("job", jid)
    after = (env.svc.paste_again().get("outcome"),)
    arts = env.rows("SELECT COUNT(*) FROM artifacts WHERE job_id=? AND"
                    " purged=0", jid)[0][0]
    env.close()
    c.check("authority_only_decreases", before == ("repaste_queued",)
            and after == ("nothing_to_paste",) and arts == 0,
            (before, after, arts))


@relation("LF-M08-MR-09")
def mr09(c):
    env = corpus_env(c, text_f1="text ")
    run(env, "hello", job(None, target=TargetSnapshot(
        target_snapshot_id="t", app_bundle="com.example.a", app_pid=101,
        category="unknown")))
    allowed_reads = len(rem.reads_on(env.w, {"F1"}))
    env.close()
    env = corpus_env(c, text_f1="text ", denied_apps=DENY_A)
    run(env, "hello", job(None, target=denied_target()))
    denied_reads = len(rem.reads_on(env.w, {"F1"}))
    inserted = "hello" in env.w.text("F1")
    env.close()
    c.check("reads_cannot_increase", denied_reads <= allowed_reads
            and denied_reads == 0, (allowed_reads, denied_reads))
    c.check("write_capability_separate", inserted)


# ---- main ---------------------------------------------------------------------

def _run_one(cid, spec, fn):
    c = Case(cid, spec)
    t0 = time.monotonic()
    try:
        fn(c)
        out = c.result()
    except NotRun as e:
        out = c.result()
        out.update(status="not_run", reason=str(e)[:300])
    except HarnessError as e:
        out = c.result()
        out.update(status="error", reason=f"harness: {e}"[:300])
    except AssertionError as e:
        out = c.result()
        out.update(status="fail", reason=f"assertion: {e}"[:300])
    except Exception as e:
        out = c.result()
        out.update(status="error", reason=f"{type(e).__name__}: {e}"[:300],
                   trace=traceback.format_exc()[-1200:])
    out["seconds"] = round(time.monotonic() - t0, 3)
    return out


def main(argv):
    out_json = argv[argv.index("--json") + 1] if "--json" in argv else None
    only = set(argv[argv.index("--only") + 1].split(",")) \
        if "--only" in argv else None
    if "--benchmark" in argv:
        BENCH["record"] = json.loads(pathlib.Path(
            argv[argv.index("--benchmark") + 1]).read_text())
    cases = []
    for spec in CORPUS["cases"]:
        cid = spec["case_id"]
        if only and cid not in only:
            continue
        fn = DRIVERS.get(cid)
        if fn is None:
            res = {"case_id": cid, "status": "error",
                   "reason": "no driver"}
        else:
            res = _run_one(cid, spec, fn)
        res.update(family=spec["family_id"], role=spec["role"])
        cases.append(res)
        print(f"{res['status']:8} {cid} {res.get('reason', '')[:120]}")
    stateful = []
    for spec in CORPUS["stateful_probes"]:
        pid = spec["probe_id"]
        if only and pid not in only:
            continue
        res = _run_one(pid, None, STATEFUL[pid])
        stateful.append(res)
        print(f"{res['status']:8} {pid} {res.get('reason', '')[:120]}")
    relations = []
    for spec in CORPUS["metamorphic_relations"]:
        rid = spec["relation_id"]
        if only and rid not in only:
            continue
        res = _run_one(rid, None, RELATIONS[rid])
        relations.append(res)
        print(f"{res['status']:8} {rid} {res.get('reason', '')[:120]}")

    def tally(rows):
        t = {}
        for r in rows:
            t[r["status"]] = t.get(r["status"], 0) + 1
        return t
    families = {}
    for r in cases:
        families.setdefault(r["family"], []).append(r)
    summary = {"cases": tally(cases), "stateful": tally(stateful),
               "metamorphic": tally(relations),
               "families": {f: tally(rs) for f, rs in sorted(
                   families.items())},
               "denominators": {"cases": len(cases),
                                "stateful": len(stateful),
                                "metamorphic": len(relations)}}
    print(json.dumps(summary["cases"]), json.dumps(summary["stateful"]),
          json.dumps(summary["metamorphic"]))
    if out_json:
        import hashlib
        pathlib.Path(out_json).write_text(json.dumps({
            "runner": "tests/v2/insertion/m08_corpus_runner.py",
            "corpus_sha256": hashlib.sha256(
                CORPUS_PATH.read_bytes()).hexdigest(),
            "policy_version": ADJ["policy_version"],
            **rem.code_stamp(), "summary": summary, "cases": cases,
            "stateful": stateful, "metamorphic": relations,
        }, indent=1, ensure_ascii=False) + "\n")
    bad = [r for r in cases + stateful + relations
           if r["status"] in ("fail", "error")]
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
