"""Worker footprint rig: the supervisor's seat at the real worker protocol.

Spawns ``python -m localflow.v2.worker --audio-root <dir>`` from a code
root, sends the load request for the two production models named by that
code root's own ``localflow.config.load()``, and measures from outside:
launch peak and idle footprint (``footprint`` and ``vmmap``), the worker's
own memory counters at six labels, and per-request stage time, round-trip
time and output digests. Side A is the baseline code root and side B the
candidate; pass the same root twice for an A/A run, which proves the rig is
quiet enough to gate anything (Rig validity). Latency is measured on two
resident workers in paired blocks that alternate A,B,B,A and B,A,A,B.

Thresholds and rule names follow the worker-footprint spec's Gate table.
Reports hold counters, timings, SHA-256 digests, identifiers and
environment facts only: no transcript, audio, observation text or config
value beyond the two model identifiers.

Only one measurement runs at a time on this machine: the run holds an
exclusive lock for its whole length and fails fast when it is taken.

Run: .venv/bin/python scripts/v2/footprint_rig.py --code-root-a <dir>
     [--code-root-b <dir>] [--mode early|shipping]
"""

import argparse
import contextlib
import ctypes
import ctypes.util
import datetime
import fcntl
import hashlib
import importlib.metadata
import json
import mmap
import os
import pathlib
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import types
import zoneinfo

MIB = 1024 * 1024
PROTOCOL_VERSION = 1
MEMORY_LABELS = ("asr_loaded", "asr_warmed", "cleanup_loaded",
                 "cleanup_warmed", "asr_result", "cleanup_result")


# ---- Gate table thresholds, by name --------------------------------------
# Latency: the paired median must worsen by less than max(floor, fraction of
# the band's baseline median); the paired p95 by less than a fraction of the
# band's baseline p95. Early stop is 8 pairs; the shipping claim is 30
# cases x 5 repeats per band.
LATENCY_MEDIAN_FLOOR_MS = 50.0
LATENCY_MEDIAN_FRACTION = 0.05
LATENCY_P95_FRACTION = 0.10
EARLY_PAIRS = 8
SHIPPING_CASES = 30
SHIPPING_REPEATS = 5
# Back-to-back gap: the candidate's gap may grow by less than this.
BACK_TO_BACK_LIMIT_MS = 50.0
# Idle floor and Peak floor (the footprint tool's "MB" is MiB).
IDLE_FLOOR_BYTES = 100 * MIB
PEAK_FLOOR_BYTES = 500 * MIB


# ---- length bands ---------------------------------------------------------
# (name, from, to): from <= value < to; None is open-ended. Cleanup bands
# are by input word count, ASR bands by audio duration in seconds. The
# 90 s edge is where the worker's 60 s chunker starts to run.
CLEANUP_BANDS = (("1-20", 1, 21), ("21-50", 21, 51),
                 ("51-100", 51, 101), ("101-200", 101, 201))
ASR_BANDS = (("under-10s", 0, 10), ("10-30s", 10, 30),
             ("30-90s", 30, 90), ("over-90s", 90, None))


class RigStop(Exception):
    """A condition that makes the run's numbers untrustworthy. The message
    is printed as is, so it never carries content."""


def assign_band(value, bands):
    for name, lo, hi in bands:
        if value >= lo and (hi is None or value < hi):
            return name
    return None


def freeze_bands(items, bands):
    """Band membership for ``(case_id, value)`` items, sorted so it cannot
    depend on enumeration order. Items outside every band are listed as
    unbanded, never dropped."""
    members = {name: [] for name, _, _ in bands}
    unbanded = []
    for case_id, value in items:
        band = assign_band(value, bands)
        (members[band] if band else unbanded).append(case_id)
    return {"edges": [{"band": n, "from": lo, "to": hi}
                      for n, lo, hi in bands],
            "members": {n: sorted(ids) for n, ids in members.items()},
            "unbanded": sorted(unbanded)}


def band_counts(frozen):
    return {name: len(ids) for name, ids in frozen["members"].items()}


def short_bands(frozen, required):
    return [name for name, n in band_counts(frozen).items() if n < required]


def _canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def digest_json(obj):
    return sha256_text(_canonical(obj))


def sha256_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---- paired statistics -------------------------------------------------------

def median(values):
    s = sorted(values)
    mid = len(s) // 2
    return float(s[mid]) if len(s) % 2 else (s[mid - 1] + s[mid]) / 2


def p95(values):
    """Nearest rank: the smallest value with at least 95% of the sample at
    or below it."""
    s = sorted(values)
    return float(s[-(-95 * len(s) // 100) - 1])


def paired_differences(blocks):
    """One paired difference per A,B,B,A block, in send order: the mean of
    the two B times minus the mean of the two A times, which cancels a
    drift that is linear over the block."""
    return [(b1 + b2) / 2 - (a1 + a2) / 2 for a1, b1, b2, a2 in blocks]


def block_order(index):
    """Blocks alternate A,B,B,A and B,A,A,B. With A,B,B,A alone the first
    request of a block always follows the same process's own previous
    request on side A and another process's on side B, which showed up as
    an offset on new inputs in an identical-code A/A."""
    return ("ABBA", "BAAB")[index % 2]


def block_orders(case_ids, used):
    """The order of each block in ``case_ids``: a case alternates between
    the two orders at each of its occurrences, so a bias that depends on
    the case is cancelled by that case's own repeats."""
    seen, out = {}, []
    for case in case_ids:
        out.append(block_order(used.index(case) + seen.get(case, 0)))
        seen[case] = seen.get(case, 0) + 1
    return out


def by_side(order, values):
    """Split a block's values (in send order) into side A's and side B's."""
    out = {"A": [], "B": []}
    for side, value in zip(order, values):
        out[side].append(value)
    return out


def _quad(block, field):
    sides = by_side(block["order"], block[field])
    return (sides["A"][0], sides["B"][0], sides["B"][1], sides["A"][1])


def block_differences(blocks, field):
    """Paired difference per block, whichever order it ran in."""
    return paired_differences([_quad(b, field) for b in blocks])


def block_baseline(blocks, field):
    """Side A's times, the Latency rule's baseline, over all blocks."""
    return [t for b in blocks for t in by_side(b["order"], b[field])["A"]]


def latency_verdict(diffs, baseline_times, aa=None):
    """The Latency rule on paired candidate-minus-baseline differences.
    With ``aa`` (this band's paired median and p95 from the pinned A/A
    report) a limit is never tighter than the instrument: the effective
    limit is max(spec limit, the A/A value of the same statistic)."""
    base_median = median(baseline_times)
    base_p95 = p95(baseline_times)
    spec_median = max(LATENCY_MEDIAN_FLOOR_MS,
                      LATENCY_MEDIAN_FRACTION * base_median)
    spec_p95 = LATENCY_P95_FRACTION * base_p95
    aa_median = aa["paired_median_ms"] if aa else None
    aa_p95 = aa["paired_p95_ms"] if aa else None
    median_limit = spec_median if aa is None else max(spec_median, aa_median)
    p95_limit = spec_p95 if aa is None else max(spec_p95, aa_p95)
    paired_median, paired_p95 = median(diffs), p95(diffs)
    median_pass = paired_median < median_limit
    p95_pass = paired_p95 < p95_limit
    return {"pairs": len(diffs),
            "baseline_median_ms": base_median, "baseline_p95_ms": base_p95,
            "paired_median_ms": paired_median, "paired_p95_ms": paired_p95,
            "spec_median_limit_ms": spec_median, "spec_p95_limit_ms": spec_p95,
            "aa_median_ms": aa_median, "aa_p95_ms": aa_p95,
            "median_limit_ms": median_limit, "p95_limit_ms": p95_limit,
            "median_pass": median_pass, "p95_pass": p95_pass,
            "pass": median_pass and p95_pass}


def rig_validity(band_verdicts):
    """Rig validity: the A/A paired median passes the Latency rule on its
    own, in every band. Bands whose paired p95 fails the rule are listed
    beside it, because a candidate would face the same p95 noise."""
    return {"pass": not [n for n, v in band_verdicts.items()
                         if not v["median_pass"]],
            "failing_bands": sorted(n for n, v in band_verdicts.items()
                                    if not v["median_pass"]),
            "p95_failing_bands": sorted(n for n, v in band_verdicts.items()
                                        if not v["p95_pass"])}


def back_to_back_gap_ms(t_first_result, t_second_result, second_stage_ms):
    """Seconds between two result arrivals, minus the second request's own
    stage time: the time the worker spent outside any stage in between."""
    return (t_second_result - t_first_result) * 1000.0 - second_stage_ms


def gap_verdict(gaps_a, gaps_b, aa_median_ms=None):
    """The Back-to-back gap rule; with the pinned A/A's paired median the
    limit is max(spec limit, that value)."""
    diffs = [b - a for a, b in zip(gaps_a, gaps_b)]
    paired_median = median(diffs)
    limit = BACK_TO_BACK_LIMIT_MS if aa_median_ms is None \
        else max(BACK_TO_BACK_LIMIT_MS, aa_median_ms)
    return {"pairs": len(diffs), "paired_median_ms": paired_median,
            "paired_max_ms": float(max(diffs)),
            "spec_limit_ms": BACK_TO_BACK_LIMIT_MS,
            "aa_median_ms": aa_median_ms, "limit_ms": limit,
            "pass": paired_median < limit}


def load_aa_report(path):
    """A finished A/A report, pinned by its SHA-256 and run id, whose
    paired statistics set the noise floor for later limits."""
    try:
        raw = pathlib.Path(path).read_bytes()
        report = json.loads(raw)
    except (OSError, ValueError):
        raise RigStop("the A/A report cannot be read as a JSON report")
    rig = report.get("rig") if isinstance(report, dict) else None
    if not isinstance(rig, dict) or rig.get("complete") is not True:
        raise RigStop("the A/A report is not complete (rig.complete is not"
                      " true)")

    def pick(v):
        return {"paired_median_ms": v["paired_median_ms"],
                "paired_p95_ms": v["paired_p95_ms"]}
    stats = {"rtt_ms": {}, "stage_ms": {}}
    res = report.get("resident") or {}
    for kind, by_band in (res.get("latency") or {}).items():
        for band, d in by_band.items():
            for field, key in (("rtt_ms", "verdict_rtt"),
                               ("stage_ms", "verdict_stage")):
                if d.get(key):
                    stats[field][f"{kind}:{band}"] = pick(d[key])
    for field, by_metric in ((report.get("first_request") or {}).get(
            "verdicts") or {}).items():
        if field in stats:
            for metric, v in by_metric.items():
                stats[field][f"first-request:{metric}"] = pick(v)
    gap = (res.get("gap") or {}).get("verdict")
    return {"sha256": hashlib.sha256(raw).hexdigest(),
            "run_id": rig.get("run_id"), "stats": stats,
            "gap_median_ms": gap["paired_median_ms"] if gap else None}


def aa_stats(ctx, key, field):
    """The pinned A/A's paired median and p95 for one band, or None."""
    return ctx.aa["stats"][field].get(key) if ctx.aa else None


# ---- planning --------------------------------------------------------------------

def evenly_spaced(ids, n):
    ids = sorted(ids)
    if len(ids) <= n:
        return ids
    return [ids[i * len(ids) // n] for i in range(n)]


def middle(ids):
    """The id in the middle of the sorted list."""
    ids = sorted(ids)
    return ids[len(ids) // 2]


def latency_plan(ids, mode):
    """The A,B,B,A blocks for one band. Early stop is 8 blocks cycling the
    band's cases; the shipping claim is up to 30 cases, each repeated 5
    times, a full pass over the cases before the next repeat so drift is
    spread over repeats. Each case first runs one warmup block, recorded
    but not measured: a process's first request for a new input costs far
    more, and far less steadily, than its repeats. A band with fewer cases
    than the shipping claim still runs what it has and says so."""
    ids = sorted(ids)
    if mode == "early":
        used = evenly_spaced(ids, min(EARLY_PAIRS, len(ids)))
        blocks = [used[i % len(used)] for i in range(EARLY_PAIRS)] \
            if used else []
    else:
        used = evenly_spaced(ids, SHIPPING_CASES)
        blocks = used * SHIPPING_REPEATS
    return {"warmup": list(used), "blocks": blocks, "cases_used": used,
            "cases_available": len(ids),
            "short_of_claim": len(ids) < SHIPPING_CASES}


# ---- model identity ------------------------------------------------------------------

_RESOLVE = (
    "import json, localflow, localflow.config as c\n"
    "cfg = c.load()\n"
    "print(json.dumps({'file': localflow.__file__,"
    " 'model': cfg.get('model'),"
    " 'cleanup_model': cfg.get('cleanup_model')}))\n")


def identity_from_config(cfg):
    """Only the two identifiers leave the configuration; anything else in
    it is neither read nor echoed."""
    for key in ("model", "cleanup_model"):
        if not isinstance(cfg.get(key), str) or not cfg[key]:
            raise RigStop("effective model identity cannot be established:"
                          f" configuration key {key!r} is not an identifier")
    return {"asr_model": cfg["model"], "cleanup_model": cfg["cleanup_model"]}


def resolve_model_identity(code_root, python, env=None):
    """The identifiers the installed app would use, by the code root's own
    ``config.load()`` precedence, run with the code root as cwd. A
    ``localflow`` that resolves outside the root (a stale editable install)
    would silently measure the wrong tree, so it stops the run."""
    code_root = pathlib.Path(code_root).resolve()
    proc = subprocess.run([python, "-c", _RESOLVE], cwd=code_root, env=env,
                          capture_output=True, text=True, timeout=120)
    lines = proc.stdout.strip().splitlines()
    try:
        out = json.loads(lines[-1])
        where = pathlib.Path(out["file"]).resolve()
    except (IndexError, ValueError, KeyError):
        raise RigStop("effective model identity cannot be established:"
                      " the code root's config could not be loaded")
    if code_root not in where.parents:
        raise RigStop("localflow resolves outside the code root"
                      f" ({where.parent}); that tree would be measured"
                      " instead")
    return identity_from_config(out)


# ---- the frame guard -------------------------------------------------------------------

class FrameGuard:
    """Every frame the worker writes passes through here. It stops the run
    on a frame that would make a number untrustworthy: a fault, a failed
    engine, an engine reporting another model than the configured one, an
    engine loading a second time, a result of another generation."""

    def __init__(self, asr_model, cleanup_model, generation=1):
        self._expected = {"asr": asr_model, "cleanup": cleanup_model}
        self._generation = generation
        self._loading = set()
        self._ready = set()

    def check(self, frame):
        op = frame.get("op")
        if op == "fault":
            raise RigStop("worker fault frame: stage="
                          f"{frame.get('stage')}"
                          f" reason_code={frame.get('reason_code')}")
        if op == "engine":
            self._check_engine(frame)
        elif op == "result" and frame.get("generation") != self._generation:
            raise RigStop("result carries generation"
                          f" {frame.get('generation')}, expected"
                          f" {self._generation}")

    def _check_engine(self, frame):
        engine, state = frame.get("engine"), frame.get("state")
        if state == "failed":
            raise RigStop(f"{engine} engine reported failed"
                          f" ({frame.get('reason_code')})")
        want = self._expected.get(engine)
        if frame.get("model_id") != want:
            raise RigStop(f"{engine} engine reports model"
                          f" {frame.get('model_id')!r}, the configuration"
                          f" names {want!r}")
        if state == "loading":
            if engine in self._loading:
                raise RigStop(f"{engine} engine emitted a second loading"
                              " frame")
            self._loading.add(engine)
        elif state == "ready":
            self._ready.add(engine)

    def both_ready(self):
        return self._ready == {"asr", "cleanup"}


# ---- content-free records ---------------------------------------------------------------

_TOKEN = re.compile(r"^[a-z0-9_.:-]{1,80}\Z")


def _token(value):
    return value if isinstance(value, str) and _TOKEN.match(value) else None


def clean_record(frame, rtt_ms):
    """What the report keeps of a cleanup result: timings, the output
    digest and the per-pass output token counts. The observations carry
    prompt and output text; only their counts are read."""
    counts = [o["output_tokens"] if isinstance(o["output_tokens"], int)
              else None
              for o in frame.get("observations") or []
              if isinstance(o, dict) and "pass_id" in o
              and "output_tokens" in o]
    return {"stage_ms": frame.get("duration_ms"), "rtt_ms": rtt_ms,
            "text_sha256": sha256_text(frame.get("text") or ""),
            "path": _token(frame.get("path")),
            "fallback_reason": _token(frame.get("fallback_reason")),
            "pass_output_tokens": counts}


def asr_record(frame, rtt_ms):
    ranges = frame.get("decode_ranges")
    return {"stage_ms": frame.get("duration_ms"), "rtt_ms": rtt_ms,
            "text_sha256": sha256_text(frame.get("text") or ""),
            "decode_ranges_sha256": sha256_text(_canonical(ranges)),
            "decode_range_count": len(ranges)
            if isinstance(ranges, list) else None,
            "sample_count": frame.get("sample_count")}


MIN_GUARDED_TEXT = 12


def assert_content_free(report, texts):
    """Refuse to write a report that contains any text the run saw (an
    output or a fixture input), plain or JSON-escaped. A text shorter than
    ``MIN_GUARDED_TEXT`` could match a report token by accident and stop a
    long run at its final write, so it is not checked."""
    blob = json.dumps(report, ensure_ascii=False)
    for text in texts:
        if len(text) >= MIN_GUARDED_TEXT and (
                text in blob or json.dumps(text)[1:-1] in blob):
            raise RigStop("the report would contain observed content;"
                          " refusing to write it")


# ---- the macOS tools ----------------------------------------------------------------------

_GPU_LINE = "IOAccelerator (graphics)"
_VMMAP_UNITS = {"": 1, "B": 1, "K": 1024, "M": MIB, "G": 1024 ** 3}


def parse_footprint_json(text, pid):
    """``footprint -j`` output for one pid: the total, the GPU line and each
    category's dirty bytes."""
    procs = [p for p in json.loads(text).get("processes", [])
             if p.get("pid") == pid]
    if not procs:
        raise RigStop(f"footprint reported no process with pid {pid}")
    proc = procs[0]
    cats = proc.get("categories") or {}
    if not isinstance(proc.get("footprint"), int) or _GPU_LINE not in cats:
        raise RigStop(f"footprint output for pid {pid} has no footprint"
                      f" total or no {_GPU_LINE} line")
    return {"total_bytes": proc["footprint"],
            "gpu_bytes": cats[_GPU_LINE]["dirty"],
            "gpu_regions": cats[_GPU_LINE]["regions"],
            "categories": {name: c.get("dirty") for name, c in cats.items()}}


def _vmmap_bytes(text, label):
    m = re.search(r"^" + re.escape(label) + r":\s+([\d.]+)([BKMG]?)\s*$",
                  text, re.M)
    if not m:
        return None
    return round(float(m.group(1)) * _VMMAP_UNITS[m.group(2)])


def parse_vmmap_summary(text):
    """The footprint and lifetime-peak lines of ``vmmap -summary``."""
    peak = _vmmap_bytes(text, "Physical footprint (peak)")
    if peak is None:
        raise RigStop("vmmap summary has no lifetime-peak line")
    return {"footprint_bytes": _vmmap_bytes(text, "Physical footprint"),
            "peak_bytes": peak}


# ---- the baseline's go / no-go --------------------------------------------------------------

def judge_levers(m):
    """Go or no-go for the levers the baseline can judge, against the Idle
    floor and Peak floor names, each line stating both measured numbers.
    Ticket 02's cheap form releases allocator cache after each engine's
    load: it can lower idle by at most the cache held at idle, and the
    launch peak by at most the cache held after the ASR warmup (within the
    peak's headroom above idle). Ticket 03 closes with no code when idle 2 s
    after a dictation burst is within the Idle floor of idle after
    warmup."""
    def mib(b):
        return f"{b / MIB:,.0f} MiB"

    def verdict(ok, floor):
        return f"{'clears' if ok else 'is under'} the {floor}"

    idle_cache = m["idle_cache_bytes"]
    peak_gain = min(m["asr_warmed_cached_bytes"],
                    m["launch_peak_bytes"] - m["idle_bytes"])
    idle_ok = idle_cache >= IDLE_FLOOR_BYTES
    peak_ok = peak_gain >= PEAK_FLOOR_BYTES
    go02 = idle_ok or peak_ok
    t02 = (f"{'GO' if go02 else 'NO-GO'} ticket 02 cheap form: cached"
           f" allocator memory at idle is {mib(idle_cache)} and"
           f" {verdict(idle_ok, 'Idle floor')}; the launch peak can fall by"
           f" up to {mib(peak_gain)} (allocator cache held after the ASR"
           " warmup, within the peak's headroom above idle) and"
           f" {verdict(peak_ok, 'Peak floor')}.")
    growth = m["burst_growth_bytes"]
    growth_ok = growth >= IDLE_FLOOR_BYTES
    when = (f"idle 2 s after a dictation burst is {mib(growth)} above idle"
            " after warmup (median over side A bursts, the baseline side)")
    t03 = (f"GO ticket 03: {when} and {verdict(True, 'Idle floor')}."
           if growth_ok else
           f"NO-GO ticket 03, close with a note: {when} and"
           f" {verdict(False, 'Idle floor')}.")
    cached = (f"{m['burst_cache_min_bytes'] / MIB:,.0f} to"
              f" {m['burst_cache_max_bytes'] / MIB:,.0f} MiB")
    return {"ticket_02": {"go": go02, "line": t02},
            "ticket_03": {"go": growth_ok, "line": t03},
            "ticket_03_observation":
                "Observation (not the criterion): the allocator cache left"
                f" after each cleanup result is {cached}."}


# ---- the worker session ------------------------------------------------------------------

class WorkerSession:
    """The supervisor's side of one worker process: spawn, framed requests,
    framed replies. A reader thread stamps every frame at arrival, so a
    round-trip time is not delayed by whatever the rig is doing; every frame
    passes the guard before anything else sees it. Requests always carry
    generation 1. ``cmd`` and ``env`` exist so the tests can substitute the
    shimmed production worker."""

    def __init__(self, code_root, audio_root, identity, *, python=None,
                 cmd=None, env=None, memory_diag=False):
        self._code_root = pathlib.Path(code_root)
        self._identity = identity
        self._cmd = cmd or [python or sys.executable, "-m",
                            "localflow.v2.worker", "--audio-root",
                            str(audio_root)]
        self._env = dict(os.environ)
        self._env.pop("LOCALFLOW_WORKER_MEMORY_DIAG", None)
        if memory_diag:
            self._env["LOCALFLOW_WORKER_MEMORY_DIAG"] = "1"
        self._env.update(env or {})
        self._guard = FrameGuard(identity["asr_model"],
                                 identity["cleanup_model"])
        self._queue = queue.Queue()
        self._seq = 0
        self._proc = None
        self._stderr = None
        self.memory_samples = []

    # -- lifecycle --

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close(kill=exc_type is not None)
        return False

    @property
    def pid(self):
        return self._proc.pid

    def start(self, timeout=120.0):
        self._stderr = tempfile.TemporaryFile()
        self._proc = subprocess.Popen(
            self._cmd, cwd=self._code_root, env=self._env,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=self._stderr)
        threading.Thread(target=self._read_frames, daemon=True).start()
        _, hello = self._next(time.monotonic() + timeout)
        if hello.get("op") != "hello" or hello.get("pid") != self._proc.pid:
            raise RigStop("the worker's first frame is not its hello")
        return hello

    def load(self, timeout=900.0):
        """Send the load request and wait for BOTH engines' ready frames:
        a request sent earlier would measure the degraded path."""
        self._write({"v": PROTOCOL_VERSION, "op": "load",
                     "asr_model": self._identity["asr_model"],
                     "cleanup_model": self._identity["cleanup_model"],
                     "cleanup_mode": "llm", "cleanup_implementation": "v2"})
        deadline = time.monotonic() + timeout
        while not self._guard.both_ready():
            self._next(deadline)

    def close(self, kill=False):
        proc = self._proc
        if proc is None:
            return
        try:
            if not kill and proc.poll() is None:
                self._write({"v": PROTOCOL_VERSION, "op": "shutdown"})
                self._drain(time.monotonic() + 60)
        except (OSError, RigStop):
            kill = True
        if kill or proc.poll() is None:
            proc.kill()
        proc.wait()
        for stream in (proc.stdin, proc.stdout):
            try:
                stream.close()
            except OSError:
                pass
        self._stderr.close()
        self._proc = None

    # -- requests --

    def send(self, op, fields=None):
        """Write one request; returns ``(req_id, sent_at)``."""
        self._seq += 1
        req_id = f"rig-{self._seq}"
        msg = {"v": PROTOCOL_VERSION, "op": op, "req_id": req_id,
               "generation": 1, "attempt": 1, "job_id": req_id}
        msg.update(fields or {})
        sent_at = time.perf_counter()
        self._write(msg)
        return req_id, sent_at

    def collect(self, req_id, sent_at, timeout=300.0):
        deadline = time.monotonic() + timeout
        while True:
            received_at, frame = self._next(deadline)
            if frame.get("op") != "result":
                continue
            if frame.get("req_id") != req_id:
                raise RigStop("a result arrived for a request that is not"
                              " the one in flight")
            return {"frame": frame, "received_at": received_at,
                    "sent_at": sent_at,
                    "rtt_ms": (received_at - sent_at) * 1000.0}

    def request(self, op, fields=None, timeout=300.0):
        return self.collect(*self.send(op, fields), timeout=timeout)

    def wait_memory(self, count, timeout):
        """The result samples are written after the result frame, so they
        may still be in flight when a request returns."""
        deadline = time.monotonic() + timeout
        while len(self.memory_samples) < count:
            self._next(deadline)
        return list(self.memory_samples)

    # -- frames --

    def _write(self, msg):
        data = json.dumps(msg).encode("utf-8")
        self._proc.stdin.write(len(data).to_bytes(4, "big") + data)
        self._proc.stdin.flush()

    def _read_frames(self):
        out = self._proc.stdout
        try:
            while True:
                head = out.read(4)
                if len(head) < 4:
                    break
                body = out.read(int.from_bytes(head, "big"))
                self._queue.put((time.perf_counter(), json.loads(body)))
        except (OSError, ValueError):
            pass
        finally:
            self._queue.put((time.perf_counter(), None))

    def _next(self, deadline):
        try:
            at, frame = self._queue.get(
                timeout=max(0.0, deadline - time.monotonic()))
        except queue.Empty:
            raise RigStop("the worker did not answer in time")
        if frame is None:
            raise RigStop("the worker closed the protocol stream"
                          f" (exit code {self._proc.poll()})")
        self._guard.check(frame)
        if frame.get("op") == "diag" and frame.get("kind") == "memory":
            self._note_memory(frame)
        return at, frame

    def _note_memory(self, frame):
        counts = [frame.get(k) for k in ("active", "cached", "peak")]
        if frame.get("label") not in MEMORY_LABELS \
                or not all(isinstance(c, int) for c in counts):
            raise RigStop("a malformed memory diagnostic frame")
        self.memory_samples.append({
            "label": frame["label"], "active": counts[0],
            "cached": counts[1], "peak": counts[2]})

    def _drain(self, deadline):
        """Read to the end of the stream (the worker exits after
        shutdown), so trailing frames are not lost."""
        while True:
            try:
                self._next(deadline)
            except RigStop as e:
                if "closed the protocol stream" in str(e):
                    return
                raise


# ---- environment facts ----------------------------------------------------------------------

def parse_power(text):
    source = re.search(r"Now drawing from '([^']+)'", text)
    percent = re.search(r"(\d+)%", text)
    return {"source": source.group(1) if source else None,
            "charge_percent": int(percent.group(1)) if percent else None}


def parse_thermal(text):
    """Clean means pmset records neither a thermal nor a performance
    warning level; anything else is kept verbatim."""
    ok = ("No thermal warning level has been recorded" in text
          and "No performance warning level has been recorded" in text)
    return {"ok": ok, "warning": None if ok else text.strip()}


def parse_ps(text):
    rows = []
    for line in text.splitlines():
        m = re.match(r"^\s*(\d+)\s+(\d+)\s+(.*)$", line)
        if m:
            rows.append((int(m.group(1)), int(m.group(2)), m.group(3)))
    return rows


def _runs_a_model_module(cmd):
    """True when the command is a Python interpreter running the worker or
    an mlx_lm module (``python -m ...``); a process that only mentions the
    names, such as a shell or an editor, is not one."""
    tokens = cmd.split()
    if not tokens or not os.path.basename(tokens[0]).lower().startswith(
            "python"):
        return False
    for i, token in enumerate(tokens[:-1]):
        if token == "-m" and (tokens[i + 1] == "localflow.v2.worker"
                              or tokens[i + 1].startswith("mlx_lm")):
            return True
    return False


def classify_workers(rows):
    """The installed app's idle worker (a worker whose parent is the
    installed app) and every other worker or mlx process, which would make
    a measurement unquiet."""
    command = {pid: cmd for pid, _, cmd in rows}
    installed, strays = None, []
    for pid, ppid, cmd in rows:
        if not _runs_a_model_module(cmd):
            continue
        if installed is None \
                and "/Applications/LocalFlow.app" in command.get(ppid, ""):
            installed = pid
        else:
            strays.append(pid)
    return installed, strays


def parse_cputime(text):
    seconds = 0.0
    for part in text.strip().split(":"):
        seconds = seconds * 60 + float(part)
    return seconds


def revision_record(manifest, snapshots):
    """The pins as the repository exposes them (the baseline manifest, with
    the model it names) against the snapshot directory the model cache
    holds; a mismatch is recorded, never resolved."""
    out = {}
    for key in ("asr", "cleanup"):
        entry = (manifest.get("models") or {}).get(key) or {}
        pinned = entry.get("revision")
        out[key] = {"manifest_model": entry.get("configured_id"),
                    "manifest": pinned, "snapshot": snapshots[key],
                    "matches": pinned is not None
                    and pinned == snapshots[key]}
    return out


def acquire_lock(path):
    pathlib.Path(path).parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(fd)
        raise RigStop(f"another measurement holds {path}; one measurement"
                      " runs at a time on this machine")
    return fd


# ---- the cleanup corpus: the committed EV-09 fixtures ------------------------------------------

ROOT = pathlib.Path(__file__).resolve().parents[2]
FIXTURE_SUITES = (("fidelity", "tests/v2/fidelity/fixtures_fidelity.json"),
                  ("literal", "tests/v2/fidelity/fixtures_literal.json"),
                  ("structure", "tests/v2/structure/fixtures_structure.json"))


def load_cleanup_cases(repo_root):
    """Fixture id -> input text, protected spans and word count. The text
    stays in memory; only ids and counts reach the report."""
    cases = {}
    for suite, rel in FIXTURE_SUITES:
        data = json.loads((pathlib.Path(repo_root) / rel).read_text())
        for case in data["cases"]:
            text = case["input"]
            spans = []
            for needle in case.get("protected", []):
                at = text.find(needle)
                if at >= 0:
                    spans.append((at, at + len(needle)))
            cases[f"{suite}:{case['case_id']}"] = {
                "text": text, "protected_spans": spans,
                "words": len(text.split())}
    return cases


# ---- the speech corpus: synthesized, shared by every run ----------------------------------------

VOICES = ("Samantha", "Daniel", "Karen")
# Invented sentences about everyday dictation; no real person or place.
SENTENCES = (
    "The quarterly planning meeting moved to Thursday afternoon, so please update the shared calendar.",
    "Remind me to send the revised budget to the finance team before the end of the week.",
    "I think the second prototype needs another round of testing before we show it to anyone outside the group.",
    "Could you let the design team know that the new layout is ready for their review?",
    "We should schedule a short call to go over the open questions about the delivery schedule.",
    "The printer on the third floor is out of toner again, and the supplier says the order will arrive on Monday.",
    "Please add a note to the project page explaining why we changed the file format.",
    "Next month's workshop will cover the basics of planning, budgeting and keeping a clear record of decisions.",
    "I will be out of the office on Friday, but I can answer messages in the morning.",
    "The summary should mention the three main risks and the steps we have already taken to reduce them.",
    "Thanks for sending the draft so quickly; I made a few small edits and left comments in the margin.",
    "Let's plan the garden for spring: tomatoes along the fence, herbs near the kitchen door, and beans in the back.",
    "The train to the coast leaves at nine, so we should arrive at the station by half past eight.",
    "Please confirm that the room is booked for twenty people and that the projector has been tested.",
    "My notes from the call say that the vendor will send a corrected invoice by the middle of next week.",
    "We need a better way to track which tasks are waiting for review and which ones are blocked.",
    "The new coffee machine in the break room is surprisingly easy to use once you find the right button.",
    "Can you check whether the backup finished last night and let me know if anything looks unusual?",
    "I would like to move our weekly check-in to Wednesday, since Tuesday is now full of other meetings.",
    "The report is almost ready; I only need to double-check the numbers in the second table.",
    "A quiet corner of the library is the best place to read the long documents without interruptions.",
    "Please remind everyone that the deadline for submitting expenses is the last day of the month.",
    "The recipe calls for two cups of flour, a pinch of salt, and enough warm water to make a soft dough.",
    "After the update, the app started faster, but the settings page took a moment longer to open.",
    "I left the keys with the neighbor, who promised to water the plants while we are away.",
    "The committee agreed to publish the minutes within two days and to keep the action list up to date.",
    "Could we add a section about common mistakes, with a short example for each one?",
    "The bridge will be closed for repairs over the weekend, so allow extra time if you are driving downtown.",
    "My plan for the morning is to answer email, review the open requests and then focus on the outline.",
    "Please keep the first paragraph short and put the most important point in the opening sentence.",
    "The museum is free on the first Sunday of every month, which makes it a good time to bring the kids.",
    "We reached a good compromise: the feature ships this month, and the polish follows in the next release.",
    "Tell the courier that the package should be left at the side door if nobody answers the bell.",
    "The meeting notes are saved in the shared folder under the project name and today's date.",
    "I am still deciding between the blue notebook and the green one, and both have a pleasant paper feel.",
    "Before we sign off, let's make sure each owner knows their next step and the date it is due.",
    "The weather forecast shows light rain in the afternoon, so I will move the picnic to the covered patio.",
    "Please summarize the feedback from the survey in a few bullet points and highlight anything surprising.",
    "A short walk after lunch makes the rest of the afternoon feel much calmer and more productive.",
    "The library card renewal takes five minutes at the front desk, and you only need a photo identification.",
    "I would suggest we test the change on a small group first and then roll it out to everyone.",
    "Dinner on Saturday is at seven; I will bring dessert if you can take care of the drinks.",
    "The onboarding guide needs a clearer description of how to request access to the shared tools.",
    "He asked whether the schedule could be shifted by an hour, because the morning session usually runs long.",
    "Our neighborhood association meets on the second Tuesday, and anyone is welcome to bring a topic.",
    "Make sure the final slide lists the contact details, the next meeting date and the shared folder link.",
    "The lighthouse at the end of the pier was built over a century ago and is still used by sailors today.",
    "Please read the instructions twice before starting, and keep the receipt in case anything has to be returned.",
)
_WORDS_PER_SECOND = 3.45  # measured with say at 175 words per minute
# Where each band's clip durations are first aimed. Sentences are whole, so
# the measured duration is what counts: a clip is redone until it lands
# inside its window, kept clear of the band edges (and, for the identity
# clips, on the right side of the 90 s chunker threshold).
_TARGET_RANGES = {"under-10s": (3.0, 6.0), "10-30s": (13.0, 26.0),
                  "30-90s": (40.0, 80.0), "over-90s": (100.0, 125.0)}
IDENTITY_CLIPS = ("identity-under90.wav", "identity-over95.wav")
CLIP_WINDOWS = {"under-10s": (0.5, 9.0), "10-30s": (10.5, 29.0),
                "30-90s": (31.0, 88.0), "over-90s": (93.0, None),
                IDENTITY_CLIPS[0]: (45.0, 88.0),
                IDENTITY_CLIPS[1]: (96.0, None)}


def clip_plan(per_band):
    plan = []
    for b, (band, _, _) in enumerate(ASR_BANDS):
        lo, hi = _TARGET_RANGES[band]
        for j in range(per_band):
            plan.append({
                "name": f"clip-{band}-{j:02d}.wav", "band": band,
                "target_s": round(lo + (hi - lo) * j / max(1, per_band - 1),
                                  1),
                "voice": VOICES[j % len(VOICES)],
                "rate": 165 + (j * 7) % 31,
                "offset": (j * 7 + b * 11) % len(SENTENCES)})
    plan.append({"name": IDENTITY_CLIPS[0], "band": None, "target_s": 60.0,
                 "voice": "Samantha", "rate": 175, "offset": 0})
    plan.append({"name": IDENTITY_CLIPS[1], "band": None, "target_s": 115.0,
                 "voice": "Samantha", "rate": 175, "offset": 17})
    return plan


def compose_text(offset, target_s, rate):
    """Sentences from ``offset`` on until the estimated speaking time
    reaches ``target_s``."""
    wps = _WORDS_PER_SECOND * rate / 175
    words, picked, i = 0, [], offset
    while words / wps < target_s:
        sentence = SENTENCES[i % len(SENTENCES)]
        picked.append(sentence)
        words += len(sentence.split())
        i += 1
    return " ".join(picked)


def read_afconvert_wav(raw):
    """Samples and rate from afconvert's float32 WAV, which carries an
    extra padding chunk the worker's strict parser refuses; the clip is
    rewritten canonically with ``store.write_wav_f32``."""
    import struct
    import numpy as np
    if raw[:4] != b"RIFF" or raw[8:12] != b"WAVE":
        raise RigStop("afconvert output is not a WAV file")
    fmt, i = None, 12
    while i + 8 <= len(raw):
        chunk, size = raw[i:i + 4], struct.unpack("<I", raw[i + 4:i + 8])[0]
        body = raw[i + 8:i + 8 + size]
        if chunk == b"fmt ":
            fmt = struct.unpack("<HHIIHH", body[:16])
        elif chunk == b"data":
            if fmt is None or (fmt[0], fmt[1], fmt[5]) != (3, 1, 32):
                raise RigStop("afconvert output is not mono float32")
            return np.frombuffer(body, dtype="<f4").copy(), fmt[2]
        i += 8 + size + (size & 1)
    raise RigStop("afconvert output has no data chunk")


def _run_tool(cmd):
    proc = subprocess.run(cmd, capture_output=True, timeout=600)
    if proc.returncode != 0:
        raise RigStop(f"{pathlib.Path(cmd[0]).name} failed"
                      f" (exit {proc.returncode})")


def synthesize_clip(text, voice, rate, out_path):
    """Speak ``text`` with the system voice, decode to 16000 Hz mono
    float32 and write the canonical WAV the worker accepts."""
    sys.path.insert(0, str(ROOT))
    from localflow.v2.store import write_wav_f32
    with tempfile.TemporaryDirectory() as td:
        td = pathlib.Path(td)
        (td / "t.txt").write_text(text)
        _run_tool(["/usr/bin/say", "-v", voice, "-r", str(rate), "-o",
                   str(td / "t.aiff"), "-f", str(td / "t.txt")])
        _run_tool(["/usr/bin/afconvert", "-f", "WAVE", "-d", "LEF32@16000",
                   "-c", "1", str(td / "t.aiff"), str(td / "t.wav")])
        samples, hz = read_afconvert_wav((td / "t.wav").read_bytes())
    if hz != 16000:
        raise RigStop("afconvert did not produce 16000 Hz audio")
    write_wav_f32(pathlib.Path(out_path), samples, hz)
    return {"sha256": hashlib.sha256(
        pathlib.Path(out_path).read_bytes()).hexdigest(),
        "duration_s": round(samples.size / hz, 3), "voice": voice,
        "rate": rate, "words": len(text.split())}


def verify_corpus(manifest, corpus_dir):
    for clip in manifest["clips"]:
        path = pathlib.Path(corpus_dir) / clip["name"]
        digest = hashlib.sha256()
        try:
            with open(path, "rb") as fh:
                for block in iter(lambda: fh.read(1 << 20), b""):
                    digest.update(block)
        except OSError:
            digest = None
        if digest is None or digest.hexdigest() != clip["sha256"]:
            raise RigStop(f"corpus clip {clip['name']} is missing or"
                          " changed since it was recorded")


def build_corpus(corpus_dir, per_band):
    """Synthesize every planned clip once. A clip whose measured duration
    falls outside its window is redone with a rescaled aim, so every band
    gets its full count and the identity clips land where the chunker
    decides: one under 90 s, one over 95 s."""
    corpus_dir = pathlib.Path(corpus_dir)
    corpus_dir.mkdir(parents=True, exist_ok=True)
    clips = []
    for spec in clip_plan(per_band):
        lo, hi = CLIP_WINDOWS[spec["band"] or spec["name"]]
        want = lo * 1.15 if hi is None else (lo + hi) / 2
        target = spec["target_s"]
        for _ in range(6):
            text = compose_text(spec["offset"], target, spec["rate"])
            rec = synthesize_clip(text, spec["voice"], spec["rate"],
                                  corpus_dir / spec["name"])
            if lo <= rec["duration_s"] \
                    and (hi is None or rec["duration_s"] <= hi):
                break
            target *= min(2.0, max(0.5, want / rec["duration_s"]))
        else:
            raise RigStop(f"{spec['name']} did not land inside its duration"
                          " window")
        clips.append({"name": spec["name"],
                      "band": assign_band(rec["duration_s"], ASR_BANDS)
                      if spec["band"] else None,
                      "target_s": round(target, 1), **rec})
    manifest = {"sample_rate": 16000, "format": "float32 mono",
                "synthesizer": "say + afconvert", "clips": clips}
    (corpus_dir / "manifest.json").write_text(json.dumps(manifest, indent=1))
    return manifest


# ---- summaries -----------------------------------------------------------------------------------

def summarize_spawns(spawns):
    """Median, min and max of each footprint figure per side and cache
    label."""
    groups = {}
    for sp in spawns:
        groups.setdefault(f"{sp['side']}/{sp['label']}", []).append(sp)

    def stat(rows, field):
        vals = [r[field] for r in rows]
        return {"median": median(vals), "min": min(vals), "max": max(vals)}

    return {key: {"spawns": len(rows),
                  **{f: stat(rows, f) for f in (
                      "idle_total_bytes", "idle_gpu_bytes",
                      "launch_peak_bytes", "load_ms")},
                  "resident_fraction_median": median(
                      [r["cache"]["resident_fraction"] for r in rows])}
            for key, rows in groups.items()}


def summarize_memory(samples):
    """The six labels at their first occurrence, the cached counter after
    every result, and the last sample of each result label."""
    first, asr, clean = {}, [], []
    for m in samples:
        first.setdefault(m["label"], m)
        if m["label"] == "asr_result":
            asr.append(m)
        elif m["label"] == "cleanup_result":
            clean.append(m)
    return {"first": first,
            "asr_result_cached": [m["cached"] for m in asr],
            "cleanup_result_cached": [m["cached"] for m in clean],
            "final_asr_result": asr[-1] if asr else None,
            "final_cleanup_result": clean[-1] if clean else None}


def lever_inputs(spawns, bursts):
    """The numbers ``judge_levers`` needs: footprint medians, the diag-on
    counters and the idle growth after a burst, all from side A, the
    baseline. Side B's growth is not pooled in: a candidate that lowered its
    idle at ready would otherwise read as growth. None when the run did not
    produce them."""
    a_spawns = [s for s in spawns if s["side"] == "A"]
    a_bursts = [b for b in bursts if b["side"] == "A"]
    diag = [b for b in a_bursts if b["memory_diag"] and b["memory"]]
    if not a_spawns or not diag:
        return None
    left = [c for b in diag for c in b["memory"]["cleanup_result_cached"]]
    return {
        "idle_bytes": median([s["idle_total_bytes"] for s in a_spawns]),
        "launch_peak_bytes": median([s["launch_peak_bytes"]
                                     for s in a_spawns]),
        "idle_cache_bytes": median(
            [b["memory"]["first"]["cleanup_warmed"]["cached"] for b in diag]),
        "asr_warmed_cached_bytes": median(
            [b["memory"]["first"]["asr_warmed"]["cached"] for b in diag]),
        "burst_growth_bytes": median(
            [b["after_burst"]["total_bytes"] - b["idle"]["total_bytes"]
             for b in a_bursts]),
        "burst_cache_min_bytes": min(left),
        "burst_cache_max_bytes": max(left)}


# ---- page cache: warm and cold-ish spawns ----------------------------------------------------------

COLD_TARGET = 0.05           # resident fraction at or under which "cold-ish"
EVICT_BUDGET_BYTES = 64 * 1024 ** 3
_libc = None


def resident_fraction(paths):
    """Share of the files' pages resident in the page cache, by mincore:
    the label of a cold-ish spawn states how cold it actually was."""
    global _libc
    if _libc is None:
        _libc = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)
        _libc.mincore.argtypes = [ctypes.c_void_p, ctypes.c_size_t,
                                  ctypes.c_char_p]
    resident = total = 0
    for path in paths:
        size = os.path.getsize(path)
        if not size:
            continue
        fd = os.open(path, os.O_RDONLY)
        try:
            mm = mmap.mmap(fd, size, access=mmap.ACCESS_COPY)
            try:
                addr = ctypes.addressof(ctypes.c_char.from_buffer(mm))
                pages = (size + mmap.PAGESIZE - 1) // mmap.PAGESIZE
                vec = ctypes.create_string_buffer(pages)
                if _libc.mincore(ctypes.c_void_p(addr), size, vec) != 0:
                    raise RigStop("mincore could not read page-cache"
                                  " residency")
                resident += sum(1 for b in vec.raw[:pages] if b & 1)
                total += pages
                del addr
            finally:
                mm.close()
        finally:
            os.close(fd)
    return resident / total if total else 0.0


def read_through(paths):
    for path in paths:
        with open(path, "rb", buffering=0) as fh:
            while fh.read(8 * MIB):
                pass


def evict_by_reading(weights, pool, protect_tokens):
    """Read unrelated large files until the weights are (nearly) out of the
    page cache or the byte budget is spent; returns the bytes read."""
    protect = set()
    for path in weights:
        st = os.stat(path)
        protect.add((st.st_dev, st.st_ino))
    pool_files = []
    for dirpath, dirnames, filenames in os.walk(pool):
        dirnames.sort()
        for name in sorted(filenames):
            path = os.path.join(dirpath, name)
            if os.path.islink(path):
                continue
            try:
                st = os.stat(path)
            except OSError:
                continue
            low = path.lower()
            if st.st_size < 64 * MIB or (st.st_dev, st.st_ino) in protect \
                    or any(t.lower() in low for t in protect_tokens):
                continue
            pool_files.append(path)
    read = checked = 0
    for path in pool_files:
        try:
            fh = open(path, "rb", buffering=0)
        except OSError:
            continue
        with fh:
            while read < EVICT_BUDGET_BYTES:
                block = fh.read(8 * MIB)
                if not block:
                    break
                read += len(block)
                if read - checked >= 2 * 1024 ** 3:
                    checked = read
                    if resident_fraction(weights) <= COLD_TARGET:
                        return read
        if read >= EVICT_BUDGET_BYTES:
            break
    return read


def prepare_cache(ctx, label):
    """Make the model files warm (read through) or cold-ish (``sudo -n
    purge`` when it needs no password, otherwise eviction by reading
    unrelated files) and report what the page cache actually holds."""
    weights = ctx.weights
    if label == "warm":
        read_through(weights)
        return {"intent": "warm", "method": "read-through",
                "bytes_read": None,
                "resident_fraction": resident_fraction(weights)}
    method, read = None, None
    if ctx.purge_allowed:
        purge = subprocess.run(["sudo", "-n", "purge"],
                               capture_output=True, timeout=120)
        if purge.returncode == 0:
            method = "purge"
        else:
            ctx.purge_allowed = False
    if method is None:
        if resident_fraction(weights) <= COLD_TARGET:
            method = "already-cold"
        else:
            read = evict_by_reading(weights, ctx.evict_pool,
                                    ctx.protect_tokens)
            method = "eviction-read"
    return {"intent": "cold-ish", "method": method, "bytes_read": read,
            "resident_fraction": resident_fraction(weights)}


# ---- the macOS tools, run ---------------------------------------------------------------------------

def read_footprint(pid, scratch):
    path = pathlib.Path(scratch) / f"footprint-{pid}.json"
    proc = subprocess.run(["/usr/bin/footprint", "-j", str(path), str(pid)],
                          capture_output=True, timeout=120)
    if proc.returncode != 0:
        raise RigStop(f"footprint failed for pid {pid}"
                      f" (exit {proc.returncode})")
    try:
        return parse_footprint_json(path.read_text(), pid)
    finally:
        path.unlink(missing_ok=True)


def read_vmmap(pid):
    proc = subprocess.run(["/usr/bin/vmmap", "-summary", str(pid)],
                          capture_output=True, text=True, timeout=300)
    if proc.returncode != 0:
        raise RigStop(f"vmmap failed for pid {pid}"
                      f" (exit {proc.returncode})")
    return parse_vmmap_summary(proc.stdout)


def _tool_text(cmd):
    return subprocess.run(cmd, capture_output=True, text=True,
                          timeout=60).stdout


def power_state():
    return parse_power(_tool_text(["pmset", "-g", "batt"]))


def thermal_state():
    return parse_thermal(_tool_text(["pmset", "-g", "therm"]))


_EASTERN = zoneinfo.ZoneInfo("America/New_York")


def now_et():
    return datetime.datetime.now(_EASTERN).isoformat(timespec="seconds")


def et_label(iso):
    """A report timestamp as US Eastern with its zone label."""
    if not iso:
        return "n/a"
    when = datetime.datetime.fromisoformat(iso).astimezone(_EASTERN)
    return when.strftime("%Y-%m-%d %-I:%M %p %Z")


# ---- requests -------------------------------------------------------------------------------------------

SETTLE_S = 2.0
BURST_DICTATIONS = 20
MODE_COUNTS = {
    "early": {"warm": 2, "cold": 2, "burst": 1, "first": 8, "gap": 8},
    "shipping": {"warm": 7, "cold": 5, "burst": 3, "first": 10, "gap": 30}}


def asr_request(clip):
    return "transcribe", {"audio": {"name": clip}, "sample_rate": 16000}


def clean_request(case):
    return "clean", {"raw_text": case["text"],
                     "protected_spans": [list(s)
                                         for s in case["protected_spans"]]}


def timed(ctx, session, op, fields, kind):
    """One request; the record holds timings and digests only. The output
    text is kept (in memory) just so the report can be checked for it."""
    r = session.request(op, fields)
    ctx.seen.add(r["frame"].get("text") or "")
    make = clean_record if kind == "clean" else asr_record
    return make(r["frame"], r["rtt_ms"])


# ---- fresh-spawn phases --------------------------------------------------------------------------------

def measure_spawn(ctx, side, label, cache):
    t0 = time.perf_counter()
    with ctx.make_session(side, False) as s:
        s.start()
        s.load()
        load_ms = (time.perf_counter() - t0) * 1000.0
        time.sleep(SETTLE_S)
        fp = read_footprint(s.pid, ctx.scratch)
        vm = read_vmmap(s.pid)
    return {"side": side, "label": label, "cache": cache, "load_ms": load_ms,
            "idle_total_bytes": fp["total_bytes"],
            "idle_gpu_bytes": fp["gpu_bytes"],
            "idle_gpu_regions": fp["gpu_regions"],
            "idle_categories": fp["categories"],
            "launch_peak_bytes": vm["peak_bytes"],
            "vmmap_footprint_bytes": vm["footprint_bytes"], "at": now_et()}


def phase_footprint(ctx):
    jobs = []
    for i in range(max(ctx.counts["warm"], ctx.counts["cold"])):
        order = ("A", "B") if i % 2 == 0 else ("B", "A")
        for label, n in (("warm", ctx.counts["warm"]),
                         ("cold-ish", ctx.counts["cold"])):
            if i < n:
                jobs += [(side, label) for side in order]
    spawns = []
    for n, (side, label) in enumerate(jobs, 1):
        print(f"  footprint spawn {n}/{len(jobs)}: side {side}, {label}",
              flush=True)
        spawns.append(measure_spawn(ctx, side, label,
                                    prepare_cache(ctx, label)))
    return {"spawns": spawns, "summary": summarize_spawns(spawns)}


def measure_burst(ctx, side, diag, dictations):
    cache = prepare_cache(ctx, "warm")
    t0 = time.perf_counter()
    with ctx.make_session(side, diag) as s:
        s.start()
        s.load()
        load_ms = (time.perf_counter() - t0) * 1000.0
        time.sleep(SETTLE_S)
        idle_fp, idle_vm = read_footprint(s.pid, ctx.scratch), read_vmmap(
            s.pid)
        rtts, last = [], None
        for clip, case_id in dictations:
            a = timed(ctx, s, *asr_request(clip), "asr")
            c = s.request(*clean_request(ctx.cases[case_id]))
            ctx.seen.add(c["frame"].get("text") or "")
            rtts.append({"asr_ms": a["rtt_ms"], "clean_ms": c["rtt_ms"]})
            last = c["received_at"]
        memory = None
        if diag:
            memory = summarize_memory(
                s.wait_memory(4 + 2 * len(dictations), 60))
        rest = SETTLE_S - (time.perf_counter() - last)
        if rest > 0:
            time.sleep(rest)
        after_fp, after_vm = read_footprint(s.pid, ctx.scratch), \
            read_vmmap(s.pid)
    return {"side": side, "memory_diag": diag, "cache": cache,
            "load_ms": load_ms, "dictations": len(dictations),
            "idle": {"total_bytes": idle_fp["total_bytes"],
                     "gpu_bytes": idle_fp["gpu_bytes"],
                     "launch_peak_bytes": idle_vm["peak_bytes"]},
            "after_burst": {"total_bytes": after_fp["total_bytes"],
                            "gpu_bytes": after_fp["gpu_bytes"],
                            "gpu_regions": after_fp["gpu_regions"],
                            "categories": after_fp["categories"],
                            "peak_bytes": after_vm["peak_bytes"]},
            "requests": rtts, "memory": memory, "at": now_et()}


def burst_dictations(ctx):
    """20 dictations, each an ASR clip then a cleanup fixture: five clips
    from the three shorter ASR bands, fixtures spread over the banded
    cases."""
    asr = ctx.bands["asr"]["members"]
    clips = evenly_spaced(asr["under-10s"] + asr["10-30s"] + asr["30-90s"],
                          5)
    banded = [c for ids in ctx.bands["cleanup"]["members"].values()
              for c in ids]
    cases = evenly_spaced(banded, BURST_DICTATIONS)
    return [(clips[k % len(clips)], cases[k % len(cases)])
            for k in range(BURST_DICTATIONS)]


def phase_bursts(ctx):
    dictations = burst_dictations(ctx)
    runs = []
    for diag in (False, True):
        for i in range(ctx.counts["burst"]):
            for side in (("A", "B") if i % 2 == 0 else ("B", "A")):
                print(f"  burst: side {side}, memory diag"
                      f" {'on' if diag else 'off'}, run {i + 1}", flush=True)
                runs.append(measure_burst(ctx, side, diag, dictations))
    return runs


def phase_first(ctx):
    asr_ids = ctx.bands["asr"]["members"]["10-30s"] or [
        c for ids in ctx.bands["asr"]["members"].values() for c in ids]
    clean_ids = ctx.bands["cleanup"]["members"]["21-50"] or [
        c for ids in ctx.bands["cleanup"]["members"].values() for c in ids]
    clip, case_id = middle(asr_ids), middle(clean_ids)
    rows = []
    for k in range(ctx.counts["first"]):
        order = ("A", "B") if k % 2 == 0 else ("B", "A")
        print(f"  first-request pair {k + 1}/{ctx.counts['first']}:"
              f" order {''.join(order)}", flush=True)
        prepare_cache(ctx, "warm")
        row = {"order": "".join(order), "asr": {}, "clean": {},
               "thermal_before": thermal_state()["ok"]}
        with contextlib.ExitStack() as stack:
            sessions = {}
            for side in order:
                s = stack.enter_context(ctx.make_session(side, False))
                s.start()
                s.load()
                sessions[side] = s
            time.sleep(SETTLE_S)
            for side in order:
                row["asr"][side] = timed(ctx, sessions[side],
                                         *asr_request(clip), "asr")
            for side in order:
                row["clean"][side] = timed(
                    ctx, sessions[side],
                    *clean_request(ctx.cases[case_id]), "clean")
        row["thermal_after"] = thermal_state()["ok"]
        rows.append(row)
    verdicts = {}
    for metric in ("asr", "clean"):
        for field in ("rtt_ms", "stage_ms"):
            diffs = [r[metric]["B"][field] - r[metric]["A"][field]
                     for r in rows]
            base = [r[metric]["A"][field] for r in rows]
            verdicts.setdefault(field, {})[metric] = latency_verdict(
                diffs, base, aa_stats(ctx, f"first-request:{metric}", field))
    return {"clip": clip, "case": case_id, "pairs": rows,
            "verdicts": verdicts}


# ---- the resident pair: identity, paired latency, back-to-back gap -----------------------------

def run_identity(ctx, sessions):
    """Every committed cleanup fixture and the two identity clips on both
    sides; the digests and per-pass token counts are the reference every
    later ticket compares against."""
    cleanup = {}
    for case_id in sorted(ctx.cases):
        row = {side: timed(ctx, sessions[side],
                           *clean_request(ctx.cases[case_id]), "clean")
               for side in ("A", "B")}
        row["match"] = (
            row["A"]["text_sha256"] == row["B"]["text_sha256"]
            and row["A"]["pass_output_tokens"]
            == row["B"]["pass_output_tokens"])
        cleanup[case_id] = row
    asr = {}
    for name in IDENTITY_CLIPS:
        row = {side: timed(ctx, sessions[side], *asr_request(name), "asr")
               for side in ("A", "B")}
        row["match"] = all(row["A"][k] == row["B"][k] for k in (
            "text_sha256", "decode_ranges_sha256", "decode_range_count"))
        asr[name] = row
    chunker = {"under90_ranges": asr[IDENTITY_CLIPS[0]]["A"][
        "decode_range_count"], "over95_ranges": asr[IDENTITY_CLIPS[1]]["A"][
        "decode_range_count"]}
    chunker["ran"] = chunker["under90_ranges"] == 1 \
        and (chunker["over95_ranges"] or 0) > 1
    return {"cleanup": cleanup, "asr": asr, "chunker": chunker,
            "mismatches": [c for c, r in cleanup.items() if not r["match"]]
            + [n for n, r in asr.items() if not r["match"]]}


def run_blocks(ctx, sessions, case_ids, used, make_request, kind):
    blocks = []
    for case_id, order in zip(case_ids, block_orders(case_ids, used)):
        op, fields = make_request(case_id)
        recs = [timed(ctx, sessions[side], op, fields, kind)
                for side in order]
        thermal = thermal_state()
        if not thermal["ok"]:
            ctx.thermal_events.append({"case": case_id,
                                       "warning": thermal["warning"]})
        blocks.append({"case": case_id, "order": order,
                       "rtt_ms": [r["rtt_ms"] for r in recs],
                       "stage_ms": [r["stage_ms"] for r in recs],
                       "text_sha256": [r["text_sha256"] for r in recs],
                       "thermal_ok": thermal["ok"]})
    return blocks


def _block_verdict(blocks, field, aa=None):
    return latency_verdict(block_differences(blocks, field),
                           block_baseline(blocks, field), aa)


def band_result(plan, blocks, warmup_blocks, aa=None):
    """Verdicts come from the measured blocks only. The warmup blocks are
    kept, with their own informational verdict (spec limits), as the record
    of the first-request-for-a-new-input regime. ``aa`` maps a time field
    to the pinned A/A statistics for this band."""
    aa = aa or {}
    meta = {k: plan[k] for k in ("cases_used", "cases_available",
                                 "short_of_claim")}
    meta["blocks"] = len(blocks)
    if not blocks:
        return {"plan": meta, "warmup_blocks": [], "blocks": [],
                "verdict_rtt": None, "verdict_stage": None,
                "warmup_verdict_rtt": None, "identity_consistent": True}
    out = {"plan": meta, "warmup_blocks": warmup_blocks, "blocks": blocks,
           "verdict_rtt": _block_verdict(blocks, "rtt_ms", aa.get("rtt_ms")),
           "verdict_stage": _block_verdict(blocks, "stage_ms",
                                           aa.get("stage_ms")),
           "warmup_verdict_rtt": _block_verdict(warmup_blocks, "rtt_ms")
           if warmup_blocks else None}
    digests = {}
    for b in warmup_blocks + blocks:
        digests.setdefault(b["case"], set()).update(b["text_sha256"])
    out["identity_consistent"] = all(len(d) == 1 for d in digests.values())
    return out


def run_gap(ctx, sessions):
    ids = ctx.bands["cleanup"]["members"]["21-50"]
    if len(ids) < 2:
        ids = sorted(ctx.cases)
    blocks = []
    for k in range(ctx.counts["gap"]):
        first_id, second_id = ids[k % len(ids)], ids[(k + 1) % len(ids)]
        gaps = []
        order = block_order(k)
        for side in order:
            s = sessions[side]
            one = s.send(*clean_request(ctx.cases[first_id]))
            two = s.send(*clean_request(ctx.cases[second_id]))
            r1, r2 = s.collect(*one), s.collect(*two)
            for r in (r1, r2):
                ctx.seen.add(r["frame"].get("text") or "")
            gaps.append(back_to_back_gap_ms(
                r1["received_at"], r2["received_at"],
                r2["frame"]["duration_ms"]))
        blocks.append({"cases": [first_id, second_id], "order": order,
                       "gap_ms": gaps})
    sides = [by_side(b["order"], b["gap_ms"]) for b in blocks]
    verdict = gap_verdict([sum(x["A"]) / 2 for x in sides],
                          [sum(x["B"]) / 2 for x in sides],
                          ctx.aa["gap_median_ms"] if ctx.aa else None)
    return {"blocks": blocks, "verdict": verdict}


def phase_resident(ctx):
    with contextlib.ExitStack() as stack:
        sessions = {}
        for side in ("A", "B"):
            s = stack.enter_context(ctx.make_session(side, False))
            s.start()
            s.load()
            sessions[side] = s
        time.sleep(SETTLE_S)
        out = {"thermal_before": thermal_state(),
               "power_before": power_state()}
        print("  identity: every fixture and both identity clips", flush=True)
        out["identity"] = run_identity(ctx, sessions)
        out["latency"] = {"cleanup": {}, "asr": {}}
        for kind, bands, make in (
                ("cleanup", ctx.bands["cleanup"]["members"],
                 lambda cid: clean_request(ctx.cases[cid])),
                ("asr", ctx.bands["asr"]["members"], asr_request)):
            for band, ids in bands.items():
                plan = latency_plan(ids, ctx.mode)
                print(f"  latency {kind} band {band}: {len(plan['warmup'])}"
                      f" warmup + {len(plan['blocks'])} paired blocks"
                      f" ({plan['cases_available']} cases"
                      f"{', short of the claim' if plan['short_of_claim'] else ''})",
                      flush=True)
                step = "clean" if kind == "cleanup" else "asr"
                used = plan["cases_used"]
                warm = run_blocks(ctx, sessions, plan["warmup"], used, make,
                                  step)
                out["latency"][kind][band] = band_result(
                    plan, run_blocks(ctx, sessions, plan["blocks"], used,
                                     make, step), warm,
                    {f: aa_stats(ctx, f"{kind}:{band}", f)
                     for f in ("rtt_ms", "stage_ms")})
        print(f"  back-to-back gap: {ctx.counts['gap']} paired blocks",
              flush=True)
        out["gap"] = run_gap(ctx, sessions)
        out["thermal_after"] = thermal_state()
        out["power_after"] = power_state()
    out["thermal_events"] = ctx.thermal_events
    return out


# ---- verdicts and judgement --------------------------------------------------------------------------

def assemble_verdicts(report):
    """The Gate-table verdicts the run can state, by name."""
    bands = {}
    res = report.get("resident") or {}
    for kind, by_band in (res.get("latency") or {}).items():
        for band, d in by_band.items():
            if d["verdict_rtt"]:
                bands[f"{kind}:{band}"] = d["verdict_rtt"]
    first = report.get("first_request") or {}
    for metric, v in (first.get("verdicts") or {}).get("rtt_ms", {}).items():
        bands[f"first-request:{metric}"] = v
    out = {"latency": {"measured_on": "paired round-trip time",
                       "pass": all(v["pass"] for v in bands.values())
                       if bands else None,
                       "bands": bands}}
    out["rig_validity"] = rig_validity(bands) if bands else None
    out["back_to_back_gap"] = (res.get("gap") or {}).get("verdict")
    ident = res.get("identity")
    if ident:
        inconsistent = sorted(
            f"{kind}:{band}" for kind, by_band in res["latency"].items()
            for band, d in by_band.items() if not d["identity_consistent"])
        out["identity"] = {
            "pass": not ident["mismatches"] and ident["chunker"]["ran"]
            and not inconsistent,
            "mismatches": ident["mismatches"],
            "chunker_ran": ident["chunker"]["ran"],
            "inconsistent_across_blocks": inconsistent}
    return out


def judgement(report):
    inputs = lever_inputs((report.get("footprint") or {}).get("spawns", []),
                          report.get("bursts") or [])
    if inputs:
        out = judge_levers(inputs)
    else:
        out = {k: {"go": None, "line": f"not judged: {k.replace('_', ' ')}"
                   " needs the footprint and burst phases"}
               for k in ("ticket_02", "ticket_03")}
    out["inputs"] = inputs
    out["loader"] = ("Loader eligibility: deferred until ticket 02's"
                     " cheap-form measurement.")
    out["residency"] = ("Residency eligibility: deferred until ticket 05's"
                        " gate.")
    return out


# ---- environment ----------------------------------------------------------------------------------------

def tree_digest(root):
    """SHA-256 of the code root's ``localflow/`` tree: the lines
    ``<path> <file SHA-256>`` in path order, paths relative to
    ``localflow/``, bytecode caches left out. An export proves equal to a
    commit by exporting the commit and comparing digests."""
    base = pathlib.Path(root) / "localflow"
    lines = []
    for path in sorted(p for p in base.rglob("*") if p.is_file()
                       and "__pycache__" not in p.relative_to(base).parts):
        lines.append(f"{path.relative_to(base).as_posix()}"
                     f" {hashlib.sha256(path.read_bytes()).hexdigest()}\n")
    return sha256_text("".join(lines))


def code_root_info(root):
    """Where a side's code came from. ``head`` and ``dirty`` are the root's
    own checkout state, reported only when git's top level IS the root: an
    export sitting inside another checkout would otherwise borrow that
    checkout's head and dirtiness. Any other root is an export (head and
    dirty null); its tree digest is the proof of what it holds."""
    def git(*args):
        return subprocess.run(["git", "-C", str(root), *args],
                              capture_output=True, text=True).stdout.strip()
    top = git("rev-parse", "--show-toplevel")
    checkout = bool(top) and os.path.realpath(top) == os.path.realpath(root)
    return {"path": str(root),
            "head": git("rev-parse", "HEAD") if checkout else None,
            "dirty": bool(git("status", "--porcelain")) if checkout
            else None,
            "export": not checkout, "tree_sha256": tree_digest(root)}


def code_root_line(side, info):
    where = (f"head {info['head']} (dirty: {info['dirty']})"
             if not info["export"] else "export, not a checkout root"
             " (no head)")
    return (f"- side {side}: {where}, localflow tree SHA-256"
            f" `{info['tree_sha256']}`")


def installed_worker_cpu(pid):
    if pid is None:
        return None
    text = _tool_text(["ps", "-o", "cputime=", "-p", str(pid)]).strip()
    return parse_cputime(text) if text else None


def environment(ctx):
    libs = {name: importlib.metadata.version(name)
            for name in ("mlx", "mlx-lm", "parakeet-mlx", "huggingface-hub")}
    sysctl = lambda key: _tool_text(["sysctl", "-n", key]).strip()  # noqa: E731
    return {
        "python": sys.version.split()[0], "libraries": libs,
        "machine": {"model": sysctl("hw.model"),
                    "chip": sysctl("machdep.cpu.brand_string"),
                    "memory_bytes": int(sysctl("hw.memsize") or 0),
                    "macos": _tool_text(["sw_vers",
                                         "-productVersion"]).strip()},
        "code_roots": {side: code_root_info(root)
                       for side, root in ctx.roots.items()},
        "models": {**ctx.identity, "revisions": ctx.revisions},
        "power_before": power_state(), "thermal_before": thermal_state(),
        "installed_worker": {"pid": ctx.installed_pid,
                             "cpu_s_before": installed_worker_cpu(
                                 ctx.installed_pid)}}


# ---- the summary ---------------------------------------------------------------------------------------

def _mib(b):
    return f"{b / MIB:,.0f}"


def _yes(flag):
    return "n/a" if flag is None else "pass" if flag else "FAIL"


def render_summary(report):
    r = report
    out = [f"# Footprint rig run {r['rig']['run_id']}", "",
           f"Mode {r['rig']['mode']}; started"
           f" {et_label(r['rig']['started_at'])}, finished"
           f" {et_label(r['rig'].get('finished_at'))}; complete:"
           f" {r['rig']['complete']}; phases: {', '.join(r['rig']['phases'])}.",
           "", "Sizes are MiB (the footprint tool's MB). Times are US Eastern.",
           ""]
    env = r["environment"]
    out += ["## Environment", "",
            f"- {env['machine']['chip']}, {env['machine']['memory_bytes'] // 1024 ** 3} GB,"
            f" macOS {env['machine']['macos']}, Python {env['python']}",
            "- libraries: " + ", ".join(f"{k} {v}" for k, v in
                                       env["libraries"].items()),
            f"- models: {env['models']['asr_model']},"
            f" {env['models']['cleanup_model']}",
            f"- revisions: {json.dumps(env['models']['revisions'])}",
            f"- power {env['power_before']} before, {env.get('power_after')} after;"
            f" thermal clean before: {env['thermal_before']['ok']},"
            f" after: {(env.get('thermal_after') or {}).get('ok')}",
            f"- installed idle worker {env['installed_worker']}", ""]
    for side, info in env["code_roots"].items():
        out.append(code_root_line(side, info))
    b = r["bands"]
    out += ["", "## Frozen bands", "",
            f"Digest `{b['digest']}`. Short of the shipping-claim case"
            f" count: {json.dumps(b['short'])}.", ""]
    for kind in ("cleanup", "asr"):
        out.append(f"- {kind}: {json.dumps(b['counts'][kind])}; unbanded:"
                   f" {len(b[kind]['unbanded'])}")
    fp = r.get("footprint")
    if fp:
        out += ["", "## Idle footprint and launch peak (fresh spawns)", "",
                "| side/cache | spawns | idle total | idle GPU line |"
                " launch peak | load s | resident |",
                "|---|---|---|---|---|---|---|"]
        for key, s in sorted(fp["summary"].items()):
            def cell(f):
                v = s[f]
                return (f"{_mib(v['median'])}"
                        f" ({_mib(v['min'])}-{_mib(v['max'])})")
            out.append(
                f"| {key} | {s['spawns']} | {cell('idle_total_bytes')} |"
                f" {cell('idle_gpu_bytes')} | {cell('launch_peak_bytes')} |"
                f" {s['load_ms']['median'] / 1000:.1f} |"
                f" {s['resident_fraction_median']:.2f} |")
        methods = sorted({sp["cache"]["method"] for sp in fp["spawns"]
                          if sp["label"] == "cold-ish"})
        out += ["", f"Cold-ish method(s): {', '.join(methods) or 'none'};"
                " the resident column is the share of the model files"
                " the page cache held just before the spawn."]
    bursts = r.get("bursts")
    if bursts:
        out += ["", "## After a 20-dictation burst", "",
                "| side | memory diag | idle total | after burst total |"
                " after burst GPU | peak after |", "|---|---|---|---|---|---|"]
        for x in bursts:
            out.append(f"| {x['side']} | {x['memory_diag']} |"
                       f" {_mib(x['idle']['total_bytes'])} |"
                       f" {_mib(x['after_burst']['total_bytes'])} |"
                       f" {_mib(x['after_burst']['gpu_bytes'])} |"
                       f" {_mib(x['after_burst']['peak_bytes'])} |")
        diag = [x for x in bursts if x["side"] == "A" and x["memory_diag"]
                and x["memory"]]
        if diag:
            out += ["", "Allocator counters at the six labels (side A,"
                    " median over diag-on spawns):", "",
                    "| label | active | cached | peak |", "|---|---|---|---|"]
            for label in MEMORY_LABELS:
                cells = [_mib(median([x["memory"]["first"][label][k]
                                      for x in diag]))
                         for k in ("active", "cached", "peak")]
                out.append(f"| {label} | " + " | ".join(cells) + " |")
    v = r.get("verdicts") or {}
    if v.get("latency"):
        aa_pin = r["rig"].get("aa_report")
        out += ["", "## Latency (paired, round-trip time)", "",
                (f"Limits are max(spec limit, A/A value) against A/A report"
                 f" {aa_pin['run_id']} (SHA-256 `{aa_pin['sha256']}`)."
                 if aa_pin else
                 "No A/A report pinned: the spec limits apply."), "",
                "| band | pairs | baseline median/p95 ms | paired median/p95 ms"
                " | spec limits ms | A/A paired ms | effective limits ms |"
                " verdict |", "|---|---|---|---|---|---|---|---|"]
        for name, x in v["latency"]["bands"].items():
            aa = "n/a" if x["aa_median_ms"] is None else (
                f"{x['aa_median_ms']:.1f} / {x['aa_p95_ms']:.1f}")
            out.append(
                f"| {name} | {x['pairs']} | {x['baseline_median_ms']:.1f} /"
                f" {x['baseline_p95_ms']:.1f} | {x['paired_median_ms']:.1f} /"
                f" {x['paired_p95_ms']:.1f} | {x['spec_median_limit_ms']:.1f} /"
                f" {x['spec_p95_limit_ms']:.1f} | {aa} |"
                f" {x['median_limit_ms']:.1f} / {x['p95_limit_ms']:.1f} |"
                f" {_yes(x['pass'])} |")
        out += ["", f"Latency verdict: {_yes(v['latency']['pass'])} (measured"
                " blocks only; each case's warmup block is recorded apart)."]
        warm = [(f"{kind}:{band}", d["warmup_verdict_rtt"])
                for kind, by_band in (r.get("resident") or {}).get(
                    "latency", {}).items()
                for band, d in by_band.items() if d["warmup_verdict_rtt"]]
        if warm:
            out += ["", "Warmup blocks (a process's first request for an"
                    " input; informational, not part of the verdict):", "",
                    "| band | pairs | paired median ms | paired p95 ms |",
                    "|---|---|---|---|"]
            out += [f"| {name} | {w['pairs']} | {w['paired_median_ms']:.1f} |"
                    f" {w['paired_p95_ms']:.1f} |" for name, w in warm]
        out.append("")
    if v.get("rig_validity"):
        rv = v["rig_validity"]
        out.append(f"Rig validity (paired median in every band):"
                   f" {_yes(rv['pass'])}; failing bands"
                   f" {rv['failing_bands']}; p95-failing bands"
                   f" {rv['p95_failing_bands']}.")
    if v.get("back_to_back_gap"):
        g = v["back_to_back_gap"]
        aa = "n/a" if g["aa_median_ms"] is None \
            else f"{g['aa_median_ms']:.1f} ms"
        out.append(f"Back-to-back gap: paired median"
                   f" {g['paired_median_ms']:.1f} ms (max"
                   f" {g['paired_max_ms']:.1f}) against an effective limit of"
                   f" {g['limit_ms']:.1f} ms (spec {g['spec_limit_ms']:.0f}"
                   f" ms, A/A {aa}): {_yes(g['pass'])}.")
    if v.get("identity"):
        out.append(f"Identity A against B: {_yes(v['identity']['pass'])};"
                   f" mismatches {v['identity']['mismatches']}; chunker ran:"
                   f" {v['identity']['chunker_ran']}.")
    j = r.get("judgement")
    if j:
        out += ["", "## Go / no-go", "", f"- {j['ticket_02']['line']}",
                f"- {j['ticket_03']['line']}"]
        if j.get("ticket_03_observation"):
            out.append(f"- {j['ticket_03_observation']}")
        out += [f"- {j['loader']}", f"- {j['residency']}"]
    return "\n".join(out) + "\n"


# ---- the run -------------------------------------------------------------------------------------------

DEFAULT_EVIDENCE_ROOT = pathlib.Path.home() / "Library" / \
    "Application Support" / "LocalFlow" / "v2-evidence" / "footprint"
# One lock for every worktree, beside the evidence it protects.
DEFAULT_LOCK = DEFAULT_EVIDENCE_ROOT / "measure.lock"
PHASES = ("footprint", "bursts", "first", "resident")


def locate_models(identity):
    from huggingface_hub import snapshot_download
    out = {}
    for key, ident in (("asr", identity["asr_model"]),
                       ("cleanup", identity["cleanup_model"])):
        if pathlib.Path(ident).is_dir():
            snap = pathlib.Path(ident)
        else:
            try:
                snap = pathlib.Path(snapshot_download(
                    ident, local_files_only=True))
            except Exception:
                raise RigStop(f"the {key} model {ident} is not in the local"
                              " model cache")
        out[key] = {"snapshot": snap.name, "files": sorted(
            f.resolve() for f in snap.glob("*.safetensors"))}
    return out


def write_report(ctx, report):
    assert_content_free(report, ctx.seen | ctx.fixture_texts)
    tmp = ctx.run_dir / "report.json.part"
    tmp.write_text(json.dumps(report, indent=1))
    tmp.replace(ctx.run_dir / "report.json")


def execute(ctx, report, phases):
    runners = {"footprint": ("footprint", phase_footprint),
               "bursts": ("bursts", phase_bursts),
               "first": ("first_request", phase_first),
               "resident": ("resident", phase_resident)}
    for name in PHASES:
        if name not in phases:
            continue
        print(f"phase {name}", flush=True)
        key, fn = runners[name]
        report[key] = fn(ctx)
        report["rig"]["phases"].append(name)
        write_report(ctx, report)


def finish(ctx, report):
    pid = ctx.installed_pid
    env = report["environment"]
    env["power_after"] = power_state()
    env["thermal_after"] = thermal_state()
    after = installed_worker_cpu(pid)
    env["installed_worker"].update({
        "cpu_s_after": after,
        "cpu_s_delta": None if after is None
        or env["installed_worker"]["cpu_s_before"] is None
        else round(after - env["installed_worker"]["cpu_s_before"], 2),
        "pid_after": ctx.installed_pid_now()})
    report["verdicts"] = assemble_verdicts(report)
    report["judgement"] = judgement(report)
    report["rig"].update({"complete": True, "finished_at": now_et()})
    write_report(ctx, report)
    (ctx.run_dir / "SUMMARY.md").write_text(render_summary(report))


def parse_args(argv):
    ap = argparse.ArgumentParser(prog="footprint_rig")
    ap.add_argument("--code-root-a", required=True)
    ap.add_argument("--code-root-b")
    ap.add_argument("--mode", choices=("early", "shipping"), default="early")
    ap.add_argument("--phases", default=",".join(PHASES))
    ap.add_argument("--run-id")
    ap.add_argument("--evidence-root", default=str(DEFAULT_EVIDENCE_ROOT))
    ap.add_argument("--corpus-dir")
    ap.add_argument("--lock", default=str(DEFAULT_LOCK))
    ap.add_argument("--aa-report", help="a finished A/A report whose paired"
                    " statistics set each limit's noise floor")
    ap.add_argument("--python", default=sys.executable)
    ap.add_argument("--evict-pool", default=str(
        pathlib.Path.home() / "Documents" / "LocalAI" / "models"))
    ap.add_argument("--prepare-corpus", action="store_true",
                    help="synthesize the speech corpus once and exit")
    for name in ("warm", "cold", "burst", "first", "gap"):
        ap.add_argument(f"--{name}-spawns" if name in ("warm", "cold",
                                                      "burst")
                        else f"--{name}-pairs", type=int)
    return ap.parse_args(argv)


def build_context(args, run_dir, corpus_dir, run_id):
    aa = load_aa_report(args.aa_report) if args.aa_report else None
    roots = {"A": pathlib.Path(args.code_root_a).resolve()}
    roots["B"] = pathlib.Path(args.code_root_b).resolve() \
        if args.code_root_b else roots["A"]
    rows = parse_ps(_tool_text(["ps", "-axo", "pid=,ppid=,command="]))
    installed, strays = classify_workers(rows)
    if strays:
        raise RigStop("another worker or mlx process is running (pids"
                      f" {strays}); a measurement needs a quiet machine")
    identities = {side: resolve_model_identity(root, args.python)
                  for side, root in roots.items()}
    if identities["A"] != identities["B"]:
        raise RigStop("the two code roots resolve different models;"
                      " a comparison would not be like for like")
    identity = identities["A"]
    models = locate_models(identity)
    manifest_path = ROOT / "docs" / "v2" / "baseline" / "manifest.json"
    pin = json.loads(manifest_path.read_text()) \
        if manifest_path.exists() else {}
    revisions = revision_record(pin, {k: m["snapshot"]
                                      for k, m in models.items()})
    corpus_manifest = corpus_dir / "manifest.json"
    if not corpus_manifest.exists():
        raise RigStop(f"no corpus at {corpus_dir}; run with"
                      " --prepare-corpus first")
    manifest = json.loads(corpus_manifest.read_text())
    verify_corpus(manifest, corpus_dir)
    cases = load_cleanup_cases(ROOT)
    clips = [(c["name"], c["duration_s"]) for c in manifest["clips"]
             if c["name"] not in IDENTITY_CLIPS]
    bands = {"cleanup": freeze_bands(
        [(cid, c["words"]) for cid, c in cases.items()], CLEANUP_BANDS),
        "asr": freeze_bands(clips, ASR_BANDS)}
    mode_counts = dict(MODE_COUNTS[args.mode])
    for key, value in (("warm", args.warm_spawns), ("cold", args.cold_spawns),
                       ("burst", args.burst_spawns),
                       ("first", args.first_pairs), ("gap", args.gap_pairs)):
        if value is not None:
            mode_counts[key] = value
    tokens = [i.rsplit("/", 1)[-1] for i in identity.values()]
    ctx = types.SimpleNamespace(
        run_id=run_id, mode=args.mode, counts=mode_counts, aa=aa, roots=roots, identity=identity,
        revisions=revisions, cases=cases, bands=bands, run_dir=run_dir,
        scratch=run_dir / "scratch", seen=set(), thermal_events=[],
        fixture_texts={c["text"] for c in cases.values()},
        weights=[f for m in models.values() for f in m["files"]],
        evict_pool=args.evict_pool, protect_tokens=tokens,
        purge_allowed=True, installed_pid=installed,
        installed_pid_now=lambda: classify_workers(parse_ps(_tool_text(
            ["ps", "-axo", "pid=,ppid=,command="])))[0],
        manifest=manifest)
    ctx.make_session = lambda side, diag: WorkerSession(
        ctx.roots[side], corpus_dir, identity, python=args.python,
        memory_diag=diag)
    return ctx


def measure(ctx, phases, started):
    """Everything after the context is built: freeze the bands on disk,
    run the phases, write the report and the summary."""
    run_dir = ctx.run_dir
    bands = {"cleanup": ctx.bands["cleanup"], "asr": ctx.bands["asr"],
             "counts": {k: band_counts(ctx.bands[k])
                        for k in ("cleanup", "asr")},
             "short": {k: short_bands(ctx.bands[k], SHIPPING_CASES)
                       for k in ("cleanup", "asr")}}
    bands["digest"] = digest_json({k: ctx.bands[k]
                                   for k in ("cleanup", "asr")})
    # Frozen first: the bands and every case's membership are on disk
    # before any comparison runs.
    (run_dir / "bands.json").write_text(json.dumps(bands, indent=1))
    print("frozen bands (case counts):")
    for kind in ("cleanup", "asr"):
        for band, n in bands["counts"][kind].items():
            note = " (short of the shipping-claim count)" \
                if band in bands["short"][kind] else ""
            print(f"  {kind} {band}: {n}{note}")
        print(f"  {kind} unbanded: {len(ctx.bands[kind]['unbanded'])}")
    report = {"rig": {"run_id": ctx.run_id, "mode": ctx.mode,
                      "started_at": started, "finished_at": None,
                      "complete": False, "phases": [],
                      "counts": ctx.counts,
                      "aa_report": {"sha256": ctx.aa["sha256"],
                                    "run_id": ctx.aa["run_id"]}
                      if ctx.aa else None},
              "environment": environment(ctx), "bands": bands,
              "corpus": {"manifest_sha256": digest_json(ctx.manifest),
                         "clips": [{k: c[k] for k in (
                             "name", "sha256", "duration_s", "band")}
                             for c in ctx.manifest["clips"]]}}
    write_report(ctx, report)
    try:
        execute(ctx, report, phases)
        finish(ctx, report)
    finally:
        shutil.rmtree(ctx.scratch, ignore_errors=True)
    v = report["verdicts"]
    print((run_dir / "SUMMARY.md").read_text())
    print(f"report: {run_dir / 'report.json'}")
    bad = (v.get("rig_validity") and not v["rig_validity"]["pass"]) \
        or (v.get("identity") and not v["identity"]["pass"])
    return 1 if bad else 0


def run(args):
    evidence_root = pathlib.Path(args.evidence_root)
    corpus_dir = pathlib.Path(args.corpus_dir or evidence_root / "corpus")
    phases = [p for p in args.phases.split(",") if p]
    unknown = [p for p in phases if p not in PHASES]
    if unknown:
        raise RigStop(f"unknown phase(s) {unknown}")
    lock_fd = acquire_lock(args.lock)
    try:
        started = now_et()
        run_id = args.run_id or datetime.datetime.now(_EASTERN).strftime(
            "%Y%m%d-%H%M%S") + "-" + args.mode
        run_dir = evidence_root / run_id
        run_dir.mkdir(parents=True, exist_ok=False)
        (run_dir / "scratch").mkdir()
        return measure(build_context(args, run_dir, corpus_dir, run_id),
                       phases, started)
    finally:
        os.close(lock_fd)


def main(argv=None):
    args = parse_args(argv)
    try:
        if args.prepare_corpus:
            corpus_dir = pathlib.Path(args.corpus_dir or pathlib.Path(
                args.evidence_root) / "corpus")
            if (corpus_dir / "manifest.json").exists():
                verify_corpus(json.loads(
                    (corpus_dir / "manifest.json").read_text()), corpus_dir)
                print(f"corpus at {corpus_dir} exists and verifies")
                return 0
            manifest = build_corpus(corpus_dir, SHIPPING_CASES)
            print(f"corpus written: {len(manifest['clips'])} clips")
            return 0
        return run(args)
    except RigStop as e:
        print(f"STOP: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
