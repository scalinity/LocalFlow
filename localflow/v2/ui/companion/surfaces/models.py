"""Models — engines and Training Data (S29.15; M09-AC05/AC06; M14 review,
splits and export) with the AppKit Hub's rules (hub.py ``training*``,
``review*``, ``splits*``, ``export*``):

- Evidence actions resolve the example from the detail token the page
  rendered; the verbatim gate is per example (a playback START of the
  rendered example opens it; selecting another closes it); annotation
  saves carry one id per (example, kind, text) so a save whose outcome
  was unknown repeats without a duplicate.
- Review actions name the queue, pair list or approved list the page
  rendered (a newer publication makes the action stale) and the row's
  own candidate id; write actions carry one operation id per logical
  action, kept only after an unknown outcome.
- Export takes its folder from a native folder panel only; one build
  per folder at a time; a folder whose export outcome is unknown cannot
  be validated until an Export of it settles; a Validate result is bound
  to the folder it checked and is never repainted by a refresh.
- Long actions (mining, export, validation) run off the main thread and
  report only while they are the newest of their key.
"""

from __future__ import annotations

from .. import bridge as B
from ..bridge import Bool, Enum, Int, List, Str
from .common import refusal_text

TABS = ("evidence", "review", "splits", "export")
EDIT_KINDS = ("recognition_error", "representation_error",
              "punctuation_or_structure", "style_preference",
              "transform_preference", "changed_intent", "user_rewrite",
              "ambiguous", "unknown")
JUDGMENTS = ("prefer_a", "prefer_b", "tie", "neither", "uncertain")


def register(ctl):
    br = ctl.bridge
    st = ctl.state
    spec = ctl.spec
    ctl.training_annotation = None  # {key, job_id, annotation_id}
    ctl.export_folder = None
    ctl.exports_running = {}
    ctl.exports_unknown = set()
    ctl.export_validation = None  # {folder, state, report|reason}
    panels = spec.get("file_panels")

    def training():
        svc = spec.get("training_service")
        if svc is None:
            B.unavailable("training_unavailable")
        return svc

    def example(p):
        """The rendered detail for the selected example (the token)."""
        d = ctl.rendered("models", p["token"])
        if d.get("example_id") != st.views["models"].get("selected_id"):
            B.stale("detail_not_current")
        return d

    def annotation_id(ctx, kind, text):
        from .... import ids
        key = (ctx["example_id"], kind, ids.sha256_text(text))
        pend = ctl.training_annotation
        if pend is not None and pend["key"] == key:
            return pend["annotation_id"]
        ctl.training_annotation = {"key": key, "job_id": ctx.get("job_id"),
                                   "annotation_id": ids.new_id("ann")}
        return ctl.training_annotation["annotation_id"]

    def action(fn, *args, **kw):
        """A training write: an admitted timeout is an unknown outcome;
        a refusal names its content-free reason."""
        try:
            return fn(*args, **kw)
        except TimeoutError:
            B.unknown("store_busy")
        except (ValueError, RuntimeError) as e:
            reason = refusal_text(e)
            if reason is None:
                raise
            B.refuse(reason)

    def rendered_list(kind, token):
        """The queue / pairs / approved list the page rendered."""
        data = st.views["models"].get("data") or {}
        cur = ctl._tokens.get(f"models.{kind}")
        if cur is None or cur[1] != token or cur[0] is not data.get(kind):
            B.stale(f"{kind}_not_current")
        return cur[0]

    # ---- navigation ------------------------------------------------------------

    @br.command("models.subview", {"subview": Enum(("engines", "training"))})
    def subview(p):
        st.select_models_subview(p["subview"])
        return {}

    @br.command("training.tab", {"tab": Enum(TABS)})
    def tab(p):
        st.select_training_tab(p["tab"])
        return {}

    @br.command("training.search", {"text": Str(max_len=200)})
    def search(p):
        st.set_training_search(p["text"])
        return {}

    @br.command("training.select", {"example_id": Str(max_len=120,
                                                      optional=True)})
    def select(p):
        st.select_training_example(p.get("example_id") or None)
        return {}

    # ---- Evidence -------------------------------------------------------------

    T = {"token": Str(max_len=40)}

    @br.command("training.mark", {**T, "correct": Bool()})
    def mark(p):
        d = example(p)
        action(training().mark_intended, d["example_id"], p["correct"])
        st.select_training_example(d["example_id"])
        return {}

    @br.command("training.pin", T)
    def pin(p):
        d = example(p)
        action(training().pin, d["example_id"], not d.get("pinned"))
        st.select_training_example(d["example_id"])
        st.reload_training()
        return {"pinned": not d.get("pinned")}

    @br.command("training.exclude", T)
    def exclude(p):
        d = example(p)
        want = d.get("state") != "excluded"
        new = action(training().exclude, d["example_id"], want)
        st.select_training_example(d["example_id"])
        st.reload_training()
        if want != (new == "excluded"):
            B.refuse(f"{'exclude' if want else 'include'}_refused:{new}")
        return {"state": new}

    @br.command("training.delete", {**T, "confirmed": Bool()})
    def delete(p):
        if not p["confirmed"]:
            B.refuse("confirmation_required")
        d = example(p)
        ex = d["example_id"]
        action(training().delete_everywhere, ex)
        if st.views["models"].get("selected_id") == ex:
            st.select_training_example(None)
        st.reload_training()
        return {"deleted": ex}

    @br.command("training.replay", T)
    def replay(p):
        d = example(p)
        audio = d.get("audio") or {}
        rp = ctl.replay
        if rp is None or not audio.get("available"):
            if rp is not None:
                rp.stop()
            B.refuse(audio.get("reason") or "no_artifact")
        out = rp.play_artifact(spec["store"], audio.get("artifact_id"))
        if out.get("status") != "playing":
            B.refuse(str(out.get("reason")))
        # The verbatim gate opens for THIS example's playback start only.
        if st.views["models"].get("detail") is d:
            st.views["models"]["listened_for"] = d["example_id"]
        ctl.request_flush()
        return {"listened": True}

    @br.command("training.verbatim", {**T, "text": Str(max_len=20_000)})
    def verbatim(p):
        text = p["text"]
        if not text:
            B.refuse("text_required")
        d = example(p)
        ex = d["example_id"]
        listened = st.views["models"].get("listened_for") == ex
        ann = annotation_id(d, "verbatim", text)
        try:
            training().set_verbatim(ex, text, listened_audio=listened,
                                    annotation_id=ann)
        except TimeoutError:
            B.unknown("save_unknown")
        except Exception as e:
            ctl.training_annotation = None
            B.refuse(refusal_text(e) or type(e).__name__)
        ctl.training_annotation = None
        st.views["models"]["listened_for"] = None
        st.select_training_example(ex)
        return {}

    @br.command("training.span", {**T,
                                  "stage": Enum(("source_text",
                                                 "applied_output")),
                                  "start": Int(lo=0), "end": Int(lo=0),
                                  "corrected": Str(max_len=20_000)})
    def span(p):
        from .... import ids
        if not p["corrected"]:
            B.refuse("text_required")
        d = example(p)
        ex = d["example_id"]
        reviewed = next((s for s in d.get("stages") or ()
                         if s.get("stage") == p["stage"]
                         and s.get("available")), None)
        if reviewed is None:
            B.refuse("stage_unavailable")
        ann = annotation_id(d, f"span:{p['stage']}:{p['start']}:{p['end']}",
                            p["corrected"])
        try:
            training().add_span_correction(
                ex, p["stage"], p["start"], p["end"], p["corrected"],
                expected_artifact_id=reviewed["artifact_id"],
                expected_sha256=ids.sha256_text(reviewed["text"]),
                annotation_id=ann)
        except TimeoutError:
            B.unknown("save_unknown")
        except Exception as e:
            ctl.training_annotation = None
            B.refuse(refusal_text(e) or type(e).__name__)
        ctl.training_annotation = None
        st.select_training_example(ex)
        return {}

    # ---- Review ----------------------------------------------------------------

    @br.command("review.sample")
    def sample(p):
        svc = spec.get("sampling_service")
        if svc is None:
            B.unavailable("sampling_unavailable")
        action(svc.refresh)
        st.select_training_tab("review")
        return {}

    @br.command("review.mine")
    def mine(p):
        svc = spec.get("learning_service")
        if svc is None:
            B.unavailable("learning_unavailable")

        def done(out, err, current):
            if not current:
                return
            ctl.notes["review"] = {"code": "mining_failed",
                                   "reason": type(err).__name__} \
                if err is not None else {"code": "mining_finished"}
            st.reload_training()
            ctl.request_flush()
        ctl.background.run("mine", svc.mine_observation_candidates, done)
        ctl.request_flush()
        return {"started": True}

    def queue_row(p):
        rows = rendered_list("queue", p["queue_token"])
        row = next((r for r in rows
                    if r.get("candidate_id") == p["candidate_id"]), None)
        if row is None:
            B.stale("candidate_not_in_queue")
        return row

    Q = {"queue_token": Str(max_len=40), "candidate_id": Str(max_len=120)}

    @br.command("review.approve", {**Q, "counterexample": Str(max_len=500)})
    def approve(p):
        learning = spec.get("learning_service")
        if learning is None:
            B.unavailable("learning_unavailable")
        queue_row(p)
        cid, counter = p["candidate_id"], p["counterexample"].strip()
        op = ctl.ops.get("approve", (cid, counter))
        unknown = False
        try:
            out = learning.approve(
                cid, counterexamples=(counter,) if counter else (),
                operation_id=op)
        except TimeoutError:
            unknown = True
            B.unknown("store_busy")
        except (ValueError, RuntimeError) as e:
            B.refuse(refusal_text(e) or type(e).__name__)
        finally:
            ctl.ops.settled("approve", unknown)
        flips = out.get("flips") or ()
        if flips:
            B.refuse("would_flip", {"flips": [
                {"phrase": f.get("phrase"), "applied": f.get("applied")}
                for f in flips]})
        st.select_training_tab("review")
        return {"action": out.get("action")}

    @br.command("review.reject", Q)
    def reject(p):
        learning = spec.get("learning_service")
        if learning is None:
            B.unavailable("learning_unavailable")
        queue_row(p)
        op = ctl.ops.get("reject", p["candidate_id"])
        unknown = False
        try:
            learning.reject(p["candidate_id"], operation_id=op)
        except TimeoutError:
            unknown = True
            B.unknown("store_busy")
        except (ValueError, RuntimeError) as e:
            B.refuse(refusal_text(e) or type(e).__name__)
        finally:
            ctl.ops.settled("reject", unknown)
        st.select_training_tab("review")
        return {}

    @br.command("review.label", {"queue_token": Str(max_len=40),
                                 "example_id": Str(max_len=120),
                                 "edit_kind": Enum(EDIT_KINDS)})
    def label(p):
        svc = spec.get("review_service")
        if svc is None:
            B.unavailable("review_unavailable")
        rows = rendered_list("queue", p["queue_token"])
        if not any(r.get("example_id") == p["example_id"] for r in rows):
            B.stale("example_not_in_queue")
        ex, kind = p["example_id"], p["edit_kind"]
        op = ctl.ops.get("label", (ex, kind))
        unknown = False
        try:
            svc.record_label(ex, edit_kind=kind, abstained=(kind == "unknown"),
                             operation_id=op)
        except TimeoutError:
            unknown = True
            B.unknown("store_busy")
        except (ValueError, RuntimeError) as e:
            B.refuse(refusal_text(e) or type(e).__name__)
        finally:
            ctl.ops.settled("label", unknown)
        st.select_training_tab("review")
        return {}

    @br.command("review.pair", {"pairs_token": Str(max_len=40),
                                "task_key": Str(max_len=200),
                                "a": Str(max_len=120), "b": Str(max_len=120),
                                "judgment": Enum(JUDGMENTS)})
    def pair(p):
        svc = spec.get("review_service")
        tstore = spec.get("transforms_store")
        if svc is None or tstore is None:
            B.unavailable("review_unavailable")
        pairs = rendered_list("preference_pairs", p["pairs_token"])
        shown = next((x for x in pairs if x.get("task_key") == p["task_key"]),
                     None)
        ids_shown = [c.get("candidate_id") for c in
                     sorted((shown or {}).get("candidates") or (),
                            key=lambda c: c.get("display_order") or 0)
                     if c.get("text") is not None][:2]
        if ids_shown != [p["a"], p["b"]]:
            B.stale("pair_not_current")
        op = ctl.ops.get("pair", (p["task_key"], p["a"], p["b"],
                                  p["judgment"]))
        unknown = False
        try:
            svc.record_pair_judgment(tstore, p["task_key"], p["a"], p["b"],
                                     p["judgment"], operation_id=op)
        except TimeoutError:
            unknown = True
            B.unknown("store_busy")
        except (ValueError, RuntimeError) as e:
            B.refuse(refusal_text(e) or type(e).__name__)
        finally:
            ctl.ops.settled("pair", unknown)
        st.select_training_tab("review")
        return {}

    @br.command("review.undo", {"approved_token": Str(max_len=40),
                                "candidate_id": Str(max_len=120)})
    def undo(p):
        learning = spec.get("learning_service")
        if learning is None:
            B.unavailable("learning_unavailable")
        rows = rendered_list("approved", p["approved_token"])
        row = next((r for r in rows
                    if r.get("candidate_id") == p["candidate_id"]), None)
        if row is None:
            B.stale("approval_not_current")
        op = ctl.ops.get("undo", p["candidate_id"])
        unknown = False
        try:
            learning.undo_approval(p["candidate_id"], operation_id=op)
        except TimeoutError:
            unknown = True
            B.unknown("store_busy")
        except (ValueError, RuntimeError) as e:
            B.refuse(refusal_text(e) or type(e).__name__)
        finally:
            ctl.ops.settled("undo", unknown)
        ctl.notes["review"] = {"code": "undone", "alias": row.get("alias"),
                               "canonical": row.get("canonical")}
        st.reload_training()
        return {}

    # ---- Splits ------------------------------------------------------------------

    @br.command("splits.assign")
    def assign(p):
        svc = spec.get("splits_service")
        if svc is None:
            B.unavailable("splits_unavailable")
        op = ctl.ops.get("assign", "assign")
        unknown = False
        try:
            out = svc.assign(operation_id=op)
        except TimeoutError:
            unknown = True
            B.unknown("store_busy")
        except (ValueError, RuntimeError) as e:
            B.refuse(refusal_text(e) or type(e).__name__)
        finally:
            ctl.ops.settled("assign", unknown)
        st.select_training_tab("splits")
        return {"unassigned_reason": (out or {}).get("unassigned_reason")}

    @br.command("splits.expose", {"family_id": Str(max_len=120,
                                                   allow_empty=False)})
    def expose(p):
        svc = spec.get("splits_service")
        if svc is None:
            B.unavailable("splits_unavailable")
        op = ctl.ops.get("expose", p["family_id"])
        unknown = False
        try:
            svc.mark_exposed([p["family_id"]], "inspected_during_tuning",
                             operation_id=op)
        except TimeoutError:
            unknown = True
            B.unknown("store_busy")
        except (ValueError, RuntimeError) as e:
            B.refuse(refusal_text(e) or type(e).__name__)
        finally:
            ctl.ops.settled("expose", unknown)
        st.select_training_tab("splits")
        return {}

    # ---- Export --------------------------------------------------------------------

    @br.command("export.choose_folder")
    def choose(p):
        path = panels.choose_folder() if panels is not None \
            else _folder_panel()
        if not path:
            raise B.Outcome("cancelled", "cancelled")
        import pathlib
        ctl.export_folder = str(pathlib.Path(path).expanduser())
        ctl.request_flush()
        return {"folder": ctl.export_folder}

    @br.command("export.run", {"views": List(Str(max_len=60), max_items=10)})
    def run(p):
        from ....curation.export import TASK_VIEWS
        svc = spec.get("export_service")
        if svc is None:
            B.unavailable("export_unavailable")
        views = [v for v in p["views"] if v in TASK_VIEWS]
        folder = ctl.export_folder
        if not folder or not views:
            B.refuse("choose_views_and_folder")
        if ctl.exports_running.get(folder):
            B.refuse("export_running")
        # A newer explicit action: a Validate still running reports
        # nothing over it.
        ctl.export_validation = None
        ctl.background.supersede("validate")
        ctl.exports_running[folder] = ctl.exports_running.get(folder, 0) + 1
        export_id = ctl.ops.get("export", (folder, tuple(sorted(views))))

        def done(out, err, current):
            unknown = isinstance(err, TimeoutError)
            ctl.ops.settled("export", unknown)
            left = ctl.exports_running.get(folder, 1) - 1
            if left > 0:
                ctl.exports_running[folder] = left
            else:
                ctl.exports_running.pop(folder, None)
            if unknown:
                ctl.exports_unknown.add(folder)
            else:
                ctl.exports_unknown.discard(folder)
            if not current:
                return
            if unknown:
                ctl.notes["export"] = {"code": "export_unknown"}
            elif err is not None:
                ctl.notes["export"] = {"code": "export_failed",
                                       "type": type(err).__name__,
                                       "reason": str(err)[:300]
                                       if type(err).__name__ == "ExportError"
                                       else None}
            else:
                ctl.notes["export"] = {
                    "code": "exported", "state": out.get("state"),
                    "export_id": out.get("export_id"),
                    "counts": out.get("counts"),
                    "fingerprint": (out.get("fingerprint") or "")[:16]}
                st.reload_training()
            ctl.request_flush()
        ctl.notes["export"] = {"code": "exporting"}
        ctl.background.run(
            "export", lambda: svc.build(folder, task_views=views,
                                        export_id=export_id), done)
        ctl.request_flush()
        return {"started": True}

    @br.command("export.validate")
    def validate(p):
        from ....curation import export as export_mod
        folder = ctl.export_folder
        if not folder:
            B.refuse("choose_folder")
        if ctl.exports_running.get(folder) or folder in ctl.exports_unknown:
            B.refuse("export_running_or_unknown")
        ctl.export_validation = {"folder": folder, "state": "validating"}

        def done(report, err, current):
            if not current:
                return  # a newer Validate or Export owns the result
            if err is not None:
                ctl.export_validation = {"folder": folder, "state": "failed",
                                         "type": type(err).__name__}
            else:
                ctl.export_validation = {
                    "folder": folder, "state": "done",
                    "valid": bool(report.get("valid")),
                    "issues": list(report.get("issues") or ())[:50],
                    "counts": report.get("counts")}
            ctl.request_flush()
        ctl.background.run("validate",
                           lambda: export_mod.validate_dataset(folder), done)
        ctl.request_flush()
        return {"started": True}

    def revoked(job_id):
        pend = ctl.training_annotation
        if pend is not None and pend.get("job_id") == job_id:
            ctl.training_annotation = None
    ctl._revoke_hooks.append(revoked)


def _folder_panel():
    from AppKit import NSOpenPanel
    panel = NSOpenPanel.openPanel()
    panel.setCanChooseDirectories_(True)
    panel.setCanChooseFiles_(False)
    panel.setCanCreateDirectories_(True)
    panel.setAllowsMultipleSelection_(False)
    panel.setPrompt_("Choose")
    if panel.runModal() != 1 or not panel.URLs():
        return None
    return str(panel.URLs()[0].path())


# ---- read model -----------------------------------------------------------------------


def _example_row(e):
    return {k: e.get(k) for k in (
        "example_id", "job_id", "captured_at_utc", "time_quality", "state",
        "families", "correctness", "pinned")} | {
        "audio": {"available": bool((e.get("audio") or {}).get("available")),
                  "reason": (e.get("audio") or {}).get("reason")},
        "annotations": len(e.get("annotations") or ())}


def models_model(ctl):
    st = ctl.state
    v = st.views["models"]
    data = v.get("data")
    sub = v.get("subview", "engines")
    tab = v.get("training_tab", "evidence")
    out = {"loading": bool(v.get("loading")), "error": v.get("error"),
           "subview": sub, "training_tab": tab,
           "search": v.get("search") or "",
           "note": ctl.notes.get("review"),
           "export_note": ctl.notes.get("export"),
           "running": sorted(k for k in ctl.background.running
                             if k in ("mine", "export", "validate")),
           "data": None}
    caps = ctl.spec.get("capabilities")
    if callable(caps):
        try:
            caps = caps()
        except Exception:
            caps = None
    if sub == "engines":
        eng = (data or {}).get("engine") if data else None
        out["data"] = None if eng is None else {
            "engine": eng, "capabilities": _caps(caps)}
        return out
    if data is None or data.get("training_tab") != tab:
        return out
    readiness = data.get("readiness") or {}
    cov = readiness.get("dataset_coverage") or {}
    d = {"readiness": {
        "examples_by_state": readiness.get("examples_by_state"),
        "storage_bytes": readiness.get("storage_bytes"),
        "consent_state": readiness.get("consent_state"),
        "infrastructure_ready": readiness.get("infrastructure_ready"),
        "coverage": {k: cov.get(k) for k in (
            "retained_audio_examples", "verbatim_reviewed_examples",
            "span_annotations", "unreviewed_outcomes",
            "explicitly_correct")}}}
    if tab == "evidence":
        detail = v.get("detail") if v.get("detail_key") == \
            v.get("selected_id") else None
        d["examples"] = [_example_row(e) for e in data.get("examples") or ()]
        d["selected_id"] = v.get("selected_id")
        d["listened_for"] = v.get("listened_for")
        d["detail_loading"] = bool(v.get("detail_loading"))
        d["detail_error"] = v.get("detail_error")
        d["detail"] = None if detail is None else {
            **_example_row(detail),
            "token": ctl.token_for("models", detail),
            "stages": [{k: s.get(k) for k in ("stage", "label", "available",
                                              "text", "reason")}
                       for s in detail.get("stages") or ()],
            "cleanup_path": detail.get("cleanup_path"),
            "outcome": detail.get("outcome"),
            "context": _context(detail.get("context_block")),
            "revisions": len(detail.get("revision_chain") or ()),
            "annotations_detail": [
                {k: a.get(k) for k in ("kind", "coverage", "stage",
                                       "created_at_utc", "listened_audio")}
                for a in detail.get("annotations") or ()]}
    elif tab == "review":
        queue = data.get("queue")
        pairs = data.get("preference_pairs")
        approved = data.get("approved")
        d["queue_token"] = _list_token(ctl, "queue", queue)
        d["pairs_token"] = _list_token(ctl, "preference_pairs", pairs)
        d["approved_token"] = _list_token(ctl, "approved", approved)
        d["queue"] = [{k: r.get(k) for k in (
            "candidate_id", "example_id", "job_id", "kind", "source",
            "candidate_status", "suggestion", "classification", "labeled")}
            for r in queue or ()]
        d["coverage"] = data.get("coverage")
        d["pairs"] = [{
            "task_key": x.get("task_key"), "source_text": x.get("source_text"),
            "judgment": x.get("comparable_judgment"),
            "candidates": [{k: c.get(k) for k in (
                "candidate_id", "transform_id", "path", "display_order",
                "text")} for c in sorted(
                x.get("candidates") or (),
                key=lambda c: c.get("display_order") or 0)
                if c.get("text") is not None][:2]}
            for x in pairs or ()]
        d["approved"] = list(approved or ())
    elif tab == "splits":
        d["summary"] = data.get("summary")
        d["families"] = list(data.get("families") or ())[:60]
        d["contamination"] = data.get("contamination")
    else:
        from ....curation.export import TASK_VIEWS
        last = data.get("last_export")
        d["views"] = list(TASK_VIEWS)
        d["last_export"] = None if not last else {k: last.get(k) for k in (
            "export_id", "state", "task_views", "examples_count",
            "excluded_count", "error", "created_at_utc", "finalized_at_utc",
            "fingerprint")}
        d["folder"] = ctl.export_folder
        d["folder_busy"] = bool(ctl.export_folder and (
            ctl.exports_running.get(ctl.export_folder)
            or ctl.export_folder in ctl.exports_unknown))
        val = ctl.export_validation
        d["validation"] = val if val and val.get("folder") == \
            ctl.export_folder else None
    out["data"] = d
    return out


def _list_token(ctl, kind, obj):
    if obj is None:
        return None
    return ctl.token_for(f"models.{kind}", obj)


def _context(block):
    if not block:
        return None
    dest = block.get("destination") or {}
    return {"present": bool(block.get("present")),
            "reason": block.get("reason"),
            "app": dest.get("app_name"), "category": dest.get("category"),
            "field_omission_reason": dest.get("field_omission_reason")}


def _caps(caps):
    if not isinstance(caps, dict):
        return None
    return {"adapter": caps.get("adapter"), "model_id": caps.get("model_id"),
            "model_revision": caps.get("model_revision"),
            "capabilities": {k: {"supported": bool((c or {}).get("supported")),
                                 "reason": (c or {}).get("reason")}
                             for k, c in (caps.get("capabilities")
                                          or {}).items()}}


READ_MODELS = {"models": models_model}
