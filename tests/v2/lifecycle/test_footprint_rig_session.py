"""The footprint rig's worker session against the PRODUCTION worker.

``WorkerSession`` plays the supervisor over the real protocol. These tests
run it against ``prod_worker_harness.py`` (the real ``Worker.serve`` with
only the two model loaders shimmed), so they prove the rig's framing, its
guard, its timing fields and its memory-sample capture. No model runs and
no figure here is a footprint or a latency of any model.

Run: .venv/bin/python tests/v2/lifecycle/test_footprint_rig_session.py
"""

import contextlib
import hashlib
import io
import json
import os
import pathlib
import sys
import subprocess
import threading
import time
import types

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from m03_helpers import PROD, ROOT, run, tmpdir, wav  # noqa: E402

sys.path.insert(0, str(ROOT / "scripts" / "v2"))

import footprint_rig as fr  # noqa: E402

IDENTITY = {"asr_model": "fake-asr", "cleanup_model": "fake-llm"}
LABELS = ["asr_loaded", "asr_warmed", "cleanup_loaded", "cleanup_warmed",
          "asr_result", "cleanup_result"]
ASR_REQUEST = {"audio": {"name": "clip.wav"}, "sample_rate": 16000}
FIRST_REQUEST_METHOD = "judged on ABBA blocks of two spawn pairs"


def _session(td, plan, memory_diag=False, idle_unload_s=0):
    td = pathlib.Path(td)
    wav(td / "audio", "clip.wav")
    plan_path = td / "plan.json"
    plan_path.write_text(json.dumps(plan))
    return fr.WorkerSession(
        ROOT, td / "audio", IDENTITY, memory_diag=memory_diag,
        idle_unload_s=idle_unload_s,
        cmd=[sys.executable, str(PROD), "--audio-root", str(td / "audio")],
        env={"LOCALFLOW_PROD_WORKER_PLAN": str(plan_path),
             "LOCALFLOW_CODE_ROOT": str(ROOT)})


def test_session_runs_both_requests_and_times_them():
    with tmpdir() as td:
        plan = {"transcribe": ["ok:asr text"], "clean": ["ok:CLEANED"]}
        with _session(td, plan) as s:
            hello = s.start()
            assert hello["pid"] == s.pid
            s.load()
            asr = s.request("transcribe", ASR_REQUEST)
            assert asr["frame"]["text"] == "asr text"
            assert asr["frame"]["generation"] == 1
            assert asr["rtt_ms"] > 0
            assert asr["rtt_ms"] >= asr["frame"]["duration_ms"], \
                "the round trip contains the worker's stage"
            clean = s.request("clean", {"raw_text": "um hello"})
            assert clean["frame"]["text"] == "CLEANED"
            assert clean["rtt_ms"] > 0
        assert s.memory_samples == [], "no memory frames with the switch off"
    print("ok  session: load, one transcription, one cleanup, round-trip"
          " time per request, no memory frames with the switch off")


def test_session_captures_the_six_memory_labels():
    with tmpdir() as td:
        plan = {"transcribe": ["ok:asr text"], "clean": ["ok:CLEANED"]}
        with _session(td, plan, memory_diag=True) as s:
            s.start()
            s.load()
            s.request("transcribe", ASR_REQUEST)
            s.request("clean", {"raw_text": "um hello"})
            samples = s.wait_memory(6, 15)
        assert [m["label"] for m in samples] == LABELS
        assert all(set(m) == {"label", "active", "cached", "peak"}
                   for m in samples)
    print("ok  session: six memory samples captured in lifecycle order")


def test_session_stops_when_an_engine_fails_to_load():
    with tmpdir() as td:
        try:
            with _session(td, {"asr_load": "fail"}) as s:
                s.start()
                s.load()
            raise AssertionError("a failed engine did not stop the run")
        except fr.RigStop as e:
            assert "failed" in str(e)
    print("ok  session: a failed engine stops the run")


def test_session_stops_on_a_worker_fault():
    with tmpdir() as td:
        try:
            with _session(td, {"transcribe": ["raise:boom"]}) as s:
                s.start()
                s.load()
                s.request("transcribe", ASR_REQUEST)
            raise AssertionError("a fault frame did not stop the run")
        except fr.RigStop as e:
            assert "stage_exception" in str(e) and "boom" not in str(e)
    print("ok  session: a fault frame stops the run, reason code only")


def test_back_to_back_sends_return_in_order():
    with tmpdir() as td:
        plan = {"clean": ["ok:ONE", "ok:TWO"]}
        with _session(td, plan) as s:
            s.start()
            s.load()
            first = s.send("clean", {"raw_text": "one"})
            second = s.send("clean", {"raw_text": "two"})
            r1 = s.collect(*first)
            r2 = s.collect(*second)
        assert (r1["frame"]["text"], r2["frame"]["text"]) == ("ONE", "TWO")
        assert r2["received_at"] > r1["received_at"]
        gap = fr.back_to_back_gap_ms(r1["received_at"], r2["received_at"],
                                     r2["frame"]["duration_ms"])
        assert gap > -1.0
    print("ok  session: two sends without a pause come back in order with"
          " arrival times for the gap")


IDLE_ENV = "LOCALFLOW_WORKER_IDLE_UNLOAD_S"


class _Spawned(Exception):
    pass


class _spawn_spy:
    """Record the environment of every worker process the rig starts, and
    (with ``stop``) refuse to start it. A worker is the one process the rig
    starts with an explicit environment; every other command it runs
    (``sysctl``, ``pmset``, ``git``) passes through untouched."""

    def __init__(self, stop=False):
        self.envs, self._stop = [], stop

    def __enter__(self):
        self._real = subprocess.Popen

        def popen(cmd, *args, **kw):
            if kw.get("env") is not None:
                self.envs.append(dict(kw["env"]))
                if self._stop:
                    raise _Spawned()
            return self._real(cmd, *args, **kw)
        subprocess.Popen = popen
        return self

    def __exit__(self, *exc):
        subprocess.Popen = self._real
        return False


def test_a_session_names_its_idle_unload_value_and_defaults_to_off():
    plan = {"transcribe": ["ok:x"], "clean": ["ok:x"]}
    seen = {}
    old = os.environ.get(IDLE_ENV)
    os.environ[IDLE_ENV] = "3"      # an ambient value must never leak in
    try:
        for name, kwargs in (("default", {}), ("off", {"idle_unload_s": 0}),
                             ("on", {"idle_unload_s": 6.0})):
            with tmpdir() as td, _spawn_spy(stop=True) as spy:
                s = fr.WorkerSession(
                    ROOT, td, IDENTITY, cmd=[sys.executable, "-c", "pass"],
                    env={"LOCALFLOW_PROD_WORKER_PLAN": str(plan)}, **kwargs)
                try:
                    s.start()
                except _Spawned:
                    pass
                seen[name] = spy.envs[0][IDLE_ENV]
    finally:
        if old is None:
            os.environ.pop(IDLE_ENV)
        else:
            os.environ[IDLE_ENV] = old
    assert seen == {"default": "0", "off": "0", "on": "6.0"}, seen
    print("ok  session: the worker's idle-unload variable is always set"
          " explicitly: '0' by default, the seconds when asked, never the"
          " ambient value")


def test_session_sees_the_unload_the_reload_and_the_hint():
    with tmpdir() as td:
        plan = {"clean": ["ok:ONE", "ok:TWO"]}
        with _session(td, plan, idle_unload_s=1.0) as s:
            s.start()
            s.load()
            ready = s.cleanup_events("ready", 0.0)
            assert len(ready) == 1
            unloaded = s.wait_unloaded(ready[0], 15.0)
            assert unloaded - ready[0] >= 0.9, "after the idle period"
            assert s.cleanup_events("unloaded", ready[0]) == [unloaded]
            t0 = time.perf_counter()
            s.ensure_cleanup()
            done = s.request("clean", {"raw_text": "um hello"})
            assert done["frame"]["path"] == "llm"
            assert done["frame"]["text"] == "ONE"
            loading = s.cleanup_events("loading", unloaded)
            again = s.cleanup_events("ready", unloaded)
            assert len(loading) == 1 and len(again) == 1
            assert t0 < loading[0] <= again[0] <= done["received_at"]
    print("ok  session: engine frames carry arrival times; the unload is"
          " awaited, ensure_cleanup reloads, one loading and one ready")


def test_a_worker_that_never_unloads_is_reported_not_waited_for():
    with tmpdir() as td:
        with _session(td, {}, idle_unload_s=0) as s:
            s.start()
            s.load()
            after = s.cleanup_events("ready", 0.0)[0]
            t0 = time.monotonic()
            try:
                s.wait_unloaded(after, 1.5)
                raise AssertionError("an unload that never came was found")
            except fr.RigStop as e:
                assert "unloaded" in str(e) and "1.5" in str(e), str(e)
            assert time.monotonic() - t0 < 5.0
    print("ok  session: waiting for an unload that never comes stops the run"
          " with a clear message at the timeout")


def _shim_context(td, counts, record=False, plan=None, idle_unload_s=None):
    """A run context over the shimmed production worker and a tiny
    synthetic corpus: one clip pair per ASR band, the real fixtures. With
    ``record`` each side's worker logs the requests its shims were given to
    ``ctx.records[side]`` (JSON lines); ``plan`` adds shim plan keys to both
    sides and ``idle_unload_s`` is the idle period the idle phase gives
    side B."""
    td = pathlib.Path(td)
    corpus = td / "corpus"
    seconds = {"clip-under-10s": 1, "clip-10-30s": 11, "clip-30-90s": 31,
               "clip-over-90s": 91, "identity-under90": 60,
               "identity-over95": 96}
    clips = []
    for stem, secs in seconds.items():
        names = [f"{stem}-{k:02d}.wav" for k in (0, 1)] \
            if stem.startswith("clip") else [f"{stem}.wav"]
        for name in names:
            path = wav(corpus, name, n=secs * 16000)
            clips.append({
                "name": name, "sha256": hashlib.sha256(
                    path.read_bytes()).hexdigest(),
                "duration_s": float(secs),
                "band": fr.assign_band(secs, fr.ASR_BANDS)
                if stem.startswith("clip") else None})
    manifest = {"clips": clips}
    cases = fr.load_cleanup_cases(ROOT)
    bands = {"cleanup": fr.freeze_bands(
        [(cid, c["words"]) for cid, c in cases.items()], fr.CLEANUP_BANDS),
        "asr": fr.freeze_bands(
            [(c["name"], c["duration_s"]) for c in clips
             if not c["name"].startswith("identity")], fr.ASR_BANDS)}
    plans, records = {}, {}
    for side in ("A", "B"):
        plans[side] = td / f"plan-{side}.json"
        records[side] = td / f"records-{side}.jsonl"
        plans[side].write_text(json.dumps(
            {"hold_gpu_mib": 64, **({"record": str(records[side])}
                                    if record else {}), **(plan or {})}))
    ctx = types.SimpleNamespace(
        run_id="shim-test", mode="early", counts=counts, aa=None,
        roots={"A": ROOT, "B": ROOT}, identity=IDENTITY, revisions={},
        cases=cases, bands=bands, run_dir=td / "run",
        scratch=td / "run" / "scratch", seen=set(), thermal_events=[],
        fixture_texts={c["text"] for c in cases.values()}, weights=[],
        evict_pool=str(td), protect_tokens=[], purge_allowed=False,
        installed_pid=None, installed_pid_now=lambda: None,
        manifest=manifest, records=records, idle_unload_s=idle_unload_s,
        cleanup_weight_bytes=2_000 * fr.MIB)
    ctx.run_dir.mkdir()
    ctx.scratch.mkdir()
    ctx.make_session = lambda side, diag, idle_unload_s=0: fr.WorkerSession(
        ROOT, corpus, IDENTITY, memory_diag=diag, idle_unload_s=idle_unload_s,
        cmd=[sys.executable, str(PROD), "--audio-root", str(corpus)],
        env={"LOCALFLOW_PROD_WORKER_PLAN": str(plans[side]),
             "LOCALFLOW_CODE_ROOT": str(ROOT)})
    return ctx


def test_whole_run_against_the_shim_worker_writes_a_content_free_report():
    counts = {"warm": 1, "cold": 1, "burst": 1, "first": 2, "gap": 2}
    with tmpdir() as td:
        ctx = _shim_context(td, counts)
        with _spawn_spy() as spy:
            fr.measure(ctx, list(fr.PHASES), "2026-10-26T00:00:00-04:00")
        # every existing phase starts its workers with unloading off, on
        # both sides, so none of them can see an unload or a reload
        by_side = {side: [e[IDLE_ENV] for e in spy.envs
                          if e["LOCALFLOW_PROD_WORKER_PLAN"].endswith(
                              f"plan-{side}.json")] for side in "AB"}
        assert all(vals and set(vals) == {"0"} for vals in by_side.values()), \
            by_side
        raw = (ctx.run_dir / "report.json").read_text()
        report = json.loads(raw)
        assert (ctx.run_dir / "bands.json").exists()
        assert report["rig"]["complete"] is True
        assert report["rig"].get("aborted") is None, \
            "the watchdog stays quiet on a healthy run"
        assert report["rig"]["phases"] == list(fr.PHASES)
        # footprint: every spawn read the GPU line beside the total
        spawns = report["footprint"]["spawns"]
        assert len(spawns) == 2 * (counts["warm"] + counts["cold"])
        assert all(s["idle_gpu_bytes"] > 0 and s["idle_total_bytes"]
                   >= s["idle_gpu_bytes"] and s["launch_peak_bytes"] > 0
                   for s in spawns)
        assert {s["label"] for s in spawns} == {"warm", "cold-ish"}
        # bursts: with the switch on, six labels and a counter per result
        bursts = report["bursts"]
        assert len(bursts) == 4 and sorted(b["memory_diag"] for b in bursts) \
            == [False, False, True, True]
        for b in bursts:
            assert b["dictations"] == fr.BURST_DICTATIONS
            if b["memory_diag"]:
                assert sorted(b["memory"]["first"]) == sorted(
                    fr.MEMORY_LABELS)
                assert len(b["memory"]["asr_result_cached"]) == 20
            else:
                assert b["memory"] is None
        # first request and the resident pair
        first_request = report["first_request"]
        assert len(first_request["pairs"]) == counts["first"]
        assert [p["order"] for p in first_request["pairs"]] == ["AB", "BA"]
        # the verdicts are judged on ABBA blocks of two pairs, and say so
        assert first_request["unit"] == "abba_block"
        for by_metric in first_request["verdicts"].values():
            for v in by_metric.values():
                assert v["pairs"] == counts["first"] // 2
        res = report["resident"]
        assert not res["identity"]["mismatches"]
        blocks = res["latency"]["asr"]["10-30s"]["blocks"]
        assert [b["order"] for b in blocks].count("ABBA") == 4
        for clip in {b["case"] for b in blocks}:
            mine = [b["order"] for b in blocks if b["case"] == clip]
            assert all(a != b for a, b in zip(mine, mine[1:])), (clip, mine)
        assert [b["order"] for b in res["gap"]["blocks"]] == ["ABBA", "BAAB"]
        band = res["latency"]["cleanup"]["51-100"]
        assert len(band["warmup_blocks"]) == len(band["plan"]["cases_used"])
        assert len(band["blocks"]) == 8, "warmup blocks are not measured"
        names = set(report["verdicts"]["latency"]["bands"])
        assert {"cleanup:1-20", "cleanup:101-200", "asr:under-10s",
                "asr:over-90s", "first-request:asr",
                "first-request:clean"} <= names
        gap = report["verdicts"]["back_to_back_gap"]
        assert gap["pairs"] == counts["gap"]
        assert report["verdicts"]["rig_validity"] is not None
        assert isinstance(report["judgement"]["ticket_02"]["go"], bool)
        assert "deferred" in report["judgement"]["loader"]
        # nothing the run read leaks into the report
        for text in ctx.fixture_texts:
            assert text not in raw and json.dumps(text)[1:-1] not in raw
        summary = (ctx.run_dir / "SUMMARY.md").read_text()
        assert "Rig validity" in summary and "Go / no-go" in summary
        assert FIRST_REQUEST_METHOD in summary
        assert "No A/A report pinned" in summary
        assert report["rig"]["aa_report"] is None
        first = report["verdicts"]["latency"]["bands"]["asr:10-30s"]
        assert first["aa_median_ms"] is None
        assert first["median_limit_ms"] == first["spec_median_limit_ms"]
        assert "NO-GO ticket 03, close with a note" in summary \
            or "GO ticket 03" in summary
        # the second run pins this run's report as its A/A
        aa_path = ctx.run_dir / "report.json"
        # The shim never splits a clip, so Identity reads "chunker did not
        # run" with no mismatch; the pinning is under test here, not the
        # chunker, so this report stands in for an A/A that passed Identity.
        assert report["verdicts"]["identity"]["mismatches"] == []
        report["verdicts"]["identity"]["pass"] = True
        aa_path.write_text(json.dumps(report, indent=1))
        digest = hashlib.sha256(aa_path.read_bytes()).hexdigest()
        ctx2 = _shim_context(pathlib.Path(td) / "second", counts)
        ctx2.aa = fr.load_aa_report(aa_path, fr.tree_digest(ROOT),
                                    fr.bands_digest(ctx2.bands))
        fr.measure(ctx2, ["first", "resident"], "2026-10-26T00:00:00-04:00")
        report2 = json.loads((ctx2.run_dir / "report.json").read_text())
        assert report2["rig"]["aa_report"] == {"sha256": digest,
                                               "run_id": "shim-test"}
        bands2 = report2["verdicts"]["latency"]["bands"]
        assert set(bands2) == set(report["verdicts"]["latency"]["bands"])
        for name, v in bands2.items():
            was = report["verdicts"]["latency"]["bands"][name]
            assert v["aa_median_ms"] == was["paired_median_ms"], name
            assert v["aa_p95_ms"] == was["paired_p95_ms"], name
            assert v["median_limit_ms"] == max(v["spec_median_limit_ms"],
                                               v["aa_median_ms"]), name
            assert v["p95_limit_ms"] == max(v["spec_p95_limit_ms"],
                                            v["aa_p95_ms"]), name
        gap2 = report2["verdicts"]["back_to_back_gap"]
        assert gap2["aa_median_ms"] == gap["paired_median_ms"]
        assert gap2["limit_ms"] == max(gap2["spec_limit_ms"],
                                       gap2["aa_median_ms"])
        summary2 = (ctx2.run_dir / "SUMMARY.md").read_text()
        assert digest in summary2 and "A/A report shim-test" in summary2
    print("ok  whole run against the shim worker: four phases, frozen bands"
          " on disk, verdicts, judgement, summary, no fixture text in the"
          " report")


def test_a_first_request_only_run_states_its_unit_in_the_method():
    counts = {"warm": 1, "cold": 1, "burst": 1, "first": 2, "gap": 2}
    with tmpdir() as td:
        ctx = _shim_context(td, counts)
        fr.measure(ctx, ["first"], "2026-10-26T00:00:00-04:00")
        summary = (ctx.run_dir / "SUMMARY.md").read_text()
        assert "## Method" in summary and FIRST_REQUEST_METHOD in summary
        assert "interleave one unmeasured cleanup" not in summary, \
            "the ASR note belongs to runs that measured the resident bands"
    print("ok  shim run: a first-request-only summary states that its rows"
          " are judged on ABBA blocks")


def test_a_first_request_only_run_states_an_identity_verdict():
    counts = {"warm": 1, "cold": 1, "burst": 1, "first": 2, "gap": 2}
    with tmpdir() as td:
        ctx = _shim_context(td, counts)
        fr.measure(ctx, ["first"], "2026-10-26T00:00:00-04:00")
        report = json.loads((ctx.run_dir / "report.json").read_text())
        assert report["first_request"]["mismatches"] == []
        assert report["verdicts"]["identity"] == {
            "pass": True, "mismatches": [], "chunker_ran": None,
            "inconsistent_across_blocks": [],
            "first_request_compared": True}
        summary = (ctx.run_dir / "SUMMARY.md").read_text()
        assert "Identity A against B: pass" in summary
        assert "chunker ran: n/a" in summary
        assert "first-request outputs compared" in summary
    print("ok  shim run: a first-request-only run states an Identity verdict"
          " and its summary says the first-request outputs were compared")


def test_a_first_request_output_mismatch_fails_identity_in_a_whole_run():
    counts = {"warm": 1, "cold": 1, "burst": 1, "first": 2, "gap": 2}
    with tmpdir() as td:
        ctx = _shim_context(td, counts)
        # side B's ASR now answers with other words; side A keeps its own
        (pathlib.Path(td) / "plan-B.json").write_text(json.dumps({
            "hold_gpu_mib": 64, "transcribe": ["ok:other words from B"]}))
        code = fr.measure(ctx, ["first"], "2026-10-26T00:00:00-04:00")
        report = json.loads((ctx.run_dir / "report.json").read_text())
        ident = report["verdicts"]["identity"]
        assert ident["pass"] is False
        assert ident["mismatches"] == [
            "first-request:asr:text_sha256 (pair 1)",
            "first-request:asr:text_sha256 (pair 2)"]
        assert code == 1, "a failed Identity check exits non-zero"
        summary = (ctx.run_dir / "SUMMARY.md").read_text()
        assert "Identity A against B: FAIL" in summary
        assert "other words from B" not in summary
    print("ok  shim run: differing first-request ASR text fails Identity by"
          " name, exits non-zero, and no output text reaches the summary")


def _real_build_context(td, aa_path, code_root=ROOT, aa=True):
    """The real ``build_context`` over the synthetic corpus in ``td``, with
    only the process list, the model identity and the model cache stubbed.
    ``aa`` False builds it without a pinned A/A report."""
    td = pathlib.Path(td)
    snap = {"snapshot": "snap", "files": []}
    argv = ["--code-root-a", str(code_root),
            "--corpus-dir", str(td / "corpus")]
    if aa:
        argv += ["--aa-report", str(aa_path)]
    with _patched(_tool_text=lambda *a, **k: "",
                  resolve_model_identity=lambda *a: IDENTITY,
                  locate_models=lambda identity: {"asr": snap,
                                                  "cleanup": snap}):
        return fr.build_context(fr.parse_args(argv), td / "run2",
                                td / "corpus", "second")


def test_the_real_context_makes_sessions_with_an_explicit_idle_value():
    with tmpdir() as td:
        td = pathlib.Path(td)
        shim = _shim_context(td, {"first": 2})
        (td / "corpus" / "manifest.json").write_text(
            json.dumps(shim.manifest))
        ctx = _real_build_context(td, None, aa=False)
        seen = []
        for args in (("A", False), ("B", True), ("B", False, 6.0)):
            with _spawn_spy(stop=True) as spy:
                try:
                    ctx.make_session(*args).start()
                except _Spawned:
                    pass
            seen.append(spy.envs[0][IDLE_ENV])
        assert seen == ["0", "0", "6.0"], seen
    print("ok  build_context: sessions made without an idle period start with"
          " unloading off, one made with it starts with those seconds")


def test_the_idle_phase_is_accepted_by_phases_and_not_run_by_default():
    with tmpdir() as td:
        td = pathlib.Path(td)
        argv = ["--code-root-a", str(ROOT), "--evidence-root", str(td / "ev"),
                "--lock", str(td / "measure.lock"), "--run-id", "idle-test",
                "--phases", "idle"]
        err = io.StringIO()
        with _patched(build_context=_stop_in_build_context):
            with contextlib.redirect_stdout(io.StringIO()), \
                    contextlib.redirect_stderr(err):
                code = fr.main(argv)
        assert code == 2 and "STOP: no corpus" in err.getvalue(), \
            err.getvalue()
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code = fr.main(argv[:-1] + ["idle,nonsense"])
        assert code == 2 and "unknown phase" in err.getvalue() \
            and "nonsense" in err.getvalue()
    print("ok  main: --phases idle passes validation; an unknown phase name"
          " is still refused")


def test_the_pinned_aa_is_checked_against_this_runs_bands_and_side_a_tree():
    counts = {"warm": 1, "cold": 1, "burst": 1, "first": 2, "gap": 2}
    with tmpdir() as td:
        td = pathlib.Path(td)
        ctx = _shim_context(td, counts)
        manifest = td / "corpus" / "manifest.json"
        manifest.write_text(json.dumps(ctx.manifest))
        fr.measure(ctx, ["first"], "2026-10-26T00:00:00-04:00")
        aa_path = ctx.run_dir / "report.json"
        # the digests build_context computes are the ones measure recorded
        pinned = _real_build_context(td, aa_path)
        assert pinned.aa["run_id"] == "shim-test"
        # a corpus that freezes other bands is refused
        fewer = {"clips": ctx.manifest["clips"][1:]}
        manifest.write_text(json.dumps(fewer))
        _stops(lambda: _real_build_context(td, aa_path), "different bands")
        manifest.write_text(json.dumps(ctx.manifest))
        # so is a side A that holds another localflow tree
        other = td / "other"
        (other / "localflow").mkdir(parents=True)
        (other / "localflow" / "mod.py").write_text("x = 1\n")
        _stops(lambda: _real_build_context(td, aa_path, other),
               "different localflow tree")
    print("ok  build_context: the pinned A/A must hold this run's bands and"
          " side-A tree; an honest A/A is accepted")


# ---- the idle phase against the shim worker -------------------------------------

RELOAD_MS = 400


def _stub_footprint(cycle_mib):
    """A footprint reader for the idle phase. The phase reads side B only, in
    the order ready, unloaded, ready, unloaded...: its reads on the main
    thread take ``cycle_mib`` in turn; the watchdog's thread gets a constant,
    so it cannot shift the sequence."""
    calls = []

    def read(pid, scratch):
        if threading.current_thread() is not threading.main_thread():
            return {"total_bytes": 1, "gpu_bytes": 1, "gpu_regions": 1,
                    "categories": {}}
        mib = cycle_mib[len(calls) % len(cycle_mib)]
        calls.append(pid)
        return {"total_bytes": mib * fr.MIB, "gpu_bytes": mib * fr.MIB // 2,
                "gpu_regions": 1, "categories": {}}
    read.calls = calls
    return read


class _hints_sent:
    """Count the ensure_cleanup hints each side's session writes."""

    def __enter__(self):
        self.sides = []
        self._real = fr.WorkerSession.ensure_cleanup
        outer = self

        def spy(session):
            plan = session._env["LOCALFLOW_PROD_WORKER_PLAN"]
            outer.sides.append("B" if plan.endswith("plan-B.json") else "A")
            outer._real(session)
        fr.WorkerSession.ensure_cleanup = spy
        return self

    def __exit__(self, *exc):
        fr.WorkerSession.ensure_cleanup = self._real
        return False


def _idle_run(td, plan_b=None, captures=(0.1, 0.9), pairs=2,
              cycle=(4000, 1800, 4100, 2000)):
    """The idle phase over the shim worker with short captures and a reload
    of RELOAD_MS; returns the context, the exit status, the footprint reader
    and the hints each side was sent."""
    ctx = _shim_context(td, {"idle": pairs}, idle_unload_s=1.0,
                        plan={"cleanup_reload_delay_ms": RELOAD_MS})
    ctx.cleanup_weight_bytes = 2500 * fr.MIB
    # Side A's speech engine loads for longer than the idle period, so in a
    # pair where side B loads first it unloads while side A is still loading.
    (pathlib.Path(td) / "plan-A.json").write_text(json.dumps({
        "hold_gpu_mib": 64, "asr_load_delay_ms": 1500}))
    if plan_b is not None:
        (pathlib.Path(td) / "plan-B.json").write_text(json.dumps({
            "hold_gpu_mib": 64, "cleanup_reload_delay_ms": RELOAD_MS,
            **plan_b}))
    footprint = _stub_footprint(cycle)
    with _patched(IDLE_CAPTURE_S=captures, SETTLE_S=0.2,
                  read_footprint=footprint), _hints_sent() as hints:
        code = fr.measure(ctx, ["idle"], "2026-10-27T00:00:00-04:00")
    return ctx, code, footprint, hints.sides


def test_the_idle_phase_measures_a_dictation_after_an_unload():
    with tmpdir() as td:
        ctx, code, footprint, hints = _idle_run(td)
        raw = (ctx.run_dir / "report.json").read_text()
        report = json.loads(raw)
        assert report["rig"]["complete"] is True and code == 0, \
            "a failing short capture is no abort and no non-zero exit"
        assert report["rig"]["phases"] == ["idle"]
        idle = report["idle"]
        assert idle["idle_unload_s"] == 1.0
        assert idle["capture_s"] == [0.1, 0.9] and idle["unit"] == "abba_block"
        assert [p["order"] for p in idle["pairs"]] == ["AB", "BA"]
        # only side B was ever hinted: once per capture, twice in the second
        # dictation, in each of the two pairs
        assert sorted(hints) == ["B"] * 8, hints
        # per capture: the reload took at least its shim time, and a
        # capture shorter than that leaves the difference to wait
        for pair in idle["pairs"]:
            short, long = pair["captures"]["D0.1s"], pair["captures"]["D0.9s"]
            for cap, d in ((short, 0.1), (long, 0.9)):
                assert cap["B"]["reload_ms"] >= RELOAD_MS
                assert cap["B"]["clean"]["path"] == "llm"
                assert "reload_ms" not in cap["A"]
            assert short["B"]["release_to_result_ms"] >= RELOAD_MS / 2, \
                "side B waited for the reload"
            assert short["A"]["release_to_result_ms"] < RELOAD_MS / 2
            assert long["B"]["release_to_result_ms"] < RELOAD_MS / 2, \
                "a capture longer than the reload hides it"
        bands = idle["bands"]
        assert list(bands) == ["idle:D0.1s", "idle:D0.9s"]
        assert all(b["pairs"] == 1 for b in bands.values())
        assert bands["idle:D0.1s"]["pass"] is False, "the accepted wait"
        assert bands["idle:D0.1s"]["reload_remainder_median_ms"] \
            >= RELOAD_MS - 100
        assert bands["idle:D0.9s"]["reload_remainder_median_ms"] == 0.0
        assert idle["reload"]["min_ms"] >= RELOAD_MS
        # the footprint numbers come from the stubbed reader: ready 4000 and
        # 4100, unloaded 1800 and 2000, so the drops are 2200 and 2100
        assert len(footprint.calls) == 8
        first = idle["pairs"][0]["captures"]
        assert first["D0.1s"]["footprint"] == {
            "ready": {"total_bytes": 4000 * fr.MIB,
                      "gpu_bytes": 2000 * fr.MIB},
            "unloaded": {"total_bytes": 1800 * fr.MIB,
                         "gpu_bytes": 900 * fr.MIB},
            "drop_bytes": 2200 * fr.MIB}
        assert first["D0.9s"]["footprint"]["drop_bytes"] == 2100 * fr.MIB
        drop = idle["footprint"]
        assert drop["drop_bytes"] == {"median": 2150 * fr.MIB,
                                      "min": 2100 * fr.MIB,
                                      "max": 2200 * fr.MIB}
        assert drop["cleanup_weight_bytes"] == 2500 * fr.MIB
        assert drop["share_of_weights"] == 0.86
        # never degraded, identity, and the second dictation
        assert idle["never_degraded"] == {"requests": 2 * (2 + 2)}
        assert idle["mismatches"] == []
        second = idle["second_dictation"]
        assert second["all_single_reload"] is True
        for pair in idle["pairs"]:
            b, a = pair["second"]["B"], pair["second"]["A"]
            assert b["reloads"] == 1 and "reloads" not in a
            assert [c["path"] for c in b["clean"]] == ["llm", "llm"]
            assert b["last_result_ms"] >= RELOAD_MS
            assert a["last_result_ms"] >= fr.SECOND_DICTATION_DELAY_S * 1000
        ident = report["verdicts"]["identity"]
        assert ident["pass"] is True and ident["idle_compared"] is True
        assert report["verdicts"]["latency"]["bands"] == {}, \
            "idle bands are not Latency bands"
        # nothing the run read leaks into the report
        for text in ctx.fixture_texts:
            assert text not in raw and json.dumps(text)[1:-1] not in raw
        summary = (ctx.run_dir / "SUMMARY.md").read_text()
        for needle in ("## Idle unload", "| D0.1s |", "| D0.9s |",
                       "2,150 MiB", "86%", "Never degraded",
                       "Identity A against B (idle outputs): pass",
                       "exactly one reload after the unload: pass",
                       "side B unloads the cleanup model after 1 idle"
                       " seconds and side A never unloads"):
            assert needle in summary, needle
    print("ok  idle phase over the shim worker: per-capture bands, reload"
          " times and remainders, the stubbed footprint drop and its share,"
          " never degraded, identity and the second dictation in one"
          " report and summary")


def test_an_idle_output_mismatch_fails_identity_in_a_whole_run():
    with tmpdir() as td:
        # side B's first ASR answer in each pair is another text
        ctx, code, _, _ = _idle_run(
            td, plan_b={"transcribe": ["ok:other words from B"]},
            captures=(0.1,), cycle=(4000, 1800))
        report = json.loads((ctx.run_dir / "report.json").read_text())
        ident = report["verdicts"]["identity"]
        assert ident["pass"] is False
        assert ident["mismatches"] == [
            "idle:D0.1s:asr:text_sha256 (pair 1)",
            "idle:D0.1s:asr:text_sha256 (pair 2)"], ident["mismatches"]
        assert code == 1, "a failed Identity check exits non-zero"
        summary = (ctx.run_dir / "SUMMARY.md").read_text()
        assert "Identity A against B (idle outputs): FAIL" in summary
        assert "other words from B" not in summary
    print("ok  idle phase: differing outputs fail Identity by name, exit"
          " non-zero, and no output text reaches the summary")


def test_a_degraded_cleanup_after_an_unload_stops_the_run():
    with tmpdir() as td:
        try:
            _idle_run(td, plan_b={"clean": ["degraded:shim secret words"]},
                      captures=(0.1,), cycle=(4000, 1800))
            raise AssertionError("a degraded answer did not stop the run")
        except fr.RigStop as e:
            assert "degraded" in str(e) and "llm_fallback_normalized" in \
                str(e) and "shim_degraded" in str(e), str(e)
            assert "shim secret words" not in str(e)
    print("ok  idle phase: a cleanup answered degraded during an unload or"
          " reload stops the run, reason codes only")


def _requests_seen(path):
    """The worker's own record of what it was asked, in order: ``transcribe``
    and ``engine_clean`` events only."""
    events = [json.loads(line)["event"]
              for line in pathlib.Path(path).read_text().splitlines()]
    return [e for e in events if e in ("transcribe", "engine_clean")]


def test_asr_bands_interleave_an_unmeasured_cleanup_on_both_sides():
    counts = {"warm": 1, "cold": 1, "burst": 1, "first": 2, "gap": 2}
    with tmpdir() as td:
        ctx = _shim_context(td, counts, record=True)
        fr.measure(ctx, ["resident"], "2026-10-26T00:00:00-04:00")
        report = json.loads((ctx.run_dir / "report.json").read_text())
        res = report["resident"]
        per_side = {side: _requests_seen(path)
                    for side, path in ctx.records.items()}
        assert per_side["A"] == per_side["B"], \
            "both sides received exactly the same requests"
        seen = per_side["A"]
        # Worked counts, from the report's own record of what was measured:
        # a band's blocks (and warmup blocks) hold four requests, two per
        # side; the gap blocks send four cleanups to each side.
        lat = res["latency"]
        asr = 2 * sum(len(b["warmup_blocks"]) + len(b["blocks"])
                      for b in lat["asr"].values())
        clean = 2 * sum(len(b["warmup_blocks"]) + len(b["blocks"])
                        for b in lat["cleanup"].values())
        gap = 4 * len(res["gap"]["blocks"])
        identity_clips = len(fr.IDENTITY_CLIPS)
        assert seen.count("transcribe") == identity_clips + asr
        assert seen.count("engine_clean") == \
            len(ctx.cases) + clean + gap + asr, \
            "one unmeasured cleanup per measured ASR request, no others"
        # every ASR request outside the identity pass is followed at once
        # by a cleanup
        at = [i for i, e in enumerate(seen) if e == "transcribe"]
        for i in at[identity_clips:]:
            assert seen[i + 1] == "engine_clean", i
        # the extra requests never reach a verdict, pair or block record
        for b in lat["asr"].values():
            for block in b["warmup_blocks"] + b["blocks"]:
                assert len(block["rtt_ms"]) == 4
        summary = (ctx.run_dir / "SUMMARY.md").read_text()
        assert "## Method" in summary
        assert ("interleave one unmeasured cleanup request after each ASR"
                " request") in summary
    print("ok  shim run: every ASR request is followed by one unmeasured"
          " cleanup, identical on both sides, outside every record")


def _stops(fn, needle):
    try:
        fn()
    except fr.RigStop as e:
        assert needle in str(e), (needle, str(e))
        return
    raise AssertionError("expected RigStop")


class _patched:
    """Replace module attributes of the rig for the length of a block."""

    def __init__(self, **attrs):
        self._attrs, self._saved = attrs, {}

    def __enter__(self):
        for name, value in self._attrs.items():
            self._saved[name] = getattr(fr, name)
            setattr(fr, name, value)

    def __exit__(self, *exc):
        for name, value in self._saved.items():
            setattr(fr, name, value)
        return False


def _aborted_run(td, **patches):
    """``fr.main`` over the shim worker with the watchdog's limits or
    readings patched; returns the exit code, the report, both log streams
    and the lock path."""
    td = pathlib.Path(td)
    counts = {"warm": 1, "cold": 1, "burst": 1, "first": 2, "gap": 2}
    ctx = _shim_context(td, counts)
    lock = td / "measure.lock"
    argv = ["--code-root-a", str(ROOT), "--evidence-root", str(td / "ev"),
            "--lock", str(lock), "--run-id", "watchdog-test",
            "--phases", "resident"]
    out, err = io.StringIO(), io.StringIO()
    with _patched(build_context=lambda *a: ctx, WATCHDOG_INTERVAL_S=0.1,
                  **patches):
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = fr.main(argv)
    report = json.loads((ctx.run_dir / "report.json").read_text())
    return code, report, out.getvalue(), err.getvalue(), lock


def _assert_aborted(td, code, report, out, err, lock, needle):
    reason = report["rig"]["aborted"]["reason"]
    assert needle in reason, reason
    assert code != 0, "an aborted run exits non-zero"
    assert report["rig"]["complete"] is False
    assert reason in err and "aborted by the watchdog" in err
    assert reason in out, "the reason is in the log as well"
    os.close(fr.acquire_lock(lock))  # the lock was released
    assert "verdicts" not in report, "an aborted run states no verdict"
    summary = (pathlib.Path(td) / "run" / "SUMMARY.md").read_text()
    assert reason in summary and "complete: False" in summary, \
        "the summary states the abort and the incomplete run"
    assert "complete: True" not in summary and "Go / no-go" not in summary


def _trip_after_finish(reason):
    """Patches for ``_aborted_run``: the watchdog trips just after ``finish``
    wrote its complete report, as it can while the final reads run."""
    dogs = []

    class Captured(fr.Watchdog):
        def __init__(self, scratch):
            super().__init__(scratch)
            dogs.append(self)

    finish = fr.finish

    def finish_then_trip(ctx, report):
        finish(ctx, report)
        dogs[0]._trip(reason)
    return {"Watchdog": Captured, "finish": finish_then_trip}


def test_a_worker_over_the_footprint_limit_aborts_the_run():
    with tmpdir() as td:
        code, report, out, err, lock = _aborted_run(
            td, WATCHDOG_FOOTPRINT_LIMIT_BYTES=1)
        _assert_aborted(td, code, report, out, err, lock, "footprint")
    print("ok  shim run: a worker over the footprint limit is killed, the"
          " report and log say why, the exit is non-zero, the lock is free")


def test_swap_growth_aborts_the_run():
    readings = iter([5 << 30])  # the starting value, then 3 GiB more

    def swap():
        return next(readings, 8 << 30)

    with tmpdir() as td:
        code, report, out, err, lock = _aborted_run(td, read_swap_used=swap)
        _assert_aborted(td, code, report, out, err, lock, "swap")
    print("ok  shim run: swap growth over its starting value aborts the run"
          " the same way")


def test_a_trip_after_the_report_was_finished_leaves_one_aborted_state():
    with tmpdir() as td:
        code, report, out, err, lock = _aborted_run(
            td, **_trip_after_finish("swap used grew late"))
        _assert_aborted(td, code, report, out, err, lock, "late")
        assert "judgement" not in report
        assert report["rig"]["finished_at"] is None
        summary = (pathlib.Path(td) / "run" / "SUMMARY.md").read_text()
        assert "## Latency" not in summary, "no figure of the finished run"
    print("ok  shim run: a trip after finish rewrites the report and the"
          " summary to the same aborted, incomplete state")


def _stop_in_build_context(*args):
    raise fr.RigStop("no corpus at the test path")


def _main_with(td, build_context, run_id):
    """``fr.main`` over an evidence root under ``td`` with ``build_context``
    replaced; returns the exit code and the error log."""
    td = pathlib.Path(td)
    argv = ["--code-root-a", str(ROOT), "--evidence-root", str(td / "ev"),
            "--lock", str(td / "measure.lock"), "--run-id", run_id,
            "--phases", "resident"]
    err = io.StringIO()
    with _patched(build_context=build_context):
        with contextlib.redirect_stdout(io.StringIO()), \
                contextlib.redirect_stderr(err):
            return fr.main(argv), err.getvalue()


def test_an_early_stop_leaves_no_run_directory_and_the_id_runs_again():
    counts = {"warm": 1, "cold": 1, "burst": 1, "first": 2, "gap": 2}
    with tmpdir() as td:
        code, err = _main_with(td, _stop_in_build_context, "stop-test")
        assert code == 2 and "STOP: no corpus" in err
        assert not (pathlib.Path(td) / "ev" / "stop-test").exists(), \
            "a stop before any phase leaves nothing behind"
        ctx = _shim_context(td, counts)
        _main_with(td, lambda *a: ctx, "stop-test")
        report = json.loads((ctx.run_dir / "report.json").read_text())
        assert report["rig"]["complete"] is True, "the same id ran through"
    print("ok  shim run: a stop before any phase removes the run directory,"
          " and the same run id then runs")


def test_an_existing_run_id_with_content_is_refused_and_kept():
    with tmpdir() as td:
        kept = pathlib.Path(td) / "ev" / "kept"
        kept.mkdir(parents=True)
        (kept / "report.json").write_text("{}")
        try:
            _main_with(td, _stop_in_build_context, "kept")
            raise AssertionError("an existing run directory was reused")
        except FileExistsError as e:
            assert "kept" in str(e)
        assert (kept / "report.json").read_text() == "{}"
    print("ok  shim run: a run id that already holds a report is refused and"
          " its directory is left alone")


def main():
    run([test_session_runs_both_requests_and_times_them,
         test_session_captures_the_six_memory_labels,
         test_session_stops_when_an_engine_fails_to_load,
         test_session_stops_on_a_worker_fault,
         test_back_to_back_sends_return_in_order,
         test_a_session_names_its_idle_unload_value_and_defaults_to_off,
         test_session_sees_the_unload_the_reload_and_the_hint,
         test_a_worker_that_never_unloads_is_reported_not_waited_for,
         test_the_real_context_makes_sessions_with_an_explicit_idle_value,
         test_the_idle_phase_is_accepted_by_phases_and_not_run_by_default,
         test_the_idle_phase_measures_a_dictation_after_an_unload,
         test_an_idle_output_mismatch_fails_identity_in_a_whole_run,
         test_a_degraded_cleanup_after_an_unload_stops_the_run,
         test_whole_run_against_the_shim_worker_writes_a_content_free_report,
         test_a_first_request_only_run_states_its_unit_in_the_method,
         test_a_first_request_only_run_states_an_identity_verdict,
         test_a_first_request_output_mismatch_fails_identity_in_a_whole_run,
         test_the_pinned_aa_is_checked_against_this_runs_bands_and_side_a_tree,
         test_asr_bands_interleave_an_unmeasured_cleanup_on_both_sides,
         test_a_worker_over_the_footprint_limit_aborts_the_run,
         test_swap_growth_aborts_the_run,
         test_a_trip_after_the_report_was_finished_leaves_one_aborted_state,
         test_an_early_stop_leaves_no_run_directory_and_the_id_runs_again,
         test_an_existing_run_id_with_content_is_refused_and_kept],
        "footprint rig session tests")


if __name__ == "__main__":
    main()
