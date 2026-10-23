"""Native prompt workspace, production previews, authoring and suggestions.

This service has no insertion or shell authority. Context assembly/eligibility
are supplied by the memory domain, and the Store remains the only SQL writer.
"""

from __future__ import annotations

import inspect
import json
import time
import dataclasses

from . import claude, engine, prompts
from .authoring import AuthoringDrafts, AuthoringLoop, executable_definition
from .conversations import (INTELLIGENCE_MIGRATIONS, PromptSessions, bounded_text,
                            encode, fingerprint, submit)
from .definitions import TransformDefinition
from .jobs import IntelligenceJobs


def memory_callbacks(memory):
    """Bind the memory domain's frozen packs to the existing writer transaction."""
    from ..memory.models import ContextItem, ContextPack, EvidenceRef
    from ..memory.sources import eligibility
    from ..memory.store import _source as read_source

    def sources_valid(db, references):
        for ref in references:
            record = read_source(db, ref["source_id"])
            if (not record or record["revision"] != ref["source_revision"] or
                    not memory._source_current(db, record) or
                    not eligibility(record, automatic=True)[0]):
                return False
        return True

    def patterns(project_id):
        if not memory.learning():
            return []

        def read(db):
            observations, seen = [], set()
            rows = db.execute("SELECT id FROM memory_sources WHERE status='active'"
                              " AND project_id IS ? ORDER BY id LIMIT 1000", (project_id,))
            for (source_id,) in rows:
                record = read_source(db, source_id)
                independent = record.get("independent_key") or source_id
                if independent in seen or not sources_valid(db, [{
                        "source_id": source_id, "source_revision": record["revision"]}]):
                    continue
                seen.add(independent)
                observations.append({"source_id": source_id,
                    "source_revision": record["revision"], "project_id": project_id,
                    "author_role": "user", "eligible": True, "text": record["text"],
                    "independent_key": independent,
                    "corrected": record.get("kind") == "manual_correction"})
            return observations
        return memory._run(read)

    def assemble(*, query, project_id, use_memory, purpose,
                 excluded_context_ids=(), pinned_context_ids=()):
        budget = 12000 if purpose in ("authoring", "refinement") else 6000
        pack = memory.search(query, project_id=project_id, include_personal=use_memory,
                             enabled=bool(project_id or use_memory), token_budget=budget)
        excluded = set(excluded_context_ids)
        pinned = []
        if pinned_context_ids:
            clause, params = memory._live_query(project_id, use_memory)

            def read(db):
                rows = []
                for item_id in pinned_context_ids:
                    row = db.execute("SELECT m.data FROM memory_records m WHERE m.id=? AND "
                                     + clause, (item_id, *params)).fetchone()
                    if row is None:
                        raise ValueError("pinned_context_unavailable")
                    rows.append(json.loads(row[0]))
                return rows
            for record in memory._run(read):
                pinned.append(ContextItem(record["id"], record["revision"], record["text"],
                    record["kind"], record["scope_id"], tuple(EvidenceRef(**r)
                    for r in record["evidence_refs"]), "pinned_by_user", record["updated_at"],
                    record["confidence_label"]))
        selected, used, seen = [], 0, set()
        omitted = list(pack.omitted)
        for item in [*pinned, *pack.items]:
            if item.id in excluded:
                omitted.append((item.id, "excluded_by_user"))
                continue
            if item.id in seen:
                continue
            cost = len(item.text.encode("utf-8")) + 96
            if used + cost > budget:
                if item.id in pinned_context_ids:
                    raise ValueError("pinned_context_over_limit")
                omitted.append((item.id, "context_budget"))
                continue
            used += cost
            selected.append(item)
            seen.add(item.id)
        pack = dataclasses.replace(pack, items=tuple(selected), omitted=tuple(omitted))
        memory.assert_current(pack)
        return pack.to_dict()

    def validate(db, value):
        if not value:
            return True
        try:
            return bool(memory._assert_current(db, ContextPack.from_dict(value)))
        except ValueError:
            return False

    def current(value):
        if not value:
            return True
        try:
            return bool(memory.assert_current(ContextPack.from_dict(value)))
        except ValueError:
            return False
    return {"assemble_context": assemble, "validate_pack": validate, "pack_valid": current,
            "learning_enabled": memory.learning, "patterns": patterns,
            "sources_valid": sources_valid}


def _general(key, name, purpose, when, before, after, instruction, terms):
    return {"suggestion_id": "general:" + key, "category": key, "name": name,
            "purpose": purpose, "when_useful": when, "before": before,
            "after": after, "instructions": instruction, "terms": terms,
            "personalized": False, "evidence": [], "reason": "General suggestion"}


GENERAL_SUGGESTIONS = (
    _general("research", "Research brief", "Turn a question into a verifiable research brief.",
             "Comparisons with uncertain claims or changing facts.",
             "Compare two note-taking approaches.",
             "Compare the two approaches using dated evidence, practical criteria, and labeled unknowns.",
             "Frame a research request with evidence standards, useful comparison criteria and clear unknowns. Preserve scope; do not answer it.",
             ("research", "compare", "evidence", "sources")),
    _general("bug_report", "Reproducible bug report", "Separate symptoms, reproduction steps and expected behavior.",
             "Rough debugging notes need a useful report.",
             "The editor loses my draft after switching tabs.",
             "Report: switching tabs loses the current draft. Expected: preserve it. Include known reproduction steps and label missing environment details.",
             "Convert notes into a bug report with observed symptoms, known reproduction steps, expected behavior and unknowns. Never invent steps, versions or a diagnosis.",
             ("bug", "debug", "crash", "reproduce", "error")),
    _general("read_only", "Read-only investigation", "Create a diagnosis request with an explicit change boundary.",
             "An issue needs investigation before implementation.",
             "Find why search stalls. Don't edit yet.",
             "Investigate why search stalls. Gather relevant evidence, distinguish causes from hypotheses, and report findings. Do not edit or execute changes.",
             "Write an investigation-only prompt. Preserve no-change and no-execution limits, ask for evidence and distinguish hypotheses from established causes.",
             ("investigate", "diagnose", "read-only", "audit", "review")),
    _general("handoff", "Implementation handoff", "Make a scoped task usable in a fresh work session.",
             "Work needs clear inputs, ownership and verification.",
             "Implement the agreed search behavior.",
             "Implement the specified search behavior using the supplied requirements. State owned files, constraints and checks; preserve any unresolved decisions.",
             "Produce a self-contained implementation handoff from supplied facts. Preserve identifiers and constraints, name required inputs, and do not invent paths or implementation authority.",
             ("handoff", "implement", "worker", "session")),
    _general("study", "Study question", "Turn study notes into a focused learning request.",
             "A concept needs explanation and a check of understanding.",
             "Help me understand diffusion.",
             "Explain diffusion at the level implied by these notes, give an appropriate example, and offer a short understanding check.",
             "Create a focused study prompt. Preserve the learner's stated level and objective; ask for an example and a proportionate understanding check without inventing course requirements.",
             ("study", "learn", "explain", "exam", "concept")),
    _general("technical_message", "Technical update", "Make a technical update easy to act on.",
             "A message needs a clear finding and next action.",
             "The export failed; I need the missing format information.",
             "The export failed. Please provide the required format information so the next attempt can use it.",
             "Write a concise technical message with the supplied finding, impact and requested next action. Preserve uncertainty, tone and all factual details.",
             ("message", "update", "colleague", "status")),
    _general("bilingual", "Bilingual explanation", "Request an explanation across two named languages.",
             "Terminology or understanding needs two languages.",
             "Explain this term in English and Spanish.",
             "Explain the term in English and Spanish, preserving technical terminology and noting any meaning that does not translate directly.",
             "Write a bilingual explanation request using only the languages supplied. Preserve names and technical terms; do not assume a language pair or translate the task itself unless requested.",
             ("bilingual", "translate", "language", "translation")),
)


class Suggestions:
    def __init__(self, store, definitions, patterns, learning_enabled,
                 sources_valid, *, clock=time.time, cooldown_seconds=7 * 86400):
        self.store, self.definitions, self.patterns = store, definitions, patterns
        self.learning_enabled, self.sources_valid = learning_enabled, sources_valid
        self.clock, self.cooldown_seconds = clock, cooldown_seconds

    def refresh(self, project_id=None, kind=None):
        if kind not in (None, "general", "personalized"):
            raise ValueError("invalid_suggestion_kind")
        learning = self.learning_enabled()
        observations = self.patterns(project_id) if learning else []
        current = self.definitions()
        candidates = []
        for general in GENERAL_SUGGESTIONS:
            # Existing custom definitions are concrete evidence of a met need.
            if any(d.mode == "custom" and d.enabled and
                   (general["name"].casefold() == d.name.casefold() or
                    sum(t in (d.name + " " + d.description).casefold()
                        for t in general["terms"]) >= 2) for d in current):
                continue
            matching = {}
            for obs in observations[:1000]:
                if not isinstance(obs, dict) or not obs.get("source_id"):
                    continue
                if obs.get("author_role") != "user" or not obs.get("eligible", False):
                    continue
                if obs.get("project_id") != project_id:
                    continue
                text = str(obs.get("text", "")).casefold()
                if (obs.get("category") == general["category"] or
                        any(t in text for t in general["terms"])):
                    matching[obs.get("independent_key") or obs["source_id"]] = obs
            candidate = {k: v for k, v in general.items() if k != "terms"}
            if len(matching) >= 2:
                evidence = [{"source_id": o["source_id"],
                             "source_revision": o.get("source_revision", 1)}
                            for o in matching.values()]
                candidate.update(
                    suggestion_id="personal:" + fingerprint(
                        [project_id, general["category"]])[:24], personalized=True,
                    project_id=project_id, evidence=evidence,
                    reason=f"{len(evidence)} eligible user-authored observations"
                           " show this recurring workflow.",
                    recurrence=len(evidence),
                    friction=sum(bool(o.get("corrected") or o.get("rejected"))
                                 for o in matching.values()))
            else:
                candidate.update(recurrence=0, friction=0)
            candidates.append(candidate)
        candidates.sort(key=lambda c: (-c["recurrence"], -c["friction"], c["suggestion_id"]))

        def op(db):
            # Refresh replaces the ranked set for this scope. Old patterns may
            # still refer to valid sources while no longer being relevant.
            for sid, payload in db.execute("SELECT suggestion_id,candidate_json FROM"
                                            " intelligence_suggestions WHERE status='active'"):
                old = json.loads(payload)
                if not old.get("personalized") or old.get("project_id") == project_id:
                    db.execute("UPDATE intelligence_suggestions SET status='superseded'"
                               " WHERE suggestion_id=?", (sid,))
            for candidate in candidates:
                if candidate["evidence"] and not self.sources_valid(db, candidate["evidence"]):
                    continue
                same_workflow = (candidate["suggestion_id"],
                    "general:" + candidate["category"],
                    "personal:" + fingerprint([project_id, candidate["category"]])[:24])
                prior = db.execute("SELECT status,cooldown_until FROM"
                                   " intelligence_suggestions WHERE suggestion_id IN (?,?,?)",
                                   same_workflow).fetchall()
                if any(status == "dismissed_forever" or (until or 0) > self.clock()
                       for status, until in prior):
                    continue
                db.execute("INSERT INTO intelligence_suggestions VALUES(?,?,?,'active',NULL,?)"
                           " ON CONFLICT(suggestion_id) DO UPDATE SET"
                           " candidate_json=excluded.candidate_json,"
                           "evidence_json=excluded.evidence_json,status='active',"
                           "cooldown_until=NULL,updated_at=excluded.updated_at",
                           (candidate["suggestion_id"], encode(candidate),
                            encode(candidate["evidence"]), str(self.clock())))
            return self._list(db, project_id, learning, kind)
        return submit(self.store, op)

    def _list(self, db, project_id, learning, kind=None):
        active = []
        for sid, payload, evidence in db.execute(
                "SELECT suggestion_id,candidate_json,evidence_json FROM"
                " intelligence_suggestions WHERE status='active'"):
            candidate, refs = json.loads(payload), json.loads(evidence)
            if refs and not self.sources_valid(db, refs):
                db.execute("UPDATE intelligence_suggestions SET status='revoked',"
                           "candidate_json='{}',evidence_json='[]' WHERE suggestion_id=?",
                           (sid,))
                continue
            if candidate.get("personalized") and (not learning or
                    candidate.get("project_id") != project_id):
                continue
            if kind is not None and bool(candidate.get("personalized")) != (kind == "personalized"):
                continue
            active.append(candidate)
        active.sort(key=lambda c: (-c.get("recurrence", 0), -c.get("friction", 0),
                                   c["suggestion_id"]))
        return active[:3]

    def list(self, project_id=None, kind=None):
        if kind not in (None, "general", "personalized"):
            raise ValueError("invalid_suggestion_kind")
        learning = self.learning_enabled()
        out = submit(self.store, lambda db: self._list(db, project_id, learning, kind))
        return out or self.refresh(project_id, kind)

    def dismiss(self, suggestion_id, permanent=False):
        def op(db):
            row = db.execute("SELECT 1 FROM intelligence_suggestions WHERE"
                             " suggestion_id=?", (suggestion_id,)).fetchone()
            if row is None:
                raise ValueError("suggestion_not_found")
            db.execute("UPDATE intelligence_suggestions SET status=?,cooldown_until=?,"
                       "updated_at=? WHERE suggestion_id=?",
                       ("dismissed_forever" if permanent else "dismissed",
                        None if permanent else self.clock() + self.cooldown_seconds,
                        str(self.clock()), suggestion_id))
            return {"dismissed": True}
        return submit(self.store, op)


class IntelligenceService:
    def __init__(self, store, transforms, transformer, *, assemble_context=None,
                 validate_pack=None, pack_valid=None, patterns=None,
                 learning_enabled=None, sources_valid=None, background_allowed=None):
        self.store, self.transforms, self.transformer = store, transforms, transformer
        self.sessions = PromptSessions(store)
        self.drafts = AuthoringDrafts(store, transforms)
        self.assemble_context = assemble_context
        self.validate_pack = validate_pack or (lambda db, pack: not bool(pack))
        self.pack_valid = pack_valid or (lambda pack: not bool(pack))
        self.patterns = patterns or (lambda project_id: [])
        self.suggestions = Suggestions(
            store, transforms.definitions, self.patterns,
            learning_enabled or (lambda: False),
            sources_valid or (lambda db, refs: not bool(refs)))
        self.jobs = IntelligenceJobs(store, background_allowed=background_allowed or (lambda: True))

    def close(self):
        self.jobs.close()

    @staticmethod
    def _policy(project_id=None, use_memory=False, depth="auto",
                excluded_context_ids=(), pinned_context_ids=()):
        if depth not in ("auto", "compact", "thorough") or type(use_memory) is not bool:
            raise ValueError("invalid_context_policy")
        if project_id is not None:
            bounded_text(project_id, 200)
        for values in (excluded_context_ids, pinned_context_ids):
            if not isinstance(values, (list, tuple)) or len(values) > 32:
                raise ValueError("invalid_context_items")
            for value in values:
                bounded_text(value, 200)
        if set(excluded_context_ids) & set(pinned_context_ids):
            raise ValueError("conflicting_context_items")
        return {"project_id": project_id, "use_memory": use_memory, "depth": depth,
                "excluded_context_ids": list(dict.fromkeys(excluded_context_ids)),
                "pinned_context_ids": list(dict.fromkeys(pinned_context_ids))}

    def _context(self, query, policy, purpose="transform"):
        if self.assemble_context is None:
            if policy["project_id"] or policy["use_memory"] or policy.get("pinned_context_ids"):
                raise ValueError("context_unavailable")
            return {}
        if policy["depth"] == "thorough" and purpose == "transform":
            purpose = "authoring"
        kwargs = {"query": query, "project_id": policy["project_id"],
                  "use_memory": policy["use_memory"], "purpose": purpose}
        for key in ("excluded_context_ids", "pinned_context_ids"):
            if policy.get(key):
                kwargs[key] = policy[key]
        pack = self.assemble_context(**kwargs)
        if hasattr(pack, "to_json"):
            pack = pack.to_json()
        elif hasattr(pack, "to_dict"):
            pack = pack.to_dict()
        if not isinstance(pack, dict) or len(encode(pack)) > 100000:
            raise ValueError("context_over_limit")
        if not self.pack_valid(pack):
            raise ValueError("context_revoked")
        return pack

    def _definition(self, transform_id):
        definition = self.transforms.definition(transform_id)
        if definition is None:
            raise ValueError("transform_not_found")
        return definition

    def _choice(self, definition, model=None, reasoning=None):
        if model is None and reasoning is None:
            choice = self.transforms.model_choice(definition.transform_id, definition.mode)
            model, reasoning = choice["model"], choice["reasoning"]
        if not claude.is_valid(model, reasoning):
            raise ValueError("unsupported_model_choice")
        return model, reasoning

    @staticmethod
    def _job(definition, source, *, pack, depth, followup="", constraints=()):
        kwargs = {"context_pack": pack or None, "depth": depth,
                  "followup": followup, "constraints": constraints}
        accepted = inspect.signature(engine.job_for_definition).parameters
        if not set(kwargs).issubset(accepted):
            if pack or depth != "auto" or followup or constraints:
                raise ValueError("compiler_upgrade_required")
            kwargs = {}
        return engine.job_for_definition(definition, source, source_kind="result", **kwargs)

    @staticmethod
    def _request(job):
        kwargs = {"custom_instruction": job.instructions, "examples": job.examples}
        for key in ("context_pack", "depth", "followup", "constraints"):
            if hasattr(job, key):
                kwargs[key] = getattr(job, key)
        system, messages = prompts.build_request(job.mode, job.source, **kwargs)
        return {"system": system, "messages": messages, "schema": prompts.schema_for(job.mode)}

    def inspect(self, transform_id=None, source="", definition=None, *, model=None,
                reasoning=None, project_id=None, use_memory=False, depth="auto",
                excluded_context_ids=(), pinned_context_ids=()):
        bounded_text(source, empty=True)
        if (transform_id is None) == (definition is None):
            raise ValueError("choose_one_definition")
        policy = self._policy(project_id, use_memory, depth, excluded_context_ids, pinned_context_ids)
        if not source.strip() and (project_id or use_memory or pinned_context_ids):
            raise ValueError("sample_required_for_context")
        definition = executable_definition(definition) if definition is not None else self._definition(transform_id)
        model, reasoning = self._choice(definition, model, reasoning)
        pack = self._context(source, policy)
        job = self._job(definition, source, pack=pack, depth=depth)
        return {"definition": definition.to_json(), **self._request(job),
                "model": model, "reasoning": reasoning, "context": pack,
                "policy": policy, "depth": depth, "task_key": job.task_key(),
                "template_only": not source.strip()}

    def inspect_job(self, **payload):
        def work(ctx):
            ctx.progress("retrieving_context")
            compiled = self.inspect(**payload)
            ctx.check()
            ctx.validators.append(lambda db: self.validate_pack(db, compiled["context"]))
            return {**compiled, "inspection_id": ctx.job_id}
        return self.jobs.start("inspection", work, priority=0,
            manifest={"source_hash": fingerprint(payload.get("source", "")),
                      "settings_hash": fingerprint({k: v for k, v in payload.items() if k != "source"})})

    def inspection_for_copy(self, inspection_id):
        job = self.read_job(inspection_id)
        if job.get("phase") == "context_revoked":
            raise ValueError("context_revoked")
        compiled = job.get("result") or {}
        if (job["status"] != "succeeded" or compiled.get("inspection_id") != inspection_id
                or not isinstance(compiled.get("system"), str)):
            raise ValueError("inspection_not_ready")
        return compiled["system"]

    def _run_preview(self, definition, source, policy, ctx, *, model=None,
                     reasoning=None, followup="", constraints=(), pack=None, budget=None,
                     source_contexts=()):
        bounded_text(source)
        def source_current():
            return all(self.pack_valid(value) for value in source_contexts)
        if not source_current():
            raise ValueError('context_revoked')
        ctx.progress("retrieving_context")
        pack = self._context(source, policy) if pack is None else pack
        ctx.validators.append(lambda db: self.validate_pack(db, pack))
        ctx.validators.append(lambda db: all(self.validate_pack(db, value) for value in source_contexts))
        model, reasoning = self._choice(definition, model, reasoning)
        request_pack = pack
        if source_contexts:
            request_pack = {**pack, 'source_context_fingerprints': list(dict.fromkeys(
                fingerprint(value) for value in source_contexts))}
        job = self._job(definition, source, pack=request_pack, depth=policy["depth"],
                        followup=followup, constraints=constraints)
        request = self._request(job)
        ctx.progress("generating_preview")
        bounds = {"request_guard": budget.before_request,
                  "response_observer": budget._account} if budget is not None else {}
        result = self.transformer.run(job, model=model, reasoning=reasoning,
            context_current=lambda _pack: self.pack_valid(pack) and source_current(),
            cancelled=lambda: ctx.cancelled(), **bounds)
        if budget is not None and budget.failure:
            raise ValueError(budget.failure)
        ctx.check()
        if not self.pack_valid(pack) or not source_current():
            raise ValueError("context_revoked")
        if result.path == engine.PATH_FALLBACK_ORIGINAL:
            reason = result.reason or "preview_failed"
            raise ValueError(reason.replace(":", "_"))
        return {"output": result.output, "path": result.path, "reason": result.reason,
                "validation": result.to_json(), "request": request,
                "requested_model": model, "requested_reasoning": reasoning,
                "served_model": result.model, "model": result.model,
                "input_tokens": result.input_tokens, "output_tokens": result.output_tokens,
                "duration_ms": result.duration_ms, "context": pack,
                "task_key": job.task_key()}

    def preview(self, source, *, transform_id=None, definition=None, model=None,
                reasoning=None, project_id=None, use_memory=False, depth="auto",
                excluded_context_ids=(), pinned_context_ids=()):
        bounded_text(source)
        if (transform_id is None) == (definition is None):
            raise ValueError("choose_one_definition")
        defn = executable_definition(definition) if definition is not None else self._definition(transform_id)
        policy = self._policy(project_id, use_memory, depth, excluded_context_ids, pinned_context_ids)
        model, reasoning = self._choice(defn, model, reasoning)
        return self.jobs.start("preview", lambda ctx: self._run_preview(
            defn, source, policy, ctx, model=model, reasoning=reasoning),
            target_id=transform_id, manifest={"source_hash": fingerprint(source),
            "definition_revision": defn.prompt_revision, "policy": policy})

    def create_session(self, source, operation_id, *, transform_id="builtin:prompt_engineer",
                       project_id=None, use_memory=False, depth="auto",
                       excluded_context_ids=(), pinned_context_ids=(), source_context=None):
        definition = self._definition(transform_id)
        session = self.sessions.create(source, definition.to_json(),
                                       self._policy(project_id, use_memory, depth,
                                           excluded_context_ids, pinned_context_ids), operation_id,
                                       context=source_context, validate=self.validate_pack)
        return self._session_view(session)

    def session_for_use(self, session_id, expected_revision):
        session = self.sessions.read(session_id)
        if session["revision"] != expected_revision:
            raise ValueError("stale_revision")
        if not all(self.pack_valid(pack) for pack in self.sessions.contexts(session)):
            raise ValueError('context_revoked')
        return session

    def session_view(self, session_id):
        """Keep saved user text, but do not redisclose revoked memory previews."""
        return self._session_view(self.sessions.read(session_id))

    def _session_view(self, session):
        revoked = set()
        for revision in session['revisions']:
            inherited = revision['kind'] not in ('source', 'manual') and revision['parent_revision'] in revoked
            if inherited or not self.pack_valid(revision.get('context') or {}):
                revoked.add(revision['revision_id'])
                revision['context'] = {'items': [], 'retrieval_mode': 'revoked', 'warnings': [
                    'This version used context that changed or was forgotten. Start from the original version or save a deliberate manual edit.']}
                revision['result'] = {}
        return session

    def refine(self, session_id, expected_revision, instruction, *, model=None, reasoning=None):
        bounded_text(instruction, 8000)
        session = self.session_for_use(session_id, expected_revision)
        source_contexts = self.sessions.contexts(session)
        definition = TransformDefinition.from_json(session["definition"])
        model, reasoning = self._choice(definition, model, reasoning)

        def work(ctx):
            pack = self._context(session["prompt"] + "\n" + instruction, session["policy"], "refinement")
            result = self._run_preview(definition, session["prompt"], session["policy"], ctx,
                                       model=model, reasoning=reasoning, followup=instruction,
                                       constraints=self.sessions.instructions(session), pack=pack,
                                       source_contexts=source_contexts)
            ctx.progress("publishing_revision")
            activity = getattr(self, "activity", None)
            if activity is not None and self.patterns is not None:
                activity.observe(instruction, source_id="refinement:" + fingerprint([
                    session_id, expected_revision, instruction]), kind="user_instruction",
                    project_id=session["policy"]["project_id"])
            return ctx.publish(lambda: self.sessions.append(
                session_id, expected_revision, result["output"],
                base_revision=session["canonical_revision"], instruction=instruction,
                context=pack, result=result, kind="assistant", keep_alternative=True,
                validate=lambda db, value: self.validate_pack(db, value) and all(
                    self.validate_pack(db, source) for source in source_contexts)))
        return self.jobs.start("refinement", work, target_id=session_id, priority=0,
                               manifest={"session_revision": expected_revision,
                                         "instruction_hash": fingerprint(instruction)})

    def edit(self, session_id, expected_revision, prompt):
        result = self.sessions.append(session_id, expected_revision, prompt, kind="manual")
        result['session'] = self._session_view(result['session'])
        return result

    def set_session_policy(self, session_id, expected_revision, **changes):
        with self.jobs._lock:
            old = self.sessions.read(session_id)
            if old["revision"] != expected_revision:
                raise ValueError("stale_revision")
            policy = self._policy(**{**old["policy"], **changes})
            self.jobs.cancel_target(session_id)
            return self._session_view(self.sessions.set_policy(session_id, expected_revision, policy))

    def clear_session(self, session_id, expected_revision):
        self.jobs.cancel_target(session_id)
        return self.sessions.clear(session_id, expected_revision)

    def select_revision(self, session_id, expected_revision, revision_id):
        return self._session_view(self.sessions.select(session_id, expected_revision, revision_id,
                                                       validate=self.validate_pack))

    def author(self, intention, *, examples=(), project_id=None, use_memory=False,
               model=None, reasoning=None, draft_id=None, expected_revision=None, instruction="",
               definition=None, excluded_context_ids=(), pinned_context_ids=()):
        bounded_text(intention, 8000)
        if not isinstance(examples, (tuple, list)) or len(examples) > 6:
            raise ValueError("invalid_examples")
        for example in examples:
            if not isinstance(example, dict) or set(example) != {"before", "after"}:
                raise ValueError("invalid_example")
            for value in example.values():
                bounded_text(value)
        policy = self._policy(project_id, use_memory, "auto", excluded_context_ids, pinned_context_ids)
        previous = None
        edited = executable_definition(definition) if definition is not None else None
        if draft_id is not None:
            previous = self.drafts.read(draft_id)
            if previous["revision"] != expected_revision:
                raise ValueError("stale_revision")
            if not all(self.pack_valid(p) for p in previous["context"].get("packs", [])):
                raise ValueError("context_revoked")
            intention, policy = previous["intention"], previous["policy"]
        if model is None and reasoning is None:
            model, reasoning = claude.ROLE_RECOMMENDED["definition_authoring"]
        model, reasoning = self._choice(self._definition("builtin:prompt_engineer"), model, reasoning)

        def work(ctx):
            pack = self._context(intention, policy, "authoring")

            def retrieve(query, purpose):
                return self._context(query, policy, purpose)

            loop = AuthoringLoop(self.transformer, model=model, reasoning=reasoning,
                context_current=lambda: self.pack_valid(pack) and
                    all(self.pack_valid(item) for item in loop.contexts),
                definitions=self.transforms.definitions, retrieve=retrieve,
                patterns=lambda: self.patterns(policy["project_id"])
                    if policy["project_id"] or policy["use_memory"] else [],
                preview=lambda draft, sample, context, budget: self._run_preview(
                    executable_definition(draft), sample, policy, context,
                    pack=pack, budget=budget))
            generated = loop.run(intention, ctx, previous=definition if edited else
                                 (previous["definition"] if previous else None),
                                 examples=examples, instruction=instruction)
            # Every retrieved pack must remain eligible at the final commit.
            contexts = [pack, *generated["contexts"]]

            def validate(db, bundle):
                return all(self.validate_pack(db, p) for p in bundle.get("packs", []))

            ctx.progress("publishing_definition")
            return ctx.publish(lambda: self.drafts.publish(
                generated, intention=intention, policy=policy, context={"packs": contexts},
                draft_id=draft_id, expected_revision=expected_revision,
                instruction=instruction, validate=validate))
        return self.jobs.start("authoring", work, target_id=draft_id,
                               manifest={"intention_hash": fingerprint(intention),
                                         "policy": policy, "draft_revision": expected_revision})

    def author_refine(self, draft_id, expected_revision, instruction, **choices):
        bounded_text(instruction, 8000)
        return self.author("refinement", draft_id=draft_id,
                           expected_revision=expected_revision, instruction=instruction, **choices)

    def save_authored(self, draft_id, expected_revision, operation_id, definition=None):
        return self.drafts.save(draft_id, expected_revision, operation_id,
            definition=definition,
            validate=lambda db, bundle: all(self.validate_pack(db, p)
                                            for p in bundle.get("packs", [])))

    def read_job(self, job_id, after_sequence=0):
        result = self.jobs.read(job_id, after_sequence)
        payload = result.get("result") or {}
        context = payload.get("context") or (payload if "revocation_revision" in payload else None)
        session = payload.get('session')
        inherited = ()
        if session is not None:
            branch = {**session, 'canonical_revision': payload.get('revision_id', session['canonical_revision'])}
            inherited = self.sessions.contexts(branch)
        if (context and not all(self.pack_valid(p) for p in context.get("packs", [context]))) \
                or not all(self.pack_valid(p) for p in inherited):
            result.update(result=None, status="failed", phase="context_revoked", error="context_revoked")
        elif session is not None:
            payload['session'] = self._session_view(session)
        return result
