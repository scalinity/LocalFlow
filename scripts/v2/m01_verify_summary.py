"""M01: summarize one piece of verification evidence for the runbook
(docs/v2/VERIFICATION.html, checks M01-V002..M01-V009).

Prints the fields a human needs to compare against the runbook's expected
values, then evaluates the mechanical invariants of that evidence kind:

    OK    <invariant>
    CHECK <invariant>   <- violated: see the check's failure interpretation

It never prints transcript text or configuration payloads (the inputs it
reads carry none). Exit 0 when every invariant holds, 1 otherwise, 2 on
unreadable input. An invariant holding is not the same as a check passing:
the runbook also asks for comparisons only a human can make.

Usage:
    python scripts/v2/m01_verify_summary.py manifest PATH
    python scripts/v2/m01_verify_summary.py snapshot RUN_DIR
    python scripts/v2/m01_verify_summary.py parse PATH
    python scripts/v2/m01_verify_summary.py probe PATH
"""

import json
import os
import pathlib
import stat
import sys

# E02 audited aggregates for the historical artifact (sha256 51e8ee70…).
E02_EXPECTED = {
    "pairs": 749, "timed_pairs": 477, "audio_records": 498,
    "cohorts.loaded": 476, "cohorts.unavailable": 272, "cohorts.unknown": 1,
    "counts.metal_shared_event_failures": 3, "counts.unpaired_timing": 16,
    "counts.empty_messages": 29, "counts.cleanup_load_failure": 21,
    "counts.cleanup_load_success": 27, "zero_voiced": 10,
    "overflow_positive": 0, "sum_stt": 176.6, "sum_cleanup": 629.6,
}


class Out:
    def __init__(self):
        self.violations = 0

    def fact(self, label, value):
        print(f"      {label}: {value}")

    def inv(self, ok, text):
        print(f"{'OK   ' if ok else 'CHECK'} {text}")
        if not ok:
            self.violations += 1


def dig(obj, dotted, default=None):
    for part in dotted.split("."):
        if not isinstance(obj, dict) or part not in obj:
            return default
        obj = obj[part]
    return obj


def manifest(m, o):
    g = m["git"]
    o.fact("described checkout", dig(m, "generator.described_checkout"))
    o.fact("HEAD", g.get("head_commit") or f"null ({g.get('head_reason')})")
    o.fact("clean_tree", g.get("clean_tree"))
    o.fact("dirty entries", len(g.get("dirty_entries") or []))
    o.fact("dirty_digest", g.get("dirty_digest"))
    o.inv(g.get("head_commit") is not None, "Git HEAD resolved")
    o.inv((g.get("dirty_digest") is None) == (g.get("clean_tree") is True),
          "dirty_digest is null exactly when the tree is clean")
    b = m["installed_bundle"]
    o.fact("bundle installed", b.get("installed"))
    if b.get("installed"):
        o.fact("bundle identity", b.get("identity"))
        o.fact("embedded == Git HEAD", b.get("embedded_code_matches_git_head"))
        o.fact("embedded == worktree", b.get("embedded_code_matches_worktree"))
        for which in ("divergence_from_head", "divergence_from_worktree"):
            d = b.get(which) or {}
            o.fact(which, {k: len(v) for k, v in d.items()})
            flag = ("embedded_code_matches_git_head" if which.endswith("head")
                    else "embedded_code_matches_worktree")
            if b.get(flag) is not None:
                o.inv(b[flag] == (not any(d.values())),
                      f"{flag} agrees with {which}")
        o.fact("launcher sha256", dig(b, "launcher.sha256"))
    for ctx, rec in m["effective_configuration"]["contexts"].items():
        o.fact(f"[{ctx}] effective source", rec.get("effective_source"))
        o.fact(f"[{ctx}] winner", rec.get("winner"))
        o.fact(f"[{ctx}] values", rec.get("effective_values"))
        o.fact(f"[{ctx}] env LOCALFLOW_CONFIG", rec.get("env_LOCALFLOW_CONFIG"))
        o.fact(f"[{ctx}] overridden keys", rec.get("overridden_keys"))
        models = m["models"].get(ctx) or {}
        for role, key in (("asr", "model"), ("cleanup", "cleanup_model")):
            mr = models.get(role) or {}
            cache = mr.get("cache") or {}
            res = cache.get("resolution") or {}
            o.fact(f"[{ctx}] {role} configured", mr.get("configured_id"))
            o.fact(f"[{ctx}] {role} hub", f"{cache.get('hub_root')} "
                   f"({cache.get('hub_root_source')})")
            o.fact(f"[{ctx}] {role} refs/main", cache.get("refs_main"))
            for s in cache.get("snapshots") or []:
                o.fact(f"[{ctx}] {role} snapshot {s['revision']}",
                       f"digest={s.get('snapshot_digest')} "
                       f"usable={s.get('usable_by_stt_rule')} "
                       f"files={len(s.get('files_sha256') or {})} "
                       f"dangling={s.get('dangling_files')}")
            o.fact(f"[{ctx}] {role} resolution", res)
            if "secondary_cache" in mr:
                o.fact(f"[{ctx}] {role} LocalAI copy same digest",
                       mr["secondary_cache"].get(
                           "same_snapshot_digest_as_effective_cache"))
            vals = rec.get("effective_values") or {}
            o.inv(mr.get("configured_id") == vals.get(key),
                  f"[{ctx}] {role} model matches the effective config")
            o.inv(mr.get("loaded") is None,
                  f"[{ctx}] {role} never claims a loaded checkpoint")
            o.inv(res.get("stt_model_cached") is True,
                  f"[{ctx}] {role} usable snapshot in the resolved cache")
    for it in m["runtime"]["interpreters"]:
        o.fact(f"interpreter {it['label']}",
               f"{it.get('python')} {it.get('realpath')} "
               f"{it.get('packages') or it.get('reason')}")
    o.fact("hardware", m["runtime"]["hardware"])
    r = m.get("readiness") or {}
    o.fact("current session (event log)", dig(r, "current_session.session")
           or dig(r, "current_session.reason"))
    o.fact("legacy log last segment", dig(r, "legacy_log_last_segment.last_segment")
           or dig(r, "legacy_log_last_segment.reason"))
    o.fact("processes", dig(r, "processes.processes"))


def snapshot(run_dir, o):
    run_dir = pathlib.Path(run_dir)
    m = json.loads((run_dir / "snapshot-manifest.json").read_text())
    o.fact("run", m.get("run_id"))
    o.fact("outcome", m.get("outcome"))
    o.fact("evidence root", m.get("evidence_root"))
    for e in m["entries"]:
        o.fact(f"{e['kind']} {pathlib.Path(e['source']).name}",
               f"{e['status']} bytes={e.get('bytes')} note={e.get('note')}")
        if e["kind"] == "sqlite_backup" and e["status"] != "missing":
            o.fact("  sqlite companions", e.get("companions"))
            o.fact("  backup integrity_check", e.get("snapshot_integrity_check"))
    o.inv(m.get("outcome") == "complete", "run outcome is complete")
    o.inv(all(e["status"] in ("unchanged", "appended_during_snapshot",
                              "verified", "not_present")
              for e in m["entries"]), "no source changed, errored or missing")
    mode = stat.S_IMODE(os.stat(run_dir).st_mode)
    o.inv(mode == 0o700, f"run directory mode {oct(mode)} == 0o700")
    loose = [p.name for p in run_dir.iterdir()
             if stat.S_IMODE(os.lstat(p).st_mode) != 0o600]
    o.inv(not loose, f"every evidence file is 0600 {loose or ''}")
    uid = os.stat(run_dir).st_uid
    o.inv(uid == os.getuid(), "run directory owned by the current user")


def parse_report(r, o):
    src = r.get("source") or {}
    o.fact("source sha256", src.get("sha256"))
    o.fact("decode", src.get("decode"))
    o.fact("parser", r.get("parser"))
    o.inv(src.get("matches_audited_artifact") is True,
          "report is bound to the audited artifact hash")
    for k, want in E02_EXPECTED.items():
        got = dig(r, k)
        o.inv(got == want, f"{k} = {got} (E02: {want})")
    for k in ("counts.timing_detached_after_posted_insertion",
              "counts.malformed_timing_records", "eof_incomplete_pairs",
              "decode_uncertain_pairs"):
        o.fact(k, dig(r, k))
    o.fact("heuristics (lexical, boundaries)",
           (r.get("loaded_lexical_changes"), r.get("loaded_new_sentence_breaks")))
    for w in r.get("notable_examples") or []:
        o.inv(w.get("located") is True, f"window {w['id']} located "
              f"(location only; semantic verification not performed)")


def probe(r, o):
    o.fact("run", r.get("run_id"))
    o.fact("environment", r.get("environment"))
    o.fact("cleanup selection", r.get("cleanup_selection"))
    o.fact("config", r.get("config"))
    o.fact("executed code (bindings.source)", dig(r, "bindings.source"))
    o.fact("config checkout", dig(r, "bindings.config_checkout"))
    o.fact("runtime load oracle", dig(r, "config.runtime_load_reason") or "ran")
    for s in r.get("stages") or []:
        o.fact(f"stage {s['stage']}", f"{s['status']} "
               f"{s.get('implementation', '')} model={s.get('loaded_model_id')} "
               f"load={s.get('load_seconds')} "
               f"runs={[(x['seconds'], x.get('path')) for x in s.get('runs', [])]}"
               f" {s.get('error') or s.get('reason') or ''}")
    summ = r.get("summary") or {}
    o.fact("summary", summ)
    o.inv(not r.get("errors"), f"no early errors {r.get('errors') or ''}")
    o.inv(summ.get("stages_failed") == 0, "no requested stage failed")
    o.inv(summ.get("fallback_runs") == 0,
          "no cleanup run fell back (a fallback is not a model-cleaned timing)")
    o.inv(dig(r, "config.matches_runtime_load") is True,
          "probe config == localflow.config.load() in the same process")
    sel = r.get("cleanup_selection") or {}
    if sel.get("selected_by") == "config":
        o.inv(sel.get("probed_implementation") ==
              sel.get("configured_implementation") or
              sel.get("probed_implementation") is None,
              "probed implementation is the configured one")


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 2 or argv[0] not in ("manifest", "snapshot", "parse", "probe"):
        print(__doc__, file=sys.stderr)
        return 2
    kind, path = argv
    o = Out()
    try:
        if kind == "snapshot":
            snapshot(path, o)
        else:
            doc = json.loads(pathlib.Path(path).read_text())
            {"manifest": manifest, "parse": parse_report, "probe": probe}[kind](doc, o)
    except (OSError, ValueError, KeyError) as e:
        print(f"ERROR: cannot summarize {path}: {type(e).__name__}: {e}",
              file=sys.stderr)
        return 2
    print(f"\n{o.violations} invariant(s) violated")
    return 1 if o.violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
