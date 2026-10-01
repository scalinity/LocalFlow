"""UI-safe read models: HubState view data → the plain data the page
renders. Each view picks its fields explicitly — nothing crosses because
it happened to be in a service's dict. Identifiers the page must echo
back (row ids, revisions, detail tokens) are included; storage details
the page has no use for (artifact paths, lease ids, raw event records)
are not.

Every model is rebuilt from the state as it is now, so a revocation or a
retention pass that scrubbed the state scrubs the page on the next flush.
"""

from __future__ import annotations

import datetime as dt


def _local_time(iso, tz):
    """'2026-09-29T09:45:00.000Z' → '9:45 am' in the History zone."""
    if not iso or tz is None:
        return None
    try:
        t = dt.datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return None
    if t.tzinfo is None:
        return None  # a zoneless instant is never guessed (S21)
    local = t.astimezone(tz)
    return f"{local.hour % 12 or 12}:{local.minute:02d} " \
           f"{'am' if local.hour < 12 else 'pm'}"


def _tz(ctl):
    return getattr(ctl.state.history_service, "tz", None)


def _row(r, tz):
    return {"kind": r.get("kind"), "id": r.get("id"),
            "date": r.get("date"),
            "time": _local_time(r.get("date_iso"), tz)
            if r.get("time_quality") != "unknown" else None,
            "time_quality": r.get("time_quality"),
            "app": r.get("app"), "mode": r.get("mode"),
            "state": r.get("state"), "state_reason": r.get("state_reason"),
            "preview": r.get("preview"), "has_audio": bool(r.get("has_audio"))}


def _groups(data, tz, max_rows=None):
    out, n = [], 0
    for g in (data or {}).get("groups") or ():
        rows = []
        for r in g.get("rows") or ():
            if max_rows is not None and n >= max_rows:
                break
            rows.append(_row(r, tz))
            n += 1
        if rows:
            out.append({"label": g.get("label"), "rows": rows})
    return out


def _base(v):
    return {"loading": bool(v.get("loading")), "error": v.get("error")}


# ---- Home ---------------------------------------------------------------------


def home(ctl):
    v = ctl.state.views["home"]
    data = v.get("data")
    out = _base(v)
    if data is None:
        out["data"] = None
        return out
    usage = data.get("usage") or None
    profile = data.get("profile")
    out["data"] = {
        "summary": data.get("summary"),
        "engine": data.get("engine"),
        "recovery": data.get("recovery"),
        "recent": _groups(data.get("recent"), _tz(ctl), max_rows=18)
        if data.get("recent") is not None else None,
        "recent_error": data.get("recent_error"),
        "usage": None if usage is None else {
            "dictations": usage.get("dictations"),
            "final_words": usage.get("final_words"),
            "wpm": usage.get("wpm"),
            "capture_seconds": usage.get("capture_seconds"),
            "range_first_day": usage.get("range_first_day")},
        "usage_error": data.get("usage_error"),
        "profile": _profile_summary(profile),
        "profile_available": ctl.state.profile_service is not None,
    }
    return out


def _profile_summary(p):
    if not p:
        return None
    measured = p.get("measured") or {}
    return {"state": p.get("state"),
            "invalidated_reason": p.get("invalidated_reason"),
            "computed_at_utc": p.get("computed_at_utc"),
            "eligible_words": measured.get("eligible_words"),
            "min_words_threshold": measured.get("min_words_threshold"),
            "cards": [{"title": c.get("title"), "kind": c.get("kind")}
                      for c in (p.get("cards") or ())][:3]}


# ---- History --------------------------------------------------------------------


def history(ctl):
    from ...history_queries import MODES, final_text
    v = ctl.state.views["history"]
    data = v.get("data")
    key = (v.get("selected_kind"), v.get("selected_id"))
    detail = v.get("detail") if v.get("detail_key") == key else None
    out = _base(v)
    out.update({
        "search": v.get("search") or "", "app": v.get("app"),
        "mode": v.get("mode"), "modes": list(MODES),
        "groups": _groups(data, _tz(ctl)) if data is not None else None,
        "total": (data or {}).get("total"),
        "selected": {"kind": key[0], "id": key[1]} if key[1] else None,
        "detail_loading": bool(v.get("detail_loading")),
        "detail_error": v.get("detail_error"),
        "detail": _history_detail(ctl, detail, final_text),
        "note": ctl.notes.get("history"),
    })
    return out


def _history_detail(ctl, d, final_text):
    if d is None:
        return None
    tz = _tz(ctl)
    lineage = []
    for s in d.get("lineage") or ():
        art = s.get("artifact")
        lineage.append({
            "stage": s.get("stage"), "label": s.get("label"),
            "present": bool(art and art.get("present")),
            "purged": bool(art and art.get("purged")),
            "text": art.get("text") if art and art.get("present") else None,
            "reason": s.get("reason") if art is None else None,
            "decision": s.get("decision")})
    audio = d.get("audio") or {}
    ins = d.get("insertion") or None
    return {
        "token": ctl.token_for("history", d),
        "kind": d.get("kind"), "job_id": d.get("job_id"),
        "captured_at_utc": d.get("captured_at_utc"),
        "time": _local_time(d.get("captured_at_utc"), tz)
        if d.get("time_quality") != "unknown" else None,
        "time_quality": d.get("time_quality"),
        "state": d.get("state"), "state_reason": d.get("state_reason"),
        "attempt": d.get("attempt"),
        "lineage_attempt": d.get("lineage_attempt"),
        "lineage_ambiguous": bool(d.get("lineage_ambiguous")),
        "app": d.get("app"),
        "final_stage": d.get("final_stage"),
        "final_text": final_text(d),
        "audio": {"available": bool(audio.get("available")),
                  "reason": audio.get("reason")},
        "insertion": None if not ins else {
            "state": ins.get("state"), "method": ins.get("method"),
            "reason_code": ins.get("reason_code")},
        "lineage": lineage,
    }


# ---- Dictionary --------------------------------------------------------------------


def dictionary(ctl):
    v = ctl.state.views["dictionary"]
    data = v.get("data")
    out = _base(v)
    out.update({
        "available": ctl.state.vocabulary_store is not None,
        "search": v.get("search") or "",
        "entries": None if data is None else [
            {"entry_id": e.get("entry_id"), "canonical": e.get("canonical"),
             "kind": e.get("kind"), "scope": e.get("scope"),
             "priority": e.get("priority"), "pinned": e.get("pinned"),
             "usage_count": e.get("usage_count"),
             "last_used_utc": e.get("last_used_utc"),
             "origin": e.get("origin"), "enabled": e.get("enabled"),
             "approved": e.get("approved"),
             "verification": e.get("verification"),
             "revision": e.get("revision"),
             "aliases": [{"alias": a.get("alias"),
                          "approved": a.get("approved")}
                         for a in e.get("aliases") or ()]}
            for e in data.get("entries") or ()],
        "note": ctl.notes.get("dictionary"),
    })
    return out


# ---- Settings -----------------------------------------------------------------------


def settings(ctl):
    v = ctl.state.views["settings"]
    data = v.get("data") or {}
    out = _base(v)
    out.update({
        "loaded": v.get("data") is not None,
        "collection_state": data.get("collection_state"),
        "retention": data.get("retention"),
        "usage": data.get("usage"),
        "config": ctl._config_summary(),
        "note": ctl.notes.get("settings"),
    })
    return out


# ---- dispatch --------------------------------------------------------------------


def unmodeled(ctl, view):
    """A view without its own read model shows nothing: raw service data
    never crosses because nobody picked its fields."""
    return {"loading": False, "error": "unmodeled", "data": None}


BUILDERS = {"home": home, "history": history, "dictionary": dictionary,
            "settings": settings}


def build(ctl, view):
    from . import surfaces
    fn = BUILDERS.get(view) or surfaces.READ_MODELS.get(view)
    return fn(ctl) if fn is not None else unmodeled(ctl, view)
