"""M04 remediation: reproductions of M04-AUDIT-01..21 against a code root.

Each probe drives the REAL production code — ``normalize`` and its
policy objects, the app's ``_vocab_job_state`` / ``_finalized_policy`` /
``_retry_job`` / coordinator ``_worker``, the ``EvidenceCollector`` and the
benchmark / test modules — with SYNTHETIC authored text only, and reports
what it observed. The same script runs against the audited base and the
repaired tree (``--code-root``); where a repair added an internal the
probe says which seam it used (``wiring``).

Inputs and outputs are authored synthetic phrases from the audit and its
corpus (no user transcript, path, audio or credential). AppKit / PyObjC /
sounddevice are the DECLARED non-native shims of
tests/v2/lifecycle/native_shims.py (app-level probes only): a result is a
portable orchestration observation, never native or model evidence.

``reproduced: true`` means the defect's failure mechanism was observed on
that code root; ``false`` means the probe ran and did not observe it.

Usage:
    .venv/bin/python scripts/v2/m04_remediation_repro.py \
        [--code-root DIR] [--output PATH] [--only a01,a02]
Exit code is always 0 (a reproduction is an observation, not a failure).
"""

import argparse
import importlib
import io
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import time
import traceback
from contextlib import redirect_stdout
from decimal import Decimal

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


def run(text, policy=None, context=None):
    res = normalize(text, policy or NormalizationPolicy(), context)
    return {
        "input": text, "output": res.text,
        "edits": [{"cls": e.cls, "input": e.input_text,
                   "output": e.output_text,
                   "value": str(e.value) if e.value is not None else None,
                   "unit": e.unit, "layer": e.layer,
                   "span": e.input_span.as_pair()} for e in res.edits],
        "rejected": [{"cls": r.cls, "input": r.input_text,
                      "reason": r.reason} for r in res.rejected],
        "_res": res,
    }


def clean(r):
    return {k: v for k, v in r.items() if not k.startswith("_")}


# ---------------------------------------------------------------------------
# Parser / grammar probes
# ---------------------------------------------------------------------------

@probe("a01")
def a01():
    pol = NormalizationPolicy(registered_skills={"code review": "code-review"})
    neg = run("we should slash code review time", pol)
    pos = [run(t, pol) for t in ("slash code review",
                                 "add slash code review to the list")]
    return {"negative": clean(neg), "positives": [clean(p) for p in pos],
            "positives_hold": [p["output"] for p in pos] == [
                "/code-review", "add /code-review to the list"],
            "reproduced": any(e["cls"] == "skill" for e in neg["edits"])}


@probe("a02")
def a02():
    cases = {"twelve percent.": "12%.",
             "twelve dollars, please": "$12, please"}
    out = {}
    lost = False
    for s, want in cases.items():
        r = run(s)
        out[s] = clean(r)
        lost |= r["output"] != want
    merged = {}
    for s, forbidden in (("twenty, five percent", "25%"),
                         ("one hundred. five percent", "105%")):
        r = run(s)
        out[s] = clean(r)
        merged[s] = forbidden in r["output"]
    return {"cases": out, "punctuation_lost": lost,
            "quantities_merged_across_delimiter": merged,
            "reproduced": lost or any(merged.values())}


@probe("a03")
def a03():
    oracle = {
        "one point two three four five thousand dollars":
            Decimal("1.2345") * Decimal(1000),
        "zero point zero zero zero one thousand dollars":
            Decimal("0.0001") * Decimal(1000),
    }
    out = {}
    wrong = False
    for s, want in oracle.items():
        r = run(s)
        out[s] = clean(r)
        if r["output"] != s:  # whole literal is an allowed refusal
            shown = Decimal(r["output"].replace("$", "").replace(",", ""))
            out[s]["rendered_amount"] = str(shown)
            out[s]["independent_amount"] = str(want)
            wrong |= shown != want
    ctrl = [run(t)["output"] for t in ("one point five million dollars",
                                       "one point two five thousand dollars")]
    return {"cases": out, "controls": ctrl, "reproduced": wrong}


@probe("a04")
def a04():
    out = {}
    bad = False
    for s in ("zero hundred dollars", "zero thousand dollars",
              "one thousand million dollars", "one million million dollars",
              "a few hundred thousand dollars"):
        r = run(s)
        out[s] = clean(r)
        bad |= r["output"] != s
    return {"cases": out, "reproduced": bad}


@probe("a05")
def a05():
    out = {}
    wrong = False
    r = run("step negative five")
    out["step negative five"] = clean(r)
    for e in r["edits"]:
        if e["cls"] == "anchored_integer":
            wrong |= e["output"].startswith("-") and e["value"] == "5"
    r = run("port negative eighty")
    out["port negative eighty"] = clean(r)
    port_accepted = any(e["cls"] == "port" for e in r["edits"])
    r = run("ten by minus twenty centimeters")
    out["ten by minus twenty centimeters"] = clean(r)
    for e in r["edits"]:
        if e["cls"] == "dimension":
            wrong |= "-20" in e["output"] and "-20" not in (e["value"] or "")
    return {"cases": out, "negative_port_accepted": port_accepted,
            "reproduced": wrong or port_accepted}


@probe("a06")
def a06():
    out = {}
    stolen = False
    for s in ("three fifteen minute breaks", "one twenty minute session"):
        r = run(s)
        out[s] = clean(r)
        stolen |= any(e["cls"] == "time" for e in r["edits"])
    ctrl = {s: run(s)["output"] for s in (
        "at five thirty", "five thirty PM", "at nine oh five am")}
    return {"cases": out, "controls": ctrl, "reproduced": stolen}


@probe("a07")
def a07():
    out = {}
    r1 = run("this may first require approval")
    r2 = run("March thirty second")
    out["modal"] = clean(r1)
    out["invalid_ordinal"] = clean(r2)
    ctrl = {s: run(s)["output"] for s in (
        "March thirty two is invalid", "May first", "September twenty fifth")}
    return {"cases": out, "controls": ctrl,
            "reproduced": (any(e["cls"] == "date" for e in r1["edits"])
                           or any(e["cls"] == "date" for e in r2["edits"]))}


@probe("a08")
def a08():
    out = {}
    partial = False
    for s in ("one point twenty six point four",
              "one dot two dot three dot four dot five",
              "point five percent", "one dot two dot three"):
        r = run(s)
        out[s] = clean(r)
        partial |= r["output"] != s
    ctrl = {s: run(s)["output"] for s in (
        "ten dot zero dot zero dot one",
        "version one point two six point four")}
    return {"cases": out, "controls": ctrl, "reproduced": partial}


@probe("a09")
def a09():
    out = {}
    wrong = 0
    total = 0
    for prof in ("technical", "standard"):
        pol = NormalizationPolicy(profile=prof)
        for s in ("period drama", "time period", "colon cancer",
                  "pipe tobacco", "a question mark",
                  "the forward slash character", "dash I asked him"):
            r = run(s, pol)
            out[f"{prof}:{s}"] = r["output"]
            total += 1
            wrong += r["output"] != s
    ctrl = {s: run(s)["output"] for s in (
        "hello comma how are you", "stop period",
        "grep dash i pattern files")}
    # "time period" is surface-identical to the accepted positive
    # "stop period" (declared residual ambiguity, design D2): reported,
    # but it cannot decide the disposition of the structural defect.
    residual = sum(1 for k, v in out.items()
                   if k.endswith(":time period") and v != "time period")
    return {"outputs": out, "rewritten": wrong, "of": total,
            "declared_residual_rewrites": residual,
            "controls": ctrl, "reproduced": wrong - residual > 0}


@probe("a10")
def a10():
    long_in = "write the phrase " + "alpha " * 12 + "period"
    r1 = run(long_in)
    r2 = run("write the phrase please write the word comma")
    return {"cap_plus_one": clean(r1), "nested": clean(r2),
            "tail_reinterpreted": r1["output"].endswith("."),
            "nested_marker_dropped": r2["output"] == "please comma",
            "reproduced": r1["output"].endswith(".")
            or r2["output"] == "please comma"}


@probe("a11")
def a11():
    r1 = run("path slash Users slash Ada slash MyProject")
    r2 = run("path slash Users slash Ada slash build2")
    r3 = run("/Users/Ada/MyProject")
    hybrid = any(e["cls"] == "path" for e in r2["edits"]) and \
        "slash" in r2["output"]
    return {"mixed_case": clean(r1), "unsupported_tail": clean(r2),
            "written_control": r3["output"],
            "case_lost": r1["output"] == "/users/ada/myproject",
            "hybrid_prefix": hybrid,
            "reproduced": r1["output"] == "/users/ada/myproject" or hybrid}


@probe("a12")
def a12():
    """Isolated subprocess: nested policy mutation after construction."""
    code = r"""
import json, sys
sys.path.insert(0, sys.argv[1])
from localflow.v2.normalize import NormalizationPolicy, normalize
res = {}
p = NormalizationPolicy()
rev0 = p.policy_revision
out0 = normalize("twelve percent", p).text
try:
    p.tables.teens["twelve"] = 13
    res["teens_mutation"] = "accepted"
except Exception as e:
    res["teens_mutation"] = "refused:" + type(e).__name__
res["rev_unchanged"] = p.policy_revision == rev0
res["output_before"] = out0
res["output_after"] = normalize("twelve percent", p).text
q = NormalizationPolicy()
res["fresh_policy_output"] = normalize("twelve percent", q).text
res["fresh_policy_same_revision"] = q.policy_revision == rev0
try:
    p.profile_table["symbols"]["comma"] = {"out": ";", "join": "left"}
    res["symbol_mutation"] = "accepted"
except Exception as e:
    res["symbol_mutation"] = "refused:" + type(e).__name__
res["comma_after"] = normalize("hello comma world", p).text
try:
    p.profile = "standard"
    res["attr_mutation"] = "accepted"
except Exception as e:
    res["attr_mutation"] = "refused:" + type(e).__name__
ids = {"user id": "userId"}
from localflow.v2.normalize import ContextSnapshot
c = ContextSnapshot(identifiers=ids)
ids["user id"] = "USER_ID"
res["context_after_caller_mutation"] = normalize("the user id field", p, c).text
print(json.dumps(res))
"""
    out = subprocess.run([sys.executable, "-c", code, str(CODE)],
                         capture_output=True, text=True, timeout=60)
    res = json.loads(out.stdout.strip().splitlines()[-1])
    res["reproduced"] = (res["teens_mutation"] == "accepted"
                         and res["output_after"] != res["output_before"]
                         and res["rev_unchanged"])
    return res


# ---------------------------------------------------------------------------
# App-level probes (declared non-native shims)
# ---------------------------------------------------------------------------

def _helpers():
    import m03_helpers as h  # noqa: E402  (installs the declared shims)
    return h


@probe("a13")
def a13():
    h = _helpers()
    out = {}
    for configured, explicit in (("technical", "standard"),
                                 ("standard", "technical")):
        with tempfile.TemporaryDirectory() as td:
            a = h.App(td, cfg={"normalization_profile": configured},
                      start_coordinator=False)
            try:
                d = a.d
                mA = {"norm_profile": explicit, "skill_records": (),
                      "skill_records_rev": None}
                pA, _, _ = d._vocab_job_state(None, m10=mA)
                mB = {"norm_profile": None, "skill_records": (),
                      "skill_records_rev": None}
                pB, _, _ = d._vocab_job_state(None, m10=mB)
                # Finalize seam: an inherit job whose base is job A's
                # policy (hotkey-down explicit, finalize resolves inherit).
                pF = d._finalized_policy(pA, {"norm_profile": None,
                                              "skill_records": ()}, None)
                txt = normalize("twelve retries failed", pB).text
                out[f"configured_{configured}"] = {
                    "job_a_profile": pA.profile,
                    "job_b_inherit_profile": pB.profile,
                    "finalize_inherit_profile": pF.profile,
                    "job_b_text": txt,
                }
            finally:
                a.close()
    leaked = any(v["job_b_inherit_profile"] != k.split("_")[1]
                 or v["finalize_inherit_profile"] != k.split("_")[1]
                 for k, v in out.items())
    return {"sequences": out, "wiring": "AppDelegate._vocab_job_state + "
            "_finalized_policy (real methods)", "reproduced": leaked}


@probe("a14")
def a14():
    pol = NormalizationPolicy(registered_skills={"period": "period"})
    ctx = ContextSnapshot(identifiers={"slash period": "/period"})
    r = run("slash period", pol, ctx)
    kept = [(e["cls"], e["layer"]) for e in r["edits"]]
    return {"case": clean(r), "accepted": kept,
            "reproduced": r["output"] != "/period"
            or any(layer != 3 for _, layer in kept)}


@probe("a15")
def a15():
    pol = NormalizationPolicy()
    ctx = ContextSnapshot(identifiers={"user id": "user ID"})
    a = normalize("user id", pol, ctx)
    b = normalize(a.text, pol, ctx)
    return {"first": a.text, "second": b.text,
            "second_edits": [(e.cls, e.input_text, e.output_text)
                             for e in b.edits],
            "is_idempotent": a.is_idempotent(pol, ctx),
            "reproduced": bool(b.edits) and b.text == a.text}


@probe("a16")
def a16():
    from localflow.v2 import ids, store as store_mod, training
    steps = ("text_write", "text_lease", "ledger_write", "ledger_lease")
    out = {}
    for fail_at in steps:
        with tempfile.TemporaryDirectory() as td:
            st = store_mod.Store(pathlib.Path(td) / "v2.db")
            events = []

            def rec(name, **kw):
                events.append((name, kw.get("outcome")))

            consent = training.ConsentManager(st, rec)
            col = training.EvidenceCollector(st, rec, consent,
                                             lambda: {"live": "x"})
            consent.set("enabled")
            ctx = col.job_started(
                ids.new_id("job"), ids.new_id("fam"),
                captured_at_utc=ids.now_utc_iso(), timezone=None,
                utc_offset_minutes=None)
            col.on_asr_result(ctx, "twelve percent", model_id="m",
                              model_revision=None, stage_duration_ms=0.0)
            counter = {"write": 0, "lease": 0}
            real_w, real_l = st.write_text_artifact, st.grant_lease

            def w(**kw):
                if kw.get("stage") == "normalization":
                    counter["write"] += 1
                    if (fail_at == "text_write" and counter["write"] == 1) \
                            or (fail_at == "ledger_write"
                                and kw.get("role") == "normalization_ledger"):
                        raise OSError("synthetic write failure")
                return real_w(**kw)

            def lease(aid, holder, days=None):
                row = st.artifact(aid) if hasattr(st, "artifact") else None
                role = (row or {}).get("role")
                if role in ("normalized_text", "normalization_ledger"):
                    counter["lease"] += 1
                    if (fail_at == "text_lease"
                            and role == "normalized_text") or \
                            (fail_at == "ledger_lease"
                             and role == "normalization_ledger"):
                        raise OSError("synthetic lease failure")
                return real_l(aid, holder, days=days)

            st.write_text_artifact = w
            st.grant_lease = lease
            pol = NormalizationPolicy()
            res = normalize("twelve percent", pol)
            n_events = len(events)
            col.on_normalization_result(ctx, res, source_text="twelve percent",
                                        policy=pol)
            st.write_text_artifact, st.grant_lease = real_w, real_l
            col.on_cleanup_result(ctx, res.text)
            ex = col.finalize(ctx)
            env = st.latest_revision(ex)
            new_events = events[n_events:]
            out[fail_at] = {
                "dictation_text": res.text,
                "envelope_normalization_present":
                    env.get("normalization") is not None,
                "missing_reason": env["missing_reasons"].get("normalization"),
                "failure_event": any(n == "training.capture_failed"
                                     for n, _ in new_events),
                "failure_outcomes": [o for n, o in new_events
                                     if n == "training.capture_failed"],
            }
            st.close()
    silent = any(not v["failure_event"]
                 or v["missing_reason"] == "not_captured_at_stage"
                 for v in out.values())
    return {"injections": out, "reproduced": silent}


@probe("a17")
def a17():
    text = " ".join(["twelve percent and hello comma world period"] * 120)
    pol = NormalizationPolicy()
    samples = []
    for _ in range(5):
        t0 = time.monotonic()
        res = normalize(text, pol)
        ext = (time.monotonic() - t0) * 1000.0
        samples.append((res.duration_ms, ext))
    # Structural check: an injected delay inside the assembly/apply step
    # must be visible in duration_ms.
    import localflow.v2.normalize.engine as eng
    real = eng._apply

    def slow(*a, **k):
        time.sleep(0.05)
        return real(*a, **k)

    eng._apply = slow
    try:
        res = normalize("twelve percent", pol)
    finally:
        eng._apply = real
    return {"dense_samples_internal_vs_external_ms":
            [(round(a, 3), round(b, 3)) for a, b in samples],
            "injected_50ms_apply_delay_reported_ms": round(res.duration_ms, 3),
            "reproduced": res.duration_ms < 50.0}


# ---------------------------------------------------------------------------
# Test-oracle probes
# ---------------------------------------------------------------------------

def _load_test(path):
    spec = importlib.util.spec_from_file_location(
        "m04probe_" + path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _run_all(mod):
    """Run every test_* function of a suite; return failing names."""
    failed = []
    for name in sorted(n for n in dir(mod) if n.startswith("test_")):
        try:
            with redirect_stdout(io.StringIO()):
                getattr(mod, name)()
        except Exception:
            failed.append(name)
    return failed


@probe("a18")
def a18():
    import localflow.v2.normalize.engine as eng
    import localflow.v2.normalize as pkg
    path = CODE / "tests" / "v2" / "normalization" / \
        "test_normalize_numbers.py"
    mod = _load_test(path)
    real = eng.normalize
    mutations = {}

    def sign_flip(text, policy, context=None):
        res = real(text, policy, context)
        from localflow.v2.normalize.span_types import EditRecord
        new = []
        for e in res.edits:
            v = e.value
            if isinstance(v, (int, Decimal)) and not isinstance(v, bool) \
                    and v != 0 and e.cls in ("percent", "currency",
                                             "anchored_integer", "integer",
                                             "unit_number", "port"):
                v = -v
            new.append(EditRecord(**{**e.__dict__, "value": v}))
        res.edits = new
        return res

    for label, fn in (("typed_sign_flip_text_unchanged", sign_flip),):
        mod.normalize = fn
        failed = _run_all(mod)
        mod.normalize = real
        mutations[label] = {"suite_failures": failed,
                            "caught": bool(failed)}
    # The time negative: a different destructive time-like rewrite
    # that avoids the forbidden "5:3" substring.
    def time_break(text, policy, context=None):
        res = real(text, policy, context)
        if text == "chapter five thirty two":
            res.text = "chapter 05h32"
        return res

    mod.normalize = time_break
    failed = _run_all(mod)
    mod.normalize = real
    mutations["time_negative_other_rewrite"] = {
        "suite_failures": failed, "caught": bool(failed)}
    # Unjustified idempotence exception flag on an ordinary fixture.
    data = json.loads((path.parent / "fixtures_numeric.json").read_text())
    for c in data["cases"]:
        if c["case_id"] == "LF-NUM-016":
            c["idempotence_expected"] = False
    mod.FIXTURES = data
    failed = _run_all(mod)
    mutations["unjustified_idempotence_flag"] = {
        "suite_failures": failed, "caught": bool(failed)}
    _ = pkg
    return {"mutations": mutations,
            "reproduced": not all(m["caught"] for m in mutations.values())}


@probe("a19")
def a19():
    """Does the AC04 scanner see a nested module / transitive alias?"""
    path = CODE / "tests" / "v2" / "normalization" / \
        "test_normalize_syntax.py"
    mod = _load_test(path)
    with tempfile.TemporaryDirectory() as td:
        pkg = pathlib.Path(td) / "normalize"
        (pkg / "helpers").mkdir(parents=True)
        for f in (CODE / "localflow" / "v2" / "normalize").glob("*.py"):
            (pkg / f.name).write_text(f.read_text())
        # A nested helper reaching a forbidden capability through an
        # alias (never executed).
        (pkg / "helpers" / "__init__.py").write_text("")
        (pkg / "helpers" / "run.py").write_text(
            "import os as _o\nRUN = getattr(_o, 'sys' + 'tem')\n")
        mod.PKG = pkg
        try:
            with redirect_stdout(io.StringIO()):
                mod.test_no_shell_no_enter_no_skill_execution()
            detected = False
        except AssertionError:
            detected = True
    return {"nested_alias_detected": detected, "reproduced": not detected}


@probe("a20")
def a20():
    path = CODE / "scripts" / "v2" / "benchmark_m04.py"
    spec = importlib.util.spec_from_file_location("m04probe_bench", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    from localflow.v2.normalize.span_types import NormalizationResult

    def identity(text, policy, context=None):
        return NormalizationResult(text=text, edits=[], rejected=[],
                                   protected=[],
                                   policy_revision=policy.policy_revision,
                                   applied=True, duration_ms=0.0)

    mod.normalize = identity
    argv = sys.argv
    sys.argv = ["benchmark_m04.py"]
    try:
        with redirect_stdout(io.StringIO()):
            try:
                code = mod.main()
            except SystemExit as e:
                code = e.code
    finally:
        sys.argv = argv
    return {"identity_normalizer_exit": code,
            "reproduced": code == 0}


@probe("a21")
def a21():
    """Caller inventory + a manual retry after a style-override job."""
    import ast
    callers = []
    for py in sorted((CODE / "localflow").rglob("*.py")):
        rel = py.relative_to(CODE).as_posix()
        if rel.startswith("localflow/v2/normalize/"):
            continue
        tree = ast.parse(py.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                f = node.func
                name = f.attr if isinstance(f, ast.Attribute) else \
                    getattr(f, "id", None)
                if name in ("normalize", "preview_phrase", "is_idempotent",
                            "replay"):
                    callers.append(f"{rel}:{node.lineno}:{name}")
    h = _helpers()
    retry = {}
    with tempfile.TemporaryDirectory() as td:
        a = h.App(td, start_coordinator=False)
        try:
            d = a.d
            # A previous live job resolved an explicit 'standard' style.
            d._vocab_job_state(None, m10={"norm_profile": "standard",
                                          "skill_records": (),
                                          "skill_records_rev": None})
            jid, fam = d.store.create_job(boot_id="boot-previous",
                                          captured_at_utc=h.T0,
                                          time_quality="known",
                                          state="capturing")
            a.journal.mkdir(parents=True, exist_ok=True)
            h.v1_journal(a.journal / f"job-{jid}.blk", jid, h.blocks_of(12))
            d._recover_journals()
            info = next(i for i in d._recoverable if i["job_id"] == jid)
            sup = h.GateSup(text="twelve retries failed")
            seen = []
            real_clean = sup.clean

            def clean(**kw):
                seen.append(kw.get("raw_text"))
                return real_clean(**kw)

            sup.clean = clean
            a.set_sup(sup)
            a.start_coordinator()
            d._retry_job(info)
            a.wait_call("_finishWithText_", 15)
            a.drain()
            retry = {"configured_profile": "technical",
                     "retry_cleanup_input": seen[:1]}
        finally:
            a.close()
    leaked = retry.get("retry_cleanup_input") == ["twelve retries failed"]
    return {"callers": callers, "retry": retry,
            "retry_used_previous_jobs_style": leaked,
            "reproduced": leaked}


def main():
    names = sorted(PROBES)
    if ARGS.only:
        names = [n for n in names if n in ARGS.only.split(",")]
    out = {"schema_version": 1, "tool": "scripts/v2/m04_remediation_repro.py",
           "code_root_sha": subprocess.run(
               ["git", "-C", str(CODE), "rev-parse", "HEAD"],
               capture_output=True, text=True).stdout.strip(),
           "working_tree_modified": bool(subprocess.run(
               ["git", "-C", str(CODE), "status", "--porcelain",
                "--untracked-files=no"], capture_output=True,
               text=True).stdout.strip()),
           "python": sys.version.split()[0],
           "evaluated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                          time.gmtime()),
           "findings": {}}
    for n in names:
        t0 = time.monotonic()
        try:
            res = PROBES[n]()
        except Exception as e:
            res = {"probe_error": type(e).__name__,
                   "trace_tail": traceback.format_exc().splitlines()[-4:]}
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
        pathlib.Path(ARGS.output).write_text(text + "\n")
    else:
        print(text)
    os._exit(0)  # coordinator daemon threads of app probes


if __name__ == "__main__":
    main()
