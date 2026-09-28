"""Synthetic world for the M14 remediation suite, corpus drivers and
mutation check (2026-09-28 read-only audit at 1e351d7).

Everything here is synthetic: a fresh temporary store per world, a fixed
store clock, synthetic ``com.synthetic.*`` app identities, generated
tone WAVs (never recorded voices) and distinct text canaries. Nothing
reads the live store, real History, notes, usage or the clipboard.

Fixtures bind to the PRODUCERS' own shapes (localflow/v2/training.py,
insertion/observation.py, transforms_store.py): artifact roles
``raw_transcript`` (stage asr), ``normalized_text`` /
``normalization_ledger``, ``applied_output`` (stage cleanup),
``original_audio`` (float32 WAV written by ``Store.write_audio_artifact``),
``cleanup_input_cleanup`` (kind model_input), ``observation_before_range``
/ ``observation_after_range``, ``transform_source`` / ``transform_output``
/ ``transform_prompt`` / ``transform_decision``. A corruption case
changes exactly one named field of an otherwise qualified graph.

Ordering at seams is decided by latches and op hooks, never sleeps. A
latch records that its seam was REACHED; a probe whose seam never
fired is invalid, not a pass. Readers here are plain SQL — the
independent side of every assertion never calls the production
function under test.
"""

from __future__ import annotations

import contextlib
import hashlib
import inspect
import json
import math
import pathlib
import struct
import sys
import tempfile
import threading

HERE = pathlib.Path(__file__).resolve()
ROOT = HERE.parents[3]
for p in (ROOT, HERE.parent):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import numpy as np  # noqa: E402

from localflow.v2 import ids  # noqa: E402
from localflow.v2 import learning as learning_mod  # noqa: E402
from localflow.v2 import profile as profile_mod  # noqa: E402
from localflow.v2 import store as store_mod  # noqa: E402
from localflow.v2 import training_data as training_mod  # noqa: E402
from localflow.v2.curation import export as export_mod  # noqa: E402
from localflow.v2.curation import review as review_mod  # noqa: E402
from localflow.v2.curation import sampling as sampling_mod  # noqa: E402
from localflow.v2.curation import splits as splits_mod  # noqa: E402
from localflow.v2.vocabulary_store import VocabularyStore  # noqa: E402

CLOCK_ISO = "2026-09-28T12:00:00.000Z"
APP = "com.synthetic.editor"
RATE = 16000

# Distinct canaries (data strings only).
A_CANARY = "A_ONLY_41"
B_CANARY = "B_ONLY_73"
PRIVATE_CANARY = "PRIVATE_PHRASE_CANARY_59"
TYPED_CANARY = "typedonlycanary"


def epoch(iso: str) -> float:
    import datetime as _dt
    return _dt.datetime.strptime(iso, "%Y-%m-%dT%H:%M:%S.%fZ").replace(
        tzinfo=_dt.timezone.utc).timestamp()


class Clock:
    def __init__(self, iso=CLOCK_ISO):
        self.t = epoch(iso)

    def __call__(self):
        return self.t

    def advance_days(self, days):
        self.t += days * 86400.0


def accepts(fn, name) -> bool:
    try:
        return name in inspect.signature(fn).parameters
    except (TypeError, ValueError):
        return False


def tone(freq: float, seconds: float = 1.0) -> np.ndarray:
    n = int(RATE * seconds)
    t = np.arange(n, dtype=np.float64) / RATE
    return (0.2 * np.sin(2 * math.pi * freq * t)).astype("<f4")


def sha256_file(path) -> str:
    with open(path, "rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


# ---- latches ---------------------------------------------------------------


class Latch:
    """A named seam. ``hit()`` records arrival and (when blocking) waits
    for ``release()``."""

    def __init__(self, name, block=True):
        self.name = name
        self.block = block
        self.reached = threading.Event()
        self.release_evt = threading.Event()
        self.hits = 0

    def hit(self):
        self.hits += 1
        self.reached.set()
        if self.block:
            assert self.release_evt.wait(30), f"latch {self.name} stuck"

    def release(self):
        self.release_evt.set()


@contextlib.contextmanager
def patched(obj, name, wrapper_factory):
    had_own = name in getattr(obj, "__dict__", {})
    original = getattr(obj, name)
    setattr(obj, name, wrapper_factory(original))
    try:
        yield original
    finally:
        if had_own:
            setattr(obj, name, original)
        else:
            try:
                delattr(obj, name)
            except AttributeError:
                setattr(obj, name, original)


@contextlib.contextmanager
def after_each_op(store, hook):
    """Run ``hook()`` in the CALLER thread after every waited
    ``store.submit`` returns (between writer ops — never inside one,
    so the hook may submit its own ops without deadlocking the single
    writer). The hook sees committed state only."""
    original = store.submit
    busy = threading.local()

    def submit(fn, wait=True, timeout=15.0):
        out = original(fn, wait=wait, timeout=timeout)
        if wait and not getattr(busy, "on", False):
            busy.on = True
            try:
                hook()
            finally:
                busy.on = False
        return out
    store.submit = submit
    try:
        yield
    finally:
        store.submit = original


# ---- the world ---------------------------------------------------------------


class MWorld:
    """A temp store with the real M14 services under a fixed clock."""

    def __init__(self, *, consent=True, min_words=2000, artifacts="arts"):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = pathlib.Path(self._tmp.name)
        self.clock = Clock()
        self.events = []
        self.store = store_mod.Store(
            self.tmp / "v2.db", artifacts_dir=self.tmp / artifacts,
            backup_dir=self.tmp / "bk", now_fn=self.clock,
            emit=self._emit)
        if consent:
            self.store.append_consent("enabled", note="m14-remediation")
        emit = self._emit
        self.vocab = VocabularyStore(self.store)
        self.learning = learning_mod.LearningService(
            self.store, emit=emit, vocabulary=self.vocab)
        self.review = review_mod.ReviewService(self.store, emit=emit)
        self.sampling = sampling_mod.SamplingService(self.store, emit=emit)
        self.splits = splits_mod.SplitService(self.store, emit=emit)
        self.profile = profile_mod.ProfileService(self.store, emit=emit,
                                                  min_words=min_words)
        self.exporter = export_mod.DatasetExporter(self.store, emit=emit)
        self.training = training_mod.TrainingDataService(self.store,
                                                         emit=emit)
        self._seq = 0
        self.closed = False

    def _emit(self, name, **kw):
        self.events.append((name, kw))

    def close(self):
        if self.closed:
            return
        self.closed = True
        try:
            self.store.close()
        finally:
            self._tmp.cleanup()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # ---- producer-shaped jobs -------------------------------------------------

    def job(self, raw, applied=None, *, normalized=None, audio=True,
            freq=None, prompts=1, family=None, app=APP, example=True,
            state="captured_unreviewed", captured_at=None,
            utc_offset=0, applied_rule_ids=(), snippets=False,
            cleanup_counts=None, extra_env=None):
        """One producer-shaped dictation. Returns a dict of ids. The
        envelope uses the collector's keys (training.py ``_envelope``)."""
        self._seq += 1
        seq = self._seq
        applied = raw if applied is None else applied
        s = self.store
        job_id, fam = s.create_job(family_id=family)
        days = s.retention_days["training_buffer"]
        out = {"job_id": job_id, "family_id": fam, "raw": raw,
               "applied": applied}
        if audio:
            out["audio_aid"] = s.write_audio_artifact(
                job_id=job_id, stage="capture",
                samples=tone(freq or (200.0 + 17.0 * seq)),
                sample_rate=RATE, meta={"synthetic": True})
            s.grant_lease(out["audio_aid"], "training", days=days)
        out["raw_aid"] = s.write_text_artifact(
            job_id=job_id, stage="asr", role="raw_transcript", text=raw,
            retention_class="training")
        s.grant_lease(out["raw_aid"], "training", days=days)
        if normalized is not None and normalized != raw:
            out["norm_aid"] = s.write_text_artifact(
                job_id=job_id, stage="normalization",
                role="normalized_text", text=normalized,
                retention_class="training", parent_artifact_id=out["raw_aid"])
        else:
            out["norm_aid"] = s.write_text_artifact(
                job_id=job_id, stage="normalization",
                role="normalization_ledger", kind="normalization_ledger_json",
                text=json.dumps({"edits": []}), retention_class="training",
                parent_artifact_id=out["raw_aid"])
        s.grant_lease(out["norm_aid"], "training", days=days)
        passes = []
        out["prompt_aids"] = []
        cleanup_input = normalized if normalized is not None else raw
        for i in range(prompts):
            prompt = (f"Clean this dictation (pass {i}):\n{cleanup_input}")
            aid = s.write_text_artifact(
                job_id=job_id, stage="cleanup", role="cleanup_input_cleanup",
                text=prompt, kind="model_input", retention_class="training",
                meta={"kind": "cleanup",
                      "input_text_sha256": ids.sha256_text(cleanup_input)})
            s.grant_lease(aid, "training", days=days)
            out["prompt_aids"].append(aid)
            passes.append({"kind": "cleanup",
                           "input_sha256": ids.sha256_text(cleanup_input),
                           "prompt_artifact_id": aid,
                           "proposal_artifact_id": None,
                           "accepted": True, "applied_sha256":
                               ids.sha256_text(applied), "status": "selected"})
        out["applied_aid"] = s.write_text_artifact(
            job_id=job_id, stage="cleanup", role="applied_output",
            text=applied, retention_class="training",
            parent_artifact_id=out["raw_aid"],
            meta={"cleanup_path": "model"})
        s.grant_lease(out["applied_aid"], "training", days=days)
        s.set_job_target(job_id, "Synthetic Editor", app)
        if not example:
            s.sync()
            return out
        consent = s.current_consent_id()
        ex = s.upsert_example(job_id=job_id, family_id=fam,
                              consent_revision_id=consent)
        out["example_id"] = ex
        cleanup = {"passes": passes, "applied_path": "model"}
        if cleanup_counts is not None:
            cleanup["v2"] = {"corrections": cleanup_counts}
        normalization = {"vocabulary": {"applied_rule_ids":
                                        list(applied_rule_ids)}}
        if snippets:
            normalization["snippets"] = {"expansions": 1}
        env = {
            "training_schema_version": 1, "example_id": ex,
            "revision_id": None, "job_id": job_id, "family_id": fam,
            "attempt": 1, "origin": "live_capture",
            "task_kind": "dictation",
            "captured_at_utc": captured_at
            or f"2026-09-2{seq % 7}T1{seq % 10}:00:00.000Z",
            "time_quality": "known", "utc_offset_minutes": utc_offset,
            "consent_revision_id": consent,
            "capture": {"duration_sec": 1.0, "sample_rate": RATE},
            "recognition": {"language": "en", "model_id": "synth-asr"},
            "normalization": normalization,
            "cleanup": cleanup,
            "artifact_ids": {"source_text": out["raw_aid"],
                             "normalization": out["norm_aid"],
                             "applied_output": out["applied_aid"]},
            "missing_reasons": {},
            "outcome": {"insertion": "confirmed",
                        "correctness": "unreviewed"},
            "annotations": [], "preferences": [],
            "state": "captured_unreviewed", "deletion_epoch": 0,
        }
        if audio:
            env["artifact_ids"]["original_audio"] = out["audio_aid"]
        env.update(extra_env or {})
        out["revision_id"] = s.append_revision(ex, env)
        if state != "captured_unreviewed":
            self.set_state(ex, state)
        return out

    def set_state(self, example_id, state):
        self.store.submit(lambda c: c.execute(
            "UPDATE training_examples SET state=? WHERE example_id=?",
            (state, example_id)))

    def envelope(self, example_id) -> dict:
        row = self.store.submit(lambda c: c.execute(
            "SELECT envelope_json FROM training_revisions WHERE"
            " example_id=? ORDER BY rowid DESC LIMIT 1",
            (example_id,)).fetchone())
        return json.loads(row[0]) if row else None

    def rewrite_envelope(self, example_id, mutate):
        """Append a revision whose envelope is ``mutate(env)`` (a
        corruption case changes exactly one field)."""
        env = self.envelope(example_id)
        parent = env.get("revision_id")
        mutate(env)
        env["revision_id"] = None
        return self.store.append_revision(example_id, env, parent)

    def text_artifact(self, job_id, role, text, *, stage="review",
                      kind="text", lease_days=None, meta=None,
                      parent=None):
        aid = self.store.write_text_artifact(
            job_id=job_id, stage=stage, role=role, text=text, kind=kind,
            retention_class="training", meta=meta,
            parent_artifact_id=parent)
        if lease_days is not False:
            self.store.grant_lease(aid, "training", days=lease_days)
        return aid

    # ---- review/annotation helpers (real services) ---------------------------

    def verbatim(self, example_id, text):
        return self.training.set_verbatim(example_id, text,
                                          listened_audio=True)

    def ready_asr(self, text=None, **kw):
        """A fully qualified ASR witness: own audio + own listened
        verbatim reference."""
        j = self.job(text or f"asr witness {self._seq + 1} {A_CANARY}",
                     **kw)
        self.verbatim(j["example_id"], j["raw"])
        return j

    def ready_cleanup(self, text=None, *, correct=True, **kw):
        j = self.job(text or f"cleanup witness {self._seq + 1}",
                     (text or f"Cleanup witness {self._seq + 1}") + ".",
                     **kw)
        self.training.mark_intended(j["example_id"], correct)
        return j

    def families(self, n, *, asr=False, frozen=0):
        """``n`` independent families; ``frozen`` of them are chosen so
        the contract's family hash (dataset_exports.md:
        sha256(seed:family_id) → [0.9, 1) is frozen_test) puts them in
        the blind holdout — computed here, not by the SplitService."""
        out = []
        for i in range(n):
            fam = frozen_family_id(i) if i < frozen else None
            out.append(self.ready_asr(family=fam) if asr else
                       self.job(f"family filler {i} utterance",
                                family=fam))
        return out

    # ---- M08 observations ------------------------------------------------------

    def observation(self, job_id, before, after, *, stop="owned_range_edited",
                    edited=True, before_job=None, after_job=None,
                    before_role="observation_before_range",
                    after_role="observation_after_range"):
        """A certified observation shaped like insertion/observation.py
        (before/after artifacts of the SAME job unless a corruption
        names another)."""
        obs_id = ids.new_id("obs")
        b = self.store.write_text_artifact(
            job_id=before_job or job_id, stage="insertion",
            role=before_role, text=before, retention_class="training",
            meta={"range_units": "utf16_host"})
        a = self.store.write_text_artifact(
            job_id=after_job or job_id, stage="insertion",
            role=after_role, text=after, retention_class="training",
            meta={"range_units": "utf16_host"})
        for art in (b, a):
            self.store.grant_lease(art, "training",
                                   days=self.store.retention_days[
                                       "training_buffer"])
        now = ids.now_utc_iso()
        self.store.submit(lambda c: c.execute(
            "INSERT INTO insertion_observations(observation_id,"
            " insertion_id, job_id, started_at_utc, stopped_at_utc,"
            " stop_reason, edited, reanchors, ticks, before_artifact_id,"
            " after_artifact_id, meta_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (obs_id, ids.new_id("ins"), job_id, now, now, stop,
             1 if edited else 0, 0, 4, b, a,
             json.dumps({"range_units": "utf16_host"}))))
        return obs_id

    # ---- M11 transform candidates ---------------------------------------------

    def transform_task(self, source, outputs, **kw):
        return transform_task(self.store, source, outputs, **kw)

    def tf_store(self):
        from localflow.v2.transforms_store import TransformStore
        return TransformStore(self.store)

    def judge(self, task, a, b, judgment):
        return self.tf_store().record_observation(
            task_key=task["task_key"], candidate_id=a, candidate_b_id=b,
            judgment=judgment, provenance="m14_pair_review")

    def accept(self, task, cand, judgment="accept"):
        return self.tf_store().record_observation(
            task_key=task["task_key"], candidate_id=cand,
            judgment=judgment, provenance="user_action")

    # ---- raw readers (independent side) ----------------------------------------

    def rows(self, sql, args=()):
        return self.store.submit(lambda c: c.execute(sql, args).fetchall())

    def one(self, sql, args=()):
        return self.store.submit(lambda c: c.execute(sql, args).fetchone())

    def artifact_row(self, aid):
        return self.one("SELECT job_id, role, purged, content_text,"
                        " content_path, sha256 FROM artifacts WHERE"
                        " artifact_id=?", (aid,))

    def purge(self, aid):
        """Purge one artifact through the store's own purge path (the
        retention/deletion primitive), committing its intent."""
        def op():
            self.store._purge_artifact(aid, reason="retention")
            self.store._purge_pending = True
        self.store._submit(op, wait=True)

    def candidate(self, cid):
        row = self.one(
            "SELECT status, proposed_alias, proposed_canonical,"
            " vocabulary_entry_id, vocabulary_action, counterexample_json,"
            " changed_spans_json, after_artifact_id, job_id, example_id,"
            " classification_json FROM learning_candidates WHERE"
            " candidate_id=?", (cid,))
        if row is None:
            return None
        return dict(zip(("status", "alias", "canonical", "entry_id",
                         "action", "counterexamples", "spans",
                         "payload_aid", "job_id", "example_id",
                         "classification"), row))

    def payload(self, cid):
        """The candidate's governed payload JSON (None once purged)."""
        c = self.candidate(cid)
        row = self.artifact_row(c["payload_aid"]) if c else None
        return json.loads(row[3]) if row and row[3] else None

    def entries(self):
        """{entry_id: (canonical, scope_kind, scope_value, enabled,
        approved, revision, [(alias, approved), ...])} straight from the
        vocabulary tables."""
        out = {}
        for eid, canon, sk, sv, en, ap, rev in self.rows(
                "SELECT entry_id, canonical, scope_kind, scope_value,"
                " enabled, approved, revision FROM vocabulary_entries"):
            aliases = sorted((a, bool(f)) for a, f in self.rows(
                "SELECT alias, approved FROM vocabulary_aliases WHERE"
                " entry_id=?", (eid,)))
            out[eid] = (canon, sk, sv, bool(en), bool(ap), rev, aliases)
        return out

    def normalize(self, text, app=None):
        """The real M05 snapshot/sandbox output for ``text``."""
        from localflow.v2 import vocabulary as vocab_mod
        ctx = vocab_mod.ScopeContext(app_bundle=app) if app \
            else vocab_mod.ScopeContext()
        snap = vocab_mod.VocabularySnapshot(self.vocab.entries(), ctx)
        return vocab_mod.sandbox_phrase(text, snap).get("output")

    def export(self, dest, views, **kw):
        return self.exporter.build(self.tmp / dest if isinstance(
            dest, str) else dest, task_views=views, **kw)


def transform_task(store, source, outputs, *, job_id=None,
                   transform_id="builtin:polish", revision=1,
                   display=None, source_sha=None):
    """One task with len(outputs) candidates, shaped like
    TransformStore.record_candidate (source/output/prompt/decision
    artifacts; task key over mode+source+instructions+examples)."""
    instructions = "Polish the synthetic draft."
    src_sha = source_sha or ids.sha256_text(source)
    ins_sha = ids.sha256_text(instructions)
    task_key = ids.sha256_text(json.dumps(["polish", src_sha, ins_sha, None]))
    now = ids.now_utc_iso()
    cands = []
    display = display or list(range(len(outputs)))

    def op(c):
        c.execute(
            "INSERT OR IGNORE INTO transform_revisions(transform_id,"
            " revision, definition_json, created_at_utc) VALUES(?,?,?,?)",
            (transform_id, revision, json.dumps(
                {"transform_id": transform_id, "revision": revision,
                 "instructions": instructions, "examples": []}), now))
        for i, text in enumerate(outputs):
            cid = ids.new_id("tcand")
            src = store_mod.insert_text_artifact_row(
                c, artifact_id=ids.new_id("art"), job_id=job_id,
                stage="transform", role="transform_source", text=source,
                retention_class="training",
                meta={"task_key": task_key, "source_kind": "selection"},
                created_at_utc=now)
            out = store_mod.insert_text_artifact_row(
                c, artifact_id=ids.new_id("art"), job_id=job_id,
                stage="transform", role="transform_output", text=text,
                retention_class="training",
                meta={"task_key": task_key, "path": "applied"},
                created_at_utc=now)
            store_mod.insert_text_artifact_row(
                c, artifact_id=ids.new_id("art"), job_id=job_id,
                stage="transform", role="transform_prompt",
                text=f"{instructions}\n{source}", kind="model_input",
                retention_class="training",
                meta={"task_key": task_key, "prompt_revision": "r1"},
                parent_artifact_id=out, created_at_utc=now)
            store_mod.insert_text_artifact_row(
                c, artifact_id=ids.new_id("art"), job_id=job_id,
                stage="transform", role="transform_decision",
                text=json.dumps({"path": "applied"}),
                kind="transform_decision_json", retention_class="training",
                meta={"task_key": task_key, "path": "applied"},
                parent_artifact_id=out, created_at_utc=now)
            c.execute(
                "INSERT INTO transform_candidates(candidate_id, task_key,"
                " task_kind, transform_id, transform_revision,"
                " prompt_revision, source_sha256, instructions_sha256,"
                " examples_revision, source_artifact_id,"
                " output_artifact_id, path, display_order, model_id,"
                " created_at_utc) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (cid, task_key, "transform_selection", transform_id,
                 revision, "r1", src_sha, ins_sha, None, src, out,
                 "applied", display[i], "qwen-synth", now))
            cands.append({"candidate_id": cid, "source_aid": src,
                          "output_aid": out, "text": text})
    store.submit(op)
    return {"task_key": task_key, "candidates": cands, "source": source}


SPLIT_SEED = "localflow-m14-splits-v1"


def family_bucket(family_id, seed=SPLIT_SEED) -> str:
    """The contract's partition for a family (independent recount)."""
    digest = hashlib.sha256(f"{seed}:{family_id}".encode()).digest()
    draw = int.from_bytes(digest[:8], "big") / float(2 ** 64)
    return "train" if draw < 0.8 else (
        "validation" if draw < 0.9 else "frozen_test")


def frozen_family_id(n) -> str:
    """The n-th synthetic family id that hashes into frozen_test."""
    found = -1
    k = 0
    while True:
        fam = f"fam-synth-frozen-{k}"
        if family_bucket(fam) == "frozen_test":
            found += 1
            if found == n:
                return fam
        k += 1


def read_jsonl(path):
    p = pathlib.Path(path)
    return [json.loads(line) for line in p.read_text().splitlines()
            if line.strip()]


def wav_frames(path):
    """The raw sample bytes of a WAV (header-independent identity)."""
    data = pathlib.Path(path).read_bytes()
    idx = data.find(b"data")
    size = struct.unpack("<I", data[idx + 4:idx + 8])[0]
    return data[idx + 8:idx + 8 + size]


def code_stamp(suite):
    import subprocess
    import localflow
    root = pathlib.Path(localflow.__file__).resolve().parents[1]

    def git(*a):
        p = subprocess.run(["git", "-C", str(root), *a],
                           capture_output=True, text=True)
        return p.stdout.strip() if p.returncode == 0 else None
    status = git("status", "--porcelain", "--untracked-files=no")
    prod = git("status", "--porcelain", "--untracked-files=no", "--",
               "localflow", "scripts")
    suite_path = root / suite
    return {"suite": suite,
            "suite_sha256": hashlib.sha256(suite_path.read_bytes())
            .hexdigest() if suite_path.is_file() else None,
            "code_root_sha": git("rev-parse", "HEAD"),
            "tracked_files_modified": bool(status) if status is not None
            else None,
            "production_tree_modified": bool(prod) if prod is not None
            else None,
            "python": sys.version.split()[0]}


def strict_json(obj) -> str:
    return json.dumps(obj, allow_nan=False, sort_keys=True, default=str)
