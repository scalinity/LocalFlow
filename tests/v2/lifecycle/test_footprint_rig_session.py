"""The footprint rig's worker session against the PRODUCTION worker.

``WorkerSession`` plays the supervisor over the real protocol. These tests
run it against ``prod_worker_harness.py`` (the real ``Worker.serve`` with
only the two model loaders shimmed), so they prove the rig's framing, its
guard, its timing fields and its memory-sample capture. No model runs and
no figure here is a footprint or a latency of any model.

Run: .venv/bin/python tests/v2/lifecycle/test_footprint_rig_session.py
"""

import hashlib
import json
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


def _shim_context(td, counts):
    """A run context over the shimmed production worker and a tiny
    synthetic corpus: one clip pair per ASR band, the real fixtures."""
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
    plan = td / "plan.json"
    plan.write_text(json.dumps({"hold_gpu_mib": 64}))
    ctx = types.SimpleNamespace(
        run_id="shim-test", mode="early", counts=counts,
        roots={"A": ROOT, "B": ROOT}, identity=IDENTITY, revisions={},
        cases=cases, bands=bands, run_dir=td / "run",
        scratch=td / "run" / "scratch", seen=set(), thermal_events=[],
        fixture_texts={c["text"] for c in cases.values()}, weights=[],
        evict_pool=str(td), protect_tokens=[], purge_allowed=False,
        installed_pid=None, installed_pid_now=lambda: None,
        manifest=manifest)
    ctx.run_dir.mkdir()
    ctx.scratch.mkdir()
    ctx.make_session = lambda side, diag: fr.WorkerSession(
        ROOT, corpus, IDENTITY, memory_diag=diag,
        cmd=[sys.executable, str(PROD), "--audio-root", str(corpus)],
        env={"LOCALFLOW_PROD_WORKER_PLAN": str(plan),
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
        assert len(report["first_request"]["pairs"]) == counts["first"]
        res = report["resident"]
        assert not res["identity"]["mismatches"]
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
    print("ok  whole run against the shim worker: four phases, frozen bands"
          " on disk, verdicts, judgement, summary, no fixture text in the"
          " report")


def main():
    run([test_session_runs_both_requests_and_times_them,
         test_session_captures_the_six_memory_labels,
         test_session_stops_when_an_engine_fails_to_load,
         test_session_stops_on_a_worker_fault,
         test_back_to_back_sends_return_in_order,
         test_whole_run_against_the_shim_worker_writes_a_content_free_report],
        "footprint rig session tests")


if __name__ == "__main__":
    main()
