"""M12 benchmark: Scratchpad writing on the reference Mac, measured only
after every measured component is proven to have done its work
(M12-AUDIT-25). Synthetic fixtures in a temporary store; no model, no
network, no AppKit.

Components (each timed separately):

- ``note_open_10k`` — ``open_note`` of a note of EXACTLY 10,000
  whitespace words whose chain holds 201 revisions (the 200-header
  boundary: 200 headers + the truncated flag); ``note_open_cold`` is the
  first such open after the store opens (one sample);
- ``version_headers_200`` / ``version_headers_201`` — ``open_note`` of
  small notes with exactly 200 and 201 revisions (header loading);
- ``search_200_notes`` — ``search`` over exactly 200 live notes whose
  known matching subset (20 ids) is fixed by the fixture;
- ``autosave_commit`` — one typed generation committed by the model's
  flush (queue wait and the writer op are reported apart);
- ``snapshot_explicit`` — the same through the explicit trigger;
- ``restore`` — ``NoteStore.restore`` of the first revision;
- ``dirty_note_switch`` — the bounded outgoing save of a dirty note plus
  loading and binding the next one (the editor's switch path, model
  level);
- ``dictated_ack`` / ``dictated_commit`` / ``dictated_confirmation`` —
  one attributed arrival: the UI acknowledgment (the buffer receipt on
  the calling thread), the commit (the flush), and the time until its
  receipt settles ``committed`` — three separate intervals;
- ``export_markdown`` / ``export_plain`` — a note with two referenced
  64 KiB image attachments exported to a fresh folder (payload copies
  included; optional evidence work excluded — no collector installed);
- ``autosave_commit_during_search`` — commits while a thread searches,
  with an independent overlap proof (interval timestamps).

Work validity (independent oracles from the fixture design, never from
the code under test): content hashes, word counts, header counts and
the truncated flag, the exact matching id set, committed revision
counts/origins/triggers/hashes, restored content, exported bytes, the
arrival's committed revision and span words, and the overlap count. Any
failure exits 3 (INVALID WORK) before a timing is accepted. Exit 0:
valid and within budget; exit 2: valid, budget missed.

Budgets (Spec S24/S20): warm 10k-word open p95 <= 200 ms; the
dictation UI acknowledgment p95 <= 50 ms. Everything else is recorded.

Test switches (the benchmark mutation check uses them):
  --noop COMPONENT      replace one component with a do-nothing stand-in
  --delay COMPONENT=MS  sleep inside that component's timed region

Usage: .venv/bin/python scripts/v2/benchmark_m12.py [--out DIR] [...]
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import pathlib
import platform
import re
import subprocess
import sys
import tempfile
import threading
import time

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from localflow.v2 import store as store_mod  # noqa: E402
from localflow.v2 import note_export  # noqa: E402
from localflow.v2.notes import (NoteStore, NotesEditorModel,  # noqa: E402
                                ORIGIN_DICTATED, ORIGIN_RESTORE,
                                ORIGIN_TYPED, TRIGGER_AUTOSAVE,
                                TRIGGER_EXPLICIT)

RUNS = 50
WARM = 5
BUDGET_OPEN_P95_MS = 200.0
BUDGET_ACK_P95_MS = 50.0
N_SEARCH = 200
MATCH_TOKEN = "zephyrmatch"
PAYLOAD = b"\x89PNG\r\n\x1a\n" + bytes(range(256)) * 256  # 64 KiB + 8

# EXACTLY 10,000 whitespace-separated words: 1,000 lines of 10 words.
WORD10K = "\n".join(
    f"benchmark filler word {i} for the scratchpad fixture line here"
    for i in range(1000))


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def pct(values, p):
    s = sorted(values)
    k = max(0, min(len(s) - 1, int(round(p / 100.0 * (len(s) - 1)))))
    return s[k]


def stats(samples):
    return {"p50_ms": round(pct(samples, 50), 4),
            "p95_ms": round(pct(samples, 95), 4),
            "p99_ms": round(pct(samples, 99), 4),
            "max_ms": round(max(samples), 4), "runs": len(samples)}


def validate_open(detail, *, words=10000, content_sha=None,
                  headers=200, truncated=True) -> bool:
    """The open did the work its label claims: the named content, its
    word count, and the populated version headers."""
    if not detail or not detail.get("revision"):
        return False
    rev = detail["revision"]
    if content_sha is not None and sha(rev.get("content") or "") \
            != content_sha:
        return False
    if len((rev.get("content") or "").split()) != words:
        return False
    vers = detail.get("versions") or []
    return len(vers) == headers \
        and bool(detail.get("versions_truncated")) == truncated \
        and len({v["revision_id"] for v in vers}) == headers


def environment(argv):
    def sh(*cmd):
        try:
            return subprocess.run(cmd, capture_output=True, text=True,
                                  timeout=10).stdout.strip()
        except Exception:
            return None
    power = sh("pmset", "-g", "batt") or ""
    shasum = sh("git", "-C", str(ROOT), "rev-parse", "HEAD")
    dirty = sh("git", "-C", str(ROOT), "status", "--porcelain",
               "--untracked-files=no")
    prod_dirty = sh("git", "-C", str(ROOT), "status", "--porcelain",
                    "--untracked-files=no", "--", "localflow")
    mem = sh("sysctl", "-n", "hw.memsize")
    # The interpreter relative to the repository (or its name alone): a
    # committed record never carries the home folder's path.
    exe = pathlib.Path(sys.executable)
    try:
        exe_label = str(exe.relative_to(ROOT))
    except ValueError:
        exe_label = exe.name
    return {
        "utc": dt.datetime.now(dt.timezone.utc).isoformat(
            timespec="seconds"),
        "code_sha": shasum, "tracked_files_modified": bool(dirty),
        "production_tree_modified": bool(prod_dirty),
        "mac_model": sh("sysctl", "-n", "hw.model"),
        "chip": sh("sysctl", "-n", "machdep.cpu.brand_string"),
        "cores": os.cpu_count(),
        "memory_gib": round(int(mem) / 2 ** 30, 1) if mem else None,
        "macos": f"{platform.mac_ver()[0]} ({sh('sw_vers', '-buildVersion')})",
        "python": sys.version.split()[0], "executable": exe_label,
        "power_source": (power.splitlines()[0].split("'")[1]
                         if "'" in power else None),
        "load_avg_1_5_15": [round(x, 2) for x in os.getloadavg()],
        "command": " ".join([pathlib.Path(sys.executable).name,
                             "scripts/v2/benchmark_m12.py", *argv]),
    }


class WriterTimes:
    """Benchmark-local instrumentation of the store's writer queue: for
    each op, when it was queued, when the writer started it and when
    it finished (the commit follows in the same writer turn)."""

    def __init__(self, store):
        self.records = []
        real = store._submit

        def submit(fn, wait=False, timeout=15.0):
            rec = {"queued": time.perf_counter()}

            def timed():
                rec["start"] = time.perf_counter()
                try:
                    return fn()
                finally:
                    rec["end"] = time.perf_counter()
            out = real(timed, wait=wait, timeout=timeout)
            rec["returned"] = time.perf_counter()
            self.records.append(rec)
            return out
        store._submit = submit


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None)
    ap.add_argument("--noop", default=None)
    ap.add_argument("--delay", default=None)
    ap.add_argument("--runs", type=int, default=RUNS)
    args = ap.parse_args(argv)
    runs = args.runs
    noop = args.noop
    delay_comp, delay_s = None, 0.0
    if args.delay:
        delay_comp, ms = args.delay.split("=")
        delay_s = float(ms) / 1000.0

    def pause(comp):
        if comp == delay_comp and delay_s:
            time.sleep(delay_s)

    tmp = tempfile.TemporaryDirectory(prefix="lf-m12-bench-")
    root = pathlib.Path(tmp.name)
    validity = {}
    timing = {}

    def check(name, cond, detail):
        validity[name] = {"valid": bool(cond), "detail": detail}

    try:
        assert len(WORD10K.split()) == 10000
        s = store_mod.Store(root / "main" / "v2.db")
        ns = NoteStore(s)
        # ---- fixtures ------------------------------------------------------
        # 201 revisions of the 10,000-word text: the open materializes
        # the content plus exactly 200 headers and the truncated flag.
        big = ns.create_note(WORD10K)["note_id"]
        for _ in range(200):
            ns.append_revision(big, WORD10K, origin=ORIGIN_TYPED,
                               trigger=TRIGGER_AUTOSAVE)
        heads = {}
        for n_revs in (200, 201):
            nid = ns.create_note("header fixture 0")["note_id"]
            for i in range(1, n_revs):
                ns.append_revision(nid, f"header fixture {i}",
                                   origin=ORIGIN_TYPED,
                                   trigger=TRIGGER_AUTOSAVE)
            heads[n_revs] = nid
        # ---- components ----------------------------------------------------
        def c_open():
            pause("note_open_10k")
            return ns.open_note(big)

        def c_headers(n):
            def run():
                pause(f"version_headers_{n}")
                return ns.open_note(heads[n])
            return run

        components = {"note_open_10k": c_open,
                      "version_headers_200": c_headers(200),
                      "version_headers_201": c_headers(201)}
        if noop == "open":
            for k in list(components):
                components[k] = (lambda: None)
        elif noop and noop not in ("search", "save", "export",
                                   "dictation", "restore", "switch"):
            raise SystemExit(f"unknown component: {noop}")
        # Cold: the first open after a fresh store open.
        s.close()
        s = store_mod.Store(root / "main" / "v2.db")
        ns.store = s
        t0 = time.perf_counter()
        cold = components["note_open_10k"]()
        timing["note_open_cold"] = {
            "ms": round((time.perf_counter() - t0) * 1000.0, 4),
            "runs": 1}
        check("note_open_cold", validate_open(cold,
                                              content_sha=sha(WORD10K)),
              "first open after the store opened: 10,000 words, 200"
              " headers, truncated")
        for name in ("note_open_10k", "version_headers_200",
                     "version_headers_201"):
            fn = components[name]
            for _ in range(WARM):
                fn()
            samples, last = [], None
            for _ in range(runs):
                t0 = time.perf_counter()
                last = fn()
                samples.append((time.perf_counter() - t0) * 1000.0)
            timing[name] = stats(samples)
            if name == "note_open_10k":
                check(name, validate_open(last, content_sha=sha(WORD10K)),
                      "content hash, 10,000 words, 200 distinct headers,"
                      " truncated flag")
            else:
                n = int(name.rsplit("_", 1)[1])
                check(name, validate_open(
                    last, words=3, headers=200, truncated=(n == 201)),
                    f"{n} revisions: 200 headers,"
                    f" truncated={n == 201}")
        # ---- search over exactly 200 live notes ----------------------------
        s2 = store_mod.Store(root / "search" / "v2.db")
        ns2 = NoteStore(s2)
        expected = set()
        for i in range(N_SEARCH):
            tok = f" {MATCH_TOKEN}" if i % 10 == 3 else ""
            nid = ns2.create_note(f"search cohort note {i} words{tok}")[
                "note_id"]
            if tok:
                expected.add(nid)
        live = s2.submit(lambda db: db.execute(
            "SELECT COUNT(*) FROM notes").fetchone()[0])

        def c_search():
            pause("search_200_notes")
            if noop == "search":
                return []
            return ns2.search(MATCH_TOKEN)
        for _ in range(WARM):
            c_search()
        samples, got = [], None
        for _ in range(runs):
            t0 = time.perf_counter()
            got = c_search()
            samples.append((time.perf_counter() - t0) * 1000.0)
        timing["search_200_notes"] = stats(samples)
        check("search_200_notes", live == N_SEARCH and {
            r["note_id"] for r in (got or [])} == expected
              and len(expected) == 20,
              f"{live} live notes; {len(got or [])} matches of the"
              f" fixed {len(expected)}")
        # ---- autosave / snapshot commits, queue vs op ----------------------
        wt = WriterTimes(s2)
        tgt = ns2.create_note("commit target")
        model = NotesEditorModel(tgt["note_id"], tgt["revision"],
                                 "commit target",
                                 on_dirty=lambda _n: None)

        def commit(i, trigger, comp):
            model.edit(f"commit target generation {i} {trigger}")
            t0 = time.perf_counter()
            pause(comp)
            if noop == "save":
                return {"outcome": "flushed"}
            out = model.flush(ns2, trigger=trigger)
            return out, (time.perf_counter() - t0) * 1000.0

        for label, trigger in (("autosave_commit", TRIGGER_AUTOSAVE),
                               ("snapshot_explicit", TRIGGER_EXPLICIT)):
            before = s2.submit(lambda db, n=tgt["note_id"]: db.execute(
                "SELECT COUNT(*) FROM note_revisions WHERE note_id=?",
                (n,)).fetchone()[0])
            wt.records.clear()
            samples = []
            for i in range(runs):
                r = commit(f"{label}-{i}", trigger, label)
                if isinstance(r, tuple):
                    samples.append(r[1])
                else:
                    samples.append(0.0)
            recs = [r for r in wt.records if "start" in r]
            rows = s2.submit(lambda db, n=tgt["note_id"]: db.execute(
                "SELECT trigger_kind, content_sha256 FROM note_revisions"
                " WHERE note_id=? ORDER BY rowid", (n,)).fetchall())
            new = rows[before:]
            timing[label] = stats(samples)
            timing[label + "_queue_wait"] = stats(
                [(r["start"] - r["queued"]) * 1000.0 for r in recs]
                or [0.0])
            timing[label + "_writer_op"] = stats(
                [(r["end"] - r["start"]) * 1000.0 for r in recs] or [0.0])
            check(label, len(new) == runs
                  and all(t == trigger for t, _h in new)
                  and len({h for _t, h in new}) == runs,
                  f"{len(new)} committed revisions (expected {runs}),"
                  f" trigger {trigger}, distinct hashes")
        # ---- restore ------------------------------------------------------
        first = s2.submit(lambda db, n=tgt["note_id"]: db.execute(
            "SELECT revision_id, content_text FROM note_revisions WHERE"
            " note_id=? ORDER BY rowid LIMIT 1", (n,)).fetchone())
        samples, last = [], None
        for _ in range(runs):
            t0 = time.perf_counter()
            pause("restore")
            last = None if noop == "restore" else ns2.restore(
                tgt["note_id"], first[0])
            samples.append((time.perf_counter() - t0) * 1000.0)
        timing["restore"] = stats(samples)
        cur = ns2.open_note(tgt["note_id"])["revision"]
        check("restore", last is not None and last["origin"] ==
              ORIGIN_RESTORE and cur["content"] == first[1],
              "the newest revision is a restore holding the first"
              " revision's exact content")
        # ---- dirty note switch --------------------------------------------
        a = ns2.create_note("switch outgoing")
        b = ns2.create_note("switch incoming")
        samples, ok = [], True
        for i in range(runs):
            out_model = NotesEditorModel(a["note_id"], None, "switch outgoing",
                                         on_dirty=lambda _n: None)
            out_model.edit(f"switch outgoing edit {i}")
            t0 = time.perf_counter()
            pause("dirty_note_switch")
            if noop == "switch":
                incoming = None
            else:
                out_model.flush(ns2, timeout=0.25)
                detail = ns2.open_note(b["note_id"])
                incoming = NotesEditorModel(
                    b["note_id"], detail["revision"]["revision_id"],
                    detail["revision"]["content"])
            samples.append((time.perf_counter() - t0) * 1000.0)
            ok = ok and incoming is not None \
                and incoming.content == "switch incoming" \
                and ns2.open_note(a["note_id"])["revision"]["content"] \
                == f"switch outgoing edit {i}"
        timing["dirty_note_switch"] = stats(samples)
        check("dirty_note_switch", ok,
              "every outgoing edit committed; the incoming buffer is the"
              " next note's content")
        # ---- dictated arrival: ack / commit / confirmation ------------------
        d = ns2.create_note("dictation base")
        dm = NotesEditorModel(d["note_id"], d["revision"], "dictation base")
        # The acknowledgment includes what the editor really does on a
        # clean note: queue the unsaved-tail marker write (conditional,
        # non-blocking) — exactly ScratchpadEditor._mark_dirty.
        dm.on_dirty = lambda nid: ns2.mark_dirty(
            nid, only_if=lambda: dm.dirty, wait=False)
        acks, commits, confirms, good = [], [], [], True
        for i in range(runs):
            word = f"spoken{i}"
            settled = {}
            t0 = time.perf_counter()
            pause("dictated_ack")
            arrival = None if noop == "dictation" else dm.insert(
                f" {word}", at=len(dm.content), origin=ORIGIN_DICTATED,
                source_job_id=f"job-bench-{i}")
            t1 = time.perf_counter()
            if arrival is not None:
                arrival.on_settled(
                    lambda a, box=settled: box.setdefault(
                        "t", time.perf_counter()))
                pause("dictated_commit")
                dm.flush(ns2)
            t2 = time.perf_counter()
            acks.append((t1 - t0) * 1000.0)
            commits.append((t2 - t1) * 1000.0)
            confirms.append(((settled.get("t") or t2) - t0) * 1000.0)
            if arrival is None or arrival.outcome != "committed":
                good = False
                continue
            row = s2.submit(lambda db, r=arrival.revision_id: db.execute(
                "SELECT content_text, origin, source_job_id, spans_json"
                " FROM note_revisions WHERE revision_id=?",
                (r,)).fetchone())
            words = row[0].split()
            spans = json.loads(row[3])
            last_span = spans[-1] if spans else None
            good = good and row[1] == ORIGIN_DICTATED \
                and row[2] == f"job-bench-{i}" and last_span is not None \
                and words[last_span[0]:last_span[1]] == [word]
        timing["dictated_ack"] = stats(acks)
        timing["dictated_commit"] = stats(commits)
        timing["dictated_confirmation"] = stats(confirms)
        check("dictated_save", good,
              "each arrival's receipt settled committed on a dictated"
              " revision of its own job whose span is exactly its word")
        # ---- export (Markdown with two payload copies, plain) ---------------
        e = ns2.create_note("export")
        m1 = ns2.add_attachment(e["note_id"], PAYLOAD, "image/png", "a.png")
        m2 = ns2.add_attachment(e["note_id"], PAYLOAD[::-1], "image/png",
                                "b.png")
        ns2.append_revision(
            e["note_id"], f"# Export\n\n- one\n- two\n\n{m1['marker']}\n\n"
            f"{m2['marker']}\n", origin=ORIGIN_TYPED,
            trigger=TRIGGER_AUTOSAVE)
        note = ns2.open_note(e["note_id"])
        for fmt in ("markdown", "plain"):
            samples, ok = [], True
            for i in range(runs):
                dest = root / "exports" / f"{fmt}-{i}"
                dest.mkdir(parents=True)
                path = dest / ("n.md" if fmt == "markdown" else "n.txt")
                t0 = time.perf_counter()
                pause(f"export_{fmt}")
                rep = {"ok": True} if noop == "export" else \
                    note_export.write_export(path, note, ns2, fmt)
                samples.append((time.perf_counter() - t0) * 1000.0)
                if not (rep.get("ok") and path.is_file()):
                    ok = False
                    continue
                if fmt == "markdown":
                    names = re.findall(r"!\[[^\]]*\]\(([^)]+)\)",
                                       path.read_text())
                    ok = ok and sorted((dest / n).read_bytes()
                                       for n in names) == sorted(
                        [PAYLOAD, PAYLOAD[::-1]])
                else:
                    ok = ok and len(rep.get("unsupported") or []) == 2
            timing[f"export_{fmt}"] = stats(samples)
            check(f"export_{fmt}", ok,
                  "markdown: both payload copies byte-identical and"
                  " referenced; plain: both images reported"
                  if fmt == "markdown" else
                  "the file written; both image markers reported")
        # ---- commits during searches, with an overlap proof -----------------
        stop = threading.Event()
        search_iv = []

        def searcher():
            while not stop.is_set():
                t0 = time.perf_counter()
                ns2.search(MATCH_TOKEN)
                search_iv.append((t0, time.perf_counter()))
        th = threading.Thread(target=searcher, daemon=True)
        th.start()
        samples, commit_iv = [], []
        try:
            for i in range(runs):
                r = commit(f"overlap-{i}", TRIGGER_AUTOSAVE,
                           "autosave_commit_during_search")
                ms = r[1] if isinstance(r, tuple) else 0.0
                t1 = time.perf_counter()
                commit_iv.append((t1 - ms / 1000.0, t1))
                samples.append(ms)
        finally:
            stop.set()
            th.join(5)
        overlaps = sum(1 for c0, c1 in commit_iv
                       if any(s0 < c1 and s1 > c0
                              for s0, s1 in search_iv))
        timing["autosave_commit_during_search"] = stats(samples)
        check("autosave_commit_during_search",
              overlaps >= runs // 2 and len(search_iv) >= runs,
              f"{overlaps}/{runs} commits overlapped a search interval;"
              f" {len(search_iv)} searches ran")
        s2.close()
        s.close()
        invalid = sorted(k for k, v in validity.items() if not v["valid"])
        result = {"kind": "m12-benchmark", "synthetic": True,
                  "environment": environment(argv),
                  "fixtures": {"note_words": 10000,
                               "note_revisions": 201,
                               "search_live_notes": N_SEARCH,
                               "search_expected_matches": 20,
                               "export_attachments": 2,
                               "export_attachment_bytes": len(PAYLOAD),
                               "runs": runs, "warm_runs": WARM,
                               "evidence_collector": "not installed"
                                                     " (excluded)"},
                  "validity": validity}
        if invalid:
            result.update({"verdict": "INVALID_WORK",
                           "invalid_components": invalid,
                           "qualified": False})
            _emit(result, args.out)
            return 3
        within = timing["note_open_10k"]["p95_ms"] <= BUDGET_OPEN_P95_MS \
            and timing["dictated_ack"]["p95_ms"] <= BUDGET_ACK_P95_MS
        result.update({
            "timing": timing,
            "budget": {"note_open_10k_p95_ms": BUDGET_OPEN_P95_MS,
                       "dictated_ack_p95_ms": BUDGET_ACK_P95_MS,
                       "within_budget": within,
                       "note": "UI acknowledgment (dictated_ack) is the"
                               " buffer receipt; commit and confirmation"
                               " are recorded separately and are not"
                               " part of the acknowledgment budget"},
            "qualified": within,
            "verdict": "VALID_WITHIN_BUDGET" if within
            else "VALID_BUDGET_MISSED"})
        _emit(result, args.out)
        return 0 if within else 2
    finally:
        tmp.cleanup()


def _emit(result, out):
    text = json.dumps(result, indent=1, sort_keys=True)
    print(text)
    if out:
        p = pathlib.Path(out)
        p.mkdir(parents=True, exist_ok=True)
        (p / "m12.json").write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
