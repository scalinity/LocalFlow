"""The footprint rig's own logic (scripts/v2/footprint_rig.py).

Pure helpers first: band assignment, the paired-difference statistics, the
Gate-table rules (Latency, Back-to-back gap), model identity, the frame
guard that stops a run, content-free request records and the parsers of the
two macOS tools. Expected values are worked by hand, never recomputed the
way the code computes them. The rig driving a real worker is covered by
test_footprint_rig_session.py; no model runs here.

Run: .venv/bin/python tests/v2/lifecycle/test_footprint_rig.py
"""

import hashlib
import json
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "v2"))

import footprint_rig as fr  # noqa: E402


def _stops(fn, *needles):
    try:
        fn()
    except fr.RigStop as e:
        for n in needles:
            assert n in str(e), (n, str(e))
        return str(e)
    raise AssertionError("expected RigStop")


# ---- bands -------------------------------------------------------------

def test_cleanup_bands_by_word_count():
    pick = lambda n: fr.assign_band(n, fr.CLEANUP_BANDS)  # noqa: E731
    assert [pick(n) for n in (1, 20, 21, 50, 51, 100, 101, 200)] == [
        "1-20", "1-20", "21-50", "21-50", "51-100", "51-100", "101-200",
        "101-200"]
    assert pick(0) is None and pick(201) is None
    print("ok  cleanup bands: 1-20, 21-50, 51-100, 101-200 words; outside is"
          " unbanded")


def test_asr_bands_by_duration():
    pick = lambda s: fr.assign_band(s, fr.ASR_BANDS)  # noqa: E731
    assert [pick(s) for s in (3.2, 9.99, 10.0, 29.99, 30.0, 89.9, 90.0,
                              118.0)] == [
        "under-10s", "under-10s", "10-30s", "10-30s", "30-90s", "30-90s",
        "over-90s", "over-90s"]
    print("ok  asr bands: under 10 s, 10-30 s, 30-90 s, over 90 s")


def test_freeze_bands_records_membership_and_unbanded():
    frozen = fr.freeze_bands([("b", 25), ("a", 5), ("d", 22), ("c", 300)],
                             fr.CLEANUP_BANDS)
    assert frozen["members"] == {"1-20": ["a"], "21-50": ["b", "d"],
                                 "51-100": [], "101-200": []}
    assert frozen["unbanded"] == ["c"]
    assert [e["band"] for e in frozen["edges"]] == [
        "1-20", "21-50", "51-100", "101-200"]
    assert fr.band_counts(frozen) == {"1-20": 1, "21-50": 2, "51-100": 0,
                                      "101-200": 0}
    assert fr.short_bands(frozen, 2) == ["1-20", "51-100", "101-200"]
    same = fr.freeze_bands([("c", 300), ("d", 22), ("a", 5), ("b", 25)],
                           fr.CLEANUP_BANDS)
    assert fr.digest_json(same) == fr.digest_json(frozen), \
        "membership must not depend on input order"
    print("ok  frozen bands: sorted membership, unbanded listed, short bands"
          " named, digest independent of input order")


# ---- paired statistics ---------------------------------------------------

def test_paired_difference_cancels_linear_drift():
    # The same true cost (100) with a drift of +1 ms per slot: A,B,B,A reads
    # 100,101,102,103. Mean B 101.5 - mean A 101.5 = 0.
    assert fr.paired_differences([(100, 101, 102, 103)]) == [0.0]
    # A real +10 ms candidate cost on top of no drift.
    assert fr.paired_differences([(100, 110, 114, 104)]) == [10.0]
    print("ok  ABBA block: linear drift cancels, a real +10 ms shows as +10")


def test_block_order_alternates_and_splits_by_side():
    assert [fr.block_order(i) for i in range(4)] == [
        "ABBA", "BAAB", "ABBA", "BAAB"]
    assert fr.by_side("ABBA", [1, 2, 3, 4]) == {"A": [1, 4], "B": [2, 3]}
    assert fr.by_side("BAAB", [1, 2, 3, 4]) == {"A": [2, 3], "B": [1, 4]}
    print("ok  blocks alternate A,B,B,A and B,A,A,B; times split by side")


def test_each_case_alternates_its_block_order():
    used = ["c0", "c1", "c2"]
    seq = used * 2 + ["c0", "c1"]
    # odd case count: the sequence alternates in time as well
    assert fr.block_orders(seq, used) == ["ABBA", "BAAB"] * 4
    # even case count: the order still alternates per case, so a bias that
    # depends on the case is cancelled by that case's own repeats
    two = ["c0", "c1"] * 3
    orders = fr.block_orders(two, ["c0", "c1"])
    for case in ("c0", "c1"):
        mine = [o for c, o in zip(two, orders) if c == case]
        assert mine == ["ABBA", "BAAB", "ABBA"] or \
            mine == ["BAAB", "ABBA", "BAAB"], (case, mine)
    assert fr.block_orders([], []) == []
    print("ok  block order: each case alternates between A,B,B,A and"
          " B,A,A,B across its occurrences")


def test_block_differences_do_not_depend_on_block_order():
    blocks = [{"order": "ABBA", "rtt_ms": [100, 110, 114, 104]},
              {"order": "BAAB", "rtt_ms": [110, 100, 104, 114]},
              {"order": "BAAB", "rtt_ms": [105, 101, 103, 105]}]
    assert fr.block_differences(blocks, "rtt_ms") == [10.0, 10.0, 3.0]
    assert fr.block_baseline(blocks, "rtt_ms") == [
        100, 104, 100, 104, 101, 103]
    print("ok  paired difference is mean B minus mean A whatever the order;"
          " the baseline times are the A times")


def test_median_and_nearest_rank_p95():
    assert fr.median([3, 1, 2]) == 2
    assert fr.median([4, 1, 3, 2]) == 2.5
    assert fr.p95([float(n) for n in range(1, 21)]) == 19.0  # ceil(.95*20)
    assert fr.p95([5.0, 1.0, 3.0]) == 5.0
    assert fr.p95([7.0]) == 7.0
    print("ok  median, nearest-rank p95")


# ---- the Gate-table rules ----------------------------------------------------

def test_latency_rule_on_median_and_p95():
    base = [100.0, 200.0, 300.0, 400.0, 500.0]  # median 300, p95 500
    # median limit max(50, 15) = 50; p95 limit 10% of 500 = 50.
    v = fr.latency_verdict([1, 2, 3, 4, 60], base)
    assert (v["baseline_median_ms"], v["baseline_p95_ms"]) == (300.0, 500.0)
    assert (v["median_limit_ms"], v["p95_limit_ms"]) == (50.0, 50.0)
    assert (v["paired_median_ms"], v["paired_p95_ms"]) == (3.0, 60.0)
    assert v["median_pass"] is True and v["p95_pass"] is False
    assert v["pass"] is False and v["pairs"] == 5
    assert fr.latency_verdict([1, 2, 3, 4, 49], base)["pass"] is True
    # A slow band: 5% of a 2000 ms median is 100 ms, above the 50 ms floor.
    slow = [2000.0] * 5
    assert fr.latency_verdict([80.0] * 5, slow)["median_limit_ms"] == 100.0
    assert fr.latency_verdict([80.0] * 5, slow)["median_pass"] is True
    assert fr.latency_verdict([120.0] * 5, slow)["median_pass"] is False
    # An improvement is never a failure.
    assert fr.latency_verdict([-30.0] * 5, base)["pass"] is True
    print("ok  latency rule: max(floor, 5%) on the paired median, 10% on the"
          " paired p95")


def _close(a, b):
    return abs(a - b) < 1e-6


def test_latency_limits_are_never_tighter_than_the_measured_noise():
    base = [1301.0] * 20            # spec p95 limit 130.1, median limit 65.05
    two_high = [1.0] * 18 + [200.0, 200.0]      # paired p95 200, median 1
    aa = {"paired_median_ms": 11.4, "paired_p95_ms": 236.5}
    spec = fr.latency_verdict(two_high, base)
    assert _close(spec["p95_limit_ms"], 130.1) and spec["p95_pass"] is False
    assert spec["aa_p95_ms"] is None and spec["aa_median_ms"] is None
    # asr:30-90s: spec 130.1, A/A 236.5 gives an effective 236.5
    pinned = fr.latency_verdict(two_high, base, aa)
    assert _close(pinned["spec_p95_limit_ms"], 130.1)
    assert _close(pinned["aa_p95_ms"], 236.5)
    assert _close(pinned["p95_limit_ms"], 236.5)
    assert pinned["p95_pass"] is True            # candidate p95 200 passes
    worse = fr.latency_verdict([1.0] * 18 + [260.0, 260.0], base, aa)
    assert worse["p95_pass"] is False            # candidate p95 260 fails
    # a band whose A/A value is below its limit stays at the spec limit
    quiet = fr.latency_verdict(two_high, base,
                               {"paired_median_ms": 11.4,
                                "paired_p95_ms": 20.0})
    assert _close(quiet["p95_limit_ms"], 130.1)
    assert _close(quiet["median_limit_ms"], 65.05)   # median unchanged
    assert _close(quiet["spec_median_limit_ms"], 65.05)
    # a noisy median raises the median limit the same way
    loud = {"paired_median_ms": 80.0, "paired_p95_ms": 20.0}
    seventy = [70.0] * 20
    assert fr.latency_verdict(seventy, base)["median_pass"] is False
    assert fr.latency_verdict(seventy, base, loud)["median_pass"] is True
    assert _close(fr.latency_verdict(seventy, base, loud)[
        "median_limit_ms"], 80.0)
    print("ok  latency limits: max(spec limit, the A/A value of the same"
          " statistic); spec limits stay where the A/A is quiet")


def test_back_to_back_gap_limit_is_never_tighter_than_the_measured_noise():
    a, b = [10.0, 10.0, 10.0], [70.0, 70.0, 70.0]        # paired median 60
    assert fr.gap_verdict(a, b)["pass"] is False
    v = fr.gap_verdict(a, b, aa_median_ms=80.0)
    assert v["pass"] is True and v["limit_ms"] == 80.0
    assert v["spec_limit_ms"] == 50.0 and v["aa_median_ms"] == 80.0
    assert fr.gap_verdict(a, b, aa_median_ms=3.0)["limit_ms"] == 50.0
    print("ok  gap limit: max(50 ms, the A/A gap), spec where the A/A is"
          " quiet")


def _aa_report(complete=True, run_id="aa-test"):
    band = {"paired_median_ms": 11.4, "paired_p95_ms": 236.5}
    stage = {"paired_median_ms": 11.0, "paired_p95_ms": 234.0}
    return {"rig": {"run_id": run_id, "complete": complete},
            "resident": {
                "latency": {"asr": {
                    "30-90s": {"verdict_rtt": band, "verdict_stage": stage},
                    "10-30s": {"verdict_rtt": None, "verdict_stage": None}}},
                "gap": {"verdict": {"paired_median_ms": 0.1}}},
            "first_request": {"verdicts": {"rtt_ms": {"asr": band},
                                           "stage_ms": {"asr": stage}}}}


def test_the_aa_report_is_pinned_by_digest_and_must_be_complete():
    with tempfile.TemporaryDirectory() as td:
        path = pathlib.Path(td) / "report.json"
        path.write_text(json.dumps(_aa_report()))
        got = fr.load_aa_report(path)
        assert got["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
        assert got["run_id"] == "aa-test"
        assert got["stats"]["rtt_ms"]["asr:30-90s"] == {
            "paired_median_ms": 11.4, "paired_p95_ms": 236.5}
        assert got["stats"]["stage_ms"]["asr:30-90s"]["paired_p95_ms"] == 234.0
        assert "asr:10-30s" not in got["stats"]["rtt_ms"]
        assert got["stats"]["rtt_ms"]["first-request:asr"][
            "paired_p95_ms"] == 236.5
        assert got["gap_median_ms"] == 0.1
        path.write_text(json.dumps(_aa_report(complete=False)))
        _stops(lambda: fr.load_aa_report(path), "complete")
        path.write_text("not json")
        _stops(lambda: fr.load_aa_report(path), "A/A report")
        _stops(lambda: fr.load_aa_report(pathlib.Path(td) / "missing.json"),
               "A/A report")
    args = fr.parse_args(["--code-root-a", ".", "--aa-report", "x.json"])
    assert args.aa_report == "x.json"
    assert fr.parse_args(["--code-root-a", "."]).aa_report is None
    print("ok  A/A report: pinned by SHA-256 and run id, refused unless"
          " rig.complete is true, --aa-report parsed")


def test_rig_validity_follows_the_median_of_every_band():
    ok = {"median_pass": True, "p95_pass": False}
    bad = {"median_pass": False, "p95_pass": True}
    assert fr.rig_validity({"a": ok, "b": ok})["pass"] is True
    v = fr.rig_validity({"a": ok, "b": bad})
    assert v["pass"] is False and v["failing_bands"] == ["b"]
    assert fr.rig_validity({"a": ok})["p95_failing_bands"] == ["a"]
    print("ok  rig validity: A/A paired median must pass in every band; p95"
          " failures are listed beside it")


def test_back_to_back_gap_is_first_to_second_result_minus_stage():
    assert round(fr.back_to_back_gap_ms(10.000, 10.350, 300.0), 3) == 50.0
    v = fr.gap_verdict([20.0, 22.0, 21.0], [25.0, 26.0, 24.0])
    assert v["paired_median_ms"] == 4.0 and v["pass"] is True
    assert v["limit_ms"] == 50.0
    v = fr.gap_verdict([20.0, 22.0, 21.0], [80.0, 90.0, 100.0])
    assert v["paired_median_ms"] == 68.0 and v["pass"] is False
    print("ok  back-to-back gap: first result to second result minus stage;"
          " grows by less than 50 ms")


# ---- planning ----------------------------------------------------------------

def test_evenly_spaced_is_deterministic():
    ids = [f"c{n:02d}" for n in range(10)]
    assert fr.evenly_spaced(ids, 4) == ["c00", "c02", "c05", "c07"]
    assert fr.evenly_spaced(ids[:3], 8) == ids[:3]
    print("ok  evenly spaced selection")


def test_middle_is_the_central_sorted_id():
    assert fr.middle(["c", "a", "b"]) == "b"
    assert fr.middle(["d", "a", "c", "b"]) == "c"
    print("ok  middle id of a sorted list")


def test_latency_plan_counts_and_shortfall():
    ids = [f"c{n:02d}" for n in range(40)]
    plan = fr.latency_plan(ids, "shipping")
    assert len(plan["blocks"]) == 150 and len(set(plan["blocks"])) == 30
    assert plan["blocks"][:30] == plan["cases_used"]  # a full pass first
    # every case gets one warmup block before any measured block
    assert plan["warmup"] == plan["cases_used"]
    assert all(plan["blocks"].count(c) == 5 for c in plan["cases_used"])
    assert plan["short_of_claim"] is False and plan["cases_available"] == 40
    short = fr.latency_plan(ids[:13], "shipping")
    assert len(short["blocks"]) == 65 and short["short_of_claim"] is True
    early = fr.latency_plan(ids[:3], "early")
    assert early["blocks"] == ["c00", "c01", "c02", "c00", "c01", "c02",
                               "c00", "c01"]
    assert early["warmup"] == ["c00", "c01", "c02"]
    print("ok  latency plan: 30 cases x 5 repeats after one warmup block per"
          " case, shortfall flagged, early stop is 8 blocks")


# ---- model identity -------------------------------------------------------------

def test_identity_keeps_only_the_two_identifiers():
    cfg = {"model": "org/asr", "cleanup_model": "org/clean",
           "input_device": "SECRET-DEVICE", "hotkey": "fn"}
    ident = fr.identity_from_config(cfg)
    assert ident == {"asr_model": "org/asr", "cleanup_model": "org/clean"}
    msg = _stops(lambda: fr.identity_from_config(
        {"model": 5, "cleanup_model": "x", "input_device": "SECRET-DEVICE"}),
        "model")
    assert "SECRET-DEVICE" not in msg
    _stops(lambda: fr.identity_from_config({"model": "a"}), "cleanup_model")
    print("ok  identity: two identifiers kept, bad or missing stops without"
          " echoing config values")


def _fake_root(td, body):
    root = pathlib.Path(td)
    (root / "localflow").mkdir()
    (root / "localflow" / "__init__.py").write_text("")
    (root / "localflow" / "config.py").write_text(body)
    return root


def test_resolution_uses_the_code_roots_own_config_load():
    with tempfile.TemporaryDirectory() as td:
        root = _fake_root(td, (
            "def load(path=None):\n"
            "    return {'model': 'fake/asr', 'cleanup_model': 'fake/clean',\n"
            "            'input_device': 'SECRET-DEVICE'}\n"))
        ident = fr.resolve_model_identity(root, sys.executable)
        assert ident == {"asr_model": "fake/asr",
                         "cleanup_model": "fake/clean"}
    with tempfile.TemporaryDirectory() as real, \
            tempfile.TemporaryDirectory() as linked:
        _fake_root(real, "def load(path=None):\n"
                         "    return {'model': 'a', 'cleanup_model': 'b'}\n")
        # A package that is really another tree would be measured instead.
        (pathlib.Path(linked) / "localflow").symlink_to(
            pathlib.Path(real) / "localflow")
        _stops(lambda: fr.resolve_model_identity(linked, sys.executable),
               "outside the code root")
    with tempfile.TemporaryDirectory() as empty:  # no localflow at all
        _stops(lambda: fr.resolve_model_identity(empty, sys.executable),
               "code root")
    print("ok  identity resolved by the code root's own config.load();"
          " a localflow outside the root stops the run")


# ---- the frame guard --------------------------------------------------------------

def _guard():
    return fr.FrameGuard("asr/id", "clean/id")


def _engine(engine, state, model_id=None):
    mid = {"asr": "asr/id", "cleanup": "clean/id"}[engine] \
        if model_id is None else model_id
    return {"v": 1, "op": "engine", "engine": engine, "state": state,
            "model_id": mid}


def test_guard_accepts_the_normal_lifecycle():
    g = _guard()
    for f in (_engine("asr", "loading"), _engine("asr", "warming"),
              _engine("asr", "ready"), _engine("cleanup", "loading"),
              _engine("cleanup", "ready"),
              {"v": 1, "op": "diag", "kind": "memory", "label": "x"},
              {"v": 1, "op": "result", "kind": "asr", "generation": 1}):
        g.check(f)
    assert g.both_ready()
    assert not _guard().both_ready()
    print("ok  guard: normal lifecycle accepted, both-ready tracked")


def test_guard_stops_on_each_forbidden_frame():
    g = _guard()
    g.check(_engine("asr", "loading"))
    _stops(lambda: g.check(_engine("asr", "loading")), "second loading")
    _stops(lambda: _guard().check(_engine("asr", "loading", "other/id")),
           "other/id", "asr/id")
    _stops(lambda: _guard().check({"v": 1, "op": "engine", "engine": "asr",
                                   "state": "ready"}), "model")
    _stops(lambda: _guard().check({"v": 1, "op": "fault", "stage": "clean",
                                   "reason_code": "stage_exception"}),
           "fault", "stage_exception")
    _stops(lambda: _guard().check(_engine("cleanup", "failed")), "failed")
    _stops(lambda: _guard().check({"v": 1, "op": "result", "kind": "clean",
                                   "generation": 2}), "generation")
    print("ok  guard: second loading, other model, missing model, fault,"
          " failed engine and wrong generation all stop the run")


# ---- content-free records -----------------------------------------------------------

SECRET = "SECRET-TEXT-4711"


def test_clean_record_holds_digests_and_counts_only():
    frame = {"v": 1, "op": "result", "kind": "clean", "generation": 1,
             "text": SECRET, "duration_ms": 12.5, "path": "llm",
             "fallback_reason": None,
             "observations": [
                 {"kind": "clean", "pass_id": "p1", "prompt": SECRET,
                  "input": SECRET, "output": SECRET, "output_tokens": 17},
                 {"kind": "window_decision", "applied": SECRET},
                 {"kind": "corrections", "pass_id": "p2", "prompt": SECRET,
                  "output": SECRET, "output_tokens": 4}]}
    rec = fr.clean_record(frame, 15.25)
    assert rec["stage_ms"] == 12.5 and rec["rtt_ms"] == 15.25
    assert rec["pass_output_tokens"] == [17, 4]
    assert rec["path"] == "llm"
    assert rec["text_sha256"] == hashlib.sha256(
        SECRET.encode("utf-8")).hexdigest()
    assert SECRET not in json.dumps(rec)
    print("ok  clean record: stage and round-trip time, digest, per-pass"
          " token counts; no content")


def test_asr_record_digests_text_and_decode_ranges():
    frame = {"v": 1, "op": "result", "kind": "asr", "generation": 1,
             "text": SECRET, "duration_ms": 80.0, "sample_count": 32000,
             "decode_ranges": [[0, 16000], [16000, 32000]]}
    rec = fr.asr_record(frame, 81.5)
    assert rec["decode_range_count"] == 2 and rec["sample_count"] == 32000
    assert rec["decode_ranges_sha256"] == hashlib.sha256(
        b"[[0,16000],[16000,32000]]").hexdigest()
    assert rec["text_sha256"] == hashlib.sha256(
        SECRET.encode("utf-8")).hexdigest()
    assert SECRET not in json.dumps(rec)
    print("ok  asr record: text digest and decode-range digest, no content")


def test_report_guard_rejects_any_seen_text():
    clean = {"cases": [{"text_sha256": "ab", "stage_ms": 1.0}]}
    fr.assert_content_free(clean, [SECRET, "another seen text"])
    # a short text is not checked: it could match a report token by chance
    fr.assert_content_free({"pass": True, "case": "true"}, ["true", "pass"])
    leaky = {"cases": [{"note": "see " + SECRET + " here"}]}
    msg = _stops(lambda: fr.assert_content_free(leaky, [SECRET]),
                 "content")
    assert SECRET not in msg
    print("ok  report guard: a seen text in the report stops the write,"
          " without echoing it")


# ---- the macOS tools -------------------------------------------------------------------

FOOTPRINT_JSON = json.dumps({"unit": "byte", "processes": [{
    "name": "Python", "pid": 30243, "footprint": 419873464, "categories": {
        "IOAccelerator (graphics)": {"dirty": 404619264, "swapped": 0,
                                     "clean": 0, "reclaimable": 1966080,
                                     "wired": 0, "regions": 92},
        "IOAccelerator": {"dirty": 65536, "swapped": 0, "clean": 0,
                          "reclaimable": 0, "wired": 65536, "regions": 2},
        "Malloc Small": {"dirty": 8896512, "swapped": 0, "clean": 0,
                         "reclaimable": 0, "wired": 0, "regions": 6}}}]})

VMMAP_HEAD = """\
Physical footprint:         400.5M
Physical footprint (peak):  458.4M
"""


def test_footprint_json_gives_total_and_gpu_line():
    got = fr.parse_footprint_json(FOOTPRINT_JSON, 30243)
    assert got["total_bytes"] == 419873464
    assert got["gpu_bytes"] == 404619264 and got["gpu_regions"] == 92
    assert got["categories"]["Malloc Small"] == 8896512
    _stops(lambda: fr.parse_footprint_json(FOOTPRINT_JSON, 1), "pid")
    _stops(lambda: fr.parse_footprint_json("{}", 30243), "footprint")
    print("ok  footprint json: total, GPU (graphics) line and regions, wrong"
          " pid refused")


def test_vmmap_summary_gives_lifetime_peak():
    got = fr.parse_vmmap_summary(VMMAP_HEAD)
    assert got["footprint_bytes"] == round(400.5 * 1024 * 1024)
    assert got["peak_bytes"] == round(458.4 * 1024 * 1024)
    assert fr.parse_vmmap_summary(
        "Physical footprint:  1.5G\nPhysical footprint (peak):  6.4G\n")[
        "peak_bytes"] == round(6.4 * 1024 ** 3)
    _stops(lambda: fr.parse_vmmap_summary("nothing here"), "peak")
    print("ok  vmmap summary: footprint and lifetime-peak lines in bytes")


# ---- the baseline's go / no-go ---------------------------------------------------------

MIB = 1024 * 1024


def _levers(**over):
    base = {"idle_cache_bytes": 30 * MIB, "asr_warmed_cached_bytes": 80 * MIB,
            "launch_peak_bytes": 2900 * MIB, "idle_bytes": 1000 * MIB,
            "burst_growth_bytes": 15 * MIB, "burst_cache_min_bytes": 173 * MIB,
            "burst_cache_max_bytes": 266 * MIB}
    base.update(over)
    return fr.judge_levers(base)


def test_ticket_02_is_judged_against_the_idle_and_peak_floor_names():
    # Idle cache clears the Idle floor.
    j = _levers(idle_cache_bytes=150 * MIB, asr_warmed_cached_bytes=10 * MIB,
                launch_peak_bytes=1000 * MIB, idle_bytes=900 * MIB)
    assert j["ticket_02"]["go"] is True and "Idle floor" in j["ticket_02"]["line"]
    assert "150 MiB and clears the Idle floor" in j["ticket_02"]["line"]
    assert "up to 10 MiB" in j["ticket_02"]["line"]
    assert "is under the Peak floor" in j["ticket_02"]["line"]
    # Peak above idle by more than the Peak floor AND cache to release.
    j = _levers(asr_warmed_cached_bytes=700 * MIB)
    assert j["ticket_02"]["go"] is True and "Peak floor" in j["ticket_02"]["line"]
    assert "is under the Idle floor" in j["ticket_02"]["line"]
    assert "up to 700 MiB" in j["ticket_02"]["line"]
    assert "clears the Peak floor" in j["ticket_02"]["line"]
    # A tall peak with nothing in the allocator cache to release is no-go.
    assert _levers()["ticket_02"]["go"] is False
    print("ok  ticket 02: Idle floor on cached idle memory, Peak floor on the"
          " releasable part of the launch peak")


def test_ticket_03_is_judged_on_idle_growth_after_a_burst():
    # The rule: idle 2 s after a job within the Idle floor of idle after
    # warmup closes the ticket with no code. Cache size is not the criterion.
    closed = _levers(burst_growth_bytes=15 * MIB)["ticket_03"]
    assert closed["go"] is False
    assert closed["line"].startswith("NO-GO ticket 03, close with a note")
    assert "15 MiB" in closed["line"] and "under the Idle floor" in closed["line"]
    assert "173" not in closed["line"] and "266" not in closed["line"]
    j = _levers(burst_growth_bytes=150 * MIB)
    assert j["ticket_03"]["go"] is True
    assert j["ticket_03"]["line"].startswith("GO ticket 03")
    assert "150 MiB" in j["ticket_03"]["line"] \
        and "clears the Idle floor" in j["ticket_03"]["line"]
    # at the floor counts as clearing it
    assert _levers(burst_growth_bytes=fr.IDLE_FLOOR_BYTES)["ticket_03"]["go"]
    assert not _levers(burst_growth_bytes=fr.IDLE_FLOOR_BYTES - 1)[
        "ticket_03"]["go"]
    # the residual cached block is a separate observation
    note = _levers()["ticket_03_observation"]
    assert "173 to 266 MiB" in note and "Observation" in note
    print("ok  ticket 03: GO only when idle growth after a burst reaches the"
          " Idle floor, otherwise NO-GO close with a note; the residual cache"
          " is an observation line")


# ---- environment, processes, corpus, lock --------------------------------------------------

def test_power_and_thermal_text():
    batt = ("Now drawing from 'AC Power'\n -InternalBattery-0 (id=22937699)"
            "\t80%; AC attached; not charging present: true\n")
    assert fr.parse_power(batt) == {"source": "AC Power",
                                    "charge_percent": 80}
    ok = ("Note: No thermal warning level has been recorded\n"
          "Note: No performance warning level has been recorded\n"
          "Note: No CPU power status has been recorded\n")
    assert fr.parse_thermal(ok) == {"ok": True, "warning": None}
    warn = "CPU_Scheduler_Limit \t= 80\nCPU_Speed_Limit \t= 80\n"
    got = fr.parse_thermal(warn)
    assert got["ok"] is False and "CPU_Speed_Limit" in got["warning"]
    print("ok  power source and thermal state read from pmset text")


PS_TEXT = """\
 75081     1 /Applications/LocalFlow.app/Contents/MacOS/LocalFlow
 75089 75081 /opt/py/Python.app/Contents/MacOS/Python -m localflow.v2.worker --audio-root /x
 20116     1 /usr/local/bin/node serve
"""


def test_report_times_are_labelled_us_eastern():
    assert fr.et_label("2026-10-26T21:25:48-04:00") == \
        "2026-10-26 9:25 PM EDT"
    assert fr.et_label("2026-12-01T09:00:00-05:00") == \
        "2026-12-01 9:00 AM EST"
    assert fr.et_label("2026-10-27T01:25:48+00:00") == \
        "2026-10-26 9:25 PM EDT", "a UTC stamp is converted, not echoed"
    assert fr.et_label(None) == "n/a"
    print("ok  report times: converted to US Eastern and labelled EDT/EST")


def test_process_table_separates_the_installed_worker_from_strays():
    installed, strays = fr.classify_workers(fr.parse_ps(PS_TEXT))
    assert installed == 75089 and strays == []
    extra = PS_TEXT + (
        " 4242     1 /usr/bin/python3 -m localflow.v2.worker --audio-root /t\n"
        " 5151     1 /v/python -m mlx_lm.generate --model m\n")
    installed, strays = fr.classify_workers(fr.parse_ps(extra))
    assert installed == 75089 and strays == [4242, 5151]
    assert fr.classify_workers(fr.parse_ps(" 20116 1 /bin/node\n")) == (
        None, [])
    # A process that only mentions the names (a shell running a grep, an
    # editor) is not a worker: the interpreter must be running the module.
    mention = PS_TEXT + (
        " 7001     1 /bin/zsh -c ps | grep -E \"localflow.v2.worker|mlx\"\n"
        " 7002     1 tail -f /logs/mlx_lm.log\n"
        " 7003     1 /usr/bin/vim localflow/v2/worker.py\n")
    assert fr.classify_workers(fr.parse_ps(mention)) == (75089, [])
    print("ok  process table: installed worker found by its app parent,"
          " any other worker or mlx process is a stray")


def test_cputime_text_in_seconds():
    assert fr.parse_cputime("0:04.46") == 4.46
    assert fr.parse_cputime("  1:02:03.50 ") == 3723.5
    print("ok  ps cputime text to seconds")


def test_revision_record_compares_manifest_and_snapshot():
    manifest = {"models": {
        "asr": {"revision": "abc", "configured_id": "org/asr"},
        "cleanup": {"revision": "def", "configured_id": "org/older"}}}
    rec = fr.revision_record(manifest, {"asr": "abc", "cleanup": "zzz"})
    assert rec["asr"] == {"manifest_model": "org/asr", "manifest": "abc",
                          "snapshot": "abc", "matches": True}
    assert rec["cleanup"] == {"manifest_model": "org/older",
                              "manifest": "def", "snapshot": "zzz",
                              "matches": False}
    assert fr.revision_record({}, {"asr": "abc", "cleanup": "zzz"})[
        "asr"]["manifest"] is None
    print("ok  revision record: manifest pin against the snapshot on disk,"
          " a mismatch is recorded not hidden")


def test_cleanup_cases_cover_every_committed_fixture():
    files = [ROOT / "tests/v2/fidelity/fixtures_fidelity.json",
             ROOT / "tests/v2/fidelity/fixtures_literal.json",
             ROOT / "tests/v2/structure/fixtures_structure.json"]
    expected = sum(len(json.loads(f.read_text())["cases"]) for f in files)
    cases = fr.load_cleanup_cases(ROOT)
    assert len(cases) == expected and expected > 0
    assert {c.split(":")[0] for c in cases} == {"fidelity", "literal",
                                                "structure"}
    for cid, c in cases.items():
        assert c["words"] == len(c["text"].split()) >= 1, cid
        assert all(0 <= a < b <= len(c["text"])
                   for a, b in c["protected_spans"]), cid
    assert any(c["protected_spans"] for c in cases.values()), \
        "literal fixtures carry protected spans"
    print("ok  cleanup cases: every committed fixture, ids prefixed by"
          " suite, protected spans inside the text")


def test_afconvert_wav_with_a_padding_chunk_is_decoded():
    import struct
    import numpy as np
    samples = np.array([0.0, 0.5, -0.25], dtype="<f4")
    fmt = struct.pack("<HHIIHH", 3, 1, 16000, 64000, 4, 32)
    raw = (b"RIFF" + struct.pack("<I", 0) + b"WAVE"
           + b"fmt " + struct.pack("<I", 16) + fmt
           + b"FLLR" + struct.pack("<I", 4) + b"\0" * 4
           + b"data" + struct.pack("<I", 12) + samples.tobytes())
    got, rate = fr.read_afconvert_wav(raw)
    assert rate == 16000 and [float(x) for x in got] == [0.0, 0.5, -0.25]
    pcm = struct.pack("<HHIIHH", 1, 1, 16000, 32000, 2, 16)
    bad = (b"RIFF" + struct.pack("<I", 0) + b"WAVE" + b"fmt "
           + struct.pack("<I", 16) + pcm + b"data" + struct.pack("<I", 2)
           + b"\0\0")
    _stops(lambda: fr.read_afconvert_wav(bad), "float32")
    print("ok  afconvert WAV: padding chunk skipped, non-float32 refused")


def test_synthesized_clip_passes_the_workers_strict_parser():
    from localflow.v2.store import parse_wav_f32
    with tempfile.TemporaryDirectory() as td:
        out = pathlib.Path(td) / "clip-test.wav"
        rec = fr.synthesize_clip("Please move the meeting to Thursday.",
                                 "Samantha", 175, out)
        samples, rate = parse_wav_f32(out.read_bytes())
        assert rate == 16000 and samples.size / rate > 0.5
        assert rec["duration_s"] == round(samples.size / rate, 3)
        assert rec["sha256"] == hashlib.sha256(out.read_bytes()).hexdigest()
    print("ok  say + afconvert clip rewritten as a canonical float32 WAV the"
          " worker accepts")


def test_corpus_manifest_is_verified_against_the_files():
    with tempfile.TemporaryDirectory() as td:
        d = pathlib.Path(td)
        (d / "clip-a.wav").write_bytes(b"abc")
        manifest = {"clips": [{"name": "clip-a.wav",
                               "sha256": hashlib.sha256(b"abc").hexdigest()}]}
        fr.verify_corpus(manifest, d)
        (d / "clip-a.wav").write_bytes(b"abd")
        _stops(lambda: fr.verify_corpus(manifest, d), "clip-a.wav")
        (d / "clip-a.wav").unlink()
        _stops(lambda: fr.verify_corpus(manifest, d), "clip-a.wav")
    print("ok  corpus: a changed or missing clip stops the run")


def test_clip_plan_names_are_safe_and_targets_sit_inside_their_band():
    plan = fr.clip_plan(30)
    names = [c["name"] for c in plan]
    assert len(names) == len(set(names)) == 4 * 30 + 2
    safe = __import__("re").compile(r"^[A-Za-z0-9._-]+\Z")
    assert all(safe.match(n) for n in names)
    assert {"identity-under90.wav", "identity-over95.wav"} <= set(names)
    by_band = {}
    for c in plan:
        if c["band"]:
            by_band.setdefault(c["band"], []).append(c["target_s"])
    for name, lo, hi in fr.ASR_BANDS:
        assert len(by_band[name]) == 30
        assert all(lo <= t < (hi if hi else 1e9) for t in by_band[name]), name
    print("ok  clip plan: 30 clips per band plus the two identity clips,"
          " safe names, targets inside their band")


def test_corpus_builder_retries_each_clip_into_its_band_window():
    # A synthesizer that speaks at 3.0 words/s, slower than the planner's
    # assumption: the first attempts land in the wrong band and are redone.
    def stub(text, voice, rate, out_path):
        words = len(text.split())
        return {"sha256": "0" * 64, "duration_s": round(words / 3.0, 3),
                "voice": voice, "rate": rate, "words": words}
    real = fr.synthesize_clip
    fr.synthesize_clip = stub
    try:
        with tempfile.TemporaryDirectory() as td:
            manifest = fr.build_corpus(pathlib.Path(td), 6)
    finally:
        fr.synthesize_clip = real
    by_band = {}
    for clip in manifest["clips"]:
        if clip["band"]:
            by_band.setdefault(clip["band"], []).append(clip)
            lo, hi = fr.CLIP_WINDOWS[clip["band"]]
        else:
            lo, hi = fr.CLIP_WINDOWS[clip["name"]]
        assert lo <= clip["duration_s"] and (hi is None
                                             or clip["duration_s"] <= hi), clip
    assert {b: len(c) for b, c in by_band.items()} == {
        "under-10s": 6, "10-30s": 6, "30-90s": 6, "over-90s": 6}
    ident = {c["name"]: c["duration_s"] for c in manifest["clips"]
             if not c["band"]}
    assert ident["identity-under90.wav"] < 90 < 95 < \
        ident["identity-over95.wav"]
    # each band's clips are assigned to the band they were aimed at
    assert all(fr.assign_band(c["duration_s"], fr.ASR_BANDS) == c["band"]
               for cs in by_band.values() for c in cs)
    print("ok  corpus builder: every clip lands inside its band window,"
          " identity clips on both sides of the chunker threshold")


def test_the_lock_lives_in_the_evidence_root_and_names_no_user():
    import os
    assert fr.DEFAULT_LOCK == fr.DEFAULT_EVIDENCE_ROOT / "measure.lock"
    source = (ROOT / "scripts" / "v2" / "footprint_rig.py").read_text()
    assert "/Users/" not in source, "no personal absolute path in the rig"
    with tempfile.TemporaryDirectory() as td:
        path = pathlib.Path(td) / "not-yet" / "deeper" / "measure.lock"
        os.close(fr.acquire_lock(path))  # creates the missing directories
        assert path.exists()
    print("ok  lock default is derived from the evidence root; its folder is"
          " created when missing")


def test_the_measurement_lock_is_exclusive():
    import os
    with tempfile.TemporaryDirectory() as td:
        path = pathlib.Path(td) / "measure.lock"
        fd = fr.acquire_lock(path)
        try:
            _stops(lambda: fr.acquire_lock(path), "one measurement")
        finally:
            os.close(fd)
        os.close(fr.acquire_lock(path))  # free again after release
    print("ok  measurement lock: a second holder fails fast")


def test_warm_preparation_leaves_the_files_resident_and_says_so():
    import os
    import types
    with tempfile.TemporaryDirectory() as td:
        path = pathlib.Path(td) / "weights.safetensors"
        path.write_bytes(os.urandom(48 * 1024 * 1024))
        ctx = types.SimpleNamespace(weights=[path])
        got = fr.prepare_cache(ctx, "warm")
        assert got["intent"] == "warm" and got["method"] == "read-through"
        assert got["resident_fraction"] > 0.9, got
        assert fr.resident_fraction([path]) > 0.9
        assert fr.resident_fraction([]) == 0.0
    print("ok  page cache: a read-through file reads back as resident"
          " (mincore), no files reads as 0")


# ---- the ASR bands' unmeasured cleanup ----------------------------------------------------------

class _FakeSession:
    """Answers like the worker's result frames and keeps what it was sent."""

    def __init__(self, clean_path="llm"):
        self.sent = []
        self._clean_path = clean_path

    def request(self, op, fields=None, timeout=300.0):
        self.sent.append((op, dict(fields or {})))
        if op == "transcribe":
            frame = {"text": "heard it", "duration_ms": 10.0,
                     "decode_ranges": [[0, 160]], "sample_count": 160}
        else:
            frame = {"text": "cleaned it", "duration_ms": 5.0,
                     "path": self._clean_path, "observations": [],
                     "fallback_reason": None if self._clean_path == "llm"
                     else "cleanup_engine_failed"}
        return {"frame": frame, "received_at": 0.0, "sent_at": 0.0,
                "rtt_ms": 12.0}


def _block_ctx():
    import types
    cases = fr.load_cleanup_cases(ROOT)
    bands = {"cleanup": fr.freeze_bands(
        [(cid, c["words"]) for cid, c in cases.items()], fr.CLEANUP_BANDS)}
    return types.SimpleNamespace(cases=cases, bands=bands, seen=set(),
                                 thermal_events=[])


def test_asr_blocks_follow_every_request_with_an_unmeasured_cleanup():
    ctx = _block_ctx()
    sessions = {"A": _FakeSession(), "B": _FakeSession()}
    ids = ["clip-1.wav", "clip-2.wav"]
    blocks = fr.run_blocks(ctx, sessions, ids, ids, fr.asr_request, "asr")
    # Each block is A,B,B,A or B,A,A,B: two ASR requests per side, so two
    # blocks give each side four, each followed by one cleanup.
    for side, s in sessions.items():
        assert [op for op, _ in s.sent] == ["transcribe", "clean"] * 4, side
    assert sessions["A"].sent[1::2] == sessions["B"].sent[1::2], \
        "both sides get the identical cleanup request"
    op, fields = sessions["A"].sent[1]
    case = next(c for c in ctx.cases.values()
                if c["text"] == fields["raw_text"])
    assert case["words"] <= 20 and (op, fields) == fr.clean_request(case), \
        "a short fixture from the 1 to 20 word band"
    # The extra request is no part of a block's record: four measured ASR
    # requests per block, and only the transcript digests.
    heard = hashlib.sha256(b"heard it").hexdigest()
    for b in blocks:
        assert len(b["rtt_ms"]) == len(b["stage_ms"]) == 4
        assert b["text_sha256"] == [heard] * 4
    assert "cleaned it" in ctx.seen, "the report guard still sees its output"
    print("ok  ASR blocks: one unmeasured cleanup after each ASR request,"
          " the same fixture on both sides, absent from the block records")


def test_cleanup_blocks_send_no_extra_request():
    ctx = _block_ctx()
    sessions = {"A": _FakeSession(), "B": _FakeSession()}
    ids = sorted(ctx.bands["cleanup"]["members"]["21-50"])[:2]
    fr.run_blocks(ctx, sessions, ids, ids,
                  lambda cid: fr.clean_request(ctx.cases[cid]), "clean")
    for side, s in sessions.items():
        assert [op for op, _ in s.sent] == ["clean"] * 4, side
    print("ok  cleanup blocks: no extra request, only the measured ones")


def test_a_degraded_unmeasured_cleanup_stops_the_run():
    ctx = _block_ctx()
    sessions = {"A": _FakeSession("llm_fallback_normalized"),
                "B": _FakeSession()}
    msg = _stops(lambda: fr.run_blocks(
        ctx, sessions, ["clip-1.wav"], ["clip-1.wav"], fr.asr_request, "asr"),
        "degraded", "llm_fallback_normalized", "cleanup_engine_failed")
    assert "cleaned it" not in msg
    print("ok  a degraded cache-reset cleanup stops the run, reason codes only")


def test_the_cache_reset_fixture_is_the_shortest_of_the_short_band():
    import types
    cases = {"s:long": {"words": 7}, "s:b": {"words": 3},
             "s:a": {"words": 3}}
    ctx = types.SimpleNamespace(
        cases=cases, bands={"cleanup": {"members": {
            "1-20": ["s:long", "s:b", "s:a"], "21-50": []}}})
    assert fr.cache_reset_case(ctx) == "s:a", "fewest words, then the lower id"
    ctx.bands["cleanup"]["members"]["1-20"] = []
    _stops(lambda: fr.cache_reset_case(ctx), "1-20")
    print("ok  cache-reset fixture: fewest words in the 1-20 band, ties by"
          " id, a stop when the band is empty")


# ---- the watchdog ----------------------------------------------------------------------------------

GIB = 1024 ** 3


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


def test_the_watchdog_limits_are_the_agreed_ones():
    assert fr.WATCHDOG_FOOTPRINT_LIMIT_BYTES == 16 * GIB
    assert fr.WATCHDOG_SWAP_GROWTH_LIMIT_BYTES == 2 * GIB
    assert fr.WATCHDOG_INTERVAL_S == 2.0
    print("ok  watchdog: 16 GiB per worker, 2 GiB of swap growth, every"
          " 2 seconds")


def test_a_worker_footprint_trips_the_watchdog_just_past_its_limit():
    limit = 16 * GIB
    assert fr.watchdog_reason({}, 0, 0) is None
    assert fr.watchdog_reason({101: 8 * GIB}, 0, 0) is None
    assert fr.watchdog_reason({101: limit}, 0, 0) is None, "at the limit"
    why = fr.watchdog_reason({101: limit + 1}, 0, 0)
    assert why and "101" in why and "footprint" in why, why
    # one of several workers is enough, and its pid is the one named
    why = fr.watchdog_reason({101: 7 * GIB, 202: limit + 1}, 0, 0)
    assert why and "202" in why and "101" not in why, why
    print("ok  watchdog: a worker footprint of exactly 16 GiB passes, one"
          " byte more trips and names the pid")


def test_swap_growth_trips_the_watchdog_just_past_its_limit():
    start = 5 * GIB
    assert fr.watchdog_reason({}, start, start) is None
    assert fr.watchdog_reason({}, start + 2 * GIB, start) is None, \
        "growth at the limit"
    why = fr.watchdog_reason({}, start + 2 * GIB + 1, start)
    assert why and "swap" in why, why
    assert fr.watchdog_reason({}, start - GIB, start) is None, \
        "swap that shrinks is never a trip"
    # swap that was already large when the run started is no trip by itself
    assert fr.watchdog_reason({}, 40 * GIB, 40 * GIB) is None
    print("ok  watchdog: swap growth is measured from the run's start; 2 GiB"
          " passes, one byte more trips")


def test_swap_usage_text_gives_the_used_bytes():
    got = fr.parse_swap_used(
        "total = 6144.00M  used = 1024.00M  free = 5120.00M  (encrypted)")
    assert got == 1024 * 1024 * 1024, got
    assert fr.parse_swap_used("total = 8.00G  used = 2.50G  free = 5.50G"
                              "  (encrypted)") == 2684354560
    assert fr.parse_swap_used("total = 0.00M  used = 0.00M  free = 0.00M"
                              "  (encrypted)") == 0
    _stops(lambda: fr.parse_swap_used("vm.swapusage: unknown oid"), "swap")
    print("ok  swap usage text: M and G units, zero, an unreadable line"
          " stops the run")


class _Worker:
    """A session as the watchdog sees it."""

    def __init__(self, pid, alive=True):
        self.pid, self.alive, self.kills = pid, alive, 0

    def live_pid(self):
        return self.pid if self.alive else None

    def kill(self):
        self.kills += 1
        self.alive = False


def _watched(td, sizes, workers):
    """A watchdog over fake workers, never polled by its own thread (the
    tests set the interval to an hour); a test calls ``poll`` itself.
    Returns the watchdog, the pids its footprint reader was asked for and
    that reader."""
    reads = []

    def footprint(pid, scratch):
        reads.append(pid)
        return {"total_bytes": sizes[pid]}

    dog = fr.Watchdog(pathlib.Path(td) / "wd")
    wrapped = dog.wrap(lambda side, diag: workers[side])
    for side in workers:
        wrapped(side, False)
    return dog, reads, footprint


def test_the_watchdog_kills_only_the_workers_the_rig_spawned():
    sizes = {111: 8 * GIB, 222: 16 * GIB + 1}
    workers = {"A": _Worker(111), "B": _Worker(222),
               "C": _Worker(333, alive=False)}
    with tempfile.TemporaryDirectory() as td:
        dog, reads, footprint = _watched(td, sizes, workers)
        with _patched(WATCHDOG_INTERVAL_S=3600.0, read_footprint=footprint,
                      read_swap_used=lambda: 0):
            with dog:
                assert dog.poll() is True
        assert dog.reason and "222" in dog.reason
        assert sorted(set(reads)) == [111, 222], \
            "a closed worker and any other process are never read"
        assert (workers["A"].kills, workers["B"].kills,
                workers["C"].kills) == (1, 1, 0), \
            "every live rig worker is killed, a closed one is left alone"
        _stops(dog.raise_if_tripped, "222")
        _stops(lambda: dog.wrap(lambda s, d: workers["A"])("A", False),
               "222")
    print("ok  watchdog: kills each live rig worker once on a trip, reads"
          " and touches no other process, refuses new workers afterwards")


def test_the_watchdog_trips_on_swap_growth_from_its_starting_value():
    swap = [7 * GIB]
    workers = {"A": _Worker(111)}
    with tempfile.TemporaryDirectory() as td:
        dog, reads, footprint = _watched(td, {111: GIB}, workers)
        with _patched(WATCHDOG_INTERVAL_S=3600.0, read_footprint=footprint,
                      read_swap_used=lambda: swap[0]):
            with dog:  # the starting value is read here
                swap[0] = 9 * GIB
                assert dog.poll() is False, "growth at the limit"
                assert workers["A"].kills == 0
                swap[0] = 9 * GIB + 1
                assert dog.poll() is True
        assert "swap" in dog.reason and workers["A"].kills == 1
    print("ok  watchdog: swap growth over the starting value trips and"
          " kills the worker")


def test_a_failed_reading_is_skipped_never_a_trip():
    with tempfile.TemporaryDirectory() as td:
        workers = {"A": _Worker(111), "B": _Worker(222)}
        dog, reads, _ = _watched(td, {}, workers)
        sizes = {111: "unreadable", 222: 16 * GIB + 1}

        def footprint(pid, scratch):
            if sizes[pid] == "unreadable":
                raise fr.RigStop("footprint output has no GPU line yet")
            return {"total_bytes": sizes[pid]}

        swap = [3 * GIB]

        def read_swap():
            if swap[0] is None:
                raise fr.RigStop("the swap usage could not be read")
            return swap[0]

        with _patched(WATCHDOG_INTERVAL_S=3600.0, read_footprint=footprint,
                      read_swap_used=read_swap):
            with dog:
                sizes[222] = 8 * GIB
                swap[0] = None
                assert dog.poll() is False, "unreadable footprint and swap"
                assert dog.reason is None
                assert (workers["A"].kills, workers["B"].kills) == (0, 0)
                sizes[222] = 16 * GIB + 1
                assert dog.poll() is True, \
                    "the other worker is still read and judged"
        assert "222" in dog.reason and "111" not in dog.reason
    print("ok  watchdog: a footprint or swap reading that fails is skipped"
          " for that tick, the other readings still decide")


# ---- summaries -----------------------------------------------------------------------------------

def _spawn(side, label, total, gpu, peak, load_ms, resident):
    return {"side": side, "label": label, "idle_total_bytes": total,
            "idle_gpu_bytes": gpu, "launch_peak_bytes": peak,
            "load_ms": load_ms,
            "cache": {"resident_fraction": resident}}


def test_spawns_are_summarized_per_side_and_label():
    spawns = [_spawn("A", "warm", 100, 80, 300, 10.0, 1.0),
              _spawn("A", "warm", 120, 90, 340, 14.0, 0.9),
              _spawn("A", "warm", 110, 85, 320, 12.0, 1.0),
              _spawn("A", "cold-ish", 105, 82, 310, 40.0, 0.0),
              _spawn("B", "warm", 130, 95, 360, 11.0, 1.0)]
    got = fr.summarize_spawns(spawns)
    assert sorted(got) == ["A/cold-ish", "A/warm", "B/warm"]
    a = got["A/warm"]
    assert a["spawns"] == 3
    assert a["idle_total_bytes"] == {"median": 110.0, "min": 100,
                                     "max": 120}
    assert a["launch_peak_bytes"]["median"] == 320.0
    assert a["load_ms"]["max"] == 14.0
    assert a["resident_fraction_median"] == 1.0
    assert got["A/cold-ish"]["resident_fraction_median"] == 0.0
    print("ok  spawn summary: median, min and max per side and cache label")


def test_lever_inputs_come_from_side_a_counters_and_footprints():
    spawns = [_spawn("A", "warm", 1000, 900, 3000, 1.0, 1.0),
              _spawn("A", "cold-ish", 1200, 900, 3400, 1.0, 0.0),
              _spawn("B", "warm", 9999, 900, 9999, 1.0, 1.0)]

    def burst(side, idle, after, diag=None):
        b = {"side": side, "memory_diag": diag is not None, "memory": None,
             "idle": {"total_bytes": idle},
             "after_burst": {"total_bytes": after}}
        if diag:
            cleanup_warmed, asr_warmed, series = diag
            b["memory"] = {"first": {
                "cleanup_warmed": {"cached": cleanup_warmed},
                "asr_warmed": {"cached": asr_warmed}},
                "cleanup_result_cached": series}
        return b
    bursts = [burst("A", 1000, 1013, (10, 50, [7, 9, 8])),
              burst("A", 1000, 1017, (30, 70, [6, 12])),
              burst("A", 2000, 2015),
              burst("B", 5, 19, (999, 999, [1, 99999]))]
    got = fr.lever_inputs(spawns, bursts)
    assert got == {"idle_bytes": 1100.0, "launch_peak_bytes": 3200.0,
                   "idle_cache_bytes": 20.0, "asr_warmed_cached_bytes": 60.0,
                   "burst_growth_bytes": 15.0, "burst_cache_min_bytes": 6,
                   "burst_cache_max_bytes": 12}
    assert fr.lever_inputs(spawns, []) is None
    print("ok  lever inputs: side A medians of footprint, counters and idle"
          " growth after a burst")


def test_ticket_03_growth_is_judged_on_side_a_bursts_only():
    # An A/B run: the baseline side grows 14 MiB after a burst; the candidate
    # reads 186 MiB because its idle at ready was already lowered. The line
    # judges the baseline side and says so.
    spawns = [_spawn("A", "warm", 1000, 900, 3000, 1.0, 1.0),
              _spawn("B", "warm", 820, 900, 2400, 1.0, 1.0)]

    def burst(side, idle, after):
        return {"side": side, "memory_diag": side == "A", "memory": {
            "first": {"cleanup_warmed": {"cached": 10},
                      "asr_warmed": {"cached": 50}},
            "cleanup_result_cached": [8]} if side == "A" else None,
            "idle": {"total_bytes": idle * MIB},
            "after_burst": {"total_bytes": after * MIB}}
    bursts = [burst("A", 4000, 4014), burst("B", 3900, 4086),
              burst("A", 4000, 4014), burst("B", 3900, 4086)]
    got = fr.lever_inputs(spawns, bursts)
    assert got["burst_growth_bytes"] == 14 * MIB, got["burst_growth_bytes"]
    line = fr.judge_levers(got)["ticket_03"]["line"]
    assert "14 MiB" in line and "186" not in line and "101" not in line, line
    assert "side A" in line and "baseline" in line, line
    print("ok  ticket 03: idle growth is taken from side A bursts only, and"
          " the line names side A")


# ---- code-root provenance ---------------------------------------------------------------------

def _git(cwd, *args):
    import subprocess
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t.invalid", *args],
        cwd=cwd, capture_output=True, text=True, check=True).stdout.strip()


def _checkout(parent):
    root = pathlib.Path(parent) / "checkout"
    (root / "localflow").mkdir(parents=True)
    (root / "localflow" / "a.py").write_text("x")
    _git(root, "init", "-q")
    _git(root, "add", "localflow/a.py")
    _git(root, "commit", "-q", "-m", "one")
    return root


def test_code_root_info_has_head_and_dirty_for_a_checkout_root():
    with tempfile.TemporaryDirectory() as td:
        root = _checkout(td)
        info = fr.code_root_info(root)
        assert info["head"] == _git(root, "rev-parse", "HEAD"), info
        assert info["dirty"] is False and info["export"] is False, info
        (root / "localflow" / "a.py").write_text("changed")
        assert fr.code_root_info(root)["dirty"] is True
    print("ok  code root: a checkout root reports its head and dirty state")


def test_code_root_info_does_not_borrow_a_parent_checkouts_head():
    with tempfile.TemporaryDirectory() as td:
        parent = _checkout(td)
        export = parent / ".scratch" / "export"
        (export / "localflow").mkdir(parents=True)
        (export / "localflow" / "a.py").write_text("x")
        info = fr.code_root_info(export)
        assert info["head"] is None and info["dirty"] is None, info
        assert info["export"] is True, info
    with tempfile.TemporaryDirectory() as td:
        (pathlib.Path(td) / "localflow").mkdir()
        info = fr.code_root_info(td)
        assert info["head"] is None and info["export"] is True, info
    print("ok  code root: a directory inside another checkout, or in none,"
          " is an export with no head")


def _tree(parent, files):
    root = pathlib.Path(parent)
    for rel, data in files.items():
        path = root / "localflow" / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return root


def test_tree_digest_covers_sorted_paths_and_file_digests():
    # Worked with shasum: the SHA-256 of the lines "<path> <file sha256>\n"
    # in path order, paths relative to localflow/.
    with tempfile.TemporaryDirectory() as td:
        root = _tree(td, {"sub/b.py": b"yy", "a.py": b"x"})
        assert fr.tree_digest(root) == \
            "bec586189675c8a3156d4c30c82d6de7fbda6713841b93f219a237b23b25cc8e"
        (root / "localflow" / "a.py").write_bytes(b"x2")
        assert fr.tree_digest(root) == \
            "c43d8517184048a0827523f5f497a8ae5edb78f70c6620eb814b6e646269d083"
    print("ok  tree digest: sorted paths and per-file digests, matches shasum")


def test_tree_digest_ignores_bytecode_but_not_other_files():
    with tempfile.TemporaryDirectory() as td:
        root = _tree(td, {"a.py": b"x", "sub/b.py": b"yy"})
        clean = fr.tree_digest(root)
        _tree(td, {"__pycache__/a.cpython-314.pyc": b"\0",
                   "sub/__pycache__/b.cpython-314.pyc": b"\1"})
        assert fr.tree_digest(root) == clean
        _tree(td, {"extra.py": b""})
        assert fr.tree_digest(root) != clean
    print("ok  tree digest: bytecode caches are ignored, any other file counts")


def test_code_root_line_prints_head_and_tree_digest():
    sha = "ab" * 32
    checkout = fr.code_root_line(
        "B", {"head": "1234567890abcdef", "dirty": False, "export": False,
              "tree_sha256": sha})
    assert checkout == ("- side B: head 1234567890abcdef (dirty: False),"
                        f" localflow tree SHA-256 `{sha}`"), checkout
    export = fr.code_root_line(
        "A", {"head": None, "dirty": None, "export": True,
              "tree_sha256": sha})
    assert export == ("- side A: export, not a checkout root (no head),"
                      f" localflow tree SHA-256 `{sha}`"), export
    print("ok  summary line: head and dirty for a checkout, export wording"
          " otherwise, tree digest on both")


def main():
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
    print(f"all footprint rig tests passed ({len(tests)})")


if __name__ == "__main__":
    main()
