"""Styles, Snippets (M10, Spec S15/S17) and Transforms (M11, Spec S16) —
the AppKit Hub's editor rules, one for one (hub.py ``_m10_*`` and
``_transform_*``):

- Add carries a pre-allocated id; repeating the SAME form after an
  unknown outcome reuses it (the store confirms or performs the write
  once), any other outcome retires it.
- Update sends only the fields changed since the editor was filled from
  its row (the page keeps that baseline); the store validates the merge
  against the row as it is now.
- Enable/Disable of a style or snippet names the rendered row's revision
  and a stale one is refused; a transform's has no revision (its store
  takes none).
- An unknown outcome is never reported as a failure.
"""

from __future__ import annotations

from .. import bridge as B
from ..bridge import Bool, Enum, List, Nullable, Obj, Int, Str

STYLE_SCOPES = ("global", "category", "app", "site", "workspace")
STYLE_MODES = ("raw", "clean", "polish", "concise", "prompt_engineer",
               "custom")
NUMBER_POLICIES = ("inherit", "technical", "standard")
SNIPPET_KINDS = ("plain", "rich", "url", "signature", "code", "prompt")
TRANSFORM_MODES = ("polish", "concise", "prompt_engineer", "custom")

STYLE_FORM = {"name": Str(max_len=200), "scope_kind": Enum(STYLE_SCOPES),
              "scope_value": Nullable(Str(max_len=300)),
              "mode": Enum(STYLE_MODES),
              "number_policy": Enum(NUMBER_POLICIES)}
SNIPPET_FORM = {"trigger": Str(max_len=200), "name": Str(max_len=200),
                "content": Str(max_len=50_000), "kind": Enum(SNIPPET_KINDS),
                "allow_rewrite": Bool()}
TRANSFORM_FORM = {"name": Str(max_len=200), "mode": Enum(TRANSFORM_MODES),
                  "prompt": Str(max_len=20_000),
                  "shortcut": Nullable(Str(max_len=1)),
                  "target_profiles": List(Str(max_len=80), max_items=20),
                  "auto_apply": Bool()}


def _partial(form):
    """The same fields, each optional (an Update's changed subset)."""
    out = {}
    for k, f in form.items():
        g = type(f).__new__(type(f))
        g.__dict__.update(f.__dict__)
        g.optional = True
        out[k] = g
    return out


def _m10_failed(e):
    from ....profiles_store import (NotFoundError, OutcomeUnknownError,
                                    StaleRevisionError)
    if isinstance(e, B.Outcome):
        raise e
    if isinstance(e, OutcomeUnknownError) or isinstance(e, TimeoutError):
        B.unknown("outcome_unknown")
    if isinstance(e, NotFoundError):
        B.refuse("not_found")
    if isinstance(e, StaleRevisionError):
        B.stale("changed_elsewhere")
    if isinstance(e, (ValueError, KeyError)):
        B.refuse(str(e).strip("'\""))
    raise e


def _tf_failed(e):
    if isinstance(e, B.Outcome):
        raise e
    if isinstance(e, TimeoutError):
        B.unknown("outcome_unknown")
    if isinstance(e, (ValueError, KeyError)):
        B.refuse(str(e).strip("'\""))
    raise e


def register(ctl):
    br = ctl.bridge
    st = ctl.state
    coord = ctl.coordinator
    pending = {}  # view -> {"form": dict, "id": str}

    def svc(view):
        s = ctl.spec.get(f"{view}_service")
        if s is None:
            B.unavailable(f"{view}_unavailable")
        return s

    def add(view, form, prefix, write, failed):
        from .... import ids
        cur = pending.get(view)
        new_id = cur["id"] if cur and cur["form"] == form \
            else ids.new_id(prefix)
        pending[view] = {"id": new_id, "form": form}
        try:
            write(new_id)
        except Exception as e:
            if not isinstance(e, TimeoutError):
                pending.pop(view, None)
            failed(e)
        pending.pop(view, None)
        getattr(st, f"reload_{view}")()
        return {"id": new_id, "confirmed": bool(cur and cur["id"] == new_id)}

    # ---- Styles ------------------------------------------------------------

    @br.command("styles.add", STYLE_FORM)
    def styles_add(p):
        s = svc("styles")
        value = p["scope_value"] if p["scope_kind"] != "global" else None
        return add("styles", p, "style", lambda i: s.add_rule(
            name=p["name"], scope_kind=p["scope_kind"], scope_value=value,
            mode=p["mode"], number_policy=p["number_policy"], rule_id=i),
            _m10_failed)

    @br.command("styles.update", {"rule_id": Str(max_len=80),
                                  "changes": Obj(_partial(STYLE_FORM))})
    def styles_update(p):
        s = svc("styles")
        if not p["changes"]:
            B.refuse("no_changes")
        try:
            updated = s.update_rule(p["rule_id"], **p["changes"])
        except Exception as e:
            st.reload_styles()
            _m10_failed(e)
        st.reload_styles()
        return {"revision": updated.revision}

    @br.command("styles.delete", {"rule_id": Str(max_len=80)})
    def styles_delete(p):
        s = svc("styles")
        try:
            s.delete_rule(p["rule_id"])
        except Exception as e:
            st.reload_styles()
            _m10_failed(e)
        st.reload_styles()
        return {}

    @br.command("styles.set_enabled", {"rule_id": Str(max_len=80),
                                       "revision": Int(lo=0),
                                       "enabled": Bool()})
    def styles_toggle(p):
        s = svc("styles")
        try:
            s.set_enabled(p["rule_id"], p["enabled"],
                          expected_revision=p["revision"])
        except Exception as e:
            st.reload_styles()
            _m10_failed(e)
        st.reload_styles()
        return {}

    @br.command("styles.preview", {"text": Str(max_len=2000),
                                   "mode": Enum(STYLE_MODES),
                                   "number_policy": Enum(NUMBER_POLICIES)})
    def styles_preview(p):
        if coord is None or not hasattr(coord, "hubPreviewPhrase"):
            B.unavailable()
        out = coord.hubPreviewPhrase(p["text"], mode=p["mode"],
                                     number_policy=p["number_policy"]) or {}
        if out.get("error"):
            B.refuse(f"preview_failed:{out['error']}")
        return {"output": out.get("output"), "changed": out.get("changed"),
                "scope": out.get("scope"), "mode": out.get("mode"),
                "edits": [{"before": e.get("before"), "after": e.get("after"),
                           "cls": e.get("cls")}
                          for e in out.get("edits") or ()],
                "rejected": [{"before": e.get("before"),
                              "reason": e.get("reason")}
                             for e in out.get("rejected") or ()]}

    # ---- Snippets ------------------------------------------------------------

    @br.command("snippets.add", SNIPPET_FORM)
    def snippets_add(p):
        s = svc("snippets")
        return add("snippets", p, "snip", lambda i: s.add_snippet(
            trigger=p["trigger"], name=p["name"] or p["trigger"],
            content=p["content"], kind=p["kind"],
            allow_rewrite=p["allow_rewrite"], snippet_id=i), _m10_failed)

    @br.command("snippets.update", {"snippet_id": Str(max_len=80),
                                    "changes": Obj(_partial(SNIPPET_FORM))})
    def snippets_update(p):
        s = svc("snippets")
        changes = dict(p["changes"])
        if not changes:
            B.refuse("no_changes")
        if "name" in changes and not changes["name"] and \
                changes.get("trigger"):
            changes["name"] = changes["trigger"]
        try:
            updated = s.update_snippet(p["snippet_id"], **changes)
        except Exception as e:
            st.reload_snippets()
            _m10_failed(e)
        st.reload_snippets()
        return {"revision": updated.revision}

    @br.command("snippets.delete", {"snippet_id": Str(max_len=80)})
    def snippets_delete(p):
        s = svc("snippets")
        try:
            s.delete_snippet(p["snippet_id"])
        except Exception as e:
            st.reload_snippets()
            _m10_failed(e)
        st.reload_snippets()
        return {}

    @br.command("snippets.set_enabled", {"snippet_id": Str(max_len=80),
                                         "revision": Int(lo=0),
                                         "enabled": Bool()})
    def snippets_toggle(p):
        s = svc("snippets")
        try:
            s.set_enabled(p["snippet_id"], p["enabled"],
                          expected_revision=p["revision"])
        except Exception as e:
            st.reload_snippets()
            _m10_failed(e)
        st.reload_snippets()
        return {}

    @br.command("snippets.collisions", {
        "trigger": Str(max_len=200), "content": Str(max_len=50_000),
        "kind": Enum(SNIPPET_KINDS),
        "snippet_id": Nullable(Str(max_len=80), optional=True)})
    def snippets_collisions(p):
        if coord is None or not hasattr(coord, "hubSnippetCollisionPreview"):
            B.unavailable()
        if not p["trigger"].strip():
            return {"collisions": []}
        out = coord.hubSnippetCollisionPreview(
            p["trigger"], snippet_id=p.get("snippet_id"),
            content=p["content"], kind=p["kind"]) or []
        return {"collisions": [{"kind": c.get("kind"),
                                "detail": c.get("detail")} for c in out]}

    # ---- Transforms ------------------------------------------------------------

    @br.command("transforms.add", TRANSFORM_FORM)
    def transforms_add(p):
        s = svc("transforms")
        return add("transforms", p, "tf", lambda i: s.add_transform(
            name=p["name"], mode=p["mode"], prompt=p["prompt"],
            shortcut=p["shortcut"] or None,
            target_profiles=tuple(p["target_profiles"]),
            auto_apply=p["auto_apply"], transform_id=i), _tf_failed)

    @br.command("transforms.update", {
        "transform_id": Str(max_len=200),
        "changes": Obj(_partial(TRANSFORM_FORM))})
    def transforms_update(p):
        s = svc("transforms")
        changes = dict(p["changes"])
        if not changes:
            B.refuse("no_changes")
        if "shortcut" in changes:
            changes["shortcut"] = changes["shortcut"] or None
        if "target_profiles" in changes:
            changes["target_profiles"] = tuple(changes["target_profiles"])
        try:
            updated = s.update_transform(p["transform_id"], **changes)
        except Exception as e:
            st.reload_transforms()
            _tf_failed(e)
        st.reload_transforms()
        return {"revision": updated.revision}

    @br.command("transforms.set_enabled", {
        "transform_id": Str(max_len=200), "enabled": Bool()})
    def transforms_toggle(p):
        s = svc("transforms")
        try:
            s.set_enabled(p["transform_id"], p["enabled"])
        except Exception as e:
            st.reload_transforms()
            _tf_failed(e)
        st.reload_transforms()
        return {}


# ---- read models ------------------------------------------------------------------


def _base(v, ctl, view):
    return {"loading": bool(v.get("loading")), "error": v.get("error"),
            "note": ctl.notes.get(view)}


def styles_model(ctl):
    v = ctl.state.views["styles"]
    data = v.get("data")
    out = _base(v, ctl, "styles")
    if data is None:
        out["rules"] = None
        return out
    eff = data.get("effective") or {}
    prof = eff.get("profile") or None
    out.update({
        "rules": [{k: r.get(k) for k in (
            "rule_id", "name", "scope", "mode", "number_policy",
            "profile_name", "enabled", "revision")}
            for r in data.get("rules") or ()],
        "invalid_rows": data.get("invalid_rows") or 0,
        "effective": None if not eff else {
            "profile": None if not prof else {k: prof.get(k) for k in (
                "mode", "effective_mode", "source", "category",
                "profile_name", "number_policy", "fallback_reason")},
            "next_job_mode": eff.get("next_job_mode"),
            "categories": list(eff.get("categories") or ()),
            "modes": list(eff.get("modes") or ()),
            "executable_modes": list(eff.get("executable_modes") or ())},
    })
    return out


def snippets_model(ctl):
    v = ctl.state.views["snippets"]
    data = v.get("data")
    out = _base(v, ctl, "snippets")
    if data is None:
        out["snippets"] = None
        return out
    out.update({
        "snippets": [{k: s.get(k) for k in (
            "snippet_id", "trigger", "name", "content", "kind",
            "allow_rewrite", "enabled", "revision")}
            for s in data.get("snippets") or ()],
        "conflicts": [{"trigger": c.get("trigger"),
                       "snippets": list(c.get("snippets") or ()),
                       "reason": c.get("reason")}
                      for c in data.get("conflicts") or ()],
    })
    return out


def transforms_model(ctl):
    v = ctl.state.views["transforms"]
    data = v.get("data")
    out = _base(v, ctl, "transforms")
    if data is None:
        out["transforms"] = None
        return out
    out.update({
        "transforms": [{k: t.get(k) for k in (
            "transform_id", "name", "mode", "origin", "description",
            "prompt", "edit_types", "shortcut", "target_profiles",
            "auto_apply", "enabled", "revision")}
            for t in data.get("transforms") or ()],
        "shortcut_conflicts": [
            {"shortcut": c.get("shortcut"),
             "transform_ids": list(c.get("transform_ids") or ())}
            for c in data.get("shortcut_conflicts") or ()],
    })
    return out


READ_MODELS = {"styles": styles_model, "snippets": snippets_model,
               "transforms": transforms_model}
