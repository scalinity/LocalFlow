"""M10 corpus drivers, part B: store concurrency and admission, snippet
triggers, placeholders, collisions, rich snippets and rewrite
authorization (registers into ``m10_drivers.DRIVERS``)."""

from __future__ import annotations

import json
import threading

from m10_drivers import Outcome, driver, verdict, run_job, harness
import m10_world as w
import test_m10_remediation as rem

from localflow.v2 import profiles_store as ps
from localflow.v2 import snippets as snip_mod
from localflow.v2 import vocabulary as vocab
from localflow.v2.normalize import (ContextSnapshot, NormalizationPolicy,
                                    normalize)

POLICY = NormalizationPolicy()


def snip(sid="snip:alpha", trigger="quick reply", content="ACK", **kw):
    return snip_mod.Snippet(snippet_id=sid, trigger=trigger,
                            name=kw.pop("name", "Synthetic reply"),
                            content=content, **kw)


def norm(text, snippets=(), policy=POLICY, **ctx):
    snap = snip_mod.SnippetSnapshot(list(snippets)) if snippets else None
    return normalize(text, policy, ContextSnapshot(snippets=snap, **ctx))


def edits(res, cls):
    return [e for e in res.edits if e.cls == cls]


# ---- store concurrency --------------------------------------------------------

def _race_barriers(reached):
    return ["both reads complete (writer-side read: structural)"] + reached


@driver("M10-C043", "M10-C204")
def correlated_style(c):
    h, *_ = harness()
    try:
        styles = h.d._styles
        rid = styles.add_rule(name="Alpha", scope_kind="app",
                              scope_value="com.example.alpha", mode="raw")
        ev = threading.Event()
        restore = rem._hold_view_until(styles, "rule", ev)
        try:
            a, b, reached = rem._race(
                h.d.store,
                lambda: styles.update_rule(rid, scope_kind="category",
                                           scope_value="coding"),
                lambda: styles.update_rule(rid,
                                           scope_value="com.example.beta"),
                view_hook=lambda done: threading.Thread(
                    target=lambda: (done.wait(15), ev.set()),
                    daemon=True).start())
        finally:
            restore()
        row = w.raw_rows(h.d.store, "style_rules", "rule_id")[0]
        public_ok = len(styles.rules()) == 1
    finally:
        h.close()
    return verdict({
        "no_invalid_tuple": (row[2], row[3]) == ("category", "coding"),
        "stale_patch_refused_explicitly": isinstance(b, ValueError),
        "first_patch_committed": not isinstance(a, Exception),
        "public_rules_usable": public_ok},
        {"row": list(row), "second": type(b).__name__},
        _race_barriers(reached))


@driver("M10-C044")
def disjoint_style(c):
    rem.c03_disjoint_patches_both_survive()
    return Outcome("PASS", {"delegated": "c03_disjoint_patches_both_survive",
                            "policy": "changed-field merge; revisions"
                                      " distinct and monotonic"})


@driver("M10-C045", "M10-C206")
def correlated_snippet(c):
    h, *_ = harness()
    try:
        store = h.d._snip_store
        sid = store.add_snippet(trigger="quick reply", name="x",
                                content="https://example.invalid/path")
        ev = threading.Event()
        restore = rem._hold_view_until(store, "snippet", ev)
        try:
            a, b, reached = rem._race(
                h.d.store, lambda: store.update_snippet(sid, kind="url"),
                lambda: store.update_snippet(sid, content="two words"),
                view_hook=lambda done: threading.Thread(
                    target=lambda: (done.wait(15), ev.set()),
                    daemon=True).start())
        finally:
            restore()
        row = w.raw_rows(h.d.store, "snippets", "snippet_id")[0]
        snap_ok = len(snip_mod.SnippetSnapshot(store.snippets()).index) == 1
    finally:
        h.close()
    return verdict({
        "no_invalid_url_row": row[3] == "url"
        and row[4] == "https://example.invalid/path",
        "stale_patch_refused": isinstance(b, ValueError),
        "revisions_monotonic": row[7] == 2,
        "snapshot_valid": snap_ok}, {"row": list(row)},
        _race_barriers(reached))


def _update_delete(c, entity):
    h, *_ = harness()
    try:
        if entity == "style":
            svc = h.d._styles
            eid = svc.add_rule(name="Alpha", mode="clean")
            read, upd, dele, table, key, meta = (
                "rule", lambda: svc.update_rule(eid, mode="raw"),
                lambda: svc.delete_rule(eid), "style_rules", "rule_id",
                "style_rules")
        else:
            svc = h.d._snip_store
            eid = svc.add_snippet(trigger="quick reply", name="x",
                                  content="ACK")
            read, upd, dele, table, key, meta = (
                "snippet", lambda: svc.update_snippet(eid, content="B"),
                lambda: svc.delete_snippet(eid), "snippets", "snippet_id",
                "snippets")
        ev = threading.Event()
        restore = rem._hold_view_until(svc, read, ev)
        before = w.meta_counter(h.d.store, meta)
        try:
            a, b, reached = rem._race(
                h.d.store, dele, upd,
                view_hook=lambda done: threading.Thread(
                    target=lambda: (done.wait(15), ev.set()),
                    daemon=True).start())
        finally:
            restore()
        rows = w.raw_rows(h.d.store, table, key)
        after = w.meta_counter(h.d.store, meta)
    finally:
        h.close()
    return verdict({"no_recreated_row": rows == [],
                    "explicit_not_found": isinstance(b, ps.NotFoundError),
                    "no_ghost_bump": after == before + 1},
                   {"second": type(b).__name__},
                   ["update read complete (writer-side: structural)",
                    "delete committed"] + reached)


@driver("M10-C046", "M10-C205")
def style_update_delete(c):
    return _update_delete(c, "style")


@driver("M10-C047")
def snippet_update_delete(c):
    return _update_delete(c, "snippet")


@driver(*[f"M10-C{n:03d}" for n in range(48, 68)])
def malformed_boolean(c):
    s = c["setup"]
    entity, field, value = s["entity"], s["field"], s["malformed_value"]
    h, sup, _ = harness()
    try:
        if entity == "style":
            eid = h.d._styles.add_rule(name="R", mode="raw", enabled=False)
            call = lambda v: h.d._styles.update_rule(eid, **{field: v})
            read = lambda: w.raw_rows(h.d.store, "style_rules", "rule_id")[0]
            meta = lambda: w.meta_counter(h.d.store, "style_rules")
        elif entity == "snippet":
            eid = h.d._snip_store.add_snippet(
                trigger="quick reply", name="x", content="ACK",
                enabled=False, allow_rewrite=False)
            call = lambda v: h.d._snip_store.update_snippet(eid, **{field: v})
            read = lambda: w.raw_rows(h.d.store, "snippets", "snippet_id")[0]
            meta = lambda: w.meta_counter(h.d.store, "snippets")
        else:
            eid = "builtin:polish"
            h.d._tf_store.update_transform(eid, auto_apply=False,
                                           enabled=False) \
                if field == "enabled" else None
            call = lambda v: h.d._tf_store.update_transform(eid, **{field: v})
            read = lambda: [r for r in w.raw_rows(h.d.store, "transforms",
                                                  "transform_id")
                            if r[0] == eid][0]
            meta = lambda: h.d._tf_store.revision()
        before, rev0 = read(), meta()
        refused = False
        try:
            call(value)
        except (ValueError, TypeError):
            refused = True
        after, rev1 = read(), meta()
        # Positive controls: real True then False update and read back.
        call(True)
        t = read()
        call(False)
        f = read()
    finally:
        h.close()
    return verdict({"refused_before_mutation": refused,
                    "row_unchanged": before == after,
                    "revision_unchanged": rev0 == rev1,
                    "true_updates": True in (t[-2], t[-3]) or 1 in
                    (t[-2], t[-3]) or t[1:] != f[1:],
                    "false_updates": f != t},
                   {"malformed": repr(value)})


@driver("M10-C068")
def same_trigger_creates(c):
    h, *_ = harness()
    try:
        store = h.d._snip_store
        a, b, reached = rem._race(
            h.d.store,
            lambda: store.add_snippet(trigger="quick reply", name="a",
                                      content="A"),
            lambda: store.add_snippet(trigger="QUICK REPLY", name="b",
                                      content="B"))
        rows = w.raw_rows(h.d.store, "snippets", "snippet_id")
        events = "\n".join(w.app_events(h))
    finally:
        h.close()
    return verdict({"one_logical_trigger": len(rows) == 1,
                    "explicit_duplicate_conflict": isinstance(b, ValueError),
                    "no_content_in_events": '"B"' not in events
                    and "QUICK REPLY" not in events},
                   {"second": type(b).__name__}, reached)


# ---- snippet triggers -------------------------------------------------------------

QR = snip()


@driver("M10-C069", "M10-C070", "M10-C071", "M10-C072", "M10-C073",
        "M10-C074", "M10-C075")
def trigger_separator(c):
    text = c["setup"]["input"]
    # The corpus JSON writes the two Unicode separators into the input
    # verbatim for C072/C073 (visible only by code point).
    res = norm(text, [QR])
    pos = norm("quick reply", [QR])
    return verdict({"no_edit_across_separator": not edits(res, "snippet"),
                    "words_and_separator_kept": res.text == text,
                    "positive_control_expands": pos.text == "ACK"},
                   {"input": repr(text), "output": repr(res.text)})


@driver("M10-C076", "M10-C077", "M10-C078")
def trigger_ordinary(c):
    res = norm(c["setup"]["input"], [QR])
    return verdict({"exact_payload": res.text == "ACK",
                    "one_rule": [e.rule_id for e in edits(res, "snippet")]
                    == ["snip:alpha"]})


@driver("M10-C079")
def trigger_edge_punct(c):
    res = norm("quick reply.", [QR])
    e = edits(res, "snippet")
    return verdict({"period_kept": res.text == "ACK.",
                    "span_owns_phrase": bool(e) and e[0].input_text
                    == "quick reply"})


@driver("M10-C080", "M10-C081")
def trigger_literal(c):
    res = norm(c["setup"]["input"], [QR])
    return verdict({"zero_snippet_edits": not edits(res, "snippet"),
                    "no_ack": "ACK" not in res.text},
                   {"output": res.text},
                   note="recognized forms: a double-quoted zone and the"
                        " literal escape 'write the words'")


@driver("M10-C082")
def disabled_duplicate(c):
    ss = [snip(s["snippet_id"], s["trigger"], s["content"],
               enabled=s["enabled"]) for s in c["setup"]["snippets"]]
    res = norm("quick reply", ss)
    return verdict({"ack_from_alpha": res.text == "ACK"
                    and edits(res, "snippet")[0].rule_id == "snip:alpha"})


@driver("M10-C083")
def enabled_duplicate(c):
    ss = [snip(s["snippet_id"], s["trigger"], s["content"])
          for s in c["setup"]["snippets"]]
    snap = snip_mod.SnippetSnapshot(ss)
    res = norm("quick reply", ss)
    return verdict({"no_arbitrary_expansion": not edits(res, "snippet"),
                    "conflict_visible": [c2["reason"]
                                         for c2 in snap.conflicts_json()]
                    == ["duplicate_trigger"]})


@driver("M10-C084")
def second_pass(c):
    ss = [snip("s1", "alpha phrase", "beta phrase"),
          snip("s2", "beta phrase", "FINAL")]
    first = norm("alpha phrase", ss)
    second = norm(first.text, ss)
    rem.c31_coordinator_runs_one_normalization_pass()
    # m10-policy-r1 (AUDIT-31): the coordinator makes ONE pass; a
    # text-only second call has lost the generated-span provenance and
    # may chain — the narrowed, documented idempotence claim.
    return verdict({"first_pass_beta": first.text == "beta phrase",
                    "text_only_second_pass_documented": second.text
                    == "FINAL",
                    "coordinator_one_pass": True},
                   {"second_pass": second.text})


# ---- placeholders ---------------------------------------------------------------

def _slot(trigger, content, spoken):
    s = snip("s:slot", trigger, content)
    text = f"{trigger} {spoken}".rstrip() if spoken else trigger
    return norm(text, [s]), s


@driver("M10-C085", "M10-C086", "M10-C087")
def one_slot(c):
    s = c["setup"]
    res, sn = _slot(s["trigger"], s["content"], s["spoken_values"])
    want = {"M10-C085": "Dear Ada", "M10-C086": "Dear ",
            "M10-C087": "Dear Ada comma Lin"}[c["id"]]
    prot = snip_mod.protected_output_spans(
        res, snip_mod.SnippetSnapshot([sn]))
    return verdict({"exact_payload": res.text == want,
                    "protected_generated_span": bool(prot)},
                   {"output": repr(res.text)})


@driver("M10-C088")
def two_slots_template(c):
    s = c["setup"]
    sn = snip("s:send", s["trigger"], s["content"])
    res = norm("send template Ada comma Review", [sn])
    want = "To: Ada\nSubject: Review\nhttps://example.invalid/A?x=1"
    e = edits(res, "snippet")
    prov = snip_mod.applied_definition(sn, e[0]) if e else {}
    return verdict({"exact_template": res.text == want,
                    "slot_provenance": prov.get("slots")
                    == [{"name": "recipient", "value": "Ada"},
                        {"name": "subject", "value": "Review"}]},
                   {"output": repr(res.text)})


@driver("M10-C089", "M10-C090", "M10-C091")
def slot_policy(c):
    s = c["setup"]
    res, _ = _slot(s["trigger"], s["content"], s["spoken"])
    want = {"M10-C089": "Ada | ", "M10-C090": "Ada | Review comma Tomorrow",
            "M10-C091": "Review | "}[c["id"]]
    return verdict({"documented_slot_policy": res.text == want},
                   {"output": repr(res.text)})


@driver("M10-C092")
def written_comma(c):
    s = c["setup"]
    res, _ = _slot(s["trigger"], s["content"], s["spoken"])
    # m10-policy-r1: a written comma inside a value stays part of the
    # value verbatim (only the spoken word "comma" separates slots).
    nl, _ = _slot(s["trigger"], s["content"], "Ada\nReview")
    return verdict({"written_comma_in_value": res.text == "Ada, Review | ",
                    "newline_not_swallowed": nl.text == "Ada | \nReview"},
                   {"output": repr(res.text), "newline": repr(nl.text)})


@driver("M10-C093", "M10-C094")
def slot_cap(c):
    s = c["setup"]
    res, _ = _slot(s["trigger"], s["content"], " ".join(s["words"]))
    n = len(s["words"])
    if n <= 24:
        ok = res.text == " ".join(s["words"])
    else:
        ok = not edits(res, "snippet") and res.text.startswith(
            "slot template value")
    return verdict({"cap_policy": ok}, {"words": n})


@driver("M10-C095")
def slot_newline(c):
    res, _ = _slot("slot template", "{{slot_1}}", "Ada\nDo not deploy")
    return verdict({"line_not_swallowed": res.text == "Ada\nDo not deploy"},
                   {"output": repr(res.text)})


@driver("M10-C096")
def slot_quote(c):
    res, _ = _slot("slot template", "{{slot_1}}", 'Ada "Do not deploy"')
    return verdict({"quote_not_consumed": res.text == 'Ada "Do not deploy"',
                    "one_expansion": len(edits(res, "snippet")) == 1},
                   {"output": repr(res.text)})


@driver("M10-C097")
def slot_unicode(c):
    h, sup, _ = harness()
    try:
        h.d._snip_store.add_snippet(trigger="slot template", name="s",
                                    content="Name: {{slot_1}}!")
        text, job = run_job(h, "slot template Zoë actually Zora")
        spans = (sup.clean_kwargs or {}).get("protected_spans") or []
    finally:
        h.close()
    return verdict({"template_exact": text.startswith("Name: ")
                    and text.endswith("!"),
                    "value_spoken_verbatim": "Zoë actually Zora" in text,
                    "generated_span_protected": any(
                        k == "generated" for _s, _e, k in spans)},
                   {"output": text},
                   note="no correction rule applies to slot text in the"
                        " fixture; the spoken value is kept verbatim")


# ---- snippet / skill collisions ---------------------------------------------------

def _skill_policy(aliases):
    return NormalizationPolicy(registered_skills=aliases)


@driver("M10-C098", "M10-C099")
def bare_alias_vs_slash(c):
    sn = snip("s:cr", "code review", "REVIEW")
    pol = _skill_policy({"code review": "code-review"})
    bare = norm("code review", [sn], pol)
    slash = norm("slash code review", [sn], pol)
    prev = snip_mod.preview_collisions(sn, [], policy=pol)
    kinds = {p["kind"] for p in prev}
    return verdict({"runtime_bare_snippet": bare.text == "REVIEW",
                    "runtime_slash_skill": slash.text == "/code-review",
                    "preview_no_bare_ambiguity": "ambiguous_with_skill"
                    not in kinds,
                    "preview_names_slash_skill": "skill_on_slash" in kinds},
                   {"preview": prev})


@driver("M10-C100")
def slash_trigger_same_span(c):
    sn = snip("s:bs", "slash brainstorm", "SNIP")
    pol = _skill_policy({"brainstorm": "brainstorm"})
    res = norm("slash brainstorm", [sn], pol)
    prev = snip_mod.preview_collisions(sn, [], policy=pol)
    reasons = {(r.cls, r.reason) for r in res.rejected}
    return verdict({"both_literal": res.text == "slash brainstorm",
                    "ambiguity_recorded": ("snippet", "ambiguous_same_span")
                    in reasons,
                    "preview_agrees": any(p["kind"] == "ambiguous_with_skill"
                                          for p in prev)})


@driver("M10-C101")
def snippet_beats_term(c):
    h, *_ = harness()
    try:
        h.d._vocab.add_entry("OtherTerm", ["code review"], approved=True)
        h.d._snip_store.add_snippet(trigger="code review", name="r",
                                    content="REVIEW")
        text, job = run_job(h, "code review")
        vocab_hits = job.get("vocab_hits")
        snip_hits = job.get("snippet_hits")
    finally:
        h.close()
    return verdict({"snippet_wins": text == "REVIEW",
                    "usage_only_applied": vocab_hits == 0
                    and snip_hits == 1})


@driver("M10-C102")
def two_equal_skills(c):
    from localflow.v2.developer import skills as sk
    reg = sk.SkillRegistry([sk.SkillRecord(name="review-a",
                                           aliases=("review",)),
                            sk.SkillRecord(name="review-b",
                                           aliases=("review",))])
    res = normalize("slash review", NormalizationPolicy(
        registered_skills=dict(reg.policy_skills)), None)
    return verdict({"no_arbitrary_token": "/review-" not in res.text,
                    "ambiguity_retained": [c2["reason"]
                                           for c2 in reg.to_json()
                                           ["conflicts"]]
                    == ["ambiguous_skill_alias"]})


@driver("M10-C103")
def inactive_vocab_preview(c):
    h, *_ = harness(bundle="com.microsoft.VSCode", category="ide",
                    workspace="ProjectA")
    try:
        d = h.d._vocab.add_entry("quick-reply", ["quick reply"],
                                 kind="skill", approved=True)
        h.d._vocab.set_enabled(d, False)
        h.d._vocab.add_entry("other-reply", ["quick reply"], kind="skill",
                             approved=True, scope_kind="workspace",
                             scope_value="OtherWorkspace")
        h.d._snip_store.add_snippet(trigger="quick reply", name="r",
                                    content="ACK", snippet_id="snip:alpha")
        text, _ = run_job(h, "quick reply")
        col = h.d.hubSnippetCollisionPreview("quick reply",
                                             snippet_id="snip:alpha",
                                             content="ACK")
    finally:
        h.close()
    return verdict({"runtime_no_conflict": text == "ACK",
                    "preview_same_decision": not any(
                        p["kind"].startswith("ambiguous") for p in col)},
                   {"preview": col})


# ---- rich snippets / allow_rewrite ------------------------------------------------

@driver("M10-C104")
def rich_plain_honest(c):
    h, sup, _ = harness()
    try:
        sid = h.d._snip_store.add_snippet(
            trigger="quick reply", name="r", kind="rich",
            content="Plain synthetic signature",
            content_rtf="{\\rtf1 Synthetic rich signature}")
        stored = h.d._snip_store.snippet(sid)
        text, job = run_job(h, "quick reply", deliver=True)
        pasted = list(h.d._insertion.pastes)
    finally:
        h.close()
    return verdict({"rtf_round_trips": stored.content_rtf
                    == "{\\rtf1 Synthetic rich signature}",
                    "plain_inserted": pasted == ["Plain synthetic signature"],
                    "no_rtf_claim": "rtf" not in json.dumps(
                        job.get("file_references") or {})})


@driver("M10-C105")
def rich_export_detached(c):
    sn = snip("s:r", kind="rich", content_rtf="{\\rtf1 Synthetic}")
    snap = snip_mod.SnippetSnapshot([sn])
    before, rev = json.dumps(snap.to_json(), sort_keys=True), snap.revision
    exported = snap.to_json()
    exported["conflicts"].append({"x": 1})
    exported["revision"] = "forged"
    return verdict({"payload_unchanged": json.dumps(
        snap.to_json(), sort_keys=True) == before,
        "revision_unchanged": snap.revision == rev})


@driver("M10-C106", "M10-C107", "M10-C219")
def captured_rewrite(c):
    allow = c["id"] == "M10-C107"
    h, sup, ctx = w.hooked_harness()
    barriers = []
    try:
        sid = h.d._snip_store.add_snippet(
            trigger="quick reply", name="r",
            content="Keep UserID\nhttps://example.invalid/A",
            allow_rewrite=allow)

        def edit():
            barriers.append("A frozen snippet")
            if c["id"] == "M10-C219":
                h.d._snip_store.delete_snippet(sid)
            else:
                h.d._snip_store.update_snippet(sid, allow_rewrite=not allow)
            barriers.append("before cleanup protection mapping")
        ctx.on_finalize = edit
        text, job = run_job(h, "quick reply")
        ctx.on_finalize = None
        spans = (sup.clean_kwargs or {}).get("protected_spans") or []
        tb, _ = run_job(h, "quick reply")
    finally:
        h.close()
    generated = [s for s in spans if s[2] == "generated"]
    return verdict({
        "a_expanded_exactly": text == "Keep UserID\nhttps://example.invalid/A",
        "captured_authorization_governs": (not generated) if allow
        else bool(generated),
        "b_follows_current_store": tb == ("quick reply"
                                          if c["id"] == "M10-C219"
                                          else text)},
        {"protected": spans}, barriers)


@driver("M10-C108")
def missing_snapshot_protects(c):
    res = norm("quick reply", [QR])
    spans = snip_mod.protected_output_spans(res, None)
    return verdict({"unavailable_definition_protects": spans
                    == [(0, len("ACK"))]})


@driver("M10-C109")
def cleanup_failure_keeps_expansion(c):
    """Adjudicated (m10-policy-r1, the M03 contract): a cleanup WORKER
    failure makes the job recoverable — nothing is inserted — and its
    exact expansion is retained on the job and in the normalization
    evidence; an explicit retry runs under the fresh unscoped default,
    which carries no snippets, so today's set never re-expands it."""
    h, sup, _ = harness()
    try:
        h.d.consent.set("enabled", note="test")
        h.d._snip_store.add_snippet(trigger="quick reply", name="r",
                                    content="ACK")
        real = sup.clean

        def failing_clean(**k):
            from localflow.v2.supervisor import WorkerFailure
            raise WorkerFailure("worker_crash", "cleaning", attempt=1)
        sup.clean = failing_clean
        # Delivered: the main-thread finish releases the failed job, as
        # in the app (an undelivered one still reads as retrying).
        text, job = run_job(h, "quick reply", deliver=True)
        arts = w.all_artifacts(h.d.store, job["job_id"])
        norm = [a[3] for a in arts if a[1] == "normalized_text"]
        sup.clean = real
        h.d._snip_store.update_snippet(
            h.d._snip_store.snippets()[0].snippet_id, content="TODAY")
        out = h.d.hubRetryJob(job["job_id"])
        _fn, (rt, rj) = h.run_coordinator()
    finally:
        h.close()
    return verdict({"job_recoverable_not_inserted": job.get("failed")
                    is True and text == "",
                    "exact_expansion_retained": job.get("normalized")
                    == "ACK" and norm == ["ACK"],
                    "retry_never_reexpands": rt == "quick reply"},
                   {"retry": out, "retry_text": rt})
