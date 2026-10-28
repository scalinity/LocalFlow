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


def _session(td, plan, memory_diag=False):
    td = pathlib.Path(td)
    wav(td / "audio", "clip.wav")
    plan_path = td / "plan.json"
    plan_path.write_text(json.dumps(plan))
    return fr.WorkerSession(
        ROOT, td / "audio", IDENTITY, memory_diag=memory_diag,
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


def _shim_context(td, counts, record=False):
    """A run context over the shimmed production worker and a tiny
    synthetic corpus: one clip pair per ASR band, the real fixtures. With
    ``record`` each side's worker logs the requests its shims were given to
    ``ctx.records[side]`` (JSON lines)."""
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
                                    if record else {})}))
    ctx = types.SimpleNamespace(
        run_id="shim-test", mode="early", counts=counts, aa=None,
        roots={"A": ROOT, "B": ROOT}, identity=IDENTITY, revisions={},
        cases=cases, bands=bands, run_dir=td / "run",
        scratch=td / "run" / "scratch", seen=set(), thermal_events=[],
        fixture_texts={c["text"] for c in cases.values()}, weights=[],
        evict_pool=str(td), protect_tokens=[], purge_allowed=False,
        installed_pid=None, installed_pid_now=lambda: None,
        manifest=manifest, records=records)
    ctx.run_dir.mkdir()
    ctx.scratch.mkdir()
    ctx.make_session = lambda side, diag: fr.WorkerSession(
        ROOT, corpus, IDENTITY, memory_diag=diag,
        cmd=[sys.executable, str(PROD), "--audio-root", str(corpus)],
        env={"LOCALFLOW_PROD_WORKER_PLAN": str(plans[side]),
             "LOCALFLOW_CODE_ROOT": str(ROOT)})
    return ctx


def test_whole_run_against_the_shim_worker_writes_a_content_free_report():
    counts = {"warm": 1, "cold": 1, "burst": 1, "first": 2, "gap": 2}
    with tmpdir() as td:
        ctx = _shim_context(td, counts)
        fr.measure(ctx, list(fr.PHASES), "2026-10-26T00:00:00-04:00")
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
        digest = hashlib.sha256(aa_path.read_bytes()).hexdigest()
        ctx2 = _shim_context(pathlib.Path(td) / "second", counts)
        ctx2.aa = fr.load_aa_report(aa_path)
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


def main():
    run([test_session_runs_both_requests_and_times_them,
         test_session_captures_the_six_memory_labels,
         test_session_stops_when_an_engine_fails_to_load,
         test_session_stops_on_a_worker_fault,
         test_back_to_back_sends_return_in_order,
         test_whole_run_against_the_shim_worker_writes_a_content_free_report,
         test_a_first_request_only_run_states_its_unit_in_the_method,
         test_asr_bands_interleave_an_unmeasured_cleanup_on_both_sides,
         test_a_worker_over_the_footprint_limit_aborts_the_run,
         test_swap_growth_aborts_the_run],
        "footprint rig session tests")


if __name__ == "__main__":
    main()
