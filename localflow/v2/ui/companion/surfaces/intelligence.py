"""Typed Hub commands for prompt authoring; no external insertion authority.

Integrator wiring: import this module in surfaces.register_all and append
``intelligence`` to its registration loop. Supply spec['intelligence_service'].
"""

from __future__ import annotations

import datetime
import json
import tempfile
import time
from pathlib import Path
from zoneinfo import ZoneInfo

from .. import bridge as B
from ..bridge import Bool, Enum, Int, List, Nullable, Obj, Str
from ....transforms.authoring import TEXT_FIELDS
from ....transforms.conversations import fingerprint


EXAMPLE = Obj({"before": Str(max_len=12000, allow_empty=False),
               "after": Str(max_len=12000, allow_empty=False)})
DRAFT = Obj({**{k: Str(max_len=n, allow_empty=(k == "description"))
                for k, n in TEXT_FIELDS.items()},
             "examples": List(EXAMPLE, max_items=6)})
CHOICE = {"model": Str(max_len=100, optional=True),
          "reasoning": Str(max_len=20, optional=True)}
SCOPE = {"project_id": Nullable(Str(max_len=200), optional=True),
         "use_memory": Bool(optional=True),
         "excluded_context_ids": List(Str(max_len=200), max_items=32, optional=True),
         "pinned_context_ids": List(Str(max_len=200), max_items=32, optional=True)}
DEPTH = Enum(("auto", "compact", "thorough"), optional=True)
SESSION = {"session_id": Str(max_len=100, allow_empty=False),
           "expected_revision": Int(lo=1)}


def _failed(exc):
    if isinstance(exc, B.Outcome):
        raise exc
    if isinstance(exc, TimeoutError):
        B.unknown("store_outcome_unknown")
    if isinstance(exc, ValueError):
        reason = str(exc)
        if reason.startswith("stale_"):
            B.stale(reason)
        B.refuse(reason if reason.isidentifier() else "invalid_request")
    raise exc


def register(ctl):
    def service():
        value = ctl.spec.get("intelligence_service")
        if value is None:
            B.unavailable("intelligence_unavailable")
        return value

    def command(name, fields, action):
        def handler(payload):
            try:
                return action(service(), payload)
            except Exception as exc:
                _failed(exc)
        ctl.bridge.add(name, fields, handler)

    command("intelligence.job", {"job_id": Str(max_len=100),
            "after_sequence": Int(lo=0, optional=True)},
            lambda s, p: s.read_job(**p))
    command("intelligence.cancel", {"job_id": Str(max_len=100)},
            lambda s, p: s.jobs.cancel(**p))
    inspection = {"transform_id": Str(max_len=200, optional=True),
                  "definition": Obj(DRAFT.fields, optional=True),
                  "source": Str(max_len=12000, optional=True),
                  "depth": DEPTH, **CHOICE, **SCOPE}
    command("transforms.inspect", inspection, lambda s, p: s.inspect_job(**p))

    def copy_text(text):
        coordinator = getattr(ctl, "coordinator", None)
        if coordinator is None or not hasattr(coordinator, "hubCopyText"):
            B.unavailable("clipboard_unavailable")
        outcome = coordinator.hubCopyText(text) or {}
        if outcome.get("outcome") == "clipboard_busy":
            B.refuse("clipboard_busy")
        return {"outcome": "copied"}
    def copy_inspection(s, payload):
        request = dict(payload)
        inspection_id = request.pop("inspection_id", None)
        if inspection_id:
            if request:
                raise ValueError("choose_one_inspection")
            text = s.inspection_for_copy(inspection_id)
        else:
            if (request.get("project_id") or request.get("use_memory") or
                    request.get("pinned_context_ids") or request.get("excluded_context_ids")):
                raise ValueError("load_inspection_before_copy")
            text = s.inspect(**request)["system"]
        return copy_text(text)
    inspection_copy_fields = {**inspection, "inspection_id": Str(max_len=100, optional=True)}
    command("transforms.copy_inspection", inspection_copy_fields, copy_inspection)
    command("transforms.preview", {"source": Str(max_len=12000, allow_empty=False),
            "transform_id": Str(max_len=200, optional=True),
            "definition": DRAFT.__class__(DRAFT.fields, optional=True),
            "depth": DEPTH, **CHOICE, **SCOPE}, lambda s, p: s.preview(**p))
    command("transforms.author", {"intention": Str(max_len=8000, allow_empty=False),
            "definition": Obj(DRAFT.fields, optional=True),
            "examples": List(EXAMPLE, max_items=6, optional=True), **CHOICE, **SCOPE},
            lambda s, p: s.author(**p))
    command("transforms.author_refine", {"draft_id": Str(max_len=100),
            "expected_revision": Int(lo=1), "instruction": Str(max_len=8000, allow_empty=False),
            "definition": Obj(DRAFT.fields, optional=True),
            **CHOICE}, lambda s, p: s.author_refine(**p))

    def save(s, payload):
        out = s.save_authored(**payload)
        ctl.state.reload_transforms()
        return out
    command("transforms.save_authored", {"draft_id": Nullable(Str(max_len=100)),
            "definition": Obj(DRAFT.fields, optional=True),
            "expected_revision": Int(lo=0), "operation_id": Str(max_len=100, allow_empty=False)}, save)
    command("prompt_sessions.create", {"source": Str(max_len=12000, allow_empty=False),
            "operation_id": Str(max_len=100, allow_empty=False),
            "transform_id": Str(max_len=200, optional=True), "depth": DEPTH, **SCOPE},
            lambda s, p: s.create_session(**p))
    def pending_open(s, payload):
        coordinator = getattr(ctl, "coordinator", None)
        return coordinator.hubTakePromptSession() if coordinator is not None and \
            hasattr(coordinator, "hubTakePromptSession") else {"session_id": None}
    command("prompt_sessions.pending_open", {}, pending_open)
    command("prompt_sessions.refine", {**SESSION,
            "instruction": Str(max_len=8000, allow_empty=False), **CHOICE},
            lambda s, p: s.refine(**p))
    command("prompt_sessions.edit", {**SESSION,
            "prompt": Str(max_len=12000, allow_empty=False)}, lambda s, p: s.edit(**p))
    command("prompt_sessions.select_revision", {**SESSION, "revision_id": Int(lo=1)},
            lambda s, p: s.select_revision(**p))
    command("prompt_sessions.set_policy", {**SESSION, **SCOPE, "depth": DEPTH},
            lambda s, p: s.set_session_policy(**p))
    command("prompt_sessions.clear", SESSION, lambda s, p: s.clear_session(**p))
    command("prompt_sessions.list", {"session_id": Str(max_len=100, optional=True)},
            lambda s, p: s.session_view(p["session_id"]) if p.get("session_id")
            else {"sessions": s.sessions.list()})
    command("prompt_sessions.copy", {"session_id": Str(max_len=100),
            "expected_revision": Int(lo=1)}, lambda s, p: copy_text(_copy(s, p)["prompt"]))
    def apply(s, payload):
        coordinator = getattr(ctl, "coordinator", None)
        if coordinator is None or not hasattr(coordinator, "hubApplyPrompt"):
            B.unavailable("destination_unavailable")
        return coordinator.hubApplyPrompt(**payload)
    command("prompt_sessions.apply", {**SESSION, "revision_id": Int(lo=1),
            "reacquire_target": Bool()}, apply)
    command("prompt_sessions.cancel", {"job_id": Str(max_len=100)},
            lambda s, p: s.jobs.cancel(**p))
    suggestion_filter = {"project_id": Nullable(Str(max_len=200), optional=True),
                         "kind": Enum(("general", "personalized"), optional=True)}
    command("suggestions.list", suggestion_filter,
            lambda s, p: {"suggestions": s.suggestions.list(**p)})
    command("suggestions.refresh", suggestion_filter,
            lambda s, p: s.jobs.start("suggestions", lambda ctx: ctx.publish(
                lambda: {"suggestions": s.suggestions.refresh(**p)}), priority=10))
    command("suggestions.dismiss", {"suggestion_id": Str(max_len=100),
            "permanent": Bool(optional=True)}, lambda s, p: s.suggestions.dismiss(**p))
    _register_memory(ctl, service)


def _copy(service, payload):
    session = service.session_for_use(payload['session_id'], payload['expected_revision'])
    return {"prompt": session["prompt"], "revision": session["revision"]}


def _record_view(record):
    out = dict(record)
    if out.get("kind") == "alias":
        out["kind"] = "terminology"
    for key in ("created_at", "updated_at", "last_observed_at", "last_confirmed_at",
                "valid_from", "valid_until"):
        if isinstance(out.get(key), (int, float)):
            out[key] = datetime.datetime.fromtimestamp(
                out[key], ZoneInfo("America/New_York")).isoformat()
    return out


def _register_memory(ctl, intelligence):
    """Adapt the memory domain's explicit public operations to bounded Hub data."""
    def command(name, fields, action):
        def handler(payload):
            memory = ctl.spec.get("memory_service")
            if memory is None:
                B.unavailable("memory_unavailable")
            try:
                return action(memory, payload)
            except Exception as exc:
                _failed(exc)
        ctl.bridge.add(name, fields, handler)

    kinds = ("preference", "project_fact", "workflow", "terminology", "note",
             "decision", "volatile", "historical_claim")
    filters = {"project_id": Nullable(Str(max_len=200), optional=True),
               "kind": Nullable(Enum(kinds), optional=True),
               "status": Nullable(Enum(("active", "proposed", "disputed", "stale",
                                         "superseded", "forgotten")), optional=True),
               "limit": Int(lo=1, hi=200, optional=True)}

    def listing(memory, payload, selected=None):
        rows = memory.list(project_id=payload.get("project_id"),
                           status=payload.get("status"), limit=payload.get("limit", 100))
        rows = [_record_view(r) for r in rows if selected is None or r["id"] in selected]
        if payload.get("kind"):
            rows = [r for r in rows if r["kind"] == payload["kind"]]
        return {"memories": rows, "learning_enabled": memory.learning()}

    command("memories.list", filters, listing)

    def embedding_status(memory, payload):
        return memory.embedding.status()
    command("memories.embedding_status", {}, embedding_status)

    def setup_embedding(memory, payload):
        def work(ctx):
            from ....memory.embeddings import MiniLMEmbedding
            # The target is host-owned cache state, never a WebView-supplied path.
            previous = memory.embedding
            last = [0.0]

            def progress(name, received, total):
                ctx.check()
                now = time.monotonic()
                if received and now - last[0] < .1 and received != total:
                    return
                last[0] = now
                label = 'search model' if name == 'model.onnx' else 'search data'
                amount = f'{received / 1_000_000:.1f} MB'
                if total:
                    amount = f'{received * 100 // total}% · {amount} of {total / 1_000_000:.1f} MB'
                ctx.progress(f'Downloading {label} · {amount}')

            ctx.progress('Preparing semantic search')

            def validate(model_dir):
                ctx.check()
                ctx.progress('Checking semantic search locally')
                candidate = MiniLMEmbedding(model_dir)
                vector = candidate.encode('Local semantic search.', cancelled=ctx.cancelled)
                ctx.check()
                if candidate.unavailable_reason == 'local_embedding_runtime_unavailable':
                    raise ValueError(candidate.unavailable_reason)
                return candidate if vector is not None else None

            if previous.status()['installed']:
                candidate = validate(previous.model_dir)
                if candidate is not None:
                    ctx.publish(lambda: setattr(memory, 'embedding', candidate))
                    return candidate.status()
            # Repair incomplete/corrupt assets in LocalFlow's own cache. Never
            # overwrite a Hugging Face cache shared with other applications.
            target = MiniLMEmbedding.cache_dir()
            if target.is_symlink():
                raise ValueError('local_embedding_cache_is_symlink')
            target.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(prefix='.search-setup-', dir=target.parent) as temporary:
                staged = Path(temporary) / 'model'
                MiniLMEmbedding.download(staged, progress=progress, cancelled=ctx.cancelled)
                candidate = validate(staged)
                if candidate is None:
                    raise ValueError('local_embedding_model_unavailable')
                backup = Path(temporary) / 'previous'

                def publish():
                    if target.exists():
                        target.rename(backup)
                    try:
                        staged.rename(target)
                    except OSError:
                        if backup.exists():
                            backup.rename(target)
                        raise
                    candidate.model_dir = target
                    memory.embedding = candidate
                # Inference may still reference the old cache paths. Wait away
                # from AppKit, then make the two-file generation visible together.
                while not previous._lock.acquire(timeout=.1):
                    ctx.check()
                try:
                    ctx.publish(publish)
                finally:
                    previous._lock.release()
                return candidate.status()
        return intelligence().jobs.start('semantic_search_setup', work, priority=0)
    command("memories.setup_embedding", {}, setup_embedding)

    def search(memory, payload):
        def work(ctx):
            ctx.progress("searching_memories")
            pack = memory.search(payload["query"], project_id=payload.get("project_id"),
                                 limit=min(payload.get("limit", 5), 32))
            ctx.check()
            ctx.validators.append(lambda db: memory._assert_current(db, pack))
            return {**listing(memory, payload, {item.id for item in pack.items}),
                    "context": pack.to_dict()}
        return intelligence().jobs.start("memory_search", work, priority=0)
    command("memories.search", {**filters, "query": Str(max_len=8000, allow_empty=False)}, search)

    def remember(memory, payload):
        project = payload.get("scope_id")
        if (payload["scope_kind"] == "project") != (project is not None):
            B.refuse("invalid_memory_scope")
        record_id = "memory:ui:" + fingerprint(payload["operation_token"])[:32]
        kind = "alias" if payload["kind"] == "terminology" else payload["kind"]

        def existing():
            raw = memory._run(lambda db: db.execute(
                "SELECT data FROM memory_records WHERE id=?", (record_id,)).fetchone())
            if raw is None:
                return None
            record = json.loads(raw[0])
            if (record["text"], record["kind"], record["scope_id"]) != (
                    payload["text"], kind, project):
                B.refuse("operation_id_in_use")
            return {"memory": _record_view(record)}
        have = existing()
        if have is not None:
            return have
        try:
            return {"memory": _record_view(memory.remember(
                payload["text"], kind=kind, project_id=project, record_id=record_id))}
        except ValueError as exc:
            if str(exc) == "memory_id_in_use":
                return existing()
            raise
    command("memories.remember", {"text": Str(max_len=8000, allow_empty=False),
            "kind": Enum(kinds), "scope_kind": Enum(("personal", "project")),
            "scope_id": Nullable(Str(max_len=200)),
            "operation_token": Str(max_len=100, allow_empty=False)}, remember)

    def update(memory, payload):
        changes = dict(payload["changes"])
        if changes.pop("status", None) == "active" and not changes.get("confirm"):
            B.refuse("confirmation_required")
        return {"memory": _record_view(memory.update(payload["memory_id"],
            expected_revision=payload["expected_revision"], **changes))}
    command("memories.update", {"memory_id": Str(max_len=100),
            "expected_revision": Int(lo=1), "changes": Obj({
                "text": Str(max_len=8000, allow_empty=False, optional=True),
                "user_pinned": Bool(optional=True), "retrieval_enabled": Bool(optional=True),
                "confirm": Bool(optional=True), "status": Enum(("active",), optional=True)})}, update)

    def forget(memory, payload):
        if payload.get("all") is True:
            if "memory_id" in payload or "expected_revision" in payload:
                B.refuse("choose_one_memory_target")
            memory.forget_all()
        else:
            if "memory_id" not in payload or "expected_revision" not in payload:
                B.refuse("memory_target_required")

            def op(db):
                row = db.execute("SELECT revision FROM memory_records WHERE id=?",
                                 (payload["memory_id"],)).fetchone()
                if row is None:
                    raise ValueError("memory_not_found")
                if row[0] != payload["expected_revision"]:
                    raise ValueError("stale_revision")
                memory._forget_db(db, payload["memory_id"])
            memory._run(op)
        return {"forgotten": True}
    command("memories.forget", {"memory_id": Str(max_len=100, optional=True),
            "expected_revision": Int(lo=1, optional=True), "all": Bool(optional=True)}, forget)
    command("memories.set_learning", {"enabled": Bool()},
            lambda m, p: {"learning_enabled": m.set_learning(p["enabled"])})
    command("memories.exclude", {"kind": Enum(("source", "project", "app")),
            "value": Str(max_len=300, allow_empty=False)},
            lambda m, p: {"excluded": m.exclude(**p) is None})
    command("context.projects", {}, lambda m, p: {"projects": m.projects()})

    def create_project(memory, payload):
        from ....memory.sources import approved_root
        roots = [str(approved_root(root)) for root in payload["roots"]]
        if not roots:
            B.refuse("project_root_required")
        project_id = memory.create_project(payload["name"], roots[0])
        for root in roots[1:]:
            project = next(p for p in memory.projects() if p["id"] == project_id)
            memory.approve_root(project_id, root, expected_revision=project["revision"])
        if payload.get("brief", "").strip():
            rid = "memory:brief:" + fingerprint(payload["operation_token"])[:32]
            old = memory._run(lambda db: db.execute(
                "SELECT id FROM memory_records WHERE id=?", (rid,)).fetchone())
            if old is None:
                memory.remember(payload["brief"], kind="project_fact", project_id=project_id,
                                subject="project", key="project_brief", record_id=rid,
                                user_pinned=True)
        return {"project_id": project_id, "projects": memory.projects()}
    command("context.create_project", {"name": Str(max_len=160, allow_empty=False),
            "roots": List(Str(max_len=2000, allow_empty=False), max_items=8),
            "brief": Str(max_len=8000, optional=True),
            "operation_token": Str(max_len=100, allow_empty=False)}, create_project)

    def import_files(memory, payload):
        def work(ctx):
            ctx.progress("importing_selected_files")
            records = memory.import_files(payload["project_id"], payload["paths"])
            ctx.check()
            ctx.progress("indexing_approved_context")
            memory.index_pending(project_id=payload["project_id"], cancelled=ctx.cancelled)
            return {"imported": len(records), "memories": [_record_view(r) for r in records]}
        return intelligence().jobs.start("context_import", work, priority=10)
    command("context.import_files", {"project_id": Str(max_len=200),
            "paths": List(Str(max_len=2000, allow_empty=False), max_items=16)}, import_files)

    def preview(memory, payload):
        def work(ctx):
            ctx.progress("retrieving_context")
            service = intelligence()
            policy = service._policy(**{k: v for k, v in payload.items() if k != "query"})
            pack = service._context(payload["query"], policy)
            ctx.check()
            ctx.validators.append(lambda db: service.validate_pack(db, pack))
            return pack
        return intelligence().jobs.start("context_preview", work, priority=0)
    command("context.preview", {"query": Str(max_len=8000, allow_empty=False),
            **SCOPE, "depth": DEPTH}, preview)
